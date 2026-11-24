# 工研院機器人自學進度

## 專案目標

學習機器人開發所需的 Linux、ROS 2、Gazebo、YOLO 物件辨識，以及 AI Agent / Multi-Agent 程式開發。

## 目前狀態（2026-11-24）

| 項目 | 狀態 |
|---|---|
| ROS 2 車輛控制、Odometry、Launch | 完成 |
| 相機 + YOLO 即時辨識管線 | 完成 |
| Camera→YOLO→Controller→Gazebo 自主控制閉環 | 完成，8 項驗收通過 |
| UR5e 碰撞場景、關節／末端控制、Pick-and-Place | 完成，連續 3 次成功 |
| 人物模型端到端測試（真實影像人員停止） | 完成，連續 2 次通過 |
| GPU 加速（RTX 4070） | 完成 |
| GUI 目視確認 | 待完成 |
| AI Agent / Multi-Agent | 尚未開始 |

詳細報告：`projects/diff_drive_yolo/docs/stage_report_2026-11-24.md`。

## 開發環境

- 作業系統：Windows + WSL2
- Linux：Ubuntu 24.04.5 LTS
- ROS 2：Jazzy
- 模擬器：Gazebo Harmonic（Gazebo Sim 8）
- 機械手臂規劃：MoveIt 2（`ur_simulation_gz`、`ur_moveit_config`）
- 物件辨識：YOLO26n（Ultralytics；RTX 4070 Laptop GPU，驅動 621.24／CUDA 13.5；venv `~/yolo_project/.venv`）
- 主要程式語言：Python
- 版本控制：Git + GitHub（WSL 以 SSH 金鑰推送）

## 專案目錄

- `projects/diff_drive_yolo`：差速車 + 相機 + YOLO 自主控制（`~/robot_ws` 的版本控制副本）。
- `projects/ur5e_gazebo_pick_place`：UR5e + 二指夾爪 + MoveIt 2 取放。
- `docs/ros2-architecture.md`：ROS 2 程式架構與資料流筆記。

## 已完成項目

### 2026-10-21：環境建置與初步測試

- [x] 安裝並啟動 WSL2 Ubuntu。
- [x] 確認 Git 可以正常使用。
- [x] 確認 ROS 2 指令可以正常執行。
- [x] 確認 demo_nodes_cpp 套件存在。
- [x] 成功啟動 Gazebo 差速車模擬範例。
- [x] 確認 ROS 2 可以列出模擬相關 Topic。
- [x] 建立 GitHub 專案與基本資料夾。

已觀察到的 ROS 2 Topic：

- /model/vehicle_blue/cmd_vel
- /model/vehicle_blue/odometry
- /model/vehicle_green/cmd_vel
- /model/vehicle_green/odometry
- /parameter_events
- /rosout

### ROS 2 車輛控制與 Odometry

- [x] 確認 Gazebo 中的機器人模型正常顯示。
- [x] 學習 cmd_vel 與速度控制，成功控制藍色車輛移動。
- [x] 學習 odometry，讀取車輛位置與速度資訊。
- [x] 撰寫 Python ROS 2 Node，控制車輛前進、轉彎與停止。
- [x] 建立 Subscriber，持續讀取 Odometry。
- [x] 建立 ROS 2 Launch，同時啟動控制與里程資訊程式。

### 相機 + YOLO 即時辨識

- [x] 實作 ROS 2 相機 + YOLO 節點，訂閱相機影像並發布 JSON 偵測結果與標註影像。
- [x] 加入 `ros2 run robot_control camera_yolo` 入口與獨立 `camera_yolo.launch.py`。
- [x] 修正 ROS 系統 Python 匯入 YOLO venv 套件的路徑問題；`robot_control` 已重新建置，`ros2 run` smoke check 成功載入模型並建立兩個 Publisher。
- [x] 將相機 Topic 對齊 `worlds/diff_drive_camera.sdf` 的 `/vehicle_blue/camera/image`，加入低頻影格接收與 YOLO 推論計數日誌。
- [x] 在 `camera_yolo.launch.py` 加入 `ros_gz_image` GZ→ROS Bridge，讓 Launch 使用專案 SDF 對應的影像 Topic。
- [x] 啟動既有 `diff_drive_camera.sdf` 完成真實端到端測試：收到 640×480 Gazebo 影格、YOLO 推論完成，`/yolo/detections` JSON 與 `/yolo/image` 標註影像均收到。空場景沒有偵測物件，輸出空 detections 為預期。
- [x] 完成 YOLO Camera + ROS 2 即時辨識管線；已驗證 Gazebo 影像輸入、YOLO 推論與偵測/標註影像 Topic 輸出。
- [x] 新增獨立 `diff_drive_camera_bottle.sdf` YOLO 測試場景，在相機前方加入瓶狀目標，並放大/移近目標以利影像辨識；保留原始空場景 world。
- [x] （2026-11-24）確認瓶子場景的即時影像：YOLO26n 將圓柱瓶子判為 `cup`（0.45），且只在起始位置成立，車前進 0.2 m 即降到 0.13；`camera_test.jpg` 無框是 JPEG 壓縮所致。改用新的杯子測試場景（白色馬克杯、小桌、正面補光），整段接近路徑 cup 0.71–0.83。

