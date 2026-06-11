from pathlib import Path


WEB_DIR = Path(__file__).resolve().parents[1] / "src" / "enterprise_rag_mvp" / "web"


def test_trace_ui_uses_selectable_dag_workflow_scene():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")
    index_html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    assert "workflowSelect" in index_html
    assert "企业制度问答 · 检索流程可视化" not in index_html
    assert "12 phases" not in index_html
    assert "36 inner steps" not in index_html
    assert "in_memory_demo" not in index_html
    assert "modeBadge" not in index_html
    assert "in_memory_demo" not in app_js
    assert "in_memory_demo" not in app_css

    assert "workflowDefinitions" in app_js
    assert "buildRagWorkflow" in app_js
    assert "renderWorkflowGraph" in app_js
    assert "renderWorkflowNode" in app_js
    assert "renderMergeRail" in app_js
    assert "workflowSelect.addEventListener" in app_js
    assert "parallel_group" in app_js
    assert "merge" in app_js
    assert "RAG 基础流程" in app_js
    assert "Embedding 检索流程" in app_js
    assert "LangChain Agent" in app_js
    assert "LangGraph 工作流" in app_js
    assert "Query Rewrite + Rerank" in app_js
    assert "多 Agent 协作" in app_js
    assert "企业知识库导入" in app_js
    assert "Langfuse 观测链路" in app_js
    assert "ragInnerStepCatalog" in app_js
    assert "prefixInnerStepCatalog" in app_js
    assert "inner-step-list" in app_js
    assert "inner-step-chip" in app_js
    assert "常见问题" in app_js
    assert "knowledge_points" in app_js
    assert "个主阶段 /" in app_js
    assert "个细节点" in app_js
    assert "lc_tool_call" in app_js
    assert "lg_condition" in app_js
    assert "ma_review_gate" in app_js
    assert "lf_dataset" in app_js


    assert "trace-tree-workbench" in app_js
    assert "trace-tree-canvas" in app_js
    assert "trace-tree-node" in app_js
    assert "tree-detail-panel" not in app_js
    assert "node-detail-drawer" in app_js
    assert "node-detail-backdrop" in app_js
    assert "openNodeDetailDrawer" in app_js
    assert "closeNodeDetailDrawer" in app_js
    assert "selectWorkflowNode" in app_js
    assert "renderTermList" in app_js
    assert "renderQualityChecks" in app_js
    assert "renderRerankComparison" in app_js
    assert "Array.isArray(value)" in app_js

    assert "THREE_MODULE_URL" not in app_js
    assert "Raycaster" not in app_js
    assert "WebGLRenderer" not in app_js
    assert "detail-connector" not in app_js
    assert "connector-line" not in app_js

    assert ".trace-tree-workbench" in app_css
    assert ".trace-tree-canvas" in app_css
    assert ".trace-tree-node" in app_css
    assert ".workflow-select" in app_css
    assert ".workflow-graph" in app_css
    assert ".workflow-row.parallel_group" in app_css
    assert ".merge-rail" in app_css
    assert ".elbow-connector" in app_css
    assert ".inner-step-list" in app_css
    assert ".inner-step-chip" in app_css
    assert ".common-question-list" in app_css
    assert ".inner-detail-list" in app_css
    assert ".tree-detail-panel" not in app_css
    assert ".node-detail-drawer" in app_css
    assert ".node-detail-backdrop" in app_css
    assert ".node-detail-drawer.open" in app_css
    assert ".drawer-close-button" in app_css
    assert ".term-list" in app_css
    assert ".quality-check-list" in app_css
    assert ".rerank-comparison" in app_css
    assert ".node-detail-drawer .kv" in app_css
    assert ".node-detail-drawer .kv dd" in app_css
    assert "minmax(260px, 0.56fr)" in app_css
    assert "minmax(760px, 1.44fr)" in app_css

    assert ".trace-3d-workbench" not in app_css
    assert ".detail-connector" not in app_css
    assert ".connector-line" not in app_css


def test_common_questions_include_brief_answers_and_are_deduplicated():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")

    assert "renderCommonQuestions" in app_js
    assert "dedupeQuestions" in app_js
    assert "normalizeQuestionKey" in app_js
    assert "question:" in app_js
    assert "answer:" in app_js
    assert "knowledge-question" in app_js
    assert "knowledge-answer" in app_js
    assert ".knowledge-question" in app_css
    assert ".knowledge-answer" in app_css
    assert ".common-question-list" in app_css

    assert "在真实业务里失败时，应该看哪些日志或 trace" not in app_js
    assert "输入、输出和边界条件分别是什么" not in app_js
    assert "这个子步骤的输入是什么，输出又交给了谁" not in app_js
    assert "为什么不能只记录归一化后的 query" in app_js
    assert "RAG 的问题应该优先看召回还是生成" in app_js
    assert "参见型片段为什么不能直接作为答案证据" in app_js



