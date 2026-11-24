#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "$(dirname "${BASH_SOURCE[0]}")/../ros2_ws/install/setup.bash"
ros2 topic pub --once \
  /parallel_gripper_controller/joint_trajectory \
  trajectory_msgs/msg/JointTrajectory \
  "{joint_names: [left_finger_joint, right_finger_joint], points: [{positions: [0.04, -0.04], time_from_start: {sec: 1, nanosec: 0}}]}"
