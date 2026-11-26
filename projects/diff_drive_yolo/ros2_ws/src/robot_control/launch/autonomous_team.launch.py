"""Autonomous cup approach with the Tracker / Predictor / Commander team."""
# The base launch (autonomous_yolo.launch.py) runs unchanged except that the
# controller publishes to /autonomy/cmd_vel_raw and leaves people to the team
# (person_stop:=false). The team Commander publishes the vehicle cmd_vel.
# All other arguments (target_class, device, speeds, thresholds, ...) are
# passed through to the base launch from the command line.
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    base = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('robot_control'), 'launch', 'autonomous_yolo.launch.py'])),
        launch_arguments={'cmd_vel_topic': '/autonomy/cmd_vel_raw',
                          'person_stop': 'false'}.items())
    team = [Node(package='robot_control', executable=e, name=e, output='screen')
            for e in ('team_tracker', 'team_predictor', 'team_commander')]
    return LaunchDescription([base] + team)
