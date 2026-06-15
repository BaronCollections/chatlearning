# Knowledge Base RAG Generalization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current example-driven policy Q&A fixes into reusable knowledge-base-level RAG capabilities.

**Architecture:** Introduce focused modules for query intent, glossary expansion, evidence validation, rule resolution, and answer planning. Keep `trace_pipeline.py` as orchestration only, while preserving current pgvector and in-memory demo paths.

**Tech Stack:** Python 3.11, FastAPI, pytest, pgvector-compatible search, deterministic local embedding fallback, vanilla JS trace UI.

---

## File Structure

- Create: `src/enterprise_rag_mvp/query_intent.py`
  - Owns `QueryIntentSchema`, aspect constants, condition extraction helpers.
- Create: `src/enterprise_rag_mvp/policy_glossary.py`
  - Owns business term mapping, synonym expansion, forbidden term groups.
- Create: `src/enterprise_rag_mvp/evidence_validator.py`
  - Owns `EvidenceAssessment`, evidence type classification, final evidence eligibility.
- Create: `src/enterprise_rag_mvp/answer_planner.py`
  - Owns `AnswerPlan`, answer type selection, required section planning.
- Modify: `src/enterprise_rag_mvp/policy_rule_resolver.py`
  - Keep rule matching here; consume `QueryIntentSchema` instead of duplicating query parsing.
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
  - Reduce responsibility to orchestration, trace node assembly, final call order.
- Modify: `src/enterprise_rag_mvp/regression_cases.py`
  - Add category, expected evidence type, expected answer type, forbidden keywords.
- Modify: `tests/test_trace_pipeline.py`
  - Preserve existing bad cases as regression tests.
- Create: `tests/test_query_intent.py`
  - Unit tests for query understanding.
- Create: `tests/test_policy_glossary.py`
  - Unit tests for synonym expansion.
- Create: `tests/test_evidence_validator.py`
  - Unit tests for evidence classification and drop reasons.
- Create: `tests/test_answer_planner.py`
  - Unit tests for answer plan selection.

## Chunk 1: Query Intent Schema

### Task 1: Add typed query intent

**Files:**
- Create: `src/enterprise_rag_mvp/query_intent.py`
- Test: `tests/test_query_intent.py`

- [ ] **Step 1: Write failing tests**

Cover:

```python
def test_extracts_policy_action_question_with_duration():
    intent = understand_query("我旷工两天会有什么处罚")
    assert intent.target_object == "旷工"
    assert intent.asked_aspect == "disciplinary_action"
    assert intent.condition_parameters["duration"] == 2
    assert intent.condition_parameters["unit"] == "day"
    assert "action_evidence" in intent.required_evidence_types
```

```python
def test_extracts_definition_question():
    intent = understand_query("二类违规是什么")
    assert intent.target_object == "二类违规行为"
    assert intent.asked_aspect == "definition"
    assert "definition_evidence" in intent.required_evidence_types
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_query_intent.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement minimal schema and parser**

Add dataclass:

```python
@dataclass(frozen=True)
class QueryIntentSchema:
    normalized_query: str
    target_object: str | None
    target_object_type: str | None
    asked_aspect: str | None
    condition_parameters: dict[str, Any]
    audience: str | None
    glossary_expansions: list[str]
    required_evidence_types: list[str]
    missing_conditions: list[str]
    confidence: float
    notes: list[str]
```

- [ ] **Step 4: Verify tests pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_query_intent.py -q
```

Expected: PASS.

## Chunk 2: Policy Glossary

### Task 2: Move synonym expansion into glossary module

**Files:**
- Create: `src/enterprise_rag_mvp/policy_glossary.py`
- Modify: `src/enterprise_rag_mvp/policy_rule_resolver.py`
- Test: `tests/test_policy_glossary.py`

- [ ] **Step 1: Write failing tests**

Cover:

```python
def test_expands_colloquial_language_to_policy_terms():
    expansion = expand_policy_terms("骂人有什么处罚")
    assert "语言不得体" in expansion.expanded_terms
    assert "投诉" in expansion.expanded_terms
    assert expansion.standard_terms["骂人"] == "语言不得体"
```

```python
def test_expands_leave_terms():
    expansion = expand_policy_terms("员工年假规则是什么")
    assert "年休假" in expansion.expanded_terms
    assert "带薪年假" in expansion.expanded_terms
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_policy_glossary.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement glossary config**

Use plain Python data structures first. Do not introduce YAML until there is a real operational need.

- [ ] **Step 4: Wire resolver to glossary**

`build_policy_lookup_spec()` should consume glossary output instead of owning all synonym expansion.

- [ ] **Step 5: Verify existing regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_policy_glossary.py tests/test_trace_pipeline.py -q
```

Expected: PASS.

## Chunk 3: Evidence Validator

### Task 3: Extract evidence classification from trace pipeline

**Files:**
- Create: `src/enterprise_rag_mvp/evidence_validator.py`
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
- Test: `tests/test_evidence_validator.py`

- [ ] **Step 1: Write failing tests**

Cover:

