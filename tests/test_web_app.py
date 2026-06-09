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
