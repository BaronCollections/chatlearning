import argparse
import os
import sys
from pathlib import Path

from enterprise_rag_mvp.embedding_client import EmbeddingClient
from enterprise_rag_mvp.pgvector_store import PgVectorStore
from enterprise_rag_mvp.render import render_results
from enterprise_rag_mvp.samples import sample_policy_chunks

DEFAULT_DSN = "postgresql://127.0.0.1:5432/enterprise_rag_mvp"
DEFAULT_EMBEDDING_URL = "http://127.0.0.1:8001"


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "db" / "001_pgvector_schema.sql"


def _dsn(args: argparse.Namespace) -> str:
    return args.dsn or os.getenv("RAG_DATABASE_DSN", DEFAULT_DSN)


def _embedding_url(args: argparse.Namespace) -> str:
    return args.embedding_url or os.getenv("EMBEDDING_SERVICE_URL", DEFAULT_EMBEDDING_URL)


def init_db(args: argparse.Namespace) -> None:
    schema_sql = _schema_path().read_text(encoding="utf-8")
    PgVectorStore(_dsn(args)).apply_schema(schema_sql)
    print("Applied pgvector schema.")


def ingest_samples(args: argparse.Namespace) -> None:
    chunks = sample_policy_chunks()
    client = EmbeddingClient(base_url=_embedding_url(args))
    embeddings = client.embed([chunk.text for chunk in chunks], input_type="document")
    PgVectorStore(_dsn(args)).upsert_chunks(chunks, embeddings)
    print(f"Ingested {len(chunks)} sample policy chunks.")


def search(args: argparse.Namespace) -> None:
    client = EmbeddingClient(base_url=_embedding_url(args))
    query_embedding = client.embed([args.query], input_type="query")[0]
    results = PgVectorStore(_dsn(args)).search(query_embedding, top_k=args.top_k)
    print(render_results(args.query, results))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enterprise RAG minimal MVP")
    parser.add_argument("--dsn", help=f"Postgres DSN. Default: {DEFAULT_DSN}")
    parser.add_argument("--embedding-url", help=f"Embedding service URL. Default: {DEFAULT_EMBEDDING_URL}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Apply pgvector schema")
    init_parser.set_defaults(func=init_db)

    ingest_parser = subparsers.add_parser("ingest-samples", help="Embed and store sample policy chunks")
    ingest_parser.set_defaults(func=ingest_samples)

    search_parser = subparsers.add_parser("search", help="Search sample policy chunks")
    search_parser.add_argument("query")
    search_parser.add_argument("--top-k", type=int, default=3)
    search_parser.set_defaults(func=search)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        if 'extension "vector" is not available' in str(exc):
            print(
                "pgvector is not available in the running Postgres instance. "
                "Install pgvector for that Postgres major version, or run a pgvector-enabled Postgres.",
                file=sys.stderr,
            )
        raise


if __name__ == "__main__":
    main()
