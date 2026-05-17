"""readFile tool tests."""

import unittest
from pathlib import Path

from oncall_app.agent.tools import ReadFileTool
from oncall_app.documents.repository import DocumentRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class ReadFileToolTest(unittest.TestCase):
    """Agent readFile tool safety."""

    def setUp(self):
        """Create a readFile tool."""
        self.tool = ReadFileTool(DocumentRepository(DATA_DIR))

    def test_reads_direct_sop_file(self):
        """The tool reads direct SOP file names and records a visible call."""
        result = self.tool.read_file("sop-001.html")

        self.assertIn("后端服务 On-Call SOP", result.content)
        self.assertEqual(result.call.tool, "readFile")
        self.assertEqual(result.call.fname, "sop-001.html")

    def test_rejects_path_traversal_and_glob(self):
        """The tool rejects path traversal, subdirectories, and globbing."""
        for fname in ("../README.md", "data/sop-001.html", "sop-*.html"):
            with self.subTest(fname=fname):
                with self.assertRaises(ValueError):
                    self.tool.read_file(fname)


if __name__ == "__main__":
    unittest.main()
