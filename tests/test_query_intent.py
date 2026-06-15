from enterprise_rag_mvp.query_intent import (
    DISCIPLINARY_ACTION_ASPECT,
    DEFINITION_ASPECT,
    TABLE_LOOKUP_ASPECT,
    understand_query,
)


def test_extracts_policy_action_question_with_duration():
    intent = understand_query("我旷工两天会有什么处罚")

    assert intent.normalized_query == "我旷工两天会有什么处罚"
    assert intent.target_object == "旷工"
    assert intent.target_object_type == "behavior"
    assert intent.asked_aspect == DISCIPLINARY_ACTION_ASPECT
    assert intent.condition_parameters["duration"] == 2
    assert intent.condition_parameters["unit"] == "day"
    assert intent.audience == "employee"
    assert "action_evidence" in intent.required_evidence_types
    assert "classification_evidence" in intent.required_evidence_types
    assert intent.confidence >= 0.75


def test_extracts_definition_question():
    intent = understand_query("二类违规是什么")

    assert intent.target_object == "二类违规行为"
    assert intent.target_object_type == "policy_section"
    assert intent.asked_aspect == DEFINITION_ASPECT
    assert "definition_evidence" in intent.required_evidence_types
    assert intent.condition_parameters == {}


def test_extracts_annual_leave_table_lookup():
    intent = understand_query("工作五年有几天年假")

    assert intent.target_object == "年休假"
    assert intent.target_object_type == "benefit_rule"
    assert intent.asked_aspect == TABLE_LOOKUP_ASPECT
    assert intent.condition_parameters["work_year"] == 5
    assert "年假" in intent.glossary_expansions
    assert "年休假" in intent.glossary_expansions
    assert "table_evidence" in intent.required_evidence_types


def test_marks_missing_conditions_for_colloquial_language_query():
    intent = understand_query("骂人有什么处罚")

    assert intent.target_object == "语言不得体"
    assert intent.target_object_type == "behavior"
    assert intent.asked_aspect == DISCIPLINARY_ACTION_ASPECT
    assert "对象为客户或来访者" in intent.missing_conditions
    assert "并引起投诉" in intent.missing_conditions
    assert "语言不得体" in intent.glossary_expansions
    assert "condition_evidence" in intent.required_evidence_types


def test_extracts_classification_question():
    intent = understand_query("虚假报销属于什么违规")

    assert intent.target_object == "虚假报销"
    assert intent.target_object_type == "behavior"
    assert intent.asked_aspect == "classification"
    assert "classification_evidence" in intent.required_evidence_types
