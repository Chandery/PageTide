"""Growing the learning map: the exploration papers a reader collects are judged by the model (one click) into
potential directions; the app only counts the evidence under each, and only a person's click adds one to the map.
Nothing here is automatic, nothing is inferred from silence, and the model's answer is an opinion that is checked."""
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
from app import routeplan, server
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
# a paper that reads like a concept already on the map
NEAR = ("n1", "Epitaxial growth of thin films by epitaxy", "epitaxy epitaxial growth of thin films on a substrate lattice", "journal-c")


def reply(results, tokens=300):
    return {"ok": True, "content": json.dumps({"results": results}, ensure_ascii=False), "usage": {"total_tokens": tokens, "prompt_tokens": 200, "completion_tokens": tokens - 200}}


def new(labels, name="应变弛豫", terms=("strain relaxation", "dislocation glide"), **extra):
    return {"papers": list(labels), "verdict": "new", "name": name, "terms": list(terms), "intro": "薄膜里的应力通过位错滑移释放。",
            "barrier": "要先懂外延和位错，难在应变与缺陷的耦合。", "needs": ["Epitaxy"], **extra}


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
            self.add(key, title, abstract, source)

    def add(self, key, title, abstract, source, pid=None):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "source": source, "published": "2026-02-01"}], project_id=pid or self.pid)

    def shown(self, *keys, kind="explore", pid=None):
        """The papers were shown to the reader in an exploration slot (or another kind)."""
        self.app.store.create_batch("2026-10-01", list(keys), project_id=pid or self.pid, route={k: (None, kind, None, None) for k in keys})

    def say(self, *pairs):
        for key, action in pairs:
            if action == "understood":
                self.app.store.save_to_library(key, project_id=self.pid)   # "understood" needs a saved paper
            self.app.record_feedback(key, action, project_id=self.pid)

    def gateway(self, result):
        calls = []

        def fake(operation, messages, dry_run=False):
            calls.append((operation, messages, dry_run))
            return result() if callable(result) else result
        patcher = mock.patch.object(self.app.gateway, "call", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def labels(self):
        """{paper key: 'p1'..} in the order the page would send them."""
        return {p["key"]: f"p{i + 1}" for i, p in enumerate(self.app._pending_explored(self.pid)[:routeplan.JUDGE_PAPERS])}

    def judge_new(self, *keys, **kw):
        """Collect the papers from exploration, then let the (fake) model call them one new direction."""
        self.shown(*keys)
        self.say(*[(k, "useful") for k in keys])
        labels = self.labels()
        self.gateway(reply([new([labels[k] for k in keys], **kw)]))
        return self.app.route_direction_judge(self.pid)

    def ready_direction(self):
        self.judge_new("s1", "s2", "s3")
        return self.app.route_candidates(self.pid)["candidates"][0]

    def names(self):
        return [c["name"] for c in self.app.route_candidates(self.pid)["candidates"]]


class PendingTests(Fixture):
    def pending(self):
        return [p["key"] for p in self.app._pending_explored(self.pid)]

    def test_a_collected_exploration_paper_is_waiting_to_be_judged(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.assertEqual(self.pending(), ["s1"])
        self.assertEqual([p["key"] for p in self.app.route_candidates(self.pid)["pending"]], ["s1"])

    def test_understood_does_not_count_as_interest(self):
        self.shown("s1")
        self.say(("s1", "understood"))
        self.assertEqual(self.pending(), [])

    def test_silence_is_not_a_reason_to_ask(self):
        self.shown("s1", "s2")                   # shown, never answered
        self.assertEqual(self.pending(), [])

    def test_not_interested_and_too_hard_are_not_a_reason_to_ask(self):
        self.shown("s1", "s2", "s3")
        self.say(("s1", "irrelevant"), ("s2", "too_hard"), ("s3", "irrelevant"), ("s3", "understood"))   # understanding what you turned down is not interest
        self.assertEqual(self.pending(), [])

    def test_useful_papers_are_pending_regardless_of_exposure_type(self):
        self.shown("s1", kind="route")
        self.shown("s2", kind=None)
        self.say(("s1", "useful"), ("s2", "useful"))
        self.assertEqual(self.pending(), ["s2", "s1"])

    def test_a_chosen_seed_can_supply_growth_evidence(self):
        self.app.store.add_project_paper(self.pid, "s1", "seed")
        self.app.store.set_setting(f"seed_keys_{self.pid}", ["s1"])
        self.assertEqual(self.pending(), ["s1"])

    def test_undone_feedback_is_no_reason(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.app.undo_feedback(self.app.latest_feedback(self.pid)["s1"]["id"])
        self.assertEqual(self.pending(), [])

    def test_another_projects_exploration_is_not_mine(self):
        self.add("o1", "Poems", "poetry", "journal-p", pid=self.other)
        self.shown("o1", pid=self.other)
        self.app.record_feedback("o1", "useful", project_id=self.other)
        self.assertEqual(self.pending(), [])

    def test_the_one_collected_last_comes_first_even_when_its_key_sorts_earlier(self):
        self.shown("s1", "s2", "s3", "s4")
        self.say(("s3", "useful"), ("s4", "useful"), ("s2", "useful"), ("s1", "useful"))       # same day: only the order of the clicks tells
        self.assertEqual(self.pending(), ["s1", "s2", "s4", "s3"])

    def test_a_project_without_a_map_has_no_proposals_to_make(self):
        out = self.app.route_candidates(self.other)
        self.assertEqual((out["candidates"], out["available"], out["pending"]), ([], False, []))


class JudgeTests(Fixture):
    def test_a_new_direction_is_stored_with_the_models_name_and_the_map_is_untouched(self):
        before = self.app.route_get(self.pid)
        out = self.judge_new("s1", "s2")
        self.assertEqual((out["ok"], [r["verdict"] for r in out["results"]], out["results"][0]["name"]), (True, ["new"], "应变弛豫"))
        found = self.app.route_candidates(self.pid)["candidates"]
        self.assertEqual([c["name"] for c in found], ["应变弛豫"])
        self.assertEqual(found[0]["terms"], ["strain relaxation", "dislocation glide"])
        self.assertIn("位错滑移", found[0]["intro"])
        self.assertIn("难在", found[0]["barrier"])
        after = self.app.route_get(self.pid)
        self.assertEqual((after["graph"], after["revision"]), (before["graph"], before["revision"]))
        self.assertEqual(self.app._pending_explored(self.pid), [])      # judged papers are not asked about again

    def test_the_model_sees_only_the_agreed_fields(self):
        self.add_secret()
        self.shown("s1", "s2")
        self.say(("s1", "useful"), ("s2", "useful"))
        calls = self.gateway(reply([]))
        self.app.route_direction_judge(self.pid)
        sent = calls[0][1][1]["content"]       # the one user message
        for forbidden in ("Poetry", "poetry", "PRIVATE NOTE", "Secret other", "journal-a", "journal-b", '"s1"', '"s2"', "useful", "Crystals", "seed"):
            self.assertNotIn(forbidden, sent, forbidden)
        body = json.loads(sent)
        self.assertEqual(set(body), {"papers", "map", "directions"})
        self.assertEqual(set(body["papers"]), {"p1", "p2"})
        self.assertTrue(all(set(p) == {"title", "abstract"} for p in body["papers"].values()))
        self.assertEqual(set(c["name"] for c in body["map"]["concepts"].values()), {"Epitaxy", "Crystal basics", "MBE"})
        self.assertEqual(calls[0][0], "route_growth_judge")

    def add_secret(self):
        self.app.create_project("Secret other project", "manual", ["classified"])
        self.app.store.set_setting("note_PRIVATE NOTE", "PRIVATE NOTE")

    def test_at_most_three_papers_are_sent_and_they_are_cut(self):
        for i in range(5):
            self.add(f"x{i}", "T" * 300, "A" * 900, "journal-x")
        self.shown(*[f"x{i}" for i in range(5)])
        self.say(*[(f"x{i}", "useful") for i in range(5)])
        calls = self.gateway(reply([]))
        self.app.route_direction_judge(self.pid)
        body = json.loads(calls[0][1][1]["content"])
        self.assertEqual(list(body["papers"]), ["p1", "p2", "p3"])
        self.assertTrue(all(len(p["title"]) <= routeplan.PAPER_TITLE_CHARS and len(p["abstract"]) <= routeplan.JUDGE_ABSTRACT_CHARS for p in body["papers"].values()))
        self.assertEqual(len(self.app._pending_explored(self.pid)), 5)    # nothing was judged yet

    def test_a_paper_that_belongs_to_a_direction_on_file_joins_it(self):
        self.judge_new("s1", "s2")
        d = self.app.route_candidates(self.pid)["candidates"][0]
        self.shown("s3")
        self.say(("s3", "useful"))
        calls = self.gateway(reply([{"papers": ["p1"], "verdict": "join", "direction": "d1"}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual([r["verdict"] for r in out["results"]], ["join"])
        self.assertIn("应变弛豫", json.dumps(calls[0][1], ensure_ascii=False))     # the model was told what is on file
        again = self.app.route_candidates(self.pid)["candidates"]
        self.assertEqual(([c["id"] for c in again], again[0]["paper_count"]), ([d["id"]], 3))

    def test_shared_search_terms_do_not_merge_distinct_tasks(self):
        self.judge_new("s1", "s2")
        self.shown("s3")
        self.say(("s3", "useful"))
        self.gateway(reply([new(["p1"], name="应变弛豫（另一个说法）", terms=["strain relaxation", "other task"])]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(out["results"][0]["verdict"], "new")
        self.assertEqual(len(self.app.route_candidates(self.pid)["candidates"]), 2)

    def test_a_neighbour_of_a_concept_is_covered_and_creates_nothing(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.gateway(reply([{"papers": ["p1"], "verdict": "covered", "nearest": "Epitaxy"}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out["results"][0]["verdict"], out["results"][0]["nearest"]), ("covered", "Epitaxy"))
        self.assertEqual(self.names(), [])
        self.assertEqual(self.app._pending_explored(self.pid), [])      # asked once, not again and again

    def test_existing_search_terms_allow_a_new_task_under_the_node(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.gateway(reply([new(["p1"], name="外延的新任务", terms=["epitaxy", "thin films"], verdict="new_task", parent="c2")]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(out["results"][0]["proposal_type"], "new_task")
        self.assertEqual(self.names(), ["外延的新任务"])

    def test_text_similarity_cannot_override_a_new_learning_task(self):
        self.add(*NEAR)
        for i in range(3):
            self.add(f"n{i + 2}", f"Epitaxial growth study {i}", "epitaxy epitaxial growth of thin films on a substrate lattice", "journal-c")
        self.shown("n1")
        self.say(("n1", "useful"))
        self.gateway(reply([new(["p1"], name="薄膜生长", terms=["thin film growth", "substrate"], verdict="new_task", parent="c2")]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(out["results"][0]["proposal_type"], "new_task")
        self.assertEqual(self.names(), ["薄膜生长"])

    def test_bad_prerequisite_references_are_rejected_not_dropped(self):
        out = self.judge_new("s1", "s2", needs=["Epitaxy", "c1", "Not a concept", "Epitaxy"])
        self.assertFalse(out['ok'])
        self.assertEqual(self.names(), [])
        self.assertEqual(len(self.app._pending_growth(self.pid)), 2)

    def test_a_reply_item_that_is_not_usable_creates_nothing_and_leaves_the_papers_waiting(self):
        self.shown("s1", "s2", "s3")
        self.say(("s1", "useful"), ("s2", "useful"), ("s3", "useful"))
        self.gateway(reply([{"papers": ["p1"], "verdict": "great"}, {"papers": ["p2"], "verdict": "new", "name": "", "terms": []},
                            {"papers": ["p3"], "verdict": "join", "direction": "d7"}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual([r["verdict"] for r in out["results"]], ["unusable", "unusable", "unusable"])
        self.assertEqual(self.names(), [])
        self.assertEqual(len(self.app._pending_explored(self.pid)), 3)     # a broken reply is not the model's opinion: ask again later

    def test_the_model_saying_it_cannot_tell_is_recorded_so_it_is_not_asked_again(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.gateway(reply([{"papers": ["p1"], "verdict": "unclear"}]))
        self.assertEqual(self.app.route_direction_judge(self.pid)["results"][0]["verdict"], "unclear")
        self.assertEqual(self.app._pending_explored(self.pid), [])

    def test_fields_of_the_wrong_type_never_become_a_direction_or_garbage_terms(self):
        self.shown("s1", "s2")
        self.say(("s1", "useful"), ("s2", "useful"))
        self.gateway(reply([new(["p1"], terms="strain relaxation"), new(["p2"], terms=["a", "b"])]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual([r["verdict"] for r in out["results"]], ["unusable", "unusable"])      # a string for terms; terms too short to search with
        self.assertEqual(self.names(), [])

    def test_intro_and_barrier_of_the_wrong_type_reject_the_proposal(self):
        out = self.judge_new("s1", "s2", intro=["a"], barrier=5)
        self.assertFalse(out['ok'])
        self.assertEqual(self.names(), [])

    def test_when_twelve_directions_are_on_file_a_new_one_waits_instead_of_piling_up(self):
        self.app.store.set_setting(f"route_directions_{self.pid}", {"judged": {}, "directions": [
            {"id": f"d-{i}", "name": f"方向{i}", "terms": [f"alpha{i} beta{i}", f"gamma{i}"], "intro": "", "barrier": "", "needs": [], "papers": [], "created": "2026-10-01", "context": self.app._growth_context(self.pid, [])}
            for i in range(App.MAX_VISIBLE_DIRECTIONS)]})
        self.shown("s1")
        self.say(("s1", "useful"))
        self.gateway(reply([new(["p1"], name="第十三个", terms=("strain relaxation", "dislocation glide"))]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(out["results"][0]["verdict"], "full")
        self.assertEqual([p["key"] for p in self.app._pending_explored(self.pid)], ["s1"])

    def test_a_direction_the_reader_turned_down_is_not_told_to_the_model_not_joined_and_not_proposed_again(self):
        cand = self.ready_direction()
        self.app.route_candidate_reject(self.pid, cand["id"])
        self.shown("s4")
        self.say(("s4", "useful"))
        calls = self.gateway(reply([{"papers": ["p1"], "verdict": "join", "direction": "d1"}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(json.loads(calls[0][1][1]["content"])["directions"], {})            # nothing about the rejected direction is sent
        self.assertEqual(out["results"][0]["verdict"], "unusable")                              # d1 does not exist for the model
        self.gateway(reply([new(["p1"])]))
        again = self.app.route_direction_judge(self.pid)
        self.assertEqual(again["results"][0]["verdict"], "declined")                            # the same words come back: the answer is no
        self.assertEqual(self.names(), [])
        self.assertEqual(self.app._pending_explored(self.pid), [])

    def test_the_model_sees_every_node_including_the_relevant_late_node(self):
        graph = self.app.route_get(self.pid)["graph"]
        for i in range(14):
            graph["concepts"].append({"id": f"z{i}", "name": f"Filler {i}", "terms": [f"zzfiller{i}"], "hint": 1, "origin": "user", "state": "active", "side": False})
        graph["concepts"].append({"id": "near", "name": "Dislocation glide", "terms": ["dislocation glide", "misfit"], "hint": 2, "origin": "user", "state": "active", "side": False})
        self.app.route_save(self.pid, graph=graph)
        self.shown("s1")
        self.say(("s1", "useful"))
        calls = self.gateway(reply([]))
        self.app.route_direction_judge(self.pid)
        names = {c["name"] for c in json.loads(calls[0][1][1]["content"])["map"]["concepts"].values()}
        self.assertEqual(len(names), 18)
        self.assertIn("Dislocation glide", names)

    def test_labels_the_model_made_up_are_ignored_and_those_papers_stay_pending(self):
        self.shown("s1", "s2")
        self.say(("s1", "useful"), ("s2", "useful"))
        labels = self.labels()
        self.gateway(reply([new(["p9", "nope"]), new([labels["s1"]])]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual([r['verdict'] for r in out['results']], ['unusable', 'new'])
        self.assertEqual([p["key"] for p in self.app._pending_explored(self.pid)], ["s2"])

    def test_an_unreadable_reply_degrades_and_counts_as_an_attempt(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.gateway({"ok": True, "content": "I cannot do that", "usage": {"total_tokens": 50}})
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out["ok"], out["reason_code"], out["judges_left"]), (False, "bad_reply", App.DIRECTION_JUDGES_PER_DAY - 1))
        self.assertEqual([p["key"] for p in self.app._pending_explored(self.pid)], ["s1"])

    def test_a_gateway_refusal_costs_no_attempt(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        self.gateway({"ok": False, "reason": "no API key"})
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out["ok"], out["reason_code"], out["judges_left"]), (False, "no_key", App.DIRECTION_JUDGES_PER_DAY))

    def test_a_dry_run_sends_nothing_and_counts_nothing(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        out = self.app.route_direction_judge(self.pid, dry_run=True)
        self.assertEqual((out["ok"], out["reason_code"], out["judges_left"]), (False, "not_approved", App.DIRECTION_JUDGES_PER_DAY))

    def test_ten_a_day_per_project_and_then_it_says_so(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        calls = self.gateway(reply([]))
        for _ in range(App.DIRECTION_JUDGES_PER_DAY):
            self.app.route_direction_judge(self.pid)
        with self.assertRaisesRegex(ValueError, "今天已经"):
            self.app.route_direction_judge(self.pid)
        self.assertEqual(len(calls), App.DIRECTION_JUDGES_PER_DAY)

    def test_one_call_at_a_time_per_project(self):
        self.shown("s1")
        self.say(("s1", "useful"))
        started, release = threading.Event(), threading.Event()

        def slow():
            started.set(); release.wait(3)
            return reply([])
        self.gateway(slow)
        worker = threading.Thread(target=lambda: self.app.route_direction_judge(self.pid))
        worker.start()
        self.assertTrue(started.wait(3))
        with self.assertRaisesRegex(ValueError, "稍候"):
            self.app.route_direction_judge(self.pid)
        release.set(); worker.join(5)

    def test_nothing_to_judge_and_no_map_are_refused_before_any_call(self):
        calls = self.gateway(reply([]))
        with self.assertRaisesRegex(ValueError, "没有待判断"):
            self.app.route_direction_judge(self.pid)
        with self.assertRaisesRegex(ValueError, "还没有学习图"):
            self.app.route_direction_judge(self.other)
        with self.assertRaises(ValueError):
            self.app.route_direction_judge("no-such")
        self.assertEqual(calls, [])


class EvidenceTests(Fixture):
    def test_nothing_is_proposed_from_silence_or_feedback_on_papers_nobody_judged(self):
        self.say(("s1", "useful"), ("s2", "understood"))
        self.assertEqual(self.names(), [])

    def test_a_fresh_direction_has_one_paper_and_says_what_it_lacks(self):
        self.judge_new("s1")
        c = self.app.route_candidates(self.pid)["candidates"][0]
        self.assertEqual((c["status"], c["paper_count"], c["positive"]), ("watch", 1, 1))
        self.assertEqual(c["gates"]["papers"], {"have": 1, "need": 3, "ok": False})
        self.assertIn("还差 2 篇属于这个方向的论文", " ".join(c["missing"]))
        self.assertTrue(0 < c["progress"] < 1)

    def test_three_marked_papers_from_two_sources_make_it_ready(self):
        c = self.ready_direction()
        self.assertEqual((c["status"], c["progress"], c["missing"]), ("ready", 1.0, []))
        self.assertTrue(all(g["ok"] for g in c["gates"].values()))
        self.assertEqual({p["key"] for p in c["papers"]}, {"s1", "s2", "s3"})
        self.assertTrue(all(p["explicit"] and p["title"] for p in c["papers"]))

    def test_a_paper_turned_down_afterwards_no_longer_counts(self):
        self.ready_direction()
        self.say(("s3", "irrelevant"))
        c = self.app.route_candidates(self.pid)["candidates"][0]
        self.assertEqual((c["status"], c["paper_count"]), ("watch", 2))

    def test_undone_feedback_is_no_evidence(self):
        self.ready_direction()
        self.app.undo_feedback(self.app.latest_feedback(self.pid)["s2"]["id"])
        c = self.app.route_candidates(self.pid)["candidates"][0]
        self.assertEqual((c["paper_count"], c["positive"], c["status"]), (2, 2, "watch"))

    def test_a_freeze_stops_new_evidence(self):
        self.judge_new("s1", "s2")
        self.app.set_profile_frozen(True, self.pid)
        self.shown("s3")
        self.say(("s3", "useful"))
        self.assertEqual(self.app._pending_explored(self.pid), [])

    def test_the_parts_are_explained_and_follow_the_interface_language(self):
        self.ready_direction()
        parts = {p["key"]: p for p in self.app.route_candidates(self.pid)["candidates"][0]["parts"]}
        self.assertEqual(set(parts), {"S", "C", "R"})       # "clearly different from the map" is the model's judgement, not a measured part
        (self.app.data / "settings.json").write_text(json.dumps({"language": "en-US"}))
        self.say(("s3", "irrelevant"))
        c = self.app.route_candidates(self.pid)["candidates"][0]
        texts = c["missing"] + [c["topology"]["note"].replace(c["name"], "")]     # the direction's own name is whatever language the model wrote it in
        self.assertTrue(all(not any("一" <= ch <= "鿿" for ch in text) for text in texts), texts)
        self.assertTrue(all(p["label"].isascii() and p["hint"].isascii() for p in c["parts"]))

    def test_the_topology_says_where_it_would_sit(self):
        c = self.ready_direction()
        cid = {x["name"]: x["id"] for x in self.app.route_get(self.pid)["graph"]["concepts"]}
        self.assertEqual([n["id"] for n in c["topology"]["needs"]], [cid["Epitaxy"]])
        self.assertIn("Epitaxy", c["topology"]["note"])
        self.assertIsNone(c["topology"]["parent"])

    def test_at_most_five_are_shown(self):
        for i in range(7):
            self.add(f"q{i}a", f"Topic {i} alpha{i} beta{i}", f"alpha{i} beta{i}", "journal-a")
            self.judge_new(f"q{i}a", name=f"方向{i}", terms=(f"alpha{i} beta{i}", f"t{i}"), needs=[])
        self.assertLessEqual(len(self.app.route_candidates(self.pid)["candidates"]), 5)


class AcceptTests(Fixture):
    def test_accepting_adds_an_active_concept_with_the_models_name_intro_and_prerequisite_and_can_be_undone(self):
        cand = self.ready_direction()
        out = self.app.route_candidate_accept(self.pid, cand["id"])
        added = [c for c in out["graph"]["concepts"] if c.get("candidate") == cand["id"]]
        self.assertEqual([(c["name"], c["state"], c["origin"], c["intro_by"]) for c in added], [("应变弛豫", "active", "grown", "ai")])
        self.assertEqual(added[0]["terms"], ["strain relaxation", "dislocation glide"])
        self.assertIn("门槛：", added[0]["intro"])
        epitaxy = next(c["id"] for c in out["graph"]["concepts"] if c["name"] == "Epitaxy")
        self.assertIn((epitaxy, added[0]["id"]), [(e["from"], e["to"]) for e in out["graph"]["prereqs"]])
        self.assertIn(added[0]["id"], out["progress"])
        self.assertNotIn("应变弛豫", self.names())      # it is on the map now
        org = Organization(self.app.store, project=self.pid)
        event = org.snapshot()["undo"]
        self.assertEqual(event["label"], "加入新方向")
        org.action({"action": "undo", "event": event["id"]})
        self.assertEqual([c for c in self.app.route_get(self.pid)["graph"]["concepts"] if c.get("candidate")], [])
        self.assertIn("应变弛豫", self.names())          # undone: the direction is back on file

    def test_evidence_strength_does_not_block_explicit_confirmation(self):
        self.judge_new("s1")
        cand = self.app.route_candidates(self.pid)["candidates"][0]
        self.assertEqual(cand['status'], 'watch')
        self.assertTrue(cand['can_accept'])
        out = self.app.route_candidate_accept(self.pid, cand['id'])
        self.assertTrue(any(c.get('candidate') == cand['id'] for c in out['graph']['concepts']))

    def test_new_feedback_and_reading_never_add_a_concept_by_itself(self):
        self.ready_direction()
        before = self.app.route_get(self.pid)["graph"]
        self.say(("s4", "useful"))
        self.app.route_candidates(self.pid)
        self.assertEqual(self.app.route_get(self.pid)["graph"], before)

    def test_rejecting_hides_it_for_good_and_can_be_undone(self):
        cand = self.ready_direction()
        out = self.app.route_candidate_reject(self.pid, cand["id"])
        self.assertEqual(out["graph"], self.app.route_get(self.pid)["graph"])
        self.assertEqual(self.names(), [])
        self.shown("s4")
        self.say(("s4", "useful"))
        self.gateway(reply([{"papers": ["p1"], "verdict": "join", "direction": "d1"}]))
        self.app.route_direction_judge(self.pid)
        self.assertEqual(self.names(), [])               # more of the same does not bring it back
        org = Organization(self.app.store, project=self.pid)
        org.action({"action": "undo", "event": org.snapshot()["undo"]["id"]})
        self.assertEqual(self.names(), ["应变弛豫"])

    def test_a_rejection_survives_saving_the_map_again(self):
        cand = self.ready_direction()
        self.app.route_candidate_reject(self.pid, cand["id"])
        self.app.route_save(self.pid, graph=self.app.route_get(self.pid)["graph"])
        self.assertEqual(self.names(), [])

    def test_a_stale_or_unknown_proposal_is_refused_and_nothing_changes(self):
        self.ready_direction()
        before = self.app.route_get(self.pid)
        for call in (self.app.route_candidate_accept, self.app.route_candidate_reject):
            with self.assertRaises(ValueError):
                call(self.pid, "d-nothing")
        self.assertEqual(self.app.route_get(self.pid)["graph"], before["graph"])

    def test_a_stale_revision_is_a_conflict(self):
        cand = self.ready_direction()
        revision = self.app.route_get(self.pid)["revision"]
        self.app.route_mode(self.pid, "off")   # another window saved first
        with self.assertRaises(Conflict):
            self.app.route_candidate_accept(self.pid, cand["id"], revision=revision)
        with self.assertRaises(Conflict):
            self.app.route_candidate_reject(self.pid, cand["id"], revision=revision)

    def test_the_page_can_take_the_step_back(self):
        cand = self.ready_direction()
        accepted = self.app.route_candidate_accept(self.pid, cand["id"])
        self.assertEqual(accepted["undo"]["label"], "加入新方向")
        back = self.app.route_undo(self.pid, revision=accepted["revision"])
        self.assertEqual([c for c in back["graph"]["concepts"] if c.get("candidate")], [])
        rejected = self.app.route_candidate_reject(self.pid, self.app.route_candidates(self.pid)["candidates"][0]["id"])
        self.assertEqual(rejected["undo"]["label"], "不再提示这个新方向")
        self.app.route_undo(self.pid)
        self.assertEqual(self.names(), ["应变弛豫"])

    def test_undo_refuses_when_something_else_happened_since(self):
        accepted = self.app.route_candidate_accept(self.pid, self.ready_direction()["id"])
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

    def test_a_legacy_concept_that_looks_like_a_paper_does_not_lock_the_map(self):
        graph = self.app.route_get(self.pid)["graph"]
        graph["concepts"][0]["name"] = "Scaling laws (Kaplan et al.)"   # saved before concept names were checked
        revision, data = self.app._route_org(self.pid)._load()
        data["route"]["graph"] = graph
        self.app.store.conn.execute("UPDATE org_projects SET data=? WHERE project=?", (json.dumps(data), self.pid))
        self.app.store.conn.commit()
        cand = self.ready_direction()  # judge against the actual legacy Map, not a stale preview
        out = self.app.route_candidate_accept(self.pid, cand["id"])   # must still work
        self.assertTrue(any(c.get("candidate") for c in out["graph"]["concepts"]))
        fresh = self.app.route_get(self.pid)["graph"]
        fresh["concepts"].append({"id": "c99", "name": "Smith et al. 2020", "terms": ["smith"], "hint": 2, "origin": "user", "state": "active", "side": False})
        with self.assertRaisesRegex(ValueError, "Smith et al. 2020"):   # a new one is refused, and the message names it
            self.app.route_save(self.pid, graph=fresh)


class HttpTests(Fixture):
    def post(self, port, body):
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/route", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_judge_ask_accept_and_conflict_over_http(self):
        self.shown("s1", "s2", "s3")
        self.say(("s1", "useful"), ("s2", "useful"), ("s3", "useful"))
        labels = self.labels()
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.post(port, {"action": "candidates", "project_id": self.pid})
            self.assertEqual((status, body["candidates"], len(body["pending"])), (200, [], 3))
            status, out = self.post(port, {"action": "direction-judge", "project_id": self.pid, "dry_run": True})
            self.assertEqual((status, out["ok"], out["reason_code"]), (200, False, "not_approved"))
            self.assertEqual(self.post(port, {"action": "direction-judge", "project_id": "no-such"})[0], 400)
            with mock.patch("app.service.Gateway.call", return_value=reply([new(list(labels.values()))])):
                status, out = self.post(port, {"action": "direction-judge", "project_id": self.pid})
            self.assertEqual((status, out["ok"]), (200, True))
            status, body = self.post(port, {"action": "candidates", "project_id": self.pid})
            cid = body["candidates"][0]["id"]
            self.assertEqual(self.post(port, {"action": "candidate-accept", "project_id": self.pid, "candidate": "d-none"})[0], 400)
            status, saved = self.post(port, {"action": "candidate-accept", "project_id": self.pid, "candidate": cid, "revision": body["revision"]})
            self.assertEqual(status, 200)
            self.assertTrue(any(c.get("candidate") == cid for c in saved["graph"]["concepts"]))
            self.assertEqual(self.post(port, {"action": "candidate-accept", "project_id": self.pid, "candidate": cid, "revision": body["revision"]})[0], 409)


if __name__ == "__main__":
    unittest.main()
