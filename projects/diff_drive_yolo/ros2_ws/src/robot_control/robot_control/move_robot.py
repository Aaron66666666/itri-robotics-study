from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node


class MoveRobot(Node):

    def __init__(self):
        super().__init__('move_robot')

        # 建立速度指令發布器，控制 Gazebo 裡的藍色車子
        self.publisher = self.create_publisher(
            Twist,
            '/model/vehicle_blue/cmd_vel',
            10
        )

        # 記錄程式開始後經過的時間
        self.start_time = self.get_clock().now()

        # 每 0.1 秒執行一次控制函式
        self.timer = self.create_timer(0.1, self.move)

        self.get_logger().info('藍色車子控制程式已啟動！')

    def move(self):
        msg = Twist()

        # 計算程式開始後經過幾秒
        elapsed_time = (
            self.get_clock().now() - self.start_time
        ).nanoseconds / 1e9

        if elapsed_time < 3.0:
            # 第 1 階段：前進 3 秒
            msg.linear.x = 0.2
            msg.angular.z = 0.0

        elif elapsed_time < 5.0:
            # 第 2 階段：前進並轉彎 2 秒
            msg.linear.x = 0.2
            msg.angular.z = 0.5

        else:
            # 第 3 階段：停止
            msg.linear.x = 0.0
            msg.angular.z = 0.0

            self.publisher.publish(msg)
            self.get_logger().info('前進、轉彎完成，藍色車子已停止！')

            # 停止計時器，避免重複執行
            self.timer.cancel()
            return

        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MoveRobot()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # 程式結束前送出停止指令
        stop_msg = Twist()
        node.publisher.publish(stop_msg)

        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
