#!/bin/bash
# Night of 2026-11-26, part 2: experiment D = experiment C settings on the upstream
# rough-terrain task, resumed from C. Then compare C and D on flat and rough
# terrain, record a rough-terrain video, export ONNX.
set -u
LOG=~/rl/run_night_d.log
exec >> "$LOG" 2>&1
STUDY=~/itri-robotics-study/projects/microduck_rl_study/scripts
UV=~/rl/tools-venv/bin/uv
cd ~/rl/microduck_rl
R=logs/rsl_rl/velocity
C_RUN=2026-11-26_00-47-33_track_v3_C
echo "[$(date +%T)] train track_v3_D_rough start"
env ROUGH=1 $UV run --locked python $STUDY/train_tracking_v3.py Mjlab-Velocity-Rough-MicroDuck-TrackV3 \
  --env.scene.num-envs 1024 --agent.logger tensorboard --agent.resume True \
  --agent.load-run $C_RUN --agent.load-checkpoint model_11995.pt \
  --agent.max-iterations 3000 --agent.run-name track_v3_D_rough > ~/rl/train_track_v3_D_rough.log 2>&1 < /dev/null
echo "[$(date +%T)] train D exit=$?"

last() { d=$(ls -td $R/*_$1 | head -1); echo "$d/$(ls $d | grep -E '^model_[0-9]+\.pt$' | sort -V | tail -1)"; }
A=$(last track_v2_A); C=$(last track_v3_C); D=$(last track_v3_D_rough)
echo "[$(date +%T)] checkpoints: $A $C $D"
for P in off on; do
  MUJOCO_GL=egl .venv/bin/python $STUDY/eval_fixed_cmd.py --checkpoints "$C" "$D" \
    --num-envs 64 --seconds 20 --pushes $P --json-out ~/rl/eval/flatCD_push_$P.json > ~/rl/eval/flatCD_push_$P.log 2>&1
  echo "[$(date +%T)] flat eval pushes=$P exit=$?"
done
MUJOCO_GL=egl .venv/bin/python $STUDY/eval_fixed_cmd.py --task Mjlab-Velocity-Rough-MicroDuck \
  --checkpoints "$A" "$C" "$D" --num-envs 64 --seconds 20 --pushes off \
  --json-out ~/rl/eval/roughACD_push_off.json > ~/rl/eval/roughACD_push_off.log 2>&1
echo "[$(date +%T)] rough eval exit=$?"
MUJOCO_GL=egl .venv/bin/python $STUDY/probe_cmd_grid.py --checkpoint "$D" --out ~/rl/probe/D_sweep.json > ~/rl/probe/D_sweep.log 2>&1
echo "[$(date +%T)] probe D exit=$?"
$UV run --locked python scripts/export.py Mjlab-Velocity-Flat-MicroDuck --checkpoint-file "$D" \
  --onnx-file ~/rl/exports/walk_v3_D_rough_$(basename "$D" .pt | sed 's/model_//').onnx > ~/rl/export_v3_D.log 2>&1
echo "[$(date +%T)] export D exit=$?"
for pair in "C:$C" "D:$D"; do
  n=${pair%%:*}; ck=${pair#*:}; dir=$(dirname "$ck")
  rm -rf "$dir/videos/play"
  MUJOCO_GL=egl timeout -k 10 420 $UV run --locked play Mjlab-Velocity-Rough-MicroDuck --agent trained \
    --checkpoint-file "$ck" --num-envs 1 --video True --video-length 500 --video-width 640 --video-height 480 \
    > ~/rl/play_rough_$n.log 2>&1 < /dev/null
  cp "$dir/videos/play/rl-video-step-0.mp4" ~/rl/play_rough_$n.mp4 && echo "[$(date +%T)] video $n ok"
done
echo "[$(date +%T)] ALL DONE"
