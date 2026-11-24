#!/bin/bash
# Capture robot-camera frames in the real robot worlds at several vehicle
# positions, for evaluating YOLO models. Usage: capture_robot_frames.sh OUT_DIR
# Frames: bottle_x<pos>.png, cup_x<pos>.png, person_x<pos>.png
S=$(cd "$(dirname "$0")" && pwd); WS=$(cd "$S/../.." && pwd); OUT=${1:?OUT_DIR}
A=$WS/tools/acceptance
source /opt/ros/jazzy/setup.bash; source "$WS/install/setup.bash"
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
mkdir -p "$OUT"
stop_all() {  # stop every simulator/bridge and wait until none is left
  kill "$GZ" 2>/dev/null || true
  pkill -f "[g]z sim" 2>/dev/null || true
  pkill -f "[i]mage_bridge" 2>/dev/null || true
  for _ in $(seq 1 30); do
    pgrep -f "[g]z sim|[i]mage_bridge" > /dev/null || return 0
    sleep 1
  done
  echo "WARNING: Gazebo still running" >&2
}
capture() {  # world_file prefix xs [person]
  stop_all
  timeout 200 gz sim -s -r --headless-rendering "$WS/$1" > "$OUT/gz_$2.log" 2>&1 &
  GZ=$!; sleep 8
  timeout 190 ros2 run ros_gz_image image_bridge /vehicle_blue/camera/image > /dev/null 2>&1 &
  sleep 4
  [ -n "$4" ] && "$A/moveperson.sh" 3.6 2.6 3.1416 > /dev/null && sleep 1
  for X in $3; do
    gz service -s /world/diff_drive/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 2000 \
      --req "name: 'vehicle_blue', position: {x: $X, y: 2, z: 0.325}" > /dev/null
    sleep 1.5
    python3 "$A/grab.py" "$OUT/$2_x$X.png" > /dev/null
  done
  stop_all
}
capture worlds/diff_drive_camera_bottle.sdf bottle "0.0 0.2 0.4 0.6 0.8 1.0 1.2 1.4"
capture worlds/diff_drive_camera_cup.sdf cup "0.0 0.2 0.4 0.55 0.7 0.9 1.1"
capture worlds/diff_drive_camera_cup_person.sdf person "0.0 0.3 0.6" person
ls "$OUT"/*.png | wc -l
