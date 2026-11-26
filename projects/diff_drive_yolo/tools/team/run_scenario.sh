#!/bin/bash
# Usage: run_scenario.sh MODE(baseline|team) SCENARIO(S1..S5) OUT_DIR [DURATION_S] [MODEL]
# Baseline = the accepted controller (stops whenever a person is visible);
# team = Tracker/Predictor/Commander (autonomous_team.launch.py).
T=$(cd "$(dirname "$0")" && pwd); WS=$(cd "$T/../.." && pwd); A=$WS/tools/acceptance
MODE=$1; SC=$2; OUT=$3; DUR=${4:-80}; MODEL=${5:-$HOME/yolo_project/yolo26n_gazebo_v3.pt}
NAME=${SC}_${MODE}; mkdir -p "$OUT"; cd "$WS"
source /opt/ros/jazzy/setup.bash; source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
PAT="[g]z sim|[a]utonomy_controller|[c]amera_yolo|[p]arameter_bridge|[i]mage_bridge|[t]eam_tracker|[t]eam_predictor|[t]eam_commander|[p]ose_logger.py|[w]alk_person.py|[m]oveperson.sh"
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"; sleep 1
setsid timeout $((DUR + 25)) gz sim -s -r --headless-rendering worlds/diff_drive_camera_cup_person.sdf > "$OUT/$NAME.gz.log" 2>&1 &
sleep 6
python3 "$T/pose_logger.py" "$OUT/$NAME.poses.csv" > /dev/null 2>&1 &
LAUNCH=autonomous_yolo.launch.py; [ "$MODE" = team ] && LAUNCH=autonomous_team.launch.py
ARGS="target_class:=cup device:=0 search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop stop_bbox_dimension:=width stop_bbox_ratio:=0.185 model_path:=$MODEL"
echo "ros2 launch robot_control $LAUNCH $ARGS" > "$OUT/$NAME.cmd"
setsid timeout -s INT $DUR ros2 launch robot_control $LAUNCH $ARGS > "$OUT/$NAME.launch.log" 2>&1 &
LP=$!
case $SC in
  S1) python3 "$T/walk_person.py" 12 0.4 "2.0,3.8;2.0,0.2" ;;                       # crossing the path
  S2) python3 "$T/walk_person.py" 8 0.4 "4.5,3.4;-1.5,3.4" ;;                       # parallel, 1.4 m to the side
  S3) python3 "$T/walk_person.py" 0 0.4 "2.2,3.5" ;;                                # standing at the side
  S4) python3 "$T/walk_person.py" 10 0.3 "4.5,2.7;1.9,2.2;1.95,2.2;1.95,4.5" ;;     # head-on into the path, then away
  S5) bash "$A/hook_person.sh" ;;                                                   # accepted test: appears in front 6 s
esac > "$OUT/$NAME.walk.log" 2>&1 &
wait $LP; sleep 2
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"
python3 "$T/analyze.py" "$OUT/$NAME"
