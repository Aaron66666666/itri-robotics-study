"""Tracker / Predictor / Commander logic for the vehicle (no ROS, unit-tested)."""
# Tracker   - person detections (camera boxes) -> range and bearing from the
# vehicle -> odometry-frame points -> tracks with stable ids. With the
# optional 360-degree lidar, the lidar gives the positions (it also
# sees beside and behind the vehicle) and the camera only labels
# a lidar track as a person (matched by bearing).
# Predictor - constant-velocity Kalman filter per track; predicts the next
# seconds and checks whether the person enters the corridor in
# front of the vehicle -> time to conflict and a risk level.
# Commander - scales the base controller's command by the risk: CLEAR keeps
# it, SLOW halves the forward speed, STOP stops; a stale prediction
# also stops (fail-safe). Every change is logged with its reason.
#
# Real-time parts are plain code on purpose: an LLM call takes 0.6-1 s and is
# not deterministic, which is not acceptable for a safety stop.

from __future__ import annotations

from dataclasses import dataclass, field
import math

# Camera: 640x480, horizontal fov 1.047 rad, 0.65 m ahead of the base origin.
IMG_W, IMG_H, HFOV = 640, 480, 1.047
FOCAL = (IMG_W / 2) / math.tan(HFOV / 2)  # ~554 px
CAM_X = 0.65
# range = RANGE_K / box height (px); calibrated with Gazebo ground truth
# (tools/team/calibrate_person.py). Pinhole value for a 1.7 m person: 554*1.7.
RANGE_K = 989.1  # calibrated 2026-11-27 (tools/team/calibrate_person.py)

# Vehicle footprint (chassis 2.0 x 1.0 m, centred 0.15 m behind the origin).
HALF_WIDTH = 0.5
FRONT = 0.85
REAR = -1.15
PERSON_R = 0.25          # body radius: gap = distance to the footprint - PERSON_R
MARGIN = 0.4             # extra lateral clearance
LOOKAHEAD = 2.5          # m ahead of the front bumper that counts as "in the way"

# 360-degree 2D lidar on the chassis, 0.9 m above the ground: it sees people,
# but not the cup on its table or the parked vehicle (both lower than 0.8 m).
LIDAR_X = -0.15          # in the base frame (chassis centre)
BODY_DEPTH = 0.1         # the scan hits the near side of a body: centre is farther
MAP_RES = 0.1            # static map cells (m), odometry frame


def measure(box, conf: float = 1.0):
    """Person box (x1, y1, x2, y2) -> (range m, bearing rad, left positive)."""
    x1, y1, x2, y2 = box
    h = max(1.0, y2 - y1)
    rng = RANGE_K / h
    u = (x1 + x2) / 2
    bearing = math.atan2(-(u - IMG_W / 2), FOCAL)
    return rng, bearing


def cluster_scan(ranges, angle_min, angle_inc, range_min=0.3, range_max=10.0,
                 gap=0.3, max_extent=1.2, min_points=2, with_points=False):
    """Cluster LaserScan ranges -> centres (x, y) of compact clusters, lidar frame."""
    # with_points: (x, y, [points]) per cluster, for the static-map check.
    pts = []
    for i, r in enumerate(ranges):
        if math.isfinite(r) and range_min < r < range_max * 0.99:
            a = angle_min + i * angle_inc
            pts.append((i, r * math.cos(a), r * math.sin(a)))
    clusters, cur = [], []
    for p in pts:  # neighbouring rays (one missing ray allowed) closer than gap
        if cur and (p[0] - cur[-1][0] > 2 or math.dist(p[1:], cur[-1][1:]) > gap):
            clusters.append(cur)
            cur = []
        cur.append(p)
    if cur:
        clusters.append(cur)
    n = len(ranges)  # a full turn wraps around: join the last and the first cluster
    if (len(clusters) > 1 and clusters[0][0][0] <= 1 and clusters[-1][-1][0] >= n - 2
            and math.dist(clusters[0][0][1:], clusters[-1][-1][1:]) <= gap):
        clusters[0] = clusters.pop() + clusters[0]
    out = []
    for c in clusters:
        if len(c) < min_points or math.dist(c[0][1:], c[-1][1:]) > max_extent:
            continue  # single rays (noise) and long surfaces (walls) are not people
        cx = sum(q[1] for q in c) / len(c)
        cy = sum(q[2] for q in c) / len(c)
        d = math.hypot(cx, cy)
        centre = (cx + BODY_DEPTH * cx / d, cy + BODY_DEPTH * cy / d)
        out.append((*centre, [q[1:] for q in c]) if with_points else centre)
    return out


