from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ChunkingStatus = Literal["success", "partial", "failed"]


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    text: str
    heading_path: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkQualityReport:
    chunker_name: str
    chunker_version: str
    status: ChunkingStatus
    chunking_strategy: str
    chunk_profile: str = "auto"
    chunk_count: int = 0
    structured_chunk_count: int = 0
    fallback_chunk_count: int = 0
    boundary_confidence: str | None = None
    fallback_reason: str | None = None
    coverage_status: str = "unknown"
    source_char_count: int = 0
    covered_char_count: int = 0
    uncovered_char_count: int = 0
    coverage_ratio: float = 0.0
    element_coverage_status: str = "unknown"
    source_element_count: int = 0
    covered_element_count: int = 0
    uncovered_element_count: int = 0
    element_coverage_ratio: float = 0.0
    retrieval_chunk_count: int = 0
    coverage_chunk_count: int = 0
    english_retrieval_chunk_count: int = 0
    orphan_title_count: int = 0
    mixed_language_chunk_count: int = 0
    provenance_missing_count: int = 0
    retrieval_provenance_missing_count: int = 0
    uncovered_ranges: list[dict[str, Any]] = field(default_factory=list)
    uncovered_elements: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkedDocument:
    source_id: str
    source_name: str
    chunks: list[DocumentChunk]
    quality: ChunkQualityReport
