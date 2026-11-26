"""Launch camera inference, Gazebo bridges, and rule-based autonomy."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, GroupAction, IncludeLaunchDescription)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare

DEFAULT_MODEL = str(Path.home() / 'yolo_project' / 'yolo26n_gazebo_v3.pt')


def generate_launch_description():
    arguments = [
        DeclareLaunchArgument('image_topic', default_value='/vehicle_blue/camera/image'),
        # Gazebo fine-tuned YOLO (v3); original: model_path:=~/yolo_project/yolo26n.pt
        DeclareLaunchArgument('model_path', default_value=DEFAULT_MODEL),
        DeclareLaunchArgument('target_class', default_value='bottle'),
        DeclareLaunchArgument('yolo_confidence_threshold', default_value='0.35'),
        DeclareLaunchArgument('diagnostic_frame_path', default_value=''),
        DeclareLaunchArgument('device', default_value='auto'),
        DeclareLaunchArgument('target_action', default_value='turn_left'),
        DeclareLaunchArgument('confidence_threshold', default_value='0.5'),
        DeclareLaunchArgument('stale_timeout', default_value='1.0'),
        DeclareLaunchArgument('action_duration', default_value='1.5'),
        DeclareLaunchArgument('linear_speed', default_value='0.2'),
        DeclareLaunchArgument('angular_speed', default_value='0.6'),
        DeclareLaunchArgument('search_speed', default_value='0.1'),
        DeclareLaunchArgument('search_duration', default_value='5.0'),
        DeclareLaunchArgument('approach_speed', default_value='0.1'),
        DeclareLaunchArgument('stop_bbox_ratio', default_value='0.55'),
        DeclareLaunchArgument('alignment_speed', default_value='0.25'),
        DeclareLaunchArgument('alignment_deadband', default_value='0.08'),
        DeclareLaunchArgument('target_loss_timeout', default_value='0.5'),
        DeclareLaunchArgument('stop_bbox_dimension', default_value='height'),
        # The team launch (autonomous_team.launch.py) redirects the controller
        # to /autonomy/cmd_vel_raw and lets the team Commander handle people.
        DeclareLaunchArgument('cmd_vel_topic', default_value='/model/vehicle_blue/cmd_vel'),
        DeclareLaunchArgument('person_stop', default_value='true'),
    ]
    # Scoped so the include's 'confidence_threshold' (YOLO conf) does not
    # overwrite the controller's own 'confidence_threshold' launch argument.
    camera = GroupAction(scoped=True, actions=[IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('robot_control'), 'launch', 'camera_yolo.launch.py'])),
        launch_arguments={
            'image_topic': LaunchConfiguration('image_topic'),
            'model_path': LaunchConfiguration('model_path'),
            'confidence_threshold': LaunchConfiguration(
                'yolo_confidence_threshold'),
            'diagnostic_frame_path': LaunchConfiguration(
                'diagnostic_frame_path'),
            'device': LaunchConfiguration('device'),
        }.items(),
    )])
    cmd_vel_bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge',
        name='cmd_vel_bridge',
        arguments=[
            '/model/vehicle_blue/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
            # Read-only odometry (Gazebo -> ROS) to verify real vehicle motion.
            '/model/vehicle_blue/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
        ],
        output='screen',
    )
    autonomy = Node(
        package='robot_control', executable='autonomy_controller',
        name='autonomy_controller', output='screen',
        parameters=[{
            'target_class': LaunchConfiguration('target_class'),
            'target_action': LaunchConfiguration('target_action'),
            'confidence_threshold': ParameterValue(
                LaunchConfiguration('confidence_threshold'), value_type=float),
            'stale_timeout': ParameterValue(
                LaunchConfiguration('stale_timeout'), value_type=float),
            'action_duration': ParameterValue(
                LaunchConfiguration('action_duration'), value_type=float),
            'linear_speed': ParameterValue(
                LaunchConfiguration('linear_speed'), value_type=float),
            'angular_speed': ParameterValue(
                LaunchConfiguration('angular_speed'), value_type=float),
            'search_speed': ParameterValue(
                LaunchConfiguration('search_speed'), value_type=float),
            'search_duration': ParameterValue(
                LaunchConfiguration('search_duration'), value_type=float),
            'approach_speed': ParameterValue(
                LaunchConfiguration('approach_speed'), value_type=float),
            'stop_bbox_ratio': ParameterValue(
                LaunchConfiguration('stop_bbox_ratio'), value_type=float),
            'alignment_speed': ParameterValue(
                LaunchConfiguration('alignment_speed'), value_type=float),
            'alignment_deadband': ParameterValue(
                LaunchConfiguration('alignment_deadband'), value_type=float),
            'target_loss_timeout': ParameterValue(
                LaunchConfiguration('target_loss_timeout'), value_type=float),
            'stop_bbox_dimension': LaunchConfiguration('stop_bbox_dimension'),
            'cmd_vel_topic': LaunchConfiguration('cmd_vel_topic'),
            'person_stop': ParameterValue(LaunchConfiguration('person_stop'), value_type=bool),
        }],
    )
    return LaunchDescription(arguments + [camera, cmd_vel_bridge, autonomy])
