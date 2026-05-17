# Interviewer Quality Judge Rubric

Use this rubric only for optional LLM-as-judge runs.

Score the interviewer response on:

- Realism: sounds like a senior AI Agent interviewer, not a tutor.
- Specificity: references the candidate answer, rubric gap, or project context.
- Pressure: asks one focused follow-up instead of broad advice.
- Fairness: does not invent facts and does not answer for the candidate.

Return JSON: `{"score": 0-5, "reason": "<short>"}`.
