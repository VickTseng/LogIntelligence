from pathlib import Path
from typing import Generator
from logiq.config.settings import ChunkingSettings
from logiq.ingestion.parser import LogEntry, parse_text_file


def scan_files(path: Path, recursive: bool = True) -> list[Path]:
    path = Path(path)
    if path.is_file():
        return [path]
    pattern = "**/*.log" if recursive else "*.log"
    return sorted(path.glob(pattern))


def load_entries(
    paths: list[Path],
    chunking_settings: ChunkingSettings,
) -> Generator[LogEntry, None, None]:
    for file_path in paths:
        yield from parse_text_file(
            file_path,
            merge_multiline=chunking_settings.merge_multiline_exceptions,
        )
