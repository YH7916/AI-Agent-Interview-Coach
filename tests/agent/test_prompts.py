"""Prompt contract tests."""

import unittest

from oncall_app.agent.prompts import SYSTEM_PROMPT


class PromptContractTest(unittest.TestCase):
    """The Agent prompt keeps generated answers concise and interview-friendly."""

    def test_system_prompt_requires_concise_scannable_answers(self):
        """Output style is constrained at the prompt layer."""
        self.assertIn("Answer style contract", SYSTEM_PROMPT)
        self.assertIn("120-350 Chinese characters", SYSTEM_PROMPT)
        self.assertIn("do not exceed 450 Chinese characters", SYSTEM_PROMPT)
        self.assertIn("3-4 concrete actions", SYSTEM_PROMPT)
        self.assertIn("citations inline and short", SYSTEM_PROMPT)
        self.assertIn("Do not repeat the same citation", SYSTEM_PROMPT)
        self.assertIn("Use compact Markdown tables", SYSTEM_PROMPT)
        self.assertIn("2-4 columns and 2-5 rows", SYSTEM_PROMPT)
        self.assertIn("answer only the most likely incident domain", SYSTEM_PROMPT)
        self.assertIn("Prefer reading 1-2 SOP files", SYSTEM_PROMPT)
        self.assertIn("Do not add greetings", SYSTEM_PROMPT)

    def test_system_prompt_preserves_tool_and_sop_boundaries(self):
        """Conciseness instructions do not weaken the tool-use constraints."""
        self.assertIn("Use only the readFile tool", SYSTEM_PROMPT)
        self.assertIn("provided hybrid retrieval candidates", SYSTEM_PROMPT)
        self.assertIn("Do not read index files", SYSTEM_PROMPT)
        self.assertIn("For P0 questions, read multiple relevant SOP files", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
