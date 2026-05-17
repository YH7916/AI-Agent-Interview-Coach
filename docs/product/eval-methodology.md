# Interview Agent Eval Methodology

The eval system follows a product question: did the interview coach become more useful and less risky? It does not grade only the final natural-language answer.

## Suites

`regression` is the release blocker. It covers behavior that should not drift: realistic follow-up terms, expected score bands, no SOP/on-call leakage from old phases, no raw-answer leakage in summaries, and required interview tools being used.

`capability` is the improvement meter. It contains harder prompts where the model should apply pressure, connect to resume evidence, and produce specific coaching. The first product release reports this score; future releases should block large regressions against a saved baseline.

`source` is the ingestion gate. It runs fixed HTML fixtures through the source pipeline and checks extracted interview questions, precision/recall, duplicate merge behavior, and quality counters.

## Grader Layers

- Case schema validation catches malformed eval data before a run starts.
- Harness checks run in isolated SQLite stores so one trial cannot poison another.
- Deterministic graders verify score bands, required terms, forbidden terms, source precision/recall, raw-answer redaction, and tool coverage.
- Transcript graders inspect intermediate events and persisted session state, not just the last text response.
- Rubric Markdown files document optional LLM-judge criteria for realism, pressure, specificity, fairness, and source usefulness.

## Commands

```powershell
python scripts\evaluate_interview_agent.py --suite regression
python scripts\evaluate_interview_agent.py --suite capability --trials 3
python scripts\evaluate_interview_agent.py --suite source
python scripts\evaluate_interview_agent.py --suite all --json-out artifacts\evals\latest.json
```

The packaging script runs the all-suite gate and writes `artifacts\evals\latest.json`.

## Product Thresholds

- Regression overall pass rate should stay at or above `0.95`.
- Raw-answer leakage must be `0`.
- Forbidden term violations must be `0`.
- Source precision and recall on fixtures should stay high enough to catch adapter regressions before users see polluted question banks.
- Capability score is tracked as a trend. Treat a drop larger than `0.05` from the last accepted baseline as a release review trigger.

## Reading Failures

Start with failed case ids, then inspect transcript fields and source fixture metrics. A failure should normally map to one owner:

- Prompt/director regression: follow-up terms, realism, or score-band drift.
- Tool orchestration regression: missing tool coverage, missing memory writes, or broken session state.
- Source ingestion regression: precision/recall, duplicate merge, fallback pages, or low quality messages.
- Product privacy regression: raw answers appearing in summaries, reports, or list APIs.
