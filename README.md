# ChatLearning: AI Workflow Trace Workbench

ChatLearning 是一个面向真实业务 RAG / Agent 系统的学习与调试工作台。它把一次 AI 问答拆成可观察、可点击、可解释的执行流程，让学生、业务方和工程师看到系统内部到底发生了什么。

当前版本包含一个 ChatGPT 风格的对话区，以及右侧的二维流程图画布。右侧不再只展示单条线性 RAG 流程，而是可以通过下拉框切换不同 AI 框架/范式的执行图谱：顺序节点、并行分支、汇聚节点和节点详情都会被明确展示。点击任意节点时，详情会从右侧以半屏抽屉展开，承载术语解释、工具选型、替代方案、常见坑、常见问题、问题解决建议和本次请求的入参/出参。这个项目的目标是做成 AI Agent/RAG 技术百科式学习工具，而不是简化演示。

## 它对你有什么帮助

- 学习 RAG：看到输入校验、query 改写、分词、embedding、召回、rerank、证据检查、答案观测这些步骤如何衔接；RAG 基础流程保留 12 个主阶段和 36+ 个细节点。
- 讲清工程细节：点击节点可以解释为什么用某个技术、有哪些替代方案、真实项目会踩什么坑。
- 面试和演示：不是只说概念，而是用可视化流程说明真实业务里的 RAG/Agent 设计。
- 调试检索问题：发送问题后，RAG 流程节点会叠加本次后端 trace，方便定位是改写、embedding、召回还是 rerank 出了问题。
- 扩展真实系统：项目保留 pgvector、embedding 服务、CLI ingest/search 和 Web API，可以逐步接入真实知识库。

## 当前内置流程

右侧“执行流程”下拉框内置这些流程：

- `RAG 基础流程`：展示真实 RAG 问答中的顺序、并行和汇聚关系。
- `Embedding 检索流程`：展开 query/document embedding、向量空间、ANN 检索和混合召回。
- `LangChain Agent`：展示 prompt、tool registry、retriever 和工具调用循环。
- `LangGraph 工作流`：展示 state、router、并行节点、reducer 和 checkpoint。
- `Query Rewrite + Rerank`：专门解释召回前改写、语义漂移检查和召回后重排。
- `多 Agent 协作`：展示 coordinator、retriever/reasoner/reviewer 并行协作和汇总。
- `企业知识库导入`：展示文档列表、正文清洗、附件解析、权限 metadata、chunk、embedding、upsert。
- `Langfuse 观测链路`：展示 trace/span/score/replay 如何帮助回放和评估 RAG/Agent 调用。
- `生产 RAG 成熟度`：把本轮 15 个生产化增强项以流程图展示，并用颜色区分已落地、接口已预留和待接入。


## 生产 RAG 成熟度 15 项

右侧流程图会用 `本轮优化` 标记本次加入的生产化能力，并用状态色表达真实落地程度：绿色是 `已落地`，蓝色是 `接口已预留`，琥珀色虚线是 `待接入`。这些状态不是营销标签，而是工程边界：没有接真实外部服务的能力不会被写成已上线。

