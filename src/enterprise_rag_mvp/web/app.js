const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const traceSteps = document.querySelector("#traceSteps");
const traceSummary = document.querySelector("#traceSummary");
const workflowSelect = document.querySelector("#workflowSelect");
const clearButton = document.querySelector("#clearButton");

let latestTraceData = null;

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "你" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  if (role === "user") {
    article.append(bubble, avatar);
  } else {
    article.append(avatar, bubble);
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function formatValue(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value) && value.every((item) => item == null || ["string", "number", "boolean"].includes(typeof item))) {
    return JSON.stringify(value);
  }
  return JSON.stringify(value, null, 2);
}

function titleizeKey(key) {
  return key.replaceAll("_", " ");
}

function appendValue(parent, key, value) {
  if (value == null || value === "") return;
  const dt = document.createElement("dt");
  dt.textContent = titleizeKey(key);
  const dd = document.createElement("dd");
  dd.textContent = formatValue(value);
  parent.append(dt, dd);
}

function renderSection(titleText, className) {
  const section = document.createElement("section");
  section.className = className;
  const title = document.createElement("h3");
  title.textContent = titleText;
  section.appendChild(title);
  return section;
}

function renderTermList(terms) {
  if (!Array.isArray(terms) || terms.length === 0) return null;
  const section = renderSection("术语解释", "term-list");
  const list = document.createElement("dl");
  terms.forEach((item) => {
    const term = document.createElement("dt");
    term.textContent = item.term || item.name || "术语";
    const definition = document.createElement("dd");
    definition.textContent = item.definition || item.description || formatValue(item);
    list.append(term, definition);
  });
  section.appendChild(list);
  return section;
}

function renderBulletList(titleText, className, values) {
  if (!Array.isArray(values) || values.length === 0) return null;
  const section = renderSection(titleText, className);
  const list = document.createElement("ul");
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = typeof value === "string" ? value : formatValue(value);
    list.appendChild(item);
  });
  section.appendChild(list);
  return section;
}

function renderQualityChecks(checks) {
  if (!Array.isArray(checks) || checks.length === 0) return null;
  const section = renderSection("质量检查", "quality-check-list");
  checks.forEach((check) => {
    const row = document.createElement("article");
    row.className = `quality-check status-${check.status || "ok"}`;
    const name = document.createElement("strong");
    name.textContent = check.name || check.key || "check";
    const status = document.createElement("span");
    status.textContent = check.status || "ok";
    const reason = document.createElement("p");
    reason.textContent = check.reason || check.summary || formatValue(check);
    row.append(name, status, reason);
    section.appendChild(row);
  });
  return section;
}

function renderRerankComparison(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const section = renderSection("Rerank 前后对比", "rerank-comparison");
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["before", "after", "score", "chunk", "reason"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.rank_before, row.rank_after, row.rerank_score, row.chunk_id || row.title, row.reason].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value == null ? "-" : String(value);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  section.appendChild(table);
  return section;
}

function renderTokenTable(rows) {
  const table = document.createElement("table");
  table.className = "token-table";
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["#", "token", "token id"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.index, row.token, row.token_id ?? "-"].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  return table;
}

function renderChoice(choice, label) {
  const section = document.createElement("section");
  section.className = "choice-box";

  const title = document.createElement("h3");
  title.textContent = label;
  section.appendChild(title);

  const selected = document.createElement("div");
  selected.className = "selected-choice";
  selected.textContent = choice.selected;
  section.appendChild(selected);

  if (choice.why) {
    const why = document.createElement("p");
    why.textContent = choice.why;
    section.appendChild(why);
  }

  ["current_usage", "when_to_use", "why_not_now"].forEach((key) => {
    if (!choice[key]) return;
    const p = document.createElement("p");
    p.textContent = `${titleizeKey(key)}: ${choice[key]}`;
    section.appendChild(p);
  });

  if (Array.isArray(choice.alternatives) && choice.alternatives.length > 0) {
    const list = document.createElement("ul");
    choice.alternatives.forEach((alternative) => {
      const item = document.createElement("li");
      const name = document.createElement("strong");
      name.textContent = alternative.name;
      item.appendChild(name);
      const reason = alternative.why_not || alternative.why_not_now || alternative.when_to_use;
      if (reason) item.append(`: ${reason}`);
      list.appendChild(item);
    });
    section.appendChild(list);
  }

  return section;
}

