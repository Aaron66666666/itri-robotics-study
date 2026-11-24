# ROS 2 程式架構學習筆記

## 1. ROS 2 是什麼？

ROS 2 是機器人開發框架，提供節點、訊息傳遞、程式管理等功能，讓不同程式能夠互相合作。

## 2. Node（節點）

Node 是 ROS 2 中負責特定工作的程式。例如，控制車輛的程式是一個 Node，讀取車輛位置的程式則是另一個 Node。

## 3. Topic（主題）

Topic 是 ROS 2 節點之間傳遞資料的通道。節點可以透過 Topic 發送或接收訊息。

本次實作使用的 Topic：

| Topic | 型別 | 用途 |
|---|---|---|
| `/model/vehicle_blue/cmd_vel` | `geometry_msgs/Twist` | 傳送藍色車輛的速度控制指令 |
| `/model/vehicle_blue/odometry` | `nav_msgs/Odometry` | 讀取藍色車輛的位置與運動資訊 |
| `/vehicle_blue/camera/image` | `sensor_msgs/Image` | 車前相機影像，640×480 |
| `/yolo/detections` | `std_msgs/String`（JSON） | YOLO 偵測結果：類別、信心值、bbox、影像尺寸 |
| `/yolo/image` | `sensor_msgs/Image` | 畫好辨識框的標註影像 |

## 4. Publisher（發布者）

Publisher 負責向 Topic 發布訊息。

實際操作中，`move_robot.py` 會發布 `Twist` 訊息，控制車輛前進、轉彎或停止。

## 5. Subscriber（訂閱者）

Subscriber 負責接收 Topic 上的訊息。

實際操作中，`read_odom.py` 訂閱 Odometry Topic，持續讀取車輛的 X、Y 座標與前進速度。

## 6. Gazebo 與 ROS 2 Bridge

Gazebo 是機器人模擬器，可以模擬機器人、環境與物理運動。

ROS 2 Bridge 負責在 ROS 2 與 Gazebo Transport 之間轉換並傳遞訊息，讓 ROS 2 程式可以控制 Gazebo 中的車輛，並讀取模擬器提供的資料。

本次實作使用兩種 Bridge：

- `ros_gz_bridge`（`parameter_bridge`）：ROS→Gazebo 傳送 `cmd_vel`；Gazebo→ROS 傳回 `odometry`。
- `ros_gz_image`（`image_bridge`）：Gazebo→ROS 傳送相機影像，使用 sensor-data QoS。

Bridge 參數中 `@` 表示雙向、`[` 表示 Gazebo→ROS、`]` 表示 ROS→Gazebo，例如 `/model/vehicle_blue/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry`。

## 7. 本次專案的資料流向

### 車輛控制

1. `move_robot.py` 發布 `Twist` 速度指令。
2. 指令透過 `/model/vehicle_blue/cmd_vel` 傳遞。
3. ROS 2 Bridge 將訊息轉換並傳送至 Gazebo。
4. Gazebo 根據指令模擬車輛前進、轉彎或停止。

### 讀取車輛位置

1. Gazebo 模擬車輛的運動狀態。
2. ROS 2 Bridge 將 Gazebo 的 Odometry 訊息轉換為 ROS 2 訊息。
3. `read_odom.py` 訂閱 `/model/vehicle_blue/odometry`。
4. 程式持續輸出車輛的 X、Y 座標與前進速度。

## 8. 相機 + YOLO 節點（`camera_yolo`）

`camera_subscriber.py` 是一個同時訂閱與發布的 Node：

1. 以 sensor-data QoS 訂閱 `/vehicle_blue/camera/image`；推論比相機慢時，舊影格會被新影格取代，不會累積延遲。
2. 用 `cv_bridge` 轉成 OpenCV BGR 影像。
3. YOLO26n 推論（信心門檻 `confidence_threshold`，預設 0.35）。
4. 發布 `/yolo/detections`（JSON，沒有偵測到物件時為 `detections: []`）與 `/yolo/image`（標註影像）。

ROS 2 的 console script 使用系統 Python，因此節點啟動時會把 YOLO venv 的 site-packages 加進 `sys.path`，才能同時匯入 `rclpy` 與 `ultralytics`。

## 9. 自主控制節點（`autonomy_controller`）

控制器訂閱 `/yolo/detections`，每 0.1 秒發布一次 `cmd_vel`。判斷順序就是安全優先順序：

