from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # 啟動機器人控制程式
        Node(
            package='robot_control',
            executable='move_robot',
            name='move_robot',
            output='screen'
        ),

        # 啟動 Odometry 監測程式
        Node(
            package='robot_control',
            executable='read_odom',
            name='read_odom',
            output='screen'
        ),
    ])
