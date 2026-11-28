"""Unit tests for the vehicle team logic (Tracker / Predictor / Commander)."""

import math

from robot_control.team_logic import (assess, BODY_DEPTH, cluster_scan, CommanderLogic,
                                      FRONT, in_corridor, KalmanCV, lidar_to_odom, LIDAR_X,
                                      measure, PersonTracker, RANGE_K, StaticMap, to_odom)


def person(box, conf=0.9):
    return {'class_name': 'person', 'confidence': conf, 'bbox_xyxy': box}


def tracked(points, step=0.1):
    """Feed a tracker (x, y) odometry-frame points with the pose at the origin."""
    tr = PersonTracker()
    for i, (x, y) in enumerate(points):
        rng = math.hypot(x - 0.65, y)
        bearing = math.atan2(y, x - 0.65)
        h = RANGE_K / rng
        u = 320 - math.tan(bearing) * 554.256
        tr.update([person([u - 20, 100, u + 20, 100 + h])], i * step, (0.0, 0.0, 0.0))
    return tr, len(points) * step - step


def test_measure_and_projection():
    rng, bearing = measure([300, 100, 340, 200])
    assert abs(rng - RANGE_K / 100) < 1e-9 and abs(bearing) < 1e-9
    _, left = measure([100, 100, 140, 200])
    assert left > 0                                  # left of the image = +y
    x, y = to_odom(2.0, 0.0, (1.0, 2.0, math.pi / 2))
    assert abs(x - 1.0) < 1e-9 and abs(y - (2.0 + 2.65)) < 1e-9


def test_kalman_estimates_velocity():
    kf = KalmanCV(0.0, 0.0, 0.0)
    for i in range(1, 21):
        kf.update(0.0, 1.0 * i * 0.1, i * 0.1)
    _, _, vx, vy = kf.state_at(2.0)
    assert abs(vx) < 0.15 and abs(vy - 1.0) < 0.15


def test_tracker_keeps_ids_and_drops_old_tracks():
    tr = PersonTracker()
    pose = (0.0, 0.0, 0.0)
    a, b = person([100, 100, 140, 250]), person([500, 100, 540, 250])
    tr.update([a, b], 0.0, pose)
    tr.update([a, b], 0.1, pose)
    assert sorted(t.n for t in tr.tracks.values()) == [2, 2]
    tr.update([], 2.0, pose)
    assert tr.tracks == {}
    tr.update([{'class_name': 'cup', 'confidence': 0.9, 'bbox_xyxy': [0, 0, 10, 10]}], 2.1, pose)
    assert tr.tracks == {}


def test_assess_risk_by_motion():
    pose = (0.0, 0.0, 0.0)
    # standing at the side of the path: clear
    side, t = tracked([(3.5, 2.0)] * 6)
    assert assess(side.tracks.values(), t, pose, 0.05)['risk'] == 'CLEAR'
    # walking parallel to the path, 1.8 m to the side: clear
    par, t = tracked([(4.0 - 0.05 * i, 1.8) for i in range(10)])
    assert assess(par.tracks.values(), t, pose, 0.05)['risk'] == 'CLEAR'
    # crossing towards the path 2.0 m ahead: stop before the person is in the path
    cross, t = tracked([(FRONT + 1.5, 2.4 - 0.08 * i) for i in range(10)])
    r = assess(cross.tracks.values(), t, pose, 0.05)
    assert r['risk'] == 'STOP' and r['ttc'] is not None and r['ttc'] > 0
    # already in the path ahead
    front, t = tracked([(FRONT + 1.0, 0.1)] * 4)
    assert assess(front.tracks.values(), t, pose, 0.05)['risk'] == 'STOP'
    # a person seen only once, close by: slow (velocity unknown)
    new, t = tracked([(2.5, 1.6)])
    assert assess(new.tracks.values(), t, pose, 0.05)['risk'] == 'SLOW'


def test_corridor():
    assert in_corridor(FRONT + 0.5, 0.0) and not in_corridor(FRONT + 0.5, 1.5)
    assert not in_corridor(0.0, 0.0)                    # behind the front bumper


def test_commander_modes_and_failsafe():
    c = CommanderLogic(clear_hold=0.0)
    assert c.decide(0.1, 0.2, None, 0.0, 1.0)[:2] == (0.0, 0.0)          # no prediction
    assert c.decide(0.1, 0.2, {'risk': 'CLEAR', 'reason': ''}, 1.0, 1.0)[:2] == (0.1, 0.2)
    assert c.decide(0.1, 0.2, {'risk': 'SLOW', 'reason': ''}, 1.0, 1.0)[:2] == (0.05, 0.2)
    assert c.decide(0.1, 0.2, {'risk': 'STOP', 'reason': ''}, 1.0, 1.0)[:2] == (0.0, 0.0)
    assert c.decide(0.1, 0.2, {'risk': 'CLEAR', 'reason': ''}, 1.0, 1.6)[:2] == (0.0, 0.0)  # stale


