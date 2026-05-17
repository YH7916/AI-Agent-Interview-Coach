import {
  getInterviewQuestions,
  loadInterviewQuestions,
} from "./interviewState.js";
import { escapeHtml } from "./markdown.js";

let questionBankStatus = "正在读取题库...";
let questionBankStatusKind = "muted";

export function setupQuestionBankPage() {
  const refreshButton = document.querySelector("[data-question-bank-refresh]");

  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      refreshButton.disabled = true;
      setQuestionBankStatus("正在刷新题库...");
      try {
        const questions = await loadInterviewQuestions({ reload: true });
        setQuestionBankStatus(`题库已刷新，共 ${questions.length} 道题`);
      } catch (error) {
        setQuestionBankStatus(error.message || "刷新失败", "error");
      } finally {
        refreshButton.disabled = false;
        renderQuestionBank();
      }
    });
  }

  void refreshQuestionBankPage();
}

async function refreshQuestionBankPage() {
  try {
    const questions = await loadInterviewQuestions({ reload: !getInterviewQuestions().length });
    setQuestionBankStatus(questions.length ? `题库已就绪，共 ${questions.length} 道题` : "题库为空");
  } catch (error) {
    setQuestionBankStatus(error.message || "读取题库失败", "error");
  }
  renderQuestionBank();
}

function renderQuestionBank() {
  renderQuestionBankStats();
  renderQuestionBankStatus();
  renderQuestionBankList();
}

function renderQuestionBankStats() {
  const target = document.querySelector("[data-question-bank-stats]");
  if (!target) {
    return;
  }
  const questions = getInterviewQuestions();
  const topics = new Set(questions.map((item) => item.topic).filter(Boolean));
  const platforms = new Set(questions.map((item) => item.platform).filter(Boolean));
  target.innerHTML = `
    <article class="metric-tile">
      <span>题目</span>
      <strong>${escapeHtml(String(questions.length))}</strong>
    </article>
    <article class="metric-tile">
      <span>主题</span>
      <strong>${escapeHtml(String(topics.size))}</strong>
    </article>
    <article class="metric-tile">
      <span>来源</span>
      <strong>${escapeHtml(String(platforms.size))}</strong>
    </article>
  `;
}

function renderQuestionBankStatus() {
  const target = document.querySelector("[data-question-bank-status]");
  if (!target) {
    return;
  }
  target.textContent = questionBankStatus;
  target.classList.toggle("is-error", questionBankStatusKind === "error");
}

function renderQuestionBankList() {
  const target = document.querySelector("[data-question-bank-list]");
  if (!target) {
    return;
  }
  const questions = getInterviewQuestions();
  if (!questions.length) {
    target.innerHTML = `<article class="product-empty">还没有题目。回到面试页输入“采集面经”，Agent 会先汇报采集结果再入库。</article>`;
    return;
  }
  target.innerHTML = questions.slice(0, 80).map(renderQuestionRow).join("");
}

function renderQuestionRow(question) {
  const source = question.platform || question.source_uri || "local";
  const meta = [
    question.difficulty ? difficultyLabel(question.difficulty) : "",
    question.frequency ? `高频 ${question.frequency} 次` : "",
  ]
    .filter(Boolean)
    .join(" / ");
  return `
    <article class="question-bank-row">
      <div>
        <span>${escapeHtml(topicLabel(question.topic))}</span>
        <strong>${escapeHtml(question.question || "")}</strong>
        <small>${escapeHtml(source)}</small>
      </div>
      ${meta ? `<em>${escapeHtml(meta)}</em>` : ""}
    </article>
  `;
}

function setQuestionBankStatus(message, kind = "muted") {
  questionBankStatus = message;
  questionBankStatusKind = kind;
  renderQuestionBankStatus();
}

function topicLabel(topic) {
  return {
    agent_eval: "Agent 评测",
    memory: "记忆系统",
    rag: "RAG",
    agent_architecture: "Agent 架构",
    mcp_skill: "MCP / Skill",
    llm_infra: "LLM Infra",
    alignment: "模型对齐",
    production: "工程落地",
    general: "综合",
  }[topic] || "综合";
}

function difficultyLabel(difficulty) {
  return {
    easy: "基础",
    medium: "中等",
    hard: "进阶",
  }[difficulty] || "中等";
}
