"""Route Mode slice 5a: generating the learning map from the research goal (operation learning_path_plan).

The model only proposes a concept graph; everything after that is local: normalize() repairs it, each concept is
checked against OpenAlex (public metadata), and a person confirms. These tests never call a real model: the
gateway is replaced by a recorder that returns canned replies.
"""
import json
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import budget
from app import pathgraph as pg
from app import routeplan, sources
from app.service import App

GOOD = {"concepts": [
    {"id": "a", "name": "Crystal structure", "terms": ["crystal structure", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial growth"], "hint": 2, "needs": ["a"]},
    {"id": "c", "name": "MBE", "terms": ["molecular beam epitaxy", "mbe"], "hint": 3, "needs": ["b"]}], "targets": ["c"]}


def reply(payload, tokens=612):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"ok": True, "content": text, "usage": {"total_tokens": tokens, "prompt_tokens": 400, "completion_tokens": tokens - 400}}


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
        self.session = self.app.create_guidance_session("半导体生长", "我想系统了解半导体晶体生长")["id"]
        mock.patch.object(sources.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def gateway(self, result):
        calls = []

        def fake(operation, messages, dry_run=False):
            calls.append((operation, messages, dry_run))
            return result() if callable(result) else result
        patcher = mock.patch.object(self.app.gateway, "call", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / "harness" / "budget.json").read_text())
        self.op = self.cfg["operations"]["learning_path_plan"]

    def test_the_operation_is_registered_bounded_and_the_owner_approved_the_raised_cap(self):
        self.assertIs(self.op["owner_approved"], True)
        self.assertIn("2026-10-06", self.op["approval_note"])   # the owner's approval of 1200 -> 1400, in their words
        self.assertIn("AI 起草的输入上限我批准了", self.op["approval_note"])
        self.assertEqual((self.op["cap"]["input"], self.op["cap"]["output"]), (1400, 900))
        self.assertEqual(self.op["prompt"], "prompts/learning-path-plan.md")
        self.assertFalse(self.op["enabled_by_default"])
        self.assertEqual(self.op["trigger"], "interactive")

    def test_the_cap_components_add_up_to_the_cap(self):
        self.assertEqual(sum(self.op["input_cap_components"].values()), self.op["cap"]["input"])

    def test_the_reference_is_inside_the_cap_and_priced_by_the_registry(self):
        self.assertLessEqual(self.op["reference"]["input"], self.op["cap"]["input"])
        self.assertLessEqual(self.op["reference"]["output"], self.op["cap"]["output"])
        self.assertLess(budget.cost(self.cfg, self.op["cap"]["input"], self.op["cap"]["output"]), 0.002)

    def test_the_approval_is_recorded_as_the_owners_not_the_agents(self):
        self.assertIn("owner", self.op["approval_note"])
        self.assertIn("2026-10-05", self.op["approval_note"])

    def test_the_prompt_file_has_the_operation_header_and_matches_the_code(self):
        text = (ROOT / "prompts" / "learning-path-plan.md").read_text(encoding="utf-8")
        self.assertIn("operation: learning_path_plan", text)
        self.assertIn(routeplan.SYSTEM, text)

    def test_the_prompt_stays_inside_its_instruction_budget_by_a_pessimistic_estimate(self):
        # Chinese is assumed to cost 1.5 tokens per character; this is a heuristic, not a tokenizer measurement
        english = routeplan.SYSTEM + routeplan.ENGLISH_OUTPUT
        self.assertLess(len(english) * 1.5, self.op["input_cap_components"]["instructions_and_schema"])


EMBODIED = {"concepts": [
    {"id": "la", "name": "Linear algebra", "terms": ["linear algebra", "matrix"], "hint": 1, "type": "foundation", "why": "matrices underlie every model", "needs": []},
    {"id": "rl", "name": "Robot Learning", "terms": ["robot learning", "imitation learning"], "hint": 1, "type": "topic", "needs": []},
    {"id": "cv", "name": "Computer Vision / Perception", "terms": ["robot perception", "visual perception"], "hint": 1, "type": "topic", "needs": []},
    {"id": "vlm", "name": "Vision-Language Models", "terms": ["vision-language model", "VLM"], "hint": 2, "type": "method", "needs": ["cv"]},
    {"id": "wm", "name": "World Models", "terms": ["world model", "latent dynamics"], "hint": 2, "type": "method", "needs": ["rl"]},
    {"id": "man", "name": "Robot Manipulation", "terms": ["robot manipulation", "grasping"], "hint": 3, "type": "problem", "needs": ["rl", "cv"]},
    {"id": "vla", "name": "VLA", "terms": ["vision-language-action", "VLA model"], "hint": 4, "type": "method", "needs": ["vlm", "wm", "man"]},
    {"id": "p1", "name": "RT-2 paper", "terms": ["2307.15818", "rt-2"], "hint": 4, "needs": ["vlm"]}],
    "targets": ["vla"], "papers": [{"title": "RT-2", "doi": "10.1000/rt2"}]}


class BoundaryTests(Fixture):
    def test_the_boundary_is_two_enum_values_and_nothing_else(self):
        self.assertIsNone(routeplan.clean_boundary(None))
        self.assertIsNone(routeplan.clean_boundary({}))
        self.assertEqual(routeplan.clean_boundary({"background": "unknown", "depth": "implement"}), {"background": "unknown", "depth": "implement"})
        self.assertEqual(routeplan.clean_boundary({"depth": "overview"}), {"depth": "overview"})
        for bad in ({"background": "wizard"}, {"depth": "everything"}, {"background": "unknown", "notes": "my private diary"}, "unknown", ["unknown"]):
            with self.assertRaises(ValueError, msg=bad):
                routeplan.clean_boundary(bad)

    def test_skipping_the_boundary_sends_none_and_the_default_is_described_to_the_model(self):
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        user = json.loads(calls[0][1][1]["content"])
        self.assertEqual(set(user), {"goal", "keywords"})
        self.assertIn("缺省论文阅读", calls[0][1][0]["content"])

    def test_a_chosen_boundary_is_sent_as_the_two_values_only(self):
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session, boundary={"background": "engineering", "depth": "read_papers"})
        self.assertEqual(json.loads(calls[0][1][1]["content"])["boundary"], {"background": "engineering", "depth": "read_papers"})

    def test_a_bad_boundary_is_refused_before_any_attempt_is_spent(self):
        calls = self.gateway(reply(GOOD))
        with self.assertRaises(ValueError):
            self.app.route_plan(self.session, boundary={"background": "wizard"})
        self.assertEqual((calls, self.app.route_plan_state(self.session)["attempts"]), ([], 0))

    def test_the_embodied_ai_map_starts_in_the_field_and_holds_no_paper(self):
        self.gateway(reply(EMBODIED))
        out = self.app.route_plan(self.session, boundary={"background": "engineering", "depth": "read_papers"})
        found = {c["name"] for c in out["graph"]["concepts"]}
        self.assertEqual(found, {"Robot Learning", "Computer Vision / Perception", "Vision-Language Models", "World Models", "Robot Manipulation", "VLA"})
        self.assertIn({"name": "Linear algebra", "why": "foundation_not_allowed"}, out["report"]["dropped_concepts"])
        self.assertIn({"name": "RT-2 paper", "why": "paper_shaped"}, out["report"]["dropped_concepts"])
        self.assertTrue(out["report"]["papers_ignored"])
        self.assertEqual(out["boundary"], {"background": "engineering", "depth": "read_papers"})

    def test_a_skipped_boundary_also_leaves_out_the_basics(self):
        self.gateway(reply(EMBODIED))
        out = self.app.route_plan(self.session)
        self.assertNotIn("Linear algebra", {c["name"] for c in out["graph"]["concepts"]})

    def test_only_a_reader_who_starts_from_scratch_gets_a_foundation_with_its_reason(self):
        self.gateway(reply(EMBODIED))
        out = self.app.route_plan(self.session, boundary={"background": "unknown", "depth": "overview"})
        basics = [c for c in out["graph"]["concepts"] if c["name"] == "Linear algebra"]
        self.assertEqual([(c["type"], c["why"]) for c in basics], [("foundation", "matrices underlie every model")])

    def test_the_project_page_takes_the_same_boundary(self):
        pid = self.app.create_project("Embodied", "manual", ["embodied"])["project_id"]
        calls = self.gateway(reply(EMBODIED))
        out = self.app.route_plan_project(pid, "从头学具身智能", boundary={"background": "unknown"})
        self.assertEqual(json.loads(calls[0][1][1]["content"])["boundary"], {"background": "unknown"})
        self.assertIn("Linear algebra", {c["name"] for c in out["graph"]["concepts"]})
        with self.assertRaises(ValueError):
            self.app.route_plan_project(pid, "从头学具身智能", boundary={"depth": "bogus"})

    def test_the_boundary_never_carries_project_history(self):
        self.app.create_project("Secret other project", "manual", ["classified"])
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session, boundary={"background": "other", "depth": "implement"})
        self.assertNotIn("classified", json.dumps(calls[0][1], ensure_ascii=False))