| 優先 | 條件 | 狀態 | 動作 |
|---|---|---|---|
| 1 | 超過 `stale_timeout`（1.0 s）沒有新偵測 | `stale_detections` | 停車 |
| 2 | 畫面中有 person | `person_detected` | 停車 |
| 3 | 目標剛消失（< `target_loss_timeout` 0.5 s） | `target_lost_wait` | 停車等待 |
| 4 | 目標消失較久 | `search_forward` → `search_timeout` | 限時低速前進搜尋，逾時停車 |
| 5 | 目標偏離畫面中央 | `align_to_target` | 原地轉向 |
| 6 | 目標還小（bbox 未達 `stop_bbox_ratio`） | `approach_target` | 低速前進 |
| 7 | 目標夠近 | `target_action:<動作>` → `target_action_complete` | 執行一次目標動作後停止 |

人員優先停止已用 Gazebo 人物模型實測：人物進入畫面後 0.1–0.2 秒內車輛停止，離開後自動恢復接近。

邏輯寫在不依賴 ROS 的 `AutonomyLogic` 類別，可直接用 pytest 測試（`test_autonomy_logic.py`）。`stop_bbox_dimension` 可選擇用 bbox 高度或寬度判斷距離；杯子位於相機下方，靠近時底部會被裁切，因此杯子場景使用寬度。

## 10. 自主控制閉環的完整資料流

1. Gazebo 相機產生影像，`image_bridge` 轉成 ROS 的 `/vehicle_blue/camera/image`。
2. `camera_yolo` 推論後發布 `/yolo/detections`。
3. `autonomy_controller` 依第 9 節的順序決定速度，發布 `/model/vehicle_blue/cmd_vel`。
4. `parameter_bridge` 把速度送到 Gazebo DiffDrive，車輛移動。
5. Gazebo 的 odometry 經 `parameter_bridge` 回到 ROS，用來驗證車輛真的有移動，而不只是 Topic 上有速度訊息。

同一時間只能有一個節點發布 `cmd_vel`：`move_robot` 與 `autonomy_controller` 不可同時啟動。

## 11. Launch 檔

- `camera_yolo.launch.py`：`image_bridge` + `camera_yolo`。
- `autonomous_yolo.launch.py`：引入 `camera_yolo.launch.py`，再加上 `cmd_vel`／odometry bridge 與 `autonomy_controller`。

學到的一點：被引入的 Launch 檔若有同名參數（兩者都有 `confidence_threshold`），引入時設定的值會覆寫外層的值。用 `GroupAction(scoped=True)` 包住引入的 Launch，參數就不會互相影響。可以用 `ros2 param dump /autonomy_controller` 確認節點實際收到的參數。

## 12. UR5e 機械手臂：ros2_control 與 MoveIt 2

手臂專案的架構分成三層：

| 層 | 元件 | 作用 |
|---|---|---|
| 模擬 | Gazebo + `gz_ros2_control` | 模擬手臂與夾爪的物理運動，提供關節介面 |
| 控制 | `scaled_joint_trajectory_controller`、`parallel_gripper_controller`、`joint_state_broadcaster` | 執行關節軌跡，發布 `/joint_states` |
| 規劃 | MoveIt 2 `move_group` | 碰撞檢查、逆運動學、路徑規劃，再把軌跡交給控制器 |

MoveIt 的規劃群組：`ur_manipulator`（6 個手臂關節，末端 `tool0`）與 `gripper`（兩個夾指）。

`pick_place_demo.py` 透過 MoveIt 提供的 Service 與 Action 完成取放：

| 介面 | 類型 | 用途 |
|---|---|---|
| `/apply_planning_scene` | Service | 加入桌子、方塊、底座等碰撞物件；夾取後把方塊附著到夾爪 |
| `/compute_ik` | Service | 檢查目標位姿是否可達 |
| `/move_action` | Action | 關節目標或末端位姿目標的規劃與執行 |
| `/compute_cartesian_path` + `/execute_trajectory` | Service + Action | 直線下降、抬起、退回 |
| `/parallel_gripper_controller/follow_joint_trajectory` | Action | 夾爪開合 |

Pick-and-place 流程：建立碰撞場景 → 移到準備姿態 → 張開夾爪 → 移到方塊上方 → 直線下降 → 夾緊 → 在 MoveIt 中附著方塊 → 抬起 → 移到放置點上方 → 下降 → 放開 → 解除附著 → 退回 → 回到準備姿態。

