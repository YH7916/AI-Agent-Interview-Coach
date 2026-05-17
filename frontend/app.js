import {
  fetchInterviewReview,
  fetchInterviewQuestions,
  fetchInterviewSessionSummary,
  fetchInterviewSourcePlatformLatestJob,
  fetchInterviewSourcePlatforms,
  fetchProviderConfig,
  fetchProviderStatus,
  fetchSearchResults,
  saveProviderConfig,
  streamChat,
  streamInterviewAnswer,
  syncInterviewSourcePlatform,
} from "./app/api.js";
import {
  applyChatFailure,
  applyChatStreamEvent,
} from "./app/chatEvents.js";
import {
  renderAssistantBody,
  renderChatConversation as renderChatConversationMarkup,
} from "./app/chatView.js";
import {
  MAX_HISTORY_ENTRIES,
  MAX_CHAT_CONTEXT_TURNS,
  MODES,
  PRODUCT_PAGES,
  modeFromPath,
  productPageFromPath,
} from "./app/config.js";
import { setupEvidenceCarousel } from "./app/evidence.js";
import {
  askInterviewFollowUp,
  completeInterviewQuestion,
  endInterviewSession,
  getInterviewSessionState,
  hasActiveInterviewSession,
  ensureInterviewQuestion,
  refreshInterviewQuestionPanel,
  setupInterviewControls,
  setupQuestionBankPage,
  setupSourcesPage,
  skipInterviewQuestion,
  startInterviewSession,
} from "./app/interviewProduct.js";
import { createReviewModel } from "./app/interviewReview.js";
import { escapeHtml } from "./app/markdown.js";
import { renderProviderStatus } from "./app/providerStatus.js";
import { renderSearchResults } from "./app/searchResults.js";
import {
  renderChatShell,
  renderHistorySidebar,
  renderHomeShell,
  renderQuestionBankShell,
  renderReviewShell,
  renderSettingsSidebar,
  renderSourcesShell,
  renderWorkspaceShell,
} from "./app/shellView.js";
import { setupSopPreview } from "./app/sopPreview.js";
import {
  compactHistoryTitle,
  createHistoryId,
  loadHistoryEntries,
  loadUserSettings,
  saveHistoryEntries,
  saveUserSettings,
} from "./app/storage.js";

const app = document.querySelector("#app");
const COLLECTION_POLL_INTERVAL_MS = 1500;
const COLLECTION_POLL_ATTEMPTS = 180;
const GENERAL_AGENT_STREAM_ENDPOINT = "/interview/agent/stream";

let mode = modeFromPath(window.location.pathname);
let config = MODES[mode];
let productPage = productPageFromPath(window.location.pathname);
const chatTurns = [];
const userSettings = loadUserSettings();
let historyEntries = loadHistoryEntries();
let activeHistoryId = null;
let activeChatHistoryId = null;
let serverReview = null;
let serverReviewLoaded = false;
let serverReviewInFlight = false;
let pendingAssistantContentTurn = null;
let pendingAssistantContentFrame = 0;

function isActiveChat() {
  return isChatMode() && productPage === "interview" && chatTurns.length > 0;
}

function isChatMode() {
  return mode === "v3" || mode === "interview";
}

function isInterviewMode() {
  return config.kind === "interview";
}

function isInterviewPage() {
  return isInterviewMode() && productPage === "interview";
}

function hasPendingChatTurn() {
  return chatTurns.some((turn) => turn.role === "pending" || turn.streaming);
}

function recordSearchHistory(query) {
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    return;
  }
  const now = Date.now();
  const existing = historyEntries.find(
    (entry) => entry.mode === mode && entry.query === normalizedQuery && !entry.turns,
  );
  const entry = {
    id: existing?.id || createHistoryId(),
    mode,
    title: compactHistoryTitle(normalizedQuery),
    query: normalizedQuery,
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  };
  activeHistoryId = entry.id;
  historyEntries = [entry, ...historyEntries.filter((item) => item.id !== entry.id)].slice(
    0,
    MAX_HISTORY_ENTRIES,
  );
  saveHistoryEntries(historyEntries);
}

function serializeChatTurns() {
  return chatTurns
    .filter((turn) => ["interviewer", "user", "assistant", "error"].includes(turn.role))
    .map((turn) => ({
      role: turn.role,
      content: turn.content || "",
      question: turn.question || "",
      questionId: turn.questionId || "",
      progress: turn.progress || "",
      followUpQueued: turn.followUpQueued === true,
      reviewKey: turn.reviewKey || "",
      completed: turn.completed === true,
      evidence: turn.evidence || [],
      trace: turn.trace || [],
      toolCalls: turn.toolCalls || [],
      memoryHits: turn.memoryHits || [],
      grade: turn.grade || null,
      interviewAction: turn.interviewAction || "",
      focusAreas: turn.focusAreas || [],
      followUp: turn.followUp || "",
      coaching: turn.coaching || "",
      streaming: false,
    }));
}

function persistCurrentChatHistory() {
  const firstUserTurn = chatTurns.find((turn) => turn.role === "user" && turn.content);
  const firstInterviewQuestion = chatTurns.find(
    (turn) => turn.role === "interviewer" && turn.content,
  );
  const firstContentTurn = firstUserTurn || firstInterviewQuestion;
  if (!firstContentTurn) {
    return;
  }
  const now = Date.now();
  const existing = historyEntries.find((entry) => entry.id === activeChatHistoryId);
  const titleSource = firstUserTurn
    ? firstUserTurn.content
    : `模拟面试：${firstInterviewQuestion?.content || ""}`;
  const entryId = existing?.id || activeChatHistoryId || createHistoryId();
  const entry = {
    id: entryId,
    mode,
    title: compactHistoryTitle(titleSource),
    query: firstContentTurn.content,
    turns: serializeChatTurns(),
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  };
  activeChatHistoryId = entry.id;
  activeHistoryId = entry.id;
  historyEntries = [entry, ...historyEntries.filter((item) => item.id !== entry.id)].slice(
    0,
    MAX_HISTORY_ENTRIES,
  );
  saveHistoryEntries(historyEntries);
}

