# 達明 TM5S-900：Gazebo + MoveIt 2 取放

依經理建議，不用 Isaac Sim，改沿用 UR5e 專案已經架好的 Gazebo Harmonic + MoveIt 2（ROS 2 Jazzy），完成達明 TM5S（臂長 900 mm 等級）的關節控制、末端控制和取放。

![TM5S 連續 3 次取放的末端路徑、方塊位置與夾爪開合](docs/evidence_2026-11-25/plot_results.png)

## 結果（2026-11-25）

| 項目 | 結果 |
|---|---|
| 控制器 | `joint_state_broadcaster`、`tmr_arm_controller`、`parallel_gripper_controller` 全部 active |
| 關節控制（3 個關節目標） | 全部成功，誤差 ≤ 0.0046 rad |
| 末端控制（夾取前姿態） | 目標 (0.400, 0.500, 1.042)，實際 (0.400, 0.501, 1.044)，誤差約 2 mm |
| 連續 3 次取放 | 3/3 成功，Gazebo 實測方塊誤差 0.1–1.4 mm |

連續取放的紀錄（`docs/evidence_2026-11-25/results.csv`）：

| 次數 | 從 → 到 | 實測位置 | 誤差 x | 誤差 y |
|---|---|---|---|---|
| 1 | (0.40, 0.50) → (0.30, 0.65) | (0.3001, 0.6488) | +0.1 mm | -1.2 mm |
| 2 | (0.30, 0.65) → (0.55, 0.30) | (0.5502, 0.2989) | +0.2 mm | -1.1 mm |
| 3 | (0.55, 0.30) → (0.40, 0.50) | (0.4002, 0.4986) | +0.2 mm | -1.4 mm |

錄 GUI 影片那次（Gazebo + RViz）也是 3/3 成功，誤差 0.0–1.4 mm，紀錄在 `docs/evidence_2026-11-25_gui_video/`。

證據：`docs/evidence_2026-11-25/` 有每次取放的 log、末端路徑（`flange_path.csv.gz`，20 Hz）、啟動 log 和上面的圖。

## 架構

和 UR5e 專案相同的場景（0.70 m 底座、工作桌、6 cm 方塊）、相同的二指夾爪和取放流程，只換手臂：

| 項目 | UR5e 專案 | TM5S 專案 |
|---|---|---|
| 手臂模型 | `ur_description` | 達明官方 [tm2_ros2](https://github.com/TechmanRobotInc/tm2_ros2) 的 `tm_gazebo`／`tm_description`（BSD-3） |
| Gazebo 啟動 | `ur_simulation_gz` | 自己寫的 `tm5s_gripper_sim.launch.py`（`ros_gz_sim` + `gz_ros2_control`） |
| MoveIt 群組／末端 | `ur_manipulator`／`tool0` | `tmr_arm`／`flange` |
| 手臂控制器 | `scaled_joint_trajectory_controller` | `tmr_arm_controller` |

`tm5s_gripper_demo` 套件內容：

- `urdf/tm5s_gripper.urdf.xacro`：引用官方 TM5S 模型，加上底座、轉接座、夾爪和 `gz_ros2_control`。
- `srdf/tm5s_gripper.srdf`：手臂和夾爪群組、碰撞排除（改自官方 `tm5s_moveit_config`）。
- `config/`：控制器、MoveIt 控制器、運動學、關節限制、RViz。
- `scripts/pick_place_demo.py`：和 UR5e 版相同的流程，只換群組名稱、關節名稱、末端和預備姿態。

## 從官方 ROS 2 Humble 版改成 Jazzy 遇到的問題

| 問題 | 原因 | 處理 |
|---|---|---|
| 官方 Gazebo 外掛在 Jazzy 不存在 | `tm_gazebo` 用的是 Humble 時代的 `ign_ros2_control` | 自己的 URDF 改用 Jazzy 的 `gz_ros2_control/GazeboSimSystem` 和 `gz_ros2_control-system` |
| 官方 `macro.gazebo.xacro` 是舊版 Gazebo Classic | 用 `libgazebo_ros_control.so` | 不引用它，只引用運動學、網格和慣量的巨集 |
| MoveIt 時間參數化需要加速度限制 | 官方 `joint_limits.yaml` 沒有開加速度限制 | 自己的 `joint_limits.yaml` 補上加速度限制（5 rad/s²） |
| 官方 MoveIt 設定的 root 是 `link_0`／`base` | `tm_gazebo` 版本的 root 是 `base_link` | SRDF 改成 `base_link` → `flange`，碰撞排除的連桿名稱一併調整 |

## 執行

需要先建置官方套件（只建 `tm_description` 和 `tm_gazebo`，不放進這個 repo）：

```bash
mkdir -p ~/tm_ws/src && cd ~/tm_ws/src
git clone --depth 1 --filter=blob:none --sparse https://github.com/TechmanRobotInc/tm2_ros2.git
cd tm2_ros2 && git sparse-checkout set tm_description tm_gazebo
cd ~/tm_ws && source /opt/ros/jazzy/setup.bash && colcon build --packages-select tm_description tm_gazebo
```

建置本專案：

```bash
cd ~/itri-robotics-study/projects/tm5s_gazebo_pick_place/ros2_ws
source /opt/ros/jazzy/setup.bash && source ~/tm_ws/install/setup.bash
colcon build --symlink-install
```

展示（Gazebo + RViz + 終端機，連續 3 次取放，最後畫出上面的圖）：

```bash
bash ~/itri-robotics-study/projects/tm5s_gazebo_pick_place/scripts/demo_pick_place_gui.sh
```

不開畫面：`GUI=0 AUTO=1 bash .../demo_pick_place_gui.sh`。分開執行：`scripts/start_moveit.sh` 啟動模擬和 MoveIt，再用 `scripts/run_pick_place.sh --stage joints | ee | pick` 執行各階段。

## 授權

達明的模型和網格來自 [tm2_ros2](https://github.com/TechmanRobotInc/tm2_ros2)（Copyright TECHMAN ROBOT INC.，BSD-3-Clause），建置時從官方下載，不放進這個 repo。SRDF 的碰撞排除、RViz 設定和關節速度限制改自官方套件，授權全文見 `THIRD_PARTY_NOTICES.txt`。
