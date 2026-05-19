# LogIntelligence 需求規格

> 版本：v1.0 | 建立日期：2026-05-19
> 前置文件：[CONSTITUTION.md](CONSTITUTION.md)

---

## 1. 功能範疇概述

LogIntelligence 是一套本地化 Log 智慧問答系統。使用者將 NLog 產生的日誌匯入系統後，可以自然語言提問，系統透過 RAG 流程從向量知識庫中檢索相關日誌片段，結合 Ollama 本地 LLM 生成有脈絡的回應。

---

## 2. 使用者角色

| 角色 | 描述 |
|------|------|
| **維運工程師** | 需要快速定位系統錯誤、追查異常事件的主要使用者 |
| **開發工程師** | 需要理解特定功能的執行流程與 Log 脈絡 |

---

## 3. 功能需求

### 3.1 Log 匯入模組

#### REQ-001：支援 NLog 文字格式解析
- **描述**：系統能讀取 NLog 輸出的純文字 Log 檔案（`.log` / `.txt`），解析每一行的時間戳、Log Level、Logger 名稱與訊息內容
- **驗收條件**：
  - 能正確解析 `YYYY-MM-DD HH:mm:ss.fff [LEVEL] Logger - Message` 格式
  - 解析失敗的行不中斷程序，記錄警告並跳過
- **優先級**：P0（必做）

#### REQ-002：支援 NLog JSON 格式解析
- **描述**：系統能讀取 NLog 輸出的 JSON 格式 Log 檔案，提取標準欄位
- **驗收條件**：
  - 能解析包含 `time`、`level`、`message`、`exception` 欄位的 JSON 物件
  - 每行一個 JSON 物件（NDJSON 格式）
- **優先級**：P1（次要）

#### REQ-003：Log 批次匯入
- **描述**：使用者透過 CLI 指定一個或多個 Log 檔案路徑，系統批次解析並存入向量資料庫
- **驗收條件**：
  - 支援單檔與目錄（遞迴掃描 `.log` 檔案）
  - 顯示匯入進度（已處理行數 / 總行數）
  - 重複匯入同一檔案不產生重複向量（以內容 hash 去重）
- **優先級**：P0（必做）

---

### 3.2 向量化模組

#### REQ-004：Log 分段（Chunking）
- **描述**：將解析後的 Log 記錄切分成適合 embedding 的片段
- **驗收條件**：
  - 預設每段不超過 512 tokens
  - 相鄰段落有 50 token 重疊（overlap）以保留上下文
  - 每個 chunk 保留原始 Log 的時間戳與 Level 作為 metadata
  - **多行例外合併**（可設定）：預設將連續的多行 exception stack trace 合併為單一 chunk，保留完整堆疊上下文；可透過 `config.yaml` 中的 `chunking.merge_multiline_exceptions: false` 關閉
- **優先級**：P0（必做）

#### REQ-005：Embedding 生成與儲存
- **描述**：使用 Ollama 的 Embedding 模型對每個 chunk 生成向量，並儲存至 ChromaDB
- **驗收條件**：
  - 預設使用 `nomic-embed-text` 模型
  - 所有 Log 來源使用單一 ChromaDB 集合（collection），每筆 chunk 的 metadata 包含：`source_file`（來源檔名）、`timestamp`（ISO 格式）、`level`（Log Level）、`text`（原始文字）
  - ChromaDB 資料持久化至本機磁碟路徑（可設定）
  - 支援跨 `source_file` 的聯合查詢，不需使用者指定來源
- **優先級**：P0（必做）

---

### 3.3 查詢與 RAG 模組

#### REQ-006：自然語言查詢介面（CLI）
- **描述**：使用者在 CLI 輸入問題，系統執行 RAG 流程並回傳答案
- **驗收條件**：
  - 互動模式：持續接受輸入直到使用者輸入 `exit`
  - 單次模式：`--query "問題"` 參數直接取得結果
- **優先級**：P0（必做）

#### REQ-007：向量相似度檢索
- **描述**：將使用者問題 embedding 後，從 ChromaDB 檢索最相關的 Log 片段
- **驗收條件**：
  - 預設取回 Top-5 最相關片段
  - 回傳片段數量可透過設定調整（`top_k` 參數）
  - 顯示每個檢索結果的相似度分數
  - **時間範圍過濾**：支援 pre-retrieval metadata filter，在 ChromaDB 的 `where` 條件以 `timestamp` 欄位過濾後再執行 similarity search；時間範圍可由使用者在問題中自然語言指定或透過 `--from` / `--to` 參數傳入
- **優先級**：P0（必做）

#### REQ-008：RAG 回應生成
- **描述**：將檢索到的 Log 片段作為 context，結合使用者問題，透過 Ollama LLM 生成回應
- **驗收條件**：
  - Prompt 模板包含：系統角色說明、檢索到的 Log context、使用者問題
  - LLM 回應後附上所用 Log 片段的來源（檔名 + 時間戳）
  - 若無相關 Log，明確告知使用者「找不到相關日誌」，不憑空生成
  - **串流輸出**：使用 Ollama streaming API，LLM 生成的 token 即時列印至終端機，來源資訊在串流結束後統一輸出
