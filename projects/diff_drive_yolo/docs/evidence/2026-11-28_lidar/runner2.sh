#!/bin/bash
# team_lidar2 (approach_stop) on S1-S6 x 2 and R1-R12, same lidar world as runner.sh.
L=~/runs_2026-11-28; T=~/robot_ws/tools/team
export WORLD=worlds/diff_drive_camera_cup_person_lidar.sdf
exec >> $L/runner.log 2>&1
step() { echo "[$(date +%T)] $*"; }
step "L2: S1-S6 x team_lidar2 x 2, R1-R12 x team_lidar2"
for r in 1 2; do for sc in S1 S2 S3 S4 S5 S6; do
  timeout 200 bash $T/run_scenario.sh team_lidar2 $sc $L/lidar/rep$r 80 > $L/lidar_${sc}_team_lidar2_$r.log 2>&1
  step "rep$r $sc team_lidar2: $(tail -1 $L/lidar_${sc}_team_lidar2_$r.log | cut -c1-200)"
done; done
for s in $(seq 1 12); do
  timeout 200 bash $T/run_scenario.sh team_lidar2 R$s $L/random 80 > $L/random_R${s}_team_lidar2.log 2>&1
  step "R$s team_lidar2: $(tail -1 $L/random_R${s}_team_lidar2.log | cut -c1-200)"
done
step "ALL DONE 2"
