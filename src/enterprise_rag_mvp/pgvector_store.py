import json
from collections.abc import Sequence

import psycopg
from psycopg.types.json import Jsonb

from enterprise_rag_mvp.models import PolicyChunk, SearchResult


def build_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _dedupe_terms(terms: list[str]) -> list[str]:
    deduped: list[str] = []
    for term in terms:
        term = term.strip()
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def _terms_from_filter_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _query_terms(query_text: str) -> list[str]:
    terms: list[str] = []
    for token in query_text.replace("？", " ").replace("?", " ").split():
        token = token.strip()
        if len(token) >= 2:
            terms.append(token)
    return _dedupe_terms(terms)


def _hybrid_term_groups(query_text: str, metadata_filters: dict | None) -> tuple[list[str], list[str], list[str]]:
    metadata_filters = metadata_filters or {}
    primary_terms: list[str] = []
    for key in ["target_terms", "target_clause", "target_subclause"]:
        primary_terms.extend(_terms_from_filter_value(metadata_filters.get(key)))
    secondary_terms = _terms_from_filter_value(metadata_filters.get("target_section"))
    query_terms = _query_terms(query_text)
    return _dedupe_terms(primary_terms), _dedupe_terms(secondary_terms), query_terms


def _hybrid_terms(query_text: str, metadata_filters: dict | None) -> list[str]:
    primary_terms, secondary_terms, query_terms = _hybrid_term_groups(query_text, metadata_filters)
    return _dedupe_terms([*primary_terms, *secondary_terms, *query_terms])


class PgVectorStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def apply_schema(self, schema_sql: str) -> None:
        with psycopg.connect(self._dsn) as conn:
            conn.execute(schema_sql)

    def upsert_chunks(self, chunks: list[PolicyChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        with psycopg.connect(self._dsn) as conn:
            for chunk, embedding in zip(chunks, embeddings):
                conn.execute(
                    """
                    INSERT INTO rag_chunks (
                      chunk_id, doc_id, block_id, chunk_text, heading_path, metadata, chunking_strategy
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      doc_id = EXCLUDED.doc_id,
                      block_id = EXCLUDED.block_id,
                      chunk_text = EXCLUDED.chunk_text,
                      heading_path = EXCLUDED.heading_path,
                      metadata = EXCLUDED.metadata,
                      chunking_strategy = EXCLUDED.chunking_strategy
                    """,
                    (
                        chunk.chunk_id,
                        chunk.doc_id,
                        chunk.block_id,
                        chunk.text,
                        chunk.heading_path,
                        Jsonb(chunk.metadata),
                        "manual-mvp-v1",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO rag_chunk_embeddings_bge_m3 (chunk_id, embedding, embedding_version)
                    VALUES (%s, %s::vector, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      embedding = EXCLUDED.embedding,
                      embedding_version = EXCLUDED.embedding_version,
                      created_at = now()
                    """,
                    (chunk.chunk_id, build_vector_literal(embedding), "mvp-local-bge-m3"),
                )

    def hybrid_search(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        top_k: int,
        metadata_filters: dict | None = None,
    ) -> list[SearchResult]:
        primary_terms, secondary_terms, query_terms = _hybrid_term_groups(query_text, metadata_filters)
        terms = _dedupe_terms([*primary_terms, *secondary_terms, *query_terms])
        if not terms:
            return self.search(query_embedding, top_k=top_k)

        patterns = [f"%{term}%" for term in terms]
        primary_patterns = [f"%{term}%" for term in primary_terms]
        secondary_patterns = [f"%{term}%" for term in secondary_terms]
        query_patterns = [f"%{term}%" for term in query_terms]
        vector = build_vector_literal(query_embedding)
        keyword_limit = max(top_k * 4, top_k)
        dense_limit = max(top_k * 2, top_k)
        with psycopg.connect(self._dsn) as conn:
            rows = conn.execute(
                """
                WITH dense AS (
                  SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.block_id,
                    c.chunk_text,
                    c.heading_path,
                    c.metadata::text,
                    e.embedding <=> %s::vector AS distance,
                    0.0 AS keyword_score
                  FROM rag_chunk_embeddings_bge_m3 e
                  JOIN rag_chunks c ON c.chunk_id = e.chunk_id
                  ORDER BY e.embedding <=> %s::vector
                  LIMIT %s
                ),
                keyword AS (
                  SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.block_id,
                    c.chunk_text,
                    c.heading_path,
                    c.metadata::text,
                    e.embedding <=> %s::vector AS distance,
                    (
                      CASE WHEN c.chunk_text ILIKE ANY(%s::text[]) THEN 8.0 ELSE 0.0 END +
                      CASE WHEN array_to_string(c.heading_path, ' ') ILIKE ANY(%s::text[]) THEN 5.0 ELSE 0.0 END +
                      CASE WHEN c.metadata::text ILIKE ANY(%s::text[]) THEN 3.0 ELSE 0.0 END +
                      CASE WHEN c.chunk_text ILIKE ANY(%s::text[]) THEN 2.0 ELSE 0.0 END +
                      CASE WHEN array_to_string(c.heading_path, ' ') ILIKE ANY(%s::text[]) THEN 2.0 ELSE 0.0 END +
                      CASE WHEN c.metadata::text ILIKE ANY(%s::text[]) THEN 1.5 ELSE 0.0 END +
                      CASE WHEN c.chunk_text ILIKE ANY(%s::text[]) THEN 1.0 ELSE 0.0 END
                    ) AS keyword_score
                  FROM rag_chunk_embeddings_bge_m3 e
                  JOIN rag_chunks c ON c.chunk_id = e.chunk_id
                  WHERE c.chunk_text ILIKE ANY(%s::text[])
                     OR array_to_string(c.heading_path, ' ') ILIKE ANY(%s::text[])
                     OR c.metadata::text ILIKE ANY(%s::text[])
                  ORDER BY keyword_score DESC, e.embedding <=> %s::vector
                  LIMIT %s
                ),
                unioned AS (
                  SELECT * FROM dense
                  UNION ALL
                  SELECT * FROM keyword
                ),
                deduped AS (
                  SELECT DISTINCT ON (chunk_id) *
                  FROM unioned
                  ORDER BY chunk_id, keyword_score DESC, distance ASC
                )
                SELECT chunk_id, doc_id, block_id, chunk_text, heading_path, metadata, distance, keyword_score
                FROM deduped
                ORDER BY keyword_score DESC, distance ASC
                LIMIT %s
                """,
                (
                    vector,
                    vector,
                    dense_limit,
                    vector,
                    primary_patterns,
                    primary_patterns,
                    primary_patterns,
                    secondary_patterns,
                    secondary_patterns,
                    secondary_patterns,
                    query_patterns,
                    patterns,
                    patterns,
                    patterns,
                    vector,
                    keyword_limit,
                    top_k,
                ),
            ).fetchall()

        results: list[SearchResult] = []
        for row in rows:
            metadata = json.loads(row[5] or "{}")
            metadata["hybrid_keyword_score"] = float(row[7] or 0.0)
            chunk = PolicyChunk(
                chunk_id=row[0],
                doc_id=row[1],
                block_id=row[2],
                text=row[3],
                heading_path=list(row[4] or []),
                metadata=metadata,
            )
            results.append(SearchResult(chunk=chunk, distance=float(row[6])))
        return results


    def search(self, query_embedding: list[float], *, top_k: int) -> list[SearchResult]:
        with psycopg.connect(self._dsn) as conn:
            rows = conn.execute(
                """
                SELECT
                  c.chunk_id,
                  c.doc_id,
                  c.block_id,
                  c.chunk_text,
                  c.heading_path,
                  c.metadata::text,
                  e.embedding <=> %s::vector AS distance
                FROM rag_chunk_embeddings_bge_m3 e
                JOIN rag_chunks c ON c.chunk_id = e.chunk_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                (build_vector_literal(query_embedding), build_vector_literal(query_embedding), top_k),
            ).fetchall()

        results: list[SearchResult] = []
        for row in rows:
            chunk = PolicyChunk(
                chunk_id=row[0],
                doc_id=row[1],
                block_id=row[2],
                text=row[3],
                heading_path=list(row[4] or []),
                metadata=json.loads(row[5] or "{}"),
            )
            results.append(SearchResult(chunk=chunk, distance=float(row[6])))
        return results
