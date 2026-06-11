const statusLabels = {
  shipped: "已落地",
  interface: "接口已预留",
  planned: "待接入",
};

function toolDoc(name, plain, input, output, role, boundary) {
  return { name, plain, input, output, role, boundary };
}

function pitfallGroup(title, items) {
  return { title, items };
}

function realCase(title, userInput, observed, rootCause, fix, result) {
  return { title, userInput, observed, rootCause, fix, result };
}

function choiceDoc(name, selected, why, alternatives, boundary) {
  return { name, selected, why, alternatives, boundary };
}

function ioExample(title, input, output, note) {
  return { title, input, output, note };
}

function knowledgePoint(term, plain, knowledgeFocus) {
  return { term, plain, knowledgeFocus };
}

function matchesEntry(entry, patterns) {
  const haystack = `${entry.id} ${entry.title} ${entry.subtitle || ""} ${entry.overview || ""}`.toLowerCase();
  return patterns.some((pattern) => haystack.includes(pattern.toLowerCase()));
}

function productionSection({ id, title, status, plain, flow, inputs, outputs, why, operation, requiredWhen, risks, validation, terms }) {
  return {
    id,
    title,
    subtitle: `${statusLabels[status] || status} · 生产 RAG 专题`,
    overview: plain,
    work: [
      `放在流程位置：${flow}`,
      `解决的问题：${why}`,
      `具体做法：${operation}`,
      `什么时候必须做：${requiredWhen}`,
    ],
    research: [
      "先判断它是基础链路、质量保障、观测治理、数据治理、权限安全，还是外部工具能力。",
      "再看它是否已经有代码落地、只是预留接口，还是需要真实业务系统才能接入。",
    ],
    decisions: [
      `当前状态标记为“${statusLabels[status] || status}”，避免把还没接真实服务的能力写成已经上线。`,
      "每个专题都要说明输入、输出、边界和验证方式，让学习者知道它不是一个抽象名词。",
    ],
    toolDocs: [
      toolDoc(title, plain, inputs, outputs, "让某一类 RAG 生产问题变成可控制、可验证、可回放的工程模块。", requiredWhen),
    ],
    pitfallGroups: [
      pitfallGroup("主要风险", risks),
      pitfallGroup("验证方式", validation),
    ],
    terms: terms || [],
    studyPrompts: [
      "如果知识点追问为什么要加这个能力，你能不能先讲它解决的失败场景，而不是先讲工具名？",
      "如果这个能力不上线，最可能在哪个用户问题上暴露风险？",
    ],
  };
}

