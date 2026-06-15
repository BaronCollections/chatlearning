from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from enterprise_rag_mvp.query_intent import understand_query

DISCIPLINARY_ACTION_ASPECT = "disciplinary_action"
DEFINITION_ASPECT = "definition"
PROCESS_ASPECT = "process"
APPLICABILITY_ASPECT = "applicability"
EXCEPTION_ASPECT = "exception"

ABSENTEEISM_BEHAVIOR = "absenteeism"

DISCIPLINARY_ACTION_QUERY_TERMS = [
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
    "警告",
    "记过",
    "降级",
    "辞退",
    "解除劳动合同",
    "绩效",
    "薪酬影响",
    "会怎样",
    "怎么办",
]

DISCIPLINARY_ACTION_RETRIEVAL_TERMS = [
    "处罚",
    "处分",
    "处理",
    "违规处理",
    "处分流程",
    "处理方式",
    "纪律处分",
    "警告",
    "记过",
    "降级",
    "辞退",
    "解除劳动合同",
    "绩效考核",
    "薪酬影响",
    "最终处理决定",
    "申诉",
]

ABSENTEEISM_BEHAVIOR_TERMS = [
    "旷工",
    "连续旷工",
    "擅自不出勤",
    "擅自离岗",
    "未提前提交请假申请",
    "请假申请未经学校批准",
    "逾期不归",
    "逾期不出勤",
    "缺勤",
    "未出勤",
]

ABSENTEEISM_UNDER_THREE_TERMS = [
    "连续旷工3个工作日以下",
    "旷工少于三天",
    "二类违规行为",
    "破坏学校管理秩序行为",
    "员工纪律制度",
    "***公司人守则-员工纪律制度",
    "扣除旷工期间工资",
    "记过处分",
]

ABSENTEEISM_THREE_OR_MORE_TERMS = [
    "连续旷工3个工作日及以上",
    "一年内累计两次及以上旷工",
    "一类违规行为",
    "员工纪律制度",
    "***公司人守则-员工纪律制度",
    "扣除旷工期间工资",
    "辞退处分",
]

ABSENTEEISM_POLICY_TITLE_TERMS = [
    "工作时间及假期管理制度",
    "***公司人守则-工作时间及假期管理制度",
    "员工纪律制度",
    "***公司人守则-员工纪律制度",
]

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


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    behavior: str
    behavior_label: str
    condition_text: str
    operator: str
    threshold: int
    unit: str
    action_evidence: list[str]
    search_terms: list[str]
    policy_titles: list[str]
    classification_terms: list[str] = field(default_factory=list)
    time_window: str | None = None
    target_section: str | None = None
    target_clause: str | None = None
    target_clause_no: str | None = None
    target_subclause: str | None = None
    exclude_sections: list[str] = field(default_factory=list)
    exclude_clauses: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleResolution:
    user_fact: str
    behavior: str
    behavior_label: str
    answer_aspect: str | None
    matched_rule: str
    rule_id: str
    comparison: str
    condition_parameters: dict[str, Any]
    expected_evidence: list[str]
    search_terms: list[str]
    policy_titles: list[str]
    classification_terms: list[str]
    target_section: str | None = None
    target_clause: str | None = None
    target_clause_no: str | None = None
    target_subclause: str | None = None
    exclude_sections: list[str] = field(default_factory=list)
    exclude_clauses: list[str] = field(default_factory=list)
    reasoning_steps: list[str] = field(default_factory=list)
    uncertainty: str | None = None

    def to_trace_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorPattern:
    behavior: str
    behavior_label: str
    triggers: list[str]
    target_section: str | None
    target_clause: str | None
    target_clause_no: str | None
    target_subclause: str | None
    classification_terms: list[str]
    search_terms: list[str]
    preferred_policy_titles: list[str]
    exclude_sections: list[str] = field(default_factory=list)
    exclude_clauses: list[str] = field(default_factory=list)
    required_conditions: list[str] = field(default_factory=list)
    condition_term_groups: dict[str, list[str]] = field(default_factory=dict)


