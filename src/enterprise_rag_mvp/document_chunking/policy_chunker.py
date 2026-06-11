from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from enterprise_rag_mvp.document_chunking.models import ChunkedDocument, ChunkQualityReport, DocumentChunk
from enterprise_rag_mvp.document_parsing import ParsedDocument, normalize_whitespace, parsed_document_text

CHUNKER_NAME = "policy_clause_group_chunker"
CHUNKER_VERSION = "1"

_CHINESE_MAJOR_HEADING_RE = re.compile(r"(?<![（(])([一二三四五六七八九十]{1,3}、\s*[^\s，。；;：:]{1,40})")
_VIOLATION_CATEGORY_RE = re.compile(r"(（[一二三四五六七八九十]{1,3}）\s*([一二三]类违规行为))")
_GROUP_HEADING_RE = re.compile(r"(?<![\d.])(\d{1,2})\.\s*(?!\d)([^。；;\d]{2,80}?)(?=[:：]|\s+\d+\.\d)")
_SUBCLAUSE_RE = re.compile(r"(?<!\d)(\d{1,2}\.\d{1,2})")
_ENGLISH_START_RE = re.compile(r"\b(?:[A-Z][A-Za-z&'.-]*(?:\s+[A-Z][A-Za-z&'.-]*){0,8}\s+)?Employee\s+Disciplinary\s+Rules\b", re.IGNORECASE)
_TOP_ENGLISH_TITLE_RE = _ENGLISH_START_RE
_DATETIME_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b")
_ENGLISH_ROMAN = r"(?:[IVX]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)"
_ENGLISH_MAJOR_HEADING_RE = re.compile(
    rf"(?<![A-Za-z0-9])(({_ENGLISH_ROMAN})\.?\s+(?:Purpose|Scope of Application|Code of Professional Conduct for Teachers|Violations|Applicable Disciplinary Actions against Violations|Management Responsibility|Determination of Violations and Disciplinary Process|Others|Appendix))",
    re.IGNORECASE,
)
_ENGLISH_CATEGORY_RE = re.compile(r"(\(([IVX]+)\)\s+(Category\s+([123])\s+Violation))", re.IGNORECASE)
_ENGLISH_GROUP_HEADING_RE = re.compile(r"(?<![\d.])(\d{1,2})\.\s+(?!\d)([A-Z][^:：。；;\d]{2,160}?)(?=[:：.]|\s+\d{1,2}\.\d{1,2})")

_VIOLATION_LEVELS = {
    "一类违规行为": "category_1",
    "二类违规行为": "category_2",
    "三类违规行为": "category_3",
}
_RETRIEVAL_CHUNK_TYPES = {
    "section_overview",
    "violation_category_overview",
    "clause_group",
    "action_clause",
    "disciplinary_rule",
    "english_category_overview",
    "english_clause_group",
    "english_action_clause",
}


@dataclass(frozen=True)
class _ElementSpan:
    element_id: str
    index: int
    text: str
    start: int
    end: int


def _attach_element_provenance(chunks: list[DocumentChunk], spans: list[_ElementSpan]) -> list[DocumentChunk]:
    updated_chunks: list[DocumentChunk] = []
    for chunk in chunks:
        metadata = dict(chunk.metadata)
        source_span = metadata.get("source_span")
        element_ids: list[str] = list(metadata.get("element_ids") or [])
        matched_spans: list[_ElementSpan] = []
        if isinstance(source_span, dict):
            start = int(source_span.get("start", 0))
            end = int(source_span.get("end", start))
            matched_spans = _element_spans_for_source_span(spans, start, end)
            span_ids = [span.element_id for span in matched_spans]
            element_ids = _dedupe_preserving_order([*element_ids, *span_ids])
        if element_ids:
            metadata["element_ids"] = element_ids
            indexed_spans = [span for span in spans if span.element_id in set(element_ids)]
            if indexed_spans:
                indexes = [span.index + 1 for span in indexed_spans]
                metadata["element_range"] = {"start": min(indexes), "end": max(indexes)}
        updated_chunks.append(replace(chunk, metadata=metadata))
    return updated_chunks


def _element_spans_for_source_span(spans: list[_ElementSpan], start: int, end: int) -> list[_ElementSpan]:
    if end < start:
        start, end = end, start
    return [span for span in spans if span.start < end and span.end > start]


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _element_coverage_report(spans: list[_ElementSpan], chunks: list[DocumentChunk]) -> dict[str, Any]:
    source_ids = {span.element_id for span in spans}
    covered_ids = {
        element_id
        for chunk in chunks
        for element_id in chunk.metadata.get("element_ids", [])
        if element_id in source_ids
    }
    uncovered = [span for span in spans if span.element_id not in covered_ids]
    source_element_count = len(spans)
    covered_element_count = len(covered_ids)
    return {
        "element_coverage_status": "complete" if not uncovered else "partial",
        "source_element_count": source_element_count,
        "covered_element_count": covered_element_count,
        "uncovered_element_count": len(uncovered),
        "element_coverage_ratio": covered_element_count / source_element_count if source_element_count else 1.0,
        "uncovered_elements": [
            {"element_id": span.element_id, "index": span.index + 1, "preview": span.text[:120]} for span in uncovered[:20]
        ],
    }


