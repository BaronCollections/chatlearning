const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const traceSteps = document.querySelector("#traceSteps");
const traceSummary = document.querySelector("#traceSummary");
const workflowSelect = document.querySelector("#workflowSelect");
const langfuseTraceLink = document.querySelector("#langfuseTraceLink");
const clearButton = document.querySelector("#clearButton");

let latestTraceData = null;
let detailDrawer = null;
let detailBackdrop = null;
let selectedDetailTrigger = null;

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

const answerSectionLabels = ["事实", "规则匹配", "违规类型", "处理结果", "处罚依据", "不确定性提醒", "结论", "处理建议"];

function stripAnswerSourceBlock(answerText) {
  return String(answerText || "").split("\n\n相关来源：")[0].replace(/\n?检索方式：.*$/, "").trim();
}

function parseAnswerSections(answerText) {
  const body = stripAnswerSourceBlock(answerText);
  if (!body) return [];
  const lines = body.split("\n").map((line) => line.trim()).filter(Boolean);
  const sections = [];
  let current = null;

  lines.forEach((line) => {
    const match = line.match(/^([^：]{2,10})：(.*)$/);
    const label = match ? match[1] : "";
    if (match && answerSectionLabels.includes(label)) {
      current = { label: label, lines: [] };
      const value = match[2].trim();
      if (value) current.lines.push(value);
      sections.push(current);
      return;
    }

    if (/^\d+[.．]/.test(line) && current?.label === "处理结果") {
      current.lines.push(line);
      return;
    }

    current = { label: null, lines: [line] };
    sections.push(current);
  });

  return sections;
}

function renderAnswerSection(section) {
  const article = document.createElement("article");
  article.className = `answer-section${section.label ? ` answer-section-${section.label}` : " answer-section-summary"}`;

  if (section.label) {
    const title = document.createElement("div");
    title.className = "answer-section-title";
    title.textContent = section.label;
    article.appendChild(title);
  }

  if (section.label === "处理结果" && section.lines.some((line) => /^\d+[.．]/.test(line))) {
    const list = document.createElement("ol");
    list.className = "answer-result-list";
    section.lines.forEach((line) => {
      const item = document.createElement("li");
      item.textContent = line.replace(/^\d+[.．]\s*/, "");
      list.appendChild(item);
    });
    article.appendChild(list);
    return article;
  }

  const body = document.createElement("p");
  body.className = "answer-section-body";
  body.textContent = section.lines.join("\n");
  article.appendChild(body);
  return article;
}

function renderStructuredAnswer(answerText) {
  const wrapper = document.createElement("section");
  wrapper.className = "structured-answer";
  const sections = parseAnswerSections(answerText);
  if (sections.length === 0) {
    const fallback = document.createElement("p");
    fallback.className = "answer-text";
    fallback.textContent = answerText || "";
    wrapper.appendChild(fallback);
    return wrapper;
  }
  sections.forEach((section) => wrapper.appendChild(renderAnswerSection(section)));
  return wrapper;
}

function renderAssistantResponse(bubble, data) {
  bubble.textContent = "";
  bubble.appendChild(renderStructuredAnswer(data.answer || ""));

  const citations = (data.answer_sources || (data.results || []).map((result) => result.citation)).filter(Boolean);
  if (citations.length === 0) return;

  const section = document.createElement("section");
  section.className = "answer-citations";
  const title = document.createElement("strong");
  title.textContent = "来源依据";
  const list = document.createElement("ul");
  citations.forEach((citation) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.className = "citation-label";
    label.textContent = citation.citation_id || "来源";
    item.appendChild(label);

    const sourceTitle = citation.title || citation.source || citation.url || "未命名来源";
    if (citation.url) {
      const link = document.createElement("a");
      link.className = "answer-source-title";
      link.href = citation.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = sourceTitle;
      item.appendChild(link);
    } else {
      const text = document.createElement("span");
      text.className = "answer-source-title";
      text.textContent = sourceTitle;
      item.appendChild(text);
    }

    const metaParts = [citation.category, citation.publish_date, citation.source ? `位置：${citation.source}` : null].filter(Boolean);
    if (metaParts.length > 0) {
      const metaText = document.createElement("small");
      metaText.textContent = metaParts.join(" / ");
      item.appendChild(metaText);
    }

    if (citation.url) {
      const sourceLink = document.createElement("a");
      sourceLink.className = "answer-source-link";
      sourceLink.href = citation.url;
      sourceLink.target = "_blank";
      sourceLink.rel = "noreferrer";
      sourceLink.textContent = "打开来源";
      item.appendChild(sourceLink);
    }
    list.appendChild(item);
  });
  section.append(title, list);
  bubble.appendChild(section);
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

function renderDataFlow(dataFlow) {
  if (!dataFlow || typeof dataFlow !== "object") return null;
  const section = renderSection("真实数据流转", "data-flow");
  const grid = document.createElement("div");
  grid.className = "data-flow-grid";

  [
    ["入参", dataFlow.input],
    ["出参", dataFlow.output],
  ].forEach(([labelText, payload]) => {
    const column = document.createElement("article");
    column.className = "data-flow-column";
    const label = document.createElement("strong");
    label.textContent = labelText;
    const pre = document.createElement("pre");
    pre.textContent = formatValue(payload || {});
    column.append(label, pre);
    grid.appendChild(column);
  });

  section.appendChild(grid);
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

function knowledge(question, answer) {
  return { question: question, answer: answer };
}

function issueSolution(issue, solution, impact) {
  return { issue: issue, solution: solution, impact: impact };
}

function normalizeQuestionKey(value) {
  const question = typeof value === "string" ? value : value?.question || value?.prompt || "";
  return String(question).trim().replace(/\s+/g, " ").toLowerCase();
}

function dedupeQuestions(values) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const deduped = [];
  values.forEach((value) => {
    const key = normalizeQuestionKey(value);
    if (!key || seen.has(key)) return;
    seen.add(key);
    deduped.push(value);
  });
  return deduped;
}

function renderCommonQuestions(values) {
  const questions = dedupeQuestions(values);
  if (questions.length === 0) return null;
  const section = renderSection("常见问题", "common-question-list");
  const list = document.createElement("ul");
  questions.forEach((value) => {
    const item = document.createElement("li");
    const question = document.createElement("strong");
    question.className = "knowledge-question";
    const answer = document.createElement("p");
    answer.className = "knowledge-answer";

    if (typeof value === "string") {
      question.textContent = value;
      answer.textContent = "回答时要结合输入、输出、失败分支和业务影响说明，避免只背概念。";
    } else {
      question.textContent = value.question || value.prompt || "常见问题";
      answer.textContent = value.answer || value.summary || "需要说明工程取舍、边界条件和真实业务中的验证方式。";
    }

    item.append(question, answer);
    list.appendChild(item);
  });
  section.appendChild(list);
  return section;
}

function renderIssueSolutions(values) {
  if (!Array.isArray(values) || values.length === 0) return null;
  const section = renderSection("问题与解决", "issue-solution-list");
  values.forEach((value) => {
    const row = document.createElement("article");
    row.className = "issue-solution-item";
    const issue = document.createElement("strong");
    issue.className = "issue-title";
    const solution = document.createElement("p");
    solution.className = "solution-text";

    if (typeof value === "string") {
      issue.textContent = value;
      solution.textContent = "先定位 trace 中的输入、输出、异常和下游依赖，再按业务风险选择重试、降级、拒答或人工确认。";
    } else {
      issue.textContent = value.issue || value.title || "可能问题";
      solution.textContent = value.solution || value.recommendation || "推荐用可观测 trace、参数校验、质量阈值和回归样本定位并修复。";
      if (value.impact) {
        const impact = document.createElement("span");
        impact.className = "issue-impact";
        impact.textContent = `影响：${value.impact}`;
        row.appendChild(impact);
      }
    }

    row.prepend(issue);
    row.appendChild(solution);
    section.appendChild(row);
  });
  return section;
}

function renderRequirementDetail(details) {
  if (!details?.requirement && !details?.requirement_reason) return null;
  const section = renderSection("流程必要性", "requirement-detail");
  const note = document.createElement("p");
  note.className = "requirement-note";
  const label = details.requirement ? `${details.requirement}：` : "";
  note.textContent = `${label}${details.requirement_reason || "根据业务目标、成本、质量要求和风险等级决定是否执行。"}`;
  section.appendChild(note);
  return section;
}

function renderEnhancementDetail(enhancements) {
  if (!Array.isArray(enhancements) || enhancements.length === 0) return null;
  const section = renderSection("生产 RAG 成熟度", "enhancement-detail");
  enhancements.forEach((enhancement) => {
    const article = document.createElement("article");
    article.className = `enhancement-card status-${enhancement.status || "planned"}`;

    const header = document.createElement("div");
    header.className = "enhancement-card-header";
    const title = document.createElement("h4");
    title.textContent = enhancement.title || enhancement.id;
    const badges = document.createElement("div");
    badges.className = "enhancement-badge-row";
    if (enhancement.current) {
      const current = document.createElement("span");
      current.className = "enhancement-current-badge";
      current.textContent = "本轮优化";
      badges.appendChild(current);
    }
    const status = document.createElement("span");
    status.className = `enhancement-status-badge status-${enhancement.status || "planned"}`;
    status.textContent = enhancementStatusLabels[enhancement.status] || enhancement.status || "待接入";
    badges.appendChild(status);
    header.append(title, badges);

    const summary = document.createElement("p");
    summary.className = "enhancement-summary";
    summary.textContent = enhancement.summary || "生产 RAG 增强项。";

    const fields = document.createElement("dl");
    fields.className = "enhancement-fields";
    [
      ["解决的问题", enhancement.solves],
      ["落地方式", enhancement.implementation],
      ["验收方式", enhancement.acceptance],
      ["边界条件", enhancement.boundaries],
    ].forEach(([labelText, value]) => {
      if (!value) return;
      const dt = document.createElement("dt");
      dt.textContent = labelText;
      const dd = document.createElement("dd");
      dd.textContent = value;
      fields.append(dt, dd);
    });

    article.append(header, summary, fields);
    section.appendChild(article);
  });
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
    "inner_steps",
    "knowledge_points",
    "issue_solutions",
    "production_enhancements",
    "requirement",
    "requirement_reason",
    "data_flow",
  ];
  Object.entries(details || {}).forEach(([key, value]) => {
    if (structuredKeys.includes(key)) return;
    appendValue(list, key, value);
  });
  if (list.children.length > 0) wrapper.appendChild(list);

  const dataFlow = renderDataFlow(details?.data_flow);
  if (dataFlow) wrapper.appendChild(dataFlow);

  const requirementNote = renderRequirementDetail(details);
  if (requirementNote) wrapper.appendChild(requirementNote);

  const enhancementDetail = renderEnhancementDetail(details?.production_enhancements);
  if (enhancementDetail) wrapper.appendChild(enhancementDetail);

  const termList = renderTermList(details?.term_definitions);
  if (termList) wrapper.appendChild(termList);

  const pitfalls = renderBulletList("常见坑", "pitfall-list", details?.pitfalls);
  if (pitfalls) wrapper.appendChild(pitfalls);

  const options = renderBulletList("真实项目还会补", "option-list", details?.options);
  if (options) wrapper.appendChild(options);

  const innerSteps = renderBulletList("细节点", "inner-detail-list", details?.inner_steps);
  if (innerSteps) wrapper.appendChild(innerSteps);

  const commonQuestions = renderCommonQuestions(details?.knowledge_points);
  if (commonQuestions) wrapper.appendChild(commonQuestions);

  const issueSolutions = renderIssueSolutions(details?.issue_solutions);
  if (issueSolutions) wrapper.appendChild(issueSolutions);

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