| 能力 | 状态 | 解决的问题 | 当前落地边界 |
|---|---|---|---|
| 回归评测集与 Eval Runner | 已落地 | 防止修 A 坏 B，固定来源、关键词和禁止词验收 | 已有 `evaluation.py` 纯函数；CLI/CI 页面可继续接入 |
| 坏例采集与反馈闭环 | 已落地 | 把错来源、缺条款、答太泛沉淀为可回放坏例 | 已有 `/api/feedback` 与 JSONL 写入，只保存 citation 摘要 |
| 导入质量报告 | 接口已预留 | 说明处理了哪些分类、文档、chunk 和失败原因 | importer 已有统计对象，报告落盘和页面待接 |
| 适用对象与权限过滤 | 待接入 | 防止员工/学生/学段/权限范围混用 | 需要接真实登录态、组织权限和 metadata filter |
| 结构化答案契约 | 已落地 | 避免直接贴 chunk，输出事实、规则、结论、来源 | 规则型问题已结构化，后续可固定 JSON schema |
| 多跳规则解析器 | 已落地 | 用户事实先匹配制度条件，再跳到处理结果 | 已覆盖旷工、虚假报销、打听工资等核心样例 |
| Cross-encoder Reranker | 接口已预留 | 在候选内部重新排序，降低相似但不回答问题的证据 | 已有 HTTP client/env，实际模型服务需外接 |
| Query Router 查询路由 | 接口已预留 | 不同问题走精确条款、规则解析、语义检索或澄清 | query understanding 已输出关键字段，独立 router 待抽象 |
| 引用 Span 高亮 | 接口已预留 | 来源细化到章节、条款和最小证据范围 | 已有章节 metadata 和 span extraction，前端高亮待接 |
| Langfuse / OpenTelemetry 观测 | 接口已预留 | 通过 trace/span 回放问题发生在哪个边界 | 本地 trace 已有，外部观测 exporter 待接 |
| 增量同步与版本管理 | 待接入 | 防止旧制度残留、删除文档仍被检索 | 需要 source_updated_at、content_hash、deleted_at 策略 |
| PDF / Word / 表格 / 多模态解析 | 待接入 | 解析附件、表格、扫描件和图片里的制度内容 | 需要接专门 parser/OCR，并进入导入质量报告 |
| Prompt Injection 与数据泄露护栏 | 待接入 | 防止越权、泄露系统提示、恶意文档指令污染 | 需要入口、文档、工具、输出分层防护 |
| 缓存与成本控制 | 待接入 | 降低重复 embedding/rerank/LLM 调用成本和延迟 | 需要按权限、模型版本、数据版本设计 cache key |
| 外部知识 API 与工具检索 | 待接入 | 回答实时审批、个人额度、业务状态等非静态知识 | 需要白名单 tool registry、权限、超时和审计 |

点击任意增强节点时，抽屉会展示 `解决的问题`、`落地方式`、`验收方式`、`边界条件` 和术语解释。主 RAG 流程里的相关节点也会显示这些增强项，便于学习者理解它们不是孤立模块，而是挂在请求接入、检索计划、rerank、证据质量、答案观测和数据导入这些真实边界上。

## RAG 基础流程怎么表达并行

真实 RAG 不是简单的一条直线。当前 `RAG 基础流程` 会这样展示：

1. 请求接入
2. 输入护栏
3. 文本归一化
4. Query 理解
5. Query 改写
6. 分词与 token 检查
7. Query embedding
8. 检索计划
9. 初始召回
10. Rerank 重排序
11. 证据质量检查
12. 答案与观测

其中第 5-8 阶段在工程实现上可以并行准备：语义表示路径负责 query rewrite、tokenize、query embedding；业务约束路径负责 top_k、权限、分类、时间和 metadata filter。并行结果会在初始召回前汇聚成统一检索请求。

后端仍然保留更细的 trace 节点。前端会把这些 trace 叠加到对应流程节点上，并保留静态学习细节点，因此不会因为接入实时 trace 就丢失教学颗粒度。

## 多条制度来源是谁控制

例如用户问“员工年假规则是什么”，真实业务里可能同时命中年休假制度、假勤补充说明、审批流程和适用对象条款。这个不是前端随便拼出来的，控制点在后端：

1. 请求参数 `top_k` 控制最终返回多少条证据。
2. `PgVectorStore.search()` 负责普通语义问题的 pgvector 向量召回。
3. `PgVectorStore.hybrid_search()` 负责精确制度问题的混合召回，同时看向量相似度、关键词、标题路径和 metadata。
4. `trace_pipeline.py` 的 query understanding 判断问题是普通规则查询，还是“二类违规”“弄虚作假行为”这类精确条款查询。
5. `trace_pipeline.py` 的 scope-aware rerank 会给目标章节/条款加权，并对竞争章节降权，例如问“二类违规”时降低“三类违规”的得分。
6. `trace_pipeline.py` 的 citation 序列化负责把每条结果变成 `[1]`、`[2]` 这样的引用，并带上标题、分类、发布时间、chunk_id、source 和可点击链接。
7. 前端只渲染后端返回的 `results[].citation`，不会自己猜链接或伪造来源。

