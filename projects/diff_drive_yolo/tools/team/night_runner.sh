#!/bin/bash
# GPU jobs of 2026-11-27 night, in order; each step logs and failures do not stop the rest.
L=~/night_2026-11-27; mkdir -p $L; exec >> $L/runner.log 2>&1
TASK_OUT=/tmp/claude-1000/-home-yulin/52e7aae4-bfd7-4bd4-92e2-5f007441ca04/tasks/barltqs97.output
T=~/robot_ws/tools/team; AG=~/itri-robotics-study/ai-agent; TM=~/itri-robotics-study/projects/tm5s_gazebo_pick_place/scripts
step() { echo "[$(date +%T)] $*"; }
step "wait for YOLO v5 chain"
until grep -qE "CHAIN DONE|TRAIN FAILED" $TASK_OUT 2>/dev/null; do sleep 30; done
tail -25 $TASK_OUT > $L/v5_eval.txt; step "v5 chain: $(grep -cE 'CHAIN DONE' $TASK_OUT) done"

step "A: team vs single on the fake table (12 cases x 2)"
cd $AG && timeout 3600 python3 eval_team.py --backend fake --modes single team --repeat 2 \
  --out eval_results/team_fake_llama.json > $L/team_fake.log 2>&1; step "A exit=$? $(grep SUMMARY $L/team_fake.log)"

step "B: car regression with v5"
timeout 1500 bash ~/robot_ws/tools/acceptance/regress_model.sh ~/yolo_project/yolo26n_gazebo_v5clean.pt $L/v5_regression \
  > $L/v5_regression.log 2>&1; step "B exit=$?"

step "C: person range calibration"
cd ~/robot_ws && source /opt/ros/jazzy/setup.bash && source install/setup.bash
export ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log
setsid timeout 150 gz sim -s -r --headless-rendering worlds/diff_drive_camera_cup_person.sdf > $L/calib_gz.log 2>&1 &
sleep 6
setsid timeout -s INT 140 ros2 launch robot_control camera_yolo.launch.py device:=0 > $L/calib_launch.log 2>&1 &
sleep 15
timeout 110 python3 $T/calibrate_person.py > $L/calibration.txt 2>&1
K=$(grep K_mean $L/calibration.txt | awk '{print $2}')
step "C: K=$K"
if python3 -c "import sys; k=float('$K'); sys.exit(0 if 500 < k < 2500 else 1)" 2>/dev/null; then
  sed -i "s/^RANGE_K = .*/RANGE_K = $K  # calibrated $(date +%F) (tools\/team\/calibrate_person.py)/" src/robot_control/robot_control/team_logic.py
  colcon build --packages-select robot_control > $L/calib_build.log 2>&1; step "C: RANGE_K set and rebuilt"
else step "C: calibration failed, RANGE_K unchanged"; fi
sleep 30

step "D: car scenarios"
for r in 1 2; do for sc in S1 S2 S3 S4 S5; do for m in baseline team; do
  timeout 200 bash $T/run_scenario.sh $m $sc $L/scenarios/rep$r 80 > $L/scenarios_${sc}_${m}_$r.log 2>&1
  step "D rep$r $sc $m: $(tail -1 $L/scenarios_${sc}_${m}_$r.log | cut -c1-160)"
done; done; done

step "E: TM5S Gazebo, single vs team (12 cases)"
bash $TM/stop_all.sh > /dev/null 2>&1; bash $TM/start_vision.sh > $L/vision_start.log 2>&1; step "E: $(tail -1 $L/vision_start.log)"
cd $AG && timeout 7200 python3 eval_team.py --backend gazebo --modes single team \
  --out eval_results/team_gazebo_llama.json > $L/team_gazebo.log 2>&1; step "E exit=$? $(grep SUMMARY $L/team_gazebo.log)"
bash $TM/stop_all.sh > /dev/null 2>&1
step "ALL DONE"
