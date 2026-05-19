# LogIntelligence 資料模型

> 版本：v1.0 | 建立日期：2026-05-19

---

## 1. 核心實體

### 1.1 LogEntry（解析後的原始 Log 記錄）

解析 NLog 輸出後在記憶體中的中間表示，**不持久化**，僅作為 chunking 的輸入。

| 欄位 | 型別 | 說明 | 必填 |
|------|------|------|------|
| `timestamp` | `datetime` | Log 產生時間（UTC 或本機時間，依來源） | ✅ |
| `timestamp_unix` | `int` | Unix timestamp（秒），用於 ChromaDB metadata filter | ✅ |
| `level` | `str` | Log Level：TRACE / DEBUG / INFO / WARN / ERROR / FATAL | ✅ |
| `logger` | `str` | Logger 名稱（通常為類別名稱，如 `OrderService`） | ✅ |
| `message` | `str` | 主要訊息文字 | ✅ |
| `exception_lines` | `list[str]` | 例外堆疊的延續行（空列表表示無例外） | ✅ |
| `source_file` | `str` | 來源 Log 檔案的絕對路徑 | ✅ |
| `raw_text` | `str` | 合併所有行的完整原始文字（含 stack trace） | ✅ |

**合法的 Log Level 值**（正規化為大寫）：
`TRACE`, `DEBUG`, `INFO`, `WARN`, `WARNING`, `ERROR`, `FATAL`, `CRITICAL`

---

### 1.2 LogChunk（向量化單元）

由 LogEntry 切分後送入 embedding 的最小單位，**持久化於 ChromaDB**。

| 欄位 | 型別 | 說明 | 儲存位置 |
|------|------|------|----------|
| `id` | `str` | SHA256(source_file + chunk_text)，作為 ChromaDB document ID | ChromaDB ID |
| `text` | `str` | chunk 的完整文字內容（含 metadata prefix） | ChromaDB document |
| `embedding` | `list[float]` | 由 `nomic-embed-text` 生成的向量 | ChromaDB embedding |
| `source_file` | `str` | 來源檔案絕對路徑 | ChromaDB metadata |
| `source_file_name` | `str` | 來源檔案名稱（basename，供顯示用） | ChromaDB metadata |
| `timestamp_unix` | `int` | 該 chunk 第一筆 LogEntry 的 Unix timestamp | ChromaDB metadata |
| `timestamp_iso` | `str` | ISO 8601 格式時間戳（供人閱讀） | ChromaDB metadata |
| `level` | `str` | Log Level（最高嚴重等級，若 chunk 跨多行） | ChromaDB metadata |
| `logger` | `str` | Logger 名稱 | ChromaDB metadata |
| `chunk_index` | `int` | 在同一 LogEntry 中的切分序號（從 0 起） | ChromaDB metadata |

**ChromaDB Collection 名稱**：`log_intelligence`（單一集合，跨所有來源）

---

### 1.3 QueryResult（查詢結果）

RAG 查詢後回傳給 CLI 的輸出結構，**不持久化**。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `question` | `str` | 使用者原始問題 |
| `answer` | `str` | LLM 生成的回答（streaming 模式下為空，直接輸出至 stdout） |
| `sources` | `list[SourceRef]` | 所用 Log 片段的來源參考列表 |
| `retrieval_count` | `int` | 實際使用的 chunk 數量 |
| `no_results` | `bool` | 若為 True 表示未找到相關日誌 |

#### SourceRef

| 欄位 | 型別 | 說明 |
|------|------|------|
| `source_file_name` | `str` | 來源檔案名稱 |
| `timestamp_iso` | `str` | 該 chunk 的時間戳 |
| `level` | `str` | Log Level |
| `score` | `float` | 相似度分數（0.0 ~ 1.0，越高越相關） |

---

## 2. ChromaDB Schema

```
Collection: log_intelligence
├── Documents: list[str]          ← chunk text
├── Embeddings: list[list[float]] ← nomic-embed-text vectors (768 dim)
├── IDs: list[str]                ← SHA256 hash (dedup key)
└── Metadatas: list[dict]
    ├── source_file: str
    ├── source_file_name: str
    ├── timestamp_unix: int        ← range filter target
    ├── timestamp_iso: str
    ├── level: str
    ├── logger: str
    └── chunk_index: int
```

---

## 3. 設定檔 Schema（config.yaml）

```yaml
ollama:
  base_url: "http://localhost:11434"
  llm_model: "llama3.2"
  embedding_model: "nomic-embed-text"
  timeout_seconds: 30
  retry:
    max_attempts: 3
    wait_seconds: 2        # 指數退避基礎值

chromadb:
  persist_path: "./data/chroma"
  collection_name: "log_intelligence"

retrieval:
  top_k: 5

chunking:
  chunk_size: 512          # tokens
  chunk_overlap: 50        # tokens
  merge_multiline_exceptions: true  # 合併多行 exception 為單一 chunk
```

---

## 4. NLog 文字格式解析規則

**支援格式**（REQ-001）：
```
YYYY-MM-DD HH:mm:ss.fff [LEVEL] Logger - Message
YYYY-MM-DD HH:mm:ss [LEVEL] Logger - Message
```

**正則模式**：
```python
r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\[(?P<level>\w+)\]\s+(?P<logger>\S+)\s+-\s+(?P<message>.+)$'
```

**多行例外判斷**：
- 新記錄行：符合上述正則
- 延續行：不符合正則（通常為 `  at ...`、`System.XXXException...`、`--- End of...`）

**NLog JSON 格式**（REQ-002，P1）：
```json
{"time":"2026-05-19T14:00:01.123","level":"Error","message":"...","exception":"..."}
```
