from __future__ import annotations

import httpx


class RerankerClient:
    def __init__(self, *, base_url: str, provider: str = "external_cross_encoder", timeout: float = 30.0) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self.provider = provider

    def rerank(self, *, query: str, documents: list[str]) -> list[float]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must contain text")
        if not documents:
            return []
        response = httpx.post(
            f"{self._base_url}/rerank",
            json={"query": query, "documents": documents},
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        return _parse_rerank_scores(body, expected_count=len(documents))


def _parse_rerank_scores(body: dict, *, expected_count: int) -> list[float]:
    if isinstance(body.get("scores"), list):
        scores = [float(score) for score in body["scores"]]
    elif isinstance(body.get("results"), list):
        scores = [0.0] * expected_count
        seen_indexes: set[int] = set()
        for item in body["results"]:
            if not isinstance(item, dict):
                raise ValueError("rerank results items must be objects")
            index = int(item["index"])
            if index < 0 or index >= expected_count:
                raise ValueError(f"rerank result index out of range: {index}")
            scores[index] = float(item["score"])
            seen_indexes.add(index)
        if len(seen_indexes) != expected_count:
            raise ValueError(f"expected {expected_count} rerank results, got {len(seen_indexes)}")
    else:
        raise ValueError("rerank response must contain scores or results")
    if len(scores) != expected_count:
        raise ValueError(f"expected {expected_count} rerank scores, got {len(scores)}")
    return scores
