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
- [ ] 以 Gazebo 人物模型做人員停止的端到端測試（目前以注入偵測訊息驗證）。
- [ ] 使用者以 GUI 目視確認。

## 環境

Ubuntu 24.04（WSL2）、ROS 2 Jazzy、Gazebo Harmonic、YOLO venv `~/yolo_project/.venv`、權重 `~/yolo_project/yolo26n.pt`（不納入 git）。

## 建置與執行

```bash
source /opt/ros/jazzy/setup.bash
cd projects/diff_drive_yolo/ros2_ws && colcon build && source install/setup.bash
cd .. && gz sim -r worlds/diff_drive_camera_cup.sdf
```

另一個終端：

```bash
source /opt/ros/jazzy/setup.bash && source projects/diff_drive_yolo/ros2_ws/install/setup.bash
ros2 launch robot_control autonomous_yolo.launch.py target_class:=cup device:=cpu \
  search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop \
  stop_bbox_dimension:=width stop_bbox_ratio:=0.14
```

## 目錄

- `ros2_ws/src/robot_control`：相機 YOLO 節點、自主控制器、Launch、單元測試。
- `ros2_ws/src/yolo_ros`：早期固定圖片 YOLO 範例。
- `worlds/`：`diff_drive_camera.sdf`（空場景）、`diff_drive_camera_bottle.sdf`（瓶子，YOLO 不穩定）、`diff_drive_camera_cup.sdf`（杯子，建議使用）。
- `tools/acceptance/`：headless 驗收腳本（`ROBOT_WS` 指定 workspace，預設 `~/robot_ws`）。
- `docs/`：進度、架構、YOLO 診斷、交接文件、階段報告與 2026-11-24 驗收證據。
