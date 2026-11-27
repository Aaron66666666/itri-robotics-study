# 差速車 + 相機 + YOLO 自主控制（Gazebo）

Gazebo Harmonic 差速車以前置相機取得影像，YOLO26n 即時辨識目標，ROS 2 控制器執行搜尋、置中、接近、目標動作與安全停止。本目錄是工作 workspace `~/robot_ws` 的版本控制副本（不含 build／install／log）。

```text
Gazebo camera → ros_gz_image bridge → /vehicle_blue/camera/image
  → camera_yolo（YOLO26n）→ /yolo/detections（JSON）、/yolo/image
  → autonomy_controller → /model/vehicle_blue/cmd_vel → ros_gz_bridge → Gazebo DiffDrive
  → /model/vehicle_blue/odometry（驗證實際移動）
```

## 進度

- [x] 相機 → YOLO → 控制器 → Gazebo 閉環；8 項驗收全部通過（2026-11-24），詳見 `docs/stage_report_2026-11-24.md`。
- [x] 人員偵測最高優先停止、短暫漏檢停車、長時間失去目標限時搜尋、偵測 stale 停車。
- [x] Gazebo 人物模型端到端測試：真實影像偵測 person 後停車、人物離開後恢復接近（2 次通過，場景 `worlds/diff_drive_camera_cup_person.sdf`）。
- [x] YOLO 自訂資料訓練（Gazebo 自動標註 + COCO 回放）：原瓶子場景可接近並停在瓶子前（`docs/yolo_training.md`）。
- [ ] 使用者以 GUI 目視確認。

## 環境

Ubuntu 24.04（WSL2）、ROS 2 Jazzy、Gazebo Harmonic、YOLO venv `~/yolo_project/.venv`、權重 `~/yolo_project/yolo26n_gazebo_v3.pt`（預設）、`yolo26n_gazebo_v5clean.pt`（v5）與 `yolo26n.pt`（原模型），皆不納入 git（見「YOLO 模型」）。

## 建置與執行

```bash
source /opt/ros/jazzy/setup.bash
cd projects/diff_drive_yolo/ros2_ws && colcon build && source install/setup.bash
cd .. && gz sim -r worlds/diff_drive_camera_cup.sdf
```

另一個終端：

```bash
source /opt/ros/jazzy/setup.bash && source projects/diff_drive_yolo/ros2_ws/install/setup.bash
ros2 launch robot_control autonomous_yolo.launch.py target_class:=cup device:=0 \
  search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop \
  stop_bbox_dimension:=width stop_bbox_ratio:=0.185
```

## YOLO 模型

三個模型都保留，用 `yolo_model:=` 選擇。`camera_yolo.launch.py`、`autonomous_yolo.launch.py`、`autonomous_team.launch.py` 都適用。權重放在 `~/yolo_project/`，不納入 git。

| `yolo_model` | 檔案 | 說明 |
|---|---|---|
| `v3`（預設） | `yolo26n_gazebo_v3.pt` | 階段 2：Gazebo 自動標註資料加 COCO128 回放微調（`docs/yolo_training.md`）。2026-11-24 的驗收都用它 |
| `v5` | `yolo26n_gazebo_v5clean.pt` | 資料和訓練方法都和 v3 相同，只是影像改用一般相機重新產生（v3 的訓練影像上有 Gazebo 畫的框）。乾淨測試集 mAP50 從 0.884 提高到 0.988 |
| `coco` | `yolo26n.pt` | 原 YOLO26n。原瓶子場景辨識不到瓶子 |

```bash
ros2 launch robot_control autonomous_yolo.launch.py yolo_model:=v5 ...
ros2 launch robot_control autonomous_team.launch.py yolo_model:=v5 ...
```

`model_path:=檔案` 仍可直接指定其他權重，並會覆蓋 `yolo_model`（節點會自行展開 `~`）。名稱打錯時，launch 會直接報錯並列出可用的名稱。v3 和 v5 的完整比較（辨識、閉環回歸、S1–S5 三代理場景）見 [`docs/three_agents_results.md`](../../docs/three_agents_results.md) 第三節。

**停止門檻依模型而不同**：v3、v5 的杯子框都包含把手，比原模型寬約 30%。v5 沿用 v3 的門檻，閉環回歸的停止位置和 v3 相差不到 3 cm。

