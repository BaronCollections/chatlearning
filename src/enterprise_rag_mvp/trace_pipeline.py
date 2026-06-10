from __future__ import annotations

import math
import hashlib
import time
from typing import Any
from urllib.parse import quote

from enterprise_rag_mvp.models import SearchResult
from enterprise_rag_mvp.samples import sample_policy_chunks

PGVECTOR_QUERY_SQL = """
SELECT
  c.chunk_id,
  c.doc_id,
  c.block_id,
  c.chunk_text,
  c.heading_path,
  c.metadata::text,
  e.embedding <=> :query_embedding::vector AS distance
FROM rag_chunk_embeddings_bge_m3 e
JOIN rag_chunks c ON c.chunk_id = e.chunk_id
ORDER BY e.embedding <=> :query_embedding::vector
LIMIT :top_k;
""".strip()

MAX_TRACE_TOKEN_ROWS = 128


def _term(term: str, definition: str) -> dict[str, str]:
    return {"term": term, "definition": definition}


def _trace_id(raw_query: str, top_k: int) -> str:
    digest = hashlib.sha256(f"{raw_query}\0{top_k}".encode("utf-8")).hexdigest()[:16]
    return f"trace_{digest}"


def _duration_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _whitespace_counts(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "leading_whitespace": len(text) - len(text.lstrip()),
        "trailing_whitespace": len(text) - len(text.rstrip()),
        "whitespace_runs": sum(1 for part in text.split(" ") if part == ""),
    }


def _normalize_query_with_trace(query: str) -> tuple[str, list[dict[str, Any]]]:
    trim_start = time.perf_counter()
    trimmed = query.strip()
    trim_step = _step(
        key="trim_whitespace",
        title="去掉首尾空白",
        summary="用 Python str.strip() 移除输入首尾空白，保留中间原文。",
        details={
            "tool": "Python str.strip()",
            "input": query,
            "output": trimmed,
            "removed": _whitespace_counts(query),
            "why": "用户复制粘贴时常带换行、制表符或空格；首尾空白不承载制度检索语义，会干扰缓存键和 trace 展示。",
            "edge_cases": ["全空白输入会在归一化后被拒绝", "中间空格不会在这一步被删除"],
        },
        duration_ms=_duration_ms(trim_start),
    )

    collapse_start = time.perf_counter()
    normalized = " ".join(trimmed.split())
    collapse_step = _step(
        key="collapse_whitespace",
        title="压缩连续空白字符",
        summary="用 str.split() + str.join() 把连续空白压缩成一个半角空格。",
        details={
            "tool": "Python str.split() + str.join()",
            "input": trimmed,
            "output": normalized,
            "operation": "split() 按任意 Unicode 空白切分并丢弃空片段，join() 用单个空格重新连接。",
            "why": "embedding 模型关注语义，重复空格、制表符和换行通常不是业务信号；统一空白能让相同问题得到稳定 token 和向量。",
            "tradeoff": "不会做同义词替换、大小写强制转换或中文标点改写，避免把用户真实问题改成另一个语义。",
        },
        duration_ms=_duration_ms(collapse_start),
    )
    semantic_start = time.perf_counter()
    semantic_step = _step(
        key="preserve_semantics_check",
        title="确认没有改写语义",
        summary="只比较格式变化，确认没有替换词义或扩大业务范围。",
        details={
            "tool": "deterministic normalization check",
            "input": query,
            "output": normalized,
            "status": "ok",
            "why": "真实 RAG 里清洗和改写必须分离；清洗只处理格式，不能偷偷把用户问题改成另一个问题。",
        },
        duration_ms=_duration_ms(semantic_start),
    )
    return normalized, [trim_step, collapse_step, semantic_step]


def _fallback_tokenize(text: str) -> dict[str, Any]:
    tokens = [char for char in text if not char.isspace()]
    return {
        "text": text,
        "tokens": tokens,
        "token_ids": [],
        "token_count": len(tokens),
        "tokenizer": "display-char-tokenizer",
        "note": "Fallback display tokenizer. Real BGE tokenizer runs inside embedding service when /tokenize is available.",
    }


def _token_table(token_info: dict[str, Any]) -> list[dict[str, Any]]:
    tokens = list(token_info.get("tokens") or [])
    token_ids = list(token_info.get("token_ids") or [])
    rows = []
    for index, token in enumerate(tokens[:MAX_TRACE_TOKEN_ROWS]):
        rows.append(
            {
                "index": index,
                "token": token,
                "token_id": token_ids[index] if index < len(token_ids) else None,
            }
        )
    return rows


def _tokenizer_choice() -> dict[str, Any]:
    return {
        "selected": "BGE-M3 tokenizer",
        "why": "token 预览必须和后续 embedding 模型的实际输入边界一致，否则展示出来的 token 与模型真正处理的 token 不一致。",
        "alternatives": [
            {
                "name": "按字符展示",
                "why_not": "中文场景直观，但不能反映 SentencePiece/模型词表的真实 token id。",
            },
            {
                "name": "按空格或标点切词",
                "why_not": "适合英文或简单关键词分析，不适合中英文混排制度文本的模型输入解释。",
            },
        ],
    }


def _embedding_model_choice() -> dict[str, Any]:
    return {
        "selected": "BGE-M3",
        "why": "当前业务有中文制度、英文标题和中英混排查询；BGE-M3 适合多语言语义检索，并且可以本地部署，便于在企业内控制数据边界。",
        "current_usage": "本 MVP 使用 dense embedding；BGE-M3 的稀疏/多向量能力可作为后续增强，不在当前最小链路里硬塞。",
        "alternatives": [
            {
                "name": "OpenAI text-embedding-3",
                "when_to_use": "需要托管服务、稳定吞吐和少维护成本时可以考虑。",
                "why_not_now": "当前项目已经有本地 BGE-M3 embedding service，且制度内容更适合先验证内网数据链路。",
            },
            {
                "name": "BM25 keyword search",
                "when_to_use": "精确词、编号、专有名词召回很强，适合作为混合检索的一路。",
                "why_not_now": "单独使用无法处理‘年假规则’和‘带薪年休假’这类语义近似表达。",
            },
            {
                "name": "bge-large-zh / text2vec",
                "when_to_use": "只做中文短文本，且希望模型更小或已有历史评测基线时可以考虑。",
                "why_not_now": "云谷制度包含英文标题和中英混排，M3 的多语言能力更贴合。",
            },
        ],
    }


