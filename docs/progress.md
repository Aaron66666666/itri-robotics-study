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
| 階段 1：AI Agent（本機 Ollama） | 完成：單一 Agent（Llama 12/12）與 Multi-Agent（11/12） |
| 階段 2：YOLO 自訂資料訓練 | 完成：瓶子辨識修好，人員未退化（v3） |
| 階段 3：機械手臂取放（原 Isaac Sim） | 完成：依經理建議改用 Gazebo + MoveIt 2；TM5S-900 連續 3 次取放成功，誤差 0.1–1.4 mm |
| 階段 4：microduck RL | 進行中：平地行走訓練 8000 次迭代完成，策略可匯出 ONNX |

詳細報告：`projects/diff_drive_yolo/docs/stage_report_2026-11-24.md`。問題與排除紀錄：`docs/troubleshooting.md`。

## 開發環境

- 作業系統：Windows + WSL2
- Linux：Ubuntu 24.04.5 LTS
- ROS 2：Jazzy
- 模擬器：Gazebo Harmonic（Gazebo Sim 8）
- 機械手臂規劃：MoveIt 2（`ur_simulation_gz`、`ur_moveit_config`）
- 物件辨識：YOLO26n，預設為 Gazebo 微調的 v3（`~/yolo_project/yolo26n_gazebo_v3.pt`，不在 git 內）；Ultralytics；RTX 4070 Laptop GPU，驅動 621.24／CUDA 13.5；venv `~/yolo_project/.venv`
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
- [x] （2026-11-24）MoveIt pick-and-place 在 Gazebo 連續 3 次成功，方塊最終位置誤差 ≤ 1.2 mm（`scripts/run_pick_place.sh`）。2026-11-25 錄影時再跑 3 次，誤差 0.1–1.5 mm，仍在 2 mm 以內。

## 待完成

### 目前專案收尾

- [x] （2026-11-25）GUI 展示腳本：`projects/diff_drive_yolo/tools/demo/demo_person_gui.sh`（Gazebo 畫面 + YOLO 標註影像 + 終端機狀態）與 `projects/ur5e_gazebo_pick_place/scripts/demo_pick_place_gui.sh`（Gazebo + RViz，連續 3 次取放並用 Gazebo 量方塊位置）。試跑：車輛遇人停車、人離開後恢復、停在杯子前 x = 0.538 m；UR5e 3 次取放全部成功，誤差 0.1–1.1 mm（證據在兩個專案的 `evidence*2026-11-25_gui_demo_dryrun`）。
- [x] （2026-11-25）開 GUI 時 Gazebo 畫面和感測器搶 GPU，偵測偶爾延遲約 1.2 s，會觸發 1.0 s 的偵測逾時安全停車；展示腳本改用 `stale_timeout:=2.0`（無畫面的驗收仍是 1.0，延遲 ≤ 0.4 s）。
- [x] （2026-11-25）錄製兩段 GUI 影片：車輛遇人停車、恢復後停在杯子前（Gazebo 實測 x = 0.548 m）；UR5e 連續 3 次取放全部成功，誤差 0.1–1.5 mm。錄影當次的紀錄在兩個專案的 `evidence*2026-11-25_gui_video`（影片本身不放在 git）。

## 後續階段路線圖

依經理建議排定的順序；全部使用本機與免費資源，不使用付費 API。

### 階段 1：AI Agent（本機 Ollama）— 完成

模型在 Windows 的 Ollama（RTX 4070）執行，WSL 的 Agent 透過 HTTP 呼叫；程式在 `ai-agent/`。