class PlanTests(Fixture):
    def test_a_good_reply_becomes_a_normalised_checked_graph(self):
        calls = self.gateway(reply(GOOD))
        out = self.app.route_plan(self.session)
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "ai")
        self.assertEqual(sorted(c["name"] for c in out["graph"]["concepts"]), ["Crystal structure", "Epitaxy", "MBE"])
        self.assertEqual(out["tokens"], 612)
        self.assertEqual([(c[0], c[2]) for c in calls], [("learning_path_plan", False)])

    def test_the_model_sees_only_the_goal_and_the_draft_never_other_projects_or_papers(self):
        self.app.create_project("Secret other project", "manual", ["classified"])
        self.app.store.upsert_papers([{"key": "x", "title": "PRIVATE TITLE", "abstract": "private abstract", "published": "2026-01-01"}])
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        sent = json.dumps(calls[0][1], ensure_ascii=False)
        for forbidden in ("Secret other project", "classified", "PRIVATE TITLE", "private abstract"):
            self.assertNotIn(forbidden, sent)
        self.assertIn("半导体晶体生长", sent)

    def test_the_input_is_bounded(self):
        session = self.app.create_guidance_session("长", "目标" * 2000)["id"]
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(session)
        self.assertLessEqual(len(json.dumps(calls[0][1], ensure_ascii=False)), 3000)

    def test_a_reply_wrapped_in_text_or_a_code_fence_is_still_read(self):
        self.gateway(reply("Here you go:\n```json\n" + json.dumps(GOOD) + "\n```\nHope it helps"))
        self.assertTrue(self.app.route_plan(self.session)["ok"])

    def test_a_reply_that_wraps_the_graph_in_a_draft_key_is_read(self):
        self.gateway(reply({"reply": "ok", "graph": GOOD}))
        self.assertTrue(self.app.route_plan(self.session)["ok"])

    def test_broken_replies_degrade_with_a_named_reason_and_keep_the_session(self):
        for bad, why in (("not json at all", "bad_reply"), ('{"concepts": "x"}', "bad_reply"), ('{"concepts": []}', "bad_reply"),
                         ('{"concepts": [{"name": "  "}]}', "bad_reply")):
            session = self.app.create_guidance_session("x", "半导体生长")["id"]   # each paid attempt counts, so one session each
            self.gateway(reply(bad))
            out = self.app.route_plan(session)
            self.assertEqual((out["ok"], out["mode"], out["reason_code"]), (False, "local", why), bad)
            self.assertIsNone(out["graph"])
            self.assertEqual(self.app.store.guidance_session(session)["status"], "draft")

    def test_gateway_refusals_degrade_without_a_graph_and_cost_no_attempt(self):
        for result in ({"ok": False, "degraded": True, "disabled": True, "reason": "AI disabled"},
                       {"ok": False, "degraded": True, "reason": "no API key"},
                       {"ok": False, "degraded": True, "reason": "awaiting owner approval"},
                       {"ok": False, "degraded": True, "reason": "daily token ceiling"}):
            self.gateway(result)
            out = self.app.route_plan(self.session)
            self.assertFalse(out["ok"])
            self.assertEqual(out["mode"], "local")
            self.assertTrue(out["reason"])
        self.assertEqual(self.app.route_plan_state(self.session)["attempts"], 0)

    def test_a_gateway_exception_degrades_too(self):
        def boom(*a, **k):
            raise RuntimeError("socket closed")
        self.gateway(boom)
        out = self.app.route_plan(self.session)
        self.assertEqual((out["ok"], out["mode"]), (False, "local"))

    def test_a_dry_run_never_reaches_a_provider_and_returns_no_graph(self):
        calls = self.gateway({"ok": False, "degraded": True, "reason": "dry run"})
        out = self.app.route_plan(self.session, dry_run=True)
        self.assertEqual((out["ok"], calls[0][2]), (False, True))

    def test_repairs_are_reported_not_hidden(self):
        messy = {"concepts": GOOD["concepts"] + [{"id": "d", "name": "Loop", "terms": ["loop"], "hint": 2, "needs": ["d"]},
                                                 {"id": "e", "name": "Epitaxy", "terms": ["epitaxy"], "hint": 2, "needs": []}], "targets": ["c"]}
        self.gateway(reply(messy))
        out = self.app.route_plan(self.session)
        self.assertEqual(len(out["report"]["merged"]), 1)
        self.assertEqual([d["why"] for d in out["report"]["dropped_edges"]], ["self"])

    def test_the_plan_is_kept_so_a_reload_does_not_cost_another_call_and_reports_no_fresh_tokens(self):
        calls = self.gateway(reply(GOOD))
        first = self.app.route_plan(self.session)
        second = self.app.route_plan(self.session)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second["graph"], first["graph"])
        self.assertEqual((second["mode"], second["tokens"]), ("kept", None))

    def test_a_search_or_a_turn_between_generations_does_not_reset_the_limit(self):
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        for _ in range(routeplan.MAX_REGENERATIONS):
            with mock.patch.object(self.app.source, "discover_topic", return_value=[]):
                self.app.guidance_search(self.session, "semiconductor growth")
            self.assertTrue(self.app.route_plan(self.session, regenerate=True)["ok"])
        with mock.patch.object(self.app.source, "discover_topic", return_value=[]):
            self.app.guidance_search(self.session, "semiconductor growth")
            self.app.guidance_preview(self.session)
        with self.assertRaises(ValueError):
            self.app.route_plan(self.session, regenerate=True)
        self.assertEqual(self.app.route_plan(self.session)["mode"], "kept")   # the plan itself survived every write
        self.assertEqual(len(calls), 1 + routeplan.MAX_REGENERATIONS)

    def test_regenerating_is_explicit_and_limited(self):
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        for _ in range(routeplan.MAX_REGENERATIONS):
            self.assertTrue(self.app.route_plan(self.session, regenerate=True)["ok"])
        with self.assertRaises(ValueError):
            self.app.route_plan(self.session, regenerate=True)
        self.assertEqual(len(calls), 1 + routeplan.MAX_REGENERATIONS)

    def test_a_paid_attempt_that_gives_no_usable_plan_counts(self):
        calls = self.gateway(reply("not json"))
        for _ in range(1 + routeplan.MAX_REGENERATIONS):
            self.assertEqual(self.app.route_plan(self.session)["reason_code"], "bad_reply")
        with self.assertRaises(ValueError):
            self.app.route_plan(self.session)
        self.assertEqual(len(calls), 1 + routeplan.MAX_REGENERATIONS)
        self.assertEqual(self.app.route_plan_state(self.session)["attempts"], 1 + routeplan.MAX_REGENERATIONS)

    def test_a_timeout_whose_cost_is_unknown_counts_too(self):
        self.gateway({"ok": False, "degraded": True, "usage_unknown": True, "reason": "TimeoutError: timed out"})
        self.assertEqual(self.app.route_plan(self.session)["reason_code"], "network")
        self.assertEqual(self.app.route_plan_state(self.session)["attempts"], 1)

    def test_concurrent_requests_cannot_bypass_the_limit(self):
        import threading
        gate = threading.Event()
        calls = []

        def slow(operation, messages, dry_run=False):
            calls.append(operation)
            gate.wait(2)
            return reply(GOOD)
        results = []

        def attempt():
            other = App(root=str(self.root), data_dir=str(self.root / "data"))
            try:
                with mock.patch.object(other.gateway, "call", side_effect=slow):
                    results.append(other.route_plan(self.session, regenerate=True))
            except ValueError as exc:
                results.append(str(exc))
            finally:
                other.store.close()
        self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        threads = [threading.Thread(target=attempt) for _ in range(6)]
        for t in threads:
            t.start()
        time.sleep(0.4)
        gate.set()
        for t in threads:
            t.join(10)
        paid = [r for r in results if isinstance(r, dict) and r.get("ok")]
        self.assertLessEqual(len(paid), routeplan.MAX_REGENERATIONS)
        self.assertLessEqual(len(calls), routeplan.MAX_REGENERATIONS)

    def test_a_second_request_for_the_same_session_while_one_is_running_is_refused(self):
        import threading
        started, release = threading.Event(), threading.Event()

        def slow(operation, messages, dry_run=False):
            started.set()
            release.wait(2)
            return reply(GOOD)
        worker = threading.Thread(target=lambda: self.app.route_plan(self.session))
        with mock.patch.object(self.app.gateway, "call", side_effect=slow):
            worker.start()
            self.assertTrue(started.wait(2))
            with self.assertRaises(ValueError):
                self.app.route_plan(self.session)
            release.set()
            worker.join(5)

    def test_a_failed_generation_does_not_hide_an_earlier_kept_plan(self):
        self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        self.gateway(reply("nope"))
        self.assertFalse(self.app.route_plan(self.session, regenerate=True)["ok"])
        self.assertEqual(self.app.route_plan(self.session)["mode"], "kept")

    def test_the_session_view_carries_the_kept_plan_so_the_page_can_restore_it(self):
        self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        self.assertEqual(len(self.app.guidance_session_view(self.session)["draft"]["route_plan"]["graph"]["concepts"]), 3)

    def test_the_kept_state_is_removed_when_the_session_ends(self):
        self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        self.app.cancel_guidance(self.session)
        self.assertIsNone(self.app.store.get_setting(f"route_plan_{self.session}"))

    def test_a_recursion_bomb_in_a_reply_is_a_bad_reply_not_a_crash(self):
        self.gateway(reply('{"a":' * 1500 + "1" + "}" * 1500))
        self.assertEqual(self.app.route_plan(self.session)["reason_code"], "bad_reply")

    def test_the_worst_case_input_fits_the_registered_cap_by_a_pessimistic_estimate(self):
        cfg = json.loads((ROOT / "harness" / "budget.json").read_text())["operations"]["learning_path_plan"]
        english = routeplan.messages("字" * 5000, ["关" * 500] * 20, True)
        chars = sum(len(m["content"]) for m in english)
        self.assertLessEqual(chars * 1.5, cfg["cap"]["input"] - cfg["input_cap_components"]["framing_and_margin"] + 150)
        both = routeplan.messages("字" * 5000, ["关" * 500] * 20, True, {"background": "ai_researcher", "depth": "read_papers"})   # and the longest boundary
        self.assertLessEqual(sum(len(m["content"]) for m in both) * 1.5, cfg["cap"]["input"] - cfg["input_cap_components"]["framing_and_margin"] + 150)

    def test_unknown_or_finished_sessions_are_refused(self):
        with self.assertRaises(ValueError):
            self.app.route_plan("no-such-session")

    def test_english_output_is_requested_in_an_english_ui(self):
        (self.app.data / "settings.json").write_text(json.dumps({"language": "en-US"}))
        calls = self.gateway(reply(GOOD))
        self.app.route_plan(self.session)
        self.assertIn(App.ENGLISH_OUTPUT, calls[0][1][0]["content"])
        self.assertEqual(routeplan.ENGLISH_OUTPUT, App.ENGLISH_OUTPUT)


