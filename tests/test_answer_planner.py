from enterprise_rag_mvp.answer_planner import plan_answer
from enterprise_rag_mvp.evidence_validator import EvidenceAssessment
from enterprise_rag_mvp.query_intent import understand_query


def test_plans_disciplinary_action_answer():
    intent = understand_query("我旷工两天会有什么处罚")
    assessments = [
        EvidenceAssessment("penalty", "action_evidence", True),
        EvidenceAssessment("classification", "classification_evidence", True),
    ]

    plan = plan_answer(intent, assessments, rule_resolution={"matched_rule": "连续旷工3个工作日以下"})

    assert plan.answer_type == "disciplinary_action"
    assert plan.sections == ["fact", "rule_match", "classification", "action", "citations", "uncertainty"]
    assert plan.cannot_answer_reason is None


def test_plans_conditional_answer_when_conditions_missing():
    intent = understand_query("骂人有什么处罚")
    assessments = [
        EvidenceAssessment("classification", "classification_evidence", True),
        EvidenceAssessment("action", "action_evidence", True),
    ]

    plan = plan_answer(intent, assessments)

    assert plan.answer_type == "conditional_disciplinary_action"
    assert "conditions" in plan.sections
    assert plan.uncertainty_notes
    assert any("对象为客户或来访者" in note for note in plan.uncertainty_notes)


def test_plan_refuses_action_answer_without_action_evidence():
    intent = understand_query("二类违规的处罚是什么")
    assessments = [EvidenceAssessment("definition", "definition_evidence", True)]

    plan = plan_answer(intent, assessments)

    assert plan.answer_type == "insufficient_evidence"
    assert plan.cannot_answer_reason
    assert "action_evidence" in plan.cannot_answer_reason
