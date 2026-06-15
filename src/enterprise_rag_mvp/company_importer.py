from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from enterprise_rag_mvp.document_chunking import DocumentChunk, chunk_parsed_document, fixed_window_chunks
from enterprise_rag_mvp.document_parsing import DocumentParserRouter, DocumentSource, clean_html_to_text, parsed_document_text
from enterprise_rag_mvp.models import PolicyChunk
from enterprise_rag_mvp.policy_structure import build_policy_chunks_from_structure, parse_policy_structure

DEFAULT_COMPANY_BASE_URL = "https://example.com"
DEFAULT_POLICY_TYPE = 2


class CompanyApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompanyInformationPage:
    rows: list[dict[str, Any]]
    total: int
    page_num: int
    page_size: int


@dataclass(frozen=True)
class CompanyCategory:
    category_id: int
    name: str
    ename: str | None = None


@dataclass(frozen=True)
class CompanyImportStats:
    documents_seen: int = 0
    documents_imported: int = 0
    documents_skipped: int = 0
    chunks_stored: int = 0
    pages_read: int = 0


@dataclass(frozen=True)
class CompanyProcessedDocument:
    import_information_id: Any
    title: str
    status: str
    chunk_count: int = 0
    reason: str | None = None
    parse_status: str | None = None
    parse_warning_count: int = 0
    attachment_count: int = 0


@dataclass(frozen=True)
class CompanyPolicyIngestReport:
    category: CompanyCategory | None
    total_available: int
    stats: CompanyImportStats
    documents: list[CompanyProcessedDocument]


@dataclass(frozen=True)
class CompanyCategoryImportSummary:
    categories: list[CompanyPolicyIngestReport]

    @property
    def category_count(self) -> int:
        return len(self.categories)

    @property
    def stats(self) -> CompanyImportStats:
        return CompanyImportStats(
            documents_seen=sum(report.stats.documents_seen for report in self.categories),
            documents_imported=sum(report.stats.documents_imported for report in self.categories),
            documents_skipped=sum(report.stats.documents_skipped for report in self.categories),
            chunks_stored=sum(report.stats.chunks_stored for report in self.categories),
            pages_read=sum(report.stats.pages_read for report in self.categories),
        )


class EmbeddingLike(Protocol):
    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        ...


class StoreLike(Protocol):
    def upsert_chunks(self, chunks: list[PolicyChunk], embeddings: list[list[float]]) -> None:
        ...


def chunk_text(text: str, *, max_chars: int = 1200, overlap_chars: int = 150) -> list[str]:
    return fixed_window_chunks(text, max_chars=max_chars, overlap_chars=overlap_chars)


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


def _int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _category_from_raw(raw: dict[str, Any]) -> CompanyCategory | None:
    category_id = _int_or_none(_metadata_value(raw, "categoryTypeId", "policyCategoryType", "categoryId", "id"))
    if category_id is None:
        return None
    name = _first_non_empty(raw.get("categoryName"), raw.get("name"), fallback=f"category-{category_id}")
    ename = _first_non_empty(raw.get("categoryEname"), raw.get("ename"), raw.get("englishName"))
    return CompanyCategory(category_id=category_id, name=name, ename=ename or None)


def _attachment_name(raw: dict[str, Any], index: int) -> str:
    return _first_non_empty(
        raw.get("name"),
        raw.get("fileName"),
        raw.get("filename"),
        raw.get("title"),
        fallback=f"attachment-{index}",
    )


def _attachment_url(raw: dict[str, Any]) -> str | None:
    value = _first_non_empty(raw.get("url"), raw.get("fileUrl"), raw.get("downloadUrl"), raw.get("path"), raw.get("filePath"))
    return value or None


def _attachment_content_type(raw: dict[str, Any]) -> str | None:
    value = _first_non_empty(raw.get("contentType"), raw.get("mimeType"), raw.get("type"))
    return value or None