class GroundingTests(Fixture):
    class Router:
        def __init__(self, counts):
            self.counts, self.urls = counts, []

        def __call__(self, request, timeout=None):
            self.urls.append(request.full_url)
            import urllib.parse
            decoded = urllib.parse.unquote_plus(request.full_url)
            results = []
            for term, n in sorted(self.counts.items(), key=lambda kv: -len(kv[0])):   # the most specific term wins
                if term in decoded:
                    results = [{"id": f"https://openalex.org/W{abs(hash(term)) % 10**6}{i}", "title": f"{term.title()} paper {i}", "doi": f"https://doi.org/10.1/{abs(hash(term)) % 10**6}{i}",
                                "publication_date": "2025-01-01", "ids": {}, "abstract_inverted_index": {term.split()[0]: [0], "growth": [1]}} for i in range(n)]
                    break
            reply_ = mock.MagicMock()
            reply_.__enter__.return_value = reply_
            reply_.read.return_value = json.dumps({"results": results}).encode()
            reply_.headers = {}
            return reply_

    def graph(self):
        return pg.normalize(GOOD)[0]

    def test_every_concept_is_searched_with_its_terms_and_counted(self):
        router = self.Router({"crystal structure": 4, "epitaxy": 5, "molecular beam epitaxy": 0})
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            checked = self.app.route_ground(self.graph())
        by_name = {c["name"]: c for c in checked["concepts"]}
        self.assertEqual(by_name["Crystal structure"]["papers"], 4)
        self.assertEqual(by_name["MBE"]["papers"], 0)
        self.assertEqual(by_name["MBE"]["grounding"], "none")
        self.assertEqual(by_name["Epitaxy"]["grounding"], "ok")
        self.assertEqual(len(checked["concepts"]), 3)

    def test_a_concept_with_no_terms_is_flagged_not_searched(self):
        graph, _ = pg.normalize({"concepts": [{"id": "a", "name": "量子阱", "terms": []}]})
        router = self.Router({})
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            checked = self.app.route_ground(graph)
        self.assertEqual((checked["concepts"][0]["grounding"], router.urls), ("no_terms", []))

    def test_edges_get_corpus_support_labels_and_the_input_is_not_modified(self):
        router = self.Router({"crystal structure": 4, "epitaxy": 5, "molecular beam epitaxy": 4})
        graph = self.graph()
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            checked = self.app.route_ground(graph)
        self.assertTrue(all("support" in e for e in checked["prereqs"]))
        self.assertTrue(all(e["support"] is None for e in graph["prereqs"]))
        self.assertTrue(all(e.get("support_label") in ("unknown", "supported", "contradicted", "neutral") for e in checked["prereqs"]))

    def test_a_failed_search_is_reported_for_its_concept_and_the_rest_are_skipped(self):
        def failing(request, timeout=None):
            raise urllib.error.URLError("offline")
        with mock.patch.object(sources.urllib.request, "urlopen", failing):
            checked = self.app.route_ground(self.graph())
        self.assertEqual(checked["concepts"][0]["grounding"], "unavailable")
        self.assertEqual({c["grounding"] for c in checked["concepts"][1:]}, {"skipped"})

    def test_a_network_failure_stops_the_remaining_searches_too(self):
        calls = {"n": 0}

        def down(request, timeout=None):
            calls["n"] += 1
            raise urllib.error.URLError("offline")
        with mock.patch.object(sources.urllib.request, "urlopen", down):
            checked = self.app.route_ground(self.graph())
        self.assertEqual([c["grounding"] for c in checked["concepts"]], ["unavailable", "skipped", "skipped"])
        self.assertLessEqual(calls["n"], 4)

    def test_grounding_has_an_overall_deadline(self):
        clock = [0.0]

        def slow_fetch(*a, **k):
            clock[0] += 9.0   # a concept needs up to two requests, so about eighteen seconds
            return {"results": []}
        with mock.patch("app.sources.OpenAlex._fetch", side_effect=slow_fetch), mock.patch("app.service.time.monotonic", lambda: clock[0]):
            checked = self.app.route_ground(self.graph())
        self.assertEqual([c["grounding"] for c in checked["concepts"]], ["none", "none", "skipped"])   # no new concept starts after 20 s

    def test_a_rate_limit_stops_the_remaining_searches(self):
        def limited(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 429, "slow down", {}, None)
        with mock.patch.object(sources.urllib.request, "urlopen", limited):
            checked = self.app.route_ground(self.graph())
        self.assertEqual([c["grounding"] for c in checked["concepts"]], ["unavailable", "skipped", "skipped"])

    def test_only_public_search_terms_leave_the_machine(self):
        router = self.Router({})
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            self.app.route_ground(self.graph())
        sent = " ".join(router.urls)
        self.assertNotIn("半导体", sent)
        self.assertNotIn("goal", sent.lower())


