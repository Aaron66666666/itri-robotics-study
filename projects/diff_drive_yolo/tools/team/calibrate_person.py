#!/usr/bin/env python3
"""Calibrate RANGE_K (range = K / person box height) with Gazebo ground truth.

Needs Gazebo (diff_drive_camera_cup_person.sdf) + camera_yolo running and the
vehicle at its start pose (0, 2, yaw 0). Prints K per position and the mean,
plus the bearing error of the pinhole model.
"""
import json
import math
import statistics
import time

from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.pose_pb2 import Pose
from gz.transport13 import Node as GzNode
import rclpy
from std_msgs.msg import String

CAM = (0.65, 2.0)       # camera position in the world at the start pose
FOCAL = 320 / math.tan(1.047 / 2)
POSITIONS = [(x, y) for x in (2.0, 3.0, 4.0, 5.0, 6.0) for y in (3.2, 0.8)]

gz = GzNode()
rclpy.init()
node = rclpy.create_node('calibrate_person')
latest = {}
node.create_subscription(String, '/yolo/detections', lambda m: latest.update(msg=m.data, t=time.time()), 10)
rows = []
for (x, y) in POSITIONS:
    req = Pose()
    req.name = 'test_person'
    req.position.x, req.position.y = x, y
    yaw = math.atan2(CAM[1] - y, CAM[0] - x)
    req.orientation.z, req.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
    gz.request('/world/diff_drive/set_pose', req, Pose, Boolean, 1000)
    t0 = time.time() + 1.5
    hs, us = [], []
    while time.time() < t0 + 2.0:
        rclpy.spin_once(node, timeout_sec=0.1)
        if latest.get('t', 0) > t0:
            for d in json.loads(latest['msg'])['detections']:
                if d['class_name'] == 'person':
                    x1, y1, x2, y2 = d['bbox_xyxy']
                    hs.append(y2 - y1)
                    us.append((x1 + x2) / 2)
            latest['t'] = 0
    rng = math.hypot(x - CAM[0], y - CAM[1])
    bearing = math.atan2(y - CAM[1], x - CAM[0])
    if hs:
        h, u = statistics.median(hs), statistics.median(us)
        est_b = math.atan2(-(u - 320), FOCAL)
        rows.append({'pos': [x, y], 'range': round(rng, 3), 'h_px': round(h, 1), 'K': round(rng * h, 1),
                     'bearing_err_deg': round(math.degrees(est_b - bearing), 2), 'frames': len(hs)})
    else:
        rows.append({'pos': [x, y], 'range': round(rng, 3), 'h_px': None})
    print(json.dumps(rows[-1]), flush=True)
ks = [r['K'] for r in rows if r.get('h_px')]
print('K_mean', round(statistics.mean(ks), 1), 'K_std', round(statistics.pstdev(ks), 1), 'n', len(ks))
