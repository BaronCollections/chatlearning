from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from enterprise_rag_mvp.evidence_validator import EvidenceAssessment
from enterprise_rag_mvp.query_intent import (
    DEFINITION_ASPECT,
    DISCIPLINARY_ACTION_ASPECT,
    PROCESS_ASPECT,
    CLASSIFICATION_ASPECT,
    SECTION_LISTING_ASPECT,
    TABLE_LOOKUP_ASPECT,
    QueryIntentSchema,
)


@dataclass(frozen=True)
class AnswerPlan:
    answer_type: str
    sections: list[str]
    required_citations: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    cannot_answer_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _intent_value(intent: QueryIntentSchema | dict[str, Any], key: str) -> Any:
    if isinstance(intent, QueryIntentSchema):
        return getattr(intent, key)
    return intent.get(key)


def _assessment_types(assessments: Iterable[EvidenceAssessment | dict[str, Any]]) -> set[str]:
    types: set[str] = set()
    for assessment in assessments:
        if isinstance(assessment, EvidenceAssessment):
            types.add(assessment.evidence_type)
        elif assessment.get("evidence_type"):
            types.add(str(assessment["evidence_type"]))
    return types


def _citation_ids(assessments: Iterable[EvidenceAssessment | dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for assessment in assessments:
        chunk_id = assessment.chunk_id if isinstance(assessment, EvidenceAssessment) else assessment.get("chunk_id")
        usable = assessment.usable_as_final if isinstance(assessment, EvidenceAssessment) else assessment.get("usable_as_final")
        if chunk_id and usable and str(chunk_id) not in ids:
            ids.append(str(chunk_id))
    return ids


def _missing_conditions(intent: QueryIntentSchema | dict[str, Any]) -> list[str]:
    return [str(item) for item in (_intent_value(intent, "missing_conditions") or []) if item]


def plan_answer(
    intent: QueryIntentSchema | dict[str, Any],
    assessments: list[EvidenceAssessment | dict[str, Any]],
    *,
    rule_resolution: dict[str, Any] | None = None,
) -> AnswerPlan:
    aspect = _intent_value(intent, "asked_aspect")
    evidence_types = _assessment_types(assessments)
    missing_conditions = _missing_conditions(intent)
    citation_ids = _citation_ids(assessments)

    if aspect == DISCIPLINARY_ACTION_ASPECT:
        if "action_evidence" not in evidence_types:
            return AnswerPlan(
                answer_type="insufficient_evidence",
                sections=["cannot_answer", "citations"],
                required_citations=citation_ids,
                cannot_answer_reason="缺少 action_evidence，不能回答处罚或处理结果。",
            )
        sections = ["fact"]
        if missing_conditions:
            sections.append("conditions")
        if rule_resolution:
            sections.append("rule_match")
        if "classification_evidence" in evidence_types or rule_resolution:
            sections.append("classification")
        sections.extend(["action", "citations", "uncertainty"])
        return AnswerPlan(
            answer_type="conditional_disciplinary_action" if missing_conditions else "disciplinary_action",
            sections=sections,
            required_citations=citation_ids,
            uncertainty_notes=[f"需要确认：{'、'.join(missing_conditions)}。"] if missing_conditions else ["最终结论需要以制度原文、事实调查和正式处理决定为准。"],
        )

    if aspect == CLASSIFICATION_ASPECT:
        if "classification_evidence" not in evidence_types:
            return AnswerPlan("insufficient_evidence", ["cannot_answer", "citations"], citation_ids, cannot_answer_reason="缺少 classification_evidence，不能回答归属类别问题。")
        return AnswerPlan("classification", ["fact", "classification", "citations", "uncertainty"], citation_ids)

    if aspect == SECTION_LISTING_ASPECT:
        if "listing_evidence" not in evidence_types:
            return AnswerPlan("insufficient_evidence", ["cannot_answer", "citations"], citation_ids, cannot_answer_reason="缺少 listing_evidence，不能回答章节包含哪些分类。")
        return AnswerPlan("section_listing", ["overview", "items", "citations", "uncertainty"], citation_ids)

    if aspect == TABLE_LOOKUP_ASPECT:
        if "table_evidence" not in evidence_types:
            return AnswerPlan("insufficient_evidence", ["cannot_answer", "citations"], citation_ids, cannot_answer_reason="缺少 table_evidence，不能回答查表类问题。")
        return AnswerPlan("table_lookup", ["result", "table", "citations", "uncertainty"], citation_ids)

    if aspect == DEFINITION_ASPECT:
        if "definition_evidence" not in evidence_types:
            return AnswerPlan("insufficient_evidence", ["cannot_answer", "citations"], citation_ids, cannot_answer_reason="缺少 definition_evidence，不能回答定义类问题。")
        return AnswerPlan("definition", ["definition", "scope", "citations"], citation_ids)

    if aspect == PROCESS_ASPECT:
        if "process_evidence" not in evidence_types:
            return AnswerPlan("insufficient_evidence", ["cannot_answer", "citations"], citation_ids, cannot_answer_reason="缺少 process_evidence，不能回答流程类问题。")
        return AnswerPlan("process", ["steps", "owner", "materials", "citations", "uncertainty"], citation_ids)

    return AnswerPlan("grounded_summary", ["summary", "citations", "uncertainty"], citation_ids)