ABSENTEEISM_RULES = [
    RuleDefinition(
        rule_id="absence_under_3_workdays",
        behavior=ABSENTEEISM_BEHAVIOR,
        behavior_label="旷工",
        condition_text="连续旷工3个工作日以下",
        operator="<",
        threshold=3,
        unit="workday",
        action_evidence=["扣除旷工期间工资", "记过处分"],
        search_terms=ABSENTEEISM_UNDER_THREE_TERMS,
        policy_titles=ABSENTEEISM_POLICY_TITLE_TERMS,
        classification_terms=["二类违规行为", "破坏学校管理秩序行为", "4.2旷工少于三天"],
        target_section="二类违规行为",
        target_clause="4. 破坏学校管理秩序行为",
        target_clause_no="4",
        target_subclause="4.2",
        exclude_sections=["一类违规行为", "三类违规行为"],
    ),
    RuleDefinition(
        rule_id="absence_3_or_more_workdays",
        behavior=ABSENTEEISM_BEHAVIOR,
        behavior_label="旷工",
        condition_text="连续旷工3个工作日及以上",
        operator=">=",
        threshold=3,
        unit="workday",
        action_evidence=["扣除旷工期间工资", "辞退处分"],
        search_terms=ABSENTEEISM_THREE_OR_MORE_TERMS,
        policy_titles=ABSENTEEISM_POLICY_TITLE_TERMS,
        classification_terms=["一类违规行为", "连续旷工3个工作日及以上"],
        target_section="一类违规行为",
        exclude_sections=["二类违规行为", "三类违规行为"],
    ),
    RuleDefinition(
        rule_id="absence_twice_or_more_in_one_year",
        behavior=ABSENTEEISM_BEHAVIOR,
        behavior_label="旷工",
        condition_text="一年内累计两次及以上旷工",
        operator=">=",
        threshold=2,
        unit="time",
        time_window="一年内",
        action_evidence=["扣除旷工期间工资", "辞退处分"],
        search_terms=ABSENTEEISM_THREE_OR_MORE_TERMS,
        policy_titles=ABSENTEEISM_POLICY_TITLE_TERMS,
        classification_terms=["一类违规行为", "一年内累计两次及以上旷工"],
        target_section="一类违规行为",
        exclude_sections=["二类违规行为", "三类违规行为"],
    ),
]

