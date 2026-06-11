import httpx
import pytest

from enterprise_rag_mvp.cli import _company_base_url, build_parser

from enterprise_rag_mvp.models import PolicyChunk
from enterprise_rag_mvp.company_importer import (
    CompanyApiError,
    CompanyCategory,
    CompanyPolicyClient,
    clean_html_to_text,
    chunk_text,
    detail_to_policy_chunks,
    ingest_company_categories,
    ingest_company_policies,
    ingest_company_policy_report,
)


def test_clean_html_to_text_removes_tags_scripts_and_compresses_whitespace():
    html = """
    <h1>制度标题</h1><script>alert(1)</script>
    <p>&nbsp;第一条&nbsp;&nbsp;员工 年假</p><style>.x{}</style><p>第二条<br>换行</p>
    """

    text = clean_html_to_text(html)

    assert text == "制度标题 第一条 员工 年假 第二条 换行"
    assert "alert" not in text
    assert ".x" not in text


def test_chunk_text_keeps_overlap_and_validates_arguments():
    text = "第一段内容。第二段内容。第三段内容。第四段内容。"

    chunks = chunk_text(text, max_chars=12, overlap_chars=4)

    assert len(chunks) > 1
    assert all(len(chunk) <= 12 for chunk in chunks)
    assert chunks[1].startswith(chunks[0][-4:])

    with pytest.raises(ValueError):
        chunk_text(text, max_chars=10, overlap_chars=10)


def test_detail_to_policy_chunks_maps_metadata_and_skips_empty_body():
    detail = {
        "importInformationId": 192,
        "cnTitle": "员工年休假制度",
        "enTitle": "Annual Leave",
        "publishDate": "2026-01-02 10:00:00",
        "policyCategoryType": 11,
        "policyCategoryTypeName": "HR政策及知识库",
        "policySystemType": 2,
        "createUserName": "Admin",
        "body": "<h2>第一章</h2><p>员工连续工作满一年后，可享受年休假。</p>",
        "fileList": [{"name": "附件.pdf"}],
    }

    chunks = detail_to_policy_chunks(detail, max_chars=18, overlap_chars=4)

    assert chunks
    assert chunks[0].doc_id == "company-policy-192"
    assert chunks[0].chunk_id.startswith("company-policy-192-chunk-")
    assert chunks[0].heading_path == ["HR政策及知识库", "员工年休假制度"]
    assert "员工连续工作" in " ".join(chunk.text for chunk in chunks)
    assert chunks[0].metadata["source"] == "company_policy_system"
    assert chunks[0].metadata["import_information_id"] == 192
    assert chunks[0].metadata["file_count"] == 1
    assert chunks[0].metadata["parser_name"] == "html_builtin"
    assert chunks[0].metadata["parse_status"] == "success"
    assert chunks[0].metadata["parse_element_count"] >= 1
    assert chunks[0].metadata["attachment_parse_status"] == "not_fetched"

    assert detail_to_policy_chunks({"importInformationId": 1, "cnTitle": "空", "body": "<p> </p>"}) == []


def test_detail_to_policy_chunks_splits_violation_clause_groups():
    body = """
    <p>（二）二类违规行为</p>
    <p>二类违规行为：指违反师德师风、学校保密义务、破坏学校管理秩序等致使学校经济、形象、声誉遭受严重损害的行为，是比较严重的违规行为。</p>
    <p>3. 侵犯学校权益行为</p>
    <p>3.1未经学校授权发言，造成不良影响。</p>
    <p>4. 弄虚作假行为</p>
    <p>4.1向学校隐瞒或有意提交虚假的重大信息。</p>
    <p>4.2 在老师个人及学生各级考试各类评选活动中弄虚作假，营私舞弊并造成严重恶劣影响。</p>
    <p>4.3虚假报销，例如报销未发生的费用或以虚假理由报销费用等。</p>
    <p>4.4 其他弄虚作假给学校造成严重不良影响或经济、声誉损失的行为。</p>
    <p>5. 破坏学校管理秩序行为</p>
    <p>5.1旷工少于三天。</p>
    <p>（三）三类违规行为</p>
    <p>三类违规行为：指一般的违规行为。</p>
    """
    chunks = detail_to_policy_chunks(
        {
            "importInformationId": 16,
            "cnTitle": "***公司人守则-员工纪律制度",
            "policyCategoryTypeName": "***公司人守则",
            "body": body,
        }
    )

    clause_chunk = next(chunk for chunk in chunks if chunk.metadata.get("clause_title") == "4. 弄虚作假行为")

    assert clause_chunk.metadata["chunk_type"] == "clause_group"
    assert clause_chunk.metadata["section_title"] == "二类违规行为"
    assert clause_chunk.metadata["clause_no"] == "4"
    assert clause_chunk.metadata["clause_range"] == "4.1-4.4"
    assert clause_chunk.metadata["section_path"] == ["二类违规行为", "4. 弄虚作假行为"]
    assert clause_chunk.metadata["source_url"] == "https://example.com/policyDetail/16"
    assert "4.1向学校隐瞒" in clause_chunk.text
    assert "4.4 其他弄虚作假" in clause_chunk.text
    assert "3. 侵犯学校权益行为" not in clause_chunk.text
    assert "5. 破坏学校管理秩序行为" not in clause_chunk.text

    section_chunk = next(chunk for chunk in chunks if chunk.metadata.get("chunk_type") == "violation_category_overview")
    assert section_chunk.metadata["legacy_chunk_type"] == "section_overview"
    assert section_chunk.metadata["section_title"] == "二类违规行为"
    assert "二类违规行为：指违反师德师风" in section_chunk.text
    assert "4. 弄虚作假行为" in section_chunk.text
    assert "（三）三类违规行为" not in section_chunk.text


