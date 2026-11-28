"""Autonomous cup approach with the Tracker / Predictor / Commander team."""
# The base launch (autonomous_yolo.launch.py) runs unchanged except that the
# controller publishes to /autonomy/cmd_vel_raw and leaves people to the team
# (person_stop:=false). The team Commander publishes the vehicle cmd_vel.
# All other arguments (target_class, device, speeds, thresholds, ...) are
# passed through to the base launch from the command line.
# lidar:=true needs a world with the 360-degree lidar on the vehicle
# (worlds/diff_drive_camera_cup_person_lidar.sdf): the lidar gives positions,
# the camera labels people, and the predictor stops if the lidar goes silent.
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _float(name):
    return ParameterValue(LaunchConfiguration(name), value_type=float)


def _bool(name):
    return ParameterValue(LaunchConfiguration(name), value_type=bool)


def generate_launch_description():
    args = [
        # stop_radius > 0: also stop whenever a person is that close (conservative mode).
        DeclareLaunchArgument('stop_radius', default_value='0.0'),
        # SLOW (and keep a STOP) while the gap between a person and the vehicle
        # body is smaller than this; 0.75 is the camera-only default.
        DeclareLaunchArgument('near_clearance', default_value='0.75'),
        DeclareLaunchArgument('lidar', default_value='false'),
        # STOP (not only SLOW) when a person inside near_clearance is coming closer.
        DeclareLaunchArgument('approach_stop', default_value='false'),
        # Static lidar map (tools/team/record_static_map.sh): clusters on it are
        # pillars / walls, not people.
        DeclareLaunchArgument('static_map', default_value=''),
    ]
    base = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('robot_control'), 'launch', 'autonomous_yolo.launch.py'])),
        launch_arguments={'cmd_vel_topic': '/autonomy/cmd_vel_raw',
                          'person_stop': 'false'}.items())
    scan_bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge', name='scan_bridge',
        arguments=['/vehicle_blue/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan'],
        output='screen',
        condition=IfCondition(LaunchConfiguration('lidar')))
    tracker = Node(package='robot_control', executable='team_tracker', name='team_tracker',
                   output='screen', parameters=[{'use_lidar': _bool('lidar'),
                                                 'static_map': ParameterValue(
                                                     LaunchConfiguration('static_map'),
                                                     value_type=str)}])
    predictor = Node(package='robot_control', executable='team_predictor',
                     name='team_predictor', output='screen',
                     parameters=[{'stop_radius': _float('stop_radius'),
                                  'near_clearance': _float('near_clearance'),
                                  'require_lidar': _bool('lidar'),
                                  'approach_stop': _bool('approach_stop')}])
    commander = Node(package='robot_control', executable='team_commander',
                     name='team_commander', output='screen')
    return LaunchDescription(args + [base, scan_bridge, tracker, predictor, commander])
