# 即時 YOLO 影格診斷操作

本文件記錄如何比較實際 ROS camera frame 與離線 YOLO 結果。診斷影格預設不保存；只有明確傳入 `diagnostic_frame_path` 才擷取第一張影像，而且不會覆寫已存在檔案。

## 擷取 live frame

在 Gazebo 和 ROS 2 可用的 WSL 原生終端，使用目前正在測試的目標場景。不要在已有模擬器執行時再啟動第二個 world。Workspace 內的 `diff_drive_camera_bottle.sdf` 是 bottle 測試場景，不含 cup。

```bash
source /opt/ros/jazzy/setup.bash
cd ~/robot_ws
source install/setup.bash
gz sim -r worlds/diff_drive_camera_bottle.sdf
```

另開終端：

```bash
source /opt/ros/jazzy/setup.bash
cd ~/robot_ws
source install/setup.bash
ros2 launch robot_control autonomous_yolo.launch.py \
  device:=cpu \
  target_class:=bottle \
  diagnostic_frame_path:=/tmp/yolo_live_frame.png
```

若目前執行的是 cup 場景，請把 `target_class:=bottle` 改為 `target_class:=cup`。`/tmp/yolo_live_frame.png` 必須尚不存在；若先前測試已建立，請自行選擇另一個未使用檔名。

## 同一張影格離線比對

啟動日誌會列出輸入 encoding、ndarray shape/dtype/channel stats，以及推論耗時、runtime device 和偵測結果。取得 PNG 後，以相同模型、conf 和 CPU 重跑：

```bash
~/yolo_project/.venv/bin/python - <<'PY'
from ultralytics import YOLO

image = '/tmp/yolo_live_frame.png'
model = YOLO('/home/yulin/yolo_project/yolo26n.pt')
result = model.predict(
    source=image,
    conf=0.35,
    device='cpu',
    verbose=False,
    save=False,
)[0]
for box in result.boxes or []:
    class_id = int(box.cls[0].item())
    print(
        result.names[class_id],
        float(box.conf[0].item()),
        box.xyxy[0].tolist(),
    )
PY
```

- 若 live topic 發布空陣列、而擷取 frame 離線也沒有 cup，差異來自該時刻影像/場景內容或模型分數未過 conf；對照日誌的 channel means、影像和 confidence。
- 若擷取 frame 離線能辨識而即時節點同影格為空，記錄完整 node startup/import 路徑、YOLO conf/device、推論錯誤及 `/yolo/detections` JSON，再檢查不同 process 的套件或參數覆寫。
- `/yolo/image` 的約 4 Hz 是標註影格更新頻率；camera topic 7–8 Hz 時，CPU 推論可能略過舊 sensor frames。這影響時間取樣，不能單獨證明影像轉換會產生空 boxes。

## ROS graph / 自主控制檢查

```bash
ros2 topic hz /vehicle_blue/camera/image
ros2 topic hz /yolo/detections
ros2 topic echo /yolo/detections
ros2 topic hz /yolo/image
ros2 topic echo /model/vehicle_blue/cmd_vel
ros2 topic echo /model/vehicle_blue/odometry
```

檢查 `approach_target` 時是否有非零 `linear.x`，以及 odometry 是否改變。不要以放寬 stale timeout 或提高車速作為通過條件；逾時停止、人員停止優先權應保持有效。
