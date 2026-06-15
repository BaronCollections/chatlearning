from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class GlossaryEntry:
    standard_term: str
    aliases: tuple[str, ...]
    expanded_terms: tuple[str, ...]
    target_object_type: str
    required_conditions: tuple[str, ...] = ()
    condition_term_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyTermExpansion:
    primary_standard_term: str | None
    standard_terms: dict[str, str]
    expanded_terms: list[str]
    matched_entries: list[str]
    target_object_types: dict[str, str]
    required_conditions: list[str]
    condition_term_groups: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict:
        return asdict(self)


GLOSSARY_ENTRIES: tuple[GlossaryEntry, ...] = (
    GlossaryEntry(
        standard_term="年休假",
        aliases=("年假", "年休假", "带薪年假", "带薪年休假", "休假管理办法"),
        expanded_terms=("年休假", "年假", "带薪年假", "带薪年休假", "休假管理办法"),
        target_object_type="benefit_rule",
    ),
    GlossaryEntry(
        standard_term="旷工",
        aliases=("旷工", "连续旷工", "擅自不出勤", "擅自离岗", "缺勤"),
        expanded_terms=("旷工", "连续旷工", "擅自不出勤", "擅自离岗", "缺勤"),
        target_object_type="behavior",
    ),
    GlossaryEntry(
        standard_term="语言不得体",
        aliases=("骂人", "说脏话", "脏话", "辱骂", "言语攻击", "语言不得体", "怠慢"),
        expanded_terms=("语言不得体", "骂人", "说脏话", "脏话", "辱骂", "言语攻击", "怠慢", "投诉"),
        target_object_type="behavior",
        required_conditions=("对象为客户或来访者", "并引起投诉"),
        condition_term_groups={
            "对象为客户或来访者": ("客户", "来访者"),
            "并引起投诉": ("投诉", "被投诉", "引起投诉"),
        },
    ),
    GlossaryEntry(
        standard_term="师德师风失范",
        aliases=("没有师德", "师德", "师德师风", "违反师德", "教师职业行为准则"),
        expanded_terms=("师德师风失范", "师德", "师德师风", "违反师德", "教师职业行为准则"),
        target_object_type="behavior",
    ),
    GlossaryEntry(
        standard_term="打听工资",
        aliases=("打听工资", "讨论工资", "工资", "奖金", "津贴补贴", "个人待遇"),
        expanded_terms=("打听工资", "打听、讨论员工工资", "工资", "奖金", "津贴补贴", "个人待遇信息", "二类违规行为", "违反保密义务行为"),
        target_object_type="behavior",
    ),
    GlossaryEntry(
        standard_term="虚假报销",
        aliases=("虚假报销", "报销未发生", "虚假理由报销"),
        expanded_terms=("虚假报销", "报销未发生的费用", "虚假理由报销", "弄虚作假行为", "二类违规行为"),
        target_object_type="behavior",
    ),
    GlossaryEntry(
        standard_term="二类违规行为",
        aliases=("二类违规", "二类违规行为"),
        expanded_terms=("二类违规行为", "二类违规"),
        target_object_type="policy_section",
    ),
    GlossaryEntry(
        standard_term="一类违规行为",
        aliases=("一类违规", "一类违规行为"),
        expanded_terms=("一类违规行为", "一类违规"),
        target_object_type="policy_section",
    ),
    GlossaryEntry(
        standard_term="三类违规行为",
        aliases=("三类违规", "三类违规行为"),
        expanded_terms=("三类违规行为", "三类违规"),
        target_object_type="policy_section",
    ),
)


def _append_unique(values: list[str], candidates: tuple[str, ...] | list[str]) -> None:
    for candidate in candidates:
        if candidate and candidate not in values:
            values.append(candidate)


def expand_policy_terms(query: str) -> PolicyTermExpansion:
    standard_terms: dict[str, str] = {}
    expanded_terms: list[str] = []
    matched_entries: list[str] = []
    target_object_types: dict[str, str] = {}
    required_conditions: list[str] = []
    condition_term_groups: dict[str, tuple[str, ...]] = {}

    for entry in GLOSSARY_ENTRIES:
        matched_aliases = [alias for alias in entry.aliases if alias in query]
        if not matched_aliases:
            continue
        matched_entries.append(entry.standard_term)
        target_object_types[entry.standard_term] = entry.target_object_type
        for alias in matched_aliases:
            standard_terms[alias] = entry.standard_term
        _append_unique(expanded_terms, list(entry.expanded_terms))
        _append_unique(required_conditions, list(entry.required_conditions))
        condition_term_groups.update(entry.condition_term_groups)

    return PolicyTermExpansion(
        primary_standard_term=matched_entries[0] if matched_entries else None,
        standard_terms=standard_terms,
        expanded_terms=expanded_terms,
        matched_entries=matched_entries,
        target_object_types=target_object_types,
        required_conditions=required_conditions,
        condition_term_groups=condition_term_groups,
    )
