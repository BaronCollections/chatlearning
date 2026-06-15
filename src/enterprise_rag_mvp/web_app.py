import inspect
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
from enterprise_rag_mvp.langfuse_tracing import langfuse_observability_error, langfuse_reporter_from_env
from enterprise_rag_mvp.management import build_management_overview, preview_document_parse
from enterprise_rag_mvp.pgvector_store import PgVectorStore
from enterprise_rag_mvp.reranker_client import RerankerClient
from enterprise_rag_mvp.trace_pipeline import run_chat_trace


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)
    conversation_context: dict[str, Any] = Field(default_factory=dict)

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


class DocumentPreviewRequest(BaseModel):
    source_name: str = Field(min_length=1)
    file_name: str | None = None
    content_type: str | None = None
    text: str = Field(min_length=1)
    max_chars: int = Field(default=1200, ge=1, le=20000)
    overlap_chars: int = Field(default=150, ge=0, le=5000)

    @field_validator("source_name")
    @classmethod
    def source_name_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_name must contain non-whitespace text")
        return value.strip()

    @field_validator("text")
    @classmethod
    def text_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace content")
        return value


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


def _default_runner(query: str, top_k: int, conversation_context: dict[str, Any] | None = None) -> dict[str, Any]:
    embedding_client = _embedding_client_from_env()
    store = None
    if os.getenv("RAG_DISABLE_PGVECTOR", "false").lower() not in {"1", "true", "yes", "on"}:
        store = PgVectorStore(os.getenv("RAG_DATABASE_DSN", DEFAULT_DSN))
    reranker_url = os.getenv("RERANKER_SERVICE_URL", "").strip()
    reranker_client = RerankerClient(base_url=reranker_url, provider=os.getenv("RERANKER_PROVIDER", "external_cross_encoder")) if reranker_url else None
    return run_chat_trace(query, embedding_client=embedding_client, store=store, top_k=top_k, reranker_client=reranker_client, conversation_context=conversation_context)


def _runner_accepts_conversation_context(runner: Callable[..., dict[str, Any]]) -> bool:
    try:
        signature = inspect.signature(runner)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters
    return "conversation_context" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


def create_app(
    *,
    chat_runner: Callable[[str, int], dict[str, Any]] | None = None,
    bad_case_path: str | Path | None = None,
    langfuse_reporter: Any | None = None,
) -> FastAPI:
    runner = chat_runner or _default_runner
    reporter = langfuse_reporter if langfuse_reporter is not None else langfuse_reporter_from_env()
    feedback_path = Path(bad_case_path or os.getenv("RAG_BAD_CASE_PATH", "data/bad_cases.jsonl"))
    app = FastAPI(title="Enterprise RAG Trace Chat", docs_url="/api/docs", redoc_url="/api/redoc")

    @app.middleware("http")
    async def disable_static_asset_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path in {"/", "/docs", "/admin"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    web_dir = _web_dir()
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (web_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/docs", response_class=HTMLResponse)
    def docs() -> str:
        return (web_dir / "docs.html").read_text(encoding="utf-8")

    @app.get("/admin", response_class=HTMLResponse)
    def admin() -> str:
        return (web_dir / "admin.html").read_text(encoding="utf-8")

    @app.get("/api/admin/overview")
    def admin_overview() -> dict[str, Any]:
        return build_management_overview()

    @app.post("/api/admin/document-preview")
    def admin_document_preview(request: DocumentPreviewRequest) -> dict[str, Any]:
        try:
            return preview_document_parse(
                source_name=request.source_name,
                file_name=request.file_name,
                content_type=request.content_type,
                text=request.text,
                max_chars=request.max_chars,
                overlap_chars=request.overlap_chars,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"message": "Invalid document preview payload", "error": str(exc)}) from exc

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        try:
            if request.conversation_context and _runner_accepts_conversation_context(runner):
                response = runner(request.message, request.top_k, conversation_context=request.conversation_context)
            else:
                response = runner(request.message, request.top_k)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "RAG pipeline unavailable", "error": str(exc)},
            ) from exc
        try:
            response["observability"] = reporter.record_chat_trace(response)
        except Exception as exc:
            response["observability"] = langfuse_observability_error(exc)
        return response

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
