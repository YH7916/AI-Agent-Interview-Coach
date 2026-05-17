"""Evidence extraction tests."""

import unittest
from pathlib import Path

from oncall_app.agent.evidence import MAX_EVIDENCE, EvidenceExtractor
from oncall_app.documents.repository import DocumentRepository
from oncall_app.models import Document, Section

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class EvidenceExtractorTest(unittest.TestCase):
    """Relevant SOP sections are extracted for answers."""

    def test_oom_extracts_oom_section_and_escalation(self):
        """OOM evidence should include the OOM scenario and escalation section."""
        repository = DocumentRepository(DATA_DIR)
        document = repository.get("sop-001")

        evidence = EvidenceExtractor().extract("服务 OOM 了怎么办？", [document])
        headings = [item.section_heading for item in evidence]

        self.assertIn("场景二：单服务OOM崩溃", headings)
        self.assertTrue(any("升级流程" in heading for heading in headings))

    def test_p0_extracts_multiple_documents(self):
        """P0 workflow evidence should span multiple SOP documents."""
        repository = DocumentRepository(DATA_DIR)
        documents = [
            repository.get("sop-001"),
            repository.get("sop-002"),
            repository.get("sop-005"),
        ]

        evidence = EvidenceExtractor().extract("P0 故障的响应流程是什么？", documents)
        files = {item.file for item in evidence}

        self.assertGreaterEqual(len(files), 2)

    def test_extract_limits_relevant_sections(self):
        """Evidence extraction keeps evidence volume bounded for the UI and prompt."""
        sections = [
            Section(heading=f"场景 {index}", level=2, text="oom 处理 升级")
            for index in range(MAX_EVIDENCE + 2)
        ]
        document = Document(
            doc_id="sop-many",
            title="Many Sections",
            text="",
            html="",
            file_name="sop-many.html",
            sections=sections,
        )

        evidence = EvidenceExtractor().extract("oom 处理", [document])

        self.assertEqual(len(evidence), MAX_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
