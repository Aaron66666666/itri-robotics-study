#!/bin/bash
# 2026-11-28 day: cluttered lidar world (pillars + wall), static-map lidar team (v3) vs the others.
L=~/runs_2026-11-28; T=~/robot_ws/tools/team
export WORLD=worlds/diff_drive_camera_cup_person_lidar_clutter.sdf
exec >> $L/runner_clutter.log 2>&1
step() { echo "[$(date +%T)] $*"; }
for r in 1 2; do for sc in S0 S1 S3 S4 S6; do for m in baseline team team_lidar2 team_lidar3; do
  [ "$m" = team_lidar2 ] && [ $r = 2 ] && continue   # stuck behind the pillar in every rep-1 run: shown once
  timeout 200 bash $T/run_scenario.sh $m $sc $L/clutter/rep$r 80 > $L/clutter_${sc}_${m}_$r.log 2>&1
  step "rep$r $sc $m: $(tail -1 $L/clutter_${sc}_${m}_$r.log | cut -c1-200)"
done; done; done
step "ALL DONE"
