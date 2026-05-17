# AI Agent Interview Coach Release Checklist

Use this checklist before calling a build product-ready. The goal is to verify the installed product path, not just the development server.

## Automated Gate

Run from `question-1/`:

```powershell
python -m ruff check .
python -m mypy oncall_app
python -m unittest discover -v
npm run lint:frontend
python scripts\evaluate.py
python scripts\evaluate_interview.py
python scripts\evaluate_interview_agent.py --suite all --json-out artifacts\evals\latest.json
powershell -ExecutionPolicy Bypass -File scripts\package_desktop.ps1
```

If Rust/Cargo is unavailable on the machine, run the same packaging script with `-SkipTauriBuild` and record that the Tauri installer was not produced in this environment.

## Manual Product Flow

1. Install or launch the packaged desktop app.
2. Confirm the app opens directly to `/v3`.
3. Open the `来源` page.
4. Import the default resume or upload a resume from the page.
5. Open the 牛客 login window.
6. Complete login and close the browser window.
7. Confirm the source card shows authorized state, or an actionable `uncertain`/`rejected` login probe reason.
8. Start source sync.
9. Confirm the job reports useful quality metrics: pages, questions, added, duplicate, quality message.
10. Confirm imported questions appear in the question bank and repeated questions merge frequency rather than duplicating cards.
11. Run a 3-question mock interview.
12. Answer at least one follow-up and confirm it stays in the same interview flow.
13. End the interview and open `复盘`.
14. Confirm the summary groups initial answers and follow-ups by question.
15. Export or view the session report and confirm raw answers are not exposed in API previews.
16. Reopen the app and confirm the latest source job and interview history are still visible.

## Release Blockers

- Desktop app requires a manual Python server.
- Source sync cannot explain login failure or source quality.
- One-question-only interview behavior returns.
- Review duplicates one answered question as multiple independent review items.
- Regression eval leaks raw answers, hits forbidden terms, or loses required tool coverage.
- Packaging leaves orphan sidecar processes after closing the app.