function restoreChatTurns(turns) {
  chatTurns.splice(
    0,
    chatTurns.length,
    ...(Array.isArray(turns) ? turns : [])
      .filter((turn) => ["interviewer", "user", "assistant", "error"].includes(turn?.role))
      .map((turn) => ({
        role: turn.role,
        content: turn.content || "",
        question: turn.question || "",
        questionId: turn.questionId || "",
        progress: turn.progress || "",
        followUpQueued: turn.followUpQueued === true,
        reviewKey: turn.reviewKey || "",
        completed: turn.completed === true,
        evidence: turn.evidence || [],
        trace: turn.trace || [],
        toolCalls: turn.toolCalls || [],
        memoryHits: turn.memoryHits || [],
        grade: turn.grade || null,
        interviewAction: turn.interviewAction || "",
        focusAreas: turn.focusAreas || [],
        followUp: turn.followUp || "",
        coaching: turn.coaching || "",
        streaming: false,
      })),
  );
}

async function refreshProviderStatus() {
  try {
    renderProviderStatus(await fetchProviderStatus());
  } catch (_error) {
    renderProviderStatus(null);
  }
}

async function refreshInterviewReview() {
  if (serverReviewInFlight) {
    return;
  }
  serverReviewInFlight = true;
  try {
    serverReview = await fetchInterviewReview();
  } catch (_error) {
    serverReview = null;
  } finally {
    serverReviewLoaded = true;
    serverReviewInFlight = false;
  }
  if (isInterviewMode() && productPage === "review") {
    renderShell();
  }
}

function invalidateServerReview() {
  serverReview = null;
  serverReviewLoaded = false;
}

function setActiveNav() {
  const switcher = document.querySelector(".version-switcher");
  if (switcher) {
    switcher.dataset.active = productPage;
  }
  document.querySelectorAll(".version-switcher a[data-product-page]").forEach((item) => {
    const isActive = item.dataset.productPage === productPage;
    item.classList.toggle("is-active", isActive);
    if (isActive) {
      item.setAttribute("aria-current", "page");
    } else {
      item.removeAttribute("aria-current");
    }
  });
}

function syncHistoryButtonState() {
  const button = document.querySelector("#history-button");
  if (!button) {
    return;
  }
  button.setAttribute("aria-expanded", String(userSettings.historyOpen));
  button.classList.toggle("is-active", userSettings.historyOpen);
}

function syncSettingsButtonState() {
  const button = document.querySelector("#settings-button");
  if (!button) {
    return;
  }
  button.setAttribute("aria-expanded", String(userSettings.settingsOpen));
  button.classList.toggle("is-active", userSettings.settingsOpen);
}

function syncPanelBackdropState() {
  const backdrop = document.querySelector(".side-panel-backdrop");
  if (backdrop) {
    backdrop.hidden = !(userSettings.historyOpen || userSettings.settingsOpen);
  }
}

function applyHistorySidebarState() {
  document.body.classList.toggle("history-open", userSettings.historyOpen);
  document.querySelector(".workspace-shell")?.classList.toggle(
    "is-history-open",
    userSettings.historyOpen,
  );
  syncPanelBackdropState();
  const sidebar = document.querySelector("#history-sidebar");
  if (sidebar) {
    sidebar.setAttribute("aria-hidden", String(!userSettings.historyOpen));
    if (userSettings.historyOpen) {
      sidebar.removeAttribute("inert");
      sidebar.innerHTML = renderHistorySidebar(historyEntries, activeHistoryId);
    } else {
      sidebar.setAttribute("inert", "");
    }
  }
  syncHistoryButtonState();
}

function applySettingsSidebarState() {
  document.body.classList.toggle("settings-open", userSettings.settingsOpen);
  document.querySelector(".workspace-shell")?.classList.toggle(
    "is-settings-open",
    userSettings.settingsOpen,
  );
  syncPanelBackdropState();
  const sidebar = document.querySelector("#settings-sidebar");
  if (sidebar) {
    sidebar.setAttribute("aria-hidden", String(!userSettings.settingsOpen));
    if (userSettings.settingsOpen) {
      sidebar.removeAttribute("inert");
      sidebar.innerHTML = renderSettingsSidebar(userSettings);
      bindSettingsControls();
      refreshProviderStatus();
    } else {
      sidebar.setAttribute("inert", "");
    }
  }
  syncSettingsButtonState();
}

function setupHistoryButton() {
  const button = document.querySelector("#history-button");
  if (!button) {
    return;
  }
  button.addEventListener("click", () => {
    userSettings.historyOpen = !userSettings.historyOpen;
    saveUserSettings(userSettings);
    applyHistorySidebarState();
  });
  syncHistoryButtonState();
}

function setupHistorySidebar() {
  app.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const deleteTrigger = event.target.closest("[data-history-delete-id]");
    if (deleteTrigger) {
      event.preventDefault();
      deleteHistoryEntry(deleteTrigger.dataset.historyDeleteId || "");
      return;
    }
    const trigger = event.target.closest("[data-history-id]");
    if (!trigger) {
      if (event.target.closest("[data-panel-dismiss]")) {
        userSettings.historyOpen = false;
        userSettings.settingsOpen = false;
        saveUserSettings(userSettings);
        applyHistorySidebarState();
        applySettingsSidebarState();
      }
      return;
    }
    event.preventDefault();
    loadHistoryEntry(trigger.dataset.historyId || "");
  });
}

function deleteHistoryEntry(id) {
  if (!id) {
    return;
  }
  historyEntries = historyEntries.filter((entry) => entry.id !== id);
  if (activeHistoryId === id) {
    activeHistoryId = null;
  }
  if (activeChatHistoryId === id) {
    activeChatHistoryId = null;
  }
  saveHistoryEntries(historyEntries);
  refreshHistorySidebar();
}

