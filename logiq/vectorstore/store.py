from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass
from chromadb import Collection
from langchain_text_splitters import RecursiveCharacterTextSplitter
from logiq.ingestion.parser import LogEntry
from logiq.vectorstore.embedder import OllamaEmbedder

logger = logging.getLogger(__name__)


@dataclass
class LogChunk:
    id: str
    text: str
    source_file: str
    source_file_name: str
    timestamp_unix: int
    timestamp_iso: str
    level: str
    logger: str
    chunk_index: int


def chunk_id(source_file: str, text: str) -> str:
    return hashlib.sha256(f"{source_file}::{text}".encode()).hexdigest()


def entries_to_chunks(
    entries: list[LogEntry],
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[LogChunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    chunks: list[LogChunk] = []
    for entry in entries:
        full_text = entry.get_full_text()
        texts = splitter.split_text(full_text)
        for idx, text in enumerate(texts):
            chunks.append(
                LogChunk(
                    id=chunk_id(entry.source_file, text),
                    text=text,
                    source_file=entry.source_file,
                    source_file_name=entry.source_file.split("/")[-1],
                    timestamp_unix=entry.timestamp_unix,
                    timestamp_iso=entry.timestamp.isoformat(),
                    level=entry.level,
                    logger=entry.logger,
                    chunk_index=idx,
                )
            )
    return chunks


def upsert_chunks(
    collection: Collection,
    chunks: list[LogChunk],
    embedder: OllamaEmbedder,
    batch_size: int = 50,
) -> tuple[int, int]:
    if not chunks:
        return 0, 0

    existing_ids: set[str] = set()
    all_ids = [c.id for c in chunks]
    try:
        existing = collection.get(ids=all_ids, include=[])
        existing_ids = set(existing["ids"])
    except Exception:
        pass

    new_chunks = [c for c in chunks if c.id not in existing_ids]
    skipped = len(chunks) - len(new_chunks)

    for i in range(0, len(new_chunks), batch_size):
        batch = new_chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        embeddings = embedder.embed_documents(texts)
        collection.upsert(
            ids=[c.id for c in batch],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "source_file": c.source_file,
                    "source_file_name": c.source_file_name,
                    "timestamp_unix": c.timestamp_unix,
                    "timestamp_iso": c.timestamp_iso,
                    "level": c.level,
                    "logger": c.logger,
                    "chunk_index": c.chunk_index,
                }
                for c in batch
            ],
        )
        logger.info("Upserted batch %d/%d", i + len(batch), len(new_chunks))

    return len(new_chunks), skipped