def test_workflow_explains_terms_and_required_vs_optional_steps():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")

    assert "globalTermCatalog" in app_js
    assert "enrichTermDefinitions" in app_js
    assert "Rerank" in app_js
    assert "Cross-encoder" in app_js
    assert "BM25" in app_js
    assert "pgvector" in app_js
    assert "Langfuse" in app_js
    assert "Hybrid Search" in app_js
    assert "章节边界截取" in app_js
    assert "Scope Guard" in app_js
    assert "参见型片段过滤" in app_js
    assert "Direct evidence" in app_js
    assert "Citation Merge" in app_js
    assert "requirement:" in app_js
    assert "required" in app_js
    assert "optional" in app_js
    assert "conditional" in app_js
    assert "requirementLabels" in app_js
    assert "requirement_reason" in app_js
    assert "可选增强" in app_js
    assert "初始召回" in app_js and "必经" in app_js
    assert "Rerank 重排序" in app_js and "可选增强" in app_js
    assert "tree-requirement-badge" in app_js
    assert "requirement-note" in app_js
    assert "connector-${requirement}" in app_js

    assert ".trace-tree-node.requirement-required" in app_css
    assert ".trace-tree-node.requirement-optional" in app_css
    assert ".trace-tree-node.requirement-conditional" in app_css
    assert ".elbow-connector.connector-optional::before" in app_css
    assert "dashed" in app_css
    assert ".elbow-connector.connector-conditional::before" in app_css
    assert "dotted" in app_css
    assert ".requirement-note" in app_css


def test_workflow_node_details_explain_possible_issues_and_solutions():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")

    assert "renderIssueSolutions" in app_js
    assert "issue_solutions" in app_js
    assert "问题与解决" in app_js
    assert "issue:" in app_js
    assert "solution:" in app_js
    assert ".issue-solution-list" in app_css
    assert ".issue-solution-item" in app_css
    assert ".issue-title" in app_css
    assert ".solution-text" in app_css



def test_workflow_marks_all_production_rag_enhancements_and_current_upgrades():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")

    assert "productionEnhancements" in app_js
    assert "生产 RAG 成熟度" in app_js
    assert "本轮优化" in app_js
    assert "renderEnhancementDetail" in app_js
    assert "enhancement-current" in app_js
    assert "enhancement-status-badge" in app_js

    expected_ids = [
        "eval_runner",
        "bad_case_feedback",
        "ingest_quality_report",
        "audience_permission_filter",
        "structured_answer_contract",
        "multi_hop_resolver",
        "cross_encoder_reranker",
        "query_router",
        "citation_span_highlight",
        "langfuse_otel_observability",
        "incremental_sync_versioning",
        "document_parser_multimodal",
        "prompt_injection_guardrails",
        "cache_cost_control",
        "external_knowledge_api",
    ]
    for enhancement_id in expected_ids:
        assert enhancement_id in app_js

    assert "解决的问题" in app_js
    assert "落地方式" in app_js
    assert "验收方式" in app_js
    assert "边界条件" in app_js
    assert "已落地" in app_js
    assert "接口已预留" in app_js
    assert "待接入" in app_js

    assert ".trace-tree-node.enhancement-current" in app_css
    assert ".enhancement-status-badge.status-shipped" in app_css
    assert ".enhancement-status-badge.status-interface" in app_css
    assert ".enhancement-status-badge.status-planned" in app_css
    assert ".enhancement-detail" in app_css


def test_chat_answer_uses_structured_sections_and_linked_sources():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")

    assert "renderStructuredAnswer" in app_js
    assert "parseAnswerSections" in app_js
    assert "answer-section" in app_js
    assert "answer-section-title" in app_js
    assert "answer-section-body" in app_js
    assert "处理结果" in app_js
    assert "不确定性提醒" in app_js
    assert "来源依据" in app_js
    assert "answer-source-link" in app_js
    assert "打开来源" in app_js

    assert ".structured-answer" in app_css
    assert ".answer-section" in app_css
    assert ".answer-section-title" in app_css
    assert ".answer-result-list" in app_css
    assert ".answer-source-link" in app_css