async function loadHistoryEntry(id) {
  const entry = historyEntries.find((item) => item.id === id);
  if (!entry) {
    return;
  }
  activeHistoryId = entry.id;
  if (entry.mode === "v3" || entry.mode === "interview") {
    activeChatHistoryId = entry.id;
    restoreChatTurns(entry.turns || []);
    switchMode(entry.mode === "interview" ? "v3" : entry.mode, true, { preserveChat: true });
    return;
  }

  switchMode(entry.mode, true);
  const textarea = document.querySelector("#query-form textarea");
  if (textarea) {
    textarea.value = entry.query || entry.title;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }
  await submitSearch(entry.query || entry.title, { record: false });
}

function switchMode(nextMode, pushState = false, options = {}) {
  if (!MODES[nextMode]) {
    return;
  }
  const previousMode = mode;
  if (
    !options.preserveChat
    && previousMode !== nextMode
    && isChatLikeMode(previousMode)
    && isChatLikeMode(nextMode)
  ) {
    chatTurns.splice(0, chatTurns.length);
    activeChatHistoryId = null;
    activeHistoryId = null;
  }
  mode = nextMode;
  config = MODES[mode];
  productPage = "interview";
  if (pushState) {
    window.history.pushState({}, "", mode === "v3" ? PRODUCT_PAGES.interview.path : `/${mode}`);
  }
  setActiveNav();
  renderShell();
}

function isChatLikeMode(candidateMode) {
  return candidateMode === "v3" || candidateMode === "interview";
}

function setupNavigation() {
  const switcher = document.querySelector(".version-switcher");
  if (switcher) {
    switcher.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) {
        return;
      }
      const link = event.target.closest("a[data-mode]");
      const productLink = event.target.closest("a[data-product-page]");
      if (productLink) {
        event.preventDefault();
        switchProductPage(productLink.dataset.productPage || "interview", true);
        return;
      }
      if (!link) {
        return;
      }
      event.preventDefault();
      const nextMode = link.dataset.mode;
      if (nextMode === mode) {
        return;
      }
      switchMode(nextMode, true);
    });
  }

  window.addEventListener("popstate", () => {
    mode = modeFromPath(window.location.pathname);
    config = MODES[mode];
    productPage = productPageFromPath(window.location.pathname);
    setActiveNav();
    renderShell();
  });
}

function switchProductPage(nextPage, pushState = false) {
  if (!PRODUCT_PAGES[nextPage]) {
    return;
  }
  mode = "v3";
  config = MODES.v3;
  productPage = nextPage;
  if (pushState) {
    window.history.pushState({}, "", PRODUCT_PAGES[nextPage].path);
  }
  setActiveNav();
  renderShell();
}

function bindSettingsControls() {
  const showTrace = document.querySelector("#setting-show-trace");
  const sectionJump = document.querySelector("#setting-section-jump");
  if (!showTrace || !sectionJump) {
    return;
  }

  showTrace.checked = userSettings.showTrace;
  sectionJump.checked = userSettings.sectionJump;

  showTrace.addEventListener("change", () => {
    userSettings.showTrace = showTrace.checked;
    saveUserSettings(userSettings);
    if (isActiveChat()) {
      renderChatConversation();
    }
  });

  sectionJump.addEventListener("change", () => {
    userSettings.sectionJump = sectionJump.checked;
    saveUserSettings(userSettings);
  });

  bindProviderConfigForm();
}

async function bindProviderConfigForm() {
  const form = document.querySelector("#provider-config-form");
  const message = document.querySelector("#provider-config-message");
  if (!form || !message) {
    return;
  }
  await loadProviderConfigForm(form, message);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
    }
    message.textContent = "正在保存...";
    const data = new FormData(form);
    try {
      const saved = await saveProviderConfig({
        base_url: String(data.get("base_url") || ""),
        model: String(data.get("model") || ""),
        api_key: String(data.get("api_key") || ""),
      });
      form.querySelector('[name="api_key"]').value = "";
      applyProviderConfigToForm(form, saved);
      message.textContent = saved.has_api_key ? "已保存，模型配置会立即用于新对话。" : "已保存，但 API Key 仍为空。";
      await refreshProviderStatus();
    } catch (error) {
      message.textContent = error.message || "保存失败";
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  });
}

async function loadProviderConfigForm(form, message) {
  try {
    applyProviderConfigToForm(form, await fetchProviderConfig());
    message.textContent = "";
  } catch (error) {
    message.textContent = error.message || "模型配置不可用";
  }
}

function applyProviderConfigToForm(form, configPayload) {
  form.querySelector('[name="base_url"]').value = configPayload.base_url || "";
  form.querySelector('[name="model"]').value = configPayload.model || "";
  const apiKeyInput = form.querySelector('[name="api_key"]');
  apiKeyInput.placeholder = configPayload.has_api_key ? "已保存，留空不修改" : "sk-...";
}

function setupSettingsPopover() {
  const button = document.querySelector("#settings-button");
  if (!button) {
    return;
  }

  button.addEventListener("click", () => {
    userSettings.settingsOpen = !userSettings.settingsOpen;
    saveUserSettings(userSettings);
    applySettingsSidebarState();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !(userSettings.historyOpen || userSettings.settingsOpen)) {
      return;
    }
    userSettings.historyOpen = false;
    userSettings.settingsOpen = false;
    saveUserSettings(userSettings);
    applyHistorySidebarState();
    applySettingsSidebarState();
  });

  syncSettingsButtonState();
}

