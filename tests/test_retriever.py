from datetime import datetime
import pytest
from logiq.retrieval.retriever import build_where_filter


def test_build_where_filter_none_returns_none():
    result = build_where_filter(None, None)
    assert result is None


def test_build_where_filter_from_only():
    from_dt = datetime(2026, 5, 19, 14, 0, 0)
    result = build_where_filter(from_dt=from_dt, to_dt=None)
    assert result is not None
    assert "timestamp_unix" in result
    assert result["timestamp_unix"] == {"$gte": int(from_dt.timestamp())}


def test_build_where_filter_to_only():
    to_dt = datetime(2026, 5, 19, 15, 0, 0)
    result = build_where_filter(from_dt=None, to_dt=to_dt)
    assert result is not None
    assert result["timestamp_unix"] == {"$lte": int(to_dt.timestamp())}


def test_build_where_filter_both_uses_and():
    from_dt = datetime(2026, 5, 19, 14, 0, 0)
    to_dt = datetime(2026, 5, 19, 15, 0, 0)
    result = build_where_filter(from_dt=from_dt, to_dt=to_dt)
    assert result is not None
    assert "$and" in result
    conditions = result["$and"]
    assert len(conditions) == 2
    assert any("$gte" in str(c) for c in conditions)
    assert any("$lte" in str(c) for c in conditions)
