from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'image_topic',
            default_value='/vehicle_blue/camera/image',
            description='ROS 2 camera image topic',
        ),
        DeclareLaunchArgument(
            'yolo_model',
            default_value='v3',
            choices=['v3', 'v5', 'coco'],
            description='YOLO weights in ~/yolo_project: v3 (Gazebo '
                        'fine-tuned, default), v5 (retrained on clean '
                        'images), coco (original YOLO26n)',
        ),
        DeclareLaunchArgument(
            'model_path',
            default_value='',
            description='Optional YOLO weights file; overrides yolo_model',
        ),
        DeclareLaunchArgument(
            'confidence_threshold',
            default_value='0.35',
            description='Minimum YOLO confidence from 0.0 to 1.0',
        ),
        DeclareLaunchArgument(
            'device',
            default_value='auto',
            description="Use Ultralytics auto-selection, or set a device such as '0' or 'cpu'",
        ),
        DeclareLaunchArgument(
            'display',
            default_value='false',
            description='Open an OpenCV window on this machine',
        ),
        DeclareLaunchArgument(
            'diagnostic_frame_path',
            default_value='',
            description='Optional path for one lossless PNG input-frame capture',
        ),
        # Bridge the camera topic declared by worlds/diff_drive_camera.sdf.
        Node(
            package='ros_gz_image',
            executable='image_bridge',
            name='camera_image_bridge',
            arguments=[LaunchConfiguration('image_topic')],
            parameters=[{'qos': 'sensor_data'}],
            output='screen',
        ),
        Node(
            package='robot_control',
            executable='camera_yolo',
            name='camera_yolo',
            output='screen',
            parameters=[{
                'image_topic': LaunchConfiguration('image_topic'),
                'yolo_model': LaunchConfiguration('yolo_model'),
                'model_path': ParameterValue(
                    LaunchConfiguration('model_path'), value_type=str),
                'confidence_threshold': ParameterValue(
                    LaunchConfiguration('confidence_threshold'),
                    value_type=float,
                ),
                # Keep device:=0 a string; ROS would otherwise type it INTEGER.
                'device': ParameterValue(
                    LaunchConfiguration('device'), value_type=str),
                'display': ParameterValue(
                    LaunchConfiguration('display'),
                    value_type=bool,
                ),
                'diagnostic_frame_path': LaunchConfiguration(
                    'diagnostic_frame_path'
                ),
            }],
        ),
    ])
