# 自主控制驗收工具（2026-11-24）

全部以 headless Gazebo 執行，不需 GUI。輸出預設寫到 `/tmp/robot_acceptance`（可用 `OUT=...` 覆寫）。
執行前請確認沒有其他 Gazebo / `move_robot` 在跑；腳本開頭會結束先前由這些腳本啟動的 Gazebo、bridge、controller。

| 腳本 | 用途 |
|---|---|
| `run.sh NAME SECONDS [launch args]` | 啟動 headless Gazebo（`WORLD=` 指定場景）＋`autonomous_yolo.launch.py`＋`recorder.py`，保存 launch log、`ros2 param dump`、CSV（detections/cmd_vel/odometry）、結束時 Gazebo world pose。`HOOK=` 可在背景執行另一腳本（例如 `hook_loss.sh`）。 |
| `report.sh NAME` | 摘要一次 `run.sh` 的狀態轉換、參數、odometry、detections。 |
| `run_inject.sh` + `scenario.py` | 以腳本發布 `/yolo/detections`（短暫漏檢、人員＋杯子、僅人員、停止發布），驅動真實 controller＋bridge＋Gazebo 車輛。 |
| `phase_odom.py /tmp/robot_acceptance/C1_inject` | 依情境階段列出 odometry 位移與 cmd_vel。 |
| `hook_loss.sh`、`movecup.sh` | 以 `gz service set_pose` 把杯子移出／移回畫面（短暫／長時間失去目標）。 |
| `sweep.sh`、`grab.py`、`yscan.py` | 把車放在不同 x 位置擷取影格，離線用 YOLO 評分（距離對信心的影響）。 |
| `person_probe.sh`、`moveperson.sh`、`hook_person.sh` | 人物模型測試：探測人物各位置的 YOLO 分數；接近途中讓人物進出畫面（場景 `worlds/diff_drive_camera_cup_person.sdf`）。 |
| `gpu_check.py PNG [RUNS]` | 顯示 PyTorch／CUDA 狀態，並比較 CPU 與 GPU 推論延遲及偵測結果（以 YOLO venv 的 python 執行）。 |
| `offline.py PNG...` | 同模型、CPU、conf 0.35／0.05 離線推論。 |

## 重現驗收

```bash
cd ~/robot_ws/tools/acceptance
WORLD=worlds/diff_drive_camera_cup.sdf ./run.sh A1_approach 60 target_class:=cup device:=cpu \
  search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop \
  stop_bbox_dimension:=width stop_bbox_ratio:=0.14
./report.sh A1_approach
```

```bash
cd ~/robot_ws/tools/acceptance
HOOK=$PWD/hook_loss.sh WORLD=worlds/diff_drive_camera_cup.sdf ./run.sh B1_loss 55 target_class:=cup device:=cpu \
  search_speed:=0.05 search_duration:=3.0 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop \
  stop_bbox_dimension:=width stop_bbox_ratio:=0.14
./report.sh B1_loss
```

```bash
cd ~/robot_ws/tools/acceptance && ./run_inject.sh && python3 phase_odom.py /tmp/robot_acceptance/C1_inject
```

```bash
cd ~/robot_ws/tools/acceptance
HOOK=$PWD/hook_person.sh WORLD=worlds/diff_drive_camera_cup_person.sdf ./run.sh D1_person 55 target_class:=cup device:=cpu \
  search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop \
  stop_bbox_dimension:=width stop_bbox_ratio:=0.14
./report.sh D1_person
```

注意：在外層 shell 指令中不要直接包含 `autonomy_controller`、`camera_yolo`、`recorder.py` 等字樣再呼叫這些腳本的清理步驟，`pkill -f` 會比對到外層 shell 本身。
