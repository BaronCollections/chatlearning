# Real RAG Trace V2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current MVP trace into a production-shaped RAG/Agent learning trace with 12 explicit nodes, detailed tool choices, term definitions, quality gates, rerank, query rewrite, and Langfuse-ready observability metadata.

**Architecture:** Keep the existing FastAPI endpoint and vanilla JS trace UI. Extend `trace_pipeline.py` with deterministic, testable production-shaped trace stages and adapters/fallbacks instead of hard-wiring external services that are not configured locally. Extend the frontend detail renderer so each node can teach terms, inputs, outputs, pitfalls, alternatives, and checks.

**Tech Stack:** Python 3.11, FastAPI, httpx embedding service, PostgreSQL + pgvector, deterministic local rerank fallback, Langfuse-ready trace metadata, vanilla JS/CSS tree UI, pytest.

---

## 12-Node Trace Spec

Each top-level step must include `key`, `title`, `summary`, `details`, `duration_ms`, `status`, `execution_mode`, and `children`. Details should use stable semantic keys so the frontend can render them generically.

### 1. `request_intake` - 请求进入与 Trace 创建

**Purpose:** Receive the user question, create a request/trace identity, and establish the business goal.

**Children:**
- `assign_request_id`: create a deterministic trace/request id for this request.
- `capture_raw_query`: preserve the exact raw user input for audit and debugging.
- `create_observation_trace`: create Langfuse-ready trace metadata.

**Terms:**
- `Trace`: one full user request lifecycle, from input to answer.
- `Span`: one timed operation inside a trace, such as rewrite or rerank.
- `Observation`: a Langfuse term for recorded work such as span, generation, retriever, embedding, evaluator, or guardrail.

**Pitfall:** Never overwrite the raw query; later rewrite stages must be auditable against it.

### 2. `input_guardrails` - 输入校验与业务边界

**Purpose:** Reject unusable input and flag questions outside the policy assistant boundary.

**Children:**
- `validate_shape`: check non-empty text, top_k range, and length limits.
- `detect_sensitive_scope`: detect privacy, salary, credentials, or personal data requests.
- `detect_policy_domain`: decide whether the question looks like a policy/RAG question.

**Terms:**
- `Guardrail`: a rule or model check that blocks or flags unsafe/out-of-scope behavior.
- `PII`: personally identifiable information, such as phone, ID number, private salary, or account credential.

**Pitfall:** A policy RAG assistant should not answer private individual data just because a document exists.

### 3. `normalize_text` - 文本规范化

**Purpose:** Make semantically identical user input stable for tokenization, embedding, cache keys, and trace display.

**Children:**
- `trim_whitespace`: remove leading/trailing whitespace.
- `collapse_whitespace`: collapse repeated spaces/tabs/newlines.
- `preserve_semantics_check`: confirm normalization did not rewrite business meaning.

**Terms:**
- `Normalization`: converting superficial formatting differences into a stable form.
- `Semantic drift`: an accidental change of meaning during rewrite or cleanup.

**Pitfall:** Do not perform aggressive synonym replacement here; that belongs in explicit query rewrite.

### 4. `query_understanding` - 查询理解

**Purpose:** Extract intent, target audience, policy category, time hints, and ambiguity signals before retrieval.

**Children:**
- `classify_intent`: classify whether the user asks for rule lookup, eligibility, process, exception, or comparison.
- `extract_entities`: detect audience, category, time range, and policy nouns.
- `detect_ambiguity`: flag missing scope such as school stage or employee/student target.

**Terms:**
- `Intent classification`: identifying what kind of task the user is asking for.
- `Entity extraction`: pulling structured business objects from text, such as HR policy or high school.
- `Ambiguity`: information missing from the question that may change the answer.

**Pitfall:** Query understanding should guide retrieval; it should not invent facts.

### 5. `query_rewrite` - Query 改写与扩展

**Purpose:** Convert conversational input into a retrieval-friendly query while retaining the original question.

