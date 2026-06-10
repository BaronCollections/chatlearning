from enterprise_rag_mvp.regression_cases import REGRESSION_CASES, cases_by_tag


def test_regression_cases_cover_core_policy_failures():
    queries = {case.query for case in REGRESSION_CASES}

    assert "二类违规是什么" in queries
    assert "二类违规的处罚是什么" in queries
    assert "我旷工两天会受到什么处罚" in queries
    assert "旷工三天会怎样" in queries
    assert "一年内旷工两次怎么处理" in queries
    assert "虚假报销属于什么违规" in queries
    assert "虚假报销怎么处罚" in queries
    assert "打听工资属于什么违规" in queries


def test_regression_cases_have_expected_and_forbidden_signals():
    for case in REGRESSION_CASES:
        assert case.expected_doc_ids
        assert case.expected_keywords
        assert case.expected_urls
        assert case.forbidden_keywords

    absence_cases = cases_by_tag("absence")
    assert len(absence_cases) == 3
    assert any("辞退处分" in case.expected_keywords for case in absence_cases)
