import pytest

from enterprise_rag_mvp.models import PolicyChunk, SearchResult
from enterprise_rag_mvp.pgvector_store import _hybrid_term_groups
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


def test_hybrid_term_groups_prioritize_clause_terms_before_section_terms():
    primary, secondary, query_terms = _hybrid_term_groups(
        "弄虚作假行为是什么？",
        {
            "target_terms": ["弄虚作假", "弄虚作假行为", "虚假报销"],
            "target_section": "二类违规行为",
            "target_clause": "4. 弄虚作假行为",
        },
    )

    assert primary[:3] == ["弄虚作假", "弄虚作假行为", "虚假报销"]
    assert "4. 弄虚作假行为" in primary
    assert secondary == ["二类违规行为"]
    assert query_terms == ["弄虚作假行为是什么"]


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
    assert rerank["details"]["tool"] == "deterministic lexical + scope-aware rerank fallback"
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


def _discipline_chunk(*, chunk_id="discipline-rough-1", text=None, metadata=None):
    rough_text = text or (
        "3. 侵犯学校权益行为 3.1未经学校授权发言，造成不良影响。 "
        "4. 弄虚作假行为 4.1向学校隐瞒或有意提交虚假的重大信息。 "
        "4.2 在老师个人及学生各级考试各类评选活动中弄虚作假，营私舞弊并造成严重恶劣影响。 "
        "4.3虚假报销，例如报销未发生的费用或以虚假理由报销费用等。 "
        "4.4 其他弄虚作假给学校造成严重不良影响或经济、声誉损失的行为。 "
        "5. 破坏学校管理秩序行为 5.1旷工少于三天。"
    )
    base_metadata = {
        "source": "yungu_policy_system",
        "import_information_id": 16,
        "title": "云谷人守则-员工纪律制度",
        "policy_category_type_name": "云谷人守则",
        "section_title": "二类违规行为",
        "source_url": "https://work.yungu.org/policyDetail/16",
    }
    if metadata:
        base_metadata.update(metadata)
    return PolicyChunk(
        chunk_id=chunk_id,
        doc_id="yungu-policy-16",
        block_id=chunk_id,
        text=rough_text,
        heading_path=["云谷人守则", "云谷人守则-员工纪律制度"],
        metadata=base_metadata,
    )


def test_exact_clause_query_uses_hybrid_search_and_scopes_answer_to_clause_group():
    class HybridStore:
        def __init__(self):
            self.calls = []

        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            self.calls.append({"query_text": query_text, "metadata_filters": metadata_filters, "top_k": top_k})
            return [SearchResult(chunk=_discipline_chunk(), distance=0.2)]

    store = HybridStore()
    response = run_chat_trace(
        "弄虚作假行为是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=store,
        top_k=3,
    )

    assert store.calls
    assert store.calls[0]["metadata_filters"]["retrieval_intent"] == "exact_policy_lookup"
    assert "exact_match" in _step(response, "retrieval_plan")["details"]["enabled_channels"]
    assert "sparse_keyword" in _step(response, "retrieval_plan")["details"]["enabled_channels"]
    assert "4.1向学校隐瞒" in response["answer"]
    assert "4.4 其他弄虚作假" in response["answer"]
    assert "3. 侵犯学校权益行为" not in response["answer"]
    assert "5. 破坏学校管理秩序行为" not in response["answer"]
    assert "检索方式：pgvector hybrid" in response["answer"]
    assert "内存向量检索 demo" not in response["answer"]
    assert response["results"][0]["citation"]["url"] == "https://work.yungu.org/policyDetail/16"

    evidence = _step(response, "evidence_quality")
    assert evidence["details"]["scope_guard"]["status"] == "ok"
    assert evidence["details"]["context_blocks"][0]["scope"]["applied"] is True




