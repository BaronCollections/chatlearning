from enterprise_rag_mvp.document_chunking import chunk_parsed_document
from enterprise_rag_mvp.document_parsing import DocumentSource, HtmlDocumentParser


POLICY_TEXT = """
示例机构员工纪律制度
Example School Employee Disciplinary Rules

一、目的
为落实示例学校的使命、愿景和文化理念，根据有关法律法规和学校实际情况制定本制度。

四、违规行为

（一）一类违规行为
一类违规行为：指严重违法及社会公德、严重违反师德师风、严重违反保密义务的行为。
3. 严重违反保密义务行为
3.1获取或泄露员工工资、奖金、津贴补贴等个人待遇信息。
3.2以谋利、破坏学校经营等不当目的，获取、使用、泄露、传播、出售任何保密信息。

（二）二类违规行为
二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等致使学校经济、形象、声誉遭受严重损害的行为。
4. 破坏学校管理秩序行为
4.1渎职给学校造成较大损失。
4.2旷工少于三天。
4.3 使用未经批准的教材上课，给学校带来较大风险。

（三）三类违规行为
三类违规行为：指一般的违规行为。
5. 破坏学校管理秩序行为
5.1一学年中出现两次及两次以上上课迟到、早退和随意停课。
5.2工作期间饮酒和酒后从事教育学生的活动。

五、违规行为相应处理
1. 违规行为相应处理
1.1一类违规行为：处分生效当年年度绩效为“低于期望”，并解除劳动合同，永不再次录用。
1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪并取消当年年终奖激励资格。
1.3三类违规行为：予以书面或口头警告。

九、附件：
1.《新时代中小学教师职业行为十项准则》：https://example.com/policyDetail/515

Example School Employee Disciplinary Rules

Introduction

We are a group of people who share a common dream and gather together here at Example School.

V. Applicable Disciplinary Actions against Violations
1.2 Category 2 Violation: A written warning will be filed in the employee's record.
"""


def _parsed_policy():
    return HtmlDocumentParser().parse(
        DocumentSource(
            source_id="policy-16",
            source_name="员工纪律制度",
            file_name="policy.html",
            content_type="text/html",
            text=POLICY_TEXT,
        )
    )


BILINGUAL_POLICY_TEXT = """
示例机构员工纪律制度
Example School Employee Disciplinary Rules
2026-01-29 11:15:40
[摘要] 我们有着共同的教育梦想，为了同一个梦相聚在示例机构。
We are a group of people who share a common dream and gather together here at Example School.

示例学校的使命、培养目标和愿景

我们的使命是：
让每一位孩子成为最好的自己。
我们的愿景：
1. 办一所创新型的优质学校，探索面向未来的教育。
2. 通过科技的力量，让优质教育惠及更多的孩子，让东方智慧与世界文明相融合

Mission, Educational Goal and Vision of Example School

Our mission：
Bring out the best of every child.
Our vision：
1. Establish a creative and high-quality school, and explore the future of education;
2. Help more children to benefit from high quality education and blend wisdom and civilizations of both East and West.

示例学校员工纪律制度
引 言

我们有着共同的教育梦想，为了同一个梦相聚在示例机构。

一、目的
为落实示例学校的使命、愿景和文化理念，根据有关法律法规和学校实际情况制定本制度。

四、违规行为
（一）一类违规行为
一类违规行为：指严重违法及社会公德、严重违反师德师风的行为。
1. 违法行为：违反国家刑事法律，被追究刑事责任或被采取刑事强制措施。

（二）二类违规行为
二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等行为。
4. 破坏学校管理秩序行为
4.1渎职给学校造成较大损失。
4.2旷工少于三天。
4.3 使用未经批准的教材上课，给学校带来较大风险。

五、违规行为相应处理
1. 违规行为相应处理
1.2二类违规行为：予以记过处分。

Example School Employee Disciplinary Rules

Introduction
We are a group of people who share a common dream and gather together here at Example School.

IV. Violations
(II) Category 2 Violation
4. Conduct that disrupts the day-to-day operation of School
4.2 Absent from work without appropriate approval for less than three days.
"""


def _parsed_bilingual_policy():
    return HtmlDocumentParser().parse(
        DocumentSource(
            source_id="policy-bilingual",
            source_name="员工纪律制度",
            file_name="policy.html",
            content_type="text/html",
            text=BILINGUAL_POLICY_TEXT,
        )
    )


