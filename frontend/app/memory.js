import { escapeHtml } from "./markdown.js";

export function renderMemoryTrace(memoryHits = []) {
  if (!memoryHits.length) {
    return "";
  }
  const items = memoryHits
    .slice(0, 4)
    .map(
      (hit) => `
        <li>
          <span>${escapeHtml(hit.layer || "memory")} / ${escapeHtml(hit.kind || "context")}</span>
          <strong>${escapeHtml(hit.summary || "")}</strong>
        </li>
      `,
    )
    .join("");
  return `<ul class="memory-hit-list">${items}</ul>`;
}
