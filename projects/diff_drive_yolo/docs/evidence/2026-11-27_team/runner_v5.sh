#!/bin/bash
# 2026-11-27: v3 default regression through the new yolo_model argument, then S1-S5 with v5.
L=~/runs_2026-11-27_v5; T=~/robot_ws/tools/team; A=~/robot_ws/tools/acceptance
exec >> $L/runner.log 2>&1
step() { echo "[$(date +%T)] $*"; }
step "R: F1-F4 with the launch defaults (expects v3)"
timeout 1500 bash $A/regress_model.sh default $L/v3_default_regression > $L/v3_default_regression.log 2>&1
step "R exit=$?"
for r in 1 2; do for sc in S1 S2 S3 S4 S5; do for m in baseline team; do
  timeout 200 bash $T/run_scenario.sh $m $sc $L/scenarios_v5/rep$r 80 v5 > $L/v5_${sc}_${m}_$r.log 2>&1
  step "rep$r $sc $m v5: $(tail -1 $L/v5_${sc}_${m}_$r.log | cut -c1-200)"
done; done; done
step "ALL DONE"
