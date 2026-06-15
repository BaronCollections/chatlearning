from enterprise_rag_mvp.policy_glossary import expand_policy_terms


def test_expands_colloquial_language_to_policy_terms():
    expansion = expand_policy_terms("骂人有什么处罚")

    assert expansion.primary_standard_term == "语言不得体"
    assert "语言不得体" in expansion.expanded_terms
    assert "投诉" in expansion.expanded_terms
    assert expansion.standard_terms["骂人"] == "语言不得体"
    assert "对象为客户或来访者" in expansion.required_conditions


def test_expands_leave_terms():
    expansion = expand_policy_terms("员工年假规则是什么")

    assert expansion.primary_standard_term == "年休假"
    assert "年假" in expansion.expanded_terms
    assert "年休假" in expansion.expanded_terms
    assert "带薪年假" in expansion.expanded_terms


def test_keeps_multiple_business_objects_when_query_mentions_two_terms():
    expansion = expand_policy_terms("员工年假和旷工规则")

    assert expansion.primary_standard_term == "年休假"
    assert expansion.standard_terms["年假"] == "年休假"
    assert expansion.standard_terms["旷工"] == "旷工"
    assert "旷工" in expansion.expanded_terms
