# 階段 2：YOLO 自訂資料訓練（2026-11-24）

結論：用 Gazebo 自動產生並標註的影像，加上少量真實 COCO 影像回放（replay），微調後的 **v3 模型**修好了瓶子辨識。原本的瓶子在 8 個距離中**全部**辨識不到 bottle，v3 在每個距離都達 0.93 以上；人員辨識維持原本水準（0.90–0.94）。機器人實測：車輛在**原本的瓶子場景**中接近瓶子並停下（x = 1.004 m），杯子與人員停止情境也都通過。

## 做法

1. **自動標註**：Gazebo 的 `boundingbox_camera` 感測器會為帶有 `Label` 外掛的物體輸出 2D 框，並已考慮遮擋，不需要人工標註。標籤值為 COCO 類別編號 + 1（感測器的 0 代表背景）：person 1、bottle 40、cup 42。
2. **隨機場景**（`tools/dataset/make_world.py` 產生 `worlds/yolo_datagen.sdf`）：
   - 8 種瓶子：機器人場景中的原瓶子，以及不同顏色、標籤、尺寸（從約 30 cm 到大型）的變體。
   - 7 種杯子：機器人場景中的原馬克杯，以及不同顏色與尺寸的變體。
   - 2 個人物模型（Gazebo Fuel）、3 張桌子、7 個干擾物（方塊、球、圓盤，不標註）、6 種地墊（v2 起含接近白色）、3 面背景牆。
   - 隨機日光方向與亮度；v2 起另有隨機補光（機器人場景有正面補光）。
   - 相機距離 0.7–4.5 m，高度與角度隨機；25% 影像使用與機器人相機完全相同的高度和角度。
3. **產生資料**（`tools/dataset/generate.py`、`build_dataset.sh`）：
   - 以 `set_pose_vector` 一次移動所有模型，等新姿態渲染完成後才擷取畫面。
   - 影像存成 PNG（先前發現 JPEG 壓縮會影響分數）。
   - 每 200 張重新啟動一次 Gazebo，失敗的批次自動重試；每個批次使用固定的亂數種子，結果可重現。
   - 速度約 6 張／秒；train 2000、val 400、test 400 張，三組使用不同種子。
4. **訓練**（`tools/dataset/train_yolo.py`）：從 COCO 預訓練的 `yolo26n.pt` 開始，在 RTX 4070 上訓練 60 epochs（約 15 分鐘）。標籤使用 COCO 類別編號，微調後的模型可以直接取代原模型。

## 三個版本與結果

評估資料是機器人相機在真實機器人場景中擷取的 18 張影格（`tools/dataset/capture_robot_frames.sh`）：瓶子場景 8 個距離、杯子場景 7 個、人物場景 3 個。下表為每類在所有影格中的**最低**分數，括號內是低於 0.35 的影格數：

| 模型 | bottle（8 張） | cup（7 張） | person（3 張） | 合成測試集 mAP50 |
|---|---|---|---|---|
| 原模型 yolo26n | 0.00 [8] | 0.26 [1] | 0.90 [0] | 0.379 |
| v1：只用合成資料 | 0.95 [0] | 0.00 [1] | 0.28 [1] | 0.994 |
| v2：加補光與白地墊、人物增加、凍結骨幹 | 0.87 [0] | 0.58 [0] | 0.07 [2] | 0.990 |
| **v3：v2 資料 + COCO128 回放 ×3** | **0.93 [0]** | **0.76 [0]** | **0.90 [0]** | 0.991 |

- v1 修好瓶子，但**人員信心值下降**（災難性遺忘），杯子在 x = 0.4 m 完全漏檢。
- v2 縮小了場景差異，杯子改善；但凍結骨幹**沒有**解決遺忘問題：人物位置仍框得準，但分數只剩 0.07，可見遺忘發生在分類輸出。
- v3 在每個 epoch 混入 128 張真實 COCO 影像（共 261 個人物框，重複 3 次），人員分數回到原本水準。

注意：這 18 張影格曾用來決定下一版要怎麼改，因此不是完全獨立的測試；最後的判斷依據是下面的閉環實測。合成測試集上所有版本都接近滿分，代表合成資料本身很容易，不能據此判斷模型在機器人場景中的表現。

