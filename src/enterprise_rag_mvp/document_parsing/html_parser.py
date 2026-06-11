from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any

from enterprise_rag_mvp.document_parsing.models import DocumentSource, ParsedDocument, ParsedElement, ParseQualityReport

PARSER_NAME = "html_builtin"
PARSER_VERSION = "1"


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


class _StructuredHTMLExtractor(HTMLParser):
    _HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
    _PARAGRAPH_TAGS = {"p", "li", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[ParsedElement] = []
        self._ignored_depth = 0
        self._headings: dict[int, str] = {}
        self._block_type: str | None = None
        self._block_tag: str | None = None
        self._block_level: int | None = None
        self._block_parts: list[str] = []
        self._table_rows: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth > 0:
            return
        if tag in self._HEADING_TAGS:
            self._start_block("title", tag, self._HEADING_TAGS[tag])
            return
        if tag in self._PARAGRAPH_TAGS:
            self._start_block("paragraph", tag, None)
            return
        if tag == "table":
            self._table_rows = []
            return
        if tag == "tr" and self._table_rows is not None:
            self._current_row = []
            return
        if tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
            return
        if tag == "br":
            self._append_data(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if self._ignored_depth > 0:
            return
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            cell = normalize_whitespace("".join(self._current_cell))
            self._current_row.append(cell)
            self._current_cell = None
            return
        if tag == "tr" and self._current_row is not None and self._table_rows is not None:
            if any(cell for cell in self._current_row):
                self._table_rows.append(self._current_row)
            self._current_row = None
            return
        if tag == "table" and self._table_rows is not None:
            self._finish_table()
            return
        if self._block_tag == tag:
            self._finish_block()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._append_data(data)

    def _append_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)
        elif self._block_type is not None:
            self._block_parts.append(data)

    def _start_block(self, block_type: str, tag: str, level: int | None) -> None:
        if self._block_type is not None:
            self._finish_block()
        self._block_type = block_type
        self._block_tag = tag
        self._block_level = level
        self._block_parts = []

    def _current_heading_path(self) -> list[str]:
        return [self._headings[level] for level in sorted(self._headings) if self._headings[level]]

    def _finish_block(self) -> None:
        text = normalize_whitespace(html.unescape("".join(self._block_parts)))
        block_type = self._block_type
        level = self._block_level
        if text and block_type == "title" and level is not None:
            for stale_level in [key for key in self._headings if key >= level]:
                del self._headings[stale_level]
            self._headings[level] = text
            self._add_element("title", text, self._current_heading_path())
        elif text and block_type == "paragraph":
            self._add_element("paragraph", text, self._current_heading_path())
        self._block_type = None
        self._block_tag = None
        self._block_level = None
        self._block_parts = []

    def _finish_table(self) -> None:
        rows = self._table_rows or []
        lines = [" | ".join(cell for cell in row) for row in rows if any(row)]
        text = normalize_whitespace("\n".join(lines))
        if text:
            self._add_element("table", text, self._current_heading_path(), {"row_count": len(rows)})
        self._table_rows = None
        self._current_row = None
        self._current_cell = None

    def _add_element(self, element_type: str, text: str, heading_path: list[str], metadata: dict[str, Any] | None = None) -> None:
        element_index = len(self.elements) + 1
        self.elements.append(
            ParsedElement(
                element_id=f"element-{element_index:04d}",
                element_type=element_type,
                text=text,
                heading_path=list(heading_path),
                metadata=metadata or {},
            )
        )


class HtmlDocumentParser:
    def parse(self, source: DocumentSource) -> ParsedDocument:
        raw_html = source.text
        if raw_html is None and source.content is not None:
            raw_html = source.content.decode("utf-8", errors="replace")
        raw_html = raw_html or ""
        extractor = _StructuredHTMLExtractor()
        extractor.feed(raw_html)
        extractor.close()
        elements = extractor.elements
        warnings: list[str] = []
        status = "success"
        if not elements:
            status = "failed"
            warnings.append("HTML body produced no parseable text elements.")
        return ParsedDocument(
            source_id=source.source_id,
            source_name=source.source_name,
            source_type="html",
            source_url=source.source_url,
            metadata=dict(source.metadata),
            elements=elements,
            quality=ParseQualityReport(
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
                status=status,
                page_count=None,
                element_count=len(elements),
                table_count=sum(1 for element in elements if element.element_type == "table"),
                image_ocr_count=0,
                low_confidence_count=0,
                warnings=warnings,
            ),
        )


def clean_html_to_text(raw_html: str | None) -> str:
    parsed = HtmlDocumentParser().parse(
        DocumentSource(source_id="html-body", source_name="HTML body", content_type="text/html", text=raw_html or "")
    )
    return " ".join(element.text for element in parsed.elements).strip()