function renderShell() {
  const activeChat = isActiveChat();
  document.body.classList.toggle("chat-active", activeChat);
  document.body.classList.toggle("history-open", userSettings.historyOpen);
  document.body.classList.toggle("settings-open", userSettings.settingsOpen);
  document.body.dataset.productPage = productPage;
  app.innerHTML = renderWorkspaceShell({
    activeHistoryId,
    content: renderMainContent(activeChat),
    historyEntries,
    userSettings,
  });
  syncHistoryButtonState();
  syncSettingsButtonState();
  bindSettingsControls();

  const form = document.querySelector("#query-form");
  if (form) {
    bindQueryForm(form);
  }

  if (isInterviewPage()) {
    setupInterviewControls({
      onStart: startInterviewFromControls,
      onSkip: skipInterviewFromControls,
      onEnd: endInterviewFromControls,
    });
    refreshInterviewQuestionPanel();
  }
  if (isInterviewMode() && productPage === "questions") {
    setupQuestionBankPage();
  }
  if (isInterviewMode() && productPage === "sources") {
    setupSourcesPage();
  }
  if (isInterviewMode() && productPage === "review" && !serverReviewLoaded && !serverReviewInFlight) {
    void refreshInterviewReview();
  }

  if (activeChat) {
    renderChatConversation();
  }
}

function renderMainContent(activeChat) {
  if (!isInterviewMode()) {
    return renderHomeShell(config);
  }
  if (productPage === "questions") {
    return renderQuestionBankShell();
  }
  if (productPage === "sources") {
    return renderSourcesShell();
  }
  if (productPage === "review") {
    return renderReviewShell(createReviewModel(historyEntries, chatTurns, activeChatHistoryId, serverReview));
  }
  return activeChat ? renderChatShell(config) : renderHomeShell(config);
}

async function startInterviewFromControls(initialUserMessage = "") {
  if (hasPendingChatTurn()) {
    return;
  }
  if (chatTurns.length) {
    persistCurrentChatHistory();
  }
  chatTurns.splice(0, chatTurns.length);
  activeChatHistoryId = createHistoryId();
  activeHistoryId = activeChatHistoryId;
  if (initialUserMessage) {
    chatTurns.push({ role: "user", content: String(initialUserMessage) });
  }
  const state = await startInterviewSession();
  if (!state.currentQuestion) {
    renderError("No interview questions available");
    return;
  }
  appendInterviewerQuestion(state);
  persistCurrentChatHistory();
  renderShell();
}

async function skipInterviewFromControls() {
  if (!hasActiveInterviewSession() || hasPendingChatTurn()) {
    return;
  }
  const state = skipInterviewQuestion();
  if (state.currentQuestion) {
    appendInterviewerQuestion(state);
  } else {
    await appendInterviewEndTurn(state);
  }
  persistCurrentChatHistory();
  renderShell();
}

async function endInterviewFromControls() {
  if (hasPendingChatTurn()) {
    return;
  }
  const state = endInterviewSession();
  await appendInterviewEndTurn(state);
  persistCurrentChatHistory();
  renderShell();
}

function appendInterviewerQuestion(state) {
  const question = state.currentQuestion;
  if (!question) {
    return;
  }
  chatTurns.push({
    role: "interviewer",
    content: state.followUp || question.question,
    question: question.question,
    questionId: question.id,
    progress: state.progress,
    followUp: state.followUp || "",
  });
}

async function appendInterviewEndTurn(state) {
  if (chatTurns.at(-1)?.role === "interviewer" && chatTurns.at(-1)?.completed) {
    return;
  }
  const { summary } = await loadActiveInterviewArtifacts();
  chatTurns.push({
    role: "interviewer",
    content: interviewEndMessage(state, summary),
    progress: "面试结束",
    completed: true,
  });
}

async function loadActiveInterviewArtifacts() {
  if (!activeChatHistoryId) {
    return { summary: null };
  }
  const summary = await fetchInterviewSessionSummary(activeChatHistoryId).catch(() => null);
  return { summary };
}

function interviewEndMessage(state, summary) {
  if (summary && Number(summary.completed || 0) > 0) {
    return summary.final_review || [
      `本场模拟面试结束。完成 ${summary.completed} 题。`,
      summary.next_step || "我已经在上面的对话里给出评价和追问方向。",
    ].join(" ");
  }
  return `本场模拟面试结束。已完成 ${state.answered}/${state.target} 个回答；这轮没有足够内容形成评价，下一轮先完整回答一题。`;
}

function bindQueryForm(form) {
  const textarea = form.querySelector("textarea");
  const submitButton = form.querySelector(".send-button");
  if (!textarea || !submitButton) {
    return;
  }
  let isSubmitting = false;
  syncComposerAvailability(textarea, submitButton);

  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  });

  textarea.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }
    event.preventDefault();
    form.requestSubmit();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isSubmitting || (isChatMode() && hasPendingChatTurn())) {
      return;
    }
    const q = new FormData(event.target).get("q") || "";
    if (!String(q).trim()) {
      textarea.focus();
      return;
    }
    isSubmitting = true;
    submitButton.disabled = true;
    if (isChatMode()) {
      textarea.value = "";
      textarea.style.height = "auto";
    }
    try {
      if (isInterviewMode()) {
        await submitInterviewInput(q);
      } else if (mode === "v3") {
        await submitChat(q);
      } else {
        await submitSearch(q);
      }
    } finally {
      isSubmitting = false;
      syncComposerAvailability(textarea, submitButton);
    }
  });
}

function syncComposerAvailability(textarea, submitButton) {
  textarea.disabled = false;
  textarea.placeholder = config.placeholder;
  submitButton.disabled = isChatMode() && hasPendingChatTurn();
}

function refreshHistorySidebar() {
  const sidebar = document.querySelector("#history-sidebar");
  if (sidebar && userSettings.historyOpen) {
    sidebar.innerHTML = renderHistorySidebar(historyEntries, activeHistoryId);
  }
}

function renderLoading(label) {
  document.querySelector("#results").innerHTML = `
    <div class="loading-row result-enter">
      <span class="spinner" aria-hidden="true"></span>
      <span>${escapeHtml(label)}</span>
    </div>
  `;
}

function renderError(message) {
  document.querySelector("#results").innerHTML = `
    <article class="notice-card">
      <strong>Request failed</strong>
      <p>${escapeHtml(message)}</p>
    </article>
  `;
}

