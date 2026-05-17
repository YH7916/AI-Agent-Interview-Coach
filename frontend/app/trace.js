import { escapeHtml } from "./markdown.js";
import { renderMemoryTrace } from "./memory.js";

export function renderInlineTrace(turn, showTrace) {
  const trace = showTrace ? turn.trace || [] : [];
  if (!trace.length) {
    return "";
  }
  const toolCallCount = (turn.toolCalls || []).length;
  const hasEvidence = (turn.evidence || []).length > 0;
  const isInterviewTrace = trace.some((item) => item.type === "question" || item.type === "grade");
  const memoryTrace = renderMemoryTrace(turn.memoryHits || []);
  if (!toolCallCount && !hasEvidence && turn.streaming) {
    return "";
  }
  const visibleTrace = mainTrace(trace);
  if (!visibleTrace.length && !toolCallCount) {
    return "";
  }
  const workflowSteps = [
    ...visibleTrace.map((item) => ({
      label: compactTraceType(item.type),
      message: compactTraceMessage(item.message),
    })),
  ];
  if (turn.content || turn.streaming) {
    workflowSteps.push({
      label: "输出",
      message: turn.streaming ? "正在生成回答" : "回答已生成",
    });
  }
  return `
    <details class="inline-trace" aria-label="${isInterviewTrace ? "面试过程" : "工具调用过程"}">
      <summary class="inline-trace-header">
        <span>${isInterviewTrace ? "面试过程" : "过程"}</span>
        <small>${toolCallCount ? `${toolCallCount} 次工具` : isInterviewTrace ? "评价完成" : "检索完成"}</small>
      </summary>
      <ol class="inline-trace-list">
        ${workflowSteps.map((item, index) => `
          <li class="inline-trace-step ${turn.streaming && index === workflowSteps.length - 1 ? "is-active" : ""}" style="--i: ${index}">
            <span class="inline-trace-dot" aria-hidden="true"></span>
            <div>
              <strong>${escapeHtml(item.label)}</strong>
              <p>${escapeHtml(item.message)}</p>
            </div>
          </li>
        `).join("")}
      </ol>
      ${renderTraceDetails(trace)}
      ${memoryTrace}
    </details>
  `;
}

function mainTrace(trace) {
  return trace
    .filter((item) => ["question", "grade", "director", "warning", "error"].includes(item.type))
    .slice(0, 4);
}

function renderTraceDetails(trace) {
  const details = trace
    .filter((item) => !["question", "thought"].includes(item.type))
    .slice(0, 20);
  if (!details.length) {
    return "";
  }
  return `
    <details class="inline-trace-details">
      <summary>查看工具细节</summary>
      <ul>
        ${details.map((item) => `
          <li>
            <span>${escapeHtml(compactTraceType(item.type))}</span>
            <em>${escapeHtml(compactTraceMessage(item.message))}</em>
          </li>
        `).join("")}
      </ul>
    </details>
  `;
}

function compactTraceType(type) {
  if (type === "question") {
    return "题目";
  }
  if (type === "thought") {
    return "思考";
  }
  if (type === "grade") {
    return "评价";
  }
  if (type === "tool_call") {
    return "工具";
  }
  if (type === "tool_result") {
    return "执行";
  }
  if (type === "retrieval") {
    return "检索";
  }
  if (type === "memory") {
    return "记忆";
  }
  if (type === "observation") {
    return "读取";
  }
  if (type === "evidence") {
    return "证据";
  }
  if (type === "director") {
    return "决策";
  }
  if (type === "warning") {
    return "提示";
  }
  if (type === "error") {
    return "错误";
  }
  return String(type || "trace");
}

function compactTraceMessage(message) {
  return String(message || "")
    .replace("v2 hybrid retrieval candidates: ", "")
    .replace(" cited sections extracted", " sections")
    .replace(" loaded", "");
}
