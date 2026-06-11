from __future__ import annotations

from pathlib import Path

from enterprise_rag_mvp.document_parsing.html_parser import HtmlDocumentParser
from enterprise_rag_mvp.document_parsing.models import DocumentKind, DocumentParser, DocumentSource, ParsedDocument, ParseQualityReport


def detect_document_kind(*, file_name: str | None, content_type: str | None, content: bytes | None = None) -> DocumentKind:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = Path(file_name or "").suffix.lower()
    sample = content or b""
    if normalized_type in {"text/html", "application/xhtml+xml"} or suffix in {".html", ".htm"}:
        return "html"
    if normalized_type.startswith("text/") or suffix in {".txt", ".md", ".markdown"}:
        return "text"
    if normalized_type == "application/pdf" or suffix == ".pdf" or sample.startswith(b"%PDF"):
        return "pdf"
    if normalized_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    } or suffix in {".docx", ".doc"}:
        return "docx"
    if normalized_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        return "image"
    return "unsupported"


def parsed_document_text(document: ParsedDocument) -> str:
    return " ".join(element.text for element in document.elements if element.text).strip()


class PlainTextDocumentParser:
    def parse(self, source: DocumentSource) -> ParsedDocument:
        text = source.text
        if text is None and source.content is not None:
            text = source.content.decode("utf-8", errors="replace")
        text = " ".join((text or "").split())
        elements = []
        if text:
            from enterprise_rag_mvp.document_parsing.models import ParsedElement

            elements = [ParsedElement(element_id="element-0001", element_type="paragraph", text=text)]
        status = "success" if elements else "failed"
        warnings = [] if elements else ["Plain text source produced no parseable text elements."]
        return ParsedDocument(
            source_id=source.source_id,
            source_name=source.source_name,
            source_type="text",
            source_url=source.source_url,
            metadata=dict(source.metadata),
            elements=elements,
            quality=ParseQualityReport(
                parser_name="text_builtin",
                parser_version="1",
                status=status,
                element_count=len(elements),
                warnings=warnings,
            ),
        )


class UnsupportedDocumentParser:
    _WARNINGS = {
        "pdf": "PDF parser is not configured. Enable Docling/PyMuPDF in the document parsing layer.",
        "docx": "DOCX parser is not configured. Enable Docling/python-docx in the document parsing layer.",
        "image": "Image OCR parser is not configured. Enable PaddleOCR or an OCR service in the document parsing layer.",
        "unsupported": "Unsupported document type. Add a parser or convert the file before ingestion.",
    }

    def __init__(self, kind: DocumentKind) -> None:
        self.kind = kind

    def parse(self, source: DocumentSource) -> ParsedDocument:
        warning = self._WARNINGS.get(self.kind, self._WARNINGS["unsupported"])
        return ParsedDocument(
            source_id=source.source_id,
            source_name=source.source_name,
            source_type=self.kind,
            source_url=source.source_url,
            metadata=dict(source.metadata),
            elements=[],
            quality=ParseQualityReport(
                parser_name=f"unsupported_{self.kind}",
                parser_version="1",
                status="failed",
                element_count=0,
                warnings=[warning],
            ),
        )


class DocumentParserRouter:
    def __init__(self, parsers: dict[DocumentKind, DocumentParser] | None = None) -> None:
        self._parsers: dict[DocumentKind, DocumentParser] = {
            "html": HtmlDocumentParser(),
            "text": PlainTextDocumentParser(),
        }
        if parsers:
            self._parsers.update(parsers)

    def parse(self, source: DocumentSource) -> ParsedDocument:
        kind = detect_document_kind(file_name=source.file_name, content_type=source.content_type, content=source.content)
        parser = self._parsers.get(kind)
        if parser is None:
            parser = UnsupportedDocumentParser(kind)
        return parser.parse(source)