class HttpTests(Fixture):
    def serve(self):
        import threading
        from app import server
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def post(self, port, path, body, origin=None):
        import urllib.request
        headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_plan_and_create_over_http_with_a_dry_run_that_sends_nothing(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, session = self.post(port, "/api/project-guidance/sessions", {"name": "晶体", "goal": "半导体晶体生长"})
            self.assertIn(status, (200, 201))
            sid = session["session"]["id"] if "session" in session else session["id"]
            status, planned = self.post(port, f"/api/project-guidance/sessions/{sid}/route", {"dry_run": True})
            self.assertEqual((status, planned["ok"], planned["reason_code"]), (200, False, "dry_run"))
            graph = pg.normalize(GOOD)[0]
            status, done = self.post(port, f"/api/project-guidance/sessions/{sid}/finalize", {"selected_keys": [], "route": {"graph": graph, "mastered": []}})
            self.assertEqual(status, 200)
            self.assertTrue(self.app.route_get(done["project_id"])["enabled"])

    def test_a_bad_boundary_is_a_400_on_both_plan_routes_and_costs_nothing(self):
        port = self.serve()
        pid = self.app.create_project("Embodied", "manual", ["embodied"])["project_id"]
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.post(port, f"/api/project-guidance/sessions/{self.session}/route", {"boundary": {"background": "wizard"}})
            self.assertEqual(status, 400)
            self.assertIn("background", body["error"])
            status, body = self.post(port, f"/api/route?project_id={pid}", {"action": "plan", "goal": "从头学具身智能", "boundary": {"depth": "forever"}})
            self.assertEqual(status, 400)
        self.assertEqual(self.app.route_plan_state(self.session)["attempts"], 0)
        self.assertIsNone(self.app.store.get_setting(f"route_plan_project_{pid}"))

    def test_a_bad_map_is_a_400_and_creates_nothing(self):
        port = self.serve()
        before = len(self.app.projects.list_projects())
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.post(port, "/api/projects", {"name": "X", "creation_mode": "manual", "keywords": ["a"], "route": {"graph": {"concepts": [], "prereqs": []}}})
        self.assertEqual(status, 400)
        self.assertEqual(len(self.app.projects.list_projects()), before)

    def test_ground_checks_a_graph_without_saving_it(self):
        port = self.serve()
        graph = pg.normalize(GOOD)[0]
        # only the OpenAlex client is faked; the test's own HTTP client to the local server stays real
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}), \
                mock.patch("app.sources.OpenAlex._fetch", return_value={"results": []}):
            status, body = self.post(port, "/api/route", {"action": "ground", "graph": graph})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["graph"]["concepts"]), 3)
        self.assertEqual({c["grounding"] for c in body["graph"]["concepts"]}, {"none"})

    def test_the_new_routes_refuse_a_foreign_origin(self):
        port = self.serve()
        self.assertEqual(self.post(port, "/api/project-guidance/sessions/x/route", {}, origin="http://evil.example")[0], 403)
        self.assertEqual(self.post(port, "/api/route", {"action": "ground", "graph": {}}, origin="http://evil.example")[0], 403)


