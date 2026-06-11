# Policy Clause Group Chunking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents are explicitly authorized) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-oriented policy document chunker that uses clause-group boundaries for enterprise policies, and make admin preview and importer use the same chunking path.

**Architecture:** Keep document parsing responsible for extracting `ParsedDocument`/`ParsedElement`, and add `document_chunking` as the boundary-aware transformation layer. Structured policy documents use clause-group chunks without sliding overlap; unstructured documents fall back to the existing fixed-window chunker with an explicit quality report.

**Tech Stack:** Python dataclasses, regex-based deterministic policy structure detection, existing FastAPI admin preview, existing company importer, pytest.

---

## Scope

This plan only covers policy/document chunking behavior and admin preview display. It does not add PDF/DOCX/OCR production parsers, tenant/auth, knowledge-base CRUD, or external Dify retrieval APIs.

## Files

- Create: `src/enterprise_rag_mvp/document_chunking/__init__.py`
- Create: `src/enterprise_rag_mvp/document_chunking/models.py`
- Create: `src/enterprise_rag_mvp/document_chunking/policy_chunker.py`
- Modify: `src/enterprise_rag_mvp/management.py`
- Modify: `src/enterprise_rag_mvp/company_importer.py`
- Modify: `src/enterprise_rag_mvp/web/admin.js`
- Test: `tests/test_document_chunking.py`
- Test: `tests/test_web_app.py`
- Test: `tests/test_company_importer.py`

## Chunk 1: Model And Chunker

- [ ] Write failing tests for clause-group chunks: no half-word starts, no cross-category leakage, violation level metadata, Chinese/English separation, disciplinary action chunks.
- [ ] Add `DocumentChunk` and `ChunkQualityReport` models.
- [ ] Implement deterministic policy chunker that reads parsed elements, detects headings, categories, clause groups, action clauses, language sections, and fallback conditions.
- [ ] Verify targeted chunking tests pass.

## Chunk 2: Admin Preview

- [ ] Write failing API test proving `/api/admin/document-preview` returns `chunking_quality` and structured chunk metadata for plain-text HTML policy content.
- [ ] Replace direct `chunk_text()` call in `management.py` with the shared policy chunker.
- [ ] Update `admin.js` to display chunk strategy, chunk type, language, heading path, clause range, and fallback reason.

## Chunk 3: Importer Consistency

- [ ] Write failing importer test proving `detail_to_policy_chunks()` emits the same structured chunk strategy and no longer relies on its narrow local `_structured_policy_blocks()` path for policy documents.
- [ ] Refactor `company_importer.py` to call the shared chunker for body chunks while keeping attachment fixed-window behavior.
- [ ] Preserve existing metadata fields expected by tests and pgvector storage.

## Chunk 4: Verification

- [ ] Run focused tests: `.venv/bin/python -m pytest tests/test_document_chunking.py tests/test_web_app.py tests/test_company_importer.py -q`.
- [ ] Run full tests: `.venv/bin/python -m pytest -q`.
- [ ] Run JS syntax check for admin UI: `node --check src/enterprise_rag_mvp/web/admin.js`.
