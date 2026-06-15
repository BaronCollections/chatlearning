from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from enterprise_rag_mvp.regression_cases import RegressionCase


@dataclass(frozen=True)
class EvaluationResult:
    query: str
    category: str
    passed: bool
    expected_doc_ids_pass: bool
    expected_keywords_pass: bool
    forbidden_keywords_pass: bool
    expected_urls_pass: bool
    expected_answer_type_pass: bool
    expected_evidence_types_pass: bool
    missing_doc_ids: list[str]
    missing_keywords: list[str]
    forbidden_keyword_hits: list[str]
    missing_urls: list[str]
    missing_evidence_types: list[str]
    observed_doc_ids: list[str]
    observed_urls: list[str]
    observed_answer_type: str | None
    observed_evidence_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[EvaluationResult]
    category_summary: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "category_summary": self.category_summary,
            "results": [result.to_dict() for result in self.results],
        }


def _answer_text(response: dict[str, Any]) -> str:
    return str(response.get("answer") or "")


def _result_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = response.get("results") or []
    return [row for row in rows if isinstance(row, dict)]


def _observed_doc_ids(response: dict[str, Any]) -> list[str]:
    doc_ids: list[str] = []
    for row in _result_rows(response):
        value = row.get("doc_id")
        chunk = row.get("chunk")
        if not value and isinstance(chunk, dict):
            value = chunk.get("doc_id")
        if value and str(value) not in doc_ids:
            doc_ids.append(str(value))
    return doc_ids


def _observed_urls(response: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for row in _result_rows(response):
        citation = row.get("citation") if isinstance(row.get("citation"), dict) else {}
        value = citation.get("url") or row.get("url")
        if value and str(value) not in urls:
            urls.append(str(value))
    return urls


def _step_details(response: dict[str, Any], key: str) -> dict[str, Any]:
    for step in response.get("steps") or []:
        if isinstance(step, dict) and step.get("key") == key and isinstance(step.get("details"), dict):
            return step["details"]
    return {}


def _observed_answer_type(response: dict[str, Any]) -> str | None:
    plan = response.get("answer_plan") if isinstance(response.get("answer_plan"), dict) else None
    if plan is None:
        plan = _step_details(response, "answer_and_observe").get("answer_plan")
    if isinstance(plan, dict) and plan.get("answer_type"):
        return str(plan["answer_type"])
    return None


def _observed_evidence_types(response: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    candidates = []
    direct = response.get("answer_evidence_assessments")
    if isinstance(direct, list):
        candidates.extend(direct)
    answer_details = _step_details(response, "answer_and_observe")
    if isinstance(answer_details.get("answer_evidence_assessments"), list):
        candidates.extend(answer_details["answer_evidence_assessments"])
    evidence_details = _step_details(response, "evidence_quality")
    target_filter = evidence_details.get("target_evidence_filter") if isinstance(evidence_details, dict) else None
    if isinstance(target_filter, dict):
        for item in target_filter.get("evidence_classifications") or []:
            if isinstance(item, dict):
                general = item.get("general_evidence_assessment")
                if isinstance(general, dict):
                    candidates.append(general)
                else:
                    candidates.append(item)
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("evidence_type") and str(candidate["evidence_type"]) not in observed:
            observed.append(str(candidate["evidence_type"]))
    return observed


def _missing(expected: Iterable[str], observed: Iterable[str]) -> list[str]:
    observed_set = set(observed)
    return [item for item in expected if item not in observed_set]


def evaluate_regression_case(case: RegressionCase, response: dict[str, Any]) -> EvaluationResult:
    answer = _answer_text(response)
    observed_doc_ids = _observed_doc_ids(response)
    observed_urls = _observed_urls(response)
    missing_doc_ids = _missing(case.expected_doc_ids, observed_doc_ids)
    missing_keywords = [keyword for keyword in case.expected_keywords if keyword not in answer]
    forbidden_keyword_hits = [keyword for keyword in case.forbidden_keywords if keyword in answer]
    missing_urls = _missing(case.expected_urls, observed_urls)
    observed_answer_type = _observed_answer_type(response)
    observed_evidence_types = _observed_evidence_types(response)
    missing_evidence_types = _missing(case.expected_evidence_types, observed_evidence_types)
    expected_doc_ids_pass = not missing_doc_ids
    expected_keywords_pass = not missing_keywords
    forbidden_keywords_pass = not forbidden_keyword_hits
    expected_urls_pass = not missing_urls
    expected_answer_type_pass = case.expected_answer_type is None or observed_answer_type == case.expected_answer_type
    expected_evidence_types_pass = not missing_evidence_types
    passed = all([
        expected_doc_ids_pass,
        expected_keywords_pass,
        forbidden_keywords_pass,
        expected_urls_pass,
        expected_answer_type_pass,
        expected_evidence_types_pass,
    ])
    return EvaluationResult(
        query=case.query,
        category=case.category,
        passed=passed,
        expected_doc_ids_pass=expected_doc_ids_pass,
        expected_keywords_pass=expected_keywords_pass,
        forbidden_keywords_pass=forbidden_keywords_pass,
        expected_urls_pass=expected_urls_pass,
        expected_answer_type_pass=expected_answer_type_pass,
        expected_evidence_types_pass=expected_evidence_types_pass,
        missing_doc_ids=missing_doc_ids,
        missing_keywords=missing_keywords,
        forbidden_keyword_hits=forbidden_keyword_hits,
        missing_urls=missing_urls,
        missing_evidence_types=missing_evidence_types,
        observed_doc_ids=observed_doc_ids,
        observed_urls=observed_urls,
        observed_answer_type=observed_answer_type,
        observed_evidence_types=observed_evidence_types,
    )


def evaluate_regression_cases(
    cases: Iterable[RegressionCase],
    runner: Callable[[RegressionCase], dict[str, Any]],
) -> EvaluationSummary:
    results = [evaluate_regression_case(case, runner(case)) for case in cases]
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed
    pass_rate = round(passed / total, 4) if total else 0.0
    category_summary: dict[str, dict[str, Any]] = {}
    for result in results:
        bucket = category_summary.setdefault(result.category, {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0})
        bucket["total"] += 1
        if result.passed:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    for bucket in category_summary.values():
        bucket["pass_rate"] = round(bucket["passed"] / bucket["total"], 4) if bucket["total"] else 0.0
    return EvaluationSummary(total=total, passed=passed, failed=failed, pass_rate=pass_rate, results=results, category_summary=category_summary)
