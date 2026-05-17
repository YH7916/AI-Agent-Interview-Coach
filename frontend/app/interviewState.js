import {
  fetchInterviewQuestions,
  fetchInterviewSessionPlan,
  importInterviewSources,
} from "./api.js";

const INTERVIEW_SESSION_SIZE = 5;

let currentInterviewQuestion = null;
let interviewQuestions = [];
let interviewQuestionIndex = 0;
let interviewSession = idleInterviewSession();

export async function ensureCurrentInterviewQuestion(options = {}) {
  if (hasActiveInterviewSession() && currentInterviewQuestion && !options.force) {
    return currentInterviewQuestion;
  }
  if (!interviewSession.started || interviewSession.completed) {
    const state = await startInterviewSession(options);
    return state.currentQuestion;
  }
  await ensureQuestionPool({ reload: options.reload });
  currentInterviewQuestion =
    interviewSession.questions[interviewSession.index] ||
    interviewQuestions[interviewQuestionIndex] ||
    null;
  return currentInterviewQuestion;
}

export async function loadInterviewQuestions(options = {}) {
  if (!interviewQuestions.length || options.reload) {
    const payload = await fetchInterviewQuestions();
    interviewQuestions = payload.items || [];
    if (interviewQuestionIndex >= interviewQuestions.length) {
      interviewQuestionIndex = 0;
    }
  }
  return interviewQuestions;
}

export async function importAndReloadInterviewQuestions() {
  await importInterviewSources();
  resetQuestionSelection();
  return loadInterviewQuestions({ reload: true });
}

export function getInterviewQuestions() {
  return interviewQuestions;
}

export function resetQuestionSelection() {
  interviewQuestionIndex = 0;
  currentInterviewQuestion = null;
}

export function advanceInterviewQuestion() {
  if (!interviewQuestions.length) {
    currentInterviewQuestion = null;
    return;
  }
  interviewQuestionIndex = (interviewQuestionIndex + 1) % interviewQuestions.length;
  currentInterviewQuestion = interviewQuestions[interviewQuestionIndex];
}

export async function startInterviewSession(options = {}) {
  await ensureQuestionPool({ reload: options.reload });
  const plannedQuestions = await planInterviewSession();
  interviewSession = {
    started: plannedQuestions.length > 0,
    completed: plannedQuestions.length === 0,
    questions: plannedQuestions,
    index: 0,
    answered: 0,
    target: plannedQuestions.length,
    followUp: "",
  };
  currentInterviewQuestion = plannedQuestions[0] || null;
  return getInterviewSessionState();
}

export function completeInterviewQuestion() {
  if (!hasActiveInterviewSession()) {
    return getInterviewSessionState();
  }
  interviewSession.followUp = "";
  interviewSession.answered += 1;
  interviewSession.index += 1;
  if (interviewSession.index >= interviewSession.target) {
    interviewSession.completed = true;
    currentInterviewQuestion = null;
  } else {
    currentInterviewQuestion = interviewSession.questions[interviewSession.index] || null;
  }
  return getInterviewSessionState();
}

export function skipInterviewQuestion() {
  if (!hasActiveInterviewSession()) {
    return getInterviewSessionState();
  }
  interviewSession.followUp = "";
  interviewSession.index += 1;
  if (interviewSession.index >= interviewSession.target) {
    interviewSession.completed = true;
    currentInterviewQuestion = null;
  } else {
    currentInterviewQuestion = interviewSession.questions[interviewSession.index] || null;
  }
  return getInterviewSessionState();
}

export function endInterviewSession() {
  if (interviewSession.started) {
    interviewSession.completed = true;
  }
  interviewSession.followUp = "";
  currentInterviewQuestion = null;
  return getInterviewSessionState();
}

export function askInterviewFollowUp(followUp) {
  if (!hasActiveInterviewSession()) {
    return getInterviewSessionState();
  }
  interviewSession.followUp = String(followUp || "").trim();
  return getInterviewSessionState();
}

export function hasActiveInterviewSession() {
  return interviewSession.started && !interviewSession.completed && Boolean(currentInterviewQuestion);
}

export function getInterviewSessionState() {
  return {
    started: interviewSession.started,
    completed: interviewSession.completed,
    currentQuestion: currentInterviewQuestion,
    followUp: interviewSession.followUp,
    awaitingFollowUp: Boolean(interviewSession.followUp),
    index: interviewSession.index,
    answered: interviewSession.answered,
    target: interviewSession.target,
    progress: interviewProgressLabel(),
  };
}

export function interviewProgressLabel() {
  if (!interviewSession.started) {
    return "Mock interview";
  }
  if (interviewSession.completed) {
    return `${interviewSession.answered}/${interviewSession.target} 已完成`;
  }
  if (interviewSession.followUp) {
    return `第 ${interviewSession.index + 1}/${interviewSession.target} 题 · 追问`;
  }
  return `第 ${interviewSession.index + 1}/${interviewSession.target} 题`;
}

async function ensureQuestionPool(options = {}) {
  await loadInterviewQuestions({ reload: options.reload });
  if (!interviewQuestions.length) {
    await importAndReloadInterviewQuestions();
  }
}

function idleInterviewSession() {
  return {
    started: false,
    completed: false,
    questions: [],
    index: 0,
    answered: 0,
    target: INTERVIEW_SESSION_SIZE,
    followUp: "",
  };
}

async function planInterviewSession() {
  try {
    const payload = await fetchInterviewSessionPlan(INTERVIEW_SESSION_SIZE);
    const planned = payload.items || [];
    if (planned.length) {
      interviewQuestions = mergePlannedQuestions(planned, interviewQuestions);
      return planned;
    }
  } catch (_error) {
    // Local planning keeps the interview usable if the server plan endpoint is unavailable.
  }
  return planLocalInterviewSession(interviewQuestions);
}

function planLocalInterviewSession(questions) {
  const ranked = [...questions]
    .sort((a, b) => {
      const topicOrder = topicPriority(b.topic) - topicPriority(a.topic);
      if (topicOrder) {
        return topicOrder;
      }
      const frequencyOrder = Number(b.frequency || 0) - Number(a.frequency || 0);
      if (frequencyOrder) {
        return frequencyOrder;
      }
      return difficultyPriority(b.difficulty) - difficultyPriority(a.difficulty);
    });
  return diverseTake(ranked, INTERVIEW_SESSION_SIZE);
}

function diverseTake(questions, size) {
  const selected = [];
  const topicCounts = new Map();
  const topicCap = size >= 4 ? 2 : 1;
  for (const question of questions) {
    const topic = question.topic || "general";
    if ((topicCounts.get(topic) || 0) >= topicCap) {
      continue;
    }
    selected.push(question);
    topicCounts.set(topic, (topicCounts.get(topic) || 0) + 1);
    if (selected.length >= size) {
      return selected;
    }
  }
  for (const question of questions) {
    if (selected.some((item) => item.id === question.id)) {
      continue;
    }
    selected.push(question);
    if (selected.length >= size) {
      return selected;
    }
  }
  return selected;
}

function mergePlannedQuestions(planned, existing) {
  const byId = new Map();
  for (const question of [...planned, ...existing]) {
    if (question?.id && !byId.has(question.id)) {
      byId.set(question.id, question);
    }
  }
  return [...byId.values()];
}

function topicPriority(topic) {
  return {
    agent_eval: 5,
    memory: 4,
    rag: 3,
    mcp_skill: 2,
  }[topic] || 1;
}

function difficultyPriority(difficulty) {
  return {
    hard: 3,
    medium: 2,
    easy: 1,
  }[difficulty] || 0;
}
