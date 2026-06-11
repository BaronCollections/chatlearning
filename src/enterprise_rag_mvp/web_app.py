import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from enterprise_rag_mvp.bad_cases import ALLOWED_FEEDBACK_TYPES, append_bad_case_record, build_bad_case_record
from enterprise_rag_mvp.cli import DEFAULT_DSN, DEFAULT_EMBEDDING_URL
from enterprise_rag_mvp.embedding_client import DeterministicEmbeddingClient, EmbeddingClient
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


class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1)
    feedback_type: str = Field(min_length=1)
    answer: str = ""
    trace_id: str | None = None
    comment: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        return value

    @field_validator("feedback_type")
    @classmethod
    def feedback_type_must_be_supported(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in ALLOWED_FEEDBACK_TYPES:
            raise ValueError(f"unsupported feedback_type: {normalized}")
        return normalized


def _web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"


def _embedding_client_from_env() -> EmbeddingClient | DeterministicEmbeddingClient:
    provider = os.getenv("RAG_EMBEDDING_PROVIDER", "http").strip().lower()
    if provider in {"local", "deterministic", "demo"}:
        return DeterministicEmbeddingClient()
    if provider in {"", "http", "remote", "external", "bge", "bge-m3"}:
        return EmbeddingClient(base_url=os.getenv("EMBEDDING_SERVICE_URL", DEFAULT_EMBEDDING_URL))
    raise ValueError(
        "unsupported RAG_EMBEDDING_PROVIDER; expected one of "
        "http, remote, external, bge, bge-m3, local, deterministic, demo"
    )


def _default_runner(query: str, top_k: int) -> dict[str, Any]:
    embedding_client = _embedding_client_from_env()
    store = None
    if os.getenv("RAG_DISABLE_PGVECTOR", "false").lower() not in {"1", "true", "yes", "on"}:
        store = PgVectorStore(os.getenv("RAG_DATABASE_DSN", DEFAULT_DSN))
    reranker_url = os.getenv("RERANKER_SERVICE_URL", "").strip()
    reranker_client = RerankerClient(base_url=reranker_url, provider=os.getenv("RERANKER_PROVIDER", "external_cross_encoder")) if reranker_url else None
    return run_chat_trace(query, embedding_client=embedding_client, store=store, top_k=top_k, reranker_client=reranker_client)


def create_app(
    *,
    chat_runner: Callable[[str, int], dict[str, Any]] | None = None,
    bad_case_path: str | Path | None = None,
) -> FastAPI:
    runner = chat_runner or _default_runner
    feedback_path = Path(bad_case_path or os.getenv("RAG_BAD_CASE_PATH", "data/bad_cases.jsonl"))
    app = FastAPI(title="Enterprise RAG Trace Chat", docs_url="/api/docs", redoc_url="/api/redoc")
    web_dir = _web_dir()
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (web_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/docs", response_class=HTMLResponse)
    def docs() -> str:
        return (web_dir / "docs.html").read_text(encoding="utf-8")

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        try:
            return runner(request.message, request.top_k)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "RAG pipeline unavailable", "error": str(exc)},
            ) from exc

    @app.post("/api/feedback")
    def collect_feedback(request: FeedbackRequest) -> dict[str, Any]:
        try:
            record = build_bad_case_record(request.model_dump())
            append_bad_case_record(feedback_path, record)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid feedback payload", "error": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "Feedback storage unavailable", "error": str(exc)},
            ) from exc
        return {
            "status": "ok",
            "stored": True,
            "feedback_type": record.feedback_type,
            "raw_trace_stored": record.raw_trace_stored,
        }

    return app


app = create_app()
