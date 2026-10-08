import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.service import App, GUIDANCE_MAX_TURNS


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=".", data_dir=Path(self.tmp.name) / "app")
        # project_guidance is approved: a test that forgets to replace the gateway must fail, not call out.
        transport = patch("app.gateway.urllib.request.urlopen",
                          side_effect=AssertionError("tests must not reach the network"))
        transport.start()
        self.addCleanup(transport.stop)

    def paper(self, key="shared-1"):
        return {"key": key, "title": "Shared World Model", "abstract": "planning and prediction",
                "published": "2026-09-01", "source": "test", "group_name": "field"}

    def test_shared_paper_has_independent_library_and_feedback(self):
        p1 = self.app.create_project("项目一")["project_id"]
        p2 = self.app.create_project("项目二")["project_id"]
        self.app.store.upsert_papers([{**self.paper(), "project_id": p1}])
        self.app.store.upsert_papers([{**self.paper(), "project_id": p2}])
        self.assertEqual({x["project_id"] for x in self.app.store.paper_projects("shared-1")}, {p1, p2})
        self.app.record_feedback("shared-1", "useful", project_id=p1)
        self.app.record_feedback("shared-1", "irrelevant", project_id=p2)
        self.assertEqual([x["key"] for x in self.app.library(p1)], ["shared-1"])
        self.assertEqual(self.app.library(p2), [])
        self.assertEqual(self.app.latest_feedback(p1)["shared-1"]["action"], "useful")
        self.assertEqual(self.app.latest_feedback(p2)["shared-1"]["action"], "irrelevant")
        self.assertEqual(self.app.profile_insights(p2)["signals"]["negative"], 1)
        self.app.projects.delete_project(p1)
        self.assertIsNotNone(self.app.store.paper("shared-1"))
        self.assertEqual([x["project_id"] for x in self.app.store.paper_projects("shared-1")], [p2])

    def test_guidance_session_turn_preview_and_finalize(self):
        session = self.app.create_guidance_session("新项目", "理解具身世界模型")
        self.assertEqual(session["status"], "draft")
        payload = '{"reply":"建议先限定规划场景","draft":{"keywords":["world models","JEPA"],"search_queries":["world models embodied planning"],"learning_path":[{"title":"基础","purpose":"理解预测表示"}],"next_question":"关注哪类环境？"}}'
        with patch.object(self.app.gateway, "call", return_value={"ok": True, "content": payload}):
            turn = self.app.guidance_turn(session["id"], "重点关注规划")
        self.assertEqual(turn["mode"], "ai")
        self.assertEqual(turn["session"]["turn_count"], 1)
        candidate = self.paper("candidate-1")
        with patch.object(self.app.source, "discover_topic", return_value=[candidate]):
            preview = self.app.guidance_preview(session["id"], turn["session"]["draft"])
        self.assertEqual(preview["items"][0]["key"], "candidate-1")
        result = self.app.finalize_guidance(session["id"], preview["session"]["draft"], ["candidate-1"])
        self.assertEqual(result["selected"], 1)
        self.assertEqual(self.app.store.guidance_session(session["id"])["status"], "confirmed")
        project = self.app.projects.get_project(result["project_id"])
        self.assertEqual(project["creation_mode"], "ai_guided")
        self.assertEqual(self.app.store.project_papers(result["project_id"])[0]["relation_kind"], "imported")

    def test_guidance_local_fallback_is_free_and_the_cap_counts_model_turns(self):
        session = self.app.create_guidance_session("本地项目", "稀疏检索")
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True, "reason": "no API key"}):
            for i in range(GUIDANCE_MAX_TURNS + 1):
                result = self.app.guidance_turn(session["id"], f"补充方向 {i}")
                self.assertEqual(result["mode"], "local")
                self.assertTrue(result["degraded"])
                self.assertEqual(result["reason_code"], "no_key")
        self.assertEqual(self.app.store.guidance_session(session["id"])["turn_count"], 0)
        payload = '{"reply":"好","draft":{"keywords":["a"],"search_queries":["a"],"learning_path":[],"next_question":""}}'
        with patch.object(self.app.gateway, "call", return_value={"ok": True, "content": payload}):
            for i in range(GUIDANCE_MAX_TURNS):
                self.assertEqual(self.app.guidance_turn(session["id"], f"模型 {i}")["mode"], "ai")
            with self.assertRaises(ValueError):
                self.app.guidance_turn(session["id"], "再问一轮")

    def test_the_transcript_is_bounded_even_without_the_model(self):
        from app.service import GUIDANCE_MAX_MESSAGES
        session = self.app.create_guidance_session("长对话", "稀疏检索")
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True}):
            with self.assertRaises(ValueError):
                for i in range(GUIDANCE_MAX_MESSAGES):
                    self.app.guidance_turn(session["id"], f"补充方向 {i}")
        self.assertLessEqual(len(self.app.store.guidance_session(session["id"])["transcript"]), GUIDANCE_MAX_MESSAGES)

    def test_first_turn_on_the_goal_is_not_recorded_twice(self):
        # Quick creation sends the goal itself as the first turn to get a reply.
        session = self.app.create_guidance_session("快速", "world model planning")
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True}):
            turn = self.app.guidance_turn(session["id"], "world model planning")
        roles = [m["role"] for m in turn["session"]["transcript"]]
        self.assertEqual(roles, ["user", "assistant"])
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True}):
            again = self.app.guidance_turn(session["id"], "world model planning")
        # A later identical answer is a real new turn.
        self.assertEqual([m["role"] for m in again["session"]["transcript"]], ["user", "assistant", "user", "assistant"])

    def test_local_guidance_says_when_it_finds_no_english_terms(self):
        session = self.app.create_guidance_session("中文", "用视频预训练的世界模型做机器人操作规划")
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True}):
            turn = self.app.guidance_turn(session["id"], "偏向真实机器人")
        self.assertEqual(turn["session"]["draft"]["keywords"], [])
        self.assertIn("英文", turn["reply"])
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True}):
            turn = self.app.guidance_turn(session["id"], "world model, robot manipulation")
        self.assertNotIn("英文", turn["reply"])
        self.assertIn("robot", turn["session"]["draft"]["keywords"])

    def test_malformed_or_failed_guidance_response_stays_local(self):
        session = self.app.create_guidance_session("容错项目", "研究检索")
        for response in ({"ok": True, "content": "not-json"}, RuntimeError("network")):
            with patch.object(self.app.gateway, "call", side_effect=response if isinstance(response, Exception) else None,
                              return_value=None if isinstance(response, Exception) else response):
                result = self.app.guidance_turn(session["id"], "限定方法")
            self.assertEqual(result["mode"], "local")

    def test_guidance_model_payload_is_bounded(self):
        session = self.app.create_guidance_session("边界项目", "x" * 4000)
        captured = {}
        def fake(operation, messages, **kwargs):
            captured["text"] = messages[-1]["content"]
            return {"ok": False, "reason": "no key"}
        with patch.object(self.app.gateway, "call", side_effect=fake):
            self.app.guidance_turn(session["id"], "y" * 2000)
        self.assertLess(len(captured["text"]), 4200)

    def test_preview_stops_after_openalex_is_unavailable(self):
        from app.sources import SourceError
        session = self.app.create_guidance_session("限流", "world model")
        draft = {**session["draft"], "search_queries": ["a", "b", "c"]}
        with patch.object(self.app.source, "discover_topic", side_effect=SourceError("503", "unavailable")) as discover:
            preview = self.app.guidance_preview(session["id"], draft)
        self.assertEqual(discover.call_count, 1)
        self.assertEqual(preview["items"], [])
        self.assertEqual([e["kind"] for e in preview["errors"]], ["unavailable"])

    def test_project_creation_rejects_invalid_mode(self):
        with self.assertRaises(ValueError):
            self.app.create_project("坏项目", "unknown")

    def test_finalize_ignores_unpreviewed_client_candidates(self):
        session = self.app.create_guidance_session("安全项目", "本地检索")
        result = self.app.finalize_guidance(session["id"], {
            "keywords": ["injected"],
            "candidates": [self.paper("injected-paper")],
        }, ["injected-paper"], skip_route=True)
        self.assertEqual(result["selected"], 0)
        self.assertEqual(self.app.store.project_papers(result["project_id"]), [])


if __name__ == "__main__":
    unittest.main()
