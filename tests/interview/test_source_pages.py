"""Tests for persisted source page artifacts."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.source_pages import (
    CapturedSourcePage,
    generate_fetch_id,
    read_source_page_meta,
    save_source_page,
)


class SourcePageArtifactTests(unittest.TestCase):
    """Raw source pages should be inspectable after background collection."""

    def test_generate_fetch_id_includes_timestamp_and_domain(self) -> None:
        captured_at = dt.datetime(2026, 5, 17, 12, 30, 5, 123000)

        fetch_id = generate_fetch_id("https://www.nowcoder.com/discuss/1", captured_at)

        self.assertEqual(fetch_id, "20260517_123005123_nowcoder-com")

    def test_save_and_read_source_page_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved = save_source_page(
                root,
                CapturedSourcePage(
                    job_id="job-1",
                    fetch_id="20260517_123005123_nowcoder-com",
                    request_url="https://www.nowcoder.com/search?q=agent",
                    final_url="https://www.nowcoder.com/search?q=agent",
                    title="牛客搜索",
                    raw_html="<html><body>Agent Eval 怎么做？</body></html>",
                    extracted_markdown="# 牛客搜索\n\nAgent Eval 怎么做？",
                    metadata={"platform": "nowcoder"},
                ),
            )
            meta = read_source_page_meta(saved.page_dir)
            self.assertTrue((saved.page_dir / "raw.html").is_file())
            self.assertTrue((saved.page_dir / "extracted.md").is_file())
            self.assertEqual(meta.fetch_id, "20260517_123005123_nowcoder-com")
            self.assertEqual(meta.metadata["platform"], "nowcoder")

    def test_rejects_path_traversal_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                save_source_page(
                    Path(temp_dir),
                    CapturedSourcePage(
                        job_id="../bad",
                        fetch_id="fetch",
                        request_url="https://x",
                        final_url="https://x",
                        title="x",
                        raw_html="<html/>",
                        extracted_markdown="",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
