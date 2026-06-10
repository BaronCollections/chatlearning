import pytest

from enterprise_rag_mvp.models import PolicyChunk, SearchResult
from enterprise_rag_mvp.trace_pipeline import run_chat_trace


EXPECTED_STEP_KEYS = [
    "request_intake",
    "input_guardrails",
    "normalize_text",
    "query_understanding",
    "query_rewrite",
    "tokenize",
    "query_embedding",
    "retrieval_plan",
    "initial_retrieval",
    "rerank",
    "evidence_quality",
    "answer_and_observe",
]


class FakeEmbeddingClient:
    def tokenize(self, text: str):
        return {
            "text": text,
            "tokens": list(text),
            "token_ids": list(range(len(text))),
            "token_count": len(text),
            "tokenizer": "fake-char-tokenizer",
        }

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "年假" in text or "年休假" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "迟到" in text:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def _step(response: dict, key: str) -> dict:
    return next(step for step in response["steps"] if step["key"] == key)


def test_run_chat_trace_returns_answer_steps_and_memory_results():
    response = run_chat_trace(
        " 员工年假规则是什么？ ",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=2,
    )

    assert response["query"] == "员工年假规则是什么？"
    assert "员工休假管理办法" in response["answer"]
    assert response["retrieval_mode"] == "in_memory_demo"
    assert response["results"][0]["chunk_id"] == "leave-annual-001"
    assert response["results"][0]["citation"]["citation_id"] == "[1]"
    assert "相关来源" in response["answer"]

    step_keys = [step["key"] for step in response["steps"]]
    assert step_keys == EXPECTED_STEP_KEYS
    assert response["steps"][5]["details"]["token_count"] > 0
    assert response["steps"][6]["details"]["dimension"] == 3
    for step in response["steps"]:
        assert {"key", "title", "summary", "details", "duration_ms", "status", "execution_mode", "children"}.issubset(step)


def test_run_chat_trace_returns_expandable_execution_tree_details():
    response = run_chat_trace(
        "  员工\t年假   规则是什么？  ",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=2,
    )

    preprocess = _step(response, "normalize_text")
    assert preprocess["execution_mode"] == "sequential"
    assert [child["key"] for child in preprocess["children"]] == [
        "trim_whitespace",
        "collapse_whitespace",
        "preserve_semantics_check",
    ]
    assert preprocess["children"][0]["details"]["tool"] == "Python str.strip()"
    assert preprocess["children"][0]["details"]["input"] == "  员工\t年假   规则是什么？  "
    assert preprocess["children"][1]["details"]["tool"] == "Python str.split() + str.join()"
    assert preprocess["details"]["normalized_query"] == "员工 年假 规则是什么？"

    tokenize = _step(response, "tokenize")
    assert tokenize["details"]["input_text"] == "员工 年假 规则是什么？"
    assert tokenize["details"]["token_table"][:3] == [
        {"index": 0, "token": "员", "token_id": 0},
        {"index": 1, "token": "工", "token_id": 1},
        {"index": 2, "token": " ", "token_id": 2},
    ]
    assert tokenize["details"]["why_this_tool"]["selected"] == "BGE-M3 tokenizer"

    embedding = _step(response, "query_embedding")
    assert embedding["details"]["model_choice"]["selected"] == "BGE-M3"
    alternative_names = {item["name"] for item in embedding["details"]["model_choice"]["alternatives"]}
    assert {"OpenAI text-embedding-3", "BM25 keyword search"}.issubset(alternative_names)

    retrieval = _step(response, "initial_retrieval")
    assert retrieval["execution_mode"] == "branch"
    assert retrieval["details"]["tool_choice"]["selected"] == "PostgreSQL + pgvector"
    assert any(child["key"] == "in_memory_fallback" for child in retrieval["children"])