def _coverage_report(text: str, chunks: list[DocumentChunk]) -> dict[str, Any]:
    source_char_count = len(text)
    if source_char_count == 0:
        return {
            "coverage_status": "complete",
            "source_char_count": 0,
            "covered_char_count": 0,
            "uncovered_char_count": 0,
            "coverage_ratio": 1.0,
            "uncovered_ranges": [],
        }
    covered = [False] * source_char_count
    for chunk in chunks:
        span = chunk.metadata.get("source_span")
        if not isinstance(span, dict):
            continue
        start = max(0, int(span.get("start", 0)))
        end = min(source_char_count, int(span.get("end", start)))
        for index in range(start, end):
            if not text[index].isspace():
                covered[index] = True

    significant_positions = [index for index, char in enumerate(text) if not char.isspace()]
    covered_char_count = sum(1 for index in significant_positions if covered[index])
    uncovered_positions = [index for index in significant_positions if not covered[index]]
    uncovered_ranges = _compress_uncovered_ranges(text, uncovered_positions)
    uncovered_char_count = len(uncovered_positions)
    return {
        "coverage_status": "complete" if uncovered_char_count == 0 else "partial",
        "source_char_count": len(significant_positions),
        "covered_char_count": covered_char_count,
        "uncovered_char_count": uncovered_char_count,
        "coverage_ratio": covered_char_count / len(significant_positions) if significant_positions else 1.0,
        "uncovered_ranges": uncovered_ranges,
    }


def _chunk_structure_report(chunks: list[DocumentChunk]) -> dict[str, Any]:
    retrieval_chunk_count = sum(1 for chunk in chunks if chunk.metadata.get("chunk_role") == "retrieval")
    coverage_chunk_count = sum(1 for chunk in chunks if chunk.metadata.get("chunk_role") == "coverage")
    english_retrieval_chunk_count = sum(
        1 for chunk in chunks if chunk.metadata.get("chunk_role") == "retrieval" and chunk.metadata.get("language") == "en"
    )
    provenance_missing_count = sum(1 for chunk in chunks if not chunk.metadata.get("element_ids"))
    retrieval_provenance_missing_count = sum(
        1 for chunk in chunks if chunk.metadata.get("chunk_role") == "retrieval" and not chunk.metadata.get("element_ids")
    )
    return {
        "retrieval_chunk_count": retrieval_chunk_count,
        "coverage_chunk_count": coverage_chunk_count,
        "english_retrieval_chunk_count": english_retrieval_chunk_count,
        "orphan_title_count": sum(1 for chunk in chunks if _is_orphan_title_chunk(chunk)),
        "mixed_language_chunk_count": sum(1 for chunk in chunks if _is_mixed_language_chunk(chunk)),
        "provenance_missing_count": provenance_missing_count,
        "retrieval_provenance_missing_count": retrieval_provenance_missing_count,
    }


def _is_orphan_title_chunk(chunk: DocumentChunk) -> bool:
    if chunk.metadata.get("semantic_type") == "document_title" or chunk.metadata.get("chunk_type") == "document_metadata":
        return False
    if chunk.metadata.get("chunk_role") == "retrieval":
        return False
    text = normalize_whitespace(chunk.text).strip(" ：:")
    return bool(text and chunk.heading_path and text == _normalize_heading(chunk.heading_path[-1]))


def _is_mixed_language_chunk(chunk: DocumentChunk) -> bool:
    language = chunk.metadata.get("language")
    if language not in {"zh", "en"}:
        return False
    has_cjk = _contains_cjk(chunk.text)
    has_alpha_words = bool(re.search(r"[A-Za-z]{3,}", chunk.text))
    if language == "zh":
        return has_cjk and has_alpha_words and chunk.metadata.get("semantic_type") != "document_title"
    return has_cjk


def _compress_uncovered_ranges(text: str, positions: list[int]) -> list[dict[str, Any]]:
    if not positions:
        return []
    ranges: list[dict[str, Any]] = []
    start = positions[0]
    previous = positions[0]
    for position in positions[1:]:
        if position == previous + 1:
            previous = position
            continue
        ranges.append(_uncovered_range(text, start, previous + 1))
        start = previous = position
    ranges.append(_uncovered_range(text, start, previous + 1))
    return ranges[:20]


def _uncovered_range(text: str, start: int, end: int) -> dict[str, Any]:
    return {"start": start, "end": end, "preview": normalize_whitespace(text[start:end])[:120]}


def fixed_window_chunks(text: str, *, max_chars: int = 1200, overlap_chars: int = 150) -> list[str]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    _validate_chunk_args(max_chars=max_chars, overlap_chars=overlap_chars)

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


