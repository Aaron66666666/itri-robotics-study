#!/bin/bash
# Usage: run.sh NAME DURATION [launch args...]
S=$(cd "$(dirname "$0")" && pwd); O=${OUT:-/tmp/robot_acceptance}; mkdir -p $O; NAME=$1; DUR=$2; shift 2; cd ${ROBOT_WS:-$HOME/robot_ws}
source /opt/ros/jazzy/setup.bash; source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
pkill -f "[g]z sim server|ruby.*[g]z sim|[a]utonomy_controller|[c]amera_yolo|[p]arameter_bridge|[i]mage_bridge|[r]ecorder.py"; sleep 2
timeout $((DUR+20)) gz sim -s -r --headless-rendering ${WORLD:-worlds/diff_drive_camera_bottle.sdf} > $O/$NAME.gz.log 2>&1 &
sleep 5
timeout $((DUR+5)) python3 $S/recorder.py $O/$NAME.csv > /dev/null 2>&1 &
echo "ros2 launch robot_control autonomous_yolo.launch.py $*" > $O/$NAME.cmd
timeout -s INT $DUR ros2 launch robot_control autonomous_yolo.launch.py "$@" > $O/$NAME.launch.log 2>&1 &
LP=$!
[ -n "$HOOK" ] && bash -c "$HOOK" > $O/$NAME.hook.log 2>&1 &
sleep 12; timeout 5 ros2 param dump /autonomy_controller > $O/$NAME.params.yaml 2>&1
wait $LP; sleep 3
timeout 5 gz topic -e -t /world/diff_drive/pose/info -n 1 2>/dev/null | grep -A8 '"vehicle_blue"' | head -9 > $O/$NAME.gzpose.txt
pkill -f "[g]z sim server|ruby.*[g]z sim|[r]ecorder.py"; wait 2>/dev/null
