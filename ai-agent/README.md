# 本機 AI Agent：機器人驗收助理

自己寫的工具呼叫（tool calling）Agent。模型跑在本機 Ollama（Windows，RTX 4070），WSL 裡的 Agent 依照使用者的指示呼叫工具，執行 Gazebo/YOLO 驗收情境並回報結果。不使用任何付費 API。

## 架構

```text
使用者任務 ─▶ run_agent()（loop.py）
                │  ① 把對話與工具定義送給模型
                ▼
         ChatModel.chat()（llm.py）── OllamaChat ─▶ Windows Ollama :11434
                │  ② 模型回覆：文字（結束）或 tool_calls
                ▼
         ToolRegistry.execute()（tools.py）
                │  ③ 驗證參數 → 執行 → 錯誤也包成結果；輸出截斷
                ▼
         acceptance_tools.py（真的）／fake_tools.py（假的）
                │  ④ 只回傳 JSON 摘要（PASS/FAIL、檢查項目、關鍵數字）
                └──▶ 結果以 role=tool 加回對話，回到 ①
```

停止條件：模型不再呼叫工具（最終回答）、達到 `--max-turns`、或模型連線錯誤。同一個呼叫（同名稱＋同參數）重複超過 2 次會被拒絕，避免小模型卡在迴圈。

| 檔案 | 作用 |
|---|---|
| `robot_agent/messages.py` | 與供應商無關的訊息格式（`Message`、`ToolCall`） |
| `robot_agent/llm.py` | 模型層：`ChatModel` 介面、`OllamaChat`、測試用 `ScriptedModel` |
| `robot_agent/tools.py` | 工具定義、參數驗證、錯誤結果、輸出截斷 |
| `robot_agent/loop.py` | Agent 迴圈與最大輪數 |
| `robot_agent/acceptance_tools.py` | 真的工具：執行／摘要驗收情境、GPU 狀態 |
| `robot_agent/fake_tools.py` | 假的工具：同名稱同 schema，固定回傳 |
| `run_agent.py` | 命令列入口 |

### 以後換成其他模型

迴圈和工具只依賴 `ChatModel.chat(messages, tools) -> Message`。若要改用雲端 API，只需在 `llm.py` 新增一個實作同一方法的類別（把 `Message`／工具定義轉成該 API 的格式），`loop.py`、工具與測試都不用改。

## 工具

| 工具 | 參數 | 說明 |
|---|---|---|
| `list_scenarios` | 無 | 可執行的情境：`approach`、`target_loss`、`person_stop` |
| `run_scenario` | `scenario`、`device`（gpu/cpu） | 在 headless Gazebo 執行一個情境（約 1.5 分鐘），回傳摘要 |
| `list_saved_runs` | 無 | 已保存的執行紀錄（含 `docs/evidence` 的證據） |
| `get_run_summary` | `run_name` | 某次執行的 PASS/FAIL 摘要 |
| `get_gpu_status` | 無 | GPU、驅動、YOLO 環境的 CUDA 狀態 |

所有解析與判定都在 Python 內完成；模型只讀摘要，不讀原始 log。

## 使用

```bash
cd ~/itri-robotics-study/ai-agent
python3 -m pytest -q                       # 測試（不需要 Ollama 或 Gazebo）
python3 run_agent.py --fake "列出情境並全部執行，回報哪些通過"
python3 run_agent.py "摘要已保存的 person_stop 執行紀錄"
python3 run_agent.py "用 GPU 執行 person_stop，回報停車反應時間"
python3 run_agent.py --model llama3.1:8b --max-turns 6 "GPU 能用嗎？"
```

連線位址順序：`--ollama-url` → 環境變數 `OLLAMA_HOST` → `http://localhost:11434`（WSL mirrored 模式）→ WSL 預設閘道（NAT 模式下的 Windows 主機，例如 `http://172.24.0.1:11434`）。

## 測試（28 項，皆不需網路）

- `tests/test_loop.py`：工具呼叫→結果→最終回答、同一輪多個呼叫、未知工具、參數錯誤（未執行工具）、工具例外、情境失敗、最大輪數、重複呼叫保護、模型錯誤、輸出截斷。
- `tests/test_ollama.py`：以本機假 `/api/chat` 伺服器驗證請求格式、tool_calls 解析、字串參數、小模型把呼叫寫成文字 JSON 的補救、HTTP 錯誤、`OLLAMA_HOST`、完整跑一次 Agent。
- `tests/test_acceptance_summary.py`：用 2026-11-24 的真實證據（A1、B1、D1、D3）驗證摘要與判定。

## Windows 端設定（Ollama）

見 `docs/progress.md` 的「需要在 Windows 操作的步驟」。WSL 目前是 NAT 網路模式，所以 Ollama 要允許 WSL 連入（或改用 mirrored 模式）。
