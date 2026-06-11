from enterprise_rag_mvp.document_parsing import (
    DocumentParserRouter,
    DocumentSource,
    HtmlDocumentParser,
    detect_document_kind,
    parsed_document_text,
)


def test_detect_document_kind_uses_mime_extension_and_magic_bytes():
    assert detect_document_kind(file_name="policy.pdf", content_type="application/pdf", content=b"%PDF-1.7") == "pdf"
    assert detect_document_kind(file_name="policy.docx", content_type=None, content=b"PK\x03\x04...") == "docx"
    assert detect_document_kind(file_name="scan.png", content_type="image/png", content=b"\x89PNG\r\n") == "image"
    assert detect_document_kind(file_name="body.html", content_type="text/html", content=b"<html></html>") == "html"
    assert detect_document_kind(file_name="unknown.bin", content_type="application/octet-stream", content=b"raw") == "unsupported"


def test_html_document_parser_outputs_elements_and_quality_report():
    parser = HtmlDocumentParser()

    parsed = parser.parse(
        DocumentSource(
            source_id="body-16",
            source_name="制度正文",
            content_type="text/html",
            text="""
            <h1>员工纪律制度</h1>
            <p>二类违规行为：比较严重的违规行为。</p>
            <table>
              <tr><th>违规类型</th><th>处理结果</th></tr>
              <tr><td>二类违规</td><td>记过处分</td></tr>
            </table>
            <script>alert(1)</script>
            """,
            metadata={"source_url": "https://example.com/policyDetail/16"},
        )
    )

    assert parsed.quality.status == "success"
    assert parsed.quality.parser_name == "html_builtin"
    assert parsed.quality.element_count == 3
    assert parsed.quality.table_count == 1
    assert [element.element_type for element in parsed.elements] == ["title", "paragraph", "table"]
    assert parsed.elements[1].heading_path == ["员工纪律制度"]
    assert "违规类型 | 处理结果" in parsed.elements[2].text
    assert "alert" not in parsed_document_text(parsed)


def test_html_document_parser_keeps_pasted_plain_text_as_paragraphs():
    parser = HtmlDocumentParser()

    parsed = parser.parse(
        DocumentSource(
            source_id="body-plain",
            source_name="员工纪律制度",
            content_type="text/html",
            text="""
            示例机构员工纪律制度
            Example School Employee Disciplinary Rules

            一、目的
            为落实示例学校的使命、愿景和文化理念，根据有关法律法规和学校实际情况制定本制度。
            """,
        )
    )

    assert parsed.quality.status == "success"
    assert parsed.quality.parser_name == "html_builtin"
    assert parsed.quality.element_count >= 2
    assert parsed.elements[0].element_type == "paragraph"
    assert "示例机构员工纪律制度" in parsed_document_text(parsed)
    assert "一、目的" in parsed_document_text(parsed)


def test_parser_router_returns_actionable_report_for_unconfigured_heavy_formats():
    router = DocumentParserRouter()

    parsed = router.parse(
        DocumentSource(
            source_id="attachment-1",
            source_name="附件.pdf",
            file_name="附件.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.7",
        )
    )

    assert parsed.source_type == "pdf"
    assert parsed.elements == []
    assert parsed.quality.status == "failed"
    assert parsed.quality.parser_name == "unsupported_pdf"
    assert parsed.quality.warnings == ["PDF parser is not configured. Enable Docling/PyMuPDF in the document parsing layer."]
