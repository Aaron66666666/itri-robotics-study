"""Scripted /yolo/detections at 10 Hz: controller+Gazebo test of brief miss and person priority."""
import json, time, rclpy
from rclpy.node import Node
from std_msgs.msg import String
CUP = {'class_id': 41, 'class_name': 'cup', 'confidence': 0.8, 'bbox_xyxy': [290, 260, 350, 380]}   # small, centered
PERSON = {'class_id': 0, 'class_name': 'person', 'confidence': 0.7, 'bbox_xyxy': [100, 100, 200, 470]}
# (start, end, detections, label)
PLAN = [(0, 4, [CUP], 'approach'), (4, 4.25, [], 'brief_miss_0.25s'), (4.25, 8, [CUP], 'approach'),
        (8, 12, [CUP, PERSON], 'person+cup'), (12, 15, [CUP], 'approach'), (15, 18, [PERSON], 'person_only'),
        (18, 19, [CUP], 'approach'), (19, 22, None, 'publisher_silent(stale)')]
class Sc(Node):
    def __init__(s):
        super().__init__('scenario_publisher'); s.p = s.create_publisher(String, '/yolo/detections', 10)
        s.t0 = time.monotonic(); s.last = None; s.create_timer(0.1, s.tick)
    def tick(s):
        t = time.monotonic() - s.t0
        for a, b, det, label in PLAN:
            if a <= t < b: break
        else: raise SystemExit
        if label != s.last: print(f'{time.time():.3f} phase {label}', flush=True); s.last = label
        if det is None: return
        s.p.publish(String(data=json.dumps({'image_size': {'width': 640, 'height': 480}, 'detections': det})))
rclpy.init(); n = Sc()
try: rclpy.spin(n)
except SystemExit: pass
