# ChatLearning Phase 2 RAG Service 方案

## 1. 目标定位

二期目标是把当前 ChatLearning 从“RAG Trace 学习与调试工作台”升级为组织内部可稳定使用的轻量多租户 RAG Service。

它不是重型 AI 平台，也不是只服务单一制度库的 demo。二期要支持不同业务资料各自建设资料库，并提供稳定导入、检索、管理、反馈、评测和 trace 回放能力。

推荐定位：

```text
可解释的轻量多租户 RAG Service
```

核心能力：

```text
多租户 / 多业务空间
+ 多知识库
+ 文档导入和解析质量报告
+ 标准检索 API
+ 可选 Dify 外部知识库协议
+ 管理后台
+ Trace 可视化
+ 坏例反馈和回归评测
```

使用规模预期是几十人级别，因此二期重点不是高并发大集群，而是：

```text
资料库隔离清楚
文档导入可追踪
解析质量看得见
检索来源可解释
权限不会串
数据更新后旧索引会失效
回答错误后能回放和修复
```

## 2. 设计原则

| 原则 | 说明 |
|---|---|
| 轻量优先 | 当前使用量不大，优先模块化单体，不直接上复杂微服务和重队列。 |
| 多租户强隔离 | 所有业务数据必须通过 `tenant_id`、`workspace_id`、`knowledge_base_id` 和权限范围过滤。 |
| 数据准确性优先 | 文档解析、chunk、embedding、检索、rerank、答案都必须可追踪。 |
| 标准接口优先 | 对内保留 trace chat，对外提供标准 retrieval API，后续可兼容 Dify。 |
| 可解释优先 | 保留当前项目优势：流程图、节点详情、证据过滤、来源引用、trace 回放。 |
| 先 pgvector，预留 Milvus | 当前规模 pgvector 足够；通过接口抽象预留 Milvus。 |
| 版本化失效 | 文档、chunk、embedding、parser、模型都要记录版本，不能只靠 TTL。 |
| 不把规划写成上线能力 | README、管理台、接口文档要区分已实现、待接入和可选扩展。 |

## 3. 总体架构

推荐二期保持模块化单体：

```text
FastAPI 应用
├── 管理后台
├── 检索 API
├── Dify-compatible Retrieval API，可选
├── 文档导入 API
├── 租户 / 权限模块
├── 文档解析模块
├── Chunking 模块
├── Embedding 模块
├── Vector Store 模块
├── Rerank 模块
├── Trace / Feedback / Eval 模块
└── 后台任务模块
```

基础设施建议：

```text
PostgreSQL
├── 业务表：tenant / workspace / knowledge_base / document / chunk / job / feedback / eval
└── pgvector：向量索引

外部服务，可选接入
├── 组织内 AI 网关 Embedding 服务
├── DashScope qwen3-rerank 或内部 rerank 网关
├── 文件转 Markdown 服务
├── OCR / Docling / Unstructured
└── Langfuse / OpenTelemetry
```

## 4. 推荐代码结构

后续可以逐步从当前扁平结构迁移到下面的结构。迁移不需要一次性完成，可以按模块逐步移动。

```text
src/enterprise_rag_mvp/
├── app.py / web_app.py
├── core/
│   ├── config.py
│   ├── auth.py
│   ├── database.py
│   ├── exceptions.py
│   └── deps.py
├── infrastructure/
│   ├── embedding.py
│   ├── rerank.py
│   ├── vector_store.py
│   ├── file_parser.py
│   ├── chunking.py
│   └── tracing.py
├── modules/
│   ├── tenant/
│   ├── workspace/
│   ├── knowledge_base/
│   ├── document/
│   ├── retrieval/
│   ├── feedback/
│   ├── evaluation/
│   └── admin/
├── web/
└── tests/
```

迁移目标不是为了目录好看，而是为了让职责清楚：

