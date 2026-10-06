"""Growing the learning map: new directions are proposed from what the reader explicitly responded to, shown
with their evidence, and only a person's click adds one. Nothing here is automatic, and silence is no evidence."""
import json
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
from app import server
from app.organization import Conflict, Organization
from app.service import App

PLAN = {"concepts": [
    {"id": "a", "name": "Crystal basics", "terms": ["crystal growth", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial"], "hint": 2, "needs": ["a"]},
    {"id": "c", "name": "MBE", "terms": ["molecular beam epitaxy"], "hint": 3, "needs": ["b"]}], "targets": ["c"]}

# four papers about one direction the map does not cover, from two sources
NEW = [("s1", "Strain relaxation by misfit dislocation glide", "strain relaxation by misfit dislocation glide in thin films", "journal-a"),
       ("s2", "Modelling strain relaxation and dislocation glide", "strain relaxation by misfit dislocation glide in strained films", "journal-b"),
       ("s3", "Strain relaxation and dislocation glide in films", "strain relaxation through misfit dislocation glide in thin films", "journal-a"),
       ("s4", "Imaging strain relaxation by dislocation glide", "strain relaxation by misfit dislocation glide imaged in thin films", "journal-b")]


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
        self.pid = self.app.create_project("Crystals", "manual", ["epitaxy"])["project_id"]
        self.other = self.app.create_project("Poetry", "manual", ["poetry"])["project_id"]
        self.app.route_save(self.pid, plan=PLAN)
        for key, title, abstract, source in NEW:
            self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "source": source, "published": "2026-02-01"}], project_id=self.pid)

    def say(self, *pairs):
        for key, action in pairs:
            self.app.record_feedback(key, action, project_id=self.pid)

    def names(self):
        return [c["name"] for c in self.app.route_candidates(self.pid)["candidates"]]

    def pick(self):
        """The proposal about the new direction (the corpus may also yield a sibling phrase for it)."""
        return next(c for c in self.app.route_candidates(self.pid)["candidates"] if c["name"] == "strain relaxation")


class EvidenceTests(Fixture):
    def test_nothing_is_proposed_from_silence(self):
        self.assertEqual(self.names(), [])

    def test_useful_and_understood_papers_are_the_evidence(self):
        self.say(("s1", "useful"), ("s2", "understood"))
        self.assertIn("strain relaxation", self.names())

    def test_a_seed_counts_as_a_chosen_direction(self):
        self.app.store.add_project_paper(self.pid, "s1", "seed")
        self.app.store.add_project_paper(self.pid, "s2", "seed")
        self.app.store.set_setting(f"seed_keys_{self.pid}", ["s1", "s2"])
        self.assertIn("strain relaxation", self.names())

    def test_not_interested_never_creates_a_branch(self):
        self.say(("s1", "irrelevant"), ("s2", "irrelevant"), ("s3", "irrelevant"))
        self.assertEqual(self.names(), [])

    def test_a_paper_turned_down_and_then_understood_is_still_not_a_direction(self):
        # understanding something you said you were not interested in is not interest in it
        for key in ("s1", "s2", "s3"):
            self.say((key, "irrelevant"), (key, "understood"))
        self.assertEqual(self.names(), [])

    def test_too_hard_is_difficulty_not_direction(self):
        self.say(("s1", "too_hard"), ("s2", "too_hard"), ("s3", "too_hard"))
        self.assertEqual(self.names(), [])

    def test_one_response_is_not_enough(self):
        self.say(("s1", "useful"))
        self.assertEqual(self.names(), [])

    def test_undone_feedback_is_no_evidence_and_a_freeze_stops_new_evidence(self):
        self.say(("s1", "useful"), ("s2", "useful"))
        self.app.undo_feedback(self.app.latest_feedback(self.pid)["s2"]["id"])
        self.assertEqual(self.names(), [])
        self.say(("s2", "useful"))
        self.assertIn("strain relaxation", self.names())
        self.app.set_profile_frozen(True, self.pid)
        self.say(("s3", "useful"))
        self.assertEqual(self.pick()["positive"], 2)

    def test_another_projects_papers_and_responses_are_not_used(self):
        for key in ("s1", "s2"):
            self.app.store.add_project_paper(self.other, key, "discovered")
            self.app.record_feedback(key, "useful", project_id=self.other)
        self.assertEqual(self.names(), [])