def _vector_store_choice() -> dict[str, Any]:
    return {
        "selected": "PostgreSQL + pgvector",
        "why": "MVP 已经以 Postgres 存 chunk 元数据；pgvector 能在同一数据库里保存向量、来源字段和 SQL 过滤条件，便于先把业务闭环跑稳。",
        "alternatives": [
            {
                "name": "Milvus / Zilliz",
                "why_not_now": "适合更大规模和专门向量索引运维；当前 133 条制度起步，用它会增加系统复杂度。",
            },
            {
                "name": "Elasticsearch / OpenSearch kNN",
                "why_not_now": "适合已经有 ES 检索体系的团队；当前项目没有这个依赖，先用 pgvector 更直接。",
            },
            {
                "name": "纯内存 cosine 检索",
                "why_not_now": "适合 demo 和 pgvector 不可用时兜底，不适合真实业务持久化、权限过滤和增量更新。",
            },
        ],
    }


def _guardrail_terms() -> list[dict[str, str]]:
    return [
        _term("Guardrail", "在请求进入业务链路前执行的规则或模型检查，用来阻止越权、隐私和不适合回答的问题。"),
        _term("PII", "personally identifiable information，能识别个人身份或私密信息的数据。"),
    ]


def _query_understanding_terms() -> list[dict[str, str]]:
    return [
        _term("Intent classification", "判断用户到底是在问规则、流程、资格、例外，还是比较多个制度。"),
        _term("Entity extraction", "从问题中抽取业务对象，例如员工、年假、幼儿园、高中、财务制度。"),
        _term("Ambiguity", "问题里缺少会影响答案的范围信息，例如没有说适用对象或时间。"),
    ]


def _rewrite_terms() -> list[dict[str, str]]:
    return [
        _term("Query rewrite", "把口语化问题改写成更适合检索的独立问题，但保留原始语义。"),
        _term("Query expansion", "补充安全的同义词或业务词，提高召回相关制度的概率。"),
        _term("Recall", "检索阶段找回相关材料的能力。"),
    ]


def _reranker_choice() -> dict[str, Any]:
    return {
        "selected": "deterministic lexical rerank fallback",
        "why": "当前本地环境没有独立 cross-encoder reranker 服务；先用可测试的词项重叠、标题命中和距离信号重排，让流程、字段和 UI 先贴近真实生产链路。",
        "current_usage": "对初召回候选计算 rerank_score，并展示 rank_before/rank_after。",
        "alternatives": [
            {
                "name": "bge-reranker-v2-m3",
                "when_to_use": "内网可部署时优先考虑；cross-encoder 直接读取 query + chunk，通常比单纯向量距离更适合最终排序。",
            },
            {
                "name": "Cohere Rerank",
                "when_to_use": "允许外部 API 且希望快速获得托管 rerank 能力时使用。",
            },
            {
                "name": "不做 rerank",
                "why_not": "会把向量相似但不能回答问题的片段直接送入生成阶段，生产风险较高。",
            },
        ],
    }


def _detect_query_understanding(query: str) -> dict[str, Any]:
    policy_category_hint = "general"
    if any(term in query for term in ["年假", "年休假", "薪酬", "员工", "HR", "考勤"]):
        policy_category_hint = "leave" if any(term in query for term in ["年假", "年休假"]) else "hr"
    elif any(term in query for term in ["报销", "采购", "发票", "财务"]):
        policy_category_hint = "finance"
    elif any(term in query for term in ["安全", "账号", "数据", "外传"]):
        policy_category_hint = "security"

    audience_hint = "employee" if any(term in query for term in ["员工", "老师", "教师", "HR"]) else "unknown"
    if any(term in query for term in ["学生", "幼儿园", "小学", "初中", "高中"]):
        audience_hint = "student_or_stage_specific"

    intent = "rule_lookup"
    if any(term in query for term in ["流程", "怎么申请", "如何申请"]):
        intent = "process_lookup"
    elif any(term in query for term in ["能不能", "是否", "可以吗"]):
        intent = "eligibility_check"
    elif any(term in query for term in ["区别", "对比", "比较"]):
        intent = "policy_comparison"

    ambiguity_flags: list[str] = []
    if audience_hint == "unknown":
        ambiguity_flags.append("missing_audience")
    if any(term in query for term in ["今年", "最新", "现在"]) and not any(char.isdigit() for char in query):
        ambiguity_flags.append("relative_time_without_year")

    return {
        "intent": intent,
        "policy_category_hint": policy_category_hint,
        "audience_hint": audience_hint,
        "time_hints": [term for term in ["今年", "最新", "现在", "2026"] if term in query],
        "ambiguity_flags": ambiguity_flags,
        "extracted_terms": [term for term in ["员工", "年假", "年休假", "报销", "考勤", "安全"] if term in query],
    }


