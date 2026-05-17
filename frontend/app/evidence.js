import { sopIdFromFile } from "./format.js";
import { escapeHtml } from "./markdown.js";

export function renderEvidence(evidence) {
  if (!evidence.length) {
    return "";
  }
  const cards = evidence;
  const hasScrollableEvidence = cards.length > 3;
  return `
    <section class="evidence-section" aria-label="引用 SOP">
      <div class="evidence-section-header">
        <span>引用 SOP</span>
        <small>${cards.length} 条</small>
      </div>
      <div class="evidence-carousel">
        <div
          class="evidence-strip"
          data-evidence-strip
          tabindex="0"
          aria-label="引用 SOP 卡片"
        >
          ${cards.map((item, index) => `
          <button
            type="button"
            class="evidence-card sop-open-button"
            data-sop-id="${escapeHtml(sopIdFromFile(item.file))}"
            data-sop-section="${escapeHtml(item.section)}"
            style="--i: ${index}"
          >
            <small>${escapeHtml(item.file)}</small>
            <h3>${escapeHtml(item.section)}</h3>
            <p>${escapeHtml(item.text)}</p>
          </button>
          `).join("")}
        </div>
        ${
          hasScrollableEvidence
            ? `
              <button
                type="button"
                class="evidence-nav-button evidence-nav-prev"
                data-evidence-direction="-1"
                aria-label="查看上一组引用 SOP"
                disabled
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="m15 18-6-6 6-6"></path>
                </svg>
              </button>
              <button
                type="button"
                class="evidence-nav-button evidence-nav-next"
                data-evidence-direction="1"
                aria-label="查看下一组引用 SOP"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="m9 18 6-6-6-6"></path>
                </svg>
              </button>
            `
            : ""
        }
      </div>
      ${
        hasScrollableEvidence
          ? `
            <div class="evidence-pagebar" data-evidence-pagebar aria-hidden="true">
              ${cards.map((_item, index) => `
                <span class="${index === 0 ? "is-active" : ""}"></span>
              `).join("")}
            </div>
          `
          : ""
      }
    </section>
  `;
}

export function setupEvidenceCarousel(root) {
  root.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const trigger = event.target.closest("[data-evidence-direction]");
    if (!trigger) {
      return;
    }
    const section = trigger.closest(".evidence-section");
    const strip = section?.querySelector("[data-evidence-strip]");
    if (!(strip instanceof HTMLElement)) {
      return;
    }
    event.preventDefault();
    scrollEvidenceStrip(strip, Number(trigger.dataset.evidenceDirection || 1));
  });

  root.addEventListener(
    "wheel",
    (event) => {
      if (!(event.target instanceof Element)) {
        return;
      }
      const strip = event.target.closest("[data-evidence-strip]");
      if (!(strip instanceof HTMLElement)) {
        return;
      }
      const horizontalDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY)
        ? event.deltaX
        : event.deltaY;
      if (!horizontalDelta || !canScrollEvidence(strip, horizontalDelta)) {
        return;
      }
      event.preventDefault();
      strip.scrollBy({ left: horizontalDelta, behavior: "auto" });
      requestAnimationFrame(() => updateEvidenceCarousel(strip));
    },
    { passive: false },
  );

  root.addEventListener(
    "scroll",
    (event) => {
      if (event.target instanceof HTMLElement && event.target.matches("[data-evidence-strip]")) {
        updateEvidenceCarousel(event.target);
      }
    },
    true,
  );
}

function scrollEvidenceStrip(strip, direction) {
  strip.scrollBy({
    left: direction * strip.clientWidth,
    behavior: "smooth",
  });
  requestAnimationFrame(() => updateEvidenceCarousel(strip));
}

function canScrollEvidence(strip, delta) {
  if (delta > 0) {
    return strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1;
  }
  return strip.scrollLeft > 0;
}

function updateEvidenceCarousel(strip) {
  const section = strip.closest(".evidence-section");
  if (!section) {
    return;
  }
  const maxScroll = Math.max(1, strip.scrollWidth - strip.clientWidth);
  const pagebar = section.querySelector("[data-evidence-pagebar]");
  const pageItems = pagebar ? [...pagebar.querySelectorAll("span")] : [];
  const prevButton = section.querySelector('[data-evidence-direction="-1"]');
  const nextButton = section.querySelector('[data-evidence-direction="1"]');
  const activeIndex = evidenceActiveDotIndex(strip);
  pageItems.forEach((item, index) => {
    item.classList.toggle("is-active", index === activeIndex);
  });
  if (prevButton instanceof HTMLButtonElement) {
    prevButton.disabled = activeIndex <= 0;
  }
  if (nextButton instanceof HTMLButtonElement) {
    nextButton.disabled = activeIndex >= pageItems.length - 1 || strip.scrollLeft >= maxScroll - 1;
  }
}

function evidenceDotCount(strip) {
  const section = strip.closest(".evidence-section");
  return section?.querySelectorAll("[data-evidence-pagebar] span").length || 1;
}

function evidenceActiveDotIndex(strip) {
  const dotCount = evidenceDotCount(strip);
  if (dotCount <= 1) {
    return 0;
  }
  const maxScroll = Math.max(1, strip.scrollWidth - strip.clientWidth);
  return Math.round((strip.scrollLeft / maxScroll) * (dotCount - 1));
}
