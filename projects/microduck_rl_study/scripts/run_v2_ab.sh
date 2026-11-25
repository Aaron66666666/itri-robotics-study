#!/bin/bash
# Experiments A and B (train_tracking_v2.py), then a fixed-command evaluation.
# Waits until the user's TM5S GUI recording has finished (or ~/rl/START_NOW exists,
# or 3 h have passed) so training does not compete with Gazebo for the GPU.
set -u
LOG=~/rl/run_v2_ab.log
exec >> "$LOG" 2>&1
STUDY=~/itri-robotics-study/projects/microduck_rl_study/scripts
UV=~/rl/tools-venv/bin/uv
cd ~/rl/microduck_rl
R=logs/rsl_rl/velocity
BASE_RUN=2026-11-25_03-29-11_walk4096_resume2
T0=$(date +%s)
echo "[$(date +%T)] waiting for the TM5S recording to finish"

sim_running() { pgrep -f "[g]z sim|[m]ove_group" > /dev/null; }
recorded() { for d in ~/demo_videos/tm5s_*; do [ -f "$d/results.csv" ] && [ "$(stat -c %Y "$d/results.csv")" -gt "$T0" ] && return 0; done; return 1; }
while true; do
  if [ -f ~/rl/START_NOW ]; then echo "[$(date +%T)] START_NOW found"; break; fi
  if recorded && ! sim_running; then echo "[$(date +%T)] recording finished"; break; fi
  if [ $(( $(date +%s) - T0 )) -gt 10800 ] && ! sim_running; then echo "[$(date +%T)] 3 h passed, starting"; break; fi
  sleep 30
done
sleep 30
while sim_running; do sleep 30; done

train() {  # $1 = run name, rest = VAR=value settings for train_tracking_v2.py
  local name=$1; shift
  echo "[$(date +%T)] train $name start ($*)"
  env "$@" $UV run --locked python $STUDY/train_tracking_v2.py Mjlab-Velocity-Flat-MicroDuck-TrackV2 \
    --env.scene.num-envs 4096 --agent.logger tensorboard --agent.resume True \
    --agent.load-run $BASE_RUN --agent.load-checkpoint model_7997.pt \
    --agent.max-iterations 2000 --agent.run-name "$name" > ~/rl/train_$name.log 2>&1 < /dev/null
  echo "[$(date +%T)] train $name exit=$?"
}
train track_v2_A LIN_STD2=0.05 YAW_FINE_WEIGHT=2.0
train track_v2_B LIN_STD2=0.05 YAW_FINE_WEIGHT=2.0 HIP_ROLL_STD_WALK=0.08

last() { d=$(ls -td $R/*_$1 | head -1); echo "$d/$(ls $d | grep -E '^model_[0-9]+\.pt$' | sort -V | tail -1)"; }
A=$(last track_v2_A); B=$(last track_v2_B); TIGHT=$(last tight_track)
echo "[$(date +%T)] eval: $R/$BASE_RUN/model_7997.pt $TIGHT $A $B"
for P in off on; do
  MUJOCO_GL=egl .venv/bin/python $STUDY/eval_fixed_cmd.py \
    --checkpoints $R/$BASE_RUN/model_7997.pt "$TIGHT" "$A" "$B" \
    --num-envs 64 --seconds 20 --pushes $P --json-out ~/rl/eval/v2_push_$P.json \
    > ~/rl/eval/v2_push_$P.log 2>&1
  echo "[$(date +%T)] eval pushes=$P exit=$?"
done
for C in "$A" "$B"; do
  N=$(basename "$(dirname "$C")" | sed 's/.*_track_v2_/v2_/')_$(basename "$C" .pt | sed 's/model_//')
  $UV run --locked python scripts/export.py Mjlab-Velocity-Flat-MicroDuck --checkpoint-file "$C" \
    --onnx-file ~/rl/exports/walk_$N.onnx > ~/rl/export_$N.log 2>&1
  echo "[$(date +%T)] export $N exit=$?"
done
echo "[$(date +%T)] ALL DONE"
