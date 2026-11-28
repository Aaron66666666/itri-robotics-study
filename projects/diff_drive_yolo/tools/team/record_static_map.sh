#!/bin/bash
# Record the static lidar map of a world with nobody near the vehicle.
# Usage: record_static_map.sh WORLD.sdf OUT.json
T=$(cd "$(dirname "$0")" && pwd); WS=$(cd "$T/../.." && pwd); cd "$WS"
source /opt/ros/jazzy/setup.bash; source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
PAT="[g]z sim|[p]arameter_bridge"
pkill -f "$PAT"; sleep 2
setsid timeout 90 gz sim -s -r --headless-rendering "$1" > /tmp/ros-log/static_map_gz.log 2>&1 &
sleep 6
# the parked test person would be mapped as a static object: move it far away
python3 "$T/walk_person.py" -- 0 1 "20,20" > /dev/null 2>&1
setsid timeout 60 ros2 run ros_gz_bridge parameter_bridge \
  /vehicle_blue/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan \
  /model/vehicle_blue/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry > /tmp/ros-log/static_map_bridge.log 2>&1 &
sleep 4
python3 "$T/record_static_map.py" "$2" 10
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"