def _parse_attachment_chunks(
    *,
    file_list: list[Any],
    parent_doc_id: str,
    parent_title: str,
    parent_heading_path: list[str],
    parent_source_url: str,
    parser_router: DocumentParserRouter,
    attachment_fetcher: Callable[[dict[str, Any]], bytes] | None,
    max_chars: int,
    overlap_chars: int,
) -> tuple[list[PolicyChunk], dict[str, Any]]:
    if not file_list:
        return [], {"status": "none", "parsed_count": 0, "warning_count": 0}
    if attachment_fetcher is None:
        return [], {"status": "fetcher_not_configured", "parsed_count": 0, "warning_count": len(file_list)}

    chunks: list[PolicyChunk] = []
    parsed_count = 0
    warning_count = 0
    failed_count = 0
    for index, raw in enumerate(file_list, start=1):
        if not isinstance(raw, dict):
            failed_count += 1
            warning_count += 1
            continue
        attachment_name = _attachment_name(raw, index)
        attachment_url = _attachment_url(raw)
        try:
            content = attachment_fetcher(raw)
        except Exception:
            failed_count += 1
            warning_count += 1
            continue
        parsed = parser_router.parse(
            DocumentSource(
                source_id=f"{parent_doc_id}-attachment-{index}",
                source_name=attachment_name,
                file_name=attachment_name,
                content_type=_attachment_content_type(raw),
                content=content,
                source_url=attachment_url or parent_source_url,
                metadata={"parent_doc_id": parent_doc_id, "attachment_index": index},
            )
        )
        warning_count += len(parsed.quality.warnings)
        attachment_text = parsed_document_text(parsed)
        if not attachment_text:
            failed_count += 1
            continue
        parsed_count += 1
        attachment_doc_id = f"{parent_doc_id}-attachment-{index}"
        for chunk_index, chunk in enumerate(chunk_text(attachment_text, max_chars=max_chars, overlap_chars=overlap_chars), start=1):
            chunks.append(
                PolicyChunk(
                    chunk_id=f"{attachment_doc_id}-chunk-{chunk_index:04d}",
                    doc_id=attachment_doc_id,
                    block_id=f"attachment-{index}-chunk-{chunk_index:04d}",
                    text=chunk,
                    heading_path=[*parent_heading_path, attachment_name] or [parent_title, attachment_name],
                    metadata={
                        "source": "company_policy_attachment",
                        "source_url": attachment_url or parent_source_url,
                        "parent_doc_id": parent_doc_id,
                        "attachment_index": index,
                        "attachment_name": attachment_name,
                        "title": parent_title,
                        "parser_name": parsed.quality.parser_name,
                        "parser_version": parsed.quality.parser_version,
                        "parse_status": parsed.quality.status,
                        "parse_element_count": parsed.quality.element_count,
                        "parse_warning_count": len(parsed.quality.warnings),
                        "parse_table_count": parsed.quality.table_count,
                        "parse_image_ocr_count": parsed.quality.image_ocr_count,
                        "chunk_type": "attachment_fixed_window",
                    },
                )
            )

    if parsed_count == len(file_list):
        status = "success"
    elif parsed_count > 0:
        status = "partial"
    elif failed_count > 0:
        status = "failed"
    else:
        status = "not_fetched"
    return chunks, {"status": status, "parsed_count": parsed_count, "warning_count": warning_count}


def _policy_chunk_heading_path(base_heading_path: list[str], title: str, document_chunk: DocumentChunk) -> list[str]:
    chunk_path = list(document_chunk.heading_path)
    if base_heading_path and chunk_path[: len(base_heading_path)] == base_heading_path:
        return chunk_path
    if chunk_path and chunk_path[0] == title:
        chunk_path = chunk_path[1:]
    return [*base_heading_path, *chunk_path] or [title]


def _policy_chunk_block_id(document_chunk: DocumentChunk, index: int) -> str:
    chunk_type = str(document_chunk.metadata.get("chunk_type") or "chunk")
    return f"{chunk_type}-{index:04d}"


def _document_chunks_to_policy_chunks(
    *,
    doc_id: str,
    title: str,
    base_heading_path: list[str],
    base_metadata: dict[str, Any],
    document_chunks: list[DocumentChunk],
) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    for index, document_chunk in enumerate(document_chunks, start=1):
        block_id = _policy_chunk_block_id(document_chunk, index)
        chunks.append(
            PolicyChunk(
                chunk_id=f"{doc_id}-chunk-{index:04d}",
                doc_id=doc_id,
                block_id=block_id,
                text=document_chunk.text,
                heading_path=_policy_chunk_heading_path(base_heading_path, title, document_chunk),
                metadata={**base_metadata, **document_chunk.metadata},
            )
        )
    return chunks


