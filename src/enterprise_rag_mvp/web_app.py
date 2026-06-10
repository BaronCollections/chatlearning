import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from enterprise_rag_mvp.cli import DEFAULT_DSN, DEFAULT_EMBEDDING_URL
from enterprise_rag_mvp.embedding_client import EmbeddingClient
from enterprise_rag_mvp.pgvector_store import PgVectorStore
from enterprise_rag_mvp.reranker_client import RerankerClient
from enterprise_rag_mvp.trace_pipeline import run_chat_trace


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must contain non-whitespace text")
        return value


def _web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"


def _default_runner(query: str, top_k: int) -> dict[str, Any]:
    embedding_client = EmbeddingClient(base_url=os.getenv("EMBEDDING_SERVICE_URL", DEFAULT_EMBEDDING_URL))
    store = None
    if os.getenv("RAG_DISABLE_PGVECTOR", "false").lower() not in {"1", "true", "yes", "on"}:
        store = PgVectorStore(os.getenv("RAG_DATABASE_DSN", DEFAULT_DSN))
    reranker_url = os.getenv("RERANKER_SERVICE_URL", "").strip()
    reranker_client = RerankerClient(base_url=reranker_url, provider=os.getenv("RERANKER_PROVIDER", "external_cross_encoder")) if reranker_url else None
    return run_chat_trace(query, embedding_client=embedding_client, store=store, top_k=top_k, reranker_client=reranker_client)


def create_app(*, chat_runner: Callable[[str, int], dict[str, Any]] | None = None) -> FastAPI:
    runner = chat_runner or _default_runner
    app = FastAPI(title="Enterprise RAG Trace Chat")
    web_dir = _web_dir()
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (web_dir / "index.html").read_text(encoding="utf-8")

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        try:
            return runner(request.message, request.top_k)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "RAG pipeline unavailable", "error": str(exc)},
            ) from exc

    return app


app = create_app()
