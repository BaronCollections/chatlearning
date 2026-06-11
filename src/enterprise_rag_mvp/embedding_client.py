import hashlib
import math

import httpx


class DeterministicEmbeddingClient:
    """Small local embedding provider for offline demo and tests.

    It is not a production embedding model. The vector keeps enough business
    term signal for the built-in policy samples, so the Web app can run on an
    isolated server without a BGE service. Production deployments should keep
    using ``EmbeddingClient`` with a real model service.
    """

    _TERM_FEATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("annual_leave", ("年假", "年休假", "带薪年休假", "休假")),
        ("late_or_early", ("迟到", "早退")),
        ("absence", ("旷工", "矿工", "缺勤")),
        ("disciplinary_action", ("处罚", "处分", "处理", "记过", "辞退", "扣除", "工资")),
        ("violation_class", ("一类违规", "二类违规", "三类违规", "违规", "纪律", "破坏学校管理秩序")),
        ("expense", ("报销", "差旅", "票据", "费用", "虚假")),
        ("security", ("数据", "外传", "账号", "凭证", "保密", "待遇", "薪酬")),
        ("employee", ("员工", "老师", "教师", "学校")),
    )
    _HASH_BUCKETS = 8

    @property
    def dimension(self) -> int:
        return len(self._TERM_FEATURES) + self._HASH_BUCKETS

    def tokenize(self, text: str) -> dict:
        tokens = list(text)
        return {
            "text": text,
            "tokens": tokens,
            "token_ids": [ord(token) for token in tokens],
            "token_count": len(tokens),
            "tokenizer": "local-deterministic-char-tokenizer",
            "max_input_tokens": None,
            "truncated": False,
            "note": "Offline demo tokenizer. Production should use the tokenizer from the real embedding model, such as BGE-M3.",
        }

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        if input_type not in {"query", "document"}:
            raise ValueError(f"unsupported input_type: {input_type}")
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        normalized = "".join(str(text).split()).lower()
        for index, (_name, terms) in enumerate(self._TERM_FEATURES):
            for term in terms:
                count = normalized.count(term.lower())
                if count:
                    vector[index] += float(count * max(len(term), 1))

        for char in normalized:
            digest = hashlib.blake2b(char.encode("utf-8"), digest_size=2).digest()
            bucket = int.from_bytes(digest, "big") % self._HASH_BUCKETS
            vector[len(self._TERM_FEATURES) + bucket] += 0.15

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 8) for value in vector]


class EmbeddingClient:
    def __init__(self, *, base_url: str, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        response = httpx.post(
            f"{self._base_url}/embed",
            json={"texts": texts, "input_type": input_type, "normalize": True},
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        return body["embeddings"]

    def tokenize(self, text: str) -> dict:
        response = httpx.post(
            f"{self._base_url}/tokenize",
            json={"text": text},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()