function renderDetails(details) {
  const wrapper = document.createElement("div");
  const list = document.createElement("dl");
  list.className = "kv";

  const structuredKeys = [
    "sql",
    "results_preview",
    "token_table",
    "model_choice",
    "tool_choice",
    "why_this_tool",
    "term_definitions",
    "pitfalls",
    "quality_checks",
    "rerank_comparison",
    "options",
  ];
  Object.entries(details || {}).forEach(([key, value]) => {
    if (structuredKeys.includes(key)) return;
    appendValue(list, key, value);
  });
  if (list.children.length > 0) wrapper.appendChild(list);

  const termList = renderTermList(details?.term_definitions);
  if (termList) wrapper.appendChild(termList);

  const pitfalls = renderBulletList("常见坑", "pitfall-list", details?.pitfalls);
  if (pitfalls) wrapper.appendChild(pitfalls);

  const options = renderBulletList("真实项目还会补", "option-list", details?.options);
  if (options) wrapper.appendChild(options);

  const qualityChecks = renderQualityChecks(details?.quality_checks);
  if (qualityChecks) wrapper.appendChild(qualityChecks);

  const rerankComparison = renderRerankComparison(details?.rerank_comparison);
  if (rerankComparison) wrapper.appendChild(rerankComparison);

  if (details?.why_this_tool) {
    wrapper.appendChild(renderChoice(details.why_this_tool, "工具选型"));
  }

  if (details?.model_choice) {
    wrapper.appendChild(renderChoice(details.model_choice, "Embedding 选型"));
  }

  if (details?.tool_choice) {
    wrapper.appendChild(renderChoice(details.tool_choice, "检索存储选型"));
  }

  if (details?.token_table) {
    wrapper.appendChild(renderTokenTable(details.token_table));
  }

  if (details?.sql) {
    const pre = document.createElement("pre");
    pre.textContent = details.sql;
    wrapper.appendChild(pre);
  }

  if (details?.results_preview) {
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(details.results_preview, null, 2);
    wrapper.appendChild(pre);
  }

  return wrapper;
}

function term(termText, definition) {
  return { term: termText, definition };
}

function node(id, title, summary, extra = {}) {
  return {
    id,
    title,
    summary,
    mode: "sequential",
    status: "ok",
    details: {},
    ...extra,
  };
}

const embeddingDetails = {
  tool: "embedding model + vector index",
  teaching_note: "Embedding 不是简单压缩文本，而是把语义位置映射到高维向量空间；query 和 document 必须使用同一模型、同一维度、同一版本。",
  model_choice: {
    selected: "BGE-M3 dense embedding",
    why: "企业制度常见中文、英文标题和中英混排，BGE-M3 多语言表现稳定，也可以本地部署，适合内部数据不出域的场景。",
    current_usage: "当前链路使用 dense 向量做语义召回，先保证最小闭环可验证。",
    alternatives: [
      { name: "OpenAI text-embedding", when_to_use: "云端部署、英文和跨语言质量要求高、数据合规允许外发时。" },
      { name: "Qwen Embedding", when_to_use: "中文业务、国产模型生态、需要云端或本地多种尺寸选择时。" },
      { name: "Jina / E5", when_to_use: "需要不同语言、长文本或开源模型对比 benchmark 时。" },
      { name: "Sparse / BM25", when_to_use: "制度编号、人名、专有名词、精确关键词特别重要时，适合和 dense 混合检索。" },
      { name: "Multi-vector", when_to_use: "长文档、多语义块、表格和细粒度段落相关性要求更高时，但成本更高。" },
    ],
  },
  term_definitions: [
    term("Dense embedding", "把整段文本表示成一个稠密向量，适合语义相似度检索。"),
    term("Sparse embedding", "保留词项级信号，适合制度编号、专有名词、关键词精确匹配。"),
    term("Multi-vector", "一段文本生成多个向量，能表达更细粒度语义，但存储和检索成本更高。"),
    term("向量维度", "模型输出向量的长度，例如 1024；文档向量和查询向量维度必须一致。"),
  ],
  quality_checks: [
    { name: "empty_text", status: "ok", reason: "embedding 前必须拒绝空文本，否则会污染索引。" },
    { name: "dimension_match", status: "ok", reason: "查询向量和库内向量维度必须一致。" },
    { name: "model_version", status: "ok", reason: "换模型后旧向量需要重建，否则相似度没有可比性。" },
  ],
  pitfalls: [
    "文档 embedding 和 query embedding 使用了不同模型，检索结果会变得不可解释。",
    "chunk 太长会被截断，chunk 太短又丢上下文。",
    "只用向量召回容易漏掉制度编号、日期、部门名这类精确条件。",
  ],
};

