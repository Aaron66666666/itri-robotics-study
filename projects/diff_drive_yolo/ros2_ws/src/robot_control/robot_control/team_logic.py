"""Tracker / Predictor / Commander logic for the vehicle (no ROS, unit-tested)."""
# Tracker   - person detections (camera boxes) -> range and bearing from the
# vehicle -> odometry-frame points -> tracks with stable ids.
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
RANGE_K = 942.0

# Vehicle footprint (chassis 2.0 x 1.0 m, centred 0.15 m behind the origin).
HALF_WIDTH = 0.5
FRONT = 0.85
MARGIN = 0.4             # extra lateral clearance
LOOKAHEAD = 2.5          # m ahead of the front bumper that counts as "in the way"


def measure(box, conf: float = 1.0):
    """Person box (x1, y1, x2, y2) -> (range m, bearing rad, left positive)."""
    x1, y1, x2, y2 = box
    h = max(1.0, y2 - y1)
    rng = RANGE_K / h
    u = (x1 + x2) / 2
    bearing = math.atan2(-(u - IMG_W / 2), FOCAL)
    return rng, bearing


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


class PersonTracker:
    def __init__(self, gate: float = 1.0, max_age: float = 1.0, min_conf: float = 0.5):
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.gate, self.max_age, self.min_conf = gate, max_age, min_conf

    def update(self, detections, t, pose):
        pts = []
        for d in detections:
            if (str(d.get('class_name', '')).lower() != 'person'
                    or float(d.get('confidence', 0)) < self.min_conf):
                continue
            rng, bearing = measure(d['bbox_xyxy'])
            pts.append(to_odom(rng, bearing, pose))
        free = set(self.tracks)
        for p in pts:  # greedy nearest-neighbour association
            best, bd = None, self.gate
            for tid in free:
                x, y, _, _ = self.tracks[tid].kf.state_at(t)
                d = math.dist(p, (x, y))
                if d < bd:
                    best, bd = tid, d
            if best is None:
                tr = Track(self.next_id, KalmanCV(p[0], p[1], t), last_seen=t)
                self.tracks[tr.tid] = tr
                self.next_id += 1
            else:
                tr = self.tracks[best]
                tr.kf.update(p[0], p[1], t)
                tr.n += 1
                tr.last_seen = t
                free.discard(best)
            tr.points.append((t, p[0], p[1]))
        for tid in [k for k, v in self.tracks.items() if t - v.last_seen > self.max_age]:
            del self.tracks[tid]
        return list(self.tracks.values())


def in_corridor(rel_x, rel_y):
    return 0.0 <= rel_x - FRONT <= LOOKAHEAD and abs(rel_y) <= HALF_WIDTH + MARGIN


def to_vehicle(p, pose):
    px, py, yaw = pose
    dx, dy = p[0] - px, p[1] - py
    return dx * math.cos(yaw) + dy * math.sin(yaw), -dx * math.sin(yaw) + dy * math.cos(yaw)


def assess(tracks, t, pose, speed, horizon=3.0, step=0.1, stop_ttc=2.0, min_obs=3):
    """-> dict(risk CLEAR|SLOW|STOP, ttc, track, reason). The vehicle is."""
    # predicted along its heading at `speed`, each person with its Kalman state.
    worst = {'risk': 'CLEAR', 'ttc': None, 'track': None, 'reason': 'no person near the path'}
    rank = {'CLEAR': 0, 'SLOW': 1, 'STOP': 2}

    def take(risk, ttc, tid, reason):
        nonlocal worst
        sooner = (risk == worst['risk'] and ttc is not None
                  and (worst['ttc'] is None or ttc < worst['ttc']))
        if rank[risk] > rank[worst['risk']] or sooner:
            worst = {'risk': risk, 'ttc': ttc, 'track': tid, 'reason': reason}

    px, py, yaw = pose
    for tr in tracks:
        x, y, vx, vy = tr.kf.state_at(t)
        rx, ry = to_vehicle((x, y), pose)
        dist_front = math.hypot(max(0.0, rx - FRONT), max(0.0, abs(ry) - HALF_WIDTH))
        if in_corridor(rx, ry):
            take('STOP', 0.0, tr.tid, f'person {tr.tid} is in the path {rx - FRONT:.1f} m ahead')
            continue
        if tr.n < min_obs:  # too new to trust a velocity: be conservative
            if dist_front < 3.0:
                take('SLOW', None, tr.tid,
                     f'new person {tr.tid} {dist_front:.1f} m away, velocity unknown')
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
            take('STOP', ttc, tr.tid, f'person {tr.tid} predicted in the path in {ttc:.1f} s')
        elif ttc is not None:
            take('SLOW', ttc, tr.tid, f'person {tr.tid} may enter the path in {ttc:.1f} s')
        elif dist_front < 1.0:
            take('SLOW', None, tr.tid, f'person {tr.tid} within {dist_front:.1f} m of the vehicle')
    return worst


class CommanderLogic:
    """Base command + prediction -> final command, with reasons."""

    def __init__(self, stale_after: float = 0.5, slow_factor: float = 0.5):
        self.stale_after, self.slow_factor = stale_after, slow_factor
        self.mode = 'STOP'
        self.reason = 'no prediction yet'

    def decide(self, lin, ang, prediction, pred_time, now):
        if prediction is None or now - pred_time > self.stale_after:
            mode, reason = 'STOP', 'prediction missing or stale (fail-safe)'
        else:
            mode, reason = prediction['risk'], prediction['reason']
        changed = (mode != self.mode)
        self.mode, self.reason = mode, reason
        if mode == 'STOP':
            return 0.0, 0.0, changed
        if mode == 'SLOW':
            return lin * self.slow_factor, ang, changed
        return lin, ang, changed
