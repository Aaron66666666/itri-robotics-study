# Claude Code 交接：ROS 2 Gazebo YOLO 差速車

## 1. 專案目標與架構

目標是在 Gazebo Harmonic 模擬差速車上，以前置相機取得影像，使用 YOLO26n 即時辨識目標，再由 ROS 2 控制器執行搜尋、置中、接近、目標動作和安全停止。此階段仍在驗證「相機 → YOLO → 控制器 → Gazebo 車輛」閉環；尚未完成車輛實際移動驗收。

```text
Gazebo world / vehicle_blue camera
  Gazebo Transport /vehicle_blue/camera/image
    → ros_gz_image image_bridge
    → /vehicle_blue/camera/image (sensor_msgs/Image)
    → camera_yolo / camera_subscriber.py (cv_bridge BGR8 + YOLO26n)
      → /yolo/detections (std_msgs/String, JSON)
      → /yolo/image (sensor_msgs/Image, annotated BGR8)
    → autonomy_controller (AutonomyLogic)
      → /model/vehicle_blue/cmd_vel (geometry_msgs/Twist)
      → ros_gz_bridge
      → Gazebo DiffDrive
      → odometry
```

`src/yolo_ros` 是較早期的固定圖片 YOLO 範例，不是相機閉環使用的節點。`move_robot` 是獨立手動示範節點；不可與 autonomy controller 同時啟動，兩者都會發佈 `/model/vehicle_blue/cmd_vel`。

## 2. 執行環境

- WSL2 / Ubuntu 24.04（進度記錄為 24.04.5 LTS）
- ROS 2 Jazzy；Python 3.12.3
- Gazebo Harmonic / Gazebo Sim 8
- YOLO26n 權重：`/home/yulin/yolo_project/yolo26n.pt`
- YOLO Python 環境：`/home/yulin/yolo_project/.venv`
- 推論基準：CPU。此 WSL 工作階段無可用 NVIDIA GPU；CPU 推論有 NVML 初始化警告但能完成。
- Workspace：`/home/yulin/robot_ws`
- `ros2`、`gz`、`colcon` 可執行；Launch 日誌需放到可寫目錄，例如 `ROS_HOME=/tmp/ros-home ROS_LOG_DIR=/tmp/ros-log`。
- 此 checkout 的 `.git` 是空目錄，不是有效 Git repository；`git status` 無法使用。

## 3. 專案目錄及重要檔案

- `src/robot_control/camera_subscriber.py`：即時相機訂閱、cv_bridge、YOLO 推論、JSON detections 與標註影像發布。
- `src/robot_control/robot_control/autonomous_controller.py`：`AutonomyLogic` 純邏輯與 ROS 2 `AutonomousController`。
- `src/robot_control/launch/camera_yolo.launch.py`：image bridge 與相機 YOLO 節點。
- `src/robot_control/launch/autonomous_yolo.launch.py`：相機 Launch、cmd_vel bridge 與 autonomy controller。
- `src/robot_control/launch/robot_control.launch.py`、`robot_control/move_robot.py`、`robot_control/read_odom.py`：原有移動示範及 odometry 節點。
- `src/robot_control/test/test_autonomy_logic.py`：控制器邏輯測試。
- `src/robot_control/test/test_camera_diagnostics.py`：診斷影格保存測試。
- `src/yolo_ros/yolo_ros/yolo_node.py`：固定圖片的舊 YOLO 範例。
- `worlds/diff_drive_camera.sdf`：差速車和相機基本場景，未放置瓶子測試物件。
- `worlds/diff_drive_camera_bottle.sdf`：瓶子測試場景，包含 `yolo_test_bottle`。
- `docs/progress.md`、`docs/ros2-architecture.md`、`docs/yolo-live-debugging.md`：先前的進度、架構與 live frame 診斷記錄；若與本文件或當前原始碼衝突，以原始碼和本次測試結果為準。

## 4. 已完成的功能及已知歷史結果

- 相機 SDF 設為 640×480；ROS 相機 topic 為 `/vehicle_blue/camera/image`。
- 相機節點以 sensor-data QoS 訂閱影像，要求 cv_bridge 輸出 `bgr8`。
- YOLO 模型沒有類別過濾；符合 YOLO conf 的類別皆放進 JSON detections。成功推論但沒有框時仍發布 `detections: []`；轉換或推論例外會記錄錯誤並略過該影格，不發布該影格結果。
- 歷史記錄指出即時影格曾辨識到 `cup:0.4517`，另一輪相同影像/流程曾得到 `cup:0.4988`。這些舊結果不代表目前影格仍有 cup。
- 本次於 2026-11-19 重新以 `/home/yulin/camera_test.jpg`、相同模型、CPU、conf=0.35 推論：`orig_shape=(480,640)`，結果 `detections=[]`。因此前後影像結果的變化是真實可重現的檔案輸入差異，但無法僅憑靜態檔案確定場景中目標移動、視角改變或光照等具體原因。
- 先前離線同影格比較曾驗證檔案、OpenCV ndarray 和 cv_bridge 往返像素一致，結果也相同。`desired_encoding='bgr8'` 以及輸出標註圖 `bgr8` 使用一致；目前沒有證據指向 RGB/BGR 轉換錯誤。

