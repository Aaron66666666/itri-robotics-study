# 階段成果報告 — 2026-11-24（Claude Code 接手 Codex）

範圍：差速車 Camera → YOLO → Controller → Gazebo 自主控制閉環驗收，以及後續 UR5e Gazebo／MoveIt pick-and-place。
環境：WSL2 Ubuntu 24.04、ROS 2 Jazzy、Gazebo Harmonic、YOLO26n（CPU）。未重新安裝任何套件，未安裝 Isaac Sim。所有模擬以 headless Gazebo 在本環境實際執行。

---

## 一、已完成

### 1. 接手檢查
- 讀完 `docs/handoff_to_claude_code.md` 並核對原始碼；Codex 的修改（`target_loss_timeout`、偵測變化日誌、單元測試）全部保留。
- `colcon build` 通過；`colcon test`：robot_control **21 passed／1 skipped**（Codex 交接時 15），yolo_ros 2 passed／1 skipped。

### 2. 即時 YOLO 診斷（已結案）
| 問題 | 結論 | 證據 |
|---|---|---|
| 即時管線是否有轉換錯誤 | 無。live PNG 與即時節點、離線推論結果逐一一致（`cup 0.4517`，同 bbox） | `evidence/2026-11-24/bottle_world_live_frame_x0.png`、`O1_bottle_observation.launch.log` |
| 瓶子是否在畫面中 | 是，位於畫面中央 | 同上影格 |
| `camera_test.jpg` 為何無框 | 該檔為有損 JPEG（`save_camera_image.py`）＋車位略不同；cup 0.31 < 0.35。PNG→JPEG 品質 75 時分數掉到 0.07 | 離線比對 |
| 為何「之前連續辨識、之後不行」 | 圓柱瓶子只有在起始位置被判為 **cup**；車前進 0.2 m 即降到 0.13，之後被判為 person/umbrella。控制器 `target_class=bottle` 也永遠對不到 `cup` | `bottle_world_x0.2.png`、距離掃描 |

處理方式：**不降低信心門檻**，而是新增一個 YOLO 能穩定辨識的測試場景 `worlds/diff_drive_camera_cup.sdf`（白色馬克杯＋小桌＋正面補光），整段接近路徑上 cup 為 0.71–0.83。

### 3. 修正的缺陷（robot_ws）
1. **Launch 參數洩漏**：YOLO conf（0.35）覆寫了控制器的 `confidence_threshold`（應為 0.5）。以 scoped `GroupAction` 修正，`ros2 param dump` 確認為 0.5。
2. **人員停止後不再接近目標**：人員與目標同時出現會被誤當作「目標動作已完成」。已修正並加測試。
3. **目標閃爍會重複觸發目標動作**：短暫漏檢不再清除 latch。
4. `device` 參數未從整合 launch 傳入：已修正。
5. 缺少 odometry 進入 ROS：bridge 加入 `/model/vehicle_blue/odometry`。
6. 新增 `stop_bbox_dimension`（預設 `height` 不改變既有行為），因杯子底部靠近時會被裁切。

### 4. 自主控制整合驗收（全部通過）
低速參數：接近／搜尋 0.05 m/s、轉向 0.15 rad/s、目標動作 `stop`、控制器門檻 0.5。

| # | 驗收項目 | 結果 |
|---|---|---|
| 1 | 偵測 cup | ✅ 0.71–0.83 連續 |
| 2 | Controller 取得目標 | ✅ `approach_target` |
| 3 | 車輛靠近目標 | ✅ 前進 0.526 m（odometry 0.5258，Gazebo world pose 0.52575） |
| 4 | 達到停止條件後停止 | ✅ `target_action_complete`，之後 35 s 不動 |
| 5 | 短暫漏檢安全停止 | ✅ 0.25 s 漏檢位移 ≤ 3.5 mm，之後直接恢復接近 |
| 6 | 長時間失去目標進入搜尋 | ✅ `target_lost_wait`→`search_forward` 3 s→`search_timeout` 停車；位移與 0.05 m/s × 3 s 吻合 |
| 7 | 人員最高停止優先權 | ✅ 人員出現時位移 ≤ 3.5 mm；離開後恢復接近 |
| 8 | Gazebo 中車輛真的移動 | ✅ odometry（20 Hz）與 Gazebo world pose 一致 |
| — | 偵測資料 stale | ✅ 1.0 s 後停車 |

第 5 項的偵測訊息由腳本產生（gz 服務延遲無法製造 < 0.5 s 的漏檢），其餘鏈路皆為實際執行，重複 2 次結果一致。第 7 項另以 Gazebo 人物模型做真實影像端到端測試（見下），連續 2 次通過：人物出現後 94／180 ms 停車，離開後 147／82 ms 恢復接近。

### 4b. 人物模型端到端測試（真實影像）
場景 `worlds/diff_drive_camera_cup_person.sdf`（Gazebo Fuel「Casual female」）。接近途中人物進入畫面 6 s 後離開：

