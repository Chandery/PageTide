"""Editing and deleting projects, and drafting a learning map for a project that already exists.

No real model is called: the gateway is replaced by a recorder that returns canned replies.
"""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import pathgraph as pg
from app import routeplan, server
from app.service import App

BRANCHED = {"concepts": [
    {"id": "a", "name": "Crystal structure", "terms": ["crystal structure", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Thermodynamics", "terms": ["thermodynamics", "phase diagram"], "hint": 1, "needs": []},
    {"id": "c", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial growth"], "hint": 2, "needs": ["a"]},
    {"id": "d", "name": "Nucleation", "terms": ["nucleation", "crystal growth kinetics"], "hint": 2, "needs": ["b"]},
    {"id": "e", "name": "MBE", "terms": ["molecular beam epitaxy", "mbe"], "hint": 3, "needs": ["c", "d"]}], "targets": ["e"]}
CHAIN = {"concepts": [{"id": f"c{i}", "name": f"Step {i}", "terms": [f"step {i}", f"s{i}"], "hint": i, "needs": [f"c{i - 1}"] if i > 1 else []} for i in range(1, 5)], "targets": ["c4"]}


def reply(payload, tokens=600):
    return {"ok": True, "content": json.dumps(payload), "usage": {"total_tokens": tokens}}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("半导体生长", "manual", ["epitaxy", "mbe", "crystal growth"])["project_id"]

    def gateway(self, result):
        calls = []

        def fake(operation, messages, dry_run=False):
            calls.append((operation, messages, dry_run))
            return result() if callable(result) else result
        patcher = mock.patch.object(self.app.gateway, "call", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls


class ManageTests(Fixture):
    def test_rename_changes_only_the_name(self):
        out = self.app.rename_project(self.pid, "  半导体晶体生长  ")
        self.assertEqual(out["name"], "半导体晶体生长")
        self.assertEqual(out["keywords"], ["epitaxy", "mbe", "crystal growth"])

    def test_rename_rejects_empty_long_non_text_and_unknown(self):
        for bad in ("", "   ", "x" * 121, None, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.app.rename_project(self.pid, bad)
        with self.assertRaises(ValueError):
            self.app.rename_project("no-such", "x")
        self.assertEqual(self.app.projects.get_project(self.pid)["name"], "半导体生长")

    def test_delete_removes_the_project_its_map_and_its_plan_counter_but_not_other_projects(self):
        other = self.app.create_project("别的", "manual", ["x"])["project_id"]
        self.app.route_save(self.pid, plan=BRANCHED)
        self.app.route_save(other, plan=BRANCHED)
        self.gateway(reply(BRANCHED))
        self.app.route_plan_project(self.pid, "我想学半导体生长")
        out = self.app.delete_project(self.pid)
        self.assertEqual(out["deleted"], self.pid)
        self.assertIn(other, out["remaining"])
        self.assertNotIn(self.pid, out["remaining"])
        self.assertIsNone(self.app.projects.get_project(self.pid))
        self.assertIsNone(self.app.store.get_setting(f"route_plan_project_{self.pid}"))
        self.assertEqual(len(self.app.route_get(other)["graph"]["concepts"]), 5)
        with self.assertRaises(ValueError):
            self.app.route_get(self.pid)

    def test_delete_first_writes_a_backup_that_still_holds_the_project_and_keeps_only_the_newest_few(self):
        import sqlite3
        out = self.app.delete_project(self.pid)
        backup = self.app.store.path.with_name(out["backup"])
        self.assertTrue(backup.exists())
        copy = sqlite3.connect(str(backup))
        try:
            self.assertEqual(copy.execute("SELECT name FROM projects WHERE id=?", (self.pid,)).fetchone()[0], "半导体生长")
        finally:
            copy.close()
        for i in range(5):
            self.app.delete_project(self.app.create_project(f"临时{i}", "manual", [])["project_id"])
        names = sorted(f.name for f in self.app.store.path.parent.glob("*.pre-delete-*.bak"))
        self.assertEqual(len(names), App.KEEP_DELETE_BACKUPS)

    def test_a_failed_backup_deletes_nothing(self):
        with mock.patch.object(self.app.store, "backup", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.app.delete_project(self.pid)
        self.assertIsNotNone(self.app.projects.get_project(self.pid))

    def test_an_empty_or_missing_id_never_falls_back_to_the_default_project(self):
        before = [p["id"] for p in self.app.projects.list_projects()]
        for bad in ("", "   ", None, 5, [], {}):
            for action in (lambda b: self.app.delete_project(b), lambda b: self.app.rename_project(b, "x"),
                           lambda b: self.app.route_plan_project(b, "我想学")):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    action(bad)
        self.assertEqual([p["id"] for p in self.app.projects.list_projects()], before)
        self.assertEqual(self.app.projects.get_project(self.pid)["name"], "半导体生长")
        self.assertEqual(list(self.app.store.path.parent.glob("*.pre-delete-*.bak")), [])

    def test_a_partial_backup_is_removed_whatever_the_failure_and_nothing_is_deleted(self):
        def broken(target):
            Path(target).write_bytes(b"partial")
            raise sqlite3.OperationalError("database or disk is full")
        with mock.patch.object(self.app.store, "backup", side_effect=broken):
            with self.assertRaises(sqlite3.OperationalError):
                self.app.delete_project(self.pid)
        self.assertEqual(list(self.app.store.path.parent.glob("*.pre-delete-*.bak")), [])
        self.assertIsNotNone(self.app.projects.get_project(self.pid))

    def test_pruning_keeps_the_backup_just_written_even_when_file_times_are_equal_or_odd(self):
        folder = self.app.store.path.parent
        for i in range(4):   # older backups with identical times, one dated in the future
            old = folder / f"{self.app.store.path.name}.pre-delete-2026010{i + 1}-000000-aaaaaaa{i}.bak"
            old.write_bytes(b"x")
            os.utime(old, (4_000_000_000 if i == 0 else 1_000_000_000,) * 2)
        out = self.app.delete_project(self.pid)
        kept = sorted(f.name for f in folder.glob("*.pre-delete-*.bak"))
        name = self.app.store.path.name
        # the order is the timestamp in the name, not the file time: the oldest names go, the future-dated one among them
        self.assertEqual(kept, sorted([f"{name}.pre-delete-20260103-000000-aaaaaaa2.bak", f"{name}.pre-delete-20260104-000000-aaaaaaa3.bak", out["backup"]]))

    def test_pruning_only_ever_touches_delete_backups(self):
        folder = self.app.store.path.parent
        other = folder / f"{self.app.store.path.name}.pre-v7.bak"
        other.write_bytes(b"keep")
        lookalike = folder / "notes.pre-delete-1.bak"
        lookalike.write_bytes(b"keep")
        for i in range(5):
            self.app.delete_project(self.app.create_project(f"临时{i}", "manual", [])["project_id"])
        self.assertTrue(other.exists() and lookalike.exists())

    def test_delete_of_an_unknown_project_is_an_error_and_deletes_nothing(self):
        with self.assertRaises(ValueError):
            self.app.delete_project("no-such")
        self.assertIsNotNone(self.app.projects.get_project(self.pid))

    def test_deleting_the_last_project_leaves_the_app_usable(self):
        for p in self.app.projects.list_projects():
            self.app.delete_project(p["id"])
        self.assertEqual(self.app.projects.list_projects(), [])
        self.assertTrue(self.app.get_default_project_id())   # an empty default appears on next use


class ProjectPlanTests(Fixture):
    GOAL = "我想系统了解半导体晶体生长，尤其是 MBE"

    def test_a_good_reply_is_a_proposal_that_saves_nothing(self):
        calls = self.gateway(reply(BRANCHED))
        out = self.app.route_plan_project(self.pid, self.GOAL)
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "ai")
        self.assertEqual(len(out["graph"]["concepts"]), 5)
        self.assertEqual(out["attempts_left"], 2)
        self.assertEqual([c[0] for c in calls], ["learning_path_plan_project"])
        self.assertIsNone(self.app.route_get(self.pid)["graph"])   # nothing was saved

    def test_the_report_says_whether_the_map_is_branched(self):
        self.gateway(reply(BRANCHED))
        shape = self.app.route_plan_project(self.pid, self.GOAL)["report"]["shape"]
        self.assertEqual((shape["roots"], shape["levels"], shape["width"], shape["chain"]), (2, 3, 2, False))
        self.gateway(reply(CHAIN))
        shape = self.app.route_plan_project(self.pid, self.GOAL)["report"]["shape"]
        self.assertTrue(shape["chain"])

    def test_the_model_sees_only_the_goal_and_the_first_five_keywords(self):
        self.app.projects.update_project(self.pid, keywords=[f"kw{i}" for i in range(9)])
        self.app.create_project("Secret other", "manual", ["classified"])
        self.app.store.upsert_papers([{"key": "x", "title": "PRIVATE TITLE", "abstract": "private abstract", "published": "2026-01-01"}])
        calls = self.gateway(reply(BRANCHED))
        self.app.route_plan_project(self.pid, self.GOAL)
        sent = json.dumps(calls[0][1], ensure_ascii=False)
        for forbidden in ("Secret other", "classified", "PRIVATE TITLE", "private abstract", "kw5", "半导体生长\""):
            self.assertNotIn(forbidden, sent)
        for wanted in ("kw0", "kw4", "MBE"):
            self.assertIn(wanted, sent)

    def test_an_empty_or_oversized_goal_is_refused_before_any_call(self):
        calls = self.gateway(reply(BRANCHED))
        for bad in ("", "   ", None, "字" * (routeplan.MAX_GOAL_CHARS + 1)):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.app.route_plan_project(self.pid, bad)
        self.assertEqual(calls, [])

    def test_three_paid_attempts_a_day_then_refused_without_a_call(self):
        calls = self.gateway(reply("not json at all"))
        for _ in range(App.PROJECT_PLANS_PER_DAY):
            self.assertEqual(self.app.route_plan_project(self.pid, self.GOAL)["reason_code"], "bad_reply")
        with self.assertRaises(ValueError):
            self.app.route_plan_project(self.pid, self.GOAL)
        self.assertEqual(len(calls), App.PROJECT_PLANS_PER_DAY)

    def test_the_limit_is_per_project_and_per_day(self):
        other = self.app.create_project("别的", "manual", ["y"])["project_id"]
        self.gateway(reply(BRANCHED))
        for _ in range(App.PROJECT_PLANS_PER_DAY):
            self.app.route_plan_project(self.pid, self.GOAL)
        self.assertTrue(self.app.route_plan_project(other, self.GOAL)["ok"])
        with mock.patch("app.service.time.strftime", return_value="2099-01-01"):
            self.assertTrue(self.app.route_plan_project(self.pid, self.GOAL)["ok"])

    def test_a_refusal_before_sending_costs_no_attempt(self):
        for result in ({"ok": False, "degraded": True, "disabled": True, "reason": "AI disabled"},
                       {"ok": False, "degraded": True, "reason": "no API key"},
                       {"ok": False, "degraded": True, "reason": "awaiting owner approval"},
                       {"ok": False, "degraded": True, "reason": "daily token ceiling"}):
            self.gateway(result)
            out = self.app.route_plan_project(self.pid, self.GOAL)
            self.assertFalse(out["ok"])
            self.assertEqual(out["attempts_left"], App.PROJECT_PLANS_PER_DAY)
        self.assertEqual(self.app.store.get_setting(f"route_plan_project_{self.pid}")["attempts"], 0)

    def test_a_timeout_of_unknown_cost_counts(self):
        self.gateway({"ok": False, "degraded": True, "usage_unknown": True, "reason": "TimeoutError: timed out"})
        self.assertEqual(self.app.route_plan_project(self.pid, self.GOAL)["attempts_left"], App.PROJECT_PLANS_PER_DAY - 1)

    def test_a_dry_run_counts_nothing_and_reaches_no_provider(self):
        calls = self.gateway({"ok": False, "degraded": True, "reason": "dry run"})
        out = self.app.route_plan_project(self.pid, self.GOAL, dry_run=True)
        self.assertEqual((out["ok"], calls[0][2]), (False, True))
        self.assertIsNone(self.app.store.get_setting(f"route_plan_project_{self.pid}"))

    def test_a_second_request_while_one_runs_is_refused(self):
        started, release = threading.Event(), threading.Event()

        def slow(operation, messages, dry_run=False):
            started.set()
            release.wait(3)
            return reply(BRANCHED)
        with mock.patch.object(self.app.gateway, "call", side_effect=slow):
            worker = threading.Thread(target=lambda: self.app.route_plan_project(self.pid, self.GOAL))
            worker.start()
            self.assertTrue(started.wait(3))
            with self.assertRaises(ValueError):
                self.app.route_plan_project(self.pid, self.GOAL)
            release.set()
            worker.join(5)
        self.assertEqual(self.app.store.get_setting(f"route_plan_project_{self.pid}")["attempts"], 1)

    def test_if_the_project_operation_is_not_approved_the_real_gateway_refuses_and_costs_nothing(self):
        ops = json.loads((ROOT / "harness" / "budget.json").read_text())["operations"]
        self.assertIs(ops["learning_path_plan"]["owner_approved"], True)            # raised cap 1200 -> 1400, approved by the owner on 2026-10-06
        self.assertIs(ops["learning_path_plan_project"]["owner_approved"], True)
        self.assertIn("2026-10-06", ops["learning_path_plan_project"]["approval_note"])
        self.assertIn("owner", ops["learning_path_plan_project"]["approval_note"])
        self.assertIn("2026-10-05", ops["learning_path_plan_project"]["approval_note"])
        self.app.gateway.config["operations"]["learning_path_plan_project"]["owner_approved"] = False
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            out = self.app.route_plan_project(self.pid, self.GOAL)
        urlopen.assert_not_called()
        self.assertEqual((out["ok"], out["reason_code"]), (False, "not_approved"))
        self.assertEqual(out["attempts_left"], App.PROJECT_PLANS_PER_DAY)   # refused before sending: no attempt used

    def test_the_project_operation_has_its_own_prompt_file_identical_to_the_session_one(self):
        ops = json.loads((ROOT / "harness" / "budget.json").read_text())["operations"]
        a, b = ops["learning_path_plan"], ops["learning_path_plan_project"]
        self.assertNotEqual(a["prompt"], b["prompt"])
        for key in ("cap", "reference", "input_cap_components", "trigger", "enabled_by_default"):
            self.assertEqual(a[key], b[key], key)
        text = (ROOT / b["prompt"]).read_text(encoding="utf-8")
        self.assertIn("operation: learning_path_plan_project", text)
        self.assertIn(routeplan.SYSTEM, text)

    def test_unknown_project_is_refused(self):
        with self.assertRaises(ValueError):
            self.app.route_plan_project("no-such", self.GOAL)

    def test_a_proposal_can_then_be_saved_like_any_map(self):
        self.gateway(reply(BRANCHED))
        graph = self.app.route_plan_project(self.pid, self.GOAL)["graph"]
        saved = self.app.route_save(self.pid, graph=graph, revision=0)
        self.assertEqual(len(saved["graph"]["concepts"]), 5)
        self.assertEqual({c["status"] if "status" in c else p["status"] for c, p in [(c, saved["progress"][c["id"]]) for c in saved["graph"]["concepts"]]} >= {"unlocked", "locked"}, True)


class PromptTests(unittest.TestCase):
    def test_the_prompt_asks_for_a_dependency_graph_not_a_line(self):
        for needle in ("依赖图", "入口", "2–3 个前置", "一线"):
            self.assertIn(needle, routeplan.SYSTEM)

    def test_shape_counts_levels_roots_and_chains(self):
        graph, _ = pg.normalize(BRANCHED)
        self.assertEqual(pg.shape(graph), {"concepts": 5, "roots": 2, "levels": 3, "width": 2, "chain": False})
        chain, _ = pg.normalize(CHAIN)
        self.assertTrue(pg.shape(chain)["chain"])
        small, _ = pg.normalize({"concepts": [{"id": "a", "name": "A", "terms": ["a", "b"], "hint": 1, "needs": []}], "targets": []})
        self.assertFalse(pg.shape(small)["chain"])   # one or two concepts is not "a line", it is a small map


class HttpTests(Fixture):
    def serve(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def call(self, port, path, body=None, method=None, origin=None):
        headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_rename_and_delete_over_http(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.call(port, f"/api/projects/{self.pid}", {"action": "rename", "name": "新名字"})
            self.assertEqual((status, body["project"]["name"]), (200, "新名字"))
            self.assertEqual(self.call(port, f"/api/projects/{self.pid}", {"action": "rename", "name": ""})[0], 400)
            self.assertEqual(self.call(port, f"/api/projects/{self.pid}", {"action": "bogus"})[0], 400)
            self.assertEqual(self.call(port, "/api/projects/nope", {"action": "rename", "name": "x"})[0], 404)
            self.assertEqual(self.call(port, "/api/projects/nope", method="DELETE")[0], 404)
            status, body = self.call(port, f"/api/projects/{self.pid}", method="DELETE")
            self.assertEqual((status, body["deleted"]), (200, self.pid))
            self.assertNotIn(self.pid, [p["id"] for p in self.call(port, "/api/projects")[1]["projects"]])

    def test_a_foreign_origin_cannot_rename_or_delete(self):
        port = self.serve()
        self.assertEqual(self.call(port, f"/api/projects/{self.pid}", {"action": "rename", "name": "x"}, origin="http://evil.example")[0], 403)
        self.assertEqual(self.call(port, f"/api/projects/{self.pid}", method="DELETE", origin="http://evil.example")[0], 403)
        self.assertIsNotNone(self.app.projects.get_project(self.pid))

    def test_the_plan_action_rejects_an_empty_goal_and_an_unknown_project_with_400(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            self.assertEqual(self.call(port, "/api/route", {"action": "plan", "project_id": self.pid, "goal": ""})[0], 400)
            self.assertEqual(self.call(port, "/api/route", {"action": "plan", "project_id": "nope", "goal": "x"})[0], 400)
            self.assertEqual(self.call(port, "/api/route", {"action": "plan", "goal": "x"})[0], 400)   # no id: never the default project

    def test_the_plan_action_returns_a_proposal_over_http_and_saves_nothing(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}), \
                mock.patch("app.gateway.Gateway.call", return_value=reply(BRANCHED)) as call:
            status, body = self.call(port, "/api/route", {"action": "plan", "project_id": self.pid, "goal": "我想学半导体生长"})
            self.assertEqual((status, body["ok"], len(body["graph"]["concepts"]), body["attempts_left"]), (200, True, 5, 2))
            self.assertEqual(call.call_args[0][0], "learning_path_plan_project")
            self.assertIsNone(self.call(port, f"/api/route?project_id={self.pid}")[1]["graph"])

    def test_deleting_or_renaming_with_an_empty_id_is_refused_over_http(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            self.assertEqual(self.call(port, "/api/projects/", method="DELETE")[0], 404)
            self.assertEqual(self.call(port, "/api/projects/", {"action": "rename", "name": "x"})[0], 404)
            self.assertIsNotNone(self.app.projects.get_project(self.pid))
            self.assertEqual(self.app.projects.get_project(self.pid)["name"], "半导体生长")


if __name__ == "__main__":
    unittest.main()
