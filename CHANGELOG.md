# Changelog

## v0.1.1 - 2026-05-17

Patch release for source collection quality and speed.

- Default source search now uses the higher-intent query `agent 面经` instead of three broad interview-topic searches.
- Source collection now reuses an authenticated browser session for detail pages and removes per-action slow motion by default.
- Detail pages are validated before import so search-result aggregate text cannot pollute the question bank.
- Collection reports now describe the execution mode as a login-state browser session.

## v0.1.0 - 2026-05-17

Initial standalone product release of AI Agent Interview Coach.

- Desktop app packaging with Tauri and a PyInstaller Python sidecar.
- Dialog-first AI Agent interview coach for free chat, mock interviews, question explanation, and source collection commands.
- Local question bank with resume upload/import, source attribution, dedupe, quality filtering, and review summaries.
- Authorized browser login-state management for Nowcoder, Xiaohongshu, and Zhihu.
- Observable source collection with visible-browser progress, accepted/rejected candidates, and saved source-page artifacts.
- Short-term session memory plus layered long-term memory for interview preferences, weak points, and recall.
- Offline regression, source-quality, memory, and product eval gates.