ENGLISH_ONLY_POLICY_TEXT = """
Example School Employee Disciplinary Rules

IV. Violations
(II) Category 2 Violation
4. Conduct that disrupts the day-to-day operation of School
4.2 Absent from work without appropriate approval for less than three days.
"""


def _parsed_english_only_policy():
    return HtmlDocumentParser().parse(
        DocumentSource(
            source_id="policy-en",
            source_name="Employee Disciplinary Rules",
            file_name="policy.html",
            content_type="text/html",
            text=ENGLISH_ONLY_POLICY_TEXT,
        )
    )


LEAVE_POLICY_TEXT = """
工作时间及假期管理制度

一、目的
为保障学校的正常运转和员工的合法假期权益，制定本假期政策。

五、假期标准
（一）假期申请及审批
1. 员工请假原则上须提前3个工作日在请假系统中提交申请。
（二）假期类型
1. 寒暑假
教学教师：暑假5周；寒假不少于20个日历天。
2. 带薪年假（适用于全体非教学老师）
2.1 按照员工的本单位连续工龄，年休假天数如下：
第一年 第二年 第三年 第四年 第五年 第六年及以后
10天 12天 14天 16天 18天 20天
2.1年休假不包括法定节假日及周末公休日；
2.2非教学老师使用年休假规则：非寒暑假时间（学期内）单次请假原则上不能连续超过5天;
3. 婚假
3.1 申请婚假须提供结婚证明。
4. 病假
4.1 一次申请病假1天以上，须提交医疗机构开具的有效病假单。
"""


def _parsed_leave_policy():
    return HtmlDocumentParser().parse(
        DocumentSource(
            source_id="leave-policy",
            source_name="工作时间及假期管理制度",
            file_name="leave.html",
            content_type="text/html",
            text=LEAVE_POLICY_TEXT,
        )
    )


def test_policy_chunker_structures_leave_policy_clause_groups():
    result = chunk_parsed_document(_parsed_leave_policy(), max_chars=1200, overlap_chars=150)

    annual_leave = next((chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "policy_clause_group" and "带薪年假" in chunk.text), None)

    assert result.quality.chunking_strategy == "policy_clause_group"
    assert result.quality.coverage_status == "complete"
    assert result.quality.element_coverage_status == "complete"
    assert annual_leave is not None
    assert annual_leave.metadata["chunk_role"] == "retrieval"
    assert annual_leave.metadata["section_title"] == "五、假期标准"
    assert annual_leave.metadata["clause_title"].startswith("2. 带薪年假")
    assert "第五年" in annual_leave.text
    assert "18天" in annual_leave.text
    assert "4. 病假" not in annual_leave.text


def test_policy_chunker_structures_english_only_policy_rules():
    result = chunk_parsed_document(_parsed_english_only_policy(), max_chars=1200, overlap_chars=150)

    english_group = next((chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "english_clause_group"), None)

    assert result.quality.chunking_strategy == "policy_clause_group"
    assert result.quality.coverage_status == "complete"
    assert result.quality.element_coverage_status == "complete"
    assert result.quality.english_retrieval_chunk_count >= 1
    assert english_group is not None
    assert english_group.metadata["violation_level"] == "category_2"
    assert english_group.metadata["clause_range"] == "4.2"
    assert "4.2 Absent from work without appropriate approval" in english_group.text


def test_policy_chunker_keeps_bilingual_front_matter_on_semantic_boundaries():
    result = chunk_parsed_document(_parsed_bilingual_policy(), max_chars=1200, overlap_chars=150)
    chunk_texts = [chunk.text for chunk in result.chunks]
    chunk_types = {chunk.metadata.get("chunk_type") for chunk in result.chunks}

    assert result.quality.status == "success"
    assert result.quality.coverage_status == "complete"
    assert result.quality.orphan_title_count == 0
    assert result.quality.english_retrieval_chunk_count >= 1
    assert "summary" in chunk_types
    assert "mission_section" in chunk_types
    assert any(chunk.metadata.get("chunk_type") == "summary" and chunk.metadata.get("language") == "zh" for chunk in result.chunks)
    assert any(chunk.metadata.get("chunk_type") == "summary" and chunk.metadata.get("language") == "en" for chunk in result.chunks)
    assert any(
        chunk.metadata.get("chunk_type") == "mission_section" and chunk.metadata.get("language") == "zh" for chunk in result.chunks
    )
    assert any(
        chunk.metadata.get("chunk_type") == "mission_section" and chunk.metadata.get("language") == "en" for chunk in result.chunks
    )
    assert not any("示例学校的使命" in text and "Mission, Educational Goal" in text for text in chunk_texts)
    assert not any("示例机构员工纪律制度" in text and "示例学校的使命" in text for text in chunk_texts)
    assert not any(text.startswith("East and West") for text in chunk_texts)
    assert not any(text == "四、违规行为" for text in chunk_texts)

    target = next(chunk for chunk in result.chunks if chunk.metadata.get("clause_title") == "4. 破坏学校管理秩序行为")
    assert target.metadata["chunk_type"] == "clause_group"
    assert target.metadata["violation_level"] == "category_2"
    assert target.metadata["clause_range"] == "4.1-4.3"
    assert target.heading_path == ["员工纪律制度", "二类违规行为", "4. 破坏学校管理秩序行为"]
    assert "4.2旷工少于三天" in target.text
    assert any(
        chunk.metadata.get("language") == "en" and "Example School Employee Disciplinary Rules" in chunk.text
        for chunk in result.chunks
    )


