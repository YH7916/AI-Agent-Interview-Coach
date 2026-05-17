export function createReviewModel(historyEntries, chatTurns, activeHistoryId = "", serverReview = null) {
  if (serverReview && Array.isArray(serverReview.items)) {
    return createServerReviewModel(serverReview);
  }
  const items = collectReviewItems(historyEntries, chatTurns, activeHistoryId);
  return {
    completed: items.length,
    aiEvaluations: items.filter((item) => item.aiReview).length,
    followUps: items.filter((item) => item.followUp).length,
    recent: items.slice(0, 5).length,
    items: items.slice(0, 8),
  };
}

function createServerReviewModel(serverReview) {
  const items = serverReview.items.map((item) => ({
    key: item.key || item.turn_id,
    question: item.question || "模拟面试",
    aiReview: item.ai_review || item.feedback || item.coaching || item.follow_up || "",
    followUp: item.follow_up || "",
    coaching: item.coaching || "",
    attempts: Number(item.attempts || 1),
    timestamp: Date.parse(item.created_at || "") || 0,
  }));
  return {
    completed: Number(serverReview.completed || items.length),
    aiEvaluations: items.filter((item) => item.aiReview).length,
    followUps: items.filter((item) => item.followUp).length,
    recent: Number(serverReview.recent || items.slice(0, 5).length),
    items: items.slice(0, 8),
  };
}

function collectReviewItems(historyEntries, chatTurns, activeHistoryId) {
  const deduped = new Map();
  for (const item of [
    ...reviewItemsFromTurns(chatTurns, activeHistoryId || "live", Date.now()),
    ...historyEntries.flatMap((entry) =>
      reviewItemsFromTurns(entry.turns || [], entry.id, entry.updatedAt || entry.createdAt || 0),
    ),
  ]) {
    if (deduped.has(item.key)) {
      continue;
    }
    deduped.set(item.key, item);
  }
  return [...deduped.values()].sort((a, b) => b.timestamp - a.timestamp);
}

function reviewItemsFromTurns(turns, entryId, timestamp) {
  return turns
    .filter((turn) => turn.role === "assistant" && (turn.grade || turn.questionId || turn.followUp || turn.coaching))
    .map((turn) => reviewItemFromTurn(turn, entryId, timestamp));
}

function reviewItemFromTurn(turn, entryId, timestamp) {
  const question = latestQuestionTrace(turn) || turn.question || "模拟面试";
  const followUp = turn.followUp || turn.grade?.follow_up || "";
  const coaching = turn.coaching || "";
  const aiReview = turn.content || turn.grade?.feedback || coaching || followUp || "";
  return {
    key: turn.reviewKey || `${entryId}:${question}:${aiReview}:${followUp}:${coaching}`,
    question,
    aiReview,
    followUp,
    coaching,
    attempts: 1,
    timestamp: Number(timestamp) || 0,
  };
}

function latestQuestionTrace(turn) {
  return [...(turn.trace || [])].reverse().find((item) => item.type === "question")?.message || "";
}
