import json

from fastapi.testclient import TestClient

from enterprise_rag_mvp.embedding_client import DeterministicEmbeddingClient
from enterprise_rag_mvp.trace_pipeline import run_chat_trace
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


def test_admin_page_serves_management_console_shell():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.get("/admin")

    assert response.status_code == 200
    assert "RAG Management Console" in response.text
    assert "documentPreviewForm" in response.text
    assert "admin.js" in response.text


def test_admin_overview_reports_manageable_surfaces_without_secret_values(monkeypatch):
    monkeypatch.setenv("EMBEDDING_SERVICE_URL", "https://embedding.example.test/private")
    monkeypatch.setenv("RERANKER_SERVICE_URL", "https://reranker.example.test/private")
    monkeypatch.setenv("RAG_DISABLE_PGVECTOR", "true")
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.get("/api/admin/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["knowledge_bases"][0]["id"] == "company_policy_system"
    assert body["interfaces"]["chat_trace"]["path"] == "/api/chat"
    assert body["interfaces"]["feedback"]["path"] == "/api/feedback"
    assert body["integrations"]["embedding"]["status"] == "configured"
    assert body["integrations"]["pgvector"]["status"] == "disabled"
    assert body["integrations"]["reranker"]["status"] == "configured"
    assert "private" not in response.text


def test_admin_document_preview_parses_html_and_reports_quality():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.post(
        "/api/admin/document-preview",
        json={
            "source_name": "员工纪律制度",
            "file_name": "policy.html",
            "content_type": "text/html",
            "text": "<h1>员工纪律制度</h1><p>二类违规行为需要记过处分。</p>",
            "max_chars": 20,
            "overlap_chars": 4,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "html"
    assert body["quality"]["status"] == "success"
    assert body["quality"]["parser_name"] == "html_builtin"
    assert body["element_count"] == 2
    assert body["chunk_count"] >= 1
    assert body["elements"][0]["heading_path"] == ["员工纪律制度"]
    assert body["chunking_quality"]["status"] == "success"
    assert body["chunking_quality"]["chunking_strategy"] in {"policy_clause_group", "fixed_window_fallback"}


def test_admin_document_preview_accepts_plain_text_pasted_with_html_content_type():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.post(
        "/api/admin/document-preview",
        json={
            "source_name": "员工纪律制度",
            "file_name": "policy.html",
            "content_type": "text/html",
            "text": "示例机构员工纪律制度\nExample School Employee Disciplinary Rules\n\n一、目的\n为落实示例学校的使命制定本制度。",
            "max_chars": 1200,
            "overlap_chars": 150,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "html"
    assert body["quality"]["status"] == "success"
    assert body["element_count"] >= 2
    assert body["chunk_count"] >= 1
    assert "示例机构员工纪律制度" in body["chunks"][0]["text"]
    assert body["chunking_quality"]["status"] == "success"


def test_admin_document_preview_uses_clause_group_chunks_for_policy_text():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.post(
        "/api/admin/document-preview",
        json={
            "source_name": "员工纪律制度",
            "file_name": "policy.html",
            "content_type": "text/html",
            "text": """
            示例机构员工纪律制度
            四、违规行为
            （二）二类违规行为
            二类违规行为：指比较严重的违规行为。
            4. 破坏学校管理秩序行为
            4.1渎职给学校造成较大损失。
            4.2旷工少于三天。
            4.3 使用未经批准的教材上课，给学校带来较大风险。
            （三）三类违规行为
            三类违规行为：指一般的违规行为。
            5. 破坏学校管理秩序行为
            5.1上课迟到、早退和随意停课。
            五、违规行为相应处理
            1. 违规行为相应处理
            1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪。
            """,
            "max_chars": 1200,
            "overlap_chars": 150,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["chunking_quality"]["chunking_strategy"] == "policy_clause_group"
    assert body["chunking_quality"]["coverage_status"] == "complete"
    assert body["chunking_quality"]["element_coverage_status"] == "complete"
    assert body["chunking_quality"]["source_element_count"] > 0
    assert body["chunking_quality"]["covered_element_count"] == body["chunking_quality"]["source_element_count"]
    assert body["chunking_quality"]["uncovered_element_count"] == 0
    assert body["chunking_quality"]["provenance_missing_count"] == 0
    assert body["chunking_quality"]["retrieval_provenance_missing_count"] == 0
    assert body["chunk_preview_limit"] == 100
    assert body["chunk_preview_count"] == body["chunk_count"]
    assert body["chunk_type_counts"]["clause_group"] >= 1
    assert body["chunk_role_counts"]["retrieval"] >= 1
    group = next(chunk for chunk in body["chunks"] if chunk["metadata"].get("clause_title") == "4. 破坏学校管理秩序行为")
    assert group["metadata"]["chunk_type"] == "clause_group"
    assert group["metadata"]["violation_level"] == "category_2"
    assert group["metadata"]["clause_range"] == "4.1-4.3"
    assert group["metadata"]["element_ids"]
    assert group["metadata"]["element_range"]["start"] <= group["metadata"]["element_range"]["end"]
    assert group["heading_path"] == ["员工纪律制度", "二类违规行为", "4. 破坏学校管理秩序行为"]
    assert "5.1上课迟到" not in group["text"]
    action = next(chunk for chunk in body["chunks"] if chunk["metadata"].get("action_target") == "category_2")
    assert action["metadata"]["chunk_type"] == "action_clause"
    assert action["metadata"]["element_ids"]
    assert action["metadata"]["element_range"]["start"] <= action["metadata"]["element_range"]["end"]
    assert action["heading_path"] == ["员工纪律制度", "五、违规行为相应处理", "1.2 二类违规行为"]


def test_admin_document_preview_rejects_blank_input():
    client = TestClient(create_app(chat_runner=lambda query, top_k: {}))

    response = client.post(
        "/api/admin/document-preview",
        json={"source_name": "空文档", "file_name": "empty.txt", "content_type": "text/plain", "text": "  "},
    )

    assert response.status_code == 422
    assert "text must contain non-whitespace content" in response.text


def test_chat_endpoint_runs_real_demo_runner_for_colloquial_policy_query():
    def demo_runner(query: str, top_k: int):
        return run_chat_trace(query, embedding_client=DeterministicEmbeddingClient(), store=None, top_k=top_k)

    client = TestClient(create_app(chat_runner=demo_runner))

    response = client.post("/api/chat", json={"message": "骂人有什么处罚", "top_k": 5})

    assert response.status_code == 200
    body = response.json()
    assert "语言不得体" in body["answer"]
    assert "如果满足条款条件" in body["answer"]
    assert "引起投诉" in body["answer"]
    assert body["results"][0]["citation"]["url"] == "https://example.com/policyDetail/16"
    understanding = next(step for step in body["steps"] if step["key"] == "query_understanding")
    assert "并引起投诉" in understanding["details"]["missing_conditions"]


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