def test_detail_to_policy_chunks_includes_structured_disciplinary_action_chunks():
    body = """
    <p>四、违规行为</p>
    <p>（二）二类违规行为</p>
    <p>二类违规行为：指比较严重的违规行为。</p>
    <p>4. 破坏学校管理秩序行为</p>
    <p>4.1渎职给学校造成较大损失。</p>
    <p>4.2旷工少于三天。</p>
    <p>五、违规行为相应处理</p>
    <p>1. 违规行为相应处理</p>
    <p>1.1一类违规行为：解除劳动合同。</p>
    <p>1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪。</p>
    <p>1.3三类违规行为：予以书面或口头警告。</p>
    """

    chunks = detail_to_policy_chunks(
        {
            "importInformationId": 16,
            "cnTitle": "员工纪律制度",
            "policyCategoryTypeName": "HR政策及知识库",
            "body": body,
        }
    )

    action = next(chunk for chunk in chunks if chunk.metadata.get("action_target") == "category_2")
    assert action.metadata["chunk_type"] == "action_clause"
    assert action.metadata["chunking_strategy"] == "policy_clause_group"
    assert action.heading_path == ["HR政策及知识库", "员工纪律制度", "五、违规行为相应处理", "1.2 二类违规行为"]
    assert "1.2二类违规行为" in action.text
    assert "1.1一类违规行为" not in action.text
    assert "1.3三类违规行为" not in action.text

def test_company_policy_client_fetches_list_and_detail_and_rejects_login_failure():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/informationList"):
            return httpx.Response(
                200,
                json={
                    "status": True,
                    "code": 1001,
                    "message": "Success",
                    "ifLogin": True,
                    "content": {
                        "total": 1,
                        "pageNum": 1,
                        "pageSize": 20,
                        "data": [{"importInformationId": 192, "cnTitle": "员工年休假制度"}],
                    },
                },
            )
        if request.url.path.endswith("/notificationById"):
            return httpx.Response(200, json={"status": True, "ifLogin": True, "content": {"importInformationId": 192}})
        return httpx.Response(404)

    client = CompanyPolicyClient(auth_cookie="COMPANY_AUTH=sample", transport=httpx.MockTransport(handler))

    page = client.fetch_information_page(page_num=1, page_size=20, policy_type=2, category_id=11)
    detail = client.fetch_detail(192)

    assert page.rows[0]["importInformationId"] == 192
    assert page.total == 1
    assert detail["importInformationId"] == 192
    assert requests[0].headers["Cookie"] == "COMPANY_AUTH=sample"
    assert requests[0].url.params["policyCategoryType"] == "11"

    def login_failed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False, "ifLogin": False, "message": "not login"})

    failed_client = CompanyPolicyClient(auth_cookie="COMPANY_AUTH=bad", transport=httpx.MockTransport(login_failed))
    with pytest.raises(CompanyApiError):
        failed_client.fetch_detail(1)