def test_policy_chunker_uses_precise_policy_and_english_structural_chunks():
    result = chunk_parsed_document(_parsed_bilingual_policy(), max_chars=1200, overlap_chars=150)

    policy_intro_chunks = [chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "policy_intro"]
    assert len(policy_intro_chunks) == 1
    assert "示例学校员工纪律制度 引 言" in policy_intro_chunks[0].text
    assert "我们有着共同的教育梦想" in policy_intro_chunks[0].text
    assert not any(chunk.metadata.get("chunk_type") == "document_intro" and chunk.text.startswith("我们有着共同的教育梦想") for chunk in result.chunks)

    overview = next(chunk for chunk in result.chunks if chunk.metadata.get("violation_level") == "category_2" and "破坏学校管理秩序" in chunk.text)
    assert overview.metadata["chunk_type"] == "violation_category_overview"
    assert overview.metadata["legacy_chunk_type"] == "section_overview"
    assert overview.metadata["chunk_role"] == "retrieval"
    assert overview.metadata["index_scope"] == "main"
    assert overview.metadata["retrieval_priority"] == "high"

    summary = next(chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "summary" and chunk.metadata.get("language") == "zh")
    assert summary.metadata["chunk_role"] == "coverage"
    assert summary.metadata["index_scope"] == "coverage"
    assert summary.metadata["retrieval_priority"] == "low"

    english_group = next(chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "english_clause_group")
    assert english_group.metadata["language"] == "en"
    assert english_group.metadata["chunk_role"] == "retrieval"
    assert english_group.metadata["index_scope"] == "main"
    assert english_group.metadata["retrieval_priority"] == "high"
    assert english_group.metadata["violation_level"] == "category_2"
    assert english_group.metadata["clause_no"] == "4"
    assert english_group.metadata["clause_range"] == "4.2"
    assert "4. Conduct that disrupts the day-to-day operation of School" in english_group.text
    assert "4.2 Absent from work without appropriate approval" in english_group.text


def test_policy_chunker_uses_clause_groups_without_crossing_violation_categories():
    result = chunk_parsed_document(_parsed_policy(), max_chars=1200, overlap_chars=150)

    target = next(chunk for chunk in result.chunks if chunk.metadata.get("clause_title") == "4. 破坏学校管理秩序行为")

    assert result.quality.status == "success"
    assert result.quality.chunking_strategy == "policy_clause_group"
    assert result.quality.chunk_profile == "policy_rule_auto"
    assert result.quality.coverage_status == "complete"
    assert target.metadata["chunk_type"] == "clause_group"
    assert target.metadata["violation_level"] == "category_2"
    assert target.metadata["clause_range"] == "4.1-4.3"
    assert target.metadata["language"] == "zh"
    assert target.heading_path == ["员工纪律制度", "二类违规行为", "4. 破坏学校管理秩序行为"]
    assert target.metadata["section_path"] == ["二类违规行为", "4. 破坏学校管理秩序行为"]
    assert "4.1渎职" in target.text
    assert "4.3 使用未经批准的教材" in target.text
    assert "三类违规行为" not in target.text
    assert "5.1一学年" not in target.text


def test_policy_chunker_splits_disciplinary_actions_by_violation_level():
    result = chunk_parsed_document(_parsed_policy(), max_chars=1200, overlap_chars=150)

    action = next(chunk for chunk in result.chunks if chunk.metadata.get("action_target") == "category_2")

    assert action.metadata["chunk_type"] == "action_clause"
    assert action.metadata["language"] == "zh"
    assert action.heading_path == ["员工纪律制度", "五、违规行为相应处理", "1.2 二类违规行为"]
    assert "1.2二类违规行为" in action.text
    assert "1.1一类违规行为" not in action.text
    assert "1.3三类违规行为" not in action.text