class StaticMap:
    """Cells the lidar hits when nobody is around (tools/team/record_static_map.py)."""

    def __init__(self, cells, res=MAP_RES):
        self.res = res
        self.cells = {tuple(c) for c in cells}

    @classmethod
    def load(cls, path):
        import json
        d = json.load(open(path))
        return cls(d['cells'], d.get('resolution', MAP_RES))

    def fraction(self, points):
        """Share of odometry-frame points on (or next to) a static cell."""
        if not points:
            return 0.0
        hit = 0
        for x, y in points:
            i, j = math.floor(x / self.res), math.floor(y / self.res)
            if any((i + di, j + dj) in self.cells for di in (-1, 0, 1) for dj in (-1, 0, 1)):
                hit += 1
        return hit / len(points)


def lidar_to_odom(points, pose):
    """Lidar-frame (x, y) points -> odometry frame. pose = (x, y, yaw)."""
    px, py, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return [(px + (LIDAR_X + x) * c - y * s, py + (LIDAR_X + x) * s + y * c)
            for x, y in points]


def to_odom(rng, bearing, pose):
    """Range/bearing from the camera -> odometry-frame (x, y). pose = (x, y, yaw)."""
    px, py, yaw = pose
    rx = CAM_X + rng * math.cos(bearing)
    ry = rng * math.sin(bearing)
    return (px + rx * math.cos(yaw) - ry * math.sin(yaw),
            py + rx * math.sin(yaw) + ry * math.cos(yaw))


