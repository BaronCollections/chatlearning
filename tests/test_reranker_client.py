import pytest

from enterprise_rag_mvp.reranker_client import _parse_rerank_scores


def test_parse_rerank_scores_accepts_plain_score_list():
    assert _parse_rerank_scores({"scores": [0.1, "0.9"]}, expected_count=2) == [0.1, 0.9]


def test_parse_rerank_scores_accepts_indexed_results():
    body = {"results": [{"index": 1, "score": 0.8}, {"index": 0, "score": 0.2}]}

    assert _parse_rerank_scores(body, expected_count=2) == [0.2, 0.8]


def test_parse_rerank_scores_rejects_wrong_count():
    with pytest.raises(ValueError, match="expected 2"):
        _parse_rerank_scores({"scores": [0.1]}, expected_count=2)
