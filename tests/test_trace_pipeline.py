import pytest

from enterprise_rag_mvp.models import PolicyChunk, SearchResult
from enterprise_rag_mvp.pgvector_store import _hybrid_term_groups
from enterprise_rag_mvp.policy_rule_resolver import build_policy_lookup_spec
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
            "rule_search_terms": ["4.3虚假报销"],
        },
    )

    assert primary[:3] == ["弄虚作假", "弄虚作假行为", "虚假报销"]
    assert "4. 弄虚作假行为" in primary
    assert "4.3虚假报销" in primary
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
    assert understanding["details"]["query_schema"]["answer_aspect"] == "definition"
    assert understanding["details"]["intent_schema"]["target_object"] == "年休假"
    assert "table_evidence" in understanding["details"]["intent_schema"]["required_evidence_types"]
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


def test_run_chat_trace_can_use_external_cross_encoder_reranker():
    class FakeStore:
        def search(self, query_embedding, top_k):
            return [
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="candidate-a",
                        doc_id="doc-a",
                        block_id="a",
                        text="普通候选片段，语义相关但不能直接回答。",
                        heading_path=["制度A"],
                        metadata={"source": "sample", "title": "制度A"},
                    ),
                    distance=0.01,
                ),
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="candidate-b",
                        doc_id="doc-b",
                        block_id="b",
                        text="员工年假规则：员工每年可按制度申请年休假。",
                        heading_path=["制度B"],
                        metadata={"source": "sample", "title": "制度B"},
                    ),
                    distance=0.9,
                ),
            ]

    class FakeRerankerClient:
        provider = "fake-cross-encoder"

        def rerank(self, *, query, documents):
            assert query == "员工年假规则是什么？"
            assert len(documents) == 2
            return [0.0, 5.0]

    response = run_chat_trace(
        "员工年假规则是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=FakeStore(),
        top_k=2,
        reranker_client=FakeRerankerClient(),
    )

    assert response["results"][0]["chunk_id"] == "candidate-b"
    rerank = _step(response, "rerank")
    assert rerank["details"]["reranker_source"] == "fake-cross-encoder"
    assert rerank["details"]["rerank_comparison"][0]["reranker_score"] == 5.0


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
                chunk_id="company-policy-2374-001",
                doc_id="company-2374",
                block_id="body-1",
                text="员工年假规则以学校 HR 政策及知识库中的年休假条款为准。",
                heading_path=["HR政策及知识库", "员工年休假条款"],
                metadata={
                    "source": "company_policy_system",
                    "import_information_id": 2374,
                    "title": "员工年休假条款",
                    "policy_category_type_name": "HR政策及知识库",
                    "publish_date": "2026-04-09 11:09:32",
                },
            )
            second = PolicyChunk(
                chunk_id="company-policy-2401-001",
                doc_id="company-2401",
                block_id="body-2",
                text="新员工年假、适用对象和审批口径需要结合考勤制度一起判断。",
                heading_path=["HR政策及知识库", "员工假勤补充说明"],
                metadata={
                    "source": "company_policy_system",
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
    assert citations[0]["url"] == "https://example.com/policyDetail/2374"
    assert citations[0]["category"] == "HR政策及知识库"
    assert "相关来源" in response["answer"]
    assert "[1]" in response["answer"] and "[2]" in response["answer"]
    assert "https://example.com/policyDetail/2374" in response["answer"]

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
        "source": "company_policy_system",
        "import_information_id": 16,
        "title": "***公司人守则-员工纪律制度",
        "policy_category_type_name": "***公司人守则",
        "section_title": "二类违规行为",
        "source_url": "https://example.com/policyDetail/16",
    }
    if metadata:
        base_metadata.update(metadata)
    return PolicyChunk(
        chunk_id=chunk_id,
        doc_id="company-policy-16",
        block_id=chunk_id,
        text=rough_text,
        heading_path=["***公司人守则", "***公司人守则-员工纪律制度"],
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
    assert response["results"][0]["citation"]["url"] == "https://example.com/policyDetail/16"

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
                        doc_id="company-policy-3000",
                        block_id="mentor-unrelated",
                        text="导师制说明，讨论学生个别支持、家校联结和班级规划。",
                        heading_path=["中小学教育教学相关制度", "导师制"],
                        metadata={
                            "source": "company_policy_system",
                            "import_information_id": 3000,
                            "title": "杭州***公司学校导师制",
                            "policy_category_type_name": "中小学教育教学相关制度",
                            "source_url": "https://example.com/policyDetail/3000",
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
        "薪酬制度补充说明。二类违规行为，具体参见《***公司人守则——员工纪律制度》。"
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
                            "title": "杭州***公司学校薪酬制度",
                            "policy_category_type_name": "HR政策及知识库",
                            "import_information_id": 192,
                            "source_url": "https://example.com/policyDetail/192",
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
    assert "杭州***公司学校薪酬制度" not in response["answer"]
    assert "（三）三类违规行为" not in response["answer"]
    assert "5.1" not in response["answer"]
    assert "5.2" not in response["answer"]
    assert response["results"][0]["citation"]["url"] == "https://example.com/policyDetail/16"
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
    assert "1.师德师风" not in response["answer"]
    assert len(response["results"]) == 1
    assert response["results"][0]["citation"]["url"] == "https://example.com/policyDetail/16"
    evidence = _step(response, "evidence_quality")
    assert evidence["details"]["citation_merge"]["removed_duplicates"] == 2


def test_in_memory_demo_section_definition_does_not_expand_child_clause():
    response = run_chat_trace(
        "二类违规是什么",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "二类违规行为：指违反师德师风" in response["answer"]
    assert "5. 破坏学校管理秩序行为" not in response["answer"]
    assert "5.1渎职" not in response["answer"]
    assert "5.2旷工" not in response["answer"]
    assert response["answer_sources"]


def test_negative_non_question_policy_assertion_does_not_retrieve_evidence():
    response = run_chat_trace(
        "我没有违规",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "请描述具体行为" in response["answer"]
    assert "破坏学校管理秩序行为" not in response["answer"]
    assert response["results"] == []
    assert response["answer_sources"] == []
    understanding = _step(response, "query_understanding")
    assert understanding["details"]["intent"] == "unsupported_policy_assertion"


def test_disciplinary_action_scope_removes_next_numbered_section_prefix():
    penalty_text = (
        "五、违规行为相应处理 1.1一类违规行为：解除劳动合同。 "
        "1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪并取消当年年终奖激励资格。 "
        "1.3三类违规行为：予以书面或口头警告。"
    )

    class PenaltyStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [SearchResult(chunk=_discipline_chunk(chunk_id="discipline-penalty-numbered", text=penalty_text), distance=0.2)]

    response = run_chat_trace(
        "二类违规的处罚是什么",
        embedding_client=FakeEmbeddingClient(),
        store=PenaltyStore(),
        top_k=3,
    )

    assert "二类违规行为：予以记过处分" in response["answer"]
    assert "1.3" not in response["answer"]
    assert "三类违规行为：予以书面或口头警告" not in response["answer"]


def test_behavior_disciplinary_action_combines_classification_and_penalty_evidence():
    classification_text = (
        "（二）二类违规行为 4. 弄虚作假行为 "
        "4.1向学校隐瞒或有意提交虚假的重大信息。"
        "4.2在老师个人及学生各级考试各类评选活动中弄虚作假。"
        "4.3虚假报销，例如报销未发生的费用或以虚假理由报销费用等。"
        "4.4其他弄虚作假给学校造成严重不良影响或经济、声誉损失的行为。"
        "5. 破坏学校管理秩序行为 5.1旷工少于三天。"
    )
    penalty_text = (
        "五、违规行为相应处理 "
        "1.1一类违规行为：处分生效当年年度绩效为低于期望，并解除劳动合同。"
        "1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪并取消当年年终奖激励资格，"
        "影响学年年度绩效，取消评优评先、外出交流学习资格，情节严重的并处降薪处分。"
        "1.3三类违规行为：予以书面或口头警告。"
    )
    broad_section_text = "（二）二类违规行为 二类违规行为：指比较严重的违规行为。1.师德师风相关行为。2.违反保密义务行为。"

    class BehaviorPenaltyStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-penalty", text=penalty_text), distance=0.05),
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-broad-section", text=broad_section_text), distance=0.08),
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-false-reimbursement", text=classification_text), distance=0.12),
            ]

    response = run_chat_trace(
        "虚假报销怎么处罚",
        embedding_client=FakeEmbeddingClient(),
        store=BehaviorPenaltyStore(),
        top_k=3,
    )

    assert "事实：虚假报销" in response["answer"]
    assert "属于二类违规行为中的弄虚作假行为（4.3虚假报销）" in response["answer"]
    assert "处理结果：" in response["answer"]
    assert "予以记过处分" in response["answer"]
    assert "一年内不得调薪" in response["answer"]
    assert "情节严重的并处降薪处分" in response["answer"]
    assert "1.3三类违规行为" not in response["answer"]
    assert response["results"][0]["chunk_id"] == "discipline-false-reimbursement"
    assert response["results"][1]["chunk_id"] == "discipline-penalty"


def test_behavior_classification_query_uses_structured_conclusion():
    salary_text = (
        "（二）二类违规行为 2. 违反保密义务行为 "
        "2.1非因工作需要获取、使用、泄露、传播保密信息。"
        "2.2其他违反数据安全规范等制度。"
        "2.3打听、讨论员工工资、奖金、津贴补贴等个人待遇信息。"
        "3. 侵犯学校权益行为 3.1未经授权发表言论。"
    )

    class SalaryStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [SearchResult(chunk=_discipline_chunk(chunk_id="discipline-salary", text=salary_text), distance=0.05)]

    response = run_chat_trace(
        "打听工资属于什么违规",
        embedding_client=FakeEmbeddingClient(),
        store=SalaryStore(),
        top_k=3,
    )

    assert "事实：打听工资" in response["answer"]
    assert "属于二类违规行为中的违反保密义务行为（2.3打听工资）" in response["answer"]
    assert "3. 侵犯学校权益行为" not in response["answer"]



def test_absenteeism_duration_query_returns_matching_penalty_rule():
    absenteeism_text = (
        "（三） 旷工 凡符合以下情况之一的应视为旷工："
        "1. 未提前提交请假申请或紧急情况下未口头征得主管同意擅自不出勤或擅自离岗的；"
        "注：连续旷工3个工作日以下的，扣除旷工期间工资，并给予记过处分；"
        "连续旷工3个工作日及以上的，或一年内累计两次及以上旷工的，扣除旷工期间工资，并给予辞退处分。"
    )
    classification_text = (
        "7.6 擅自携带违禁品进入工作场所。任何其他经学校制度委员会确定为一类违规行为的行为。"
        "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等"
        "致使学校经济、形象、声誉遭受严重损害的行为。"
        "4. 破坏学校管理秩序行为 4.1渎职给学校造成较大损失。5.2旷工少于三天。"
        "（三）三类违规行为 三类违规行为：指一般的违规行为。"
    )
    student_text = (
        "学生红黄灯行为处理办法。严重违纪可给予记过处分、停课、停学等教育惩戒措施。"
    )

    class AbsenteeismStore:
        def __init__(self):
            self.calls = []

        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            self.calls.append({"query_text": query_text, "metadata_filters": metadata_filters})
            return [
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="student-discipline",
                        doc_id="student-policy",
                        block_id="student-discipline",
                        text=student_text,
                        heading_path=["***公司学校小学部红黄灯行为及处理办法"],
                        metadata={"title": "***公司学校小学部红黄灯行为及处理办法", "policy_category_type_name": "中小学教育教学相关制度"},
                    ),
                    distance=0.05,
                ),
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="discipline-classification",
                        doc_id="company-policy-16",
                        block_id="chunk-0004",
                        text=classification_text,
                        heading_path=["***公司人守则-员工纪律制度"],
                        metadata={
                            "source": "company_policy_system",
                            "import_information_id": 16,
                            "title": "***公司人守则-员工纪律制度",
                            "policy_category_type_name": "***公司人守则",
                            "source_url": "https://example.com/policyDetail/16",
                        },
                    ),
                    distance=0.18,
                ),
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="worktime-absenteeism",
                        doc_id="company-policy-11",
                        block_id="chunk-0001",
                        text=absenteeism_text,
                        heading_path=["***公司人守则-工作时间及假期管理制度"],
                        metadata={
                            "source": "company_policy_system",
                            "import_information_id": 11,
                            "title": "***公司人守则-工作时间及假期管理制度",
                            "policy_category_type_name": "***公司人守则",
                            "source_url": "https://example.com/policyDetail/11",
                        },
                    ),
                    distance=0.2,
                ),
            ]

    store = AbsenteeismStore()
    response = run_chat_trace(
        "我旷工两天会受到什么处罚",
        embedding_client=FakeEmbeddingClient(),
        store=store,
        top_k=3,
    )

    filters = store.calls[0]["metadata_filters"]
    assert filters["target_behavior"] == "absenteeism"
    assert filters["behavior_duration"] == {"value": 2, "unit": "day"}
    assert "连续旷工3个工作日以下" in filters["target_terms"]
    assert "旷工少于三天" in filters["target_terms"]
    assert "二类违规行为" in filters["target_terms"]
    rewrite = _step(response, "query_rewrite")
    assert "连续旷工3个工作日以下" in rewrite["details"]["expanded_query"]
    assert "事实：旷工 2 天" in response["answer"]
    assert "规则匹配：2 < 3" in response["answer"]
    assert "属于二类违规行为" in response["answer"]
    assert "属于一类违规行为" not in response["answer"]
    assert "三类违规行为" not in response["answer"]
    assert "破坏学校管理秩序行为" in response["answer"]
    assert "5.2旷工少于三天" in response["answer"]
    assert "处理结果：" in response["answer"]
    assert "1. 扣除旷工期间工资" in response["answer"]
    assert "2. 给予记过处分" in response["answer"]
    assert "不确定性提醒" in response["answer"]
    assert "连续旷工3个工作日及以上" not in response["answer"]
    assert "辞退处分" not in response["answer"]
    assert "学生红黄灯行为处理办法" not in response["answer"]
    assert response["results"][0]["chunk_id"] == "worktime-absenteeism"
    assert response["results"][1]["chunk_id"] == "discipline-classification"
    rerank = _step(response, "rerank")
    assert "命中行为对象" in rerank["details"]["rerank_comparison"][0]["reason"]
    evidence = _step(response, "evidence_quality")
    assert evidence["details"]["target_evidence_filter"]["output_count"] == 2
    evidence_types = {item["evidence_type"] for item in evidence["details"]["target_evidence_filter"]["evidence_classifications"]}
    assert "direct_behavior_evidence" in evidence_types
    general_types = {
        item["general_evidence_assessment"]["evidence_type"]
        for item in evidence["details"]["target_evidence_filter"]["evidence_classifications"]
    }
    assert "action_evidence" in general_types
    observe = _step(response, "answer_and_observe")
    assert observe["details"]["answer_plan"]["answer_type"] == "disciplinary_action"
    assert observe["details"]["answer_plan"]["sections"] == ["fact", "rule_match", "classification", "action", "citations", "uncertainty"]
    understanding = _step(response, "query_understanding")
    assert understanding["details"]["query_schema"]["target_object"]["key"] == "absenteeism"
    assert understanding["details"]["rule_resolution"]["matched_rule"] == "连续旷工3个工作日以下"
    assert understanding["details"]["rule_resolution"]["comparison"] == "2 < 3"



