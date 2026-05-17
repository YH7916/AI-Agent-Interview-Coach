"""Interview API route tests."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app
from oncall_app.api.router import runtime
from oncall_app.interview.collection_jobs import CollectionJobStatus
from oncall_app.llm.config import PROVIDER_CONFIG_PATH_ENV


class InterviewRoutesTest(unittest.TestCase):
    def test_interview_page_serves_frontend_shell(self):
        client = TestClient(create_app(test_mode=True))

        response = client.get("/interview")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI Agent Interview Coach", response.text)

    def test_question_list_route_returns_items(self):
        client = TestClient(create_app(test_mode=True))

        response = client.get("/interview/questions")

        self.assertEqual(response.status_code, 200)
        self.assertIn("items", response.json())

    def test_import_text_route_extracts_questions(self):
        client = TestClient(create_app(test_mode=True))

        imported = client.post(
            "/interview/sources/import-text",
            json={
                "text": "1. Agent eval 怎么做？\n2. L0-L3 记忆系统怎么设计？",
                "source_uri": "manual://dialog",
            },
        )
        listed = client.get("/interview/questions")

        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["snapshots"], 1)
        self.assertEqual(imported.json()["questions"], 2)
        self.assertEqual(len(listed.json()["items"]), 2)
        self.assertEqual({item["source_uri"] for item in listed.json()["items"]}, {"manual://dialog"})

    def test_question_list_hides_uncurated_collection_noise(self):
        client = TestClient(create_app(test_mode=True))

        imported = client.post(
            "/interview/sources/import-text",
            json={
                "text": "\n".join(
                    [
                        "怎么学Agent？",
                        "请问有没有现场coding？能不能用ide？",
                        "越来越搞不明白了，skill和prompt区别究竟是什么，一个可以自动注入的prompt？",
                    ]
                ),
                "source_uri": "manual://noisy-thread",
            },
        )
        listed = client.get("/interview/questions")

        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["questions"], 1)
        self.assertEqual(
            [item["question"] for item in listed.json()["items"]],
            ["Skill 和 Prompt 的区别是什么？"],
        )

    def test_session_plan_route_uses_weakness_focus_and_avoids_recent_question(self):
        client = TestClient(create_app(test_mode=True))
        answered = client.post(
            "/interview/questions",
            json={
                "question": "Agent eval 怎么做？",
                "answer_hint": "outcome transcript grader",
                "source_uri": "manual://interview",
            },
        ).json()
        followup = client.post(
            "/interview/questions",
            json={
                "question": "Agent eval 指标有哪些？",
                "answer_hint": "success rate tool accuracy",
                "source_uri": "manual://interview",
            },
        ).json()
        client.post(
            "/interview/questions",
            json={
                "question": "RAG 召回失败怎么排查？",
                "answer_hint": "query chunk rerank",
                "source_uri": "manual://interview",
            },
        )

        response = client.post(
            "/interview/chat/stream",
            json={
                "session_id": "plan-session",
                "question_id": answered["id"],
                "answer": "看最终答案。",
            },
        )
        plan = client.get("/interview/session-plan?size=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(plan.status_code, 200)
        payload = plan.json()
        self.assertIn("agent_eval", payload["focus_topics"])
        self.assertEqual(payload["items"][0]["id"], followup["id"])
        self.assertNotEqual(payload["items"][0]["id"], answered["id"])
        self.assertNotIn("user_answer", str(payload))

    def test_manual_question_route_creates_question(self):
        client = TestClient(create_app(test_mode=True))

        response = client.post(
            "/interview/questions",
            json={
                "question": "MCP 和 Skill 的边界是什么？",
                "answer_hint": "MCP 是协议，Skill 是可复用能力资产。",
                "source_uri": "manual://interview",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["topic"], "mcp_skill")

    def test_free_interview_agent_chat_is_dialog_first(self):
        client = TestClient(create_app(test_mode=True))

        response = client.post(
            "/interview/agent/stream",
            json={"message": "你可以直接和我对话吗？", "history": []},
        )

        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("event: answer_delta", body)
        self.assertIn("自由对话", body)
        self.assertNotIn("SOP", body)
        self.assertNotIn("告警", body)

    def test_free_interview_agent_updates_short_term_memory(self):
        client = TestClient(create_app(test_mode=True))

        response = client.post(
            "/interview/agent/stream",
            json={
                "session_id": "short-memory-session",
                "message": "我希望做好短期记忆模块，不要只截断 history。",
                "history": [],
            },
        )
        context = runtime.interview_runtime.short_term_memory.build_context("short-memory-session")

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(context.canvas)
        self.assertIn("graph TD", context.canvas.mermaid)
        self.assertTrue(any(atom.kind == "constraint" for atom in context.atoms))
        self.assertIn("Short-term working memory", context.prompt_block)

    def test_provider_config_route_persists_without_returning_key(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "provider-config.json"
            with patch.dict("os.environ", {PROVIDER_CONFIG_PATH_ENV: str(config_path)}, clear=True):
                client = TestClient(create_app(test_mode=True))

                saved = client.post(
                    "/provider-config",
                    json={
                        "base_url": "http://127.0.0.1:8080/v1",
                        "model": "gpt-5.4",
                        "api_key": "secret-key",
                    },
                )
                loaded = client.get("/provider-config")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["base_url"], "http://127.0.0.1:8080/v1")
        self.assertEqual(loaded.json()["model"], "gpt-5.4")
        self.assertTrue(loaded.json()["has_api_key"])
        self.assertNotIn("secret-key", str(loaded.json()))

    def test_session_turn_route_returns_persisted_turns(self):
        client = TestClient(create_app(test_mode=True))
        created = client.post(
            "/interview/questions",
            json={
                "question": "Agent eval 怎么做？",
                "answer_hint": "task trial outcome",
                "source_uri": "manual://interview",
            },
        )
        question_id = created.json()["id"]

        response = client.post(
            "/interview/chat/stream",
            json={"session_id": "route-session", "question_id": question_id, "answer": "看最终答案。"},
        )
        turns = client.get("/interview/sessions/route-session/turns")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(turns.status_code, 200)
        item = turns.json()["items"][0]
        self.assertEqual(item["question_id"], question_id)
        self.assertEqual(item["answer_chars"], len("看最终答案。"))
        self.assertEqual(item["answer_preview"], "[answer hidden]")
        self.assertNotEqual(item["answer_preview"], "看最终答案。")
        self.assertNotIn("user_answer", item)
        self.assertTrue(item["scores"])
        self.assertIn("label", item["scores"][0])
        self.assertIn("criterion", item["scores"][0])

    def test_session_summary_route_returns_end_of_interview_summary(self):
        client = TestClient(create_app(test_mode=True))
        created = client.post(
            "/interview/questions",
            json={
                "question": "Agent memory 怎么设计？",
                "answer_hint": "L0 L1 L2 L3",
                "source_uri": "manual://interview",
            },
        )
        question_id = created.json()["id"]

        response = client.post(
            "/interview/chat/stream",
            json={
                "session_id": "summary-session",
                "question_id": question_id,
                "answer": "短期上下文加长期画像。",
            },
        )
        summary = client.get("/interview/sessions/summary-session/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary.status_code, 200)
        payload = summary.json()
        self.assertEqual(payload["session_id"], "summary-session")
        self.assertEqual(payload["completed"], 1)
        self.assertEqual(payload["turns"], 1)
        self.assertIn("average_score", payload)
        self.assertTrue(payload["next_step"])
        self.assertIn("final_review", payload)
        self.assertIn("本场面试到这里", payload["final_review"])
        self.assertEqual(payload["items"][0]["question_id"], question_id)
        self.assertTrue(payload["items"][0]["ai_review"])
        self.assertTrue(payload["items"][0]["scores"])
        self.assertIn("criterion", payload["items"][0]["scores"][0])
        self.assertNotIn("user_answer", payload["items"][0])
        self.assertNotIn("短期上下文加长期画像", str(payload))

    def test_session_report_route_returns_markdown_without_raw_answers(self):
        client = TestClient(create_app(test_mode=True))
        created = client.post(
            "/interview/questions",
            json={
                "question": "Agent eval 怎么做？",
                "answer_hint": "outcome transcript grader",
                "source_uri": "manual://interview",
            },
        )
        question_id = created.json()["id"]

        response = client.post(
            "/interview/chat/stream",
            json={
                "session_id": "report-session",
                "question_id": question_id,
                "answer": "我的原始回答不要出现在报告里。",
            },
        )
        report = client.get("/interview/sessions/report-session/report")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(report.status_code, 200)
        payload = report.json()
        self.assertEqual(payload["session_id"], "report-session")
        self.assertIn("# 面试报告", payload["markdown"])
        self.assertIn("Agent eval 怎么做", payload["markdown"])
        self.assertIn("## 题目复盘", payload["markdown"])
        self.assertIn("AI 评价", payload["markdown"])
        self.assertNotIn("评分依据", payload["markdown"])
        self.assertNotIn("user_answer", payload["markdown"])
        self.assertNotIn("我的原始回答", payload["markdown"])

    def test_review_route_returns_server_backed_summary(self):
        client = TestClient(create_app(test_mode=True))
        created = client.post(
            "/interview/questions",
            json={
                "question": "RAG 召回失败怎么排查？",
                "answer_hint": "query chunk BM25 vector RRF",
                "source_uri": "manual://interview",
            },
        )
        question_id = created.json()["id"]

        response = client.post(
            "/interview/chat/stream",
            json={"session_id": "review-session", "question_id": question_id, "answer": "调大 top_k。"},
        )
        follow_up = client.post(
            "/interview/chat/stream",
            json={"session_id": "review-session", "question_id": question_id, "answer": "再补充 query rewrite 和 rerank。"},
        )
        review = client.get("/interview/review")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(review.status_code, 200)
        payload = review.json()
        self.assertEqual(payload["completed"], 1)
        self.assertIn("average_score", payload)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["question_id"], question_id)
        self.assertIn("RAG", payload["items"][0]["question"])
        self.assertEqual(payload["items"][0]["attempts"], 2)
        self.assertTrue(payload["items"][0]["ai_review"])
        self.assertTrue(payload["items"][0]["scores"])
        self.assertIn("reason", payload["items"][0]["scores"][0])
        self.assertNotIn("user_answer", payload["items"][0])

    def test_web_login_routes_store_only_metadata(self):
        client = TestClient(create_app(test_mode=True))

        created = client.post("/interview/web-login", json={"host": "https://www.nowcoder.com/discuss/1"})
        listed = client.get("/interview/web-login")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["host"], "nowcoder.com")
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("cookie", str(listed.json()).casefold())

    def test_browser_open_login_route_uses_disabled_connector_in_test_mode(self):
        client = TestClient(create_app(test_mode=True))

        response = client.post(
            "/interview/browser/open-login",
            json={"url": "https://www.nowcoder.com/discuss/1"},
        )
        listed = client.get("/interview/web-login")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["opened"])
        self.assertEqual(response.json()["host"], "nowcoder.com")
        self.assertIn("INTERVIEW_ENABLE_BROWSER", response.json()["error"])
        self.assertEqual(listed.json()["entries"], [])

    def test_source_platform_routes_expose_three_login_states(self):
        client = TestClient(create_app(test_mode=True))
        client.post(
            "/interview/questions",
            json={
                "question": "Agent eval 怎么做？",
                "answer_hint": "outcome transcript grader",
                "source_uri": "https://www.nowcoder.com/search?query=agent",
            },
        )

        listed = client.get("/interview/source-platforms")
        opened = client.post("/interview/source-platforms/nowcoder/open-login")
        synced = client.post("/interview/source-platforms/nowcoder/sync")
        missing = client.post("/interview/source-platforms/github/open-login")
        nowcoder = listed.json()["platforms"][0]

        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()["platforms"]], ["nowcoder", "xiaohongshu", "zhihu"])
        self.assertEqual(
            [item["icon_path"] for item in listed.json()["platforms"]],
            [
                "/static/assets/source-platforms/nowcoder.ico",
                "/static/assets/source-platforms/xiaohongshu.ico",
                "/static/assets/source-platforms/zhihu.ico",
            ],
        )
        self.assertFalse(nowcoder["connected"])
        self.assertEqual(nowcoder["snapshots"], 0)
        self.assertEqual(nowcoder["questions"], 0)
        self.assertEqual(nowcoder["needs_login"], 0)
        self.assertEqual(nowcoder["recent_questions"][0]["question"], "Agent eval 怎么做？")
        self.assertEqual(nowcoder["recent_questions"][0]["source_uri"], "https://www.nowcoder.com/search?query=agent")
        self.assertEqual(opened.status_code, 200)
        self.assertFalse(opened.json()["opened"])
        self.assertEqual(opened.json()["host"], "nowcoder.com")
        self.assertEqual(synced.status_code, 200)
        self.assertTrue(synced.json()["job_id"].startswith("job-"))
        self.assertEqual(synced.json()["platform_id"], "nowcoder")
        self.assertIn(synced.json()["state"], {"queued", "running", "needs_login"})
        latest = client.get("/interview/source-platforms/nowcoder/jobs/latest")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["job_id"], synced.json()["job_id"])
        self.assertIn("updated_at", latest.json())
        self.assertEqual(missing.status_code, 404)

    def test_source_platform_routes_expose_login_probe_metadata(self):
        client = TestClient(create_app(test_mode=True))
        client.post("/interview/web-login", json={"host": "nowcoder.com"})
        runtime.interview_runtime.store.update_web_login_metadata(
            "nowcoder.com",
            {
                "login_probe_state": "verified",
                "login_probe_reason": "检测到登录后页面特征",
                "login_probe_at": "2026-05-17T00:00:00Z",
            },
        )

        listed = client.get("/interview/source-platforms")
        nowcoder = listed.json()["platforms"][0]

        self.assertEqual(nowcoder["login_probe_state"], "verified")
        self.assertEqual(nowcoder["login_probe_reason"], "检测到登录后页面特征")
        self.assertEqual(nowcoder["login_probe_at"], "2026-05-17T00:00:00Z")

    def test_source_platform_login_state_matches_sibling_host(self):
        client = TestClient(create_app(test_mode=True))
        runtime.interview_runtime.store.upsert_web_login(
            "account.zhihu.com",
            runtime.interview_runtime._profile_dir_for_host("account.zhihu.com"),
        )

        listed = client.get("/interview/source-platforms")
        zhihu = next(item for item in listed.json()["platforms"] if item["id"] == "zhihu")

        self.assertEqual(listed.status_code, 200)
        self.assertTrue(zhihu["connected"])
        self.assertEqual(zhihu["status"], "已授权")

    def test_source_platform_routes_expose_quality_metadata(self):
        client = TestClient(create_app(test_mode=True))
        runtime.interview_runtime.store.upsert_collection_job(
            CollectionJobStatus(
                job_id="job-quality",
                platform_id="nowcoder",
                state="completed",
                message="后台采集完成",
                snapshots=2,
                questions=2,
                metadata={
                    "unique_questions": 1,
                    "duplicate_questions": 1,
                    "source_pages": 3,
                    "detail_pages": 2,
                    "rejected_blocks": 4,
                    "effective_question_rate": 0.5,
                    "quality_status": "partial",
                    "quality_message": "采集有效，新增 1 / 重复 1",
                    "dry_run": True,
                    "visited_pages": ["搜索页：牛客搜索 - https://www.nowcoder.com/search?q=agent"],
                    "accepted_questions": ["Agent Eval 怎么做？"],
                    "rejected_candidates": ["怎么学Agent？（求资料、求路线或流程咨询，不像面试题）"],
                    "rewritten_questions": ["agent出错率，是模型问题还是RAG还是Prompt？ -> Agent 出错时，如何区分是模型、RAG 还是 Prompt 的问题？"],
                },
            )
        )

        listed = client.get("/interview/source-platforms")
        latest = client.get("/interview/source-platforms/nowcoder/jobs/latest")
        nowcoder = listed.json()["platforms"][0]

        self.assertEqual(nowcoder["unique_questions"], 1)
        self.assertEqual(nowcoder["duplicate_questions"], 1)
        self.assertEqual(nowcoder["source_pages"], 3)
        self.assertEqual(nowcoder["detail_pages"], 2)
        self.assertEqual(nowcoder["rejected_blocks"], 4)
        self.assertEqual(nowcoder["effective_question_rate"], 0.5)
        self.assertEqual(nowcoder["quality_status"], "partial")
        self.assertIn("新增 1", nowcoder["quality_message"])
        self.assertTrue(nowcoder["dry_run"])
        self.assertIn("牛客搜索", nowcoder["visited_pages"][0])
        self.assertEqual(nowcoder["accepted_questions"], ["Agent Eval 怎么做？"])
        self.assertTrue(nowcoder["rejected_candidates"])
        self.assertEqual(latest.json()["unique_questions"], 1)
        self.assertEqual(latest.json()["quality_status"], "partial")
        self.assertTrue(latest.json()["dry_run"])
        self.assertTrue(latest.json()["rewritten_questions"])

    def test_resume_upload_imports_source_snapshot(self):
        client = TestClient(create_app(test_mode=True))

        initial = client.get("/interview/resume")
        uploaded = client.post(
            "/interview/resume/upload",
            files={"file": ("resume.txt", b"AI Agent resume\nRAG Memory Eval", "text/plain")},
        )
        status = client.get("/interview/resume")

        self.assertEqual(initial.status_code, 200)
        self.assertFalse(initial.json()["imported"])
        self.assertEqual(uploaded.status_code, 200)
        self.assertTrue(uploaded.json()["imported"])
        self.assertEqual(uploaded.json()["title"], "resume.txt")
        self.assertGreater(uploaded.json()["chars"], 20)
        self.assertTrue(status.json()["imported"])

    def test_source_platform_delete_uses_known_host(self):
        client = TestClient(create_app(test_mode=True))
        client.post("/interview/web-login", json={"host": "https://www.zhihu.com/question/1"})

        deleted = client.delete("/interview/source-platforms/zhihu")
        listed = client.get("/interview/source-platforms")

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["host"], "zhihu.com")
        self.assertTrue(deleted.json()["deleted"])
        zhihu = [item for item in listed.json()["platforms"] if item["id"] == "zhihu"][0]
        self.assertFalse(zhihu["connected"])

    def test_delete_web_login_route_removes_metadata(self):
        client = TestClient(create_app(test_mode=True))
        client.post("/interview/web-login", json={"host": "https://www.nowcoder.com/discuss/1"})

        deleted = client.delete("/interview/web-login/nowcoder.com")
        listed = client.get("/interview/web-login")

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["host"], "nowcoder.com")
        self.assertTrue(deleted.json()["deleted"])
        self.assertEqual(listed.json()["entries"], [])

    def test_import_web_returns_login_request_when_browser_disabled(self):
        client = TestClient(create_app(test_mode=True))

        response = client.post(
            "/interview/sources/import-web",
            json={"url": "https://www.nowcoder.com/discuss/1"},
        )
        listed = client.get("/interview/source-platforms")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["needs_login"], 1)
        self.assertFalse(listed.json()["platforms"][0]["connected"])


if __name__ == "__main__":
    unittest.main()