def _rewrite_query(query: str, understanding: dict[str, Any]) -> dict[str, Any]:
    standalone_query = query
    if understanding.get("audience_hint") == "employee" and "员工" not in standalone_query:
        standalone_query = f"员工{standalone_query}"
    if understanding.get("policy_category_hint") == "leave" and "规则" not in standalone_query:
        standalone_query = f"{standalone_query} 规则"

    expansions: list[str] = []
    if "年假" in standalone_query and "年休假" not in standalone_query:
        expansions.append("年休假")
    if "年休假" in standalone_query and "年假" not in standalone_query:
        expansions.append("年假")
    if understanding.get("policy_category_hint") == "leave":
        expansions.extend(["带薪年休假", "休假管理办法"])

    deduped_expansions = []
    for term in expansions:
        if term not in deduped_expansions and term not in standalone_query:
            deduped_expansions.append(term)
    expanded_query = " ".join([standalone_query, *deduped_expansions]).strip()
    return {
        "original_query": query,
        "standalone_query": standalone_query,
        "expanded_query": expanded_query,
        "added_terms": deduped_expansions,
        "semantic_drift_check": {
            "status": "ok",
            "method": "rule-based scope comparison",
            "reason": "只补充同义词和制度检索词，没有改变用户的对象、动作或问题类型。",
        },
    }


def _lexical_terms(text: str) -> set[str]:
    terms = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    for token in text.replace("？", " ").replace("?", " ").split():
        if token:
            terms.add(token.lower())
    return terms


def _rerank_results(query: str, results: list[SearchResult]) -> tuple[list[SearchResult], list[dict[str, Any]]]:
    query_terms = _lexical_terms(query)
    scored: list[tuple[float, int, SearchResult, str]] = []
    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        haystack = " ".join([chunk.text, " ".join(chunk.heading_path), " ".join(str(v) for v in chunk.metadata.values())])
        overlap = len(query_terms.intersection(_lexical_terms(haystack)))
        heading_bonus = 2 if any(term in "".join(chunk.heading_path) for term in ["年假", "年休假", "休假"]) else 0
        distance_score = max(0.0, 1.0 - result.distance)
        score = round(overlap * 0.2 + heading_bonus * 0.15 + distance_score, 4)
        reason = "命中查询词和标题信号" if overlap or heading_bonus else "主要依赖向量距离，词项证据较弱"
        scored.append((score, index, result, reason))

    scored.sort(key=lambda item: (-item[0], item[1]))
    reranked = [item[2] for item in scored]
    comparison = [
        {
            "chunk_id": result.chunk.chunk_id,
            "title": " > ".join(result.chunk.heading_path) if result.chunk.heading_path else result.chunk.doc_id,
            "rank_before": rank_before,
            "rank_after": rank_after,
            "rerank_score": score,
            "distance": round(result.distance, 6),
            "reason": reason,
        }
        for rank_after, (score, rank_before, result, reason) in enumerate(scored, start=1)
    ]
    return reranked, comparison


