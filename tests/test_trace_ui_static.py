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
    assert "面试关注点" in app_js
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
    assert ".interview-list" in app_css
    assert ".inner-detail-list" in app_css
    assert ".tree-detail-panel" in app_css
    assert ".term-list" in app_css
    assert ".quality-check-list" in app_css
    assert ".rerank-comparison" in app_css
    assert ".tree-detail-panel .kv" in app_css
    assert ".tree-detail-panel .kv dd" in app_css
    assert "minmax(280px, 0.62fr)" in app_css
    assert "minmax(720px, 1.38fr)" in app_css

    assert ".trace-3d-workbench" not in app_css
    assert ".detail-connector" not in app_css
    assert ".connector-line" not in app_css
