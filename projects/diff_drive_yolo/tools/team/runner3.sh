L=~/night_2026-11-27; exec >> $L/runner.log 2>&1; T=~/robot_ws/tools/team
until grep -q "ALL DONE 2" $L/runner.log; do sleep 30; done
for r in 1 2; do for sc in S2 S4 S1; do
  timeout 200 bash $T/run_scenario.sh team_safe $sc $L/scenarios/rep$r 80 > $L/scenarios_${sc}_team_safe_$r.log 2>&1
  echo "[$(date +%T)] D3 rep$r $sc team_safe: $(tail -1 $L/scenarios_${sc}_team_safe_$r.log | cut -c1-200)"
done; done
echo "[$(date +%T)] ALL DONE 3"
