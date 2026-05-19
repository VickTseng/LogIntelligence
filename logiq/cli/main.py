from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from logiq.config.settings import load_settings
from logiq.ingestion.loader import scan_files, load_entries
from logiq.vectorstore.client import get_chroma_client, get_or_create_collection
from logiq.vectorstore.embedder import OllamaEmbedder
from logiq.vectorstore.store import entries_to_chunks, upsert_chunks
from logiq.retrieval.retriever import LogRetriever
from logiq.chain.rag_chain import stream_answer

app = typer.Typer(name="logiq", help="LogIntelligence — NLog 智慧問答系統")
console = Console()
err_console = Console(stderr=True)

DEFAULT_CONFIG = Path("config.yaml")


def _load_cfg(config: Path):
    if not config.exists():
        err_console.print(f"[red]找不到設定檔：{config}[/red]")
        raise typer.Exit(1)
    return load_settings(config)


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="日誌檔案路徑或目錄路徑"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="目錄時是否遞迴掃描"),
    fmt: str = typer.Option("auto", "--format", help="NLog 格式：auto / text / json"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="設定檔路徑"),
):
    """將 NLog 日誌檔案匯入向量知識庫。"""
    settings = _load_cfg(config)

    if not path.exists():
        err_console.print(f"[red]路徑不存在：{path}[/red]")
        raise typer.Exit(1)

    files = scan_files(path, recursive=recursive)
    if not files:
        err_console.print("[yellow]未找到任何 .log 檔案。[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]正在匯入[/bold] {len(files)} 個檔案...")

    try:
        client = get_chroma_client(settings.chroma)
        collection = get_or_create_collection(client, settings.chroma, settings.ollama)
        embedder = OllamaEmbedder(settings.ollama)
    except Exception as e:
        err_console.print(f"[red]初始化失敗：{e}[/red]")
        raise typer.Exit(3)

    total_added = total_skipped = total_parse_errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for file_path in files:
            task_id = progress.add_task(f"[cyan]{file_path.name}[/cyan]", total=None)
            try:
                entries = list(load_entries([file_path], settings.chunking))
                progress.update(task_id, total=len(entries), completed=len(entries))
                chunks = entries_to_chunks(entries, settings.chunking.chunk_size, settings.chunking.chunk_overlap)
                added, skipped = upsert_chunks(collection, chunks, embedder)
                total_added += added
                total_skipped += skipped
            except httpx.ConnectError:
                err_console.print("[red]無法連線至 Ollama，請確認 ollama serve 已啟動。[/red]")
                raise typer.Exit(2)
            except Exception as e:
                err_console.print(f"[red]處理 {file_path.name} 時發生錯誤：{e}[/red]")
                total_parse_errors += 1

    console.print("\n[bold green]✅ 匯入完成[/bold green]")
    table = Table(show_header=False, box=None)
    table.add_row("新增至知識庫", f"[green]{total_added}[/green] chunks")
    table.add_row("重複（已存在）", f"{total_skipped} chunks")
    table.add_row("處理失敗檔案", f"[red]{total_parse_errors}[/red]" if total_parse_errors else "0")
    console.print(table)