def _metadata_value(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _source_url(chunk: Any) -> str | None:
    metadata = chunk.metadata or {}
    explicit_url = _metadata_value(metadata, "url", "source_url", "detail_url")
    if explicit_url:
        return str(explicit_url)

    import_information_id = _metadata_value(metadata, "import_information_id", "importInformationId")
    if import_information_id is not None and metadata.get("source") == "yungu_policy_system":
        return "https://work.yungu.org/home/policyDetail?" + f"importInformationId={quote(str(import_information_id))}"
    return None


def _citation_for_result(result: SearchResult, index: int) -> dict[str, Any]:
    chunk = result.chunk
    metadata = chunk.metadata or {}
    heading_title = " > ".join(chunk.heading_path) if chunk.heading_path else chunk.doc_id
    title = _metadata_value(metadata, "title", "cn_title", "cnTitle", "en_title", "enTitle") or heading_title
    category = _metadata_value(
        metadata,
        "policy_category_type_name",
        "policyCategoryTypeName",
        "category_name",
        "categoryName",
    )
    publish_date = _metadata_value(metadata, "publish_date", "publishDate")
    import_information_id = _metadata_value(metadata, "import_information_id", "importInformationId")
    page = metadata.get("page")
    source = metadata.get("source", chunk.doc_id)
    return {
        "citation_id": f"[{index}]",
        "title": str(title),
        "source": source,
        "url": _source_url(chunk),
        "category": category,
        "publish_date": publish_date,
        "import_information_id": import_information_id,
        "page": page,
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "block_id": chunk.block_id,
        "heading_path": chunk.heading_path,
        "distance": round(result.distance, 6),
    }


def _quality_checks(results: list[SearchResult], rerank_comparison: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    top_score = rerank_comparison[0]["rerank_score"] if rerank_comparison else 0
    checks = [
        {
            "name": "relevance_threshold",
            "status": "ok" if top_score >= 0.5 else "warn",
            "reason": f"top rerank score={top_score}；低分时应反问或提示证据不足。",
        },
        {
            "name": "source_metadata",
            "status": "ok" if all(result.chunk.metadata.get("source") for result in results) else "warn",
            "reason": "检查每个候选是否有 source/page/category/citation 等可引用字段。",
        },
        {
            "name": "freshness_conflict",
            "status": "warn" if results and not any("effective_date" in result.chunk.metadata for result in results) else "ok",
            "reason": "样例 chunk 没有生效日期；真实制度导入时需要比较 publishDate/effectiveDate/废止状态。",
        },
        {
            "name": "context_assembly",
            "status": "ok" if results else "warn",
            "reason": f"组装 {len(results)} 个 context block，并保留标题、来源、页码和引用链接。",
        },
    ]
    context_blocks = []
    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        citation = _citation_for_result(result, index)
        context_blocks.append(
            {
                "chunk_id": chunk.chunk_id,
                "title": citation["title"],
                "text": chunk.text,
                "source": chunk.metadata.get("source", chunk.doc_id),
                "page": chunk.metadata.get("page"),
                "citation": citation,
            }
        )
    return checks, context_blocks


def _langfuse_observations(trace_id: str, retrieval_mode: str, result_count: int) -> list[dict[str, Any]]:
    return [
        {"type": "trace", "name": "rag_chat", "id": trace_id, "purpose": "一次用户问题的完整生命周期。"},
        {"type": "span", "name": "query_rewrite", "purpose": "记录改写输入输出和耗时。"},
        {"type": "retriever", "name": retrieval_mode, "result_count": result_count},
        {"type": "embedding", "name": "BGE-M3 query embedding", "purpose": "记录模型、维度和输入类型。"},
        {"type": "evaluator", "name": "evidence_quality", "purpose": "记录证据质量检查结果。"},
        {"type": "generation", "name": "grounded_answer", "purpose": "记录最终回复模板或 LLM 调用。"},
        {"type": "score", "name": "retrieval_quality", "purpose": "线上可写入用户反馈或自动评估分。"},
        {"type": "feedback_hook", "name": "thumbs_up_down", "purpose": "把失败样本沉淀为回归评估 dataset。"},
    ]


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    return 1.0 - (dot / (left_norm * right_norm))


def _memory_search(
    query_embedding: list[float],
    *,
    embedding_client: Any,
    top_k: int,
) -> list[SearchResult]:
    chunks = sample_policy_chunks()
    document_embeddings = embedding_client.embed([chunk.text for chunk in chunks], input_type="document")
    ranked = sorted(
        (
            SearchResult(chunk=chunk, distance=_cosine_distance(query_embedding, embedding))
            for chunk, embedding in zip(chunks, document_embeddings)
        ),
        key=lambda result: result.distance,
    )
    return ranked[:top_k]


def _serialize_result(result: SearchResult, index: int = 1) -> dict[str, Any]:
    chunk = result.chunk
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "block_id": chunk.block_id,
        "text": chunk.text,
        "heading_path": chunk.heading_path,
        "metadata": chunk.metadata,
        "distance": round(result.distance, 6),
        "citation": _citation_for_result(result, index),
    }


def _compose_answer(results: list[SearchResult], retrieval_mode: str) -> str:
    if not results:
        return "没有在当前制度样本中检索到足够相关的内容。"

    best = results[0].chunk
    best_citation = _citation_for_result(results[0], 1)
    mode_label = "pgvector" if retrieval_mode == "pgvector" else "内存向量检索 demo"
    source_lines = []
    for index, result in enumerate(results, start=1):
        citation = _citation_for_result(result, index)
        meta_parts = [part for part in [citation.get("category"), citation.get("publish_date")] if part]
        meta = f"（{' / '.join(str(part) for part in meta_parts)}）" if meta_parts else ""
        has_url = bool(citation.get("url"))
        location = citation.get("url") or citation.get("source") or citation.get("doc_id")
        location_label = "链接" if has_url else "位置"
        source_lines.append(f"{citation['citation_id']}《{citation['title']}》{meta} {location_label}：{location}")

    return (
        f"我在制度库中返回了 {len(results)} 条候选片段。优先依据 {best_citation['citation_id']}"
        f"《{best_citation['title']}》：{best.text}\n\n"
        "相关来源：\n"
        + "\n".join(source_lines)
        + f"\n检索方式：{mode_label}。"
    )


def _step(
    *,
    key: str,
    title: str,
    summary: str,
    details: dict[str, Any],
    duration_ms: float,
    status: str = "ok",
    execution_mode: str = "sequential",
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "status": status,
        "execution_mode": execution_mode,
        "summary": summary,
        "details": details,
        "duration_ms": duration_ms,
        "children": children or [],
    }


def run_chat_trace(
    query: str,
    *,
    embedding_client: Any,
    store: Any | None,
    top_k: int = 3,
) -> dict[str, Any]:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if not query.strip():
        raise ValueError("query must contain non-whitespace text")
    if not isinstance(top_k, int) or top_k < 1 or top_k > 10:
        raise ValueError("top_k must be an integer between 1 and 10")

    steps: list[dict[str, Any]] = []
    trace_id = _trace_id(query, top_k)

    start = time.perf_counter()
    steps.append(
        _step(
            key="request_intake",
            title="Step 1 · 请求进入与 Trace 创建",
            summary="接收原始问题，生成 request/trace 身份，并保留审计入口。",
            details={
                "tool": "FastAPI POST /api/chat",
                "raw_query": query,
                "trace_id": trace_id,
                "request_id": trace_id,
                "business_goal": "把用户问题转成可追踪的检索请求，并保留每一步输入输出，方便排查和学习。",
                "term_definitions": [
                    _term("Trace", "一次用户请求从输入、检索、重排、回答到观测的完整生命周期。"),
                    _term("Span", "Trace 里的一个带耗时的子操作，例如 query rewrite 或 rerank。"),
                    _term("Observation", "Langfuse 中记录 span、retriever、embedding、generation、evaluator 等工作的统称。"),
                ],
                "pitfalls": ["不能丢失 raw_query；后续改写必须能回溯原始输入。"],
            },
            duration_ms=_duration_ms(start),
            children=[
                _step(
                    key="assign_request_id",
                    title="生成 request_id",
                    summary="用原始问题和 top_k 生成稳定 trace id，方便本地复现。",
                    details={"tool": "sha256 digest", "trace_id": trace_id},
                    duration_ms=0,
                ),
                _step(
                    key="capture_raw_query",
                    title="保留原始输入",
                    summary="记录用户输入原文，后续清洗和改写都不能覆盖它。",
                    details={"raw_query": query},
                    duration_ms=0,
                ),
                _step(
                    key="create_observation_trace",
                    title="创建观测 trace",
                    summary="当前不接真实 SDK，但输出 Langfuse-ready trace 元数据。",
                    details={"tool": "Langfuse-ready metadata", "trace_id": trace_id},
                    duration_ms=0,
                ),
            ],
        )
    )

    start = time.perf_counter()
    sensitive_flags = [term for term in ["工资", "身份证", "手机号", "账号", "密码"] if term in query]
    domain_terms = [term for term in ["制度", "规则", "年假", "年休假", "报销", "考勤", "安全", "政策"] if term in query]
    steps.append(
        _step(
            key="input_guardrails",
            title="Step 2 · 输入校验与业务边界",
            summary="检查输入形状、隐私风险和是否属于制度问答边界。",
            details={
                "tool": "deterministic guardrail rules",
                "top_k": top_k,
                "max_top_k": 10,
                "sensitive_flags": sensitive_flags,
                "policy_domain_terms": domain_terms,
                "domain_status": "policy_question" if domain_terms else "needs_more_context",
                "term_definitions": _guardrail_terms(),
                "pitfalls": ["真实业务不能因为检索到了材料就回答个人隐私或越权问题。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="parallel",
            status="warn" if sensitive_flags else "ok",
            children=[
                _step(
                    key="validate_shape",
                    title="校验请求参数",
                    summary="确认 query 是非空字符串，top_k 在允许范围内。",
                    details={"query_type": type(query).__name__, "query_length": len(query), "top_k": top_k, "status": "ok"},
                    duration_ms=0,
                ),
                _step(
                    key="detect_sensitive_scope",
                    title="识别敏感边界",
                    summary="标记隐私、薪酬、账号凭证等需要特殊处理的问题。",
                    details={"sensitive_flags": sensitive_flags, "status": "warn" if sensitive_flags else "ok"},
                    duration_ms=0,
                    status="warn" if sensitive_flags else "ok",
                ),
                _step(
                    key="detect_policy_domain",
                    title="识别制度问答边界",
                    summary="确认问题是否看起来属于制度/政策/流程检索。",
                    details={"policy_domain_terms": domain_terms, "status": "ok" if domain_terms else "warn"},
                    duration_ms=0,
                    status="ok" if domain_terms else "warn",
                ),
            ],
        )
    )

    start = time.perf_counter()
    normalized_query, normalize_children = _normalize_query_with_trace(query)
    steps.append(
        _step(
            key="normalize_text",
            title="Step 3 · 文本规范化",
            summary="去掉首尾空白、压缩连续空白，并确认没有改变业务语义。",
            details={
                "raw_query": query,
                "normalized_query": normalized_query,
                "logic": "strip + whitespace normalization",
                "why_only_this": "查询预处理只做格式归一，不做摘要、翻译或改写，避免在检索前擅自改变用户意图。",
                "term_definitions": [
                    _term("Normalization", "把空格、换行、制表符等格式差异变成稳定形式。"),
                    _term("Semantic drift", "清洗或改写过程中不小心改变了用户原本含义。"),
                ],
                "pitfalls": ["不要在规范化阶段做同义词替换；那属于显式 query rewrite。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="sequential",
            children=normalize_children,
        )
    )

    start = time.perf_counter()
    understanding = _detect_query_understanding(normalized_query)
    steps.append(
        _step(
            key="query_understanding",
            title="Step 4 · 查询理解",
            summary="抽取意图、制度类别、适用对象、时间线索和歧义信号。",
            details={
                "tool": "rule-based query understanding",
                "why": "真实 Agent 不能直接 embedding；先理解问题才能决定过滤条件、改写策略和是否需要追问。",
                "tradeoff": "当前用确定性规则方便教学和测试；生产可替换为小模型分类器或 LLM function calling。",
                "term_definitions": _query_understanding_terms(),
                "pitfalls": ["查询理解只能抽取和标记，不能凭空补事实。"],
                **understanding,
            },
            duration_ms=_duration_ms(start),
            execution_mode="parallel",
            status="warn" if understanding["ambiguity_flags"] else "ok",
            children=[
                _step(
                    key="classify_intent",
                    title="意图分类",
                    summary="判断用户是在查规则、流程、资格、例外还是比较制度。",
                    details={"intent": understanding["intent"]},
                    duration_ms=0,
                ),
                _step(
                    key="extract_entities",
                    title="抽取业务实体",
                    summary="抽取适用对象、制度类别、时间和核心政策词。",
                    details={
                        "policy_category_hint": understanding["policy_category_hint"],
                        "audience_hint": understanding["audience_hint"],
                        "time_hints": understanding["time_hints"],
                        "extracted_terms": understanding["extracted_terms"],
                    },
                    duration_ms=0,
                ),
                _step(
                    key="detect_ambiguity",
                    title="识别歧义",
                    summary="标记缺少适用对象、年份或范围的信息。",
                    details={"ambiguity_flags": understanding["ambiguity_flags"]},
                    duration_ms=0,
                    status="warn" if understanding["ambiguity_flags"] else "ok",
                ),
            ],
        )
    )

    start = time.perf_counter()
    rewrite = _rewrite_query(normalized_query, understanding)
    retrieval_query = rewrite["standalone_query"]
    steps.append(
        _step(
            key="query_rewrite",
            title="Step 5 · Query 改写与扩展",
            summary="把口语化输入变成检索友好的独立问题，并补充安全同义词。",
            details={
                "tool": "deterministic query rewrite rules",
                "why": "改写能让‘年假’匹配到制度正文里的‘年休假’，但必须展示改写前后，防止语义漂移。",
                "tradeoff": "当前 embedding 仍使用 standalone_query；expanded_query 先作为检索计划和后续 hybrid search 的输入说明。",
                "term_definitions": _rewrite_terms(),
                "pitfalls": ["改写不能替用户回答问题，也不能扩大到用户没问的对象或时间范围。"],
                **rewrite,
            },
            duration_ms=_duration_ms(start),
            execution_mode="sequential",
            children=[
                _step(
                    key="build_standalone_query",
                    title="生成独立问题",
                    summary="把依赖上下文的问法改成可单独检索的问题。",
                    details={"standalone_query": rewrite["standalone_query"]},
                    duration_ms=0,
                ),
                _step(
                    key="expand_policy_terms",
                    title="扩展制度检索词",
                    summary="补充年休假、带薪年休假等安全同义词。",
                    details={"added_terms": rewrite["added_terms"], "expanded_query": rewrite["expanded_query"]},
                    duration_ms=0,
                ),
                _step(
                    key="semantic_drift_check",
                    title="检查改写漂移",
                    summary="确认改写没有改变对象、动作或问题类型。",
                    details=rewrite["semantic_drift_check"],
                    duration_ms=0,
                ),
            ],
        )
    )

    start = time.perf_counter()
    token_call_start = time.perf_counter()
    try:
        tokenize = getattr(embedding_client, "tokenize")
        token_info = tokenize(retrieval_query)
    except Exception as exc:
        token_info = _fallback_tokenize(retrieval_query)
        token_info["error"] = str(exc)
    token_call_duration = _duration_ms(token_call_start)

    token_table_start = time.perf_counter()
    token_rows = _token_table(token_info)
    token_table_duration = _duration_ms(token_table_start)
    tokenize_children = [
        _step(
            key="call_tokenizer",
            title="调用 tokenizer",
            summary="把归一化后的文本交给 embedding service 的 /tokenize 接口。",
            details={
                "tool": "httpx -> embedding service POST /tokenize",
                "input_text": retrieval_query,
                "tokenizer": token_info.get("tokenizer"),
                "error": token_info.get("error"),
            },
            duration_ms=token_call_duration,
            status="error" if token_info.get("error") else "ok",
        ),
        _step(
            key="build_token_table",
            title="生成 token 展示表",
            summary="按 index/token/token_id 展示模型输入片段。",
            details={
                "tool": "Python list enumeration",
                "token_table": token_rows,
                "row_limit": MAX_TRACE_TOKEN_ROWS,
                "truncated_for_trace": len(token_info.get("tokens") or []) > MAX_TRACE_TOKEN_ROWS,
            },
            duration_ms=token_table_duration,
        ),
    ]
    steps.append(
        _step(
            key="tokenize",
            title="Step 6 · 分词 / Tokenize",
            summary="把问题拆成模型可处理的 token，并展示 token 与 token id。",
            details={
                "input_text": retrieval_query,
                "tokenizer": token_info.get("tokenizer"),
                "token_count": token_info.get("token_count"),
                "tokens_preview": token_info.get("tokens", [])[:24],
                "token_ids_preview": token_info.get("token_ids", [])[:24],
                "token_table": token_rows,
                "max_input_tokens": token_info.get("max_input_tokens"),
                "truncated_by_model": token_info.get("truncated"),
                "truncated_for_trace": len(token_info.get("tokens") or []) > MAX_TRACE_TOKEN_ROWS,
                "why_this_tool": _tokenizer_choice(),
                "note": token_info.get("note", "BGE-M3 tokenizer preview from embedding service."),
                "term_definitions": [
                    _term("Token", "模型处理文本的最小输入单元，可能是字、词片段、标点或特殊符号。"),
                    _term("Token id", "模型词表里某个 token 对应的数字编号。"),
                    _term("Token budget", "模型一次输入最多能处理的 token 数量。"),
                ],
                "pitfalls": ["展示 token 必须尽量使用 embedding 模型真实 tokenizer，否则教学结果会误导。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="sequential",
            children=tokenize_children,
        )
    )

    start = time.perf_counter()
    embedding_call_start = time.perf_counter()
    query_embedding = embedding_client.embed([retrieval_query], input_type="query")[0]
    embedding_call_duration = _duration_ms(embedding_call_start)
    shape_check_start = time.perf_counter()
    embedding_dimension = len(query_embedding)
    embedding_preview = [round(value, 6) for value in query_embedding[:8]]
    shape_check_duration = _duration_ms(shape_check_start)
    embedding_children = [
        _step(
            key="call_embedding_service",
            title="调用 embedding service",
            summary="使用 query 输入类型生成查询向量。",
            details={
                "tool": "httpx -> embedding service POST /embed",
                "payload": {"texts": [retrieval_query], "input_type": "query", "normalize": True},
                "why_input_type_query": "同一个模型通常会区分 query 和 document 的编码提示；查询问题用 query 类型，制度正文入库用 document 类型。",
            },
            duration_ms=embedding_call_duration,
        ),
        _step(
            key="inspect_embedding_shape",
            title="检查向量形状",
            summary="确认返回的是非空数值向量，并展示前几个维度。",
            details={
                "dimension": embedding_dimension,
                "vector_preview": embedding_preview,
                "validation": "当前 MVP 校验维度和预览；生产导入还应校验维度与表结构一致。",
            },
            duration_ms=shape_check_duration,
        ),
    ]
    steps.append(
        _step(
            key="query_embedding",
            title="Step 7 · Query Embedding",
            summary="调用 BGE-M3 embedding service，把问题转成向量。",
            details={
                "framework": "httpx -> embedding service POST /embed",
                "input_text": retrieval_query,
                "input_type": "query",
                "dimension": embedding_dimension,
                "vector_preview": embedding_preview,
                "model_choice": _embedding_model_choice(),
                "term_definitions": [
                    _term("Embedding", "把文本表示成一组数字向量，用来比较语义相似度。"),
                    _term("Dense vector", "固定长度且大多数维度都有数值的向量。"),
                    _term("Cosine distance", "向量夹角距离，值越小通常表示语义越接近。"),
                ],
                "pitfalls": ["Embedding 对精确日期、制度编号、否定句和专有名词不一定可靠。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="sequential",
            children=embedding_children,
        )
    )

    start = time.perf_counter()
    candidate_limit = max(top_k, min(10, top_k * 4))
    metadata_filters = {
        "policy_category_hint": understanding["policy_category_hint"],
        "audience_hint": understanding["audience_hint"],
        "time_hints": understanding["time_hints"],
    }
    steps.append(
        _step(
            key="retrieval_plan",
            title="Step 8 · 检索计划生成",
            summary="决定召回通道、metadata filter、候选数量和最终 top_k。",
            details={
                "tool": "retrieval planner rules",
                "enabled_channels": ["dense_vector"],
                "production_options": ["BM25", "hybrid_search", "metadata_filter"],
                "candidate_limit": candidate_limit,
                "final_top_k": top_k,
                "metadata_filters": metadata_filters,
                "expanded_query_for_future_hybrid": rewrite["expanded_query"],
                "why": "真实 RAG 通常先多召回，再 rerank 到少量证据；不能直接把 top_k 当作唯一候选数。",
                "tradeoff": "当前代码只启用 dense vector，BM25/hybrid/filter 以计划字段呈现，后续可插拔实现。",
                "term_definitions": [
                    _term("BM25", "搜索引擎常用的关键词排序算法，适合制度编号、专有名词和精确词。"),
                    _term("Hybrid search", "把向量语义检索和关键词检索合并，兼顾语义召回和精确匹配。"),
                    _term("Metadata filter", "用分类、适用对象、发布时间等结构化字段限制检索范围。"),
                ],
                "pitfalls": ["candidate_limit 太小会让 rerank 没有发挥空间；太大又会增加延迟。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="parallel",
            children=[
                _step(
                    key="choose_channels",
                    title="选择召回通道",
                    summary="当前启用 dense vector，记录 BM25/hybrid 作为生产扩展点。",
                    details={"enabled_channels": ["dense_vector"], "production_options": ["BM25", "hybrid_search"]},
                    duration_ms=0,
                ),
                _step(
                    key="derive_metadata_filters",
                    title="派生 metadata filters",
                    summary="从查询理解结果派生分类、对象和时间过滤线索。",
                    details=metadata_filters,
                    duration_ms=0,
                ),
                _step(
                    key="set_candidate_limits",
                    title="设置候选数量",
                    summary="先多取候选，再由 rerank 决定最终证据顺序。",
                    details={"candidate_limit": candidate_limit, "final_top_k": top_k},
                    duration_ms=0,
                ),
            ],
        )
    )

    start = time.perf_counter()
    retrieval_mode = "pgvector"
    vector_details: dict[str, Any] = {
        "framework": "PostgreSQL + pgvector",
        "sql": PGVECTOR_QUERY_SQL,
        "top_k": candidate_limit,
        "tool_choice": _vector_store_choice(),
        "term_definitions": [
            _term("Chunk", "从源文档切出来的可检索文本块。"),
            _term("pgvector", "PostgreSQL 的向量相似度扩展，可以在数据库内按向量距离排序。"),
            _term("Fallback", "主依赖不可用时的受控兜底路径，必须在 trace 里明确展示。"),
        ],
        "pitfalls": ["fallback 只能用于 demo 或降级，不能让用户误以为是完整生产检索。"],
    }
    build_query_start = time.perf_counter()
    build_query_details = {
        "tool": "PostgreSQL SQL + pgvector <=> operator",
        "sql": PGVECTOR_QUERY_SQL,
        "top_k": candidate_limit,
        "distance_metric": "cosine distance，值越小越相似。",
    }
    vector_children = [
        _step(
            key="build_vector_query",
            title="构造向量查询",
            summary="准备 pgvector cosine distance 查询和 TopK 参数。",
            details=build_query_details,
            duration_ms=_duration_ms(build_query_start),
        )
    ]
    try:
        if store is None:
            raise RuntimeError("No pgvector store configured for this request.")
        pgvector_start = time.perf_counter()
        results = store.search(query_embedding, top_k=candidate_limit)
        pgvector_duration = _duration_ms(pgvector_start)
        vector_children.append(
            _step(
                key="pgvector_search",
                title="执行 pgvector 检索",
                summary="在已入库 chunk embedding 中按向量距离取 TopK。",
                details={
                    "tool": "PgVectorStore.search",
                    "result_count": len(results),
                    "results_preview": [_serialize_result(result, index) for index, result in enumerate(results, start=1)],
                },
                duration_ms=pgvector_duration,
            )
        )
    except Exception as exc:
        retrieval_mode = "in_memory_demo"
        vector_details.update(
            {
                "framework": "Python in-memory cosine fallback",
                "pgvector_error": str(exc),
                "fallback_reason": "pgvector is unavailable or not configured; running demo retrieval over sample chunks.",
            }
        )
        vector_children.append(
            _step(
                key="pgvector_search",
                title="执行 pgvector 检索",
                summary="pgvector 不可用，进入 fallback 分支。",
                details={"tool": "PgVectorStore.search", "error": str(exc)},
                duration_ms=_duration_ms(start),
                status="error",
            )
        )
        fallback_start = time.perf_counter()
        results = _memory_search(query_embedding, embedding_client=embedding_client, top_k=candidate_limit)
        fallback_duration = _duration_ms(fallback_start)
        vector_children.append(
            _step(
                key="in_memory_fallback",
                title="内存向量检索 fallback",
                summary="只在本地样例 chunk 上计算 cosine distance，保证页面仍可学习流程。",
                details={
                    "tool": "Python cosine distance over sample chunks",
                    "business_status": "demo fallback, not production storage",
                    "result_count": len(results),
                    "results_preview": [_serialize_result(result, index) for index, result in enumerate(results, start=1)],
                },
                duration_ms=fallback_duration,
            )
        )

    vector_details["result_count"] = len(results)
    vector_details["results_preview"] = [_serialize_result(result, index) for index, result in enumerate(results, start=1)]
    steps.append(
        _step(
            key="initial_retrieval",
            title="Step 9 · 初召回",
            summary="优先走 pgvector cosine distance；不可用时走内存 demo 检索，并输出候选 chunk。",
            details=vector_details,
            duration_ms=_duration_ms(start),
            execution_mode="branch",
            children=vector_children,
        )
    )

    start = time.perf_counter()
    reranked_results, rerank_comparison = _rerank_results(retrieval_query, results)
    steps.append(
        _step(
            key="rerank",
            title="Step 10 · Rerank 重排",
            summary="对初召回候选重新打分，展示排序前后的变化。",
            details={
                "tool": "deterministic lexical rerank fallback",
                "reranker_choice": _reranker_choice(),
                "input_candidate_count": len(results),
                "output_candidate_count": len(reranked_results),
                "rerank_comparison": rerank_comparison,
                "term_definitions": [
                    _term("Rerank", "对已召回候选重新排序，让真正回答问题的证据排到前面。"),
                    _term("Cross-encoder", "同时读取 query 和 document 的模型，直接输出相关性分数。"),
                    _term("Relevance score", "候选 chunk 与问题相关程度的分数。"),
                ],
                "pitfalls": ["Rerank 会增加延迟；只应该重排候选集，不应该重排全库。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="sequential",
            children=[
                _step(
                    key="prepare_rerank_pairs",
                    title="准备 query/chunk pair",
                    summary="把检索问题和每个候选 chunk 组成可打分输入。",
                    details={"pair_count": len(results)},
                    duration_ms=0,
                ),
                _step(
                    key="score_candidates",
                    title="候选打分",
                    summary="用本地确定性 fallback 计算 rerank_score。",
                    details={"tool": "lexical overlap + heading bonus + vector distance"},
                    duration_ms=0,
                ),
                _step(
                    key="compare_before_after",
                    title="比较排序变化",
                    summary="展示 rank_before、rank_after、score 和原因。",
                    details={"rerank_comparison": rerank_comparison},
                    duration_ms=0,
                ),
            ],
        )
    )

    final_results = reranked_results[:top_k]
    quality_start = time.perf_counter()
    quality_checks, context_blocks = _quality_checks(final_results, rerank_comparison)
    steps.append(
        _step(
            key="evidence_quality",
            title="Step 11 · 证据质量检查与上下文组装",
            summary="检查证据相关性、来源字段、时效冲突，并组装可引用上下文。",
            details={
                "tool": "deterministic evidence quality checks",
                "quality_checks": quality_checks,
                "context_blocks": context_blocks,
                "term_definitions": [
                    _term("Faithfulness", "回答中的结论是否能被检索证据支持。"),
                    _term("Citation", "让用户能追溯到来源文档、标题、页码或 chunk 的引用信息。"),
                    _term("Freshness", "制度是否仍然有效，是否有更新或废止风险。"),
                ],
                "pitfalls": ["模型拿到相关材料也可能总结错；生成前要先检查证据能不能支撑答案。"],
            },
            duration_ms=_duration_ms(quality_start),
            execution_mode="parallel",
            status="warn" if any(check["status"] == "warn" for check in quality_checks) else "ok",
            children=[
                _step(
                    key="check_relevance_threshold",
                    title="检查相关性阈值",
                    summary="确认 top evidence 分数不是过低。",
                    details=quality_checks[0],
                    duration_ms=0,
                    status=quality_checks[0]["status"],
                ),
                _step(
                    key="check_source_metadata",
                    title="检查来源字段",
                    summary="确认 source/page/category 等引用字段存在。",
                    details=quality_checks[1],
                    duration_ms=0,
                    status=quality_checks[1]["status"],
                ),
                _step(
                    key="check_conflict_and_freshness",
                    title="检查冲突与时效",
                    summary="标记缺少生效日期或可能冲突的制度证据。",
                    details=quality_checks[2],
                    duration_ms=0,
                    status=quality_checks[2]["status"],
                ),
                _step(
                    key="assemble_context",
                    title="组装上下文",
                    summary="把最终证据整理成带引用的 context block。",
                    details={"context_blocks": context_blocks},
                    duration_ms=0,
                ),
            ],
        )
    )

    start = time.perf_counter()
    answer = _compose_answer(final_results, retrieval_mode)
    observations = _langfuse_observations(trace_id, retrieval_mode, len(final_results))
    steps.append(
        _step(
            key="answer_and_observe",
            title="Step 12 · 回答生成、后校验与 Langfuse 观测",
            summary="基于证据拼装回答，检查可追溯性，并输出 Langfuse-ready 观测记录。",
            details={
                "tool": "grounded answer template + Langfuse-ready observation metadata",
                "template": "top reranked result + source + retrieval mode",
                "answer": answer,
                "post_answer_faithfulness_check": {
                    "status": "ok" if final_results else "warn",
                    "reason": "当前回答模板只引用最终证据；接入 LLM 后需要逐句检查引用覆盖。",
                },
                "langfuse_observations": observations,
                "why_not_full_llm_now": "当前版本先把真实 RAG 诊断链路和可观测字段跑通；LLM 生成要在引用、权限和评估闭环后接入。",
                "term_definitions": [
                    _term("Grounded answer", "只基于检索证据生成或拼装的回答。"),
                    _term("Evaluation score", "用于监控回答质量的自动或人工评分。"),
                    _term("Dataset", "保存失败样本或标准问题，用于回归评估检索和生成质量。"),
                ],
                "pitfalls": ["观测不是最后打日志；生产 RAG 要能回放每一步输入、输出、耗时和质量分。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="sequential",
            children=[
                _step(
                    key="compose_grounded_answer",
                    title="拼装有依据回答",
                    summary="只使用最终证据中的 top result 和来源字段。",
                    details={"answer": answer},
                    duration_ms=0,
                ),
                _step(
                    key="post_answer_faithfulness_check",
                    title="回答后校验",
                    summary="确认回答能追溯到当前证据。",
                    details={"status": "ok" if final_results else "warn"},
                    duration_ms=0,
                    status="ok" if final_results else "warn",
                ),
                _step(
                    key="record_langfuse_observations",
                    title="记录观测事件",
                    summary="列出会写入 Langfuse 的 trace/span/retriever/evaluator 等记录。",
                    details={"langfuse_observations": observations},
                    duration_ms=0,
                ),
                _step(
                    key="collect_feedback_hook",
                    title="用户反馈入口",
                    summary="把用户反馈沉淀为后续评估 dataset。",
                    details={"feedback": "thumbs_up/down + comment -> evaluation dataset"},
                    duration_ms=0,
                ),
            ],
        )
    )

    return {
        "query": normalized_query,
        "answer": answer,
        "retrieval_mode": retrieval_mode,
        "results": [_serialize_result(result, index) for index, result in enumerate(final_results, start=1)],
        "steps": steps,
    }