BEHAVIOR_PATTERNS = [
    BehaviorPattern(
        behavior=ABSENTEEISM_BEHAVIOR,
        behavior_label="旷工",
        triggers=ABSENTEEISM_BEHAVIOR_TERMS,
        target_section=None,
        target_clause=None,
        target_clause_no=None,
        target_subclause=None,
        classification_terms=["旷工", "旷工少于三天", "二类违规行为", "破坏学校管理秩序行为"],
        search_terms=[
            "旷工",
            "连续旷工3个工作日以下",
            "连续旷工3个工作日及以上",
            "一年内累计两次及以上旷工",
            "扣除旷工期间工资",
            "记过处分",
            "辞退处分",
            "旷工少于三天",
        ],
        preferred_policy_titles=ABSENTEEISM_POLICY_TITLE_TERMS,
    ),
    BehaviorPattern(
        behavior="abusive_language",
        behavior_label="语言不得体",
        triggers=["骂人", "说脏话", "脏话", "辱骂", "言语攻击", "语言不得体"],
        target_section="三类违规行为",
        target_clause="4. 侵犯学校权益行为",
        target_clause_no="4",
        target_subclause="4.2",
        classification_terms=["三类违规行为", "侵犯学校权益行为", "4.2对客户、来访者怠慢或语言不得体"],
        search_terms=["语言不得体", "怠慢", "投诉", "三类违规行为", "侵犯学校权益行为", "书面或口头警告"],
        preferred_policy_titles=["员工纪律制度", "***公司人守则-员工纪律制度"],
        exclude_sections=["一类违规行为", "二类违规行为"],
        required_conditions=["对象为客户或来访者", "并引起投诉"],
        condition_term_groups={
            "对象为客户或来访者": ["客户", "来访者"],
            "并引起投诉": ["投诉", "被投诉", "引起投诉"],
        },
    ),
    BehaviorPattern(
        behavior="teacher_ethics",
        behavior_label="师德师风失范",
        triggers=["没有师德", "师德", "师德师风", "违反师德", "教师职业行为准则"],
        target_section="二类违规行为",
        target_clause="1. 师德师风相关的违规行为",
        target_clause_no="1",
        target_subclause="1.1",
        classification_terms=["二类违规行为", "师德师风相关的违规行为", "1.1违反教师职业行为准则"],
        search_terms=["师德师风", "教师职业行为准则", "限制性规定", "二类违规行为", "记过处分"],
        preferred_policy_titles=["员工纪律制度", "***公司人守则-员工纪律制度"],
        exclude_sections=["一类违规行为", "三类违规行为"],
    ),
    BehaviorPattern(
        behavior="salary_inquiry",
        behavior_label="打听工资",
        triggers=["打听工资", "讨论工资", "工资", "奖金", "津贴补贴", "个人待遇"],
        target_section="二类违规行为",
        target_clause="2. 违反保密义务行为",
        target_clause_no="2",
        target_subclause="2.3",
        classification_terms=["二类违规行为", "违反保密义务行为", "2.3打听、讨论员工工资"],
        search_terms=["打听、讨论员工工资", "奖金", "津贴补贴", "个人待遇信息", "二类违规行为", "违反保密义务行为"],
        preferred_policy_titles=["员工纪律制度", "***公司人守则-员工纪律制度"],
        exclude_sections=["一类违规行为", "三类违规行为"],
    ),
    BehaviorPattern(
        behavior="false_reimbursement",
        behavior_label="虚假报销",
        triggers=["虚假报销", "报销未发生", "虚假理由报销"],
        target_section="二类违规行为",
        target_clause="4. 弄虚作假行为",
        target_clause_no="4",
        target_subclause="4.3",
        classification_terms=["二类违规行为", "弄虚作假行为", "4.3虚假报销"],
        search_terms=["虚假报销", "报销未发生的费用", "虚假理由报销", "4.3", "弄虚作假行为"],
        preferred_policy_titles=["员工纪律制度", "***公司人守则-员工纪律制度"],
        exclude_sections=["一类违规行为", "三类违规行为"],
        exclude_clauses=["3. 侵犯学校权益行为", "5. 破坏学校管理秩序行为"],
    ),
    BehaviorPattern(
        behavior="lateness",
        behavior_label="迟到",
        triggers=["迟到", "早退", "停课", "顶课", "调课"],
        target_section="三类违规行为",
        target_clause="5. 破坏学校管理秩序行为",
        target_clause_no="5",
        target_subclause="5.1",
        classification_terms=["三类违规行为", "破坏学校管理秩序行为", "5.1一学年中出现两次及两次以上", "一学年中出现两次及两次以上"],
        search_terms=["迟到", "早退", "一学年中出现两次及两次以上", "三类违规行为", "破坏学校管理秩序行为"],
        preferred_policy_titles=["员工纪律制度", "***公司人守则-员工纪律制度"],
        exclude_sections=["一类违规行为", "二类违规行为"],
    ),
]


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def parse_chinese_number(value: str) -> int | None:
    if value in CHINESE_NUMBER_MAP:
        return CHINESE_NUMBER_MAP[value]
    if value.startswith("十") and len(value) == 2:
        ones = CHINESE_NUMBER_MAP.get(value[1:])
        return 10 + ones if ones is not None else None
    if value.endswith("十") and len(value) == 2:
        tens = CHINESE_NUMBER_MAP.get(value[:1])
        return tens * 10 if tens is not None else None
    if "十" in value and len(value) == 3:
        tens = CHINESE_NUMBER_MAP.get(value[:1])
        ones = CHINESE_NUMBER_MAP.get(value[2:])
        if tens is not None and ones is not None:
            return tens * 10 + ones
    return None