class ProposalTests(Fixture):
    def setUp(self):
        super().setUp()
        self.say(("s1", "useful"), ("s2", "understood"))

    def test_a_proposal_shows_its_evidence(self):
        cand = self.pick()
        self.assertEqual((cand["name"], cand["status"]), ("strain relaxation", "ready"))
        self.assertEqual((cand["positive"], cand["sources"]), (2, 2))
        self.assertEqual({p["key"] for p in cand["papers"]}, {"s1", "s2", "s3", "s4"})
        self.assertTrue(all(p["title"] for p in cand["papers"]))
        self.assertGreaterEqual(cand["overlap"], 0)
        self.assertLessEqual(cand["overlap"], 1)
        self.assertIn("parent", cand)
        self.assertIn("prereqs", cand)

    def test_asking_changes_nothing_on_the_map(self):
        before = self.app.route_get(self.pid)
        self.app.route_candidates(self.pid)
        after = self.app.route_get(self.pid)
        self.assertEqual((after["graph"], after["revision"]), (before["graph"], before["revision"]))

    def test_new_feedback_never_adds_a_concept_by_itself(self):
        before = self.app.route_get(self.pid)["graph"]
        self.say(("s3", "useful"), ("s4", "useful"))
        self.app.route_candidates(self.pid)
        self.assertEqual(self.app.route_get(self.pid)["graph"], before)

    def test_accepting_adds_an_active_concept_that_joins_progress_and_can_be_undone(self):
        cand = self.pick()
        out = self.app.route_candidate_accept(self.pid, cand["id"])
        added = [c for c in out["graph"]["concepts"] if c.get("candidate") == cand["id"]]
        self.assertEqual([(c["name"], c["state"], c["origin"]) for c in added], [("strain relaxation", "active", "grown")])
        self.assertIn(added[0]["id"], out["progress"])
        self.assertNotEqual(out["progress"][added[0]["id"]]["status"], "proposed")
        self.assertNotIn("strain relaxation", self.names())   # it is on the map now
        org = Organization(self.app.store, project=self.pid)
        event = org.snapshot()["undo"]
        self.assertEqual(event["label"], "加入新方向")
        org.action({"action": "undo", "event": event["id"]})
        self.assertEqual([c for c in self.app.route_get(self.pid)["graph"]["concepts"] if c.get("candidate")], [])

    def test_rejecting_hides_it_for_good_and_can_be_undone(self):
        cand = self.pick()
        out = self.app.route_candidate_reject(self.pid, cand["id"])
        self.assertEqual(out["graph"], self.app.route_get(self.pid)["graph"])
        self.assertNotIn("strain relaxation", self.names())
        self.say(("s3", "useful"), ("s4", "useful"))   # more of the same does not bring it back
        self.assertNotIn("strain relaxation", self.names())
        org = Organization(self.app.store, project=self.pid)
        org.action({"action": "undo", "event": org.snapshot()["undo"]["id"]})
        self.assertIn("strain relaxation", self.names())

    def test_a_rejection_holds_when_more_papers_change_the_cluster(self):
        self.app.route_candidate_reject(self.pid, self.pick()["id"])
        for i in range(5, 8):
            self.app.store.upsert_papers([{"key": f"s{i}", "title": f"More strain relaxation by misfit dislocation glide {i}", "abstract": "strain relaxation by misfit dislocation glide in thin films", "source": f"journal-{i}", "published": "2026-03-01"}], project_id=self.pid)
        self.say(("s5", "useful"), ("s6", "useful"))
        self.assertNotIn("strain relaxation", self.names())   # the cluster has a different set of papers now, the direction is the same

    def test_a_direction_already_on_the_map_is_not_proposed_again_when_the_cluster_grows(self):
        self.app.route_candidate_accept(self.pid, self.pick()["id"])
        for i in range(5, 8):
            self.app.store.upsert_papers([{"key": f"s{i}", "title": f"More strain relaxation by misfit dislocation glide {i}", "abstract": "strain relaxation by misfit dislocation glide in thin films", "source": f"journal-{i}", "published": "2026-03-01"}], project_id=self.pid)
        self.say(("s5", "useful"), ("s6", "useful"))
        self.assertNotIn("strain relaxation", self.names())

    def test_a_legacy_concept_that_looks_like_a_paper_does_not_lock_the_map(self):
        graph = self.app.route_get(self.pid)["graph"]
        graph["concepts"][0]["name"] = "Scaling laws (Kaplan et al.)"   # saved before concept names were checked
        revision, data = self.app._route_org(self.pid)._load()
        data["route"]["graph"] = graph
        self.app.store.conn.execute("UPDATE org_projects SET data=? WHERE project=?", (json.dumps(data), self.pid))
        self.app.store.conn.commit()
        out = self.app.route_candidate_accept(self.pid, self.pick()["id"])   # must still work
        self.assertTrue(any(c.get("candidate") for c in out["graph"]["concepts"]))
        fresh = self.app.route_get(self.pid)["graph"]
        fresh["concepts"].append({"id": "c99", "name": "Smith et al. 2020", "terms": ["smith"], "hint": 2, "origin": "user", "state": "active", "side": False})
        with self.assertRaisesRegex(ValueError, "Smith et al. 2020"):   # a new one is refused, and the message names it
            self.app.route_save(self.pid, graph=fresh)

    def test_a_rejection_survives_saving_the_map_again(self):
        cand = self.pick()
        self.app.route_candidate_reject(self.pid, cand["id"])
        self.app.route_save(self.pid, graph=self.app.route_get(self.pid)["graph"])
        self.assertNotIn("strain relaxation", self.names())

    def test_a_stale_or_unknown_proposal_is_refused_and_nothing_changes(self):
        before = self.app.route_get(self.pid)
        for call in (self.app.route_candidate_accept, self.app.route_candidate_reject):
            with self.assertRaises(ValueError):
                call(self.pid, "g-nothing")
        self.assertEqual(self.app.route_get(self.pid)["graph"], before["graph"])

    def test_a_stale_revision_is_a_conflict(self):
        cand = self.pick()
        revision = self.app.route_get(self.pid)["revision"]
        self.app.route_mode(self.pid, "off")   # another window saved first
        with self.assertRaises(Conflict):
            self.app.route_candidate_accept(self.pid, cand["id"], revision=revision)
        with self.assertRaises(Conflict):
            self.app.route_candidate_reject(self.pid, cand["id"], revision=revision)

    def test_the_page_can_take_the_step_back(self):
        cand = self.pick()
        accepted = self.app.route_candidate_accept(self.pid, cand["id"])
        self.assertEqual(accepted["undo"]["label"], "加入新方向")
        back = self.app.route_undo(self.pid, revision=accepted["revision"])
        self.assertEqual([c for c in back["graph"]["concepts"] if c.get("candidate")], [])
        self.assertIn("strain relaxation", self.names())
        rejected = self.app.route_candidate_reject(self.pid, self.pick()["id"])
        self.assertEqual(rejected["undo"]["label"], "不再提示这个新方向")
        self.app.route_undo(self.pid)
        self.assertIn("strain relaxation", self.names())

    def test_undo_refuses_when_something_else_happened_since(self):
        accepted = self.app.route_candidate_accept(self.pid, self.pick()["id"])
        mark = next(c["id"] for c in accepted["graph"]["concepts"] if c["name"] == "Crystal basics")
        self.app.route_manual(self.pid, mark, "mastered")
        with self.assertRaisesRegex(ValueError, "之后"):
            self.app.route_undo(self.pid, event=accepted["undo"]["id"])
        state = self.app.route_get(self.pid)
        self.assertEqual(state["manual"], {mark: "mastered"})
        self.assertTrue(any(c.get("candidate") for c in state["graph"]["concepts"]))

    def test_nothing_to_take_back_is_an_error(self):
        with self.assertRaises(ValueError):
            self.app.route_undo(self.other)

    def test_a_project_without_a_map_has_no_proposals_to_make(self):
        out = self.app.route_candidates(self.other)
        self.assertEqual((out["candidates"], out["available"]), ([], False))