## 5. 本輪修改檔案與原因

- `src/robot_control/robot_control/autonomous_controller.py`：新增 `target_loss_timeout`（預設 0.5 秒）。目標剛消失時立即輸出零速度 `target_lost_wait`，在短暫漏檢期間保持停車；超時後才回到原有的限時搜尋行為。這處理了空陣列使 `approach_target` 立即切換 `search_forward` 的明確狀態邏輯，不放寬 YOLO 信心門檻，也不維持上一個前進速度。
- `src/robot_control/launch/autonomous_yolo.launch.py`：宣告並傳入 `target_loss_timeout` Launch 參數。
- `src/robot_control/camera_subscriber.py`：偵測類別/信心 signature 改變時立即記錄（包括轉為空陣列），其餘保留每 30 次推論記錄；推論錯誤日誌附上相機影格序號，協助分辨漏發和空 detections。
- `src/robot_control/test/test_autonomy_logic.py`：新增短暫漏檢停車、目標重新出現及超時搜尋測試。

本輪沒有修改 YOLO conf、車速、SDF 場景、模型權重或整體架構。由於沒有 live frame，本輪不能宣稱已找出 cup 消失的確切物理原因。

## 6. 本輪測試及完整結果

執行時間：2026-11-19 約 20:18（Asia/Taipei，UTC 約 12:18）。

- `python3 -m py_compile` 檢查 `camera_subscriber.py`、`autonomous_controller.py`、兩個 YOLO launch 檔及 `yolo_node.py`：通過，exit 0。
- `colcon build`（修改完成後）：通過，`robot_control`、`yolo_ros` 兩套件完成，約 0.91 秒。
- `colcon test --event-handlers console_direct+`（修改後）：通過。`robot_control`：15 passed、1 skipped；`yolo_ros`：2 passed、1 skipped。Flake8 有 16 個 fork/multithread 警告，測試未因此失敗。總計 17 passed、2 skipped。
- `ros2 launch robot_control autonomous_yolo.launch.py --show-args`：通過，列出新 `target_loss_timeout=0.5` 及其他參數。
- `ros2 launch robot_control camera_yolo.launch.py --show-args`：通過，列出影像、模型、conf、device、display 與 diagnostic frame 參數。
- YOLO 單張圖片測試：程式正常完成，但 `/home/yulin/camera_test.jpg` 在 CPU、conf=0.35 下為空 detections；這是測試結果，不是測試通過辨識目標。
- 測試過程紀錄：第一次新增單元測試的 bbox fixture 太大，實際觸發了近距離 action；修正 fixture 為小型置中框後，完整 `colcon test` 重跑通過。首次 `--show-args` 因 ROS_HOME 預設指向唯讀的 `/home/yulin/.ros` 失敗；設 `ROS_HOME`/`ROS_LOG_DIR` 至 `/tmp` 後兩個 launch 檢查均通過。
- ROS graph：`ros2 topic list --no-daemon` 只列出 `/parameter_events`、`/rosout`；DDS 顯示 `getifaddrs` / UDP socket `Operation not permitted`。未觀察到實際模擬 topic，故 topic、node、資料流整合未驗證。
- 未啟動 Gazebo，未取得當前 ROS live camera frame，未測量 `/model/vehicle_blue/odometry`，未證明車輛實際移動。不能宣稱端到端驗收成功。

## 7. 尚未解決的問題與已知原因範圍

