# Knowledge Base RAG Generalization Design

## 背景

当前系统已经能通过几个典型问题暴露并修复 RAG 链路问题，例如年假、旷工、语言不得体、师德师风等。但这些问题不能继续用“一问一补”的方式扩展。项目目标是一整个知识库的通用问答、学习和调试平台，因此需要把坏例沉淀为通用能力：问题理解、证据建模、规则解析、答案计划、质量评测和可视化 trace。

本设计把当前修复视为回归样本，而不是最终业务规则。后续开发必须围绕“任意制度类知识库问题都能走同一套机制”展开。

## 目标

1. 把散落在 `trace_pipeline.py` 中的业务判断迁移为可复用模块。
2. 用统一 schema 描述用户问题、知识块、证据类型、答案计划。
3. 让规则型查询从“硬编码问题”升级为“用户事实 -> 制度条件 -> 结论条款”。
4. 让回答阶段按问题面生成结构化答案，而不是直接贴 chunk。
5. 建立分类级回归评测集，防止修一个问题坏一类问题。
6. 在 trace 中展示真实数据流转：每个节点入参、出参、判断原因、失败兜底。

## 非目标

1. 本阶段不引入大型外部 LLM 作为强依赖。
2. 本阶段不一次性完成所有制度的自动知识抽取。
3. 本阶段不替换现有 pgvector / 内存样例检索链路。
4. 本阶段不把真实业务数据提交到公开仓库。

## 核心问题

### 1. 单点规则不可持续

坏例修复中加入了年假、旷工、语言不得体等规则。如果继续这样做，规则会越来越散，换一个分类或换一个业务数据源就会失效。

解决方向：把规则拆成可配置的 `PolicyRule`、`BehaviorPattern`、`GlossaryTerm`，由 resolver 使用统一接口消费。

### 2. 问题理解不够统一

系统需要统一识别：

- `target_object`：用户问的对象，例如年假、旷工、报销、数据安全。
- `asked_aspect`：问题面，例如定义、处罚、流程、条件、例外、额度。
- `condition_parameters`：数值和条件，例如 2 天、3 次、5 年、金额、岗位。
- `audience`：适用对象，例如员工、教师、学生、访客。
- `confidence`：当前理解是否足够支撑直接回答。

### 3. 证据需要类型化

不是所有 chunk 都能回答问题。候选证据至少需要分为：

- `definition_evidence`：能回答“是什么”。
- `condition_evidence`：能回答“什么条件下”。
- `action_evidence`：能回答“怎么处理 / 处罚是什么”。
- `process_evidence`：能回答“流程怎么走”。
- `table_evidence`：能回答“额度 / 天数 / 对照表”。
- `classification_evidence`：能回答“属于什么类别”。
- `cross_reference_evidence`：只提供二跳线索，不能直接作为最终答案。
- `insufficient_evidence`：和问题相关但不足以回答。

### 4. 答案需要先有计划

回答阶段应该先生成 `AnswerPlan`，再生成自然语言答案。比如处罚类问题需要：事实复述、规则匹配、违规等级、处理结果、依据、不确定性；流程类问题需要：步骤、责任人、材料、时限、例外。

## 推荐架构

```text
User Query
  -> QueryNormalizer
  -> QueryUnderstandingEngine
  -> QueryRewriteEngine
  -> RetrievalPlanner
  -> HybridRetriever
  -> RerankEngine
  -> EvidenceValidator
  -> RuleResolver
  -> AnswerPlanner
  -> AnswerComposer
  -> TraceRecorder
```

### QueryUnderstandingEngine

输入：原始问题、归一化问题、词库。

输出：`QueryIntentSchema`。

作用：把自然语言问题转换为系统能处理的结构化意图。

白话解释：它负责判断用户到底在问什么，不只是找关键词。

### Glossary / Ontology

输入：业务词配置、用户问题、制度文本。

输出：标准词、同义词、禁用词、扩展检索词。

作用：把口语词映射为制度正式表达。

白话解释：用户说“骂人”，制度里可能叫“语言不得体”，这个模块负责翻译。

### RetrievalPlanner

输入：`QueryIntentSchema`。

输出：检索计划，包括 dense、sparse、metadata filter、candidate limit、是否需要 rerank。

作用：不同问题用不同检索策略。精确条款查询不能只靠 embedding。