const globalTermCatalog = [
  { term: "RAG", definition: "Retrieval-Augmented Generation，先检索可信知识，再让模型基于证据回答，适合制度、知识库、文档问答。", aliases: ["RAG", "检索增强"] },
  { term: "Query", definition: "进入检索系统的问题表达，可以是用户原文，也可以是经过清洗、改写后的检索问题。", aliases: ["Query", "查询"] },
  { term: "Query rewrite", definition: "把口语化、上下文依赖的问题改写成更适合检索的独立问题；它能提升召回，也可能引入语义漂移。", aliases: ["Query 改写", "rewrite", "改写"] },
  { term: "Semantic drift", definition: "处理前后问题的对象、时间、动作或范围发生变化，导致检索和答案偏离用户原意。", aliases: ["语义漂移", "drift"] },
  { term: "Token", definition: "模型词表里的最小处理单元，不等同于中文词语；同一句话会被 tokenizer 切成多个 token id。", aliases: ["token", "分词"] },
  { term: "Token id", definition: "token 在模型词表中的整数编号，展示它能帮助理解模型真实接收的输入。", aliases: ["token id", "Token id"] },
  { term: "Embedding", definition: "把文本映射成向量，语义相近的文本在向量空间里距离更近。", aliases: ["Embedding", "向量"] },
  { term: "Dense embedding", definition: "稠密向量表示，适合语义相似度检索，但对编号、专有名词等精确匹配不一定敏感。", aliases: ["dense", "稠密"] },
  { term: "Sparse / BM25", definition: "基于词项匹配的稀疏检索信号，适合制度编号、部门名、日期、人名等精确匹配，常和 dense 混合使用。", aliases: ["Sparse", "BM25", "关键词"] },
  { term: "Hybrid search", definition: "混合检索，把向量语义召回和关键词/稀疏召回合并，兼顾语义泛化和精确命中。", aliases: ["Hybrid", "混合检索"] },
  { term: "Chunk", definition: "把长文档按标题、段落、条款或 token 上限拆成可检索片段，是 RAG 的基本索引单元。", aliases: ["chunk", "切块"] },
  { term: "Metadata filter", definition: "基于分类、权限、时间、来源等结构化字段过滤候选，企业 RAG 通常必须做。", aliases: ["metadata", "filter", "过滤"] },
  { term: "Top-k", definition: "召回候选数量；太小容易漏证据，太大增加成本并带入噪声。", aliases: ["top_k", "top-k", "Top-k"] },
  { term: "Initial retrieval", definition: "初始召回，从向量库、关键词索引或混合检索中找候选证据；没有召回就没有可依据的上下文。", aliases: ["初始召回", "retrieval", "召回"] },
  { term: "Rerank", definition: "对初始候选重新排序，常用于减少语义相似但业务不相关的结果；它是质量增强，不是所有场景都必须。", aliases: ["Rerank", "重排序", "rerank"] },
  { term: "Cross-encoder", definition: "同时读取 query 和文档片段并输出相关性分数的重排模型，质量通常更好但成本和延迟更高。", aliases: ["Cross-encoder", "cross encoder"] },
  { term: "Evidence quality", definition: "检查证据是否相关、最新、来源可信、无冲突，并决定是否回答、拒答或反问。", aliases: ["证据质量", "evidence"] },
  { term: "Hallucination", definition: "模型生成了缺少证据或与证据冲突的内容；RAG 通过引用证据、阈值和拒答机制降低它。", aliases: ["hallucination", "幻觉"] },
  { term: "pgvector", definition: "PostgreSQL 的向量扩展，可以把业务 metadata 和向量索引放在同一个数据库系统里。", aliases: ["pgvector", "PostgreSQL"] },
  { term: "ANN", definition: "Approximate Nearest Neighbor，近似最近邻检索，用可接受的近似换取高维向量检索速度。", aliases: ["ANN", "近似最近邻"] },
  { term: "HNSW", definition: "常见 ANN 图索引结构，适合高维向量快速近邻搜索，pgvector 也支持。", aliases: ["HNSW"] },
  { term: "LangChain", definition: "LLM 应用开发框架，提供 prompt、model、tool、retriever 等组件，但生产系统仍需补边界、观测和降级。", aliases: ["LangChain"] },
  { term: "LangGraph", definition: "把 Agent/LLM 流程建成有状态图，适合分支、循环、并行、checkpoint 和人工介入。", aliases: ["LangGraph"] },
  { term: "Agent", definition: "能基于状态选择下一步动作的模型驱动流程，通常会调用工具、检索器或其他子任务。", aliases: ["Agent"] },
  { term: "Tool call", definition: "模型请求执行外部函数或服务，生产里必须限制输入输出 schema、权限和调用次数。", aliases: ["Tool Call", "工具调用"] },
  { term: "Observation", definition: "工具调用返回给 Agent 的结果，应该进入 trace，方便审计模型为什么继续下一步。", aliases: ["Observation"] },
  { term: "Trace / Span", definition: "trace 表示一次完整请求，span 表示其中一个步骤；二者用于定位 RAG/Agent 错误发生在哪个环节。", aliases: ["trace", "span", "Trace", "Span"] },
  { term: "Langfuse", definition: "LLM/RAG/Agent 观测平台，可记录 trace、span、输入输出、耗时、评分和回放。", aliases: ["Langfuse"] },
  { term: "Checkpoint", definition: "保存工作流状态，失败后可以从中间恢复，避免整条链路重跑。", aliases: ["Checkpoint", "checkpoint"] },
  { term: "Reducer", definition: "在图工作流里合并多个节点输出的函数，决定并行结果如何写回共享 state。", aliases: ["Reducer", "reducer"] },
  { term: "Upsert", definition: "有则更新、无则插入，适合知识库导入的断点续跑和重复写入。", aliases: ["Upsert", "upsert"] },
];

const requirementLabels = {
  required: "必经",
  optional: "可选增强",
  conditional: "条件触发",
};

const requirementDescriptions = {
  required: "这一步是该流程的核心约束，不执行会破坏链路语义或无法产生可信输出。",
  optional: "这一步用于提升质量、解释性或稳定性，可以按业务质量、延迟和成本要求选择。",
  conditional: "这一步由场景触发，例如检索策略、输入复杂度、权限要求或部署方式不同会影响是否执行。",
};

const enhancementStatusLabels = {
  shipped: "已落地",
  interface: "接口已预留",
  planned: "待接入",
};

function productionEnhancement(config) {
  return {
    current: true,
    requirement: "optional",
    status: "planned",
    term_definitions: [],
    knowledge_points: [],
    issue_solutions: [],
    ...config,
  };
}

