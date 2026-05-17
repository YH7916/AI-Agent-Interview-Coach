import { MAX_HISTORY_ENTRIES, MODES } from "./config.js";

const SETTINGS_STORAGE_KEY = "oncall-copilot-settings";
const HISTORY_STORAGE_KEY = "oncall-copilot-history";
const HISTORY_TITLE_CHARS = 48;

export function loadUserSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || "{}");
    return {
      showTrace: saved.showTrace === true,
      sectionJump: saved.sectionJump !== false,
      historyOpen: saved.historyOpen === true,
      settingsOpen: saved.settingsOpen === true,
    };
  } catch (_error) {
    return { showTrace: false, sectionJump: true, historyOpen: false, settingsOpen: false };
  }
}

export function saveUserSettings(settings) {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}

export function loadHistoryEntries() {
  try {
    const saved = JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) || "[]");
    if (!Array.isArray(saved)) {
      return [];
    }
    return saved
      .filter((entry) => MODES[entry?.mode] && entry.id && entry.title)
      .slice(0, MAX_HISTORY_ENTRIES);
  } catch (_error) {
    return [];
  }
}

export function saveHistoryEntries(entries) {
  localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
}

export function createHistoryId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `history-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function compactHistoryTitle(value) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "Untitled";
  }
  if (normalized.length <= HISTORY_TITLE_CHARS) {
    return normalized;
  }
  return `${normalized.slice(0, HISTORY_TITLE_CHARS - 1)}...`;
}