云谷制度来源会根据 `import_information_id` 生成 `https://work.yungu.org/policyDetail/{id}` 形式的详情链接；普通样例或文件来源如果没有真实 URL，就只展示 source/page/chunk metadata。这样可以同时满足学习展示、审计追溯和真实业务回答的可信度要求。

## 精确条款问答如何避免串段

这次重点修复的是“问二类违规，却把三类违规也答出来”这类真实业务问题。它不是单一 bug，而是从导入、检索、重排、上下文组装到引用展示的链路问题：

1. 结构化切块：`yungu_importer.py` 不再只按固定长度切文本，会优先识别制度里的同级标题和条款组。例如 `4. 弄虚作假行为` 会和 `4.1` 到 `4.4` 放在同一个 `clause_group` chunk 里，并在 metadata 中记录 `section_title`、`clause_no`、`clause_range`、`section_path`。
2. 精确意图识别：`trace_pipeline.py` 会识别 `二类违规`、`三类违规`、`弄虚作假行为`、`4.1` 这类查询，标记为 `exact_policy_lookup`。这类问题不能只靠 embedding 相似度。
3. 问题面识别：系统不只识别目标对象，还会识别用户问的是定义、处罚/处分、流程还是适用条件。例如 `二类违规是什么` 应命中定义段，`二类违规的处罚是什么` 会补充 `处分`、`违规处理`、`处分流程`、`最终处理决定` 等检索词，并标记 `asked_aspect=disciplinary_action`。
4. 规则型查询解析：`policy_rule_resolver.py` 把“用户事实 -> 制度条件 -> 结论条款”独立出来，不再把每个问法硬写在 `trace_pipeline.py`。例如 `我旷工两天会受到什么处罚` 会被解析为 `target_behavior=absenteeism`、`duration=2天`、`matched_rule=连续旷工3个工作日以下`、`expected_evidence=[扣除旷工期间工资, 记过处分]`。回答时会组合互补证据：`员工纪律制度` 说明它属于 `二类违规行为 / 破坏学校管理秩序行为 / 4.2旷工少于三天`，`工作时间及假期管理制度` 说明处理结果是扣除旷工期间工资并给予记过处分。
5. Hybrid Search：精确查询会启用 `exact_match + sparse_keyword + dense_vector`。字面命中保证条款名不丢，向量召回保证用户表达不完全一致时还能召回。
6. Scope-aware Rerank：重排阶段会把目标章节、目标条款、目标子条款、行为对象和问题面作为强特征；相邻但不属于目标的问题会被降权，不能回答问题面的候选也会降权。Rerank 是业务可选增强，但在制度问答里很推荐。
7. Span Extraction：如果历史数据里仍然存在粗 chunk，系统会在命中的 chunk 内二次截取目标范围。例如从 `（二）二类违规行为` 截到 `（三）三类违规行为` 之前，从 `1.2二类违规行为` 截到 `1.3三类违规行为` 前，或从 `连续旷工3个工作日以下` 截到下一条旷工阈值前。
8. Scope Guard：证据质量检查会记录是否成功收窄范围，并检查结果里是否混入竞争章节。这个检查用于调试和教学，也用于后续接入 LLM 前的安全闸。
9. Evidence Filter：精确制度查询会把候选分成 `direct_section_evidence`、`direct_behavior_evidence`、`cross_reference_evidence` 和不足证据。参见型片段不会直接进入答案，但可以作为二跳检索线索。
10. 两跳行为处罚：例如 `虚假报销怎么处罚` 会先用 `4.3虚假报销` 确认它属于 `二类违规行为 / 弄虚作假行为`，再跳到 `1.2二类违规行为` 的处理条款，最后结构化输出事实、规则匹配、处理结果、依据和不确定性。
11. Citation Merge：如果同一篇制度的多个相邻 chunk 都命中，展示层会按文档、章节和范围合并引用，避免重复来源刷屏。
12. 可追溯链接：云谷制度链接使用真实详情地址 `https://work.yungu.org/policyDetail/{importInformationId}`，不会生成未验证的前端路由。

