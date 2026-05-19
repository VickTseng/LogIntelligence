# LogIntelligence 專案憲章

> 版本：v1.0 | 建立日期：2026-05-19

---

## 1. 專案願景

打造一套以 RAG（Retrieval-Augmented Generation）為核心的 Log 智慧分析系統，讓開發者與維運人員能以自然語言查詢 NLog 日誌，獲得精準、有脈絡的回答，取代人工翻閱大量 Log 的低效作業。

---

## 2. 核心價值原則

1. **RAG-First**：所有 LLM 回應必須以檢索到的 Log 內容為依據，禁止純粹靠模型推測回答。
2. **本地優先**：LLM（Ollama）與向量資料庫（ChromaDB）均在本機執行，不依賴外部雲端 API，保護日誌隱私。
3. **可觀測性**：每次查詢應能追溯使用了哪些 Log 片段作為 context，確保回答可驗證。
4. **模組化設計**：Log 收集、向量化、檢索、LLM 回應各為獨立模組，可個別替換或擴充。

---

## 3. 技術選型決策

| 決策 ID | 技術面向 | 選擇 | 理由 |
|---------|---------|------|------|
| ADR-001 | 程式語言 | Python 3.11+ | LangChain、ChromaDB、Ollama SDK 生態最成熟 |
| ADR-002 | RAG 框架 | LangChain | 提供完整的 Document Loader、Text Splitter、Retriever、Chain 抽象 |
| ADR-003 | LLM Runtime | Ollama | 本地執行開源模型，零雲端依賴，支援多模型切換 |
| ADR-004 | 向量資料庫 | ChromaDB | 輕量、嵌入式部署，適合單機開發與中小規模日誌量 |
| ADR-005 | Embedding Model | nomic-embed-text（via Ollama） | 與 LLM 同源，維持本地化原則 |
| ADR-006 | Log 來源格式 | NLog 結構化輸出（JSON / 純文字） | 匹配現有 .NET 專案日誌輸出 |

---

## 4. 架構風格

```
NLog 日誌檔案
     │
     ▼
[Log Ingestion Module]   ← 解析、清洗 NLog 格式
     │
     ▼
[Chunking & Embedding]   ← LangChain Text Splitter + Ollama Embedding
     │
     ▼
[ChromaDB]               ← 向量儲存與持久化
     │
     ▼  ← 使用者提問
[Retriever]              ← similarity search
     │
     ▼
[RAG Chain]              ← LangChain RetrievalQA / LCEL
     │
     ▼
[Ollama LLM]             ← 本地推論
     │
     ▼
  回應給使用者
```

---

## 5. 開發規範

### 5.1 程式碼規範
- 使用 `uv` 或 `pip` 管理相依套件，鎖定版本於 `requirements.txt`
- 模組目錄結構：
  ```
  logIntelligence/
  ├── ingestion/      # Log 解析與載入
  ├── vectorstore/    # ChromaDB 初始化、新增、查詢
  ├── retrieval/      # LangChain Retriever 封裝
  ├── chain/          # RAG Chain 組裝
  ├── cli/            # 使用者介面（CLI 優先）
  └── config/         # 設定檔（Ollama model、ChromaDB path 等）
  ```
- 每個模組有對應的單元測試（pytest）

### 5.2 設定管理
- 敏感設定（模型名稱、資料路徑）透過 `.env` 或 `config.yaml` 管理，不寫死於程式碼

### 5.3 版本控制
- 功能分支命名：`feature/TASK-XXX-description`
- Commit 訊息格式：`[TASK-XXX] 動詞 + 說明`

---

## 6. 不做清單（Out of Scope）

- 不實作雲端部署或容器化（Docker）— 初版以本機執行為主
- 不實作 Web UI — 初版以 CLI 為主，後續可擴充
- 不支援 NLog 以外的日誌格式 — 初版聚焦單一格式
- 不實作使用者帳號或權限管理

---

## 7. 成功指標

| 指標 | 目標值 |
|------|--------|
| 查詢回應時間 | < 10 秒（本機，含 LLM 推論） |
| 檢索準確率（人工評估） | > 80%（回答內容與日誌實際記錄相符） |
| Log 匯入吞吐量 | 支援單次匯入 10,000 行以上 |
