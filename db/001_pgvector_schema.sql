CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  block_id TEXT,
  chunk_text TEXT NOT NULL,
  heading_path TEXT[],
  metadata JSONB DEFAULT '{}'::jsonb,
  chunking_strategy TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_chunk_embeddings_bge_m3 (
  chunk_id TEXT PRIMARY KEY REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE,
  embedding vector(1024) NOT NULL,
  embedding_model TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
  embedding_dimension INT NOT NULL DEFAULT 1024,
  embedding_version TEXT,
  normalized BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_bge_m3_embedding_hnsw_idx
ON rag_chunk_embeddings_bge_m3
USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS rag_chunk_embeddings_qwen3_06b (
  chunk_id TEXT PRIMARY KEY REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE,
  embedding vector(1024) NOT NULL,
  embedding_model TEXT NOT NULL DEFAULT 'Qwen/Qwen3-Embedding-0.6B',
  embedding_dimension INT NOT NULL DEFAULT 1024,
  embedding_version TEXT,
  normalized BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_qwen3_06b_embedding_hnsw_idx
ON rag_chunk_embeddings_qwen3_06b
USING hnsw (embedding vector_cosine_ops);
