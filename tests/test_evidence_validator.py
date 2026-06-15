from enterprise_rag_mvp.evidence_validator import assess_evidence
from enterprise_rag_mvp.models import PolicyChunk
from enterprise_rag_mvp.query_intent import understand_query


def _chunk(text: str, *, chunk_id: str = "chunk-1", heading_path: list[str] | None = None) -> PolicyChunk:
    return PolicyChunk(
        chunk_id=chunk_id,
        doc_id="doc-1",
        block_id=chunk_id,
        text=text,
        heading_path=heading_path or ["员工纪律制度"],
        metadata={"source": "sample"},
    )


def test_action_question_rejects_definition_only_evidence():
    intent = understand_query("二类违规的处罚是什么")
    assessment = assess_evidence(
        _chunk("（二）二类违规行为 二类违规行为：指比较严重的违规行为。"),
        intent,
    )

    assert assessment.evidence_type == "insufficient_evidence"
    assert not assessment.usable_as_final
    assert "处罚" in assessment.reason or "处理" in assessment.reason


def test_action_question_accepts_action_evidence():
    intent = understand_query("二类违规的处罚是什么")
    assessment = assess_evidence(
        _chunk("五、违规行为相应处理 1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪。"),
        intent,
    )

    assert assessment.evidence_type == "action_evidence"
    assert assessment.usable_as_final
    assert "二类违规行为" in assessment.matched_terms


def test_table_lookup_accepts_annual_leave_table_evidence():
    intent = understand_query("工作五年有几天年假")
    assessment = assess_evidence(
        _chunk("带薪年假 年休假天数如下：第一年 第二年 第三年 第四年 第五年 第六年及以后 10天 12天 14天 16天 18天 20天。"),
        intent,
    )

    assert assessment.evidence_type == "table_evidence"
    assert assessment.usable_as_final


def test_reference_only_evidence_is_not_final_answer():
    intent = understand_query("虚假报销怎么处理")
    assessment = assess_evidence(
        _chunk("虚假报销的处理规则具体参见《员工纪律制度》相关条款。"),
        intent,
    )

    assert assessment.evidence_type == "cross_reference_evidence"
    assert not assessment.usable_as_final