class KalmanCV:
    """Constant-velocity Kalman filter, state (x, y, vx, vy)."""

    def __init__(self, x, y, t, q=0.5, r=0.15):
        self.s = [x, y, 0.0, 0.0]
        self.P = [[r * r, 0, 0, 0], [0, r * r, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]
        self.t, self.q, self.r = t, q, r

    def _predict(self, dt):
        x, y, vx, vy = self.s
        self.s = [x + vx * dt, y + vy * dt, vx, vy]
        F = [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]]
        FP = [[sum(F[i][k] * self.P[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
        self.P = [[sum(FP[i][k] * F[j][k] for k in range(4)) for j in range(4)] for i in range(4)]
        q = self.q * self.q
        for i, v in ((0, dt ** 3 / 3), (1, dt ** 3 / 3), (2, dt), (3, dt)):
            self.P[i][i] += q * v
        for a, b in ((0, 2), (1, 3)):
            self.P[a][b] += q * dt * dt / 2
            self.P[b][a] += q * dt * dt / 2

    def update(self, x, y, t):
        self._predict(max(0.0, t - self.t))
        self.t = t
        r2 = self.r * self.r
        for i, z in ((0, x), (1, y)):  # sequential scalar updates (H picks x or y)
            S = self.P[i][i] + r2
            K = [self.P[k][i] / S for k in range(4)]
            innov = z - self.s[i]
            self.s = [self.s[k] + K[k] * innov for k in range(4)]
            Pi = list(self.P[i])
            self.P = [[self.P[a][b] - K[a] * Pi[b] for b in range(4)] for a in range(4)]

    def state_at(self, t):
        x, y, vx, vy = self.s
        dt = t - self.t
        return x + vx * dt, y + vy * dt, vx, vy


@dataclass
class Track:
    tid: int
    kf: KalmanCV
    n: int = 1
    last_seen: float = 0.0
    points: list = field(default_factory=list)
    label: str = 'person'    # 'object': lidar only, not (yet) seen as a person
    source: str = 'camera'   # 'camera' or 'lidar': what gives the position
    static: bool = False     # on the static map (pillar, wall) and never seen as a person


class PersonTracker:
    def __init__(self, gate: float = 1.0, max_age: float = 1.0, min_conf: float = 0.5,
                 lidar_gate: float = 0.8, bearing_gate: float = 0.12):
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.gate, self.max_age, self.min_conf = gate, max_age, min_conf
        self.lidar_gate, self.bearing_gate = lidar_gate, bearing_gate
        self.lidar_time = None

    def update(self, detections, t, pose):
        """Camera detections. With a fresh lidar scan they only label tracks."""
        lidar_fresh = self.lidar_time is not None and t - self.lidar_time < 0.5
        pts = []
        for d in detections:
            if (str(d.get('class_name', '')).lower() != 'person'
                    or float(d.get('confidence', 0)) < self.min_conf):
                continue
            rng, bearing = measure(d['bbox_xyxy'])
            tid = self._match_bearing(bearing, t, pose) if lidar_fresh else None
            if tid is not None:
                self.tracks[tid].label = 'person'
                self.tracks[tid].static = False
                continue
            pts.append(to_odom(rng, bearing, pose))
        self._associate(pts, t, self.gate, 'person', 'camera')
        return self._expire(t)

    def update_lidar(self, points, t, static=None):
        """Odometry-frame lidar cluster centres (lidar_to_odom(cluster_scan(...)))."""
        # static: one flag per point, True if that cluster lies on the static map.
        self.lidar_time = t
        self._associate(points, t, self.lidar_gate, 'object', 'lidar', static)
        return self._expire(t)

    def _match_bearing(self, bearing, t, pose):
        best, bd = None, self.bearing_gate
        for tid, tr in self.tracks.items():
            if tr.source != 'lidar' or t - tr.last_seen > 0.3:
                continue
            x, y, _, _ = tr.kf.state_at(t)
            rx, ry = to_vehicle((x, y), pose)
            if rx - CAM_X < 0.2:
                continue
            d = abs(math.atan2(ry, rx - CAM_X) - bearing)
            if d < bd:
                best, bd = tid, d
        return best

    def _associate(self, pts, t, gate, label, source, static=None):
        free = set(self.tracks)
        for k, p in enumerate(pts):  # greedy nearest-neighbour association
            best, bd = None, gate
            for tid in free:
                x, y, _, _ = self.tracks[tid].kf.state_at(t)
                d = math.dist(p, (x, y))
                if d < bd:
                    best, bd = tid, d
            if best is None:
                tr = Track(self.next_id, KalmanCV(p[0], p[1], t), last_seen=t,
                           label=label, source=source)
                self.tracks[tr.tid] = tr
                self.next_id += 1
            else:
                tr = self.tracks[best]
                tr.kf.update(p[0], p[1], t)
                tr.n += 1
                tr.last_seen = t
                if source == 'lidar':
                    tr.source = 'lidar'
                free.discard(best)
            if static is not None:
                # a camera-confirmed person is never treated as a static obstacle
                tr.static = bool(static[k]) and tr.label != 'person'
            tr.points.append((t, p[0], p[1]))

    def _expire(self, t):
        for tid in [k for k, v in self.tracks.items() if t - v.last_seen > self.max_age]:
            del self.tracks[tid]
        return list(self.tracks.values())


def in_corridor(rel_x, rel_y):
    return 0.0 <= rel_x - FRONT <= LOOKAHEAD and abs(rel_y) <= HALF_WIDTH + MARGIN


def to_vehicle(p, pose):
    px, py, yaw = pose
    dx, dy = p[0] - px, p[1] - py
    return dx * math.cos(yaw) + dy * math.sin(yaw), -dx * math.sin(yaw) + dy * math.cos(yaw)


PASS_GAP = 0.5   # approach_stop: stop if a near person is predicted closer than this


def min_predicted_gap(state, pose, speed, horizon=3.0, step=0.1):
    """Smallest body gap over the horizon: person at constant velocity, vehicle ahead at speed."""
    x, y, vx, vy = state
    px, py, yaw = pose
    best = math.inf
    k = 1
    while k * step <= horizon + 1e-9:
        tt = k * step
        vpose = (px + speed * math.cos(yaw) * tt, py + speed * math.sin(yaw) * tt, yaw)
        rx, ry = to_vehicle((x + vx * tt, y + vy * tt), vpose)
        best = min(best, footprint_distance(rx, ry) - PERSON_R)
        k += 1
    return best


def footprint_distance(rx, ry):
    """Distance (m) from a vehicle-frame point to the vehicle footprint."""
    ex = max(0.0, rx - FRONT, REAR - rx)
    return math.hypot(ex, max(0.0, abs(ry) - HALF_WIDTH))


def assess(tracks, t, pose, speed, horizon=3.0, step=0.1, stop_ttc=2.0, min_obs=3,
           stop_radius=0.0, near_clearance=0.75, approach_stop=False):
    """-> dict(risk CLEAR|SLOW|STOP, ttc, track, reason, min_gap)."""
    # The vehicle is predicted along its heading at `speed`, each person with
    # its Kalman state. near_clearance: SLOW while the gap between a person and
    # the vehicle body is smaller (SLOW does not release a STOP, see
    # CommanderLogic); 0.75 is the camera-only default (1.0 m to the footprint).
    # approach_stop: STOP instead of SLOW when that person is also predicted to
    # come within PASS_GAP of the body in the next seconds (walking up to the
    # vehicle), not when they just walk past at a constant distance. Found with
    # the random walks: a person walking up beside the path was within 0.6 m
    # while the lidar team still crept forward at half speed (2026-11-27, R1).
    worst = {'risk': 'CLEAR', 'ttc': None, 'track': None, 'reason': 'no person near the path'}
    rank = {'CLEAR': 0, 'SLOW': 1, 'STOP': 2}

    def take(risk, ttc, tid, reason):
        nonlocal worst
        sooner = (risk == worst['risk'] and ttc is not None
                  and (worst['ttc'] is None or ttc < worst['ttc']))
        if rank[risk] > rank[worst['risk']] or sooner:
            worst = {'risk': risk, 'ttc': ttc, 'track': tid, 'reason': reason}

    px, py, yaw = pose
    min_gap = None
    for tr in tracks:
        x, y, vx, vy = tr.kf.state_at(t)
        rx, ry = to_vehicle((x, y), pose)
        static = getattr(tr, 'static', False)
        name = f"{'obstacle' if static else getattr(tr, 'label', 'person')} {tr.tid}"
        dist = footprint_distance(rx, ry)
        gap = dist - PERSON_R
        if not static:
            min_gap = gap if min_gap is None else min(min_gap, gap)
        if in_corridor(rx, ry):
            take('STOP', 0.0, tr.tid, f'{name} is in the path {rx - FRONT:.1f} m ahead')
            continue
        if static:  # a pillar or a wall beside the path does not walk into it
            continue
        # Conservative mode: stop whenever a person is this close, wherever.
        if dist < stop_radius:
            take('STOP', None, tr.tid, f'{name} within {dist:.1f} m (stop radius)')
            continue
        if tr.n < min_obs:  # too new to trust a velocity: be conservative
            if dist < 3.0:
                take('SLOW', None, tr.tid, f'new {name} {dist:.1f} m away, velocity unknown')
            continue
        ttc = None
        k = 1
        while k * step <= horizon + 1e-9:
            tt = k * step
            vxv, vyv = px + speed * math.cos(yaw) * tt, py + speed * math.sin(yaw) * tt
            prx, pry = to_vehicle((x + vx * tt, y + vy * tt), (vxv, vyv, yaw))
            if in_corridor(prx, pry):
                ttc = round(tt, 1)
                break
            k += 1
        if ttc is not None and ttc <= stop_ttc:
            take('STOP', ttc, tr.tid, f'{name} predicted in the path in {ttc:.1f} s')
        elif ttc is not None:
            take('SLOW', ttc, tr.tid, f'{name} may enter the path in {ttc:.1f} s')
        elif gap < near_clearance:
            ahead = (min_predicted_gap((x, y, vx, vy), pose, speed, horizon, step)
                     if approach_stop else gap)
            if ahead < min(gap, PASS_GAP):
                take('STOP', None, tr.tid,
                     f'{name} {max(0.0, gap):.1f} m away, coming to {max(0.0, ahead):.1f} m')
            else:
                take('SLOW', None, tr.tid, f'{name} {max(0.0, gap):.1f} m from the vehicle')
    worst['min_gap'] = None if min_gap is None else round(min_gap, 2)
    return worst


class CommanderLogic:
    """Base command + prediction -> final command, with reasons."""

    # After a STOP the vehicle only moves again once the prediction has been
    # CLEAR for clear_hold seconds; SLOW does not release a STOP. Without it the
    # vehicle resumed at half speed while a person who had just left the path
    # was still ~0.6 m away (scenario S4, 2026-11-27).

    def __init__(self, stale_after: float = 0.5, slow_factor: float = 0.5,
                 clear_hold: float = 1.0):
        self.stale_after, self.slow_factor, self.clear_hold = stale_after, slow_factor, clear_hold
        self.mode = 'STOP'
        self.reason = 'no prediction yet'
        self.clear_since = None

    def decide(self, lin, ang, prediction, pred_time, now):
        if prediction is None or now - pred_time > self.stale_after:
            mode, reason = 'STOP', 'prediction missing or stale (fail-safe)'
        else:
            mode, reason = prediction['risk'], prediction['reason']
        if mode == 'CLEAR':
            self.clear_since = now if self.clear_since is None else self.clear_since
        else:
            self.clear_since = None
        if self.mode == 'STOP' and mode != 'STOP':
            held = self.clear_since is not None and now - self.clear_since >= self.clear_hold
            if not held:
                mode = 'STOP'
                reason = f'holding stop until clear for {self.clear_hold:.0f} s ({reason})'
        changed = (mode != self.mode)
        self.mode, self.reason = mode, reason
        if mode == 'STOP':
            return 0.0, 0.0, changed
        if mode == 'SLOW':
            return lin * self.slow_factor, ang, changed
        return lin, ang, changed