是否每一步都必须做：结构化切块、来源 metadata、引用链接是制度问答的基础；Hybrid Search、Rerank、Scope Guard 属于真实业务强烈建议项；Langfuse 观测、离线评测、权限过滤、附件解析会随着生产化程度逐步补齐。

## 学习颗粒度

每个流程都按三层组织：

1. 主阶段：展示执行骨架，例如 RAG 的 12 个主阶段。
2. 细节点：每个主阶段内部展开 3 个以上微步骤，例如 tokenizer 调用、token id 展示、截断检查。
3. 百科详情：点击主节点或细节点后展示术语、输入输出、工具选型、替代方案、质量检查、常见坑、常见问题和问题解决建议。
4. 真实数据流：后端每个 trace 节点都会输出 `data_flow.input` 和 `data_flow.output`，前端以“入参 / 出参”展示本次请求在该节点真实消费和产出的字段。

这样设计的原因是：学习者需要先看到整体骨架，再逐层深入到真实工程细节；面试准备也需要能解释“为什么这么做”、“什么时候可以不做”和“不这么做会出什么问题”。

## 关键技术点

- RAG：Retrieval-Augmented Generation，先检索可信知识，再让模型基于证据回答。
- Query understanding：把问题拆成目标对象、问题面、条件参数和适用对象，例如目标对象是 `二类违规行为`，或行为条件是 `旷工两天`，问题面是 `处罚/处分`。
- Query rewrite：把用户口语化问题改写成更适合检索的问题，但必须检查语义漂移。
- Tokenize：把文本拆成模型可处理的 token，并展示 token id，方便理解模型实际输入。
- Embedding：把文本语义映射成向量，用于相似度检索。
- BGE-M3：当前示例推荐的 embedding 模型，适合中文、英文和中英混排，也适合本地部署。
- pgvector：PostgreSQL 的向量扩展，用熟悉的数据库系统承载向量检索。
- Hybrid Search：混合检索，把 dense vector 的语义相似度与关键词/精确匹配一起用，适合制度条款这类既要语义又要字面准确的场景。
- Rerank：对初始召回结果重新排序，减少“向量相似但业务不相关”的候选进入答案。默认使用可解释的确定性 fallback；配置 `RERANKER_SERVICE_URL` 后可接入 bge-reranker-v2-m3 等 cross-encoder 服务，形成“规则硬约束 + reranker 软排序”。
- Span Extraction：在命中的 chunk 内继续抽取目标段落，例如只截取 `4. 弄虚作假行为` 到下一个同级标题之前。
- Scope Guard：范围护栏，检查答案证据是否混入用户没有问的相邻章节，例如问“二类违规”时不能带出“三类违规”。
- Direct evidence：直接证据，指文本本身包含目标章节、定义、行为规则或条款正文；只写“参见某制度”的片段不算直接证据。
- Rule Resolver：规则解析器，把用户事实映射到制度条件和结论证据，例如把 `旷工两天` 映射到 `2 < 3` 和 `连续旷工3个工作日以下`。
- Regression dataset：回归评测集，保存标准问题、期望来源、必须命中的关键词和禁止出现的关键词，用于避免修 A 坏 B。
- Citation Merge：引用合并，把同一篇制度、同一章节的多个相邻 chunk 合并展示，避免 `[1]`、`[2]`、`[3]` 全是同一个来源。
- Langfuse：RAG/Agent 观测平台，可记录 trace、span、输入输出、耗时、评分和回放。