def test_policy_chunker_separates_chinese_and_english_sections():
    result = chunk_parsed_document(_parsed_policy(), max_chars=320, overlap_chars=80)

    english_chunks = [chunk for chunk in result.chunks if chunk.metadata.get("language") == "en"]
    assert english_chunks
    assert all("九、附件" not in chunk.text for chunk in english_chunks)
    assert all("二类违规行为" not in chunk.text for chunk in english_chunks)
    assert all(not chunk.text.startswith("nt,") for chunk in english_chunks)


def test_policy_chunker_preserves_all_document_material_with_complete_coverage():
    result = chunk_parsed_document(_parsed_policy(), max_chars=1200, overlap_chars=150)
    all_chunk_text = " ".join(chunk.text for chunk in result.chunks)
    chunk_types = {chunk.metadata.get("chunk_type") for chunk in result.chunks}

    assert result.quality.coverage_status == "complete"
    assert result.quality.uncovered_char_count == 0
    assert result.quality.source_char_count > 0
    assert result.quality.covered_char_count == result.quality.source_char_count
    assert "document_intro" in chunk_types
    assert "policy_section" in chunk_types
    assert "clause_group" in chunk_types
    assert "action_clause" in chunk_types
    assert "appendix" in chunk_types
    assert "english_section" in chunk_types
    assert "为落实示例学校的使命" in all_chunk_text
    assert "1.2二类违规行为：予以记过处分" in all_chunk_text
    assert "《新时代中小学教师职业行为十项准则》" in all_chunk_text
    assert "Example School Employee Disciplinary Rules" in all_chunk_text


def test_policy_chunker_attaches_element_provenance_to_every_structured_chunk():
    result = chunk_parsed_document(_parsed_bilingual_policy(), max_chars=1200, overlap_chars=150)

    assert result.quality.element_coverage_status == "complete"
    assert result.quality.source_element_count > 0
    assert result.quality.covered_element_count == result.quality.source_element_count
    assert result.quality.provenance_missing_count == 0
    assert result.quality.retrieval_provenance_missing_count == 0
    assert all(chunk.metadata.get("element_ids") for chunk in result.chunks)

    chinese_group = next(chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "clause_group")
    english_group = next(chunk for chunk in result.chunks if chunk.metadata.get("chunk_type") == "english_clause_group")
    assert chinese_group.metadata["element_ids"]
    assert english_group.metadata["element_ids"]
    assert chinese_group.metadata["element_range"]["start"] <= chinese_group.metadata["element_range"]["end"]
    assert english_group.metadata["element_range"]["start"] <= english_group.metadata["element_range"]["end"]


def test_policy_chunker_falls_back_explicitly_for_unstructured_text():
    parsed = HtmlDocumentParser().parse(
        DocumentSource(
            source_id="memo-1",
            source_name="普通说明",
            file_name="memo.html",
            content_type="text/html",
            text="这是一段普通说明，没有制度章节编号。它仍然应该可以被切成可检索片段。",
        )
    )

    result = chunk_parsed_document(parsed, max_chars=30, overlap_chars=5)

    assert result.quality.status == "success"
    assert result.quality.chunking_strategy == "fixed_window_fallback"
    assert result.quality.fallback_reason == "no_policy_structure_detected"
    assert result.quality.element_coverage_status == "complete"
    assert result.quality.provenance_missing_count == 0
    assert all(chunk.metadata.get("element_ids") for chunk in result.chunks)
    assert result.chunks[0].metadata["chunk_type"] == "fixed_window"


def test_policy_chunker_reports_partial_coverage_when_fallback_chunk_loses_source_span(monkeypatch):
    from enterprise_rag_mvp.document_chunking import policy_chunker

    parsed = HtmlDocumentParser().parse(
        DocumentSource(
            source_id="memo-broken",
            source_name="普通说明",
            file_name="memo.html",
            content_type="text/html",
            text="真实原文内容。",
        )
    )
    monkeypatch.setattr(policy_chunker, "fixed_window_chunks", lambda text, *, max_chars, overlap_chars: ["不存在的切块内容"])

    result = policy_chunker.chunk_parsed_document(parsed, max_chars=30, overlap_chars=5)

    assert result.quality.status == "success"
    assert result.quality.coverage_status == "partial"
    assert result.quality.covered_char_count == 0
    assert result.quality.provenance_missing_count == 1
    assert result.chunks[0].metadata.get("source_span") is None
