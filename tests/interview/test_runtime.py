"""Interview runtime tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oncall_app.interview.collection_jobs import CollectionJobStatus
from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.runtime import InterviewRuntime
from oncall_app.interview.source_platforms import SOURCE_PLATFORMS, SourcePlatform


class InterviewRuntimeTest(unittest.TestCase):
    def test_imports_markdown_paths_and_lists_questions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "questions.md"
            source.write_text("# 牛客\n1. Agent eval 怎么做？", encoding="utf-8")
            runtime = InterviewRuntime(store_path=root / "interview.sqlite3", source_paths=[source])

            result = runtime.import_sources()

            self.assertEqual(result["snapshots"], 1)
            self.assertEqual(result["questions"], 1)
            self.assertEqual(runtime.list_questions()[0].topic, "agent_eval")

    def test_import_text_source_extracts_questions_into_bank(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = InterviewRuntime(store_path=root / "interview.sqlite3")

            result = runtime.import_text_source(
                "1. Agent eval 怎么做？\n2. RAG 召回失败怎么排查？",
                source_uri="manual://paste",
            )
            questions = runtime.list_questions()

            self.assertEqual(result["snapshots"], 1)
            self.assertEqual(result["questions"], 2)
            self.assertEqual(len(questions), 2)
            self.assertEqual({item.source_uri for item in questions}, {"manual://paste"})

    def test_weak_answer_writes_l3_interview_weakness_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = InterviewRuntime(store_path=root / "interview.sqlite3")
            runtime.store.upsert_question(
                InterviewQuestion(
                    id="q-eval",
                    question="Agent eval 怎么做？",
                    source_snapshot_id="src",
                    source_uri="source.md",
                    normalized_question="agenteval",
                    topic="agent_eval",
                )
            )

            events = list(runtime.answer_events("session-1", "q-eval", "看最终答案。"))
            memories = runtime.memory_store.list_memories(layer="L3")

            self.assertTrue(any(item.kind == "interview_weakness" for item in memories))
            self.assertTrue(any("agent_eval" in item.summary for item in memories))
            self.assertTrue(runtime.list_turns("session-1"))
            self.assertIn("persist_interview_turn", [event["payload"].get("tool") for event in events if event["type"] == "tool_call"])

    def test_imports_authenticated_web_snapshot_with_fake_connector(self):
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                from oncall_app.interview.browser_connector import BrowserFetchResult

                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客面经",
                    html="<html><body><h1>牛客面经</h1><p>1. Agent eval 怎么做？</p></body></html>",
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = InterviewRuntime(
                store_path=root / "interview.sqlite3",
                browser_connector=FakeConnector(),
            )
            result = runtime.import_authenticated_url("https://www.nowcoder.com/discuss/1")

            self.assertEqual(result["snapshots"], 1)
            self.assertEqual(result["questions"], 1)

    def test_import_authenticated_web_reuses_sibling_login_profile(self):
        class FakeConnector:
            def __init__(self):
                self.profile_dirs = []

            def fetch(self, url, profile_dir):
                del url
                from oncall_app.interview.browser_connector import BrowserFetchResult

                self.profile_dirs.append(Path(profile_dir))
                return BrowserFetchResult(
                    url="https://docs.feishu.cn/wiki",
                    final_url="https://docs.feishu.cn/wiki",
                    title="飞书面经",
                    html='<html><body><h2>Agent 工具调用怎么设计？</h2></body></html>',
                    needs_login=False,
                    profile_host="accounts.feishu.cn",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = FakeConnector()
            runtime = InterviewRuntime(
                store_path=root / "interview.sqlite3",
                browser_connector=connector,
                profile_root=root / "profiles",
            )
            runtime.store.upsert_web_login(
                "accounts.feishu.cn",
                root / "profiles" / "web-fetch-accounts-feishu-cn",
            )

            result = runtime.import_authenticated_url("https://docs.feishu.cn/wiki")
            snapshot = runtime.store.get_source_snapshot(str(result["snapshot_ids"][0]))

            self.assertEqual(
                connector.profile_dirs[0],
                root / "profiles" / "web-fetch-accounts-feishu-cn",
            )
            self.assertEqual(snapshot.metadata["profile_host"], "accounts.feishu.cn")

    def test_import_authenticated_web_needs_login_does_not_mark_connected(self):
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                from oncall_app.interview.browser_connector import BrowserFetchResult

                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="",
                    html="",
                    needs_login=True,
                    error="login required",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = InterviewRuntime(
                store_path=root / "interview.sqlite3",
                browser_connector=FakeConnector(),
            )

            result = runtime.import_authenticated_url("https://www.nowcoder.com/discuss/1")

            self.assertEqual(result["needs_login"], 1)
            self.assertEqual(runtime.store.list_web_logins(), [])

    def test_import_source_platform_fetches_configured_search_urls(self):
        class FakeConnector:
            def __init__(self):
                self.urls = []

            def fetch(self, url, profile_dir):
                del profile_dir
                from oncall_app.interview.browser_connector import BrowserFetchResult

                self.urls.append(url)
                if "discuss" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="牛客详情",
                        html='<html><body><h1>Agent eval 怎么做？</h1></body></html>',
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html='<html><body><a class="post-title" href="/discuss/eval">Agent eval 怎么做？</a></body></html>',
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = FakeConnector()
            store_path = root / "interview.sqlite3"
            runtime = InterviewRuntime(
                store_path=store_path,
                browser_connector=connector,
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="/static/assets/source-platforms/nowcoder.ico",
                search_urls=("https://www.nowcoder.com/search?query=agent",),
            )

            result = runtime.import_source_platform(platform)

            self.assertEqual(
                connector.urls,
                [
                    "https://www.nowcoder.com/search?query=agent",
                    "https://www.nowcoder.com/discuss/eval",
                ],
            )
            self.assertEqual(result["snapshots"], 1)
            self.assertEqual(result["questions"], 1)
            self.assertEqual(result["metadata"]["extractor"], "nowcoder")
            self.assertEqual(result["metadata"]["candidate_blocks"], 1)

    def test_default_source_platforms_search_agent_interview_experience_once(self):
        for platform in SOURCE_PLATFORMS:
            self.assertEqual(len(platform.search_urls), 1)
            self.assertIn("agent", platform.search_urls[0].lower())
            self.assertIn("%E9%9D%A2%E7%BB%8F", platform.search_urls[0])

    def test_source_platform_sync_runs_as_background_job(self):
        class FakeConnector:
            def __init__(self):
                self.urls = []

            def fetch(self, url, profile_dir):
                del profile_dir
                from oncall_app.interview.browser_connector import BrowserFetchResult

                self.urls.append(url)
                if "question" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="知乎详情",
                        html='<html><body><h1>Agent memory 怎么设计？</h1></body></html>',
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="知乎面经",
                    html='<html><body><a class="ContentItem-title" href="/question/1">Agent memory 怎么设计？</a></body></html>',
                    needs_login=False,
                )

            def open_login(self, url, profile_dir):
                raise AssertionError("background sync should fetch, not open a login window")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = FakeConnector()
            store_path = root / "interview.sqlite3"
            runtime = InterviewRuntime(
                store_path=store_path,
                browser_connector=connector,
            )
            platform = SourcePlatform(
                id="zhihu",
                label="知乎",
                host="zhihu.com",
                login_url="https://www.zhihu.com",
                icon_path="/static/assets/source-platforms/zhihu.ico",
                search_urls=("https://www.zhihu.com/search?q=agent",),
            )

            queued = runtime.start_source_platform_sync(platform, initial_delay_seconds=0)
            completed = runtime.wait_source_platform_sync(platform.id)

            self.assertTrue(queued.job_id.startswith("job-"))
            self.assertEqual(completed.job_id, queued.job_id)
            self.assertEqual(completed.state, "completed")
            self.assertEqual(completed.snapshots, 1)
            self.assertEqual(completed.questions, 1)
            self.assertEqual(completed.metadata["extractor"], "zhihu")
            self.assertEqual(completed.metadata["candidate_blocks"], 1)
            self.assertEqual(
                connector.urls,
                ["https://www.zhihu.com/search?q=agent", "https://www.zhihu.com/question/1"],
            )
            question = runtime.list_questions()[0]
            self.assertEqual(question.metadata["collection_job_ids"], [queued.job_id])
            self.assertEqual(question.metadata["extractors"], ["zhihu"])
            restarted = InterviewRuntime(store_path=store_path)
            restored = restarted.source_platform_sync_status(platform.id)
            self.assertEqual(restored.job_id, queued.job_id)
            self.assertEqual(restored.state, "completed")
            self.assertEqual(restored.questions, 1)

    def test_source_platform_sync_waits_for_login_window_before_fetching(self):
        class LoginAwareConnector:
            def __init__(self):
                self.open_checks = 0
                self.fetches = []

            def is_login_open(self, profile_dir):
                del profile_dir
                self.open_checks += 1
                return self.open_checks == 1

            def fetch(self, url, profile_dir):
                del profile_dir
                from oncall_app.interview.browser_connector import BrowserFetchResult

                self.fetches.append((self.open_checks, url))
                if "question" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="知乎详情",
                        html='<html><body><h1>Agent memory 怎么设计？</h1></body></html>',
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="知乎面经",
                    html='<html><body><a class="ContentItem-title" href="/question/1">Agent memory 怎么设计？</a></body></html>',
                    needs_login=False,
                )

            def open_login(self, url, profile_dir):
                raise AssertionError("sync should not open an extra login window")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = LoginAwareConnector()
            runtime = InterviewRuntime(
                store_path=root / "interview.sqlite3",
                browser_connector=connector,
                profile_root=root / "profiles",
            )
            platform = SourcePlatform(
                id="zhihu",
                label="知乎",
                host="zhihu.com",
                login_url="https://www.zhihu.com",
                icon_path="/static/assets/source-platforms/zhihu.ico",
                search_urls=("https://www.zhihu.com/search?q=agent",),
            )

            with patch("oncall_app.interview.runtime.PLATFORM_SYNC_RETRY_SECONDS", 0.01):
                queued = runtime.start_source_platform_sync(platform, initial_delay_seconds=0)
                completed = runtime.wait_source_platform_sync(platform.id, timeout_seconds=2)

            self.assertEqual(completed.job_id, queued.job_id)
            self.assertEqual(completed.state, "completed")
            self.assertEqual(
                connector.fetches,
                [(2, "https://www.zhihu.com/search?q=agent"), (2, "https://www.zhihu.com/question/1")],
            )
            self.assertEqual(completed.attempts, 1)

    def test_source_platform_sync_records_worker_failure(self):
        class FailingRuntime(InterviewRuntime):
            def import_source_platform(
                self,
                platform,
                collection_job_id="",
                *,
                dry_run=False,
                since_days=None,
                max_detail_pages=5,
                progress_callback=None,
            ):
                del platform
                del collection_job_id
                del dry_run
                del since_days
                del max_detail_pages
                del progress_callback
                raise RuntimeError("fetch crashed")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = FailingRuntime(store_path=root / "interview.sqlite3")
            platform = SourcePlatform(
                id="zhihu",
                label="知乎",
                host="zhihu.com",
                login_url="https://www.zhihu.com",
                icon_path="/static/assets/source-platforms/zhihu.ico",
                search_urls=("https://www.zhihu.com/search?q=agent",),
            )

            queued = runtime.start_source_platform_sync(platform, initial_delay_seconds=0)
            failed = runtime.wait_source_platform_sync(platform.id)

            self.assertEqual(failed.job_id, queued.job_id)
            self.assertEqual(failed.state, "failed")
            self.assertEqual(failed.message, "后台采集失败，请稍后重试")
            self.assertIn("fetch crashed", failed.error)

    def test_source_platform_sync_marks_stale_running_job_after_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store_path = root / "interview.sqlite3"
            runtime = InterviewRuntime(store_path=store_path)
            runtime.store.upsert_collection_job(
                CollectionJobStatus(
                    job_id="job-stale",
                    platform_id="zhihu",
                    state="running",
                    message="后台采集进行中",
                    attempts=1,
                    updated_at="2026-05-17T00:00:00Z",
                )
            )

            restarted = InterviewRuntime(store_path=store_path)
            status = restarted.source_platform_sync_status("zhihu")
            persisted = restarted.store.latest_collection_job("zhihu")

            self.assertEqual(status.job_id, "job-stale")
            self.assertEqual(status.state, "failed")
            self.assertIn("应用重启", status.message)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.state, "failed")

    def test_open_authorized_browser_registers_profile_metadata(self):
        class FakeConnector:
            def __init__(self):
                self.opened = []

            def fetch(self, url, profile_dir):
                raise AssertionError("open login should not fetch the page")

            def open_login(self, url, profile_dir):
                from oncall_app.interview.browser_connector import BrowserLoginResult

                self.opened.append((url, Path(profile_dir)))
                return BrowserLoginResult(
                    opened=True,
                    url=url,
                    host="nowcoder.com",
                    profile_dir=str(profile_dir),
                    message="login window opened",
                )

            def is_login_open(self, profile_dir):
                del profile_dir
                return False

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connector = FakeConnector()
            with patch.dict("os.environ", {"INTERVIEW_BROWSER_PROFILE_DIR": str(root / "profiles")}):
                runtime = InterviewRuntime(
                    store_path=root / "interview.sqlite3",
                    browser_connector=connector,
                )

                result = runtime.open_authorized_browser("https://www.nowcoder.com/discuss/1")
                pending = runtime.store.list_web_logins()[0]
                runtime.refresh_login_window_states()
                logins = runtime.store.list_web_logins()

            self.assertTrue(result.opened)
            self.assertEqual(result.host, "nowcoder.com")
            self.assertEqual(pending["metadata"]["login_probe_state"], "pending")
            self.assertEqual(logins[0]["host"], "nowcoder.com")
            self.assertEqual(logins[0]["metadata"]["login_probe_state"], "verified")
            self.assertIn("关闭登录窗口", logins[0]["metadata"]["login_probe_reason"])
            self.assertEqual(connector.opened[0][0], "https://www.nowcoder.com/discuss/1")

    def test_forget_authorized_host_removes_metadata_and_profile_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict("os.environ", {"INTERVIEW_BROWSER_PROFILE_DIR": str(root / "profiles")}):
                runtime = InterviewRuntime(store_path=root / "interview.sqlite3")
                profile_dir = runtime._profile_dir_for_host("nowcoder.com")
                profile_dir.mkdir(parents=True)
                (profile_dir / "Cookies").write_text("browser owned state", encoding="utf-8")
                runtime.store.upsert_web_login("nowcoder.com", profile_dir)

                result = runtime.forget_authorized_host("https://www.nowcoder.com/discuss/1")

            self.assertEqual(result["host"], "nowcoder.com")
            self.assertTrue(result["deleted"])
            self.assertTrue(result["cleared_profile"])
            self.assertFalse(profile_dir.exists())
            self.assertEqual(runtime.store.list_web_logins(), [])
