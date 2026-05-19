from __future__ import annotations
from typing import Generator
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from langchain_ollama import ChatOllama
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from logiq.config.settings import Settings
from logiq.chain.prompt import RAG_PROMPT, NO_RESULTS_MESSAGE, format_docs


def build_chain(settings: Settings):
    llm = ChatOllama(
        model=settings.ollama.llm_model,
        base_url=settings.ollama.base_url,
        streaming=True,
    )
    chain = (
        {"context": RunnablePassthrough(), "question": RunnablePassthrough()}
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )
    return chain


def stream_answer(
    settings: Settings,
    question: str,
    docs: list[Document],
) -> Generator[str, None, None]:
    if not docs:
        yield NO_RESULTS_MESSAGE
        return

    context = format_docs(docs)
    llm = ChatOllama(
        model=settings.ollama.llm_model,
        base_url=settings.ollama.base_url,
        streaming=True,
    )
    chain = RAG_PROMPT | llm | StrOutputParser()

    s = settings.ollama.retry

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException, ConnectionError)),
        stop=stop_after_attempt(s.max_attempts),
        wait=wait_exponential(multiplier=s.wait_seconds, min=s.wait_seconds, max=s.wait_seconds * 4),
        reraise=True,
    )
    def _stream():
        return chain.stream({"context": context, "question": question})

    for token in _stream():
        yield token