def extract_quantity(query: str, units: list[str]) -> dict[str, Any] | None:
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    digit_match = re.search(rf"(\d{{1,2}})\s*(?:个)?(?:{unit_pattern})", query)
    if digit_match:
        return {"value": int(digit_match.group(1)), "unit": _canonical_unit(digit_match.group(0))}
    chinese_match = re.search(rf"([一二两三四五六七八九十]{{1,3}})\s*(?:个)?(?:{unit_pattern})", query)
    if chinese_match:
        value = parse_chinese_number(chinese_match.group(1))
        if value is not None:
            return {"value": value, "unit": _canonical_unit(chinese_match.group(0))}
    return None


def _canonical_unit(raw: str) -> str:
    if "次" in raw:
        return "time"
    if "工作日" in raw:
        return "day"
    if "天" in raw or "日" in raw:
        return "day"
    return "count"


def extract_day_duration(query: str) -> dict[str, Any] | None:
    value = extract_quantity(query, ["工作日", "天", "日"])
    if value and value.get("unit") == "day":
        return value
    return None


def extract_occurrence_count(query: str) -> dict[str, Any] | None:
    value = extract_quantity(query, ["次"])
    if value and value.get("unit") == "time":
        return value
    return None


def has_disciplinary_action_intent(query: str) -> bool:
    return any(term in query for term in DISCIPLINARY_ACTION_QUERY_TERMS)


def infer_answer_aspect(query: str) -> str | None:
    if has_disciplinary_action_intent(query):
        return DISCIPLINARY_ACTION_ASPECT
    if any(term in query for term in ["是什么", "属于什么", "哪类", "什么违规", "定义"]):
        return DEFINITION_ASPECT
    if any(term in query for term in ["流程", "怎么申请", "如何申请"]):
        return PROCESS_ASPECT
    if any(term in query for term in ["能不能", "是否", "可以吗", "适用"]):
        return APPLICABILITY_ASPECT
    if any(term in query for term in ["例外", "特殊情况", "除外"]):
        return EXCEPTION_ASPECT
    return None


def _matches_rule(value: int, rule: RuleDefinition) -> bool:
    if rule.operator == "<":
        return value < rule.threshold
    if rule.operator == ">=":
        return value >= rule.threshold
    if rule.operator == "==":
        return value == rule.threshold
    return False


def _comparison(value: int, rule: RuleDefinition) -> str:
    return f"{value} {rule.operator} {rule.threshold}"


def _duration_rule_resolution(query: str, answer_aspect: str | None) -> RuleResolution | None:
    duration = extract_day_duration(query)
    if not duration:
        return None
    value = duration.get("value")
    if not isinstance(value, int):
        return None
    for rule in ABSENTEEISM_RULES[:2]:
        if _matches_rule(value, rule):
            comparison = _comparison(value, rule)
            return RuleResolution(
                user_fact=f"旷工 {value} 天",
                behavior=rule.behavior,
                behavior_label=rule.behavior_label,
                answer_aspect=answer_aspect or DISCIPLINARY_ACTION_ASPECT,
                matched_rule=rule.condition_text,
                rule_id=rule.rule_id,
                comparison=comparison,
                condition_parameters={"duration": duration},
                expected_evidence=rule.action_evidence,
                search_terms=rule.search_terms,
                policy_titles=rule.policy_titles,
                classification_terms=rule.classification_terms,
                target_section=rule.target_section,
                target_clause=rule.target_clause,
                target_clause_no=rule.target_clause_no,
                target_subclause=rule.target_subclause,
                exclude_sections=rule.exclude_sections,
                exclude_clauses=rule.exclude_clauses,
                reasoning_steps=[
                    f"识别用户事实：旷工 {value} 天。",
                    f"把用户事实和制度阈值比较：{comparison}。",
                    f"命中制度条件：{rule.condition_text}。",
                    "处罚结论必须由命中的制度证据支持，不能只靠代码推断。",
                ],
                uncertainty="如果不是连续旷工、单位不是工作日，或存在已批准请假/特殊审批，需要按实际考勤和 HR 确认。",
            )
    return None