function traceStepMap(traceData) {
  const map = new Map();
  function visit(step) {
    if (!step || !step.key) return;
    map.set(step.key, step);
    (step.children || []).forEach(visit);
  }
  (traceData?.steps || []).forEach(visit);
  return map;
}

function mergeTraceNode(staticNode, liveSteps) {
  const live = staticNode.traceKey ? liveSteps.get(staticNode.traceKey) : null;
  if (!live) return { ...staticNode, details: { ...(staticNode.details || {}) } };

  return {
    ...staticNode,
    title: staticNode.title || live.title,
    summary: live.summary || staticNode.summary,
    status: live.status || staticNode.status || "ok",
    mode: live.execution_mode || staticNode.mode || "sequential",
    duration_ms: live.duration_ms,
    details: {
      ...(staticNode.details || {}),
      ...(live.details || {}),
      backend_step_key: live.key,
      backend_status: live.status || "ok",
      inner_steps: (live.children || []).map((child) => child.title || child.key),
    },
  };
}

function hydrateRows(rows, liveSteps) {
  return rows.map((row) => {
    if (row.type === "parallel_group") {
      return {
        ...row,
        branches: row.branches.map((branch) => ({
          ...branch,
          nodes: branch.nodes.map((item) => mergeTraceNode(item, liveSteps)),
        })),
      };
    }
    return {
      ...row,
      nodes: (row.nodes || []).map((item) => mergeTraceNode(item, liveSteps)),
    };
  });
}

function buildRagWorkflow(traceData) {
  const rows = [
    { type: "serial", nodes: [node("request_intake", "请求接入", "接收用户问题、top_k 和本次 trace 上下文。", { traceKey: "request_intake", sequence: "01", details: { business_goal: "确认这次问题要进入哪条 RAG/Agent 链路，而不是直接丢给模型。" } })] },
    { type: "serial", nodes: [node("input_guardrails", "输入护栏", "检查空输入、超长输入、注入风险和参数边界。", { traceKey: "input_guardrails", sequence: "02", details: { why: "真实业务里模型调用前必须先判断请求是否安全、是否可处理。" } })] },
    { type: "serial", nodes: [node("normalize_text", "文本归一化", "只处理格式：去首尾空白、压缩连续空白，不偷偷改写语义。", { traceKey: "normalize_text", sequence: "03", details: { why: "清洗和改写要分离，否则 trace 中看不出原始问题被改成了什么。" } })] },
    { type: "serial", nodes: [node("query_understanding", "Query 理解", "识别意图、制度类别、对象范围、时间提示和歧义。", { traceKey: "query_understanding", sequence: "04", details: { why: "后续检索过滤、改写、是否反问都依赖这里的判断。" } })] },
    {
      type: "parallel_group",
      id: "rag_parallel_prepare",
      title: "并行准备：查询表示 + 检索约束",
      summary: "query 理解后，可以同时准备语义向量路径和检索过滤路径。",
      branches: [
        {
          title: "语义表示路径",
          nodes: [
            node("query_rewrite", "Query 改写", "补齐独立问题和同义词，提升召回但不能扩大问题范围。", { traceKey: "query_rewrite", sequence: "05A", mode: "parallel", details: { why: "用户问题常常很短，适度改写可以把口语问题变成可检索表达。" } }),
            node("tokenize", "分词与 token", "展示模型实际处理的 token 和 token id，确认输入没有被截断。", { traceKey: "tokenize", sequence: "05B", mode: "parallel", details: { why: "教学和调试时要看到模型到底吃进去了什么。" } }),
            node("query_embedding", "Query Embedding", "把检索问题转成向量，进入语义相似度空间。", { traceKey: "query_embedding", sequence: "05C", mode: "parallel", details: embeddingDetails }),
          ],
        },
        {
          title: "业务约束路径",
          nodes: [
            node("retrieval_plan", "检索计划", "准备 top_k、向量库、分类、权限、时间和 SQL 形状。", { traceKey: "retrieval_plan", sequence: "05D", mode: "parallel", details: { why: "真实企业 RAG 不能只看语义相似，还要受权限、分类、时效和来源约束。", options: ["按用户身份加 permission_scope 过滤", "按制度分类加 metadata filter", "按发布时间或生效时间做 freshness check"] } }),
          ],
        },
      ],
    },
    { type: "merge", title: "查询表示与检索计划汇聚", nodes: [node("retrieval_merge", "汇聚检索输入", "语义向量和业务过滤条件在这里合并，形成可执行检索请求。", { sequence: "06", mode: "merge", details: { why: "并行不是各做各的，必须在召回前汇合成统一的查询计划。" } })] },
    { type: "serial", nodes: [node("initial_retrieval", "初始召回", "用向量库或混合检索找到候选 chunk。", { traceKey: "initial_retrieval", sequence: "07" })] },
    { type: "serial", nodes: [node("rerank", "Rerank 重排序", "对候选证据重新打分，把更相关、更可引用的内容排到前面。", { traceKey: "rerank", sequence: "08", details: { why: "初始召回负责找全，rerank 负责把最可能回答问题的证据放到前面。" } })] },
    { type: "serial", nodes: [node("evidence_quality", "证据质量检查", "检查相关度、来源、时效、冲突和是否需要反问。", { traceKey: "evidence_quality", sequence: "09" })] },
    { type: "serial", nodes: [node("answer_and_observe", "答案与观测", "基于证据组织回答，并记录 trace、耗时和质量信号。", { traceKey: "answer_and_observe", sequence: "10", mode: "observe", details: { why: "最终答案只是结果，trace 才能帮助调试为什么这么答。" } })] },
  ];
  return {
    id: "rag-core",
    title: "RAG 基础流程",
    summary: "展示真实 RAG 问答里顺序、并行和汇聚关系。",
    rows: hydrateRows(rows, traceStepMap(traceData)),
  };
}

