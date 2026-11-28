#!/bin/bash
# Usage: run_scenario.sh MODE SCENARIO OUT_DIR [DURATION_S] [MODEL]
# MODE: baseline | team | team_safe | team_lidar | team_lidar2 | team_lidar3;  SCENARIO: S0..S6 or R<seed>
# MODEL: v3 (default) | v5 | coco, or a YOLO weights file.
# WORLD=worlds/....sdf overrides the world (team_lidar needs the lidar world).
# Baseline = the accepted controller (stops whenever a person is visible);
# team = Tracker/Predictor/Commander (autonomous_team.launch.py);
# team_lidar = the team with the 360-degree lidar (positions) + camera (labels);
# team_lidar2 = team_lidar that also stops for a near person walking up to the vehicle;
# team_lidar3 = team_lidar2 + a static lidar map (STATIC_MAP=..., record_static_map.sh): pillars / walls are not people.
T=$(cd "$(dirname "$0")" && pwd); WS=$(cd "$T/../.." && pwd); A=$WS/tools/acceptance
MODE=$1; SC=$2; OUT=$3; DUR=${4:-80}; MODEL=${5:-v3}
case $MODEL in v3|v5|coco) MODEL_ARG="yolo_model:=$MODEL" ;; *) MODEL_ARG="model_path:=$MODEL" ;; esac
NAME=${SC}_${MODE}; mkdir -p "$OUT"; cd "$WS"
source /opt/ros/jazzy/setup.bash; source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
PAT="[g]z sim|[a]utonomy_controller|[c]amera_yolo|[p]arameter_bridge|[i]mage_bridge|[t]eam_tracker|[t]eam_predictor|[t]eam_commander|[p]ose_logger.py|[w]alk_person.py|[m]oveperson.sh"
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"; sleep 1
WORLD=${WORLD:-worlds/diff_drive_camera_cup_person.sdf}
setsid timeout $((DUR + 25)) gz sim -s -r --headless-rendering $WORLD > "$OUT/$NAME.gz.log" 2>&1 &
sleep 6
python3 "$T/pose_logger.py" "$OUT/$NAME.poses.csv" > /dev/null 2>&1 &
LAUNCH=autonomous_yolo.launch.py; EXTRA=""
[ "$MODE" = team ] && LAUNCH=autonomous_team.launch.py
[ "$MODE" = team_safe ] && { LAUNCH=autonomous_team.launch.py; EXTRA="stop_radius:=1.0"; }
[ "$MODE" = team_lidar ] && { LAUNCH=autonomous_team.launch.py; EXTRA="lidar:=true near_clearance:=1.0"; }
[ "$MODE" = team_lidar2 ] && { LAUNCH=autonomous_team.launch.py; EXTRA="lidar:=true near_clearance:=1.0 approach_stop:=true"; }
[ "$MODE" = team_lidar3 ] && { LAUNCH=autonomous_team.launch.py; EXTRA="lidar:=true near_clearance:=1.0 approach_stop:=true static_map:=${STATIC_MAP:-$WS/maps/clutter_static_map.json}"; }
ARGS="$EXTRA target_class:=cup device:=0 search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop stop_bbox_dimension:=width stop_bbox_ratio:=0.185 $MODEL_ARG"
echo "WORLD=$WORLD ros2 launch robot_control $LAUNCH $ARGS" > "$OUT/$NAME.cmd"
setsid timeout -s INT $DUR ros2 launch robot_control $LAUNCH $ARGS > "$OUT/$NAME.launch.log" 2>&1 &
LP=$!
case $SC in
  S0) python3 "$T/walk_person.py" -- 0 1 "20,20" ;;                                 # nobody around
  S1) python3 "$T/walk_person.py" 12 0.4 "2.0,3.8;2.0,0.2" ;;                       # crossing the path
  S2) python3 "$T/walk_person.py" 8 0.4 "4.5,3.4;-1.5,3.4" ;;                       # parallel, 1.4 m to the side
  S3) python3 "$T/walk_person.py" 0 0.4 "3.5,3.3" ;;                                # standing at the side, in view (24 deg)
  S4) python3 "$T/walk_person.py" 10 0.3 "4.5,2.7;1.9,2.2;1.95,2.2;1.95,4.5" ;;     # head-on into the path, then away
  S5) bash "$A/hook_person.sh" ;;                                                   # accepted test: appears in front 6 s
  S6) python3 "$T/walk_person.py" -- 3 0.5 "-2.5,3.6;1.9,3.4;1.9,-0.5" ;;          # from behind-left, crosses close in front
  R*) python3 "$T/walk_person.py" -- $(python3 "$T/random_walk.py" "${SC#R}") ;;        # seeded random walk
esac > "$OUT/$NAME.walk.log" 2>&1 &
wait $LP; sleep 2
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"
python3 "$T/analyze.py" "$OUT/$NAME"