**Children:**
- `build_standalone_query`: make the question self-contained.
- `expand_policy_terms`: add safe domain synonyms, such as 年假 -> 年休假.
- `semantic_drift_check`: compare original and rewritten query to avoid changing user intent.

**Terms:**
- `Query rewrite`: rewriting a user question into a form that retrieval systems can match more reliably.
- `Query expansion`: adding related terms to improve recall.
- `Recall`: how many relevant documents the retrieval stage is able to find.

**Pitfall:** Rewrite should improve search, not answer the question or change its scope.

### 6. `tokenize` - 分词与 Token 预算

**Purpose:** Show exactly how the retrieval query becomes model tokens and check token budget.

**Children:**
- `call_tokenizer`: call the embedding service tokenizer when available.
- `build_token_table`: render token/token_id rows.
- `check_token_budget`: detect truncation or overlong input.

**Terms:**
- `Token`: the model's input unit; it may be a character, word piece, punctuation, or special symbol.
- `Token id`: the numeric vocabulary id for a token.
- `Token budget`: the maximum tokens a model can accept for an input.

**Pitfall:** A UI token preview is only useful when it matches the embedding model's real tokenizer.

### 7. `query_embedding` - Query Embedding

**Purpose:** Convert the retrieval query into a dense vector used for semantic search.

**Children:**
- `call_embedding_service`: send query text to `/embed` with `input_type=query`.
- `inspect_embedding_shape`: validate vector dimension and numeric shape.
- `embedding_quality_note`: explain dense embedding strengths and limits.

**Terms:**
- `Embedding`: a numeric vector representing text meaning.
- `Dense vector`: a fixed-length vector where most dimensions contain values.
- `Cosine distance`: a similarity metric; smaller distance means closer meaning in pgvector search.

**Pitfall:** Embedding is not enough for exact names, dates, policy numbers, and negation-sensitive rules.

### 8. `retrieval_plan` - 检索计划生成

**Purpose:** Decide which retrieval channels and filters should run before touching storage.

**Children:**
- `choose_channels`: choose dense vector now, note BM25/hybrid as production options.
- `derive_metadata_filters`: derive category/audience/time filters from query understanding.
- `set_candidate_limits`: decide initial candidate count and final top_k.

**Terms:**
- `BM25`: a keyword ranking algorithm commonly used by search engines.
- `Hybrid search`: combining vector semantic search with keyword search.
- `Metadata filter`: filtering by structured fields such as category, date, audience, or source.

**Pitfall:** TopK should not be blindly fixed; recall and rerank need enough candidates.

### 9. `initial_retrieval` - 初召回

**Purpose:** Retrieve candidate chunks from pgvector or local fallback.

**Children:**
- `build_vector_query`: build pgvector cosine query.
- `pgvector_search`: execute database search when configured.
- `in_memory_fallback`: execute deterministic sample search when database is unavailable.
- `dedupe_candidates`: remove duplicate chunk ids before rerank.

**Terms:**
- `Chunk`: a searchable text block from a source document.
- `pgvector`: PostgreSQL extension for vector similarity search.
- `Fallback`: controlled backup path when the primary dependency is unavailable.

**Pitfall:** Fallback must be visible in trace; otherwise users may mistake demo retrieval for production retrieval.

### 10. `rerank` - Rerank 重排

**Purpose:** Reorder retrieved candidates by direct query-document relevance.

**Children:**
- `prepare_rerank_pairs`: build query + candidate text pairs.
- `score_candidates`: use local lexical fallback now; cross-encoder adapter later.
- `compare_before_after`: show rank movement and score deltas.

**Terms:**
- `Rerank`: re-scoring retrieved candidates to improve final ordering.
- `Cross-encoder`: a model that reads query and document together and outputs one relevance score.
- `Relevance score`: numeric estimate of whether a chunk answers the query.

**Pitfall:** Rerank improves precision but adds latency; rerank only a candidate set, never the whole corpus.

### 11. `evidence_quality` - 证据质量检查与上下文组装

**Purpose:** Verify that the evidence can support an answer and assemble model-ready context.

