#!/bin/bash
# 1) the yolo_model argument loads the right weights; 2) person range K with v5.
L=~/runs_2026-11-27_v5; T=~/robot_ws/tools/team; cd ~/robot_ws
source /opt/ros/jazzy/setup.bash; source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
PAT="[g]z sim|[c]amera_yolo|[p]arameter_bridge|[i]mage_bridge|[a]utonomy_controller|[t]eam_tracker|[t]eam_predictor|[t]eam_commander"
for case in default v5 coco bad; do
  case $case in default) A="" ;; bad) A="yolo_model:=v4" ;; *) A="yolo_model:=$case" ;; esac
  timeout -s INT 20 ros2 launch robot_control camera_yolo.launch.py device:=0 $A > $L/launch_$case.log 2>&1
  echo "$case: $(grep -aoE 'YOLO model loaded: \S+|not in choices.*|unknown yolo_model.*' $L/launch_$case.log | head -1)"
  pkill -f "$PAT"; sleep 2
done
timeout -s INT 25 ros2 launch robot_control autonomous_team.launch.py yolo_model:=v5 device:=0 > $L/launch_team_v5.log 2>&1
echo "team v5: $(grep -aoE 'YOLO model loaded: \S+' $L/launch_team_v5.log | head -1)"
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"; sleep 1
# person range calibration with v5 (same procedure as the v3 calibration)
setsid timeout 150 gz sim -s -r --headless-rendering worlds/diff_drive_camera_cup_person.sdf > $L/calib_gz.log 2>&1 &
sleep 6
setsid timeout -s INT 140 ros2 launch robot_control camera_yolo.launch.py device:=0 yolo_model:=v5 > $L/calib_launch.log 2>&1 &
sleep 15
timeout 110 python3 $T/calibrate_person.py > $L/calibration_v5.txt 2>&1
echo "calib model: $(grep -aoE 'YOLO model loaded: \S+' $L/calib_launch.log | head -1)"
tail -1 $L/calibration_v5.txt
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"
echo CHECK DONE