```python
def test_action_question_rejects_definition_only_evidence():
    assessment = assess_evidence(definition_chunk, action_intent)
    assert assessment.evidence_type == "insufficient_evidence"
    assert not assessment.usable_as_final
```

```python
def test_action_question_accepts_action_evidence():
    assessment = assess_evidence(action_chunk, action_intent)
    assert assessment.evidence_type == "action_evidence"
    assert assessment.usable_as_final
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_evidence_validator.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Move evidence logic**

Move or wrap current helpers:

- `_classify_evidence`
- `_filter_target_evidence`
- `_is_direct_target_evidence`
- `_is_reference_only_text`

Keep behavior identical first.

- [ ] **Step 4: Verify existing behavior remains stable**

Run:

```bash
.venv/bin/python -m pytest tests/test_evidence_validator.py tests/test_trace_pipeline.py tests/test_web_app.py -q
```

Expected: PASS.

## Chunk 4: Answer Planner

### Task 4: Add AnswerPlan before natural language answer

**Files:**
- Create: `src/enterprise_rag_mvp/answer_planner.py`
- Modify: `src/enterprise_rag_mvp/trace_pipeline.py`
- Test: `tests/test_answer_planner.py`

- [ ] **Step 1: Write failing tests**

Cover:

```python
def test_plans_disciplinary_action_answer():
    plan = plan_answer(action_intent, assessments, rule_resolution=rule)
    assert plan.answer_type == "disciplinary_action"
    assert plan.sections == ["fact", "rule_match", "classification", "action", "citations", "uncertainty"]
```

```python
def test_plans_conditional_answer_when_conditions_missing():
    plan = plan_answer(intent_with_missing_conditions, assessments)
    assert "conditions" in plan.sections
    assert plan.uncertainty_notes
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_answer_planner.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement AnswerPlan only**

Do not rewrite all answer strings yet. First expose plan in trace details.

- [ ] **Step 4: Verify trace contains answer plan**

Add assertion to `tests/test_trace_pipeline.py` that `answer_and_observe.details.answer_plan` exists.

Run:

```bash
.venv/bin/python -m pytest tests/test_answer_planner.py tests/test_trace_pipeline.py -q
```

Expected: PASS.

## Chunk 5: Regression Dataset Expansion

### Task 5: Upgrade regression cases from examples to category checks

**Files:**
- Modify: `src/enterprise_rag_mvp/regression_cases.py`
- Modify: `src/enterprise_rag_mvp/evaluation.py`
- Test: `tests/test_evaluation.py`

- [ ] **Step 1: Write failing tests**

Cover that each case can carry:

- `category`
- `expected_answer_type`
- `expected_evidence_types`
- `expected_keywords`
- `forbidden_keywords`
- `expected_source_urls`

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_evaluation.py -q
```

Expected: FAIL for missing fields or unsupported assertions.

- [ ] **Step 3: Implement schema expansion**

Keep backward compatibility for existing cases.

- [ ] **Step 4: Add representative cases**

Add cases for:

- 年假规则
- 年假年限查表
- 二类违规定义
- 二类违规处罚
- 旷工无天数
- 旷工两天
- 旷工三天
- 语言不得体条件性处罚
- 师德师风处罚

- [ ] **Step 5: Verify evaluation**

Run:

```bash
.venv/bin/python -m pytest tests/test_evaluation.py tests/test_trace_pipeline.py -q
```

Expected: PASS.

## Chunk 6: Final Integration and Safety

### Task 6: Full verification

**Files:**
- No new files unless failures require focused fixes.

- [ ] **Step 1: Run full Python tests**

```bash
.venv/bin/python -m pytest -q
```

Expected: all pass.

- [ ] **Step 2: Run frontend syntax checks**

```bash
node --check src/enterprise_rag_mvp/web/app.js
node --check src/enterprise_rag_mvp/web/admin.js
node --check src/enterprise_rag_mvp/web/docs.js
```

Expected: all exit 0.

- [ ] **Step 3: Run whitespace and public safety scans**

```bash
git diff --check
# Run the repository public-safety scan used before publishing.
# Keep the private denylist outside public documentation so the doc does not match itself.
```

Expected: `git diff --check` exits 0; the public-safety scan reports no matches.

- [ ] **Step 4: Manual smoke examples**

Run:

```bash
.venv/bin/python - <<'PY'
from enterprise_rag_mvp.trace_pipeline import run_chat_trace
from enterprise_rag_mvp.embedding_client import DeterministicEmbeddingClient
for query in [
    "员工年假规则是什么？",
    "工作五年有几天年假",
    "二类违规是什么",
    "二类违规的处罚是什么",
    "旷工会有什么处罚",
    "我旷工两天会有什么处罚",
    "旷工三天会怎样",
    "骂人有什么处罚",
    "没有师德会有什么处罚",
]:
    response = run_chat_trace(query, embedding_client=DeterministicEmbeddingClient(), store=None, top_k=5)
    print("\n===", query, "===")
    print(response["answer"])
PY
```

Expected: no “没有检索到足够相关内容” for covered examples; answers include citations and appropriate uncertainty.

- [ ] **Step 5: Commit exact files only after user approval**

Do not run `git add .`.
