from pathlib import Path
import tempfile
import pytest
from logiq.ingestion.parser import parse_text_file, LogEntry


def write_temp_log(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def test_parse_single_line_entry():
    log = "2026-05-19 14:00:01.123 [ERROR] OrderService - Payment failed\n"
    path = write_temp_log(log)
    entries = list(parse_text_file(path, merge_multiline=True))
    assert len(entries) == 1
    e = entries[0]
    assert e.level == "ERROR"
    assert e.logger == "OrderService"
    assert e.message == "Payment failed"
    assert e.timestamp_unix == int(e.timestamp.timestamp())


def test_parse_multiline_exception_merged(sample_log_text):
    path = write_temp_log(sample_log_text)
    entries = list(parse_text_file(path, merge_multiline=True))
    assert len(entries) == 2
    error_entry = entries[0]
    assert error_entry.level == "ERROR"
    assert len(error_entry.exception_lines) == 3
    assert "NullReferenceException" in error_entry.exception_lines[0]


def test_parse_multiline_exception_not_merged(sample_log_text):
    path = write_temp_log(sample_log_text)
    entries = list(parse_text_file(path, merge_multiline=False))
    assert len(entries) == 2
    error_entry = entries[0]
    assert error_entry.exception_lines == []


def test_unparseable_lines_are_skipped():
    log = (
        "this is not a valid log line\n"
        "2026-05-19 14:00:01 [INFO] App - Started\n"
    )
    path = write_temp_log(log)
    entries = list(parse_text_file(path, merge_multiline=False))
    assert len(entries) == 1
    assert entries[0].level == "INFO"


def test_get_full_text_includes_exception():
    log = (
        "2026-05-19 14:00:01 [ERROR] Svc - Boom\n"
        "  at Svc.Run() in Svc.cs:line 1\n"
    )
    path = write_temp_log(log)
    entries = list(parse_text_file(path, merge_multiline=True))
    full = entries[0].get_full_text()
    assert "Boom" in full
    assert "at Svc.Run()" in full
