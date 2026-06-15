# 内网 Langfuse 部署

这个目录用于在内网用 Docker Compose 部署 Langfuse，并给 Enterprise RAG 主服务提供 trace 上报。

## 地址

- Langfuse Web: http://10.0.193.128:3030
- 本机 SDK Host: http://127.0.0.1:3030

## 常用命令

```bash
cd /Users/zhendong.mzd/enterprise-rag/rag-backend/infra/langfuse
docker compose up -d
docker compose ps
docker compose logs -f langfuse-web
```

## 初始账号与项目

账号、密码和 API key 在 `.env` 中，由本机生成，不提交仓库。

```bash
grep '^LANGFUSE_INIT_USER_EMAIL\|^LANGFUSE_INIT_USER_PASSWORD\|^LANGFUSE_INIT_PROJECT_ID\|^LANGFUSE_INIT_PROJECT_PUBLIC_KEY\|^LANGFUSE_INIT_PROJECT_SECRET_KEY' .env
```

## RAG 服务需要的环境变量

```bash
LANGFUSE_TRACING_ENABLED=true
LANGFUSE_HOST=http://127.0.0.1:3030
LANGFUSE_PROJECT_ID=enterprise-rag
LANGFUSE_PUBLIC_KEY=<LANGFUSE_INIT_PROJECT_PUBLIC_KEY>
LANGFUSE_SECRET_KEY=<LANGFUSE_INIT_PROJECT_SECRET_KEY>
LANGFUSE_TRACE_URL_TEMPLATE=http://10.0.193.128:3030/project/{project_id}/traces/{trace_id}
```