def test_stop_radius_conservative_mode():
    pose = (0.0, 0.0, 0.0)
    side, t = tracked([(FRONT + 0.5, 1.3)] * 5)          # 0.8 m beside the path, not in it
    assert assess(side.tracks.values(), t, pose, 0.05)['risk'] != 'STOP'
    assert assess(side.tracks.values(), t, pose, 0.05, stop_radius=1.0)['risk'] == 'STOP'


def test_commander_holds_stop_until_clear():
    c = CommanderLogic(clear_hold=1.0)
    stop, slow, clear = ({'risk': r, 'reason': ''} for r in ('STOP', 'SLOW', 'CLEAR'))
    assert c.decide(0.1, 0.0, stop, 0.0, 0.0)[0] == 0.0
    assert c.decide(0.1, 0.0, slow, 0.1, 0.1)[0] == 0.0       # SLOW does not release a stop
    assert c.decide(0.1, 0.0, clear, 0.2, 0.2)[0] == 0.0      # clear, but not for 1 s yet
    assert c.decide(0.1, 0.0, clear, 1.2, 1.25)[0] == 0.1     # clear for 1 s: move again


N_RAYS = 720
INC = 2 * math.pi / N_RAYS


def ray(angle):
    return int(round((angle + math.pi) / INC)) % N_RAYS


def scan_with(*objects):
    """objects: (range m, bearing rad, angular half width rad) or ('wall', i0, i1, r)."""
    ranges = [math.inf] * N_RAYS
    for o in objects:
        if o[0] == 'wall':
            for i in range(o[1], o[2]):
                ranges[i] = o[3]
            continue
        rng, bearing, half = o
        for k in range(-int(half / INC), int(half / INC) + 1):
            ranges[ray(bearing + k * INC)] = rng
    return ranges


def test_cluster_scan_people_not_walls_or_noise():
    ranges = scan_with((2.0, math.pi / 2, 0.1), ('wall', 100, 200, 3.0))
    ranges[300] = 1.0                                     # one stray ray
    pts = cluster_scan(ranges, -math.pi, INC)
    assert len(pts) == 1
    x, y = pts[0]
    assert abs(x) < 0.05 and abs(y - (2.0 + BODY_DEPTH)) < 0.05
    behind = cluster_scan(scan_with((3.0, math.pi, 0.06)), -math.pi, INC)  # wraps around
    assert len(behind) == 1 and abs(behind[0][0] + 3.0 + BODY_DEPTH) < 0.05


def test_lidar_positions_camera_labels():
    tr = PersonTracker()
    pose = (0.0, 0.0, 0.0)
    for i in range(3):                       # someone 3 m ahead, seen by the lidar
        tr.update_lidar(lidar_to_odom([(3.0 - LIDAR_X, 0.0)], pose), i * 0.1)
    (track,) = tr.tracks.values()
    assert track.label == 'object' and track.source == 'lidar'
    # the camera sees a person at that bearing (its range estimate is off): label only
    tr.update([person([300, 100, 340, 100 + RANGE_K / 2.0])], 0.25, pose)
    assert list(tr.tracks) == [track.tid] and track.label == 'person'
    x, _, _, _ = track.kf.state_at(0.25)
    assert abs(x - 3.0) < 0.1                # position still from the lidar
    # without a fresh scan the camera position is used, as in the camera-only team
    tr.update([person([100, 100, 140, 250])], 2.0, pose)
    assert [t.source for t in tr.tracks.values()] == ['camera']


def lidar_tracked(x, y, n=5):
    tr = PersonTracker()
    for i in range(n):
        tr.update_lidar([(x, y)], i * 0.1)
    return tr, (n - 1) * 0.1