白话解释：它决定先去哪里找、怎么找、取多少候选。

### EvidenceValidator

输入：候选 chunk、问题意图。

输出：证据类型、是否可用于最终答案、保留/丢弃原因。

作用：防止“召回了相关片段但不能回答问题”的情况。

白话解释：它像审核员，判断这段材料到底能不能证明答案。

### RuleResolver

输入：用户事实、规则证据、条件证据。

输出：匹配的制度条件、比较过程、结论条款、缺失条件。

作用：处理“旷工两天”“工作五年”“报销超额”等规则型问题。

白话解释：它把用户说的事实放进制度条件里算一下，判断命中哪条规则。

### AnswerPlanner

输入：问题意图、证据集合、规则解析结果。

输出：`AnswerPlan`。

作用：决定答案应该包含哪些段落，以及哪些内容不能说。

白话解释：它不是直接写答案，而是先列一个回答提纲。

### TraceRecorder

输入：每个节点的输入、输出、耗时、状态、原因。

输出：前端可展示的流程节点。

作用：让学习者看到系统为什么这样处理。

白话解释：它负责把机器内部过程翻译成可学习、可回放的流程图。

## 数据结构草案

### QueryIntentSchema

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

### EvidenceAssessment

```python
@dataclass(frozen=True)
class EvidenceAssessment:
    chunk_id: str
    evidence_type: str
    usable_as_final: bool
    matched_terms: list[str]
    missing_terms: list[str]
    reason: str
```

### AnswerPlan

```python
@dataclass(frozen=True)
class AnswerPlan:
    answer_type: str
    sections: list[str]
    required_citations: list[str]
    uncertainty_notes: list[str]
    cannot_answer_reason: str | None
```

## 阶段计划

### Phase 1：先抽象当前能力

把当前坏例中已经证明有价值的逻辑抽出来，不扩大业务范围。

交付：

- `query_intent.py`
- `policy_glossary.py`
- `evidence_validator.py`
- `answer_planner.py`
- 当前坏例全部转为通用 schema 测试。

验收：

- 年假、旷工、语言不得体、师德师风继续通过。
- 代码中不再把大部分业务判断塞在 `trace_pipeline.py`。
- trace 能展示统一的入参、出参、判断原因。

### Phase 2：建立分类级评测集

从“几个问题”扩展到“每类制度都有基础问题”。

交付：

- `regression_cases.py` 扩充分类字段。
- 每个主要分类至少覆盖定义、流程、条件、处罚/结果、来源引用。
- evaluation 输出分类维度通过率。

验收：

- 修改检索或规则逻辑后，能知道哪个分类被影响。
- 坏例不再只靠人工聊天发现。

### Phase 3：增强导入时知识建模

导入阶段识别正文结构，而不是只生成普通 chunk。

交付：

- section / clause / table / action / exception 元数据。
- 表格类 chunk 保留表头和来源定位。
- 文档解析质量报告进入导入报告。

验收：

- 处罚类问题优先召回 action evidence。
- 表格类问题不会丢表头。
- 粗 chunk 中混入相邻章节的概率下降。

### Phase 4：生产化增强

接入真实业务需要的观测、权限、缓存、多知识库隔离。

交付：

- Langfuse/OpenTelemetry exporter 接口。
- knowledge_base_id / tenant_id 过滤。
- embedding / rerank cache。
- source ACL 校验。

验收：

- 多业务数据源互不串库。
- 每次错误回答可以通过 trace 回放。
- 缓存命中不影响来源和权限判断。

## 风险与边界

1. 规则抽取不能完全自动化，本阶段先支持可配置规则和半自动抽取。
2. 词库扩展可能带来误召回，需要配 forbidden terms 和评测集。
3. Evidence Validator 过严会导致“有答案但被过滤”，需要保留 drop reason。
4. AnswerPlan 不能把不确定问题说成确定结论。
5. 公开仓库中只能使用脱敏样例和 `example.com` 链接。

## 验收清单

- 查询不再依赖单个硬编码问题。
- 每个问题都有结构化 intent。
- 每个候选证据都有 evidence assessment。
- 每个答案都有 answer plan。
- 每个 trace 节点展示真实入参、出参、判断原因。
- 每个公开样例不包含真实机构、真实域名、会话、密码、内网 IP。
- 全量测试、前端静态检查、敏感词扫描通过。