const productionEnhancements = [
  productionEnhancement({
    id: "eval_runner",
    title: "回归评测集与 Eval Runner",
    stage: "质量评测闭环",
    status: "shipped",
    requirement: "required",
    summary: "把典型问题、期望来源、必须命中的关键词和禁止词沉淀成可重复运行的评测样本。",
    solves: "解决每次手工提问才发现问题、修 A 坏 B 无法证明的质量回归。",
    implementation: "后端已提供 evaluate_regression_case / evaluate_regression_cases，按 doc_id、URL、关键词和 forbidden keyword 给出通过率；下一步可接 CLI、CI 和 Langfuse dataset。",
    acceptance: "新增检索策略、chunk 策略或 rerank 参数后，核心制度问答样本必须稳定通过，并能看到失败原因。",
    boundaries: "评测只判断可观测信号，不替代人工制度解释；没有标准答案的开放问题应单独建人工评分集。",
    term_definitions: [
      term("Eval Runner", "批量运行标准问题集并输出通过率、失败原因和回归对比的评测执行器。"),
      term("Forbidden keyword", "答案中不应该出现的词，用来防止相邻章节、错误制度或越权内容混入。"),
    ],
    knowledge_points: [knowledge("RAG 为什么一定要有回归评测？", "因为检索、切块、rerank 和 prompt 都会互相影响；没有评测集就无法证明一次优化没有破坏其它问题。")],
    issue_solutions: [issueSolution("只靠人工点几个问题验收", "把高频问题、事故问题和边界问题写成 regression cases，每次改动自动跑。", "线上会反复出现同类错误，团队无法量化质量是否提升。")],
  }),
  productionEnhancement({
    id: "bad_case_feedback",
    title: "坏例采集与反馈闭环",
    stage: "质量评测闭环",
    status: "shipped",
    requirement: "required",
    summary: "把用户点踩、错来源、缺条款、答太泛等反馈保存成结构化坏例。",
    solves: "解决线上回答错了以后只能看聊天记录，无法沉淀为下一轮评测和修复输入。",
    implementation: "后端提供 /api/feedback 和 bad_cases JSONL 写入，只保存 query、反馈类型、答案和 citation 摘要，不保存完整制度正文或原始 trace。",
    acceptance: "提交 missing_clause / wrong_source 等反馈后，data/bad_cases.jsonl 中能看到可回放的最小记录，且不包含完整 chunk text。",
    boundaries: "反馈不直接修改答案，也不自动训练模型；需要人工或离线任务审核后再进入评测集。",
    term_definitions: [term("Bad Case", "线上或测试中发现的失败样本，通常包含 query、错误类型、期望证据和复现信息。")],
    knowledge_points: [knowledge("坏例为什么不能只存在聊天历史里？", "聊天历史难检索、难分类、难回归；结构化坏例才能进入评测、排期和质量看板。")],
    issue_solutions: [issueSolution("保存完整 trace 或正文造成数据风险", "只保存 citation 摘要、doc_id、chunk_id 和反馈标签；敏感正文通过授权环境重新拉取。", "内部制度、个人信息或权限内容可能被错误写入可提交文件。")],
  }),
  productionEnhancement({
    id: "ingest_quality_report",
    title: "导入质量报告",
    stage: "数据治理",
    status: "interface",
    requirement: "required",
    summary: "统计每次导入的分类、页数、文档数、chunk 数、空正文、重复 ID、解析失败和跳过原因。",
    solves: "解决知识库看似导入成功，但实际缺正文、缺权限、重复 chunk 或附件解析失败的问题。",
    implementation: "导入链路已有分类和导入统计对象；需要补充质量报告落盘、阈值判断和前端查看入口。",
    acceptance: "每次导入都输出 category-level report，能回答处理了哪些分类、多少文档、失败原因是什么。",
    boundaries: "报告只能证明导入过程完整，不保证制度内容本身是最新或业务解释正确。",
    term_definitions: [term("Ingestion Quality Report", "导入任务的质量账本，记录源数据、处理结果、失败原因和可审计统计。")],
    issue_solutions: [issueSolution("只看 upsert 成功数", "同时校验 source count、detail count、chunk count、empty body、ACL 字段和 citation URL。", "检索失败时无法判断是没导入、切坏了，还是检索策略错。")],
  }),
  productionEnhancement({
    id: "audience_permission_filter",
    title: "适用对象与权限过滤",
    stage: "检索治理",
    status: "planned",
    requirement: "required",
    summary: "把员工、学生、学段、部门、制度分类和可见范围作为 metadata filter 参与召回。",
    solves: "解决员工问题命中学生制度、未授权用户看到内部制度、跨学段答案混用的问题。",
    implementation: "导入时写入 audience、permission_scope、category、stage 等字段；检索计划阶段按用户身份生成强制过滤条件。",
    acceptance: "同一个问题在不同用户身份下返回的候选范围不同，越权文档在初始召回前就被过滤。",
    boundaries: "权限过滤必须依赖真实登录态和组织权限系统；前端展示不能替代后端强约束。",
    term_definitions: [term("Audience Filter", "按适用对象和用户可见范围限制候选文档的 metadata 过滤条件。")],
    issue_solutions: [issueSolution("只在答案阶段提示适用对象", "权限和 audience 要在 retrieval plan 和 SQL/filter 层执行，不能等生成后再补一句提醒。", "错误证据一旦进入上下文，模型可能已经泄露或混用。")],
  }),
  productionEnhancement({
    id: "structured_answer_contract",
    title: "结构化答案契约",
    stage: "答案生成",
    status: "shipped",
    requirement: "required",
    summary: "答案按事实复述、规则匹配、结论、依据、不确定性提醒组织，而不是直接贴 chunk。",
    solves: "解决回答冗长、夹带无关章节、用户看不出为什么得到这个结论的问题。",
    implementation: "规则型问题已按用户事实、匹配条件、处理结果和来源生成结构化回答；后续可进一步固定 JSON schema 给前端渲染。",
    acceptance: "问旷工两天、虚假报销、打听工资时，答案能说明命中哪个制度条件、属于什么违规、处理结果是什么。",
    boundaries: "结构化答案不能弥补证据不足；证据不足时应拒答或反问，不允许用格式包装猜测。",
    term_definitions: [term("Answer Contract", "后端承诺给前端和用户的答案结构，包括结论、证据、边界、来源和不确定性。")],
    issue_solutions: [issueSolution("把候选 chunk 整段输出", "先做 span extraction 和规则匹配，再输出结论条目和引用。", "答案会混入上一节/下一节内容，学习者也看不懂推理路径。")],
  }),
  productionEnhancement({
    id: "multi_hop_resolver",
    title: "多跳规则解析器",
    stage: "Query 理解与规则匹配",
    status: "shipped",
    requirement: "conditional",
    summary: "把用户事实转换成制度条件，再从条件跳到处罚或处理结果。",
    solves: "解决 `我旷工两天会怎样` 这类问题只召回定义块，找不到最终处罚条款。",
    implementation: "已抽出 policy_rule_resolver，把行为、次数/天数、阈值、命中规则和结论证据结构化，支持旷工、虚假报销、打听工资等样例。",
    acceptance: "系统能解释 `2 < 3`，所以命中 `连续旷工3个工作日以下`，并返回扣薪和记过处分。",
    boundaries: "当前规则解析覆盖核心样例；复杂金额、累计次数、跨制度引用还需要从制度文本抽取更多规则。",
    term_definitions: [term("Multi-hop Resolver", "先找到线索或条件，再跳到最终规则/结论的解析器，常用于制度、法规和流程问答。")],
    issue_solutions: [issueSolution("只召回包含用户原词的片段", "识别行为和问题面后，补充同义词与目标属性，例如处罚、处分、处理方式。", "用户问处罚却只得到违规定义。")],
  }),
  productionEnhancement({
    id: "cross_encoder_reranker",
    title: "Cross-encoder Reranker",
    stage: "检索排序",
    status: "interface",
    requirement: "optional",
    summary: "用 query+候选文本成对打分，把真正能回答问题的证据排在前面。",
    solves: "解决初始召回候选很多、相似章节互相干扰、关键词命中但不能回答问题的问题。",
    implementation: "已预留 RerankerClient、RERANKER_SERVICE_URL、RERANKER_PROVIDER；当前可接 bge-reranker-v2-m3 或企业内部 rerank 服务。",
    acceptance: "启用外部 reranker 后，trace 展示 rerank 前后排序、score 和原因；服务不可用时保留确定性规则兜底。",
    boundaries: "Rerank 只能重排已召回候选，不能补救没入库、没召回、权限漏过滤或 chunk 混段。",
    term_definitions: [term("Cross-encoder", "把 query 和候选文本一起输入模型打相关性分数，通常比单独向量相似度更准但更慢。")],
    issue_solutions: [issueSolution("把 reranker 当万能修复", "先保证召回池足够、权限正确、chunk 边界干净，再让 reranker 排序。", "候选池没有正确答案时，reranker 只能在错误候选里选一个。")],
  }),
  productionEnhancement({
    id: "query_router",
    title: "Query Router 查询路由",
    stage: "请求编排",
    status: "interface",
    requirement: "required",
    summary: "按问题类型选择精确条款、语义问答、规则解析、多跳检索、拒答或澄清。",
    solves: "解决所有问题都走同一条 RAG 流程，导致精确条款、处罚问法和开放问法互相干扰。",
    implementation: "Query understanding 已输出 exact_policy_lookup、asked_aspect、target_behavior 等字段；下一步抽象成独立 router 层。",
    acceptance: "`二类违规是什么`、`二类违规处罚是什么`、`我旷工两天会怎样` 会进入不同检索和证据策略。",
    boundaries: "Router 的输出必须可回放，不能用黑盒 prompt 随机决定流程；低置信度时应进入澄清或保守策略。",
    term_definitions: [term("Query Router", "根据意图、风险和证据需求选择后续检索/工具/回答路径的路由器。")],
    issue_solutions: [issueSolution("所有 query 都只做向量检索", "先识别问题面和风险等级，再选择 exact、hybrid、multi-hop 或普通 semantic search。", "精确规则问题会被语义相似章节冲掉。")],
  }),
  productionEnhancement({
    id: "citation_span_highlight",
    title: "引用 Span 高亮",
    stage: "证据展示",
    status: "interface",
    requirement: "required",
    summary: "引用不只指向文档，还要指向章节、条款号和命中的最小文本 span。",
    solves: "解决来源链接正确但证据范围太大，用户无法判断结论到底来自哪句话。",
    implementation: "后端已有章节边界截取和 citation metadata；下一步把 start/end span、clause_path 和前端高亮接上。",
    acceptance: "点击来源能看到具体命中的条款，例如 `4. 弄虚作假行为` 的 4.1-4.4，而不是整篇制度。",
    boundaries: "没有可靠位置偏移的 HTML/PDF 只能做章节级引用，不能伪造精确高亮。",
    term_definitions: [term("Citation Span", "答案引用对应的最小证据片段，包含文档、章节、条款和文本范围。")],
    issue_solutions: [issueSolution("来源只到文档级", "导入时保留 section_path、clause_no、chunk_id；回答时返回引用 span。", "用户需要自己在长制度里搜索，信任成本高。")],
  }),
  productionEnhancement({
    id: "langfuse_otel_observability",
    title: "Langfuse / OpenTelemetry 观测",
    stage: "线上观测",
    status: "interface",
    requirement: "required",
    summary: "把 query understanding、rewrite、embedding、retrieval、rerank、answer、feedback 都作为 trace/span 记录。",
    solves: "解决线上回答错了以后无法判断是数据、检索、rerank、prompt、模型还是权限问题。",
    implementation: "当前前端和后端已有本地 trace；已预留 Langfuse/OTel 观测链路说明，后续接 exporter 和采样策略。",
    acceptance: "每次请求能通过 trace_id 回放输入输出、耗时、候选、rerank 分数、证据过滤原因和最终答案。",
    boundaries: "观测平台不能记录敏感原文到外部；生产要做脱敏、采样和保留周期控制。",
    term_definitions: [term("OpenTelemetry", "通用可观测性标准，用 trace、span、metric、log 串联分布式系统行为。")],
    issue_solutions: [issueSolution("只有最终答案日志", "按节点记录输入、输出、耗时、状态和关键中间值，并统一 trace_id。", "问题定位只能猜，无法复现。")],
  }),
  productionEnhancement({
    id: "incremental_sync_versioning",
    title: "增量同步与版本管理",
    stage: "数据治理",
    status: "planned",
    requirement: "required",
    summary: "按源系统更新时间、版本号和删除状态同步文档，避免重复导入和旧制度残留。",
    solves: "解决制度更新后向量库仍回答旧版本、源系统删除后知识库还搜得到的问题。",
    implementation: "需要为 doc_id、source_updated_at、content_hash、embedding_version、deleted_at 建同步策略和幂等 upsert。",
    acceptance: "同一文档更新后只保留当前版本可检索；下架文档从 chunk 表和向量索引同步删除或软删除。",
    boundaries: "如果源系统没有可靠更新时间或删除事件，需要定期全量校验和 hash 对账。",
    term_definitions: [term("Incremental Sync", "只处理新增、变更、删除数据的同步方式，比每次全量重建更快也更可审计。")],
    issue_solutions: [issueSolution("只追加不删除", "同步任务必须处理 delete/disable 状态，并记录版本和 hash。", "用户可能拿到已经废止的制度答案。")],
  }),
  productionEnhancement({
    id: "document_parser_multimodal",
    title: "PDF / Word / 表格 / 多模态解析",
    stage: "数据接入",
    status: "planned",
    requirement: "conditional",
    summary: "解析附件、表格、扫描件和图片，保留标题层级、页码、表头和来源位置。",
    solves: "解决制度正文在附件里、表格规则被拉平成乱码、扫描件无法检索的问题。",
    implementation: "按文件类型接 unstructured、docling、pymupdf、OCR 或企业文档解析服务；解析结果统一成 PolicyChunk。",
    acceptance: "附件中的表格条款能被检索并带页码/表格标题引用，解析失败进入导入质量报告。",
    boundaries: "OCR 和复杂表格有误识别风险，高风险制度需要人工抽检或双解析器对比。",
    term_definitions: [term("Document Parser", "把 PDF、Word、HTML、表格、图片等原始文件转换成可检索结构化文本的解析器。")],
    issue_solutions: [issueSolution("附件只保存文件名不解析", "导入任务把附件解析结果作为独立 source，并保留 page/table/cell metadata。", "用户问附件里的规则时永远召回不到。")],
  }),
  productionEnhancement({
    id: "prompt_injection_guardrails",
    title: "Prompt Injection 与数据泄露护栏",
    stage: "安全治理",
    status: "planned",
    requirement: "required",
    summary: "识别忽略制度、泄露系统提示、导出全部知识库、越权索取等攻击输入和恶意文档内容。",
    solves: "解决用户或文档诱导模型绕过证据、泄露内部信息或执行危险工具的问题。",
    implementation: "在输入护栏、文档清洗、工具调用和答案阶段分别做注入检测、权限校验、拒答和审计记录。",
    acceptance: "攻击型 query 不进入检索/生成，恶意文档内容不会被当作系统指令执行，trace 记录拒绝原因。",
    boundaries: "护栏不能只靠关键词；必须结合权限、工具边界、系统提示隔离和输出审查。",
    term_definitions: [term("Prompt Injection", "通过用户输入或文档内容诱导模型忽略原规则、泄露信息或执行非预期操作的攻击。")],
    issue_solutions: [issueSolution("只在最终答案阶段拦截", "入口、检索文档、工具调用和输出都要做分层防护。", "恶意内容可能已经污染上下文或触发工具。")],
  }),
  productionEnhancement({
    id: "cache_cost_control",
    title: "缓存与成本控制",
    stage: "性能与成本",
    status: "planned",
    requirement: "optional",
    summary: "对 embedding、rerank、检索结果、模型回答和静态元数据做可失效缓存与预算控制。",
    solves: "解决重复问题反复调用模型、延迟高、成本不可控、外部服务抖动的问题。",
    implementation: "按 normalized_query、embedding_version、retrieval_filters、model_version 设计 cache key，并记录命中率和失效条件。",
    acceptance: "重复查询命中缓存时 trace 显示 cache_hit，成本和耗时下降；制度更新后相关缓存被失效。",
    boundaries: "权限相关结果不能跨用户共享缓存；制度更新、模型版本变化和过滤条件变化必须失效。",
    term_definitions: [term("Cache Key", "决定一条缓存是否可复用的唯一键，必须包含会影响结果的模型、权限和过滤条件。")],
    issue_solutions: [issueSolution("按原始 query 全局缓存答案", "缓存 key 加用户权限、过滤条件、模型版本和数据版本；高风险答案只缓存证据不缓存结论。", "不同用户可能看到彼此不该看的制度答案。")],
  }),
  productionEnhancement({
    id: "external_knowledge_api",
    title: "外部知识 API 与工具检索",
    stage: "系统集成",
    status: "planned",
    requirement: "conditional",
    summary: "当本地知识库不足时，按白名单调用 HR、OA、工单、搜索或业务系统 API 补充实时事实。",
    solves: "解决 RAG 库只适合静态制度，无法回答实时审批状态、个人额度、最新流程状态的问题。",
    implementation: "通过 tool registry 定义工具 schema、权限、超时、重试、降级和引用格式；router 决定何时调用。",
    acceptance: "静态制度问题不调用外部 API；实时个人化问题必须带用户权限和 trace，并清楚标出数据来源。",
    boundaries: "外部工具调用必须最小权限、可审计、可超时降级；不能让模型自由拼 URL 或 SQL。",
    term_definitions: [term("Tool Registry", "集中声明可调用工具、参数 schema、权限、超时和返回契约的注册表。")],
    issue_solutions: [issueSolution("让模型直接决定任意 API 调用", "只允许调用白名单工具，并由后端校验参数、权限和速率。", "可能造成越权查询、费用失控或业务系统误操作。")],
  }),
];

const productionEnhancementById = new Map(productionEnhancements.map((item) => [item.id, item]));

