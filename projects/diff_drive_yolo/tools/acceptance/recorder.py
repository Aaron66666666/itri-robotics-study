"""Record detections, cmd_vel and odometry to CSV for acceptance evidence."""
import json, sys, time, math
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
class Rec(Node):
    def __init__(s, path):
        super().__init__('acceptance_recorder')
        s.f = open(path, 'w'); s.f.write('t,kind,a,b,c,d\n'); s.t0 = time.monotonic()
        s.create_subscription(String, '/yolo/detections', s.det, 10)
        s.create_subscription(Twist, '/model/vehicle_blue/cmd_vel', s.cmd, 10)
        s.create_subscription(Odometry, '/model/vehicle_blue/odometry', s.odom, 10)
        s.n = 0
    def w(s, *v): s.f.write(','.join(str(x) for x in (round(time.time(), 3),) + v) + '\n'); s.f.flush()
    def det(s, m):
        d = json.loads(m.data)['detections']
        s.w('det', ';'.join(f"{x['class_name']}:{x['confidence']:.3f}:h={(x['bbox_xyxy'][3]-x['bbox_xyxy'][1])/480:.3f}:cx={(x['bbox_xyxy'][0]+x['bbox_xyxy'][2])/1280-0.5:+.3f}" for x in d) or 'none', '', '', '')
    def cmd(s, m): s.w('cmd', m.linear.x, m.angular.z, '', '')
    def odom(s, m):
        s.n += 1
        if s.n % 2: return
        p = m.pose.pose.position; q = m.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        s.w('odom', round(p.x, 4), round(p.y, 4), round(yaw, 4), round(m.twist.twist.linear.x, 4))
rclpy.init(); n = Rec(sys.argv[1])
try: rclpy.spin(n)
except Exception: pass