| 執行 | 出現→停車 | 停車期間 | 離開→恢復接近 | 最終停止 |
|---|---|---|---|---|
| D1 | 94 ms | 位移 2.6 mm 後 vx=0；38/38 影格 person 0.915 | 147 ms | x=0.531 m |
| D2 | 180 ms | 停車 | 82 ms | x=0.523 m |

### 5. UR5e Gazebo／MoveIt（`~/itri-robotics-study/projects/ur5e_gazebo_pick_place`）
| 項目 | 結果 |
|---|---|
| 工作桌與方塊碰撞場景 | ✅ 桌面、4 桌腳、方塊、底座加入 MoveIt planning scene |
| 手臂關節控制 | ✅ 3 個 joint goal，Gazebo 實際誤差 ≤ 0.005 rad |
| 末端執行器控制 | ✅ tool0 pose goal 誤差約 1 mm；夾爪開合 ±0.03 |
| Pick-and-place | ✅ 連續 3 次成功，方塊最終位置誤差 ≤ 1.2 mm |

過程中修正的既有問題：
- **右夾指從未在 Gazebo 中移動**（起始位置剛好在關節限制邊界被 DART 卡住）→ 限制各加 2 mm 餘量；命令慣例、SRDF、開合腳本均不變。
- **方塊不可達**（底座在地面、桌面 0.70 m，IK 無解）→ 手臂裝在 0.70 m 底座（URDF `mount_z`、世界 `robot_pedestal`）。
- 自己的 pick 程式第一版 yaw 自由導致放置段失敗 → 限制 yaw ±0.05 rad，修正後 3/3 成功。

---

## 二、進行中

- 本報告與 `docs/progress.md`、UR5e `README.md` 已更新；尚待使用者以 GUI 目視確認。

## 三、待完成

1. **使用者 GUI 目視確認**（需要您操作，見下方指令）。
2. 決定是否把 cup 場景參數設為 `autonomous_yolo.launch.py` 預設（目前預設仍為 `bottle`／高度停止）。
3. 原 bottle 場景若要保留使用，需換成 YOLO 能穩定辨識的瓶子模型。
4. 抓取以摩擦力夾持完成；若要更長距離或高速搬運，可再評估夾持力／接觸參數。

## 四、需要您操作（GUI 目視確認，可選）

車輛閉環（兩個終端）：
```bash
source /opt/ros/jazzy/setup.bash && cd ~/robot_ws && source install/setup.bash
gz sim -r worlds/diff_drive_camera_cup.sdf
```
```bash
source /opt/ros/jazzy/setup.bash && cd ~/robot_ws && source install/setup.bash
ros2 launch robot_control autonomous_yolo.launch.py target_class:=cup device:=cpu search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop stop_bbox_dimension:=width stop_bbox_ratio:=0.14
```
預期：車向杯子前進約 0.5 m 後停下，log 顯示 `approach_target` → `target_action:stop` → `target_action_complete`。

UR5e（兩個終端）：
```bash
cd ~/itri-robotics-study/projects/ur5e_gazebo_pick_place && ./scripts/start_moveit.sh
```
```bash
cd ~/itri-robotics-study/projects/ur5e_gazebo_pick_place && ./scripts/run_pick_place.sh --stage pick
```
預期：手臂夾起紅色方塊，從 (0.40, 0.50) 移到 (0.30, 0.65)；`./scripts/cube_pose.sh` 可讀方塊位置。

---

## 附錄：修改檔案清單

robot_ws：
- `src/robot_control/launch/autonomous_yolo.launch.py`（scoped include、device、odometry bridge、stop_bbox_dimension）
- `src/robot_control/robot_control/autonomous_controller.py`（人員 latch 修正、漏檢 latch、stop_bbox_dimension）
- `src/robot_control/test/test_autonomy_logic.py`（+6 測試）
- `src/robot_control/package.xml`（nav_msgs）
- `worlds/diff_drive_camera_cup.sdf`、`worlds/diff_drive_camera_cup_person.sdf`（新增）
- `tools/acceptance/*`（新增）、`docs/evidence/2026-11-24/*`（新增）
- `docs/progress.md`、`docs/stage_report_2026-11-24.md`

ur5e_gazebo_pick_place：
- `ros2_ws/src/ur5e_gripper_demo/urdf/ur5e_gripper.urdf.xacro`（mount_z、夾指限制餘量）
- `ros2_ws/src/ur5e_gripper_demo/pick_place_world.sdf`（robot_pedestal）
- `ros2_ws/src/ur5e_gripper_demo/launch/ur5e_moveit.launch.py`、`ur5e_gripper_moveit.launch.py`（launch_rviz）
- `ros2_ws/src/ur5e_gripper_demo/scripts/pick_place_demo.py`（新增）、`CMakeLists.txt`、`package.xml`
- `scripts/run_pick_place.sh`、`scripts/cube_pose.sh`、`scripts/gripper_monitor.py`（新增）、`scripts/start_moveit.sh`（轉傳參數）
- `README.md`；備份 `docs/backup_2026-11-24_before_pedestal/`；紀錄 `docs/evidence_2026-11-24/`