class FakeCompanyClient:
    def fetch_information_page(self, *, page_num, page_size, policy_type, category_id=None, keyword=""):
        assert policy_type == 2
        return type("Page", (), {
            "rows": [{"importInformationId": 1, "cnTitle": "制度"}],
            "total": 1,
            "page_num": page_num,
            "page_size": page_size,
        })()

    def fetch_detail(self, import_information_id):
        assert import_information_id == 1
        return {
            "importInformationId": 1,
            "cnTitle": "制度",
            "policyCategoryTypeName": "HR",
            "body": "<p>员工连续工作满一年后，可享受年休假。</p>",
        }


class FakeEmbeddingClient:
    def __init__(self):
        self.texts = []

    def embed(self, texts, *, input_type):
        self.texts.extend(texts)
        assert input_type == "document"
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeStore:
    def __init__(self):
        self.saved = []

    def upsert_chunks(self, chunks: list[PolicyChunk], embeddings):
        assert len(chunks) == len(embeddings)
        self.saved.extend(chunks)


def test_ingest_company_policies_fetches_details_embeds_and_stores_chunks():
    embedding_client = FakeEmbeddingClient()
    store = FakeStore()

    stats = ingest_company_policies(
        client=FakeCompanyClient(),
        embedding_client=embedding_client,
        store=store,
        policy_type=2,
        page_size=20,
        max_docs=1,
        chunk_max_chars=30,
        chunk_overlap_chars=5,
        embedding_batch_size=2,
    )

    assert stats.documents_seen == 1
    assert stats.documents_imported == 1
    assert stats.chunks_stored >= 1
    assert store.saved[0].metadata["source"] == "company_policy_system"
    assert embedding_client.texts == [chunk.text for chunk in store.saved]


class FakeCategoryCompanyClient:
    def __init__(self):
        self.page_calls = []
        self.detail_calls = []

    def fetch_policy_categories(self, *, policy_type):
        assert policy_type == 2
        return [
            CompanyCategory(category_id=8, name="后勤制度", ename="Logistics Policy and Rules"),
            CompanyCategory(category_id=11, name="HR政策及知识库", ename="HR Policy and Knowledge Base"),
        ]

    def fetch_information_page(self, *, page_num, page_size, policy_type, category_id=None, keyword=""):
        self.page_calls.append((category_id, page_num, page_size))
        assert policy_type == 2
        rows_by_category = {
            8: {
                1: [{"importInformationId": 801, "cnTitle": "车辆管理"}],
                2: [{"importInformationId": 802, "cnTitle": "会议室管理"}],
            },
            11: {
                1: [{"importInformationId": 1101, "cnTitle": "年休假制度"}],
            },
        }
        totals = {8: 2, 11: 1}
        rows = rows_by_category.get(category_id, {}).get(page_num, [])
        return type("Page", (), {
            "rows": rows,
            "total": totals.get(category_id, 0),
            "page_num": page_num,
            "page_size": page_size,
        })()

    def fetch_detail(self, import_information_id):
        self.detail_calls.append(import_information_id)
        return {
            "importInformationId": import_information_id,
            "cnTitle": f"制度 {import_information_id}",
            "body": "<p>这是制度正文第一条。第二条用于测试分页分类导入。</p>",
        }


def test_ingest_company_categories_paginates_each_category_and_reports_documents():
    embedding_client = FakeEmbeddingClient()
    store = FakeStore()
    client = FakeCategoryCompanyClient()

    summary = ingest_company_categories(
        client=client,
        embedding_client=embedding_client,
        store=store,
        policy_type=2,
        page_size=1,
        max_docs_per_category=None,
        chunk_max_chars=60,
        chunk_overlap_chars=5,
        embedding_batch_size=2,
    )

    assert summary.category_count == 2
    assert summary.stats.documents_seen == 3
    assert summary.stats.documents_imported == 3
    assert summary.stats.pages_read == 3
    assert [report.category.name for report in summary.categories] == ["后勤制度", "HR政策及知识库"]
    assert summary.categories[0].total_available == 2
    assert [(doc.import_information_id, doc.title, doc.status) for doc in summary.categories[0].documents] == [
        (801, "制度 801", "imported"),
        (802, "制度 802", "imported"),
    ]
    assert client.page_calls == [(8, 1, 1), (8, 2, 1), (11, 1, 1)]
    assert client.detail_calls == [801, 802, 1101]
    assert len(store.saved) == summary.stats.chunks_stored
    assert store.saved[0].metadata["policy_category_type"] == 8
    assert store.saved[0].metadata["policy_category_type_name"] == "后勤制度"


