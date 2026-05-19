import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from langchain_ollama import OllamaEmbeddings
from logiq.config.settings import OllamaSettings


class OllamaEmbedder:
    def __init__(self, settings: OllamaSettings) -> None:
        self._settings = settings
        self._embeddings = OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.base_url,
        )

    def _retry_decorator(self):
        s = self._settings.retry
        return retry(
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            stop=stop_after_attempt(s.max_attempts),
            wait=wait_exponential(multiplier=s.wait_seconds, min=s.wait_seconds, max=s.wait_seconds * 4),
            reraise=True,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        @self._retry_decorator()
        def _call():
            return self._embeddings.embed_documents(texts)
        return _call()

    def embed_query(self, text: str) -> list[float]:
        @self._retry_decorator()
        def _call():
            return self._embeddings.embed_query(text)
        return _call()
