"""Interview director prompt tests."""

import unittest

from oncall_app.interview.director import InterviewDirector
from oncall_app.interview.grader import InterviewGrader
from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.prompts import INTERVIEW_DIRECTOR_SYSTEM_PROMPT


class InterviewDirectorTest(unittest.TestCase):
    def test_prompt_is_interview_specific_not_sop_agent(self):
        self.assertIn("senior AI Agent interviewer", INTERVIEW_DIRECTOR_SYSTEM_PROMPT)
        self.assertIn("Return only valid JSON", INTERVIEW_DIRECTOR_SYSTEM_PROMPT)
        self.assertIn("Do not mention SOPs", INTERVIEW_DIRECTOR_SYSTEM_PROMPT)
        self.assertIn("resume_alignment", INTERVIEW_DIRECTOR_SYSTEM_PROMPT)

    def test_uses_llm_json_decision_when_available(self):
        class FakeChatClient:
            def create_chat_completion(self, messages, tools):
                self.messages = messages
                self.tools = tools
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"action":"follow_up","interviewer_message":"你提到了 L0-L3，'
                                    '但还没讲冲突处理。","follow_up":"冲突记忆怎么覆盖？",'
                                    '"coaching":"补冲突和过期策略。","target_topic":"memory",'
                                    '"rubric_focus":["tradeoff_depth"]}'
                                )
                            }
                        }
                    ]
                }

        question = _question()
        grade = InterviewGrader().grade(question, "L0 L1 L2 L3 profile。")
        client = FakeChatClient()

        decision = InterviewDirector(client).direct_turn(question, "L0 L1 L2 L3 profile。", grade, {}, [], [])

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.follow_up, "冲突记忆怎么覆盖？")
        self.assertEqual(client.tools, [])
        self.assertIn("candidate_answer", client.messages[1]["content"])

    def test_falls_back_to_deterministic_rubric_when_llm_json_is_invalid(self):
        class BadChatClient:
            def create_chat_completion(self, messages, tools):
                del messages, tools
                return {"choices": [{"message": {"content": "not json"}}]}

        question = _question()
        grade = InterviewGrader().grade(question, "把历史消息存起来。")

        decision = InterviewDirector(BadChatClient()).direct_turn(question, "把历史消息存起来。", grade, {}, [], [])

        self.assertEqual(decision.source, "fallback")
        self.assertTrue(decision.follow_up.startswith("追问："))

    def test_falls_back_when_llm_provider_errors(self):
        class FailingChatClient:
            def create_chat_completion(self, messages, tools):
                del messages, tools
                raise RuntimeError("provider 502")

        question = _question()
        grade = InterviewGrader().grade(question, "把历史消息存起来。")

        decision = InterviewDirector(FailingChatClient()).direct_turn(question, "把历史消息存起来。", grade, {}, [], [])

        self.assertEqual(decision.source, "fallback")
        self.assertTrue(decision.interviewer_message)

    def test_fallback_coaching_uses_resume_alignment(self):
        question = _question()
        grade = InterviewGrader().grade(question, "把历史消息存起来。")
        context = {
            "resume_alignment": {
                "available": True,
                "matched_terms": ["Agent", "memory"],
            }
        }

        decision = InterviewDirector().direct_turn(question, "把历史消息存起来。", grade, context, [], [])

        self.assertIn("简历", decision.coaching)
        self.assertIn("Agent", decision.coaching)


def _question() -> InterviewQuestion:
    return InterviewQuestion(
        question="L0-L3 记忆系统怎么设计？",
        source_snapshot_id="src",
        source_uri="source.md",
        normalized_question="memory",
        topic="memory",
    )


if __name__ == "__main__":
    unittest.main()
