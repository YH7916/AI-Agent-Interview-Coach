import { fetchDocumentDetail } from "./api.js";
import { sectionKey, sopIdFromFile } from "./format.js";
import { escapeHtml } from "./markdown.js";

export function setupSopPreview(root, getSettings) {
  root.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const trigger = event.target.closest("[data-sop-id]");
    if (!trigger) {
      return;
    }
    event.preventDefault();
    openSopModal(trigger.dataset.sopId || "", trigger.dataset.sopSection || "", getSettings);
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    if (event.target.matches("[data-modal-close]")) {
      closeSopModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSopModal();
    }
  });
}

async function openSopModal(rawId, targetSection, getSettings) {
  const docId = sopIdFromFile(rawId);
  if (!docId) {
    return;
  }
  renderSopModal(`
    <header class="sop-modal-header">
      <div>
        <p>SOP preview</p>
        <h2 id="sop-modal-title">${escapeHtml(docId)}.html</h2>
      </div>
      <button type="button" class="sop-modal-close" data-modal-close aria-label="Close preview">×</button>
    </header>
    <div class="sop-modal-status">
      <span class="spinner" aria-hidden="true"></span>
      <span>Loading source</span>
    </div>
  `);

  try {
    const documentDetail = await fetchDocumentDetail(docId);
    renderSopModal(renderSopDocument(documentDetail, targetSection, getSettings));
    scrollToSopSection(targetSection, getSettings);
  } catch (error) {
    renderSopModal(`
      <header class="sop-modal-header">
        <div>
          <p>SOP preview</p>
          <h2 id="sop-modal-title">Unable to open ${escapeHtml(docId)}.html</h2>
        </div>
        <button type="button" class="sop-modal-close" data-modal-close aria-label="Close preview">×</button>
      </header>
      <div class="sop-modal-body">
        <article class="notice-card">
          <strong>Request failed</strong>
          <p>${escapeHtml(error.message || "Unknown error")}</p>
        </article>
      </div>
    `);
  }
}

function renderSopModal(innerHtml) {
  let root = document.querySelector("#sop-modal-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "sop-modal-root";
    document.body.append(root);
  }
  root.innerHTML = `
    <div class="sop-modal-backdrop" data-modal-close></div>
    <section class="sop-modal" role="dialog" aria-modal="true" aria-labelledby="sop-modal-title">
      ${innerHtml}
    </section>
  `;
  document.body.classList.add("modal-open");
  root.querySelector(".sop-modal-close")?.focus();
}

function renderSopDocument(documentDetail, targetSection, getSettings) {
  const targetKey = getSettings().sectionJump ? sectionKey(targetSection) : "";
  const sections = (documentDetail.sections || [])
    .filter((section) => String(section.text || "").trim())
    .map((section) => `
      <section
        class="sop-full-section${targetKey && sectionKey(section.heading) === targetKey ? " is-target" : ""}"
        data-section-key="${escapeHtml(sectionKey(section.heading))}"
      >
        <h3>${escapeHtml(section.heading || documentDetail.title)}</h3>
        <p>${escapeHtml(section.text)}</p>
      </section>
    `)
    .join("");

  return `
    <header class="sop-modal-header">
      <div>
        <p>${escapeHtml(documentDetail.file)}</p>
        <h2 id="sop-modal-title">${escapeHtml(documentDetail.title)}</h2>
      </div>
      <button type="button" class="sop-modal-close" data-modal-close aria-label="Close preview">×</button>
    </header>
    <div class="sop-modal-body">
      ${sections || `<p>${escapeHtml(documentDetail.text || "")}</p>`}
    </div>
  `;
}

function scrollToSopSection(targetSection, getSettings) {
  if (!getSettings().sectionJump) {
    return;
  }
  const key = sectionKey(targetSection);
  if (!key) {
    return;
  }
  requestAnimationFrame(() => {
    const target = document.querySelector(`[data-section-key="${CSS.escape(key)}"]`);
    target?.scrollIntoView({ block: "start", behavior: "smooth" });
  });
}

function closeSopModal() {
  const root = document.querySelector("#sop-modal-root");
  if (root) {
    root.remove();
  }
  document.body.classList.remove("modal-open");
}
