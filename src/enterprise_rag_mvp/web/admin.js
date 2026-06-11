const knowledgeBaseList = document.getElementById("knowledgeBaseList");
const interfaceStatusList = document.getElementById("interfaceStatusList");
const integrationStatusList = document.getElementById("integrationStatusList");
const documentPreviewForm = document.getElementById("documentPreviewForm");
const previewResults = document.getElementById("previewResults");

function renderList(target, rows, renderItem) {
  target.innerHTML = "";
  if (!rows.length) {
    target.textContent = "暂无数据";
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("div");
    item.className = "status-item";
    item.innerHTML = renderItem(row);
    target.appendChild(item);
  });
}

function statusBadge(status) {
  const safeStatus = escapeHtml(status || "unknown");
  const safeClass = String(status || "unknown").toLowerCase().replace(/[^a-z0-9_-]/g, "-");
  return `<span class="status-badge status-${safeClass}">${safeStatus}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderCountMap(counts) {
  const entries = Object.entries(counts || {});
  if (!entries.length) return "无";
  return entries.map(([key, value]) => `${escapeHtml(key)}: ${escapeHtml(value)}`).join(" / ");
}

function renderElementRange(range) {
  if (!range) return "";
  return `${escapeHtml(range.start ?? "?")}-${escapeHtml(range.end ?? "?")}`;
}

async function loadManagementOverview() {
  try {
    const response = await fetch("/api/admin/overview");
    if (!response.ok) throw new Error(`overview ${response.status}`);
    const data = await response.json();
    renderList(knowledgeBaseList, data.knowledge_bases || [], (item) => `
      <strong>${item.name}</strong>
      ${statusBadge(item.status)}
      <p>${item.description}</p>
      <small>${item.id} / ${item.source}</small>
    `);
    renderList(interfaceStatusList, Object.values(data.interfaces || {}), (item) => `
      <strong>${item.method} ${item.path}</strong>
      ${statusBadge(item.status)}
      <p>${item.purpose}</p>
    `);
    renderList(integrationStatusList, Object.values(data.integrations || {}), (item) => `
      <strong>${item.label}</strong>
      ${statusBadge(item.status)}
      <p>${item.detail}</p>
    `);
  } catch (error) {
    knowledgeBaseList.textContent = "管理概览加载失败";
    interfaceStatusList.textContent = "管理概览加载失败";
    integrationStatusList.textContent = String(error.message || error);
  }
}

function renderPreview(data) {
  const elements = (data.elements || []).map((item) => `
    <li>
      <strong>${escapeHtml(item.element_type)}</strong>
      <span>${escapeHtml((item.heading_path || []).join(" > "))}</span>
      <p>${escapeHtml(item.text)}</p>
    </li>
  `).join("");
  const chunkingQuality = data.chunking_quality || {};
  const uncoveredRanges = (chunkingQuality.uncovered_ranges || []).map((item) => `
    <li>${escapeHtml(item.preview || `${item.start}-${item.end}`)}</li>
  `).join("");
  const uncoveredElements = (chunkingQuality.uncovered_elements || []).map((item) => `
    <li>#${escapeHtml(item.index ?? item.element_id)} ${escapeHtml(item.preview || "")}</li>
  `).join("");
  const chunks = (data.chunks || []).map((item) => `
    <li class="chunk-preview-item">
      <header>
        <strong>#${escapeHtml(item.index)}</strong>
        <span class="chunk-chip">${escapeHtml(item.metadata?.chunk_type || "chunk")}</span>
        ${item.metadata?.semantic_type ? `<span class="chunk-chip">${escapeHtml(item.metadata.semantic_type)}</span>` : ""}
        ${item.metadata?.chunk_role ? `<span class="chunk-chip">${escapeHtml(item.metadata.chunk_role)}</span>` : ""}
        ${item.metadata?.language ? `<span class="chunk-chip">${escapeHtml(item.metadata.language)}</span>` : ""}
        ${item.metadata?.clause_range ? `<span class="chunk-chip">${escapeHtml(item.metadata.clause_range)}</span>` : ""}
      </header>
      <div class="chunk-meta">路径：${escapeHtml((item.heading_path || []).join(" > ") || "未识别")}</div>
      ${item.metadata?.element_range ? `<div class="chunk-meta">元素范围：${renderElementRange(item.metadata.element_range)}</div>` : ""}
      ${item.metadata?.fallback_reason ? `<div class="chunk-meta">兜底原因：${escapeHtml(item.metadata.fallback_reason)}</div>` : ""}
      <p>${escapeHtml(item.text)}</p>
    </li>
  `).join("");
  previewResults.innerHTML = `
    <section>
      <h3>解析质量</h3>
      <dl>
        <dt>类型</dt><dd>${data.source_type}</dd>
        <dt>状态</dt><dd>${data.quality.status}</dd>
        <dt>解析器</dt><dd>${data.quality.parser_name}</dd>
        <dt>元素数</dt><dd>${data.element_count}</dd>
        <dt>Chunk 数</dt><dd>${data.chunk_count}</dd>
      </dl>
    </section>
    <section>
      <h3>切块质量</h3>
      <dl>
        <dt>状态</dt><dd>${escapeHtml(chunkingQuality.status || "unknown")}</dd>
        <dt>策略</dt><dd>${escapeHtml(chunkingQuality.chunking_strategy || "unknown")}</dd>
        <dt>切块器</dt><dd>${escapeHtml(chunkingQuality.chunker_name || "unknown")}</dd>
        <dt>边界置信</dt><dd>${escapeHtml(chunkingQuality.boundary_confidence || "未评估")}</dd>
        <dt>覆盖状态</dt><dd>${escapeHtml(chunkingQuality.coverage_status || "unknown")}</dd>
        <dt>覆盖字符</dt><dd>${escapeHtml(chunkingQuality.covered_char_count ?? 0)} / ${escapeHtml(chunkingQuality.source_char_count ?? 0)}</dd>
        <dt>元素覆盖</dt><dd>${escapeHtml(chunkingQuality.element_coverage_status || "unknown")}，${escapeHtml(chunkingQuality.covered_element_count ?? 0)} / ${escapeHtml(chunkingQuality.source_element_count ?? 0)}，未覆盖 ${escapeHtml(chunkingQuality.uncovered_element_count ?? 0)}</dd>
        <dt>元素覆盖率</dt><dd>${escapeHtml(chunkingQuality.element_coverage_ratio ?? 0)}</dd>
        <dt>溯源缺失</dt><dd>全部 ${escapeHtml(chunkingQuality.provenance_missing_count ?? 0)} / 检索 ${escapeHtml(chunkingQuality.retrieval_provenance_missing_count ?? 0)}</dd>
        <dt>检索块</dt><dd>${escapeHtml(chunkingQuality.retrieval_chunk_count ?? 0)}，英文检索块 ${escapeHtml(chunkingQuality.english_retrieval_chunk_count ?? 0)}</dd>
        <dt>覆盖块</dt><dd>${escapeHtml(chunkingQuality.coverage_chunk_count ?? 0)}</dd>
        <dt>结构问题</dt><dd>孤立标题 ${escapeHtml(chunkingQuality.orphan_title_count ?? 0)} / 混合语言 ${escapeHtml(chunkingQuality.mixed_language_chunk_count ?? 0)}</dd>
        <dt>预览数量</dt><dd>${escapeHtml(data.chunk_preview_count ?? 0)} / ${escapeHtml(data.chunk_count ?? 0)}，上限 ${escapeHtml(data.chunk_preview_limit ?? 0)}</dd>
        <dt>Chunk 类型</dt><dd>${renderCountMap(data.chunk_type_counts)}</dd>
        <dt>语言分布</dt><dd>${renderCountMap(data.chunk_language_counts)}</dd>
        <dt>角色分布</dt><dd>${renderCountMap(data.chunk_role_counts)}</dd>
        <dt>兜底原因</dt><dd>${escapeHtml(chunkingQuality.fallback_reason || "无")}</dd>
      </dl>
      ${uncoveredRanges ? `<h4>未覆盖片段</h4><ol>${uncoveredRanges}</ol>` : ""}
      ${uncoveredElements ? `<h4>未覆盖元素</h4><ol>${uncoveredElements}</ol>` : ""}
    </section>
    <section>
      <h3>元素</h3>
      <ol>${elements || "<li>无元素</li>"}</ol>
    </section>
    <section>
      <h3>Chunks</h3>
      <ol>${chunks || "<li>无 chunk</li>"}</ol>
    </section>
  `;
}

async function submitDocumentPreview(event) {
  event.preventDefault();
  previewResults.textContent = "解析中...";
  const payload = {
    source_name: document.getElementById("sourceNameInput").value,
    file_name: document.getElementById("fileNameInput").value,
    content_type: document.getElementById("contentTypeInput").value,
    text: document.getElementById("documentTextInput").value,
    max_chars: Number(document.getElementById("maxCharsInput").value),
    overlap_chars: Number(document.getElementById("overlapCharsInput").value),
  };
  try {
    const response = await fetch("/api/admin/document-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(data));
    renderPreview(data);
  } catch (error) {
    previewResults.textContent = `解析失败：${error.message || error}`;
  }
}

documentPreviewForm.addEventListener("submit", submitDocumentPreview);
loadManagementOverview();