function workflowFromRows(id, title, summary, rows) {
  return () => ({ id, title, summary, rows: hydrateRows(rows, new Map()) });
}

const workflowDefinitions = [
  { id: "rag-core", title: "RAG 基础流程", build: buildRagWorkflow },
  {
    id: "embedding-retrieval",
    title: "Embedding 检索流程",
    build: workflowFromRows("embedding-retrieval", "Embedding 检索流程", "专门展开 query/document embedding、向量库和混合检索。", [
      { type: "serial", nodes: [node("embed_intake", "文本进入", "接收 query 或文档 chunk，先做空文本、长度和语言检查。", { sequence: "01", details: { quality_checks: embeddingDetails.quality_checks } })] },
      {
        type: "parallel_group",
        id: "embed_parallel",
        title: "双路径向量化",
        summary: "文档索引和查询检索是两条路径，但必须使用一致的模型和向量空间。",
        branches: [
          { title: "Document path", nodes: [node("doc_chunk", "文档切块", "按标题、条款、token 上限切 chunk。", { sequence: "02A" }), node("doc_embed", "Document Embedding", "把 chunk 转成 document embedding 并写入向量库。", { sequence: "02B", mode: "parallel", details: embeddingDetails })] },
          { title: "Query path", nodes: [node("query_clean", "查询清洗", "清洗用户 query 并保留原始语义。", { sequence: "02C" }), node("query_embed_static", "Query Embedding", "把用户问题转成 query embedding。", { sequence: "02D", mode: "parallel", details: embeddingDetails })] },
        ],
      },
      { type: "merge", title: "同一向量空间汇聚", nodes: [node("vector_space", "向量空间对齐", "确认模型、维度、归一化和版本一致。", { sequence: "03", mode: "merge", details: { pitfalls: embeddingDetails.pitfalls } })] },
      { type: "serial", nodes: [node("ann_search", "ANN / pgvector 检索", "用 cosine distance 或 inner product 找近邻。", { sequence: "04", details: { term_definitions: [term("ANN", "Approximate Nearest Neighbor，近似最近邻检索，用速度换取可接受的召回近似。"), term("HNSW", "常见向量索引结构，适合高维向量快速近邻搜索。")] } })] },
      { type: "serial", nodes: [node("hybrid_rerank", "混合召回与重排", "结合关键词、metadata filter 和 rerank，修正纯向量的误差。", { sequence: "05" })] },
    ]),
  },
  {
    id: "langchain-agent",
    title: "LangChain Agent",
    build: workflowFromRows("langchain-agent", "LangChain Agent", "展示 Agent 如何在工具、记忆和检索之间循环决策。", [
      { type: "serial", nodes: [node("lc_input", "输入与记忆", "接收用户输入，并读取会话记忆或业务上下文。", { sequence: "01" })] },
      { type: "parallel_group", id: "lc_tools", title: "工具准备", summary: "Agent 决策前先准备可用工具、retriever 和 prompt。", branches: [
        { title: "Prompt", nodes: [node("lc_prompt", "Prompt Template", "把角色、约束、工具说明拼成模型输入。", { sequence: "02A" })] },
        { title: "Tools", nodes: [node("lc_tools_node", "Tool Registry", "注册搜索、数据库、计算等工具。", { sequence: "02B", mode: "parallel" })] },
        { title: "Retriever", nodes: [node("lc_retriever", "Retriever", "包装 RAG 检索器供 Agent 调用。", { sequence: "02C", mode: "parallel" })] },
      ] },
      { type: "merge", title: "Agent 决策", nodes: [node("lc_plan", "Plan / Act", "模型选择下一步工具或直接回答。", { sequence: "03", mode: "merge" })] },
      { type: "serial", nodes: [node("lc_loop", "工具调用循环", "执行工具、读取 observation，再决定是否继续。", { sequence: "04", details: { pitfalls: ["工具返回必须进入可审计 observation。", "循环次数要有限制，否则容易成本失控。"] } })] },
    ]),
  },
  {
    id: "langgraph-workflow",
    title: "LangGraph 工作流",
    build: workflowFromRows("langgraph-workflow", "LangGraph 工作流", "展示状态图如何显式表达分支、并行和可恢复节点。", [
      { type: "serial", nodes: [node("lg_state", "State 初始化", "定义 query、messages、evidence、route 等状态字段。", { sequence: "01" })] },
      { type: "parallel_group", id: "lg_parallel", title: "Graph 节点并行", summary: "图结构可以把互不依赖的节点并行执行，再汇聚到状态。", branches: [
        { title: "Router", nodes: [node("lg_route", "路由节点", "判断走 RAG、工具调用、澄清还是拒答。", { sequence: "02A" })] },
        { title: "Retriever", nodes: [node("lg_retrieve", "检索节点", "拉取候选证据并写回 state。", { sequence: "02B", mode: "parallel" })] },
        { title: "Policy", nodes: [node("lg_policy", "策略节点", "检查权限、风险和输出规则。", { sequence: "02C", mode: "parallel" })] },
      ] },
      { type: "merge", title: "State 汇聚", nodes: [node("lg_merge", "Reducer / State Merge", "把多个节点结果合并为下一轮状态。", { sequence: "03", mode: "merge" })] },
      { type: "serial", nodes: [node("lg_checkpoint", "Checkpoint", "保存状态，支持失败恢复和人工介入。", { sequence: "04" })] },
    ]),
  },
  {
    id: "rewrite-rerank",
    title: "Query Rewrite + Rerank",
    build: workflowFromRows("rewrite-rerank", "Query Rewrite + Rerank", "专门展示召回前改写和召回后重排的质量控制。", [
      { type: "serial", nodes: [node("qr_understand", "Query 理解", "抽取实体、意图、时间和范围。", { sequence: "01" })] },
      { type: "parallel_group", id: "qr_parallel", title: "改写候选", summary: "多个改写候选可以并行生成，再做漂移检查。", branches: [
        { title: "同义词", nodes: [node("qr_synonym", "同义词扩展", "补年假/年休假等业务同义词。", { sequence: "02A" })] },
        { title: "独立问题", nodes: [node("qr_standalone", "Standalone Query", "把上下文依赖问题改写成独立问题。", { sequence: "02B", mode: "parallel" })] },
        { title: "过滤条件", nodes: [node("qr_filter", "Metadata Filter", "抽取分类、对象、时间等过滤条件。", { sequence: "02C", mode: "parallel" })] },
      ] },
      { type: "merge", title: "漂移检查", nodes: [node("qr_drift", "Semantic Drift Check", "确认改写没有改变用户原意。", { sequence: "03", mode: "merge" })] },
      { type: "serial", nodes: [node("qr_rerank", "Rerank", "用 cross-encoder 或规则模型重排候选证据。", { sequence: "04" })] },
    ]),
  },
  {
    id: "multi-agent",
    title: "多 Agent 协作",
    build: workflowFromRows("multi-agent", "多 Agent 协作", "展示多个角色并行处理任务，再由协调器汇总。", [
      { type: "serial", nodes: [node("ma_coordinator", "Coordinator", "拆任务、分配角色、定义验收标准。", { sequence: "01" })] },
      { type: "parallel_group", id: "ma_workers", title: "并行子任务", summary: "互不依赖的工作可以并行，结果需要统一审查。", branches: [
        { title: "Retriever Agent", nodes: [node("ma_retriever", "检索 Agent", "负责查证据和来源。", { sequence: "02A" })] },
        { title: "Reasoner Agent", nodes: [node("ma_reasoner", "推理 Agent", "负责基于证据形成候选答案。", { sequence: "02B", mode: "parallel" })] },
        { title: "Reviewer Agent", nodes: [node("ma_reviewer", "审查 Agent", "负责找漏洞、冲突和缺证据处。", { sequence: "02C", mode: "parallel" })] },
      ] },
      { type: "merge", title: "协调汇总", nodes: [node("ma_synthesis", "Synthesis", "合并结果、解决冲突、输出最终答案。", { sequence: "03", mode: "merge" })] },
    ]),
  },
  {
    id: "enterprise-ingest",
    title: "企业知识库导入",
    build: workflowFromRows("enterprise-ingest", "企业知识库导入", "展示真实制度数据如何从业务系统进入向量库。", [
      { type: "serial", nodes: [node("ingest_list", "枚举文档", "分页拉取文档 ID、标题、分类和发布时间。", { sequence: "01" })] },
      { type: "parallel_group", id: "ingest_parallel", title: "内容处理并行", summary: "正文、附件、权限和元数据可以分路径处理。", branches: [
        { title: "正文", nodes: [node("ingest_body", "正文清洗", "HTML/PDF/Word 清洗，保留标题层级。", { sequence: "02A" }), node("ingest_chunk", "Chunk 切分", "按章节和 token 预算切块。", { sequence: "02B" })] },
        { title: "附件", nodes: [node("ingest_files", "附件解析", "识别附件、表格和引用来源。", { sequence: "02C", mode: "parallel" })] },
        { title: "权限", nodes: [node("ingest_acl", "权限同步", "写入 audience、permission_scope 等 metadata。", { sequence: "02D", mode: "parallel" })] },
      ] },
      { type: "merge", title: "文档单元汇聚", nodes: [node("ingest_record", "PolicyChunk", "生成可检索、可引用、可权限过滤的 chunk 记录。", { sequence: "03", mode: "merge" })] },
      { type: "serial", nodes: [node("ingest_upsert", "Embedding + Upsert", "向量化后写入 pgvector，支持更新和删除同步。", { sequence: "04", details: embeddingDetails })] },
    ]),
  },
  {
    id: "langfuse-observe",
    title: "Langfuse 观测链路",
    build: workflowFromRows("langfuse-observe", "Langfuse 观测链路", "展示 RAG/Agent 如何记录 trace、评分和回放。", [
      { type: "serial", nodes: [node("lf_trace", "Trace 创建", "为一次用户请求创建 trace_id 和 session 信息。", { sequence: "01" })] },
      { type: "parallel_group", id: "lf_parallel", title: "观测事件", summary: "模型、检索、rerank、工具调用都可以作为 span 上报。", branches: [
        { title: "RAG", nodes: [node("lf_retrieval", "Retrieval Span", "记录 query、top_k、候选证据和耗时。", { sequence: "02A" })] },
        { title: "LLM", nodes: [node("lf_llm", "Generation Span", "记录 prompt、模型、token、输出和成本。", { sequence: "02B", mode: "parallel" })] },
        { title: "Quality", nodes: [node("lf_score", "Score / Feedback", "记录人工反馈、自动评分和质量标签。", { sequence: "02C", mode: "parallel" })] },
      ] },
      { type: "merge", title: "回放与分析", nodes: [node("lf_replay", "Replay", "按 trace 回放问题，定位召回、改写或生成问题。", { sequence: "03", mode: "merge" })] },
    ]),
  },
];

