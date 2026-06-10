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
    assert "面试关注点" not in app_js
    assert "个主阶段 /" in app_js
    assert "个细节点" in app_js
    assert "lc_tool_call" in app_js
    assert "lg_condition" in app_js
    assert "ma_review_gate" in app_js
    assert "lf_dataset" in app_js


    assert "trace-tree-workbench" in app_js
    assert "trace-tree-canvas" in app_js
    assert "trace-tree-node" in app_js
    assert "tree-detail-panel" in app_js
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
    assert ".tree-detail-panel" in app_css
    assert ".term-list" in app_css
    assert ".quality-check-list" in app_css
    assert ".rerank-comparison" in app_css
    assert ".tree-detail-panel .kv" in app_css
    assert ".tree-detail-panel .kv dd" in app_css
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
    assert "interview-question" in app_js
    assert "interview-answer" in app_js
    assert ".interview-question" in app_css
    assert ".interview-answer" in app_css
    assert ".common-question-list" in app_css



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
