# ROS 2 機器人自學專案進度

> 最新狀態：2026-11-24（Claude Code 接手）。舊紀錄保留於下方「2026-11-18/19 紀錄（Codex）」。完整階段報告：`docs/stage_report_2026-11-24.md`。

## 2026-11-24 進度（Claude Code）

### 總結

| 項目 | 狀態 |
|---|---|
| Workspace 建置／測試 | ✅ `colcon build` 通過；`colcon test` robot_control 21 passed、1 skipped；yolo_ros 2 passed、1 skipped |
| 即時 YOLO 診斷 | ✅ 找到原因（見下） |
| Camera→YOLO→Controller→Gazebo 閉環 | ✅ 以 odometry 與 Gazebo world pose 證實車輛實際移動與停止 |
| 短暫漏檢停車、長時間失去目標搜尋、人員最高優先停止、stale 停止 | ✅ 實機（Gazebo）驗證 |
| 人物模型端到端（真實影像 person 偵測→停車→恢復） | ✅ 連續 2 次通過 |
| UR5e 碰撞場景、關節控制、末端控制、Pick-and-Place | ✅ 連續 3 次成功（另一專案，見下） |

所有測試以 headless Gazebo（`gz sim -s -r --headless-rendering`）在此 WSL 環境執行，未重新安裝 ROS 2／Gazebo／YOLO。

### 即時 YOLO 診斷結果

1. 即時管線正常：瓶子場景 live frame（`docs/evidence/2026-11-24/bottle_world_live_frame_x0.png`）中瓶子置中可見；即時節點與同一 PNG 離線推論（同模型、CPU、conf=0.35）完全一致：`cup 0.4517`，bbox [281,258,359,414]。無 RGB/BGR、跳影格或例外問題。
2. `camera_test.jpg` 無框的原因：該檔由 `~/save_camera_image.py` 以 `cv2.imwrite` 存成 **JPEG**（有損）且車輛位置略有差異。live PNG 轉 JPEG：品質 95→0.46、90→0.42、75→0.07；`camera_test.jpg` 本身 cup 僅 0.31（< 0.35）。
3. 根本問題：Gazebo 的綠色圓柱「瓶子」對 YOLO26n 而言是很弱的目標——只在起始位置被判為 **cup**（不是 bottle），車往前 0.2 m 分數就降到 0.13，再近則變成 person/umbrella。所以車一移動就失去目標，這正是「之前能連續辨識 cup、後來不能」的原因。控制器 `target_class=bottle` 也永遠對不上 YOLO 的 `cup`。
4. 處理（不降低 YOLO conf）：新增測試場景 `worlds/diff_drive_camera_cup.sdf`——白色馬克杯（含把手、咖啡面）放在 0.15 m 小桌上，並加入正面補光（原太陽光由正前方背光，物體呈黑色剪影）。實測車位 x=0.0–0.55 m 時 cup 0.71–0.83，全部高於控制器門檻 0.5。原 bottle 場景未修改。

### 本輪程式修改（robot_ws）

- `src/robot_control/launch/autonomous_yolo.launch.py`
  - **修正參數洩漏**：camera include 以 `GroupAction(scoped=True)` 包住。原本 include 的 `confidence_threshold`（YOLO conf 0.35）覆寫了控制器同名參數，實測 `ros2 param dump` 控制器門檻為 0.35 而非預設 0.5。修正後為 0.5。
  - 轉傳 `device` 參數（原本 `device:=cpu` 在整合 launch 無效）。
  - cmd_vel bridge 加入 `/model/vehicle_blue/odometry`（Gazebo→ROS，唯讀）以驗證實際移動。
  - 新增 `stop_bbox_dimension` 參數（預設 `height`，行為不變）。
- `src/robot_control/robot_control/autonomous_controller.py`
  - **修正人員停止後不再接近目標**：人員與目標同時出現時，原程式 `target_latched = bool(targets)` 會把目標當成已完成動作，人員離開後只輸出 `target_action_complete` 而不再接近。改為只保留既有的 latch。
  - 短暫漏檢（`target_lost_wait`）不再清除已完成動作的 latch，避免目標閃爍造成重複執行目標動作。
  - 新增 `stop_bbox_dimension`（`height`/`width`）。杯子位於相機下方，靠近時底部被裁切、bbox 高度不單調；寬度單調遞增，適合作停止條件。