const enhancementNodeMap = {
  request_intake: ["query_router", "cache_cost_control"],
  input_guardrails: ["prompt_injection_guardrails"],
  query_understanding: ["query_router", "multi_hop_resolver"],
  query_rewrite: ["query_router"],
  retrieval_plan: ["audience_permission_filter", "external_knowledge_api", "cache_cost_control"],
  initial_retrieval: ["audience_permission_filter", "external_knowledge_api"],
  rerank: ["cross_encoder_reranker"],
  evidence_quality: ["citation_span_highlight", "prompt_injection_guardrails"],
  answer_and_observe: ["structured_answer_contract", "bad_case_feedback", "eval_runner", "langfuse_otel_observability"],
  ingest_list: ["incremental_sync_versioning", "ingest_quality_report"],
  ingest_body: ["document_parser_multimodal"],
  ingest_files: ["document_parser_multimodal"],
  ingest_acl: ["audience_permission_filter"],
  ingest_record: ["citation_span_highlight"],
  ingest_upsert: ["incremental_sync_versioning", "cache_cost_control"],
  ingest_validate: ["ingest_quality_report"],
  ingest_delete_sync: ["incremental_sync_versioning"],
  lf_trace: ["langfuse_otel_observability"],
  lf_retrieval: ["langfuse_otel_observability"],
  lf_llm: ["langfuse_otel_observability"],
  lf_score: ["bad_case_feedback", "eval_runner", "langfuse_otel_observability"],
  lf_dataset: ["eval_runner", "bad_case_feedback"],
};

function resolveProductionEnhancements(ids = []) {
  return [...new Set(ids)].map((id) => productionEnhancementById.get(id)).filter(Boolean);
}

function mergeTermDefinitions(baseTerms = [], enhancements = []) {
  const terms = Array.isArray(baseTerms) ? [...baseTerms] : [];
  const seen = new Set(terms.map((entry) => entry.term || entry.name));
  enhancements.forEach((enhancement) => {
    (enhancement.term_definitions || []).forEach((entry) => {
      const key = entry.term || entry.name;
      if (!key || seen.has(key)) return;
      seen.add(key);
      terms.push(entry);
    });
  });
  return terms;
}

function withProductionEnhancements(details = {}, enhancements = []) {
  if (!Array.isArray(enhancements) || enhancements.length === 0) return details;
  return {
    ...details,
    production_enhancements: enhancements,
    term_definitions: mergeTermDefinitions(details.term_definitions, enhancements),
  };
}

function normalizeRequirement(value) {
  return ["required", "optional", "conditional"].includes(value) ? value : "required";
}

function enrichTermDefinitions(details = {}, item = {}) {
  const existing = Array.isArray(details.term_definitions) ? details.term_definitions : [];
  const terms = [...existing];
  const seen = new Set(existing.map((entry) => entry.term || entry.name));
  const searchable = [item.id, item.title, item.summary, JSON.stringify(details)].filter(Boolean).join(" ").toLowerCase();

  globalTermCatalog.forEach((entry) => {
    const matched = entry.aliases.some((alias) => searchable.includes(String(alias).toLowerCase()));
    if (matched && !seen.has(entry.term)) {
      seen.add(entry.term);
      terms.push(term(entry.term, entry.definition));
    }
  });
  return terms;
}

function withLearningDetails(details, item, requirement, requirementReason) {
  const normalizedRequirement = normalizeRequirement(requirement);
  const reason = requirementReason || details.requirement_reason || requirementDescriptions[normalizedRequirement];
  const learningDetails = {
    ...details,
    requirement: requirementLabels[normalizedRequirement],
    requirement_reason: reason,
    term_definitions: enrichTermDefinitions(details, item),
  };
  if (Array.isArray(details.issue_solutions) && details.issue_solutions.length > 0) {
    learningDetails.issue_solutions = details.issue_solutions;
  }
  return learningDetails;
}

function microStep(title, summary, details = {}) {
  return { title, summary, details };
}

