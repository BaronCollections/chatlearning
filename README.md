# ChatLearning RAG Trace Workbench

ChatLearning 是一个面向真实业务 RAG / Agent 系统的学习、调试和验证工作台。它不是单纯的聊天 demo，而是把一次 AI 问答拆成可观察、可点击、可解释的执行流程，让使用者看到系统内部如何完成输入校验、问题理解、改写、Embedding、召回、Rerank、证据检查、答案组织和来源引用。

当前项目以“企业制度问答”为样例场景，重点展示真实 RAG 链路里容易出问题的细节，例如 chunk 过粗、章节串段、精确条款查询、规则型问题、多跳证据、引用去重、解析质量报告和回归评测。

## 当前定位

这个仓库当前更接近：

```text
RAG / Agent 学习工作台
+ 企业制度问答最小服务
+ 检索 trace 可视化
+ 数据导入与解析骨架
+ 回归评测与坏例反馈
```

它还不是完整的 K12 教学资料上传服务，也还没有实现 Dify External Knowledge API、Milvus、文档 CRUD、API Key 鉴权和生产级文件解析集群。下面会明确列出已经具备的能力和缺口。

## 技术栈

| 模块 | 当前实现 | 说明 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 提供页面、文档页、聊天接口和反馈接口 |
| 前端 | 原生 HTML / CSS / JavaScript | ChatGPT 风格对话区 + 右侧流程图画布 + 节点详情抽屉 |
| 向量数据库 | PostgreSQL + pgvector，可关闭 | 生产检索可用 pgvector；本地可用内存样例模式 |
| Embedding | HTTP Embedding 服务；本地 deterministic fallback | `EMBEDDING_SERVICE_URL` 接外部 embedding；`RAG_EMBEDDING_PROVIDER=local` 用于离线演示 |
| Rerank | 规则 fallback + 可选 HTTP cross-encoder | `RERANKER_SERVICE_URL` 可接 bge-reranker-v2-m3 或同类服务 |
| 文本分段 | HTML 解析 + 制度章节/条款结构化切块 + fixed window fallback | 优先按制度标题、条款组、章节范围切；没有结构时按长度切 |
| 文件解析 | P0 解析骨架 | 已有统一 `DocumentParser`、HTML parser、文本附件 parser、PDF/DOCX/图片路由和质量报告；重型解析器待接入 |
| 回归评测 | 内置回归样本 + evaluation 纯函数 | 保护“二类违规”“旷工两天”等关键问题不回归 |
| 反馈闭环 | `/api/feedback` | 记录坏例摘要，不保存完整 chunk 正文 |
| 观测 | 本地 trace | 前端展示每次请求的关键步骤；Langfuse/OpenTelemetry exporter 待接入 |

## 项目结构

```text
.
├── db/
│   └── 001_pgvector_schema.sql              # pgvector 表结构
├── docs/
│   └── superpowers/plans/                   # 关键设计与实现计划
├── src/enterprise_rag_mvp/
│   ├── web_app.py                           # FastAPI Web 服务入口
│   ├── cli.py                               # init-db / ingest-samples / search / ingest-company-policies
│   ├── models.py                            # PolicyChunk / SearchResult 数据模型
│   ├── embedding_client.py                  # Embedding 客户端和本地 fallback
│   ├── reranker_client.py                   # 可选 cross-encoder reranker HTTP 客户端
│   ├── pgvector_store.py                    # pgvector 写入、向量检索和 hybrid search
│   ├── trace_pipeline.py                    # RAG trace 主流程
│   ├── policy_rule_resolver.py              # 规则型查询：用户事实 -> 制度条件 -> 结论条款
│   ├── regression_cases.py                  # 回归评测样本
│   ├── evaluation.py                        # 回归评测执行与结果汇总
│   ├── bad_cases.py                         # 坏例反馈记录，默认不保存完整正文
│   ├── samples.py                           # 公开样例制度 chunk
│   ├── company_importer.py                  # 通用业务制度分页、详情、附件解析、chunk、导入报告
│   ├── document_parsing/                    # 文档解析 P0 骨架
│   │   ├── models.py                        # ParsedDocument / ParsedElement / ParseQualityReport
│   │   ├── router.py                        # 文件类型识别和解析路由
│   │   └── html_parser.py                   # HTML 正文解析器
│   └── web/                                 # 前端页面、流程图和文档页
└── tests/                                   # 后端、解析层、trace、Web API 和前端静态测试
```

