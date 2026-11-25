"""Gazebo (TM5S + gripper + controllers) and MoveIt 2 together."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    launch_dir = os.path.join(get_package_share_directory('tm5s_gripper_demo'), 'launch')
    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(launch_dir, 'tm5s_gripper_sim.launch.py')),
        launch_arguments={'gazebo_gui': LaunchConfiguration('gazebo_gui')}.items())
    moveit = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(launch_dir, 'tm5s_moveit.launch.py')),
        launch_arguments={'launch_rviz': LaunchConfiguration('launch_rviz')}.items())
    return LaunchDescription([
        DeclareLaunchArgument('gazebo_gui', default_value='true'),
        DeclareLaunchArgument('launch_rviz', default_value='true'),
        sim, moveit,
    ])
