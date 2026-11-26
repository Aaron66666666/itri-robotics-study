#!/usr/bin/env python3
"""Walk the test person along waypoints at a fixed speed (10 Hz set_pose).

Usage: walk_person.py DELAY_S SPEED "x,y;x,y;..." [--hold-end] [--world diff_drive]
The person faces its walking direction; with --hold-end it stays at the end.
"""
import argparse
import math
import sys
import time

from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.pose_pb2 import Pose
from gz.transport13 import Node


def main():
    p = argparse.ArgumentParser()
    p.add_argument('delay', type=float)
    p.add_argument('speed', type=float)
    p.add_argument('path')
    p.add_argument('--world', default='diff_drive')
    p.add_argument('--name', default='test_person')
    a = p.parse_args()
    pts = [tuple(float(v) for v in s.split(',')) for s in a.path.split(';')]
    node = Node()
    svc = f'/world/{a.world}/set_pose'

    def put(x, y, yaw):
        req = Pose()
        req.name = a.name
        req.position.x, req.position.y = x, y
        req.orientation.z, req.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        node.request(svc, req, Pose, Boolean, 500)

    yaw0 = math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]) if len(pts) > 1 else 0.0
    put(pts[0][0], pts[0][1], yaw0)
    time.sleep(a.delay)
    print(f'{time.time():.3f} walk start {pts[0]}', flush=True)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        yaw = math.atan2(y1 - y0, x1 - x0)
        n = max(1, int(seg / a.speed / 0.1))
        t0 = time.monotonic()
        for i in range(1, n + 1):
            f = i / n
            put(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, yaw)
            time.sleep(max(0.0, t0 + i * 0.1 - time.monotonic()))
    print(f'{time.time():.3f} walk end {pts[-1]}', flush=True)


if __name__ == '__main__':
    sys.exit(main())