const productionTopics = [
  productionSection({
    id: "production-eval-runner",
    title: "回归评测集与 Eval Runner",
    status: "shipped",
    plain: "它像一套固定考试题。每次你改检索、重排或回答格式，都用同一批题检查有没有把旧问题修坏。",
    flow: "每次改 query understanding、rewrite、hybrid search、rerank、evidence filter、answer 之后。",
    inputs: "用户问题、期望命中的制度、必须出现的关键词、禁止出现的关键词、期望来源链接。",
    outputs: "每条样本通过或失败，以及失败原因，例如缺关键词、错来源、带出禁止词。",
    why: "之前我们靠手工问“二类违规”“旷工两天”发现问题，修 A 很容易坏 B。",
    operation: "把真实错例整理成 regression case；测试时跑完整问答链路，检查来源、关键词和禁止词。",
    requiredWhen: "只要不是一次性 demo，就应该有。真实业务开发必须让关键问题可重复验证。",
    risks: ["样本太少会形成假安全感。", "只检查答案文字、不检查来源，会放过幻觉式回答。", "禁止词不写清楚，二类违规仍可能带出三类违规。"],
    validation: ["二类违规是什么不能出现三类违规正文。", "旷工两天必须出现扣除工资、记过处分和两个来源。", "虚假报销、打听工资等行为题要命中正确制度分类。"],
    terms: [{ term: "Eval", definition: "用固定样本衡量系统质量的测试方法。" }],
  }),
  productionSection({
    id: "production-bad-case",
    title: "Bad Case 采集与反馈闭环",
    status: "shipped",
    plain: "它像错题本。用户发现回答不对时，不只是当场修，而是把这个错例沉淀成以后每次都要检查的样本。",
    flow: "答案展示之后，用户点踩、标记错来源、缺条款或答非所问时。",
    inputs: "query、feedback_type、trace_id、答案摘要、来源摘要、用户补充说明。",
    outputs: "一条可审查的 bad case 记录，后续可以转成回归评测样本。",
    why: "线上问题如果只存在聊天记录里，很快会丢失上下文。",
    operation: "只保存 citation 摘要，不保存完整制度正文；人工确认后加入 regression dataset。",
    requiredWhen: "面向真实用户时必须有，否则系统不会越用越稳。",
    risks: ["反馈里可能包含敏感信息。", "如果保存完整制度正文，容易产生数据泄露风险。", "没有分类字段，后续不知道这是错来源、缺条款还是答太泛。"],
    validation: ["测试确认 bad case 文件不保存完整 chunk 文本。", "反馈类型必须在白名单内。"],
    terms: [{ term: "Bad Case", definition: "真实失败样本，用来复盘和回归测试。" }],
  }),
  productionSection({
    id: "production-ingest-quality",
    title: "导入质量报告",
    status: "interface",
    plain: "它像入库体检报告。不是说“我导入了”，而是说每个分类导入多少、失败多少、为什么失败。",
    flow: "分类分页、详情拉取、HTML 清洗、附件解析、chunk、embedding、upsert 之后。",
    inputs: "分类列表、列表分页结果、详情响应、清洗结果、chunk 统计、embedding 写入结果、失败异常。",
    outputs: "分类数、文档数、chunk 数、附件数、失败原因、跳过原因、重试建议。",
    why: "用户明确要求按分类录入，并列出处理了哪些数据。没有质量报告就无法解释覆盖范围。",
    operation: "导入器累计每个分类的处理指标，最后落盘或在页面展示。",
    requiredWhen: "一旦接真实制度库批量导入就必须做。",
    risks: ["只统计总数会掩盖某个分类全失败。", "只记录异常文本，不记录文章 ID，后续无法重跑。", "附件解析失败如果不进报告，知识库会缺关键条款。"],
    validation: ["12 个分类分别展示文章数和 chunk 数。", "失败样本可以按分类重试。"],
    terms: [{ term: "Ingest", definition: "把外部知识源清洗、切块并写入检索库的过程。" }],
  }),
  productionSection({
    id: "production-permission",
    title: "适用对象与权限过滤",
    status: "planned",
    plain: "它像门禁。员工、学生、小学部、财务、人事看到的制度范围可能不一样，不能只靠模型自己猜。",
    flow: "检索计划和初始召回之前，作为 metadata filter 或查询路由条件。",
    inputs: "登录用户、组织关系、角色、学段、制度 metadata、用户问题里的适用对象。",
    outputs: "允许检索的 audience_scope 和 permission_filter。",
    why: "同一个“旷工”问题，员工制度和学生考勤制度不能混用。",
    operation: "从可信登录态和制度 metadata 生成过滤条件；query 里提到学生、小学、财务时再缩小范围。",
    requiredWhen: "知识库包含不同人群、组织或权限内容时必须做。",
    risks: ["只靠 LLM 判断权限不可信。", "cache key 如果缺权限维度，会把 A 用户答案给 B 用户。", "metadata 缺失时应该降级澄清，而不是乱答。"],
    validation: ["员工身份不能召回学生内部制度。", "学生问题不能优先命中员工纪律制度。"],
    terms: [{ term: "Metadata Filter", definition: "用结构化字段先过滤候选资料，再做语义检索。" }],
  }),
  productionSection({
    id: "production-answer-contract",
    title: "结构化答案契约",
    status: "shipped",
    plain: "它像答题模板。制度问答不能把一大段原文甩给用户，而要固定讲事实、规则、结论、依据和不确定性。",
    flow: "证据确认之后、前端展示之前。",
    inputs: "用户问题、命中规则、证据片段、来源链接、不确定条件。",
    outputs: "事实、规则匹配、违规类型、处理结果、处罚依据、不确定性提醒、来源依据。",
    why: "用户指出回答里标题和正文没层次，处理结果不突出，来源没有链接。",
    operation: "后端组织结构化段落，前端按标签渲染成分区和列表。",
    requiredWhen: "制度、HR、合规、财务问答都应该有。",
    risks: ["如果只靠文本标签解析，格式漂移会影响展示。", "后续应升级成 JSON schema。"],
    validation: ["处理结果以列表展示。", "来源有 policyDetail 链接。"],
    terms: [{ term: "Answer Contract", definition: "前后端约定好的答案字段结构。" }],
  }),
  productionSection({
    id: "production-rule-resolver",
    title: "多跳规则解析器 Rule Resolver",
    status: "shipped",
    plain: "它像按制度做计算。用户说“旷工两天”，系统要先看两天落在哪个条件里，再找对应处罚。",
    flow: "Query Understanding 之后、检索计划之前。",
    inputs: "用户事实、行为词、数量、单位、问题面、制度规则候选。",
    outputs: "matched_rule、比较过程、处罚证据、分类证据、需要补问的条件。",
    why: "“我旷工两天会怎样”不是普通语义题，而是事实 -> 条件 -> 结论。",
    operation: "解析 behavior=旷工、duration=2、asked_aspect=处罚，匹配连续旷工3个工作日以下，再补二类违规分类。",
    requiredWhen: "问题里有次数、天数、累计、阈值、少于、以上时。",
    risks: ["硬编码只能覆盖样例。", "单位不清楚时要提醒是工作日还是自然日。", "规则版本变化后需要重新抽取。"],
    validation: ["2 < 3 命中记过。", "3 天及以上命中辞退，不能误用三天以下。"],
    terms: [{ term: "Rule Resolver", definition: "把用户事实映射到制度条件和结论的模块。" }],
  }),
  productionSection({
    id: "production-reranker",
    title: "Cross-encoder Reranker",
    status: "interface",
    plain: "它像复审老师。初召回先找一堆可能相关的材料，reranker 再判断哪一段最能回答当前问题。",
    flow: "初召回之后、证据过滤之前。",
    inputs: "query 和候选文档片段列表。",
    outputs: "每个候选的新分数、排序、降级原因或外部服务错误。",
    why: "向量检索会觉得“二类违规定义”和“二类违规处罚”都相关，但用户问处罚时定义块不是最佳答案。",
    operation: "优先预留 HTTP reranker；没有服务时用确定性规则加分，例如处罚词、目标章节、行为词。",
    requiredWhen: "候选相似、答案要求精确、top-k 里常有相近但不回答的片段时。",
    risks: ["增加延迟和成本。", "不能替代权限过滤。", "模型分数要和规则硬约束一起用。"],
    validation: ["trace 展示 rerank 前后对比。", "服务超时能降级 deterministic fallback。"],
    terms: [{ term: "Cross-encoder", definition: "把问题和候选一起输入模型打分的重排方式。" }],
  }),
  productionSection({
    id: "production-query-router",
    title: "Query Router 查询路由",
    status: "interface",
    plain: "它像前台分诊。定义题、处罚题、规则计算题、实时个人数据题，不应该都走同一条路。",
    flow: "请求清洗后、query rewrite 和检索之前。",
    inputs: "意图、问题面、目标对象、是否有个人/实时/权限信息、是否缺条件。",
    outputs: "exact_clause、rule_resolver、semantic_rag、tool_api、clarification 等路线。",
    why: "“二类违规是什么”和“我还有几天年假”不是同一种问题。",
    operation: "先用规则和轻量分类输出 route，再把 route_reason 写入 trace。",
    requiredWhen: "系统同时支持静态制度、规则计算和外部业务 API 时。",
    risks: ["路由错会走错边界。", "缺少兜底澄清会导致乱答。", "路由决策必须可观测。"],
    validation: ["处罚题走规则/精确证据。", "实时余额题走工具 API 或提示无法回答。"],
    terms: [{ term: "Router", definition: "根据问题类型选择处理路径的模块。" }],
  }),
  productionSection({
    id: "production-span-highlight",
    title: "引用 Span 高亮",
    status: "interface",
    plain: "它像荧光笔。不是只告诉你参考了哪篇制度，而是标出真正支持答案的那一句。",
    flow: "证据组装和答案展示阶段。",
    inputs: "chunk 文本、章节路径、命中的条款、start/end 或 clause_id。",
    outputs: "最小证据范围、可点击来源、可高亮原文。",
    why: "用户需要知道答案来自具体哪条，而不是只看到整篇制度标题。",
    operation: "span extraction 找起止边界；前端来源区域显示章节和条款，后续可展开高亮。",
    requiredWhen: "制度、法务、财务、合规场景都建议做。",
    risks: ["chunk 太粗会让 span 不稳定。", "OCR 或 HTML 清洗错误会导致定位错位。"],
    validation: ["二类违规只高亮二类段落，不带三类。", "旷工处罚只高亮三天以下对应规则。"],
    terms: [{ term: "Span", definition: "文本中的一小段连续范围。" }],
  }),
  productionSection({
    id: "production-langfuse",
    title: "Langfuse / OpenTelemetry 观测链路",
    status: "interface",
    plain: "它像系统行车记录仪。出错时不是靠猜，而是按 trace_id 回放每一步发生了什么。",
    flow: "贯穿 intake、rewrite、embedding、retrieval、rerank、answer、feedback。",
    inputs: "每个阶段的输入、输出、耗时、模型版本、候选列表、分数、过滤原因、用户反馈。",
    outputs: "trace、span、score、dataset、线上回放记录。",
    why: "今天很多追问都是“为什么这个答案错了”，没有观测就只能猜是数据、模型、规则还是提示词。",
    operation: "本地 trace 先服务教学；生产接 Langfuse 或 OpenTelemetry exporter，记录可脱敏的关键中间值。",
    requiredWhen: "多人使用、上线、接外部模型、接真实制度数据时必须做。",
    risks: ["不能记录 authentication cookie、完整敏感制度正文。", "需要脱敏、采样和权限控制。", "只记录最终 prompt 不够，必须记录检索候选和过滤原因。"],
    validation: ["用 trace_id 回放一个错例，能定位到 rewrite、hybrid search、rerank 或 answer。"],
    terms: [{ term: "Span", definition: "trace 里的一个子步骤记录。" }, { term: "Score", definition: "对一次回答质量或检索质量的评分。" }],
  }),
  productionSection({
    id: "production-incremental-sync",
    title: "增量同步与版本管理",
    status: "planned",
    plain: "它像制度库的版本控制。制度改了、删了，向量库也要跟着变，不能继续回答旧规则。",
    flow: "制度导入、chunk upsert、删除同步阶段。",
    inputs: "source_updated_at、content_hash、version、deleted_at、doc_id、chunk_id。",
    outputs: "新增、更新、软删除的 chunk 和索引状态。",
    why: "只追加不更新会让旧制度残留在检索库里。",
    operation: "按 content_hash 判断是否变化，按 source_id 处理删除，保留版本用于追溯。",
    requiredWhen: "制度源持续维护时必须做。",
    risks: ["只按标题判断会误伤。", "删除不同步会污染答案。", "版本字段缺失会导致无法回溯。"],
    validation: ["模拟制度修改和删除，确认检索结果随版本变化。"],
    terms: [{ term: "Content Hash", definition: "根据正文算出的指纹，用来判断内容是否变化。" }],
  }),
  productionSection({
    id: "production-parsers",
    title: "PDF / Word / 表格 / OCR 解析",
    status: "planned",
    plain: "它像把附件翻译成系统能读懂的文字。制度经常藏在 Word、PDF、表格和扫描件里。",
    flow: "附件导入阶段，进入 HTML 清洗和 chunk 之前。",
    inputs: "fileList、文件类型、二进制内容、OCR 结果、表格结构。",
    outputs: "结构化文本、表格行列、图片识别文本、解析质量指标。",
    why: "只导入网页 body 会漏掉附件里的关键制度。",
    operation: "按文件类型选择 parser；表格保留行列语义；扫描件走 OCR；结果进入导入质量报告。",
    requiredWhen: "fileList 不为空或制度正文依赖附件时。",
    risks: ["表格拍平会丢条件。", "OCR 错字影响条款匹配。", "附件权限可能和正文不同。"],
    validation: ["报告附件解析成功率、空文本率、表格数量和 OCR 置信度。"],
    terms: [{ term: "OCR", definition: "把图片里的文字识别成可搜索文本。" }],
  }),
  productionSection({
    id: "production-prompt-injection",
    title: "Prompt Injection 与数据泄露护栏",
    status: "planned",
    plain: "它像安全检查。用户或文档可能试图让系统忽略规则、泄露信息或调用危险工具。",
    flow: "请求入口、文档导入、工具调用、答案输出四个边界。",
    inputs: "用户 query、文档内容、工具调用请求、输出答案。",
    outputs: "放行、拒绝、脱敏、降级或人工确认。",
    why: "真实 Agent/RAG 不只是回答准，还要防止越权和泄露。",
    operation: "入口意图检查，文档指令隔离，工具白名单，权限校验，输出敏感信息检查。",
    requiredWhen: "接用户上传、外部文档、工具 API 或真实权限数据时。",
    risks: ["一句 prompt 不能解决安全问题。", "工具没有白名单会扩大攻击面。", "文档里的恶意指令不能当系统指令执行。"],
    validation: ["恶意 query 不能泄露系统提示。", "恶意文档不能覆盖系统规则。", "无权限工具不能被调用。"],
    terms: [{ term: "Prompt Injection", definition: "用输入内容诱导模型违反系统规则的攻击。" }],
  }),
  productionSection({
    id: "production-cache-cost",
    title: "缓存与成本控制",
    status: "planned",
    plain: "它像记住重复劳动。相同文档不要反复 embedding，相似重复问题不要每次都全链路重跑。",
    flow: "embedding、rerank、LLM answer、工具 API 调用前后。",
    inputs: "query、normalized_query、user_scope、model_version、data_version、content_hash。",
    outputs: "缓存命中结果、重新计算结果、成本和延迟指标。",
    why: "并发上来后，重复计算会让系统慢且贵。",
    operation: "按权限和数据版本设计 cache key；document embedding 按 content_hash 缓存。",
    requiredWhen: "并发、成本或外部服务限流成为问题时。",
    risks: ["cache key 少了权限会串数据。", "数据版本不进 key 会返回旧答案。", "缓存过度会掩盖质量问题。"],
    validation: ["重复问题命中缓存。", "不同权限用户不会共享敏感答案。"],
    terms: [{ term: "Cache Key", definition: "决定一条缓存是否可以复用的唯一标识。" }],
  }),
  productionSection({
    id: "production-tool-api",
    title: "外部知识 API 与工具检索",
    status: "planned",
    plain: "它像去业务系统查实时信息。制度能回答规则，但不能回答你个人现在还有几天年假。",
    flow: "Query Router 判断静态制度无法回答时进入。",
    inputs: "用户身份、工具名称、工具参数、权限上下文、超时设置。",
    outputs: "实时业务结果、工具错误、无权限、空结果或部分失败。",
    why: "静态 RAG 只能回答制度规则，不能回答审批状态、余额、个人记录。",
    operation: "建立 tool registry；每个工具有 schema、权限、超时、重试和审计日志。",
    requiredWhen: "问题出现我的、当前、今天、余额、状态、审批、记录等动态信息。",
    risks: ["工具越权风险高于静态检索。", "外部服务超时要降级。", "工具输出也要进入 trace。"],
    validation: ["模拟超时、无权限、空结果、部分失败。", "工具调用 span 可回放。"],
    terms: [{ term: "Tool Registry", definition: "登记系统允许调用哪些工具、参数和权限的清单。" }],
  }),
];

