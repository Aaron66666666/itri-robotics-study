from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'robot_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    py_modules=['camera_subscriber'],

    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
    ],

    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='yulin',
    maintainer_email='203986674+Aaron66666666@users.noreply.github.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'move_robot = robot_control.move_robot:main',
            'read_odom = robot_control.read_odom:main',
            'camera_yolo = camera_subscriber:main',
            'autonomy_controller = robot_control.autonomous_controller:main',
            'team_tracker = robot_control.team_nodes:tracker_main',
            'team_predictor = robot_control.team_nodes:predictor_main',
            'team_commander = robot_control.team_nodes:commander_main',
        ],
    },
)
