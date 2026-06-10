from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol

import httpx

from enterprise_rag_mvp.models import PolicyChunk

DEFAULT_YUNGU_BASE_URL = "https://work.yungu.org"
DEFAULT_POLICY_TYPE = 2


class YunguApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class YunguInformationPage:
    rows: list[dict[str, Any]]
    total: int
    page_num: int
    page_size: int


@dataclass(frozen=True)
class YunguImportStats:
    documents_seen: int = 0
    documents_imported: int = 0
    documents_skipped: int = 0
    chunks_stored: int = 0
    pages_read: int = 0


class EmbeddingLike(Protocol):
    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        ...


class StoreLike(Protocol):
    def upsert_chunks(self, chunks: list[PolicyChunk], embeddings: list[list[float]]) -> None:
        ...


class _HTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
        "ol",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth == 0 and tag in self._BLOCK_TAGS:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if self._ignored_depth == 0 and tag in self._BLOCK_TAGS:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_html_to_text(raw_html: str | None) -> str:
    if not raw_html:
        return ""
    extractor = _HTMLTextExtractor()
    extractor.feed(str(raw_html))
    extractor.close()
    return normalize_whitespace(html.unescape(extractor.text()).replace("\xa0", " "))


def chunk_text(text: str, *, max_chars: int = 1200, overlap_chars: int = 150) -> list[str]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            sentence_boundary = max(normalized.rfind(mark, start, end) for mark in ["。", "；", ";", ".", "\n"])
            if sentence_boundary > start + max_chars // 2:
                end = sentence_boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)
    return chunks