## 快速开始

### 1. 准备环境

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

可以复制示例环境变量，但不要把真实 `.env` 提交到仓库：

```bash
cp .env.example .env
```

### 2. 启动内存样例模式

没有 PostgreSQL / pgvector 时，先用内存样例模式启动页面：

```bash
RAG_DISABLE_PGVECTOR=true \
RAG_EMBEDDING_PROVIDER=local \
.venv/bin/python -m uvicorn enterprise_rag_mvp.web_app:app --host 127.0.0.1 --port 8010
```

打开：

```text
http://127.0.0.1:8010
```

文档页：

```text
http://127.0.0.1:8010/docs
```

`RAG_EMBEDDING_PROVIDER=local` 只适合离线演示和部署验收，不能代表真实 embedding 效果。

## 使用 pgvector

### 1. 创建数据库

```bash
createdb enterprise_rag_mvp
```

### 2. 初始化表结构

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
.venv/bin/python -m enterprise_rag_mvp.cli init-db
```

### 3. 写入公开样例数据

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-samples
```

### 4. 命令行检索

```bash
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli search '员工年假规则是什么？' --top-k 3
```

## Web API

### 聊天检索接口

```http
POST /api/chat
Content-Type: application/json
```

请求体：

```json
{
  "message": "我旷工两天会有什么处罚",
  "top_k": 3
}
```

响应结构：

```json
{
  "query": "我旷工两天会有什么处罚",
  "answer": "结构化答案文本",
  "results": [
    {
      "content": "候选证据片段",
      "score": 0.88,
      "citation": {
        "title": "制度标题",
        "url": "https://example.com/policyDetail/11",
        "metadata": {}
      }
    }
  ],
  "steps": []
}
```

### 坏例反馈接口

```http
POST /api/feedback
Content-Type: application/json
```

请求体：

```json
{
  "query": "二类违规的处罚是什么",
  "feedback_type": "missing_clause",
  "answer": "只返回了定义，缺少处罚",
  "trace_id": "trace-id",
  "results": []
}
```

支持的 `feedback_type`：

```text
correct / wrong_source / missing_clause / irrelevant_answer / too_verbose / scope_leak / unsafe_or_sensitive
```

反馈默认写入 `data/bad_cases.jsonl`，`data/` 不会提交到 Git。

## 检索流程

当前普通问答的主链路：

```text
用户问题
-> 输入校验
-> 文本归一化
-> Query Understanding
-> Query Rewrite
-> Tokenize 展示
-> Query Embedding
-> pgvector / 内存样例召回
-> Hybrid Search 或普通向量召回
-> 规则约束 Rerank
-> Evidence Filter
-> Span Extraction
-> Citation Merge
-> 结构化答案
-> Trace 展示
```

规则型问题会走更细的链路：

```text
用户事实
-> 行为识别，例如 旷工 / 虚假报销 / 打听工资
-> 条件参数识别，例如 2 天 / 三天 / 一年内两次
-> 匹配制度条件
-> 跳转处理条款
-> 组合互补证据
-> 输出事实、规则匹配、处理结果、依据和不确定性
```

例如“我旷工两天会有什么处罚”会同时返回：

1. 旷工 2 天属于哪类违规。
2. 命中的处罚规则是什么。
3. 处理结果是什么。
4. 来源链接和制度标题。

## 文档导入流水线

### 公开样例导入

```bash
.venv/bin/python -m enterprise_rag_mvp.cli ingest-samples
```

这个命令只读取 `samples.py` 里的公开样例，不访问外部系统。

### 自定义业务制度源导入

仓库提供 `ingest-company-policies`，用于演示：

```text
业务系统分页列表
-> 逐篇详情正文
-> HTML 解析
-> 附件按需解析
-> 结构化切块
-> Embedding
-> pgvector 入库
```

认证 cookie 和真实业务域名只能放在当前终端或部署平台 secret 中，不要写入代码或 README。

```bash
export COMPANY_AUTH_COOKIE='<put-your-auth-cookie-here>'
```

先 dry-run，只拉取、解析和切块，不调用 embedding、不写数据库：

