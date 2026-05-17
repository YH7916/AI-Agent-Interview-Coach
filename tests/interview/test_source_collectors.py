"""Tests for real source collection flow."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.browser_connector import BrowserFetchResult
from oncall_app.interview.source_collectors import SourceCollector
from oncall_app.interview.source_platforms import SourcePlatform
from oncall_app.interview.store import InterviewStore


class SourceCollectorTests(unittest.TestCase):
    """Collectors should expand search results into useful source pages."""

    def test_nowcoder_adapter_extracts_result_links_and_imports_details(self) -> None:
        class FakeConnector:
            def __init__(self) -> None:
                self.urls = []

            def fetch(self, url, profile_dir):
                del profile_dir
                self.urls.append(url)
                if "search" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="牛客搜索",
                        html="""
                        <html><body>
                          <a class="post-title" href="/discuss/1">Agent 记忆系统怎么做？</a>
                          <a class="post-title" href="https://www.nowcoder.com/discuss/2">RAG 召回失败怎么排查？</a>
                        </body></html>
                        """,
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="详情",
                    html=f"<html><body><h1>{'Agent 记忆系统怎么做？' if url.endswith('/1') else 'RAG 召回失败怎么排查？'}</h1></body></html>",
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=FakeConnector(),
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            result = collector.collect(platform, collection_job_id="job-1")

        self.assertEqual(result["snapshots"], 2)
        self.assertEqual(result["questions"], 2)
        self.assertEqual(result["unique_questions"], 2)
        self.assertEqual(result["duplicate_questions"], 0)
        self.assertEqual(result["metadata"]["detail_pages"], 2)
        self.assertEqual(result["metadata"]["source_pages"], 3)
        self.assertEqual(result["metadata"]["quality_status"], "good")
        self.assertIn("Agent 记忆系统怎么做？", result["metadata"]["accepted_questions"])
        self.assertTrue(any("搜索页" in item for item in result["metadata"]["visited_pages"]))

    def test_collector_reports_progress_after_each_visible_page(self) -> None:
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                if "discuss" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="牛客详情",
                        html='<html><body><h1>Agent memory 怎么设计？</h1></body></html>',
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html='<html><body><a class="post-title" href="/discuss/memory">Agent memory 怎么设计？</a></body></html>',
                    needs_login=False,
                )

        progress: list[tuple[str, int, int]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=FakeConnector(),
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
                progress_callback=lambda totals, message: progress.append(
                    (
                        message,
                        int(totals["metadata"]["source_pages"]),
                        int(totals["questions"]),
                    )
                ),
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            collector.collect(platform, collection_job_id="job-1")

        self.assertGreaterEqual(len(progress), 2)
        self.assertEqual(progress[0], ("已访问搜索页：牛客搜索", 1, 0))
        self.assertEqual(progress[-1], ("已处理详情页：牛客详情", 2, 1))

    def test_collector_batches_detail_clicks_when_browser_supports_it(self) -> None:
        class BatchConnector:
            def __init__(self) -> None:
                self.batch_calls = []

            def fetch(self, url, profile_dir):
                del profile_dir
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html="""
                    <html><body>
                      <a class="post-title" href="/discuss/memory">Agent memory 怎么设计？</a>
                      <a class="post-title" href="/discuss/rag">RAG 召回失败怎么排查？</a>
                    </body></html>
                    """,
                    needs_login=False,
                )

            def fetch_result_pages_by_click(self, search_url, target_urls, profile_dir):
                del profile_dir
                self.batch_calls.append((search_url, tuple(target_urls)))
                return [
                    BrowserFetchResult(
                        url=target_url,
                        final_url=target_url,
                        title="详情",
                        html=f"<html><body><h1>{title}</h1></body></html>",
                        needs_login=False,
                    )
                    for target_url, title in zip(
                        target_urls,
                        ("Agent memory 怎么设计？", "RAG 召回失败怎么排查？"),
                        strict=True,
                    )
                ]

            def fetch_by_click(self, search_url, target_url, profile_dir):
                del search_url, target_url, profile_dir
                raise AssertionError("detail pages should be fetched in one visible browser session")

        connector = BatchConnector()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=connector,
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            result = collector.collect(platform, collection_job_id="job-1")

        self.assertEqual(result["snapshots"], 2)
        self.assertEqual(len(connector.batch_calls), 1)
        self.assertEqual(
            connector.batch_calls[0],
            (
                "https://www.nowcoder.com/search?q=agent",
                (
                    "https://www.nowcoder.com/discuss/memory",
                    "https://www.nowcoder.com/discuss/rag",
                ),
            ),
        )

    def test_duplicate_questions_are_counted(self) -> None:
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                if "discuss" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="详情",
                        html='<html><body><h1>Agent Eval 怎么做？</h1></body></html>',
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html='<html><body><a class="post-title" href="/discuss/eval">Agent Eval 怎么做？</a></body></html>',
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=FakeConnector(),
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            first = collector.collect(platform, collection_job_id="job-1")
            second = collector.collect(platform, collection_job_id="job-2")

        self.assertEqual(first["unique_questions"], 1)
        self.assertEqual(second["unique_questions"], 0)
        self.assertEqual(second["duplicate_questions"], 1)
        self.assertEqual(second["metadata"]["quality_status"], "partial")

    def test_search_result_noise_is_not_followed_or_imported(self) -> None:
        class FakeConnector:
            def __init__(self) -> None:
                self.urls = []

            def fetch(self, url, profile_dir):
                del profile_dir
                self.urls.append(url)
                if "search" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="牛客搜索",
                        html="""
                        <html><body>
                          <a class="post-title" href="/discuss/noise">怎么学Agent？</a>
                          <a class="post-title" href="/discuss/valid">agent出错率，是模型问题还是RAG还是Prompt？</a>
                        </body></html>
                        """,
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="详情",
                    html="<html><body><h1>agent出错率，是模型问题还是RAG还是Prompt？</h1></body></html>",
                    needs_login=False,
                )

        connector = FakeConnector()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=connector,
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            result = collector.collect(platform, collection_job_id="job-1")
            questions = store.list_questions()

        self.assertEqual(connector.urls, ["https://www.nowcoder.com/search?q=agent", "https://www.nowcoder.com/discuss/valid"])
        self.assertEqual(result["questions"], 1)
        self.assertTrue(any("Agent 出错时" in item for item in result["metadata"]["accepted_questions"]))
        self.assertTrue(any("详情页" in item for item in result["metadata"]["visited_pages"]))
        self.assertEqual([item.question for item in questions], ["Agent 出错时，如何区分是模型、RAG 还是 Prompt 的问题？"])

    def test_search_page_without_clickable_details_is_not_imported(self) -> None:
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html='<html><body><h2 class="post-title">Agent Eval 怎么做？</h2></body></html>',
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=FakeConnector(),
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            result = collector.collect(platform, collection_job_id="job-1")

        self.assertEqual(result["snapshots"], 0)
        self.assertEqual(result["questions"], 0)
        self.assertEqual(result["metadata"]["fallback_pages"], 1)
        self.assertTrue(any("没有找到可点击详情链接" in item for item in result["metadata"]["rejected_candidates"]))

    def test_recent_filter_requires_time_evidence_on_detail_page(self) -> None:
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                if "fresh" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="详情",
                        html="<html><body><span>3天前</span><h1>Agent Eval 怎么做？</h1></body></html>",
                        needs_login=False,
                    )
                if "stale" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="详情",
                        html="<html><body><h1>RAG 召回失败怎么排查？</h1></body></html>",
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html="""
                    <html><body>
                      <a class="post-title" href="/discuss/fresh">Agent Eval 怎么做？</a>
                      <a class="post-title" href="/discuss/stale">RAG 召回失败怎么排查？</a>
                    </body></html>
                    """,
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=FakeConnector(),
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            result = collector.collect(platform, collection_job_id="job-1", since_days=7)
            stored_questions = store.list_questions()

        self.assertEqual(result["questions"], 1)
        self.assertEqual(result["metadata"]["since_days"], 7)
        self.assertEqual([item.question for item in stored_questions], ["Agent eval 怎么做？"])
        self.assertTrue(any("没有最近 7 天内" in item for item in result["metadata"]["rejected_candidates"]))

    def test_dry_run_reports_candidates_without_writing_question_bank(self) -> None:
        class FakeConnector:
            def fetch(self, url, profile_dir):
                del profile_dir
                if "discuss" in url:
                    return BrowserFetchResult(
                        url=url,
                        final_url=url,
                        title="详情",
                        html='<html><body><h1>Agent Eval 怎么做？</h1></body></html>',
                        needs_login=False,
                    )
                return BrowserFetchResult(
                    url=url,
                    final_url=url,
                    title="牛客搜索",
                    html='<html><body><a class="post-title" href="/discuss/eval">Agent Eval 怎么做？</a></body></html>',
                    needs_login=False,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = InterviewStore(root / "interview.sqlite3")
            collector = SourceCollector(
                store=store,
                browser_connector=FakeConnector(),
                profile_dir_for_host=lambda host: root / "profiles" / host,
                artifact_root=root / "source_pages",
            )
            platform = SourcePlatform(
                id="nowcoder",
                label="牛客",
                host="nowcoder.com",
                login_url="https://www.nowcoder.com",
                icon_path="",
                search_urls=("https://www.nowcoder.com/search?q=agent",),
            )

            result = collector.collect(platform, collection_job_id="job-1", dry_run=True)
            stored_questions = store.list_questions()

        self.assertTrue(result["metadata"]["dry_run"])
        self.assertEqual(result["questions"], 1)
        self.assertEqual(stored_questions, [])


if __name__ == "__main__":
    unittest.main()
