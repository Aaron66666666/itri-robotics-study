#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash
printf 'ROS_DISTRO=%s\n' "${ROS_DISTRO:-unset}"
for package in ur_simulation_gz ur_description ur_moveit_config moveit; do
    if ros2 pkg prefix "$package" >/dev/null 2>&1; then
        printf '[installed] %s: ' "$package"
        ros2 pkg prefix "$package"
    else
        printf '[missing]   %s\n' "$package"
    fi
done
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || true
else
    printf '[info] nvidia-smi unavailable; CPU/Gazebo software rendering may be used.\n'
fi
