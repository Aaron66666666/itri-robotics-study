#!/bin/bash
S=$(cd "$(dirname "$0")" && pwd); O=${OUT:-/tmp/robot_acceptance}; mkdir -p $O; N=C1_inject; cd ${ROBOT_WS:-$HOME/robot_ws}
source /opt/ros/jazzy/setup.bash; source install/setup.bash; export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
rm -f $O/$N.*
timeout 60 gz sim -s -r --headless-rendering worlds/diff_drive_camera_cup.sdf > $O/$N.gz.log 2>&1 &
sleep 5
timeout 45 ros2 run ros_gz_bridge parameter_bridge /model/vehicle_blue/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist \
  '/model/vehicle_blue/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry' > $O/$N.bridge.log 2>&1 &
timeout -s INT 40 ros2 run robot_control autonomy_controller --ros-args -p target_class:=cup -p approach_speed:=0.05 \
  -p search_speed:=0.0 -p target_action:=stop > $O/$N.ctrl.log 2>&1 &
timeout 42 python3 $S/recorder.py $O/$N.csv > /dev/null 2>&1 &
sleep 5; python3 $S/scenario.py > $O/$N.phases.log 2>&1
sleep 6; wait