1. **為什麼 cup 由有框變成空陣列：**本次最新圖片離線也無框，支持「輸入影像/目標可見程度不同」或模型對該圖的信心低於門檻；缺少舊圖與新圖、live frame 的同步影像和場景位置資料，無法區分物件移動、視角、遮擋、光照或尺寸。不要猜測性修改模型或 conf。
2. **是否因車輛移動/相機視角改變：**未驗證。瓶子在場景大約位於藍車前方（車初始 pose 約 `(0,2,0.325)`，瓶子模型 pose 約 `(2.8,2,0)`；相機相對車體前置約 x=0.8）。場景重啟、車輛移動或 Gazebo 初始模型狀態都可能影響影像，需擷取 live frame 及 odometry 確認。
3. **是否 RGB/BGR 錯誤：**程式路徑明確轉成 BGR8，歷史像素往返測試一致；目前無證據顯示轉換錯誤，但仍需同步比較當前 live PNG 和同一影格即時結果。
4. **是否跳影格/例外：**目前 callback 沒有刻意丟棄影格；每張成功推論的影格都會發布 JSON，無框發布空陣列。CPU 推論較相機頻率慢時，sensor-data QoS 可讓等待中的舊影像被取代，故時間取樣可能跳過。例外會記錄並跳過該影格。本輪新增影格序號與偵測狀態變化日誌；尚未在即時節點觀察。
5. **Controller 狀態跳轉：**已確認空 `detections` 以前會立即清除目標狀態並進入搜尋；本輪以 0.5 秒停止緩衝降低單次漏檢造成的狀態抖動。連續漏檢超時後仍會使用原有有限時搜尋。
6. **速度發布：**controller timer 每 0.1 秒發布目前 `Twist`，stale 資料會清零。`robot_control.launch.py` 的 `move_robot` 也發布同一 cmd_vel topic；不得與自主控制同時啟動。`autonomous_yolo.launch.py` 中的 bridge 是 ROS↔Gazebo 命令橋接。尚未在運行中的 graph/odometry 證明指令有到達或車輪移動。
7. **參數記錄差異：**目前 Launch 原始碼預設是 `stale_timeout=1.0`、`search_speed=0.1`、`approach_speed=0.1`；任務背景所述曾觀察到 `stale_timeout=3.0`、`search_speed=0.0`、`approach_speed=0.03`，可能是執行時 override 或另一個版本。下一次測試應保存啟動命令及 `ros2 param dump`，不要把歷史觀察當成目前預設。

## 8. Gazebo 場景及啟動指令

本 workspace 兩個測試 world 的相機 topic 都是 `/vehicle_blue/camera/image`。瓶子測試場景：`worlds/diff_drive_camera_bottle.sdf`；基本場景 `worlds/diff_drive_camera.sdf` 不含瓶子。啟動時先確認沒有另一個 Gazebo world 正在跑，避免重複模擬：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/yulin/robot_ws
source install/setup.bash
gz sim -r worlds/diff_drive_camera_bottle.sdf
```

另一個終端啟動閉環（診斷檔名須不存在；此設定以 CPU 為基準）：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/yulin/robot_ws
source install/setup.bash
ros2 launch robot_control autonomous_yolo.launch.py \
  device:=cpu target_class:=bottle \
  diagnostic_frame_path:=/tmp/yolo_live_frame.png
```

第一輪驗證控制器可先用 `search_speed:=0.0 approach_speed:=0.0` 觀察偵測和狀態，避免驗證階段移動。之後用小速度做受控 odometry 驗收；不要長時間開放搜尋或使用其他 cmd_vel publisher。若要測 cup，需提供場景中含 cup 的模型，並設 `target_class:=cup`；目前瓶子場景放的是 bottle。

## 9. ROS Topic、Node、重要參數

| 名稱 | 型別 / 用途 |
|---|---|
| `/vehicle_blue/camera/image` | `sensor_msgs/msg/Image`，Gazebo camera 經 `ros_gz_image image_bridge` 橋接，640×480 |
| `/yolo/detections` | `std_msgs/msg/String`，每個成功推論影格發 JSON；空結果為 `detections: []` |
| `/yolo/image` | `sensor_msgs/msg/Image`，YOLO 標註影格，BGR8 |
| `/model/vehicle_blue/cmd_vel` | `geometry_msgs/msg/Twist`，AutonomousController 每 0.1 秒發布；ros_gz_bridge 轉到 Gazebo |
| `/model/vehicle_blue/odometry` | Gazebo DiffDrive odometry；是否能見取決於 SDF/bridge/執行中的模擬 |

主要 Nodes：`camera_image_bridge`、`camera_yolo`（節點類別 `camera_subscriber`）、`autonomy_controller`、`cmd_vel_bridge`。

`autonomous_yolo.launch.py` 原始碼預設：`target_class=bottle`、YOLO conf `0.35`、controller confidence `0.5`、device `auto`、`stale_timeout=1.0`、`search_speed=0.1`、`search_duration=5.0`、`approach_speed=0.1`、`target_loss_timeout=0.5`、`alignment_speed=0.25`、`alignment_deadband=0.08`、`stop_bbox_ratio=0.55`、`target_action=turn_left`、`action_duration=1.5`、`linear_speed=0.2`、`angular_speed=0.6`。這些是程式預設值；運行參數可能被覆寫。

JSON detections 中每個 detection 有 `class_id`、`class_name`、`confidence`、`bbox_xyxy`，頂層含 `stamp`、`frame_id`、`image_size`。

## 10. 下一步測試建議

