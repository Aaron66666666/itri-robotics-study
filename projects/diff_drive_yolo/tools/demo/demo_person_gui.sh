#!/bin/bash
# GUI demo: the car approaches the cup; a person steps in front of it (car stops),
# the person leaves (car resumes), and the car stops at the cup.
# Windows: Gazebo GUI, rqt_image_view (/yolo/image with boxes), and this terminal.
# Usage: bash demo_person_gui.sh      (AUTO=1 skips the Enter prompts)
D=$(cd "$(dirname "$0")" && pwd); WS=${ROBOT_WS:-$HOME/robot_ws}; A=$WS/tools/acceptance
OUT=${OUT:-$HOME/demo_videos/person_$(date +%Y%m%d_%H%M%S)}; mkdir -p "$OUT"
cd "$WS"; source /opt/ros/jazzy/setup.bash; source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
PAT="[g]z sim|[a]utonomy_controller|[c]amera_yolo|[p]arameter_bridge|[i]mage_bridge|[r]qt_image_view|[d]emo/monitor.py"
cleanup() { pkill -INT -f "[r]os2 launch robot_control"; sleep 2; pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"; }  # gz GUI and rqt ignore TERM
trap cleanup EXIT
pause() { [ "${AUTO:-0}" = 1 ] && sleep "${2:-1}" || read -r -p "$1"; }
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"

echo "== 啟動 Gazebo（含畫面）與 YOLO 標註影像視窗 =="
gz sim -r worlds/diff_drive_camera_cup_person.sdf > "$OUT/gz.log" 2>&1 &
sleep 10
# Gazebo GUI camera: behind and to the side of the car, looking at the cup.
python3 - <<'EOF' > /tmp/demo_guicam.txt
import math
px, py, pz, tx, ty, tz = -1.0, 0.3, 1.7, 2.4, 2.2, 0.2
yaw = math.atan2(ty - py, tx - px); pitch = math.atan2(pz - tz, math.hypot(tx - px, ty - py))
cy, sy, cp, sp = math.cos(yaw / 2), math.sin(yaw / 2), math.cos(pitch / 2), math.sin(pitch / 2)
print(f"pose: {{position: {{x: {px}, y: {py}, z: {pz}}}, orientation: {{x: {-sy*sp:.4f}, y: {cy*sp:.4f}, z: {sy*cp:.4f}, w: {cy*cp:.4f}}}}}")
EOF
gz service -s /gui/move_to/pose --reqtype gz.msgs.GUICamera --reptype gz.msgs.Boolean --timeout 3000 --req "$(cat /tmp/demo_guicam.txt)" > /dev/null 2>&1
ros2 run rqt_image_view rqt_image_view /yolo/image > "$OUT/rqt.log" 2>&1 &

echo
echo "請把 Gazebo、YOLO 影像視窗和這個終端機排好，開始錄影。"
pause "準備好後按 Enter 開始（車子會開始移動）... " 3

# stale_timeout 2.0 (acceptance runs use 1.0): with the Gazebo GUI rendering on the
# same GPU, detections occasionally pause for ~1.2 s (measured), which would trigger
# the stale-detection safety stop and make the car stutter. Headless gaps are <= 0.4 s.
ros2 launch robot_control autonomous_yolo.launch.py target_class:=cup device:=0 \
  search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop \
  stop_bbox_dimension:=width stop_bbox_ratio:=0.185 stale_timeout:=2.0 > "$OUT/launch.log" 2>&1 &
python3 "$D/monitor.py" 2>/dev/null &

# Person steps in front of the car for 8 s, then leaves.
( sleep 14; echo; echo ">>> 人物走進車子前方"; bash "$A/moveperson.sh" 3.6 2.6 3.1416
  sleep 8;  echo; echo ">>> 人物離開"; bash "$A/moveperson.sh" -3 2 ) > >(tee "$OUT/person.log") 2>&1 &

# Wait until the controller reports the task is complete (max 90 s).
for i in $(seq 180); do grep -q "target_action_complete" "$OUT/launch.log" 2>/dev/null && break; sleep 0.5; done
sleep 3
pkill -f "[d]emo/monitor.py"
echo
echo "== 結果 =="
grep -a "Autonomy state" "$OUT/launch.log" | sed 's/.*Autonomy state: /狀態：/' | uniq
echo "Gazebo 中車輛的實際位置（vehicle_blue）："
timeout 5 gz topic -e -t /world/diff_drive/pose/info -n 1 2>/dev/null | grep -A4 '"vehicle_blue"' | grep -A3 position | head -4 | tee "$OUT/gzpose.txt"
echo "紀錄存在：$OUT"
pause "按 Enter 結束並關閉所有視窗... " 2