def _occurrence_rule_resolution(query: str, answer_aspect: str | None) -> RuleResolution | None:
    occurrence = extract_occurrence_count(query)
    if not occurrence or "旷工" not in query:
        return None
    value = occurrence.get("value")
    if not isinstance(value, int):
        return None
    rule = next(item for item in ABSENTEEISM_RULES if item.rule_id == "absence_twice_or_more_in_one_year")
    if not _matches_rule(value, rule):
        return None
    comparison = _comparison(value, rule)
    condition_parameters: dict[str, Any] = {"occurrence_count": occurrence}
    if any(term in query for term in ["一年内", "一学年", "年内"]):
        condition_parameters["time_window"] = "一年内"
    return RuleResolution(
        user_fact=f"旷工 {value} 次",
        behavior=rule.behavior,
        behavior_label=rule.behavior_label,
        answer_aspect=answer_aspect or DISCIPLINARY_ACTION_ASPECT,
        matched_rule=rule.condition_text,
        rule_id=rule.rule_id,
        comparison=comparison,
        condition_parameters=condition_parameters,
        expected_evidence=rule.action_evidence,
        search_terms=rule.search_terms,
        policy_titles=rule.policy_titles,
        classification_terms=rule.classification_terms,
        target_section=rule.target_section,
        target_clause=rule.target_clause,
        target_clause_no=rule.target_clause_no,
        target_subclause=rule.target_subclause,
        exclude_sections=rule.exclude_sections,
        exclude_clauses=rule.exclude_clauses,
        reasoning_steps=[
            f"识别用户事实：旷工 {value} 次。",
            f"把次数和制度阈值比较：{comparison}。",
            f"命中制度条件：{rule.condition_text}。",
        ],
        uncertainty="需要确认统计窗口是否为制度口径下的一年或一学年。",
    )


def resolve_rule_query(query: str) -> RuleResolution | None:
    answer_aspect = infer_answer_aspect(query)
    if any(term in query for term in ABSENTEEISM_BEHAVIOR_TERMS):
        occurrence_resolution = _occurrence_rule_resolution(query, answer_aspect)
        if occurrence_resolution:
            return occurrence_resolution
        return _duration_rule_resolution(query, answer_aspect)
    return None


def find_behavior_pattern(query: str) -> BehaviorPattern | None:
    for pattern in BEHAVIOR_PATTERNS:
        if any(trigger in query for trigger in pattern.triggers):
            return pattern
    return None


def matched_behavior_label(query: str, pattern: BehaviorPattern) -> str:
    matched = [trigger for trigger in pattern.triggers if trigger in query]
    if pattern.behavior == "lateness" and matched:
        return max(matched, key=len)
    return pattern.behavior_label


def aspect_terms(aspect: str | None) -> list[str]:
    if aspect == DISCIPLINARY_ACTION_ASPECT:
        return DISCIPLINARY_ACTION_RETRIEVAL_TERMS
    return []


def default_query_schema() -> dict[str, Any]:
    return {
        "target_object": None,
        "answer_aspect": None,
        "condition_parameters": {},
        "audience": "unknown",
        "rule_match": None,
        "notes": [],
    }


def _base_spec() -> dict[str, Any]:
    return {
        "retrieval_intent": "semantic_policy_lookup",
        "target_terms": [],
        "target_section": None,
        "target_clause": None,
        "target_clause_no": None,
        "target_subclause": None,
        "target_behavior": None,
        "target_behavior_label": None,
        "behavior_duration": None,
        "behavior_threshold": None,
        "preferred_policy_titles": [],
        "asked_aspect": None,
        "answer_aspect": None,
        "condition_parameters": {},
        "rule_resolution": None,
        "rule_search_terms": [],
        "expected_evidence": [],
        "query_schema": default_query_schema(),
        "intent_schema": None,
        "exclude_sections": [],
        "exclude_clauses": [],
        "required_conditions": [],
        "missing_conditions": [],
    }


def _add_terms(spec: dict[str, Any], *terms: str) -> None:
    spec["retrieval_intent"] = "exact_policy_lookup"
    current = list(spec.get("target_terms") or [])
    for term in terms:
        if term and term not in current:
            current.append(term)
    spec["target_terms"] = current


def _merge_unique(spec: dict[str, Any], key: str, values: list[str]) -> None:
    current = list(spec.get(key) or [])
    for value in values:
        if value and value not in current:
            current.append(value)
    spec[key] = current


