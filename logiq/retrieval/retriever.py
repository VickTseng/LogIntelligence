from __future__ import annotations
from datetime import datetime
from chromadb import Collection
from langchain_core.documents import Document
from logiq.vectorstore.embedder import OllamaEmbedder


def build_where_filter(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> dict | None:
    conditions = []
    if from_dt is not None:
        conditions.append({"timestamp_unix": {"$gte": int(from_dt.timestamp())}})
    if to_dt is not None:
        conditions.append({"timestamp_unix": {"$lte": int(to_dt.timestamp())}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class LogRetriever:
    def __init__(self, collection: Collection, embedder: OllamaEmbedder) -> None:
        self._collection = collection
        self._embedder = embedder

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[Document]:
        query_embedding = self._embedder.embed_query(question)
        where = build_where_filter(from_dt, to_dt)

        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = self._collection.query(**kwargs)
        except Exception:
            return []

        documents: list[Document] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            score = max(0.0, 1.0 - dist)
            documents.append(
                Document(
                    page_content=doc,
                    metadata={**meta, "score": round(score, 4)},
                )
            )
        return documents
