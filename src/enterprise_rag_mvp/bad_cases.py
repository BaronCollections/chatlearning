from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_FEEDBACK_TYPES = {
    "correct",
    "wrong_source",
    "missing_clause",
    "irrelevant_answer",
    "too_verbose",
    "scope_leak",
    "unsafe_or_sensitive",
}


@dataclass(frozen=True)
class BadCaseRecord:
    query: str
    feedback_type: str
    answer: str = ""
    trace_id: str | None = None
    comment: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    raw_trace_stored: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _citation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    citation = result.get("citation") if isinstance(result.get("citation"), dict) else {}
    return {
        "chunk_id": result.get("chunk_id"),
        "doc_id": result.get("doc_id"),
        "title": citation.get("title"),
        "url": citation.get("url"),
        "category": citation.get("category"),
        "publish_date": citation.get("publish_date"),
    }


def build_bad_case_record(payload: dict[str, Any]) -> BadCaseRecord:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    feedback_type = str(payload.get("feedback_type") or "").strip()
    if feedback_type not in ALLOWED_FEEDBACK_TYPES:
        raise ValueError(f"unsupported feedback_type: {feedback_type}")
    results = payload.get("results") or []
    citations = [_citation_from_result(result) for result in results if isinstance(result, dict)]
    return BadCaseRecord(
        query=query,
        feedback_type=feedback_type,
        answer=str(payload.get("answer") or ""),
        trace_id=str(payload.get("trace_id")) if payload.get("trace_id") else None,
        comment=str(payload.get("comment")) if payload.get("comment") else None,
        citations=citations,
        raw_trace_stored=False,
    )


def append_bad_case_record(path: str | Path, record: BadCaseRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
