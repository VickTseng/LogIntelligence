# LogIntelligence 任務清單

> 版本：v1.0 | 建立日期：2026-05-19
> 前置文件：[plan.md](plan.md) | [spec.md](spec.md)
> 總任務數：30 | 預估工時：9.5 人天

---

## 使用者故事對應

| 故事 | 標題 | 優先級 | 核心需求 |
|------|------|--------|---------|
| US-001 | 匯入今天的 Log 並開始查詢 | P0 | REQ-001、REQ-003、REQ-004、REQ-005、REQ-006、REQ-007、REQ-008 |
| US-002 | 追查特定錯誤的原因 | P0 | REQ-001（多行合併）、REQ-007（來源評分）、REQ-008（串流 + 來源標示）|
| US-003 | 了解系統在特定時間的行為 | P1 | REQ-007（時間過濾）、REQ-006（--from/--to）|

---

## Phase 1：專案初始化（Setup）

> 目標：建立可執行的空白專案骨架，確保環境可運行

- [x] T001 建立完整目錄結構：`logiq/ingestion/`、`logiq/vectorstore/`、`logiq/retrieval/`、`logiq/chain/`、`logiq/cli/`、`logiq/config/`、`tests/`，含所有 `__init__.py`
- [x] T002 建立 `requirements.txt`，版本依 research.md 鎖定（langchain>=0.3、langchain-ollama>=0.2、langchain-chroma>=0.1、chromadb>=0.5、typer>=0.12、tenacity>=8.2、pyyaml>=6.0、python-dotenv>=1.0、rich>=13.0）
- [x] T003 [P] 建立 `config.yaml` 範本，包含 ollama.base_url、ollama.llm_model、ollama.embedding_model、ollama.retry、chromadb.persist_path、retrieval.top_k、chunking 所有欄位，依 data-model.md § 3 的 Schema
- [x] T004 [P] 建立 `pytest.ini`（testpaths=tests）與 `tests/conftest.py`（含 `settings` fixture，載入 test config）
- [x] T005 實作 `logiq/config/settings.py`：`OllamaSettings`、`ChromaSettings`、`RetrievalSettings`、`ChunkingSettings`、`Settings` dataclass，以及 `load_settings(config_path)` 函式，支援 `.env` 覆寫

---

## Phase 2：基礎模組（Foundational — 所有 US 的前置條件）

> 目標：ChromaDB 連線與 Ollama Embedding 可用，所有 US 都依賴此基礎

- [x] T006 實作 `logiq/vectorstore/client.py`：`get_chroma_client(settings)` 回傳 `PersistentClient`，`get_or_create_collection(client, name)` 確保 Collection `log_intelligence` 存在，embedding function 使用 `OllamaEmbeddingFunction`
- [x] T007 實作 `logiq/vectorstore/embedder.py`：`OllamaEmbedder` 類別，封裝 `OllamaEmbeddings`，`embed_documents(texts)` 與 `embed_query(text)` 方法均以 `@retry(retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)), stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=10))` 裝飾

---

## Phase 3：US-001 — 匯入日誌並進行基礎查詢

> 故事目標：`logiq ingest <file>` → `logiq query` → 獲得基於 Log 的回答
> 獨立驗收條件：執行 ingest 後，可在 ChromaDB 查到 chunks；執行 query 可獲得 LLM streaming 回應並附來源

### 3.1 Log 解析與向量化

- [x] T008 [US1] 實作 `logiq/ingestion/parser.py`：
  - `LogEntry` dataclass（欄位依 data-model.md § 1.1）
  - `TIMESTAMP_RE` 正則（依 data-model.md § 4）
  - `parse_text_file(path, merge_multiline)` → `Generator[LogEntry, None, None]`
  - 多行合併邏輯：以 `is_new_entry()` 判斷行首，延續行依 `merge_multiline` 設定決定合併或獨立
  - 解析失敗行：記錄警告並跳過，不中斷

- [x] T009 [P] [US1] 實作 `logiq/ingestion/loader.py`：
  - `scan_files(path, recursive)` → `list[Path]`（遞迴掃描 `.log` 檔）
  - `load_entries(paths, settings)` → `Generator[LogEntry, None, None]`（呼叫 parser）

- [x] T010 [US1] 實作 `logiq/vectorstore/store.py`：
  - `LogChunk` dataclass（欄位依 data-model.md § 1.2）
  - `entries_to_chunks(entries, chunk_size, chunk_overlap)` 使用 `RecursiveCharacterTextSplitter`
  - `chunk_id(source_file, text)` → SHA256 hex string（依 research.md § 6）
  - `upsert_chunks(collection, chunks, embedder)` 批次 upsert，回傳 `(added, skipped)` tuple

