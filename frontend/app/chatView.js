import { renderEvidence } from "./evidence.js";
import { escapeHtml, renderMarkdown } from "./markdown.js";
import { renderInlineTrace } from "./trace.js";

export function renderChatConversation(turns, options) {
  return `
    <div class="agent-layout chat-agent-layout result-enter">
      <section class="answer-panel chat-thread-panel">
        <div class="chat-list">
          ${turns.map((turn, index) => renderChatTurn(turn, index, options)).join("")}
        </div>
      </section>
    </div>
  `;
}

export function renderAssistantBody(turn, placeholderForTurn, _options = {}) {
  return `
    ${
      turn.content
        ? renderMarkdown(turn.content)
        : `<p class="stream-placeholder">${escapeHtml(placeholderForTurn(turn))}</p>`
    }
    ${turn.streaming ? `<span class="stream-cursor" aria-hidden="true"></span>` : ""}
  `;
}

function renderChatTurn(turn, index, options) {
  if (turn.role === "pending") {
    return `
      <div class="loading-row chat-loading" style="--i: ${index}">
        <span class="spinner" aria-hidden="true"></span>
        <span>${escapeHtml(turn.content)}</span>
      </div>
    `;
  }
  if (turn.role === "error") {
    return `
      <article class="notice-card chat-message" style="--i: ${index}">
        <strong>Request failed</strong>
        <p>${escapeHtml(turn.content)}</p>
      </article>
    `;
  }
  if (turn.role === "user") {
    return `
      <article class="chat-message chat-message-user" style="--i: ${index}">
        <p>${escapeHtml(turn.content)}</p>
      </article>
    `;
  }
  if (turn.role === "interviewer") {
    return `
      <article class="chat-message chat-message-interviewer" style="--i: ${index}">
        ${turn.progress ? `<span>${escapeHtml(turn.progress)}</span>` : ""}
        <p>${escapeHtml(turn.content)}</p>
      </article>
    `;
  }
  return `
    <article class="chat-message chat-message-assistant" data-turn-index="${index}" style="--i: ${index}">
      ${renderInlineTrace(turn, options.showTrace && !options.compactInterview)}
      ${renderAssistantMain(turn, options)}
      ${!options.compactInterview && turn.coaching ? `<div class="coaching-card">${escapeHtml(turn.coaching)}</div>` : ""}
      ${!options.compactInterview && turn.followUp && !turn.followUpQueued ? `<div class="follow-up-card">${escapeHtml(turn.followUp)}</div>` : ""}
      ${renderEvidence(turn.evidence || [])}
    </article>
  `;
}

function renderAssistantMain(turn, options) {
  const body = renderAssistantBody(turn, options.placeholderForTurn, options).trim();
  if (!body) {
    return "";
  }
  return `<div class="markdown-body">${body}</div>`;
}