def test_near_clearance_beside_and_behind_the_vehicle():
    pose = (0.0, 0.0, 0.0)
    beside, t = lidar_tracked(0.0, 1.2)      # beside the body: gap 0.45 m
    r = assess(beside.tracks.values(), t, pose, 0.05, near_clearance=1.0)
    assert r['risk'] == 'SLOW' and abs(r['min_gap'] - 0.45) < 0.01
    far, t = lidar_tracked(0.0, 2.0)         # gap 1.25 m
    assert assess(far.tracks.values(), t, pose, 0.05, near_clearance=1.0)['risk'] == 'CLEAR'
    behind, t = lidar_tracked(-3.0, 0.0)     # 1.85 m behind the rear bumper
    r = assess(behind.tracks.values(), t, pose, 0.05, near_clearance=1.0)
    assert r['risk'] == 'CLEAR' and abs(r['min_gap'] - 1.6) < 0.01
    # the camera-only default (gap 0.75) is the earlier rule (1.0 m to the footprint)
    mid, t = lidar_tracked(0.0, 1.6)         # gap 0.85 m
    assert assess(mid.tracks.values(), t, pose, 0.05)['risk'] == 'CLEAR'
    assert assess(mid.tracks.values(), t, pose, 0.05, near_clearance=1.0)['risk'] == 'SLOW'


def test_stop_is_kept_while_a_person_is_near():
    c = CommanderLogic(clear_hold=1.0)
    pose = (0.0, 0.0, 0.0)
    front, t = lidar_tracked(FRONT + 0.5, 0.0)
    beside, _ = lidar_tracked(0.0, 1.2)
    stop = assess(front.tracks.values(), t, pose, 0.05, near_clearance=1.0)
    near = assess(beside.tracks.values(), t, pose, 0.05, near_clearance=1.0)
    assert c.decide(0.1, 0.0, stop, 0.0, 0.0)[0] == 0.0
    for k in range(1, 30):                   # left the path but still 0.45 m away
        assert c.decide(0.1, 0.0, near, k * 0.1, k * 0.1)[0] == 0.0


def test_approach_stop_only_for_people_walking_up_to_the_vehicle():
    pose = (0.0, 0.0, 0.0)

    def walker(x0, y0, vx, vy, n=8):
        tr = PersonTracker()
        for i in range(n):
            tr.update_lidar([(x0 + vx * i * 0.1, y0 + vy * i * 0.1)], i * 0.1)
        return tr, (n - 1) * 0.1
    # walking towards the vehicle 1.0 m beside its axis (passes 0.25 m from the body)
    up, t = walker(2.1, 1.0, -0.5, 0.0, n=12)
    assert assess(up.tracks.values(), t, pose, 0.05, near_clearance=1.0)['risk'] == 'SLOW'
    assert assess(up.tracks.values(), t, pose, 0.05, near_clearance=1.0,
                  approach_stop=True)['risk'] == 'STOP'
    # walking past 1.4 m beside the axis (0.65 m from the body all the way): only slow
    past, t = walker(1.4, 1.4, -0.4, 0.0, n=12)
    assert assess(past.tracks.values(), t, pose, 0.05, near_clearance=1.0,
                  approach_stop=True)['risk'] == 'SLOW'


def test_static_map_obstacles_are_not_people():
    pose = (0.0, 0.0, 0.0)
    pillar = (0.0, 1.0)                      # beside the vehicle, gap 0.25 m
    smap = StaticMap([(0, 9), (0, 10), (-1, 10)])
    assert smap.fraction([(0.02, 0.95), (0.05, 1.01)]) == 1.0
    assert smap.fraction([(3.0, 3.0)]) == 0.0
    tr = PersonTracker()
    for i in range(5):
        tr.update_lidar([pillar], i * 0.1, static=[True])
    r = assess(tr.tracks.values(), 0.4, pose, 0.05, near_clearance=1.0, approach_stop=True)
    assert r['risk'] == 'CLEAR' and r['min_gap'] is None
    # the same place without the map: a possible person 0.25 m away
    tr2 = PersonTracker()
    for i in range(5):
        tr2.update_lidar([pillar], i * 0.1)
    assert assess(tr2.tracks.values(), 0.4, pose, 0.05, near_clearance=1.0)['risk'] == 'SLOW'
    # a static obstacle in the path still stops the vehicle
    tr3 = PersonTracker()
    for i in range(5):
        tr3.update_lidar([(FRONT + 0.8, 0.0)], i * 0.1, static=[True])
    assert assess(tr3.tracks.values(), 0.4, pose, 0.05)['risk'] == 'STOP'
    # a track the camera confirmed as a person is never static
    tr4 = PersonTracker()
    for i in range(3):
        tr4.update_lidar(lidar_to_odom([(3.0 - LIDAR_X, 0.0)], pose), i * 0.1, static=[True])
    tr4.update([person([300, 100, 340, 100 + RANGE_K / 2.0])], 0.25, pose)
    tr4.update_lidar(lidar_to_odom([(3.0 - LIDAR_X, 0.0)], pose), 0.3, static=[True])
    assert [t.static for t in tr4.tracks.values()] == [False]
