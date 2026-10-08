"""A concept can say what it is. The model may write one sentence for one concept when the person clicks (the
`concept_intro` operation), the page can list the papers of the project that fit a concept and show a few public
papers about it; none of it is saved until the person saves the map."""
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
sys.path.insert(0, str(ROOT / "scripts"))
import budget
from app import routeplan, server
from app.service import App
from app.sources import SourceError

PLAN = {"concepts": [
    {"id": "a", "name": "Crystal basics", "terms": ["crystal growth", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial"], "hint": 2, "needs": ["a"]}], "targets": ["b"]}


def reply(text, tokens=90):
    return {"ok": True, "content": text, "usage": {"total_tokens": tokens, "prompt_tokens": 70, "completion_tokens": tokens - 70}}


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
        self.route = self.app.route_save(self.pid, plan=PLAN)
        self.cid = {c["name"]: c["id"] for c in self.route["graph"]["concepts"]}

    def gateway(self, result):
        calls = []

        def fake(operation, messages, dry_run=False):
            calls.append((operation, messages, dry_run))
            return result() if callable(result) else result
        patcher = mock.patch.object(self.app.gateway, "call", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def paper(self, key, title, abstract="", pid=None):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": "2026-01-01"}], project_id=pid or self.pid)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / "harness" / "budget.json").read_text())
        self.op = self.cfg["operations"]["concept_intro"]

    def test_it_is_registered_bounded_and_the_owners_approval_is_recorded_in_their_words(self):
        self.assertIs(self.op["owner_approved"], True)
        self.assertIn("2026-10-06", self.op["approval_note"])
        self.assertIn("写这个节点的简介", self.op["approval_note"])
        self.assertIn("批准：简介 + 方向解释两项上调", self.op["approval_note"])      # the second approval, in the owner's words
        self.assertEqual((self.op["cap"]["input"], self.op["cap"]["output"]), (2000, 400))
        self.assertEqual(sum(self.op["input_cap_components"].values()), self.op["cap"]["input"])
        self.assertFalse(self.op["enabled_by_default"])
        self.assertEqual(self.op["trigger"], "interactive")
        self.assertLessEqual(self.op["reference"]["input"], self.op["cap"]["input"])
        self.assertLess(budget.cost(self.cfg, 2000, 400), 0.002)

    def test_the_prompt_file_has_the_header_and_matches_the_code(self):
        text = (ROOT / self.op["prompt"]).read_text(encoding="utf-8")
        self.assertIn("operation: concept_intro", text)
        self.assertIn("contract: implemented", text)
        self.assertIn(routeplan.INTRO_SYSTEM, text)

    def test_long_input_keeps_explicit_fields_and_bounds_optional_retrieval_on_full_wire(self):
        big = {"title": "题" * 500, "abstract": "摘" * 3000}
        out = routeplan.intro_messages("名" * 500, ["词" * 500, "词" * 500, "词" * 500], "目" * 5000, True, [big] * 5)
        from app.gateway import input_bound, request_envelope
        self.assertLessEqual(input_bound(request_envelope('concept_intro', 'deepseek-flash', 400, out)), self.op['cap']['input'])
        body = json.loads(out[-1]['content'])
        self.assertEqual(body['concept'], '名' * 30); self.assertEqual(body['terms'], ['词' * 30, '词' * 30])
        self.assertEqual(body['goal'], '目' * 40)
        self.assertLess(len(body['papers']), 3)
        self.assertTrue(all(p['title'] == '题' * 80 and p['abstract'] == '摘' * 200 for p in body['papers']))
        smaller = routeplan.intro_messages('Concept', ['term'], 'Goal', True, [{'title': 'Public paper', 'abstract': 'Public short abstract'}] * 3)
        self.assertEqual(len(json.loads(smaller[-1]['content'])['papers']), 3)

    def test_the_plan_operations_carry_the_raised_caps_the_owner_approved(self):
        for name in ("learning_path_plan", "learning_path_plan_project"):
            op = self.cfg["operations"][name]
            self.assertEqual((op["cap"]["input"], op["cap"]["output"]), (1460, 1500), name)
            self.assertEqual(op["reference"]["output"], 1100, name)
            self.assertEqual(sum(op["input_cap_components"].values()), 1460, name)
            self.assertIs(op["owner_approved"], True, name)
            self.assertIn("2026-10-06", op["approval_note"], name)


class JudgeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / "harness" / "budget.json").read_text())
        self.op = self.cfg["operations"]["direction_judge"]

    def test_it_is_registered_bounded_and_the_owners_approval_is_recorded_in_their_words(self):
        self.assertIs(self.op["owner_approved"], True)
        self.assertIn("2026-10-06", self.op["approval_note"])
        self.assertIn("批准：简介 + 方向解释两项上调", self.op["approval_note"])
        self.assertEqual((self.op["cap"]["input"], self.op["cap"]["output"]), (3000, 500))
        self.assertEqual(sum(self.op["input_cap_components"].values()), self.op["cap"]["input"])
        self.assertFalse(self.op["enabled_by_default"])
        self.assertEqual(self.op["trigger"], "interactive")
        self.assertLessEqual(self.op["reference"]["input"], self.op["cap"]["input"])
        self.assertLess(budget.cost(self.cfg, 3000, 500), 0.002)

    def test_the_prompt_file_has_the_header_and_matches_the_code(self):
        text = (ROOT / self.op["prompt"]).read_text(encoding="utf-8")
        self.assertIn("operation: direction_judge", text)
        self.assertIn("contract: implemented", text)
        self.assertIn(routeplan.JUDGE_SYSTEM, text)

    def test_the_longest_input_fits_the_cap_by_a_pessimistic_estimate(self):
        big = {"title": "题" * 500, "abstract": "摘" * 3000}
        out = routeplan.judge_messages([big] * 5, ["概" * 100] * 20, [{"name": "向" * 100, "intro": "介" * 100}] * 9, True)
        self.assertLessEqual(sum(len(m["content"]) for m in out) * 1.5, self.op["cap"]["input"])    # 1.5 tokens per character: a heuristic

    def test_the_reply_is_found_bare_fenced_or_wrapped_and_garbage_gives_nothing(self):
        item = {"papers": ["p1"], "verdict": "new"}
        self.assertEqual(routeplan.parse_judge(json.dumps({"results": [item]})), [item])
        self.assertEqual(routeplan.parse_judge("```json\n" + json.dumps({"results": [item, 5]}) + "\n```"), [item])
        self.assertEqual(routeplan.parse_judge("sure! " + json.dumps({"results": [item]}) + " done"), [item])
        for bad in ("", "no json", '{"results": 5}', '{"other": []}', None):
            self.assertEqual(routeplan.parse_judge(bad), [])


class ParseIntroTests(unittest.TestCase):
    def test_a_json_reply_without_an_intro_offers_nothing(self):
        self.assertEqual(routeplan.parse_intro('{"concept": "x"}'), "")
        self.assertEqual(routeplan.parse_intro('{"intro": 5}'), "")

    def test_json_and_plain_replies_give_one_clean_sentence(self):
        self.assertEqual(routeplan.parse_intro('{"intro": "一句话。"}'), "一句话。")
        self.assertEqual(routeplan.parse_intro('简介：“一句话。”'), "一句话。")
        self.assertEqual(routeplan.parse_intro("在这些论文里指用示范学技能。\n门槛：要先懂监督学习，难在数据质量。"), "在这些论文里指用示范学技能。 门槛：要先懂监督学习，难在数据质量。")
        self.assertEqual(routeplan.parse_intro('{"intro": "第一行\\n第二行"}'), "第一行 第二行")
        self.assertEqual(routeplan.parse_intro(""), "")


class IntroTests(Fixture):
    def test_one_click_asks_once_and_returns_a_sentence_without_saving_anything(self):
        calls = self.gateway(reply('{"intro": "把外延生长的原子层一层层对齐的方法。"}'))
        before = self.app.route_get(self.pid)
        out = self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertEqual((out["ok"], out["intro"], out["intro_by"]), (True, "把外延生长的原子层一层层对齐的方法。", "ai"))
        self.assertEqual([c[0] for c in calls], ["concept_intro"])
        after = self.app.route_get(self.pid)
        self.assertEqual((after["graph"], after["revision"]), (before["graph"], before["revision"]))

    def test_a_plain_sentence_reply_is_read_too_and_quotes_are_removed(self):
        self.gateway(reply('"外延是在晶体上继续长出同样取向的晶体。"'))
        self.assertEqual(self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])["intro"], "外延是在晶体上继续长出同样取向的晶体。")

    def test_a_long_reply_is_cut_to_the_limit(self):
        self.gateway(reply("很长" * 100))
        self.assertLessEqual(len(self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])["intro"]), 140)

    def test_the_model_sees_the_concept_the_goal_and_its_matching_papers_only(self):
        self.app.create_project("Secret other project", "manual", ["classified"])
        self.paper("x", "PRIVATE TITLE", "private abstract")                                    # in the project, matches nothing
        self.paper("m1", "Epitaxial growth of GaN", "epitaxy of gallium nitride on sapphire needs lattice matching")
        calls = self.gateway(reply("一句话。"))
        self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        sent = calls[0][1][1]["content"]
        for forbidden in ("Secret other project", "classified", "PRIVATE TITLE", "private abstract", "Crystal basics", '"m1"', "journal"):
            self.assertNotIn(forbidden, sent)
        body = json.loads(sent)
        self.assertEqual(set(body), {"concept", "terms", "goal", "papers"})
        self.assertEqual(body["papers"], [{"title": "Epitaxial growth of GaN", "abstract": "epitaxy of gallium nitride on sapphire needs lattice matching"}])
        for wanted in ("Epitaxy", "epitaxy"):
            self.assertIn(wanted, sent)

    def test_at_most_three_matching_papers_are_sent_each_cut_to_size(self):
        for i in range(6):
            self.paper(f"m{i}", "Epitaxy " + "T" * 300, "epitaxy " + "A" * 900)
        calls = self.gateway(reply("一句话。"))
        self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        papers = json.loads(calls[0][1][1]["content"])["papers"]
        self.assertEqual(len(papers), routeplan.INTRO_PAPERS)
        self.assertTrue(all(len(p["title"]) <= routeplan.PAPER_TITLE_CHARS and len(p["abstract"]) <= routeplan.INTRO_ABSTRACT_CHARS for p in papers))

    def test_a_concept_no_paper_uses_is_asked_about_without_papers(self):
        calls = self.gateway(reply("一句话。"))
        self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertEqual(json.loads(calls[0][1][1]["content"])["papers"], [])

    def test_the_goal_is_bounded(self):
        self.app.projects.update_project(self.pid, name="N" * 400)
        calls = self.gateway(reply("一句话。"))
        self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertLess(len(json.dumps(calls[0][1], ensure_ascii=False)), 800)

    def test_an_unreadable_reply_degrades_with_a_reason_and_counts_as_an_attempt(self):
        self.gateway(reply("   "))
        out = self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertEqual((out["ok"], out["reason_code"]), (False, "bad_reply"))
        self.assertEqual(out["attempts_left"], App.CONCEPT_INTROS_PER_DAY - 1)

    def test_a_gateway_refusal_costs_no_attempt(self):
        self.gateway({"ok": False, "reason": "no API key"})
        out = self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertEqual((out["ok"], out["reason_code"], out["attempts_left"]), (False, "no_key", App.CONCEPT_INTROS_PER_DAY))

    def test_a_dry_run_sends_nothing_and_counts_nothing(self):
        out = self.app.route_concept_intro(self.pid, self.cid["Epitaxy"], dry_run=True)
        self.assertEqual((out["ok"], out["reason_code"], out["attempts_left"]), (False, "dry_run", App.CONCEPT_INTROS_PER_DAY))

    def test_twenty_a_day_per_project_and_then_it_says_so(self):
        calls = self.gateway(reply("一句话。"))
        for _ in range(App.CONCEPT_INTROS_PER_DAY):
            self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        with self.assertRaisesRegex(ValueError, "今天已经"):
            self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertEqual(len(calls), App.CONCEPT_INTROS_PER_DAY)
        other = self.app.create_project("Other", "manual", ["x"])["project_id"]
        self.app.route_save(other, plan=PLAN)
        self.app.route_concept_intro(other, {c["name"]: c["id"] for c in self.app.route_get(other)["graph"]["concepts"]}["Epitaxy"])   # its own allowance

    def test_one_call_at_a_time_per_project(self):
        started, release = threading.Event(), threading.Event()

        def slow():
            started.set(); release.wait(3)
            return reply("一句话。")
        self.gateway(slow)
        worker = threading.Thread(target=lambda: self.app.route_concept_intro(self.pid, self.cid["Epitaxy"]))
        worker.start()
        self.assertTrue(started.wait(3))
        with self.assertRaisesRegex(ValueError, "稍候"):
            self.app.route_concept_intro(self.pid, self.cid["Crystal basics"])
        release.set(); worker.join(5)

    def test_an_unknown_concept_or_project_is_refused_before_any_call(self):
        calls = self.gateway(reply("一句话。"))
        for args in ((self.pid, "nope"), ("no-such", self.cid["Epitaxy"]), ("", self.cid["Epitaxy"])):
            with self.assertRaises(ValueError):
                self.app.route_concept_intro(*args)
        self.assertEqual(calls, [])

    def test_the_sentence_is_kept_as_the_models_when_the_person_saves_it(self):
        self.gateway(reply("一句话说明外延。"))
        out = self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        graph = self.app.route_get(self.pid)["graph"]
        for c in graph["concepts"]:
            if c["id"] == self.cid["Epitaxy"]:
                c["intro"], c["intro_by"] = out["intro"], out["intro_by"]
        saved = self.app.route_save(self.pid, graph=graph)
        got = next(c for c in saved["graph"]["concepts"] if c["id"] == self.cid["Epitaxy"])
        self.assertEqual((got["intro"], got["intro_by"]), ("一句话说明外延。", "ai"))

    def test_english_output_is_asked_for_in_an_english_interface(self):
        (self.app.data / "settings.json").write_text(json.dumps({"language": "en-US"}))
        calls = self.gateway(reply("One sentence."))
        self.app.route_concept_intro(self.pid, self.cid["Epitaxy"])
        self.assertIn('Reply in English.', calls[0][1][0]['content'])
        self.assertIn(routeplan.INTRO_SYSTEM, calls[0][1][0]['content'])