```text
core 管配置、鉴权、异常和数据库
infrastructure 管外部服务和技术适配
modules 管业务对象和业务流程
web 管前端静态页面
```

## 5. 核心数据模型

二期最重要的是数据模型。建议核心关系：

```text
tenant
  -> workspace
    -> knowledge_base
      -> document
        -> document_version
          -> chunk
```

### 5.1 tenant

表示租户或隔离边界。学校内部可以先把 tenant 理解为一个大的组织边界，后续如果有校区、学段、部门隔离要求，再扩展。

关键字段：

```text
id
name
status
created_at
updated_at
```

### 5.2 workspace

表示业务空间，例如 HR、财务、教学、招生、IT。

关键字段：

```text
id
tenant_id
name
description
status
created_at
updated_at
```

### 5.3 knowledge_base

表示一个可检索资料库。

关键字段：

```text
id
tenant_id
workspace_id
name
description
status
retrieval_config
embedding_provider
embedding_model
rerank_provider
created_at
updated_at
```

### 5.4 document

表示原始资料，例如 PDF、Word、网页制度、外部系统文章。

关键字段：

```text
id
tenant_id
workspace_id
knowledge_base_id
title
source_type
source_url
external_document_id
status
current_version_id
created_at
updated_at
```

### 5.5 document_version

表示文档版本，解决重新解析、重新切块、重新 embedding 和旧版本失效问题。

关键字段：

```text
id
document_id
version_no
content_hash
file_hash
parser_name
parser_version
chunk_strategy
chunk_strategy_version
embedding_provider
embedding_model
embedding_dimension
status
parse_quality_report
created_at
```

### 5.6 chunk

表示最终可检索片段。

关键字段：

```text
id
tenant_id
workspace_id
knowledge_base_id
document_id
document_version_id
chunk_index
chunk_type
text
text_hash
heading_path
page_number
bbox
source_url
permission_scope
metadata
embedding
embedding_model
embedding_version
created_at
```

### 5.7 ingestion_job

表示导入任务。

状态建议：

```text
pending
downloading
parsing
chunking
embedding
indexing
completed
partial
failed
```

关键字段：

```text
id
tenant_id
knowledge_base_id
document_id
status
step
progress
error_message
retry_count
started_at
finished_at
created_at
updated_at
```

### 5.8 retrieval_log

记录每次检索和 trace 回放所需信息。

关键字段：

```text
id
trace_id
tenant_id
workspace_id
knowledge_base_ids
user_id
query
query_understanding
rewrite_query
retrieval_mode
candidates
rerank_scores
filtered_candidates
citations
latency_ms
error
created_at
```

### 5.9 feedback

记录坏例反馈。

关键字段：

```text
id
trace_id
tenant_id
query
feedback_type
comment
citations
created_by
created_at
```

### 5.10 eval_case

记录回归评测样本。

关键字段：

```text
id
tenant_id
knowledge_base_id
query
expected_doc_ids
expected_keywords
forbidden_keywords
expected_url
status
created_at
updated_at
```

## 6. 多租户和权限策略

二期不建议每个租户独立数据库，也不建议每个知识库独立向量表。推荐：

```text
单 PostgreSQL
单 chunks 表
所有业务表带 tenant_id
所有检索强制 metadata filter
```

检索过滤必须在后端执行：

```text
WHERE tenant_id = 当前用户 tenant
AND knowledge_base_id IN 当前用户可访问知识库
AND document_status = active
AND permission_scope <= 当前用户权限
```

前端传入的 tenant/workspace/kb 只能作为请求意图，不能作为可信权限。后端必须根据登录态或 API Key 解析真实权限。

建议权限模型先保持简单：

```text
admin：管理租户、业务空间、知识库和文档
editor：维护指定知识库文档
viewer：检索指定知识库
service：外部系统 API Key 调用
```

## 7. 检索链路

二期检索链路：

