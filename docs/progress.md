# 工研院機器人自學進度

## 專案目標

學習機器人開發所需的 Linux、ROS 2、Gazebo、YOLO 物件辨識，以及 AI Agent / Multi-Agent 程式開發。

## 開發環境

- 作業系統：Windows + WSL2
- Linux：Ubuntu 24.04.5 LTS
- ROS 2：Jazzy
- 模擬器：Gazebo Harmonic
- 主要程式語言：Python
- 版本控制：Git + GitHub

## 已完成項目

### 2026-10-21：環境建置與初步測試

- [x] 安裝並啟動 WSL2 Ubuntu。
- [x] 確認 Git 可以正常使用。
- [x] 確認 ROS 2 指令可以正常執行。
- [x] 確認 demo_nodes_cpp 套件存在。
- [x] 成功啟動 Gazebo 差速車模擬範例。
- [x] 確認 ROS 2 可以列出模擬相關 Topic。
- [x] 建立 GitHub 專案與基本資料夾。

### 已觀察到的 ROS 2 Topic

- /model/vehicle_blue/cmd_vel
- /model/vehicle_blue/odometry
- /model/vehicle_green/cmd_vel
- /model/vehicle_green/odometry
- /parameter_events
- /rosout

## 下一步

- [ ] 確認 Gazebo 中的機器人模型是否正常顯示。
- [ ] 學習 cmd_vel 與速度控制。
- [ ] 學習 odometry 與機器人位置資訊。
- [ ] 練習撰寫 Python ROS 2 Node。
- [ ] 學習 YOLO 物件辨識。
- [ ] 研究 AI Agent / Multi-Agent 協作程式開發。
