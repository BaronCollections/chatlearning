import json

import pytest

from enterprise_rag_mvp.bad_cases import build_bad_case_record, append_bad_case_record


def test_build_bad_case_record_keeps_debug_fields_without_full_trace_dump():
    record = build_bad_case_record(
        {
            "query": "虚假报销怎么处罚",
            "answer": "错误答案",
            "feedback_type": "wrong_source",
            "trace_id": "trace_123",
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "doc-1",
                    "citation": {"title": "制度", "url": "https://example.test/policy/1"},
                    "text": "不应该保存完整 chunk 正文",
                }
            ],
            "steps": [{"huge": "trace"}],
        }
    )

    assert record.query == "虚假报销怎么处罚"
    assert record.feedback_type == "wrong_source"
    assert record.trace_id == "trace_123"
    assert record.citations[0]["chunk_id"] == "chunk-1"
    assert "text" not in record.citations[0]
    assert record.raw_trace_stored is False


def test_build_bad_case_record_rejects_unknown_feedback_type():
    with pytest.raises(ValueError, match="unsupported feedback_type"):
        build_bad_case_record({"query": "q", "feedback_type": "whatever"})


def test_append_bad_case_record_writes_jsonl(tmp_path):
    record = build_bad_case_record({"query": "q", "feedback_type": "missing_clause", "answer": "a"})
    path = tmp_path / "bad_cases.jsonl"

    append_bad_case_record(path, record)

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[0]["query"] == "q"
    assert rows[0]["feedback_type"] == "missing_clause"
