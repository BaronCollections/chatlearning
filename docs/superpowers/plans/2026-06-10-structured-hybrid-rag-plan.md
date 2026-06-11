# Structured Hybrid RAG Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make enterprise policy Q&A precise for exact policy clauses such as “二类违规” and “4. 弄虚作假行为”.

**Architecture:** Add structure-aware Company chunking first, then hybrid retrieval signals and scoped answer assembly. Keep existing pgvector dense search but add optional hybrid search hooks, deterministic rerank constraints, span extraction, scope guard, and citation dedupe in the trace pipeline.

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL/pgvector, deterministic tests, vanilla JS trace UI.

---

### Task 1: Structure-Aware Policy Chunking

**Files:**
- Modify: `src/enterprise_rag_mvp/company_importer.py`
- Test: `tests/test_company_importer.py`

- [ ] Add failing tests for section/chapter parsing: `二类违规行为` and `4. 弄虚作假行为` should become separate clause group chunks.
- [ ] Implement numbered heading detection for Chinese section headings `（一）` and clause group headings `4.` with children `4.1`-`4.4`.
- [ ] Add metadata: `chunk_type`, `section_title`, `clause_title`, `clause_no`, `section_path`, `source_url`, `start_marker`, `end_marker`.
- [ ] Keep fallback fixed-window chunking for documents without recognizable structure.

### Task 2: Hybrid Retrieval Hook

**Files:**
- Modify: `src/enterprise_rag_mvp/pgvector_store.py`
- Modify: `db/001_pgvector_schema.sql`
- Test: `tests/test_mvp.py` or `tests/test_trace_pipeline.py`

- [ ] Add optional `hybrid_search(query_text, query_embedding, top_k, metadata_filters)` store method.
- [ ] Preserve `search()` compatibility.
- [ ] Use SQL that combines dense distance with exact/title/metadata/text keyword signals when available.
- [ ] Add schema indexes for metadata and text search/trigram where safe.

### Task 3: Query Understanding and Retrieval Plan

**Files:**
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
- Test: `tests/test_trace_pipeline.py`

- [ ] Detect exact policy lookups: `二类违规`, `三类违规`, `一类违规`, `弄虚作假行为`, `4.1`.
- [ ] Record `target_terms`, `target_section`, `target_clause`, `exclude_sections`, and `retrieval_intent`.
- [ ] Enable channels `exact_match`, `sparse_keyword`, `dense_vector` for exact policy lookups.

### Task 4: Constraint-Aware Rerank and Scoped Context

**Files:**
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
- Test: `tests/test_trace_pipeline.py`

- [ ] Add rerank bonuses for exact `section_path` / `clause_title` matches.
- [ ] Add penalties for competing sections such as `三类违规` when asking `二类违规`.
- [ ] Add span extraction from `start_marker` to `end_marker` or metadata-scoped chunk text.
- [ ] Add scope guard to catch leaked competing sections in the answer.

### Task 5: Citation Merge and UI Learning Nodes

**Files:**
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
- Modify: `src/enterprise_rag_mvp/web/app.js`
- Modify: `src/enterprise_rag_mvp/web/app.css`
- Test: `tests/test_trace_pipeline.py`
- Test: `tests/test_trace_ui_static.py`

- [ ] Deduplicate citations by doc + section + clause.
- [ ] Expose trace details for hybrid search, section boundary detection, span extraction, scope guard, and citation merge.
- [ ] Update static UI checks so these learning nodes are visible.

### Task 6: Docs, Verification, and Reindex

**Files:**
- Modify: `README.md`

- [ ] Document structure-aware chunks and hybrid search.
- [ ] Run all tests, JS check, sensitive scan.
- [ ] If valid credentials and embedding service are available, dry-run one policy detail, then reingest selected policy 16, then full category/all policies.
