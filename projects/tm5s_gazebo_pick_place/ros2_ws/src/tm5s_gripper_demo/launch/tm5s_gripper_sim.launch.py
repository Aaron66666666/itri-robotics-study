"""Gazebo Harmonic + TM5S with gripper: spawn the robot and start its controllers."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            OpaqueFunction, RegisterEventHandler)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _gazebo(context):
    world = LaunchConfiguration('world_file').perform(context)
    gui = LaunchConfiguration('gazebo_gui').perform(context).lower() == 'true'
    gz_args = f'-r -v 2 {world}' if gui else f'-r -s --headless-rendering -v 2 {world}'
    return [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': gz_args, 'on_exit_shutdown': 'true'}.items())]


def generate_launch_description():
    share = get_package_share_directory('tm5s_gripper_demo')
    robot_description = ParameterValue(Command([
        'xacro ', os.path.join(share, 'urdf', 'tm5s_gripper.urdf.xacro'),
        ' controllers_file:=', os.path.join(share, 'config', 'ros2_controllers.yaml'),
    ]), value_type=str)

    rsp = Node(package='robot_state_publisher', executable='robot_state_publisher',
               output='screen',
               parameters=[{'robot_description': robot_description, 'use_sim_time': True}])
    spawn = Node(package='ros_gz_sim', executable='create', output='screen',
                 arguments=['-topic', 'robot_description', '-name', 'tm5s',
                            '-allow_renaming', 'false'])
    clock = Node(package='ros_gz_bridge', executable='parameter_bridge', output='screen',
                 arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'])

    def spawner(name):
        return Node(package='controller_manager', executable='spawner', output='screen',
                    arguments=[name, '-c', '/controller_manager',
                               '--controller-manager-timeout', '60'])

    jsb = spawner('joint_state_broadcaster')
    # Start the trajectory controllers only after the broadcaster is up.
    after_jsb = RegisterEventHandler(OnProcessExit(
        target_action=jsb,
        on_exit=[spawner('tmr_arm_controller'), spawner('parallel_gripper_controller')]))

    return LaunchDescription([
        DeclareLaunchArgument('gazebo_gui', default_value='true'),
        DeclareLaunchArgument('world_file', default_value=os.path.join(
            share, 'worlds', 'pick_place_world.sdf')),
        OpaqueFunction(function=_gazebo),
        rsp, clock, spawn, jsb, after_jsb,
    ])