const docChapters = [
  {
    id: "project-start",
    title: "项目起始",
    description: "先讲为什么做、怎么调研、为什么这样选型。",
    sections: [
      {
        id: "project-start-goal",
        title: "项目起始：业务目标与学习目标",
        subtitle: "从制度问答 demo 到 AI Agent / RAG 学习工作台",
        overview: "这一章回答一个最基本的问题：我们到底在做什么。它不是单纯让 AI 回答制度，而是把一次回答背后的检索、判断、过滤、引用和观测过程讲清楚，让没有接触过 AI Agent 的技术人员也能学习。",
        work: ["明确左侧做业务问答，右侧做流程解释，文档页做系统化学习。", "把目标从“能答”提升到“答得准、说得清、能复盘、能教学”。", "把每次问题都沉淀成流程节点、测试样本或文档章节。"],
        research: ["先看真实制度页面是不是静态页面，再确认背后的 API。", "先验证最小响应形状，再决定导入器和数据结构。", "先跑通一小类制度，再扩到 12 个分类。"],
        decisions: ["选 FastAPI 是为了快速暴露 API、方便测试和部署。", "选原生 JS/CSS 是为了先把学习工作台跑起来，不引入构建链。", "选 pgvector 是因为早期数据规模小，Postgres 可以同时管理 metadata 和向量。"],
        toolDocs: [
          toolDoc("FastAPI", "像一个轻量后端服务员：接收网页请求，把问题交给 RAG 流程，再把答案和 trace 返回。", "HTTP 请求，比如 /api/chat。", "JSON 响应，比如 answer、results、steps。", "提供 Web 页面、问答 API、反馈 API 和文档页。", "它不负责理解制度内容，只负责服务入口和返回结构。"),
          toolDoc("原生 JS/CSS", "像页面里的操作说明书：负责点击、渲染、切换目录、展示流程和答案。", "后端返回的数据、用户点击。", "页面上的消息、流程图、文档内容。", "降低部署复杂度，适合当前单页学习工具。", "后续如果交互继续变复杂，可以迁移到组件框架。"),
          toolDoc("pgvector", "像带向量能力的资料库：既能存制度片段，也能按语义距离查相似内容。", "chunk、metadata、embedding 向量。", "最相似的制度片段列表。", "让制度数据和来源字段保存在同一个 Postgres 体系。", "当前远端 demo 模式没有接真实 pgvector。"),
        ],
        pitfallGroups: [
          pitfallGroup("目标容易偏掉", ["只做聊天框会变成普通 demo。", "只做流程图会脱离真实业务。", "只写文档不接真实问答会缺乏可信度。"]),
          pitfallGroup("选型容易过度", ["一开始就上复杂前端框架会拖慢验证。", "数据只有百级时直接上大型向量库会增加运维负担。"]),
        ],
        studyPrompts: ["为什么真实 RAG 产品不能只看最终答案？", "如果你按知识点介绍这个项目，第一句话应该讲业务目标还是模型技术？"],
      },
      {
        id: "project-start-source-research",
        title: "项目起始：数据源调研与接口验证",
        subtitle: "从***公司制度页面找到真实 API",
        overview: "这一节讲我们怎么从一个制度页面出发，确认真实数据来自接口，而不是页面 HTML。这个阶段最重要的是克制：只做最小 API 验证，不直接全量抓取。",
        work: ["验证分类元数据接口。", "验证列表第一页前 3 条。", "验证单条详情接口，确认正文在 body HTML 中。", "统计 12 个分类共 133 条制度。"],
        research: ["观察前端资源，确认 policyList 和详情页对应的接口。", "比较列表字段和详情字段，确认列表没有完整正文。", "只按分类取 pageSize=1 读取 total，避免全量拉正文。"],
        decisions: ["列表接口只负责枚举 ID 和标题。", "详情接口才是 RAG 原文来源。", "来源链接必须使用真实可访问的 /policyDetail/{id}。"],
        toolDocs: [
          toolDoc("policySystemTypeList", "像目录接口：告诉你制度有哪些分类和分组。", "policyType=2。", "分类列表、分类 ID、分类中英文名。", "决定后续按哪些分类分页导入。", "它不返回制度正文。"),
          toolDoc("informationList", "像文章列表：告诉你每页有哪些制度文章。", "keyword、pageNum、pageSize、policyType、policyCategoryType。", "importInformationId、标题、发布时间、分类、目标组。", "枚举详情 ID。", "列表里的 body 基本不能当 RAG 正文。"),
          toolDoc("notificationById", "像文章详情：给出单篇制度完整正文。", "importInformationId。", "标题、发布时间、body HTML、fileList。", "RAG 原始文本主要来自这里。", "附件可能为空，也可能后续需要解析。"),
        ],
        pitfallGroups: [
          pitfallGroup("接口幻读", ["不能凭 URL 猜详情链接，必须以实际可访问链接和接口字段为准。", "之前 /home/policyDetail?importInformationId=16 就不是最终展示链接。"]),
          pitfallGroup("数据误用", ["列表字段看起来有 body，但内容为空或不完整。", "不拉详情就做 embedding，会导致知识库只有标题和摘要。"]),
          pitfallGroup("安全边界", ["临时响应文件里可能有真实制度正文，验证后要清理。", "authentication cookie 不能写进代码或上传。"]),
        ],
        studyPrompts: ["为什么真实导入前要先做接口形状验证？", "如果接口返回 ifLogin=false，你应该在哪一步中断？"],
      },
    ],
  },
  {
    id: "knowledge-build",
    title: "知识库构建",
    description: "讲分类导入、正文清洗、chunk 粒度和来源链接。",
    sections: [
      {
        id: "knowledge-ingest",
        title: "知识库构建：分类导入与结构化切块",
        subtitle: "分类列表 -> 分页列表 -> 详情正文 -> HTML 清洗 -> chunk -> embedding",
        overview: "这一节讲制度怎么进入知识库。关键不是把文本存进去，而是保留分类、章节、条款、来源链接和失败原因。",
        work: ["按 12 个分类分页处理。", "每条列表再拉详情 body。", "清洗 HTML 并保留标题层级。", "按章节和条款切 chunk。", "为每个 chunk 保存 source_url、heading_path、category、publishDate。"],
        research: ["先用一个小分类跑通链路，再考虑全量。", "观察二类违规案例，确认粗 chunk 会混入三类违规。", "评估附件 fileList，先兼容空列表，后续接附件解析。"],
        decisions: ["chunk 要尽量对应完整规则块，而不是固定长度硬切。", "source_url 必须跟随 chunk 保存，答案才能给来源。", "导入统计要保留分类级结果，后续形成质量报告。"],
        toolDocs: [
          toolDoc("HTML 清洗", "像把网页正文洗成可读文本：去掉标签噪音，但保留标题、编号和条款。", "body HTML。", "结构化文本块和标题路径。", "减少 HTML 噪声对检索的影响。", "不能把表格和编号洗没。"),
          toolDoc("Chunker", "像切资料卡片：把长制度切成模型容易检索的小段。", "清洗后的正文、标题层级、token 上限。", "多个带 metadata 的 chunk。", "让检索命中最小可用证据。", "太粗会混章节，太细会丢上下文。"),
          toolDoc("Embedding", "像给每张资料卡做语义坐标：意思相近的文本在向量空间更近。", "chunk 文本。", "一组数字向量。", "支持语义检索。", "精确条款和数字规则不能只靠它。"),
        ],
        pitfallGroups: [
          pitfallGroup("Chunk 粒度", ["二类违规和三类违规放在同一块，会导致回答越界。", "固定 token 切分不理解制度章节。", "最小块应该是完整条款或规则组。"]),
          pitfallGroup("来源缺失", ["没有 source_url，答案无法回到原制度。", "同文档相邻 chunk 不合并，来源会重复。"]),
          pitfallGroup("导入质量", ["不按分类统计，就不知道哪类漏了。", "失败只打印日志不入报告，后续无法重跑。"]),
        ],
        studyPrompts: ["为什么 chunk 粒度比 embedding 模型还影响答案质量？", "如果一个制度标题下有 20 条处罚规则，你会怎么切？"],
      },
      {
        id: "knowledge-chunk-boundary",
        title: "知识库构建：章节边界与 Span 截取",
        subtitle: "解决“二类违规”带出“三类违规”的问题",
        overview: "这一节是我们遇到的第一个典型 RAG 坑：用户问的是精确章节，但证据块太粗，导致答案把相邻章节也带出来。",
        work: ["识别目标章节起点，例如（二）二类违规行为。", "识别同级下一章节终点，例如（三）三类违规行为。", "检索后只截取目标 span。", "同文档同章节来源合并展示。"],
        research: ["分析错误答案，发现 top chunk 同时包含一类结尾、二类全文、三类开头。", "确认问题不是模型乱答，而是证据本身混杂。"],
        decisions: ["导入时切细是根治，运行时 span extraction 是保险。", "Evidence Filter 要看章节边界，不只是看相似度。", "引用要到章节和条款，不能只到文档。"],
        toolDocs: [
          toolDoc("Span Extraction", "像从一页书里划出真正有用的几行。", "粗 chunk、目标标题、同级标题规则。", "最小证据文本。", "避免把相邻章节带进答案。", "依赖标题识别质量。"),
          toolDoc("Citation Merge", "像把重复参考文献合并。", "多个同源候选。", "去重后的来源列表。", "避免 [1][2][3] 都是同一篇制度。", "不能合并不同章节的证据。"),
        ],
        pitfallGroups: [
          pitfallGroup("证据混杂", ["模型只是复述了 chunk 里的内容。", "粗 chunk 会让 rerank 和 answer 都很难救。"]),
          pitfallGroup("边界识别", ["中文编号、阿拉伯编号、括号编号都要识别。", "标题缺失时要降级为更保守的截取。"]),
        ],
        studyPrompts: ["为什么“二类违规是什么”更像精确条款查询，而不是开放语义查询？"],
      },
    ],
  },
  {
    id: "rag-pipeline",
    title: "RAG 问答链路",
    description: "讲 query understanding、rewrite、hybrid search、rerank、证据过滤和答案。",
    sections: [
      {
        id: "rag-query-understanding",
        title: "RAG 链路：Query Understanding 与 Query Rewrite",
        subtitle: "先理解问题，再决定怎么检索",
        overview: "这一节讲为什么“二类违规的处罚是什么”不能只识别“二类违规”。系统必须识别目标对象、问题面、行为、数量、适用对象。",
        work: ["识别 target_section、target_behavior、asked_aspect。", "把处罚扩展成处理、处分、违规处理、纪律处分、记过、辞退等制度词。", "把口语问题改写成适合检索的 standalone query。"],
        research: ["对比“二类违规是什么”和“二类违规的处罚是什么”的失败结果。", "确认制度正文里可能不用“处罚”这个词，而用“处分/处理”。"],
        decisions: ["清洗和改写分开：清洗只处理格式，不能改语义。", "rewrite 只做安全同义扩展，不能偷换问题。", "问题面 asked_aspect 会影响召回目标。"],
        toolDocs: [
          toolDoc("Query Understanding", "像先听懂用户到底问什么。", "原始问题。", "目标对象、问题面、条件参数、适用对象。", "决定后面走定义、处罚、规则计算还是澄清。", "不应该凭空补用户没说的条件。"),
          toolDoc("Query Rewrite", "像把口语问题翻译成制度库更容易搜到的话。", "原始问题和理解结果。", "standalone query 和扩展词。", "提高召回率。", "只能扩展同义词，不能改变意图。"),
        ],
        pitfallGroups: [
          pitfallGroup("理解不完整", ["只识别目标对象，不识别问题面，会把处罚题答成定义题。", "不识别数量，两天、三天、一年内两次会混。"]),
          pitfallGroup("改写过度", ["把问题改成系统擅长回答的问题，是严重语义漂移。", "同义词扩展要能解释来源。"]),
        ],
        studyPrompts: ["为什么 query rewrite 不是越多越好？", "如果用户问“我会不会被辞退”，asked_aspect 应该是什么？"],
      },
      {
        id: "rag-retrieval-rerank",
        title: "RAG 链路：Hybrid Search、Rerank 与 Evidence Filter",
        subtitle: "相关不等于能回答",
        overview: "这一节讲召回和证据判断。向量检索负责找语义相近，关键词负责找制度原词，rerank 负责排序，Evidence Filter 负责判断候选能不能回答问题。",
        work: ["根据 query understanding 制定检索计划。", "向量召回和关键词召回合并。", "rerank 对候选重新排序。", "Evidence Filter 区分直接证据、行为证据、参见线索。"],
        research: ["分析为什么处罚问题总是先命中定义块。", "确认参见型片段不能直接作为答案，但可以触发二跳检索。"],
        decisions: ["Hybrid Search 比纯 embedding 更适合制度编号和正式词。", "Rerank 是可选增强，但精确制度问答强烈建议启用。", "Evidence Filter 不能一刀切丢参见线索。"],
        toolDocs: [
          toolDoc("Hybrid Search", "像同时问两个检索员：一个按意思找，一个按关键词找。", "query embedding、关键词、metadata filter。", "合并后的候选片段。", "兼顾语义表达和精确条款。", "权重要按问题类型调。"),
          toolDoc("Rerank", "像把初筛材料重新排座次。", "query 和候选片段。", "新排序和分数。", "让真正回答问题的证据排前面。", "不能代替权限和规则判断。"),
          toolDoc("Evidence Filter", "像证据审查员：判断这段材料能不能支撑答案。", "候选片段、问题面、目标章节、规则解析结果。", "保留、降权、截断、丢弃和原因。", "防止相关但不回答的材料进入答案。", "过滤原因必须写入 trace。"),
        ],
        pitfallGroups: [
          pitfallGroup("召回偏差", ["embedding 觉得定义和处罚都相关。", "关键词太强会召回一堆只含术语但不回答的片段。"]),
          pitfallGroup("重排误用", ["reranker 分数高不代表有权限。", "外部 reranker 超时必须降级。"]),
          pitfallGroup("证据质量", ["相关证据、直接证据、参见证据要区分。", "处罚问题不能只给定义证据。"]),
        ],
        studyPrompts: ["为什么 rerank 是可选，但 evidence filter 接近必需？"],
      },
    ],
  },
  {
    id: "rule-answer",
    title: "规则推理与答案呈现",
    description: "讲规则型查询、结构化答案和来源链接。",
    sections: [
      {
        id: "rule-resolver",
        title: "规则推理：旷工两天为什么能算出处罚",
        subtitle: "用户事实 -> 制度条件 -> 结论条款",
        overview: "这一节讲我们怎么处理“我旷工两天会受到什么处罚”。这类问题不能只查相似文本，而要先把事实结构化，再匹配制度条件。",
        work: ["抽取行为：旷工。", "抽取数量：2 天。", "识别问题面：处罚。", "匹配条件：2 < 3，连续旷工3个工作日以下。", "补充违规类型：二类违规中的破坏学校管理秩序行为。"],
        research: ["第一次回答无结果，说明检索没有理解行为和数量。", "第二次只给处罚不够，业务上还要说明属于哪类违规。"],
        decisions: ["规则型查询抽成 Rule Resolver，不再在 pipeline 里临时硬写。", "答案必须展示比较过程，而不是只给结论。", "分类证据和处罚证据都要列来源。"],
        toolDocs: [
          toolDoc("Rule Resolver", "像按制度规则做判断题。", "用户事实、行为、数量、单位、问题面。", "匹配规则、比较过程、结论证据、分类证据。", "解决带阈值和条件的制度问题。", "长期应从制度文本抽规则，不只写样例。"),
          toolDoc("结构化答案", "像把答案写成清楚的报告。", "事实、规则、证据、来源。", "事实、规则匹配、违规类型、处理结果、依据、提醒。", "让用户快速看到结论和原因。", "后续最好升级成 JSON schema。"),
        ],
        pitfallGroups: [
          pitfallGroup("规则条件", ["两天是自然日还是工作日？", "是否连续？", "是否已经请假审批？这些都会影响结论。"]),
          pitfallGroup("证据组合", ["处罚规则和违规分类可能来自两篇制度。", "只给处罚不说明违规类型，业务解释不完整。"]),
        ],
        studyPrompts: ["为什么规则题要显示“2 < 3”这种过程？", "如果用户问“一年内旷工两次”，Rule Resolver 应该抽取哪些字段？"],
      },
    ],
  },
  {
    id: "observability",
    title: "观测、评测与复盘",
    description: "讲 trace、Langfuse、回归评测和错题本。",
    sections: [
      {
        id: "observability-trace-eval",
        title: "观测与评测：为什么每一步都要可回放",
        subtitle: "Trace、Langfuse、Eval、Bad Case",
        overview: "这一节讲今天反复追问的核心：回答错了以后怎么知道错在哪里。答案不是看最终文本，而是看每一步输入、输出、候选、分数和过滤原因。",
        work: ["每个节点记录入参和出参。", "把常见问题从模板改成真实失败场景。", "建立 regression cases。", "新增 bad case feedback。", "预留 Langfuse / OpenTelemetry 生产观测。"],
        research: ["分析二类违规、二类违规处罚、旷工两天三个错例分别卡在哪一步。", "区分本地教学 trace 和生产观测 trace。"],
        decisions: ["本地 trace 用于教学展示。", "生产 trace 要接 Langfuse 或 OpenTelemetry，并做脱敏和采样。", "每次线上错例要进入 bad case，再筛选为 eval。"],
        toolDocs: [
          toolDoc("Trace", "像一次请求的录像。", "每一步的输入、输出、耗时、状态。", "可展开的执行记录。", "定位错误发生在哪一步。", "不能记录敏感凭证。"),
          toolDoc("Langfuse", "像专门给 AI 应用用的观测后台。", "trace、span、模型版本、候选、评分、反馈。", "回放记录、评分数据集、线上问题分析。", "生产排障和评测闭环。", "需要脱敏，不能把 authentication cookie 和完整敏感正文发出去。"),
          toolDoc("Bad Case", "像错题本。", "用户问题、错误类型、来源摘要、trace_id。", "可复盘失败样本。", "把线上问题变成可改进资产。", "默认不保存完整制度正文。"),
        ],
        pitfallGroups: [
          pitfallGroup("观测不足", ["只记录最终 prompt，不记录检索候选，无法定位召回问题。", "没有 trace_id，前后端日志串不起来。"]),
          pitfallGroup("评测不足", ["只测 happy path 会漏掉三类违规混入。", "只看答案关键词不看来源，会放过幻觉。"]),
          pitfallGroup("数据安全", ["观测平台不能直接存 AUTH_COOKIE。", "敏感制度正文要脱敏或摘要化。"]),
        ],
        studyPrompts: ["一个 RAG 答错了，你会按什么顺序看 trace？", "Langfuse 和前端 trace 的区别是什么？"],
      },
    ],
  },
  {
    id: "production-topics",
    title: "生产 RAG 专题",
    description: "15 个可独立学习和继续研究的生产化能力。",
    sections: productionTopics,
  },
  {
    id: "deployment",
    title: "部署上线",
    description: "讲独立 Docker 部署、端口隔离和远端验证。",
    sections: [
      {
        id: "deployment-remote",
        title: "部署上线：远端隔离与 IP 端口访问",
        subtitle: "不动机器上其他服务",
        overview: "这一节讲我们怎么把项目部署到 <server-ip>，并保证不影响机器上已有 nginx、Java、Docker 服务。",
        work: ["探测远端运行时和端口。", "发现没有 Python 3，但有 Docker。", "选择 8123 空闲端口。", "同步代码到 /opt/chatlearning/current。", "构建 chatlearning-rag 镜像并用独立容器启动。"],
        research: ["远端 80、443、5200、3000、8080 等都有服务。", "不安装系统 Python，避免污染机器环境。", "远端没有 embedding 服务，所以 demo 模式需要本地 deterministic embedding。"],
        decisions: ["用 Docker 而不是 yum 安装 Python。", "不接 nginx，因为用户要 IP + 端口直接访问。", "RAG_EMBEDDING_PROVIDER=local 只用于教学部署，生产仍应接真实 embedding 服务。"],
        toolDocs: [
          toolDoc("Docker", "像把应用装进一个独立盒子。", "镜像、环境变量、端口映射、挂载目录。", "独立运行的容器。", "避免影响机器上的系统 Python 和其他服务。", "容器名、端口、数据目录要独立。"),
          toolDoc("Deterministic Embedding", "像一个离线演示用的简化向量器。", "文本。", "固定规则生成的向量。", "让远端没有 BGE 服务也能跑通教学 demo。", "不能代表真实 embedding 模型效果。"),
          toolDoc("rsync 排除规则", "像搬家时列出不能搬的东西。", "项目目录和排除列表。", "远端代码目录。", "防止上传 .env、authentication cookie、数据库、日志和缓存。", "不能用删除同步误删远端内容。"),
        ],
        pitfallGroups: [
          pitfallGroup("机器隔离", ["不能占用已有端口。", "不能覆盖已有 nginx 配置。", "不能重启无关服务。"]),
          pitfallGroup("依赖隔离", ["远端没有 Python 3，不能假设本地启动方式可用。", "容器内安装依赖不会污染系统。"]),
          pitfallGroup("数据隔离", [".env、cookie、AUTH_COOKIE、jsonl、数据库不能上传。", "反馈数据单独挂载到 /opt/chatlearning/data。"]),
        ],
        studyPrompts: ["为什么远端 demo 要显式标记 local embedding？", "如果未来接真实 BGE 服务，部署变量应该怎么改？"],
      },
    ],
  },
];


