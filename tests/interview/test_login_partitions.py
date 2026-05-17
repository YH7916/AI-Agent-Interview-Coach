"""Tests for YouNavi-style source login partition resolution."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.login_partitions import (
    profile_partition_name,
    registrable_domain,
    resolve_profile_host,
)
from oncall_app.interview.store import InterviewStore


class LoginPartitionTests(unittest.TestCase):
    """Login profile metadata should route background fetches predictably."""

    def test_registrable_domain_handles_common_hosts(self) -> None:
        self.assertEqual(registrable_domain("www.zhihu.com"), "zhihu.com")
        self.assertEqual(registrable_domain("accounts.feishu.cn"), "feishu.cn")
        self.assertEqual(registrable_domain("a.b.taobao.com.cn"), "taobao.com.cn")

    def test_profile_partition_name_is_stable(self) -> None:
        self.assertEqual(profile_partition_name("accounts.feishu.cn"), "web-fetch-accounts-feishu-cn")

    def test_exact_host_hit_returns_profile_host_and_touches_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            store.upsert_web_login("www.zhihu.com", Path(temp_dir) / "zhihu")
            before = store.list_web_logins()[0]["last_used_at"]

            resolved = resolve_profile_host(store, "www.zhihu.com")
            after = store.list_web_logins()[0]["last_used_at"]

        self.assertEqual(resolved, "www.zhihu.com")
        self.assertGreaterEqual(str(after), str(before))

    def test_falls_back_to_sibling_login_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            store.upsert_web_login("accounts.feishu.cn", Path(temp_dir) / "feishu")

            resolved = resolve_profile_host(store, "docs.feishu.cn")

        self.assertEqual(resolved, "accounts.feishu.cn")

    def test_registrable_domain_itself_does_not_use_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            store.upsert_web_login("accounts.feishu.cn", Path(temp_dir) / "feishu")

            resolved = resolve_profile_host(store, "feishu.cn")

        self.assertIsNone(resolved)

    def test_missing_login_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")

            resolved = resolve_profile_host(store, "example.com")

        self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
