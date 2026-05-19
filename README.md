# LogIntelligence

以自然語言查詢 NLog 日誌的本地 RAG 系統。將 NLog 產生的日誌匯入後，直接用中文提問，系統透過語意檢索找到相關日誌片段，再交由本地 LLM 生成有脈絡的回答。

所有運算在本機完成，日誌資料不會離開你的環境。

---

## 架構概覽

```
NLog 日誌檔案
    │
    ▼
logiq ingest          ← 解析 NLog 格式、切分 chunk、向量化
    │
    ▼
ChromaDB              ← 向量儲存（本機持久化）
    │
    ▼  ← 使用者提問
logiq query           ← 語意檢索 + Ollama LLM 串流回應
```

**技術選型**：Python 3.9 · LangChain · Ollama · ChromaDB · Typer

---

## 系統需求

| 需求 | 說明 |
|------|------|
| Python | 3.9+ |
| [Ollama](https://ollama.com/) | 本機 LLM runtime |
| 磁碟空間 | 依日誌量與模型大小而定（建議 ≥ 10 GB） |

---

## 安裝

### 1. 安裝 Python 套件

```bash
pip install -r requirements.txt
```

### 2. 安裝並啟動 Ollama

```bash
# 安裝 Ollama（見 https://ollama.com/download）

# 下載所需模型
ollama pull llama3.2          # LLM（推論用）
ollama pull nomic-embed-text  # Embedding 模型（向量化用）

# 啟動 Ollama 服務
ollama serve
```

### 3. 調整設定（選用）

複製並編輯 `config.yaml`：

```yaml
ollama:
  base_url: "http://localhost:11434"
  llm_model: "llama3.2"          # 可換成其他 Ollama 模型
  embedding_model: "nomic-embed-text"

chromadb:
  persist_path: "./data/chroma"  # 向量資料儲存路徑

retrieval:
  top_k: 5                       # 每次查詢取回的最相關片段數

chunking:
  chunk_size: 512
  chunk_overlap: 50
  merge_multiline_exceptions: true  # 將 exception stack trace 合併為單一片段
```

也可透過環境變數覆寫，例如：

```bash
export OLLAMA_LLM_MODEL=mistral
export RETRIEVAL_TOP_K=8
```

---

## 使用方式

所有指令皆以 `python3 -m logiq.cli.main` 執行，或安裝後直接使用 `logiq`：

```bash
# 安裝為可執行指令（選用）
pip install -e .
```

---

### `logiq ingest` — 匯入日誌

將 NLog 日誌解析並向量化存入知識庫。

```bash
# 匯入單一檔案
logiq ingest ./logs/app-2026-05-19.log

# 匯入整個目錄（遞迴掃描 .log 檔）
logiq ingest ./logs/

# 不遞迴掃描子目錄
logiq ingest ./logs/ --no-recursive

# 指定設定檔
logiq ingest ./logs/ --config /path/to/config.yaml
```

**執行結果範例**：

```
正在匯入 3 個檔案...
✅ 匯入完成
新增至知識庫   195 chunks
重複（已存在）  12 chunks
處理失敗檔案    0
```

重複執行同一檔案不會產生重複資料（以內容 hash 去重）。

---

### `logiq query` — 查詢日誌

以自然語言提問，獲得基於日誌的 LLM 串流回答。

**互動模式**（持續提問）：

```bash
logiq query
```

```
進入互動模式。輸入問題後按 Enter，輸入 exit 離開。

> 今天有哪些 ERROR？
檢索中... 找到 5 個相關片段

─────────────────────────────────────────
根據日誌記錄，今天共出現以下 ERROR...
（LLM 逐字串流輸出）
─────────────────────────────────────────

來源日誌：
  [1] app-2026-05-19.log | 2026-05-19 14:02:31 | ERROR | 相似度: 0.92
  [2] app-2026-05-19.log | 2026-05-19 09:15:44 | ERROR | 相似度: 0.87

> exit
```

**單次查詢**：

```bash
logiq query -q "OrderService 為什麼拋出 NullReferenceException？"
```

**依時間範圍查詢**（對應 US-003）：

```bash
logiq query -q "這段時間發生了什麼事？" \
  --from "2026-05-19 14:00" \
  --to "2026-05-19 14:30"
```

**其他選項**：

```bash
--top-k 10          # 取回更多相關片段
--no-sources        # 不顯示來源日誌列表
```

---

### `logiq status` — 查看知識庫狀態

```bash
logiq status
```

```
          知識庫狀態
ChromaDB 路徑    ./data/chroma
Collection       log_intelligence
總 chunk 數      12,345
來源檔案數        8
最早記錄         2026-05-01T00:00:01
最新記錄         2026-05-19T23:59:58
Ollama 狀態      ✅ 連線正常 (http://localhost:11434)
LLM 模型         llama3.2
Embedding 模型   nomic-embed-text
```

---

### `logiq clear` — 清除知識庫

```bash
logiq clear
# 將提示確認後清除所有向量資料

logiq clear --confirm  # 跳過確認（適合腳本使用）
```

---

## 支援的 NLog 格式

**純文字格式**（預設，REQ-001）：

```
2026-05-19 14:00:01.123 [ERROR] OrderService - Payment failed
System.NullReferenceException: Object reference not set
  at OrderService.ProcessPayment() in OrderService.cs:line 42
  at Controller.Post() in OrderController.cs:line 18
2026-05-19 14:00:02.456 [INFO] OrderService - Order rollback complete
```

Exception stack trace 會依 `merge_multiline_exceptions` 設定決定是否合併為單一 chunk（預設合併，保留完整除錯上下文）。

---

## 典型工作流程

```bash
# 每天早上匯入昨日日誌
logiq ingest /var/log/myapp/ --no-recursive

# 調查生產事件
logiq query -q "昨晚 23:00 到 00:00 之間有哪些異常？" \
  --from "2026-05-18 23:00" --to "2026-05-19 00:00"

# 追查特定錯誤
logiq query -q "DatabaseTimeoutException 是在哪個模組最常發生？"

# 了解特定服務行為
logiq query -q "PaymentService 處理訂單的完整流程是什麼？"
```

---

## 專案結構

```
LogIntelligence/
├── logiq/
│   ├── config/        # 設定載入（Settings dataclass）
│   ├── ingestion/     # NLog 解析（parser）與檔案掃描（loader）
│   ├── vectorstore/   # ChromaDB 連線、Embedding、chunk upsert
│   ├── retrieval/     # 語意檢索 + 時間範圍過濾
│   ├── chain/         # RAG Prompt 模板 + LCEL streaming chain
│   └── cli/           # Typer CLI 入口點
├── tests/             # pytest 單元測試
├── config.yaml        # 預設設定
├── requirements.txt
└── pyproject.toml
```

---

## 常見問題

**Q: 查詢回應很慢？**
回應時間主要取決於 LLM 推論速度。使用較小的模型（如 `llama3.2:1b`）可大幅提升速度，或增加系統 RAM / 使用 Apple Silicon 加速。

**Q: 出現 `無法連線至 Ollama` 錯誤？**
確認 Ollama 服務已啟動：`ollama serve`，並確認 `config.yaml` 的 `base_url` 正確。

**Q: 回應說「找不到相關日誌」？**
- 確認已執行 `logiq ingest` 匯入日誌
- 執行 `logiq status` 確認 chunk 數量 > 0
- 嘗試不同的問題關鍵字，或放寬時間範圍

**Q: 如何換用不同的 LLM 模型？**
修改 `config.yaml` 中的 `ollama.llm_model`，確認已執行 `ollama pull <model_name>`。