def _structure_chunks_to_policy_chunks(
    *,
    doc_id: str,
    title: str,
    base_heading_path: list[str],
    base_metadata: dict[str, Any],
    document_chunks: list[DocumentChunk],
    start_index: int,
) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    for offset, document_chunk in enumerate(document_chunks, start=start_index):
        block_id = _policy_chunk_block_id(document_chunk, offset)
        chunks.append(
            PolicyChunk(
                chunk_id=f"{doc_id}-chunk-{offset:04d}",
                doc_id=doc_id,
                block_id=block_id,
                text=document_chunk.text,
                heading_path=_policy_chunk_heading_path(base_heading_path, title, document_chunk),
                metadata={**base_metadata, **document_chunk.metadata},
            )
        )
    return chunks


def _with_parent_metadata(chunks: list[PolicyChunk], base_metadata: dict[str, Any]) -> list[PolicyChunk]:
    return [
        PolicyChunk(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            block_id=chunk.block_id,
            text=chunk.text,
            heading_path=chunk.heading_path,
            metadata={**base_metadata, **chunk.metadata},
        )
        for chunk in chunks
    ]


def detail_to_policy_chunks(
    detail: dict[str, Any],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    parse_attachments: bool = False,
    attachment_fetcher: Callable[[dict[str, Any]], bytes] | None = None,
    parser_router: DocumentParserRouter | None = None,
) -> list[PolicyChunk]:
    import_id = _metadata_value(detail, "importInformationId", "id")
    if import_id is None:
        raise ValueError("detail missing importInformationId")

    title = _first_non_empty(detail.get("cnTitle"), detail.get("title"), detail.get("enTitle"), fallback=f"policy-{import_id}")
    category_name = _first_non_empty(detail.get("policyCategoryTypeName"), detail.get("categoryTypeName"), detail.get("categoryName"))
    doc_id = f"company-policy-{import_id}"
    heading_path = [value for value in [category_name, title] if value]
    file_list = detail.get("fileList") or []
    file_count = len(file_list) if isinstance(file_list, list) else 0
    source_url = f"https://example.com/policyDetail/{import_id}"
    effective_parser_router = parser_router or DocumentParserRouter()
    parsed_body = effective_parser_router.parse(
        DocumentSource(
            source_id=f"{doc_id}-body",
            source_name=title,
            file_name=f"{import_id}.html",
            content_type="text/html",
            text=str(detail.get("body") or ""),
            source_url=source_url,
            metadata={"import_information_id": import_id},
        )
    )
    text = parsed_document_text(parsed_body)

    attachment_chunks, attachment_summary = _parse_attachment_chunks(
        file_list=file_list if parse_attachments and isinstance(file_list, list) else [],
        parent_doc_id=doc_id,
        parent_title=title,
        parent_heading_path=heading_path,
        parent_source_url=source_url,
        parser_router=effective_parser_router,
        attachment_fetcher=attachment_fetcher,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
    if file_count and not parse_attachments:
        attachment_summary = {"status": "not_fetched", "parsed_count": 0, "warning_count": 0}
    attachment_parse_status = attachment_summary["status"]
    parse_warnings = parsed_body.quality.warnings
    base_metadata = {
        "source": "company_policy_system",
        "source_url": source_url,
        "import_information_id": import_id,
        "title": title,
        "cn_title": detail.get("cnTitle"),
        "en_title": detail.get("enTitle"),
        "publish_date": detail.get("publishDate"),
        "policy_category_type": detail.get("policyCategoryType"),
        "policy_category_type_name": category_name or None,
        "policy_system_type": detail.get("policySystemType"),
        "create_user_name": detail.get("createUserName"),
        "file_count": file_count,
        "attachment_parse_status": attachment_parse_status,
        "attachment_parsed_count": attachment_summary["parsed_count"],
        "attachment_parse_warning_count": attachment_summary["warning_count"],
        "parser_name": parsed_body.quality.parser_name,
        "parser_version": parsed_body.quality.parser_version,
        "parse_status": parsed_body.quality.status,
        "parse_element_count": parsed_body.quality.element_count,
        "parse_warning_count": len(parse_warnings),
        "parse_table_count": parsed_body.quality.table_count,
        "parse_image_ocr_count": parsed_body.quality.image_ocr_count,
        "parse_warnings": parse_warnings or None,
    }
    base_metadata = {key: value for key, value in base_metadata.items() if value is not None}
    attachment_chunks = _with_parent_metadata(attachment_chunks, base_metadata)

    body_chunks: list[PolicyChunk] = []
    if text:
        chunked_body = chunk_parsed_document(parsed_body, max_chars=max_chars, overlap_chars=overlap_chars)
        structure = parse_policy_structure(
            parsed_body,
            doc_id=doc_id,
            source_name=title,
            base_heading_path=heading_path or [title],
            source_url=source_url,
        )
        structure_document_chunks = build_policy_chunks_from_structure(
            structure,
            base_metadata={"category_name": category_name} if category_name else {},
            max_chars=max_chars,
        )
        chunk_quality_metadata = {
            "chunker_name": chunked_body.quality.chunker_name,
            "chunker_version": chunked_body.quality.chunker_version,
            "chunking_status": chunked_body.quality.status,
            "chunking_strategy": chunked_body.quality.chunking_strategy,
            "chunking_fallback_reason": chunked_body.quality.fallback_reason,
            "chunking_boundary_confidence": chunked_body.quality.boundary_confidence,
            "structure_parser_name": structure.quality.parser_name,
            "structure_parser_version": structure.quality.parser_version,
            "structure_status": structure.quality.status,
            "structure_node_count": structure.quality.node_count,
            "structure_issue_count": structure.quality.issue_count,
            "structure_warnings": structure.quality.warnings or None,
        }
        legacy_body_chunks = _document_chunks_to_policy_chunks(
            doc_id=doc_id,
            title=title,
            base_heading_path=heading_path or [title],
            base_metadata={**base_metadata, **{key: value for key, value in chunk_quality_metadata.items() if value is not None}},
            document_chunks=chunked_body.chunks,
        )
        structure_body_chunks = _structure_chunks_to_policy_chunks(
            doc_id=doc_id,
            title=title,
            base_heading_path=heading_path or [title],
            base_metadata={**base_metadata, **{key: value for key, value in chunk_quality_metadata.items() if value is not None}},
            document_chunks=structure_document_chunks,
            start_index=len(legacy_body_chunks) + 1,
        )
        body_chunks = structure_body_chunks + legacy_body_chunks
    return body_chunks + attachment_chunks


class CompanyPolicyClient:
    def __init__(
        self,
        *,
        auth_cookie: str,
        base_url: str = DEFAULT_COMPANY_BASE_URL,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        auth_cookie = auth_cookie.strip()
        if not auth_cookie:
            raise ValueError("auth_cookie must not be blank")
        self._auth_cookie = auth_cookie
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self._base_url}/home/policyList",
                "Cookie": self._auth_cookie,
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CompanyPolicyClient":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _get_json(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise CompanyApiError(f"Company API returned non-JSON for {path}") from exc
        if not isinstance(payload, dict):
            raise CompanyApiError(f"Company API returned unexpected payload type for {path}")
        if payload.get("ifLogin") is False:
            raise CompanyApiError("Company API authentication cookie is not logged in or has expired")
        if payload.get("status") is False or payload.get("code") not in (None, 0, 200, 1001, "0", "200", "1001"):
            message = payload.get("message") or payload.get("msg") or "unknown error"
            raise CompanyApiError(f"Company API error for {path}: {message}")
        return payload

    def fetch_policy_categories(self, *, policy_type: int = DEFAULT_POLICY_TYPE) -> list[CompanyCategory]:
        payload = self._get_json("/api/import/policySystemTypeList", params={"policyType": policy_type})
        content = payload.get("content") or []
        if isinstance(content, dict):
            systems = [content]
        elif isinstance(content, list):
            systems = content
        else:
            raise CompanyApiError("policySystemTypeList content must be a list or object")

        categories: list[CompanyCategory] = []
        seen_ids: set[int] = set()
        for system in systems:
            if not isinstance(system, dict):
                continue
            raw_categories = system.get("categoryList") or system.get("policyCategoryList") or []
            if not isinstance(raw_categories, list):
                continue
            for raw_category in raw_categories:
                if not isinstance(raw_category, dict):
                    continue
                category = _category_from_raw(raw_category)
                if category is None or category.category_id in seen_ids:
                    continue
                seen_ids.add(category.category_id)
                categories.append(category)
        return categories

    def fetch_information_page(
        self,
        *,
        page_num: int,
        page_size: int,
        policy_type: int = DEFAULT_POLICY_TYPE,
        category_id: int | None = None,
        keyword: str = "",
    ) -> CompanyInformationPage:
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
            raise CompanyApiError("informationList content must be an object")
        rows = content.get("data") or content.get("list") or []
        if not isinstance(rows, list):
            raise CompanyApiError("informationList rows must be a list")
        return CompanyInformationPage(
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
            raise CompanyApiError("notificationById content must be an object")
        return content


def _batched(items: list[Any], batch_size: int) -> list[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _row_import_id(row: dict[str, Any]) -> Any:
    return _metadata_value(row, "importInformationId", "id")


def _stats(
    *,
    documents_seen: int,
    documents_imported: int,
    documents_skipped: int,
    chunks_stored: int,
    pages_read: int,
) -> CompanyImportStats:
    return CompanyImportStats(
        documents_seen=documents_seen,
        documents_imported=documents_imported,
        documents_skipped=documents_skipped,
        chunks_stored=chunks_stored,
        pages_read=pages_read,
    )


def _title_from_row_or_detail(row: dict[str, Any], detail: dict[str, Any] | None, import_id: Any) -> str:
    detail = detail or {}
    return _first_non_empty(
        detail.get("cnTitle"),
        detail.get("title"),
        detail.get("enTitle"),
        row.get("cnTitle"),
        row.get("title"),
        row.get("enTitle"),
        fallback=f"policy-{import_id}",
    )


def _with_category_metadata(detail: dict[str, Any], category: CompanyCategory | None) -> dict[str, Any]:
    if category is None:
        return detail
    enriched = dict(detail)
    enriched.setdefault("policyCategoryType", category.category_id)
    enriched.setdefault("policyCategoryTypeName", category.name)
    if category.ename:
        enriched.setdefault("policyCategoryTypeEname", category.ename)
    return enriched


def ingest_company_policy_report(
    *,
    client: Any,
    embedding_client: EmbeddingLike,
    store: StoreLike,
    policy_type: int = DEFAULT_POLICY_TYPE,
    category: CompanyCategory | None = None,
    category_id: int | None = None,
    page_size: int = 50,
    max_docs: int | None = None,
    max_pages: int | None = None,
    chunk_max_chars: int = 1200,
    chunk_overlap_chars: int = 150,
    embedding_batch_size: int = 16,
    keyword: str = "",
    dry_run: bool = False,
    parse_attachments: bool = False,
    continue_on_error: bool = True,
) -> CompanyPolicyIngestReport:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if max_docs is not None and max_docs <= 0:
        raise ValueError("max_docs must be positive when provided")
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages must be positive when provided")
    if category is not None and category_id is not None and category.category_id != category_id:
        raise ValueError("category and category_id disagree")

    effective_category_id = category.category_id if category is not None else category_id
    effective_category = category or (
        CompanyCategory(category_id=effective_category_id, name=f"category-{effective_category_id}")
        if effective_category_id is not None
        else None
    )

    documents_seen = 0
    documents_imported = 0
    documents_skipped = 0
    chunks_stored = 0
    pages_read = 0
    page_num = 1
    total_pages: int | None = None
    total_available = 0
    documents: list[CompanyProcessedDocument] = []

    while True:
        if max_pages is not None and pages_read >= max_pages:
            break
        page = client.fetch_information_page(
            page_num=page_num,
            page_size=page_size,
            policy_type=policy_type,
            category_id=effective_category_id,
            keyword=keyword,
        )
        pages_read += 1
        if total_available == 0:
            total_available = page.total
        if total_pages is None:
            total_pages = max(1, math.ceil(page.total / page_size)) if page.total else 1

        if not page.rows:
            break

        for row in page.rows:
            if max_docs is not None and documents_seen >= max_docs:
                return CompanyPolicyIngestReport(
                    category=effective_category,
                    total_available=total_available,
                    stats=_stats(
                        documents_seen=documents_seen,
                        documents_imported=documents_imported,
                        documents_skipped=documents_skipped,
                        chunks_stored=chunks_stored,
                        pages_read=pages_read,
                    ),
                    documents=documents,
                )

            import_id = _row_import_id(row)
            documents_seen += 1
            if import_id is None:
                documents_skipped += 1
                documents.append(CompanyProcessedDocument(None, _title_from_row_or_detail(row, None, "unknown"), "skipped", reason="missing importInformationId"))
                continue

            detail: dict[str, Any] | None = None
            try:
                detail = _with_category_metadata(client.fetch_detail(import_id), effective_category)
                chunks = detail_to_policy_chunks(
                    detail,
                    max_chars=chunk_max_chars,
                    overlap_chars=chunk_overlap_chars,
                    parse_attachments=parse_attachments,
                    attachment_fetcher=client.fetch_attachment_bytes if parse_attachments and hasattr(client, "fetch_attachment_bytes") else None,
                )
                title = _title_from_row_or_detail(row, detail, import_id)
                if not chunks:
                    documents_skipped += 1
                    documents.append(CompanyProcessedDocument(import_id, title, "skipped", reason="empty cleaned body"))
                    continue

                if dry_run:
                    chunks_stored += len(chunks)
                else:
                    for batch in _batched(chunks, embedding_batch_size):
                        embeddings = embedding_client.embed([chunk.text for chunk in batch], input_type="document")
                        store.upsert_chunks(batch, embeddings)
                        chunks_stored += len(batch)

                documents_imported += 1
                first_metadata = chunks[0].metadata if chunks else {}
                documents.append(
                    CompanyProcessedDocument(
                        import_id,
                        title,
                        "imported",
                        chunk_count=len(chunks),
                        parse_status=first_metadata.get("parse_status"),
                        parse_warning_count=int(first_metadata.get("parse_warning_count") or 0),
                        attachment_count=int(first_metadata.get("file_count") or 0),
                    )
                )
            except Exception as exc:
                if not continue_on_error:
                    raise
                documents_skipped += 1
                title = _title_from_row_or_detail(row, detail, import_id)
                documents.append(CompanyProcessedDocument(import_id, title, "error", reason=f"{type(exc).__name__}: {exc}"))

        if page_num >= total_pages:
            break
        page_num += 1

    return CompanyPolicyIngestReport(
        category=effective_category,
        total_available=total_available,
        stats=_stats(
            documents_seen=documents_seen,
            documents_imported=documents_imported,
            documents_skipped=documents_skipped,
            chunks_stored=chunks_stored,
            pages_read=pages_read,
        ),
        documents=documents,
    )


def ingest_company_policies(
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
    parse_attachments: bool = False,
) -> CompanyImportStats:
    report = ingest_company_policy_report(
        client=client,
        embedding_client=embedding_client,
        store=store,
        policy_type=policy_type,
        category_id=category_id,
        page_size=page_size,
        max_docs=max_docs,
        max_pages=max_pages,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
        embedding_batch_size=embedding_batch_size,
        keyword=keyword,
        dry_run=dry_run,
        parse_attachments=parse_attachments,
    )
    return report.stats


def ingest_company_categories(
    *,
    client: Any,
    embedding_client: EmbeddingLike,
    store: StoreLike,
    policy_type: int = DEFAULT_POLICY_TYPE,
    categories: list[CompanyCategory] | None = None,
    page_size: int = 50,
    max_docs_per_category: int | None = None,
    max_pages_per_category: int | None = None,
    chunk_max_chars: int = 1200,
    chunk_overlap_chars: int = 150,
    embedding_batch_size: int = 16,
    keyword: str = "",
    dry_run: bool = False,
    parse_attachments: bool = False,
) -> CompanyCategoryImportSummary:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if max_docs_per_category is not None and max_docs_per_category <= 0:
        raise ValueError("max_docs_per_category must be positive when provided")
    if max_pages_per_category is not None and max_pages_per_category <= 0:
        raise ValueError("max_pages_per_category must be positive when provided")

    effective_categories = categories if categories is not None else client.fetch_policy_categories(policy_type=policy_type)
    reports = [
        ingest_company_policy_report(
            client=client,
            embedding_client=embedding_client,
            store=store,
            policy_type=policy_type,
            category=category,
            page_size=page_size,
            max_docs=max_docs_per_category,
            max_pages=max_pages_per_category,
            chunk_max_chars=chunk_max_chars,
            chunk_overlap_chars=chunk_overlap_chars,
            embedding_batch_size=embedding_batch_size,
            keyword=keyword,
            dry_run=dry_run,
            parse_attachments=parse_attachments,
        )
        for category in effective_categories
    ]
    return CompanyCategoryImportSummary(categories=reports)