function node(id, title, summary, extra = {}) {
  const defaults = nodeDefaults(id, title);
  const requirement = normalizeRequirement(extra.requirement || defaults.requirement || "required");
  const enhancementIds = extra.enhancements || defaults.enhancements || [];
  const enhancements = resolveProductionEnhancements(enhancementIds);
  const details = withProductionEnhancements({
    ...(defaults.details || {}),
    ...(extra.details || {}),
  }, enhancements);
  const requirementReason = extra.requirementReason || details.requirement_reason || requirementDescriptions[requirement];
  return {
    id,
    title,
    summary,
    mode: "sequential",
    status: "ok",
    ...defaults,
    ...extra,
    enhancements,
    requirement,
    requirementReason,
    details: withLearningDetails(details, { id, title, summary }, requirement, requirementReason),
    innerSteps: extra.innerSteps || defaults.innerSteps || [],
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

const ragInnerStepCatalog = {
  request_intake: [
    microStep("读取原始问题", "保留用户原文、top_k 和入口来源，后续 trace 必须能回放原始输入。", { knowledge_points: [knowledge("为什么不能只记录归一化后的 query？", "原始 query 是审计和复盘的基准；只记录归一化结果会丢掉用户真实表达，后面无法判断清洗或改写是否引入语义变化。"), knowledge("trace_id 应该在哪里生成？", "应在请求入口生成，并贯穿检索、rerank、LLM 和前端展示；这样日志、Langfuse span 和用户会话才能稳定关联。")] }),
    microStep("生成 trace_id", "为本次请求生成稳定追踪 ID，用于日志、Langfuse 和前后端关联。", { term_definitions: [term("trace_id", "一次请求的唯一追踪编号，用于把检索、模型、工具调用串起来。")] }),
    microStep("初始化执行上下文", "把用户、会话、top_k、时间、权限上下文放进 pipeline context。", { pitfalls: ["上下文缺用户身份，后面就无法做权限过滤。"] }),
  ],
  input_guardrails: [
    microStep("空输入检查", "拒绝空字符串、纯空白和没有业务语义的输入。", { quality_checks: [{ name: "non_empty", status: "ok", reason: "空输入进入 embedding 会污染观测和缓存。" }] }),
    microStep("长度边界检查", "限制 query 长度，避免 tokenizer、embedding 或模型调用成本失控。", { term_definitions: [term("Token budget", "模型一次输入可处理的 token 上限。")] }),
    microStep("注入风险识别", "识别忽略规则、泄露系统提示、伪造工具输出等 prompt injection 信号。", { pitfalls: ["RAG 里的攻击不只发生在用户问题，也会发生在检索回来的文档中。"] }),
  ],
  normalize_text: [
    microStep("去首尾空白", "使用确定性规则移除首尾空格、换行和制表符。", { tool: "str.strip()" }),
    microStep("压缩连续空白", "把连续空白统一成单个空格，让缓存键、token 和 trace 更稳定。", { tool: "split() + join()" }),
    microStep("语义保持检查", "确认清洗只改变格式，不替换词义、不扩大问题范围。", { knowledge_points: [knowledge("normalize 和 rewrite 的边界是什么？", "normalize 只做格式层面的确定性清洗；rewrite 会改变检索表达，所以必须做语义漂移检查。")] }),
  ],
  query_understanding: [
    microStep("识别意图", "判断用户是在问规则、流程、定义、适用范围还是最新版本。", { term_definitions: [term("Intent", "用户真正想完成的动作或问题类型。 ")] }),
    microStep("抽取业务实体", "识别员工、年假、报销、考勤、安全等制度实体。", { pitfalls: ["只抽关键词不理解对象范围，会导致权限和分类过滤错误。"] }),
    microStep("标记歧义", "发现缺少年份、对象、校区、部门等信息时，为后续反问或保守回答做准备。", { quality_checks: [{ name: "ambiguity", status: "ok", reason: "歧义不是错误，但需要显式进入决策。" }] }),
  ],
  query_rewrite: [
    microStep("生成独立问题", "把依赖上下文的短问句改写成可单独检索的问题。", { term_definitions: [term("Standalone query", "不依赖聊天上文也能表达完整意图的问题。 ")] }),
    microStep("补充同义词", "补年假/年休假、制度/规则等业务同义词，提高召回率。", { pitfalls: ["同义词扩展不能加入用户没有问到的新对象。"] }),
    microStep("语义漂移检查", "比较改写前后对象、动作、时间和范围是否一致。", { knowledge_points: [knowledge("query rewrite 为什么可能造成错误答案？", "改写可能扩大对象、改变时间或引入同义词误判，导致检索到看似相关但业务范围错误的证据。")] }),
  ],
  tokenize: [
    microStep("调用 tokenizer", "用 embedding 模型对应 tokenizer 展示真实 token 边界。", { term_definitions: [term("Tokenizer", "把文本切成模型词表 token 的工具。 ")] }),
    microStep("展示 token id", "展示每个 token 在词表里的数字编号，说明模型不是按中文词语直接理解。", { term_definitions: [term("Token id", "token 在模型词表中的整数编号。 ")] }),
    microStep("检查截断风险", "确认 query 没有超过 embedding 服务的最大输入长度。", { quality_checks: [{ name: "truncation", status: "ok", reason: "被截断的 query 会让检索语义不完整。" }] }),
  ],
  query_embedding: [
    microStep("选择 embedding 模型", "根据语言、部署边界、成本和检索质量选择模型。", embeddingDetails),
    microStep("生成 query vector", "把用户检索问题转换成向量，用于相似度计算。", { term_definitions: [term("Query embedding", "查询文本对应的向量表示。 ")] }),
    microStep("校验维度和版本", "确认 query vector 和文档向量使用同一模型、同一维度、同一归一化策略。", { quality_checks: embeddingDetails.quality_checks }),
  ],
  retrieval_plan: [
    microStep("确定 top_k", "设置召回候选数量，平衡召回率、rerank 成本和上下文长度。", { knowledge_points: [knowledge("top_k 过大或过小分别有什么问题？", "过小会漏召回，过大会增加 rerank 和上下文成本，还可能把噪声证据带入答案。")] }),
    microStep("识别精确制度查询", "把二类违规、4.1、弄虚作假行为识别为 exact policy lookup。", { term_definitions: [term("Exact match", "对制度标题、条款号、章节名做确定性匹配，适合精确制度查询。 ")] }),
    microStep("生成过滤条件", "根据分类、权限、时间、目标章节和排除章节生成 metadata filter。", { pitfalls: ["没有权限过滤和章节约束的企业 RAG 不能上线。"] }),
    microStep("选择 Hybrid Search", "决定 dense vector、sparse keyword、exact match 是否并行召回。", { term_definitions: [term("Hybrid Search", "结合向量语义召回、关键词召回和精确匹配的检索方式。 ")] }),
  ],
  initial_retrieval: [
    microStep("执行 Hybrid Search", "精确制度查询同时走 exact match、sparse keyword 和 pgvector dense 召回。", { term_definitions: [term("Sparse keyword", "保留关键词和条款号信号，适合二类违规、4.1 这类精确词。 ")] }),
    microStep("执行向量检索", "用 pgvector/HNSW/余弦距离找语义相近 chunk。", { term_definitions: [term("HNSW", "常见近似最近邻向量索引结构。 ")] }),
    microStep("读取 chunk 元数据", "带回标题层级、source、category、publish_date、section_path、clause_title 等字段。", { quality_checks: [{ name: "source_metadata", status: "ok", reason: "没有来源字段和章节字段就无法引用和审计。" }] }),
    microStep("候选去重", "按 doc_id、section_path、clause_title 或 chunk_id 去掉重复候选。", { pitfalls: ["重复 chunk 会挤掉真正有用的证据。"] }),
  ],
  rerank: [
    microStep("构造 query-document pair", "把用户问题和候选 chunk 组成重排输入。", { term_definitions: [term("Cross-encoder", "同时读取 query 和文档并输出相关性分数的模型。 ")] }),
    microStep("计算 rerank score", "结合语义、关键词、标题、来源和业务规则重新打分。", { pitfalls: ["只看向量距离可能把语义相近但制度不相关的文本排第一。"] }),
    microStep("排序稳定性检查", "保留 before/after 排名，方便解释为什么候选顺序改变。", { knowledge_points: [knowledge("召回和 rerank 的职责边界是什么？", "召回负责尽量找全候选，rerank 负责在候选中重新排序和压噪；两者目标不同，不能互相替代。")] }),
  ],
  evidence_quality: [
    microStep("相关度阈值", "低于阈值时不强答，改为提示证据不足或反问。", { quality_checks: [{ name: "relevance_threshold", status: "ok", reason: "证据不足时强答会制造幻觉。" }] }),
    microStep("章节边界截取", "从粗 chunk 中按 start_marker/end_marker 抽取目标章节，避免带出相邻条款。", { term_definitions: [term("Span extraction", "从较长文本中截取真正回答当前问题的片段。 ")] }),
    microStep("Scope Guard", "检查答案和 context 是否泄露了一类/三类违规等竞争章节。", { quality_checks: [{ name: "scope_guard", status: "ok", reason: "精确查询只能回答用户询问的章节。" }] }),
    microStep("参见型片段过滤", "如果候选只是在别的制度里写“具体参见某制度”，不能把它当作最终答案证据。", { term_definitions: [term("Direct evidence", "直接包含目标章节、定义或条款正文的证据；只提到参见其它制度的文本只能作为线索。 ")] }),
    microStep("Citation Merge", "按 doc_id、section_path、clause_title 合并重复来源。", { term_definitions: [term("Citation Merge", "把同一制度同一章节的多个 chunk 合并为一个可审计来源。 ")] }),
    microStep("时效性检查", "检查 publish_date、effective_date 和是否存在新旧制度冲突。", { pitfalls: ["制度问答经常错在旧政策覆盖新政策。"] }),
    microStep("引用完整性检查", "确认答案能引用具体制度、章节、来源和必要元数据。", { knowledge_points: [knowledge("RAG 如何降低 hallucination？", "通过只基于可引用证据回答、设置相关度阈值、拒答证据不足问题，并把来源返回给用户审计。")] }),
  ],
  answer_and_observe: [
    microStep("组织证据上下文", "把高质量证据按引用和 token budget 拼成回答上下文。", { term_definitions: [term("Context window", "模型一次生成时可读取的上下文长度。 ")] }),
    microStep("生成可追溯回答", "答案必须说明依据、边界和不确定性，不能脱离证据发挥。", { pitfalls: ["最终回答不能把检索不到的信息说成确定事实。"] }),
    microStep("写入观测数据", "记录 trace、耗时、检索结果、rerank 分数和质量检查，方便 Langfuse 回放。", { term_definitions: [term("Span", "trace 中一个具体步骤的观测记录。 ")] }),
  ],
};

const prefixInnerStepCatalog = {
  embed: [
    microStep("输入质量检查", "检查文本为空、过长、语言混杂和不可解析字符。"),
    microStep("模型与维度确认", "确认 query/document embedding 使用同一模型版本和维度。", embeddingDetails),
    microStep("索引与召回验证", "用样例 query 检查向量库是否能召回目标 chunk。", { knowledge_points: [knowledge("如何判断 embedding 模型适不适合你的业务？", "用真实问题集做离线评测，比较 recall@k、MRR、跨语言表现、成本和部署约束，而不是只看通用榜单。")] }),
  ],
  doc: [
    microStep("语义边界识别", "按标题、段落、条款和表格边界切分文档。"),
    microStep("chunk 元数据绑定", "为 chunk 绑定来源、分类、权限和生效时间。"),
    microStep("向量写入校验", "确认 chunk_id、embedding、metadata 能幂等 upsert。"),
  ],
  query: [
    microStep("问题标准化", "把用户表达整理成可检索 query。"),
    microStep("检索信号生成", "生成向量、关键词、过滤条件等多路信号。"),
    microStep("漂移和截断检查", "确认处理后没有改变原意，也没有超过 token budget。"),
  ],
  lc: [
    microStep("组件装配", "把 prompt、model、tools、retriever 和 memory 组合成 chain/agent。"),
    microStep("调用边界控制", "限制工具调用次数、输入输出 schema 和异常分支。"),
    microStep("结果解释", "把 tool observation 和模型输出串成可审计轨迹。", { knowledge_points: [knowledge("LangChain 的优点和局限是什么？", "优点是组件丰富、上手快；局限是复杂链路容易隐藏状态和异常边界，生产系统要补 tracing、schema 和可控降级。")] }),
  ],
  lg: [
    microStep("State 读写", "每个节点只读写明确的 state 字段，避免隐式共享状态。"),
    microStep("条件边和并行边", "用 graph edge 表达分支、循环、并行和汇聚。"),
    microStep("Checkpoint 与恢复", "失败后从保存的 state 继续执行，而不是整条链重跑。", { knowledge_points: [knowledge("LangGraph 相比普通 chain 解决了什么问题？", "它把流程建模成有状态图，适合分支、循环、并行、人工介入和 checkpoint 恢复，比线性 chain 更可控。")] }),
  ],
  qr: [
    microStep("候选改写生成", "生成多个查询候选，不直接相信第一个改写结果。"),
    microStep("语义漂移检测", "检查改写是否改变对象、动作、时间和范围。"),
    microStep("重排与证据校验", "用 rerank 和质量阈值控制最终进入答案的证据。"),
  ],
  ma: [
    microStep("任务拆解", "协调器把问题拆成检索、推理、审查等角色任务。"),
    microStep("并行执行", "互不依赖的 Agent 并行工作，减少等待时间。"),
    microStep("冲突解决", "合并多个 Agent 的结果，显式处理矛盾和缺证据。", { knowledge_points: [knowledge("多 Agent 什么时候有必要，什么时候是过度设计？", "当任务可拆分且角色之间能独立产出时才有价值；简单问答强行多 Agent 只会增加延迟、成本和调试难度。")] }),
  ],
  ingest: [
    microStep("数据抽取", "从业务系统拉取列表、详情、附件和权限字段。"),
    microStep("清洗切块", "清理正文并按语义和 token budget 切 chunk。"),
    microStep("幂等入库", "用 doc_id/chunk_id 做断点续跑、更新和删除同步。"),
  ],
  lf: [
    microStep("Trace 建模", "把一次请求拆成 trace 和多个 span。"),
    microStep("评分与反馈", "记录人工反馈、自动评分和错误标签。"),
    microStep("回放分析", "按 trace 回放，定位改写、召回、rerank 或生成问题。", { knowledge_points: [knowledge("为什么 RAG 系统需要 observability？", "RAG 错误可能发生在改写、召回、rerank、证据拼接或生成任一环节；没有 trace 就无法定位根因。")] }),
  ],
};

const ragNodeDetailCatalog = {
  request_intake: {
    knowledge_points: [
      knowledge("RAG 的问题应该优先看召回还是生成？", "先用入口 trace 切边界：原始问题、用户身份、top_k、trace_id 是否正确进入链路；如果入口状态错了，后面的召回和生成排查都没有意义。"),
      knowledge("为什么请求入口要带 tenant/user/session，而不是只传 message？", "企业知识库首先是权限系统；tenant、user、session 决定能检索哪些文档、是否可追溯、能否复现多轮上下文。"),
      knowledge("trace_id 放在前端、网关还是后端生成？", "入口层必须生成或接收一个全链路 trace_id，并透传给检索、rerank、LLM、日志和前端结果，这样线上问题才能按一次请求完整回放。"),
    ],
    issue_solutions: [
      issueSolution("入口没有固化 top_k、用户身份和 trace_id", "把 request schema 固定为 message/top_k/user_context/session_id/trace_id；缺失身份时只允许走公开样例或直接拒绝进入企业知识库。", "同一个问题在不同用户下返回不同制度，事故发生后无法判断是权限、召回还是模型造成。"),
      issueSolution("把多轮上下文直接拼进 message", "入口只接收当前用户问题和会话标识；历史上下文由独立的 memory/context assembler 控制 token budget 和引用来源。", "上下文膨胀会拖慢检索和生成，还可能把上一轮无关实体带入本轮检索。"),
    ],
  },
  input_guardrails: {
    knowledge_points: [
      knowledge("Prompt injection 为什么不能只靠入口拦截？", "入口能拦用户输入里的显式攻击，但 RAG 还会从文档里取回恶意内容；所以检索后和生成前也要做 evidence guardrail。"),
      knowledge("什么时候应该拒答，而不是继续检索？", "权限不足、空输入、明显越权、要求泄露系统提示或内部密钥时应拒答；业务问题不完整但低风险时可以进入理解阶段并标记歧义。"),
    ],
    issue_solutions: [
      issueSolution("护栏只检查用户 query，不检查检索文档", "把 guardrail 分成入口检查和 evidence 检查；检索回来的 chunk 如果要求模型忽略规则或泄露信息，应从上下文中剔除。", "攻击文本可以藏在制度附件、网页正文或历史工单里，入口看不到这些内容。"),
      issueSolution("超长输入直接送 embedding 或 LLM", "入口记录原文长度和 token 估算，超过阈值时先摘要、截断或要求用户拆分问题。", "成本失控、请求超时，甚至因为尾部被截断导致检索语义完全变形。"),
    ],
  },
  normalize_text: {
    knowledge_points: [
      knowledge("normalize 和 query rewrite 的边界是什么？", "normalize 只能做确定性格式清洗，例如 trim、压缩空白、统一全半角；rewrite 会改变检索表达，必须单独记录和做语义漂移检查。"),
      knowledge("为什么要同时保留 raw query 和 normalized query？", "raw query 用于审计用户原意，normalized query 用于稳定缓存和后续处理；只保留后者会看不出清洗是否引入错误。"),
    ],
    issue_solutions: [
      issueSolution("清洗规则误删条款编号或中文标点", "对 `4.1`、`（二）`、书名号、冒号这类制度结构符号做保护测试；这些符号通常是精确检索的关键。", "问 `4.1` 或 `二类违规` 时，结构符号丢失会让 Hybrid Search 和章节截取失效。"),
      issueSolution("缓存键使用 raw query 导致同义空白重复请求", "缓存键使用 normalized query，同时 trace 中保留 raw query；这样既稳定缓存，又不丢审计信息。", "同一个问题只因空格或换行不同就重复 embedding，浪费成本。"),
    ],
  },
  query_understanding: {
    knowledge_points: [
      knowledge("怎么判断用户是在做精确条款查询，而不是普通语义查询？", "看是否包含制度名、条款号、章节名、定义问法，例如 `二类违规`、`4.1`、`弄虚作假行为是什么`；这类问题要走 exact/hybrid/scoped evidence。"),
      knowledge("用户问题缺少年级、员工身份或时间，应该反问还是先检索？", "低风险知识问答可以先检索并说明适用边界；涉及权限、审批、处罚、金额或个人数据时应先澄清关键条件。"),
    ],
    issue_solutions: [
      issueSolution("把 `二类违规是什么` 当普通语义查询", "Query understanding 输出 `exact_policy_lookup`、target_section、exclude_sections；后续 retrieval/rerank/scope 都读取这些结构化字段。", "embedding 会把一类、二类、三类违规都看成相关，最终答案混入相邻章节。"),
      issueSolution("只抽关键词，不抽业务对象和适用范围", "实体抽取至少包含对象、制度类型、时间、阶段、权限和条款目标；不确定字段进入 ambiguity_flags。", "员工制度、学生制度、幼儿园制度可能同时命中，答案看似相关但适用对象错。"),
    ],
  },
  query_rewrite: {
    knowledge_points: [
      knowledge("Query rewrite 为什么可能让 RAG 变差？", "改写可能加入用户没问的对象、时间或同义词，召回更丰富但语义漂移；所以要记录 added_terms，并检查对象、动作、范围是否一致。"),
      knowledge("Multi-query 或 RAG-Fusion 什么时候值得做？", "当用户表达口语化、召回容易漏时可以多路改写；但每条改写都要去重、限流和评估，否则成本和噪声都会上升。"),
    ],
    issue_solutions: [
      issueSolution("改写把精确条款问题扩成泛问", "精确查询只补充同一章节/条款的别名，不补充跨制度同义词；改写结果要带 semantic_drift_check。", "问 `虚假报销` 时如果扩成 `报销制度`，会召回财务流程而不是纪律条款。"),
      issueSolution("多路改写没有去重和召回预算", "为每条改写设置 channel、weight 和 candidate limit，合并候选后再 rerank。", "RAG-Fusion 可能把相似候选刷屏，挤掉真正有用的证据。"),
    ],
  },
  tokenize: {
    knowledge_points: [
      knowledge("为什么知识点会追问 tokenizer，而不是只问 embedding？", "tokenizer 决定截断、成本和模型实际看到的边界；中文、编号、表格符号被怎么切，会影响条款检索和上下文拼接。"),
      knowledge("用字符数控制 chunk 长度有什么问题？", "字符数不等于 token 数；中英混排、表格、URL、编号的 token 密度不同，必须按 tokenizer 结果估算预算。"),
    ],
    issue_solutions: [
      issueSolution("chunk 或 query 被静默截断", "记录 token_count、max_tokens 和 truncation 状态；超过阈值时拆分或拒绝，不允许静默截断。", "被截断后模型和向量库看到的问题不完整，排查时却以为用的是用户原问题。"),
      issueSolution("制度编号被 tokenizer 切散后只做语义检索", "编号、条款号和标题同时进入 sparse/exact 通道，不能只依赖 dense embedding。", "`4.3`、`二类违规` 这类精确信号在纯向量里容易被稀释。"),
    ],
  },
  query_embedding: {
    knowledge_points: [
      knowledge("Embedding 模型怎么选，不能只说看排行榜？", "用业务评测集比较 recall@k、MRR、中文/英文/编号表现、部署合规、延迟和成本；排行榜只能作为候选筛选。"),
      knowledge("为什么 query embedding 和 document embedding 必须同模型同版本？", "向量空间由模型定义；不同模型或不同版本的向量不可直接比较，混用会让距离失去语义意义。"),
    ],
    issue_solutions: [
      issueSolution("换 embedding 模型后没有重建索引", "embedding_version 写入 metadata；查询模型版本和库内版本不一致时拒绝检索或触发重建。", "线上看起来还能返回结果，但相似度排序已经不可解释。"),
      issueSolution("只用 dense embedding 检索制度编号和专有名词", "制度编号、标题、条款名进入 Hybrid Search；dense 负责语义，sparse/exact 负责字面精度。", "问 `二类违规`、`4.1`、`BGE-M3` 这类词时，纯向量可能召回相邻概念。"),
    ],
  },
  retrieval_plan: {
    knowledge_points: [
      knowledge("top_k、candidate_k、final_k 有什么区别？", "candidate_k 是给召回和 rerank 的候选池，final_k 是最终给用户和生成器的证据数；candidate_k 通常要大于 final_k。"),
      knowledge("Hybrid Search 是必做还是可选？", "普通语义问答可以先 dense；制度条款、编号、人名、日期、报销金额这类精确信号强的业务，应启用 hybrid。"),
    ],
    issue_solutions: [
      issueSolution("candidate_k 太小导致 rerank 没有发挥空间", "召回阶段多取候选，例如 final_k=3 时 candidate_k 可设 10-30，再由 rerank 和 evidence filter 压噪。", "目标 chunk 一开始没进入候选池，后面再强的 rerank 也救不回来。"),
      issueSolution("检索计划没有权限和分类约束", "metadata_filters 必须包含用户可见范围、制度分类、目标章节和排除章节；缺字段时降级或拒答。", "企业 RAG 最常见事故不是答不上来，而是答了用户不该看的内容。"),
    ],
  },
  initial_retrieval: {
    knowledge_points: [
      knowledge("向量召回没命中目标 chunk，应该怎么排查？", "按顺序查：数据是否入库、chunk 是否过粗、embedding 版本是否一致、query 是否漂移、keyword 是否被弱化、candidate_k 是否过小。"),
      knowledge("dense、BM25、metadata filter 的职责怎么分？", "dense 找语义相近，BM25/keyword 保留字面精度，metadata filter 控制权限和业务范围；三者不是互相替代。"),
    ],
    issue_solutions: [
      issueSolution("章节词权重压过条款词", "Hybrid Search 把 target_clause/target_terms 作为 primary terms，权重大于 target_section；二类违规不能压过弄虚作假。", "问具体条款时召回了一堆只含章节名的泛片段，答案偏题。"),
      issueSolution("同一文档相邻 chunk 大量重复进入候选", "初召回先保留足够候选，证据阶段再按 doc_id + section_path + clause_title 合并。", "重复候选会挤掉其它来源，也会让用户看到 `[1][2][3]` 都是同一篇制度。"),
    ],
  },
  rerank: {
    knowledge_points: [
      knowledge("Rerank 是必做还是可选？", "它是可选增强；如果候选噪声大、相似概念多、答案要求高精度就推荐做，低延迟粗问答可以先跳过。"),
      knowledge("Rerank 不能解决什么问题？", "不能解决目标文档没召回、权限过滤缺失、chunk 本身混段、metadata 错误；它只能在候选集内部重新排序。"),
    ],
    issue_solutions: [
      issueSolution("参见型片段因为关键词命中排到第一", "rerank 加 direct evidence 约束：只写 `具体参见某制度` 的片段降权，直接包含定义或条款正文的片段加权。", "用户问定义时，系统引用了另一个制度里的跳转说明，而不是原始条款。"),
      issueSolution("rerank 只看文本相似度，不看业务目标", "把 target_section、target_clause、exclude_sections、source_type 都纳入打分原因，并在 trace 中展示 before/after。", "模型认为一类、二类、三类违规都相似，但业务上只能回答用户问的那一类。"),
    ],
  },
  evidence_quality: {
    knowledge_points: [
      knowledge("参见型片段为什么不能直接作为答案证据？", "它只告诉你真正制度在哪里，不包含定义和条款正文；最终答案必须基于 direct evidence，否则就是把线索当结论。"),
      knowledge("为什么 chunk 命中了还要做 span extraction？", "粗 chunk 可能同时包含上一节、目标节和下一节；生成前必须按章节边界截取目标 span，避免把相邻条款带进答案。"),
      knowledge("引用重复是不是小问题？", "不是。重复引用会让用户误以为有多个来源支持同一结论，也会挤掉真正不同的证据来源。"),
    ],
    issue_solutions: [
      issueSolution("粗 chunk 同时包含二类和三类违规", "用 start_marker/end_marker 截取目标章节；如果找不到边界，scope_guard 标 warn，并避免直接长段输出。", "答案把用户没问的三类违规一起说出来，属于证据范围越界。"),
      issueSolution("没有 direct evidence 还强行回答", "证据过滤后 output_count=0 时返回证据不足，不使用导师制、薪酬制度等不相关候选兜底。", "RAG 最危险的不是无结果，而是用看似相关的错误证据生成确定答案。"),
    ],
  },
  answer_and_observe: {
    knowledge_points: [
      knowledge("Grounded answer 和普通 LLM 回答有什么区别？", "Grounded answer 每个关键结论都来自检索证据，并带 citation；普通回答可能基于模型参数记忆，无法审计来源。"),
      knowledge("RAG 质量怎么评估，不只看用户觉得对不对？", "离线看 recall@k、MRR、context precision、faithfulness；线上看拒答率、引用点击、人工反馈和失败样本回放。"),
    ],
    issue_solutions: [
      issueSolution("把 top chunk 原样整段输出", "回答阶段要先抽取目标 span，再组织结论、边界和来源；长 chunk 只作为证据，不等于最终答案。", "用户要的是答案，不是把制度全文粘出来；长段输出也更容易夹带无关条款。"),
      issueSolution("没有把失败样本沉淀成评测集", "把无召回、错召回、引用越界、用户点踩样本写入 dataset，后续每次改 chunk/rerank/embedding 都跑回归。", "系统会反复修同一类问题，但没有证据证明新版本真的更好。"),
    ],
  },
};


function nodeDefaults(id, title) {
  const prefix = String(id).split("_")[0];
  const innerSteps = ragInnerStepCatalog[id] || prefixInnerStepCatalog[prefix] || [
    microStep("输入", `读取 ${title} 需要的上游状态。`),
    microStep("处理", `执行 ${title} 的核心逻辑。`),
    microStep("校验", `检查 ${title} 的输出是否能安全交给下游。`),
  ];
  return {
    innerSteps,
    enhancements: enhancementNodeMap[id] || [],
    details: {
      ...(ragNodeDetailCatalog[id] || {}),
      inner_step_count: innerSteps.length,
    },
  };
}


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

function liveChildToInnerStep(parent, child, index) {
  return {
    id: `${parent.id}.live.${child.key || index}`,
    title: child.title || child.key || `细节点 ${index + 1}`,
    summary: child.summary || "后端返回的真实执行子步骤。",
    mode: child.execution_mode || parent.mode || "sequential",
    status: child.status || "ok",
    duration_ms: child.duration_ms,
    details: {
      ...(child.details || {}),
      backend_step_key: child.key,
      backend_status: child.status || "ok",
    },
  };
}

function normalizeInnerStep(parent, innerStep, index) {
  if (typeof innerStep === "string") {
    return {
      id: `${parent.id}.inner.${index}`,
      title: innerStep,
      summary: "静态学习细节点。",
      mode: parent.mode || "sequential",
      status: "ok",
      details: {},
    };
  }
  return {
    id: innerStep.id || `${parent.id}.inner.${index}`,
    title: innerStep.title || `细节点 ${index + 1}`,
    summary: innerStep.summary || "静态学习细节点。",
    mode: innerStep.mode || parent.mode || "sequential",
    status: innerStep.status || "ok",
    details: {
      ...(innerStep.details || {}),
      parent_phase: parent.title,
    },
  };
}

function mergeTraceNode(staticNode, liveSteps) {
  const live = staticNode.traceKey ? liveSteps.get(staticNode.traceKey) : null;
  const staticInnerSteps = (staticNode.innerSteps || []).map((item, index) => normalizeInnerStep(staticNode, item, index));
  if (!live) {
    return {
      ...staticNode,
      innerSteps: staticInnerSteps,
      details: withLearningDetails(
        {
          ...(staticNode.details || {}),
          inner_steps: staticInnerSteps.map((item) => item.title),
        },
        staticNode,
        staticNode.requirement,
        staticNode.requirementReason,
      ),
    };
  }

  const liveInnerSteps = (live.children || []).map((child, index) => liveChildToInnerStep(staticNode, child, index));
  const liveTitles = new Set(liveInnerSteps.map((child) => child.title));
  const staticRemainder = staticInnerSteps.filter((child) => !liveTitles.has(child.title));
  const innerSteps = liveInnerSteps.length > 0 ? [...liveInnerSteps, ...staticRemainder] : staticInnerSteps;

  return {
    ...staticNode,
    title: staticNode.title || live.title,
    summary: live.summary || staticNode.summary,
    status: live.status || staticNode.status || "ok",
    mode: live.execution_mode || staticNode.mode || "sequential",
    duration_ms: live.duration_ms,
    innerSteps,
    details: withLearningDetails(
      {
        ...(staticNode.details || {}),
        ...(live.details || {}),
        backend_step_key: live.key,
        backend_status: live.status || "ok",
        inner_steps: innerSteps.map((child) => child.title),
      },
      staticNode,
      staticNode.requirement,
      staticNode.requirementReason,
    ),
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
    { type: "serial", nodes: [node("request_intake", "请求接入", "接收用户问题、top_k 和本次 trace 上下文。", { traceKey: "request_intake", sequence: "01", requirement: "required", requirementReason: "入口层是所有后续 trace、权限和参数校验的来源，属于必经步骤。", details: { business_goal: "确认这次问题要进入哪条 RAG/Agent 链路，而不是直接丢给模型。" } })] },
    { type: "serial", nodes: [node("input_guardrails", "输入护栏", "检查空输入、超长输入、注入风险和参数边界。", { traceKey: "input_guardrails", sequence: "02", requirement: "required", requirementReason: "企业系统必须先判断请求是否可处理、是否安全，否则后续模型和工具调用都会放大风险。", details: { why: "真实业务里模型调用前必须先判断请求是否安全、是否可处理。" } })] },
    { type: "serial", nodes: [node("normalize_text", "文本归一化", "只处理格式：去首尾空白、压缩连续空白，不偷偷改写语义。", { traceKey: "normalize_text", sequence: "03", requirement: "required", requirementReason: "归一化保证缓存、日志和 tokenizer 输入稳定，但它只能改格式，不能改语义。", details: { why: "清洗和改写要分离，否则 trace 中看不出原始问题被改成了什么。" } })] },
    { type: "serial", nodes: [node("query_understanding", "Query 理解", "识别意图、制度类别、对象范围、时间提示和歧义。", { traceKey: "query_understanding", sequence: "04", requirement: "required", requirementReason: "真实业务要知道问题问谁、问什么范围、是否缺条件；否则权限过滤和证据选择都会错。", details: { why: "后续检索过滤、改写、是否反问都依赖这里的判断。" } })] },
    {
      type: "parallel_group",
      id: "rag_parallel_prepare",
      title: "并行准备：查询表示 + 检索约束",
      summary: "query 理解后，可以同时准备语义向量路径和检索过滤路径。",
      branches: [
        {
          title: "语义表示路径",
          nodes: [
            node("query_rewrite", "Query 改写", "补齐独立问题和同义词，提升召回但不能扩大问题范围。", { traceKey: "query_rewrite", sequence: "05A", mode: "parallel", requirement: "optional", requirementReason: "短 query、多轮省略或同义词较多时建议做；如果用户问题已经完整、业务风险高，也可以跳过或只做保守改写。", details: { why: "用户问题常常很短，适度改写可以把口语问题变成可检索表达。" } }),
            node("tokenize", "分词与 token", "展示模型实际处理的 token 和 token id，确认输入没有被截断。", { traceKey: "tokenize", sequence: "05B", mode: "parallel", requirement: "conditional", requirementReason: "生产链路通常做长度检查；完整展示 token/token id 更偏教学、调试和截断排查，按场景触发。", details: { why: "教学和调试时要看到模型到底吃进去了什么。" } }),
            node("query_embedding", "Query Embedding", "把检索问题转成向量，进入语义相似度空间。", { traceKey: "query_embedding", sequence: "05C", mode: "parallel", requirement: "conditional", requirementReason: "如果使用向量或混合检索，这是必经；如果某些场景只走 BM25/精确过滤，可以不生成 query embedding。", details: embeddingDetails }),
          ],
        },
        {
          title: "业务约束路径",
          nodes: [
            node("retrieval_plan", "检索计划", "准备 top_k、向量库、分类、权限、时间和 SQL 形状。", { traceKey: "retrieval_plan", sequence: "05D", mode: "parallel", requirement: "required", requirementReason: "企业 RAG 必须先确定权限、分类、top_k 和检索方式，否则召回结果不可控。", details: { why: "真实企业 RAG 不能只看语义相似，还要受权限、分类、时效和来源约束。", options: ["按用户身份加 permission_scope 过滤", "按制度分类加 metadata filter", "按发布时间或生效时间做 freshness check"] } }),
          ],
        },
      ],
    },
    { type: "merge", title: "查询表示与检索计划汇聚", nodes: [] },
    { type: "serial", nodes: [node("initial_retrieval", "初始召回", "用向量库或混合检索找到候选 chunk。", { traceKey: "initial_retrieval", sequence: "07", requirement: "required", requirementReason: "初始召回是 RAG 的必经步骤；没有候选证据，后面的 rerank、证据检查和回答都没有依据。" })] },
    { type: "serial", nodes: [node("rerank", "Rerank 重排序", "对候选证据重新打分，把更相关、更可引用的内容排到前面。", { traceKey: "rerank", sequence: "08", requirement: "optional", requirementReason: "Rerank 是可选增强：候选多、相似但不相关的结果多、答案质量要求高时建议做；低延迟、小知识库或高精度过滤场景可以先不用。", details: { why: "初始召回负责找全，rerank 负责把最可能回答问题的证据放到前面。" } })] },
    { type: "serial", nodes: [node("evidence_quality", "证据质量检查", "检查相关度、来源、时效、冲突和是否需要反问。", { traceKey: "evidence_quality", sequence: "09", requirement: "required", requirementReason: "企业制度问答不能只要检索结果，还必须判断证据是否足够、是否过期、是否冲突。" })] },
    { type: "serial", nodes: [node("answer_and_observe", "答案与观测", "基于证据组织回答，并记录 trace、耗时和质量信号。", { traceKey: "answer_and_observe", sequence: "10", mode: "observe", requirement: "required", requirementReason: "回答是业务交付结果，观测是定位质量问题的基础；生产系统至少要保留可审计 trace。", details: { why: "最终答案只是结果，trace 才能帮助调试为什么这么答。" } })] },
  ];
  return {
    id: "rag-core",
    title: "RAG 基础流程",
    summary: "展示真实 RAG 问答里顺序、并行和汇聚关系。",
    rows: hydrateRows(rows, traceStepMap(traceData)),
  };
}


function enhancementWorkflowNode(id, sequence, mode = "sequential") {
  const enhancement = productionEnhancementById.get(id);
  return node(id, enhancement?.title || id, enhancement?.summary || "生产 RAG 增强项。", {
    sequence,
    mode,
    requirement: enhancement?.requirement || "optional",
    requirementReason: enhancement ? `${enhancementStatusLabels[enhancement.status]}：${enhancement.boundaries}` : undefined,
    enhancements: [id],
    details: {
      stage: enhancement?.stage,
      implementation_status: enhancementStatusLabels[enhancement?.status] || "待接入",
      why: enhancement?.solves,
    },
  });
}

function buildProductionRagMaturityWorkflow() {
  const rows = [
    { type: "serial", nodes: [enhancementWorkflowNode("eval_runner", "01"), enhancementWorkflowNode("bad_case_feedback", "02")] },
    {
      type: "parallel_group",
      id: "production_quality_parallel",
      title: "本轮优化：检索质量并行增强",
      summary: "Query 路由、规则多跳、权限过滤、外部知识和 rerank 可以按场景并行准备，再在证据质量阶段汇聚。",
      branches: [
        { title: "理解与路由", nodes: [enhancementWorkflowNode("query_router", "03A", "parallel"), enhancementWorkflowNode("multi_hop_resolver", "03B", "parallel")] },
        { title: "召回与排序", nodes: [enhancementWorkflowNode("audience_permission_filter", "03C", "parallel"), enhancementWorkflowNode("cross_encoder_reranker", "03D", "parallel")] },
        { title: "证据扩展", nodes: [enhancementWorkflowNode("citation_span_highlight", "03E", "parallel"), enhancementWorkflowNode("external_knowledge_api", "03F", "parallel")] },
      ],
    },
    { type: "merge", title: "检索质量汇聚", nodes: [enhancementWorkflowNode("structured_answer_contract", "04", "merge")] },
    {
      type: "parallel_group",
      id: "production_ingest_ops_parallel",
      title: "本轮优化：数据与运维治理",
      summary: "数据导入、版本同步、解析、安全、观测和成本控制并不是一条线，它们围绕 RAG 主链路形成治理层。",
      branches: [
        { title: "数据治理", nodes: [enhancementWorkflowNode("ingest_quality_report", "05A", "parallel"), enhancementWorkflowNode("incremental_sync_versioning", "05B", "parallel"), enhancementWorkflowNode("document_parser_multimodal", "05C", "parallel")] },
        { title: "安全治理", nodes: [enhancementWorkflowNode("prompt_injection_guardrails", "05D", "parallel")] },
        { title: "观测与成本", nodes: [enhancementWorkflowNode("langfuse_otel_observability", "05E", "parallel"), enhancementWorkflowNode("cache_cost_control", "05F", "parallel")] },
      ],
    },
  ];
  return {
    id: "production-rag-maturity",
    title: "生产 RAG 成熟度",
    summary: "用 15 个生产增强项说明当前系统距离真实企业 RAG 还需要哪些质量、治理、安全和观测能力。",
    rows: hydrateRows(rows, new Map()),
  };
}

function extraWorkflowRows(id) {
  const rowsByWorkflow = {
    "embedding-retrieval": [
      { type: "serial", nodes: [node("embed_benchmark", "Embedding Benchmark", "用标准问题集比较模型、chunk 策略和召回指标。", { sequence: "06" })] },
      { type: "serial", nodes: [node("embed_monitor", "Embedding 监控", "监控向量维度、索引大小、召回质量和模型版本漂移。", { sequence: "07" })] },
    ],
    "langchain-agent": [
      { type: "serial", nodes: [node("lc_tool_call", "Tool Call", "把模型选择的工具调用转换成受控函数执行。", { sequence: "05" })] },
      { type: "serial", nodes: [node("lc_observation", "Observation", "把工具返回结果写回 Agent 可见上下文。", { sequence: "06" })] },
      { type: "serial", nodes: [node("lc_parser", "Output Parser", "把模型输出解析成结构化结果或可展示答案。", { sequence: "07" })] },
      { type: "serial", nodes: [node("lc_guardrails", "最终护栏", "检查答案是否越权、缺证据、格式错误或工具调用失败。", { sequence: "08" })] },
    ],
    "langgraph-workflow": [
      { type: "serial", nodes: [node("lg_condition", "Conditional Edge", "根据 state 判断下一步走检索、工具、人工介入还是结束。", { sequence: "05" })] },
      { type: "serial", nodes: [node("lg_human", "Human-in-the-loop", "高风险或证据不足时进入人工确认节点。", { sequence: "06" })] },
      { type: "serial", nodes: [node("lg_retry", "Retry / Recovery", "节点失败时按 state 和 checkpoint 恢复执行。", { sequence: "07" })] },
      { type: "serial", nodes: [node("lg_finish", "Graph Finish", "把最终 state 转成答案、事件和观测记录。", { sequence: "08" })] },
    ],
    "rewrite-rerank": [
      { type: "serial", nodes: [node("qr_retrieve", "多路召回", "用原 query、改写 query、关键词和 metadata filter 多路召回。", { sequence: "05" })] },
      { type: "serial", nodes: [node("qr_threshold", "阈值与反问", "相关性不够时拒绝强答，转为澄清问题。", { sequence: "06" })] },
      { type: "serial", nodes: [node("qr_answer", "证据驱动回答", "只基于通过 rerank 和质量检查的证据回答。", { sequence: "07" })] },
      { type: "serial", nodes: [node("qr_observe", "改写效果观测", "记录 rewrite 候选、召回差异和 rerank 前后排序。", { sequence: "08" })] },
    ],
    "multi-agent": [
      { type: "serial", nodes: [node("ma_contract", "任务契约", "定义每个 Agent 的输入、输出、禁止行为和验收标准。", { sequence: "04" })] },
      { type: "serial", nodes: [node("ma_review_gate", "审查闸口", "检查多个 Agent 的结果是否冲突、缺证据或越权。", { sequence: "05" })] },
      { type: "serial", nodes: [node("ma_memory", "共享记忆", "把可复用事实写入短期或长期记忆，避免重复工作。", { sequence: "06" })] },
      { type: "serial", nodes: [node("ma_eval", "协作评估", "评估并行协作是否真的提升质量，而不是增加复杂度。", { sequence: "07" })] },
    ],
    "enterprise-ingest": [
      { type: "serial", nodes: [node("ingest_validate", "导入校验", "校验 chunk 数、空文本、重复 ID、权限字段和来源字段。", { sequence: "05" })] },
      { type: "serial", nodes: [node("ingest_delete_sync", "删除同步", "源系统删除或下架文档时，同步删除向量和 chunk。", { sequence: "06" })] },
      { type: "serial", nodes: [node("ingest_monitor", "导入监控", "记录耗时、失败重试、断点续跑和告警。", { sequence: "07" })] },
    ],
    "langfuse-observe": [
      { type: "serial", nodes: [node("lf_dataset", "Dataset", "沉淀标准问题集，用于回归测试和模型/检索策略对比。", { sequence: "04" })] },
      { type: "serial", nodes: [node("lf_prompt_version", "Prompt 版本", "记录 prompt、模型和参数版本，方便回滚和对比。", { sequence: "05" })] },
      { type: "serial", nodes: [node("lf_eval", "自动评估", "用规则、LLM-as-judge 或人工标注评估答案质量。", { sequence: "06" })] },
      { type: "serial", nodes: [node("lf_alert", "异常告警", "低分、超时、成本异常或证据缺失时触发告警。", { sequence: "07" })] },
    ],
  };
  return rowsByWorkflow[id] || [];
}

function workflowFromRows(id, title, summary, rows) {
  return () => ({ id, title, summary, rows: hydrateRows([...rows, ...extraWorkflowRows(id)], new Map()) });
}

const workflowDefinitions = [
  { id: "rag-core", title: "RAG 基础流程", build: buildRagWorkflow },
  { id: "production-rag-maturity", title: "生产 RAG 成熟度", build: buildProductionRagMaturityWorkflow },
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
  const requirement = normalizeRequirement(item.requirement);
  meta.textContent = `${modeLabel(item.mode)} · ${requirementLabels[requirement]} · ${item.status || "ok"}${duration}`;

  const title = document.createElement("h3");
  title.textContent = shortTitle(item.title);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "drawer-close-button";
  close.textContent = "关闭";
  close.addEventListener("click", () => closeNodeDetailDrawer());

  const summary = document.createElement("p");
  summary.textContent = item.summary;

  header.append(meta, title, close, summary);
  panel.append(header, renderDetails(item.details));
  return panel;
}

function ensureNodeDetailDrawer() {
  if (detailDrawer && detailBackdrop) return { drawer: detailDrawer, backdrop: detailBackdrop };

  detailBackdrop = document.createElement("div");
  detailBackdrop.className = "node-detail-backdrop";
  detailBackdrop.addEventListener("click", () => closeNodeDetailDrawer());

  detailDrawer = document.createElement("aside");
  detailDrawer.className = "node-detail-drawer";
  detailDrawer.setAttribute("aria-label", "流程节点详情");

  document.body.append(detailBackdrop, detailDrawer);
  return { drawer: detailDrawer, backdrop: detailBackdrop };
}

function openNodeDetailDrawer(item, trigger) {
  const { drawer, backdrop } = ensureNodeDetailDrawer();
  drawer.innerHTML = "";
  drawer.appendChild(renderNodeDetail(item));
  drawer.classList.add("open");
  backdrop.classList.add("open");
  document.body.classList.add("detail-drawer-open");
  selectedDetailTrigger = trigger || null;
}

function closeNodeDetailDrawer() {
  if (!detailDrawer || !detailBackdrop) return;
  detailDrawer.classList.remove("open");
  detailBackdrop.classList.remove("open");
  document.body.classList.remove("detail-drawer-open");
  traceSteps.querySelectorAll(".trace-tree-node.selected, .inner-step-chip.selected").forEach((selected) => selected.classList.remove("selected"));
  if (selectedDetailTrigger) selectedDetailTrigger.focus?.();
  selectedDetailTrigger = null;
}

function selectWorkflowNode(item, nodeButton) {
  traceSteps.querySelectorAll(".trace-tree-node.selected, .inner-step-chip.selected").forEach((selected) => selected.classList.remove("selected"));
  nodeButton.classList.add("selected");
  openNodeDetailDrawer(item, nodeButton);
}

function renderWorkflowNode(item, rowIndex) {
  const enhancements = Array.isArray(item.enhancements) ? item.enhancements : (item.details?.production_enhancements || []);
  const hasCurrentEnhancement = enhancements.some((enhancement) => enhancement.current);
  const button = document.createElement("article");
  button.setAttribute("role", "button");
  button.tabIndex = 0;
  button.className = [
    "trace-tree-node",
    "workflow-node",
    `mode-${item.mode || "sequential"}`,
    `status-${item.status || "ok"}`,
    `requirement-${normalizeRequirement(item.requirement)}`,
    hasCurrentEnhancement ? "enhancement-current" : "",
  ].filter(Boolean).join(" ");

  const top = document.createElement("div");
  top.className = "tree-node-top";
  const index = document.createElement("span");
  index.className = "tree-step-index";
  index.textContent = item.sequence || String(rowIndex + 1).padStart(2, "0");
  const badge = document.createElement("span");
  badge.className = "tree-mode-badge";
  badge.textContent = modeLabel(item.mode || "sequential");
  const requirementBadge = document.createElement("span");
  requirementBadge.className = "tree-requirement-badge";
  requirementBadge.textContent = requirementLabels[normalizeRequirement(item.requirement)];
  top.append(index, badge, requirementBadge);

  const title = document.createElement("div");
  title.className = "tree-node-title";
  title.textContent = shortTitle(item.title);

  const summary = document.createElement("div");
  summary.className = "tree-node-summary";
  summary.textContent = item.summary;

  const requirementNote = document.createElement("div");
  requirementNote.className = "requirement-note";
  requirementNote.textContent = item.requirementReason || item.details?.requirement_reason || requirementDescriptions[normalizeRequirement(item.requirement)];

  button.append(top, title, summary, requirementNote);

  if (enhancements.length > 0) {
    const enhancementBadges = document.createElement("div");
    enhancementBadges.className = "enhancement-badge-row node-enhancement-badges";
    enhancements.slice(0, 3).forEach((enhancement) => {
      const badge = document.createElement("span");
      badge.className = `enhancement-status-badge status-${enhancement.status || "planned"}`;
      badge.textContent = `${enhancement.current ? "本轮优化 · " : ""}${enhancementStatusLabels[enhancement.status] || "待接入"}`;
      badge.title = enhancement.title || enhancement.id;
      enhancementBadges.appendChild(badge);
    });
    if (enhancements.length > 3) {
      const more = document.createElement("span");
      more.className = "enhancement-more-badge";
      more.textContent = `+${enhancements.length - 3}`;
      enhancementBadges.appendChild(more);
    }
    button.appendChild(enhancementBadges);
  }

  if (Array.isArray(item.innerSteps) && item.innerSteps.length > 0) {
    const innerList = document.createElement("div");
    innerList.className = "inner-step-list";
    item.innerSteps.forEach((innerStep, index) => {
      const normalized = normalizeInnerStep(item, innerStep, index);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "inner-step-chip";
      chip.textContent = `${index + 1}. ${normalized.title}`;
      chip.addEventListener("click", (event) => {
        event.stopPropagation();
        selectWorkflowNode(normalized, chip);
      });
      innerList.appendChild(chip);
    });
    button.appendChild(innerList);
  }

  button.addEventListener("click", () => selectWorkflowNode(item, button));
  button.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectWorkflowNode(item, button);
    }
  });
  return button;
}

