"""Terminal monitor for the GUI demo: one readable status line per 0.5 s.

Shows elapsed time, autonomy state (from /rosout), YOLO detections,
commanded speed and odometry position, and prints a highlighted line
whenever the controller changes state.
"""
import json
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import Log
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String

STATE_ZH = {
    'stale_detections': '等待影像',
    'search_forward': '搜尋目標',
    'approach_target': '接近杯子',
    'align_target': '對準杯子',
    'person_detected': '偵測到人，停車',
    'target_lost_wait': '短暫漏檢，先停車',
    'target_action:stop': '到達杯子，停止',
    'target_action_complete': '任務完成',
}


class Monitor(Node):
    def __init__(self):
        super().__init__('demo_monitor')
        self.t0 = time.monotonic()
        self.state = '-'
        self.dets = []
        self.vx = 0.0
        self.x = None
        self.create_subscription(Log, '/rosout', self.on_log, 50)
        self.create_subscription(String, '/yolo/detections', self.on_det, 10)
        self.create_subscription(Twist, '/model/vehicle_blue/cmd_vel', self.on_cmd, 10)
        self.create_subscription(Odometry, '/model/vehicle_blue/odometry', self.on_odom, qos_profile_sensor_data)
        self.create_timer(0.5, self.tick)

    def elapsed(self):
        return time.monotonic() - self.t0

    def on_log(self, msg):
        if msg.name == 'autonomy_controller' and 'Autonomy state:' in msg.msg:
            state = msg.msg.split('Autonomy state:', 1)[1].strip()
            if state != self.state:
                self.state = state
                label = STATE_ZH.get(state, state)
                print(f'\n>>> [{self.elapsed():5.1f}s] 狀態切換：{state}（{label}）\n', flush=True)

    def on_det(self, msg):
        try:
            d = json.loads(msg.data).get('detections', [])
            self.dets = [f"{x['class_name']}:{x['confidence']:.2f}" for x in d]
        except (ValueError, KeyError, TypeError):
            pass

    def on_cmd(self, msg):
        self.vx = msg.linear.x

    def on_odom(self, msg):
        self.x = msg.pose.pose.position.x

    def tick(self):
        x = f'{self.x:6.3f}' if self.x is not None else '   -  '
        dets = ', '.join(self.dets) if self.dets else '（無）'
        print(f'[{self.elapsed():5.1f}s] 狀態={self.state:<22} vx={self.vx:5.3f} m/s  x={x} m  偵測={dets}', flush=True)


def main():
    rclpy.init()
    node = Monitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
