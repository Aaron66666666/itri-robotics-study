#!/bin/bash
# 2026-11-28 night: lidar team vs baseline vs camera team, all in the lidar world (YOLO v3 default).
L=~/runs_2026-11-28; T=~/robot_ws/tools/team
export WORLD=worlds/diff_drive_camera_cup_person_lidar.sdf
exec >> $L/runner.log 2>&1
step() { echo "[$(date +%T)] $*"; }
step "L: S1-S6 x {baseline, team, team_lidar} x 2"
for r in 1 2; do for sc in S1 S2 S3 S4 S5 S6; do for m in baseline team team_lidar; do
  timeout 200 bash $T/run_scenario.sh $m $sc $L/lidar/rep$r 80 > $L/lidar_${sc}_${m}_$r.log 2>&1
  step "rep$r $sc $m: $(tail -1 $L/lidar_${sc}_${m}_$r.log | cut -c1-200)"
done; done; done
step "RND: random walks R1-R12 x {baseline, team, team_lidar}"
for s in $(seq 1 12); do for m in baseline team team_lidar; do
  timeout 200 bash $T/run_scenario.sh $m R$s $L/random 80 > $L/random_R${s}_${m}.log 2>&1
  step "R$s $m: $(tail -1 $L/random_R${s}_${m}.log | cut -c1-200)"
done; done
step "ALL DONE"
