import json

from enterprise_rag_mvp.langfuse_tracing import (
    DisabledLangfuseReporter,
    LangfuseTraceReporter,
    build_langfuse_trace_id,
)


class RecordingObservation:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.updates = []
        self.trace_id = kwargs.get("trace_context", {}).get("trace_id")
        self.id = kwargs.get("name")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, **kwargs):
        self.updates.append(kwargs)


class RecordingLangfuseClient:
    def __init__(self):
        self.observations = []
        self.flushed = False

    def start_as_current_observation(self, **kwargs):
        observation = RecordingObservation(**kwargs)
        self.observations.append(observation)
        return observation

    def flush(self):
        self.flushed = True


def test_disabled_langfuse_reporter_returns_disabled_status():
    result = DisabledLangfuseReporter().record_chat_trace({"query": "年假", "steps": []})

    assert result == {
        "provider": "langfuse",
        "enabled": False,
        "status": "disabled",
        "trace_id": None,
        "trace_url": None,
        "span_count": 0,
        "error": None,
    }


def test_build_langfuse_trace_id_is_w3c_hex_and_deterministic():
    trace_id = build_langfuse_trace_id("trace_local_1")

    assert trace_id == build_langfuse_trace_id("trace_local_1")
    assert len(trace_id) == 32
    assert trace_id.islower()
    assert all(char in "0123456789abcdef" for char in trace_id)


def test_langfuse_reporter_records_sanitized_trace_without_full_chunk_text():
    client = RecordingLangfuseClient()
    reporter = LangfuseTraceReporter(client=client, host="https://langfuse.example", project_id="proj_1")
    payload = {
        "trace_id": "trace_local_1",
        "query": "工作五年有几天年假",
        "answer": "结论：第五年为 18天。",
        "retrieval_mode": "in_memory_demo",
        "results": [
            {
                "chunk_id": "leave-annual-001",
                "doc_id": "employee-leave-policy",
                "text": "完整制度正文不要发到 Langfuse。第五年 18天。",
                "distance": 0.02,
                "citation": {"title": "年休假", "source": "制度库"},
            }
        ],
        "steps": [
            {
                "key": "retrieval",
                "title": "Step 6 · 初始召回",
                "status": "ok",
                "execution_mode": "sequential",
                "summary": "召回候选证据。",
                "duration_ms": 2.4,
                "details": {"tool": "hybrid search", "raw_query": "工作五年有几天年假"},
            }
        ],
    }

    observability = reporter.record_chat_trace(payload)

    assert observability["status"] == "ok"
    assert observability["trace_id"] == build_langfuse_trace_id("trace_local_1")
    assert observability["trace_url"] == f"https://langfuse.example/project/proj_1/traces/{observability['trace_id']}"
    assert observability["span_count"] == 2
    assert client.flushed is True
    serialized = json.dumps(
        [{"kwargs": obs.kwargs, "updates": obs.updates} for obs in client.observations],
        ensure_ascii=False,
    )
    assert "leave-annual-001" in serialized
    assert "完整制度正文不要发到 Langfuse" not in serialized
    assert "第五年 18天" not in serialized