function renderInlineConnector(targetRequirement = "required") {
  const connector = document.createElement("div");
  const requirement = normalizeRequirement(targetRequirement);
  connector.className = `elbow-connector inline connector-${requirement}`;
  connector.title = `${requirementLabels[requirement]}：${requirementDescriptions[requirement]}`;
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



function renderWorkflowRow(row, rowIndex) {
  const wrapper = document.createElement("section");
  const firstNode = row.nodes?.[0] || row.branches?.[0]?.nodes?.[0];
  const rowRequirement = normalizeRequirement(row.requirement || firstNode?.requirement);
  wrapper.className = `workflow-row ${row.type} requirement-${rowRequirement}`;

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
        if (index > 0) branchEl.appendChild(renderInlineConnector(item.requirement));
        branchEl.appendChild(renderWorkflowNode(item, rowIndex));
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
    if (index > 0) nodes.appendChild(renderInlineConnector(item.requirement));
    nodes.appendChild(renderWorkflowNode(item, rowIndex));
  });
  wrapper.appendChild(nodes);
  return wrapper;
}

function getSelectedWorkflow() {
  const selectedId = workflowSelect.value || workflowDefinitions[0].id;
  const definition = workflowDefinitions.find((item) => item.id === selectedId) || workflowDefinitions[0];
  return definition.build(latestTraceData);
}

