# LogIntelligence CLI 介面合約

> 版本：v1.0 | 建立日期：2026-05-19
> CLI 工具名稱：`logiq`

---

## 指令總覽

```
logiq [OPTIONS] COMMAND [ARGS]...

Commands:
  ingest   將 NLog 日誌檔案匯入向量知識庫
  query    以自然語言查詢日誌知識庫
  status   顯示知識庫統計資訊
  clear    清除向量知識庫
```

---

## `logiq ingest`

### 用途
解析 NLog 日誌檔案，向量化後存入 ChromaDB。

### 語法
```
logiq ingest PATH [OPTIONS]
```

### 參數

| 參數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `PATH` | `str` (必填) | 日誌檔案路徑或目錄路徑 | — |
| `--recursive` / `--no-recursive` | `bool` | 若 PATH 為目錄，是否遞迴掃描子目錄 | `True` |
| `--format` | `choice: text\|json\|auto` | NLog 格式（auto 自動偵測） | `auto` |
| `--config` | `Path` | 指定 config.yaml 路徑 | `./config.yaml` |

### 輸出格式
```
[logiq] 正在匯入: ./logs/app-2026-05-19.log
[logiq] 解析中... 1,234 / 5,678 行 (21.7%)
[logiq] 向量化中... 42 / 198 chunks
[logiq] ✅ 匯入完成
        - 解析行數: 5,678
        - 成功 chunks: 195
        - 跳過（解析失敗）: 3 行
        - 重複（已存在）: 12 chunks
        - 新增至知識庫: 183 chunks
```

### 錯誤行為
| 情境 | 行為 |
|------|------|
| PATH 不存在 | 立即失敗，顯示路徑錯誤訊息，exit code 1 |
| 解析失敗的行 | 警告並跳過，繼續處理；完成後報告跳過數量 |
| Ollama embedding 服務不可用 | 重試 3 次後失敗，exit code 2 |
| ChromaDB 寫入失敗 | 顯示錯誤並終止，exit code 3 |

---

## `logiq query`

### 用途
以自然語言提問，透過 RAG 流程從日誌知識庫生成回答。

### 語法
```
logiq query [OPTIONS]
logiq query --question "問題"  # 單次模式
```

### 參數

| 參數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `--question` / `-q` | `str` | 問題（省略則進入互動模式） | `None` |
| `--from` | `datetime` | 時間範圍起點（ISO 8601 或 `YYYY-MM-DD HH:mm`） | `None` |
| `--to` | `datetime` | 時間範圍終點 | `None` |
| `--top-k` | `int` | 檢索 chunk 數量 | 設定檔值（預設 5） |
| `--show-sources` / `--no-sources` | `bool` | 是否顯示來源 Log 片段 | `True` |
| `--config` | `Path` | 指定 config.yaml 路徑 | `./config.yaml` |

### 輸出格式（streaming 模式）

```
[logiq] 檢索中... 找到 5 個相關片段

─────────────────────────────────────────────
根據日誌記錄，OrderService 在 14:02:31 拋出了 NullReferenceException...
（LLM 回應逐字串流輸出）
─────────────────────────────────────────────

來源日誌：
  [1] app-2026-05-19.log | 2026-05-19 14:02:31 | ERROR | 相似度: 0.92
  [2] app-2026-05-19.log | 2026-05-19 14:02:28 | WARN  | 相似度: 0.81
  [3] worker-2026-05-19.log | 2026-05-19 14:02:30 | ERROR | 相似度: 0.79
```

### 互動模式
```
[logiq] 進入互動模式。輸入問題後按 Enter，輸入 'exit' 離開。

> 今天有哪些 ERROR？
...（串流回應）...

> exit
[logiq] 結束查詢。
```

### 無結果回應
```
[logiq] 未找到與您問題相關的日誌記錄。
        建議：
        - 確認已匯入相關時間範圍的日誌（使用 logiq status）
        - 嘗試更改關鍵字或放寬時間範圍
```

### 錯誤行為
| 情境 | 行為 |
|------|------|
| Ollama LLM 不可用 | 重試 3 次（每次 2 秒），失敗後顯示錯誤並建議 `ollama serve`，exit code 2 |
| ChromaDB 不存在或為空 | 顯示提示訊息並建議先執行 `logiq ingest`，exit code 4 |
| `--from` > `--to` | 立即失敗，顯示時間範圍錯誤，exit code 1 |

---

## `logiq status`

### 用途
顯示目前知識庫的統計資訊。

### 語法
```
logiq status [OPTIONS]
```

### 輸出格式
```
[logiq] 知識庫狀態
────────────────────────────────
ChromaDB 路徑:  ./data/chroma
Collection:     log_intelligence
總 chunk 數:    12,345
來源檔案數:     8
最早記錄:       2026-05-01 00:00:01
最新記錄:       2026-05-19 23:59:58
────────────────────────────────
Ollama 狀態:    ✅ 連線正常 (http://localhost:11434)
LLM 模型:       llama3.2
Embedding 模型: nomic-embed-text
```

---

## `logiq clear`

### 用途
清除 ChromaDB 中的所有向量資料。

### 語法
```
logiq clear [OPTIONS]
```

### 參數

| 參數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `--confirm` | `bool` | 跳過確認提示（供腳本使用） | `False` |

### 互動確認
```
[logiq] ⚠️  即將清除知識庫中的 12,345 個 chunks。此操作無法復原。
確認清除？ [y/N]: y
[logiq] ✅ 知識庫已清除。
```

---

## Exit Codes

| Code | 意義 |
|------|------|
| 0 | 成功 |
| 1 | 輸入參數錯誤 |
| 2 | Ollama 服務不可用（重試耗盡） |
| 3 | ChromaDB 寫入失敗 |
| 4 | ChromaDB 為空或未初始化 |