- `src/robot_control/test/test_autonomy_logic.py`：新增 6 個測試（漏檢後不重複動作、人員優先於近距離動作、cup 類別、寬度停止、人員離開後恢復接近、動作中遇人員不重新開始）。
- `src/robot_control/package.xml`：加入 `nav_msgs` exec_depend。
- `worlds/diff_drive_camera_cup.sdf`（新增）：杯子測試場景；odometry 發布頻率 20 Hz（原場景為 1 Hz，不足以驗證短時間停車）。
- `tools/acceptance/`（新增）：可重現的驗收腳本（說明見該目錄 README）。
- 證據：`docs/evidence/2026-11-24/`（launch log、參數、CSV、影格）。

### 自主控制驗收結果（cup 場景，低速）

參數：`target_class:=cup device:=cpu search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop stop_bbox_dimension:=width stop_bbox_ratio:=0.14`，控制器信心門檻 0.5、YOLO conf 0.35、`stale_timeout` 1.0、`target_loss_timeout` 0.5。

| 驗收項目 | 結果 | 證據 |
|---|---|---|
| 1. 偵測 cup | ✅ 連續 0.71–0.83 | A1_approach.csv |
| 2. Controller 取得目標 | ✅ `approach_target` | A1_approach.launch.log |
| 3. 車輛靠近 | ✅ 0.05 m/s 行駛 12.6 s，odometry x=0.5258 m；Gazebo world pose x=0.52575 m | A1_approach.gzpose.txt |
| 4. 停止條件後停止 | ✅ `target_action:stop`→`target_action_complete`，其後 35 s 位置不變、vx=0 | A1_approach.csv |
| 5. 短暫漏檢安全停止 | ✅ 0.25 s 漏檢：`target_lost_wait`，位移 ≤ 3.5 mm，之後恢復接近、未進入搜尋 | C1_inject.* |
| 6. 長時間失去目標→搜尋 | ✅ 實機把杯子移出畫面 12 s：`target_lost_wait`→`search_forward`（3 s, 0.15 m）→`search_timeout` 停車 | B1_loss.* |
| 7. 人員最高停止優先權 | ✅ 人員＋杯子 4 s、僅人員 3 s：`person_detected`，位移 ≤ 3.5 mm；人員離開後恢復接近 | C1_inject.* |
| 8. Gazebo 真的移動 | ✅ odometry 與 Gazebo world pose 一致 | 上述 |
| stale 停止 | ✅ 偵測停止發布 1.0 s 後 `stale_detections` 停車（期間依設計滑行約 0.05 m） | C1_inject.* |

註：項目 5、7 使用腳本產生的 `/yolo/detections`（因 Gazebo 場景沒有人員模型，且 gz set_pose 服務延遲約 0.4 s 無法製造 < 0.5 s 的漏檢），但控制器、ros_gz_bridge、Gazebo 車輛與 odometry 皆為真實執行；邏輯另有單元測試。C1 情境已重複執行 2 次，結果一致。

### UR5e Gazebo／MoveIt（`~/itri-robotics-study/projects/ur5e_gazebo_pick_place`）

- 發現並修正：
  1. **右夾指在 Gazebo 中從未移動**（控制器輸出有變化，Gazebo 關節狀態恆為 0）。原因：夾指起始位置剛好在關節限制邊界，DART 將其卡住。修正：兩指限制各加 2 mm 餘量。命令慣例、SRDF 與 `gripper_open/close.sh` 不變。
  2. **方塊不可達**：手臂底座在地面、桌面 0.70 m，由上往下夾取需 tool0 約 0.92 m，`/compute_ik` 回 NO_IK_SOLUTION（關閉碰撞檢查也一樣）。修正：URDF `mount_z`（預設 0.70）＋世界加入 `robot_pedestal`。