## 閉環實測（v3，GPU，低速 0.05 m/s）

| 情境 | 結果 | 偵測（每個偵測訊息） |
|---|---|---|
| E1：原瓶子場景，`target_class:=bottle` | PASS：接近 22.6 s，停在 x = 1.004 m，之後不動 | bottle ≥ 0.5 佔 100%（最低 0.84）；原模型完全辨識不到 |
| E2：杯子場景 | PASS：停在 x = 0.529 m | cup ≥ 0.5 佔 99.4%（最低 0.43）；原模型為 100%（最低 0.63） |
| E3：人物情境 | PASS：人物出現後 478 ms 停車，畫面中有人時位移 0.0 m，人離開後 58 ms 恢復接近，停在 x = 0.555 m | person 0.946 |

使用 v3 時的參數：

```bash
model_path:=$HOME/yolo_project/runs/gazebo_ft/yolo26n_gazebo_v3/weights/best.pt device:=0
# 瓶子：target_class:=bottle stop_bbox_dimension:=width stop_bbox_ratio:=0.22
# 杯子：target_class:=cup    stop_bbox_dimension:=width stop_bbox_ratio:=0.185
```

**停止門檻必須依模型重新校正**：Gazebo 的標註框包含杯子把手，所以 v3 的杯子框比原模型寬約 30%。沿用原模型的 0.14 時，車輛一開始就判定「已到達」而完全不動。改為 0.185 後，停止位置與原本相同（約 x = 0.5 m）。

## 取捨與限制

- v3 的杯子在閉環中有少數影格低於控制器門檻 0.5（每次約 2 個影格），造成短暫停車再繼續（安全處理）。原模型對杯子較穩定。因此 launch 的預設模型**維持不變**；需要辨識瓶子時再改用 v3。是否改成預設由使用者決定。
- E3 的停車反應時間 478 ms，接近 500 ms 的檢查上限；先前的執行為 94–180 ms。同一時段 headless Gazebo 的相機只有約 3.7 Hz（正常約 10 Hz，偵測頻率也受影響），但也可能部分來自 person 分數，尚未分開驗證。
- 只驗證 person、bottle、cup 三類。COCO 其他 77 類沒有評估：COCO128 同時用於訓練，無法當作獨立測試。
- 下載項目：COCO128 範例資料集（7 MB，`~/datasets/coco128`）、Ultralytics 繪圖字型。Ultralytics 的 AMP 檢查另外下載了一份 `yolo26n.pt` 到 `~/yolo_project/weights/`（不用於訓練，可刪除）。原本的 `~/yolo_project/yolo26n.pt` 未被修改。

## 檔案位置

| 項目 | 位置 |
|---|---|
| 資料產生與訓練工具 | `tools/dataset/`（`make_world.py`、`generate.py`、`gzcapture.py`、`build_dataset.sh`、`montage.py`、`train_yolo.py`、`eval_models.py`、`capture_robot_frames.sh`） |
| 資料世界 | `worlds/yolo_datagen.sdf`（由 `make_world.py` 產生） |
| 資料集（不納入 git） | `~/yolo_project/datasets/gazebo_bottle_cup`（v1）、`gazebo_bottle_cup_v2`（v2、v3） |
| 模型（不納入 git） | `~/yolo_project/runs/gazebo_ft/yolo26n_gazebo{,_v2,_v3}/weights/best.pt` |
| 證據 | `docs/evidence/2026-11-24/yolo_training/` |

## 開發中遇到的問題

- **Python 的 Gazebo 服務呼叫逾時**：同一個程序若訂閱影像，`request()` 會卡住，因此服務呼叫改在獨立的子程序中執行。
- **離開 Python 時 segfault**：發生在 gz-transport 結束時，以 `os._exit(0)` 避開。
- **Gazebo 執行約 370 張後感測器停止輸出**：改為每 200 張重新啟動 Gazebo，並自動重試失敗的批次。
- **`set -e` 加上找不到行程的 `pkill`** 會讓腳本默默結束；清理步驟改為不會中斷腳本。
- **評估影格混到別的場景**：前一個 Gazebo 尚未完全關閉，兩個模擬器同時發布同一個相機 topic。改為等所有模擬器結束後再啟動下一個，並逐張檢查影格內容。