```bash
COMPANY_AUTH_COOKIE="$COMPANY_AUTH_COOKIE" \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-company-policies \
  --base-url 'https://your-internal-policy-host.example' \
  --dry-run \
  --max-docs 2 \
  --page-size 20
```

确认 dry-run 后再写入 pgvector：

```bash
COMPANY_AUTH_COOKIE="$COMPANY_AUTH_COOKIE" \
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-company-policies \
  --base-url 'https://your-internal-policy-host.example' \
  --max-docs 2 \
  --page-size 20
```

默认不会下载 `fileList` 附件，避免误全量拉取大文件。需要附件解析时显式加：

```bash
--parse-attachments
```

全分类 dry-run：

```bash
COMPANY_AUTH_COOKIE="$COMPANY_AUTH_COOKIE" \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-company-policies \
  --base-url 'https://your-internal-policy-host.example' \
  --all-categories \
  --dry-run \
  --max-docs 2 \
  --page-size 20
```

明确全量导入时必须加 `--all`：

```bash
COMPANY_AUTH_COOKIE="$COMPANY_AUTH_COOKIE" \
RAG_DATABASE_DSN=postgresql://127.0.0.1:5432/enterprise_rag_mvp \
EMBEDDING_SERVICE_URL=http://127.0.0.1:8001 \
.venv/bin/python -m enterprise_rag_mvp.cli ingest-company-policies \
  --base-url 'https://your-internal-policy-host.example' \
  --all-categories \
  --all \
  --page-size 20
```

## 文件解析能力

当前已经落地 P0 解析骨架：

```text
DocumentSource
-> DocumentParserRouter
-> ParsedDocument
-> ParsedElement
-> ParseQualityReport
-> chunk metadata
-> 导入报告
```

已支持：

- HTML 正文解析：保留 title、paragraph、table 元素。
- 文本附件解析：`text/plain` / `.txt` / `.md` 可解析成 chunk。
- PDF / DOCX / 图片类型识别：能路由并返回明确的未配置报告。
- 解析质量 metadata：`parser_name`、`parser_version`、`parse_status`、`parse_element_count`、`parse_warning_count`、`parse_table_count`、`parse_image_ocr_count`。

待接入：

- PDF：PyMuPDF 预检 + Docling 主解析 + Unstructured hi_res fallback。
- DOCX：python-docx / Docling。
- 图片和扫描件：PaddleOCR 或企业 OCR 服务。
- 页码、bbox、OCR confidence、跨页表格、人工复核队列。

## 和完整 K12 RAG Service 相比缺少什么

你给的 K12 样例是完整资料上传和检索服务。对照那个目标，我们当前还缺这些能力：

| 能力 | 当前状态 | 建议 |
|---|---|---|
| Dify External Knowledge API | 未实现 | 增加 `POST /retrieval`，按 Dify records 协议返回 |
| 知识库 CRUD | 未实现 | 增加 knowledge_base 模块、API Key、权限边界 |
| 文档上传 API | 未实现 | 增加 document 模块，支持 file_url / upload / status |
| Milvus | 未使用 | 当前是 pgvector；如果数据量大或要多租户高并发，可引入 Milvus |
| SQLAlchemy async + Alembic | 未使用 | 当前是 SQL schema + psycopg；生产服务建议迁移到迁移管理 |
| API Key 鉴权 | 未实现 | 需要对管理 API 和检索 API 分开鉴权 |
| 文件转 Markdown 服务 | 未接入 | 当前只有解析骨架；可接 Docling/Unstructured/企业解析服务 |
| 生产 OCR | 未接入 | 图片、扫描 PDF 需要 PaddleOCR 或专用 OCR 服务 |
| 权限过滤 | 待接入 | metadata 里要有 audience、tenant、user_scope，检索层强过滤 |
| 增量同步 | 待接入 | 增加 content_hash、source_updated_at、deleted_at |
| Docker 部署文件 | 未提供 | 增加 Dockerfile、compose、健康检查 |
| Langfuse / OpenTelemetry | 待接入 | 当前只有本地 trace，可外接观测平台 |

## Dify 接入规划

当前还没有实现 Dify External Knowledge API。建议后续新增：

```http
POST /retrieval
Authorization: Bearer {API_KEY}
```

请求体：

```json
{
  "knowledge_id": "知识库 ID",
  "query": "光合作用的过程",
  "retrieval_setting": {
    "top_k": 5,
    "score_threshold": 0.5
  }
}
```

