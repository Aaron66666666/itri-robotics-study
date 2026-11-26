"""Autonomous cup approach with the Tracker / Predictor / Commander team."""
# The base launch (autonomous_yolo.launch.py) runs unchanged except that the
# controller publishes to /autonomy/cmd_vel_raw and leaves people to the team
# (person_stop:=false). The team Commander publishes the vehicle cmd_vel.
# All other arguments (target_class, device, speeds, thresholds, ...) are
# passed through to the base launch from the command line.
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    base = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('robot_control'), 'launch', 'autonomous_yolo.launch.py'])),
        launch_arguments={'cmd_vel_topic': '/autonomy/cmd_vel_raw',
                          'person_stop': 'false'}.items())
    team = [Node(package='robot_control', executable=e, name=e, output='screen',
                 parameters=[{'stop_radius': ParameterValue(LaunchConfiguration('stop_radius'),
                                                            value_type=float)}]
                 if e == 'team_predictor' else [])
            for e in ('team_tracker', 'team_predictor', 'team_commander')]
    # stop_radius > 0: also stop whenever a person is that close (conservative mode).
    stop_radius = DeclareLaunchArgument('stop_radius', default_value='0.0')
    return LaunchDescription([stop_radius, base] + team)