def _first_non_empty(*values: Any, fallback: str = "") -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def _metadata_value(detail: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in detail and detail[key] not in (None, ""):
            return detail[key]
    return None


def detail_to_policy_chunks(
    detail: dict[str, Any],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[PolicyChunk]:
    import_id = _metadata_value(detail, "importInformationId", "id")
    if import_id is None:
        raise ValueError("detail missing importInformationId")

    title = _first_non_empty(detail.get("cnTitle"), detail.get("title"), detail.get("enTitle"), fallback=f"policy-{import_id}")
    category_name = _first_non_empty(detail.get("policyCategoryTypeName"), detail.get("categoryTypeName"), detail.get("categoryName"))
    text = clean_html_to_text(detail.get("body"))
    chunks = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
    if not chunks:
        return []

    doc_id = f"yungu-policy-{import_id}"
    heading_path = [value for value in [category_name, title] if value]
    file_list = detail.get("fileList") or []
    metadata = {
        "source": "yungu_policy_system",
        "import_information_id": import_id,
        "title": title,
        "cn_title": detail.get("cnTitle"),
        "en_title": detail.get("enTitle"),
        "publish_date": detail.get("publishDate"),
        "policy_category_type": detail.get("policyCategoryType"),
        "policy_category_type_name": category_name or None,
        "policy_system_type": detail.get("policySystemType"),
        "create_user_name": detail.get("createUserName"),
        "file_count": len(file_list) if isinstance(file_list, list) else 0,
    }

    return [
        PolicyChunk(
            chunk_id=f"{doc_id}-chunk-{index:04d}",
            doc_id=doc_id,
            block_id=f"chunk-{index:04d}",
            text=chunk,
            heading_path=heading_path or [title],
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


class YunguPolicyClient:
    def __init__(
        self,
        *,
        session: str,
        base_url: str = DEFAULT_YUNGU_BASE_URL,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        session = session.strip()
        if not session:
            raise ValueError("session must not be blank")
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self._base_url}/home/policyList",
                "Cookie": f"SESSION={self._session}",
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "YunguPolicyClient":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _get_json(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise YunguApiError(f"Yungu API returned non-JSON for {path}") from exc
        if not isinstance(payload, dict):
            raise YunguApiError(f"Yungu API returned unexpected payload type for {path}")
        if payload.get("ifLogin") is False:
            raise YunguApiError("Yungu API session is not logged in or has expired")
        if payload.get("status") is False or payload.get("code") not in (None, 0, 200, "0", "200"):
            message = payload.get("message") or payload.get("msg") or "unknown error"
            raise YunguApiError(f"Yungu API error for {path}: {message}")
        return payload

    def fetch_information_page(
        self,
        *,
        page_num: int,
        page_size: int,
        policy_type: int = DEFAULT_POLICY_TYPE,
        category_id: int | None = None,
        keyword: str = "",
    ) -> YunguInformationPage:
        if page_num <= 0:
            raise ValueError("page_num must be positive")
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        params: dict[str, Any] = {
            "keyword": keyword,
            "pageNum": page_num,
            "pageSize": page_size,
            "policyType": policy_type,
        }
        if category_id is not None:
            params["policyCategoryType"] = category_id
        payload = self._get_json("/api/import/informationList", params=params)
        content = payload.get("content") or {}
        if not isinstance(content, dict):
            raise YunguApiError("informationList content must be an object")
        rows = content.get("data") or content.get("list") or []
        if not isinstance(rows, list):
            raise YunguApiError("informationList rows must be a list")
        return YunguInformationPage(
            rows=[row for row in rows if isinstance(row, dict)],
            total=int(content.get("total") or 0),
            page_num=int(content.get("pageNum") or page_num),
            page_size=int(content.get("pageSize") or page_size),
        )

    def fetch_detail(self, import_information_id: int | str) -> dict[str, Any]:
        if not str(import_information_id).strip():
            raise ValueError("import_information_id must not be blank")
        payload = self._get_json(
            "/api/import/notificationById",
            params={"importInformationId": import_information_id},
        )
        content = payload.get("content") or {}
        if not isinstance(content, dict):
            raise YunguApiError("notificationById content must be an object")
        return content


def _batched(items: list[Any], batch_size: int) -> list[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _row_import_id(row: dict[str, Any]) -> Any:
    return _metadata_value(row, "importInformationId", "id")


def ingest_yungu_policies(
    *,
    client: Any,
    embedding_client: EmbeddingLike,
    store: StoreLike,
    policy_type: int = DEFAULT_POLICY_TYPE,
    category_id: int | None = None,
    page_size: int = 50,
    max_docs: int | None = None,
    max_pages: int | None = None,
    chunk_max_chars: int = 1200,
    chunk_overlap_chars: int = 150,
    embedding_batch_size: int = 16,
    keyword: str = "",
    dry_run: bool = False,
) -> YunguImportStats:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if max_docs is not None and max_docs <= 0:
        raise ValueError("max_docs must be positive when provided")
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages must be positive when provided")

    documents_seen = 0
    documents_imported = 0
    documents_skipped = 0
    chunks_stored = 0
    pages_read = 0
    page_num = 1
    total_pages: int | None = None

    while True:
        if max_pages is not None and pages_read >= max_pages:
            break
        page = client.fetch_information_page(
            page_num=page_num,
            page_size=page_size,
            policy_type=policy_type,
            category_id=category_id,
            keyword=keyword,
        )
        pages_read += 1
        if total_pages is None:
            total_pages = max(1, math.ceil(page.total / page_size)) if page.total else 1

        if not page.rows:
            break

        for row in page.rows:
            if max_docs is not None and documents_seen >= max_docs:
                return YunguImportStats(documents_seen, documents_imported, documents_skipped, chunks_stored, pages_read)
            import_id = _row_import_id(row)
            if import_id is None:
                documents_seen += 1
                documents_skipped += 1
                continue

            documents_seen += 1
            detail = client.fetch_detail(import_id)
            chunks = detail_to_policy_chunks(detail, max_chars=chunk_max_chars, overlap_chars=chunk_overlap_chars)
            if not chunks:
                documents_skipped += 1
                continue
            documents_imported += 1

            if dry_run:
                chunks_stored += len(chunks)
                continue

            for batch in _batched(chunks, embedding_batch_size):
                embeddings = embedding_client.embed([chunk.text for chunk in batch], input_type="document")
                store.upsert_chunks(batch, embeddings)
                chunks_stored += len(batch)

        if page_num >= total_pages:
            break
        page_num += 1

    return YunguImportStats(documents_seen, documents_imported, documents_skipped, chunks_stored, pages_read)
