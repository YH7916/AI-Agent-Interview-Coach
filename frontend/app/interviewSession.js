import {
  askInterviewFollowUp as askInterviewFollowUpState,
  completeInterviewQuestion as completeInterviewQuestionState,
  endInterviewSession as endInterviewSessionState,
  ensureCurrentInterviewQuestion,
  getInterviewSessionState,
  hasActiveInterviewSession,
  interviewProgressLabel,
  skipInterviewQuestion as skipInterviewQuestionState,
  startInterviewSession as startInterviewSessionState,
} from "./interviewState.js";
import { escapeHtml } from "./markdown.js";

export { getInterviewSessionState, hasActiveInterviewSession };

export async function ensureInterviewQuestion(options = {}) {
  const question = await ensureCurrentInterviewQuestion(options);
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
  return question;
}

export function setupInterviewControls(handlers = {}) {
  const startButton = document.querySelector("[data-interview-start]");
  const nextButton = document.querySelector("[data-interview-next]");
  const endButton = document.querySelector("[data-interview-end]");
  if (startButton) {
    startButton.addEventListener("click", () => {
      void handlers.onStart?.();
    });
  }
  if (nextButton) {
    nextButton.addEventListener("click", () => {
      void handlers.onSkip?.();
    });
  }
  if (endButton) {
    endButton.addEventListener("click", () => {
      void handlers.onEnd?.();
    });
  }
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
}

export async function startInterviewSession(options = {}) {
  const state = await startInterviewSessionState(options);
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
  return state;
}

export function completeInterviewQuestion() {
  const state = completeInterviewQuestionState();
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
  return state;
}

export function askInterviewFollowUp(followUp) {
  const state = askInterviewFollowUpState(followUp);
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
  return state;
}

export function skipInterviewQuestion() {
  const state = skipInterviewQuestionState();
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
  return state;
}

export function endInterviewSession() {
  const state = endInterviewSessionState();
  syncInterviewControlButtons();
  refreshInterviewQuestionPanel();
  return state;
}

export function refreshInterviewQuestionPanel() {
  const panel = document.querySelector("#interview-question-panel");
  if (!panel) {
    return;
  }
  const state = getInterviewSessionState();
  if (!state.started) {
    panel.innerHTML = `
      <div class="interview-question-main">
        <span class="interview-question-topic">Agent</span>
        <strong>可以直接对话</strong>
        <small>输入“开始面试”才进入模拟面试；采集、讲题也可以用自然语言发起。</small>
      </div>
    `;
    return;
  }
  if (state.completed) {
    panel.innerHTML = `
      <div class="interview-question-main">
        <span class="interview-question-topic">Review</span>
        <strong>本场面试已结束</strong>
        <small>面试官总结已写在当前对话里。</small>
      </div>
    `;
    return;
  }
  if (!state.currentQuestion) {
    panel.innerHTML = `
      <div class="interview-question-main">
        <span class="interview-question-topic">Loading</span>
        <strong>正在准备题目...</strong>
      </div>
    `;
    return;
  }
  panel.innerHTML = `
    <div class="interview-question-main">
      <span class="interview-question-topic">${escapeHtml(interviewProgressLabel())}</span>
      <strong>${escapeHtml(state.awaitingFollowUp ? "正在追问" : "正在作答")}</strong>
      <small>${escapeHtml(questionMeta(state.currentQuestion, state.awaitingFollowUp))}</small>
    </div>
  `;
}

function syncInterviewControlButtons() {
  const state = getInterviewSessionState();
  const startButton = document.querySelector("[data-interview-start]");
  const nextButton = document.querySelector("[data-interview-next]");
  const endButton = document.querySelector("[data-interview-end]");
  if (startButton) {
    startButton.textContent = "重新开始";
    startButton.hidden = !state.started;
  }
  if (nextButton) {
    nextButton.disabled = !hasActiveInterviewSession();
    nextButton.hidden = !state.started;
  }
  if (endButton) {
    endButton.disabled = !state.started || state.completed;
    endButton.hidden = !state.started;
  }
}

function questionMeta(question, awaitingFollowUp = false) {
  return [
    awaitingFollowUp ? "围绕上一轮回答继续追问" : "",
    question.topic || "",
    question.difficulty ? `难度 ${question.difficulty}` : "",
    question.platform || question.source_uri || "",
  ]
    .filter(Boolean)
    .join(" / ");
}
