"""Start MoveIt using the UR5e plus the project's parallel gripper description."""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    package_share = get_package_share_directory('ur5e_gripper_demo')
    ur_type = LaunchConfiguration('ur_type')
    moveit_config = (
        MoveItConfigsBuilder(robot_name='ur', package_name='ur_moveit_config')
        .robot_description(
            file_path=os.path.join(package_share, 'urdf', 'ur5e_gripper.urdf.xacro'),
            mappings={'name': 'ur', 'ur_type': ur_type},
        )
        .robot_description_semantic(
            file_path=os.path.join(package_share, 'srdf', 'ur5e_gripper.srdf.xacro'),
            mappings={'name': 'ur'},
        )
        .trajectory_execution(
            file_path=os.path.join(package_share, 'config', 'moveit_controllers.yaml'),
            moveit_manage_controllers=False,
        )
        .to_moveit_configs()
    )

    move_group = Node(
        package='moveit_ros_move_group',
        executable='move_group',
        output='screen',
        parameters=[moveit_config.to_dict(), {'use_sim_time': True}],
    )
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2_moveit',
        output='screen',
        condition=IfCondition(LaunchConfiguration('launch_rviz')),
        arguments=['-d', os.path.join(
            get_package_share_directory('ur_moveit_config'), 'config', 'moveit.rviz')],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
            {'use_sim_time': True},
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument('ur_type', default_value='ur5e'),
        # Set false for headless runs (e.g. automated pick-and-place tests).
        DeclareLaunchArgument('launch_rviz', default_value='true'),
        # The custom URDF is loaded directly into MoveIt, so no UR driver
        # helper node is needed. Start both MoveIt and RViz after Gazebo has
        # had a moment to publish the simulated joint states.
        TimerAction(period=3.0, actions=[move_group, rviz]),
    ])
