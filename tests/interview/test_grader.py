"""Interview grader tests."""

import unittest

from oncall_app.interview.grader import InterviewGrader
from oncall_app.interview.models import InterviewQuestion


class InterviewGraderTest(unittest.TestCase):
    def test_strong_agent_eval_answer_scores_higher_than_vague_answer(self):
        question = InterviewQuestion(
            question="Agent 评估体系怎么做？",
            source_snapshot_id="src",
            source_uri="source.md",
            normalized_question="agenteval",
            topic="agent_eval",
        )
        grader = InterviewGrader()

        vague = grader.grade(question, "看最终答案对不对，人工看看。")
        strong = grader.grade(
            question,
            "我会把 eval 拆成 task、trial、transcript 和 outcome。"
            "先用 deterministic grader 检查工具调用、状态变化和引用覆盖，"
            "再用 rubric judge 评分沟通质量，并抽样人工校准。",
        )

        self.assertLess(vague.score_total, strong.score_total)
        self.assertIn("outcome", strong.feedback)
        self.assertNotIn("总分", strong.feedback)
        self.assertEqual(strong.scores[0].label, "概念准确")
        self.assertTrue(strong.scores[0].criterion)
        self.assertIn("命中", strong.scores[0].reason)

    def test_generates_follow_up_for_missing_tradeoff(self):
        question = InterviewQuestion(
            question="RAG 召回失败怎么排查？",
            source_snapshot_id="src",
            source_uri="source.md",
            normalized_question="rag",
            topic="rag",
        )
        result = InterviewGrader().grade(
            question,
            "query 先切 chunk，用 BM25、rerank、top_k 建候选，通过 API trace 记录，"
            "再用 eval、outcome、transcript 做回归。",
        )

        self.assertIn("追问", result.follow_up)
        self.assertIn("top_k", result.follow_up)
        tradeoff = next(item for item in result.scores if item.dimension == "tradeoff_depth")
        self.assertEqual(tradeoff.label, "取舍深度")
        self.assertIn("缺少", tradeoff.reason)

    def test_memory_follow_ups_are_question_specific_and_human(self):
        grader = InterviewGrader()
        full_save = grader.grade(
            InterviewQuestion(
                question="对话记忆是否全保存？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="memory-full-save",
                topic="memory",
            ),
            "那肯定不能",
        )
        raw_or_tag = grader.grade(
            InterviewQuestion(
                question="Q8：记忆存原始语料还是标签片段？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="memory-raw-tag",
                topic="memory",
            ),
            "片段",
        )
        stuck = grader.grade(
            InterviewQuestion(
                question="Memory 怎么设计？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="memory-design",
                topic="memory",
            ),
            "不会",
        )

        self.assertNotEqual(full_save.follow_up, raw_or_tag.follow_up)
        self.assertIn("全保存", full_save.follow_up)
        self.assertIn("原文", raw_or_tag.follow_up)
        self.assertIn("这题先记为不会", stuck.feedback)
        self.assertNotIn("0/10", stuck.feedback)


if __name__ == "__main__":
    unittest.main()