function shortTitle(title) {
  return String(title || "").replace(/^Step \d+ ·\s*/, "");
}

function modeLabel(mode) {
  const labels = {
    sequential: "顺序",
    parallel: "并行",
    merge: "汇聚",
    observe: "观测",
    branch: "分支",
  };
  return labels[mode] || "节点";
}

function renderNodeDetail(item) {
  const panel = document.createElement("div");
  panel.className = "detail-card";

  const header = document.createElement("div");
  header.className = "node-detail-header";

  const meta = document.createElement("div");
  meta.className = "node-detail-meta";
  const duration = item.duration_ms == null ? "" : ` · ${item.duration_ms} ms`;
  meta.textContent = `${modeLabel(item.mode)} · ${item.status || "ok"}${duration}`;

  const title = document.createElement("h3");
  title.textContent = shortTitle(item.title);

  const collapse = document.createElement("button");
  collapse.type = "button";
  collapse.className = "detail-collapse-button";
  collapse.textContent = "收起";
  collapse.addEventListener("click", () => collapseDetailPanel());

  const summary = document.createElement("p");
  summary.textContent = item.summary;

  header.append(meta, title, collapse, summary);
  panel.append(header, renderDetails(item.details));
  return panel;
}

function collapseDetailPanel() {
  const detailPanel = traceSteps.querySelector(".tree-detail-panel");
  if (!detailPanel) return;
  detailPanel.classList.add("collapsed");
  detailPanel.innerHTML = "";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "detail-open-button";
  button.textContent = "详情";
  button.addEventListener("click", () => {
    detailPanel.classList.remove("collapsed");
    detailPanel.innerHTML = '<div class="node-detail-empty">点击流程节点查看详细解释。</div>';
  });
  detailPanel.appendChild(button);
}

