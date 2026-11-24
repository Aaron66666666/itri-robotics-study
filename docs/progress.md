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
| 階段 1：AI Agent（本機 Ollama） | 進行中：單一 Agent 完成（Llama 3.1 8B 12/12），下一步 Multi-Agent |
| 階段 2–4：YOLO 訓練、Isaac Sim、microduck RL | 尚未開始 |

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
- `ai-agent`：本機 Ollama 工具呼叫 Agent（驗收助理）。
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

## 後續階段路線圖

依經理建議排定的順序；全部使用本機與免費資源，不使用付費 API。

### 階段 1：AI Agent（本機 Ollama）— 進行中

模型在 Windows 的 Ollama（RTX 4070）執行，WSL 的 Agent 透過 HTTP 呼叫；程式在 `ai-agent/`。

- [x] （2026-11-24）自己撰寫 Agent 迴圈：工具定義、tool call、結果回傳、最多輪數、重複呼叫保護；模型呼叫層獨立（`ChatModel`），以後換模型只需新增一個類別。
- [x] （2026-11-24）以假工具（同名稱、同 schema）及假 Ollama 伺服器測試迴圈；28 項測試通過，不需網路。
- [x] （2026-11-24）接上真實驗收工具：執行／摘要 Gazebo 情境（approach、target_loss、person_stop）與 GPU 狀態，只回傳 JSON 摘要。直接呼叫 `run_scenario` 實測：person_stop PASS（GPU，人物出現後 114 ms 停車）。
- [x] （2026-11-24）Windows 安裝 Ollama 0.40.18，下載 Qwen 2.5 7B 與 Llama 3.1 8B；兩者皆完整載入 GPU（約 5 GB VRAM），暖機後每次呼叫約 0.6–1 秒。WSL（NAT 模式）透過 Windows 主機 IP 連線，防火牆只允許 WSL 網段。
- [x] （2026-11-24）以 `eval_models.py` 比較兩個模型（6 個固定任務 × 2 次，自動檢查工具呼叫、禁止動作、答案數字、繁體中文）：Llama 3.1 8B 12/12、Qwen 2.5 7B 10/12。發現並處理：Qwen 會編造結果與混用簡體字（加強提示詞改善）、Llama 會自行改跑使用者沒要求的情境（改以程式層 policy 禁止）。預設模型改為 Llama 3.1 8B。
- [x] （2026-11-24）真實工具實測（Llama）：Agent 自行執行 Gazebo person_stop，回報 PASS、130 ms 停車、畫面有人時位移 0.0 m，與執行紀錄一致；比較 CPU／GPU 兩次已保存紀錄，修正工具名稱解析後答案完全正確（94／93 ms 停車、27／20 ms 推論）。
- [ ] Multi-Agent：規劃者／執行者／審查者分工，審查者核對報告數字是否都來自工具結果。

### 階段 2：YOLO 自訂資料訓練

- [ ] 用 Gazebo 自動產生瓶子／杯子影像（不同距離、角度、光線、背景），並自動產生標註（由已知物體位置與相機投影計算 bbox，或使用 Gazebo 的 bounding box 相機）。
- [ ] 切分 train／val／test，以 GPU 微調 YOLO26n。
- [ ] 評估 mAP，並在原 bottle 場景驗證整段接近路徑都能穩定辨識 bottle（修好瓶子辨識）。
- [ ] 以微調後的模型重跑自主控制驗收。

### 階段 3：Isaac Sim（Windows 原生，不在 WSL）

- [ ] 先執行 Isaac Sim 相容性檢查（Compatibility Checker）。注意：先前查到 Isaac Sim 6.2 文件列出的最低規格為 32 GB RAM 與 RTX 4080；本機為 RTX 4070 Laptop（8 GB VRAM），需以檢查結果決定是否可行。
- [ ] 在 Windows 安裝 Isaac Sim（安裝前先確認）。
- [ ] 匯入 UR 手臂（UR5／UR5e）USD，完成關節控制與物件取放。
- [ ] 取得達明 TM5S-900 的官方模型，轉成 USD 匯入，完成控制與取放。

### 階段 4：microduck RL

- [ ] 研讀 [microduck_rl](https://github.com/pollen-robotics/microduck_rl)（MuJoCo／mjlab + PPO），在本機重現模擬與訓練。

## 需要在 Windows 操作的步驟

每一項安裝前都會先確認。

| 項目 | 階段 | 狀態 |
|---|---|---|
| 更新 NVIDIA 驅動（Studio 621.24，CUDA 13.5） | GPU | 完成 |
| 安裝 Ollama 並下載模型（含防火牆規則） | 1 | 完成 |
| Isaac Sim 相容性檢查與安裝 | 3 | 之後 |

### 安裝 Ollama（階段 1）

1. 從 <https://ollama.com/download/windows> 下載 `OllamaSetup.exe` 並安裝（安裝到使用者帳號，不需系統管理員）。
2. 讓 WSL 連得到 Ollama。WSL 目前是 NAT 網路模式，`localhost` 連不到 Windows，二選一：
   - **A（建議，不影響 ROS 2/Gazebo）**：在 PowerShell 設定 Ollama 監聽所有介面，再從系統匣結束並重新開啟 Ollama：

     ```powershell
     [Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
     ```

     再以**系統管理員** PowerShell 加入防火牆規則，只允許 WSL 網段連入：

     ```powershell
     New-NetFirewallRule -DisplayName "Ollama from WSL" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 172.16.0.0/12 -Action Allow
     ```

   - **B**：在 `C:\Users\<使用者>\.wslconfig` 加入 `[wsl2]` 與 `networkingMode=mirrored`，執行 `wsl --shutdown`。之後 `localhost:11434` 可直接使用，但網路模式改變後需要重新驗證 ROS 2/Gazebo。
3. 在 PowerShell 下載模型（各約 5 GB，8 GB VRAM 可完整放入 GPU）：

   ```powershell
   ollama pull qwen2.5:7b
   ollama pull llama3.1:8b
   ```

4. 確認：`ollama run qwen2.5:7b "hello"` 有回應，`ollama ps` 顯示 `100% GPU`。
5. 在 WSL 確認：`python3 ~/itri-robotics-study/ai-agent/run_agent.py --fake "列出所有情境"`（Agent 會自動找 localhost 或 Windows 主機 IP）。

注意：Ollama 第一次對外監聽時，Windows 可能跳出「是否允許存取」視窗。**不要按取消**：取消會替 ollama.exe 建立封鎖規則，優先權高於允許規則，WSL 會連不上。若已按取消，用系統管理員 PowerShell 刪除封鎖規則：

```powershell
Get-NetFirewallRule -Direction Inbound -Action Block | Where-Object { $_.DisplayName -like "*ollama*" } | Remove-NetFirewallRule
```