- [x] （2026-11-24）自己撰寫 Agent 迴圈：工具定義、tool call、結果回傳、最多輪數、重複呼叫保護；模型呼叫層獨立（`ChatModel`），以後換模型只需新增一個類別。
- [x] （2026-11-24）以假工具（同名稱、同 schema）及假 Ollama 伺服器測試迴圈；28 項測試通過，不需網路。
- [x] （2026-11-24）接上真實驗收工具：執行／摘要 Gazebo 情境（approach、target_loss、person_stop）與 GPU 狀態，只回傳 JSON 摘要。直接呼叫 `run_scenario` 實測：person_stop PASS（GPU，人物出現後 114 ms 停車）。
- [x] （2026-11-24）Windows 安裝 Ollama 0.40.18，下載 Qwen 2.5 7B 與 Llama 3.1 8B；兩者皆完整載入 GPU（約 5 GB VRAM），暖機後每次呼叫約 0.6–1 秒。WSL（NAT 模式）透過 Windows 主機 IP 連線，防火牆只允許 WSL 網段。
- [x] （2026-11-24）以 `eval_models.py` 比較兩個模型（6 個固定任務 × 2 次，自動檢查工具呼叫、禁止動作、答案數字、繁體中文）：Llama 3.1 8B 12/12、Qwen 2.5 7B 10/12。發現並處理：Qwen 會編造結果與混用簡體字（加強提示詞改善）、Llama 會自行改跑使用者沒要求的情境（改以程式層 policy 禁止）。預設模型改為 Llama 3.1 8B。
- [x] （2026-11-24）真實工具實測（Llama）：Agent 自行執行 Gazebo person_stop，回報 PASS、130 ms 停車、畫面有人時位移 0.0 m，與執行紀錄一致；比較 CPU／GPU 兩次已保存紀錄，修正工具名稱解析後答案完全正確（94／93 ms 停車、27／20 ms 推論）。
- [x] （2026-11-24）Multi-Agent：規劃者（結構化 JSON，程式檢查計畫）→ 執行者（工具呼叫迴圈）→ 再規劃 → 報告者 → 審查者（程式查數字／PASS-FAIL／無測試結果時不得宣稱判定，LLM 只查涵蓋度）；不通過退回修改。59 項測試通過。
- [x] （2026-11-24）評估：Multi-Agent 在同 6 個任務上 Llama 11/12、Qwen 8/12，單一 Agent 為 12/12、10/12；Multi-Agent 慢約 8 倍，但能攔下編造的數字與判定並留下完整紀錄。審查者採「先拆解要求再逐項判斷」後，兩個模型的審查正確率由 8/16、12/16 提升到 14/16，且 0 次錯誤核准。真實工具比較 CPU／GPU 紀錄，報告第一次即核准且數字完全正確。

### 階段 2：YOLO 自訂資料訓練 — 完成

詳見 `projects/diff_drive_yolo/docs/yolo_training.md`。


- [x] （2026-11-24）用 Gazebo `boundingbox_camera` 自動標註，產生 2800 張隨機場景影像（8 種瓶子、7 種杯子、2 個人物、干擾物、隨機光線、地墊與背景；25% 為機器人相機視角）。每 200 張重新啟動 Gazebo，失敗自動重試，結果可重現。
- [x] （2026-11-24）train 2000／val 400／test 400（不同種子），以 RTX 4070 微調 YOLO26n 三版。v1 出現人員遺忘；v2 凍結骨幹無效；v3 加入 COCO128 真實影像回放後解決。
- [x] （2026-11-24）機器人場景 18 張影格各類最低分數：bottle 0.00 → 0.93（8 個距離全部辨識）、cup 0.26 → 0.76、person 0.90 → 0.90；合成測試集 mAP50 0.379 → 0.991。
- [x] （2026-11-24）以 v3 重跑閉環：原瓶子場景接近並停在 x = 1.004 m（以前做不到）；杯子 PASS（≥ 0.5 影格 99.4%，略低於原模型 100%）；人物停止 PASS（478 ms、位移 0.0 m）。發現停止門檻須依模型重新校正（v3 杯子框含把手，0.14 → 0.185）。
- [x] （2026-11-24）v3 設為 launch 預設模型：權重複製到 `~/yolo_project/yolo26n_gazebo_v3.pt`（不指向 `runs/`），可用 `model_path:=~/yolo_project/yolo26n.pt` 切回原模型；找不到權重時直接報錯，不自動下載；杯子停止門檻依 v3 改為 0.185。重跑驗收 5 項全部通過（杯子、目標遺失、人物停止 264 ms、原瓶子場景、切回原模型），README 說明權重不在 git 內及取得／重新訓練方法。

