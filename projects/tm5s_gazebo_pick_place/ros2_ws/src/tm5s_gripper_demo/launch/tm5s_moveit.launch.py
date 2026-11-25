"""MoveIt 2 (move_group + optional RViz) for the TM5S with the parallel gripper."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    share = get_package_share_directory('tm5s_gripper_demo')
    moveit_config = (
        MoveItConfigsBuilder(robot_name='tm5s', package_name='tm5s_gripper_demo')
        .robot_description(
            file_path=os.path.join(share, 'urdf', 'tm5s_gripper.urdf.xacro'),
            mappings={'controllers_file': os.path.join(share, 'config', 'ros2_controllers.yaml')})
        .robot_description_semantic(file_path=os.path.join(share, 'srdf', 'tm5s_gripper.srdf'))
        .robot_description_kinematics(file_path=os.path.join(share, 'config', 'kinematics.yaml'))
        .joint_limits(file_path=os.path.join(share, 'config', 'joint_limits.yaml'))
        .trajectory_execution(
            file_path=os.path.join(share, 'config', 'moveit_controllers.yaml'),
            moveit_manage_controllers=False)
        .planning_pipelines(pipelines=['ompl'], default_planning_pipeline='ompl')
        .to_moveit_configs()
    )
    move_group = Node(
        package='moveit_ros_move_group', executable='move_group', output='screen',
        parameters=[moveit_config.to_dict(), {'use_sim_time': True}])
    rviz = Node(
        package='rviz2', executable='rviz2', name='rviz2_moveit', output='screen',
        condition=IfCondition(LaunchConfiguration('launch_rviz')),
        arguments=['-d', os.path.join(share, 'config', 'moveit.rviz')],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
            {'use_sim_time': True},
        ])
    return LaunchDescription([
        DeclareLaunchArgument('launch_rviz', default_value='true'),
        TimerAction(period=3.0, actions=[move_group, rviz]),
    ])
