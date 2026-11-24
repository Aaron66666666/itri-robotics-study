#!/bin/bash
# person_probe.sh : grab camera frames with the test person at candidate poses
# ("x y yaw" triples in POSES) for offline YOLO scoring with yscan.py.
S=$(cd "$(dirname "$0")" && pwd); cd ${ROBOT_WS:-$HOME/robot_ws}
source /opt/ros/jazzy/setup.bash; source install/setup.bash; export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
OUT=${OUT:-/tmp/robot_acceptance}/${SW:-person_probe}; mkdir -p $OUT; rm -f $OUT/*.png
timeout 200 gz sim -s -r --headless-rendering worlds/diff_drive_camera_cup_person.sdf > $OUT/gz.log 2>&1 &
sleep 8
timeout 190 ros2 run ros_gz_image image_bridge /vehicle_blue/camera/image > $OUT/bridge.log 2>&1 &
sleep 4
python3 $S/grab.py $OUT/p_parked.png
while read -r X Y YAW; do
  [ -z "$X" ] && continue
  $S/moveperson.sh $X $Y $YAW > /dev/null; sleep 1.5
  python3 $S/grab.py $OUT/p_${X}_${Y}_${YAW}.png
done <<< "${POSES:-3.6 2.6 3.1416
3.6 2.6 0
3.6 1.4 3.1416
4.2 2.0 3.1416}"
pkill -f "[g]z sim server|ruby.*[g]z sim|[i]mage_bridge"; wait 2>/dev/null
