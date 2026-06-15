from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from enterprise_rag_mvp.models import PolicyChunk
from enterprise_rag_mvp.query_intent import (
    DEFINITION_ASPECT,
    DISCIPLINARY_ACTION_ASPECT,
    PROCESS_ASPECT,
    CLASSIFICATION_ASPECT,
    SECTION_LISTING_ASPECT,
    TABLE_LOOKUP_ASPECT,
    QueryIntentSchema,
)

ACTION_TERMS = ("处罚", "处分", "处理", "警告", "记过", "辞退", "扣除", "解除劳动合同", "调薪", "年终奖")
STRONG_ACTION_TERMS = ("予以", "给予", "警告", "记过", "辞退", "扣除", "解除劳动合同", "调薪", "年终奖")
CLASSIFICATION_TERMS = (
    "一类违规行为",
    "二类违规行为",
    "三类违规行为",
    "属于",
    "师德师风相关的违规行为",
    "违反保密义务行为",
    "侵犯学校权益行为",
    "弄虚作假行为",
    "破坏学校管理秩序行为",
)
LISTING_EXCLUDE_TERMS = ("违规行为相应处理", "处理结果", "处罚依据")
DEFINITION_SIGNALS = ("指", "定义", "是指", "是")
REFERENCE_TERMS = ("参见", "详见", "参考", "参照", "见《", "具体参见")
PROCESS_TERMS = ("流程", "步骤", "申请", "审批", "办理", "提交")
TABLE_TERMS = ("第一年", "第二年", "第三年", "第四年", "第五年", "第六年", "天数", "如下", "标准")


@dataclass(frozen=True)
class EvidenceAssessment:
    chunk_id: str
    evidence_type: str
    usable_as_final: bool
    matched_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _intent_value(intent: QueryIntentSchema | dict[str, Any], key: str) -> Any:
    if isinstance(intent, QueryIntentSchema):
        return getattr(intent, key)
    return intent.get(key)


def _intent_terms(intent: QueryIntentSchema | dict[str, Any]) -> list[str]:
    terms: list[str] = []
    target_object = _intent_value(intent, "target_object")
    if target_object:
        terms.append(str(target_object))
    for term in _intent_value(intent, "glossary_expansions") or []:
        if term and str(term) not in terms:
            terms.append(str(term))
    return terms


def _haystack(chunk: PolicyChunk) -> str:
    return " ".join([chunk.text, " ".join(chunk.heading_path), " ".join(str(v) for v in (chunk.metadata or {}).values())])


def _matched_terms(haystack: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in haystack]


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_reference_only(text: str) -> bool:
    return _has_any(text, REFERENCE_TERMS) and not _has_any(text, STRONG_ACTION_TERMS)


def _table_score(text: str) -> int:
    return sum(1 for term in TABLE_TERMS if term in text) + len(re.findall(r"\d+\s*天", text))


