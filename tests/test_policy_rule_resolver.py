from enterprise_rag_mvp.policy_rule_resolver import build_policy_lookup_spec, resolve_rule_query


def test_absenteeism_two_days_resolves_to_under_three_workday_rule():
    resolution = resolve_rule_query("我旷工两天会受到什么处罚")

    assert resolution is not None
    assert resolution.user_fact == "旷工 2 天"
    assert resolution.behavior == "absenteeism"
    assert resolution.behavior_label == "旷工"
    assert resolution.answer_aspect == "disciplinary_action"
    assert resolution.matched_rule == "连续旷工3个工作日以下"
    assert resolution.comparison == "2 < 3"
    assert resolution.expected_evidence == ["扣除旷工期间工资", "记过处分"]
    assert "二类违规行为" in resolution.classification_terms


def test_absenteeism_three_days_resolves_to_dismissal_rule():
    resolution = resolve_rule_query("旷工三天会怎样")

    assert resolution is not None
    assert resolution.user_fact == "旷工 3 天"
    assert resolution.matched_rule == "连续旷工3个工作日及以上"
    assert resolution.comparison == "3 >= 3"
    assert resolution.expected_evidence == ["扣除旷工期间工资", "辞退处分"]


def test_absenteeism_twice_in_one_year_resolves_to_occurrence_rule():
    resolution = resolve_rule_query("一年内旷工两次怎么处理")

    assert resolution is not None
    assert resolution.condition_parameters["occurrence_count"] == {"value": 2, "unit": "time"}
    assert resolution.condition_parameters["time_window"] == "一年内"
    assert resolution.matched_rule == "一年内累计两次及以上旷工"
    assert resolution.comparison == "2 >= 2"
    assert "辞退处分" in resolution.expected_evidence


def test_policy_lookup_spec_exposes_unified_schema_for_rule_queries():
    spec = build_policy_lookup_spec("我旷工两天会受到什么处罚")

    assert spec["retrieval_intent"] == "exact_policy_lookup"
    assert spec["query_schema"]["target_object"] == {"type": "behavior", "value": "旷工", "key": "absenteeism"}
    assert spec["query_schema"]["answer_aspect"] == "disciplinary_action"
    assert spec["query_schema"]["condition_parameters"]["duration"] == {"value": 2, "unit": "day"}
    assert spec["rule_resolution"]["matched_rule"] == "连续旷工3个工作日以下"
    assert "连续旷工3个工作日以下" in spec["rule_search_terms"]
    assert "扣除旷工期间工资" in spec["expected_evidence"]


def test_catalog_covers_salary_inquiry_and_false_reimbursement_queries():
    salary = build_policy_lookup_spec("打听工资属于什么违规")
    reimbursement = build_policy_lookup_spec("虚假报销怎么处理")

    assert salary["target_behavior"] == "salary_inquiry"
    assert salary["target_subclause"] == "2.3"
    assert salary["query_schema"]["target_object"]["value"] == "打听工资"
    assert "二类违规行为" in salary["target_terms"]

    assert reimbursement["target_behavior"] == "false_reimbursement"
    assert reimbursement["target_clause"] == "4. 弄虚作假行为"
    assert reimbursement["target_subclause"] == "4.3"
    assert reimbursement["query_schema"]["target_object"]["value"] == "虚假报销"
