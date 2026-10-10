"""PROJECT-01: resumable guided creation, local degradation and explicit cross-project sharing.

No test performs a network request: the source and gateway transport are replaced.
"""
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from recommendation_fixtures import english_papers
from app.service import App, GUIDANCE_MAX_TURNS

ROOT = Path(__file__).resolve().parents[1]


def candidate(key, title="Candidate world model"):
    return {"key": key, "title": title, "abstract": "planning", "published": "2026-09-01",
            "source": "openalex", "group_name": "field"}


class GuidedCreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "PDH_DEV": "0"})
        env.start()
        self.addCleanup(env.stop)
        # project_guidance is owner-approved, so the gateway would really send: the transport is
        # replaced for every test here and an offline network must leave the session usable.
        transport = mock.patch("app.gateway.urllib.request.urlopen",
                               side_effect=urllib.error.URLError("offline"))
        self.urlopen = transport.start()
        self.addCleanup(transport.stop)
        self.data = Path(self.tmp.name) / "app"
        self.app = App(root=ROOT, data_dir=self.data)

    def answer_like_the_model(self, keywords=("world models",)):
        reply = {"reply": "先限定场景", "draft": {"keywords": list(keywords), "search_queries": ["world models planning"],
                                                  "learning_path": [], "next_question": "哪类环境？"}}
        body = json.dumps({"model": "deepseek-flash", "choices": [{"message": {"content": json.dumps(reply)}}],
                           "usage": {"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400}}).encode()
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = body
        self.urlopen.side_effect = None
        self.urlopen.return_value = response

    def test_approved_guidance_turn_uses_the_model_reply(self):
        self.answer_like_the_model()
        session = self.app.create_guidance_session("接模型", "world models")
        turn = self.app.guidance_turn(session["id"], "world models")
        self.assertEqual(turn["mode"], "ai")
        self.assertFalse(turn["degraded"])
        self.assertEqual(turn["reply"], "先限定场景")
        self.assertEqual(turn["tokens"], 400)
        self.assertIsNone(turn["reason_code"])
        self.assertEqual(self.urlopen.call_count, 1)

    def test_guidance_prompt_schema_example_is_valid_json(self):
        session = self.app.create_guidance_session("提示", "world models")
        self.app.guidance_turn(session["id"], "world models")
        system = json.loads(self.urlopen.call_args[0][0].data)["messages"][0]["content"]
        schema = json.loads(system[system.index("{"):system.rindex("}") + 1])
        self.assertEqual(set(schema["d"]), {"k", "q", "a", "c", "s", "ready"})

    def test_draft_resumes_after_restart(self):
        session = self.app.create_guidance_session("可恢复", "world model planning")
        self.answer_like_the_model(["robot manipulation"])
        self.app.guidance_turn(session["id"], "robot manipulation")
        restarted = App(root=ROOT, data_dir=self.data)
        resumed = restarted.store.guidance_session(session["id"])
        self.assertEqual(resumed["status"], "draft")
        self.assertEqual(resumed["turn_count"], 1)
        self.assertIn("robot manipulation", json.dumps(resumed["transcript"], ensure_ascii=False))
        with mock.patch.object(restarted.source, "discover_topic", return_value=[candidate("c1")]):
            restarted.guidance_preview(session["id"])
        result = restarted.finalize_guidance(session["id"], selected_keys=["c1"])
        self.assertEqual(result["selected"], 1)

    def test_cancel_only_applies_to_drafts(self):
        session = self.app.create_guidance_session("取消", "x")
        self.assertTrue(self.app.cancel_guidance(session["id"])["cancelled"])
        for call in (lambda: self.app.guidance_turn(session["id"], "y"),
                     lambda: self.app.guidance_preview(session["id"]),
                     lambda: self.app.finalize_guidance(session["id"])):
            with self.assertRaises(ValueError):
                call()
        confirmed = self.app.create_guidance_session("确认", "x")
        self.app.finalize_guidance(confirmed["id"])
        with self.assertRaises(ValueError):
            self.app.cancel_guidance(confirmed["id"])
        with self.assertRaises(ValueError):
            self.app.finalize_guidance(confirmed["id"])
        self.assertEqual(self.app.store.guidance_session(confirmed["id"])["status"], "confirmed")
        with self.assertRaises(LookupError):
            self.app.cancel_guidance("missing")

    def test_turns_without_an_ai_answer_do_not_use_up_the_six(self):
        session = self.app.create_guidance_session("离线", "latent planning")
        for i in range(GUIDANCE_MAX_TURNS + 2):  # offline transport: every turn degrades to local
            turn = self.app.guidance_turn(session["id"], f"方向 {i}")
            self.assertEqual((turn["mode"], turn["reason_code"]), ("local", "network"))
        self.assertEqual(self.app.store.guidance_session(session["id"])["turn_count"], 0)

    def test_retry_asks_the_model_again_without_recording_the_question_twice(self):
        session = self.app.create_guidance_session("重试", "latent planning")
        self.app.guidance_turn(session["id"], "world models")  # offline: local answer
        self.answer_like_the_model()
        turn = self.app.guidance_turn(session["id"], None, retry=True)
        self.assertEqual(turn["mode"], "ai")
        roles = [m["role"] for m in turn["session"]["transcript"]]
        self.assertEqual(roles, ["user", "user", "assistant"])  # goal, question, one answer
        self.assertEqual(turn["session"]["turn_count"], 1)
        with self.assertRaisesRegex(ValueError, "重试"):
            self.app.guidance_turn(session["id"], None, retry=True)  # last answer came from the model

    def test_quick_creation_is_a_single_ai_call(self):
        session = self.app.create_guidance_session("快速", "world models", "quick")
        self.answer_like_the_model()
        self.assertEqual(self.app.guidance_turn(session["id"], "world models")["mode"], "ai")
        with self.assertRaisesRegex(ValueError, "快速创建"):
            self.app.guidance_turn(session["id"], "再问一次")
        self.assertEqual(self.urlopen.call_count, 1)

    def test_the_reason_a_turn_had_no_ai_is_named(self):
        session = self.app.create_guidance_session("原因", "latent planning")
        turn = self.app.guidance_turn(session["id"], "a", dry_run=True)
        self.assertEqual(turn["reason_code"], "dry_run")
        import io
        self.urlopen.side_effect = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b""))
        turn = self.app.guidance_turn(session["id"], "b")
        self.assertEqual((turn["reason_code"], turn["mode"]), ("http", "local"))
        self.assertIn("401", turn["reason"])
        self.assertIn("401", self.app.store.guidance_session(session["id"])["transcript"][-1]["reason_text"])
        self.urlopen.side_effect = None
        self.urlopen.return_value = mock.MagicMock()
        self.urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "not json"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        turn = self.app.guidance_turn(session["id"], "c")
        self.assertEqual(turn["reason_code"], "bad_reply")
        self.assertEqual(self.app.store.guidance_session(session["id"])["transcript"][-1]["reason"], "bad_reply")

    def test_search_streams_per_query_and_merges_candidates(self):
        session = self.app.create_guidance_session("流式", "world models")
        with mock.patch.object(self.app.source, "discover_topic", return_value=[candidate("a"), candidate("b")]):
            first = self.app.guidance_search(session["id"], "world models")
        with mock.patch.object(self.app.source, "discover_topic", return_value=[candidate("b"), candidate("c")]):
            second = self.app.guidance_search(session["id"], "latent planning")
        self.assertEqual([i["new"] for i in first["items"]], [True, True])
        self.assertEqual([(i["key"], i["new"]) for i in second["items"]], [("b", False), ("c", True)])
        self.assertEqual(second["total"], 3)
        merged = {i["key"]: i["matched_queries"] for i in second["items"]}
        self.assertEqual(merged["b"], ["world models", "latent planning"])
        stored = self.app.store.guidance_session(session["id"])["draft"]["candidates"]
        self.assertEqual([p["key"] for p in stored], ["a", "b", "c"])

    def test_a_failed_query_reports_why_and_keeps_earlier_results(self):
        from app.sources import SourceError
        session = self.app.create_guidance_session("限流", "world models")
        with mock.patch.object(self.app.source, "discover_topic", return_value=[candidate("a")]):
            self.app.guidance_search(session["id"], "q1")
        with mock.patch.object(self.app.source, "discover_topic", side_effect=SourceError("503", "unavailable")):
            result = self.app.guidance_search(session["id"], "q2")
        self.assertEqual((result["items"], result["error"]["kind"], result["total"]), ([], "unavailable", 1))

    def test_after_six_turns_the_draft_can_still_be_edited_and_confirmed(self):
        session = self.app.create_guidance_session("六轮", "latent planning")
        self.answer_like_the_model()
        for i in range(GUIDANCE_MAX_TURNS):
            self.assertEqual(self.app.guidance_turn(session["id"], f"方向 {i}")["mode"], "ai")
        with self.assertRaises(ValueError):
            self.app.guidance_turn(session["id"], "第七轮")
        self.assertEqual(self.urlopen.call_count, GUIDANCE_MAX_TURNS)  # no retry, nothing after the cap
        edited = {"keywords": ["edited term"], "search_queries": ["edited query"]}
        with mock.patch.object(self.app.source, "discover_topic", return_value=[candidate("c1"), candidate("c2")]):
            preview = self.app.guidance_preview(session["id"], edited)
        self.assertEqual(len(preview["items"]), 2)
        result = self.app.finalize_guidance(session["id"], edited, ["c2", "not-previewed"])
        self.assertEqual(result["selected"], 1)
        project = self.app.projects.get_project(result["project_id"])
        self.assertEqual(project["keywords"], ["edited term"])
        self.assertEqual([p["key"] for p in self.app.store.project_papers(result["project_id"])], ["c2"])

    def test_no_candidate_is_added_without_explicit_selection(self):
        session = self.app.create_guidance_session("未勾选", "x")
        with mock.patch.object(self.app.source, "discover_topic", return_value=[candidate("c1")]):
            self.app.guidance_preview(session["id"])
        result = self.app.finalize_guidance(session["id"])
        self.assertEqual(result["selected"], 0)
        self.assertEqual(self.app.store.project_papers(result["project_id"]), [])

    def test_creation_completes_without_key_budget_or_network(self):
        cases = {
            "no_key": {"DEEPSEEK_API_KEY": ""},
            "ai_off": None,
        }
        for label, env in cases.items():
            with self.subTest(label):
                app = App(root=ROOT, data_dir=Path(self.tmp.name) / label)
                if env is None:
                    app.gateway.set_enabled(False)
                patch_env = mock.patch.dict(os.environ, env or {})
                with patch_env, mock.patch.object(app.gateway, "_key_candidates", return_value=iter(())), \
                        mock.patch("app.gateway.urllib.request.urlopen") as urlopen, \
                        mock.patch.object(app.source, "discover_topic",
                                          side_effect=urllib.error.URLError("offline")):
                    session = app.create_guidance_session("离线", "world model planning")
                    turn = app.guidance_turn(session["id"], "robotics")
                    preview = app.guidance_preview(session["id"])
                    result = app.finalize_guidance(session["id"])
                urlopen.assert_not_called()
                self.assertEqual(turn["mode"], "local")
                self.assertTrue(preview["errors"], "offline search failure is reported, not hidden")
                self.assertTrue(app.projects.get_project(result["project_id"]))

    def test_budget_refusal_keeps_guidance_local(self):
        from app.gateway import BudgetExceeded
        session = self.app.create_guidance_session("预算", "x")
        with mock.patch.object(self.app.gateway, "admit", side_effect=BudgetExceeded("daily token ceiling")), \
                mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            turn = self.app.guidance_turn(session["id"], "y")
        urlopen.assert_not_called()
        self.assertEqual(turn["mode"], "local")

    def test_project_deletion_removes_its_creation_transcript(self):
        session = self.app.create_guidance_session("私密", "private goal text")
        result = self.app.finalize_guidance(session["id"])
        other = self.app.create_guidance_session("草稿", "other goal")
        self.app.projects.delete_project(result["project_id"])
        self.assertIsNone(self.app.store.guidance_session(session["id"]))
        self.assertEqual(self.app.store.guidance_session(other["id"])["status"], "draft")


class CrossProjectSharingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name) / "app")
        self.a = self.app.create_project("A", "manual", ["world model"])["project_id"]
        self.b = self.app.create_project("B", "manual", ["planning"])["project_id"]
        self.app.store.upsert_papers([{**candidate("shared"), "project_id": self.a, "relation_kind": "seed"}])
        self.app.store.set_setting(f"seed_keys_{self.a}", ["shared"])

    def test_explicit_add_records_source_and_never_downgrades_a_seed(self):
        self.app.store.add_project_paper(self.b, "shared", "shared", source_project_id=self.a)
        rows = {r["project_id"]: r for r in self.app.store.paper_projects("shared")}
        self.assertEqual(rows[self.b]["source_project_name"], "A")
        # A later discovery of the same paper keeps the seed relation in A.
        self.app.store.upsert_papers([{**candidate("shared"), "project_id": self.a}])
        self.app.store.add_project_paper(self.a, "shared", "shared")
        self.assertEqual(self.app.seed_keys(self.a), ["shared"])
        with self.assertRaises(ValueError):
            self.app.store.add_project_paper(self.b, "shared", "shared", source_project_id="missing")
        with self.assertRaises(ValueError):
            self.app.store.add_project_paper(self.b, "unknown-paper")

    def test_feedback_saves_exposure_and_qa_stay_per_project(self):
        self.app.store.add_project_paper(self.b, "shared", "shared", source_project_id=self.a)
        self.app.record_feedback("shared", "useful", project_id=self.a)
        english_papers(self.app, self.b)
        self.app.build_batch(project_id=self.b)
        self.app.store.add_qa("shared", "user", "A question", project_id=self.a)
        self.assertEqual(self.app.latest_feedback(self.b), {})
        self.assertEqual(self.app.library(self.b), [])
        self.assertEqual(self.app.stats(self.a)["shown"], 0)
        self.assertEqual(self.app.stats(self.b)["shown"], 1)
        self.assertEqual(self.app.qa_history("shared", project_id=self.b), [])
        self.assertEqual(len(self.app.qa_history("shared", project_id=self.a)), 1)

    def test_removing_a_relation_keeps_global_facts(self):
        pdf = Path(self.tmp.name) / "shared.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        self.app.store.record_pdf("shared", pdf, "local")
        self.app.store.add_project_paper(self.b, "shared", "shared", source_project_id=self.a)
        self.app.record_feedback("shared", "irrelevant", project_id=self.b)
        self.app.store.remove_project_paper(self.b, "shared")
        self.assertIsNotNone(self.app.store.paper("shared"))
        self.assertTrue(self.app.store.pdf("shared") if hasattr(self.app.store, "pdf") else pdf.exists())
        self.assertEqual([r["project_id"] for r in self.app.store.paper_projects("shared")], [self.a])
        self.assertEqual(self.app.latest_feedback(self.b), {})
        # The event itself is retained (append-only), only hidden while unrelated.
        self.assertEqual(self.app.store.conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE project_id=?", (self.b,)).fetchone()[0], 1)
        self.assertEqual(self.app.seed_keys(self.a), ["shared"])


class URLProjectPrecedenceTests(unittest.TestCase):
    def test_url_project_id_wins_over_stored_project(self):
        """Execute the actual start-up selection lines from index.html."""
        source = (ROOT / "app/static/index.html").read_text()
        start = source.index("const requested = new URLSearchParams")
        end = source.index("await loadProjects();", start)
        snippet = source[start:end]
        script = (
            "const results=[];for (const [search, stored] of [['?project_id=url', 'stored'], ['', 'stored'], ['', null]]) {"
            "const window={location:{search}};const localStorage={getItem:()=>stored};const state={currentProject:'default'};"
            + snippet + "results.push(state.currentProject);}console.log(JSON.stringify(results));")
        try:
            output = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
        except FileNotFoundError:
            self.skipTest("node is not installed")
        self.assertEqual(json.loads(output.stdout), ["url", "stored", "default"])


if __name__ == "__main__":
    unittest.main()