function selectWorkflowNode(item, nodeButton, detailPanel) {
  traceSteps.querySelectorAll(".trace-tree-node.selected").forEach((selected) => selected.classList.remove("selected"));
  nodeButton.classList.add("selected");
  detailPanel.classList.remove("collapsed");
  detailPanel.innerHTML = "";
  detailPanel.appendChild(renderNodeDetail(item));
}

function renderWorkflowNode(item, rowIndex, detailPanel) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = [
    "trace-tree-node",
    "workflow-node",
    `mode-${item.mode || "sequential"}`,
    `status-${item.status || "ok"}`,
  ].join(" ");

  const top = document.createElement("div");
  top.className = "tree-node-top";
  const index = document.createElement("span");
  index.className = "tree-step-index";
  index.textContent = item.sequence || String(rowIndex + 1).padStart(2, "0");
  const badge = document.createElement("span");
  badge.className = "tree-mode-badge";
  badge.textContent = modeLabel(item.mode || "sequential");
  top.append(index, badge);

  const title = document.createElement("div");
  title.className = "tree-node-title";
  title.textContent = shortTitle(item.title);

  const summary = document.createElement("div");
  summary.className = "tree-node-summary";
  summary.textContent = item.summary;

  button.append(top, title, summary);
  button.addEventListener("click", () => selectWorkflowNode(item, button, detailPanel));
  return button;
}

