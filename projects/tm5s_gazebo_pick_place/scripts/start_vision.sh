#!/bin/bash
# Start the TM5S vision world (Gazebo + MoveIt) and the camera image bridge.
# Usage: start_vision.sh [datagen] [gui]   logs go to $LOG_DIR (default /tmp/tm5s_vision)
S=$(cd "$(dirname "$0")" && pwd)
source "$S/env.sh"
LOG_DIR=${LOG_DIR:-/tmp/tm5s_vision}; mkdir -p "$LOG_DIR"
SHARE=$(ros2 pkg prefix tm5s_gripper_demo)/share/tm5s_gripper_demo
WORLD=$SHARE/worlds/vision_world.sdf; [ "${1:-}" = datagen ] && WORLD=$SHARE/worlds/vision_world_datagen.sdf
GUI_ARGS="gazebo_gui:=false launch_rviz:=false"; [ "${2:-${1:-}}" = gui ] && GUI_ARGS=""
setsid bash "$S/start_moveit.sh" $GUI_ARGS world_file:=$WORLD > "$LOG_DIR/launch.log" 2>&1 < /dev/null &
setsid ros2 run ros_gz_image image_bridge /table_camera/image > "$LOG_DIR/bridge.log" 2>&1 < /dev/null &
for i in $(seq 120); do grep -q "You can start planning now" "$LOG_DIR/launch.log" 2>/dev/null && break; sleep 1; done
grep -q "You can start planning now" "$LOG_DIR/launch.log" && { sleep 5; echo "ready ($WORLD)"; } || { echo "MoveIt not ready, see $LOG_DIR/launch.log"; exit 1; }
