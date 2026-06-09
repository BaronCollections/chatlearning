import json
from collections.abc import Sequence

import psycopg
from psycopg.types.json import Jsonb

from enterprise_rag_mvp.models import PolicyChunk, SearchResult


def build_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


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