function renderInlineConnector() {
  const connector = document.createElement("div");
  connector.className = "elbow-connector inline";
  return connector;
}

function renderMergeRail(row) {
  const rail = document.createElement("div");
  rail.className = "merge-rail";
  const line = document.createElement("div");
  line.className = "merge-rail-line";
  const label = document.createElement("span");
  label.textContent = row.title || "汇聚";
  rail.append(line, label);
  return rail;
}

function renderWorkflowRow(row, rowIndex, detailPanel) {
  const wrapper = document.createElement("section");
  wrapper.className = `workflow-row ${row.type}`;

  if (row.type === "parallel_group") {
    const label = document.createElement("div");
    label.className = "parallel-label";
    label.textContent = row.title;
    const hint = document.createElement("p");
    hint.textContent = row.summary;

    const branches = document.createElement("div");
    branches.className = "parallel-branches";
    row.branches.forEach((branch) => {
      const branchEl = document.createElement("article");
      branchEl.className = "workflow-branch";
      const branchTitle = document.createElement("h3");
      branchTitle.textContent = branch.title;
      branchEl.appendChild(branchTitle);
      branch.nodes.forEach((item, index) => {
        if (index > 0) branchEl.appendChild(renderInlineConnector());
        branchEl.appendChild(renderWorkflowNode(item, rowIndex, detailPanel));
      });
      branches.appendChild(branchEl);
    });

    wrapper.append(label, hint, branches, renderMergeRail({ title: "并行结果汇聚" }));
    return wrapper;
  }

  if (row.type === "merge") {
    wrapper.appendChild(renderMergeRail(row));
  }

  const nodes = document.createElement("div");
  nodes.className = "workflow-row-nodes";
  (row.nodes || []).forEach((item, index) => {
    if (index > 0) nodes.appendChild(renderInlineConnector());
    nodes.appendChild(renderWorkflowNode(item, rowIndex, detailPanel));
  });
  wrapper.appendChild(nodes);
  return wrapper;
}