## 项目结构

```text
.
├── db/001_pgvector_schema.sql          # pgvector 表结构
├── src/enterprise_rag_mvp/
│   ├── cli.py                          # init-db / ingest-samples / search
│   ├── embedding_client.py             # embedding 服务客户端
│   ├── models.py                       # PolicyChunk / SearchResult 数据模型
│   ├── pgvector_store.py               # pgvector 写入与检索
│   ├── reranker_client.py              # 可选 cross-encoder reranker HTTP 客户端
│   ├── policy_rule_resolver.py         # 规则型查询解析：事实 -> 条件 -> 结论
│   ├── regression_cases.py             # 制度问答回归评测样本
│   ├── evaluation.py                    # 回归评测执行与结果汇总
│   ├── bad_cases.py                     # 坏例反馈记录，默认不保存完整正文
│   ├── samples.py                      # 可公开的样例制度 chunk
│   ├── yungu_importer.py               # 云谷制度分页、详情、HTML 清洗和结构化切块
│   ├── trace_pipeline.py               # 后端 RAG trace 主流程
│   ├── web_app.py                      # FastAPI Web 服务
│   └── web/                            # 原生 JS/CSS 前端
└── tests/                              # 后端与前端静态测试
```

## 回归评测集

`src/enterprise_rag_mvp/regression_cases.py` 保存了当前必须稳定的制度问答样本，包括：

- `二类违规是什么`：必须命中员工纪律制度里的二类违规定义，禁止带出三类违规正文。
- `二类违规的处罚是什么`：必须命中违规处理/处分流程，不能只返回二类违规定义。
- `我旷工两天会受到什么处罚`：必须同时返回工作时间及假期管理制度的处罚规则，以及员工纪律制度里的二类违规分类。
- `旷工三天会怎样`、`一年内旷工两次怎么处理`：必须命中辞退处分规则，不能误用“4.2旷工少于三天”。
- `虚假报销属于什么违规`、`虚假报销怎么处罚`、`打听工资属于什么违规`：必须能从具体行为跳到制度分类，并在处罚问题里继续跳到对应违规等级的处理条款。

这些样本不是为了展示，而是为了保护真实业务链路。每次改 query understanding、hybrid search、rerank、evidence filter、span extraction 或 answer template，都应该跑测试，确认来源、关键词和禁止词没有回归。

## 本地运行

要求：

- Python 3.11+
- 一个 embedding 服务，默认地址是 `http://127.0.0.1:8001`
- 可选：PostgreSQL + pgvector

安装依赖：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

没有 pgvector 时，可以先用内存样例模式启动页面：

```bash
RAG_DISABLE_PGVECTOR=true \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m uvicorn enterprise_rag_mvp.web_app:app --host 127.0.0.1 --port 8010
```

打开：

```text
http://127.0.0.1:8010
```

## 使用 pgvector

创建数据库：

```bash
createdb enterprise_rag_mvp
```

初始化表结构：

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
.venv/bin/python -m enterprise_rag_mvp.cli init-db
```

写入公开样例数据：

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-samples
```

命令行检索：

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli search '员工年假规则是什么？' --top-k 3
```

可选接入 reranker 服务时，服务需要支持：

```http
POST /rerank
Content-Type: application/json

{"query":"用户问题","documents":["候选片段1","候选片段2"]}
```

返回可以是 `{"scores":[0.1,0.9]}`，也可以是 `{"results":[{"index":1,"score":0.9},{"index":0,"score":0.1}]}`。如果服务超时、返回数量不一致或未配置，系统会降级到确定性 fallback，并在 rerank trace 里记录 `reranker_source` 和 `reranker_error`。

启动 Web 服务：

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m uvicorn enterprise_rag_mvp.web_app:app --host 0.0.0.0 --port 8010
```


Web 服务还提供坏例反馈接口，适合把用户点踩、错来源、缺条款等问题沉淀成后续回归样本：