async function submitSearch(q, options = {}) {
  renderLoading(mode === "v1" ? "Searching keywords" : "Retrieving evidence");
  try {
    const payload = await fetchSearchResults(config.endpoint, q);
    renderSearchResults(payload.results || [], config.resultTitle);
    if (options.record !== false) {
      recordSearchHistory(q);
      refreshHistorySidebar();
    }
    refreshProviderStatus();
  } catch (error) {
    renderError(error.message || "Unknown error");
  }
}

async function submitChat(message) {
  if (!activeChatHistoryId) {
    activeChatHistoryId = createHistoryId();
    activeHistoryId = activeChatHistoryId;
  }
  const sessionId = activeChatHistoryId;
  const history = visibleChatHistory();
  chatTurns.push({ role: "user", content: String(message) });
  const assistantTurn = {
    role: "assistant",
    content: "",
    evidence: [],
    trace: [],
    toolCalls: [],
    memoryHits: [],
    streaming: true,
  };
  chatTurns.push(assistantTurn);
  renderShell();
  try {
    await streamChat(
      config.streamEndpoint || `${config.endpoint}/stream`,
      message,
      history,
      (event) => {
        const renderMode = applyChatStreamEvent(assistantTurn, event);
        if (renderMode === "content") {
          scheduleAssistantContentUpdate(assistantTurn);
          return;
        }
        cancelAssistantContentUpdate();
        renderChatConversation();
      },
      { sessionId },
    );
    assistantTurn.streaming = false;
    renderShell();
  } catch (error) {
    applyChatFailure(assistantTurn, error.message || "Unknown error");
    renderShell();
  } finally {
    invalidateServerReview();
    persistCurrentChatHistory();
    renderShell();
    refreshProviderStatus();
  }
}

async function submitInterviewInput(message) {
  const activeSession = hasActiveInterviewSession();
  const command = parseInterviewCommand(message, { activeSession });
  if (command === "start") {
    await startInterviewFromControls(message);
    return;
  }
  if (command === "collect") {
    await collectInterviewSourcesFromCommand(message);
    return;
  }
  if (command === "explain") {
    await explainInterviewQuestionFromCommand(message);
    return;
  }
  if (activeSession && isAgentMetaConversation(message)) {
    await submitAgentConversation(message, { modelMessage: interviewMetaConversationMessage(message) });
    return;
  }
  if (!activeSession) {
    await submitAgentConversation(message);
    return;
  }
  await submitInterviewAnswer(message);
}

async function submitAgentConversation(message, options = {}) {
  if (!activeChatHistoryId) {
    activeChatHistoryId = createHistoryId();
    activeHistoryId = activeChatHistoryId;
  }
  const sessionId = activeChatHistoryId;
  const history = visibleChatHistory();
  const modelMessage = options.modelMessage || message;
  ensureCommandChat(message);
  const assistantTurn = {
    role: "assistant",
    content: "",
    evidence: [],
    trace: [],
    toolCalls: [],
    memoryHits: [],
    streaming: true,
  };
  chatTurns.push(assistantTurn);
  renderShell();
  try {
    await streamChat(
      GENERAL_AGENT_STREAM_ENDPOINT,
      modelMessage,
      history,
      (event) => {
        const renderMode = applyChatStreamEvent(assistantTurn, event);
        if (renderMode === "content") {
          scheduleAssistantContentUpdate(assistantTurn);
          return;
        }
        cancelAssistantContentUpdate();
        renderChatConversation();
      },
      { sessionId },
    );
    assistantTurn.streaming = false;
    renderShell();
  } catch (error) {
    applyChatFailure(assistantTurn, error.message || "Unknown error");
    renderShell();
  } finally {
    persistCurrentChatHistory();
    renderShell();
    refreshProviderStatus();
  }
}

async function submitInterviewAnswer(answer) {
  const question = await ensureInterviewQuestion();
  if (!question) {
    renderError("No interview questions available");
    return;
  }
  if (!activeChatHistoryId) {
    activeChatHistoryId = createHistoryId();
    activeHistoryId = activeChatHistoryId;
  }
  if (!chatTurns.some((turn) => turn.role === "interviewer" && turn.questionId === question.id)) {
    appendInterviewerQuestion(getInterviewSessionState());
  }
  const answeringFollowUp = Boolean(getInterviewSessionState().awaitingFollowUp);
  const reviewKey = `${activeChatHistoryId}:${question.id}:${Date.now()}`;
  chatTurns.push({ role: "user", content: String(answer), questionId: question.id });
  const assistantTurn = {
    role: "assistant",
    content: "",
    question: question.question,
    questionId: question.id,
    reviewKey,
    evidence: [],
    trace: [{ type: "question", message: question.question }],
    toolCalls: [],
    memoryHits: [],
    streaming: true,
    grade: null,
    followUp: "",
    coaching: "",
  };
  chatTurns.push(assistantTurn);
  renderShell();
  try {
    await streamInterviewAnswer(
      config.streamEndpoint,
      {
        session_id: activeChatHistoryId || "default",
        question_id: question.id,
        answer: String(answer),
      },
      (event) => {
        const renderMode = applyChatStreamEvent(assistantTurn, event);
        if (renderMode === "content") {
          scheduleAssistantContentUpdate(assistantTurn);
          return;
        }
        cancelAssistantContentUpdate();
        renderChatConversation();
      },
    );
    assistantTurn.streaming = false;
    const state = nextInterviewStateAfterAnswer(assistantTurn, answeringFollowUp);
    if (state.currentQuestion) {
      appendInterviewerQuestion(state);
    } else {
      await appendInterviewEndTurn(state);
    }
    renderShell();
  } catch (error) {
    applyChatFailure(assistantTurn, error.message || "Unknown error");
    renderShell();
  } finally {
    invalidateServerReview();
    persistCurrentChatHistory();
    renderShell();
    refreshProviderStatus();
  }
}

