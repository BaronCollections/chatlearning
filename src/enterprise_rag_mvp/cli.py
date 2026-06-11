import argparse
import os
import sys
from pathlib import Path

from enterprise_rag_mvp.embedding_client import EmbeddingClient
from enterprise_rag_mvp.pgvector_store import PgVectorStore
from enterprise_rag_mvp.render import render_results
from enterprise_rag_mvp.samples import sample_policy_chunks
from enterprise_rag_mvp.company_importer import (
    DEFAULT_POLICY_TYPE,
    DEFAULT_COMPANY_BASE_URL,
    CompanyCategoryImportSummary,
    CompanyPolicyClient,
    ingest_company_categories,
    ingest_company_policies,
)

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


def _company_auth_cookie(args: argparse.Namespace) -> str:
    auth_cookie = args.auth_cookie or os.getenv("COMPANY_AUTH_COOKIE", "")
    if not auth_cookie.strip():
        raise ValueError("Company authentication cookie is required. Pass --auth-cookie or set COMPANY_AUTH_COOKIE.")
    return auth_cookie.strip()


def _company_base_url(args: argparse.Namespace) -> str:
    return args.base_url or os.getenv("COMPANY_POLICY_BASE_URL", DEFAULT_COMPANY_BASE_URL)


def render_company_category_summary(summary: CompanyCategoryImportSummary, *, dry_run: bool) -> str:
    stats = summary.stats
    action = "Prepared" if dry_run else "Ingested"
    chunk_label = "prepared" if dry_run else "stored"
    lines = [
        (
            f"{action} Company policy categories: "
            f"categories={summary.category_count}, "
            f"documents_seen={stats.documents_seen}, "
            f"documents_imported={stats.documents_imported}, "
            f"documents_skipped={stats.documents_skipped}, "
            f"chunks_{chunk_label}={stats.chunks_stored}, "
            f"pages_read={stats.pages_read}"
        )
    ]
    for index, report in enumerate(summary.categories, start=1):
        category = report.category
        category_id = category.category_id if category else "-"
        name = category.name if category else "未分类"
        ename = f" / {category.ename}" if category and category.ename else ""
        lines.append(
            f"[{index}/{summary.category_count}] category_id={category_id} {name}{ename}: "
            f"total={report.total_available}, "
            f"pages_read={report.stats.pages_read}, "
            f"seen={report.stats.documents_seen}, "
            f"imported={report.stats.documents_imported}, "
            f"skipped={report.stats.documents_skipped}, "
            f"chunks={report.stats.chunks_stored}"
        )
        for document in report.documents:
            reason = f" reason={document.reason}" if document.reason else ""
            lines.append(
                f"  - id={document.import_information_id} "
                f"status={document.status} "
                f"chunks={document.chunk_count} "
                f"title={document.title}{reason}"
            )
    return "\n".join(lines)


def ingest_company(args: argparse.Namespace) -> None:
    max_docs = None if args.all else args.max_docs
    company_client = CompanyPolicyClient(
        auth_cookie=_company_auth_cookie(args),
        base_url=_company_base_url(args),
        timeout=args.timeout,
    )
    embedding_client = EmbeddingClient(base_url=_embedding_url(args))
    store = PgVectorStore(_dsn(args))
    try:
        if args.all_categories:
            summary = ingest_company_categories(
                client=company_client,
                embedding_client=embedding_client,
                store=store,
                policy_type=args.policy_type,
                page_size=args.page_size,
                max_docs_per_category=max_docs,
                max_pages_per_category=args.max_pages,
                chunk_max_chars=args.chunk_max_chars,
                chunk_overlap_chars=args.chunk_overlap_chars,
                embedding_batch_size=args.embedding_batch_size,
                keyword=args.keyword,
                dry_run=args.dry_run,
            )
            print(render_company_category_summary(summary, dry_run=args.dry_run))
            return

        stats = ingest_company_policies(
            client=company_client,
            embedding_client=embedding_client,
            store=store,
            policy_type=args.policy_type,
            category_id=args.category_id,
            page_size=args.page_size,
            max_docs=max_docs,
            max_pages=args.max_pages,
            chunk_max_chars=args.chunk_max_chars,
            chunk_overlap_chars=args.chunk_overlap_chars,
            embedding_batch_size=args.embedding_batch_size,
            keyword=args.keyword,
            dry_run=args.dry_run,
        )
    finally:
        company_client.close()

    action = "Prepared" if args.dry_run else "Ingested"
    print(
        f"{action} Company policies: "
        f"documents_seen={stats.documents_seen}, "
        f"documents_imported={stats.documents_imported}, "
        f"documents_skipped={stats.documents_skipped}, "
        f"chunks={'prepared' if args.dry_run else 'stored'}={stats.chunks_stored}, "
        f"pages_read={stats.pages_read}"
    )


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

    company_parser = subparsers.add_parser("ingest-company-policies", help="Fetch Company policy details, chunk, embed, and store them")
    company_parser.add_argument("--auth-cookie", help="Company authentication cookie header value. Prefer COMPANY_AUTH_COOKIE env var.")
    company_parser.add_argument("--base-url", help=f"Policy system base URL. Default: COMPANY_POLICY_BASE_URL or {DEFAULT_COMPANY_BASE_URL}")
    company_parser.add_argument("--policy-type", type=int, default=DEFAULT_POLICY_TYPE)
    company_parser.add_argument("--category-id", type=int)
    company_parser.add_argument("--keyword", default="")
    company_parser.add_argument("--page-size", type=int, default=20)
    company_parser.add_argument("--max-docs", type=int, default=2, help="Safety default: only import 2 docs unless --all is set")
    company_parser.add_argument("--max-pages", type=int)
    company_parser.add_argument("--all", action="store_true", help="Import all matching policies instead of the safety-limited --max-docs")
    company_parser.add_argument("--all-categories", action="store_true", help="Read policySystemTypeList and import each category with a category-level report")
    company_parser.add_argument("--chunk-max-chars", type=int, default=1200)
    company_parser.add_argument("--chunk-overlap-chars", type=int, default=150)
    company_parser.add_argument("--embedding-batch-size", type=int, default=16)
    company_parser.add_argument("--timeout", type=float, default=30.0)
    company_parser.add_argument("--dry-run", action="store_true", help="Fetch and chunk, but do not call embedding or write pgvector")
    company_parser.set_defaults(func=ingest_company)

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
