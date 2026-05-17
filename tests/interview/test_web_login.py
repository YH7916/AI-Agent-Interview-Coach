"""Interview web-login boundary tests."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oncall_app.interview.browser_connector import DisabledBrowserConnector, _browser_headless
from oncall_app.interview.store import InterviewStore
from oncall_app.interview.web_login import detect_login_wall, normalize_host, profile_name_for_host


class InterviewWebLoginTest(unittest.TestCase):
    def test_host_normalization_and_profile_name_are_safe(self):
        self.assertEqual(normalize_host(" HTTPS://NowCoder.com/interview "), "nowcoder.com")
        self.assertEqual(normalize_host("https://www.xiaohongshu.com/explore"), "xiaohongshu.com")
        self.assertEqual(normalize_host("https://www.zhihu.com/question/1"), "zhihu.com")
        self.assertEqual(profile_name_for_host("www.xiaohongshu.com"), "web-fetch-www-xiaohongshu-com")

    def test_login_metadata_does_not_store_cookies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            store.upsert_web_login("nowcoder.com", Path(temp_dir) / "profiles" / "nowcoder")
            row = store.list_web_logins()[0]

            self.assertEqual(row["host"], "nowcoder.com")
            self.assertNotIn("cookie", str(row).casefold())

    def test_detects_login_wall_from_html(self):
        html = "<html><body><button>登录</button><div>请先登录后查看完整内容</div></body></html>"

        self.assertTrue(detect_login_wall(html, "https://www.nowcoder.com/discuss/1").needs_login)

    def test_plain_login_navigation_does_not_reject_content_page(self):
        html = "<main><a>登录</a><article>Agent eval 面经：如何设计 outcome grader？</article></main>"

        self.assertFalse(detect_login_wall(html, "https://www.nowcoder.com/discuss/1").needs_login)

    def test_collection_browser_is_visible_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_browser_headless())

        with patch.dict(os.environ, {"INTERVIEW_BROWSER_HEADLESS": "1"}, clear=True):
            self.assertTrue(_browser_headless())

    def test_disabled_browser_connector_returns_actionable_login_request(self):
        result = DisabledBrowserConnector().fetch("https://www.nowcoder.com/discuss/1", profile_dir="")

        self.assertTrue(result.needs_login)
        self.assertIn("INTERVIEW_ENABLE_BROWSER", result.error)


if __name__ == "__main__":
    unittest.main()
