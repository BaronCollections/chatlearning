from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Mapping

MAX_LANGFUSE_TEXT_CHARS = 600
_FALSE_VALUES = {"", "0", "false", "no", "off", "disabled"}
_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def _base_payload(*, enabled: bool, status: str, trace_id: str | None = None, trace_url: str | None = None, span_count: int = 0, error: str | None = None) -> dict[str, Any]:
    return {
        "provider": "langfuse",
        "enabled": enabled,
        "status": status,
        "trace_id": trace_id,
        "trace_url": trace_url,
        "span_count": span_count,
        "error": error,
    }


def langfuse_observability_error(error: Exception | str, *, enabled: bool = True) -> dict[str, Any]:
    return _base_payload(enabled=enabled, status="error", error=str(error))


def build_langfuse_trace_id(seed: str | None = None) -> str:
    value = str(seed or "").strip().lower()
    if len(value) == 32 and all(char in "0123456789abcdef" for char in value):
        return value
    if not value:
        return uuid.uuid4().hex
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _short_text(value: Any, *, limit: int = MAX_LANGFUSE_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _extract_local_trace_id(payload: Mapping[str, Any]) -> str | None:
    for key in ("trace_id", "request_id"):
        value = payload.get(key)
        if value:
            return str(value)
    for step in payload.get("steps") or []:
        details = step.get("details") or {}
        value = details.get("trace_id") or details.get("request_id")
        if value:
            return str(value)
    query = payload.get("query")
    return str(query) if query else None


def _trace_url(host: str | None, project_id: str | None, trace_id: str, template: str | None = None) -> str | None:
    if template:
        return template.format(trace_id=trace_id, project_id=project_id or "")
    if not host or not project_id:
        return None
    return f"{host.rstrip('/')}/project/{project_id}/traces/{trace_id}"


def _sanitize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    citation = result.get("citation") or {}
    return {
        "chunk_id": result.get("chunk_id"),
        "doc_id": result.get("doc_id"),
        "block_id": result.get("block_id"),
        "distance": result.get("distance"),
        "heading_path": result.get("heading_path"),
        "citation": {
            "title": citation.get("title"),
            "source": citation.get("source"),
            "url": citation.get("url"),
            "category": citation.get("category"),
            "publish_date": citation.get("publish_date"),
        },
    }


def _sanitize_step(step: Mapping[str, Any]) -> dict[str, Any]:
    details = step.get("details") or {}
    safe_detail_keys = [
        "tool",
        "intent",
        "retrieval_intent",
        "policy_category_hint",
        "candidate_limit",
        "enabled_channels",
        "semantic_drift_check",
        "post_answer_faithfulness_check",
        "scope_guard",
        "reranker_provider",
        "result_count",
        "status",
    ]
    safe_details = {key: details[key] for key in safe_detail_keys if key in details}
    return {
        "key": step.get("key"),
        "title": step.get("title"),
        "status": step.get("status"),
        "execution_mode": step.get("execution_mode"),
        "summary": _short_text(step.get("summary"), limit=240),
        "duration_ms": step.get("duration_ms"),
        "child_count": len(step.get("children") or []),
        "details": safe_details,
    }


def _start_observation(client: Any, **kwargs: Any):
    try:
        return client.start_as_current_observation(**kwargs)
    except TypeError:
        kwargs.pop("trace_context", None)
        return client.start_as_current_observation(**kwargs)


def _update_observation(observation: Any, **kwargs: Any) -> None:
    update = getattr(observation, "update", None)
    if callable(update):
        update(**kwargs)


class DisabledLangfuseReporter:
    def record_chat_trace(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return _base_payload(enabled=False, status="disabled")


class UnavailableLangfuseReporter:
    def __init__(self, reason: str):
        self.reason = reason

    def record_chat_trace(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        local_trace_id = _extract_local_trace_id(payload)
        trace_id = build_langfuse_trace_id(local_trace_id) if local_trace_id else None
        return _base_payload(enabled=True, status="unavailable", trace_id=trace_id, error=self.reason)


class LangfuseTraceReporter:
    def __init__(self, *, client: Any, host: str | None = None, project_id: str | None = None, trace_url_template: str | None = None):
        self.client = client
        self.host = host
        self.project_id = project_id
        self.trace_url_template = trace_url_template

    def record_chat_trace(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        local_trace_id = _extract_local_trace_id(payload)
        trace_id = build_langfuse_trace_id(local_trace_id)
        results = [_sanitize_result(result) for result in payload.get("results") or []]
        steps = [_sanitize_step(step) for step in payload.get("steps") or []]
        span_count = 1

        with _start_observation(
            self.client,
            as_type="span",
            name="rag_chat",
            trace_context={"trace_id": trace_id},
        ) as root:
            _update_observation(
                root,
                input={"query": _short_text(payload.get("query")), "retrieval_mode": payload.get("retrieval_mode")},
                output={"answer_preview": _short_text(payload.get("answer")), "result_count": len(results)},
                metadata={
                    "local_trace_id": local_trace_id,
                    "retrieval_mode": payload.get("retrieval_mode"),
                    "results": results,
                    "sanitization": "full chunk text is omitted; only identifiers, citations, scores, and short answer preview are sent",
                },
            )
            for step in steps:
                with _start_observation(self.client, as_type="span", name=str(step.get("key") or "rag_step")) as span:
                    span_count += 1
                    _update_observation(
                        span,
                        input={"step": step.get("key")},
                        output={"status": step.get("status"), "duration_ms": step.get("duration_ms")},
                        metadata=step,
                    )

        flush = getattr(self.client, "flush", None)
        if callable(flush):
            flush()

        return _base_payload(
            enabled=True,
            status="ok",
            trace_id=trace_id,
            trace_url=_trace_url(self.host, self.project_id, trace_id, self.trace_url_template),
            span_count=span_count,
        )


def _env_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def langfuse_reporter_from_env(env: Mapping[str, str] | None = None) -> Any:
    source = os.environ if env is None else env
    explicit_enabled = _env_flag(source.get("LANGFUSE_TRACING_ENABLED"))
    public_key = source.get("LANGFUSE_PUBLIC_KEY")
    secret_key = source.get("LANGFUSE_SECRET_KEY")
    enabled = explicit_enabled if explicit_enabled is not None else bool(public_key and secret_key)
    if not enabled:
        return DisabledLangfuseReporter()
    if not public_key or not secret_key:
        return UnavailableLangfuseReporter("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when Langfuse tracing is enabled")

    try:
        from langfuse import get_client
    except Exception as exc:  # pragma: no cover - depends on optional package availability
        return UnavailableLangfuseReporter(f"langfuse package is not installed: {exc}")

    try:
        client = get_client()
    except Exception as exc:  # pragma: no cover - depends on SDK/runtime config
        return UnavailableLangfuseReporter(f"failed to initialize langfuse client: {exc}")

    return LangfuseTraceReporter(
        client=client,
        host=source.get("LANGFUSE_HOST") or source.get("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com",
        project_id=source.get("LANGFUSE_PROJECT_ID"),
        trace_url_template=source.get("LANGFUSE_TRACE_URL_TEMPLATE"),
    )
