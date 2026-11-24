#!/bin/bash
S=$(cd "$(dirname "$0")" && pwd); cd ${ROBOT_WS:-$HOME/robot_ws}
source /opt/ros/jazzy/setup.bash; source install/setup.bash; export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
WORLDF=${WORLD:-worlds/diff_drive_camera_bottle.sdf}; WN=${WN:-diff_drive}; OUT=${OUT:-/tmp/robot_acceptance}/${SW:-sweep}; mkdir -p $OUT
timeout 200 gz sim -s -r --headless-rendering $WORLDF > $OUT/gz.log 2>&1 &
sleep 5
timeout 190 ros2 run ros_gz_image image_bridge /vehicle_blue/camera/image > $OUT/bridge.log 2>&1 &
sleep 4
for X in ${XS:-0.0 0.2 0.4 0.6 0.8 1.0 1.2}; do
  gz service -s /world/$WN/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 2000 \
    --req "name: 'vehicle_blue', position: {x: $X, y: 2, z: 0.325}" > /dev/null
  sleep 1.5; python3 $S/grab.py $OUT/x_$X.png
done
pkill -f "[g]z sim server|ruby.*[g]z sim|[i]mage_bridge"; wait 2>/dev/null
