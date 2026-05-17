"""Tests for separated frontend assets."""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FrontendStaticTest(unittest.TestCase):
    """Frontend assets are separate from route code."""

    def test_frontend_files_exist(self):
        """The frontend lives outside backend route modules."""
        for name in ("index.html", "app.js", "styles.css"):
            self.assertTrue((PROJECT_ROOT / "frontend" / name).is_file())
        for name in (
            "api.js",
            "chatEvents.js",
            "chatView.js",
            "config.js",
            "evidence.js",
            "format.js",
            "markdown.js",
            "interviewProduct.js",
            "interviewReview.js",
            "interviewSession.js",
            "interviewState.js",
            "providerStatus.js",
            "questionsPage.js",
            "resumeSource.js",
            "searchResults.js",
            "shellView.js",
            "sopPreview.js",
            "sourcePlatforms.js",
            "sourcesPage.js",
            "sse.js",
            "storage.js",
            "trace.js",
        ):
            self.assertTrue((PROJECT_ROOT / "frontend" / "app" / name).is_file())
        self.assertTrue((PROJECT_ROOT / "frontend" / "assets" / "settings-2.svg").is_file())
        self.assertTrue((PROJECT_ROOT / "frontend" / "assets" / "file-text.svg").is_file())
        for name in ("nowcoder.ico", "xiaohongshu.ico", "zhihu.ico"):
            self.assertTrue((PROJECT_ROOT / "frontend" / "assets" / "source-platforms" / name).is_file())

    def test_pages_use_static_frontend_shell(self):
        """README page routes serve the shared static frontend shell."""
        client = TestClient(create_app(test_mode=True))

        for path in ("/v3", "/v3/questions", "/v3/sources", "/v3/review"):
            response = client.get(path)

            self.assertEqual(response.status_code, 200)
            self.assertIn('<script type="module" src="/static/app.js"', response.text)
            self.assertIn('<link rel="stylesheet" href="/static/styles.css"', response.text)
            self.assertIn('/static/assets/settings-2.svg', response.text)
            self.assertIn('id="settings-button"', response.text)
            self.assertIn('data-product-page="interview"', response.text)
            self.assertIn('data-product-page="questions"', response.text)
            self.assertIn('data-product-page="sources"', response.text)
            self.assertIn('data-product-page="review"', response.text)
            self.assertNotIn("v1 Search", response.text)
            self.assertNotIn("v2 RAG", response.text)

    def test_static_js_calls_readme_api_routes(self):
        """Frontend JavaScript calls the README API routes."""
        js = self._frontend_js()

        self.assertIn("/v1/search", js)
        self.assertIn("/v2/search", js)
        self.assertIn("/interview/chat/stream", js)
        self.assertIn("/interview/session-plan", js)
        self.assertIn("/interview/sources/import-text", js)
        self.assertIn("importInterviewTextSource", js)
        self.assertNotIn("data-question-bank-collect", js)
        self.assertNotIn("question-collect-modal-root", js)
        self.assertIn("topicLabel", js)
        self.assertIn("difficultyLabel", js)
        self.assertIn("Agent 架构", js)
        self.assertIn("高频 ${question.frequency} 次", js)
        self.assertIn("/interview/review", js)
        self.assertIn("fetchInterviewReview", js)
        self.assertIn("fetchInterviewSessionPlan", js)
        self.assertIn("/interview/sessions/${encodeURIComponent(sessionId)}/summary", js)
        self.assertIn("/interview/sessions/${encodeURIComponent(sessionId)}/report", js)
        self.assertIn("fetchInterviewSessionSummary", js)
        self.assertIn("fetchInterviewSessionReport", js)
        self.assertIn("interviewEndMessage", js)
        self.assertIn("/provider-status", js)
        self.assertIn("/provider-config", js)
        self.assertIn("fetchProviderConfig", js)
        self.assertIn("saveProviderConfig", js)
        self.assertIn("bindProviderConfigForm", js)
        self.assertIn("setupSettingsPopover", js)
        self.assertIn("setting-show-trace", js)
        self.assertNotIn("Agent 主线", js)
        self.assertIn("查看工具细节", js)
        self.assertIn("visibleChatHistory", js)
        self.assertIn("MAX_CHAT_CONTEXT_TURNS", js)
        self.assertIn(".slice(-MAX_CHAT_CONTEXT_TURNS)", js)
        self.assertIn("applyChatFailure", js)
        self.assertIn("streamingPlaceholder", js)
        self.assertIn("scheduleAssistantContentUpdate", js)
        self.assertIn("updateAssistantContent", js)
        self.assertIn('renderMode === "content"', js)
        self.assertIn("session_id: options.sessionId || \"default\"", js)
        self.assertIn("renderMarkdown", js)
        self.assertIn("renderMarkdownTable", js)
        self.assertIn("collectMarkdownTable", js)
        self.assertIn("pendingListBreak", js)
        self.assertIn("isListItem", js)
        self.assertIn("markdown-body", js)
        self.assertIn("renderChatShell", js)
        self.assertIn("chat-screen", js)
        self.assertIn("/documents/", js)
        self.assertIn("openSopModal", js)
        self.assertIn('data-sop-section="${escapeHtml(item.section || "")}"', js)
        self.assertIn("setupEvidenceCarousel", js)
        self.assertIn("const hasScrollableEvidence = cards.length > 3;", js)
        self.assertIn("data-evidence-direction", js)
        self.assertIn("data-evidence-pagebar", js)
        self.assertIn("scrollEvidenceStrip", js)
        self.assertIn("evidenceActiveDotIndex", js)
        self.assertIn("data-sop-id", js)
        self.assertIn("data-sop-section", js)
        self.assertIn("evidence-section", js)
        self.assertIn("memory_hits", js)
        self.assertIn("renderMemoryTrace", js)
        self.assertIn("/v3/memory/search", js)
        self.assertIn("/interview/source-platforms", js)
        self.assertIn("/interview/resume", js)
        self.assertIn("/interview/resume/import-default", js)
        self.assertIn("/interview/resume/upload", js)
        self.assertIn("data-resume-source-import-default", js)
        self.assertIn("data-resume-source-upload", js)
        self.assertIn("setupResumeSourceControls", js)
        self.assertIn("data-source-platforms", js)
        self.assertIn("data-source-platform-login", js)
        self.assertIn("data-source-platform-disconnect", js)
        self.assertIn("setupSourcePlatformControls", js)
        self.assertIn("source-platform-icon", js)
        self.assertIn("scheduleSourcePlatformRefresh", js)
        self.assertIn("这里只管理登录态", js)
        self.assertIn("syncInterviewSourcePlatform", js)
        self.assertIn("fetchInterviewSourcePlatformLatestJob", js)
        self.assertIn("parseInterviewCommand", js)
        self.assertIn("isAgentMetaConversation", js)
        self.assertIn("collectInterviewSourcesFromCommand", js)
        self.assertIn("collectionReportMarkdown", js)
        self.assertIn("COLLECTION_POLL_ATTEMPTS = 180", js)
        self.assertIn("progressByPlatform.set", js)
        self.assertIn("accepted_questions", js)
        self.assertIn("rejected_candidates", js)
        self.assertIn("不要入库", js)
        self.assertIn("pageLimitFromCommand", js)
        self.assertIn("max_pages", js)
        self.assertIn("explainInterviewQuestionFromCommand", js)
        self.assertIn("GENERAL_AGENT_STREAM_ENDPOINT", js)
        self.assertIn("/interview/agent/stream", js)
        self.assertIn("submitAgentConversation", js)
        self.assertIn("可以直接对话", js)
        self.assertIn("直接聊天，或输入“开始面试”“采集面经”“讲 RAG 召回失败”", js)
        self.assertNotIn("(!activeSession && /(开始|模拟|面试|考我|开一场|来一场)/.test(text))", js)
        self.assertIn("refreshSourcePlatforms", js)
        self.assertIn("productPageFromPath", js)
        self.assertIn("setupQuestionBankPage", js)
        self.assertIn("setupSourcesPage", js)
        self.assertIn("renderQuestionBankShell", js)
        self.assertIn("renderSourcesShell", js)
        self.assertIn("renderReviewShell", js)
        self.assertIn("createServerReviewModel", js)
        self.assertIn("完成题目", js)
        self.assertIn("attempts", js)
        self.assertIn("startInterviewSession", js)
        self.assertIn("completeInterviewQuestion", js)
        self.assertIn("askInterviewFollowUp", js)
        self.assertIn("nextInterviewStateAfterAnswer", js)
        self.assertIn("followUpQueued", js)
        self.assertIn("reviewKey", js)
        self.assertIn("director_decision", js)
        self.assertIn("chat-message-interviewer", js)
        self.assertIn("compactInterview", js)
        self.assertIn("final_review", js)
        self.assertIn("AI 评价", js)
        self.assertNotIn("本题评判依据", js)
        self.assertNotIn("review-rubric", js)
        self.assertIn("正在追问", js)

    def test_v3_evidence_cards_use_scroll_carousel(self):
        """V3 evidence cards render as a compact horizontal carousel."""
        css = (PROJECT_ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".evidence-carousel", css)
        self.assertIn(".evidence-strip", css)
        self.assertIn("--evidence-visible: 3;", css)
        self.assertIn("scroll-snap-type: x mandatory;", css)
        self.assertIn(".evidence-nav-button", css)
        self.assertIn(".evidence-pagebar", css)
        self.assertIn("width: 18px;", css)
        self.assertIn("-webkit-line-clamp: 2;", css)

    def test_markdown_styles_support_readable_hierarchy(self):
        """Markdown output has GitHub-like hierarchy and rich block support."""
        css = (PROJECT_ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".markdown-body h2", css)
        self.assertIn("border-bottom: 1px solid var(--line-soft);", css)
        self.assertIn(".markdown-body blockquote", css)
        self.assertIn(".markdown-body table", css)
        self.assertIn(".markdown-body strong", css)

    def test_interview_product_pages_use_compact_system(self):
        """Interview product pages use the existing compact visual system."""
        css = (PROJECT_ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".source-platform-list", css)
        self.assertIn(".resume-source-card", css)
        self.assertIn(".source-platform-card", css)
        self.assertIn(".source-platform-icon", css)
        self.assertIn(".source-platform-actions", css)
        self.assertIn(".source-platform-card.is-working", css)
        self.assertIn(".product-page", css)
        self.assertIn(".question-bank-row", css)
        self.assertIn(".review-item", css)
        self.assertNotIn(".review-rubric", css)
        self.assertNotIn(".rubric-feedback", css)
        self.assertIn(".chat-message-interviewer", css)
        self.assertIn("grid-template-columns: repeat(4, var(--switch-item-width));", css)

    @staticmethod
    def _frontend_js() -> str:
        """Return the concatenated static frontend modules."""
        paths = [PROJECT_ROOT / "frontend" / "app.js"]
        paths.extend(sorted((PROJECT_ROOT / "frontend" / "app").glob("*.js")))
        return "\n".join(path.read_text(encoding="utf-8") for path in paths)


if __name__ == "__main__":
    unittest.main()
