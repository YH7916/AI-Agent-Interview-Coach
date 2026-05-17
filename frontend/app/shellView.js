import { MAX_HISTORY_ENTRIES } from "./config.js";
import { escapeHtml } from "./markdown.js";

export function renderWorkspaceShell({
  activeHistoryId,
  content,
  historyEntries,
  userSettings,
}) {
  return `
    <div class="workspace-shell ${userSettings.historyOpen ? "is-history-open" : ""} ${userSettings.settingsOpen ? "is-settings-open" : ""}">
      <div
        class="side-panel-backdrop"
        ${userSettings.historyOpen || userSettings.settingsOpen ? "" : "hidden"}
        data-panel-dismiss
      ></div>
      <aside
        id="history-sidebar"
        class="side-panel history-sidebar"
        aria-label="聊天记录"
        aria-hidden="${userSettings.historyOpen ? "false" : "true"}"
        ${userSettings.historyOpen ? "" : "inert"}
      >
        ${renderHistorySidebar(historyEntries, activeHistoryId)}
      </aside>
      <aside
        id="settings-sidebar"
        class="side-panel settings-sidebar"
        aria-label="运行设置"
        aria-hidden="${userSettings.settingsOpen ? "false" : "true"}"
        ${userSettings.settingsOpen ? "" : "inert"}
      >
        ${renderSettingsSidebar(userSettings)}
      </aside>
      <div class="workspace-main">
        ${content}
      </div>
    </div>
  `;
}

export function renderHistorySidebar(historyEntries, activeHistoryId) {
  const entries = historyEntries.slice(0, MAX_HISTORY_ENTRIES);
  const emptyState = `
    <p class="history-empty">还没有记录。搜索或提问后会自动出现在这里。</p>
  `;

  return `
    <div class="history-sidebar-header">
      <span>聊天记录</span>
    </div>
    <div class="history-list">
      ${
        entries.length
          ? entries.map((entry, index) => renderHistoryEntry(entry, index, activeHistoryId)).join("")
          : emptyState
      }
    </div>
  `;
}

export function renderHomeShell(config) {
  return `
    <section class="home">
      <p class="kicker">${escapeHtml(config.kicker)}</p>
      <h1>${escapeHtml(config.title)}</h1>
      <p class="subtitle">${escapeHtml(config.subtitle)}</p>
      ${config.kind === "interview" ? renderInterviewControls() : ""}
      <form id="query-form" class="query-box">
        <textarea name="q" rows="1" placeholder="${escapeHtml(config.placeholder)}" autofocus></textarea>
        <button class="send-button" type="submit" aria-label="Submit query">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 19V5"></path>
            <path d="m5 12 7-7 7 7"></path>
          </svg>
        </button>
      </form>
    </section>
    <section id="results" class="results" aria-label="${escapeHtml(config.resultTitle)}"></section>
  `;
}

export function renderChatShell(config) {
  return `
    <section class="chat-screen ${config.kind === "interview" ? "chat-screen-interview" : ""}">
      ${config.kind === "interview" ? renderInterviewControls("is-compact") : ""}
      <section id="results" class="results chat-results" aria-label="${escapeHtml(config.resultTitle)}"></section>
      <form id="query-form" class="query-box chat-composer">
        <textarea name="q" rows="1" placeholder="${escapeHtml(config.placeholder)}" autofocus></textarea>
        <button class="send-button" type="submit" aria-label="Submit query">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 19V5"></path>
            <path d="m5 12 7-7 7 7"></path>
          </svg>
        </button>
      </form>
    </section>
  `;
}

export function renderQuestionBankShell() {
  return `
    <section class="product-page question-bank-page result-enter">
      <div class="product-page-header">
        <p class="kicker">Question Bank</p>
        <h1>题库</h1>
        <div class="product-page-actions">
          <button type="button" class="interview-action-button" data-question-bank-refresh>刷新</button>
        </div>
      </div>
      <div class="product-metrics" data-question-bank-stats></div>
      <div class="product-status" data-question-bank-status>正在读取题库...</div>
      <section class="question-bank-list" data-question-bank-list aria-label="题库列表"></section>
    </section>
  `;
}

export function renderSourcesShell() {
  return `
    <section class="product-page sources-page result-enter">
      <div class="product-page-header">
        <p class="kicker">Sources</p>
        <h1>来源</h1>
      </div>
      <p class="product-subtitle">只管理简历和站点登录态。采集、讲题和面试都从面试页输入框发起。</p>
      <section class="resume-source-card" aria-label="简历来源">
        <div class="source-platform-icon">
          <img src="/static/assets/file-text.svg" alt="" aria-hidden="true">
        </div>
        <div class="source-platform-main">
          <span>resume</span>
          <strong>简历</strong>
          <small data-resume-source-status>正在读取简历状态...</small>
        </div>
        <div class="source-platform-state">
          <mark data-resume-source-badge>未导入</mark>
          <small data-resume-source-meta></small>
        </div>
        <div class="source-platform-actions">
          <input type="file" accept=".pdf,.txt,.md" data-resume-source-file hidden>
          <button type="button" class="interview-action-button" data-resume-source-import-default>
            导入默认简历
          </button>
          <button type="button" class="interview-action-button" data-resume-source-upload>
            上传
          </button>
        </div>
      </section>
      <div class="product-status" data-source-platform-status>正在读取平台登录态...</div>
      <section class="source-platform-list" data-source-platforms aria-label="来源平台登录态"></section>
    </section>
  `;
}