def chunk_parsed_document(document: ParsedDocument, *, max_chars: int = 1200, overlap_chars: int = 150) -> ChunkedDocument:
    _validate_chunk_args(max_chars=max_chars, overlap_chars=overlap_chars)
    text = parsed_document_text(document)
    if not text:
        return ChunkedDocument(
            source_id=document.source_id,
            source_name=document.source_name,
            chunks=[],
            quality=ChunkQualityReport(
                chunker_name=CHUNKER_NAME,
                chunker_version=CHUNKER_VERSION,
                status="failed",
                chunking_strategy="none",
                fallback_reason="empty_parsed_text",
                warnings=["Parsed document produced no text for chunking."],
            ),
        )

    element_spans = _element_spans(document, text)
    chunks = _policy_chunks(document, text, max_chars=max_chars)
    if chunks:
        chunks_with_provenance = _attach_element_provenance(chunks, element_spans)
        numbered_chunks = [replace(chunk, chunk_id=f"chunk-{index:04d}") for index, chunk in enumerate(chunks_with_provenance, start=1)]
        coverage = _coverage_report(text, numbered_chunks)
        element_coverage = _element_coverage_report(element_spans, numbered_chunks)
        structure = _chunk_structure_report(numbered_chunks)
        return ChunkedDocument(
            source_id=document.source_id,
            source_name=document.source_name,
            chunks=numbered_chunks,
            quality=ChunkQualityReport(
                chunker_name=CHUNKER_NAME,
                chunker_version=CHUNKER_VERSION,
                status="success",
                chunking_strategy="policy_clause_group",
                chunk_profile="policy_rule_auto",
                chunk_count=len(chunks),
                structured_chunk_count=len(chunks),
                fallback_chunk_count=0,
                boundary_confidence="high",
                **coverage,
                **element_coverage,
                **structure,
            ),
        )

    fallback_chunks = _fallback_document_chunks(
        document_name=document.source_name,
        text=text,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
    fallback_chunks = _attach_element_provenance(fallback_chunks, element_spans)
    fallback_char_coverage = _coverage_report(text, fallback_chunks)
    fallback_coverage = _element_coverage_report(element_spans, fallback_chunks)
    fallback_structure = _chunk_structure_report(fallback_chunks)
    return ChunkedDocument(
        source_id=document.source_id,
        source_name=document.source_name,
        chunks=fallback_chunks,
        quality=ChunkQualityReport(
            chunker_name=CHUNKER_NAME,
            chunker_version=CHUNKER_VERSION,
            status="success" if fallback_chunks else "failed",
            chunking_strategy="fixed_window_fallback",
            chunk_profile="fixed_window",
            chunk_count=len(fallback_chunks),
            structured_chunk_count=0,
            fallback_chunk_count=len(fallback_chunks),
            boundary_confidence="low" if fallback_chunks else None,
            fallback_reason="no_policy_structure_detected",
            **fallback_char_coverage,
            **fallback_coverage,
            **fallback_structure,
            warnings=[] if fallback_chunks else ["No chunks produced by fixed-window fallback."],
        ),
    )


def _fallback_document_chunks(*, document_name: str, text: str, max_chars: int, overlap_chars: int) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    cursor = 0
    for index, chunk in enumerate(fixed_window_chunks(text, max_chars=max_chars, overlap_chars=overlap_chars), start=1):
        start = text.find(chunk, cursor)
        if start < 0:
            start = text.find(chunk)
        metadata = {
            "chunk_type": "fixed_window",
            "chunking_strategy": "fixed_window_fallback",
        }
        if start >= 0:
            end = start + len(chunk)
            cursor = max(cursor, end - overlap_chars)
            metadata["source_span"] = {"start": start, "end": end}
        chunks.append(
            DocumentChunk(
                chunk_id=f"chunk-{index:04d}",
                text=chunk,
                heading_path=[document_name],
                metadata=metadata,
            )
        )
    return chunks


def _validate_chunk_args(*, max_chars: int, overlap_chars: int) -> None:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")


def _policy_chunks(document: ParsedDocument, text: str, *, max_chars: int) -> list[DocumentChunk]:
    spans = _element_spans(document, text)
    if not spans:
        return []

    body_start_index = _find_chinese_body_start_index(spans)
    english_tail_start = _find_english_tail_start(spans, body_start_index)
    english_tail_index = english_tail_start[0] if english_tail_start is not None else None
    has_policy_structure = body_start_index is not None or english_tail_index is not None or any(
        _VIOLATION_CATEGORY_RE.search(span.text) for span in spans
    )
    if not has_policy_structure:
        return []

    chunks: list[DocumentChunk] = []
    front_matter_end = body_start_index if body_start_index is not None else (english_tail_index or 0)
    if front_matter_end > 0:
        chunks.extend(
            _front_matter_chunks(
                spans[:front_matter_end],
                source_text=text,
                document_name=document.source_name,
                max_chars=max_chars,
            )
        )

    if body_start_index is not None:
        body_start = spans[body_start_index].start
        if english_tail_start is not None:
            body_end = spans[english_tail_start[0]].start + english_tail_start[1]
        else:
            body_end = spans[-1].end
        body_text, body_source_offset = _strip_with_source_offset(text[body_start:body_end], body_start)
        if body_text:
            chunks.extend(
                _chinese_policy_chunks(
                    body_text,
                    document_name=document.source_name,
                    max_chars=max_chars,
                    source_offset=body_source_offset,
                )
            )

    if english_tail_start is not None:
        english_start = spans[english_tail_start[0]].start + english_tail_start[1]
        chunks.extend(
            _english_tail_chunks(
                spans[english_tail_start[0] :],
                source_text=text,
                document_name=document.source_name,
                max_chars=max_chars,
                start_offset=english_start,
            )
        )
    return chunks


def _element_spans(document: ParsedDocument, text: str) -> list[_ElementSpan]:
    spans: list[_ElementSpan] = []
    cursor = 0
    for index, element in enumerate(document.elements):
        element_text = normalize_whitespace(element.text)
        if not element_text:
            continue
        start = text.find(element_text, cursor)
        if start < 0:
            start = text.find(element_text)
        if start < 0:
            start = cursor
        end = start + len(element_text)
        spans.append(_ElementSpan(element.element_id, index, element_text, start, end))
        cursor = end
    return spans


def _find_chinese_body_start_index(spans: list[_ElementSpan]) -> int | None:
    for index, span in enumerate(spans):
        if _CHINESE_MAJOR_HEADING_RE.search(span.text) or _VIOLATION_CATEGORY_RE.search(span.text):
            return index
    return None


def _find_english_tail_start(spans: list[_ElementSpan], body_start_index: int | None) -> tuple[int, int] | None:
    start_index = 0 if body_start_index is None else body_start_index + 1
    for index in range(start_index, len(spans)):
        match = _first_english_policy_marker(spans[index].text)
        if match:
            return index, match.start()
    return None


def _first_english_policy_marker(text: str) -> re.Match[str] | None:
    matches = [
        match
        for match in (
            _ENGLISH_START_RE.search(text),
            _ENGLISH_MAJOR_HEADING_RE.search(text),
            _ENGLISH_CATEGORY_RE.search(text),
        )
        if match is not None
    ]
    return min(matches, key=lambda match: match.start()) if matches else None


def _strip_with_source_offset(raw_text: str, source_start: int) -> tuple[str, int]:
    leading_whitespace = len(raw_text) - len(raw_text.lstrip())
    return raw_text.strip(), source_start + leading_whitespace


def _front_matter_chunks(
    spans: list[_ElementSpan], *, source_text: str, document_name: str, max_chars: int
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    index = 0
    while index < len(spans):
        span = spans[index]
        span_text = span.text
        if "[摘要]" in span_text or _TOP_ENGLISH_TITLE_RE.search(span_text):
            chunks.extend(_top_document_chunks(span, document_name=document_name, max_chars=max_chars))
            index += 1
            continue
        if _looks_like_english_summary(span_text):
            chunks.extend(
                _span_chunk(
                    span,
                    span_text,
                    heading_path=[document_name, "摘要"],
                    metadata={"chunk_type": "summary", "language": "en", "chunk_role": "coverage"},
                    max_chars=max_chars,
                )
            )
            index += 1
            continue
        if _looks_like_chinese_mission_heading(span_text):
            group_end = _collect_until(spans, index + 1, (_looks_like_english_mission_heading, _looks_like_policy_intro))
            chunks.extend(
                _spans_chunk(
                    spans[index:group_end],
                    source_text=source_text,
                    heading_path=[document_name, "使命、培养目标和愿景"],
                    metadata={"chunk_type": "mission_section", "language": "zh", "chunk_role": "coverage"},
                    max_chars=max_chars,
                )
            )
            index = group_end
            continue
        if _looks_like_english_mission_heading(span_text):
            group_end = _collect_until(spans, index + 1, (_looks_like_policy_intro,))
            chunks.extend(
                _spans_chunk(
                    spans[index:group_end],
                    source_text=source_text,
                    heading_path=[document_name, "Mission, Educational Goal and Vision"],
                    metadata={"chunk_type": "mission_section", "language": "en", "chunk_role": "coverage"},
                    max_chars=max_chars,
                )
            )
            index = group_end
            continue
        if _looks_like_policy_intro(span_text):
            group_end = _collect_until(
                spans,
                index + 1,
                (_looks_like_chinese_major_heading, _looks_like_chinese_mission_heading, _looks_like_english_mission_heading),
            )
            chunks.extend(
                _spans_chunk(
                    spans[index:group_end],
                    source_text=source_text,
                    heading_path=[document_name, "引言"],
                    metadata={"chunk_type": "policy_intro", "language": "zh", "chunk_role": "coverage"},
                    max_chars=max_chars,
                )
            )
            index = group_end
            continue

        chunks.extend(
            _span_chunk(
                span,
                span_text,
                heading_path=[document_name, "文档背景"],
                metadata={
                    "chunk_type": "document_intro",
                    "language": _language_for_text(span_text),
                    "chunk_role": "coverage",
                },
                max_chars=max_chars,
            )
        )
        index += 1
    return chunks


def _top_document_chunks(span: _ElementSpan, *, document_name: str, max_chars: int) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    text = span.text
    summary_start = text.find("[摘要]")
    prefix_end = summary_start if summary_start >= 0 else len(text)
    prefix = text[:prefix_end]
    title_end = prefix_end
    date_match = _DATETIME_RE.search(prefix)
    if date_match:
        title_end = date_match.start()

    title_text = prefix[:title_end].strip()
    english_match = _TOP_ENGLISH_TITLE_RE.search(title_text)
    if english_match:
        zh_title = title_text[: english_match.start()].strip()
        en_title = title_text[english_match.start() :].strip()
        if zh_title:
            chunks.extend(
                _partial_span_chunk(
                    span,
                    0,
                    english_match.start(),
                    heading_path=[document_name],
                    metadata={"chunk_type": "document_intro", "semantic_type": "document_title", "language": "zh", "chunk_role": "coverage"},
                    max_chars=max_chars,
                )
            )
        if en_title:
            chunks.extend(
                _partial_span_chunk(
                    span,
                    english_match.start(),
                    title_end,
                    heading_path=[document_name],
                    metadata={"chunk_type": "document_intro", "semantic_type": "document_title", "language": "en", "chunk_role": "coverage"},
                    max_chars=max_chars,
                )
            )
    elif title_text:
        chunks.extend(
            _partial_span_chunk(
                span,
                0,
                title_end,
                heading_path=[document_name],
                metadata={
                    "chunk_type": "document_intro",
                    "semantic_type": "document_title",
                    "language": _language_for_text(title_text),
                    "chunk_role": "coverage",
                },
                max_chars=max_chars,
            )
        )

    if date_match:
        chunks.extend(
            _partial_span_chunk(
                span,
                date_match.start(),
                date_match.end(),
                heading_path=[document_name, "文档时间"],
                metadata={"chunk_type": "document_metadata", "language": "neutral", "chunk_role": "coverage"},
                max_chars=max_chars,
            )
        )

    if summary_start >= 0:
        chunks.extend(
            _partial_span_chunk(
                span,
                summary_start,
                len(text),
                heading_path=[document_name, "摘要"],
                metadata={"chunk_type": "summary", "language": "zh", "chunk_role": "coverage"},
                max_chars=max_chars,
            )
        )
    return chunks


def _collect_until(spans: list[_ElementSpan], start_index: int, stop_predicates: tuple[Any, ...]) -> int:
    index = start_index
    while index < len(spans):
        if any(predicate(spans[index].text) for predicate in stop_predicates):
            break
        index += 1
    return index


def _english_tail_chunks(
    spans: list[_ElementSpan], *, source_text: str, document_name: str, max_chars: int, start_offset: int | None = None
) -> list[DocumentChunk]:
    if not spans:
        return []
    source_start = spans[0].start if start_offset is None else start_offset
    english_text, source_offset = _strip_with_source_offset(source_text[source_start : spans[-1].end], source_start)
    chunks = _english_policy_chunks(english_text, document_name=document_name, max_chars=max_chars, source_offset=source_offset)
    if chunks:
        return chunks
    metadata = {
        "chunk_type": "english_section",
        "language": "en",
        "chunk_role": "coverage",
        "element_ids": [span.element_id for span in spans],
    }
    return _bounded_chunks(
        english_text,
        heading_path=[document_name, "English"],
        metadata=metadata,
        max_chars=max_chars,
        source_start=source_offset,
    )


def _english_policy_chunks(text: str, *, document_name: str, max_chars: int, source_offset: int) -> list[DocumentChunk]:
    sections = _english_major_sections(text)
    chunks: list[DocumentChunk] = []
    if not sections:
        if _ENGLISH_CATEGORY_RE.search(text):
            return _english_violation_chunks(text, heading="Violations", document_name=document_name, max_chars=max_chars, source_offset=source_offset)
        return []

    preface = text[: sections[0][1]].strip()
    if preface:
        chunks.extend(
            _bounded_chunks(
                preface,
                heading_path=[document_name, "English"],
                metadata={"chunk_type": "english_section", "language": "en", "section_title": "English"},
                max_chars=max_chars,
                source_start=source_offset,
            )
        )

    for index, (heading, start, body_start) in enumerate(sections):
        end = sections[index + 1][1] if index + 1 < len(sections) else len(text)
        section_text = text[start:end].strip()
        section_body = text[body_start:end].strip()
        if "disciplinary actions" in heading.lower():
            first_action = _SUBCLAUSE_RE.search(section_text)
            include_leading_on_first = False
            if first_action and first_action.start() > 0:
                prefix = section_text[: first_action.start()].strip()
                if _is_substantive_section_intro(prefix, heading):
                    chunks.extend(
                        _bounded_chunks(
                            prefix,
                            heading_path=[document_name, heading],
                            metadata={"chunk_type": "english_section", "language": "en", "section_title": heading},
                            max_chars=max_chars,
                            source_start=source_offset + start,
                        )
                    )
                else:
                    include_leading_on_first = True
            chunks.extend(
                _english_disciplinary_action_chunks(
                    section_text,
                    heading=heading,
                    document_name=document_name,
                    max_chars=max_chars,
                    source_offset=source_offset + start,
                    include_leading_on_first=include_leading_on_first,
                )
            )
        elif heading.lower().endswith("violations") or heading.lower() == "violations":
            section_heading_text = text[start:body_start].strip()
            if _is_substantive_section_intro(section_heading_text, heading):
                chunks.extend(
                    _bounded_chunks(
                        section_heading_text,
                        heading_path=[document_name, heading],
                        metadata={"chunk_type": "english_section", "language": "en", "section_title": heading},
                        max_chars=max_chars,
                        source_start=source_offset + start,
                    )
                )
            violation_chunks = _english_violation_chunks(
                section_text,
                heading=heading,
                document_name=document_name,
                max_chars=max_chars,
                source_offset=source_offset + start,
            )
            if violation_chunks:
                chunks.extend(violation_chunks)
            elif section_body:
                chunks.extend(
                    _bounded_chunks(
                        section_text,
                        heading_path=[document_name, heading],
                        metadata={"chunk_type": "english_section", "language": "en", "section_title": heading},
                        max_chars=max_chars,
                        source_start=source_offset + start,
                    )
                )
        elif section_body:
            chunks.extend(
                _bounded_chunks(
                    section_text,
                    heading_path=[document_name, heading],
                    metadata={"chunk_type": "english_section", "language": "en", "section_title": heading},
                    max_chars=max_chars,
                    source_start=source_offset + start,
                )
            )
    return chunks


def _english_major_sections(text: str) -> list[tuple[str, int, int]]:
    sections: list[tuple[str, int, int]] = []
    seen_starts: set[int] = set()
    for match in _ENGLISH_MAJOR_HEADING_RE.finditer(text):
        if match.start() in seen_starts:
            continue
        seen_starts.add(match.start())
        sections.append((_normalize_heading(match.group(1)), match.start(), match.end()))
    return sections


def _english_violation_chunks(section_text: str, *, heading: str, document_name: str, max_chars: int, source_offset: int) -> list[DocumentChunk]:
    category_matches = list(_ENGLISH_CATEGORY_RE.finditer(section_text))
    chunks: list[DocumentChunk] = []
    for index, category_match in enumerate(category_matches):
        category_title = _normalize_heading(category_match.group(3))
        category_start = category_match.start()
        category_end = category_matches[index + 1].start() if index + 1 < len(category_matches) else len(section_text)
        category_text = section_text[category_start:category_end].strip()
        level = f"category_{category_match.group(4)}"
        group_matches = list(_ENGLISH_GROUP_HEADING_RE.finditer(category_text))

        overview_end = group_matches[0].start() if group_matches else len(category_text)
        group_titles = [f"{match.group(1)}. {_normalize_heading(match.group(2))}" for match in group_matches]
        overview_parts = [heading] if index == 0 and heading else []
        overview_parts.extend([category_text[:overview_end].strip(), *group_titles])
        overview_text = normalize_whitespace(" ".join(overview_parts))
        if overview_text:
            chunks.extend(
                _bounded_chunks(
                    overview_text,
                    heading_path=[document_name, category_title],
                    metadata={
                        "chunk_type": "english_category_overview",
                        "language": "en",
                        "section_title": category_title,
                        "section_marker": _normalize_heading(category_match.group(1)),
                        "section_path": [category_title],
                        "start_marker": _normalize_heading(category_match.group(1)),
                        "end_marker": None,
                        "violation_level": level,
                    },
                    max_chars=max_chars,
                    source_start=source_offset if index == 0 and heading else source_offset + category_start,
                )
            )

        for group_index, group_match in enumerate(group_matches):
            group_end = group_matches[group_index + 1].start() if group_index + 1 < len(group_matches) else len(category_text)
            group_text = category_text[group_match.start() : group_end].strip()
            clause_no = group_match.group(1)
            group_title = f"{clause_no}. {_normalize_heading(group_match.group(2))}"
            metadata = {
                "chunk_type": "english_clause_group",
                "language": "en",
                "section_title": category_title,
                "group_title": group_title,
                "clause_title": group_title,
                "clause_no": clause_no,
                "clause_range": _clause_range(group_text, clause_no),
                "section_path": [category_title, group_title],
                "start_marker": group_title,
                "end_marker": None,
                "violation_level": level,
            }
            chunks.extend(
                _bounded_chunks(
                    group_text,
                    heading_path=[document_name, category_title, group_title],
                    metadata=metadata,
                    max_chars=max_chars,
                    source_start=source_offset + category_start + group_match.start(),
                )
            )
    return chunks


def _english_disciplinary_action_chunks(
    section_text: str,
    *,
    heading: str,
    document_name: str,
    max_chars: int,
    source_offset: int,
    include_leading_on_first: bool = False,
) -> list[DocumentChunk]:
    matches = list(_SUBCLAUSE_RE.finditer(section_text))
    chunks: list[DocumentChunk] = []
    for index, match in enumerate(matches):
        start = 0 if index == 0 and include_leading_on_first else match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section_text)
        clause_text = section_text[start:end].strip()
        if not clause_text:
            continue
        clause_no = match.group(1)
        target_level = _english_first_violation_level(clause_text)
        metadata = {
            "chunk_type": "english_action_clause",
            "language": "en",
            "clause_no": clause_no,
            "section_title": heading,
            "section_path": [heading, clause_no],
        }
        action_heading = clause_no
        if target_level:
            metadata["action_target"] = target_level
            metadata["violation_level"] = target_level
            action_heading = f"{clause_no} Category {target_level[-1]} Violation"
        chunks.extend(
            _bounded_chunks(
                clause_text,
                heading_path=[document_name, heading, action_heading],
                metadata=metadata,
                max_chars=max_chars,
                source_start=source_offset + start,
            )
        )
    return chunks


def _english_first_violation_level(text: str) -> str | None:
    match = re.search(r"Category\s+([123])\s+Violation", text, re.IGNORECASE)
    if not match:
        return None
    return f"category_{match.group(1)}"


def _spans_chunk(
    spans: list[_ElementSpan],
    *,
    source_text: str,
    heading_path: list[str],
    metadata: dict[str, Any],
    max_chars: int,
) -> list[DocumentChunk]:
    if not spans:
        return []
    chunk_metadata = dict(metadata)
    chunk_metadata.setdefault("chunking_strategy", "policy_clause_group")
    chunk_metadata["element_ids"] = [span.element_id for span in spans]
    return _bounded_chunks(
        _text_for_spans(source_text, spans),
        heading_path=heading_path,
        metadata=chunk_metadata,
        max_chars=max_chars,
        source_start=spans[0].start,
    )


def _span_chunk(
    span: _ElementSpan,
    chunk_text: str,
    *,
    heading_path: list[str],
    metadata: dict[str, Any],
    max_chars: int,
) -> list[DocumentChunk]:
    relative_start = span.text.find(chunk_text)
    if relative_start < 0:
        relative_start = 0
    return _partial_span_chunk(
        span,
        relative_start,
        relative_start + len(chunk_text),
        heading_path=heading_path,
        metadata=metadata,
        max_chars=max_chars,
    )


def _partial_span_chunk(
    span: _ElementSpan,
    relative_start: int,
    relative_end: int,
    *,
    heading_path: list[str],
    metadata: dict[str, Any],
    max_chars: int,
) -> list[DocumentChunk]:
    raw_text = span.text[relative_start:relative_end]
    if not normalize_whitespace(raw_text):
        return []
    chunk_metadata = dict(metadata)
    chunk_metadata.setdefault("chunking_strategy", "policy_clause_group")
    chunk_metadata["element_ids"] = [span.element_id]
    return _bounded_chunks(
        raw_text,
        heading_path=heading_path,
        metadata=chunk_metadata,
        max_chars=max_chars,
        source_start=span.start + relative_start,
    )


def _text_for_spans(source_text: str, spans: list[_ElementSpan]) -> str:
    return source_text[spans[0].start : spans[-1].end]


def _is_english_policy_title(text: str) -> bool:
    return bool(_ENGLISH_START_RE.search(text)) and not _contains_cjk(text)


def _looks_like_chinese_mission_heading(text: str) -> bool:
    return _contains_cjk(text) and "使命" in text and "愿景" in text and "摘要" not in text


def _looks_like_english_mission_heading(text: str) -> bool:
    return "Mission, Educational Goal and Vision" in text


def _looks_like_policy_intro(text: str) -> bool:
    return _contains_cjk(text) and "员工纪律制度" in text and ("引 言" in text or "引言" in text)


def _looks_like_chinese_major_heading(text: str) -> bool:
    return bool(_CHINESE_MAJOR_HEADING_RE.search(text))


def _looks_like_english_summary(text: str) -> bool:
    return not _contains_cjk(text) and text.startswith("We are a group of people")


def _language_for_text(text: str) -> str:
    if _contains_cjk(text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return "neutral"



def _chinese_policy_chunks(text: str, *, document_name: str, max_chars: int, source_offset: int) -> list[DocumentChunk]:
    sections = _major_sections(text)
    if not sections and _VIOLATION_CATEGORY_RE.search(text):
        return _violation_chunks(text, heading="四、违规行为", document_name=document_name, max_chars=max_chars, source_offset=source_offset)
    if not sections:
        return []

    chunks: list[DocumentChunk] = []
    preface = text[: sections[0][1]].strip()
    if preface and _contains_cjk(preface):
        chunks.extend(
            _bounded_chunks(
                preface,
                heading_path=[document_name, "文档背景"],
                metadata={"chunk_type": "document_intro", "language": "zh", "chunking_strategy": "policy_clause_group"},
                max_chars=max_chars,
                source_start=source_offset,
            )
        )

    for index, (heading, start, body_start) in enumerate(sections):
        end = sections[index + 1][1] if index + 1 < len(sections) else len(text)
        section_text = text[start:end].strip()
        section_body = text[body_start:end].strip()
        if heading.startswith("四、") and "违规行为" in heading:
            section_heading_text = text[start:body_start].strip()
            if _is_substantive_section_intro(section_heading_text, heading):
                chunks.extend(
                    _bounded_chunks(
                        section_heading_text,
                        heading_path=[document_name, heading],
                        metadata={
                            "chunk_type": "policy_section",
                            "language": "zh",
                            "section_title": heading,
                            "chunk_role": "coverage",
                            "chunking_strategy": "policy_clause_group",
                        },
                        max_chars=max_chars,
                        source_start=source_offset + start,
                    )
                )
            chunks.extend(_violation_chunks(section_text, heading=heading, document_name=document_name, max_chars=max_chars, source_offset=source_offset + start))
        elif heading.startswith("五、") and "违规行为相应处理" in heading:
            first_action = _SUBCLAUSE_RE.search(section_text)
            if first_action and first_action.start() > 0:
                chunks.extend(
                    _bounded_chunks(
                        section_text[: first_action.start()].strip(),
                        heading_path=[document_name, heading],
                        metadata={"chunk_type": "policy_section", "language": "zh", "section_title": heading, "chunking_strategy": "policy_clause_group"},
                        max_chars=max_chars,
                        source_start=source_offset + start,
                    )
                )
            chunks.extend(_disciplinary_action_chunks(section_text, heading=heading, document_name=document_name, max_chars=max_chars, source_offset=source_offset + start))
        elif heading.startswith("九、") or "附件" in heading:
            chunks.extend(
                _bounded_chunks(
                    section_text,
                    heading_path=[document_name, heading],
                    metadata={"chunk_type": "appendix", "language": "zh", "section_title": heading, "chunking_strategy": "policy_clause_group"},
                    max_chars=max_chars,
                    source_start=source_offset + start,
                )
            )
        elif section_body:
            chunks.extend(
                _bounded_chunks(
                    section_text,
                    heading_path=[document_name, heading],
                    metadata={"chunk_type": "policy_section", "language": "zh", "section_title": heading, "chunking_strategy": "policy_clause_group"},
                    max_chars=max_chars,
                    source_start=source_offset + start,
                )
            )
    return chunks


def _is_substantive_section_intro(text: str, heading: str) -> bool:
    normalized = normalize_whitespace(text)
    return bool(normalized and normalized != _normalize_heading(heading))


def _major_sections(text: str) -> list[tuple[str, int, int]]:
    sections: list[tuple[str, int, int]] = []
    seen_starts: set[int] = set()
    for match in _CHINESE_MAJOR_HEADING_RE.finditer(text):
        heading = _normalize_heading(match.group(1))
        if match.start() in seen_starts:
            continue
        seen_starts.add(match.start())
        sections.append((heading, match.start(), match.end()))
    return sections


def _violation_chunks(section_text: str, *, heading: str, document_name: str, max_chars: int, source_offset: int) -> list[DocumentChunk]:
    category_matches = list(_VIOLATION_CATEGORY_RE.finditer(section_text))
    chunks: list[DocumentChunk] = []
    for index, category_match in enumerate(category_matches):
        category_title = _normalize_heading(category_match.group(2))
        category_start = category_match.start()
        category_end = category_matches[index + 1].start() if index + 1 < len(category_matches) else len(section_text)
        category_text = section_text[category_start:category_end].strip()
        level = _VIOLATION_LEVELS.get(category_title)
        group_matches = list(_GROUP_HEADING_RE.finditer(category_text))

        overview_end = group_matches[0].start() if group_matches else len(category_text)
        group_titles = [f"{match.group(1)}. {_normalize_heading(match.group(2))}" for match in group_matches]
        overview_parts = [heading] if index == 0 and heading else []
        overview_parts.extend([category_text[:overview_end].strip(), *group_titles])
        overview_text = normalize_whitespace(" ".join(overview_parts))
        if overview_text:
            chunks.extend(
                _bounded_chunks(
                    overview_text,
                    heading_path=[document_name, category_title],
                    metadata={
                        "chunk_type": "violation_category_overview",
                        "legacy_chunk_type": "section_overview",
                        "language": "zh",
                        "section_title": category_title,
                        "section_marker": _normalize_heading(category_match.group(1)),
                        "section_path": [category_title],
                        "start_marker": _normalize_heading(category_match.group(1)),
                        "end_marker": None,
                        "violation_level": level,
                        "chunking_strategy": "policy_clause_group",
                    },
                    max_chars=max_chars,
                    source_start=source_offset if index == 0 and heading else source_offset + category_start,
                )
            )

        for group_index, group_match in enumerate(group_matches):
            group_end = group_matches[group_index + 1].start() if group_index + 1 < len(group_matches) else len(category_text)
            group_text = category_text[group_match.start() : group_end].strip()
            clause_no = group_match.group(1)
            group_title = f"{clause_no}. {_normalize_heading(group_match.group(2))}"
            metadata = {
                "chunk_type": "clause_group",
                "language": "zh",
                "section_title": category_title,
                "group_title": group_title,
                "clause_title": group_title,
                "clause_no": clause_no,
                "clause_range": _clause_range(group_text, clause_no),
                "section_path": [category_title, group_title],
                "start_marker": group_title,
                "end_marker": None,
                "violation_level": level,
                "chunking_strategy": "policy_clause_group",
            }
            chunks.extend(
                _bounded_chunks(
                    group_text,
                    heading_path=[document_name, category_title, group_title],
                    metadata=metadata,
                    max_chars=max_chars,
                    source_start=source_offset + category_start + group_match.start(),
                )
            )
    return chunks


def _disciplinary_action_chunks(section_text: str, *, heading: str, document_name: str, max_chars: int, source_offset: int) -> list[DocumentChunk]:
    matches = list(_SUBCLAUSE_RE.finditer(section_text))
    chunks: list[DocumentChunk] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section_text)
        clause_text = section_text[match.start() : end].strip()
        if not clause_text:
            continue
        target_title = _first_violation_title(clause_text)
        clause_no = match.group(1)
        if target_title:
            metadata = {
                "chunk_type": "action_clause",
                "language": "zh",
                "action_target": _VIOLATION_LEVELS[target_title],
                "violation_level": _VIOLATION_LEVELS[target_title],
                "clause_no": clause_no,
                "section_title": heading,
                "section_path": [heading, f"{clause_no} {target_title}"],
                "chunking_strategy": "policy_clause_group",
            }
            action_heading = f"{clause_no} {target_title}"
        else:
            metadata = {
                "chunk_type": "disciplinary_rule",
                "language": "zh",
                "clause_no": clause_no,
                "section_title": heading,
                "section_path": [heading, clause_no],
                "chunking_strategy": "policy_clause_group",
            }
            action_heading = clause_no
        chunks.extend(
            _bounded_chunks(
                clause_text,
                heading_path=[document_name, heading, action_heading],
                metadata=metadata,
                max_chars=max_chars,
                source_start=source_offset + match.start(),
            )
        )
    return chunks


def _chunk_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    chunk_metadata = dict(metadata)
    chunk_metadata.setdefault("chunking_strategy", "policy_clause_group")
    chunk_type = chunk_metadata.get("chunk_type")
    default_role = "retrieval" if chunk_type in _RETRIEVAL_CHUNK_TYPES else "coverage"
    chunk_metadata.setdefault("chunk_role", default_role)
    if chunk_metadata.get("chunk_role") == "retrieval":
        chunk_metadata.setdefault("retrieval_priority", "high")
        chunk_metadata.setdefault("index_scope", "main")
    else:
        chunk_metadata.setdefault("retrieval_priority", "low")
        chunk_metadata.setdefault("index_scope", "coverage")
    return chunk_metadata


def _bounded_chunks(text: str, *, heading_path: list[str], metadata: dict[str, Any], max_chars: int, source_start: int) -> list[DocumentChunk]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        chunk_metadata = _chunk_metadata(metadata)
        chunk_metadata["source_span"] = {"start": source_start, "end": source_start + len(text)}
        return [DocumentChunk(chunk_id="", text=normalized, heading_path=heading_path, metadata=chunk_metadata)]

    chunks: list[DocumentChunk] = []
    cursor = 0
    for index, part in enumerate(_split_without_overlap(normalized, max_chars=max_chars), start=1):
        child_metadata = _chunk_metadata(metadata)
        child_metadata["split_reason"] = "exceeds_max_chars"
        child_metadata["split_index"] = index
        relative_start = text.find(part, cursor)
        if relative_start < 0:
            relative_start = cursor
        relative_end = relative_start + len(part)
        cursor = relative_end
        child_metadata["source_span"] = {"start": source_start + relative_start, "end": source_start + relative_end}
        chunks.append(DocumentChunk(chunk_id="", text=part, heading_path=heading_path, metadata=child_metadata))
    return chunks


def _split_without_overlap(text: str, *, max_chars: int) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind(mark, start, end) for mark in ["。", "；", ";", ".", " "])
            if boundary > start + max_chars // 2:
                end = boundary + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return parts


def _clause_range(group_text: str, clause_no: str) -> str | None:
    sub_numbers = [f"{clause_no}.{item}" for item in re.findall(rf"(?<!\d){re.escape(clause_no)}\.(\d+)", group_text)]
    if not sub_numbers:
        return None
    return f"{sub_numbers[0]}-{sub_numbers[-1]}" if len(sub_numbers) > 1 else sub_numbers[0]


def _first_violation_title(text: str) -> str | None:
    for title in _VIOLATION_LEVELS:
        if title in text:
            return title
    return None


def _normalize_heading(text: str) -> str:
    return normalize_whitespace(text).strip(" ：:")


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))
