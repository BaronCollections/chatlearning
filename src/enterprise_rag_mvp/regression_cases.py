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


REGRESSION_CASES: list[RegressionCase] = [
    RegressionCase(
        query="二类违规是什么",
        expected_doc_ids=["yungu-policy-16"],
        expected_keywords=["二类违规行为", "比较严重的违规行为"],
        forbidden_keywords=["三类违规行为：指一般的违规行为", "学生红黄灯"],
        expected_urls=["https://work.yungu.org/policyDetail/16"],
        tags=["definition", "discipline"],
    ),
    RegressionCase(
        query="二类违规的处罚是什么",
        expected_doc_ids=["yungu-policy-16"],
        expected_keywords=["二类、三类违规", "最终处理决定", "申诉"],
        forbidden_keywords=["二类违规行为：指违反师德师风"],
        expected_urls=["https://work.yungu.org/policyDetail/16"],
        tags=["disciplinary_action", "discipline"],
    ),
    RegressionCase(
        query="我旷工两天会受到什么处罚",
        expected_doc_ids=["yungu-policy-11", "yungu-policy-16"],
        expected_keywords=["连续旷工3个工作日以下", "扣除旷工期间工资", "记过处分", "二类违规行为", "4.2旷工少于三天"],
        forbidden_keywords=["辞退处分", "学生红黄灯", "属于一类违规行为"],
        expected_urls=["https://work.yungu.org/policyDetail/11", "https://work.yungu.org/policyDetail/16"],
        tags=["rule_resolver", "absence", "disciplinary_action"],
    ),
    RegressionCase(
        query="旷工三天会怎样",
        expected_doc_ids=["yungu-policy-11"],
        expected_keywords=["连续旷工3个工作日及以上", "扣除旷工期间工资", "辞退处分"],
        forbidden_keywords=["学生红黄灯", "记过处分；"],
        expected_urls=["https://work.yungu.org/policyDetail/11"],
        tags=["rule_resolver", "absence", "disciplinary_action"],
    ),
    RegressionCase(
        query="一年内旷工两次怎么处理",
        expected_doc_ids=["yungu-policy-11"],
        expected_keywords=["一年内累计两次及以上旷工", "扣除旷工期间工资", "辞退处分"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://work.yungu.org/policyDetail/11"],
        tags=["rule_resolver", "absence", "occurrence"],
    ),
    RegressionCase(
        query="虚假报销属于什么违规",
        expected_doc_ids=["yungu-policy-16"],
        expected_keywords=["虚假报销", "弄虚作假行为"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://work.yungu.org/policyDetail/16"],
        tags=["behavior", "classification"],
    ),
    RegressionCase(
        query="虚假报销怎么处罚",
        expected_doc_ids=["yungu-policy-16"],
        expected_keywords=["虚假报销", "弄虚作假行为"],
        forbidden_keywords=["学生红黄灯"],
        expected_urls=["https://work.yungu.org/policyDetail/16"],
        tags=["behavior", "disciplinary_action"],
    ),
    RegressionCase(
        query="打听工资属于什么违规",
        expected_doc_ids=["yungu-policy-16"],
        expected_keywords=["打听", "工资", "二类违规行为", "违反保密义务"],
        forbidden_keywords=["学生红黄灯", "三类违规行为"],
        expected_urls=["https://work.yungu.org/policyDetail/16"],
        tags=["behavior", "classification", "confidentiality"],
    ),
]


def cases_by_tag(tag: str) -> list[RegressionCase]:
    return [case for case in REGRESSION_CASES if tag in case.tags]