- [x] T011 [P] [US1] 撰寫 `tests/test_parser.py`：
  - 測試標準格式單行解析正確性
  - 測試多行 exception 合併（`merge_multiline=True`）
  - 測試不符格式的行被跳過並計數

- [x] T012 [P] [US1] 撰寫 `tests/test_store.py`：
  - 測試 `chunk_id` 對相同輸入產生相同 hash
  - 測試 `upsert_chunks` 重複匯入不產生重複（mock ChromaDB）

### 3.2 RAG 查詢鏈

- [x] T013 [US1] 實作 `logiq/retrieval/retriever.py`：
  - `LogRetriever` 類別
  - `retrieve(question, top_k, where_filter)` → `list[Document]`（LangChain Document，metadata 完整保留）
  - 無結果時回傳空列表（不拋異常）

- [x] T014 [US1] 實作 `logiq/chain/prompt.py`：
  - `RAG_PROMPT` = `ChatPromptTemplate`，system 角色說明（依 plan.md § 4.5 模板），含 `{context}` 與 `{question}` 變數
  - `format_docs(docs)` → str（將 Document list 轉為 context 字串，含 metadata prefix）
  - 空 docs 返回固定字串 `"[無相關日誌記錄]"`

- [x] T015 [US1] 實作 `logiq/chain/rag_chain.py`：
  - `build_chain(settings)` → LCEL chain（`ChatOllama(streaming=True)` + `StrOutputParser()`）
  - `stream_answer(chain, question, docs)` → `Generator[str, None, None]`
  - 無結果守衛：若 docs 為空，直接 yield 固定拒絕訊息，不進入 LLM
  - Ollama 連線失敗以 Tenacity 重試（依 NFR-006：3 次、每次 2 秒）

### 3.3 CLI 基礎指令

- [x] T016 [US1] 實作 `logiq/cli/main.py`：Typer app 骨架 + `ingest` 指令
  - 參數：`PATH`（必填）、`--recursive`（預設 True）、`--format`（auto/text/json）、`--config`
  - 使用 `rich.progress` 顯示解析與向量化進度
  - 完成後輸出摘要（解析行數、成功 chunks、跳過行、重複 chunks、新增 chunks）
  - 依 contracts/cli-schema.md 的錯誤行為與 exit code

- [x] T017 [US1] 在 `logiq/cli/main.py` 新增 `query` 指令（基礎版，不含時間過濾）
  - 參數：`--question/-q`、`--top-k`、`--show-sources`、`--config`
  - 互動模式（無 `-q`）：持續接受輸入直到 `exit`
  - streaming 輸出：逐 token print（`end=""`, `flush=True`）
  - 串流結束後輸出 SourceRef 列表（檔名、時間戳、Level、分數）

- [x] T018 [US1] 在 `logiq/cli/main.py` 新增 `status` 指令
  - 顯示：ChromaDB 路徑、Collection 名稱、總 chunk 數、來源檔案數、最早/最新記錄時間戳
  - 顯示 Ollama 連線狀態（✅ / ❌）、LLM model、Embedding model

---

## Phase 4：US-002 — 追查特定錯誤的原因

> 故事目標：輸入錯誤關鍵字 → 取得含完整 stack trace 的 Log 片段與 LLM 分析
> 獨立驗收條件：查詢包含 exception 關鍵字的問題，回應中的來源 chunk 包含完整 stack trace

- [x] T019 [US2] 強化 `logiq/ingestion/parser.py`：新增 `get_full_text(entry)` 將 message + exception_lines 合併為單一字串，確保 stack trace 完整進入 chunk text，加入整合測試案例驗證多行 exception 可被正確檢索

- [x] T020 [P] [US2] 強化 `logiq/chain/prompt.py`：在 `format_docs` 中為每個 Document 加入 metadata header（`[來源: {source_file_name} | 時間: {timestamp_iso} | Level: {level}]`），讓 LLM 能在回應中參照具體時間與來源

- [x] T021 [P] [US2] 強化 `logiq/cli/main.py` query 指令的 SourceRef 輸出格式：依 contracts/cli-schema.md 格式輸出帶序號的來源列表，包含相似度分數（保留 2 位小數）

