# LogIntelligence 技術實作計畫

> 版本：v1.0 | 建立日期：2026-05-19
> 前置文件：[spec.md](spec.md) | [CONSTITUTION.md](CONSTITUTION.md)
> 設計產物：[research.md](research.md) | [data-model.md](data-model.md) | [contracts/cli-schema.md](contracts/cli-schema.md)

---

## 1. 技術選型確認

| 技術面向 | 選擇 | 套件 / 版本 |
|---------|------|------------|
| 程式語言 | Python 3.11+ | — |
| RAG 框架 | LangChain | `langchain>=0.3`, `langchain-core>=0.3` |
| LLM 整合 | Ollama via LangChain | `langchain-ollama>=0.2` |
| 向量資料庫 | ChromaDB | `langchain-chroma>=0.1`, `chromadb>=0.5` |
| Embedding | nomic-embed-text（Ollama） | 同 `langchain-ollama` |
| CLI 框架 | Typer | `typer>=0.12` |
| 重試機制 | Tenacity | `tenacity>=8.0` |
| 設定管理 | PyYAML + python-dotenv | `pyyaml>=6.0`, `python-dotenv>=1.0` |
| 測試框架 | pytest | `pytest>=8.0`, `pytest-mock>=3.12` |

---

## 2. 憲章合規確認

| 原則 | 合規狀態 | 說明 |
|------|---------|------|
| RAG-First | ✅ | Prompt 模板強制要求 LLM 依 context 回答；無 context 時回傳固定拒絕訊息 |
| 本地優先 | ✅ | Ollama + ChromaDB 全本機；無任何外部 API 呼叫 |
| 可觀測性 | ✅ | 每次回應附來源 chunk 清單（REQ-008）；streaming 後輸出 SourceRef |
| 模組化設計 | ✅ | 5 個獨立模組（ingestion / vectorstore / retrieval / chain / cli），可個別替換 |

---

## 3. 系統架構

```
logiq/
├── config/
│   ├── __init__.py
│   └── settings.py          ← 載入 config.yaml + .env，提供 Settings dataclass
│
├── ingestion/
│   ├── __init__.py
│   ├── parser.py            ← NLog 文字/JSON 格式解析 → LogEntry
│   └── loader.py            ← 檔案/目錄掃描，產出 LogEntry 串流
│
├── vectorstore/
│   ├── __init__.py
│   ├── client.py            ← ChromaDB 連線、Collection 初始化
│   ├── embedder.py          ← OllamaEmbeddings 封裝（含重試）
│   └── store.py             ← LogChunk upsert、去重（SHA256 ID）
│
├── retrieval/
│   ├── __init__.py
│   └── retriever.py         ← ChromaDB similarity search + metadata filter
│
├── chain/
│   ├── __init__.py
│   ├── prompt.py            ← Prompt 模板定義
│   └── rag_chain.py         ← LCEL chain 組裝（streaming）
│
├── cli/
│   ├── __init__.py
│   └── main.py              ← Typer app，定義 ingest / query / status / clear
│
└── tests/
    ├── test_parser.py
    ├── test_store.py
    ├── test_retriever.py
    └── test_rag_chain.py
```

---

## 4. 模組設計詳細說明

### 4.1 config/settings.py

```python
from dataclasses import dataclass
from pathlib import Path
import yaml, os
from dotenv import load_dotenv

@dataclass
class OllamaSettings:
    base_url: str
    llm_model: str
    embedding_model: str
    timeout_seconds: int
    retry_max_attempts: int
    retry_wait_seconds: int

@dataclass
class ChromaSettings:
    persist_path: Path
    collection_name: str

@dataclass
class RetrievalSettings:
    top_k: int

@dataclass
class ChunkingSettings:
    chunk_size: int
    chunk_overlap: int
    merge_multiline_exceptions: bool

@dataclass
class Settings:
    ollama: OllamaSettings
    chroma: ChromaSettings
    retrieval: RetrievalSettings
    chunking: ChunkingSettings

def load_settings(config_path: Path = Path("config.yaml")) -> Settings: ...
```

---

### 4.2 ingestion/parser.py

**核心職責**：將 NLog 原始文字轉為 `LogEntry` 物件串列

**多行合併邏輯**：
1. 逐行掃描，以 `TIMESTAMP_RE` 判斷是否為新記錄
2. 若為新記錄且有暫存中的 pending entry → flush 前一筆
3. 若為延續行（`merge_multiline_exceptions=True`）→ 附加至 pending entry 的 `exception_lines`
4. 若為延續行（`merge_multiline_exceptions=False`）→ 獨立建立 LogEntry（`level=CONTINUATION`）

**JSON 格式解析**（P1）：
- 嘗試 `json.loads()` 每行，成功則走 JSON 路徑，失敗則走文字路徑

---

### 4.3 vectorstore/embedder.py

**重試包裝**：

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

class OllamaEmbedder:
    def __init__(self, settings: OllamaSettings):
        self._embeddings = OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.base_url,
        )

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
    )
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
```

---

### 4.4 retrieval/retriever.py

**時間範圍過濾（pre-retrieval）**：

```python
def build_where_filter(from_ts: int | None, to_ts: int | None) -> dict | None:
    conditions = []
    if from_ts:
        conditions.append({"timestamp_unix": {"$gte": from_ts}})
    if to_ts:
        conditions.append({"timestamp_unix": {"$lte": to_ts}})
    if not conditions:
        return None
    return {"$and": conditions} if len(conditions) > 1 else conditions[0]
