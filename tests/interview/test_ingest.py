"""Interview markdown ingestion tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.ingest import (
    extract_questions,
    extract_questions_with_audit,
    load_markdown_snapshots,
)
from oncall_app.interview.models import SourceSnapshot
from oncall_app.interview.platform_extractors import extract_interview_markdown_from_html


class InterviewIngestTest(unittest.TestCase):
    def test_loads_markdown_files_from_file_and_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            single = root / "fusion.md"
            child = root / "raw"
            child.mkdir()
            nested = child / "ali.md"
            single.write_text("# 融合\n1. Agent vs LLM 单次调用？", encoding="utf-8")
            nested.write_text("# 阿里\n- RAG 完整流程是什么？", encoding="utf-8")

            snapshots = load_markdown_snapshots([single, child])

            self.assertEqual(len(snapshots), 2)
            self.assertEqual({item.title for item in snapshots}, {"融合", "阿里"})

    def test_extracts_questions_with_topic_and_platform(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "00_牛客主整合_拿来就能背.md"
            path.write_text(
                "# 牛客 Agent 面经\n"
                "| # | 题目 | 答题模板要点 |\n"
                "|---|---|---|\n"
                "| 1 | **Agent 评估体系怎么做？** | outcome + trace + grader |\n",
                encoding="utf-8",
            )

            snapshots = load_markdown_snapshots([path])
            questions = extract_questions(snapshots)

            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0].question, "Agent 评估体系怎么做？")
            self.assertEqual(questions[0].topic, "agent_eval")
            self.assertEqual(questions[0].platform, "牛客")
            self.assertEqual(questions[0].answer_hint, "outcome + trace + grader")

    def test_extracts_plain_question_lines_from_browser_text(self):
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri="https://www.nowcoder.com/search",
            title="牛客搜索",
            content_text="Agent eval 怎么做？\n普通描述文本\nRAG 和 Agent 的边界是什么？",
            content_hash="hash",
            metadata={"platform": "牛客"},
        )

        questions = extract_questions([snapshot])

        self.assertEqual(
            [item.question for item in questions],
            ["Agent eval 怎么做？", "RAG 和 Agent 的边界是什么？"],
        )

    def test_rejects_social_logistics_and_learning_noise(self):
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri="https://www.xiaohongshu.com/search_result?keyword=agent",
            title="小红书搜索",
            content_text="\n".join(
                [
                    "大佬，我想请教一下。目前的agent开发应该算是传统JAVA后端的扩展内容吧，也就是说还是要先去学会JAVA后端的内容吧？",
                    "怎么学Agent？",
                    "这些问题的答案可以分享一下吗？",
                    "请问手撕代码限制用什么语言吗？",
                    "请问有没有现场coding？能不能用ide？",
                    "你好，方便推一下课程和老师吗？",
                    "如何快速拿到LLM offer？",
                ]
            ),
            content_hash="hash",
            metadata={"platform": "小红书"},
        )

        questions = extract_questions([snapshot])

        self.assertEqual(questions, [])

    def test_rejects_job_search_hc_noise_even_with_agent_marker(self):
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri="https://www.nowcoder.com/search?query=agent",
            title="牛客搜索",
            content_text="5、怎么识别agent业务HC？",
            content_hash="hash",
            metadata={"platform": "牛客"},
        )

        questions, audit = extract_questions_with_audit([snapshot])

        self.assertEqual(questions, [])
        self.assertTrue(any("业务HC" in item for item in audit.rejected_candidates))

    def test_extraction_audit_reports_accepted_rejected_and_rewritten_candidates(self):
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri="https://www.nowcoder.com/search",
            title="牛客搜索",
            content_text="\n".join(
                [
                    "怎么学Agent？",
                    "越来越搞不明白了，skill和prompt区别究竟是什么，一个可以自动注入的prompt？",
                    "RAG 召回失败怎么排查？",
                ]
            ),
            content_hash="hash",
            metadata={"platform": "牛客"},
        )

        questions, audit = extract_questions_with_audit([snapshot])

        self.assertEqual(len(questions), 2)
        self.assertEqual(audit.raw_candidate_count, 3)
        self.assertIn("Skill 和 Prompt 的区别是什么？", audit.accepted_questions)
        self.assertTrue(any("怎么学Agent" in item and "不像面试题" in item for item in audit.rejected_candidates))
        self.assertTrue(any("skill和prompt" in item for item in audit.rewritten_questions))

    def test_curates_noisy_technical_threads_into_clean_questions(self):
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri="https://www.nowcoder.com/search?query=rag",
            title="牛客搜索",
            content_text="\n".join(
                [
                    "越来越搞不明白了，skill和prompt区别究竟是什么，一个可以自动注入的prompt？",
                    "agent出错率，是模型问题还是RAG还是Prompt？不换模型情况下工程角度解决幻觉的方案？",
                    "自我介绍 RAG 的流程 RAG 的优势 怎么识别大模型的幻觉？减少大模型幻觉的措施有哪些？ 用了 RAG 以后，大模型就一定不出幻觉了吗？怎么排查？ 怎么确保 RAG 检索到的文档块一定是想要的？",
                ]
            ),
            content_hash="hash",
            metadata={"platform": "牛客"},
        )

        questions = extract_questions([snapshot])

        self.assertEqual(
            [item.question for item in questions],
            [
                "Skill 和 Prompt 的区别是什么？",
                "Agent 出错时，如何区分是模型、RAG 还是 Prompt 的问题？",
                "不换模型时，工程上如何降低幻觉？",
                "RAG 的完整流程是什么？",
                "RAG 的优势是什么？",
                "用了 RAG 以后，大模型还会出现幻觉吗？",
                "RAG 出现幻觉时怎么排查？",
                "怎么确保 RAG 检索到的文档块符合问题意图？",
                "怎么识别大模型的幻觉？",
                "减少大模型幻觉的措施有哪些？",
            ],
        )
        self.assertEqual(questions[0].topic, "mcp_skill")
        self.assertEqual(questions[1].topic, "rag")
        self.assertEqual(questions[0].metadata["raw_question"], "越来越搞不明白了，skill和prompt区别究竟是什么，一个可以自动注入的prompt？")

    def test_nowcoder_html_uses_platform_candidate_blocks(self):
        result = extract_interview_markdown_from_html(
            "牛客搜索",
            """
            <html><body>
              <a class="post-title" href="/discuss/1">Agent eval 怎么做？</a>
              <p>普通搜索摘要不是问题</p>
              <script>RAG 噪声问题？</script>
            </body></html>
            """,
            "https://www.nowcoder.com/search?query=agent",
        )
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri="https://www.nowcoder.com/search?query=agent",
            title="牛客搜索",
            content_text=result.markdown,
            content_hash="hash",
            metadata=result.metadata,
        )

        questions = extract_questions([snapshot])

        self.assertEqual(result.metadata["extractor"], "nowcoder")
        self.assertEqual(result.metadata["candidate_blocks"], 1)
        self.assertFalse(result.metadata["fallback_used"])
        self.assertEqual([item.question for item in questions], ["Agent eval 怎么做？"])
        self.assertEqual(questions[0].platform, "牛客")

    def test_platform_extractor_filters_common_ui_noise(self):
        result = extract_interview_markdown_from_html(
            "牛客搜索",
            """
            <html><body>
              <a class="post-title">打开APP查看更多？</a>
              <a class="post-title">相关搜索：Agent 是什么？</a>
              <a class="post-title">Agent eval 怎么做？</a>
            </body></html>
            """,
            "https://www.nowcoder.com/search?query=agent",
        )

        self.assertIn("Agent eval 怎么做？", result.markdown)
        self.assertNotIn("打开APP", result.markdown)
        self.assertNotIn("相关搜索", result.markdown)
        self.assertEqual(result.metadata["candidate_blocks"], 1)

    def test_zhihu_and_xiaohongshu_html_use_specific_extractors(self):
        zhihu = extract_interview_markdown_from_html(
            "知乎搜索",
            '<h2 class="ContentItem-title">Agent Memory 怎么设计？</h2>',
            "https://www.zhihu.com/search?q=agent",
        )
        xhs = extract_interview_markdown_from_html(
            "小红书搜索",
            '<section class="note-item"><span class="title">RAG 面试怎么讲？</span></section>',
            "https://www.xiaohongshu.com/search_result?keyword=agent",
        )

        self.assertEqual(zhihu.metadata["extractor"], "zhihu")
        self.assertIn("Agent Memory 怎么设计？", zhihu.markdown)
        self.assertEqual(xhs.metadata["extractor"], "xiaohongshu")
        self.assertIn("RAG 面试怎么讲？", xhs.markdown)


if __name__ == "__main__":
    unittest.main()
