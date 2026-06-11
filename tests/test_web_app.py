import json

from fastapi.testclient import TestClient

from enterprise_rag_mvp.web_app import _default_runner, create_app


def test_home_page_serves_trace_chat_shell():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.get("/")

    assert response.status_code == 200
    assert "RAG Trace Chat" in response.text
    assert "messageInput" in response.text


def test_docs_page_serves_standalone_documentation_shell():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.get("/docs")

    assert response.status_code == 200
    assert "ChatLearning Docs" in response.text
    assert "docs-page-shell" in response.text
    assert "docs.js" in response.text


def test_chat_endpoint_returns_trace_response():
    def fake_runner(query: str, top_k: int):
        return {
            "query": query,
            "answer": "测试回答",
            "retrieval_mode": "in_memory_demo",
            "results": [],
            "steps": [
                {
                    "key": "receive_query",
                    "title": "Step 1 · 接收用户问题",
                    "status": "ok",
                    "summary": "收到问题",
                    "details": {"top_k": top_k},
                    "duration_ms": 1.2,
                }
            ],
        }

    client = TestClient(create_app(chat_runner=fake_runner))

    response = client.post("/api/chat", json={"message": "员工年假规则是什么？", "top_k": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "测试回答"
    assert body["query"] == "员工年假规则是什么？"
    assert body["steps"][0]["details"] == {"top_k": 2}


def test_chat_endpoint_rejects_blank_message_without_calling_runner():
    called = False

    def fake_runner(query: str, top_k: int):
        nonlocal called
        called = True
        return {}

    client = TestClient(create_app(chat_runner=fake_runner))

    response = client.post("/api/chat", json={"message": " \t\n ", "top_k": 2})

    assert response.status_code == 422
    assert called is False


def test_chat_endpoint_returns_service_error_when_runner_fails():
    def fake_runner(query: str, top_k: int):
        raise RuntimeError("embedding service unavailable")

    client = TestClient(create_app(chat_runner=fake_runner), raise_server_exceptions=False)

    response = client.post("/api/chat", json={"message": "员工年假规则是什么？", "top_k": 2})

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "RAG pipeline unavailable"
    assert "embedding service unavailable" in response.json()["detail"]["error"]


def test_feedback_endpoint_stores_bad_case_without_raw_trace(tmp_path):
    bad_case_path = tmp_path / "bad_cases.jsonl"
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}, bad_case_path=bad_case_path))

    response = client.post(
        "/api/feedback",
        json={
            "query": "二类违规的处罚是什么",
            "feedback_type": "missing_clause",
            "answer": "只返回了定义，缺少处罚",
            "trace_id": "trace-1",
            "results": [
                {
                    "doc_id": "policy-16",
                    "chunk_id": "policy-16:section-2",
                    "text": "不应该保存完整制度正文",
                    "citation": {
                        "title": "***公司人守则-员工纪律制度",
                        "url": "https://example.com/policyDetail/16",
                        "category": "***公司人守则",
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["stored"] is True
    assert response.json()["raw_trace_stored"] is False
    rows = [json.loads(line) for line in bad_case_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["feedback_type"] == "missing_clause"
    assert rows[0]["citations"][0]["title"] == "***公司人守则-员工纪律制度"
    assert "不应该保存完整制度正文" not in bad_case_path.read_text(encoding="utf-8")


def test_default_runner_supports_explicit_local_embedding_provider(monkeypatch):
    monkeypatch.setenv("RAG_DISABLE_PGVECTOR", "true")
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "local")

    response = _default_runner("我旷工两天会有什么处罚", 2)

    assert response["retrieval_mode"] == "in_memory_demo"
    assert "扣除旷工期间工资" in response["answer"]
    assert "记过处分" in response["answer"]
    assert any(result["citation"].get("url") == "https://example.com/policyDetail/11" for result in response["results"])
