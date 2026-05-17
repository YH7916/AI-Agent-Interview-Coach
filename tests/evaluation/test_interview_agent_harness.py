"""Tests for isolated interview-agent eval harness."""

import unittest

from oncall_app.evaluation.interview_agent_cases import EvalCase, EvalExpected, EvalInput
from oncall_app.evaluation.interview_agent_harness import run_eval_case


class InterviewAgentHarnessTests(unittest.TestCase):
    """The harness should run cases without leaking state between trials."""

    def test_runs_interview_case_and_captures_transcript(self) -> None:
        case = EvalCase(
            case_id="harness-1",
            suite="regression",
            input=EvalInput(
                question="L0-L3 记忆系统怎么设计？",
                answer="L0 raw event，L1 事实，L2 场景，L3 profile；要处理冲突、过期和来源链，并用 eval 指标验证。",
                resume_text="候选人做过 v3 Agent、RAG、Memory 和 Eval。",
                topic="memory",
            ),
            expected=EvalExpected(min_score=6, max_score=10),
            graders=("score_band", "tool_coverage"),
        )

        trial = run_eval_case(case, trial_index=0)

        self.assertEqual(trial.case_id, "harness-1")
        self.assertEqual(trial.trial_index, 0)
        self.assertGreaterEqual(trial.score_total, 6)
        self.assertTrue(trial.follow_up.startswith("追问：") or trial.follow_up == "")
        self.assertIn("director_decision", trial.event_types)
        self.assertIn("persist_interview_turn", trial.tool_names)
        self.assertGreater(trial.latency_ms, 0)
        self.assertEqual(trial.raw_answer_leakage, 0)

    def test_runs_source_case_and_extracts_expected_questions(self) -> None:
        case = EvalCase(
            case_id="source-1",
            suite="source",
            input=EvalInput(
                html="""
                <html><body>
                  <a class="post-title" href="/p/1">Agent 记忆系统怎么做？</a>
                  <div>打开APP查看更多</div>
                  <a class="post-title" href="/p/2">RAG 召回失败怎么排查？</a>
                </body></html>
                """,
                source_url="https://www.nowcoder.com/search?query=AI%20Agent",
                source_title="牛客搜索",
            ),
            expected=EvalExpected(
                expected_questions=("Agent 记忆系统怎么做？", "RAG 召回失败怎么排查？"),
            ),
            graders=("source_precision", "source_recall"),
        )

        trial = run_eval_case(case, trial_index=1)

        self.assertEqual(trial.extracted_questions, case.expected.expected_questions)
        self.assertEqual(trial.source_precision, 1.0)
        self.assertEqual(trial.source_recall, 1.0)


if __name__ == "__main__":
    unittest.main()
