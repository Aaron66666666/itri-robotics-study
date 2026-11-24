#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$PROJECT_DIR/ros2_ws/install/setup.bash" ]]; then
    echo 'Build the project workspace first: cd ros2_ws && colcon build --symlink-install' >&2
    exit 2
fi
source "$PROJECT_DIR/ros2_ws/install/setup.bash"
ros2 launch ur5e_gripper_demo ur5e_gripper.launch.py