### YOLO 自主控制閉環

- [x] 整合 Launch 加入獨立 `yolo_confidence_threshold` 參數並傳入相機辨識節點；可調低門檻觀察候選框，而自主行為門檻仍獨立控制。
- [x] 新增自主控制節點與 Gazebo cmd_vel bridge Launch；人物偵測優先停止、無目標時限速前進搜尋、依目標框置中/接近、接近後執行設定動作、偵測逾時安全停止等 9 項邏輯測試通過。
- [x] （2026-11-24）修正 Launch 參數洩漏（YOLO conf 覆寫控制器門檻）、人員離開後不再接近目標、目標閃爍重複觸發動作；新增 odometry bridge 與 `stop_bbox_dimension`；robot_control 測試 21 passed。
- [x] （2026-11-24）Camera→YOLO→Controller→Gazebo 閉環驗收 8 項全部通過：偵測 cup、接近 0.526 m 後停止（odometry 與 Gazebo world pose 一致）、短暫漏檢停車、長時間失去目標進入限時搜尋、人員最高優先停止、stale 停止。
- [x] （2026-11-24）Gazebo 人物模型端到端測試：新增 `worlds/diff_drive_camera_cup_person.sdf`（Fuel「Casual female」）。接近途中人物進入畫面，YOLO 以真實相機影像偵測 person 0.915，車輛 94／180 ms 內停車並維持 vx=0；人物離開後恢復接近，最終停在杯子前（x=0.531／0.523 m）。連續 2 次通過。
- [x] （2026-11-24）GPU 加速：Windows NVIDIA 驅動更新為 Studio 621.24（CUDA 13.5）後，YOLO 可使用 RTX 4070 Laptop GPU（PyTorch cu130，venv 未修改）。離線推論 21.4 → 11.2 ms；實機推論中位數 27 → 20 ms。修正 `device:=0` 被 ROS 當成整數導致相機節點無法啟動。GPU 版人物情境測試通過。
- [x] （2026-11-24）差速車 YOLO 專案程式與文件納入版本控制：`projects/diff_drive_yolo`（`~/robot_ws` 的副本）。

### 獨立專案：UR5e Gazebo 模擬與取放

- [x] 新增 `projects/ur5e_gazebo_pick_place`，以 ROS 2 Jazzy + Gazebo Harmonic + UR5e + MoveIt 2/RViz 做機械手臂模擬。
- [x] 建立工作桌與方塊的 Gazebo SDF 場景、環境檢查腳本及 UR5e/MoveIt 啟動腳本。
- [x] 安裝官方 `ur_simulation_gz`、UR MoveIt 設定與 MoveIt 2 ROS 套件。
- [x] 新增自訂二指平行夾爪 URDF 與 ros2_control JointTrajectoryController；新專案 workspace 建置成功，Xacro 展開與 URDF 結構檢查通過。
- [x] 再次建置 UR5e 專案套件；Xacro 展開、`check_urdf` 與 Gazebo SDF 靜態格式檢查通過。
- [x] 使用者確認 WSL Gazebo 與夾爪開合正常。
- [x] 新增 MoveIt `gripper` 規劃群組、`open`/`closed` 姿態與夾爪 FollowJointTrajectory 控制器；MoveIt config 生成檢查通過。
- [x] 修正 MoveIt Launch 對未安裝 `ur_robot_driver` 的依賴；自訂 URDF 直接提供給 MoveIt，工作空間重建及 Launch 參數解析通過。
- [x] 使用者啟動新版 MoveIt 成功；輸出顯示 Gazebo 的夾爪、手臂控制器已啟動，MoveIt 已載入兩個軌跡控制器並提供規劃服務。
- [x] 修正 MoveIt/RViz 啟動條件：RViz 現在會與 MoveGroup 一起啟動；重建與 Launch 參數解析通過。
- [x] 使用者確認 RViz 中 `gripper` 群組的開合規劃與執行完成。
- [x] （2026-11-24）修正右夾指在 Gazebo 中完全不動（起始位置在關節限制邊界被 DART 卡住，兩指限制各留 2 mm 餘量）。
- [x] （2026-11-24）手臂改裝於 0.70 m 底座：原底座在地面、桌面 0.70 m，由上往下夾取超出 UR5e 可達範圍。
- [x] （2026-11-24）工作桌、桌腳、方塊、底座加入 MoveIt 碰撞場景；關節控制誤差 ≤ 0.005 rad；末端位姿誤差約 1 mm。
- [x] （2026-11-24）MoveIt pick-and-place 在 Gazebo 連續 3 次成功，方塊最終位置誤差 ≤ 1.2 mm（`scripts/run_pick_place.sh`）。

## 待完成

### 目前專案收尾

- [ ] 使用者以 GUI 目視確認車輛閉環（`worlds/diff_drive_camera_cup.sdf`）。
- [ ] 使用者以 GUI（Gazebo + RViz）目視確認一次完整 pick-and-place。

### 後續模擬與機器人學習方向

- [ ] 評估 Isaac Sim/USD 或 Microduck RL 作為延伸項目；目前不列入已完成成果。

### 後續學習階段：AI Agent 與 Multi-Agent

- [ ] 學習 AI Agent、工具呼叫與任務規劃。
- [ ] 學習 Multi-Agent 協作程式開發。