def test_cli_exposes_safe_company_ingest_defaults():
    args = build_parser().parse_args(["ingest-company-policies", "--auth-cookie", "COMPANY_AUTH=sample", "--dry-run"])

    assert args.max_docs == 2
    assert args.all is False
    assert args.page_size == 20
    assert args.dry_run is True

    category_args = build_parser().parse_args([
        "ingest-company-policies",
        "--auth-cookie",
        "COMPANY_AUTH=sample",
        "--all-categories",
        "--dry-run",
    ])
    assert category_args.all_categories is True
    assert category_args.max_docs == 2


def test_company_base_url_uses_arg_env_then_placeholder(monkeypatch):
    parser = build_parser()

    explicit_args = parser.parse_args([
        "ingest-company-policies",
        "--auth-cookie",
        "COMPANY_AUTH=sample",
        "--base-url",
        "https://policy.example.test",
        "--dry-run",
    ])
    assert _company_base_url(explicit_args) == "https://policy.example.test"

    env_args = parser.parse_args(["ingest-company-policies", "--auth-cookie", "COMPANY_AUTH=sample", "--dry-run"])
    monkeypatch.setenv("COMPANY_POLICY_BASE_URL", "https://env-policy.example.test")
    assert _company_base_url(env_args) == "https://env-policy.example.test"

    monkeypatch.delenv("COMPANY_POLICY_BASE_URL")
    assert _company_base_url(env_args) == "https://example.com"


def test_processed_document_records_parse_quality_in_report():
    embedding_client = FakeEmbeddingClient()
    store = FakeStore()

    report = ingest_company_policy_report(
        client=FakeCompanyClient(),
        embedding_client=embedding_client,
        store=store,
        policy_type=2,
        page_size=20,
        max_docs=1,
        chunk_max_chars=80,
        chunk_overlap_chars=5,
        dry_run=True,
    )

    assert report.documents[0].parse_status == "success"
    assert report.documents[0].parse_warning_count == 0
    assert report.documents[0].attachment_count == 0


def test_detail_to_policy_chunks_can_parse_text_attachment_when_enabled():
    detail = {
        "importInformationId": 88,
        "cnTitle": "附件制度",
        "policyCategoryTypeName": "HR",
        "body": "<p>正文条款。</p>",
        "fileList": [
            {"name": "补充说明.txt", "url": "https://files.example.test/policy-88.txt", "contentType": "text/plain"}
        ],
    }

    def fetch_attachment(raw_attachment):
        assert raw_attachment["name"] == "补充说明.txt"
        return "附件里的补充条款。".encode("utf-8")

    chunks = detail_to_policy_chunks(
        detail,
        max_chars=80,
        overlap_chars=5,
        parse_attachments=True,
        attachment_fetcher=fetch_attachment,
    )

    assert any(chunk.metadata.get("source") == "company_policy_attachment" for chunk in chunks)
    attachment_chunk = next(chunk for chunk in chunks if chunk.metadata.get("source") == "company_policy_attachment")
    assert attachment_chunk.text == "附件里的补充条款。"
    assert attachment_chunk.metadata["attachment_name"] == "补充说明.txt"
    assert attachment_chunk.metadata["parser_name"] == "text_builtin"
    body_chunk = next(chunk for chunk in chunks if chunk.metadata.get("source") == "company_policy_system")
    assert body_chunk.metadata["attachment_parse_status"] == "success"
    assert body_chunk.metadata["attachment_parsed_count"] == 1


def test_detail_to_policy_chunks_imports_attachment_when_body_is_empty():
    detail = {
        "importInformationId": 89,
        "cnTitle": "附件-only 制度",
        "policyCategoryTypeName": "HR",
        "body": "<p> </p>",
        "fileList": [
            {"name": "正式制度.txt", "url": "https://files.example.test/policy-89.txt", "contentType": "text/plain"}
        ],
    }

    chunks = detail_to_policy_chunks(
        detail,
        max_chars=80,
        overlap_chars=5,
        parse_attachments=True,
        attachment_fetcher=lambda raw_attachment: "附件才是正式制度内容。".encode("utf-8"),
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["source"] == "company_policy_attachment"
    assert chunks[0].metadata["parent_doc_id"] == "company-policy-89"
    assert chunks[0].metadata["import_information_id"] == 89
    assert chunks[0].metadata["file_count"] == 1
    assert chunks[0].metadata["attachment_parse_status"] == "success"
    assert chunks[0].metadata["attachment_parsed_count"] == 1
    assert chunks[0].metadata["title"] == "附件-only 制度"
    assert chunks[0].text == "附件才是正式制度内容。"