class DraftWithIntroTests(Fixture):
    def test_a_drafted_map_keeps_the_models_intros_marked_as_the_models(self):
        draft = {"concepts": [{"id": "a", "name": "World models", "terms": ["world model", "latent dynamics"], "hint": 2, "needs": [],
                               "intro": "让智能体在脑中模拟环境。"}], "targets": ["a"]}
        self.gateway(reply(json.dumps(draft, ensure_ascii=False), tokens=300))
        out = self.app.route_plan_project(self.pid, "学世界模型")
        concept = out["graph"]["concepts"][0]
        self.assertEqual((concept["intro"], concept["intro_by"]), ("让智能体在脑中模拟环境。", "ai"))

    def test_the_plan_prompt_asks_for_an_intro_and_the_file_matches(self):
        self.assertIn("intro", routeplan.SYSTEM)
        for name in ("learning-path-plan.md", "learning-path-plan-project.md"):
            self.assertIn(routeplan.SYSTEM, (ROOT / "prompts" / name).read_text(encoding="utf-8"))


class ConceptPapersTests(Fixture):
    def setUp(self):
        super().setUp()
        self.paper("e1", "Epitaxial layers", "epitaxy of thin films")
        self.paper("e2", "More epitaxy", "epitaxial growth on lattice-matched substrates")
        self.paper("c1", "Crystal growth basics", "crystal growth and lattice")
        self.paper("none", "Poetry", "Tang dynasty")

    def test_the_papers_that_fit_a_concept_are_listed_with_the_words_that_matched(self):
        out = self.app.route_concept_papers(self.pid, self.cid["Epitaxy"])
        keys = [p["key"] for p in out["papers"]]
        self.assertTrue({"e1", "e2"} <= set(keys))
        self.assertNotIn("none", keys)
        first = next(p for p in out["papers"] if p["key"] == "e1")
        self.assertEqual(first["title"], "Epitaxial layers")
        self.assertEqual(set(first["terms"]), {"epitaxy", "epitaxial"})   # the words of the concept that the title or abstract uses

    def test_it_says_what_the_reader_did_with_each_paper_and_never_what_they_did_not(self):
        self.app.record_feedback("e1", "useful", project_id=self.pid)
        out = {p["key"]: p for p in self.app.route_concept_papers(self.pid, self.cid["Epitaxy"])["papers"]}
        self.assertEqual(out["e1"]["feedback"], "useful")
        self.assertIsNone(out["e2"]["feedback"])

    def test_at_most_five_and_the_total_is_given(self):
        for i in range(8):
            self.paper(f"m{i}", f"Epitaxy study {i}", "epitaxy")
        out = self.app.route_concept_papers(self.pid, self.cid["Epitaxy"])
        self.assertEqual(len(out["papers"]), 5)
        self.assertGreaterEqual(out["total"], 10)

    def test_another_projects_papers_are_not_listed(self):
        other = self.app.create_project("Poetry", "manual", ["poetry"])["project_id"]
        self.paper("o1", "Epitaxy elsewhere", "epitaxy", pid=other)
        self.assertNotIn("o1", [p["key"] for p in self.app.route_concept_papers(self.pid, self.cid["Epitaxy"])["papers"]])

    def test_it_is_read_only(self):
        before = self.app.route_get(self.pid)["revision"]
        self.app.route_concept_papers(self.pid, self.cid["Epitaxy"])
        self.assertEqual(self.app.route_get(self.pid)["revision"], before)

    def test_titles_stay_text(self):
        self.paper("x", "<img src=x onerror=1> epitaxy", "epitaxy")
        titles = [p["title"] for p in self.app.route_concept_papers(self.pid, self.cid["Epitaxy"])["papers"]]
        self.assertIn("<img src=x onerror=1> epitaxy", titles)   # the page escapes it

    def test_an_unknown_concept_is_refused(self):
        with self.assertRaises(ValueError):
            self.app.route_concept_papers(self.pid, "nope")