async function collectInterviewSourcesFromCommand(message) {
  const text = String(message);
  ensureCommandChat(text);
  const constraints = collectionConstraintsFromCommand(text);
  const payload = await fetchInterviewSourcePlatforms();
  const platforms = payload.platforms || [];
  const targets = platforms.filter((platform) => platform.connected && platformMatchesCommand(platform, text));
  if (!targets.length) {
    const connected = platforms.filter((platform) => platform.connected);
    const suffix = connected.length
      ? "你也可以直接说“采集面经”，我会采集所有已授权平台。"
      : "先去来源页打开对应网站登录，登录后关闭浏览器窗口即可。";
    chatTurns.push({
      role: "assistant",
      content: `没有找到可用的已授权平台。${suffix}`,
    });
    persistCurrentChatHistory();
    renderShell();
    return;
  }
  const jobs = await Promise.allSettled(
    targets.map((platform) => syncInterviewSourcePlatform(platform.id, constraints)),
  );
  const started = jobs
    .map((result, index) => (result.status === "fulfilled" ? { platform: targets[index], job: result.value } : null))
    .filter(Boolean);
  const failed = jobs
    .map((result, index) => (result.status === "rejected" ? targets[index].label : ""))
    .filter(Boolean);
  const assistantTurn = {
    role: "assistant",
    content: collectionStartedMarkdown(started.map((item) => item.platform), failed, constraints),
    streaming: Boolean(started.length),
  };
  chatTurns.push(assistantTurn);
  persistCurrentChatHistory();
  renderShell();
  if (!started.length) {
    assistantTurn.streaming = false;
    assistantTurn.content = collectionReportMarkdown([], failed, constraints);
    persistCurrentChatHistory();
    renderShell();
    return;
  }
  const progressByPlatform = new Map();
  const refreshCollectionProgress = (report) => {
    progressByPlatform.set(report.platform.id, report);
    assistantTurn.content = collectionReportMarkdown(
      Array.from(progressByPlatform.values()),
      failed,
      constraints,
    );
    renderChatConversation();
  };
  const reports = await Promise.all(
    started.map((item) => waitForInterviewCollectionJob(item.platform, refreshCollectionProgress)),
  );
  assistantTurn.streaming = false;
  assistantTurn.content = collectionReportMarkdown(reports, failed, constraints);
  persistCurrentChatHistory();
  renderShell();
}

async function waitForInterviewCollectionJob(platform, onProgress) {
  let latest = null;
  for (let attempt = 0; attempt < COLLECTION_POLL_ATTEMPTS; attempt += 1) {
    try {
      latest = await fetchInterviewSourcePlatformLatestJob(platform.id);
      onProgress?.({ platform, job: latest, timedOut: false, error: "" });
      if (isCollectionJobFinished(latest)) {
        return { platform, job: latest, timedOut: false, error: "" };
      }
    } catch (error) {
      return { platform, job: latest, timedOut: false, error: error.message || "状态读取失败" };
    }
    await sleep(COLLECTION_POLL_INTERVAL_MS);
  }
  return { platform, job: latest, timedOut: true, error: "" };
}

function isCollectionJobFinished(job) {
  return ["completed", "failed", "needs_login"].includes(String(job?.state || ""));
}

function collectionStartedMarkdown(platforms, failedLabels, constraints) {
  const names = platforms.map((platform) => platform.label).join("、");
  const lines = [
    constraints.dryRun
      ? `我先按预览模式检查：${names || "无可用平台"}，不会写入题库。`
      : `我开始采集：${names || "无可用平台"}。`,
    "我会复用来源页保存的登录态，并在完成后汇报访问页面、通过题目和拒收候选。",
  ];
  if (constraints.maxPages) {
    lines.push(`本次最多查看 ${constraints.maxPages} 篇候选详情。`);
  }
  if (failedLabels.length) {
    lines.push(`启动失败：${failedLabels.join("、")}。`);
  }
  return lines.join("\n\n");
}

function collectionReportMarkdown(reports, failedLabels, constraints) {
  const hasActiveReport = reports.some((report) => report.job && !isCollectionJobFinished(report.job) && !report.timedOut);
  const lines = [collectionReportHeader(constraints.dryRun, hasActiveReport)];
  if (failedLabels.length) {
    lines.push(`启动失败：${failedLabels.join("、")}。`);
  }
  for (const report of reports) {
    const { platform, job, timedOut, error } = report;
    if (error) {
      lines.push(`\n**${platform.label}**：状态读取失败，${error}。`);
      continue;
    }
    if (!job) {
      lines.push(`\n**${platform.label}**：还没有拿到采集结果。`);
      continue;
    }
    const mode = job.dry_run ? "预览" : "入库";
    const collectionMode = job.collection_mode === "browser_session" ? "登录态浏览器会话" : "浏览器采集";
    const status = timedOut ? "仍在后台运行" : collectionStateLabel(job.state);
    lines.push(
      `\n**${platform.label}**：${status}，模式：${mode}，执行方式：${collectionMode}，访问 ${job.source_pages || 0} 页，识别 ${job.questions || 0} 道，新增 ${job.unique_questions || 0}，重复 ${job.duplicate_questions || 0}。`,
    );
    if (job.quality_message) {
      lines.push(`质量判断：${job.quality_message}`);
    }
    if (job.since_days) {
      lines.push(`时间过滤：只接受最近 ${job.since_days} 天且详情页可验证发布时间的内容。`);
    }
    if (job.max_pages || constraints.maxPages) {
      lines.push(`候选上限：${job.max_pages || constraints.maxPages} 篇详情。`);
    }
    appendCollectionList(lines, "访问过的页面", job.visited_pages);
    appendCollectionList(lines, "浏览器动作", job.interaction_trace);
    appendCollectionList(lines, job.dry_run ? "可入库题目" : "已通过题目", job.accepted_questions);
    appendCollectionList(lines, "拒收候选", job.rejected_candidates);
    appendCollectionList(lines, "自动改写", job.rewritten_questions);
    if (job.state === "needs_login") {
      lines.push("需要你在来源页重新打开登录窗口，登录后关闭窗口，我再继续采集。");
    }
  }
  if (!reports.length && !failedLabels.length) {
    lines.push("没有启动任何采集任务。");
  }
  return lines.join("\n");
}