- **優先級**：P0（必做）

#### REQ-009：可設定的 Ollama 模型
- **描述**：使用者可設定要使用的 Ollama 模型名稱
- **驗收條件**：
  - 可在設定檔或環境變數中指定模型（如 `llama3`、`mistral` 等）
  - 若指定模型不存在，給出清楚的錯誤訊息與建議命令（`ollama pull <model>`）
- **優先級**：P1（次要）

---

### 3.4 系統設定模組

#### REQ-010：集中設定管理
- **描述**：系統透過設定檔管理所有可調整參數
- **驗收條件**：
  - 設定檔格式：`config.yaml`（支援 `.env` 覆寫）
  - 可設定項目：Ollama base URL、LLM model、Embedding model、ChromaDB 路徑、top_k、chunk size、overlap
- **優先級**：P0（必做）

---

## 4. 非功能需求

| ID | 類別 | 需求 | 目標 |
|----|------|------|------|
| NFR-001 | 效能 | 單次查詢端到端回應時間 | < 10 秒（本機） |
| NFR-002 | 效能 | 批次匯入吞吐量 | ≥ 1,000 行 / 秒（解析 + embedding） |
| NFR-003 | 可靠性 | 匯入失敗不中斷整批處理 | 跳過錯誤行，完成後報告錯誤統計 |
| NFR-006 | 可靠性 | Ollama 連線失敗自動重試 | 預設重試 3 次，間隔 2 秒；重試耗盡後顯示錯誤訊息與 `ollama serve` 建議指令 |
| NFR-004 | 隱私 | 所有資料處理在本機完成 | 不傳送任何日誌至外部網路 |
| NFR-005 | 可維護性 | 模組解耦 | 各模組可獨立替換（如換掉 ChromaDB → FAISS） |

---

## 5. 使用者故事

### US-001：匯入今天的 Log 並開始查詢

```
身為維運工程師，
我想要執行一個指令將今天的 NLog 檔案匯入系統，
以便我能立即透過自然語言查詢今天發生的錯誤。

驗收條件：
- 執行 `logiq ingest ./logs/app-2026-05-19.log` 後，系統完成向量化並顯示摘要
- 執行 `logiq query` 進入互動模式，輸入「今天有哪些 ERROR？」獲得列表式回答
```

### US-002：追查特定錯誤的原因

```
身為開發工程師，
我想要輸入一段錯誤訊息關鍵字，
以便快速找到該錯誤在 Log 中的完整上下文與可能原因。

驗收條件：
- 輸入「NullReferenceException 在 OrderService 的原因是什麼？」
- 系統回傳包含相關 Log 片段與 LLM 分析的回應
- 回應附上來源 Log 的時間戳
```

### US-003：了解系統在特定時間的行為

```
身為維運工程師，
我想要詢問特定時間區間的系統狀態，
以便理解某次異常事件的前因後果。

驗收條件：
- 輸入「2026-05-19 14:00 到 14:30 之間發生了什麼？」
- 系統從 ChromaDB 過濾對應時間的 Log 並生成時序摘要
```

---

## 6. 系統邊界與限制

- **Log 格式**：初版僅支援 NLog 純文字格式（REQ-001）；JSON 格式（REQ-002）為次要優先
- **使用介面**：初版僅提供 CLI；Web API 為未來擴充項目
- **資料規模**：ChromaDB 單機部署，適合 < 100 萬筆向量（約數百 MB 日誌）
- **語言**：使用者問題與 LLM 回應語言跟隨 Ollama 模型能力，預設以繁體中文提問為主

---

## 8. 澄清記錄

### Session 2026-05-19

- Q: NLog 多行記錄（例外堆疊）應如何處理？ → A: 可設定，預設合併多行 exception 為單一 chunk，使用者可透過 config 關閉
- Q: Ollama 服務不可用時系統應如何處理？ → A: 自動重試 N 次後失敗，適合 Ollama 偶爾啟動慢的情境
- Q: 時間範圍過濾應在哪個層次實作？ → A: Pre-retrieval，在 ChromaDB 以 metadata timestamp 過濾後再做 similarity search
- Q: LLM 回應應以串流還是批次方式輸出？ → A: 串流輸出（streaming），LLM 生成字元即時顯示於終端機
- Q: 多來源 Log 的 ChromaDB 集合策略為何？ → A: 單一集合，每筆 chunk 以 source_file metadata 區分來源，支援跨服務查詢

---

## 7. 術語表

| 術語 | 定義 |
|------|------|
| RAG | Retrieval-Augmented Generation，先檢索相關文件再交由 LLM 生成回答的技術架構 |
| Chunk | 將長文件切分後的文字片段，作為 embedding 的基本單位 |
| Embedding | 將文字轉換為高維向量，用於語意相似度比對 |
| NLog | .NET 平台的日誌框架，本系統的 Log 來源 |
| Ollama | 本地執行大型語言模型的工具 |
| ChromaDB | 開源嵌入式向量資料庫 |