```text
请求接入
-> API Key / 登录态鉴权
-> tenant/workspace/kb 权限解析
-> Query Understanding
-> Query Rewrite
-> Query Embedding
-> metadata filter
-> pgvector recall 或 hybrid recall
-> rule constraints
-> external rerank，可选
-> evidence filter
-> span extraction
-> citation merge
-> answer assembly 或 records serialization
-> trace log
```

### 7.1 `/api/chat`

面向当前页面和 trace 展示，返回结构化答案和步骤。

### 7.2 `/api/retrieval`

面向内部业务系统，只返回检索记录，不强制生成长答案。

### 7.3 `/retrieval`

可选 Dify-compatible 外部知识库协议。

建议请求体：

```json
{
  "knowledge_id": "知识库 ID",
  "query": "用户问题",
  "retrieval_setting": {
    "top_k": 5,
    "score_threshold": 0.5
  }
}
```

建议响应体：

```json
{
  "records": [
    {
      "content": "候选片段正文",
      "score": 0.92,
      "title": "资料标题",
      "metadata": {
        "document_id": "document-id",
        "chunk_id": "chunk-id",
        "description": "章节路径",
        "source_url": "https://example.com/source"
      }
    }
  ]
}
```

## 8. 导入链路

二期导入链路：

```text
创建导入任务
-> 获取文件或文章详情
-> 文件类型识别
-> 文档解析
-> 解析质量报告
-> chunking
-> embedding
-> vector upsert
-> 文档版本切换为 active
-> 旧版本失效
-> 导入报告
```

支持输入来源：

```text
业务系统文章 ID
file_url
手动上传文件
纯文本 / Markdown / HTML
```

导入必须异步化，即使当前使用量低，也不要让上传请求阻塞到解析和 embedding 完成。

推荐第一版任务执行方式：

```text
PostgreSQL ingestion_job 表
+ FastAPI BackgroundTasks
+ 单独 worker 进程
```

后续如果任务量变大，再升级 Celery / RQ / Dramatiq。

## 9. 文档解析方案

当前已经具备 P0 骨架：

```text
DocumentSource
DocumentParserRouter
ParsedDocument
ParsedElement
ParseQualityReport
HTML parser
text parser
PDF/DOCX/image unsupported report
```

二期建议继续扩展：

```text
PDF:
  PyMuPDF 预检
  Docling 主解析
  Unstructured hi_res fallback

DOCX:
  python-docx 简单解析
  Docling 复杂解析
  LibreOffice 转换兜底

图片 / 扫描件:
  PaddleOCR 或内部 OCR 服务
  记录 OCR confidence
  低置信度进入人工复核队列

Markdown:
  MarkdownHeaderTextSplitter
  RecursiveCharacterTextSplitter
```

解析质量报告必须记录：

```text
parser_name
parser_version
status
page_count
element_count
table_count
image_ocr_count
low_confidence_count
warnings
```

## 10. Chunking 方案

二期建议引入 `ChunkingRouter`：

```text
PolicyClauseChunker
MarkdownHeaderChunker
RecursiveTextChunker
TableAwareChunker
OCRTextChunker
```

路由规则：

```text
制度类文档：PolicyClauseChunker
Markdown 文档：MarkdownHeaderChunker + RecursiveTextChunker
表格元素：TableAwareChunker
OCR 元素：OCRTextChunker
兜底：RecursiveTextChunker
```

chunk metadata 必须包含：

```text
tenant_id
workspace_id
knowledge_base_id
document_id
document_version_id
heading_path
page_number
bbox
chunk_type
chunk_strategy_version
parser_name
parser_version
source_url
permission_scope
content_hash
```

## 11. Embedding 方案

二期建议从单一 `EmbeddingClient` 升级为：

```text
EmbeddingProviderRouter
```

支持：

```text
local demo
组织内 AI 网关
BGE-M3
DashScope / text-embedding
OpenAI-compatible embedding
```