def test_absenteeism_three_days_answer_does_not_reuse_under_three_classification():
    penalty_text = (
        "（三） 旷工 注：连续旷工3个工作日以下的，扣除旷工期间工资，并给予记过处分；"
        "连续旷工3个工作日及以上的，或一年内累计两次及以上旷工的，扣除旷工期间工资，并给予辞退处分。"
    )
    under_three_classification = (
        "（二）二类违规行为 5. 破坏学校管理秩序行为 5.2旷工少于三天。"
    )

    class AbsenteeismThreeDayStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            return [
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="worktime-absenteeism",
                        doc_id="company-policy-11",
                        block_id="chunk-0001",
                        text=penalty_text,
                        heading_path=["***公司人守则-工作时间及假期管理制度"],
                        metadata={"source": "company_policy_system", "import_information_id": 11, "title": "***公司人守则-工作时间及假期管理制度"},
                    ),
                    distance=0.1,
                ),
                SearchResult(
                    chunk=PolicyChunk(
                        chunk_id="discipline-classification-under-three",
                        doc_id="company-policy-16",
                        block_id="chunk-0004",
                        text=under_three_classification,
                        heading_path=["***公司人守则-员工纪律制度"],
                        metadata={"source": "company_policy_system", "import_information_id": 16, "title": "***公司人守则-员工纪律制度"},
                    ),
                    distance=0.2,
                ),
            ]

    response = run_chat_trace(
        "旷工三天会怎样",
        embedding_client=FakeEmbeddingClient(),
        store=AbsenteeismThreeDayStore(),
        top_k=3,
    )

    assert "事实：旷工 3 天" in response["answer"]
    assert "规则匹配：3 >= 3" in response["answer"]
    assert "给予辞退处分" in response["answer"]
    assert "5.2旷工少于三天" not in response["answer"]
    assert "属于二类违规行为" not in response["answer"]


