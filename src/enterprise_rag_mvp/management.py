from __future__ import annotations

import os
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from enterprise_rag_mvp.document_chunking import chunk_parsed_document
from enterprise_rag_mvp.document_parsing import DocumentParserRouter, DocumentSource, parsed_document_text


@dataclass(frozen=True)
class ManagementIntegrationStatus:
    status: str
    label: str
    detail: str


@dataclass(frozen=True)
class ManagementInterfaceSummary:
    path: str
    method: str
    status: str
    purpose: str


@dataclass(frozen=True)
class ManagementKnowledgeBaseSummary:
    id: str
    name: str
    source: str
    status: str
    description: str


def _configured(value: str | None) -> bool:
    return bool((value or "").strip())


def _is_disabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_management_overview() -> dict[str, Any]:
    pgvector_disabled = _is_disabled(os.getenv("RAG_DISABLE_PGVECTOR"))
    embedding_configured = _configured(os.getenv("EMBEDDING_SERVICE_URL")) or os.getenv("RAG_EMBEDDING_PROVIDER", "http").strip().lower() in {
        "local",
        "deterministic",
        "demo",
    }
    reranker_configured = _configured(os.getenv("RERANKER_SERVICE_URL"))

    knowledge_bases = [
        ManagementKnowledgeBaseSummary(
            id="company_policy_system",
            name="企业制度知识库",
            source="company_policy_importer",
            status="available",
            description="当前工程切片通过公司制度导入器写入 pgvector；后续会替换为可持久化的知识库表。",
        )
    ]
    interfaces = {
        "chat_trace": ManagementInterfaceSummary(
            path="/api/chat",
            method="POST",
            status="available",
            purpose="返回带执行步骤的 RAG Trace Chat 响应。",
        ),
        "feedback": ManagementInterfaceSummary(
            path="/api/feedback",
            method="POST",
            status="available",
            purpose="记录坏例反馈和引用摘要，不保存完整原文 trace。",
        ),
        "document_preview": ManagementInterfaceSummary(
            path="/api/admin/document-preview",
            method="POST",
            status="available",
            purpose="在写入知识库前预览解析质量、元素和切块结果。",
        ),
    }
    integrations = {
        "embedding": ManagementIntegrationStatus(
            status="configured" if embedding_configured else "missing",
            label="Embedding service",
            detail="已配置 embedding provider。" if embedding_configured else "未配置 EMBEDDING_SERVICE_URL 或本地 embedding provider。",
        ),
        "pgvector": ManagementIntegrationStatus(
            status="disabled" if pgvector_disabled else "enabled",
            label="PostgreSQL + pgvector",
            detail="当前请求会跳过 pgvector 并使用演示 fallback。" if pgvector_disabled else "当前请求会尝试使用 pgvector store。",
        ),
        "reranker": ManagementIntegrationStatus(
            status="configured" if reranker_configured else "optional",
            label="Cross-encoder reranker",
            detail="已配置外部 reranker。" if reranker_configured else "未配置外部 reranker，系统会使用确定性 fallback。",
        ),
    }
    return {
        "status": "ok",
        "knowledge_bases": [asdict(item) for item in knowledge_bases],
        "interfaces": {key: asdict(value) for key, value in interfaces.items()},
        "integrations": {key: asdict(value) for key, value in integrations.items()},
    }


def preview_document_parse(
    *,
    source_name: str,
    file_name: str | None,
    content_type: str | None,
    text: str,
    max_chars: int,
    overlap_chars: int,
    parser_router: DocumentParserRouter | None = None,
) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("text must contain non-whitespace content")
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    router = parser_router or DocumentParserRouter()
    parsed = router.parse(
        DocumentSource(
            source_id="admin-preview",
            source_name=source_name,
            file_name=file_name,
            content_type=content_type,
            text=text,
        )
    )
    parsed_text = parsed_document_text(parsed)
    chunked = chunk_parsed_document(parsed, max_chars=max_chars, overlap_chars=overlap_chars) if parsed_text else None
    chunks = chunked.chunks if chunked else []
    chunk_preview_limit = 100
    chunk_type_counts = Counter(str(chunk.metadata.get("chunk_type") or "chunk") for chunk in chunks)
    chunk_language_counts = Counter(str(chunk.metadata.get("language") or "unknown") for chunk in chunks)
    chunk_role_counts = Counter(str(chunk.metadata.get("chunk_role") or "unknown") for chunk in chunks)
    return {
        "source_id": parsed.source_id,
        "source_name": parsed.source_name,
        "source_type": parsed.source_type,
        "quality": asdict(parsed.quality),
        "chunking_quality": asdict(chunked.quality) if chunked else None,
        "element_count": len(parsed.elements),
        "chunk_count": len(chunks),
        "chunk_preview_limit": chunk_preview_limit,
        "chunk_preview_count": min(len(chunks), chunk_preview_limit),
        "chunk_type_counts": dict(sorted(chunk_type_counts.items())),
        "chunk_language_counts": dict(sorted(chunk_language_counts.items())),
        "chunk_role_counts": dict(sorted(chunk_role_counts.items())),
        "elements": [
            {
                "element_id": element.element_id,
                "element_type": element.element_type,
                "text": element.text,
                "heading_path": element.heading_path,
                "page_number": element.page_number,
                "confidence": element.confidence,
                "metadata": element.metadata,
            }
            for element in parsed.elements[:20]
        ],
        "chunks": [
            {
                "index": index,
                "text": chunk.text,
                "char_count": len(chunk.text),
                "heading_path": chunk.heading_path,
                "metadata": chunk.metadata,
            }
            for index, chunk in enumerate(chunks[:chunk_preview_limit], start=1)
        ],
    }
