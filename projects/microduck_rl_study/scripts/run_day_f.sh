#!/bin/bash
# 2026-11-28 day: experiment F (lateral air_time window 0.20 s), then the same evaluation as C/E and gait analysis.
set -u
LOG=~/rl/run_day_f.log
exec >> "$LOG" 2>&1
STUDY=~/itri-robotics-study/projects/microduck_rl_study/scripts
UV=~/rl/tools-venv/bin/uv
cd ~/rl/microduck_rl
R=logs/rsl_rl/velocity
C_RUN=2026-11-26_00-47-33_track_v3_C
echo "[$(date +%T)] train track_v3_F start"
$UV run --locked python $STUDY/train_cadence_f.py Mjlab-Velocity-Flat-MicroDuck-TrackV3F \
  --env.scene.num-envs 4096 --agent.logger tensorboard --agent.resume True \
  --agent.load-run $C_RUN --agent.load-checkpoint model_11995.pt \
  --agent.max-iterations 2000 --agent.run-name track_v3_F > ~/rl/train_track_v3_F.log 2>&1 < /dev/null
echo "[$(date +%T)] train track_v3_F exit=$?"
last() { d=$(ls -td $R/*_$1 | head -1); echo "$d/$(ls $d | grep -E '^model_[0-9]+\.pt$' | sort -V | tail -1)"; }
C=$R/$C_RUN/model_11995.pt; F=$(last track_v3_F)
echo "[$(date +%T)] checkpoints: $C $F"
for P in off on; do
  MUJOCO_GL=egl .venv/bin/python $STUDY/eval_fixed_cmd.py --checkpoints "$C" "$F" \
    --num-envs 64 --seconds 20 --pushes $P --json-out ~/rl/eval/flatCF_push_$P.json > ~/rl/eval/flatCF_push_$P.log 2>&1
  echo "[$(date +%T)] eval pushes=$P exit=$?"
done
MUJOCO_GL=egl .venv/bin/python $STUDY/probe_cmd_grid.py --checkpoint "$F" --out ~/rl/probe/F_sweep.json > ~/rl/probe/F_sweep.log 2>&1
echo "[$(date +%T)] probe F exit=$?"
MUJOCO_GL=egl .venv/bin/python $STUDY/gait_analysis.py --checkpoint "$F" \
  --commands 0.15,0,0 0.3,0,0 0.5,0,0 0,0.15,0 0,0.3,0 0,0.5,0 0,-0.3,0 0,0,0 --json-out ~/rl/gait/F_gait.json > ~/rl/gait/F_gait.log 2>&1
echo "[$(date +%T)] gait F exit=$?"
$UV run --locked python scripts/export.py Mjlab-Velocity-Flat-MicroDuck --checkpoint-file "$F" \
  --onnx-file ~/rl/exports/walk_v3_F_$(basename "$F" .pt | sed 's/model_//').onnx > ~/rl/export_v3_F.log 2>&1
echo "[$(date +%T)] export F exit=$?"
echo "[$(date +%T)] ALL DONE"