def test_exact_clause_query_returns_no_answer_when_direct_evidence_is_missing():
    class IrrelevantStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="mentor-unrelated",
                        doc_id="yungu-policy-3000",
                        block_id="mentor-unrelated",
                        text="导师制说明，讨论学生个别支持、家校联结和班级规划。",
                        heading_path=["中小学教育教学相关制度", "导师制"],
                        metadata={
                            "source": "yungu_policy_system",
                            "import_information_id": 3000,
                            "title": "杭州云谷学校导师制",
                            "policy_category_type_name": "中小学教育教学相关制度",
                            "source_url": "https://work.yungu.org/policyDetail/3000",
                        },
                    ),
                    distance=0.01,
                )
            ]

    response = run_chat_trace(
        "弄虚作假行为是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=IrrelevantStore(),
        top_k=3,
    )

    assert response["results"] == []
    assert "没有在当前制度样本中检索到足够相关的内容" in response["answer"]
    evidence = _step(response, "evidence_quality")
    assert evidence["details"]["target_evidence_filter"]["applied"] is True
    assert evidence["details"]["target_evidence_filter"]["output_count"] == 0

def test_exact_section_query_prefers_definition_over_cross_reference():
    reference_text = (
        "薪酬制度补充说明。二类违规行为，具体参见《云谷人守则——员工纪律制度》。"
        "员工对薪酬收入有疑义，请联系人力资源部申请复核。"
    )
    definition_text = (
        "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等"
        "致使学校经济、形象、声誉遭受严重损害的行为，是比较严重的违规行为。"
        "1.师德师风相关的违规行为 2. 违反保密义务行为 3. 侵犯学校权益行为 4. 弄虚作假行为 "
        "（三）三类违规行为 三类违规行为：指一般的违规行为。"
    )

    class CrossReferenceStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [
                SearchResult(
                    chunk=_discipline_chunk(
                        chunk_id="salary-reference",
                        text=reference_text,
                        metadata={
                            "title": "杭州云谷学校薪酬制度",
                            "policy_category_type_name": "HR政策及知识库",
                            "import_information_id": 192,
                            "source_url": "https://work.yungu.org/policyDetail/192",
                        },
                    ),
                    distance=0.01,
                ),
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-definition", text=definition_text), distance=0.2),
            ]

    response = run_chat_trace(
        "二类违规是什么",
        embedding_client=FakeEmbeddingClient(),
        store=CrossReferenceStore(),
        top_k=3,
    )

    assert "二类违规行为：指违反师德师风" in response["answer"]
    assert "具体参见" not in response["answer"]
    assert "杭州云谷学校薪酬制度" not in response["answer"]
    assert "（三）三类违规行为" not in response["answer"]
    assert response["results"][0]["citation"]["url"] == "https://work.yungu.org/policyDetail/16"
    evidence = _step(response, "evidence_quality")
    assert evidence["details"]["scope_guard"]["status"] == "ok"

def test_exact_section_query_deduplicates_sources_and_excludes_competing_sections():
    section_text = (
        "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等致使学校经济、形象、声誉遭受严重损害的行为，是比较严重的违规行为。 "
        "1.师德师风相关的违规行为 2. 违反保密义务行为 3. 侵犯学校权益行为 4. 弄虚作假行为 5. 破坏学校管理秩序行为 "
        "（三）三类违规行为 三类违规行为：指一般的违规行为。"
    )

    class DuplicateStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-a", text=section_text), distance=0.1),
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-b", text=section_text), distance=0.11),
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-c", text=section_text), distance=0.12),
            ]

    response = run_chat_trace(
        "二类违规是什么",
        embedding_client=FakeEmbeddingClient(),
        store=DuplicateStore(),
        top_k=3,
    )

    assert "二类违规行为：指违反师德师风" in response["answer"]
    assert "（三）三类违规行为" not in response["answer"]
    assert "三类违规行为：指一般" not in response["answer"]
    assert len(response["results"]) == 1
    assert response["results"][0]["citation"]["url"] == "https://work.yungu.org/policyDetail/16"
    evidence = _step(response, "evidence_quality")
    assert evidence["details"]["citation_merge"]["removed_duplicates"] == 2
