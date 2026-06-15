from enterprise_rag_mvp.document_parsing import DocumentSource, HtmlDocumentParser
from enterprise_rag_mvp.policy_structure import parse_policy_structure


POLICY_HTML = """
<h1>***公司人守则-员工纪律制度</h1>
<p>四、违规行为</p>
<p>（二）二类违规行为</p>
<p>二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等致使机构经济、形象、声誉遭受严重损害的行为。</p>
<p>1. 师德师风相关的违规行为</p>
<p>1.1违反教师职业行为准则中的限制性规定。</p>
<p>2. 违反保密义务行为</p>
<p>2.1非因工作需要获取、使用、泄露、传播保密信息。</p>
<p>2.2打听、讨论员工工资、奖金、津贴补贴等个人待遇信息。</p>
<p>3. 侵犯机构权益行为</p>
<p>3.1未经机构授权，以机构代表身份向媒体发表言论，造成不良影响。</p>
<p>4. 破坏机构管理秩序行为</p>
<p>4.1渎职给机构造成较大损失。</p>
<p>4.2旷工少于三天。</p>
<p>（三）三类违规行为</p>
<p>三类违规行为：指一般的违规行为。</p>
<p>五、违规行为相应处理</p>
<p>1. 违规行为相应处理</p>
<p>1.1一类违规行为：解除劳动合同。</p>
<p>1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪。</p>
<p>1.3三类违规行为：予以书面或口头警告。</p>
"""


def _parse(html: str = POLICY_HTML):
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


def test_parse_policy_structure_preserves_violation_children_ordinals_and_parentage():
    structure = _parse()

    category_2 = structure.find_first(node_type="violation_level", title="二类违规行为")
    assert category_2 is not None
    assert category_2.ordinal_label == "（二）"
    assert category_2.metadata["violation_level"] == "category_2"
    assert "二类违规行为：指违反师德师风" in category_2.text

    children = structure.children_of(category_2.node_id, node_type="violation_group")
    assert [child.ordinal_label for child in children] == ["1.", "2.", "3.", "4."]
    assert [child.title for child in children] == [
        "师德师风相关的违规行为",
        "违反保密义务行为",
        "侵犯机构权益行为",
        "破坏机构管理秩序行为",
    ]

    fourth = children[3]
    assert fourth.ordinal_value == 4
    assert fourth.heading_path[-1] == "4. 破坏机构管理秩序行为"

    subclauses = structure.children_of(fourth.node_id, node_type="leaf_clause")
    assert [sub.ordinal_label for sub in subclauses] == ["4.1", "4.2"]
    assert all(sub.parent_id == fourth.node_id for sub in subclauses)
    assert "旷工少于三天" in subclauses[1].text


def test_parse_policy_structure_keeps_action_mapping_outside_violation_level():
    structure = _parse()
    category_2 = structure.find_first(node_type="violation_level", title="二类违规行为")
    action = structure.find_first(node_type="action_mapping", title="二类违规行为")

    assert action is not None
    assert action.parent_id != category_2.node_id
    assert action.metadata["action_target"] == "category_2"
    assert action.ordinal_label == "1.2"
    assert "予以记过处分" in action.text
    assert "五、违规行为相应处理" in action.heading_path


def test_parse_policy_structure_reports_missing_group_ordinals():
    structure = _parse(
        POLICY_HTML.replace(
            "<p>3. 侵犯机构权益行为</p>\n<p>3.1未经机构授权，以机构代表身份向媒体发表言论，造成不良影响。</p>\n",
            "",
        )
    )

    assert structure.quality.status == "partial"
    assert any(issue["code"] == "missing_ordinal" and issue["missing"] == [3] for issue in structure.quality.issues)


def test_parse_policy_structure_reports_duplicate_group_ordinals():
    structure = _parse(POLICY_HTML.replace("<p>4. 破坏机构管理秩序行为</p>", "<p>3. 破坏机构管理秩序行为</p>"))

    assert structure.quality.status == "partial"
    assert any(issue["code"] == "duplicate_ordinal" and issue["ordinal"] == 3 for issue in structure.quality.issues)
