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
        with patch.object(self.app.source, "discover", return_value=[candidate]):
            preview = self.app.guidance_preview(session["id"], turn["session"]["draft"])
        self.assertEqual(preview["items"][0]["key"], "candidate-1")
        result = self.app.finalize_guidance(session["id"], preview["session"]["draft"], ["candidate-1"])
        self.assertEqual(result["selected"], 1)
        self.assertEqual(self.app.store.guidance_session(session["id"])["status"], "confirmed")
        project = self.app.projects.get_project(result["project_id"])
        self.assertEqual(project["creation_mode"], "ai_guided")
        self.assertEqual(self.app.store.project_papers(result["project_id"])[0]["relation_kind"], "imported")

    def test_guidance_local_fallback_and_turn_cap(self):
        session = self.app.create_guidance_session("本地项目", "稀疏检索")
        with patch.object(self.app.gateway, "call", return_value={"ok": False, "degraded": True, "reason": "no API key"}):
            for i in range(GUIDANCE_MAX_TURNS):
                result = self.app.guidance_turn(session["id"], f"补充方向 {i}")
                self.assertEqual(result["mode"], "local")
                self.assertTrue(result["degraded"])
        with self.assertRaises(ValueError):
            self.app.guidance_turn(session["id"], "再问一轮")

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

    def test_project_creation_rejects_invalid_mode(self):
        with self.assertRaises(ValueError):
            self.app.create_project("坏项目", "unknown")

    def test_finalize_ignores_unpreviewed_client_candidates(self):
        session = self.app.create_guidance_session("安全项目", "本地检索")
        result = self.app.finalize_guidance(session["id"], {
            "keywords": ["injected"],
            "candidates": [self.paper("injected-paper")],
        }, ["injected-paper"])
        self.assertEqual(result["selected"], 0)
        self.assertEqual(self.app.store.project_papers(result["project_id"]), [])


if __name__ == "__main__":
    unittest.main()
