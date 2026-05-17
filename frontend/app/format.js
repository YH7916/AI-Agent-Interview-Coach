export function scoreLabel(score) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) {
    return String(score);
  }
  return numeric.toFixed(numeric >= 10 ? 0 : 2);
}

export function sopIdFromFile(value) {
  return String(value || "").replace(/\.html$/i, "");
}

export function sectionKey(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}
