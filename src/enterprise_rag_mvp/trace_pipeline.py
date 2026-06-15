from __future__ import annotations

import math
import re
import hashlib
import time
from typing import Any
from urllib.parse import quote

from enterprise_rag_mvp.answer_planner import plan_answer
from enterprise_rag_mvp.evidence_validator import assess_evidence
from enterprise_rag_mvp.models import PolicyChunk, SearchResult
from enterprise_rag_mvp.policy_rule_resolver import (
    ABSENTEEISM_BEHAVIOR,
    ABSENTEEISM_BEHAVIOR_TERMS,
    DISCIPLINARY_ACTION_ASPECT,
    SECTION_LISTING_ASPECT,
    aspect_terms as resolver_aspect_terms,
    build_policy_lookup_spec,
)
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
                "why_not_now": "***公司制度包含英文标题和中英混排，M3 的多语言能力更贴合。",
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


def _aspect_terms(aspect: str | None) -> list[str]:
    return resolver_aspect_terms(aspect)


def _policy_lookup_spec(query: str) -> dict[str, Any]:
    return build_policy_lookup_spec(query)

def _detect_query_understanding(query: str) -> dict[str, Any]:
    policy_category_hint = "general"
    if any(term in query for term in ["年假", "年休假", "薪酬", "员工", "HR", "考勤", "违规", "弄虚作假", "旷工", "迟到", "早退", "离岗", "骂人", "说脏话", "脏话", "辱骂", "语言不得体", "师德", "师德师风"]):
        if any(term in query for term in ["年假", "年休假"]):
            policy_category_hint = "leave"
        elif any(term in query for term in ["违规", "弄虚作假", "旷工", "骂人", "说脏话", "脏话", "辱骂", "语言不得体", "师德", "师德师风"]):
            policy_category_hint = "conduct"
        elif any(term in query for term in ["考勤", "迟到", "早退", "离岗"]):
            policy_category_hint = "attendance"
        else:
            policy_category_hint = "hr"
    elif any(term in query for term in ["报销", "采购", "发票", "财务"]):
        policy_category_hint = "finance"
    elif any(term in query for term in ["安全", "账号", "数据", "外传"]):
        policy_category_hint = "security"

    audience_hint = "employee" if any(term in query for term in ["员工", "老师", "教师", "HR", "违规", "弄虚作假", "旷工", "迟到", "早退", "离岗", "骂人", "说脏话", "脏话", "辱骂", "语言不得体", "师德", "师德师风"]) else "unknown"
    if any(term in query for term in ["学生", "幼儿园", "小学", "初中", "高中"]):
        audience_hint = "student_or_stage_specific"

    intent = "rule_lookup"
    if any(term in query for term in ["流程", "怎么申请", "如何申请"]):
        intent = "process_lookup"
    elif any(term in query for term in ["能不能", "是否", "可以吗"]):
        intent = "eligibility_check"
    elif any(term in query for term in ["区别", "对比", "比较"]):
        intent = "policy_comparison"

    policy_lookup = _policy_lookup_spec(query)
    if policy_lookup["retrieval_intent"] == "exact_policy_lookup":
        if policy_lookup.get("answer_aspect") == DISCIPLINARY_ACTION_ASPECT:
            intent = "policy_disciplinary_action_lookup"
        elif policy_lookup.get("answer_aspect") == SECTION_LISTING_ASPECT:
            intent = "policy_section_listing_lookup"
        else:
            intent = "policy_definition_lookup"

    ambiguity_flags: list[str] = []
    if audience_hint == "unknown":
        ambiguity_flags.append("missing_audience")
    if any(term in query for term in ["今年", "最新", "现在"]) and not any(char.isdigit() for char in query):
        ambiguity_flags.append("relative_time_without_year")

    extracted_terms = [
        term
        for term in [
            "员工",
            "年假",
            "年休假",
            "报销",
            "考勤",
            "安全",
            "违规",
            "二类违规",
            "弄虚作假",
            "虚假报销",
            "处罚",
            "处分",
            "处理",
            "旷工",
            "迟到",
            "早退",
            "离岗",
        ]
        if term in query
    ]
    return {
        "intent": intent,
        "policy_category_hint": policy_category_hint,
        "audience_hint": audience_hint,
        "time_hints": [term for term in ["今年", "最新", "现在", "2026"] if term in query],
        "ambiguity_flags": ambiguity_flags,
        "extracted_terms": extracted_terms,
        "aspect_terms": _aspect_terms(policy_lookup.get("asked_aspect")),
        **policy_lookup,
    }


def _rewrite_query(query: str, understanding: dict[str, Any]) -> dict[str, Any]:
    standalone_query = query
    if understanding.get("retrieval_intent") != "exact_policy_lookup":
        if understanding.get("audience_hint") == "employee" and "员工" not in standalone_query:
            standalone_query = f"员工{standalone_query}"
        if understanding.get("policy_category_hint") == "leave" and "规则" not in standalone_query:
            standalone_query = f"{standalone_query} 规则"

    expansions: list[str] = []
    if understanding.get("retrieval_intent") == "exact_policy_lookup":
        expansions.extend(understanding.get("target_terms") or [])
        if understanding.get("target_section"):
            expansions.append(understanding["target_section"])
        if understanding.get("target_clause"):
            expansions.append(understanding["target_clause"])
    else:
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
            "reason": "精确制度查询只补充同一目标章节/条款词；普通查询只补充同义词和制度检索词，没有改变用户的对象、动作或问题类型。",
        },
    }


def _lexical_terms(text: str) -> set[str]:
    terms = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    for token in text.replace("？", " ").replace("?", " ").split():
        if token:
            terms.add(token.lower())
    return terms


def _metadata_text(chunk: Any) -> str:
    metadata = chunk.metadata or {}
    values = []
    for value in metadata.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return " ".join(values)


def _section_marker_variants(section: str | None) -> list[str]:
    if not section:
        return []
    return [
        f"（一）{section}",
        f"（二）{section}",
        f"（三）{section}",
        f"{section}：",
        f"{section}:",
    ]


def _has_section_definition(text: str, target_section: str | None) -> bool:
    if not text or not target_section:
        return False
    if any(marker in text for marker in _section_marker_variants(str(target_section))):
        return True
    return bool(re.search(rf"{re.escape(str(target_section))}\s*[：:,，]?\s*指", text))


def _is_reference_only_text(text: str, understanding: dict[str, Any]) -> bool:
    if not text or understanding.get("retrieval_intent") != "exact_policy_lookup":
        return False
    target_markers = [
        str(item)
        for item in [
            understanding.get("target_clause"),
            understanding.get("target_subclause"),
            understanding.get("target_section"),
            *(understanding.get("target_terms") or []),
        ]
        if item
    ]
    if not any(marker in text for marker in target_markers):
        return False
    has_definition = _has_section_definition(text, understanding.get("target_section"))
    target_clause = understanding.get("target_clause")
    if target_clause and str(target_clause) in text:
        has_definition = True
    reference_words = ["参见", "详见", "参考", "参照", "见《", "具体参见"]
    return not has_definition and any(word in text for word in reference_words)


def _has_target_metadata_scope(metadata: dict[str, Any], understanding: dict[str, Any]) -> bool:
    section_path = metadata.get("section_path") or []
    target_section = understanding.get("target_section")
    target_clause = understanding.get("target_clause")
    if target_clause and (metadata.get("clause_title") == target_clause or target_clause in section_path):
        return True
    if target_section and (metadata.get("section_title") == target_section or target_section in section_path):
        return True
    return False