所有 document embedding 必须记录：

```text
embedding_provider
embedding_model
embedding_dimension
embedding_config_version
```

不能混用不同维度和不同语义空间的 embedding。

## 12. Rerank 方案

推荐组合：

```text
规则硬约束
+ qwen3-rerank / bge-reranker 软排序
+ fallback deterministic rerank
```

规则负责不能错的边界：

```text
目标章节
问题面
权限范围
竞争章节降权
无效证据过滤
```

reranker 负责在候选内部提升排序质量。

trace 需要记录：

```text
reranker_provider
reranker_model
reranker_score
fallback_reason
reranker_error
```

## 13. Vector Store 方案

二期建议继续优先 pgvector：

```text
使用量小
部署简单
metadata filter 方便
业务表和向量一致性好
```

同时抽象接口：

```text
VectorStore
├── PgVectorStore
└── MilvusStore，后续可选
```

什么时候考虑 Milvus：

```text
文档量明显变大
高并发检索
平台统一要求
需要专门向量集群运维
```

## 14. 缓存策略

缓存分层设计：

| 缓存对象 | 建议策略 |
|---|---|
| 文件解析结果 | 长期缓存，靠 `file_hash + parser_version` 失效 |
| chunk 结果 | 长期缓存，靠 `content_hash + chunk_strategy_version` 失效 |
| document embedding | 长期缓存，靠 `chunk_hash + embedding_model_version` 失效 |
| query embedding | 10 分钟到 1 小时 |
| retrieval 结果 | 5 到 10 分钟 |
| rerank 结果 | 10 到 30 分钟 |
| final answer | 默认不缓存；如缓存，TTL 5 到 15 分钟且必须权限隔离 |
| 权限信息 | 1 到 5 分钟或事件驱动失效 |

缓存 key 必须包含：

```text
tenant_id
knowledge_base_id
permission_hash
knowledge_base_version
query_hash
filter_hash
embedding_model
rerank_model
prompt_version
```

## 15. 管理后台

二期管理后台建议覆盖：

```text
租户 / 业务空间
知识库管理
文档管理
导入任务状态
解析预览
chunk 预览
检索调试
回归评测
坏例反馈
系统集成状态
```

第一版重点不是复杂报表，而是让管理员能回答这些问题：

```text
这个知识库有哪些文档？
这个文档解析成功了吗？
切了多少 chunk？
embedding 成功了吗？
为什么这个问题没检索到？
用户反馈的问题能不能转成评测样本？
```

## 16. API 规划

### 16.1 管理 API

```http
POST /api/tenants
GET  /api/tenants

POST /api/workspaces
GET  /api/workspaces

POST /api/knowledge-bases
GET  /api/knowledge-bases
GET  /api/knowledge-bases/{kb_id}
PUT  /api/knowledge-bases/{kb_id}
DELETE /api/knowledge-bases/{kb_id}
```

### 16.2 文档 API

```http
POST /api/knowledge-bases/{kb_id}/documents
GET  /api/knowledge-bases/{kb_id}/documents
GET  /api/documents/{doc_id}
DELETE /api/documents/{doc_id}

POST /api/documents/{doc_id}/reparse
POST /api/documents/{doc_id}/reindex
```

### 16.3 检索 API

```http
POST /api/chat
POST /api/retrieval
POST /retrieval
```

### 16.4 调试 API

```http
POST /api/admin/document-preview
POST /api/admin/retrieval-preview
GET  /api/admin/jobs
GET  /api/admin/jobs/{job_id}
```

## 17. 观测和排错

最低要求是本地可回放：

```text
retrieval_log
trace steps
feedback
bad cases
eval cases
```

每次请求记录：

```text
trace_id
tenant_id
knowledge_base_ids
query
query_understanding
rewrite_query
embedding_model
retrieved_candidates
rerank_scores
filtered_candidates
answer
citations
latency_ms
error
```