function getSelectedWorkflow() {
  const selectedId = workflowSelect.value || workflowDefinitions[0].id;
  const definition = workflowDefinitions.find((item) => item.id === selectedId) || workflowDefinitions[0];
  return definition.build(latestTraceData);
}

function renderWorkflowGraph(workflow) {
  traceSteps.innerHTML = "";
  const workbench = document.createElement("div");
  workbench.className = "trace-tree-workbench";

  const canvas = document.createElement("div");
  canvas.className = "trace-tree-canvas";

  const graph = document.createElement("div");
  graph.className = "workflow-graph";

  const intro = document.createElement("div");
  intro.className = "workflow-intro";
  intro.textContent = workflow.summary;
  graph.appendChild(intro);

  const detailPanel = document.createElement("aside");
  detailPanel.className = "tree-detail-panel";
  detailPanel.innerHTML = '<div class="node-detail-empty">点击流程节点查看工具、输入输出、选型原因和真实业务坑点。</div>';

  workflow.rows.forEach((row, index) => graph.appendChild(renderWorkflowRow(row, index, detailPanel)));
  canvas.appendChild(graph);
  workbench.append(canvas, detailPanel);
  traceSteps.appendChild(workbench);

  const firstNode = traceSteps.querySelector(".trace-tree-node");
  if (firstNode) firstNode.click();
}

function renderSelectedWorkflow() {
  const workflow = getSelectedWorkflow();
  traceSummary.textContent = latestTraceData ? `${workflow.title}：已叠加本次问题的执行细节` : workflow.summary;
  renderWorkflowGraph(workflow);
}

function populateWorkflowSelect() {
  workflowSelect.innerHTML = "";
  workflowDefinitions.forEach((definition) => {
    const option = document.createElement("option");
    option.value = definition.id;
    option.textContent = definition.title;
    workflowSelect.appendChild(option);
  });
}

async function ask(message) {
  appendMessage("user", message);
  appendMessage("assistant", "正在执行 RAG 流程...");
  const pending = messages.lastElementChild.querySelector(".bubble");

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, top_k: 3 }),
  });

  if (!response.ok) {
    let errorText = await response.text();
    try {
      const errorBody = JSON.parse(errorText);
      if (errorBody.detail?.message) {
        errorText = `${errorBody.detail.message}: ${errorBody.detail.error || "unknown error"}`;
      }
    } catch (_) {
      // Keep the plain response body when the server returns non-JSON errors.
    }
    pending.textContent = `请求失败：${errorText}`;
    return;
  }

  const data = await response.json();
  latestTraceData = data;
  pending.textContent = data.answer;
  workflowSelect.value = "rag-core";
  renderSelectedWorkflow();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  ask(message);
  input.value = "";
});

workflowSelect.addEventListener("change", () => renderSelectedWorkflow());

clearButton.addEventListener("click", () => {
  messages.innerHTML = "";
  latestTraceData = null;
  traceSummary.textContent = "选择一个流程节点查看细节";
  renderSelectedWorkflow();
});

populateWorkflowSelect();
renderSelectedWorkflow();