def _target_marker_variants(understanding: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    target_section = understanding.get("target_section")
    if target_section:
        section = str(target_section)
        markers.append(section)
        if section.endswith("行为"):
            markers.append(section.removesuffix("行为"))
    target_clause = understanding.get("target_clause")
    if target_clause:
        markers.append(str(target_clause))
    target_subclause = understanding.get("target_subclause")
    if target_subclause:
        markers.append(str(target_subclause))
    target_behavior_label = understanding.get("target_behavior_label")
    if target_behavior_label:
        markers.append(str(target_behavior_label))
    if "二类违规" in markers or understanding.get("target_section") == "二类违规行为":
        markers.extend(["二类、三类违规", "一类及二类违规", "二类及三类违规"])
    if "一类违规" in markers or understanding.get("target_section") == "一类违规行为":
        markers.extend(["一类及二类违规", "一类违规行为"])
    if "三类违规" in markers or understanding.get("target_section") == "三类违规行为":
        markers.extend(["二类、三类违规", "二类及三类违规", "三类违规行为"])
    if understanding.get("target_behavior") == ABSENTEEISM_BEHAVIOR:
        markers.extend(ABSENTEEISM_BEHAVIOR_TERMS)
    return list(dict.fromkeys(marker for marker in markers if marker))


def _has_target_marker(text: str, understanding: dict[str, Any]) -> bool:
    return any(marker in text for marker in _target_marker_variants(understanding))


def _has_aspect_signal(text: str, understanding: dict[str, Any]) -> bool:
    return any(term in text for term in _aspect_terms(understanding.get("asked_aspect")))


def _is_section_listing_query(understanding: dict[str, Any]) -> bool:
    intent_schema = understanding.get("intent_schema") or {}
    return (
        understanding.get("answer_aspect") == SECTION_LISTING_ASPECT
        or understanding.get("asked_aspect") == SECTION_LISTING_ASPECT
        or intent_schema.get("asked_aspect") == SECTION_LISTING_ASPECT
    )


def _listing_title_from_result(result: SearchResult, understanding: dict[str, Any]) -> str | None:
    target_section = understanding.get("target_section")
    heading_path = list(result.chunk.heading_path or [])
    if target_section and target_section in heading_path:
        section_index = heading_path.index(str(target_section))
        if section_index + 1 < len(heading_path):
            return heading_path[section_index + 1]
    metadata = result.chunk.metadata or {}
    clause_title = metadata.get("clause_title") or metadata.get("clauseTitle")
    if clause_title and clause_title != target_section:
        return str(clause_title)
    text = re.sub(r"\s+", " ", result.chunk.text)
    match = re.search(r"(?<!\d)(\d{1,2})\.\s*([^。；;：:]{2,40}?行为)", text)
    if match:
        return match.group(2).strip()
    return None


def _is_listing_evidence_result(result: SearchResult, understanding: dict[str, Any]) -> bool:
    if not _is_section_listing_query(understanding):
        return False
    target_section = understanding.get("target_section")
    haystack = " ".join([result.chunk.text, " ".join(result.chunk.heading_path), _metadata_text(result.chunk)])
    if not target_section or str(target_section) not in haystack:
        return False
    if "违规行为相应处理" in haystack:
        return False
    return _listing_title_from_result(result, understanding) is not None


def _has_violation_classification_signal(text: str) -> bool:
    return any(term in text for term in ["一类违规行为", "二类违规行为", "三类违规行为", "破坏学校管理秩序行为"])


def _is_direct_target_evidence(result: SearchResult, understanding: dict[str, Any]) -> bool:
    if understanding.get("retrieval_intent") != "exact_policy_lookup":
        return True
    text = result.chunk.text
    metadata = result.chunk.metadata or {}
    target_clause = understanding.get("target_clause")
    target_subclause = understanding.get("target_subclause")
    target_section = understanding.get("target_section")
    if _is_reference_only_text(text, understanding):
        return False
    if understanding.get("target_behavior") == ABSENTEEISM_BEHAVIOR:
        return _has_target_marker(text, understanding) and (
            _has_aspect_signal(text, understanding) or _has_violation_classification_signal(text)
        )
    if understanding.get("target_behavior"):
        has_marker = _has_target_marker(text, understanding)
        has_classification = _has_violation_classification_signal(text) or bool(target_clause and str(target_clause) in text) or bool(target_subclause and str(target_subclause) in text)
        if understanding.get("asked_aspect") == DISCIPLINARY_ACTION_ASPECT:
            return has_marker and (_has_aspect_signal(text, understanding) or has_classification)
        return has_marker or has_classification
    if understanding.get("asked_aspect") == DISCIPLINARY_ACTION_ASPECT:
        return _has_target_marker(text, understanding) and _has_aspect_signal(text, understanding)
    if target_clause and str(target_clause) in text:
        return True
    if target_subclause and str(target_subclause) in text:
        return True
    if _has_section_definition(text, str(target_section) if target_section else None):
        return True
    if _has_target_metadata_scope(metadata, understanding):
        return True
    scope = metadata.get("scope") if isinstance(metadata, dict) else None
    return bool(isinstance(scope, dict) and scope.get("applied"))


SEMANTIC_TOPIC_TERMS_BY_CATEGORY = {
    "leave": ["年假", "年休假", "带薪年休假", "休假管理办法"],
    "attendance": ["考勤", "迟到", "早退", "旷工", "离岗"],
    "finance": ["报销", "采购", "发票", "财务", "票据"],
    "security": ["安全", "账号", "数据", "外传", "凭证"],
    "conduct": ["违规", "处分", "处罚", "旷工", "弄虚作假", "虚假报销", "纪律"],
}


def _semantic_topic_terms(understanding: dict[str, Any]) -> list[str]:
    terms = [str(term) for term in understanding.get("extracted_terms") or [] if str(term) != "员工"]
    category_terms = SEMANTIC_TOPIC_TERMS_BY_CATEGORY.get(str(understanding.get("policy_category_hint") or ""), [])
    for term in category_terms:
        if term not in terms:
            terms.append(term)
    return terms


def _filter_semantic_topic_evidence(results: list[SearchResult], understanding: dict[str, Any]) -> tuple[list[SearchResult], dict[str, Any]]:
    audience = understanding.get("audience_hint") or (understanding.get("intent_schema") or {}).get("audience")
    if audience in {"student", "student_or_stage_specific"}:
        student_terms = ["学生", "幼儿园", "小学", "初中", "高中", "学段", "家长"]
        retained = []
        for result in results:
            metadata = result.chunk.metadata or {}
            declared_audience = str(metadata.get("audience") or metadata.get("target_audience") or "")
            scope_text = " ".join([" ".join(result.chunk.heading_path), str(metadata.get("source", "")), str(metadata.get("title", "")), str(metadata.get("policy_type", "")), declared_audience])
            if declared_audience in {"student", "student_or_stage_specific"} or (any(term in scope_text for term in student_terms) and "员工" not in scope_text):
                retained.append(result)
        if not retained:
            return [], {
                "applied": True,
                "audience": audience,
                "input_count": len(results),
                "output_count": 0,
                "dropped_chunk_ids": [result.chunk.chunk_id for result in results],
                "reason": "用户问题指向学生或学段，但当前候选没有学生/学段适用范围；为避免套用员工制度，拒绝作为最终证据。",
            }
        results = retained

    topic_terms = _semantic_topic_terms(understanding)
    if not topic_terms:
        return results, {"applied": False, "reason": "普通语义查询没有明确主题词，不做最终证据过滤。"}
    retained = []
    for result in results:
        haystack = " ".join([result.chunk.text, " ".join(result.chunk.heading_path), _metadata_text(result.chunk)])
        if any(term in haystack for term in topic_terms):
            retained.append(result)
    if not retained:
        return results, {
            "applied": False,
            "topic_terms": topic_terms,
            "reason": "未找到命中主题词的候选，保守保留原候选并交给质量检查。",
        }
    return retained, {
        "applied": True,
        "topic_terms": topic_terms,
        "input_count": len(results),
        "output_count": len(retained),
        "dropped_chunk_ids": [result.chunk.chunk_id for result in results if result not in retained],
        "reason": "普通语义查询按主题词过滤最终证据，避免把只因泛词或向量距离接近的候选展示为相关来源。",
    }


def _classify_evidence(result: SearchResult, understanding: dict[str, Any]) -> dict[str, Any]:
    text = result.chunk.text
    general_assessment = assess_evidence(result.chunk, understanding.get("intent_schema") or {})
    evidence_type = "semantic_candidate"
    usable_as_final = True
    reason = "普通语义候选，非精确制度查询不做强过滤。"

    if understanding.get("retrieval_intent") == "exact_policy_lookup":
        if _is_section_listing_query(understanding):
            if _is_listing_evidence_result(result, understanding):
                evidence_type = "listing_evidence"
                reason = "片段是目标章节下的分类小节，可用于回答‘有哪些/包括哪些’。"
            else:
                evidence_type = "irrelevant_or_insufficient_evidence"
                usable_as_final = False
                reason = "用户问的是章节分类列表；该片段不是分类小节，或属于处理/处罚条款。"
        elif _is_reference_only_text(text, understanding):
            evidence_type = "cross_reference_evidence"
            usable_as_final = False
            reason = "片段只提供参见或线索，不能直接回答；可作为二跳检索线索。"
        elif understanding.get("target_behavior") and _is_direct_target_evidence(result, understanding):
            evidence_type = "direct_behavior_evidence"
            reason = "片段包含用户行为、规则条件、分类或问题面证据，可作为行为型规则答案证据。"
        elif _is_direct_target_evidence(result, understanding):
            evidence_type = "direct_section_evidence"
            reason = "片段包含目标章节、条款或定义正文，可作为章节型答案证据。"
        else:
            evidence_type = "irrelevant_or_insufficient_evidence"
            usable_as_final = False
            reason = "片段缺少目标章节/条款/行为本体或问题面，不能支撑当前回答。"

    return {
        "chunk_id": result.chunk.chunk_id,
        "title": " > ".join(result.chunk.heading_path) if result.chunk.heading_path else result.chunk.doc_id,
        "evidence_type": evidence_type,
        "usable_as_final": usable_as_final,
        "general_evidence_assessment": general_assessment.to_dict(),
        "reason": reason,
    }


def _filter_target_evidence(results: list[SearchResult], understanding: dict[str, Any]) -> tuple[list[SearchResult], dict[str, Any]]:
    if understanding.get("retrieval_intent") != "exact_policy_lookup":
        return _filter_semantic_topic_evidence(results, understanding)
    evidence_classifications = [_classify_evidence(result, understanding) for result in results]
    usable_chunk_ids = {item["chunk_id"] for item in evidence_classifications if item["usable_as_final"]}
    direct_results = [result for result in results if result.chunk.chunk_id in usable_chunk_ids]
    cross_reference_ids = [item["chunk_id"] for item in evidence_classifications if item["evidence_type"] == "cross_reference_evidence"]
    if not direct_results:
        return [], {
            "applied": True,
            "input_count": len(results),
            "output_count": 0,
            "dropped_chunk_ids": [result.chunk.chunk_id for result in results],
            "cross_reference_chunk_ids": cross_reference_ids,
            "evidence_classifications": evidence_classifications,
            "reason": "没有找到明确的目标章节/条款/行为本体；参见型片段只保留为线索，不直接生成答案。",
        }
    dropped = [result.chunk.chunk_id for result in results if result not in direct_results]
    return direct_results, {
        "applied": True,
        "input_count": len(results),
        "output_count": len(direct_results),
        "dropped_chunk_ids": dropped,
        "cross_reference_chunk_ids": cross_reference_ids,
        "evidence_classifications": evidence_classifications,
        "retained_evidence_types": sorted({item["evidence_type"] for item in evidence_classifications if item["usable_as_final"]}),
        "reason": "精确制度查询按 direct_section_evidence、direct_behavior_evidence、cross_reference_evidence 分类；最终答案只使用直接证据。",
    }


def _external_reranker_scores(
    query: str,
    results: list[SearchResult],
    reranker_client: Any | None,
) -> tuple[list[float] | None, str, str | None]:
    if reranker_client is None:
        return None, "deterministic_fallback", None
    provider = str(getattr(reranker_client, "provider", "external_reranker"))
    try:
        scores = reranker_client.rerank(query=query, documents=[result.chunk.text for result in results])
        if len(scores) != len(results):
            return None, f"{provider}_invalid_fallback", f"expected {len(results)} scores, got {len(scores)}"
        return [float(score) for score in scores], provider, None
    except Exception as exc:
        return None, f"{provider}_failed_fallback", str(exc)


def _rerank_results(
    query: str,
    results: list[SearchResult],
    understanding: dict[str, Any] | None = None,
    *,
    reranker_client: Any | None = None,
) -> tuple[list[SearchResult], list[dict[str, Any]]]:
    understanding = understanding or {}
    query_terms = _lexical_terms(query)
    target_terms = [str(term) for term in understanding.get("target_terms") or []]
    target_section = understanding.get("target_section")
    target_clause = understanding.get("target_clause")
    target_behavior = understanding.get("target_behavior")
    preferred_policy_titles = [str(item) for item in understanding.get("preferred_policy_titles") or []]
    asked_aspect = understanding.get("asked_aspect")
    exclude_sections = [str(item) for item in understanding.get("exclude_sections") or []]
    exclude_clauses = [str(item) for item in understanding.get("exclude_clauses") or []]
    external_scores, reranker_source, reranker_error = _external_reranker_scores(query, results, reranker_client)
    scored: list[tuple[float, float, float | None, int, SearchResult, str]] = []
    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        metadata = chunk.metadata or {}
        haystack = " ".join([chunk.text, " ".join(chunk.heading_path), _metadata_text(chunk)])
        overlap = len(query_terms.intersection(_lexical_terms(haystack)))
        heading_bonus = 2 if any(term in "".join(chunk.heading_path) for term in ["年假", "年休假", "休假"]) else 0
        exact_bonus = 0.0
        reasons: list[str] = []
        for term in target_terms:
            if term and term in haystack:
                exact_bonus += 1.0
        if exact_bonus:
            reasons.append("命中精确制度词")
        section_path = metadata.get("section_path") or []
        if target_section and (metadata.get("section_title") == target_section or target_section in section_path or target_section in "".join(chunk.heading_path)):
            exact_bonus += 3.0
            reasons.append("命中目标章节")
        if target_section and _has_section_definition(chunk.text, str(target_section)):
            exact_bonus += 4.0
            reasons.append("命中章节定义正文")
        if target_clause and (metadata.get("clause_title") == target_clause or target_clause in section_path or target_clause in chunk.text):
            exact_bonus += 4.0
            reasons.append("命中目标条款组")
        if asked_aspect and _has_target_marker(haystack, understanding):
            exact_bonus += 2.0
            reasons.append("命中目标对象")
        if target_behavior and _has_target_marker(haystack, understanding):
            exact_bonus += 4.0
            reasons.append("命中行为对象")
        if preferred_policy_titles and any(title in haystack for title in preferred_policy_titles):
            exact_bonus += 4.0
            reasons.append("命中优先制度")
        if asked_aspect and _has_aspect_signal(haystack, understanding):
            exact_bonus += 5.0
            reasons.append("命中问题面")

        penalty = 0.0
        if understanding.get("retrieval_intent") == "exact_policy_lookup" and target_section:
            if not _is_direct_target_evidence(result, understanding):
                penalty += 3.0
                reasons.append("缺少目标章节/条款/行为本体，已降权")
            if _is_reference_only_text(chunk.text, understanding):
                penalty += 6.0
                reasons.append("仅为参见型片段，不能作为最终证据")
        if target_behavior and not _has_target_marker(haystack, understanding):
            penalty += 6.0
            reasons.append("缺少行为对象，已降权")
        if asked_aspect and not _has_aspect_signal(haystack, understanding):
            penalty += 5.0
            reasons.append("缺少问题面证据，已降权")
        leaked = [item for item in [*exclude_sections, *exclude_clauses] if item and item in haystack]
        if leaked:
            penalty += 0.8 * len(leaked)
            reasons.append("包含竞争章节，已降权")
        distance_score = max(0.0, 1.0 - result.distance)
        deterministic_score = round(overlap * 0.2 + heading_bonus * 0.15 + exact_bonus + distance_score - penalty, 4)
        reranker_score = external_scores[index - 1] if external_scores is not None else None
        if reranker_score is not None:
            reasons.append(f"cross-encoder reranker_score={round(reranker_score, 4)}")
        combined_score = round(deterministic_score + (reranker_score or 0.0), 4)
        reason = "；".join(reasons) if reasons else ("命中查询词和标题信号" if overlap or heading_bonus else "主要依赖向量距离，词项证据较弱")
        scored.append((combined_score, deterministic_score, reranker_score, index, result, reason))

    scored.sort(key=lambda item: (-item[0], item[3]))
    reranked = [item[4] for item in scored]
    comparison = [
        {
            "chunk_id": result.chunk.chunk_id,
            "title": " > ".join(result.chunk.heading_path) if result.chunk.heading_path else result.chunk.doc_id,
            "rank_before": rank_before,
            "rank_after": rank_after,
            "rerank_score": score,
            "deterministic_score": deterministic_score,
            "reranker_score": reranker_score,
            "reranker_source": reranker_source,
            "reranker_error": reranker_error,
            "distance": round(result.distance, 6),
            "reason": reason,
            "target_section": target_section,
            "target_clause": target_clause,
            "target_behavior": target_behavior,
            "asked_aspect": asked_aspect,
        }
        for rank_after, (score, deterministic_score, reranker_score, rank_before, result, reason) in enumerate(scored, start=1)
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
    if import_information_id is not None and metadata.get("source") == "company_policy_system":
        return "https://example.com/policyDetail/" + quote(str(import_information_id))
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



def _marker_variants(marker: str | None) -> list[str]:
    if not marker:
        return []
    variants = [marker]
    variants.append(marker.replace(". ", "."))
    variants.append(marker.replace(".", ". ", 1) if "." in marker else marker)
    return list(dict.fromkeys(variants))


def _find_first_marker(text: str, markers: list[str], *, start: int = 0) -> tuple[int, str | None]:
    matches = [(text.find(marker, start), marker) for marker in markers if marker]
    matches = [(index, marker) for index, marker in matches if index >= 0]
    if not matches:
        return -1, None
    return min(matches, key=lambda item: item[0])


def _next_clause_marker(clause_no: str | None) -> str | None:
    if not clause_no:
        return None
    try:
        return f"{int(clause_no) + 1}."
    except ValueError:
        return None


def _trim_end_marker_prefix(text: str, end_index: int) -> tuple[int, str | None]:
    if end_index <= 0:
        return end_index, None
    prefix = text[max(0, end_index - 16):end_index]
    numbered = re.search(r"(?:^|\s)(\d{1,2}(?:\.\d+)*\s*)$", prefix)
    if numbered:
        marker_prefix = numbered.group(1)
        return end_index - len(marker_prefix), marker_prefix.strip()
    bracketed = re.search(r"([（(][一二三四五六七八九十]+[）)]\s*)$", prefix)
    if bracketed:
        marker_prefix = bracketed.group(1)
        return end_index - len(marker_prefix), marker_prefix.strip()
    return end_index, None


def _disciplinary_action_scope(text: str, understanding: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if understanding.get("asked_aspect") != DISCIPLINARY_ACTION_ASPECT:
        return None
    target_section = understanding.get("target_section")
    if not target_section:
        return None
    section = str(target_section)
    level_markers = {
        "一类违规行为": {"starts": ["1.1一类违规行为", "1.1 一类违规行为", "一类违规行为："], "ends": ["1.2二类违规行为", "1.2 二类违规行为", "1.2二类违规"]},
        "二类违规行为": {"starts": ["1.2二类违规行为", "1.2 二类违规行为", "二类违规行为："], "ends": ["1.3三类违规行为", "1.3 三类违规行为", "1.3三类违规", "1.4 ", "2. 其他处分规定", "2.其他处分规定"]},
        "三类违规行为": {"starts": ["1.3三类违规行为", "1.3 三类违规行为", "三类违规行为："], "ends": ["1.4 ", "2. 其他处分规定", "2.其他处分规定"]},
    }
    markers = level_markers.get(section)
    if not markers:
        return None
    if not any(signal in text for signal in ["违规行为相应处理", "处分", "处理", "调薪", "年终奖", "解除劳动合同", "警告"]):
        return None
    start_index, start_marker = _find_first_marker(text, markers["starts"])
    if start_index < 0:
        return None
    end_index, end_marker = _find_first_marker(text, markers["ends"], start=start_index + len(start_marker or ""))
    end_marker_prefix = None
    if end_index < 0:
        end_index = len(text)
    else:
        end_index, end_marker_prefix = _trim_end_marker_prefix(text, end_index)
    scoped = text[start_index:end_index].strip()
    if not scoped:
        return None
    return scoped, {
        "applied": True,
        "start_marker": start_marker,
        "end_marker": end_marker,
        "end_marker_prefix_trimmed": end_marker_prefix,
        "scope_type": "disciplinary_action_by_violation_level",
    }


def _extract_scoped_text(text: str, understanding: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    target_clause = understanding.get("target_clause")
    target_section = understanding.get("target_section")
    target_behavior = understanding.get("target_behavior")
    exclude_sections = [str(item) for item in understanding.get("exclude_sections") or []]
    exclude_clauses = [str(item) for item in understanding.get("exclude_clauses") or []]
    scope = {
        "applied": False,
        "target_section": target_section,
        "target_clause": target_clause,
        "target_behavior": target_behavior,
        "behavior_threshold": understanding.get("behavior_threshold"),
        "start_marker": None,
        "end_marker": None,
        "excluded_markers": [*exclude_sections, *exclude_clauses],
    }
    if not text or understanding.get("retrieval_intent") != "exact_policy_lookup":
        return text, scope

    action_scope = _disciplinary_action_scope(text, understanding)
    if action_scope and (not target_clause or str(target_clause) not in text):
        scoped, action_scope_details = action_scope
        scope.update(action_scope_details)
        return scoped, scope

    if target_clause:
        start_markers = _marker_variants(str(target_clause))
        start_index, start_marker = _find_first_marker(text, start_markers)
        if start_index < 0:
            return text, scope
        next_clause = _next_clause_marker(understanding.get("target_clause_no"))
        end_markers = [*exclude_clauses]
        for section in exclude_sections:
            end_markers.extend([f"（一）{section}", f"（二）{section}", f"（三）{section}", str(section)])
        if next_clause:
            end_markers.extend([next_clause, f" {next_clause}"])
        end_index, end_marker = _find_first_marker(text, end_markers, start=start_index + len(start_marker or ""))
    elif target_section:
        start_markers = [f"（二）{target_section}", f"（一）{target_section}", f"（三）{target_section}", f"{target_section}：", str(target_section)]
        start_index, start_marker = _find_first_marker(text, start_markers)
        if start_index < 0:
            return text, scope
        end_markers = []
        for section in exclude_sections:
            end_markers.extend([f"（一）{section}", f"（二）{section}", f"（三）{section}", str(section)])
        end_index, end_marker = _find_first_marker(text, end_markers, start=start_index + len(start_marker or ""))
    elif target_behavior == ABSENTEEISM_BEHAVIOR:
        threshold = understanding.get("behavior_threshold")
        if (
            threshold == "continuous_absence_under_3_workdays"
            and "旷工少于三天" in text
            and _has_violation_classification_signal(text)
        ):
            start_markers = ["（二）二类违规行为", "(二)二类违规行为", "二类违规行为：", "二类违规行为"]
            end_markers = ["（三）三类违规行为", "(三)三类违规行为", "三类违规行为"]
        elif threshold == "continuous_absence_under_3_workdays":
            start_markers = ["连续旷工3个工作日以下", "连续旷工 3 个工作日以下", "旷工3个工作日以下"]
            end_markers = ["连续旷工3个工作日及以上", "连续旷工 3 个工作日及以上", "考勤结果", "五、假期标准"]
        elif threshold == "continuous_absence_3_or_more_workdays":
            start_markers = ["连续旷工3个工作日及以上", "连续旷工 3 个工作日及以上", "一年内累计两次及以上旷工"]
            end_markers = ["考勤结果", "五、假期标准"]
        else:
            start_markers = ["（三） 旷工", "（三）旷工", "旷工 凡符合", "连续旷工"]
            end_markers = ["考勤结果", "五、假期标准"]
        start_index, start_marker = _find_first_marker(text, start_markers)
        if start_index < 0:
            return text, scope
        end_index, end_marker = _find_first_marker(text, end_markers, start=start_index + len(start_marker or ""))
    else:
        return text, scope

    end_marker_prefix = None
    if end_index < 0:
        end_index = len(text)
    else:
        end_index, end_marker_prefix = _trim_end_marker_prefix(text, end_index)
    scoped = text[start_index:end_index].strip()
    if not scoped:
        return text, scope
    scope.update({"applied": True, "start_marker": start_marker, "end_marker": end_marker, "end_marker_prefix_trimmed": end_marker_prefix})
    return scoped, scope


def _scope_result(result: SearchResult, understanding: dict[str, Any]) -> SearchResult:
    scoped_text, scope = _extract_scoped_text(result.chunk.text, understanding)
    if not scope["applied"]:
        return result
    metadata = {**(result.chunk.metadata or {}), "scope": scope, "scoped_text_applied": True}
    chunk = PolicyChunk(
        chunk_id=result.chunk.chunk_id,
        doc_id=result.chunk.doc_id,
        block_id=result.chunk.block_id,
        text=scoped_text,
        heading_path=result.chunk.heading_path,
        metadata=metadata,
    )
    return SearchResult(chunk=chunk, distance=result.distance)


def _scope_results(results: list[SearchResult], understanding: dict[str, Any]) -> list[SearchResult]:
    return [_scope_result(result, understanding) for result in results]


def _evidence_key(result: SearchResult, understanding: dict[str, Any]) -> tuple[Any, ...]:
    metadata = result.chunk.metadata or {}
    doc_id = result.chunk.doc_id
    target_behavior = understanding.get("target_behavior")
    if target_behavior == ABSENTEEISM_BEHAVIOR:
        text = result.chunk.text
        if "扣除旷工期间工资" in text or "连续旷工" in text or "一年内累计两次及以上旷工" in text:
            return (doc_id, "behavior_penalty")
        if _has_violation_classification_signal(text):
            return (doc_id, "behavior_classification")
        return (doc_id, "behavior_support")
    if target_behavior:
        text = result.chunk.text
        target_label = understanding.get("target_behavior_label")
        target_clause = understanding.get("target_clause")
        target_subclause = understanding.get("target_subclause")
        has_specific_behavior = bool(target_label and str(target_label) in text) or bool(target_clause and str(target_clause) in text) or bool(target_subclause and str(target_subclause) in text)
        if _has_aspect_signal(text, understanding) and understanding.get("target_section") in text:
            return (doc_id, target_behavior, "violation_level_penalty")
        if has_specific_behavior:
            return (doc_id, target_behavior, "behavior_classification")
        return (doc_id, target_behavior, "behavior_support", result.chunk.block_id or result.chunk.chunk_id)
    if understanding.get("target_clause"):
        return (doc_id, metadata.get("section_title") or understanding.get("target_section"), metadata.get("clause_title") or understanding.get("target_clause"))
    if _is_section_listing_query(understanding) and understanding.get("target_section"):
        listing_title = _listing_title_from_result(result, understanding)
        return (
            doc_id,
            metadata.get("section_title") or understanding.get("target_section"),
            listing_title or result.chunk.block_id or tuple(result.chunk.heading_path) or result.chunk.chunk_id,
        )
    if understanding.get("target_section"):
        return (doc_id, metadata.get("section_title") or understanding.get("target_section"))
    section_path = metadata.get("section_path")
    if section_path:
        return (doc_id, tuple(section_path))
    return (doc_id, result.chunk.block_id or result.chunk.chunk_id)


def _dedupe_evidence(results: list[SearchResult], understanding: dict[str, Any]) -> tuple[list[SearchResult], dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduped: list[SearchResult] = []
    duplicate_chunk_ids: list[str] = []
    for result in results:
        key = _evidence_key(result, understanding)
        if key in seen:
            duplicate_chunk_ids.append(result.chunk.chunk_id)
            continue
        seen.add(key)
        deduped.append(result)
    return deduped, {
        "input_count": len(results),
        "output_count": len(deduped),
        "removed_duplicates": len(duplicate_chunk_ids),
        "duplicate_chunk_ids": duplicate_chunk_ids,
    }


def _find_behavior_classification_result(results: list[SearchResult], understanding: dict[str, Any]) -> SearchResult | None:
    if not understanding.get("target_behavior") or understanding.get("target_behavior") == ABSENTEEISM_BEHAVIOR:
        return None
    target_clause = understanding.get("target_clause")
    target_subclause = understanding.get("target_subclause")
    target_label = understanding.get("target_behavior_label")
    target_section = understanding.get("target_section")
    for result in results:
        text = result.chunk.text
        metadata_without_scope = {key: value for key, value in (result.chunk.metadata or {}).items() if key not in {"scope", "scoped_text_applied"}}
        metadata_text = " ".join(str(value) for value in metadata_without_scope.values())
        haystack = " ".join([text, " ".join(result.chunk.heading_path), metadata_text])
        has_violation_scope = _has_violation_classification_signal(haystack)
        if target_section and str(target_section) not in haystack:
            continue
        if target_subclause and str(target_subclause) in text and has_violation_scope:
            return result
        if target_label and str(target_label) in text and has_violation_scope:
            return result
        if target_clause and str(target_clause) in text and has_violation_scope and not _has_aspect_signal(text, understanding):
            return result
    return None


def _find_behavior_penalty_result(results: list[SearchResult], understanding: dict[str, Any]) -> SearchResult | None:
    if not understanding.get("target_behavior") or understanding.get("target_behavior") == ABSENTEEISM_BEHAVIOR:
        return None
    target_section = understanding.get("target_section")
    for result in results:
        text = result.chunk.text
        if target_section and str(target_section) in text and _has_aspect_signal(text, understanding):
            return result
    return None


def _select_behavior_final_results(results: list[SearchResult], understanding: dict[str, Any]) -> list[SearchResult]:
    target_behavior = understanding.get("target_behavior")
    if not target_behavior:
        return results
    if target_behavior == ABSENTEEISM_BEHAVIOR:
        penalty_result = _find_absenteeism_penalty_result(results)
        classification_result = _find_absenteeism_classification_result(results, understanding)
        selected: list[SearchResult] = []
        for result in [penalty_result, classification_result]:
            if result is not None and result not in selected:
                selected.append(result)
        return selected or results

    classification_result = _find_behavior_classification_result(results, understanding)
    penalty_result = _find_behavior_penalty_result(results, understanding) if understanding.get("asked_aspect") == DISCIPLINARY_ACTION_ASPECT else None
    selected = []
    for result in [classification_result, penalty_result]:
        if result is not None and result not in selected:
            selected.append(result)
    return selected or results


def _scope_guard(texts: list[str], understanding: dict[str, Any]) -> dict[str, Any]:
    forbidden = [str(item) for item in [*(understanding.get("exclude_sections") or []), *(understanding.get("exclude_clauses") or [])] if item]
    joined = " ".join(texts)
    leaked = [marker for marker in forbidden if marker in joined]
    return {
        "status": "ok" if not leaked else "warn",
        "forbidden_markers": forbidden,
        "leaked_markers": leaked,
        "reason": "答案和上下文没有包含竞争章节。" if not leaked else "检测到用户未询问的相邻章节，需要截断或重写。",
    }


def _quality_checks(
    results: list[SearchResult],
    rerank_comparison: list[dict[str, Any]],
    *,
    understanding: dict[str, Any] | None = None,
    citation_merge: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, Any]]:
    understanding = understanding or {}
    citation_merge = citation_merge or {"removed_duplicates": 0}
    top_score = rerank_comparison[0]["rerank_score"] if rerank_comparison else 0
    guard = _scope_guard([result.chunk.text for result in results], understanding)
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
        {
            "name": "scope_guard",
            "status": guard["status"],
            "reason": guard["reason"],
        },
        {
            "name": "citation_merge",
            "status": "ok",
            "reason": f"合并重复来源 {citation_merge.get('removed_duplicates', 0)} 条。",
        },
    ]
    context_blocks = []
    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        citation = _citation_for_result(result, index)
        scope = chunk.metadata.get("scope") if isinstance(chunk.metadata, dict) else None
        context_blocks.append(
            {
                "chunk_id": chunk.chunk_id,
                "title": citation["title"],
                "text": chunk.text,
                "source": chunk.metadata.get("source", chunk.doc_id),
                "page": chunk.metadata.get("page"),
                "citation": citation,
                "scope": scope or {"applied": False},
            }
        )
    return checks, context_blocks, guard


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


def _mode_label(retrieval_mode: str) -> str:
    mode_labels = {
        "pgvector_hybrid": "pgvector hybrid",
        "pgvector": "pgvector",
        "in_memory_demo": "内存向量检索 demo",
    }
    return mode_labels.get(retrieval_mode, retrieval_mode)


def _source_lines(results: list[SearchResult]) -> list[str]:
    source_lines = []
    for index, result in enumerate(results, start=1):
        citation = _citation_for_result(result, index)
        meta_parts = [part for part in [citation.get("category"), citation.get("publish_date")] if part]
        meta = f"（{' / '.join(str(part) for part in meta_parts)}）" if meta_parts else ""
        has_url = bool(citation.get("url"))
        location = citation.get("url") or citation.get("source") or citation.get("doc_id")
        location_label = "链接" if has_url else "位置"
        source_lines.append(f"{citation['citation_id']}《{citation['title']}》{meta} {location_label}：{location}")
    return source_lines


def _find_absenteeism_penalty_result(results: list[SearchResult]) -> SearchResult | None:
    for result in results:
        text = result.chunk.text
        if "旷工" in text and any(term in text for term in ["扣除旷工期间工资", "记过处分", "辞退处分"]):
            return result
    return None


def _find_absenteeism_classification_result(results: list[SearchResult], understanding: dict[str, Any] | None = None) -> SearchResult | None:
    understanding = understanding or {}
    rule_resolution = understanding.get("rule_resolution") or {}
    classification_terms = [str(term) for term in rule_resolution.get("classification_terms") or []]
    target_category = next((term for term in ["一类违规行为", "二类违规行为", "三类违规行为"] if term in classification_terms), None)

    if target_category:
        specific_terms = [
            term
            for term in classification_terms
            if term != target_category and term not in {"破坏学校管理秩序行为"}
        ]
        for result in results:
            text = result.chunk.text
            if target_category not in text or not _has_violation_classification_signal(text):
                continue
            if any(term in text for term in specific_terms) or "旷工" in text:
                return result
        return None

    if understanding.get("target_behavior") == ABSENTEEISM_BEHAVIOR and not rule_resolution:
        for result in results:
            text = result.chunk.text
            if "旷工少于三天" in text and _has_violation_classification_signal(text):
                return result
    return None


def _absenteeism_classification_label(result: SearchResult | None, understanding: dict[str, Any] | None = None) -> str | None:
    if result is None:
        return None
    understanding = understanding or {}
    text = result.chunk.text
    rule_terms = list((understanding.get("rule_resolution") or {}).get("classification_terms") or [])
    category = next((candidate for candidate in ["一类违规行为", "二类违规行为", "三类违规行为"] if candidate in rule_terms), None)
    clause = next((term for term in rule_terms if re.match(r"\d+\.\d+", str(term))), None)
    if clause:
        clause = str(clause).replace(". ", ".")
    if not clause:
        clause_match = re.search(r"(\d+\.\s*\d+\s*旷工少于三天)", text)
        clause = clause_match.group(1).replace(". ", ".") if clause_match else None
        category_scan_end = clause_match.start() if clause_match else len(text)
    else:
        clause_match = re.search(re.escape(clause), text)
        category_scan_end = clause_match.start() if clause_match else len(text)
    if not category:
        category_positions = [
            (text.rfind(candidate, 0, category_scan_end), candidate)
            for candidate in ["一类违规行为", "二类违规行为", "三类违规行为"]
        ]
        category_positions = [(index, candidate) for index, candidate in category_positions if index >= 0]
        if category_positions:
            category = max(category_positions, key=lambda item: item[0])[1]
        else:
            category = next((candidate for candidate in ["一类违规行为", "二类违规行为", "三类违规行为"] if candidate in text), None)
    if not category:
        return None
    has_management_scope = "破坏学校管理秩序行为" in text or "破坏学校管理秩序行为" in rule_terms
    if has_management_scope and clause:
        return f"属于{category}中的破坏学校管理秩序行为（{clause}）"
    if has_management_scope:
        return f"属于{category}中的破坏学校管理秩序行为"
    if clause:
        return f"属于{category}（{clause}）"
    return f"属于{category}"


def _normalize_action_item(item: str) -> str:
    item = item.strip("，。；; ")
    if item.endswith("处分") and not item.startswith(("给予", "予以")):
        return f"给予{item}"
    return item


def _format_action_items(expected_evidence: list[str], fallback_text: str) -> list[str]:
    if expected_evidence:
        return [_normalize_action_item(str(item)) for item in expected_evidence if item]
    text = fallback_text.strip("；;。 ")
    if "，" in text:
        text = text.split("，", 1)[1]
    return [_normalize_action_item(part) for part in re.split(r"，并|并|；|;", text) if part.strip("，。；; ")]


def _compose_absenteeism_answer(results: list[SearchResult], retrieval_mode: str, understanding: dict[str, Any]) -> str | None:
    penalty_result = _find_absenteeism_penalty_result(results)
    classification_result = _find_absenteeism_classification_result(results, understanding)
    classification_label = _absenteeism_classification_label(classification_result, understanding)
    rule_resolution = understanding.get("rule_resolution") or {}
    if penalty_result is None:
        return None

    penalty_index = results.index(penalty_result) + 1
    penalty_citation = _citation_for_result(penalty_result, penalty_index)
    if not rule_resolution:
        lines = [
            f"我在制度库中返回了 {len(results)} 条候选片段。",
            "事实：旷工。",
            "规则匹配：当前问题没有给出连续旷工天数或一年内累计次数，不能直接落到单一处罚档，需要按制度条件分流。",
        ]
        if classification_result is not None and classification_label:
            classification_index = results.index(classification_result) + 1
            classification_citation = _citation_for_result(classification_result, classification_index)
            lines.append(
                f"违规类型：如果能确认连续旷工少于三天，根据 {classification_citation['citation_id']}《{classification_citation['title']}》，旷工{classification_label}。"
            )
        lines.extend(
            [
                "处理结果：\n1. 连续旷工3个工作日以下：扣除旷工期间工资；给予记过处分\n2. 连续旷工3个工作日及以上，或一年内累计两次及以上旷工：扣除旷工期间工资；给予辞退处分",
                f"处罚依据：根据 {penalty_citation['citation_id']}《{penalty_citation['title']}》中的旷工处理规则。",
                "不确定性提醒：如果能确认连续旷工天数、是否为工作日、是否一年内累计两次及以上，系统才能进一步匹配到唯一处罚档；存在请假审批或特殊审批时需要按实际考勤和 HR 确认。",
            ]
        )
        return (
            "\n".join(lines)
            + "\n\n相关来源：\n"
            + "\n".join(_source_lines(results))
            + f"\n检索方式：{_mode_label(retrieval_mode)}。"
        )

    user_fact = rule_resolution.get("user_fact") or "旷工事实"
    matched_rule = rule_resolution.get("matched_rule") or understanding.get("behavior_threshold") or "旷工规则"
    comparison = rule_resolution.get("comparison")
    expected_evidence = list(rule_resolution.get("expected_evidence") or [])
    action_items = _format_action_items(expected_evidence, penalty_result.chunk.text)
    action_lines = "\n".join(f"{index}. {item}" for index, item in enumerate(action_items, start=1))
    rule_line = f"规则匹配：{comparison}，命中“{matched_rule}”。" if comparison else f"规则匹配：命中“{matched_rule}”。"

    lines = [
        f"我在制度库中返回了 {len(results)} 条候选片段。",
        f"事实：{user_fact}。",
        rule_line,
    ]
    if classification_result is not None and classification_label:
        classification_index = results.index(classification_result) + 1
        classification_citation = _citation_for_result(classification_result, classification_index)
        lines.append(f"违规类型：根据 {classification_citation['citation_id']}《{classification_citation['title']}》，{user_fact}{classification_label}。")
    lines.extend([
        f"处理结果：\n{action_lines}",
        f"处罚依据：根据 {penalty_citation['citation_id']}《{penalty_citation['title']}》中的“{matched_rule}”规则。",
    ])
    uncertainty = rule_resolution.get("uncertainty") or "如果存在请假审批、统计口径、适用对象或生效版本差异，需要以制度原文和 HR/制度委员会确认为准。"
    lines.append(f"不确定性提醒：{uncertainty}")
    return (
        "\n".join(lines)
        + "\n\n相关来源：\n"
        + "\n".join(_source_lines(results))
        + f"\n检索方式：{_mode_label(retrieval_mode)}。"
    )


def _strip_clause_number(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"^\d+(?:\.\d+)?\.?\s*", "", str(value)).strip()


def _behavior_classification_label(understanding: dict[str, Any]) -> str | None:
    classification_terms = [str(term) for term in understanding.get("target_terms") or []]
    rule_resolution = understanding.get("rule_resolution") or {}
    classification_terms.extend(str(term) for term in rule_resolution.get("classification_terms") or [])
    target_section = understanding.get("target_section")
    if target_section:
        classification_terms.append(str(target_section))
    category = next((term for term in ["一类违规行为", "二类违规行为", "三类违规行为"] if term in classification_terms), None)
    clause_name = _strip_clause_number(understanding.get("target_clause"))
    subclause = understanding.get("target_subclause")
    behavior_label = understanding.get("target_behavior_label") or "该行为"
    if category and clause_name and subclause:
        return f"属于{category}中的{clause_name}（{subclause}{behavior_label}）"
    if category and clause_name:
        return f"属于{category}中的{clause_name}"
    if category:
        return f"属于{category}"
    return None


def _format_violation_action_items(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", "", text.strip())
    cleaned = re.sub(r"^\d+\.\d+[一二三]类违规行为[:：]", "", cleaned)
    if "：" in cleaned and "违规行为" in cleaned.split("：", 1)[0]:
        cleaned = cleaned.split("：", 1)[1]
    parts = [part.strip("，。；; ") for part in re.split(r"[，。；;]", cleaned) if part.strip("，。；; ")]
    return parts or ([cleaned] if cleaned else [])


def _extract_behavior_condition_text(text: str, behavior_label: str) -> str | None:
    normalized = re.sub(r"\s+", "", text.strip())
    for segment in re.split(r"[。；;]", normalized):
        if behavior_label not in segment:
            continue
        if any(signal in segment for signal in ["一学年", "两次", "少于", "及以上", "并引起", "投诉", "造成"]):
            subclause_match = re.search(r"(\d+\.\d+.*)", segment)
            return (subclause_match.group(1) if subclause_match else segment).strip("，。；; ")
    return None


def _compose_behavior_policy_answer(results: list[SearchResult], retrieval_mode: str, understanding: dict[str, Any]) -> str | None:
    target_behavior = understanding.get("target_behavior")
    if not target_behavior or target_behavior == ABSENTEEISM_BEHAVIOR:
        return None
    classification_result = _find_behavior_classification_result(results, understanding)
    if classification_result is None:
        return None
    behavior_label = understanding.get("target_behavior_label") or "该行为"
    classification_index = results.index(classification_result) + 1
    classification_citation = _citation_for_result(classification_result, classification_index)
    classification_label = _behavior_classification_label(understanding)
    lines = [
        f"我在制度库中返回了 {len(results)} 条候选片段。",
        f"事实：{behavior_label}。",
    ]
    missing_conditions = [str(item) for item in understanding.get("missing_conditions") or [] if item]
    required_conditions = [str(item) for item in understanding.get("required_conditions") or [] if item]
    conditional_prefix = "如果满足条款条件，" if missing_conditions else ""
    if classification_label:
        lines.append(f"规则匹配：根据 {classification_citation['citation_id']}《{classification_citation['title']}》，{conditional_prefix}{behavior_label}{classification_label}。")
    else:
        lines.append(f"规则匹配：根据 {classification_citation['citation_id']}《{classification_citation['title']}》，{conditional_prefix}命中与{behavior_label}相关的制度条款。")
    if missing_conditions:
        lines.append(f"条件说明：当前问题还需要确认：{'、'.join(missing_conditions)}；制度条款要求：{'、'.join(required_conditions)}。")
    else:
        condition_text = _extract_behavior_condition_text(classification_result.chunk.text, behavior_label)
        if condition_text:
            lines.append(f"条款条件：{condition_text}。")

    if understanding.get("asked_aspect") == DISCIPLINARY_ACTION_ASPECT:
        penalty_result = _find_behavior_penalty_result(results, understanding)
        if penalty_result is not None:
            penalty_index = results.index(penalty_result) + 1
            penalty_citation = _citation_for_result(penalty_result, penalty_index)
            action_items = _format_violation_action_items(penalty_result.chunk.text)
            action_lines = "\n".join(f"{index}. {item}" for index, item in enumerate(action_items, start=1))
            result_heading = "处理结果（满足上述条件时）：" if missing_conditions else "处理结果："
            uncertainty = (
                f"不确定性提醒：需要确认{'、'.join(missing_conditions)}；如果对象、场景、投诉、影响程度或调查结论不同，最终处理需要以制度原文和正式处理决定为准。"
                if missing_conditions
                else "不确定性提醒：如果事实情节、损失程度、调查结论或制度委员会认定不同，最终处理需要以制度原文和正式处理决定为准。"
            )
            lines.extend([
                f"{result_heading}\n{action_lines}",
                f"处罚依据：根据 {penalty_citation['citation_id']}《{penalty_citation['title']}》中的“{understanding.get('target_section') or '对应违规等级'}”处理条款。",
                uncertainty,
            ])
        else:
            lines.append("处理结果：当前召回证据只覆盖行为分类，未召回到对应违规等级的处理条款，不能凭空给出处罚结论。")
    else:
        lines.append(f"结论：{classification_label or '命中相关违规条款'}。")

    return (
        "\n".join(lines)
        + "\n\n相关来源：\n"
        + "\n".join(_source_lines(results))
        + f"\n检索方式：{_mode_label(retrieval_mode)}。"
    )


_CHINESE_DIGIT_VALUES = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_ANNUAL_LEAVE_YEAR_LABELS = {
    1: "第一年",
    2: "第二年",
    3: "第三年",
    4: "第四年",
    5: "第五年",
    6: "第六年及以后",
}


def _chinese_number_to_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = _CHINESE_DIGIT_VALUES.get(left, 1 if left == "" else None)
        ones = _CHINESE_DIGIT_VALUES.get(right, 0 if right == "" else None)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(value) == 1:
        return _CHINESE_DIGIT_VALUES.get(value)
    return None


def _extract_requested_work_year(query: str) -> int | None:
    if "第六年及以后" in query or "六年及以后" in query or "6年及以后" in query:
        return 6
    for match in re.finditer(r"(?:第|工作|工龄|司龄|连续工龄|本单位连续工龄|满)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*年", query):
        value = _chinese_number_to_int(match.group(1))
        if value is not None and 1 <= value <= 20:
            return value
    return None


def _annual_leave_entitlements(text: str) -> dict[int, int]:
    normalized = re.sub(r"\s+", " ", text)
    table_match = re.search(
        r"第一年\s*第二年\s*第三年\s*第四年\s*第五年\s*第六年及以后\s*"
        r"(\d+)天\s*(\d+)天\s*(\d+)天\s*(\d+)天\s*(\d+)天\s*(\d+)天",
        normalized,
    )
    if table_match:
        values = [int(value) for value in table_match.groups()]
        return {year: values[year - 1] for year in range(1, 7)}

    entitlements: dict[int, int] = {}
    for year, label in _ANNUAL_LEAVE_YEAR_LABELS.items():
        match = re.search(rf"{re.escape(label)}\s*(\d+)天", normalized)
        if match:
            entitlements[year] = int(match.group(1))
    return entitlements


def _find_annual_leave_result(results: list[SearchResult]) -> SearchResult | None:
    for result in results:
        text = result.chunk.text
        if any(term in text for term in ["带薪年假", "带薪年休假", "年休假天数"]):
            entitlements = _annual_leave_entitlements(text)
            if entitlements:
                return result
    return None


def _format_annual_leave_table(entitlements: dict[int, int]) -> str:
    parts = []
    for year in range(1, 7):
        if year in entitlements:
            parts.append(f"{_ANNUAL_LEAVE_YEAR_LABELS[year]} {entitlements[year]}天")
    return "、".join(parts)


def _compose_annual_leave_answer(
    results: list[SearchResult],
    retrieval_mode: str,
    understanding: dict[str, Any],
    query: str,
) -> str | None:
    if understanding.get("policy_category_hint") != "leave" and not any(term in query for term in ["年假", "年休假"]):
        return None
    annual_result = _find_annual_leave_result(results)
    if annual_result is None:
        return None

    entitlements = _annual_leave_entitlements(annual_result.chunk.text)
    if not entitlements:
        return None
    requested_year = _extract_requested_work_year(query)
    citation = _citation_for_result(annual_result, results.index(annual_result) + 1)
    lines = [f"我在制度库中返回了 {len(results)} 条候选片段。"]

    if requested_year is not None:
        entitlement_key = 6 if requested_year >= 6 else requested_year
        days = entitlements.get(entitlement_key)
        if days is None:
            return None
        year_label = _ANNUAL_LEAVE_YEAR_LABELS[entitlement_key]
        lines.extend(
            [
                f"结论：本单位连续工龄{year_label}，带薪年假为 {days}天。",
                f"规则匹配：用户问的是工作{requested_year}年，对应制度表中的“{year_label}”。",
            ]
        )
    else:
        lines.append(f"结论：带薪年假按本单位连续工龄分档，{_format_annual_leave_table(entitlements)}。")

    if "适用于全体非教学老师" in annual_result.chunk.text:
        lines.append("适用范围：该条款写明“带薪年假（适用于全体非教学老师）”。")
    lines.append(f"年假表：{_format_annual_leave_table(entitlements)}。")

    note_parts = []
    if "不包括法定节假日及周末公休日" in annual_result.chunk.text:
        note_parts.append("年休假不包括法定节假日及周末公休日")
    if "单次请假原则上不能连续超过5天" in annual_result.chunk.text:
        note_parts.append("非寒暑假时间（学期内）单次请假原则上不能连续超过5天")
    if "3个月内休完" in annual_result.chunk.text:
        note_parts.append("未休完的年休假可在该入职年度结束后的3个月内休完，逾期规则以制度原文为准")
    if note_parts:
        lines.append("注意事项：" + "；".join(note_parts) + "。")
    lines.append(f"依据：根据 {citation['citation_id']}《{citation['title']}》中的带薪年假条款。")
    return (
        "\n".join(lines)
        + "\n\n相关来源：\n"
        + "\n".join(_source_lines([annual_result]))
        + f"\n检索方式：{_mode_label(retrieval_mode)}。"
    )


def _listing_sort_key(item: tuple[int, SearchResult]) -> tuple[int, int]:
    fallback_index, result = item
    title = _listing_title_from_result(result, {}) or ""
    normalized = re.sub(r"\s+", " ", result.chunk.text)
    if title:
        match = re.search(rf"(?<!\d)(\d{{1,2}})\.\s*{re.escape(title)}", normalized)
        if match:
            return (int(match.group(1)), fallback_index)
    return (999, fallback_index)


def _listing_detail(title: str, text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    position = normalized.find(title)
    detail = normalized[position + len(title):] if position >= 0 else normalized
    detail = re.sub(r"^[：:，。；;\s]+", "", detail).strip()
    detail = re.sub(r"（[一二三四五六七八九十]+）[^。]*?：指[^。]*。?", "", detail).strip()
    if len(detail) > 140:
        detail = detail[:140].rstrip("，。；; ") + "..."
    return detail


def _compose_section_listing_answer(results: list[SearchResult], retrieval_mode: str, understanding: dict[str, Any]) -> str | None:
    if not _is_section_listing_query(understanding):
        return None
    listing_results = [result for result in results if _is_listing_evidence_result(result, understanding)]
    if not listing_results:
        return None

    seen_titles: set[str] = set()
    unique_results: list[SearchResult] = []
    for result in listing_results:
        title = _listing_title_from_result(result, understanding)
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        unique_results.append(result)

    ordered_results = [result for _, result in sorted(enumerate(unique_results), key=_listing_sort_key)]
    target_section = str(understanding.get("target_section") or "目标章节")
    section_label = target_section.removesuffix("行为") if target_section.endswith("行为") else target_section
    lines = [f"我在制度库中返回了 {len(ordered_results)} 条候选片段。", f"{section_label}主要包括："]
    for index, result in enumerate(ordered_results, start=1):
        title = _listing_title_from_result(result, understanding) or f"分类 {index}"
        detail = _listing_detail(title, result.chunk.text)
        if detail:
            lines.append(f"{index}. {title}：{detail}")
        else:
            lines.append(f"{index}. {title}")
    lines.append("说明：这里回答的是分类范围，不展开处罚结果；如果要看处理方式，需要继续问对应违规等级的处罚。")
    return (
        "\n".join(lines)
        + "\n\n相关来源：\n"
        + "\n".join(_source_lines(ordered_results))
        + f"\n检索方式：{_mode_label(retrieval_mode)}。"
    )


def _compose_answer(results: list[SearchResult], retrieval_mode: str, understanding: dict[str, Any] | None = None, query: str = "") -> str:
    if not results:
        return "没有在当前制度样本中检索到足够相关的内容。"

    section_listing_answer = _compose_section_listing_answer(results, retrieval_mode, understanding or {})
    if section_listing_answer:
        return section_listing_answer

    if (understanding or {}).get("target_behavior") == ABSENTEEISM_BEHAVIOR:
        absenteeism_answer = _compose_absenteeism_answer(results, retrieval_mode, understanding or {})
        if absenteeism_answer:
            return absenteeism_answer

    behavior_answer = _compose_behavior_policy_answer(results, retrieval_mode, understanding or {})
    if behavior_answer:
        return behavior_answer

    annual_leave_answer = _compose_annual_leave_answer(results, retrieval_mode, understanding or {}, query)
    if annual_leave_answer:
        return annual_leave_answer

    best = results[0].chunk
    best_citation = _citation_for_result(results[0], 1)
    return (
        f"我在制度库中返回了 {len(results)} 条候选片段。优先依据 {best_citation['citation_id']}"
        f"《{best_citation['title']}》：{best.text}\n\n"
        "相关来源：\n"
        + "\n".join(_source_lines(results))
        + f"\n检索方式：{_mode_label(retrieval_mode)}。"
    )


DATA_FLOW_INPUT_KEYS = (
    "input",
    "input_text",
    "payload",
    "query_type",
    "query_length",
    "top_k",
    "max_top_k",
    "pair_count",
    "input_candidate_count",
    "metadata_filters",
)

DATA_FLOW_OUTPUT_KEYS = (
    "trace_id",
    "request_id",
    "status",
    "normalized_query",
    "intent",
    "policy_category_hint",
    "audience_hint",
    "time_hints",
    "ambiguity_flags",
    "extracted_terms",
    "retrieval_intent",
    "target_terms",
    "target_section",
    "target_clause",
    "target_clause_no",
    "target_subclause",
    "target_behavior",
    "target_behavior_label",
    "behavior_duration",
    "behavior_threshold",
    "condition_parameters",
    "answer_aspect",
    "query_schema",
    "rule_resolution",
    "rule_search_terms",
    "expected_evidence",
    "preferred_policy_titles",
    "asked_aspect",
    "aspect_terms",
    "exclude_sections",
    "exclude_clauses",
    "standalone_query",
    "expanded_query",
    "expanded_query_for_future_hybrid",
    "added_terms",
    "semantic_drift_check",
    "tokenizer",
    "token_count",
    "tokens_preview",
    "token_ids_preview",
    "max_input_tokens",
    "truncated_by_model",
    "truncated_for_trace",
    "dimension",
    "vector_preview",
    "enabled_channels",
    "candidate_limit",
    "final_top_k",
    "result_count",
    "results_preview",
    "output_candidate_count",
    "rerank_comparison",
    "quality_checks",
    "context_blocks",
    "scope_guard",
    "citation_merge",
    "target_evidence_filter",
    "answer",
    "post_answer_faithfulness_check",
    "langfuse_observations",
)


def _derive_data_flow(key: str, details: dict[str, Any]) -> dict[str, Any]:
    input_payload: dict[str, Any] = {}
    output_payload: dict[str, Any] = {}

    if "raw_query" in details:
        input_payload["raw_message"] = details["raw_query"]
    for field in DATA_FLOW_INPUT_KEYS:
        if field in details:
            input_payload[field] = details[field]

    if "output" in details:
        output_payload["output"] = details["output"]
    for field in DATA_FLOW_OUTPUT_KEYS:
        if field in details:
            output_payload[field] = details[field]

    if "expanded_query_for_future_hybrid" in output_payload and "expanded_query" not in output_payload:
        output_payload["expanded_query"] = output_payload["expanded_query_for_future_hybrid"]

    visible_keys = sorted(field for field in details.keys() if field != "data_flow")
    if not input_payload:
        input_payload = {"node_key": key, "detail_keys": visible_keys[:12]}
    if not output_payload:
        output_payload = {"node_key": key, "detail_keys": visible_keys[:12]}
    return {"input": input_payload, "output": output_payload}


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
    normalized_details = dict(details or {})
    normalized_details.setdefault("data_flow", _derive_data_flow(key, normalized_details))
    return {
        "key": key,
        "title": title,
        "status": status,
        "execution_mode": execution_mode,
        "summary": summary,
        "details": normalized_details,
        "duration_ms": duration_ms,
        "children": children or [],
    }


def run_chat_trace(
    query: str,
    *,
    embedding_client: Any,
    store: Any | None,
    top_k: int = 3,
    reranker_client: Any | None = None,
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
    domain_terms = [term for term in ["制度", "规则", "年假", "年休假", "报销", "考勤", "安全", "政策", "处罚", "处分", "旷工", "骂人", "说脏话", "师德"] if term in query]
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
                    key="extract_rule_conditions",
                    title="抽取规则条件",
                    summary="把用户事实拆成目标对象、问题面和条件参数，并尝试匹配制度规则。",
                    details={
                        "query_schema": understanding.get("query_schema"),
                        "rule_resolution": understanding.get("rule_resolution"),
                        "expected_evidence": understanding.get("expected_evidence"),
                    },
                    duration_ms=0,
                    status="ok" if understanding.get("rule_resolution") or understanding.get("query_schema") else "warn",
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
    retrieval_query = rewrite["expanded_query"] if understanding.get("retrieval_intent") == "exact_policy_lookup" else rewrite["standalone_query"]
    steps.append(
        _step(
            key="query_rewrite",
            title="Step 5 · Query 改写与扩展",
            summary="把口语化输入变成检索友好的独立问题，并补充安全同义词。",
            details={
                "tool": "deterministic query rewrite rules",
                "why": "改写能让‘年假’匹配到制度正文里的‘年休假’，但必须展示改写前后，防止语义漂移。",
                "tradeoff": "普通语义问题使用 standalone_query 控制语义漂移；精确制度查询使用 expanded_query，让同义词、条款号和处理词进入召回。",
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
    candidate_limit = max(top_k, min(24, top_k * 4))
    enabled_channels = ["dense_vector"]
    if understanding.get("retrieval_intent") == "exact_policy_lookup":
        enabled_channels = ["exact_match", "sparse_keyword", "dense_vector"]
    metadata_filters = {
        "policy_category_hint": understanding["policy_category_hint"],
        "audience_hint": understanding["audience_hint"],
        "time_hints": understanding["time_hints"],
        "retrieval_intent": understanding.get("retrieval_intent"),
        "target_terms": understanding.get("target_terms"),
        "target_section": understanding.get("target_section"),
        "target_clause": understanding.get("target_clause"),
        "target_clause_no": understanding.get("target_clause_no"),
        "target_subclause": understanding.get("target_subclause"),
        "target_behavior": understanding.get("target_behavior"),
        "target_behavior_label": understanding.get("target_behavior_label"),
        "behavior_duration": understanding.get("behavior_duration"),
        "behavior_threshold": understanding.get("behavior_threshold"),
        "preferred_policy_titles": understanding.get("preferred_policy_titles"),
        "asked_aspect": understanding.get("asked_aspect"),
        "aspect_terms": understanding.get("aspect_terms"),
        "exclude_sections": understanding.get("exclude_sections"),
        "exclude_clauses": understanding.get("exclude_clauses"),
    }
    steps.append(
        _step(
            key="retrieval_plan",
            title="Step 8 · 检索计划生成",
            summary="决定召回通道、metadata filter、候选数量和最终 top_k。",
            details={
                "tool": "retrieval planner rules",
                "enabled_channels": enabled_channels,
                "production_options": ["BM25", "hybrid_search", "metadata_filter"],
                "candidate_limit": candidate_limit,
                "final_top_k": top_k,
                "metadata_filters": metadata_filters,
                "expanded_query_for_future_hybrid": rewrite["expanded_query"],
                "why": "精确制度词必须启用 exact/sparse 信号；普通语义问题可以先用 dense vector，再由 rerank 压噪。",
                "tradeoff": "hybrid search 比纯向量更适合条款编号和制度标题，但需要更好的索引和 metadata。",
                "term_definitions": [
                    _term("Exact match", "对制度标题、条款号、章节名做确定性匹配，适合二类违规、4.1 这类精确查询。"),
                    _term("BM25", "搜索引擎常用的关键词排序算法，适合制度编号、专有名词和精确词。"),
                    _term("Hybrid search", "把向量语义检索和关键词检索合并，兼顾语义召回和精确匹配。"),
                    _term("Metadata filter", "用分类、适用对象、发布时间等结构化字段限制检索范围。"),
                ],
                "pitfalls": ["candidate_limit 太小会让 rerank 没有发挥空间；太大又会增加延迟。", "精确条款查询不能只靠 embedding。"],
            },
            duration_ms=_duration_ms(start),
            execution_mode="parallel",
            children=[
                _step(
                    key="detect_exact_policy_lookup",
                    title="识别精确制度查询",
                    summary="判断是否需要 exact/sparse/dense 三路召回。",
                    details={
                        "retrieval_intent": understanding.get("retrieval_intent"),
                        "target_terms": understanding.get("target_terms"),
                        "target_section": understanding.get("target_section"),
                        "target_clause": understanding.get("target_clause"),
                    },
                    duration_ms=0,
                ),
                _step(
                    key="choose_channels",
                    title="选择召回通道",
                    summary="精确制度查询启用 exact/sparse/dense；普通查询使用 dense。",
                    details={"enabled_channels": enabled_channels, "production_options": ["BM25", "hybrid_search"]},
                    duration_ms=0,
                ),
                _step(
                    key="derive_metadata_filters",
                    title="派生 metadata filters",
                    summary="从查询理解结果派生分类、对象、章节和排除范围。",
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
    retrieval_mode = "pgvector_hybrid" if "exact_match" in enabled_channels else "pgvector"
    vector_details: dict[str, Any] = {
        "framework": "PostgreSQL + pgvector hybrid" if retrieval_mode == "pgvector_hybrid" else "PostgreSQL + pgvector",
        "sql": PGVECTOR_QUERY_SQL,
        "top_k": candidate_limit,
        "enabled_channels": enabled_channels,
        "metadata_filters": metadata_filters,
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
        "tool": "PostgreSQL hybrid search" if retrieval_mode == "pgvector_hybrid" else "PostgreSQL SQL + pgvector <=> operator",
        "sql": PGVECTOR_QUERY_SQL,
        "top_k": candidate_limit,
        "distance_metric": "cosine distance，值越小越相似。",
        "enabled_channels": enabled_channels,
    }
    vector_children = [
        _step(
            key="build_vector_query",
            title="构造检索查询",
            summary="准备 dense vector 查询；精确制度查询额外带 exact/sparse 过滤信号。",
            details=build_query_details,
            duration_ms=_duration_ms(build_query_start),
        )
    ]
    try:
        if store is None:
            raise RuntimeError("No pgvector store configured for this request.")
        pgvector_start = time.perf_counter()
        if retrieval_mode == "pgvector_hybrid" and hasattr(store, "hybrid_search"):
            results = store.hybrid_search(
                query_text=rewrite["expanded_query"],
                query_embedding=query_embedding,
                top_k=candidate_limit,
                metadata_filters=metadata_filters,
            )
            search_tool = "PgVectorStore.hybrid_search"
            search_key = "hybrid_search"
            search_title = "执行 Hybrid Search"
        else:
            results = store.search(query_embedding, top_k=candidate_limit)
            search_tool = "PgVectorStore.search"
            search_key = "pgvector_search"
            search_title = "执行 pgvector 检索"
        pgvector_duration = _duration_ms(pgvector_start)
        vector_children.append(
            _step(
                key=search_key,
                title=search_title,
                summary="按检索计划召回候选 chunk。",
                details={
                    "tool": search_tool,
                    "enabled_channels": enabled_channels,
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
                "fallback_reason": "pgvector/hybrid search is unavailable or not configured; running demo retrieval over sample chunks.",
            }
        )
        vector_children.append(
            _step(
                key="pgvector_search",
                title="执行 pgvector / hybrid 检索",
                summary="pgvector 不可用，进入 fallback 分支。",
                details={"tool": "PgVectorStore.search or hybrid_search", "error": str(exc)},
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
            summary="按检索计划执行 dense 或 hybrid 召回，并输出候选 chunk。",
            details=vector_details,
            duration_ms=_duration_ms(start),
            execution_mode="branch",
            children=vector_children,
        )
    )

    start = time.perf_counter()
    reranked_results, rerank_comparison = _rerank_results(retrieval_query, results, understanding, reranker_client=reranker_client)
    steps.append(
        _step(
            key="rerank",
            title="Step 10 · Rerank 重排",
            summary="对初召回候选重新打分，展示排序前后的变化。",
            details={
                "tool": "deterministic lexical + scope-aware rerank fallback",
                "reranker_choice": _reranker_choice(),
                "input_candidate_count": len(results),
                "output_candidate_count": len(reranked_results),
                "rerank_comparison": rerank_comparison,
                "reranker_source": rerank_comparison[0].get("reranker_source") if rerank_comparison else "none",
                "reranker_error": rerank_comparison[0].get("reranker_error") if rerank_comparison else None,
                "term_definitions": [
                    _term("Rerank", "对已召回候选重新排序，让真正回答问题的证据排到前面。"),
                    _term("Cross-encoder", "同时读取 query 和 document 的模型，直接输出相关性分数。"),
                    _term("Relevance score", "候选 chunk 与问题相关程度的分数。"),
                ],
                "pitfalls": ["Rerank 会增加延迟；只应该重排候选集，不应该重排全库。", "精确条款查询需要给目标章节加分，并给相邻竞争章节降权。"],
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
                    details={"tool": "lexical overlap + heading bonus + exact section/clause bonus + competing section penalty + vector distance"},
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

    scoped_results = _scope_results(reranked_results, understanding)
    target_filtered_results, target_evidence_filter = _filter_target_evidence(scoped_results, understanding)
    deduped_results, citation_merge = _dedupe_evidence(target_filtered_results, understanding)
    behavior_selected_results = _select_behavior_final_results(deduped_results, understanding)
    final_results = behavior_selected_results[:top_k]
    quality_start = time.perf_counter()
    quality_checks, context_blocks, scope_guard = _quality_checks(
        final_results,
        rerank_comparison,
        understanding=understanding,
        citation_merge=citation_merge,
    )
    steps.append(
        _step(
            key="evidence_quality",
            title="Step 11 · 证据质量检查与上下文组装",
            summary="检查证据相关性、来源字段、时效冲突，并组装可引用上下文。",
            details={
                "tool": "deterministic evidence quality checks",
                "quality_checks": quality_checks,
                "context_blocks": context_blocks,
                "scope_guard": scope_guard,
                "citation_merge": citation_merge,
                "target_evidence_filter": target_evidence_filter,
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
                    key="extract_scoped_context",
                    title="章节边界截取",
                    summary="按目标章节/条款从粗 chunk 中截取相关 span，避免带出相邻章节。",
                    details={"context_blocks": context_blocks, "scope_guard": scope_guard},
                    duration_ms=0,
                    status=scope_guard["status"],
                ),
                _step(
                    key="filter_reference_only_evidence",
                    title="过滤参见型片段",
                    summary="精确制度查询只保留目标章节/条款本体，参见其它制度的片段不能当答案证据。",
                    details=target_evidence_filter,
                    duration_ms=0,
                ),
                _step(
                    key="merge_duplicate_citations",
                    title="合并重复来源",
                    summary="按 doc + section + clause 合并重复候选，避免同一制度重复展示多次。",
                    details=citation_merge,
                    duration_ms=0,
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
    answer_assessments = [assess_evidence(result.chunk, understanding.get("intent_schema") or {}) for result in final_results]
    answer_plan = plan_answer(
        understanding.get("intent_schema") or {},
        answer_assessments,
        rule_resolution=understanding.get("rule_resolution"),
    )
    answer = _compose_answer(final_results, retrieval_mode, understanding, normalized_query)
    observations = _langfuse_observations(trace_id, retrieval_mode, len(final_results))
    steps.append(
        _step(
            key="answer_and_observe",
            title="Step 12 · 回答生成、后校验与 Langfuse 观测",
            summary="基于证据拼装回答，检查可追溯性，并输出 Langfuse-ready 观测记录。",
            details={
                "tool": "grounded answer template + Langfuse-ready observation metadata",
                "template": "structured grounded answer + source + retrieval mode",
                "answer": answer,
                "answer_plan": answer_plan.to_dict(),
                "answer_evidence_assessments": [assessment.to_dict() for assessment in answer_assessments],
                "post_answer_faithfulness_check": {
                    "status": "ok" if final_results and scope_guard["status"] == "ok" else "warn",
                    "reason": "当前回答模板只引用最终证据；行为型问题会组合规则匹配、违规类型和处理结果。接入 LLM 后需要逐句检查引用覆盖和章节越界。",
                    "scope_guard": scope_guard,
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
                    summary="按问题类型组织最终证据，行为型规则查询会拆成事实、规则匹配、结论和来源。",
                    details={"answer": answer, "answer_plan": answer_plan.to_dict()},
                    duration_ms=0,
                ),
                _step(
                    key="post_answer_faithfulness_check",
                    title="回答后校验",
                    summary="确认回答能追溯到当前证据。",
                    details={"status": "ok" if final_results and scope_guard["status"] == "ok" else "warn", "scope_guard": scope_guard},
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
