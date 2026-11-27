#!/bin/bash
# Demo for a screen recording: the TM5S Tracker / Predictor / Commander team
# carries out five Chinese commands in Gazebo (table camera + YOLO v4 -> MoveIt
# picks), and the terminal shows, live, what each agent says. A recording
# camera with a three-quarter view is also saved as an mp4 with captions.
# Usage: bash demo_language_gui.sh
#   GUI=0     headless (no Gazebo window)      AUTO=1    no Enter prompts
#   RECORD=0  no mp4                            OUT=DIR   output folder
# Needs the local Ollama model (llama3.1:8b), as for ai-agent/eval_team.py.
S=$(cd "$(dirname "$0")" && pwd); AG=$(cd "$S/../../../ai-agent" && pwd)
OUT=${OUT:-$HOME/demo_videos/tm5s_team_$(date +%Y%m%d_%H%M%S)}; mkdir -p "$OUT"
source "$S/env.sh"
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log LOG_DIR=$OUT
REC=""
cleanup() {
  [ -n "$REC" ] && kill -INT "$REC" 2>/dev/null && sleep 3
  bash "$S/stop_all.sh" > /dev/null 2>&1
}
trap cleanup EXIT
pause() { [ "${AUTO:-0}" = 1 ] && sleep "${2:-1}" || read -r -p "$1"; }
bash "$S/stop_all.sh" > /dev/null 2>&1

echo "== 啟動 Gazebo、MoveIt 2 與桌面相機（約 1 分鐘）=="
G=""; [ "${GUI:-1}" = 1 ] && G=gui
GUI_EXTRA="launch_rviz:=false" bash "$S/start_vision.sh" demo $G || { echo "啟動失敗，請看 $OUT/launch.log"; exit 1; }
if [ "${RECORD:-1}" = 1 ]; then
  setsid ros2 run ros_gz_image image_bridge /demo_camera/image > "$OUT/demo_bridge.log" 2>&1 < /dev/null &
  sleep 3
  python3 "$S/record_camera.py" "$OUT/demo_camera.mp4" --caption "$OUT/caption.txt" > "$OUT/record.log" 2>&1 &
  REC=$!
fi
echo
echo "已就緒。請把 Gazebo 視窗和這個終端機並排，開始錄影。"
pause "準備好後按 Enter 開始（共 5 句指令，約 4 分鐘）... " 3
cd "$AG" && python3 demo_team.py --caption "$OUT/caption.txt" --out "$OUT/demo_steps.json" 2>&1 | tee "$OUT/demo.log"
echo
[ -n "$REC" ] && echo "錄影用相機的影片：$OUT/demo_camera.mp4"
echo "紀錄：$OUT"
pause "按 Enter 結束並關閉所有視窗... " 2