function collectionReportHeader(dryRun, hasActiveReport) {
  if (dryRun) {
    return hasActiveReport ? "采集预览进度：" : "采集预览报告：";
  }
  return hasActiveReport ? "采集进度：" : "采集完成报告：";
}

function appendCollectionList(lines, title, items) {
  const values = Array.isArray(items) ? items.filter(Boolean).slice(0, 6) : [];
  if (!values.length) {
    return;
  }
  lines.push(`${title}：`);
  for (const value of values) {
    lines.push(`- ${value}`);
  }
}

function collectionStateLabel(state) {
  if (state === "completed") {
    return "完成";
  }
  if (state === "failed") {
    return "失败";
  }
  if (state === "needs_login") {
    return "等待登录";
  }
  if (state === "running") {
    return "采集中";
  }
  return "已启动";
}

function collectionConstraintsFromCommand(message) {
  const text = String(message || "").toLowerCase();
  return {
    dryRun: /(预览|先看|看看|看一下|不要入库|不入库|先别入库|只看)/.test(text),
    sinceDays: recentDaysFromCommand(text),
    maxPages: pageLimitFromCommand(text),
  };
}

function pageLimitFromCommand(text) {
  const match = String(text || "").match(/(?:先)?(?:搜集|采集|搜索|抓取|爬取)?\s*(\d{1,2})\s*(?:篇|页|个|条)/);
  if (!match) {
    return null;
  }
  return Math.min(Math.max(Number(match[1]) || 5, 1), 20);
}