EARLY = [("t1", "Tactile sensing with gel sensors", "tactile sensing with gel sensors for in-hand slip detection", "arXiv cs.RO"),
         ("t2", "Gel sensors for tactile sensing", "tactile sensing with gel sensors for in-hand slip detection", "arXiv cs.RO")]


class PotentialDirectionTests(Fixture):
    """A direction that is still forming is shown with what it has and what it lacks, not hidden until it is ready."""

    def add_early(self):
        for key, title, abstract, source in EARLY:
            self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "source": source, "published": "2026-03-01"}], project_id=self.pid)
        self.say(("t1", "useful"), ("t2", "useful"))

    def find(self, name):
        # two phrases that cover the same papers are one direction named by either; match on any of its phrases
        return next((c for c in self.app.route_candidates(self.pid)["candidates"] if name == c["name"] or name in c["terms"]), None)

    def test_a_direction_with_two_explicit_papers_shows_up_early_as_forming(self):
        self.add_early()
        c = self.find("tactile sensing")
        self.assertEqual(c["status"], "watch")
        self.assertEqual(c["gates"]["papers"], {"have": 2, "need": 3, "ok": False})
        self.assertEqual(c["gates"]["positive"], {"have": 2, "need": 2, "ok": True})
        self.assertEqual(c["gates"]["sources"]["have"], 1)
        self.assertFalse(all(g["ok"] for g in c["gates"].values()))     # a forming direction really lacks something
        self.assertTrue(c["missing"])

    def test_ready_means_every_shown_gate_is_met_so_the_page_never_says_enough_beside_a_disabled_button(self):
        self.add_early()
        self.say(("s1", "useful"), ("s2", "understood"))
        found = self.app.route_candidates(self.pid)["candidates"]
        self.assertTrue(found)
        for c in found:
            self.assertEqual(c["status"] == "ready", all(g["ok"] for g in c["gates"].values()), c["name"])
            self.assertEqual(c["status"] == "ready", not c["missing"], c["name"])

    def test_it_says_what_is_missing_in_plain_words(self):
        self.add_early()
        missing = " ".join(self.find("tactile sensing")["missing"])
        self.assertIn("还差 1 篇含这个短语的论文", missing)
        self.assertIn("还差 1 个不同来源", missing)
        self.assertNotIn("明确点过", missing)   # that gate is met

    def test_progress_grows_with_evidence_and_is_full_only_when_it_can_be_added(self):
        self.add_early()
        early = self.find("tactile sensing")["progress"]
        self.assertTrue(0 < early < 1)
        self.say(("s1", "useful"), ("s2", "understood"))
        ready = self.find("strain relaxation")
        self.assertEqual((ready["status"], ready["progress"], ready["missing"]), ("ready", 1.0, []))
        self.assertTrue(all(g["ok"] for g in ready["gates"].values()))

    def test_a_not_ready_direction_never_shows_a_full_bar(self):
        self.add_early()
        self.assertLess(self.find("tactile sensing")["progress"], 1.0)

    def test_the_papers_say_which_ones_you_marked(self):
        self.add_early()
        self.app.store.upsert_papers([{"key": "t3", "title": "Unrated tactile sensing paper", "abstract": "tactile sensing with gel sensors for in-hand slip detection", "source": "Science Robotics", "published": "2026-03-01"}], project_id=self.pid)
        c = self.find("tactile sensing")
        by = {p["key"]: p for p in c["papers"]}
        self.assertEqual((by["t1"]["explicit"], by["t3"]["explicit"]), (True, False))
        self.assertTrue(all(p["title"] and "source" in p for p in c["papers"]))

    def test_the_topology_says_where_it_would_sit(self):
        self.add_early()
        c = self.find("tactile sensing")
        self.assertIn("新的入口", c["topology"]["note"])
        self.assertEqual(c["topology"]["needs"], [])
        self.say(("s1", "useful"), ("s2", "useful"))
        self.assertIn("topology", self.find("strain relaxation"))

    def test_a_forming_direction_cannot_be_added_yet(self):
        self.add_early()
        c = self.find("tactile sensing")
        before = self.app.route_get(self.pid)["graph"]
        with self.assertRaisesRegex(ValueError, "证据还不够"):
            self.app.route_candidate_accept(self.pid, c["id"])
        self.assertEqual(self.app.route_get(self.pid)["graph"], before)

    def test_a_forming_direction_can_be_turned_down_like_any_other(self):
        self.add_early()
        self.app.route_candidate_reject(self.pid, self.find("tactile sensing")["id"])
        self.assertIsNone(self.find("tactile sensing"))

    def test_one_explicit_paper_is_still_not_a_direction(self):
        self.app.store.upsert_papers([{"key": "t1", "title": "Tactile sensing with gel sensors", "abstract": "tactile sensing with gel sensors", "source": "x", "published": "2026-03-01"}], project_id=self.pid)
        self.say(("t1", "useful"))
        self.assertIsNone(self.find("tactile sensing"))

    def test_the_parts_are_explained_not_just_numbered(self):
        self.add_early()
        parts = {p["key"]: p for p in self.find("tactile sensing")["parts"]}
        self.assertEqual(set(parts), {"S", "C", "R", "N"})
        self.assertTrue(all(p["label"] and p["hint"] and 0 <= p["value"] <= 1 for p in parts.values()))

    def test_the_explanations_follow_the_interface_language(self):
        self.add_early()
        (self.app.data / "settings.json").write_text(json.dumps({"language": "en-US"}))
        c = self.find("tactile sensing")
        self.assertTrue(all(not any("\u4e00" <= ch <= "\u9fff" for ch in text) for text in c["missing"] + [c["topology"]["note"]]))
        self.assertIn("more paper", " ".join(c["missing"]))
        self.assertTrue(all(p["label"].isascii() and p["hint"].isascii() for p in c["parts"]))

    def test_at_most_five_are_shown(self):
        self.add_early()
        self.assertLessEqual(len(self.app.route_candidates(self.pid)["candidates"]), 5)


class HttpTests(Fixture):
    def post(self, port, body):
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/route", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_ask_accept_and_reject_over_http(self):
        self.say(("s1", "useful"), ("s2", "useful"))
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.post(port, {"action": "candidates", "project_id": self.pid})
            self.assertEqual(status, 200)
            cid = next(c["id"] for c in body["candidates"] if c["name"] == "strain relaxation")
            self.assertEqual(self.post(port, {"action": "candidate-accept", "project_id": self.pid, "candidate": "g-none"})[0], 400)
            status, saved = self.post(port, {"action": "candidate-accept", "project_id": self.pid, "candidate": cid, "revision": body["revision"]})
            self.assertEqual(status, 200)
            self.assertTrue(any(c.get("candidate") == cid for c in saved["graph"]["concepts"]))
            self.assertEqual(self.post(port, {"action": "candidate-accept", "project_id": self.pid, "candidate": cid, "revision": body["revision"]})[0], 409)


if __name__ == "__main__":
    unittest.main()
