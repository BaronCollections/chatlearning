# AI Workflow Atlas Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the right-side trace panel from a single linear RAG flow into a selectable AI workflow atlas with DAG-style serial, parallel, and merge visualization.

**Architecture:** Keep the FastAPI and RAG backend unchanged. Add frontend workflow definitions in `app.js`, render selected workflow definitions as a 2D DAG, and overlay live backend trace details onto matching RAG nodes after a chat response.

**Tech Stack:** FastAPI, vanilla JavaScript, CSS grid/flex, pytest static checks, Node syntax check.

---

## Chunk 1: Workflow Selector And DAG Renderer

### Task 1: Static Contract Tests

**Files:**
- Modify: `tests/test_trace_ui_static.py`

- [x] Add assertions that `index.html` contains `workflowSelect` and no longer shows the old subtitle text.
- [x] Add assertions that `app.js` contains `workflowDefinitions`, `buildRagWorkflow`, `renderWorkflowGraph`, `renderWorkflowNode`, `renderMergeRail`, and a `frameworkSelect` listener.
- [x] Add assertions that the static workflow list includes RAG, Embedding, LangChain, LangGraph, Query Rewrite + Rerank, Multi-Agent, enterprise ingest, and Langfuse.

### Task 2: Frontend Structure

**Files:**
- Modify: `src/enterprise_rag_mvp/web/index.html`
- Modify: `src/enterprise_rag_mvp/web/app.js`
- Modify: `src/enterprise_rag_mvp/web/app.css`

- [x] Add a workflow selector next to the `执行流程` heading.
- [x] Remove the old visible subtitle and mode badge business status wording from the header area.
- [x] Add workflow definitions for multiple AI frameworks.
- [x] Render a DAG with lanes, serial nodes, parallel groups, merge nodes, and clear elbow connector lines.
- [x] Keep detail panel collapsible behavior and make content more important than the title.
- [x] Overlay live backend trace details into the RAG workflow when a chat response arrives.

### Task 3: README And Release Hygiene

**Files:**
- Modify: `README.md`
- Create/Modify: `.gitignore`

- [x] Describe the project as an AI workflow/RAG trace learning workbench.
- [x] Document selector-driven workflows and the real RAG execution graph.
- [x] Document local run, pgvector, feeding data, and privacy boundaries.
- [x] Scan for local paths, cookies, sessions, secrets, and real data before publishing.
- [x] Run pytest and node syntax checks before pushing.