const docsEnhancementRules = [
  {
    patterns: ["project-start", "source-research", "数据源调研"],
    realCases: [
      realCase(
        "来源链接被写错的问题",
        "用户指出 https://example.com/home/policyDetail?importInformationId=16 不能访问，正确地址是 https://example.com/policyDetail/16。",
        "回答里虽然给了制度标题，但来源 URL 不可点，用户无法核验。",
        "把前端路由和真实详情路由混在一起了；数据读取时没有把可访问链接作为字段校验。",
        "在 citation 里统一使用 source_url，并用真实链接格式 /policyDetail/{id}；测试里也校验 URL。",
        "后续回答“旷工两天”时同时返回 /policyDetail/11 和 /policyDetail/16。",
      ),
      realCase(
        "列表接口没有正文的问题",
        "最小验证 informationList?pageSize=3 后发现 body 和 fileList 基本为空。",
        "如果直接用列表数据入库，RAG 只能检索标题和发布时间，答不出制度条款。",
        "列表接口只负责枚举文章，详情接口 notificationById 才包含完整 HTML 正文。",
        "导入链路改为：分类 -> 列表分页 -> 详情正文 -> HTML 清洗 -> chunk。",
        "确认 12 个分类、133 条制度；后续导入按分类统计。",
      ),
    ],
    choices: [
      choiceDoc("FastAPI", "当前选用", "后端只需要清晰暴露 /api/chat、/api/feedback、/docs，FastAPI 足够轻，类型校验和测试也方便。", ["Flask：更轻，但参数校验和 OpenAPI 需要更多手写。", "Django：适合完整后台系统，但当前工作台过重。", "Node/Express：前端团队熟悉时可选，但当前 Python RAG 代码更多。"], "如果未来有复杂用户、权限、后台管理，再考虑 Django 或独立 BFF。"),
      choiceDoc("原生 JS/CSS", "当前选用", "先验证学习工作台和流程图交互，不引入构建链，部署最简单。", ["React/Vue：适合组件复杂、状态很多时升级。", "D3/React Flow：适合图编辑和复杂 DAG。", "低代码平台：快，但很难表达真实 trace 和教学细节。"], "当节点交互、抽屉、搜索、目录过滤继续变复杂时，应迁移到组件化框架。"),
    ],
    ioExamples: [
      ioExample(
        "真实接口最小验证",
        "GET /api/import/policySystemTypeList?policyType=2\nGET /api/import/informationList?pageNum=1&pageSize=3&policyType=2\nGET /api/import/notificationById?importInformationId=192",
        "分类接口返回 categoryList；列表接口返回 importInformationId、标题、发布时间；详情接口返回完整 body HTML。",
        "这个样例说明为什么不能跳过详情接口。",
      ),
      ioExample(
        "来源链接字段",
        { importInformationId: 16, title: "***公司人守则-员工纪律制度" },
        { source_url: "https://example.com/policyDetail/16", citation_title: "***公司人守则-员工纪律制度" },
        "真实业务里来源能不能打开，和答案本身一样重要。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint("RAG 不是直接问模型", "先查可信资料，再让模型基于资料回答。", "牛客 RAG 知识点常问完整链路、为什么能降低幻觉、和微调相比有什么优势。"),
      knowledgePoint("Citation", "答案里能点击核验的来源。", "知识点里可以强调：企业制度问答必须可追溯，否则业务方无法信任。"),
    ],
  },
  {
    patterns: ["knowledge", "chunk", "span", "结构化切块", "章节边界"],
    realCases: [
      realCase(
        "二类违规答案混入三类违规",
        "用户问：二类违规是什么。",
        "答案同时带出一类违规结尾、二类违规全文和三类违规开头。",
        "chunk 太粗，context assembly 没有同级章节边界意识。",
        "导入时按标题层级切块；检索后再做 span extraction，从“（二）二类违规行为”截到“（三）三类违规行为”之前。",
        "答案只保留二类违规段落，引用合并为同一篇制度同一章节。",
      ),
      realCase(
        "需要细化到 4. 弄虚作假行为",
        "用户指定：4. 弄虚作假行为及 4.1-4.4 应该作为一个内容块。",
        "原切块粒度只能到大章节，无法精确展示某个行为组。",
        "制度文本有多级编号，不能只按固定 token 长度切。",
        "把中文编号、阿拉伯编号和同级标题作为切块边界，保留 heading_path。",
        "检索结果可以细化到“二类违规行为 > 4. 弄虚作假行为”。",
      ),
    ],
    choices: [
      choiceDoc("结构化 Chunk", "当前选用", "制度条款天然有章节、条、款，按结构切比按固定长度切更可靠。", ["固定 token chunk：实现简单，但容易把二类和三类混在一起。", "滑窗 chunk：召回率高，但重复多、引用难合并。", "LLM 自动切块：语义好但成本高，且结果不稳定。"], "制度、合同、手册优先结构化切块；普通长文才考虑固定长度和滑窗。"),
      choiceDoc("HTML 清洗", "当前选用", "***公司详情 body 是 HTML，需要先把标签、nbsp、连续空白整理成可检索文本。", ["BeautifulSoup/lxml：更稳，适合复杂 HTML。", "正则清洗：快但容易误删结构。", "Markdown 转换：适合保留标题和列表。"], "当前样例可用轻量清洗，生产应使用结构化 HTML parser。"),
    ],
    ioExamples: [
      ioExample(
        "章节切块输入输出",
        "输入：...（二）二类违规行为 ... 4. 破坏学校管理秩序行为 4.2旷工少于三天。（三）三类违规行为 ...",
        { heading_path: ["员工纪律制度", "二类违规行为", "破坏学校管理秩序行为"], text: "4.2旷工少于三天。", source_url: "https://example.com/policyDetail/16" },
        "heading_path 是后续精确检索、引用和展示的关键字段。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint("Chunk 粒度", "把长文切成多小块，每块既不能太大，也不能丢掉上下文。", "牛客知识点常问 RAG 怎么优化，chunk 优化是最常见追问。"),
      knowledgePoint("Span Extraction", "命中粗块后，再从里面截出真正回答问题的那一小段。", "适合解释为什么“召回到了但回答仍然不准”。"),
    ],
  },
  {
    patterns: ["rag-query", "query understanding", "query rewrite", "hybrid", "rerank", "evidence"],
    realCases: [
      realCase(
        "二类违规处罚返回了二类违规定义",
        "用户问：二类违规的处罚是什么。",
        "系统返回二类违规行为定义，没有回答处罚。",
        "Query Understanding 只识别 target_section，没有识别 asked_aspect=disciplinary_action。",
        "把问题拆成目标对象、问题面、同义词和期望证据；rewrite 补充“处罚/处分/处理/违规处理”。",
        "检索从“二类违规定义块”转向“二类违规 + 处理条款”或跨章节证据。",
      ),
      realCase(
        "旷工两天一开始检索不到",
        "用户问：我旷工两天会受到什么处罚。",
        "系统提示没有足够相关内容。",
        "向量召回偏语义，相似证据被 evidence filter 一刀切过滤；系统没有理解“2 天 < 3 个工作日”。",
        "引入规则型理解：行为=旷工，数量=2，问题面=处罚；再做规则匹配和交叉证据召回。",
        "最终返回处罚制度和员工纪律制度两个来源。",
      ),
    ],
    choices: [
      choiceDoc("Hybrid Search", "当前选用", "制度问答既要语义相似，也要命中原文词，例如“旷工”“二类违规”“记过处分”。", ["纯向量检索：能找语义相似，但容易把一类/二类/三类混在一起。", "纯 BM25：能命中字面词，但处理口语改写弱。", "Elastic/OpenSearch：搜索能力强，但对当前 MVP 运维更重。"], "制度条款、法律条款、财务规则优先混合检索。"),
      choiceDoc("Rerank", "当前是规则 fallback，预留 cross-encoder", "先用可解释规则保证不能错，再用模型重排提高排序质量。", ["bge-reranker-v2-m3：中文和多语言场景常用。", "Cohere/Jina reranker：托管方便，但有成本和数据出境问题。", "只靠向量距离：简单但不能判断证据是否回答问题。"], "当 topK 候选里噪声多、问题面细、答案要求高时必须加。"),
    ],
    ioExamples: [
      ioExample(
        "Query Understanding 输出",
        "二类违规的处罚是什么",
        { target_section: "二类违规行为", asked_aspect: "disciplinary_action", target_terms: ["二类违规", "处罚", "处分", "处理"] },
        "这一步决定后面到底找定义、找流程，还是找处罚。",
      ),
      ioExample(
        "Hybrid Search 候选",
        { dense_query: "二类违规 disciplinary action", sparse_terms: ["二类违规", "处罚", "处分"] },
        [{ title: "员工纪律制度 > 违规处理", reason: "同时命中二类违规和处理条款" }],
        "候选进入 rerank 前要保留分数和命中理由，方便 trace 展示。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint("Query Understanding", "把用户一句话拆成系统能执行的检索任务。", "知识点里不要只说“做意图识别”，要说识别目标对象、问题面、条件参数、适用对象。"),
      knowledgePoint("Rerank", "在召回候选里重新排序，把真正能回答问题的证据放前面。", "牛客 RAG 题常问为什么只用向量检索不够。"),
    ],
  },
  {
    patterns: ["rule-resolver", "规则推理", "旷工"],
    realCases: [
      realCase(
        "处罚答案缺少违规类型",
        "用户问：我旷工两天会有什么处罚。",
        "答案只给了“扣除工资、记过处分”，没有说明它属于哪一类违规。",
        "系统只找到了工作时间及假期管理制度，没有继续找员工纪律制度里的分类证据。",
        "规则解析后要求 evidence set 至少包含处罚证据和分类证据。",
        "答案展示事实、规则匹配、违规类型、处理结果、处罚依据和不确定性提醒。",
      ),
    ],
    choices: [
      choiceDoc("Rule Resolver", "当前选用", "像“旷工两天”这种问题有数量和阈值，不能只靠相似度。", ["硬编码 if/else：快，但问题一多会失控。", "规则 DSL：更可维护，适合制度稳定后。", "Drools/规则引擎：强但接入成本高。", "LLM 直接判断：灵活但可解释性和稳定性不足。"], "现在先抽象 schema，后续从制度文本抽规则。"),
      choiceDoc("结构化答案", "当前选用", "用户要的是业务结论，不是大段 chunk。", ["直接贴 chunk：快但难读。", "自由文本总结：可读但难测。", "JSON schema + 模板渲染：最稳，适合生产。"], "规则型问答应逐步固定 answer schema。"),
    ],
    ioExamples: [
      ioExample(
        "规则解析输入输出",
        "我旷工两天会有什么处罚",
        { behavior: "旷工", duration: 2, unit: "天", matched_rule: "连续旷工3个工作日以下", comparison: "2 < 3", actions: ["扣除旷工期间工资", "给予记过处分"], violation_type: "二类违规行为" },
        "这个输出可以直接驱动答案和 trace 节点。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint("规则型查询", "用户给出事实，系统要按制度条件算出结论。", "知识点里可以用它区分普通 RAG 和业务规则推理。"),
      knowledgePoint("多跳证据", "一个答案需要来自多篇制度或多个章节的证据。", "真实业务常见，不能只取 top1 chunk。"),
    ],
  },
  {
    patterns: ["observability", "trace", "eval", "bad case", "langfuse"],
    realCases: [
      realCase(
        "不知道错在哪一步的问题",
        "用户连续追问：为什么二类违规处罚不对？为什么旷工两天没有结果？",
        "如果只看最终答案，无法判断是 query 理解、召回、过滤、重排还是答案模板出错。",
        "缺少每一步输入输出、候选、分数、过滤原因和 trace_id。",
        "前端 trace 展示教学过程；生产预留 Langfuse/OpenTelemetry 记录 span。",
        "每次错例可以按 trace 回放，再沉淀到 regression dataset。",
      ),
    ],
    choices: [
      choiceDoc("Langfuse", "接口已预留", "它专门记录 LLM/RAG 的 trace、span、prompt、评分和回放，比普通日志更贴合 AI 应用。", ["OpenTelemetry：通用观测标准，适合接企业现有链路。", "Arize Phoenix：偏 LLM observability 和评测。", "自研日志：最灵活，但检索候选、评分、回放要自己做。"], "真实制度正文、authentication cookie 不能直接上报。"),
      choiceDoc("Regression Dataset", "当前选用", "把今天发现的错例变成固定测试，避免后面修坏。", ["人工抽查：成本低但不可重复。", "RAGAS/DeepEval：指标丰富，但要结合业务标准。", "pytest 自定义：最贴近当前工程。"], "关键制度问题必须有来源、关键词和禁止词校验。"),
    ],
    ioExamples: [
      ioExample(
        "Trace 节点输入输出",
        { step: "evidence_filter", candidates: ["二类违规定义", "违规处理条款"], query_aspect: "处罚" },
        { kept: ["违规处理条款"], dropped: [{ title: "二类违规定义", reason: "不能回答处罚问题" }] },
        "排查时最有价值的是 drop reason，不只是最终 topK。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint("Trace", "一次请求从入口到回答的完整记录。", "牛客后端知识点会追问 RAG 出问题怎么排查，trace 是核心答案。"),
      knowledgePoint("Bad Case", "真实失败样本。", "比凭感觉优化更可靠，能说明你做过真实业务闭环。"),
    ],
  },
  {
    patterns: ["deployment", "部署"],
    realCases: [
      realCase(
        "远端机器不能影响其他服务",
        "用户要求部署到 root@<server-ip>，并且机器上其他东西都不要动。",
        "如果直接安装系统 Python、改 nginx 或删目录，可能破坏已有服务。",
        "部署边界没有隔离会造成不可控风险。",
        "用 Docker 独立容器，端口固定 8123->8010，rsync 排除 .env、data、logs、db、jsonl。",
        "远端只替换 chatlearning-rag 容器，保留 /opt/chatlearning/data 挂载。",
      ),
    ],
    choices: [
      choiceDoc("Docker", "当前选用", "把应用依赖装进容器，避免污染远端系统环境。", ["直接 venv 运行：轻，但远端 Python 版本和依赖容易不一致。", "systemd：适合长期服务，但仍要解决环境隔离。", "Kubernetes：适合多服务集群，当前单机过重。"], "容器只能管理 chatlearning-rag，不碰其他服务。"),
    ],
    ioExamples: [
      ioExample(
        "部署输入输出",
        "rsync 项目代码，排除 .env/.venv/data/logs/*.db/*.jsonl；docker run -p 8123:8010。",
        { url: "http://<server-ip>:8123/docs", container: "chatlearning-rag", mode: "RAG_EMBEDDING_PROVIDER=local" },
        "local embedding 只用于教学部署验收，不代表生产 embedding 效果。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint("环境隔离", "让一个应用的依赖、端口和数据不影响其他应用。", "后端知识点常问部署、扩容、故障隔离。"),
      knowledgePoint("配置和数据边界", "代码可以同步，密钥、cookie、数据库和日志不能随便同步。", "企业 AI 项目尤其要讲清数据安全。"),
    ],
  },
];

function alternativesForProduction(title) {
  if (title.includes("Eval")) return ["pytest 自定义评测：贴合当前业务。", "RAGAS/DeepEval：指标多，适合后续扩展。", "人工验收表：起步快，但不可持续。"];
  if (title.includes("Bad Case")) return ["Langfuse feedback：和 trace 绑定。", "客服工单：贴近用户但结构不稳定。", "JSONL 错题本：当前轻量可控。"];
  if (title.includes("导入")) return ["自定义 importer：最贴近***公司接口。", "Airflow/Dagster：适合复杂批处理调度。", "低代码 ETL：快但细节控制弱。"];
  if (title.includes("权限")) return ["metadata filter：检索前过滤。", "应用层 ACL：业务逻辑清晰。", "数据库 RLS：强隔离但实施复杂。"];
  if (title.includes("结构化答案")) return ["Pydantic/JSON Schema：可校验。", "自由文本模板：快但难测试。", "Function calling：适合模型直接产结构。"];
  if (title.includes("规则")) return ["规则 DSL：可维护。", "规则引擎：强但重。", "LLM 抽取：灵活但要验证。"];
  if (title.includes("Reranker")) return ["bge-reranker-v2-m3：中文友好。", "Cohere/Jina：托管方便。", "规则重排：可解释但覆盖有限。"];
  if (title.includes("Router")) return ["规则路由：稳定可解释。", "小模型分类：泛化更好。", "LLM router：灵活但成本和不确定性高。"];
  if (title.includes("Span")) return ["标题边界截取：适合制度。", "LLM 摘取：语义好但成本高。", "固定窗口：简单但容易混章节。"];
  if (title.includes("Langfuse")) return ["OpenTelemetry：通用标准。", "Arize Phoenix：LLM 观测友好。", "自研日志：灵活但成本高。"];
  if (title.includes("版本")) return ["content_hash：判断正文变化。", "source_updated_at：跟随源系统。", "deleted_at：处理删除同步。"];
  if (title.includes("PDF") || title.includes("OCR")) return ["unstructured/marker：文档解析。", "OCR：处理扫描件。", "表格 parser：保留行列语义。"];
  if (title.includes("Prompt Injection")) return ["入口 guardrails。", "文档指令隔离。", "输出敏感信息检查。"];
  if (title.includes("缓存")) return ["embedding cache。", "rerank cache。", "answer cache，但必须带权限和数据版本。"];
  if (title.includes("API")) return ["白名单 tool registry。", "OpenAI/厂商 Agents SDK。", "LangGraph 工具节点。"];
  return ["轻量规则实现。", "成熟开源框架。", "外部托管服务。"];
}

function createProductionEnhancement(entry) {
  if (entry.chapter.id !== "production-topics") return { realCases: [], choices: [], ioExamples: [], knowledgePoints: [] };
  const tool = Array.isArray(entry.toolDocs) ? entry.toolDocs[0] : null;
  return {
    realCases: [
      realCase(
        `${entry.title} 的真实触发场景`,
        `线上出现一个回答错误、来源错误、权限错误、成本过高或无法复盘的问题，需要判断是否由“${entry.title}”缺失导致。`,
        "如果没有这类能力，工程师只能临时看日志或凭经验猜。",
        entry.work && entry.work[1] ? entry.work[1].replace("解决的问题：", "") : "生产 RAG 链路缺少可验证的控制点。",
        entry.work && entry.work[2] ? entry.work[2].replace("具体做法：", "") : "把能力拆成明确输入、输出、边界和验收方式。",
        "在流程图和文档中标明状态：已落地、接口已预留或待接入，避免把概念说成上线能力。",
      ),
    ],
    choices: [
      choiceDoc(entry.title, statusLabels[entry.status] || entry.subtitle || "按专题状态决定", "先按真实失败场景决定是否需要，而不是因为名词热门就接入。", alternativesForProduction(entry.title), "没有接真实服务或真实权限的能力，只能标记为接口预留或待接入。"),
    ],
    ioExamples: [
      ioExample(
        `${entry.title} 的数据流`,
        tool ? tool.input : "该能力的上游输入。",
        tool ? tool.output : "该能力的下游输出。",
        "生产能力必须能说清输入、输出和验收方式，否则只是口号。",
      ),
    ],
    knowledgePoints: [
      knowledgePoint(entry.title, entry.overview, "牛客/知识点追问通常不会只问定义，会继续问：什么时候必须做、怎么验证、失败了怎么排查。"),
    ],
  };
}

function mergeDocEnhancement(target, source) {
  ["realCases", "choices", "ioExamples", "knowledgePoints"].forEach((key) => {
    if (Array.isArray(source[key])) target[key].push(...source[key]);
  });
}

function getDocEnhancements(entry) {
  const result = { realCases: [], choices: [], ioExamples: [], knowledgePoints: [] };
  docsEnhancementRules.forEach((rule) => {
    if (matchesEntry(entry, rule.patterns)) mergeDocEnhancement(result, rule);
  });
  mergeDocEnhancement(result, createProductionEnhancement(entry));
  mergeDocEnhancement(result, entry);
  return result;
}

let selectedDocId = window.location.hash ? window.location.hash.slice(1) : "project-start-goal";

const docsNav = document.querySelector("#docsNav");
const docsContent = document.querySelector("#docsContent");

function allSections() {
  return docChapters.flatMap((chapter) => chapter.sections.map((section) => ({ ...section, chapter })));
}

function getSelectedEntry() {
  return allSections().find((entry) => entry.id === selectedDocId) || allSections()[0];
}


const chapterStages = {
  "project-start": "目标与调研",
  knowledge: "数据建设",
  rag: "检索问答",
  "rule-answer": "规则推理",
  observability: "质量闭环",
  "production-topics": "生产能力",
  deployment: "上线运维",
};

function getChapterStage(chapter) {
  return chapterStages[chapter.id] || "学习章节";
}

function getShortSectionTitle(section) {
  const title = section.title || "";
  if (!title.includes("：")) return title;
  return title.split("：").slice(1).join("：").trim();
}

function renderListSection(titleText, values, className = "docs-section") {
  if (!Array.isArray(values) || values.length === 0) return null;
  const section = document.createElement("section");
  section.className = className;
  const title = document.createElement("h2");
  title.textContent = titleText;
  const list = document.createElement("ul");
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  });
  section.append(title, list);
  return section;
}

function renderToolDocs(toolDocs) {
  if (!Array.isArray(toolDocs) || toolDocs.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section tool-docs";
  const title = document.createElement("h2");
  title.textContent = "框架 / 工具 / 函数白话说明";
  const grid = document.createElement("div");
  grid.className = "tool-doc-grid";
  toolDocs.forEach((tool) => {
    const card = document.createElement("article");
    card.className = "tool-card";
    const heading = document.createElement("h3");
    heading.textContent = tool.name;
    const plain = document.createElement("p");
    plain.className = "tool-plain";
    plain.textContent = tool.plain;
    card.append(heading, plain);
    [
      ["输入", tool.input],
      ["输出", tool.output],
      ["作用", tool.role],
      ["边界", tool.boundary],
    ].forEach(([label, value]) => {
      const row = document.createElement("p");
      row.className = "tool-row";
      const strong = document.createElement("strong");
      strong.textContent = `${label}：`;
      row.append(strong, document.createTextNode(value));
      card.appendChild(row);
    });
    grid.appendChild(card);
  });
  section.append(title, grid);
  return section;
}

function renderPitfallGroups(groups) {
  if (!Array.isArray(groups) || groups.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section pitfall-docs";
  const title = document.createElement("h2");
  title.textContent = "问题和坑点分组";
  const grid = document.createElement("div");
  grid.className = "pitfall-grid";
  groups.forEach((group) => {
    const article = document.createElement("article");
    article.className = "pitfall-card";
    const heading = document.createElement("h3");
    heading.textContent = group.title;
    const list = document.createElement("ul");
    group.items.forEach((value) => {
      const item = document.createElement("li");
      item.textContent = value;
      list.appendChild(item);
    });
    article.append(heading, list);
    grid.appendChild(article);
  });
  section.append(title, grid);
  return section;
}

function renderValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function appendTextRow(parent, label, value) {
  if (!value) return;
  const row = document.createElement("p");
  row.className = "doc-detail-row";
  const strong = document.createElement("strong");
  strong.textContent = `${label}：`;
  row.append(strong, document.createTextNode(renderValue(value)));
  parent.appendChild(row);
}

function renderRealCases(cases) {
  if (!Array.isArray(cases) || cases.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section case-docs";
  const title = document.createElement("h2");
  title.textContent = "真实排查案例";
  const grid = document.createElement("div");
  grid.className = "case-grid";
  cases.forEach((item) => {
    const card = document.createElement("article");
    card.className = "case-card";
    const heading = document.createElement("h3");
    heading.textContent = item.title;
    card.appendChild(heading);
    appendTextRow(card, "用户问题 / 触发场景", item.userInput);
    appendTextRow(card, "当时现象", item.observed);
    appendTextRow(card, "根因", item.rootCause);
    appendTextRow(card, "处理方式", item.fix);
    appendTextRow(card, "处理结果", item.result);
    grid.appendChild(card);
  });
  section.append(title, grid);
  return section;
}

function renderChoiceDocs(choices) {
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section choice-docs";
  const title = document.createElement("h2");
  title.textContent = "选型对比：为什么选它";
  const grid = document.createElement("div");
  grid.className = "choice-grid";
  choices.forEach((item) => {
    const card = document.createElement("article");
    card.className = "choice-card";
    const heading = document.createElement("h3");
    heading.textContent = item.name;
    card.appendChild(heading);
    appendTextRow(card, "当前选择", item.selected);
    appendTextRow(card, "为什么选", item.why);
    if (Array.isArray(item.alternatives) && item.alternatives.length > 0) {
      const altTitle = document.createElement("p");
      altTitle.className = "choice-alt-title";
      altTitle.textContent = "其他选择";
      const list = document.createElement("ul");
      item.alternatives.forEach((value) => {
        const li = document.createElement("li");
        li.textContent = value;
        list.appendChild(li);
      });
      card.append(altTitle, list);
    }
    appendTextRow(card, "边界", item.boundary);
    grid.appendChild(card);
  });
  section.append(title, grid);
  return section;
}

function renderIoExamples(examples) {
  if (!Array.isArray(examples) || examples.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section io-docs";
  const title = document.createElement("h2");
  title.textContent = "真实输入输出";
  const grid = document.createElement("div");
  grid.className = "io-grid";
  examples.forEach((item) => {
    const card = document.createElement("article");
    card.className = "io-card";
    const heading = document.createElement("h3");
    heading.textContent = item.title;
    const inputLabel = document.createElement("strong");
    inputLabel.textContent = "输入";
    const input = document.createElement("pre");
    input.className = "io-block";
    input.textContent = renderValue(item.input);
    const outputLabel = document.createElement("strong");
    outputLabel.textContent = "输出";
    const output = document.createElement("pre");
    output.className = "io-block";
    output.textContent = renderValue(item.output);
    card.append(heading, inputLabel, input, outputLabel, output);
    appendTextRow(card, "说明", item.note);
    grid.appendChild(card);
  });
  section.append(title, grid);
  return section;
}

function renderKnowledgePoints(points) {
  if (!Array.isArray(points) || points.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section knowledge-docs";
  const title = document.createElement("h2");
  title.textContent = "对应知识点 / 知识点追问";
  const grid = document.createElement("div");
  grid.className = "knowledge-grid";
  points.forEach((item) => {
    const card = document.createElement("article");
    card.className = "knowledge-card";
    const heading = document.createElement("h3");
    heading.textContent = item.term;
    card.appendChild(heading);
    appendTextRow(card, "白话解释", item.plain);
    appendTextRow(card, "常见追问", item.knowledgeFocus);
    grid.appendChild(card);
  });
  section.append(title, grid);
  return section;
}

function renderTerms(terms) {
  if (!Array.isArray(terms) || terms.length === 0) return null;
  const section = document.createElement("section");
  section.className = "docs-section docs-terms";
  const title = document.createElement("h2");
  title.textContent = "关键名词";
  const list = document.createElement("dl");
  terms.forEach((item) => {
    const term = document.createElement("dt");
    term.textContent = item.term;
    const definition = document.createElement("dd");
    definition.textContent = item.definition;
    list.append(term, definition);
  });
  section.append(title, list);
  return section;
}

function renderStudyPrompts(prompts) {
  return renderListSection("可以继续思考的问题", prompts, "docs-section study-prompts");
}

function renderDocsNav() {
  docsNav.innerHTML = "";
  const selectedEntry = getSelectedEntry();
  docChapters.forEach((chapter, chapterIndex) => {
    const isCurrentChapter = chapter.id === selectedEntry.chapter.id;
    const group = document.createElement("details");
    group.className = `docs-nav-group${isCurrentChapter ? " active" : ""}`;
    group.open = isCurrentChapter;

    const heading = document.createElement("summary");
    heading.className = "docs-nav-heading";
    const chapterNumber = document.createElement("span");
    chapterNumber.className = "docs-nav-chapter-index";
    chapterNumber.textContent = `第 ${chapterIndex + 1} 章`;
    const copy = document.createElement("span");
    copy.className = "docs-nav-heading-copy";
    const title = document.createElement("strong");
    title.textContent = chapter.title;
    const description = document.createElement("small");
    description.textContent = `${getChapterStage(chapter)} · ${chapter.sections.length} 节`;
    copy.append(title, description);
    heading.append(chapterNumber, copy);
    group.appendChild(heading);

    const list = document.createElement("div");
    list.className = "docs-nav-list";
    chapter.sections.forEach((section, sectionIndex) => {
      const link = document.createElement("a");
      link.href = `#${section.id}`;
      link.className = `docs-nav-item${section.id === selectedDocId ? " active" : ""}`;
      if (section.id === selectedDocId) link.setAttribute("aria-current", "page");
      const number = document.createElement("span");
      number.className = "docs-nav-section-index";
      number.textContent = `${chapterIndex + 1}.${sectionIndex + 1}`;
      const text = document.createElement("span");
      text.className = "docs-nav-section-title";
      text.textContent = getShortSectionTitle(section);
      link.append(number, text);
      list.appendChild(link);
    });
    group.appendChild(list);
    docsNav.appendChild(group);
  });
}

function renderDocsContent() {
  const entry = getSelectedEntry();
  docsContent.innerHTML = "";
  document.title = `${entry.title} - ChatLearning Docs`;

  const hero = document.createElement("header");
  hero.className = "docs-hero";
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = entry.chapter.title;
  const title = document.createElement("h1");
  title.textContent = entry.title;
  const subtitle = document.createElement("p");
  subtitle.className = "doc-subtitle";
  subtitle.textContent = entry.subtitle || entry.chapter.description;
  const summary = document.createElement("p");
  summary.className = "hero-summary";
  summary.textContent = entry.overview;
  hero.append(eyebrow, title, subtitle, summary);
  docsContent.appendChild(hero);

  [
    ["这一阶段做了什么", entry.work, "docs-section docs-work"],
    ["怎么调研", entry.research, "docs-section docs-research"],
    ["怎么选型 / 为什么这样做", entry.decisions, "docs-section docs-choices"],
  ].forEach(([titleText, values, className]) => {
    const section = renderListSection(titleText, values, className);
    if (section) docsContent.appendChild(section);
  });

  const enhancements = getDocEnhancements(entry);

  [
    renderToolDocs(entry.toolDocs),
    renderChoiceDocs(enhancements.choices),
    renderRealCases(enhancements.realCases),
    renderIoExamples(enhancements.ioExamples),
    renderKnowledgePoints(enhancements.knowledgePoints),
    renderPitfallGroups(entry.pitfallGroups),
    renderTerms(entry.terms),
    renderStudyPrompts(entry.studyPrompts),
  ].forEach((section) => {
    if (section) docsContent.appendChild(section);
  });

  const pager = document.createElement("nav");
  pager.className = "docs-pager";
  const entries = allSections();
  const currentIndex = entries.findIndex((item) => item.id === entry.id);
  const prev = entries[currentIndex - 1];
  const next = entries[currentIndex + 1];
  if (prev) {
    const prevLink = document.createElement("a");
    prevLink.href = `#${prev.id}`;
    prevLink.textContent = `上一节：${prev.title}`;
    pager.appendChild(prevLink);
  }
  if (next) {
    const nextLink = document.createElement("a");
    nextLink.href = `#${next.id}`;
    nextLink.textContent = `下一节：${next.title}`;
    pager.appendChild(nextLink);
  }
  docsContent.appendChild(pager);
}

function renderDocsPage() {
  if (!allSections().some((item) => item.id === selectedDocId)) selectedDocId = allSections()[0].id;
  renderDocsNav();
  renderDocsContent();
}

window.addEventListener("hashchange", () => {
  selectedDocId = window.location.hash ? window.location.hash.slice(1) : allSections()[0].id;
  renderDocsPage();
});

renderDocsPage();
