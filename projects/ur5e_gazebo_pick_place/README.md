# UR5e Gazebo 模擬與取放專案

## 專案目標

在 ROS 2 Jazzy + Gazebo Harmonic 中控制 UR5e，加入可開合的平行夾爪，接著整合規劃和物件抓取/放置。本專案獨立於 `robot_control` / YOLO 專案。

Gazebo 負責物理模擬；MoveIt 2 負責機械手臂運動規劃；RViz 顯示機械手臂和規劃結果。

## 進度

- [x] 建立 UR5e Gazebo + MoveIt 專案資料夾與工作桌/方塊場景。
- [x] 加入自訂二指平行夾爪 URDF、兩指 ros2_control 關節及 JointTrajectoryController。
- [x] 加入啟動模擬和發送開/合夾命令的腳本。
- [x] 建置新專案工作空間；Xacro 展開、URDF 結構及 Gazebo SDF 靜態格式檢查通過。
- [x] 使用者已確認 WSL 中 Gazebo 與夾爪開合正常。
- [x] 加入 MoveIt 的 `gripper` 規劃群組、張開/閉合姿態，以及手臂和夾爪的 FollowJointTrajectory 控制器設定。
- [x] 使用者已啟動新版 MoveIt；log 顯示 Gazebo 手臂/夾爪控制器啟動，MoveIt 載入兩個 FollowJointTrajectory 控制器。
- [x] 修正啟動流程，RViz 會隨 MoveIt 一起啟動；Launch 解析和工作空間重建通過。
- [x] 使用者已在 RViz 以 `gripper` 群組完成開合規劃與執行。
- [x] 在 Gazebo 中確認夾爪可開合。
- [x] （2026-11-24）修正右夾指在 Gazebo 中完全不動：兩指關節限制各留 2 mm 餘量（指頭起始正好在限制邊界時被 DART 卡住）。命令慣例不變（開 `[0, 0]`、合 `[0.04, -0.04]`）。
- [x] （2026-11-24）UR5e 改裝於 0.70 m 底座（`mount_z`，世界加入 `robot_pedestal`）。原本底座在地面、桌面高 0.70 m，由上往下夾取超出 UR5e 可達範圍（`/compute_ik` 回 NO_IK_SOLUTION）。
- [x] （2026-11-24）工作桌（桌面＋4 支桌腳）、方塊、底座加入 MoveIt 碰撞場景。
- [x] （2026-11-24）手臂關節控制：3 個 MoveIt joint goal 規劃並在 Gazebo 執行，誤差 ≤ 0.005 rad。
- [x] （2026-11-24）末端執行器控制：tool0 pose goal（朝下），實測 (0.400, 0.501, 1.043)，目標 (0.40, 0.50, 1.042)。
- [x] （2026-11-24）Pick-and-place：連續 3 次成功，Gazebo 方塊最終位置誤差 ≤ 1.2 mm；夾指停在 ±0.031（6 cm 方塊接觸點）。
- [ ] 在 GUI（Gazebo + RViz）中由使用者目視確認一次完整流程。

## 環境需求

- Ubuntu 24.04 + ROS 2 Jazzy
- Gazebo Harmonic / Gazebo Sim 8
- `ros-jazzy-ur-simulation-gz`、`ros-jazzy-moveit`、`colcon`

ROS 模擬套件已安裝。建置專案套件：

```bash
source /opt/ros/jazzy/setup.bash
cd ~/itri-robotics-study/projects/ur5e_gazebo_pick_place/ros2_ws
colcon build --symlink-install
```

## 啟動 UR5e 和夾爪

```bash
source /opt/ros/jazzy/setup.bash
cd ~/itri-robotics-study/projects/ur5e_gazebo_pick_place
./scripts/start_sim.sh
```

Gazebo 與 RViz 啟動後，另開終端機測試夾爪。初始位置為張開：

```bash
source /opt/ros/jazzy/setup.bash
cd ~/itri-robotics-study/projects/ur5e_gazebo_pick_place
./scripts/gripper_close.sh
./scripts/gripper_open.sh
```

使用者已確認夾爪可以開合。這不代表已經能抓方塊；接下來還要在 MoveIt 中驗證規劃群組、把工作桌和方塊加入碰撞場景，再測試夾持與搬運。

若要回報 Gazebo 執行狀況，請在 WSL 原生終端執行以上啟動指令；Gazebo 伺服器必須保持執行，再於第二個終端執行 `./scripts/gripper_close.sh` 和 `./scripts/gripper_open.sh`。確認控制器是否存在可用 `ros2 control list_controllers`；若該命令不存在，請回報啟動終端中 `controller_manager` 或 `gz_ros2_control` 的錯誤訊息。

## 啟動含夾爪規劃組的 MoveIt

```bash
source /opt/ros/jazzy/setup.bash
cd ~/itri-robotics-study/projects/ur5e_gazebo_pick_place
./scripts/start_moveit.sh
```

`./scripts/start_moveit.sh` 會啟動 Gazebo、MoveIt 和 RViz，載入包含 `ur_manipulator` 與 `gripper` 群組的自訂配置。RViz 的 MotionPlanning 面板選擇 `gripper` 群組後，可選 `open` 或 `closed` 目標，再按 **Plan & Execute** 測試 MoveIt 到夾爪控制器的整合。這個執行步驟尚待使用者端驗證。

MoveIt 直接使用專案 URDF，因此不需要 `ur_robot_driver` 中僅供官方真實手臂流程使用的描述等待節點。

## 自動 Pick-and-Place（MoveIt，無需 RViz 操作）

```bash
# 終端 1（可加 launch_rviz:=false gazebo_gui:=false 以 headless 執行）
./scripts/start_moveit.sh
# 終端 2：等待 "You can start planning now!" 後
./scripts/run_pick_place.sh --stage pick                     # 方塊 (0.40,0.50) → (0.30,0.65)
./scripts/run_pick_place.sh --stage pick --cube-x 0.30 --cube-y 0.65 --place-x 0.40 --place-y 0.50
./scripts/cube_pose.sh                                        # Gazebo 中方塊實際位置
```

`--stage` 可為 `scene`（只建立碰撞場景）、`joints`（關節控制）、`ee`（末端位姿＋夾爪開合）、`pick`（完整流程）。程式：`ros2_ws/src/ur5e_gripper_demo/scripts/pick_place_demo.py`，透過 `/apply_planning_scene`、`/compute_ik`、`/move_action`、`/compute_cartesian_path`、`/execute_trajectory` 與夾爪 `FollowJointTrajectory` 動作（不需 moveit_py）。修改前檔案備份於 `docs/backup_2026-11-24_before_pedestal/`，測試紀錄於 `docs/evidence_2026-11-24/`。

## 官方技術來源

- [Universal Robots Gazebo Sim + MoveIt 2](https://github.com/UniversalRobots/Universal_Robots_ROS2_GZ_Simulation)：官方提供 Gazebo 控制、MoveIt 啟動及自訂 URDF/world 入口。
- [gz_ros2_control Jazzy 文件](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html)：說明 Gazebo Sim 中 ros2_control 硬體與控制器設定。
- [Isaac Sim 6.2 系統需求](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/requirements.html)：目前 RTX 4070 低於文件列出的 RTX 4080 最低 GPU，因此第一階段選擇已安裝的 Gazebo。
- [Microduck RL](https://github.com/pollen-robotics/microduck_rl)：MuJoCo/mjlab + PPO 的後續 RL 方向。

Gazebo UR5e 使用 URDF/Xacro；USD 是 Isaac Sim 常用匯入格式，RViz 是視覺化工具而非物理模擬器。
