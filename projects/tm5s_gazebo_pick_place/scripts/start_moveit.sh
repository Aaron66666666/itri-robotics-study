#!/usr/bin/env bash
# Gazebo (TM5S + gripper) + MoveIt 2 + RViz. Pass gazebo_gui:=false launch_rviz:=false for headless.
set -eo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
ros2 launch tm5s_gripper_demo tm5s_gripper_moveit.launch.py "$@"