1. 在 ROS/DDS 可工作的 WSL 原生終端啟動既有 bottle world，僅啟動一個自主控制流程；確認 `move_robot` 沒有同時跑。
2. 先停車式觀測：`search_speed:=0.0 approach_speed:=0.0 device:=cpu`，設定一個新的 `diagnostic_frame_path`。確認 `/vehicle_blue/camera/image`、YOLO frame/inference 記錄及 `/yolo/detections` JSON 時戳、類別、信心值。
3. 用剛擷取的 PNG 離線重跑相同權重、CPU、conf=0.35。若 live inference 空且 PNG 離線也空，逐像素/畫面確認瓶子是否在視野；若 live empty、同一 PNG 離線有框，保存日誌、PNG、參數及套件路徑再查程序差異。
4. 查 `ros2 param dump /autonomy_controller`，記錄實際參數；確認短暫漏檢出現 `target_lost_wait` 並發零速度，連續漏檢才轉入限時搜尋。
5. 在設定低速及短時段下 echo `/model/vehicle_blue/cmd_vel` 並監看 `/model/vehicle_blue/odometry`；只有 odometry 確認變化才算車輛移動已驗證。每次測試中只保留一個 cmd_vel 控制來源。
6. 保存完整 console log、當前 world、影格、啟動命令和 odometry，完成相機到車輛端到端測試後再調整參數。

## 11. Claude Code 修改原則

- 先閱讀本交接文件及相關原始碼，以現況驗證歷史紀錄；不要假設不存在的檔案或參數。
- 先收集同步 live frame、detections、參數、速度和 odometry，再更動辨識/控制邏輯；不得靠降低信心門檻掩蓋影格差異。
- 保留 ROS 2 Jazzy、Gazebo Harmonic、現有 YOLO venv 與 workspace；不要重複安裝或重新下載既有模型。
- 只做針對已確認問題的最小修改；保留 stale 停車、人員優先停止、限時搜尋和目標接近停止行為。
- 測試需明確標記「命令完成但無偵測」與「通過」的差別；沒有 ROS graph/Gazebo/odometry 證據不得宣稱整合驗收完成。
- 不要安裝 Isaac Sim；不要開始 UR5e 新專案或無關重構。

## 12. 尚未完成的驗收標準

- live camera topic 穩定提供 640×480 影像，且可取得同步診斷 PNG。
- 同一影格即時與離線 CPU YOLO 結果可重現；空結果有影格/推論記錄可追查。
- 對目標時，JSON 類別/信心/bbox 正確；短暫漏檢先停車，資料 stale 時停車。
- `target_class` 與目標動作符合場景；人員優先停止邏輯保持有效。
- 只有一個 velocity controller；cmd_vel 與 odometry 證明低速車輛依預期移動，停車時速度回零。
- Camera→YOLO→Controller→Gazebo 端到端測試完整記錄並重複成功。

## 13. 下一階段 UR5e Gazebo / MoveIt 規劃背景

既有學習規劃提到後續 UR5e Gazebo/MoveIt 階段，主要待辦是將工作桌與方塊加入 MoveIt planning scene 的碰撞物件，完成 pick-and-place。先完成目前差速車 YOLO 閉環驗收；未取得既有 UR5e workspace/套件資料前，不要建立新專案或推測檔案路徑。Isaac Sim 不屬於本階段；本次明確不安裝 Isaac Sim。

## 14. 最後執行摘要

- **Codex 最後執行日期與時間：**2026-11-19 約 20:18 Asia/Taipei（UTC 約 12:18）。
- **最後一次成功建置：**本輪修改後 `colcon build` 成功，`robot_control`、`yolo_ros` 均完成。
- **最後一次測試：**`colcon test` 成功：`robot_control 15 passed, 1 skipped`；`yolo_ros 2 passed, 1 skipped`。Python 語法及兩個 Launch `--show-args` 也通過。
- **尚未驗證：**live camera frame、目前 cup/bottle 可見性、ROS graph 資料流、Gazebo 啟動、速度實際到達、車輛 odometry/移動、完整端到端自主控制。
- **Claude Code 第一個任務：**在可用 ROS/DDS 的 WSL 終端啟動既有 `diff_drive_camera_bottle.sdf`，以 CPU、零搜尋/接近速度擷取一張新的 live PNG；同步保存 YOLO log、`/yolo/detections`、實際參數和 odometry，再以相同模型/門檻離線推論該 PNG，定位目標不可見或 live/offline 不一致的原因。
- **不要重複安裝/建立：**Ubuntu/WSL、ROS 2 Jazzy、Gazebo Harmonic、Python 3.12、`/home/yulin/yolo_project/.venv`、YOLO26n 權重以及 `/home/yulin/robot_ws` workspace 均已存在；不要重新下載模型、重建 workspace 或開始 Isaac Sim/UR5e 新專案。
