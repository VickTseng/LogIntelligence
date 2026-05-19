from unittest.mock import MagicMock, patch
import pytest
import httpx
from langchain_core.documents import Document
from logiq.chain.prompt import format_docs, NO_RESULTS_MESSAGE
from logiq.chain.rag_chain import stream_answer


def make_doc(content: str = "Log message", **meta) -> Document:
    default_meta = {
        "source_file_name": "app.log",
        "timestamp_iso": "2026-05-19T14:00:01",
        "level": "ERROR",
        "score": 0.92,
    }
    return Document(page_content=content, metadata={**default_meta, **meta})


def test_format_docs_empty_returns_placeholder():
    result = format_docs([])
    assert result == "[無相關日誌記錄]"


def test_format_docs_includes_metadata_header():
    doc = make_doc("Payment failed", source_file_name="api.log", level="ERROR")
    result = format_docs([doc])
    assert "來源: api.log" in result
    assert "Level: ERROR" in result
    assert "Payment failed" in result


def test_format_docs_multiple_docs_numbered():
    docs = [make_doc(f"msg {i}") for i in range(3)]
    result = format_docs(docs)
    assert "[1]" in result
    assert "[2]" in result
    assert "[3]" in result


def test_stream_answer_no_docs_yields_rejection():
    settings = MagicMock()
    tokens = list(stream_answer(settings, "任何問題", []))
    assert len(tokens) == 1
    assert NO_RESULTS_MESSAGE in tokens[0]


def test_stream_answer_with_docs_calls_llm(mocker):
    settings = MagicMock()
    settings.ollama.llm_model = "llama3.2"
    settings.ollama.base_url = "http://localhost:11434"
    settings.ollama.retry.max_attempts = 3
    settings.ollama.retry.wait_seconds = 2

    mock_chain = MagicMock()
    mock_chain.stream.return_value = iter(["這是", "回應"])
    mocker.patch("logiq.chain.rag_chain.RAG_PROMPT.__or__", return_value=mock_chain)
    mocker.patch("logiq.chain.rag_chain.ChatOllama", return_value=MagicMock())

    docs = [make_doc("Payment failed")]
    tokens = list(stream_answer(settings, "發生了什麼？", docs))
    assert len(tokens) > 0