后续可接：

```text
Langfuse
OpenTelemetry
Prometheus
```

## 18. 部署方案

二期第一版建议：

```text
FastAPI 单服务
PostgreSQL + pgvector
单 worker 进程
.env / 部署平台 secret
Dockerfile
compose 文件
healthcheck
```

暂不建议：

```text
Kubernetes
多服务拆分
复杂消息队列
独立向量集群
多数据库隔离
```

## 19. 分阶段实施

### Phase 2.1：多知识库基础

目标：从单一资料库升级为多租户、多业务空间、多知识库。

交付：

```text
tenant/workspace/knowledge_base/document/chunk 表
SQLAlchemy + Alembic
知识库 CRUD
pgvector metadata filter
管理台知识库列表
```

验收：

```text
可以创建多个知识库
同一 query 可在不同知识库下得到不同结果
检索强制 tenant/kb filter
```

### Phase 2.2：文档导入闭环

目标：资料能稳定进入知识库。

交付：

```text
文档上传 / file_url
导入任务表
解析质量报告
chunk 预览
embedding 状态
失败重试
reparse / reindex
```

验收：

```text
管理员能看到每个文档导入到哪一步
解析失败有明确原因
chunk 和 parser warning 可查看
```

### Phase 2.3：标准检索 API

目标：让其它业务系统或 Agent 能调用。

交付：

```text
/api/retrieval
/retrieval Dify-compatible
API Key 鉴权
score_threshold
qwen3-rerank 或外部 reranker 接入
```

验收：

```text
外部系统可按 knowledge_id 检索
不同 API Key 只能访问授权知识库
返回 records 带来源 metadata
```

### Phase 2.4：质量与运维

目标：长期可维护。

交付：

```text
回归评测管理
坏例转 eval
retrieval log
缓存
增量同步
删除同步
Langfuse / OpenTelemetry 可选接入
```

验收：

```text
关键问题可一键回归
线上坏例可复盘
知识库更新后旧索引会失效
```

## 20. 关键风险

| 风险 | 影响 | 处理方式 |
|---|---|---|
| 权限串库 | 不同业务资料互相泄露 | 后端强制 tenant/kb/permission filter，前端参数不可信 |
| 文件解析不准 | embedding 和答案都基于错误文本 | ParseQualityReport、抽样验收、低置信度拦截 |
| chunk 策略不适合 | 召回混段或找不到条款 | ChunkingRouter，按文档类型选择策略 |
| 模型切换导致向量混用 | 检索质量异常或维度错误 | 记录 embedding_model/dimension/config_version |
| 缓存污染 | 返回旧资料或越权资料 | cache key 包含 tenant/kb/version/permission |
| 管理后台只展示不闭环 | 问题发生后仍然无法修复 | 导入任务、反馈、eval、trace 必须串起来 |
| 一开始架构过重 | 交付慢，运维复杂 | 二期采用模块化单体，后续按压力拆分 |

## 21. 最小可落地版本

第一版二期最小范围建议：

```text
1. 多知识库 CRUD
2. 文档导入任务
3. 文档解析预览
4. chunk 和 embedding 入库
5. 按知识库检索
6. API Key 鉴权
7. pgvector metadata filter
8. 外部 reranker 可选接入
9. trace 回放
10. 坏例反馈
```

不建议第一版就做：

```text
复杂组织架构权限
高并发向量集群
复杂计费
完整人工审核流
复杂报表
```

## 22. 下一步建议

建议优先产出 Phase 2.1 的详细实施计划：

```text
1. 数据库 schema 和 Alembic 迁移
2. SQLAlchemy async 基础设施
3. tenant/workspace/knowledge_base/document/chunk 模型
4. knowledge_base CRUD API
5. pgvector metadata filter 改造
6. 管理台知识库列表
7. 最小权限模型
8. 测试和回归样本
```

这样二期会从“架构想法”落到可执行任务。
