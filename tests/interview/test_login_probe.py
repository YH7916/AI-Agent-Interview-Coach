"""Tests for deterministic source login-state probing."""

import unittest

from oncall_app.interview.login_probe import LoginProbeResult, probe_login_state


class LoginProbeTests(unittest.TestCase):
    """Login probing should provide actionable verified/rejected/uncertain states."""

    def test_login_wall_is_rejected(self) -> None:
        result = probe_login_state(
            "<html><button>登录</button><p>请先登录后查看完整内容</p></html>",
            "https://www.nowcoder.com/discuss/1",
        )

        self.assertEqual(result.state, "rejected")
        self.assertEqual(result.confidence, "high")
        self.assertTrue(result.needs_login)

    def test_logged_in_markers_are_verified(self) -> None:
        result = probe_login_state(
            '<html><a href="/settings">账号设置</a><img class="avatar" src="me.png"></html>',
            "https://www.zhihu.com",
        )

        self.assertEqual(result.state, "verified")
        self.assertIn("avatar", result.indicators)

    def test_medium_confidence_can_use_llm_judge(self) -> None:
        def judge(html: str, final_url: str, indicators: tuple[str, ...]) -> LoginProbeResult:
            self.assertIn("消息", html)
            self.assertEqual(final_url, "https://www.xiaohongshu.com")
            self.assertIn("message-entry", indicators)
            return LoginProbeResult(
                state="verified",
                confidence="high",
                indicators=indicators,
                reason="LLM verified user menu",
                needs_login=False,
                llm_used=True,
            )

        result = probe_login_state(
            '<html><div class="message-entry">消息</div></html>',
            "https://www.xiaohongshu.com",
            llm_judge=judge,
        )

        self.assertEqual(result.state, "verified")
        self.assertTrue(result.llm_used)

    def test_uncertain_when_no_decisive_signal(self) -> None:
        result = probe_login_state("<html><main>公开内容</main></html>", "https://example.com")

        self.assertEqual(result.state, "uncertain")
        self.assertEqual(result.confidence, "low")


if __name__ == "__main__":
    unittest.main()
