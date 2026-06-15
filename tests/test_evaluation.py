from enterprise_rag_mvp.evaluation import evaluate_regression_case, evaluate_regression_cases
from enterprise_rag_mvp.regression_cases import RegressionCase


def test_evaluate_regression_case_passes_expected_keywords_urls_and_doc_ids():
    case = RegressionCase(
        query="虚假报销怎么处罚",
        expected_doc_ids=["company-policy-16"],
        expected_keywords=["虚假报销", "记过处分"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/16"],
    )
    response = {
        "answer": "虚假报销属于二类违规，处理结果包括记过处分。",
        "results": [
            {
                "doc_id": "company-policy-16",
                "citation": {"url": "https://example.com/policyDetail/16"},
            }
        ],
    }

    result = evaluate_regression_case(case, response)

    assert result.passed is True
    assert result.expected_keywords_pass is True
    assert result.forbidden_keywords_pass is True
    assert result.expected_doc_ids_pass is True
    assert result.expected_urls_pass is True


def test_evaluate_regression_case_reports_missing_and_forbidden_signals():
    case = RegressionCase(
        query="二类违规是什么",
        expected_doc_ids=["company-policy-16"],
        expected_keywords=["比较严重的违规行为"],
        forbidden_keywords=["三类违规行为：指一般"],
        expected_urls=["https://example.com/policyDetail/16"],
    )
    response = {"answer": "三类违规行为：指一般的违规行为。", "results": []}

    result = evaluate_regression_case(case, response)

    assert result.passed is False
    assert result.missing_keywords == ["比较严重的违规行为"]
    assert result.forbidden_keyword_hits == ["三类违规行为：指一般"]
    assert result.expected_doc_ids_pass is False
    assert result.expected_urls_pass is False


def test_evaluate_regression_cases_builds_summary_with_pass_rate():
    cases = [
        RegressionCase(query="a", expected_doc_ids=["doc"], expected_keywords=["ok"], forbidden_keywords=["bad"], expected_urls=[]),
        RegressionCase(query="b", expected_doc_ids=["doc"], expected_keywords=["missing"], forbidden_keywords=["bad"], expected_urls=[]),
    ]

    summary = evaluate_regression_cases(cases, lambda case: {"answer": "ok", "results": [{"doc_id": "doc"}]})

    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.pass_rate == 0.5


def test_evaluate_regression_case_checks_answer_and_evidence_types():
    case = RegressionCase(
        query="我旷工两天会有什么处罚",
        category="attendance",
        expected_doc_ids=["company-policy-11"],
        expected_keywords=["记过处分"],
        expected_urls=["https://example.com/policyDetail/11"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence", "classification_evidence"],
    )
    response = {
        "answer": "处理结果包括记过处分。",
        "results": [{"doc_id": "company-policy-11", "citation": {"url": "https://example.com/policyDetail/11"}}],
        "steps": [
            {
                "key": "answer_and_observe",
                "details": {
                    "answer_plan": {"answer_type": "disciplinary_action"},
                    "answer_evidence_assessments": [
                        {"evidence_type": "action_evidence"},
                        {"evidence_type": "classification_evidence"},
                    ],
                },
            }
        ],
    }

    result = evaluate_regression_case(case, response)

    assert result.passed is True
    assert result.category == "attendance"
    assert result.expected_answer_type_pass is True
    assert result.expected_evidence_types_pass is True
    assert result.observed_answer_type == "disciplinary_action"


def test_evaluate_regression_cases_reports_category_summary():
    cases = [
        RegressionCase(query="a", category="leave", expected_doc_ids=["doc"], expected_keywords=["ok"]),
        RegressionCase(query="b", category="attendance", expected_doc_ids=["doc"], expected_keywords=["missing"]),
    ]

    summary = evaluate_regression_cases(cases, lambda case: {"answer": "ok", "results": [{"doc_id": "doc"}]})

    assert summary.category_summary["leave"]["passed"] == 1
    assert summary.category_summary["attendance"]["failed"] == 1


def test_builtin_regression_cases_pass_against_in_memory_demo():
    from enterprise_rag_mvp.embedding_client import DeterministicEmbeddingClient
    from enterprise_rag_mvp.regression_cases import REGRESSION_CASES
    from enterprise_rag_mvp.trace_pipeline import run_chat_trace

    def runner(case):
        return run_chat_trace(case.query, embedding_client=DeterministicEmbeddingClient(), store=None, top_k=5)

    summary = evaluate_regression_cases(REGRESSION_CASES, runner)

    assert summary.failed == 0
    assert summary.pass_rate == 1.0
    assert {"leave", "discipline", "attendance", "confidentiality"}.issubset(summary.category_summary)
