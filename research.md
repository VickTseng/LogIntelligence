# LogIntelligence 技術研究摘要

> 版本：v1.0 | 建立日期：2026-05-19

---

## 1. LangChain 套件結構（2025+）

**Decision**: 使用拆分後的 LangChain 套件組合

| 套件 | 用途 | 版本 |
|------|------|------|
| `langchain-core` | 基礎抽象（Runnable、BaseMessage 等） | ≥ 0.3 |
| `langchain-ollama` | ChatOllama、OllamaEmbeddings | ≥ 0.2 |
| `langchain-chroma` | ChromaDB retriever 整合 | ≥ 0.1 |
| `langchain` | Chain、LCEL 組裝工具 | ≥ 0.3 |

**Rationale**: LangChain 自 v0.2 起將第三方整合拆分為獨立套件，`langchain-ollama` 提供原生 streaming 支援與 Ollama chat/embedding 統一介面。

**Alternatives considered**: LlamaIndex — 功能相近但社群資源較少，且 Ollama 整合成熟度略遜於 LangChain。

---

## 2. Ollama Streaming 實作方式

**Decision**: 使用 `ChatOllama(streaming=True)` 搭配 LCEL pipe

```python
from langchain_ollama import ChatOllama
llm = ChatOllama(model="llama3.2", streaming=True)
for chunk in chain.stream({"question": q, "context": ctx}):
    print(chunk, end="", flush=True)
```

**Rationale**: LCEL `stream()` 方法直接對接 Ollama 的 `/api/chat` streaming endpoint，無需手動處理 HTTP chunked response。

**Alternatives considered**: 直接呼叫 `ollama` Python SDK — 可行，但繞過 LangChain 抽象層，增加替換成本。

---

## 3. Ollama 重試機制

**Decision**: 使用 `tenacity` 實作指數退避重試

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
)
def call_ollama(...): ...
```

**Rationale**: `tenacity` 為 Python 標準重試函式庫，支援精確的異常型別過濾，避免對邏輯錯誤（如 prompt 格式問題）進行無意義重試。預設 3 次重試、間隔 2/4/8 秒。

**Alternatives considered**: 自行撰寫重試迴圈 — 易遺漏 jitter，不建議。

---

## 4. NLog 多行例外解析

**Decision**: 以 timestamp 正則作為行首判斷，非 timestamp 開頭的連續行合併至上一筆 LogEntry

```python
TIMESTAMP_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)? \['
)

def is_new_entry(line: str) -> bool:
    return bool(TIMESTAMP_RE.match(line))
```

**Rationale**: NLog 所有有效的新記錄都以 ISO 時間戳開頭，例外堆疊行（`  at ...`、`System.NullRef...`）不符合此模式，可安全判定為延續行。

---

## 5. ChromaDB 時間範圍 Metadata 過濾

**Decision**: 將 timestamp 儲存為 Unix timestamp（整數），使用 ChromaDB `where` filter

```python
collection.query(
    query_embeddings=[embedding],
    n_results=top_k,
    where={
        "$and": [
            {"timestamp_unix": {"$gte": start_ts}},
            {"timestamp_unix": {"$lte": end_ts}},
        ]
    }
)
```

**Rationale**: ChromaDB 的 metadata filter 僅支援數值比較運算子（`$gte`、`$lte`），字串型 ISO timestamp 無法直接範圍查詢，須轉為 Unix timestamp（int）。

---

## 6. 內容去重策略

**Decision**: 以 `SHA256(source_file_abs_path + chunk_text)` 作為 ChromaDB document ID

```python
import hashlib
doc_id = hashlib.sha256(f"{abs_path}::{chunk_text}".encode()).hexdigest()
```

**Rationale**: ChromaDB `add()` 對重複 ID 採 upsert 行為，相同 ID 的文件不會新增副本，自動達成冪等匯入。

---

## 7. CLI 框架

**Decision**: 使用 `typer`（基於 Click）

**Rationale**: `typer` 支援型別提示自動生成 CLI 參數、自動產生 `--help`，比純 `argparse` 更簡潔，且與 Python 3.11+ 型別系統整合良好。

**主要指令結構**：
```
logiq ingest <path> [--recursive]
logiq query [--query TEXT] [--from DATETIME] [--to DATETIME] [--top-k INT]
logiq clear [--confirm]
logiq status
```