**Children:**
- `check_relevance_threshold`: warn if top evidence score is too weak.
- `check_source_metadata`: ensure title/source/category/page metadata exists.
- `check_conflict_and_freshness`: flag possible conflicts or missing effective date.
- `assemble_context`: build context blocks with citations and token budget.

**Terms:**
- `Faithfulness`: whether the answer is supported by retrieved evidence.
- `Citation`: metadata that lets a user trace a statement back to the source.
- `Freshness`: whether a policy is current enough for the question.

**Pitfall:** A generated answer without evidence quality checks can be fluent but wrong.

### 12. `answer_and_observe` - 回答生成、后校验与 Langfuse 观测

**Purpose:** Compose the response, verify support, and emit observability/evaluation metadata.

**Children:**
- `compose_grounded_answer`: answer only from evidence.
- `post_answer_faithfulness_check`: check that answer references retrieved evidence.
- `record_langfuse_observations`: list trace/span/generation/retriever/evaluator records that would be sent.
- `collect_feedback_hook`: expose where user feedback would become evaluation data.

**Terms:**
- `Grounded answer`: an answer based on retrieved evidence, not model memory.
- `Evaluation score`: a numeric or categorical judgment used to monitor output quality.
- `Dataset`: saved examples used for regression testing prompts, retrieval, and rerank behavior.

**Pitfall:** Observability is not an afterthought; it is how production RAG failures are debugged.

---

## File Structure

- Modify `src/enterprise_rag_mvp/trace_pipeline.py`: implement 12-node trace, deterministic query understanding/rewrite/rerank/evidence checks, and term definitions.
- Modify `src/enterprise_rag_mvp/web/app.js`: render term definitions, pitfalls, checks, before/after rerank rows, and status notes without hard-coding every node.
- Modify `src/enterprise_rag_mvp/web/app.css`: style term boxes and quality/check sections inside the existing right-side detail panel.
- Modify `tests/test_trace_pipeline.py`: assert the 12 top-level keys and key child branches.
- Modify `tests/test_trace_ui_static.py`: assert frontend support for term lists and no 3D regression.

---

## Task 1: Backend 12-Node Trace Pipeline

**Files:**
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
- Test: `tests/test_trace_pipeline.py`

- [ ] Step 1: Write failing tests for the exact 12 top-level step keys.
- [ ] Step 2: Write failing tests for query rewrite, rerank, evidence quality, and Langfuse-ready metadata.
- [ ] Step 3: Implement deterministic helper functions for understanding/rewrite/rerank/evidence checks.
- [ ] Step 4: Refactor `run_chat_trace` to emit the 12 top-level steps while keeping response fields `query`, `answer`, `retrieval_mode`, `results`, and `steps` stable.
- [ ] Step 5: Run `pytest tests/test_trace_pipeline.py -q` and then full tests.

## Task 2: Frontend Detail Renderer Enhancements

**Files:**
- Modify: `src/enterprise_rag_mvp/web/app.js`
- Modify: `src/enterprise_rag_mvp/web/app.css`
- Test: `tests/test_trace_ui_static.py`

- [ ] Step 1: Write failing static test markers for `renderTermList`, `term-list`, `quality-check-list`, and `rerank-comparison`.
- [ ] Step 2: Add generic renderers for term definitions, quality checks, pitfalls, and rerank comparison arrays.
- [ ] Step 3: Style the new sections compactly inside `.tree-detail-panel` without changing the tree layout.
- [ ] Step 4: Run JS syntax check and static UI tests.

## Task 3: Integration Verification

**Files:**
- Verify: all touched files

- [ ] Step 1: Run `node --check src/enterprise_rag_mvp/web/app.js`.
- [ ] Step 2: Run `.venv/bin/python -m pytest -q`.
- [ ] Step 3: Use browser smoke on `http://127.0.0.1:8010`, ask `员工年假规则是什么？`, and assert 12 tree nodes render with no overlap.
- [ ] Step 4: Confirm console has no errors and `/api/chat` still returns HTTP 200.
