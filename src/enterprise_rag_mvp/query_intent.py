from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from enterprise_rag_mvp.policy_glossary import PolicyTermExpansion, expand_policy_terms

DISCIPLINARY_ACTION_ASPECT = "disciplinary_action"
DEFINITION_ASPECT = "definition"
PROCESS_ASPECT = "process"
APPLICABILITY_ASPECT = "applicability"
EXCEPTION_ASPECT = "exception"
CLASSIFICATION_ASPECT = "classification"
SECTION_LISTING_ASPECT = "section_listing"
TABLE_LOOKUP_ASPECT = "table_lookup"

CHINESE_NUMBER_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

DISCIPLINARY_ACTION_TERMS = (
    "处罚",
    "处分",
    "处理",
    "处理方式",
    "怎么处理",
    "如何处理",
    "纪律处分",
    "违规处理",
    "惩罚",
    "后果",
    "会怎样",
    "有什么事",
    "怎么办",
    "警告",
    "记过",
    "辞退",
)
DEFINITION_TERMS = ("是什么", "什么是", "定义", "指什么", "什么意思")
PROCESS_TERMS = ("流程", "步骤", "怎么申请", "如何申请", "审批", "办理")
EXCEPTION_TERMS = ("例外", "除外", "特殊情况", "豁免")
TABLE_LOOKUP_TERMS = ("几天", "多少天", "几次", "多少次", "额度", "标准", "对照")
SECTION_LISTING_TERMS = ("有哪些", "包括哪些", "包含哪些", "哪几类", "哪几种", "几类", "类型有哪些", "类别有哪些")


@dataclass(frozen=True)
class QueryIntentSchema:
    normalized_query: str
    target_object: str | None
    target_object_type: str | None
    asked_aspect: str | None
    condition_parameters: dict[str, Any] = field(default_factory=dict)
    audience: str | None = None
    glossary_expansions: list[str] = field(default_factory=list)
    required_evidence_types: list[str] = field(default_factory=list)
    missing_conditions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "")).strip()


def chinese_number_to_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = CHINESE_NUMBER_MAP.get(left, 1 if not left else None)
        ones = CHINESE_NUMBER_MAP.get(right, 0 if not right else None)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(value) == 1:
        return CHINESE_NUMBER_MAP.get(value)
    return None


def infer_answer_aspect(query: str) -> str | None:
    if any(term in query for term in DISCIPLINARY_ACTION_TERMS):
        return DISCIPLINARY_ACTION_ASPECT
    if any(term in query for term in SECTION_LISTING_TERMS):
        return SECTION_LISTING_ASPECT
    if "属于" in query and any(term in query for term in ["违规", "行为", "类别", "类型"]):
        return CLASSIFICATION_ASPECT
    if any(term in query for term in ["年假", "年休假", "带薪年假", "带薪年休假"]) and "规则" in query:
        return TABLE_LOOKUP_ASPECT
    if any(term in query for term in PROCESS_TERMS):
        return PROCESS_ASPECT
    if any(term in query for term in EXCEPTION_TERMS):
        return EXCEPTION_ASPECT
    if any(term in query for term in TABLE_LOOKUP_TERMS):
        return TABLE_LOOKUP_ASPECT
    if any(term in query for term in DEFINITION_TERMS):
        return DEFINITION_ASPECT
    return None


def glossary_expansions_for(query: str) -> tuple[str | None, list[str]]:
    expansion = expand_policy_terms(query)
    return expansion.primary_standard_term, expansion.expanded_terms


def _target_object_type(target_object: str | None, expansion: PolicyTermExpansion) -> str | None:
    if not target_object:
        return None
    return expansion.target_object_types.get(target_object)


def _extract_duration(query: str) -> dict[str, Any]:
    match = re.search(r"(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*(?:个)?\s*(工作日|天|日)", query)
    if not match:
        return {}
    value = chinese_number_to_int(match.group(1))
    if value is None:
        return {}
    unit_text = match.group(2)
    return {"duration": value, "unit": "workday" if unit_text == "工作日" else "day"}


def _extract_occurrence(query: str) -> dict[str, Any]:
    match = re.search(r"(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*次", query)
    if not match:
        return {}
    value = chinese_number_to_int(match.group(1))
    if value is None:
        return {}
    params: dict[str, Any] = {"occurrence_count": value, "unit": "time"}
    if any(term in query for term in ["一年", "一学年", "年内"]):
        params["time_window"] = "一年内"
    return params


