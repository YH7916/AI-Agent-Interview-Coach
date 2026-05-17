import { escapeHtml } from "./markdown.js";

export function renderProviderStatus(status) {
  const summary = document.querySelector("#settings-summary");
  const details = document.querySelector("#provider-status-details");
  const button = document.querySelector("#settings-button");
  if (!summary || !details || !button) {
    return;
  }

  if (!status) {
    summary.textContent = "状态不可用";
    details.innerHTML = `<p>状态暂时不可用。</p>`;
    return;
  }

  const embeddingMode = status.embedding?.mode || "fallback";
  const chatMode = status.chat?.mode || "fallback";
  const isAllReal = embeddingMode === "real" && chatMode === "real";
  button.title = isAllReal ? "模型服务已连接" : "部分能力使用本地模式";
  summary.textContent = isAllReal ? "模型服务已连接" : "部分本地模式";
  details.innerHTML = `
    ${renderProviderRow("向量检索", status.embedding, "SiliconFlow Embedding")}
    ${renderProviderRow("对话模型", status.chat, "OpenAI Chat Completions")}
    ${renderCacheRow(status.cache || {})}
  `;
}

function renderProviderRow(label, item, realLabel) {
  const mode = item?.mode || "fallback";
  const isReal = mode === "real";
  const model = item?.model ? `<small>${escapeHtml(item.model)}</small>` : "";
  return `
    <article class="provider-row">
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(isReal ? realLabel : "本地兜底")}</span>
        ${model}
      </div>
      <mark class="${isReal ? "is-real" : ""}">${isReal ? "已连接" : "本地"}</mark>
    </article>
  `;
}

function renderCacheRow(cache) {
  if (!cache.enabled) {
    return `
      <article class="provider-row">
        <div>
          <strong>向量缓存</strong>
          <span>当前未启用</span>
        </div>
        <mark>关闭</mark>
      </article>
    `;
  }
  return `
    <article class="provider-row">
      <div>
        <strong>向量缓存</strong>
        <span>${escapeHtml(cache.entries || 0)} 条向量，命中 ${escapeHtml(cache.hits || 0)} 次</span>
      </div>
      <mark class="is-real">开启</mark>
    </article>
  `;
}