def _apply_section_lookup(query: str, spec: dict[str, Any]) -> None:
    if "一类违规" in query:
        _add_terms(spec, "一类违规", "一类违规行为")
        spec["target_section"] = "一类违规行为"
        spec["exclude_sections"] = ["二类违规行为", "三类违规行为"]
    if "二类违规" in query:
        _add_terms(spec, "二类违规", "二类违规行为")
        spec["target_section"] = "二类违规行为"
        spec["exclude_sections"] = ["一类违规行为", "三类违规行为"]
    if "三类违规" in query:
        _add_terms(spec, "三类违规", "三类违规行为")
        spec["target_section"] = "三类违规行为"
        spec["exclude_sections"] = ["一类违规行为", "二类违规行为"]
    if "弄虚作假" in query:
        _add_terms(spec, "弄虚作假", "弄虚作假行为", "4. 弄虚作假行为")
        spec["target_section"] = "二类违规行为"
        spec["target_clause"] = "4. 弄虚作假行为"
        spec["target_clause_no"] = "4"
        spec["exclude_sections"] = ["一类违规行为", "三类违规行为"]
        _merge_unique(spec, "exclude_clauses", ["3. 侵犯学校权益行为", "5. 破坏学校管理秩序行为"])


def _apply_rule_resolution(spec: dict[str, Any], resolution: RuleResolution) -> None:
    trace = resolution.to_trace_dict()
    spec["target_behavior"] = resolution.behavior
    spec["target_behavior_label"] = resolution.behavior_label
    spec["asked_aspect"] = resolution.answer_aspect
    spec["answer_aspect"] = resolution.answer_aspect
    spec["behavior_duration"] = resolution.condition_parameters.get("duration")
    threshold_keys = {
        "absence_under_3_workdays": "continuous_absence_under_3_workdays",
        "absence_3_or_more_workdays": "continuous_absence_3_or_more_workdays",
        "absence_twice_or_more_in_one_year": "absence_twice_or_more_in_one_year",
    }
    spec["behavior_threshold"] = threshold_keys.get(resolution.rule_id, resolution.rule_id)
    spec["rule_resolution"] = trace
    spec["rule_search_terms"] = resolution.search_terms
    spec["expected_evidence"] = resolution.expected_evidence
    spec["preferred_policy_titles"] = resolution.policy_titles
    if resolution.behavior != ABSENTEEISM_BEHAVIOR:
        spec["target_section"] = resolution.target_section or spec.get("target_section")
        spec["target_clause"] = resolution.target_clause or spec.get("target_clause")
        spec["target_clause_no"] = resolution.target_clause_no or spec.get("target_clause_no")
        spec["target_subclause"] = resolution.target_subclause or spec.get("target_subclause")
        _merge_unique(spec, "exclude_sections", resolution.exclude_sections)
        _merge_unique(spec, "exclude_clauses", resolution.exclude_clauses)
    _add_terms(spec, *ABSENTEEISM_BEHAVIOR_TERMS, *resolution.policy_titles, *resolution.search_terms, *resolution.classification_terms)
    spec["condition_parameters"] = resolution.condition_parameters
    spec["query_schema"] = {
        "target_object": {"type": "behavior", "value": resolution.behavior_label, "key": resolution.behavior},
        "answer_aspect": resolution.answer_aspect,
        "condition_parameters": resolution.condition_parameters,
        "audience": "employee",
        "rule_match": trace,
        "notes": resolution.reasoning_steps,
    }


def _missing_required_conditions(query: str, pattern: BehaviorPattern) -> list[str]:
    missing: list[str] = []
    for condition in pattern.required_conditions:
        terms = pattern.condition_term_groups.get(condition) or [condition]
        if not any(term in query for term in terms):
            missing.append(condition)
    return missing


