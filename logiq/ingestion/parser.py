from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

TIMESTAMP_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"\[(?P<level>\w+)\]\s+"
    r"(?P<log_logger>\S+)\s+-\s+"
    r"(?P<message>.+)$"
)

LEVEL_ALIASES = {"WARNING": "WARN", "CRITICAL": "FATAL"}


@dataclass
class LogEntry:
    timestamp: datetime
    timestamp_unix: int
    level: str
    logger: str
    message: str
    exception_lines: list[str]
    source_file: str
    raw_text: str = field(default="", repr=False)

    def get_full_text(self) -> str:
        parts = [f"{self.timestamp.isoformat()} [{self.level}] {self.logger} - {self.message}"]
        parts.extend(self.exception_lines)
        return "\n".join(parts)


def _normalize_level(level: str) -> str:
    upper = level.upper()
    return LEVEL_ALIASES.get(upper, upper)


def _parse_timestamp(ts_str: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str}")


def _flush_entry(
    ts_str: str,
    level: str,
    log_logger: str,
    message: str,
    exception_lines: list[str],
    source_file: str,
) -> LogEntry | None:
    try:
        ts = _parse_timestamp(ts_str)
    except ValueError as e:
        logger.warning("Timestamp parse error: %s", e)
        return None
    entry = LogEntry(
        timestamp=ts,
        timestamp_unix=int(ts.timestamp()),
        level=_normalize_level(level),
        logger=log_logger,
        message=message,
        exception_lines=list(exception_lines),
        source_file=source_file,
    )
    entry.raw_text = entry.get_full_text()
    return entry


def parse_text_file(
    path: Path,
    merge_multiline: bool = True,
) -> Generator[LogEntry, None, None]:
    skip_count = 0
    pending: dict | None = None

    def flush() -> LogEntry | None:
        if pending is None:
            return None
        return _flush_entry(**pending, source_file=str(path))

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            m = TIMESTAMP_RE.match(line)
            if m:
                if pending is not None:
                    entry = flush()
                    if entry:
                        yield entry
                pending = {
                    "ts_str": m.group("timestamp"),
                    "level": m.group("level"),
                    "log_logger": m.group("log_logger"),
                    "message": m.group("message"),
                    "exception_lines": [],
                }
            else:
                if pending is not None and merge_multiline:
                    pending["exception_lines"].append(line)
                elif pending is not None and not merge_multiline:
                    entry = flush()
                    if entry:
                        yield entry
                    pending = None
                    skip_count += 1
                else:
                    skip_count += 1

    if pending is not None:
        entry = flush()
        if entry:
            yield entry

    if skip_count:
        logger.warning("Skipped %d unparseable lines in %s", skip_count, path)