function countWorkflowStats(workflow) {
  let phases = 0;
  let innerSteps = 0;
  workflow.rows.forEach((row) => {
    if (row.type === "parallel_group") {
      row.branches.forEach((branch) => {
        phases += branch.nodes.length;
        innerSteps += branch.nodes.reduce((total, item) => total + (item.innerSteps || []).length, 0);
      });
      return;
    }
    phases += (row.nodes || []).length;
    innerSteps += (row.nodes || []).reduce((total, item) => total + (item.innerSteps || []).length, 0);
  });
  return { phases, innerSteps };
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
  const stats = countWorkflowStats(workflow);
  intro.textContent = `${workflow.summary} · ${stats.phases} 个主阶段 / ${stats.innerSteps} 个细节点`;
  graph.appendChild(intro);

  const requirementLegend = document.createElement("div");
  requirementLegend.className = "requirement-legend";
  ["required", "optional", "conditional"].forEach((requirement) => {
    const item = document.createElement("span");
    item.className = `legend-item connector-${requirement}`;
    item.textContent = `${requirementLabels[requirement]}：${requirementDescriptions[requirement]}`;
    requirementLegend.appendChild(item);
  });
  graph.appendChild(requirementLegend);

  workflow.rows.forEach((row, index) => graph.appendChild(renderWorkflowRow(row, index)));
  canvas.appendChild(graph);
  workbench.appendChild(canvas);
  traceSteps.appendChild(workbench);
}