class ConceptExamplesTests(Fixture):
    FOUND = [{"title": f"Public paper {i}", "abstract": "x" * 400, "published": f"202{i}-05-01", "source": "Nature", "key": f"k{i}"} for i in range(5)]

    def test_a_few_public_papers_with_year_and_a_short_snippet(self):
        with mock.patch.object(self.app.source, "discover_topic", return_value=self.FOUND) as search:
            out = self.app.route_concept_examples(self.pid, self.cid["Epitaxy"])
        search.assert_called_once()
        self.assertEqual(search.call_args[0][0], "epitaxy")           # only the concept's own first search term leaves the machine
        self.assertEqual([e["title"] for e in out["examples"]], ["Public paper 0", "Public paper 1", "Public paper 2"])
        self.assertEqual(out["examples"][0]["year"], "2020")
        self.assertLessEqual(len(out["examples"][0]["snippet"]), 160)
        self.assertTrue(out["ok"])

    def test_nothing_found_is_said_plainly(self):
        with mock.patch.object(self.app.source, "discover_topic", return_value=[]):
            out = self.app.route_concept_examples(self.pid, self.cid["Epitaxy"])
        self.assertEqual((out["ok"], out["examples"], out["reason_code"]), (True, [], "none"))

    def test_an_outage_is_reported_not_raised_and_nothing_is_stored(self):
        before = self.app.route_get(self.pid)["revision"]
        with mock.patch.object(self.app.source, "discover_topic", side_effect=SourceError("down", "unavailable")):
            out = self.app.route_concept_examples(self.pid, self.cid["Epitaxy"])
        self.assertEqual((out["ok"], out["reason_code"]), (False, "unavailable"))
        self.assertEqual(self.app.route_get(self.pid)["revision"], before)

    def test_a_concept_without_search_terms_sends_nothing(self):
        graph = self.app.route_get(self.pid)["graph"]
        graph["concepts"][0]["name"], graph["concepts"][0]["terms"] = "晶体基础", []   # a Chinese name gets no search term made up for it
        self.app.route_save(self.pid, graph=graph)
        with mock.patch.object(self.app.source, "discover_topic") as search:
            out = self.app.route_concept_examples(self.pid, self.cid["Crystal basics"])
        search.assert_not_called()
        self.assertEqual(out["reason_code"], "no_terms")


class HttpTests(Fixture):
    def serve(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def post(self, port, body):
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/route", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_the_three_actions_over_http_and_a_dry_run_that_sends_nothing(self):
        self.paper("e1", "Epitaxial layers", "epitaxy")
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.post(port, {"action": "concept-papers", "project_id": self.pid, "concept": self.cid["Epitaxy"]})
            self.assertEqual((status, [p["key"] for p in body["papers"]]), (200, ["e1"]))
            status, body = self.post(port, {"action": "concept-intro", "project_id": self.pid, "concept": self.cid["Epitaxy"], "dry_run": True})
            self.assertEqual((status, body["ok"], body["reason_code"]), (200, False, "dry_run"))
            self.assertEqual(self.post(port, {"action": "concept-intro", "project_id": self.pid, "concept": "nope"})[0], 400)
            self.assertEqual(self.post(port, {"action": "concept-examples", "project_id": self.pid})[0], 400)


if __name__ == "__main__":
    unittest.main()
