import {
  fetchInterviewSourcePlatforms,
  forgetInterviewSourcePlatform,
  openInterviewSourcePlatformLogin,
} from "./api.js";
import { escapeHtml } from "./markdown.js";

let sourcePlatforms = [];
let sourcePlatformsLoaded = false;
let sourcePlatformStatus = "正在读取平台登录态...";
let sourcePlatformStatusKind = "muted";
let sourcePlatformPollTimer = 0;

export function setupSourcePlatformControls() {
  const list = document.querySelector("[data-source-platforms]");
  if (!list) {
    return;
  }
  list.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const loginButton = event.target.closest("[data-source-platform-login]");
    if (loginButton) {
      void openSourcePlatformLogin(loginButton.dataset.sourcePlatformLogin || "", loginButton);
      return;
    }
    const disconnectButton = event.target.closest("[data-source-platform-disconnect]");
    if (!disconnectButton) {
      return;
    }
    void disconnectSourcePlatform(
      disconnectButton.dataset.sourcePlatformDisconnect || "",
      disconnectButton,
    );
  });
}

export async function refreshSourcePlatforms(options = {}) {
  if (sourcePlatformsLoaded && !options.force) {
    renderSourcePlatforms();
    return;
  }
  sourcePlatformsLoaded = true;
  try {
    const payload = await fetchInterviewSourcePlatforms();
    sourcePlatforms = payload.platforms || [];
    setSourcePlatformStatus("这里只管理登录态；采集和讲题从面试页输入框发起。");
  } catch (error) {
    sourcePlatformsLoaded = false;
    setSourcePlatformStatus(error.message || "读取平台登录态失败", "error");
  }
  renderSourcePlatforms();
  scheduleSourcePlatformRefresh();
}

export function renderSourcePlatformStatus() {
  const status = document.querySelector("[data-source-platform-status]");
  if (status) {
    status.textContent = sourcePlatformStatus;
    status.classList.toggle("is-error", sourcePlatformStatusKind === "error");
  }
}

async function openSourcePlatformLogin(platformId, button) {
  if (!platformId) {
    return;
  }
  button.disabled = true;
  setSourcePlatformStatus("正在打开登录窗口...");
  try {
    const result = await openInterviewSourcePlatformLogin(platformId);
    if (result.opened) {
      setSourcePlatformStatus(`已打开 ${result.host} 登录窗口，登录后关闭窗口即可`);
    } else {
      setSourcePlatformStatus(result.error || result.message || "当前未启用浏览器连接器", "error");
    }
    await refreshSourcePlatforms({ force: true });
  } catch (error) {
    setSourcePlatformStatus(error.message || "打开登录窗口失败", "error");
  } finally {
    button.disabled = false;
  }
}

async function disconnectSourcePlatform(platformId, button) {
  if (!platformId) {
    return;
  }
  button.disabled = true;
  setSourcePlatformStatus("正在断开登录态...");
  try {
    await forgetInterviewSourcePlatform(platformId);
    setSourcePlatformStatus("已断开平台登录态");
    await refreshSourcePlatforms({ force: true });
  } catch (error) {
    setSourcePlatformStatus(error.message || "断开失败", "error");
  } finally {
    button.disabled = false;
  }
}

function setSourcePlatformStatus(message, kind = "muted") {
  sourcePlatformStatus = message;
  sourcePlatformStatusKind = kind;
  renderSourcePlatformStatus();
}

function renderSourcePlatforms() {
  const list = document.querySelector("[data-source-platforms]");
  if (!list) {
    return;
  }
  if (!sourcePlatforms.length) {
    list.innerHTML = `<article class="product-empty">正在读取平台登录态...</article>`;
    return;
  }
  list.innerHTML = sourcePlatforms.map(renderSourcePlatformCard).join("");
}

function renderSourcePlatformCard(platform) {
  return `
    <article class="source-platform-card ${sourcePlatformCardClass(platform)}">
      <div class="source-platform-icon">
        <img src="${escapeHtml(platform.icon_path || "")}" alt="" aria-hidden="true">
      </div>
      <div class="source-platform-main">
        <span>${escapeHtml(platform.host)}</span>
        <strong>${escapeHtml(platform.label)}</strong>
        <small>${escapeHtml(platform.sync_status || "")}</small>
      </div>
      <div class="source-platform-state">
        <mark>${escapeHtml(platform.status || "")}</mark>
        ${platform.last_used_at ? `<small>最近授权 ${escapeHtml(platform.last_used_at)}</small>` : ""}
      </div>
      <div class="source-platform-actions">
        <button
          type="button"
          class="interview-action-button"
          data-source-platform-login="${escapeHtml(platform.id)}"
        >
          ${platform.connected ? "重新登录" : "打开登录"}
        </button>
        <button
          type="button"
          class="interview-action-button"
          data-source-platform-disconnect="${escapeHtml(platform.id)}"
          ${platform.connected ? "" : "disabled"}
        >
          断开
        </button>
      </div>
    </article>
  `;
}

function sourcePlatformCardClass(platform) {
  const classes = [];
  if (platform.connected) {
    classes.push("is-connected");
  }
  if (platform.status === "待确认") {
    classes.push("is-working");
  }
  if (platform.status === "需重新登录") {
    classes.push("is-needs-login");
  }
  return classes.join(" ");
}

function scheduleSourcePlatformRefresh() {
  window.clearTimeout(sourcePlatformPollTimer);
  const hasPendingLogin = sourcePlatforms.some((platform) => platform.status === "待确认");
  if (!hasPendingLogin || !document.querySelector("[data-source-platforms]")) {
    return;
  }
  sourcePlatformPollTimer = window.setTimeout(() => {
    sourcePlatformsLoaded = false;
    void refreshSourcePlatforms({ force: true });
  }, 2000);
}