```http
POST /api/feedback
Content-Type: application/json

{
  "query": "二类违规的处罚是什么",
  "feedback_type": "missing_clause",
  "answer": "只返回了定义，缺少处罚",
  "trace_id": "trace-id",
  "results": []
}
```

支持的 `feedback_type` 包括 `correct`、`wrong_source`、`missing_clause`、`irrelevant_answer`、`too_verbose`、`scope_leak`、`unsafe_or_sensitive`。接口只保存 citation 摘要，不保存完整 chunk 正文或原始 trace。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EMBEDDING_SERVICE_URL` | `http://127.0.0.1:8001` | embedding 服务地址 |
| `RAG_DATABASE_DSN` | `postgresql://127.0.0.1:5432/enterprise_rag_mvp` | PostgreSQL 连接串 |
| `RAG_DISABLE_PGVECTOR` | `false` | 设置为 `true` 时跳过 pgvector，使用内存样例模式 |
| `RERANKER_SERVICE_URL` | 空 | 可选 cross-encoder reranker 服务地址，接口为 `POST /rerank` |
| `RERANKER_PROVIDER` | `external_cross_encoder` | trace 中展示的 reranker 名称，例如 `bge-reranker-v2-m3` |
| `RAG_BAD_CASE_PATH` | `data/bad_cases.jsonl` | `/api/feedback` 写入的坏例 JSONL 路径；`data/` 默认不提交 |

不要把 `.env`、cookie、session、数据库密码或真实源文档提交到仓库；GitHub 发布只同步代码、公开样例、测试和说明文档。

## 怎么喂数据

公开仓库只包含少量手写样例 chunk，不包含真实企业制度数据。真实接入时建议写一个 importer，按下面流程处理：

1. 从业务系统分页拉取文档列表，只保存必要的文档 ID、标题、分类、发布时间和权限字段。
2. 逐篇拉取详情正文，不要把 cookie、session 或内部接口地址写死在代码里。
3. 清洗 HTML、PDF 或 Word 内容，保留标题层级、表格文本、附件信息和来源信息。
4. 按语义边界切 chunk，优先使用章节/条款/条款组；没有结构时才回退到最大 token 或固定窗口。
5. 为每个 chunk 写入 metadata，例如 `source`、`category`、`audience`、`publish_date`、`effective_date`、`permission_scope`、`section_title`、`clause_no`、`clause_range`、`source_url`。
6. 调用 embedding 服务把 chunk 文本转成 document embedding。
7. 调用 `PgVectorStore.upsert_chunks(chunks, embeddings)` 写入数据库。
8. 用真实问题回放 trace，检查 query understanding、Hybrid Search、rerank、Scope Guard、Citation Merge 和答案观测。

最小自定义导入示例：

```python
from enterprise_rag_mvp.embedding_client import EmbeddingClient
from enterprise_rag_mvp.models import PolicyChunk
from enterprise_rag_mvp.pgvector_store import PgVectorStore

chunks = [
    PolicyChunk(
        chunk_id="policy-001#chunk-001",
        doc_id="policy-001",
        block_id="section-1",
        text="这里放清洗后的制度正文片段。",
        heading_path=["人力制度", "年休假"],
        metadata={
            "source": "internal-policy-system",
            "category": "HR",
            "publish_date": "2026-01-01",
            "permission_scope": "employee",
        },
    )
]

embedding_client = EmbeddingClient(base_url="http://127.0.0.1:8001")
embeddings = embedding_client.embed([chunk.text for chunk in chunks], input_type="document")
PgVectorStore("postgresql://127.0.0.1:5432/enterprise_rag_mvp").upsert_chunks(chunks, embeddings)
```

生产导入还需要补齐：分页重试、限流、断点续跑、重复文档检测、删除同步、权限过滤、附件解析、数据脱敏、导入日志和失败告警。


## 直接接入云谷制度数据

仓库提供了 `ingest-yungu-policies` 命令，用于读取云谷制度列表、逐篇拉取详情正文、清洗 HTML、切 chunk、调用 embedding 服务，并写入 pgvector。