响应体：

```json
{
  "records": [
    {
      "content": "候选片段正文",
      "score": 0.92,
      "title": "资料标题.pdf",
      "metadata": {
        "path": "资料标题.pdf",
        "description": "章节路径",
        "document_id": "document-id",
        "chunk_index": 15,
        "source_url": "https://example.com/source"
      }
    }
  ]
}
```

建议实现顺序：

```text
API Key 鉴权
-> knowledge_id 到知识库范围映射
-> query embedding
-> metadata filter
-> pgvector / Milvus 召回
-> rerank
-> score_threshold
-> Dify records 序列化
```

## Reranker 接入

可选配置：

```bash
RERANKER_SERVICE_URL=http://127.0.0.1:9000
RERANKER_PROVIDER=bge-reranker-v2-m3
```

服务需要支持：

```http
POST /rerank
Content-Type: application/json

{
  "query": "用户问题",
  "documents": ["候选片段1", "候选片段2"]
}
```

返回可以是：

```json
{"scores": [0.1, 0.9]}
```

也可以是：

```json
{
  "results": [
    {"index": 1, "score": 0.9},
    {"index": 0, "score": 0.1}
  ]
}
```

服务未配置、超时或返回异常时，系统会降级到确定性 fallback，并在 trace 里记录来源和错误。

## 回归评测

`src/enterprise_rag_mvp/regression_cases.py` 保存当前必须稳定的问答样本，例如：

- `二类违规是什么`
- `二类违规的处罚是什么`
- `我旷工两天会受到什么处罚`
- `旷工三天会怎样`
- `虚假报销属于什么违规`
- `虚假报销怎么处罚`

每次改 query understanding、hybrid search、rerank、evidence filter、span extraction、answer template 或 document parsing，都应该跑测试，避免修 A 坏 B。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RAG_DISABLE_PGVECTOR` | `false` | 设置为 `true` 时跳过 pgvector，使用内存样例模式 |
| `RAG_EMBEDDING_PROVIDER` | 空 | 设置为 `local` 时使用本地 deterministic embedding |
| `RAG_DATABASE_DSN` | `postgresql://127.0.0.1:5432/enterprise_rag_mvp` | PostgreSQL 连接串 |
| `EMBEDDING_SERVICE_URL` | `http://127.0.0.1:8001` | 外部 embedding 服务地址 |
| `RERANKER_SERVICE_URL` | 空 | 可选 cross-encoder reranker 服务地址 |
| `RERANKER_PROVIDER` | `external_cross_encoder` | trace 中展示的 reranker 名称 |
| `RAG_BAD_CASE_PATH` | `data/bad_cases.jsonl` | 坏例反馈写入路径；`data/` 默认不提交 |
| `COMPANY_AUTH_COOKIE` | 空 | 自定义业务制度源认证 cookie，只能放本机或 secret |
| `COMPANY_POLICY_BASE_URL` | `https://example.com` | 自定义业务制度源地址，公开仓库只保留占位值 |

## 测试

```bash
node --check src/enterprise_rag_mvp/web/app.js
node --check src/enterprise_rag_mvp/web/docs.js
.venv/bin/python -m pytest -q
```

## 隐私与发布边界

这个仓库只应该包含代码、公开样例、测试和说明文档。不要提交：

- `.env`、数据库密码、API key、cookie、登录态。
- 真实制度正文、附件、学生或员工信息。
- embedding 向量、本地数据库、JSONL 反馈数据。
- 本机绝对路径、服务器 IP、运维账号和个人文件。

`.gitignore` 已排除 `.env*`、虚拟环境、缓存、日志、本地数据库、`data/`、`outputs/` 和临时目录；仓库保留 `.env.example`，只用于说明变量名和占位值。

## 当前边界

- 当前没有完整 K12 资料上传、文档状态流转和知识库管理 API。
- 当前没有 Dify External Knowledge API，需要单独实现 `/retrieval`。
- 当前没有 Dockerfile 和 docker-compose。
- 当前文件解析只完成 P0 骨架，PDF / DOCX / 图片生产解析器还未接入。
- 当前没有真正调用 LLM 生成长答案，重点是 RAG 检索链路、规则解析、trace 和学习展示。
- 当前内存样例模式只适合教学和联调，真实业务应使用 pgvector、Milvus 或其它可持久化向量库。
