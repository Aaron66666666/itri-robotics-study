#!/usr/bin/env bash
# Run the MoveIt pick-and-place demo against an already running
# ./scripts/start_moveit.sh (Gazebo + MoveIt). Extra args are passed through,
# e.g. --stage joints | ee | pick, --cube-x 0.4 --cube-y 0.5 --place-x 0.3 --place-y 0.65
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "$(dirname "${BASH_SOURCE[0]}")/../ros2_ws/install/setup.bash"
ros2 run ur5e_gripper_demo pick_place_demo.py "$@"
