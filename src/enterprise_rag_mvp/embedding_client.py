import httpx


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
