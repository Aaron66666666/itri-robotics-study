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

**程式層級的安全規則（policy）**：`run_scenario` 只能執行使用者在任務中明確點名的情境（任務含「全部／所有／每個／all」時才允許全部）。被拒絕的呼叫不會執行，只回傳錯誤給模型。這條規則寫在程式裡，而不是只寫在提示詞裡，因為實測發現小模型不一定遵守提示詞（見下方評估）。

| 檔案 | 作用 |
|---|---|
| `robot_agent/messages.py` | 與供應商無關的訊息格式（`Message`、`ToolCall`） |
| `robot_agent/llm.py` | 模型層：`ChatModel` 介面、`OllamaChat`、測試用 `ScriptedModel` |
| `robot_agent/tools.py` | 工具定義、參數驗證、錯誤結果、輸出截斷 |
| `robot_agent/loop.py` | Agent 迴圈、最大輪數、重複呼叫保護、policy |
| `robot_agent/prompts.py` | 系統提示詞（CLI 與評估共用） |
| `robot_agent/acceptance_tools.py` | 真的工具：執行／摘要驗收情境、GPU 狀態 |
| `robot_agent/fake_tools.py` | 假的工具：同名稱同 schema，固定回傳 |
| `run_agent.py` | 命令列入口 |
| `eval_models.py` | 模型評估：固定任務、自動檢查、結果存到 `eval_results/` |

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
python3 run_agent.py --model llama3.1:8b "摘要已保存的 D1_person 執行紀錄"
python3 run_agent.py "用 GPU 執行 person_stop，回報停車反應時間"
python3 run_agent.py --model llama3.1:8b --max-turns 6 "GPU 能用嗎？"
```

連線位址順序：`--ollama-url` → 環境變數 `OLLAMA_HOST` → `http://localhost:11434`（WSL mirrored 模式）→ WSL 預設閘道（NAT 模式下的 Windows 主機，例如 `http://172.24.0.1:11434`）。

## 模型評估（2026-11-24，本機 Ollama，RTX 4070）

`python3 eval_models.py --repeat 2`：6 個固定任務（列出情境、執行 person_stop、GPU 狀態、情境失敗時說明哪項檢查沒過、摘要已保存紀錄、要求不存在的情境），以假工具執行，每項自動檢查「該呼叫的工具有呼叫」、「沒有執行不該執行的工具」、「答案含工具結果的關鍵數字」、「繁體中文」。

| 版本 | Qwen 2.5 7B | Llama 3.1 8B |
|---|---|---|
| 初版提示詞 | 8/12 | 10/12 |
| 加強提示詞（不可只說計畫、不可描述未取得的結果、錯誤提示要照做） | 10/12 | 10/12 |
| 再加程式層 policy（只能執行使用者點名的情境） | 10/12 | **12/12** |

模型已完整載入 GPU（約 5 GB VRAM），暖機後每次呼叫約 0.6–1 秒；每個任務平均 1.4 秒（Llama）／2.8 秒（Qwen）。

觀察到的問題與處理：

- **Qwen 編造結果**：只呼叫了 `list_saved_runs`，就自行寫出一份不存在的摘要 JSON。加強提示詞後不再編造，但仍會停下來反問，而不是去取得摘要。
- **Qwen 混用簡體字**（例如「场」）：在提示詞中舉出繁簡對照後改善。
- **Llama 自作主張**：使用者要求不存在的 `fly_to_moon` 時，它改去執行 `approach`。只靠提示詞擋不住，最後以程式層 policy 解決。
- **評估本身的錯誤也要修**：一開始的關鍵字檢查太嚴（把正確的拒絕判為失敗），假工具也比真工具寬鬆；修正後才是公平比較。

**真實工具實測（Llama 3.1 8B）**：
- 「用 GPU 執行 person_stop…」：Agent 自行執行 Gazebo，回報 PASS、停車反應 130 ms、人物在畫面時位移 0.0 m，與執行紀錄完全一致（`eval_results/real_person_stop_llama.txt`）。
- 「比較 D1_person（CPU）和 D3_person_gpu（GPU）」：第一次失敗。模型照抄了「D1_person (CPU)」當名稱，即使錯誤訊息提示正確名稱也沒有修正。這是工具介面設計的問題：改為當括號前的部分剛好是已保存的紀錄名稱時直接接受（並在結果註明），模糊的名稱則回傳最接近的建議。修正後答案完全正確：94／93 ms 停車、27／20 ms 推論（`eval_results/real_compare_llama.txt`）。兩次停車時間只差 1 ms，屬正常變動，不代表 GPU 讓停車變快。

結論：**目前以 Llama 3.1 8B 作為預設模型較合適**（`run_agent.py --model llama3.1:8b`）。學到的重點：必須遵守的規則要寫在程式裡；工具的錯誤訊息要直接告訴模型怎麼修正；評估要讀實際答案，不能只看分數。

## 測試（34 項，皆不需網路）

- `tests/test_loop.py`：工具呼叫→結果→最終回答、同一輪多個呼叫、未知工具、參數錯誤（未執行工具）、工具例外、情境失敗、最大輪數、重複呼叫保護、模型錯誤、輸出截斷、policy 拒絕未點名的情境。
- `tests/test_ollama.py`：以本機假 `/api/chat` 伺服器驗證請求格式、tool_calls 解析、字串參數、小模型把呼叫寫成文字 JSON 的補救、HTTP 錯誤、`OLLAMA_HOST`、完整跑一次 Agent。
- `tests/test_acceptance_summary.py`：用 2026-11-24 的真實證據（A1、B1、D1、D3）驗證摘要與判定，以及錯誤名稱的提示與解析。

## Windows 端設定（Ollama，2026-11-24 已完成）

Ollama 0.40.18 安裝在 Windows，已下載 `qwen2.5:7b` 與 `llama3.1:8b`。WSL 為 NAT 網路模式，因此：使用者環境變數 `OLLAMA_HOST=0.0.0.0:11434`，加上只允許 WSL 網段（172.16.0.0/12）連入 11434 的防火牆規則「Ollama from WSL」。若 Windows 跳出「是否允許存取」視窗，**不要按取消**：取消會建立封鎖規則，優先權高於允許規則。詳細步驟見 `docs/progress.md`。
