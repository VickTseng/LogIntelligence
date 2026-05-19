from dataclasses import dataclass
from pathlib import Path
import os
import yaml
from dotenv import load_dotenv


@dataclass
class RetrySettings:
    max_attempts: int
    wait_seconds: int


@dataclass
class OllamaSettings:
    base_url: str
    llm_model: str
    embedding_model: str
    timeout_seconds: int
    retry: RetrySettings


@dataclass
class ChromaSettings:
    persist_path: Path
    collection_name: str


@dataclass
class RetrievalSettings:
    top_k: int


@dataclass
class ChunkingSettings:
    chunk_size: int
    chunk_overlap: int
    merge_multiline_exceptions: bool


@dataclass
class Settings:
    ollama: OllamaSettings
    chroma: ChromaSettings
    retrieval: RetrievalSettings
    chunking: ChunkingSettings


def load_settings(config_path: Path = Path("config.yaml")) -> Settings:
    load_dotenv()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    o = raw["ollama"]
    retry_cfg = o.get("retry", {})
    ollama = OllamaSettings(
        base_url=os.getenv("OLLAMA_BASE_URL", o["base_url"]),
        llm_model=os.getenv("OLLAMA_LLM_MODEL", o["llm_model"]),
        embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", o["embedding_model"]),
        timeout_seconds=int(os.getenv("OLLAMA_TIMEOUT", o.get("timeout_seconds", 30))),
        retry=RetrySettings(
            max_attempts=int(retry_cfg.get("max_attempts", 3)),
            wait_seconds=int(retry_cfg.get("wait_seconds", 2)),
        ),
    )

    c = raw["chromadb"]
    chroma = ChromaSettings(
        persist_path=Path(os.getenv("CHROMA_PERSIST_PATH", c["persist_path"])),
        collection_name=os.getenv("CHROMA_COLLECTION", c["collection_name"]),
    )

    retrieval = RetrievalSettings(
        top_k=int(os.getenv("RETRIEVAL_TOP_K", raw["retrieval"]["top_k"])),
    )

    ck = raw["chunking"]
    chunking = ChunkingSettings(
        chunk_size=ck["chunk_size"],
        chunk_overlap=ck["chunk_overlap"],
        merge_multiline_exceptions=ck["merge_multiline_exceptions"],
    )

    return Settings(
        ollama=ollama,
        chroma=chroma,
        retrieval=retrieval,
        chunking=chunking,
    )
