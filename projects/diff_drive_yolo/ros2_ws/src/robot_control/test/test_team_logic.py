"""Unit tests for the vehicle team logic (Tracker / Predictor / Commander)."""

import math

from robot_control.team_logic import (assess, CommanderLogic, FRONT, in_corridor, KalmanCV,
                                      measure, PersonTracker, RANGE_K, to_odom)


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
    c = CommanderLogic()
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