SESSION 不要写进代码或 README，建议只放在当前终端环境变量里：

```bash
export YUNGU_SESSION='只在本机终端设置，不要提交到仓库'
```

先做 dry-run，只拉取和切块，不调用 embedding、不写数据库：

```bash
YUNGU_SESSION="$YUNGU_SESSION" \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-yungu-policies \
  --dry-run \
  --max-docs 2 \
  --page-size 20
```

确认 dry-run 后再写入 pgvector。默认仍然只导入 2 篇，避免误全量：

```bash
YUNGU_SESSION="$YUNGU_SESSION" \
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-yungu-policies \
  --max-docs 2 \
  --page-size 20
```

如果要按所有分类分页处理，使用 `--all-categories`。不加 `--all` 时仍然是安全模式：每个分类最多处理 `--max-docs` 篇，适合先验证分类、分页和详情结构。

```bash
YUNGU_SESSION="$YUNGU_SESSION" \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-yungu-policies \
  --all-categories \
  --dry-run \
  --max-docs 2 \
  --page-size 20
```

确认 dry-run 报告后，再显式使用 `--all-categories --all` 做全分类导入：

```bash
YUNGU_SESSION="$YUNGU_SESSION" \
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-yungu-policies \
  --all-categories \
  --all \
  --page-size 20
```

如果只导入一个分类，可以继续使用 `--category-id`。如果明确要导入该分类全部文档，也必须显式使用 `--all`：

```bash
YUNGU_SESSION="$YUNGU_SESSION" \
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-yungu-policies \
  --category-id 11 \
  --all
```

按分类导入完成后，命令会输出分类级报告：分类数量、每个分类的接口 total、读取页数、处理文档数、导入/跳过数量、chunk 数，以及每篇制度的 `importInformationId`、标题、状态和 chunk 数。报告不会打印制度正文。

导入器会写入这些 metadata：`source`、`import_information_id`、`title`、`publish_date`、`policy_category_type`、`policy_category_type_name`、`policy_system_type`、`create_user_name`、`file_count`、`source_url`、`chunk_type`、`section_title`、`clause_title`、`clause_no`、`clause_range`、`section_path`。

真实检索结果的来源控制依赖这些 metadata。回答阶段会把 `import_information_id`、标题、分类和发布时间序列化为 citation；前端展示 citation 链接，但不负责决定哪条制度应该进入答案。

已有历史数据如果是在旧切块策略下导入的，建议重新执行导入，让数据库里产生新的 `section_overview` 和 `clause_group` chunk。即使暂时不重导，回答阶段的 Span Extraction 也会尽量从粗 chunk 中截取目标章节，但结构化重导的准确性更高。

## 隐私与发布边界

这个仓库只应该包含代码、公开样例、测试和说明文档。当前本地导入到 PostgreSQL 的真实制度数据、embedding 向量、运行时环境变量和 SESSION 都不属于 GitHub 发布内容。

不要提交：

- `.venv/`、缓存、日志和临时文件。
- `.env`、数据库密码、API key、cookie、session。
- 真实制度正文、附件、学生或员工信息。
- 本机绝对路径和个人目录信息。

如果要接入真实数据，建议把连接信息放到部署平台的环境变量里，把原始文档放到受控存储中，并只把脱敏后的样例数据用于公开演示。

## 测试

```bash
.venv/bin/python -m pytest -q
node --check src/enterprise_rag_mvp/web/app.js
```

## 当前边界

- 当前没有内置 PDF/Word 解析器，需要在 importer 中接入专门的解析组件。
- 当前没有真正调用 LLM 生成长答案，重点是 RAG 检索链路、流程图谱和 trace 学习展示。
- 当前 Langfuse 是生产观测建议，仓库内未强制依赖 Langfuse SDK。
- 内存样例模式只适合教学和联调，真实业务应使用 pgvector 或其它可持久化向量库。
