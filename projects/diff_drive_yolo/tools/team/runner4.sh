L=~/night_2026-11-27; exec >> $L/runner.log 2>&1
TM=~/itri-robotics-study/projects/tm5s_gazebo_pick_place/scripts; AG=~/itri-robotics-study/ai-agent; T=~/robot_ws/tools/team
echo "[$(date +%T)] E3: TM5S Gazebo, team 12 cases"
bash $TM/stop_all.sh > /dev/null 2>&1; bash $TM/start_vision.sh > $L/vision_start3.log 2>&1
rm -f $AG/eval_results/team_gazebo_llama_team.json.partial.jsonl
cd $AG && timeout 5400 python3 eval_team.py --backend gazebo --modes team --out eval_results/team_gazebo_llama_team.json > $L/team_gazebo3.log 2>&1
echo "[$(date +%T)] E3 $(grep SUMMARY $L/team_gazebo3.log | cut -c1-250)"; bash $TM/stop_all.sh > /dev/null 2>&1
for r in 1 2; do for sc in S1 S2 S3 S4 S5; do
  timeout 200 bash $T/run_scenario.sh team $sc $L/scenarios_hold/rep$r 80 > $L/hold_${sc}_$r.log 2>&1
  echo "[$(date +%T)] D4 rep$r $sc team(hold): $(tail -1 $L/hold_${sc}_$r.log | cut -c1-200)"
done; done
echo "[$(date +%T)] ALL DONE 4"