def _extract_work_year(query: str) -> dict[str, Any]:
    if "第六年及以后" in query or "六年及以后" in query or "6年及以后" in query:
        return {"work_year": 6, "unit": "year"}
    for match in re.finditer(r"(?:第|工作|工龄|司龄|连续工龄|本单位连续工龄|满)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*年", query):
        value = chinese_number_to_int(match.group(1))
        if value is not None and 1 <= value <= 50:
            return {"work_year": value, "unit": "year"}
    return {}


def extract_condition_parameters(query: str, target_object: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    params.update(_extract_duration(query))
    params.update(_extract_occurrence(query))
    if target_object == "年休假" or any(term in query for term in ["年假", "年休假"]):
        params.update(_extract_work_year(query))
    return params


def required_evidence_types_for(aspect: str | None, target_object: str | None, expansion: PolicyTermExpansion) -> list[str]:
    evidence: list[str] = []
    if aspect == DISCIPLINARY_ACTION_ASPECT:
        evidence.extend(["action_evidence", "classification_evidence"])
    elif aspect == DEFINITION_ASPECT:
        evidence.append("definition_evidence")
    elif aspect == PROCESS_ASPECT:
        evidence.append("process_evidence")
    elif aspect == CLASSIFICATION_ASPECT:
        evidence.append("classification_evidence")
    elif aspect == SECTION_LISTING_ASPECT:
        evidence.append("listing_evidence")
    elif aspect == TABLE_LOOKUP_ASPECT:
        evidence.append("table_evidence")
    elif aspect == EXCEPTION_ASPECT:
        evidence.append("exception_evidence")

    if target_object and target_object in expansion.condition_term_groups and "condition_evidence" not in evidence:
        evidence.append("condition_evidence")
    if expansion.required_conditions and "condition_evidence" not in evidence:
        evidence.append("condition_evidence")
    return evidence


def missing_conditions_for(query: str, expansion: PolicyTermExpansion) -> list[str]:
    missing: list[str] = []
    for condition, terms in expansion.condition_term_groups.items():
        if not any(term in query for term in terms):
            missing.append(condition)
    return missing


def infer_audience(query: str, target_object: str | None) -> str:
    if any(term in query for term in ["学生", "孩子", "家长"]):
        return "student" if "学生" in query or "孩子" in query else "guardian"
    if target_object in {"旷工", "语言不得体", "师德师风失范", "年休假"} or any(term in query for term in ["员工", "老师", "教师", "我"]):
        return "employee"
    return "unknown"


def _confidence(target_object: str | None, aspect: str | None, condition_parameters: dict[str, Any], missing_conditions: list[str]) -> float:
    score = 0.25
    if target_object:
        score += 0.35
    if aspect:
        score += 0.25
    if condition_parameters:
        score += 0.1
    if missing_conditions:
        score -= 0.15
    return max(0.0, min(1.0, round(score, 2)))


def understand_query(query: str) -> QueryIntentSchema:
    normalized = normalize_query(query)
    expansion = expand_policy_terms(normalized)
    target_object = expansion.primary_standard_term
    aspect = infer_answer_aspect(normalized)
    condition_parameters = extract_condition_parameters(normalized, target_object)
    missing_conditions = missing_conditions_for(normalized, expansion)
    required_evidence_types = required_evidence_types_for(aspect, target_object, expansion)
    notes: list[str] = []
    if missing_conditions:
        notes.append("用户问题缺少条款成立条件，回答应使用条件性结论。")
    if target_object and not aspect:
        notes.append("已识别业务对象，但问题面不明确，需要依赖检索证据或追问。")
    return QueryIntentSchema(
        normalized_query=normalized,
        target_object=target_object,
        target_object_type=_target_object_type(target_object, expansion),
        asked_aspect=aspect,
        condition_parameters=condition_parameters,
        audience=infer_audience(normalized, target_object),
        glossary_expansions=expansion.expanded_terms,
        required_evidence_types=required_evidence_types,
        missing_conditions=missing_conditions,
        confidence=_confidence(target_object, aspect, condition_parameters, missing_conditions),
        notes=notes,
    )
