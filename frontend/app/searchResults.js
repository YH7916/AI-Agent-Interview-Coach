import { scoreLabel } from "./format.js";
import { escapeHtml } from "./markdown.js";

export function renderSearchResults(results, resultTitle) {
  const displayedResults = results.slice(0, 3);
  const empty = `
    <article class="notice-card result-enter">
      <strong>No matching SOP found</strong>
      <p>Try a concrete incident keyword such as OOM, CDN, P0, 黑客攻击, or 模型。</p>
    </article>
  `;

  document.querySelector("#results").innerHTML = `
    <div class="section-heading result-enter">
      <h2>${escapeHtml(resultTitle)}</h2>
      <span>${displayedResults.length ? `${displayedResults.length} shown` : "empty"}</span>
    </div>
    <div class="result-list">
      ${
        displayedResults.length
          ? displayedResults
              .map(
                (item, index) => `
                  <button
                    type="button"
                    class="result-row sop-open-button"
                    data-sop-id="${escapeHtml(item.id)}"
                    data-sop-section="${escapeHtml(item.section || "")}"
                    style="--i: ${index}"
                  >
                    <span class="result-index">${index + 1}</span>
                    <div>
                      <h3>${escapeHtml(item.title)}</h3>
                      <p>${escapeHtml(item.snippet)}</p>
                      <small>${escapeHtml(item.id)} · score ${escapeHtml(scoreLabel(item.score))}</small>
                    </div>
                  </button>
                `,
              )
              .join("")
          : empty
      }
    </div>
  `;
}
