#!/bin/bash
# Night of 2026-11-28: experiment E = C + more pure-lateral commands (resume C, 2000 iterations),
# then the same fixed-command evaluation (C vs E, pushes off/on), the command-response probe and export.
set -u
LOG=~/rl/run_night_e.log
exec >> "$LOG" 2>&1
STUDY=~/itri-robotics-study/projects/microduck_rl_study/scripts
UV=~/rl/tools-venv/bin/uv
cd ~/rl/microduck_rl
R=logs/rsl_rl/velocity
C_RUN=2026-11-26_00-47-33_track_v3_C
echo "[$(date +%T)] train track_v3_E start (AXIS_BUCKET=0.4 LATERAL_SHARE=0.8)"
AXIS_BUCKET=0.4 LATERAL_SHARE=0.8 $UV run --locked python $STUDY/train_tracking_v3.py Mjlab-Velocity-Flat-MicroDuck-TrackV3 \
  --env.scene.num-envs 4096 --agent.logger tensorboard --agent.resume True \
  --agent.load-run $C_RUN --agent.load-checkpoint model_11995.pt \
  --agent.max-iterations 2000 --agent.run-name track_v3_E > ~/rl/train_track_v3_E.log 2>&1 < /dev/null
echo "[$(date +%T)] train track_v3_E exit=$?"
last() { d=$(ls -td $R/*_$1 | head -1); echo "$d/$(ls $d | grep -E '^model_[0-9]+\.pt$' | sort -V | tail -1)"; }
C=$R/$C_RUN/model_11995.pt; E=$(last track_v3_E)
echo "[$(date +%T)] checkpoints: $C $E"
for P in off on; do
  MUJOCO_GL=egl .venv/bin/python $STUDY/eval_fixed_cmd.py --checkpoints "$C" "$E" \
    --num-envs 64 --seconds 20 --pushes $P --json-out ~/rl/eval/flatCE_push_$P.json > ~/rl/eval/flatCE_push_$P.log 2>&1
  echo "[$(date +%T)] eval pushes=$P exit=$?"
done
MUJOCO_GL=egl .venv/bin/python $STUDY/probe_cmd_grid.py --checkpoint "$E" --out ~/rl/probe/E_sweep.json > ~/rl/probe/E_sweep.log 2>&1
echo "[$(date +%T)] probe E exit=$?"
$UV run --locked python scripts/export.py Mjlab-Velocity-Flat-MicroDuck --checkpoint-file "$E" \
  --onnx-file ~/rl/exports/walk_v3_E_$(basename "$E" .pt | sed 's/model_//').onnx > ~/rl/export_v3_E.log 2>&1
echo "[$(date +%T)] export E exit=$?"
echo "[$(date +%T)] ALL DONE"
