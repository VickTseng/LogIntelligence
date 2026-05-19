from unittest.mock import MagicMock, patch
from datetime import datetime
from logiq.ingestion.parser import LogEntry
from logiq.vectorstore.store import chunk_id, entries_to_chunks, upsert_chunks


def make_entry(msg: str = "Test message", level: str = "INFO") -> LogEntry:
    ts = datetime(2026, 5, 19, 14, 0, 1)
    e = LogEntry(
        timestamp=ts,
        timestamp_unix=int(ts.timestamp()),
        level=level,
        logger="TestLogger",
        message=msg,
        exception_lines=[],
        source_file="/logs/app.log",
    )
    e.raw_text = e.get_full_text()
    return e


def test_chunk_id_is_deterministic():
    cid1 = chunk_id("/logs/app.log", "hello world")
    cid2 = chunk_id("/logs/app.log", "hello world")
    assert cid1 == cid2


def test_chunk_id_differs_by_source():
    cid1 = chunk_id("/logs/a.log", "hello world")
    cid2 = chunk_id("/logs/b.log", "hello world")
    assert cid1 != cid2


def test_entries_to_chunks_produces_chunks():
    entry = make_entry("Short message")
    chunks = entries_to_chunks([entry], chunk_size=512, chunk_overlap=50)
    assert len(chunks) >= 1
    assert chunks[0].source_file_name == "app.log"
    assert chunks[0].level == "INFO"
    assert chunks[0].timestamp_unix == entry.timestamp_unix


def test_upsert_chunks_skips_duplicates():
    entry = make_entry("Duplicate test")
    chunks = entries_to_chunks([entry])

    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": [chunks[0].id]}

    mock_embedder = MagicMock()
    mock_embedder.embed_documents.return_value = [[0.1] * 768]

    added, skipped = upsert_chunks(mock_collection, chunks, mock_embedder)
    assert skipped == len(chunks)
    assert added == 0
    mock_collection.upsert.assert_not_called()


def test_upsert_chunks_adds_new():
    entry = make_entry("New entry")
    chunks = entries_to_chunks([entry])

    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}

    mock_embedder = MagicMock()
    mock_embedder.embed_documents.return_value = [[0.1] * 768] * len(chunks)

    added, skipped = upsert_chunks(mock_collection, chunks, mock_embedder)
    assert added == len(chunks)
    assert skipped == 0
    mock_collection.upsert.assert_called_once()
