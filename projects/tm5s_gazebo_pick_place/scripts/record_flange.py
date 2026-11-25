"""Record the TM5S flange position (world frame, from TF) and the finger joint
positions to a CSV at 20 Hz until interrupted.

Usage: python3 record_flange.py out.csv
"""
import csv
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformListener


class Recorder(Node):
    def __init__(self, path):
        super().__init__('flange_recorder', parameter_overrides=[
            rclpy.parameter.Parameter('use_sim_time', value=True)])
        self.buf = Buffer()
        self.tl = TransformListener(self.buf, self)
        self.finger = 0.0
        self.create_subscription(JointState, '/joint_states', self.on_js, 10)
        self.f = open(path, 'w', newline='')
        self.w = csv.writer(self.f)
        self.w.writerow(['wall_t', 'sim_t', 'x', 'y', 'z', 'finger_q'])
        self.t0 = time.monotonic()
        self.create_timer(0.05, self.tick)

    def on_js(self, msg):
        if 'left_finger_joint' in msg.name:
            self.finger = msg.position[msg.name.index('left_finger_joint')]

    def tick(self):
        try:
            tf = self.buf.lookup_transform('world', 'flange', Time())
        except Exception:  # TF not available yet
            return
        p = tf.transform.translation
        st = tf.header.stamp.sec + tf.header.stamp.nanosec * 1e-9
        self.w.writerow([f'{time.monotonic() - self.t0:.3f}', f'{st:.3f}',
                         f'{p.x:.4f}', f'{p.y:.4f}', f'{p.z:.4f}', f'{self.finger:.4f}'])
        self.f.flush()


def main():
    rclpy.init()
    node = Recorder(sys.argv[1])
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.f.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
