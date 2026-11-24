from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node


class ReadOdom(Node):

    def __init__(self):
        super().__init__('read_odom')

        # 訂閱藍色車子的 Odometry Topic
        self.subscription = self.create_subscription(
            Odometry,
            '/model/vehicle_blue/odometry',
            self.odom_callback,
            10
        )

        self.get_logger().info('開始讀取藍色車子的 Odometry！')

    # 每次收到 Odometry 資料，就會執行這個函式
    def odom_callback(self, msg):

        # 讀取車子的座標
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y

        # 讀取車子的前進速度
        speed = msg.twist.twist.linear.x

        # 顯示資料
        self.get_logger().info(
            f'位置：x={x:.2f}, y={y:.2f} | 前進速度：{speed:.2f} m/s'
        )


def main(args=None):
    rclpy.init(args=args)

    node = ReadOdom()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