export function renderReviewShell(review) {
  return `
    <section class="product-page review-page result-enter">
      <div class="product-page-header">
        <p class="kicker">Review</p>
        <h1>复盘</h1>
      </div>
      <div class="product-metrics">
        <article class="metric-tile">
          <span>完成题目</span>
          <strong>${escapeHtml(String(review.completed))}</strong>
        </article>
        <article class="metric-tile">
          <span>AI 评价</span>
          <strong>${escapeHtml(String(review.aiEvaluations || 0))}</strong>
        </article>
        <article class="metric-tile">
          <span>追问轮次</span>
          <strong>${escapeHtml(String(review.followUps || 0))}</strong>
        </article>
      </div>
      <section class="review-list" aria-label="最近复盘">
        ${
          review.items.length
            ? review.items.map((item) => renderReviewItem(item)).join("")
            : `<article class="product-empty">完成一轮模拟面试后，这里会显示 AI 面试官评价、追问和下一步建议。</article>`
        }
      </section>
    </section>
  `;
}

function renderInterviewControls(modifier = "") {
  return `
    <div class="interview-controls ${modifier}">
      <div id="interview-question-panel" class="interview-question-panel">
        <div class="interview-question-main">
          <span class="interview-question-topic" data-interview-progress>Agent</span>
          <strong>可以直接对话</strong>
          <small>输入“开始面试”才进入模拟面试；采集、讲题也可以用自然语言发起。</small>
        </div>
      </div>
      <div class="interview-actions">
        <button type="button" class="interview-action-button" data-interview-start hidden>重新开始</button>
        <button type="button" class="interview-action-button" data-interview-next disabled>跳过本题</button>
        <button type="button" class="interview-action-button" data-interview-end disabled>结束</button>
      </div>
    </div>
  `;
}

export function renderSettingsSidebar(userSettings) {
  return `
    <div class="side-panel-header">
      <span>运行状态</span>
      <small id="settings-summary">正在检查</small>
    </div>
    <div id="provider-status-details" class="provider-status-details">
      <p>正在加载运行状态...</p>
    </div>
    <form id="provider-config-form" class="provider-config-form">
      <label>
        <span>Base URL</span>
        <input name="base_url" type="url" placeholder="http://127.0.0.1:8080/v1">
      </label>
      <label>
        <span>Model</span>
        <input name="model" type="text" placeholder="gpt-5.4">
      </label>
      <label>
        <span>API Key</span>
        <input name="api_key" type="password" autocomplete="off" placeholder="留空不修改">
      </label>
      <button type="submit">保存并重连</button>
      <small id="provider-config-message"></small>
    </form>
    <div class="settings-group">
      <span>界面</span>
      <label>
        <input id="setting-show-trace" type="checkbox" ${userSettings.showTrace ? "checked" : ""}>
        显示工具调用过程
      </label>
      <label>
        <input id="setting-section-jump" type="checkbox" ${userSettings.sectionJump ? "checked" : ""}>
        打开引用时定位章节
      </label>
    </div>
  `;
}

function renderHistoryEntry(entry, index, activeHistoryId) {
  const isCurrent = entry.id === activeHistoryId;
  return `
    <article class="history-entry ${isCurrent ? "is-current" : ""}" style="--i: ${index}">
      <button
        type="button"
        class="history-entry-load"
        data-history-id="${escapeHtml(entry.id)}"
      >
        <span class="history-mode-tag">${escapeHtml(entry.mode)}</span>
        <span class="history-entry-title">${escapeHtml(entry.title)}</span>
      </button>
      <button
        type="button"
        class="history-delete-button"
        data-history-delete-id="${escapeHtml(entry.id)}"
        aria-label="删除 ${escapeHtml(entry.title)}"
      >
        <img src="/static/assets/trash-2.svg" alt="" aria-hidden="true">
      </button>
    </article>
  `;
}

function renderReviewItem(item) {
  const attemptLabel = Number(item.attempts || 1) > 1 ? ` · ${item.attempts} 轮追问` : "";
  const aiReview = item.aiReview || item.coaching || item.followUp || "本轮暂无 AI 评价。";
  return `
    <article class="review-item">
      <div>
        <span>${escapeHtml(item.question)}</span>
        <strong>AI 评价</strong>
      </div>
      <p>${escapeHtml(aiReview)}</p>
      ${item.followUp ? `<small>${escapeHtml(`追问：${item.followUp}`)}</small>` : ""}
      ${item.coaching || attemptLabel ? `<small>${escapeHtml(`${item.coaching || "已完成追问"}${attemptLabel}`)}</small>` : ""}
    </article>
  `;
}