def _apply_behavior_pattern(spec: dict[str, Any], pattern: BehaviorPattern, answer_aspect: str | None, query: str) -> None:
    behavior_label = matched_behavior_label(query, pattern)
    spec["target_behavior"] = pattern.behavior
    spec["target_behavior_label"] = behavior_label
    spec["target_section"] = pattern.target_section
    spec["target_clause"] = pattern.target_clause
    spec["target_clause_no"] = pattern.target_clause_no
    spec["target_subclause"] = pattern.target_subclause
    spec["preferred_policy_titles"] = pattern.preferred_policy_titles
    retrieval_aspect = answer_aspect if answer_aspect == DISCIPLINARY_ACTION_ASPECT else None
    spec["asked_aspect"] = retrieval_aspect
    spec["answer_aspect"] = answer_aspect
    spec["rule_search_terms"] = pattern.search_terms
    missing_conditions = _missing_required_conditions(query, pattern)
    spec["required_conditions"] = list(pattern.required_conditions)
    spec["missing_conditions"] = missing_conditions
    _merge_unique(spec, "exclude_sections", pattern.exclude_sections)
    _merge_unique(spec, "exclude_clauses", pattern.exclude_clauses)
    _add_terms(spec, *pattern.triggers, *pattern.search_terms, *pattern.classification_terms, *pattern.preferred_policy_titles)
    condition_parameters = {
        "required_conditions": list(pattern.required_conditions),
        "missing_conditions": missing_conditions,
    } if pattern.required_conditions else {}
    notes = ["命中行为型制度查询，但当前没有数值阈值规则；使用目标条款和分类作为检索约束。"]
    if missing_conditions:
        notes.append("用户问题缺少条款成立条件，回答必须按条件性结论处理，不能直接判定最终处罚。")
    spec["condition_parameters"] = condition_parameters
    spec["query_schema"] = {
        "target_object": {"type": "behavior", "value": behavior_label, "key": pattern.behavior},
        "answer_aspect": answer_aspect,
        "condition_parameters": condition_parameters,
        "audience": "employee",
        "rule_match": None,
        "notes": notes,
    }


def build_policy_lookup_spec(query: str) -> dict[str, Any]:
    spec = _base_spec()
    intent_schema = understand_query(query)
    spec["intent_schema"] = intent_schema.to_dict()
    answer_aspect = infer_answer_aspect(query)
    retrieval_aspect = answer_aspect if answer_aspect == DISCIPLINARY_ACTION_ASPECT else None
    spec["asked_aspect"] = retrieval_aspect
    spec["answer_aspect"] = answer_aspect
    spec["query_schema"]["answer_aspect"] = answer_aspect

    _apply_section_lookup(query, spec)

    audience = intent_schema.audience
    allow_employee_policy_patterns = audience in {"employee", "unknown"}

    if allow_employee_policy_patterns:
        false_reimbursement_pattern = next(item for item in BEHAVIOR_PATTERNS if item.behavior == "false_reimbursement")
        if any(trigger in query for trigger in false_reimbursement_pattern.triggers):
            _apply_behavior_pattern(spec, false_reimbursement_pattern, answer_aspect, query)

        rule_resolution = resolve_rule_query(query)
        if rule_resolution:
            _apply_rule_resolution(spec, rule_resolution)
        else:
            pattern = find_behavior_pattern(query)
            if pattern:
                _apply_behavior_pattern(spec, pattern, answer_aspect, query)

    if answer_aspect == DISCIPLINARY_ACTION_ASPECT and allow_employee_policy_patterns:
        _add_terms(spec, *DISCIPLINARY_ACTION_RETRIEVAL_TERMS)

    subclause_match = re.search(r"(?<!\d)(\d{1,2}\.\d+)(?!\d)", query)
    if subclause_match:
        subclause = subclause_match.group(1)
        _add_terms(spec, subclause)
        spec["target_subclause"] = subclause
        spec["target_clause_no"] = subclause.split(".")[0]

    spec["target_terms"] = _dedupe(spec.get("target_terms") or [])
    spec["rule_search_terms"] = _dedupe(spec.get("rule_search_terms") or [])
    spec["preferred_policy_titles"] = _dedupe(spec.get("preferred_policy_titles") or [])
    spec["exclude_sections"] = _dedupe(spec.get("exclude_sections") or [])
    spec["exclude_clauses"] = _dedupe(spec.get("exclude_clauses") or [])
    return spec