function traceStep(data, key) {
  return (data?.steps || []).find((step) => step.key === key) || null;
}

function updateConversationContext(data) {
  const nextContext = data.next_conversation_context;
  if (nextContext && typeof nextContext === "object" && !Array.isArray(nextContext)) {
    conversationContext = { ...nextContext };
    return;
  }

  const understanding = traceStep(data, "query_understanding")?.details || {};
  const targetSection = understanding.target_section || understanding.context_resolution?.selected?.section;
  const targetClause = understanding.target_clause || understanding.context_resolution?.selected?.clause;
  if (!targetSection) return;
  conversationContext = {
    ...conversationContext,
    last_target_section: targetSection,
    last_target_clause: targetClause || null,
  };
}


function renderLangfuseStatus() {
  if (!langfuseTraceLink) return;
  const observability = latestTraceData?.observability;
  langfuseTraceLink.className = "langfuse-link status-disabled";
  langfuseTraceLink.removeAttribute("href");
  langfuseTraceLink.removeAttribute("target");
  langfuseTraceLink.removeAttribute("rel");
  langfuseTraceLink.setAttribute("aria-disabled", "true");
  langfuseTraceLink.title = "发送问题后，如果后端启用了 Langfuse，这里会打开本次 trace。";

  if (!observability || observability.enabled === false || observability.status === "disabled") {
    langfuseTraceLink.textContent = "Langfuse 未启用";
    return;
  }

  if (observability.status === "ok" && observability.trace_url) {
    langfuseTraceLink.className = "langfuse-link status-ok";
    langfuseTraceLink.href = observability.trace_url;
    langfuseTraceLink.target = "_blank";
    langfuseTraceLink.rel = "noreferrer noopener";
    langfuseTraceLink.removeAttribute("aria-disabled");
    langfuseTraceLink.textContent = "打开 Langfuse";
    langfuseTraceLink.title = observability.trace_id ? `Trace ID: ${observability.trace_id}` : "打开本次 Langfuse trace";
    return;
  }

  if (observability.status === "ok") {
    langfuseTraceLink.className = "langfuse-link status-warn";
    langfuseTraceLink.textContent = "Langfuse 已上报";
    langfuseTraceLink.title = observability.trace_id ? `Trace ID: ${observability.trace_id}；未配置可打开的 Langfuse 链接。` : "已上报，但后端没有返回 trace 链接。";
    return;
  }

  if (observability.status === "unavailable") {
    langfuseTraceLink.className = "langfuse-link status-warn";
    langfuseTraceLink.textContent = "Langfuse 不可用";
    langfuseTraceLink.title = observability.error || "后端启用了 Langfuse，但 SDK 或配置不可用。";
    return;
  }

  langfuseTraceLink.className = "langfuse-link status-error";
  langfuseTraceLink.textContent = "Langfuse 上报失败";
  langfuseTraceLink.title = observability.error || "Langfuse 上报失败，主问答流程未中断。";
}

function renderSelectedWorkflow() {
  closeNodeDetailDrawer();
  const workflow = getSelectedWorkflow();
  traceSummary.textContent = latestTraceData ? `${workflow.title}：已叠加本次问题的执行细节` : workflow.summary;
  renderLangfuseStatus();
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
    body: JSON.stringify({ message, top_k: 3, conversation_context: conversationContext }),
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
  updateConversationContext(data);
  renderAssistantResponse(pending, data);
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
  conversationContext = {};
  traceSummary.textContent = "选择一个流程节点查看细节";
  renderLangfuseStatus();
  renderSelectedWorkflow();
});

populateWorkflowSelect();
renderSelectedWorkflow();