- [x] T022 [US2] 撰寫 `tests/test_rag_chain.py`：
  - 測試 `stream_answer` 在 docs 為空時直接返回拒絕訊息（mock LLM）
  - 測試 `format_docs` 包含 metadata header
  - 測試 Tenacity 重試邏輯（mock httpx.ConnectError，確認重試 3 次後拋出）

---

## Phase 5：US-003 — 依時間範圍查詢

> 故事目標：`logiq query --from "2026-05-19 14:00" --to "2026-05-19 14:30"` 僅檢索對應時間範圍的 Log
> 獨立驗收條件：指定時間範圍後，回應的來源 chunks 時間戳皆在範圍內

- [x] T023 [US3] 強化 `logiq/retrieval/retriever.py`：
  - 實作 `build_where_filter(from_ts, to_ts)` → `dict | None`（依 research.md § 5 的 `$and`/`$gte`/`$lte` 語法）
  - `retrieve()` 方法接受 `from_dt` / `to_dt`（`datetime | None`），內部轉為 Unix timestamp 後傳入 `build_where_filter`

- [x] T024 [US3] 強化 `logiq/cli/main.py` query 指令：新增 `--from` / `--to` 參數（型別 `Optional[datetime]`，Typer 自動解析 ISO 8601），傳入 `retrieve()` 呼叫；若 `--from` > `--to` 則顯示錯誤並以 exit code 1 終止

- [x] T025 [P] [US3] 撰寫 `tests/test_retriever.py`：
  - 測試 `build_where_filter(None, None)` 返回 None
  - 測試 `build_where_filter(from_ts, None)` 只包含 `$gte`
  - 測試 `build_where_filter(from_ts, to_ts)` 包含 `$and` 雙條件

- [x] T026 [US3] 在 `logiq/vectorstore/store.py` 的 `entries_to_chunks()` 確認 `timestamp_unix`（int）與 `timestamp_iso`（ISO str）正確寫入每個 chunk 的 metadata，補充對應的單元測試到 `tests/test_store.py`

---

## Phase 6：收尾與品質提升（Polish）

> 目標：完整 CLI、端到端驗證、效能確認、文件

- [x] T027 在 `logiq/cli/main.py` 新增 `clear` 指令：互動確認（`--confirm` 可跳過），顯示將清除的 chunk 數，執行 `collection.delete()` 後顯示成功訊息；依 contracts/cli-schema.md exit code 規格
- [x] T028 [P] 建立 `pyproject.toml` 或更新 `requirements.txt` 設定 CLI entry point：`logiq = "logiq.cli.main:app"`，確認 `pip install -e .` 後可直接執行 `logiq` 指令
- [ ] T029 撰寫 `tests/test_e2e.py` 端到端整合測試（需本機 Ollama + ChromaDB）：
  - 測試 ingest 小型 NLog 範本檔 → query → 回應包含預期關鍵字
  - 測試時間範圍過濾正確縮小結果集
  - 測試 Ollama 不可用時重試後顯示正確錯誤訊息
- [x] T030 [P] 建立 `README.md`：安裝步驟（pip install、ollama pull nomic-embed-text、ollama pull llama3.2）、config.yaml 設定說明、`logiq ingest` / `logiq query` 快速上手範例，對應 US-001 / US-002 / US-003 操作情境

---

## 相依關係圖

```
T001 → T002 → T003
     ↘ T004
     ↘ T005 → T006 → T008 → T009 → T010 → T016 (US-001 ingest)
              ↘ T007 ↗                  ↘ T013 → T014 → T015 → T017 (US-001 query)
                                                              ↘ T018 (status)
                                    T019 (US-002 parser 強化)
                                    T020 → T021 → T022 (US-002 RAG 強化)
              T023 → T024 → T025 → T026 (US-003 時間過濾)
              T027 → T028 → T029 → T030 (收尾)
```

**可並行執行的任務組**（標示 `[P]`）：
- T003、T004 可與 T005 並行（不同檔案）
- T009、T011、T012 可與 T008 完成後並行
- T020、T021、T025、T028、T030 可並行（不同模組）

---

## MVP 範圍建議

最小可驗收版本（MVP）= **Phase 1 + Phase 2 + Phase 3**（T001–T018）

完成後即可：
1. `logiq ingest ./logs/app.log`
2. `logiq query -q "今天有哪些 ERROR？"`
3. 獲得 streaming 回應並附來源 Log 時間戳

Phase 4、5、6 為漸進式增強，可在 MVP 驗收後繼續實作。
