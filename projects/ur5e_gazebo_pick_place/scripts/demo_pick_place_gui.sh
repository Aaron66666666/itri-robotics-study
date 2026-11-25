#!/bin/bash
# GUI demo: UR5e picks and places the cube 3 times in a row (Gazebo + RViz),
# and measures the cube's final position in Gazebo after each place.
# Usage: bash demo_pick_place_gui.sh      (AUTO=1 skips the Enter prompts)
S=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$HOME/demo_videos/ur5e_$(date +%Y%m%d_%H%M%S)}; mkdir -p "$OUT"
source /opt/ros/jazzy/setup.bash; source "$S/../ros2_ws/install/setup.bash"
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
PAT="[g]z sim|[m]ove_group|[r]viz2|[r]obot_state_publisher|[c]ontroller_manager|[r]os2_control_node|[p]arameter_bridge|[s]pawner|[p]ick_place_demo"
cleanup() { pkill -INT -f "[r]os2 launch ur5e_gripper_demo"; sleep 3; pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"; }
trap cleanup EXIT
pause() { [ "${AUTO:-0}" = 1 ] && sleep "${2:-1}" || read -r -p "$1"; }
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"

echo "== 啟動 Gazebo（含畫面）、MoveIt 2 與 RViz =="
bash "$S/start_moveit.sh" > "$OUT/launch.log" 2>&1 &
for i in $(seq 120); do grep -q "You can start planning now" "$OUT/launch.log" 2>/dev/null && break; sleep 1; done
grep -q "You can start planning now" "$OUT/launch.log" || { echo "MoveIt 沒有在 120 秒內就緒，請看 $OUT/launch.log"; exit 1; }
sleep 5
echo "MoveIt 已就緒。"
echo
echo "請把 Gazebo、RViz 和這個終端機排好，開始錄影。"
pause "準備好後按 Enter 開始（手臂會開始動作）... " 3

# Three moves in a row: A -> B, B -> C, C -> A.
MOVES=("0.40 0.50 0.30 0.65" "0.30 0.65 0.55 0.30" "0.55 0.30 0.40 0.50")
printf "%s\n" "次數,起點x,起點y,目標x,目標y,實測x,實測y,誤差x_mm,誤差y_mm,結果" > "$OUT/results.csv"
n=0
for m in "${MOVES[@]}"; do
  n=$((n+1)); set -- $m
  echo
  echo "=================================================================="
  echo " 第 $n 次取放：從 ($1, $2) 搬到 ($3, $4)"
  echo "=================================================================="
  bash "$S/run_pick_place.sh" --cube-x $1 --cube-y $2 --place-x $3 --place-y $4 2>&1 \
    | tee "$OUT/pick_$n.log"
  rc=${PIPESTATUS[0]}
  sleep 2
  pose=$(bash "$S/cube_pose.sh")
  read -r cx cy < <(echo "$pose" | sed -E 's/.*x=([-0-9.]+) y=([-0-9.]+).*/\1 \2/')
  ex=$(python3 -c "print(f'{($cx-$3)*1000:+.1f}')"); ey=$(python3 -c "print(f'{($cy-$4)*1000:+.1f}')")
  ok=$([ "$rc" = 0 ] && echo 成功 || echo 失敗)
  echo ">>> Gazebo 實測方塊位置：$pose"
  echo ">>> 和目標 ($3, $4) 的誤差：x ${ex} mm，y ${ey} mm（$ok）"
  echo "$n,$1,$2,$3,$4,$cx,$cy,$ex,$ey,$ok" >> "$OUT/results.csv"
done

echo
echo "== 結果（誤差單位：mm）=="
column -s, -t "$OUT/results.csv"
echo "紀錄存在：$OUT"
pause "按 Enter 結束並關閉所有視窗... " 2