function recentDaysFromCommand(text) {
  if (/(最近|近)(一周|7天|七天|一个星期|一星期|一礼拜)/.test(text)) {
    return 7;
  }
  const days = text.match(/(?:最近|近)(\d{1,2})\s*天/);
  if (days) {
    return Math.min(Math.max(Number(days[1]) || 7, 1), 30);
  }
  if (/(最近|近)(一个月|30天|三十天)/.test(text)) {
    return 30;
  }
  return null;
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function explainInterviewQuestionFromCommand(message) {
  const text = String(message);
  ensureCommandChat(text);
  const state = getInterviewSessionState();
  const question = state.currentQuestion || (await findQuestionForExplanation(text));
  if (!question) {
    chatTurns.push({
      role: "assistant",
      content: "我还没有找到对应题目。你可以说“讲 RAG 召回失败”或先去题库入库更多面经。",
    });
  } else {
    chatTurns.push({
      role: "assistant",
      content: interviewQuestionExplanation(question),
      question: question.question,
      questionId: question.id,
    });
  }
  persistCurrentChatHistory();
  renderShell();
}

function ensureCommandChat(message) {
  if (!activeChatHistoryId) {
    activeChatHistoryId = createHistoryId();
    activeHistoryId = activeChatHistoryId;
  }
  chatTurns.push({ role: "user", content: String(message) });
}

function parseInterviewCommand(message, options = {}) {
  const text = String(message || "").trim().toLowerCase();
  if (!text) {
    return "";
  }
  const activeSession = options.activeSession === true;
  if (isStartInterviewCommand(text, activeSession)) {
    return "start";
  }
  if (isCollectInterviewCommand(text, activeSession)) {
    return "collect";
  }
  if (isExplainQuestionCommand(text)) {
    return "explain";
  }
  return "";
}

function isAgentMetaConversation(message) {
  const text = String(message || "").trim().toLowerCase();
  if (!text) {
    return false;
  }
  return /^(你在干嘛|你是谁|你能干嘛|你可以.*对话|可以.*对话|能.*聊天|正常.*聊天|正常.*对话|怎么用|如何使用|退出流程|暂停面试)$/.test(text)
    || /(这个|现在).*(agent|产品|功能|流程|ui|界面|对话|聊天).*(不对|不行|不好|奇怪|烂|乱|问题|做不到)/.test(text)
    || /(为什么|怎么).*(不能|没法|无法|一直|总是).*(对话|聊天|追问|换题|流程|卡住)/.test(text)
    || /^(不是|不对|等一下|停一下|暂停|先别).*面试/.test(text);
}

function interviewMetaConversationMessage(message) {
  const state = getInterviewSessionState();
  const question = state.currentQuestion;
  const currentQuestion = question?.question || "当前面试题";
  return [
    String(message),
    "",
    "隐藏上下文：用户正在一次模拟面试中发起元对话，不是在回答当前题，也不是要求开始新题。",
    `当前题目：${currentQuestion}`,
    `当前进度：${state.progress || ""}`,
    "请直接回答用户的问题；如果用户问你在做什么，就说明你正在等他围绕当前题作答，必要时可以把当前题换成更自然的问法。",
    "不要另起一场面试，不要生成新的题目，不要把这句话当作候选人答案评价。",
  ].join("\n");
}

function isStartInterviewCommand(text, activeSession) {
  if (activeSession && text.length > 12) {
    return false;
  }
  return /^(开始|重新开始|开始面试|模拟面试|考我|开一场|来一场)$/.test(text)
    || (!activeSession && /^(开始|重新开始|开始一场|开始模拟|开始模拟面试|模拟一场|来一场面试|开一场面试|考我一下)$/.test(text));
}

function isCollectInterviewCommand(text, activeSession) {
  if (activeSession) {
    return /^(采集|爬取|抓取|搜集|搜索|入库|预览|看看|看一下|帮我采集|去采集).*(面经|牛客|小红书|知乎)/.test(text)
      || /^面经.*(采集|爬取|抓取|搜集|搜索|入库|预览|看看|看一下)/.test(text);
  }
  return /(采集|爬取|抓取|搜集|搜索|入库|预览|看看|看一下).*(面经|题|牛客|小红书|知乎)|面经.*(采集|爬取|抓取|搜集|搜索|入库|预览|看看|看一下)/.test(text);
}

function isExplainQuestionCommand(text) {
  return /^(讲|解释|解析|讲一下|解释一下|解析一下|帮我讲|给我讲)/.test(text)
    || /^(这道题|这个题).*(怎么答|答案|思路|讲|解释|解析)/.test(text)
    || /^(怎么答|答案|思路)$/.test(text);
}

function platformMatchesCommand(platform, message) {
  const text = String(message).toLowerCase();
  const hasSpecificPlatform = /(牛客|nowcoder|小红书|xiaohongshu|知乎|zhihu)/.test(text);
  if (!hasSpecificPlatform) {
    return true;
  }
  return text.includes(String(platform.id).toLowerCase())
    || text.includes(String(platform.host).toLowerCase())
    || text.includes(String(platform.label).toLowerCase());
}

async function findQuestionForExplanation(message) {
  const payload = await fetchInterviewQuestions();
  const questions = payload.items || [];
  const query = String(message).replace(/(讲|解释|解析|怎么答|答案|思路|这道题|题目)/g, "").trim();
  const topic = topicFromText(message);
  return questions.find((question) => query && question.question.includes(query))
    || questions.find((question) => topic && question.topic === topic)
    || questions[0]
    || null;
}

function interviewQuestionExplanation(question) {
  const topic = topicLabel(question.topic);
  const hint = question.answer_hint ? `\n\n可用素材：${question.answer_hint}` : "";
  return [
    `题目：${question.question}`,
    "",
    `面试官主要看 ${topic} 的理解是不是能落到工程。回答时别只讲概念，按“场景 -> 方案 -> 取舍 -> 验证 -> 项目落地”五步说。`,
    "",
    "推荐回答骨架：",
    "1. 先定义问题边界和目标。",
    "2. 讲核心链路、数据结构或工具调用过程。",
    "3. 主动说成本、延迟、准确率、可靠性等 tradeoff。",
    "4. 给出 eval / 指标 / badcase 回归方式。",
    "5. 最后落到自己的 v3 Agent、RAG、Memory 或登录态采集项目。",
    hint,
  ].join("\n");
}

function topicFromText(message) {
  const text = String(message).toLowerCase();
  if (/eval|评测|评分|grader|outcome/.test(text)) {
    return "agent_eval";
  }
  if (/memory|记忆|l0|l1|l2|l3/.test(text)) {
    return "memory";
  }
  if (/rag|召回|检索|rerank|向量/.test(text)) {
    return "rag";
  }
  if (/mcp|skill/.test(text)) {
    return "mcp_skill";
  }
  if (/agent|react|工具调用/.test(text)) {
    return "agent_architecture";
  }
  return "";
}

function topicLabel(topic) {
  return {
    agent_eval: "Agent Eval",
    memory: "记忆系统",
    rag: "RAG",
    agent_architecture: "Agent 架构",
    mcp_skill: "MCP / Skill",
  }[topic] || "AI Agent";
}

function nextInterviewStateAfterAnswer(assistantTurn, answeringFollowUp) {
  void answeringFollowUp;
  const followUp = String(assistantTurn.followUp || "").trim();
  if (followUp) {
    assistantTurn.followUpQueued = true;
    return askInterviewFollowUp(followUp);
  }
  return completeInterviewQuestion();
}

function visibleChatHistory() {
  return chatTurns
    .filter((turn) => turn.role === "user" || turn.role === "assistant")
    .map((turn) => ({
      role: turn.role,
      content: String(turn.content || "").trim(),
    }))
    .filter((turn) => turn.content)
    .slice(-MAX_CHAT_CONTEXT_TURNS);
}

function streamingPlaceholder(turn) {
  if ((turn.evidence || []).length) {
    return isInterviewMode() ? "已整理面试上下文，正在追问..." : "已读取证据，正在生成回答...";
  }
  if ((turn.memoryHits || []).length) {
    return isInterviewMode() ? "已召回弱点记忆，正在生成评价..." : "已召回相关记忆，正在检索资料...";
  }
  if ((turn.toolCalls || []).length) {
    return isInterviewMode() ? "正在调用面试工具..." : "正在读取相关资料...";
  }
  if ((turn.trace || []).length) {
    return isInterviewMode() ? "正在生成面试官评价和追问..." : "正在检索相关资料...";
  }
  return isInterviewMode() ? "正在生成面试官评价..." : "Retrieving evidence...";
}

function renderChatConversation() {
  document.querySelector("#results").innerHTML = renderChatConversationMarkup(chatTurns, {
    placeholderForTurn: streamingPlaceholder,
    showTrace: userSettings.showTrace,
    compactInterview: isInterviewMode(),
  });
}

function scheduleAssistantContentUpdate(turn) {
  pendingAssistantContentTurn = turn;
  if (pendingAssistantContentFrame) {
    return;
  }
  pendingAssistantContentFrame = window.requestAnimationFrame(() => {
    pendingAssistantContentFrame = 0;
    if (pendingAssistantContentTurn) {
      updateAssistantContent(pendingAssistantContentTurn);
    }
    pendingAssistantContentTurn = null;
  });
}

function cancelAssistantContentUpdate() {
  if (pendingAssistantContentFrame) {
    window.cancelAnimationFrame(pendingAssistantContentFrame);
    pendingAssistantContentFrame = 0;
  }
  pendingAssistantContentTurn = null;
}

function updateAssistantContent(turn) {
  const index = chatTurns.indexOf(turn);
  const body = document.querySelector(
    `.chat-message-assistant[data-turn-index="${index}"] .markdown-body`,
  );
  if (!body) {
    renderChatConversation();
    return;
  }
  body.innerHTML = renderAssistantBody(turn, streamingPlaceholder, {
    compactInterview: isInterviewMode(),
  });
}

setupNavigation();
setupHistoryButton();
setupHistorySidebar();
setupSettingsPopover();
setupEvidenceCarousel(app);
setupSopPreview(app, () => userSettings);
setActiveNav();
renderShell();
refreshProviderStatus();
