from pathlib import Path
import chromadb
from chromadb import Collection
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from logiq.config.settings import ChromaSettings, OllamaSettings


def get_chroma_client(chroma_settings: ChromaSettings) -> chromadb.PersistentClient:
    persist_path = Path(chroma_settings.persist_path)
    persist_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_path))


def get_or_create_collection(
    client: chromadb.PersistentClient,
    chroma_settings: ChromaSettings,
    ollama_settings: OllamaSettings,
) -> Collection:
    embedding_fn = OllamaEmbeddingFunction(
        url=f"{ollama_settings.base_url}/api/embeddings",
        model_name=ollama_settings.embedding_model,
    )
    return client.get_or_create_collection(
        name=chroma_settings.collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