def test_run_chat_trace_explains_query_rewrite_rerank_quality_and_observability():
    response = run_chat_trace(
        "员工年假规则是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=2,
    )

    understanding = _step(response, "query_understanding")
    assert understanding["details"]["intent"] == "rule_lookup"
    assert understanding["details"]["policy_category_hint"] == "leave"
    assert understanding["details"]["term_definitions"][0]["term"]

    rewrite = _step(response, "query_rewrite")
    assert rewrite["details"]["original_query"] == "员工年假规则是什么？"
    assert "年休假" in rewrite["details"]["expanded_query"]
    assert rewrite["details"]["semantic_drift_check"]["status"] == "ok"

    retrieval_plan = _step(response, "retrieval_plan")
    assert retrieval_plan["details"]["candidate_limit"] >= 2
    assert "dense_vector" in retrieval_plan["details"]["enabled_channels"]

    rerank = _step(response, "rerank")
    assert rerank["details"]["tool"] == "deterministic lexical rerank fallback"
    assert rerank["details"]["rerank_comparison"]
    assert {"rank_before", "rank_after", "rerank_score", "reason"}.issubset(
        rerank["details"]["rerank_comparison"][0]
    )

    evidence = _step(response, "evidence_quality")
    check_names = {check["name"] for check in evidence["details"]["quality_checks"]}
    assert {"relevance_threshold", "source_metadata", "freshness_conflict", "context_assembly"}.issubset(check_names)
    assert evidence["details"]["context_blocks"]

    observe = _step(response, "answer_and_observe")
    observation_types = {item["type"] for item in observe["details"]["langfuse_observations"]}
    assert {"trace", "span", "retriever", "embedding", "evaluator", "generation", "score", "feedback_hook"}.issubset(
        observation_types
    )


def test_run_chat_trace_rejects_blank_query_after_normalization():
    with pytest.raises(ValueError, match="non-whitespace"):
        run_chat_trace(" \t\n ", embedding_client=FakeEmbeddingClient(), store=None, top_k=1)


def test_run_chat_trace_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k"):
        run_chat_trace("员工年假规则是什么？", embedding_client=FakeEmbeddingClient(), store=None, top_k=0)


def test_run_chat_trace_uses_pgvector_store_when_available():
    class FakeStore:
        def search(self, query_embedding: list[float], *, top_k: int):
            chunk = PolicyChunk(
                chunk_id="store-hit-001",
                doc_id="store-doc",
                block_id="article-1",
                text="数据库返回的制度片段。",
                heading_path=["数据库制度", "第一条"],
                metadata={"source": "db.md", "page": 1},
            )
            return [SearchResult(chunk=chunk, distance=0.01)]

    response = run_chat_trace(
        "数据库检索测试",
        embedding_client=FakeEmbeddingClient(),
        store=FakeStore(),
        top_k=1,
    )

    assert response["retrieval_mode"] == "pgvector"
    assert response["results"][0]["chunk_id"] == "store-hit-001"
    retrieval = _step(response, "initial_retrieval")
    assert retrieval["details"]["framework"] == "PostgreSQL + pgvector"
    assert any(child["key"] == "pgvector_search" for child in retrieval["children"])


def test_run_chat_trace_returns_policy_citations_with_links_for_multiple_hits():
    class FakeStore:
        def search(self, query_embedding: list[float], *, top_k: int):
            first = PolicyChunk(
                chunk_id="yungu-policy-2374-001",
                doc_id="yungu-2374",
                block_id="body-1",
                text="员工年假规则以学校 HR 政策及知识库中的年休假条款为准。",
                heading_path=["HR政策及知识库", "员工年休假条款"],
                metadata={
                    "source": "yungu_policy_system",
                    "import_information_id": 2374,
                    "title": "员工年休假条款",
                    "policy_category_type_name": "HR政策及知识库",
                    "publish_date": "2026-04-09 11:09:32",
                },
            )
            second = PolicyChunk(
                chunk_id="yungu-policy-2401-001",
                doc_id="yungu-2401",
                block_id="body-2",
                text="新员工年假、适用对象和审批口径需要结合考勤制度一起判断。",
                heading_path=["HR政策及知识库", "员工假勤补充说明"],
                metadata={
                    "source": "yungu_policy_system",
                    "import_information_id": 2401,
                    "title": "员工假勤补充说明",
                    "policy_category_type_name": "HR政策及知识库",
                    "publish_date": "2026-05-01 09:00:00",
                },
            )
            return [SearchResult(chunk=first, distance=0.01), SearchResult(chunk=second, distance=0.02)]

    response = run_chat_trace(
        "员工年假规则是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=FakeStore(),
        top_k=2,
    )

    citations = [result["citation"] for result in response["results"]]
    assert [citation["citation_id"] for citation in citations] == ["[1]", "[2]"]
    assert citations[0]["title"] == "员工年休假条款"
    assert citations[0]["url"] == "https://work.yungu.org/policyDetail/2374"
    assert citations[0]["category"] == "HR政策及知识库"
    assert "相关来源" in response["answer"]
    assert "[1]" in response["answer"] and "[2]" in response["answer"]
    assert "https://work.yungu.org/policyDetail/2374" in response["answer"]

    evidence = _step(response, "evidence_quality")
    first_block = evidence["details"]["context_blocks"][0]
    assert first_block["citation"]["url"] == citations[0]["url"]
    assert first_block["citation"]["import_information_id"] == 2374