```

**Retriever 封裝**：返回 `list[Document]`（LangChain 標準型別），metadata 完整傳遞供 SourceRef 建構使用。

---

### 4.5 chain/prompt.py

**Prompt 模板**（繁體中文系統提示）：

```
你是一個專業的系統日誌分析助理。
你的回答必須完全基於以下提供的日誌記錄，不可自行推測或編造。
若日誌記錄中沒有足夠的資訊回答問題，請明確告知「根據目前日誌，無法確定...」。

=== 相關日誌記錄 ===
{context}
===================

使用者問題：{question}

請以繁體中文回答：
```

---

### 4.6 chain/rag_chain.py

**LCEL 組裝（streaming）**：

```python
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

chain = (
    {
        "context": retriever | format_docs,
        "question": RunnablePassthrough(),
    }
    | prompt
    | llm  # ChatOllama(streaming=True)
    | StrOutputParser()
)

# 使用端：
for token in chain.stream(question):
    print(token, end="", flush=True)
```

**無結果守衛**：在 `format_docs` 步驟判斷 retriever 回傳為空，若為空則短路返回固定拒絕訊息，不進入 LLM。

---

## 5. 實作階段規劃

### Phase 1：基礎建設（預估 2 人天）

| 任務 | 產出 |
|------|------|
| 建立專案目錄結構 | 所有 `__init__.py`、`requirements.txt`、`config.yaml` 範本 |
| 實作 `config/settings.py` | `Settings` dataclass + `load_settings()` |
| 撰寫 pytest 設定 | `pytest.ini`、`tests/conftest.py` |

### Phase 2：Log 解析與匯入（預估 3 人天）

| 任務 | 產出 | 對應需求 |
|------|------|---------|
| 實作 `ingestion/parser.py` | NLog 文字格式解析 + 多行合併 | REQ-001、REQ-004 |
| 實作 `ingestion/loader.py` | 目錄掃描、單檔讀取 | REQ-003 |
| 實作 `vectorstore/client.py` | ChromaDB 連線與 collection 初始化 | REQ-005 |
| 實作 `vectorstore/embedder.py` | OllamaEmbedder + Tenacity 重試 | REQ-005、NFR-006 |
| 實作 `vectorstore/store.py` | LogChunk upsert + SHA256 去重 | REQ-003、REQ-005 |
| 撰寫對應測試 | `test_parser.py`、`test_store.py` | — |

### Phase 3：RAG 查詢鏈（預估 2 人天）

| 任務 | 產出 | 對應需求 |
|------|------|---------|
| 實作 `retrieval/retriever.py` | similarity search + metadata filter | REQ-007 |
| 實作 `chain/prompt.py` | 繁中系統提示模板 | REQ-008 |
| 實作 `chain/rag_chain.py` | LCEL streaming chain + 無結果守衛 | REQ-008、NFR-006 |
| 撰寫對應測試 | `test_retriever.py`、`test_rag_chain.py` | — |

### Phase 4：CLI 介面（預估 1.5 人天）

| 任務 | 產出 | 對應需求 |
|------|------|---------|
| 實作 `cli/main.py`：`ingest` 指令 | 進度顯示、錯誤處理 | REQ-003、REQ-006 |
| 實作 `cli/main.py`：`query` 指令 | 互動模式 + 單次模式 + streaming | REQ-006、REQ-007、REQ-008 |
| 實作 `cli/main.py`：`status` 指令 | ChromaDB 統計 + Ollama 狀態 | — |
| 實作 `cli/main.py`：`clear` 指令 | 確認提示 + 清除 collection | — |

### Phase 5：整合測試與收尾（預估 1 人天）

| 任務 | 產出 |
|------|------|
| 端到端整合測試（使用真實 Ollama + ChromaDB） | `tests/test_e2e.py` |
| 撰寫 `README.md`（安裝、設定、使用說明） | `README.md` |
| 效能驗證（NFR-001、NFR-002） | 測試報告 |

**總預估**：9.5 人天

---

## 6. 關鍵風險與緩解

| 風險 | 可能性 | 影響 | 緩解策略 |
|------|--------|------|---------|
| Ollama `nomic-embed-text` 在不同機器嵌入維度不一致 | 低 | 高 | 初始化時驗證 collection embedding function，維度不符則警告並建議重建 |
| ChromaDB pre-retrieval filter 與 similarity search 聯合效能在大量 chunk 時下降 | 中 | 中 | 設定 `hnsw:space=cosine` 並預留 index 調整空間 |
| NLog 格式客製化導致正則不符 | 中 | 中 | Parser 提供 debug 模式輸出跳過行，方便使用者反饋格式差異 |
| LLM streaming 在 Typer 互動模式中 flush 不正常 | 低 | 低 | 強制 `print(token, end="", flush=True)`，測試多個終端機環境 |

---

## 7. 相依套件清單（requirements.txt 草稿）

```
langchain>=0.3.0
langchain-core>=0.3.0
langchain-ollama>=0.2.0
langchain-chroma>=0.1.0
chromadb>=0.5.0
typer>=0.12.0
tenacity>=8.2.0
pyyaml>=6.0.0
python-dotenv>=1.0.0
rich>=13.0.0        # CLI 進度條與格式化輸出

# Dev / Test
pytest>=8.0.0
pytest-mock>=3.12.0
```
