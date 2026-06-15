from enterprise_rag_mvp.regression_cases import REGRESSION_CASES, cases_by_tag


def test_regression_cases_cover_core_policy_failures():
    queries = {case.query for case in REGRESSION_CASES}

    assert "二类违规是什么" in queries
    assert "二类违规的处罚是什么" in queries
    assert "我旷工两天会受到什么处罚" in queries
    assert "旷工三天会怎样" in queries
    assert "一年内旷工两次怎么处理" in queries
    assert "员工缺勤两天会怎样" in queries
    assert "早退两次怎么处理" in queries
    assert "学生迟到怎么处理" in queries
    assert "虚假报销属于什么违规" in queries
    assert "虚假报销怎么处罚" in queries
    assert "打听工资属于什么违规" in queries


def test_regression_cases_have_expected_and_forbidden_signals():
    for case in REGRESSION_CASES:
        assert case.expected_keywords
        assert case.forbidden_keywords
        if "no_relevant_policy" not in case.tags:
            assert case.expected_doc_ids
            assert case.expected_urls

    no_policy_cases = cases_by_tag("no_relevant_policy")
    assert no_policy_cases
    assert all(not case.expected_doc_ids for case in no_policy_cases)

    absence_cases = cases_by_tag("absence")
    assert len(absence_cases) >= 4
    assert any("missing_condition" in case.tags for case in absence_cases)
    assert any("辞退处分" in case.expected_keywords for case in absence_cases)