| 目標 | v3、v5 | 原模型（`coco`） |
|---|---|---|
| 杯子（`stop_bbox_dimension:=width`） | `stop_bbox_ratio:=0.185` | `stop_bbox_ratio:=0.14` |
| 原瓶子場景的瓶子（`stop_bbox_dimension:=width`） | `stop_bbox_ratio:=0.22` | 原模型辨識不到瓶子 |

三代理用偵測框高度估計人的距離（`RANGE_K`）。v3 校正值為 989.1，v5 為 993.6，差 0.5%，所以共用 989.1。

### 權重不在 git 裡

`*.pt` 被 `.gitignore` 排除，模型檔與資料集都不在 repo 中。找不到權重檔時，相機節點會直接報錯，不會自動下載。取得方式（三選一）：

1. **本機已訓練過**：

   ```bash
   cp ~/yolo_project/runs/gazebo_ft/yolo26n_gazebo_v3/weights/best.pt ~/yolo_project/yolo26n_gazebo_v3.pt
   cp ~/yolo_project/runs/gazebo_ft/yolo26n_gazebo_v5clean/weights/best.pt ~/yolo_project/yolo26n_gazebo_v5clean.pt
   ```

2. **從另一台電腦複製**：把權重（各約 5.5 MB）放到 `~/yolo_project/`。可用 `sha256sum` 驗證，SHA-256 前 16 碼：v3（2026-11-24）為 `f99d3033ae1dfbae`，v5（2026-11-27）為 `481ef41091f75548`。

3. **重新訓練**（RTX 4070 約 10 分鐘產生資料、15 分鐘訓練；隨機種子固定，但 GPU 訓練不保證逐位元相同）。v3 和 v5 只差在產生資料時取哪一台相機的影像：

   ```bash
   # 回放用的 COCO128（只需一次）
   cd ~/yolo_project && .venv/bin/python -c "from ultralytics.data.utils import check_det_dataset as c; c('coco128.yaml')"
   # v5：一般相機的乾淨影像（build_dataset.sh 的預設）
   D=~/yolo_project/datasets/gazebo_bottle_cup_v5clean; NAME=yolo26n_gazebo_v5clean
   ~/robot_ws/tools/dataset/build_dataset.sh $D
   # v3：改取 boundingbox 相機自己的影像（上面有畫框），重現原本的資料
   #   D=~/yolo_project/datasets/gazebo_bottle_cup_v2; NAME=yolo26n_gazebo_v3
   #   IMAGE_TOPIC=/datagen/boxes_image ~/robot_ws/tools/dataset/build_dataset.sh $D
   python3 ~/robot_ws/tools/dataset/make_replay_yaml.py $D
   cd ~/yolo_project && .venv/bin/python -I ~/robot_ws/tools/dataset/train_yolo.py \
       $D/data_v3_replay.yaml --name $NAME --freeze 0
   cp runs/gazebo_ft/$NAME/weights/best.pt $NAME.pt
   ```

   重新訓練後，請用 `tools/dataset/eval_models.py` 和 `tools/acceptance` 的驗收腳本確認結果（`tools/acceptance/regress_model.sh v5 OUT_DIR`）。

## 目錄

- `ros2_ws/src/robot_control`：相機 YOLO 節點、自主控制器、Launch、單元測試。
- `ros2_ws/src/yolo_ros`：早期固定圖片 YOLO 範例。
- `worlds/`：`diff_drive_camera.sdf`（空場景）、`diff_drive_camera_bottle.sdf`（瓶子，YOLO 不穩定）、`diff_drive_camera_cup.sdf`（杯子，建議使用）、`diff_drive_camera_cup_person.sdf`（杯子 + 人物，人員停止測試；人物模型由 Gazebo Fuel 下載）。
- `tools/acceptance/`：headless 驗收腳本（`ROBOT_WS` 指定 workspace，預設 `~/robot_ws`）。
- `tools/dataset/`：合成資料產生（Gazebo 自動標註）、YOLO 訓練與評估。
- `docs/`：進度、架構、YOLO 診斷、交接文件、階段報告與 2026-11-24 驗收證據。