- 新增 `scripts/pick_place_demo.py`（MoveIt 服務／動作，分階段 scene/joints/ee/pick）、`scripts/run_pick_place.sh`、`scripts/cube_pose.sh`、`scripts/gripper_monitor.py`；launch 新增 `launch_rviz` 參數（預設 true）。
- 結果：碰撞場景（桌面、4 桌腳、方塊、底座）✅；關節控制誤差 ≤ 0.005 rad ✅；末端位姿誤差約 1 mm ✅；Pick-and-place 連續 3 次成功，方塊最終位置誤差 ≤ 1.2 mm ✅。
- 修改前檔案備份：`docs/backup_2026-11-24_before_pedestal/`；紀錄：`docs/evidence_2026-11-24/`。

### 人物模型端到端測試（2026-11-24）

- 新增 `worlds/diff_drive_camera_cup_person.sdf`：杯子場景 + Gazebo Fuel「Casual female」人物（起始停在車後方、不在畫面中）；`tools/acceptance/moveperson.sh` 以 gz set_pose 移動人物，`hook_person.sh` 在接近途中讓人物進入畫面 6 s 後離開。
- 離線探測（`person_probe.sh`）：人物在畫面中時 YOLO `person` 0.90–0.91，杯子仍為 cup 0.56–0.72（> 0.5，未被遮擋）。
- 實機結果（全部為真實相機影像與 YOLO，無注入訊息）：

| 執行 | 人物出現→`person_detected` | 人物在畫面中的車輛位移 | 人物離開→恢復 `approach_target` | 最終停止位置 |
|---|---|---|---|---|
| D1 | 94 ms | 2.6 mm 後 vx=0 維持 6 s；38/38 影格偵測到 person（0.915） | 147 ms | x=0.531 m |
| D2 | 180 ms | 停車 | 82 ms | x=0.523 m |

證據：`docs/evidence/2026-11-24/D1_person.*`、`D2_person.*`、`person_world_frame_person_in_view.png`。

### 仍待處理

- 使用者以 GUI（Gazebo + RViz）目視確認一次車輛閉環與 UR5e pick-and-place。
- `autonomous_yolo.launch.py` 預設 `target_class` 仍為 `bottle`；cup 場景需使用上表參數。是否把 cup 場景參數做成預設，待使用者決定。
- 原 bottle 場景若要繼續使用，需要更像瓶子的模型；YOLO26n 對目前的圓柱瓶子不穩定。
- `itri-robotics-study/projects/` 尚未加入 git（未提交任何變更）。

---

## 2026-11-18/19 紀錄（Codex）

## 開發環境

- WSL2 / Ubuntu 24.04.5 LTS / ROS 2 Jazzy
- Gazebo Harmonic（Gazebo Sim 8）
- Python 3.12
- YOLO26n、Ultralytics、PyTorch CPU 推論
- ROS workspace：`~/robot_ws`
- YOLO venv：`~/yolo_project/.venv`

## 已完成

- Gazebo 差速車、相機、ROS 2 Image Bridge、即時 YOLO 節點和自主控制器已存在。
- 即時節點訂閱 `/vehicle_blue/camera/image`，以 sensor-data QoS 接收影像，發布 `/yolo/detections` JSON 及 `/yolo/image` 標註影像。
- 控制器具備目標搜尋、置中、接近、目標動作、人員優先停止及 stale detection 安全停止邏輯。
- 比較 `/home/yulin/camera_test.jpg` 的檔案、OpenCV ndarray、`cv_bridge` 往返 ndarray：三種輸入均得到 `cup`，confidence `0.4988`；橋接前後 ndarray 像素相同。
- 以即時節點採用的系統 Python 匯入路徑（venv site-packages）對同一影格推論：`device=auto` 實際使用 CPU，結果同樣為 `cup 0.4988`。
- 加入預設關閉、明確指定路徑才執行的一次性 PNG 原始影格擷取，以及 encoding、影像統計、推論耗時、執行裝置和偵測信心值診斷記錄。
- 診斷 PNG 使用 exclusive-create，不會覆寫既有檔案；新增測試涵蓋無損保存、禁止覆寫及副檔名檢查。
- 執行完整 workspace 建置成功：`colcon build`，`robot_control`、`yolo_ros` 均完成。
- 執行完整 workspace 測試成功：`robot_control` 14 passed、1 skipped；`yolo_ros` 2 passed、1 skipped。
- `ros2 launch robot_control autonomous_yolo.launch.py --show-args` 成功，確認診斷影格參數經整合 Launch 傳遞；ROS log 暫存於 `/tmp`，未啟動節點。