class FlowTests(Fixture):
    def test_confirming_a_plan_saves_the_map_with_the_project_and_keeps_start_marks(self):
        self.gateway(reply(GOOD))
        plan = self.app.route_plan(self.session)
        mastered = [c["id"] for c in plan["graph"]["concepts"] if c["name"] == "Crystal structure"]
        project = self.app.create_project("Crystals", "manual", ["epitaxy"], route={"graph": plan["graph"], "mastered": mastered})["project_id"]
        route = self.app.route_get(project)
        self.assertTrue(route["enabled"])
        self.assertEqual(len(route["graph"]["concepts"]), 3)
        status = {c["name"]: route["progress"][c["id"]]["status"] for c in route["graph"]["concepts"]}
        self.assertEqual(status, {"Crystal structure": "satisfied", "Epitaxy": "unlocked", "MBE": "locked"})   # the mark opens the next concept

    def test_an_invalid_graph_blocks_creation_before_anything_is_created(self):
        before = len(self.app.projects.list_projects())
        with self.assertRaises(ValueError):
            self.app.create_project("Bad", "manual", ["x"], route={"graph": {"concepts": [], "prereqs": []}})
        self.assertEqual(len(self.app.projects.list_projects()), before)

    def test_finalizing_a_guidance_session_can_carry_the_map(self):
        self.gateway(reply(GOOD))
        plan = self.app.route_plan(self.session)
        done = self.app.finalize_guidance(self.session, None, [], route={"graph": plan["graph"], "mastered": []})
        self.assertTrue(self.app.route_get(done["project_id"])["enabled"])

    def test_a_project_without_a_map_is_unchanged(self):
        project = self.app.create_project("Plain", "manual", ["x"])["project_id"]
        self.assertFalse(self.app.route_get(project)["enabled"])


if __name__ == "__main__":
    unittest.main()
