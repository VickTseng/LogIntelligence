from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

_SYSTEM_TEMPLATE = """\
你是一個專業的系統日誌分析助理。
你的回答必須完全基於以下提供的日誌記錄，不可自行推測或編造。
若日誌記錄中沒有足夠的資訊回答問題，請明確告知「根據目前日誌，無法確定...」。

=== 相關日誌記錄 ===
{context}
===================
"""

_HUMAN_TEMPLATE = "使用者問題：{question}\n\n請以繁體中文回答："

RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM_TEMPLATE),
        ("human", _HUMAN_TEMPLATE),
    ]
)

NO_RESULTS_MESSAGE = "根據目前已匯入的日誌，找不到與您問題相關的記錄。\n建議確認已匯入相關時間範圍的日誌（使用 logiq status），或嘗試不同的關鍵字。"


def format_docs(docs: list[Document]) -> str:
    if not docs:
        return "[無相關日誌記錄]"
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        header = (
            f"[{i}] 來源: {meta.get('source_file_name', '?')} | "
            f"時間: {meta.get('timestamp_iso', '?')} | "
            f"Level: {meta.get('level', '?')}"
        )
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n".join(parts)
