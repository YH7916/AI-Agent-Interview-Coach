export function applyChatStreamEvent(turn, event) {
  const data = event.data || {};
  if (event.type === "question") {
    turn.trace = [
      ...(turn.trace || []),
      { type: "question", message: data.question || "interview question selected" },
    ];
    return "full";
  }
  if (event.type === "thought") {
    turn.trace = [
      ...(turn.trace || []),
      { type: "thought", message: data.message || "继续判断下一步动作" },
    ];
    return "full";
  }
  if (event.type === "retrieval") {
    const files = (data.candidates || []).map((item) => item.file).join(", ");
    turn.trace = [
      ...(turn.trace || []),
      {
        type: "retrieval",
        message: files ? `v2 hybrid retrieval candidates: ${files}` : "no candidates",
      },
    ];
    return "full";
  }
  if (event.type === "tool_call") {
    turn.toolCalls = [
      ...(turn.toolCalls || []),
      { tool: data.tool || "tool", input: data.input || data.fname || "" },
    ];
    turn.trace = [
      ...(turn.trace || []),
      { type: "tool_call", message: formatToolCallMessage(data) },
    ];
    return "full";
  }
  if (event.type === "tool_result") {
    turn.trace = [
      ...(turn.trace || []),
      {
        type: "tool_result",
        message: data.message || `${data.tool || "tool"} finished`,
        tool: data.tool || "tool",
      },
    ];
    return "full";
  }
  if (event.type === "memory") {
    turn.memoryHits = data.items || [];
    turn.trace = [
      ...(turn.trace || []),
      {
        type: "memory",
        message: turn.memoryHits.length
          ? `recalled ${turn.memoryHits.length} memories`
          : "no memory context",
      },
    ];
    return "full";
  }
  if (event.type === "observation") {
    turn.trace = [
      ...(turn.trace || []),
      { type: "observation", message: `${data.fname || "context"} loaded (${data.chars || 0} chars)` },
    ];
    return "full";
  }
  if (event.type === "evidence") {
    turn.evidence = data.items || [];
    turn.trace = [
      ...(turn.trace || []),
      { type: "evidence", message: `${turn.evidence.length} cited sections extracted` },
    ];
    return "full";
  }
  if (event.type === "grade") {
    turn.grade = data;
    turn.trace = [
      ...(turn.trace || []),
      { type: "grade", message: "AI 评价已生成" },
    ];
    return "full";
  }
  if (event.type === "director_decision") {
    turn.interviewAction = data.action || "";
    turn.focusAreas = data.focus_areas || [];
    turn.trace = [
      ...(turn.trace || []),
      {
        type: "director",
        message: data.action === "follow_up" ? "继续围绕当前题追问" : "当前题可以进入下一步",
      },
    ];
    return "full";
  }
  if (event.type === "follow_up") {
    turn.followUp = data.message || "";
    return "content";
  }
  if (event.type === "coaching") {
    turn.coaching = data.message || "";
    return "content";
  }
  if (event.type === "answer_delta") {
    turn.content = `${turn.content || ""}${data.delta || ""}`;
    return "content";
  }
  if (event.type === "done") {
    turn.streaming = false;
    turn.content = data.answer || turn.content || "";
    if (turn.grade) {
      turn.grade.feedback = data.feedback || turn.grade.feedback || "";
      turn.grade.follow_up = data.follow_up || turn.grade.follow_up || "";
    }
    turn.evidence = data.evidence || turn.evidence || [];
    turn.trace = mergeTraceEvents(turn.trace || [], data.trace || []);
    turn.toolCalls = data.tool_calls || turn.toolCalls || [];
    turn.memoryHits = data.memory_hits || turn.memoryHits || [];
    turn.coaching = data.coaching || turn.coaching || "";
    return "full";
  }
  if (event.type === "warning") {
    turn.trace = [
      ...(turn.trace || []),
      { type: "warning", message: data.message || "Agent finished with a fallback answer" },
    ];
    return "full";
  }
  if (event.type === "error") {
    applyChatFailure(turn, data.message || "Streaming request failed");
  }
  return "full";
}

export function applyChatFailure(turn, message) {
  turn.streaming = false;
  if (hasPartialAgentState(turn)) {
    turn.trace = [
      ...(turn.trace || []),
      { type: "error", message },
    ];
    if (!turn.content) {
      turn.content = `模型调用失败：${message}`;
    }
    return;
  }
  turn.role = "error";
  turn.content = message;
}

function mergeTraceEvents(existingTrace, finalTrace) {
  const seen = new Set();
  return [...existingTrace, ...finalTrace].filter((item) => {
    const key = `${item.type}:${item.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function formatToolCallMessage(data) {
  const tool = data.tool || "tool";
  const input = data.input || data.fname || "";
  return input ? `${tool}(${input})` : `${tool}()`;
}

function hasPartialAgentState(turn) {
  return Boolean(
    turn.content
      || (turn.evidence || []).length
      || (turn.trace || []).length
      || (turn.toolCalls || []).length
      || (turn.memoryHits || []).length,
  );
}