def test_evolution_documentation_is_a_standalone_developer_docs_page():
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    app_css = (WEB_DIR / "app.css").read_text(encoding="utf-8")
    docs_js = (WEB_DIR / "docs.js").read_text(encoding="utf-8")
    docs_css = (WEB_DIR / "docs.css").read_text(encoding="utf-8")
    docs_html = (WEB_DIR / "docs.html").read_text(encoding="utf-8")
    index_html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    assert 'href="/docs"' in index_html
    assert "演进文档" in index_html
    assert "docsOverlay" not in index_html
    assert "evolutionDocs" not in app_js
    assert "openEvolutionDocs" not in app_js
    assert "docs-overlay" not in app_css

    assert "ChatLearning Docs" in docs_html
    assert "docs-page-shell" in docs_html
    assert "docs-sidebar" in docs_html
    assert "docsContent" in docs_html
    assert "学习目录" in docs_html
    assert "项目起始" in docs_html
    assert "evolutionDocs" not in docs_js
    assert "docChapters" in docs_js
    assert "productionTopics" in docs_js
    assert "toolDoc(" in docs_js
    assert "pitfallGroup(" in docs_js
    assert "realCase(" in docs_js
    assert "choiceDoc(" in docs_js
    assert "ioExample(" in docs_js
    assert "knowledgePoint(" in docs_js
    assert "renderDocsNav" in docs_js
    assert "renderDocsContent" in docs_js
    assert 'document.createElement("details")' in docs_js
    assert "docs-nav-chapter-index" in docs_js
    assert "docs-nav-section-index" in docs_js
    assert "getShortSectionTitle" in docs_js
    assert "getChapterStage" in docs_js
    assert "项目起始：业务目标与学习目标" in docs_js
    assert "项目起始：数据源调研与接口验证" in docs_js
    assert "知识库构建：分类导入与结构化切块" in docs_js
    assert "RAG 链路：Query Understanding 与 Query Rewrite" in docs_js
    assert "规则推理：旷工两天为什么能算出处罚" in docs_js
    assert "观测与评测：为什么每一步都要可回放" in docs_js
    assert "部署上线：远端隔离与 IP 端口访问" in docs_js
    assert "框架 / 工具 / 函数白话说明" in docs_js
    assert "选型对比：为什么选它" in docs_js
    assert "真实排查案例" in docs_js
    assert "真实输入输出" in docs_js
    assert "对应知识点 / 知识点追问" in docs_js
    assert "问题和坑点分组" in docs_js
    assert "可以继续思考的问题" in docs_js
    assert "来源链接被写错的问题" in docs_js
    assert "二类违规答案混入三类违规" in docs_js
    assert "二类违规处罚返回了二类违规定义" in docs_js
    assert "旷工两天一开始检索不到" in docs_js
    assert "牛客" in docs_js
    assert "生产 RAG 专题" in docs_js
    assert "Langfuse / OpenTelemetry 观测链路" in docs_js
    assert "Query Router 查询路由" in docs_js
    assert "Prompt Injection 与数据泄露护栏" in docs_js
    assert "缓存与成本控制" in docs_js
    assert "外部知识 API 与工具检索" in docs_js
    assert "什么时候必须做" in docs_js
    assert "验证方式" in docs_js
    replacement_char = "\ufffd"
    assert f"标题{replacement_char}{replacement_char}中文编号" not in docs_js
    assert f"端口都{replacement_char}{replacement_char}能随意占用" not in docs_js

    assert ".docs-page-shell" in docs_css
    assert ".docs-sidebar" in docs_css
    assert ".docs-nav-item.active" in docs_css
    assert ".docs-nav-group" in docs_css
    assert ".docs-nav-heading" in docs_css
    assert ".docs-nav-chapter-index" in docs_css
    assert ".docs-nav-heading-copy" in docs_css
    assert ".docs-nav-list" in docs_css
    assert ".docs-nav-section-index" in docs_css
    assert ".docs-nav-section-title" in docs_css
    assert ".docs-hero" in docs_css
    assert ".doc-subtitle" in docs_css
    assert ".docs-terms" in docs_css
    assert ".tool-docs" in docs_css
    assert ".tool-doc-grid" in docs_css
    assert ".tool-card" in docs_css
    assert ".tool-row" in docs_css
    assert ".choice-docs" in docs_css
    assert ".choice-card" in docs_css
    assert ".case-docs" in docs_css
    assert ".case-card" in docs_css
    assert ".io-docs" in docs_css
    assert ".io-block" in docs_css
    assert ".knowledge-docs" in docs_css
    assert ".knowledge-card" in docs_css
    assert ".pitfall-docs" in docs_css
    assert ".pitfall-grid" in docs_css
    assert ".pitfall-card" in docs_css
    assert ".study-prompts" in docs_css