### 階段 3：Isaac Sim（Windows 原生，不在 WSL）

> 2026-11-25：經理建議 RTX 4070 筆電（8 GB VRAM）加 WSL2 不適合硬跑 Isaac Sim。達明 TM5S-900 的取放驗證改用已經架好的 Gazebo + MoveIt 2（或 MuJoCo）。若之後仍要用 Isaac Sim，需要系統直接安裝 Linux 並使用 4.5 版。相容性檢查工具（`C:\isaacsim\env_check`）停在 EULA 確認畫面，沒有繼續執行。
>
> 達明官方的 [tm2_ros2](https://github.com/TechmanRobotInc/tm2_ros2)（BSD-3）提供 TM5S 的模型（xacro、網格）、`tm5s_moveit_config` 和 `tm_gazebo`，可以沿用 UR5e 專案的架構。

- [x] （2026-11-24）比對 Isaac Sim 6.2 官方需求（[requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)，文件更新於 2026-10-14）與本機規格：

  | 項目 | 最低需求 | 本機 | 結果 |
  |---|---|---|---|
  | 作業系統 | Windows 11 | Windows 11（build 26200） | 符合 |
  | CPU／核心數 | Core i7 第 7 代，4 核 | i7-13620H，10 核 16 執行緒 | 符合 |
  | 記憶體 | 32 GB | 31.6 GB | 約等於最低需求 |
  | 儲存空間 | 50 GB SSD | C: 剩 1.7 TB | 符合 |
  | GPU／VRAM | RTX 4080，16 GB | RTX 4070 Laptop，8 GB | **低於最低需求** |
  | 驅動程式 | 測試版本 595.97 | 621.24 | 較新 |

  文件提到「低於最低規格的 GPU 可能無法執行部分教學與 benchmark」，但沒有說 8 GB 不支援；需以相容性檢查結果決定。Windows 端已安裝 Python 3.12（winget，個人安裝）並開啟長路徑支援（`LongPathsEnabled = 1`），檢查工具裝在 `C:\isaacsim\env_check`。
- [ ] 執行 Isaac Sim 相容性檢查（Compatibility Checker），步驟見下方「Isaac Sim 相容性檢查」，等待使用者確認後執行。
- [ ] 在 Windows 安裝 Isaac Sim（安裝前先確認）。
- [ ] 匯入 UR 手臂（UR5／UR5e）USD，完成關節控制與物件取放。
- [x] （2026-11-25）達明 TM5S-900：用官方 tm2_ros2 模型（BSD-3），在 Gazebo Harmonic + MoveIt 2 完成控制與取放（取代 Isaac Sim）。三個控制器全部啟動；關節控制誤差 ≤ 0.0046 rad；末端控制誤差約 2 mm；連續 3 次取放全部成功，方塊誤差 0.1–1.4 mm。附末端路徑與夾爪開合圖。專案：`projects/tm5s_gazebo_pick_place`。
- [x] （2026-11-25）錄製 TM5S 取放的 GUI 影片：錄影當次連續 3 次全部成功，誤差 0.0–1.4 mm（`projects/tm5s_gazebo_pick_place/docs/evidence_2026-11-25_gui_video`，影片本身不放在 git）。

### 階段 4：microduck RL

- [x] 研讀 [microduck_rl](https://github.com/pollen-robotics/microduck_rl)（MuJoCo／mjlab + PPO），在本機建立環境（uv、mjlab 1.3.0、torch 2.9.1+cu128）。
- [x] 重現平地行走訓練（`Mjlab-Velocity-Flat-MicroDuck`，4096 個環境）：3 輪共 8000 次迭代，約 7 小時。前 2000 次迭代進步最多，之後進入平台期（線速度誤差約 0.41、角速度誤差約 1.06）。
- [x] 匯出 ONNX 策略（輸入 61 維、輸出 14 維，無 NaN），錄影確認 10 秒內保持直立。
- [x] 固定指令評估（6 種指令 × 64 個環境 × 20 秒）：3999 次以後不推時零跌倒；頻繁推力下 5998／7997 比 3999 穩。發現速度追蹤不足：前進只達指令的 50–60%，後退與側移約 20%。
- [x] 調嚴速度追蹤獎勵後接續訓練 2000 次迭代（約 1.8 小時）：前進本體速度從指令的 55–60% 提高到 75–82%，抗推力變好；但直線保持和轉向變差，後退與側移仍約 20%。結果是部分改善。
- [x] （2026-11-25）研讀上游獎勵設計與開發紀錄：上游自己的實機策略也只達指令的約 40%（0.4 → 0.17 m/s）；側移可能被姿態獎勵的 `hip_roll` 容許值（0.05 rad）限制；上次轉向變差是因為把角速度追蹤調窄，上游的解法是另外加 `track_yaw_fine`。
- [ ] 實驗 A／B（`train_tracking_v2.py`）：加 `track_yaw_fine`，以及放寬走路時的 `hip_roll`，各約 1.8 小時 GPU。
- [ ] 研讀獎勵設計與觀測空間，試其他任務（例如崎嶇地形）。

筆記、指令與評估腳本：`projects/microduck_rl_study/README.md`。上游程式碼和機器人網格檔（CC BY-NC-SA）不放進這個 repo。

## 需要在 Windows 操作的步驟

每一項安裝前都會先確認。

| 項目 | 階段 | 狀態 |
|---|---|---|
| 更新 NVIDIA 驅動（Studio 621.24，CUDA 13.5） | GPU | 完成 |
| 安裝 Ollama 並下載模型（含防火牆規則） | 1 | 完成 |
| Isaac Sim 相容性檢查 | 3 | 延後到最後；檢查工具已安裝，停在 EULA |
| Isaac Sim 完整安裝 | 3 | 依檢查結果決定 |

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

### Isaac Sim 相容性檢查（階段 3，延後到最後）

採用最小的 pip 安裝 `isaacsim[compatibility-check]`，只取得檢查工具，不下載完整的 Isaac Sim。步驟依官方文件（[pip 安裝](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html)、[工作站安裝](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_workstation.html)）：

1. 從 python.org 安裝 **Python 3.12**（Windows 64 位元），安裝時勾選「Add python.exe to PATH」與「py launcher」。
2. 以系統管理員 PowerShell 開啟長路徑支援（需重新開機或重新登入才生效）：

   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
   ```

3. 以一般 PowerShell 建立獨立虛擬環境並安裝檢查工具（安裝時需同意 NVIDIA EULA）：

   ```powershell
   mkdir C:\isaacsim
   py -3.12 -m venv C:\isaacsim\env_check
   C:\isaacsim\env_check\Scripts\activate
   pip install "isaacsim[compatibility-check]==6.2.0.0" --extra-index-url https://pypi.nvidia.com
   isaacsim isaacsim.exp.compatibility_check
   ```

4. 檢查結果以顏色標示：綠／淺綠表示良好，橘色表示勉強可用，紅色表示不足或不支援。截圖回報，並按「Test Kit」確認最小的 Kit 應用程式能執行。

預期 VRAM 會顯示紅色或橘色。之後依結果決定：安裝完整 Isaac Sim（官方 zip 安裝在 `C:\isaacsim`，只做簡單場景，例如 UR 手臂取放）、改用其他環境，或延後此階段。

