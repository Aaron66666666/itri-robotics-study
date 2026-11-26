L=~/night_2026-11-27; exec >> $L/runner.log 2>&1
TM=~/itri-robotics-study/projects/tm5s_gazebo_pick_place/scripts; AG=~/itri-robotics-study/ai-agent; T=~/robot_ws/tools/team
echo "[$(date +%T)] E2: TM5S Gazebo, team (fixed) 12 cases"
bash $TM/stop_all.sh > /dev/null 2>&1; bash $TM/start_vision.sh > $L/vision_start2.log 2>&1
cd $AG && timeout 5400 python3 eval_team.py --backend gazebo --modes team --out eval_results/team_gazebo_llama_team.json > $L/team_gazebo2.log 2>&1
echo "[$(date +%T)] E2 $(grep SUMMARY $L/team_gazebo2.log)"; bash $TM/stop_all.sh > /dev/null 2>&1
for r in 1 2; do for m in baseline team; do
  timeout 200 bash $T/run_scenario.sh $m S3 $L/scenarios/rep$r 80 > $L/scenarios_S3_${m}_$r.log 2>&1
  echo "[$(date +%T)] D2 rep$r S3 $m: $(tail -1 $L/scenarios_S3_${m}_$r.log | cut -c1-200)"
done; done
echo "[$(date +%T)] ALL DONE 2"
