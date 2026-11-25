# itri-robotics-study

ITRI Robotics Self-Study: ROS 2, Gazebo, YOLO, AI Agents and reinforcement learning.

- 進度：[`docs/progress.md`](docs/progress.md)
- 問題與排除紀錄：[`docs/troubleshooting.md`](docs/troubleshooting.md)
- ROS 2 架構筆記：[`docs/ros2-architecture.md`](docs/ros2-architecture.md)

## 各階段的程式、測試與原始紀錄

| 階段 | 程式 | 測試／驗收腳本 | 原始紀錄（log、評估結果） |
|---|---|---|---|
| 自走車 + YOLO 自主控制 | [`projects/diff_drive_yolo/ros2_ws/src`](projects/diff_drive_yolo/ros2_ws/src)、[`worlds`](projects/diff_drive_yolo/worlds) | 單元測試：`ros2_ws/src/*/test`；閉環驗收：[`tools/acceptance`](projects/diff_drive_yolo/tools/acceptance) | [`docs/evidence/2026-11-24`](projects/diff_drive_yolo/docs/evidence/2026-11-24)：每個情境的 launch log、odometry CSV、Gazebo 實際位置、參數 |
| UR5e 取放 | [`projects/ur5e_gazebo_pick_place/ros2_ws/src`](projects/ur5e_gazebo_pick_place/ros2_ws/src)（含場景與 URDF） | [`scripts/run_pick_place.sh`](projects/ur5e_gazebo_pick_place/scripts/run_pick_place.sh)、`check_environment.sh`、`cube_pose.sh` | [`docs/evidence_2026-11-24`](projects/ur5e_gazebo_pick_place/docs/evidence_2026-11-24)：每次取放的 log（含修正前失敗的紀錄） |
| 階段 1：AI Agent | [`ai-agent/robot_agent`](ai-agent/robot_agent)、`run_agent.py` | [`ai-agent/tests`](ai-agent/tests)（59 項）、`eval_models.py`、`eval_reviewer.py` | [`ai-agent/eval_results`](ai-agent/eval_results)：模型比較 JSON、真實工具實測紀錄 |
| 階段 2：YOLO 自訂資料訓練 | [`projects/diff_drive_yolo/tools/dataset`](projects/diff_drive_yolo/tools/dataset) | `eval_models.py`、閉環重跑：`tools/acceptance` | [`docs/evidence/2026-11-24/yolo_training`](projects/diff_drive_yolo/docs/evidence/2026-11-24/yolo_training)、[`v3_default`](projects/diff_drive_yolo/docs/evidence/2026-11-24/v3_default)；說明：[`yolo_training.md`](projects/diff_drive_yolo/docs/yolo_training.md) |
| 階段 4：microduck RL | [`projects/microduck_rl_study/scripts`](projects/microduck_rl_study/scripts)（上游程式碼不在本 repo） | `eval_fixed_cmd.py`、`check_onnx.py` | [`docs/eval`](projects/microduck_rl_study/docs/eval)（評估 JSON）、[`docs/raw_logs`](projects/microduck_rl_study/docs/raw_logs)（訓練 log、評估輸出、TensorBoard 數值 CSV，gzip 壓縮） |

不放進 repo 的檔案：模型權重（YOLO `.pt`、microduck `.pt`／`.onnx`）、影片、第三方上游程式碼與授權不允許散布的 3D 模型。取得或重新產生的方法寫在各專案的 README。