def assess_evidence(chunk: PolicyChunk, intent: QueryIntentSchema | dict[str, Any]) -> EvidenceAssessment:
    text = _haystack(chunk)
    terms = _intent_terms(intent)
    matched = _matched_terms(text, terms)
    missing = [term for term in terms if term not in matched]
    aspect = _intent_value(intent, "asked_aspect")

    if _is_reference_only(text):
        return EvidenceAssessment(
            chunk_id=chunk.chunk_id,
            evidence_type="cross_reference_evidence",
            usable_as_final=False,
            matched_terms=matched,
            missing_terms=missing,
            reason="片段只是参见或线索，不能直接作为最终回答依据。",
        )

    if aspect == DISCIPLINARY_ACTION_ASPECT:
        if _has_any(text, DEFINITION_SIGNALS) and not _has_any(text, STRONG_ACTION_TERMS):
            return EvidenceAssessment(
                chunk_id=chunk.chunk_id,
                evidence_type="insufficient_evidence",
                usable_as_final=False,
                matched_terms=matched,
                missing_terms=missing,
                reason="用户问的是处罚或处理结果，但片段只是定义说明。",
            )
        if _has_any(text, ACTION_TERMS) and (matched or _has_any(text, CLASSIFICATION_TERMS)):
            return EvidenceAssessment(
                chunk_id=chunk.chunk_id,
                evidence_type="action_evidence",
                usable_as_final=True,
                matched_terms=matched,
                missing_terms=missing,
                reason="片段包含处理/处分信号，可回答处罚或处理结果。",
            )
        if matched and _has_any(text, CLASSIFICATION_TERMS):
            return EvidenceAssessment(
                chunk_id=chunk.chunk_id,
                evidence_type="classification_evidence",
                usable_as_final=True,
                matched_terms=matched,
                missing_terms=missing,
                reason="片段可说明行为或对象属于哪个制度分类，但仍需要处理条款补足处罚。",
            )
        return EvidenceAssessment(
            chunk_id=chunk.chunk_id,
            evidence_type="insufficient_evidence",
            usable_as_final=False,
            matched_terms=matched,
            missing_terms=missing,
            reason="用户问的是处罚或处理结果，但片段没有可用的处理/处分信号。",
        )

    if aspect == CLASSIFICATION_ASPECT:
        if matched and _has_any(text, CLASSIFICATION_TERMS):
            return EvidenceAssessment(chunk.chunk_id, "classification_evidence", True, matched, missing, "片段包含分类信号，可回答属于什么类型。")
        return EvidenceAssessment(chunk.chunk_id, "insufficient_evidence", False, matched, missing, "分类类问题需要类别、等级或归属证据。")

    if aspect == SECTION_LISTING_ASPECT:
        if _has_any(text, LISTING_EXCLUDE_TERMS):
            return EvidenceAssessment(chunk.chunk_id, "insufficient_evidence", False, matched, missing, "用户问的是分类列表，但片段属于处理或处罚条款。")
        if matched and _has_any(text, CLASSIFICATION_TERMS):
            return EvidenceAssessment(chunk.chunk_id, "listing_evidence", True, matched, missing, "片段包含目标章节下的分类信号，可回答有哪些。")
        return EvidenceAssessment(chunk.chunk_id, "insufficient_evidence", False, matched, missing, "枚举类问题需要目标章节下的分类、小节或条款证据。")

    if aspect == TABLE_LOOKUP_ASPECT:
        if matched and _table_score(text) >= 3:
            return EvidenceAssessment(
                chunk_id=chunk.chunk_id,
                evidence_type="table_evidence",
                usable_as_final=True,
                matched_terms=matched,
                missing_terms=missing,
                reason="片段包含表格或对照标准，可支撑查表类问题。",
            )
        return EvidenceAssessment(chunk.chunk_id, "insufficient_evidence", False, matched, missing, "查表类问题需要表格、档位或对照标准证据。")

    if aspect == DEFINITION_ASPECT:
        if matched and _has_any(text, DEFINITION_SIGNALS):
            return EvidenceAssessment(chunk.chunk_id, "definition_evidence", True, matched, missing, "片段包含定义信号，可回答是什么。")
        return EvidenceAssessment(chunk.chunk_id, "insufficient_evidence", False, matched, missing, "定义类问题需要定义或解释性证据。")

    if aspect == PROCESS_ASPECT:
        if matched and _has_any(text, PROCESS_TERMS):
            return EvidenceAssessment(chunk.chunk_id, "process_evidence", True, matched, missing, "片段包含流程或审批信号。")
        return EvidenceAssessment(chunk.chunk_id, "insufficient_evidence", False, matched, missing, "流程类问题需要步骤、材料或审批证据。")

    return EvidenceAssessment(
        chunk_id=chunk.chunk_id,
        evidence_type="semantic_candidate",
        usable_as_final=True,
        matched_terms=matched,
        missing_terms=missing,
        reason="普通语义候选，当前问题面未触发强证据类型约束。",
    )
