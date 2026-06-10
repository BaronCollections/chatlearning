import json

from fastapi.testclient import TestClient

from enterprise_rag_mvp.web_app import create_app


def test_home_page_serves_trace_chat_shell():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.get("/")

    assert response.status_code == 200
    assert "RAG Trace Chat" in response.text
    assert "messageInput" in response.text


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
                        "title": "云谷人守则-员工纪律制度",
                        "url": "https://work.yungu.org/policyDetail/16",
                        "category": "云谷人守则",
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
    assert rows[0]["citations"][0]["title"] == "云谷人守则-员工纪律制度"
    assert "不应该保存完整制度正文" not in bad_case_path.read_text(encoding="utf-8")
