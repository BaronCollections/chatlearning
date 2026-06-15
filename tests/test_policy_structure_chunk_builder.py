from enterprise_rag_mvp.document_parsing import DocumentSource, HtmlDocumentParser
from enterprise_rag_mvp.policy_structure import build_policy_chunks_from_structure, parse_policy_structure


def _structure():
    html = """
    <p>四、违规行为</p>
    <p>（二）二类违规行为</p>
    <p>二类违规行为：指违反师德师风、保密义务、破坏管理秩序等致使机构经济、形象、声誉遭受严重损害的行为。</p>
    <p>1. 师德师风相关的违规行为</p>
    <p>1.1违反教师职业行为准则中的限制性规定。</p>
    <p>2. 违反保密义务行为</p>
    <p>2.1非因工作需要获取、使用、泄露、传播保密信息。</p>
    <p>3. 侵犯机构权益行为</p>
    <p>3.1未经机构授权，以机构代表身份发表言论，造成不良影响。</p>
    <p>4. 破坏机构管理秩序行为</p>
    <p>4.1渎职给机构造成较大损失。</p>
    <p>4.2旷工少于三天。</p>
    <p>五、违规行为相应处理</p>
    <p>1. 违规行为相应处理</p>
    <p>1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪。</p>
    """
    parsed = HtmlDocumentParser().parse(
        DocumentSource(
            source_id="policy-16",
            source_name="员工纪律制度",
            content_type="text/html",
            text=html,
            source_url="https://example.com/policyDetail/16",
        )
    )
    return parse_policy_structure(
        parsed,
        doc_id="policy-16",
        source_name="员工纪律制度",
        base_heading_path=["***公司人守则", "员工纪律制度"],
        source_url="https://example.com/policyDetail/16",
    )


def test_build_policy_chunks_from_structure_emits_definition_children_leaf_and_action_chunks():
    structure = _structure()

    chunks = build_policy_chunks_from_structure(structure, base_metadata={"category_name": "***公司人守则"}, max_chars=1200)
    chunk_types = [chunk.metadata["chunk_type"] for chunk in chunks]

    assert "section_definition" in chunk_types
    assert "section_children" in chunk_types
    assert "leaf_clause" in chunk_types
    assert "action_mapping" in chunk_types

    children_chunk = next(chunk for chunk in chunks if chunk.metadata["chunk_type"] == "section_children")
    assert children_chunk.heading_path == ["***公司人守则", "员工纪律制度", "二类违规行为"]
    assert children_chunk.metadata["node_type"] == "violation_level"
    assert children_chunk.metadata["child_count"] == 4
    assert children_chunk.metadata["ordinal_sequence"] == ["1.", "2.", "3.", "4."]
    assert children_chunk.metadata["ordinal_continuity_status"] == "complete"
    assert "1. 师德师风相关的违规行为" in children_chunk.text
    assert "2. 违反保密义务行为" in children_chunk.text
    assert "3. 侵犯机构权益行为" in children_chunk.text
    assert "4. 破坏机构管理秩序行为" in children_chunk.text

    leaf = next(chunk for chunk in chunks if chunk.metadata.get("ordinal_label") == "4.2")
    assert leaf.metadata["chunk_type"] == "leaf_clause"
    assert leaf.metadata["parent_node_type"] == "violation_group"
    assert leaf.metadata["source_url"] == "https://example.com/policyDetail/16"
    assert leaf.heading_path[-2:] == ["4. 破坏机构管理秩序行为", "4.2 旷工少于三天。"]

    action = next(chunk for chunk in chunks if chunk.metadata["chunk_type"] == "action_mapping")
    assert action.metadata["action_target"] == "category_2"
    assert action.metadata["ordinal_label"] == "1.2"
    assert "予以记过处分" in action.text


def test_build_policy_chunks_marks_incomplete_child_sequences_without_renumbering():
    html = """
    <p>四、违规行为</p>
    <p>（二）二类违规行为</p>
    <p>二类违规行为：指比较严重的违规行为。</p>
    <p>1. 师德师风相关的违规行为</p>
    <p>2. 违反保密义务行为</p>
    <p>4. 破坏机构管理秩序行为</p>
    """
    parsed = HtmlDocumentParser().parse(DocumentSource(source_id="policy-16", source_name="员工纪律制度", text=html, content_type="text/html"))
    structure = parse_policy_structure(parsed, doc_id="policy-16", source_name="员工纪律制度")

    chunks = build_policy_chunks_from_structure(structure, max_chars=1200)
    children_chunk = next(chunk for chunk in chunks if chunk.metadata["chunk_type"] == "section_children")

    assert children_chunk.metadata["ordinal_sequence"] == ["1.", "2.", "4."]
    assert children_chunk.metadata["ordinal_continuity_status"] == "incomplete"
    assert children_chunk.metadata["missing_ordinals"] == [3]
    assert "4. 破坏机构管理秩序行为" in children_chunk.text
    assert "3. 破坏机构管理秩序行为" not in children_chunk.text
