from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ParseStatus = Literal["success", "partial", "failed"]
DocumentKind = Literal["html", "text", "pdf", "docx", "image", "unsupported"]


@dataclass(frozen=True)
class DocumentSource:
    source_id: str
    source_name: str
    file_name: str | None = None
    content_type: str | None = None
    content: bytes | None = None
    text: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedElement:
    element_id: str
    element_type: str
    text: str
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    heading_path: list[str] = field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseQualityReport:
    parser_name: str
    parser_version: str
    status: ParseStatus
    page_count: int | None = None
    element_count: int = 0
    low_confidence_count: int = 0
    table_count: int = 0
    image_ocr_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedDocument:
    source_id: str
    source_name: str
    source_type: DocumentKind
    elements: list[ParsedElement]
    quality: ParseQualityReport
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentParser(Protocol):
    def parse(self, source: DocumentSource) -> ParsedDocument:
        ...
