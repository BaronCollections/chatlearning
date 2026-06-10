from enterprise_rag_mvp.models import PolicyChunk, SearchResult
from enterprise_rag_mvp.embedding_client import EmbeddingClient
from enterprise_rag_mvp.cli import _schema_path
from enterprise_rag_mvp.pgvector_store import build_vector_literal
from enterprise_rag_mvp.render import render_results
from enterprise_rag_mvp.samples import sample_policy_chunks


def test_render_results_includes_rank_title_source_and_distance():
    chunk = PolicyChunk(
        chunk_id="leave-001",
        doc_id="employee-leave-policy",
        block_id="article-3",
        text="员工连续工作满一年后，可依法享受带薪年休假。",
        heading_path=["员工休假管理办法", "第三条 年休假"],
        metadata={"source": "员工休假管理办法.md", "page": 3},
    )
    result = SearchResult(chunk=chunk, distance=0.123456)

    rendered = render_results("员工年假规则是什么？", [result])

    assert "Query: 员工年假规则是什么？" in rendered
    assert "1. 员工休假管理办法 > 第三条 年休假" in rendered
    assert "distance=0.1235" in rendered
    assert "员工连续工作满一年后" in rendered
    assert "source=员工休假管理办法.md" in rendered
    assert "page=3" in rendered


def test_build_vector_literal_formats_pgvector_value():
    assert build_vector_literal([0.1, -0.25, 1.0]) == "[0.1,-0.25,1.0]"


def test_sample_policy_chunks_include_business_metadata():
    chunks = sample_policy_chunks()

    assert len(chunks) >= 3
    assert all(chunk.chunk_id for chunk in chunks)
    assert all(chunk.heading_path for chunk in chunks)
    assert all("source" in chunk.metadata for chunk in chunks)


def test_embedding_client_extracts_embeddings_from_service_response(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://embedding.local/embed",
        json={
            "model": "models/bge-m3",
            "model_key": "bge-m3",
            "dimension": 3,
            "normalize": True,
            "input_type": "query",
            "embeddings": [[0.1, 0.2, 0.3]],
            "usage": {"text_count": 1},
        },
    )
    client = EmbeddingClient(base_url="http://embedding.local")

    embeddings = client.embed(["员工年假规则是什么？"], input_type="query")

    assert embeddings == [[0.1, 0.2, 0.3]]


def test_embedding_client_extracts_tokenize_response(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://embedding.local/tokenize",
        json={
            "text": "员工年假规则是什么？",
            "tokenizer": "bge-m3",
            "tokens": ["▁员工", "年", "假"],
            "token_ids": [101, 102, 103],
            "token_count": 3,
            "max_input_tokens": 8192,
            "truncated": False,
        },
    )
    client = EmbeddingClient(base_url="http://embedding.local")

    token_info = client.tokenize("员工年假规则是什么？")

    assert token_info["tokens"] == ["▁员工", "年", "假"]
    assert token_info["token_ids"] == [101, 102, 103]


def test_schema_path_points_to_existing_pgvector_schema():
    path = _schema_path()

    assert path.name == "001_pgvector_schema.sql"
    assert path.exists()


def test_sample_policy_chunks_cover_absenteeism_rule_demo():
    texts = "\n".join(chunk.text for chunk in sample_policy_chunks())

    assert "连续旷工3个工作日以下" in texts
    assert "扣除旷工期间工资" in texts
    assert "记过处分" in texts
    assert "4.2旷工少于三天" in texts
    assert "二类违规行为" in texts