## 本階段尚未完成

- 尚未擷取正在執行的 ROS camera topic 影格，因此無法逐像素與 `camera_test.jpg` 比對，也未能證明即時空 detections 的確切影格原因。
- 靜態程式及相同離線影格測試未發現會特別移除 cup 的邏輯；即時與離線差異最可能來自實際影格內容／時間差，但仍待 live frame 驗證。
- 此環境的 ROS graph 查詢因 socket 權限回報 `Operation not permitted`；本次沒有啟動 Gazebo 或 ROS 節點，故 Camera→YOLO→Autonomy→Gazebo 尚未完成本次端到端驗收。
- `camera_test.jpg` 的 cup confidence 為 0.4988；場景、物件尺寸、光照或模糊造成分數低於 0.35 是可能因素，尚未以 live frame 證實。
- workspace 的 `diff_drive_camera.sdf` 沒有 cup 模型；`diff_drive_camera_bottle.sdf` 放的是 bottle。若要測 cup，需使用含 cup 的場景或新增獨立測試場景。
- `autonomous_yolo.launch.py` 的 `target_class` 預設仍為 `bottle`。以 cup 測試自主控制時需指定 `target_class:=cup`；這不會影響 YOLO 本身的 detections。

## 本輪修改檔案

- `src/robot_control/camera_subscriber.py`：新增可選原始影格擷取與推論診斷。
- `src/robot_control/launch/camera_yolo.launch.py`、`src/robot_control/launch/autonomous_yolo.launch.py`：轉傳 `diagnostic_frame_path`，預設為空字串。
- `src/robot_control/test/test_camera_diagnostics.py`：新增三個診斷保存測試。
- `src/robot_control/robot_control/move_robot.py`、`src/robot_control/robot_control/read_odom.py`、`src/robot_control/launch/robot_control.launch.py`、`src/yolo_ros/yolo_ros/yolo_node.py`：只修正原有 Flake8 import/空白格式，不改執行邏輯。

## 已知限制

- WSL 中 `torch.cuda.is_available()` 為 False、CUDA device count 為 0；目前即時推論使用 CPU。
- `robot_ws/.git` 目前不是有效的 Git metadata，無法在此環境取得 `git status` 或提交差異。
- 文件 `docs/progress.md` 和 `docs/ros2-architecture.md` 先前不存在於此 workspace，已在此建立；另有學習紀錄位於 `~/itri-robotics-study/docs/`，本輪僅讀取，未修改該 workspace。

## 下一階段

既有學習規劃中，UR5e Gazebo/MoveIt 專案最明確的未完成工作是把工作桌與方塊加入 MoveIt 碰撞場景，完成 pick-and-place。優先完成這個既有階段，不在目前 WSL 環境安裝 Isaac Sim。

目前 WSL 可見約 15 GiB RAM，沒有可用 GPU 裝置。NVIDIA Isaac Sim 6.2 系統需求列出 32 GB RAM 與 RTX 4080 16 GB VRAM 最低規格；NVIDIA 開發者論壇亦說明目前 WSL2 不支援 Isaac Sim 所需 RTX 功能。因此 Isaac Sim 應留待符合條件的原生 Linux／Windows 或雲端 GPU 環境再評估。參考：[Isaac Sim 6.2 系統需求](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/requirements.html)、[NVIDIA 關於 WSL2 支援的說明](https://forums.developer.nvidia.com/t/is-it-possible-to-run-isaac-sim-in-wsl2/349609/2)。
