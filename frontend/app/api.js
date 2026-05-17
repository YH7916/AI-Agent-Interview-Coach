import { readSseStream } from "./sse.js";

export async function fetchProviderStatus() {
  const response = await fetch("/provider-status");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchProviderConfig() {
  const response = await fetch("/provider-config");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function saveProviderConfig(payload) {
  const response = await fetch("/provider-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchSearchResults(endpoint, query) {
  const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function streamChat(endpoint, message, history, onEvent, options = {}) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history,
      session_id: options.sessionId || "default",
    }),
  });
  if (!response.ok) {
    throw new Error(await requestErrorMessage(response));
  }
  await readSseStream(response, onEvent);
}

export async function streamInterviewAnswer(endpoint, payload, onEvent) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await requestErrorMessage(response));
  }
  await readSseStream(response, onEvent);
}

async function requestErrorMessage(response) {
  const payload = await response.json().catch(() => null);
  if (payload?.detail) {
    return `HTTP ${response.status}: ${formatErrorDetail(payload.detail)}`;
  }
  return `HTTP ${response.status}`;
}

function formatErrorDetail(detail) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "";
        const message = item?.msg || JSON.stringify(item);
        return field ? `${field}: ${message}` : message;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

export async function importInterviewSources() {
  const response = await fetch("/interview/sources/import", { method: "POST" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewQuestions(topic = "") {
  const suffix = topic ? `?topic=${encodeURIComponent(topic)}` : "";
  const response = await fetch(`/interview/questions${suffix}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function importInterviewTextSource({ text, title, sourceUri }) {
  const response = await fetch("/interview/sources/import-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      title: title || "题库页采集",
      source_uri: sourceUri || "manual://question-bank-dialog",
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewSessionPlan(size = 5) {
  const response = await fetch(`/interview/session-plan?size=${encodeURIComponent(size)}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewReview() {
  const response = await fetch("/interview/review");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewSessionSummary(sessionId) {
  const response = await fetch(
    `/interview/sessions/${encodeURIComponent(sessionId)}/summary`,
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewSessionReport(sessionId) {
  const response = await fetch(
    `/interview/sessions/${encodeURIComponent(sessionId)}/report`,
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewWebLogins() {
  const response = await fetch("/interview/web-login");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewSourcePlatforms() {
  const response = await fetch("/interview/source-platforms");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewResume() {
  const response = await fetch("/interview/resume");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function importDefaultInterviewResume() {
  const response = await fetch("/interview/resume/import-default", { method: "POST" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function uploadInterviewResume(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/interview/resume/upload", {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchInterviewSourcePlatformLatestJob(platformId) {
  const response = await fetch(
    `/interview/source-platforms/${encodeURIComponent(platformId)}/jobs/latest`,
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function syncInterviewSourcePlatform(platformId, options = {}) {
  const response = await fetch(
    `/interview/source-platforms/${encodeURIComponent(platformId)}/sync`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        dry_run: Boolean(options.dryRun),
        since_days: options.sinceDays || null,
        max_pages: options.maxPages || null,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function openInterviewSourcePlatformLogin(platformId) {
  const response = await fetch(
    `/interview/source-platforms/${encodeURIComponent(platformId)}/open-login`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function openInterviewBrowserLogin(url) {
  const response = await fetch("/interview/browser/open-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function importInterviewWebUrl(url) {
  const response = await fetch("/interview/sources/import-web", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function forgetInterviewSourcePlatform(platformId) {
  const response = await fetch(`/interview/source-platforms/${encodeURIComponent(platformId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function forgetInterviewWebLogin(host) {
  const response = await fetch(`/interview/web-login/${encodeURIComponent(host)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function searchMemories(query) {
  const response = await fetch(`/v3/memory/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentDetail(docId) {
  const response = await fetch(`/documents/${encodeURIComponent(docId)}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}
