#!/usr/bin/env bash
# Run the pick-and-place demo against a running start_moveit.sh. Args pass through,
# e.g. --stage joints | ee | pick, --cube-x 0.4 --cube-y 0.5 --place-x 0.3 --place-y 0.65
set -eo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
ros2 run tm5s_gripper_demo pick_place_demo.py "$@"
