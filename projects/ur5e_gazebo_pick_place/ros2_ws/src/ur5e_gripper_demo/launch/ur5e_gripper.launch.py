"""Start the official UR5e Gazebo simulation with a controllable gripper."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = FindPackageShare('ur5e_gripper_demo')
    simulation_share = FindPackageShare('ur_simulation_gz')
    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            simulation_share, 'launch', 'ur_sim_control.launch.py'])),
        launch_arguments={
            'ur_type': 'ur5e',
            'description_file': PathJoinSubstitution([
                package_share, 'urdf', 'ur5e_gripper.urdf.xacro']),
            'controllers_file': PathJoinSubstitution([
                simulation_share, 'config', 'ur_controllers.yaml']),
            'initial_joint_controller': 'scaled_joint_trajectory_controller',
            'launch_rviz': LaunchConfiguration('launch_rviz'),
            'gazebo_gui': LaunchConfiguration('gazebo_gui'),
            'world_file': LaunchConfiguration('world_file'),
        }.items(),
    )
    gripper_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'parallel_gripper_controller',
            '-c', '/controller_manager',
        ],
        output='screen',
    )
    return LaunchDescription([
        DeclareLaunchArgument('launch_rviz', default_value='true'),
        DeclareLaunchArgument('gazebo_gui', default_value='true'),
        DeclareLaunchArgument(
            'world_file',
            default_value=PathJoinSubstitution([
                package_share, 'worlds', 'pick_place_world.sdf']),
        ),
        simulation,
        gripper_controller,
    ])
