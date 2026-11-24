"""Grab one frame from the ROS camera topic and save as PNG."""
import sys, rclpy, cv2
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
rclpy.init(); n = Node('grab'); b = CvBridge(); got = []
n.create_subscription(Image, '/vehicle_blue/camera/image', lambda m: got.append(m), qos_profile_sensor_data)
cnt = 0
while len(got) < 4 and cnt < 200: rclpy.spin_once(n, timeout_sec=0.1); cnt += 1
cv2.imwrite(sys.argv[1], b.imgmsg_to_cv2(got[-1], 'bgr8')); print('saved', sys.argv[1])