def test_absenteeism_three_days_query_uses_rule_resolver_for_dismissal():
    spec = build_policy_lookup_spec("旷工三天会怎样")

    assert spec["target_behavior"] == "absenteeism"
    assert spec["behavior_threshold"] == "continuous_absence_3_or_more_workdays"
    assert spec["rule_resolution"]["matched_rule"] == "连续旷工3个工作日及以上"
    assert spec["rule_resolution"]["comparison"] == "3 >= 3"
    assert "辞退处分" in spec["expected_evidence"]



def test_disciplinary_action_query_prefers_penalty_process_over_definition():
    definition_text = (
        "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等"
        "致使学校经济、形象、声誉遭受严重损害的行为，是比较严重的违规行为。"
        "1.师德师风相关的违规行为 2. 违反保密义务行为。"
    )
    penalty_text = (
        "（二）处分流程 1. 二类、三类违规由学部校园长作出最终处理决定；"
        "一类违规行为由学校纪律制度委员会结合调查结果、调查方处理建议、法务顾问建议，根据本制度规定作出最终处理决定。"
        "2. 最终处理决定由违规员工的主管及HRG负责向员工传达，听取员工反馈，安排员工签署书面处理决定。"
        "3. 违规员工如对处理决定有异议，有权提出申诉，申诉期间处理决定维持不变。"
    )

    class PenaltyStore:
        def __init__(self):
            self.calls = []

        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            self.calls.append({"query_text": query_text, "metadata_filters": metadata_filters})
            return [
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-definition", text=definition_text), distance=0.05),
                SearchResult(chunk=_discipline_chunk(chunk_id="discipline-penalty", text=penalty_text), distance=0.2),
            ]

    store = PenaltyStore()
    response = run_chat_trace(
        "二类违规的处罚是什么",
        embedding_client=FakeEmbeddingClient(),
        store=store,
        top_k=3,
    )

    filters = store.calls[0]["metadata_filters"]
    assert filters["asked_aspect"] == "disciplinary_action"
    assert "处分流程" in filters["target_terms"]
    assert "违规处理" in filters["target_terms"]
    rewrite = _step(response, "query_rewrite")
    assert "处分流程" in rewrite["details"]["expanded_query"]
    assert "违规处理" in rewrite["details"]["expanded_query"]
    assert "二类、三类违规由学部校园长作出最终处理决定" in response["answer"]
    assert "二类违规行为：指违反师德师风" not in response["answer"]
    assert response["results"][0]["chunk_id"] == "discipline-penalty"
    rerank = _step(response, "rerank")
    assert rerank["details"]["rerank_comparison"][0]["chunk_id"] == "discipline-penalty"
    assert "命中问题面" in rerank["details"]["rerank_comparison"][0]["reason"]


