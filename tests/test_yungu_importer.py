import httpx
import pytest

from enterprise_rag_mvp.cli import build_parser

from enterprise_rag_mvp.models import PolicyChunk
from enterprise_rag_mvp.yungu_importer import (
    YunguApiError,
    YunguPolicyClient,
    clean_html_to_text,
    chunk_text,
    detail_to_policy_chunks,
    ingest_yungu_policies,
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
    assert chunks[0].doc_id == "yungu-policy-192"
    assert chunks[0].chunk_id.startswith("yungu-policy-192-chunk-")
    assert chunks[0].heading_path == ["HR政策及知识库", "员工年休假制度"]
    assert "员工连续工作" in " ".join(chunk.text for chunk in chunks)
    assert chunks[0].metadata["source"] == "yungu_policy_system"
    assert chunks[0].metadata["import_information_id"] == 192
    assert chunks[0].metadata["file_count"] == 1

    assert detail_to_policy_chunks({"importInformationId": 1, "cnTitle": "空", "body": "<p> </p>"}) == []


def test_yungu_policy_client_fetches_list_and_detail_and_rejects_login_failure():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/informationList"):
            return httpx.Response(
                200,
                json={
                    "status": True,
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

    client = YunguPolicyClient(session="session-value", transport=httpx.MockTransport(handler))

    page = client.fetch_information_page(page_num=1, page_size=20, policy_type=2, category_id=11)
    detail = client.fetch_detail(192)

    assert page.rows[0]["importInformationId"] == 192
    assert page.total == 1
    assert detail["importInformationId"] == 192
    assert requests[0].headers["Cookie"] == "SESSION=session-value"
    assert requests[0].url.params["policyCategoryType"] == "11"

    def login_failed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False, "ifLogin": False, "message": "not login"})

    failed_client = YunguPolicyClient(session="bad", transport=httpx.MockTransport(login_failed))
    with pytest.raises(YunguApiError):
        failed_client.fetch_detail(1)


class FakeYunguClient:
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


def test_ingest_yungu_policies_fetches_details_embeds_and_stores_chunks():
    embedding_client = FakeEmbeddingClient()
    store = FakeStore()

    stats = ingest_yungu_policies(
        client=FakeYunguClient(),
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
    assert store.saved[0].metadata["source"] == "yungu_policy_system"
    assert embedding_client.texts == [chunk.text for chunk in store.saved]


def test_cli_exposes_safe_yungu_ingest_defaults():
    args = build_parser().parse_args(["ingest-yungu-policies", "--session", "session-value", "--dry-run"])

    assert args.max_docs == 2
    assert args.all is False
    assert args.page_size == 20
    assert args.dry_run is True
