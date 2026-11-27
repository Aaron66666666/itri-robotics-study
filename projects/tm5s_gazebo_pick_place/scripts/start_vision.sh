#!/bin/bash
# Start the TM5S vision world (Gazebo + MoveIt) and the camera image bridge.
# Usage: start_vision.sh [datagen|demo] [gui]   logs go to $LOG_DIR (default /tmp/tm5s_vision)
# demo: the same scene plus a recording camera (/demo_camera/image); gui: Gazebo window
# (and RViz unless GUI_EXTRA=launch_rviz:=false).
S=$(cd "$(dirname "$0")" && pwd)
source "$S/env.sh"
LOG_DIR=${LOG_DIR:-/tmp/tm5s_vision}; mkdir -p "$LOG_DIR"
SHARE=$(ros2 pkg prefix tm5s_gripper_demo)/share/tm5s_gripper_demo
WORLD=$SHARE/worlds/vision_world.sdf; [ "${1:-}" = datagen ] && WORLD=$SHARE/worlds/vision_world_datagen.sdf
[ "${1:-}" = demo ] && WORLD=$SHARE/worlds/vision_world_demo.sdf
GUI_ARGS="gazebo_gui:=false launch_rviz:=false"; [ "${2:-${1:-}}" = gui ] && GUI_ARGS="${GUI_EXTRA:-}"
setsid bash "$S/start_moveit.sh" $GUI_ARGS world_file:=$WORLD > "$LOG_DIR/launch.log" 2>&1 < /dev/null &
setsid ros2 run ros_gz_image image_bridge /table_camera/image > "$LOG_DIR/bridge.log" 2>&1 < /dev/null &
for i in $(seq 120); do grep -q "You can start planning now" "$LOG_DIR/launch.log" 2>/dev/null && break; sleep 1; done
grep -q "You can start planning now" "$LOG_DIR/launch.log" || { echo "MoveIt not ready, see $LOG_DIR/launch.log"; exit 1; }
sleep 5
# Every controller must be active (a slow start-up once left joint_state_broadcaster inactive).
for c in joint_state_broadcaster tmr_arm_controller parallel_gripper_controller; do
  for try in 1 2 3; do
    state=$(timeout 10 ros2 service call /controller_manager/list_controllers controller_manager_msgs/srv/ListControllers 2>/dev/null \
            | grep -oE "name='$c'[^)]*state='[a-z]+'" | grep -oE "state='[a-z]+'" | head -1)
    [ "$state" = "state='active'" ] && break
    echo "$c is ${state:-missing}, activating (try $try)"
    timeout 20 ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController \
      "{activate_controllers: ['$c'], strictness: 1, timeout: {sec: 10}}" > /dev/null 2>&1
    sleep 2
  done
done
timeout 10 ros2 topic echo --once /joint_states > /dev/null 2>&1 || { echo "no /joint_states"; exit 1; }
echo "ready ($WORLD)"
