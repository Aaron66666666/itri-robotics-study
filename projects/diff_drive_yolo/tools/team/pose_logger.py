#!/usr/bin/env python3
"""Log Gazebo ground truth of the vehicle and the person to CSV (until killed)."""
import math
import sys
import time

from gz.msgs10.pose_v_pb2 import Pose_V
from gz.transport13 import Node

out = open(sys.argv[1], 'w')
out.write('t,vx,vy,vyaw,px,py\n')
state = {'last': 0.0}


def cb(msg):
    now = time.time()
    if now - state['last'] < 0.05:
        return
    poses = {p.name: p for p in msg.pose if p.name in ('vehicle_blue', 'test_person')}
    if len(poses) < 2:
        return
    v, p = poses['vehicle_blue'], poses['test_person']
    q = v.orientation
    yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
    out.write(f'{now:.3f},{v.position.x:.4f},{v.position.y:.4f},{yaw:.4f},'
              f'{p.position.x:.4f},{p.position.y:.4f}\n')
    out.flush()
    state['last'] = now


node = Node()
node.subscribe(Pose_V, sys.argv[2] if len(sys.argv) > 2 else '/world/diff_drive/pose/info', cb)
while True:
    time.sleep(1)