def test_every_trace_step_exposes_data_flow_input_and_output():
    response = run_chat_trace(
        "员工年假规则是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=2,
    )

    def assert_data_flow(step):
        data_flow = step["details"].get("data_flow")
        assert data_flow, step["key"]
        assert "input" in data_flow, step["key"]
        assert "output" in data_flow, step["key"]
        for child in step.get("children") or []:
            assert_data_flow(child)

    for step in response["steps"]:
        assert_data_flow(step)

    assert _step(response, "request_intake")["details"]["data_flow"]["input"]["raw_message"] == "员工年假规则是什么？"
    assert _step(response, "normalize_text")["details"]["data_flow"]["output"]["normalized_query"] == "员工年假规则是什么？"
    assert _step(response, "retrieval_plan")["details"]["data_flow"]["output"]["enabled_channels"] == ["dense_vector"]


def test_in_memory_demo_answers_absenteeism_duration_query():
    response = run_chat_trace(
        "我旷工两天会有什么事儿",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
    )

    assert "事实：旷工 2 天" in response["answer"]
    assert "规则匹配：2 < 3" in response["answer"]
    assert "连续旷工3个工作日以下" in response["answer"]
    assert "扣除旷工期间工资" in response["answer"]
    assert "给予记过处分" in response["answer"]
    assert "属于二类违规行为" in response["answer"]
    assert "链接：https://example.com/policyDetail/11" in response["answer"]
    assert "链接：https://example.com/policyDetail/16" in response["answer"]
    assert response["results"][0]["citation"]["url"] == "https://example.com/policyDetail/11"
    assert response["results"][1]["citation"]["url"] == "https://example.com/policyDetail/16"


