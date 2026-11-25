#!/bin/bash
# Night of 2026-11-26: train experiment C, re-run the (fixed) evaluation for every
# version, probe command responses, and calibrate/validate a command remap.
set -u
LOG=~/rl/run_night_c.log
exec >> "$LOG" 2>&1
STUDY=~/itri-robotics-study/projects/microduck_rl_study/scripts
UV=~/rl/tools-venv/bin/uv
cd ~/rl/microduck_rl
R=logs/rsl_rl/velocity
A_RUN=2026-11-25_20-42-20_track_v2_A
echo "[$(date +%T)] train track_v3_C start"
$UV run --locked python $STUDY/train_tracking_v3.py Mjlab-Velocity-Flat-MicroDuck-TrackV3 \
  --env.scene.num-envs 4096 --agent.logger tensorboard --agent.resume True \
  --agent.load-run $A_RUN --agent.load-checkpoint model_9996.pt \
  --agent.max-iterations 2000 --agent.run-name track_v3_C > ~/rl/train_track_v3_C.log 2>&1 < /dev/null
echo "[$(date +%T)] train track_v3_C exit=$?"

last() { d=$(ls -td $R/*_$1 | head -1); echo "$d/$(ls $d | grep -E '^model_[0-9]+\.pt$' | sort -V | tail -1)"; }
B7997=$R/2026-11-25_03-29-11_walk4096_resume2/model_7997.pt
TIGHT=$(last tight_track); A=$(last track_v2_A); B=$(last track_v2_B); C=$(last track_v3_C)
echo "[$(date +%T)] checkpoints: $B7997 $TIGHT $A $B $C"
for P in off on; do
  MUJOCO_GL=egl .venv/bin/python $STUDY/eval_fixed_cmd.py --checkpoints $B7997 "$TIGHT" "$A" "$B" "$C" \
    --num-envs 64 --seconds 20 --pushes $P --json-out ~/rl/eval/fixed2_push_$P.json > ~/rl/eval/fixed2_push_$P.log 2>&1
  echo "[$(date +%T)] eval pushes=$P exit=$?"
done
for pair in "7997:$B7997" "tight:$TIGHT" "A:$A" "B:$B" "C:$C"; do
  n=${pair%%:*}; ck=${pair#*:}
  MUJOCO_GL=egl .venv/bin/python $STUDY/probe_cmd_grid.py --checkpoint "$ck" --out ~/rl/probe/${n}_sweep.json > ~/rl/probe/${n}_sweep.log 2>&1
  echo "[$(date +%T)] probe $n exit=$?"
done
$UV run --locked python scripts/export.py Mjlab-Velocity-Flat-MicroDuck --checkpoint-file "$C" \
  --onnx-file ~/rl/exports/walk_v3_C_$(basename "$C" .pt | sed 's/model_//').onnx > ~/rl/export_v3_C.log 2>&1
echo "[$(date +%T)] export C exit=$?"
for n in A C; do
  ck=$([ $n = A ] && echo "$A" || echo "$C")
  if [ -f $STUDY/cmd_remap.py ]; then
    .venv/bin/python $STUDY/cmd_remap.py build ~/rl/probe/${n}_sweep.json ~/rl/probe/${n}_remap.json > ~/rl/probe/${n}_remap_build.log 2>&1
    MUJOCO_GL=egl .venv/bin/python $STUDY/cmd_remap.py validate --checkpoint "$ck" --remap ~/rl/probe/${n}_remap.json \
      --out ~/rl/probe/${n}_remap_validate.json > ~/rl/probe/${n}_remap_validate.log 2>&1
    echo "[$(date +%T)] remap $n exit=$?"
  fi
done
echo "[$(date +%T)] ALL DONE"
