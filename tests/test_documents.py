"""Tests for SOP document parsing and repository access."""

import unittest
from pathlib import Path

from oncall_app.documents.parser import parse_document
from oncall_app.documents.repository import DocumentRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class HtmlParserTest(unittest.TestCase):
    """Visible text extraction behavior."""

    def test_extracts_decoded_title_and_visible_text(self):
        """Parser decodes entities in titles and body text."""
        html = (DATA_DIR / "sop-003.html").read_text(encoding="utf-8")

        parsed = parse_document("sop-003", html, file_name="sop-003.html")

        self.assertEqual(parsed.title, "前端Web On-Call SOP & 故障处理指南")
        self.assertIn("PC端&移动端H5&小程序WebView", parsed.text)
        self.assertNotIn("&#38;", parsed.text)
        self.assertTrue(parsed.sections)

    def test_excludes_script_and_style_content(self):
        """Parser ignores style and script blocks while keeping real body content."""
        html = (DATA_DIR / "sop-002.html").read_text(encoding="utf-8")

        parsed = parse_document("sop-002", html, file_name="sop-002.html")

        self.assertIn("主从复制状态", parsed.text)
        self.assertNotIn("replicationLag", parsed.text)
        self.assertNotIn("fetchMetrics", parsed.text)
        self.assertNotIn("font-family", parsed.text)


class DocumentRepositoryTest(unittest.TestCase):
    """Document repository behavior."""

    def test_loads_all_documents_from_data_dir(self):
        """Repository loads the bundled SOP files."""
        repository = DocumentRepository(DATA_DIR)

        documents = repository.all_documents()

        self.assertEqual(len(documents), 10)
        self.assertEqual(repository.get("sop-001").title, "后端服务 On-Call SOP")
        self.assertEqual(repository.get("sop-001").file_name, "sop-001.html")

    def test_read_file_allows_direct_file_names_only(self):
        """The readFile backing method only accepts plain file names."""
        repository = DocumentRepository(DATA_DIR)

        content = repository.read_file("sop-001.html")

        self.assertIn("后端服务 On-Call SOP", content)
        with self.assertRaises(ValueError):
            repository.read_file("../README.md")
        with self.assertRaises(ValueError):
            repository.read_file("sop-*.html")
        with self.assertRaises(FileNotFoundError):
            repository.read_file("missing.html")


if __name__ == "__main__":
    unittest.main()
