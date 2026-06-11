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
  return `<span class="status-badge status-${String(status).toLowerCase()}">${status}</span>`;
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
      <strong>${item.element_type}</strong>
      <span>${(item.heading_path || []).join(" > ")}</span>
      <p>${item.text}</p>
    </li>
  `).join("");
  const chunks = (data.chunks || []).map((item) => `
    <li><strong>#${item.index}</strong> ${item.text}</li>
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