@app.command()
def query(
    question: Optional[str] = typer.Option(None, "--question", "-q", help="問題（省略則進入互動模式）"),
    from_dt: Optional[datetime] = typer.Option(None, "--from", help="時間起點（ISO 8601）"),
    to_dt: Optional[datetime] = typer.Option(None, "--to", help="時間終點（ISO 8601）"),
    top_k: Optional[int] = typer.Option(None, "--top-k", help="檢索 chunk 數量"),
    show_sources: bool = typer.Option(True, "--show-sources/--no-sources", help="是否顯示來源"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="設定檔路徑"),
):
    """以自然語言查詢日誌知識庫。"""
    settings = _load_cfg(config)

    if from_dt and to_dt and from_dt > to_dt:
        err_console.print("[red]--from 時間不可晚於 --to 時間。[/red]")
        raise typer.Exit(1)

    try:
        client = get_chroma_client(settings.chroma)
        collection = get_or_create_collection(client, settings.chroma, settings.ollama)
    except Exception as e:
        err_console.print(f"[red]ChromaDB 初始化失敗：{e}[/red]")
        raise typer.Exit(4)

    if collection.count() == 0:
        err_console.print("[yellow]知識庫為空，請先執行 logiq ingest。[/yellow]")
        raise typer.Exit(4)

    embedder = OllamaEmbedder(settings.ollama)
    retriever = LogRetriever(collection, embedder)
    k = top_k or settings.retrieval.top_k

    def _run_query(q: str):
        console.print(f"\n[dim]檢索中...[/dim]")
        docs = retriever.retrieve(q, top_k=k, from_dt=from_dt, to_dt=to_dt)
        console.print(f"[dim]找到 {len(docs)} 個相關片段[/dim]\n")
        console.rule()
        try:
            for token in stream_answer(settings, q, docs):
                print(token, end="", flush=True)
            print()
        except httpx.ConnectError:
            err_console.print("\n[red]無法連線至 Ollama，請確認 ollama serve 已啟動。[/red]")
            raise typer.Exit(2)
        console.rule()

        if show_sources and docs:
            console.print("\n[bold]來源日誌：[/bold]")
            for i, doc in enumerate(docs, 1):
                m = doc.metadata
                console.print(
                    f"  [{i}] {m.get('source_file_name','?')} | "
                    f"{m.get('timestamp_iso','?')} | "
                    f"{m.get('level','?')} | "
                    f"相似度: {m.get('score', 0):.2f}"
                )

    if question:
        _run_query(question)
    else:
        console.print("[bold]進入互動模式[/bold]。輸入問題後按 Enter，輸入 [bold]exit[/bold] 離開。\n")
        while True:
            try:
                q = typer.prompt(">")
            except (KeyboardInterrupt, EOFError):
                break
            if q.strip().lower() in ("exit", "quit", "q"):
                break
            if q.strip():
                _run_query(q.strip())
        console.print("\n[dim]結束查詢。[/dim]")


@app.command()
def status(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="設定檔路徑"),
):
    """顯示知識庫統計資訊。"""
    settings = _load_cfg(config)

    table = Table(title="知識庫狀態", show_header=False)
    table.add_row("ChromaDB 路徑", str(settings.chroma.persist_path))
    table.add_row("Collection", settings.chroma.collection_name)

    try:
        client = get_chroma_client(settings.chroma)
        collection = get_or_create_collection(client, settings.chroma, settings.ollama)
        count = collection.count()
        table.add_row("總 chunk 數", str(count))

        if count > 0:
            all_meta = collection.get(include=["metadatas"])["metadatas"]
            sources = {m.get("source_file_name", "?") for m in all_meta}
            timestamps = [m.get("timestamp_unix", 0) for m in all_meta if m.get("timestamp_unix")]
            table.add_row("來源檔案數", str(len(sources)))
            if timestamps:
                from datetime import datetime as dt
                table.add_row("最早記錄", dt.fromtimestamp(min(timestamps)).isoformat())
                table.add_row("最新記錄", dt.fromtimestamp(max(timestamps)).isoformat())
    except Exception as e:
        table.add_row("狀態", f"[red]錯誤：{e}[/red]")

    import httpx as _httpx
    try:
        resp = _httpx.get(f"{settings.ollama.base_url}/api/tags", timeout=3)
        ollama_status = "[green]✅ 連線正常[/green]"
    except Exception:
        ollama_status = "[red]❌ 無法連線[/red]"

    table.add_row("Ollama 狀態", ollama_status)
    table.add_row("LLM 模型", settings.ollama.llm_model)
    table.add_row("Embedding 模型", settings.ollama.embedding_model)

    console.print(table)


@app.command()
def clear(
    confirm: bool = typer.Option(False, "--confirm", help="跳過確認提示"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="設定檔路徑"),
):
    """清除向量知識庫中的所有資料。"""
    settings = _load_cfg(config)

    try:
        client = get_chroma_client(settings.chroma)
        collection = get_or_create_collection(client, settings.chroma, settings.ollama)
        count = collection.count()
    except Exception as e:
        err_console.print(f"[red]ChromaDB 連線失敗：{e}[/red]")
        raise typer.Exit(3)

    if not confirm:
        proceed = typer.confirm(
            f"即將清除知識庫中的 {count} 個 chunks，此操作無法復原。確認清除？",
            default=False,
        )
        if not proceed:
            console.print("[dim]已取消。[/dim]")
            raise typer.Exit(0)

    try:
        client.delete_collection(settings.chroma.collection_name)
        console.print("[bold green]✅ 知識庫已清除。[/bold green]")
    except Exception as e:
        err_console.print(f"[red]清除失敗：{e}[/red]")
        raise typer.Exit(3)


def main():
    app()


if __name__ == "__main__":
    main()