def test_in_memory_demo_handles_absenteeism_penalty_typo_query():
    response = run_chat_trace(
        "我旷工两天会有有什么处罚",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
    )

    assert "事实：旷工 2 天" in response["answer"]
    assert "扣除旷工期间工资" in response["answer"]
    assert "给予记过处分" in response["answer"]


def test_in_memory_demo_answers_absenteeism_penalty_without_duration():
    response = run_chat_trace(
        "旷工会有什么处罚",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "没有在当前制度样本中检索到足够相关的内容" not in response["answer"]
    assert "事实：旷工" in response["answer"]
    assert "连续旷工3个工作日以下" in response["answer"]
    assert "扣除旷工期间工资" in response["answer"]
    assert "给予记过处分" in response["answer"]
    assert "连续旷工3个工作日及以上" in response["answer"]
    assert "给予辞退处分" in response["answer"]
    assert "如果能确认连续旷工天数" in response["answer"]
    assert "链接：https://example.com/policyDetail/11" in response["answer"]


@pytest.mark.parametrize("query", ["说脏话有什么处罚", "骂人有什么处罚"])
def test_in_memory_demo_maps_colloquial_abusive_language_to_policy_terms(query):
    response = run_chat_trace(
        query,
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "没有在当前制度样本中检索到足够相关的内容" not in response["answer"]
    assert "语言不得体" in response["answer"]
    assert "属于三类违规行为中的侵犯学校权益行为" in response["answer"]
    assert "予以书面或口头警告" in response["answer"]
    assert "如果满足条款条件" in response["answer"]
    assert "引起投诉" in response["answer"]
    assert "需要确认" in response["answer"]
    assert "链接：https://example.com/policyDetail/16" in response["answer"]
    understanding = _step(response, "query_understanding")
    assert "并引起投诉" in understanding["details"]["missing_conditions"]


def test_in_memory_demo_maps_teacher_ethics_query_to_policy_terms():
    response = run_chat_trace(
        "没有师德会有什么处罚",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "没有在当前制度样本中检索到足够相关的内容" not in response["answer"]
    assert "师德师风" in response["answer"]
    assert "属于二类违规行为中的师德师风相关的违规行为" in response["answer"]
    assert "予以记过处分" in response["answer"]
    assert "链接：https://example.com/policyDetail/16" in response["answer"]


def test_in_memory_demo_answers_annual_leave_days_from_work_year():
    response = run_chat_trace(
        "工作五年有几天年假",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
    )

    assert "结论" in response["answer"]
    assert "第五年" in response["answer"]
    assert "18天" in response["answer"]
    assert "带薪年假" in response["answer"]
    assert "适用于全体非教学老师" in response["answer"]
    assert "4. 病假" not in response["answer"]
    assert "链接：https://example.com/policyDetail/3" in response["answer"]
    assert response["results"][0]["chunk_id"] == "leave-annual-001"
    assert response["results"][0]["citation"]["url"] == "https://example.com/policyDetail/3"


def test_annual_leave_question_returns_context_for_follow_up_work_year():
    response = run_chat_trace(
        "我有几天年假",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
    )

    assert response["next_conversation_context"] == {
        "last_policy_category_hint": "leave",
        "last_target_object": "年休假",
        "last_answer_aspect": "annual_leave_days",
        "last_retrieval_intent": "semantic_policy_lookup",
    }


def test_annual_leave_follow_up_work_year_uses_previous_leave_context():
    first = run_chat_trace(
        "我有几天年假",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
    )
    response = run_chat_trace(
        "我工作8年",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
        conversation_context=first["next_conversation_context"],
    )

    assert "结论" in response["answer"]
    assert "工作8年" in response["answer"]
    assert "第六年及以后" in response["answer"]
    assert "20天" in response["answer"]
    assert "年假表" in response["answer"]
    assert response["results"][0]["chunk_id"] == "leave-annual-001"


def test_in_memory_demo_answers_three_day_absenteeism_with_violation_level():
    response = run_chat_trace(
        "旷工三天会怎样",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "事实：旷工 3 天" in response["answer"]
    assert "连续旷工3个工作日及以上" in response["answer"]
    assert "属于一类违规行为" in response["answer"]
    assert "给予辞退处分" in response["answer"]
    assert "链接：https://example.com/policyDetail/11" in response["answer"]
    assert "链接：https://example.com/policyDetail/16" in response["answer"]


def test_in_memory_demo_filters_unrelated_semantic_candidates_from_answer_sources():
    response = run_chat_trace(
        "员工年假规则是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=3,
    )

    chunk_ids = [result["chunk_id"] for result in response["results"]]
    assert chunk_ids == ["leave-annual-001"]
    assert "员工休假管理办法" in response["answer"]
    assert "旷工处理" not in response["answer"]
    assert "员工纪律制度" not in response["answer"]

def test_trace_maps_absence_synonym_to_absenteeism_rule_answer():
    response = run_chat_trace(
        "员工缺勤两天会怎样",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "事实：旷工 2 天" in response["answer"]
    assert "连续旷工3个工作日以下" in response["answer"]
    assert "记过处分" in response["answer"]


def test_trace_does_not_answer_student_behavior_with_employee_discipline_policy():
    response = run_chat_trace(
        "学生迟到怎么处理",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "予以书面或口头警告" not in response["answer"]
    assert "员工纪律制度" not in response["answer"]
    understanding = _step(response, "query_understanding")
    assert understanding["details"]["intent_schema"]["audience"] == "student"


def test_trace_uses_discipline_classification_for_lateness_and_preserves_label():
    response = run_chat_trace(
        "早退两次怎么处理",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "事实：早退" in response["answer"]
    assert "一学年中出现两次及两次以上" in response["answer"]
    assert "予以书面或口头警告" in response["answer"]
    assert "考勤管理制度 > 第五条 迟到早退" not in response["answer"]

def test_section_listing_query_aggregates_all_retained_clause_groups():
    response = run_chat_trace(
        "二类违规有哪些",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "二类违规主要包括" in response["answer"]
    assert "师德师风相关的违规行为" in response["answer"]
    assert "违反保密义务行为" in response["answer"]
    assert "弄虚作假行为" in response["answer"]
    assert "破坏学校管理秩序行为" in response["answer"]
    assert "4. 弄虚作假行为" in response["answer"]
    assert "3. 弄虚作假行为" not in response["answer"]
    assert "3. 破坏学校管理秩序行为" not in response["answer"]
    assert "违规行为相应处理" not in response["answer"]
    assert response["results"][0]["chunk_id"] == "discipline-category-2-children-001"


def test_section_listing_query_prefers_structured_children_and_preserves_source_ordinals():
    class StructuredListingStore:
        def hybrid_search(self, *, query_text, query_embedding, top_k, metadata_filters):
            structured_children = PolicyChunk(
                chunk_id="discipline-category-2-children-001",
                doc_id="employee-discipline-policy",
                block_id="category-2-children",
                text=(
                    "二类违规行为\n"
                    "1. 师德师风相关的违规行为\n"
                    "2. 违反保密义务行为\n"
                    "3. 侵犯学校权益行为\n"
                    "4. 破坏学校管理秩序行为"
                ),
                heading_path=["***公司人守则-员工纪律制度", "二类违规行为"],
                metadata={
                    "source": "员工纪律制度.md",
                    "source_url": "https://example.com/policyDetail/16",
                    "chunk_type": "section_children",
                    "chunking_strategy": "policy_structure",
                    "node_type": "violation_level",
                    "section_title": "二类违规行为",
                    "child_count": 4,
                    "ordinal_sequence": ["1.", "2.", "3.", "4."],
                    "ordinal_continuity_status": "complete",
                },
            )
            noisy_group = PolicyChunk(
                chunk_id="discipline-category-2-group-rough-001",
                doc_id="employee-discipline-policy",
                block_id="class-2-falsification",
                text="（二）二类违规行为 4. 弄虚作假行为 4.1虚假报销。",
                heading_path=["***公司人守则-员工纪律制度", "二类违规行为", "弄虚作假行为"],
                metadata={"source": "员工纪律制度.md", "source_url": "https://example.com/policyDetail/16"},
            )
            return [SearchResult(chunk=noisy_group, distance=0.01), SearchResult(chunk=structured_children, distance=0.2)]

    response = run_chat_trace(
        "二类违规有哪些",
        embedding_client=FakeEmbeddingClient(),
        store=StructuredListingStore(),
        top_k=5,
    )

    assert "结构化章节子项" in response["answer"]
    assert "1. 师德师风相关的违规行为" in response["answer"]
    assert "2. 违反保密义务行为" in response["answer"]
    assert "3. 侵犯学校权益行为" in response["answer"]
    assert "4. 破坏学校管理秩序行为" in response["answer"]
    assert "3. 破坏学校管理秩序行为" not in response["answer"]
    assert response["results"][0]["chunk_id"] == "discipline-category-2-children-001"


def test_section_listing_trace_exposes_structured_children_selection():
    response = run_chat_trace(
        "二类违规有哪些",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    retrieval_plan = _step(response, "retrieval_plan")
    assert "policy_structure" in retrieval_plan["details"]["enabled_channels"]

    evidence = _step(response, "evidence_quality")
    structure_step = next(child for child in evidence["children"] if child["key"] == "policy_structure_children_selection")
    details = structure_step["details"]
    assert details["applied"] is True
    assert details["selected_chunk_id"] == "discipline-category-2-children-001"
    assert details["child_count"] == 5
    assert details["ordinal_sequence"] == ["1.", "2.", "3.", "4.", "5."]
    assert details["ordinal_continuity_status"] == "complete"
    assert details["why"] == "用户询问章节包含哪些子项，结构化 section_children 能直接给出原文编号和子项列表。"

def test_section_listing_exposes_only_answer_used_source():
    response = run_chat_trace(
        "二类违规有哪些",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    answer_sources = response["answer_sources"]
    assert [source["chunk_id"] for source in answer_sources] == ["discipline-category-2-children-001"]
    assert answer_sources[0]["title"] == "***公司人守则-员工纪律制度 > 二类违规行为"
    assert answer_sources[0]["url"] == "https://example.com/policyDetail/16"
    assert len(response["results"]) >= len(answer_sources)


def test_section_listing_returns_next_conversation_context_for_follow_up_clause():
    response = run_chat_trace(
        "二类违规有哪些",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert response["next_conversation_context"] == {
        "last_target_section": "二类违规行为",
        "last_target_clause": None,
        "last_answer_aspect": "section_listing",
        "last_retrieval_intent": "exact_policy_lookup",
    }


def test_unrelated_policy_query_replaces_previous_clause_context_with_leave_context():
    response = run_chat_trace(
        "员工年假规则是什么？",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
        conversation_context={"last_target_section": "二类违规行为"},
    )

    assert response["next_conversation_context"] == {
        "last_policy_category_hint": "leave",
        "last_target_object": "年休假",
        "last_answer_aspect": "annual_leave_days",
        "last_retrieval_intent": "semantic_policy_lookup",
    }
    assert "last_target_section" not in response["next_conversation_context"]


def test_clause_title_query_expands_confidentiality_clause_detail():
    response = run_chat_trace(
        "违反保密义务行为",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "你问的是" in response["answer"]
    assert "二类违规行为" in response["answer"]
    assert "第 2 项：违反保密义务行为" in response["answer"]
    assert "2.1非因工作需要获取、使用、泄露、传播保密信息" in response["answer"]
    assert "2.2其他违反数据安全规范等制度" in response["answer"]
    assert "2.3打听、讨论员工工资、奖金、津贴补贴等个人待遇信息" in response["answer"]
    assert "师德师风相关的违规行为" not in response["answer"]
    assert [source["chunk_id"] for source in response["answer_sources"]] == ["discipline-salary-classification-001"]


def test_numbered_clause_query_expands_clause_instead_of_repeating_listing():
    response = run_chat_trace(
        "5. 破坏学校管理秩序行为",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "第 5 项：破坏学校管理秩序行为" in response["answer"]
    assert "5.1" in response["answer"]
    assert "5.2旷工少于三天" in response["answer"]
    assert "二类违规主要包括" not in response["answer"]
    assert [source["chunk_id"] for source in response["answer_sources"]] == ["discipline-absence-classification-001"]


def test_ambiguous_clause_title_query_asks_for_scope_instead_of_mixing_levels():
    response = run_chat_trace(
        "破坏学校管理秩序行为",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
    )

    assert "这个条款名在多个违规等级下都存在" in response["answer"]
    assert "二类违规行为 > 破坏学校管理秩序行为" in response["answer"]
    assert "一类违规行为 > 破坏学校管理秩序行为" in response["answer"]
    assert "请补充要查哪个违规等级" in response["answer"]
    assert "优先依据" not in response["answer"]
    assert response["answer_sources"] == []


def test_ambiguous_clause_title_uses_conversation_section_context():
    response = run_chat_trace(
        "破坏学校管理秩序行为",
        embedding_client=FakeEmbeddingClient(),
        store=None,
        top_k=5,
        conversation_context={"last_target_section": "二类违规行为"},
    )

    assert "第 5 项：破坏学校管理秩序行为" in response["answer"]
    assert "所属违规等级：二类违规行为" in response["answer"]
    assert "这个条款名在多个违规等级下都存在" not in response["answer"]
    assert [source["chunk_id"] for source in response["answer_sources"]] == ["discipline-absence-classification-001"]
    assert response["next_conversation_context"]["last_target_section"] == "二类违规行为"
    assert response["next_conversation_context"]["last_target_clause"] == "5. 破坏学校管理秩序行为"
