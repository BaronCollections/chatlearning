from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegressionCase:
    query: str
    expected_doc_ids: list[str]
    expected_keywords: list[str]
    forbidden_keywords: list[str] = field(default_factory=list)
    expected_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category: str = "general"
    expected_answer_type: str | None = None
    expected_evidence_types: list[str] = field(default_factory=list)


REGRESSION_CASES: list[RegressionCase] = [
    RegressionCase(
        query="员工年假规则是什么？",
        category="leave",
        expected_doc_ids=["employee-leave-policy"],
        expected_keywords=["带薪年假", "第一年", "第六年及以后"],
        forbidden_keywords=["旷工处理", "员工纪律制度"],
        expected_urls=["https://example.com/policyDetail/3"],
        expected_answer_type="table_lookup",
        expected_evidence_types=["table_evidence"],
        tags=["leave", "table_lookup"],
    ),
    RegressionCase(
        query="工作五年有几天年假",
        category="leave",
        expected_doc_ids=["employee-leave-policy"],
        expected_keywords=["第五年", "18天"],
        forbidden_keywords=["旷工处理", "员工纪律制度"],
        expected_urls=["https://example.com/policyDetail/3"],
        expected_answer_type="table_lookup",
        expected_evidence_types=["table_evidence"],
        tags=["leave", "table_lookup"],
    ),
    RegressionCase(
        query="二类违规是什么",
        category="discipline",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["二类违规行为", "违反师德师风"],
        forbidden_keywords=["三类违规行为：指一般的违规行为", "学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/16"],
        expected_answer_type="definition",
        expected_evidence_types=["definition_evidence"],
        tags=["definition", "discipline"],
    ),
    RegressionCase(
        query="二类违规的处罚是什么",
        category="discipline",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["二类违规行为", "予以记过处分", "一年内不得调薪"],
        forbidden_keywords=["二类违规行为：指违反师德师风"],
        expected_urls=["https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["disciplinary_action", "discipline"],
    ),
    RegressionCase(
        query="我旷工两天会受到什么处罚",
        category="attendance",
        expected_doc_ids=["worktime-leave-policy", "employee-discipline-policy"],
        expected_keywords=["连续旷工3个工作日以下", "扣除旷工期间工资", "记过处分", "二类违规行为", "4.2旷工少于三天"],
        forbidden_keywords=["辞退处分", "学生红黄灯", "属于一类违规行为"],
        expected_urls=["https://example.com/policyDetail/11", "https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["rule_resolver", "absence", "disciplinary_action"],
    ),
    RegressionCase(
        query="旷工会有什么处罚",
        category="attendance",
        expected_doc_ids=["worktime-leave-policy", "employee-discipline-policy"],
        expected_keywords=["连续旷工3个工作日以下", "连续旷工3个工作日及以上", "记过处分", "辞退处分"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/11", "https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["absence", "missing_condition", "disciplinary_action"],
    ),
    RegressionCase(
        query="旷工三天会怎样",
        category="attendance",
        expected_doc_ids=["worktime-leave-policy", "employee-discipline-policy"],
        expected_keywords=["连续旷工3个工作日及以上", "扣除旷工期间工资", "辞退处分", "一类违规行为"],
        forbidden_keywords=["学生红黄灯", "记过处分；"],
        expected_urls=["https://example.com/policyDetail/11", "https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["rule_resolver", "absence", "disciplinary_action"],
    ),
    RegressionCase(
        query="一年内旷工两次怎么处理",
        category="attendance",
        expected_doc_ids=["worktime-leave-policy", "employee-discipline-policy"],
        expected_keywords=["一年内累计两次及以上旷工", "扣除旷工期间工资", "辞退处分"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/11"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["rule_resolver", "absence", "occurrence"],
    ),
    RegressionCase(
        query="员工缺勤两天会怎样",
        category="attendance",
        expected_doc_ids=["worktime-leave-policy", "employee-discipline-policy"],
        expected_keywords=["事实：旷工 2 天", "连续旷工3个工作日以下", "记过处分", "二类违规行为"],
        forbidden_keywords=["辞退处分", "学生红黄灯", "属于一类违规行为"],
        expected_urls=["https://example.com/policyDetail/11", "https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["rule_resolver", "absence", "synonym", "disciplinary_action"],
    ),
    RegressionCase(
        query="早退两次怎么处理",
        category="attendance",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["事实：早退", "一学年中出现两次及两次以上", "三类违规行为", "书面或口头警告"],
        forbidden_keywords=["考勤管理制度 > 第五条 迟到早退", "一类违规行为中的", "二类违规行为中的"],
        expected_urls=["https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["behavior", "lateness", "disciplinary_action"],
    ),
    RegressionCase(
        query="学生迟到怎么处理",
        category="audience_scope",
        expected_doc_ids=[],
        expected_keywords=["没有在当前制度样本中检索到足够相关的内容"],
        forbidden_keywords=["员工纪律制度", "予以书面或口头警告"],
        expected_urls=[],
        expected_answer_type="insufficient_evidence",
        expected_evidence_types=[],
        tags=["audience_scope", "student", "no_relevant_policy"],
    ),
    RegressionCase(
        query="骂人有什么处罚",
        category="discipline",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["语言不得体", "对象为客户或来访者", "并引起投诉", "书面或口头警告"],
        forbidden_keywords=["一类违规行为中的"],
        expected_urls=["https://example.com/policyDetail/16"],
        expected_answer_type="conditional_disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["behavior", "conditional", "disciplinary_action"],
    ),
    RegressionCase(
        query="没有师德会有什么处罚",
        category="discipline",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["师德师风", "二类违规行为", "记过处分"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/16"],
        expected_answer_type="disciplinary_action",
        expected_evidence_types=["action_evidence"],
        tags=["behavior", "disciplinary_action"],
    ),
    RegressionCase(
        query="虚假报销属于什么违规",
        category="discipline",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["虚假报销", "弄虚作假行为"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/16"],
        tags=["behavior", "classification"],
    ),
    RegressionCase(
        query="虚假报销怎么处罚",
        category="discipline",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["虚假报销", "弄虚作假行为"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://example.com/policyDetail/16"],
        tags=["behavior", "disciplinary_action"],
    ),
    RegressionCase(
        query="打听工资属于什么违规",
        category="confidentiality",
        expected_doc_ids=["employee-discipline-policy"],
        expected_keywords=["打听", "工资", "二类违规行为", "违反保密义务"],
        forbidden_keywords=["学生红黄灯", "三类违规行为"],
        expected_urls=["https://example.com/policyDetail/16"],
        tags=["behavior", "classification", "confidentiality"],
    ),
]


def cases_by_tag(tag: str) -> list[RegressionCase]:
    return [case for case in REGRESSION_CASES if tag in case.tags]
