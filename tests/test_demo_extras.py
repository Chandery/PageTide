"""The demo project's extras: the offline library import, asking about a selected sentence in the demo reading material,
and the Baidu Scholar interface that is no longer offered. Every model call is an error and the network is shut."""
import http.client
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import demo, demo_fixture as fixture, user_settings
from app.gateway import Gateway
from app.user_settings import SourcePolicy

import test_demo_sandbox as sandbox   # the tests directory is on the path under `unittest discover -s tests`

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "static" / "demo"
KEY = fixture.READING_KEY
S1, S2, S3 = (entry["sentence"] for entry in fixture.READING_QA)
TABLES = sandbox.REAL_TABLES + ("qa_history", "pdfs", "import_batches", "import_items", "summaries")


def _generator():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_demo_reading_pdf", ROOT / "scripts" / "make_demo_reading_pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReadingMaterialTests(unittest.TestCase):
    def test_the_committed_pdf_is_exactly_what_the_script_writes(self):
        self.assertEqual((ASSETS / fixture.READING_FILE).read_bytes(), _generator().build())

    def test_it_is_a_real_pdf_with_a_text_layer_and_the_banner_first(self):
        data = (ASSETS / fixture.READING_FILE).read_bytes()
        self.assertTrue(data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF"))
        runs = [m.replace("\\(", "(").replace("\\)", ")") for m in re.findall(r"\((.*)\) Tj", data.decode("latin-1"))]
        self.assertEqual(runs[0], fixture.READING["banner"])
        self.assertIn("not the paper's original text", runs[0])
        text = " ".join(runs)
        for entry in fixture.READING_QA:
            self.assertIn(entry["sentence"], text)          # every askable sentence is in the text layer, line breaks aside
        # the highlight is a filled rectangle drawn before the text of its line, only for the entries that ask for it
        self.assertEqual(data.count(b" re f"), 2)                           # the highlighted sentence runs over two lines
        self.assertTrue(fixture.READING_QA[0]["highlight"] and not any(e.get("highlight") for e in fixture.READING_QA[1:]))

    def test_it_quotes_nothing_from_the_paper_and_is_not_its_abstract(self):
        paper = next(p for p in fixture.PAPERS if p["arxiv_id"] == fixture.READING_ARXIV_ID)
        data = (ASSETS / fixture.READING_FILE).read_bytes().decode("latin-1")
        self.assertNotIn(paper["abstract"][:60], data)
        self.assertEqual(fixture.READING_KEY, fixture.key_of(paper))

    def test_the_assets_are_in_the_packaged_static_folder(self):
        # the desktop build adds the whole app/static folder, so app/static/demo travels with it
        build = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")
        self.assertIn("ROOT / 'app' / 'static'", build)
        self.assertEqual({p.name for p in ASSETS.iterdir()}, {fixture.READING_FILE, fixture.SAMPLE_BIB_FILE})

    def test_sample_library_is_three_new_papers_that_parse(self):
        from app import reference_files
        parsed = reference_files.parse("bibtex", (ASSETS / fixture.SAMPLE_BIB_FILE).read_bytes())
        self.assertEqual(parsed["errors"], [])
        ids = [e["arxiv"] for e in parsed["entries"]]
        self.assertEqual(ids, ["1803.02155", "1911.02150", "2106.09685"])
        self.assertFalse(set(ids) & {p["arxiv_id"] for p in fixture.PAPERS})   # none is one of the demo's own papers
        self.assertTrue(all(e["abstract"] and e["doi"].startswith("10.48550/arxiv.") for e in parsed["entries"]))


class MatchingTests(unittest.TestCase):
    def test_a_selection_across_lines_a_part_of_the_sentence_and_changed_case_all_match(self):
        self.assertEqual(demo.match_selection(S1)["id"], "self-attention")
        self.assertEqual(demo.match_selection("Self-attention lets every position look at every other position in a single step,\nso two distant words are connected")["id"], "self-attention")
        self.assertEqual(demo.match_selection("  MULTI-HEAD attention runs several small attention computations ")["id"], "heads")
        self.assertEqual(demo.match_selection("the model adds a position signal to every word")["id"], "position")
        # the sentence with some of its neighbours around it
        self.assertEqual(demo.match_selection("answers. " + S1 + " Because all positions are handled together")["id"], "self-attention")

    def test_anything_else_does_not_match(self):
        for text in ("", "   ", "Before 2017 the strongest systems for translating and modelling text", "self-attention", "position signal",
                     "Attention compares every position with every other one, so its cost grows", "completely unrelated words here"):
            self.assertIsNone(demo.match_selection(text), text)

    def test_translation_wants_the_whole_sentence(self):
        self.assertEqual(demo.match_selection(S2, strict=True)["id"], "position")
        self.assertIsNone(demo.match_selection("the model adds a position signal to every word", strict=True))
        self.assertEqual(demo.reading_translation(S3, english=False), fixture.READING_QA[2]["translation"])
        self.assertEqual(demo.reading_translation("some other text of the paper", english=True), fixture.READING_GENERIC["translation"]["en"])

    def test_the_question_decides_before_the_selection_and_every_followup_is_answerable(self):
        for entry in fixture.READING_QA:
            for lang, english in (("zh", False), ("en", True)):
                answer, followups = demo.reading_reply(None, entry["question"][lang], english)
                self.assertEqual(answer, entry["answer"][lang])
                self.assertEqual(len(followups), 2)
                for follow in followups:                    # a follow-up button leads to an answer of its own, not the general reply
                    self.assertNotEqual(demo.reading_reply(None, follow, english)[0], fixture.READING_GENERIC["answer"][lang])
        answer, _ = demo.reading_reply(S1, fixture.READING_QA[1]["question"]["zh"], False)
        self.assertEqual(answer, fixture.READING_QA[1]["answer"]["zh"])
        answer, followups = demo.reading_reply(S1, fixture.READING_GENERIC["default_question"]["en"], True)
        self.assertEqual(answer, fixture.READING_QA[0]["answer"]["en"])
        generic, followups = demo.reading_reply("some other text", "anything", False)
        self.assertEqual(generic, fixture.READING_GENERIC["answer"]["zh"]); self.assertEqual(len(followups), 3)

    def test_the_fixture_is_complete_in_both_languages(self):
        for entry in fixture.READING_QA:
            for field in ("question", "answer"):
                self.assertTrue(entry[field]["zh"].strip() and entry[field]["en"].strip(), (entry["id"], field))
            self.assertTrue(entry["translation"].strip())
            self.assertTrue(set(entry["followups"]) <= {e["id"] for e in fixture.READING_QA})
        for field in ("answer", "translation", "default_question"):
            self.assertTrue(fixture.READING_GENERIC[field]["zh"].strip() and fixture.READING_GENERIC[field]["en"].strip())


class DemoReadingTests(sandbox.DemoCase):
    def setUp(self):
        super().setUp()
        self.calls = Gateway.call   # the class-level mock of the base case: any model call raises and is counted
        self.set_language("zh-CN")
        self.start()

    def set_language(self, language):
        (self.data / "settings.json").write_text(json.dumps({"theme": "dark", "language": language}), encoding="utf-8")

    def counts(self):
        db = sqlite3.connect(str(self.data / "pagetide.sqlite"))
        try:
            return {t: db.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in TABLES
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()}
        finally:
            db.close()

    def reader_session(self):
        status, payload = self.call("GET", "/api/qa/session?key=%s&project_id=%s" % (KEY, demo.PROJECT_ID))
        self.assertEqual(status, 200, payload)
        return payload["session"]

    def prepared(self):
        status, payload = self.call("POST", "/api/pdf/prepare", {"key": KEY})
        self.assertEqual((status, payload["ok"]), (200, True), payload)
        return payload

    def ask(self, question, selection=None, **extra):
        body = {"key": KEY, "question": question, "selection": selection, "project_id": demo.PROJECT_ID,
                "session_id": self.reader_session()["id"], "reader_context": {"key": KEY, "project_id": demo.PROJECT_ID,
                                                                             "pdf_sha256": self.prepared()["sha256"], "kind": "pdf"}}
        body.update(extra)
        return self.call("POST", "/api/qa", body)

    # ------------------------------------------------------------------------------------------------ the PDF
    def test_the_reading_material_opens_through_the_real_routes_and_nothing_else_does(self):
        before = self.counts()
        prepared = self.prepared()
        data = (ASSETS / fixture.READING_FILE).read_bytes()
        self.assertEqual(prepared["sha256"], __import__("hashlib").sha256(data).hexdigest())
        # pdf.js sends no demo header: the address names the demo project
        status, raw = self.call("GET", "/api/pdf/view?key=%s&sha256=%s&project_id=%s" % (KEY, prepared["sha256"], demo.PROJECT_ID), header=False)
        self.assertEqual((status, raw), (200, data))
        other = fixture.key_of(fixture.candidates()[1])
        status, payload = self.call("POST", "/api/pdf/prepare", {"key": other})
        self.assertEqual((status, payload["ok"], payload["reason"]), (200, False, "demo_offline"))
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.real_counts().get("pdfs", 0), 0)

    def test_the_paper_is_a_candidate_with_a_local_pdf_and_is_in_todays_cards(self):
        status, daily = self.call("POST", "/api/daily", {"project_id": demo.PROJECT_ID})
        self.assertEqual(status, 200, daily)
        self.assertIn(KEY, [card["key"] for card in daily["cards"]])

    # ------------------------------------------------------------------------------------------------ asking
    def test_the_highlighted_sentence_gets_its_pre_written_answer_in_the_interface_language(self):
        before = self.counts()
        for language, lang in (("zh-CN", "zh"), ("en-US", "en")):
            self.set_language(language)
            status, reply = self.ask(fixture.READING_GENERIC["default_question"][lang], selection=S1)
            self.assertEqual(status, 200, reply)
            self.assertTrue(reply["ok"] and reply["demo"] and reply["model"] == "demo")
            self.assertEqual(reply["answer"], fixture.READING_QA[0]["answer"][lang])
            self.assertEqual(reply["followups"], [fixture.READING_QA[1]["question"][lang], fixture.READING_QA[2]["question"][lang]])
            self.assertEqual((reply["usd"], reply["usage"]), (0, None))
        self.calls.assert_not_called()
        after = self.counts()
        self.assertEqual({k: v for k, v in after.items() if k != "qa_history"}, {k: v for k, v in before.items() if k != "qa_history"})
        self.assertEqual(after["qa_history"], before["qa_history"])            # the real database got no question or answer
        self.assertEqual(self.real_counts().get("qa_history", 0), 0)

    def test_a_selection_across_two_lines_and_a_followup_without_a_selection_work(self):
        at = S1.index(" ", 60)
        text = S1[:at] + "\n" + S1[at + 1:]       # a line break where the PDF wraps
        status, reply = self.ask("这句话是什么意思？", selection=text)
        self.assertEqual(reply["answer"], fixture.READING_QA[0]["answer"]["zh"])
        status, reply = self.ask(fixture.READING_QA[2]["question"]["zh"])
        self.assertEqual(reply["answer"], fixture.READING_QA[2]["answer"]["zh"])
        self.calls.assert_not_called()

    def test_any_other_selection_gets_the_one_general_reply_that_says_it_is_pre_written(self):
        status, reply = self.ask("这句话是什么意思？", selection="Before 2017 the strongest systems for translating and modelling text")
        self.assertTrue(reply["ok"] and reply["demo"])
        self.assertEqual(reply["answer"], fixture.READING_GENERIC["answer"]["zh"])
        self.assertIn("预先写好", reply["answer"])
        self.assertEqual(len(reply["followups"]), 3)
        self.set_language("en-US")
        status, reply = self.ask("What does this mean?", selection="a")
        self.assertEqual(reply["answer"], fixture.READING_GENERIC["answer"]["en"])
        self.assertIn("pre-written", reply["answer"])
        self.calls.assert_not_called()

    def test_the_conversation_is_kept_in_the_sandbox_and_the_session_checks_still_apply(self):
        self.ask("这句话是什么意思？", selection=S2)
        status, payload = self.call("GET", "/api/qa?key=%s&project_id=%s" % (KEY, demo.PROJECT_ID))
        self.assertEqual([row["role"] for row in payload["history"]], ["user", "assistant"])
        self.assertEqual(payload["history"][1]["content"], fixture.READING_QA[1]["answer"]["zh"])
        status, payload = self.ask("q", selection=S1, session_id="not-the-session")
        self.assertEqual(status, 400); self.assertIn("会话", payload["error"])
        status, payload = self.ask("q", selection=S1, reader_context={"key": KEY, "project_id": demo.PROJECT_ID, "pdf_sha256": "0" * 64, "kind": "pdf"})
        self.assertEqual(status, 400)
        status, payload = self.call("POST", "/api/qa", {"key": KEY, "question": "q", "project_id": "nope"})
        self.assertEqual(status, 400); self.assertIn("不属于", payload["error"])

    def test_a_new_reading_session_starts_in_the_sandbox(self):
        status, payload = self.call("POST", "/api/qa/session", {"key": KEY, "project_id": demo.PROJECT_ID})
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["session"]["id"])

    def test_the_text_layer_is_stored_in_the_sandbox_only(self):
        status, payload = self.call("POST", "/api/fulltext", {"key": KEY, "pages": [{"page": 1, "text": S1}],
                                                               "source_pdf_sha256": self.prepared()["sha256"]})
        self.assertEqual(status, 200, payload)
        self.assertEqual(self.real_counts().get("fulltext", 0), 0)

    # ------------------------------------------------------------------------------------------------ translating
    def test_translation_is_pre_written_for_the_highlighted_sentence_and_general_otherwise(self):
        status, reply = self.call("POST", "/api/translate", {"text": S1})
        self.assertEqual(status, 200, reply)
        self.assertTrue(reply["ok"] and reply["demo"])
        self.assertEqual(reply["translation"], fixture.READING_QA[0]["translation"])
        status, reply = self.call("POST", "/api/translate", {"text": "Because all positions are handled together"})
        self.assertEqual(reply["translation"], fixture.READING_GENERIC["translation"]["zh"])
        self.set_language("en-US")
        status, reply = self.call("POST", "/api/translate", {"text": "Because all positions are handled together"})
        self.assertEqual(reply["translation"], fixture.READING_GENERIC["translation"]["en"])
        status, reply = self.call("POST", "/api/translate", {"text": "  "})
        self.assertFalse(reply["ok"])
        self.calls.assert_not_called()

    def test_the_demo_gateway_still_refuses_every_call(self):
        app = demo.open_app(str(self.root), str(self.data))
        try:
            with self.assertRaises(demo.DemoBlocked):
                app.gateway.call("paper_qa", [])
            self.assertTrue(app.qa(KEY, "q", S1)["demo"])
            self.assertTrue(app.translate(S1)["demo"])
        finally:
            app.store.close()


class DemoImportTests(sandbox.DemoCase):
    def upload(self, batch, data, name="sample-library.bib"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            conn.request("POST", "/api/import/batches/%s/sidecar" % batch, body=data,
                         headers={"Content-Type": "application/octet-stream", "X-Filename": name, demo.HEADER: "1"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def counts(self):
        return DemoReadingTests.counts(self)

    def test_the_real_import_runs_offline_on_the_sample_and_only_writes_the_sandbox(self):
        self.start()
        before = self.counts()
        sample = (ASSETS / fixture.SAMPLE_BIB_FILE).read_bytes()
        # the page's own request (online metadata on, no fileless records) is turned into the offline form
        status, batch = self.call("POST", "/api/import/batches", {"project_id": demo.PROJECT_ID, "source": "zotero", "root_name": "",
                                                                  "options": {"online": True, "include_fileless": False, "folder_categories": True}})
        self.assertEqual(status, 200, batch)
        self.assertFalse(batch["options"]["online"]); self.assertTrue(batch["options"]["include_fileless"])
        status, summary = self.upload(batch["id"], sample)
        self.assertEqual((status, summary["entries"], summary["errors_count"]), (200, 3, 0), summary)
        status, started = self.call("POST", "/api/import/batches/%s/resolve" % batch["id"], {})
        self.assertEqual((status, started["started"], started["worker_alive"]), (200, True, False))   # matched in the request, no worker thread
        status, detail = self.call("GET", "/api/import/batches/%s?limit=50" % batch["id"])
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["status"], "review")
        self.assertEqual(detail["counts"], {"matched": 3})
        self.assertEqual({i["paper"]["arxiv_id"] for i in detail["items"]}, {"1803.02155", "1911.02150", "2106.09685"})
        status, committed = self.call("POST", "/api/import/batches/%s/commit" % batch["id"], {})
        self.assertEqual(status, 200, committed)
        self.assertEqual((committed["result"]["new_papers"], committed["result"]["unresolved"]), (3, 0))
        status, library = self.call("GET", "/api/library?project_id=" + demo.PROJECT_ID)
        titles = [item["title"] for item in library["items"]]
        for title in ("Self-Attention with Relative Position Representations", "LoRA: Low-Rank Adaptation of Large Language Models"):
            self.assertIn(title, titles)
        self.assertEqual(len(titles), 22 + 3)
        self.assertEqual(self.counts(), before)          # the real database: not one row more, in any table that exists there
        self.assertEqual(self.real_counts().get("papers", 0), 1)
        sandbox_app = demo.open_app(str(self.root), str(self.data))
        try:
            self.assertEqual(sandbox_app.library_import.batch(batch["id"], limit=0)["status"], "committed")
        finally:
            sandbox_app.store.close()
        Gateway.call.assert_not_called()

    def test_the_demo_import_cannot_upload_a_pdf_or_set_seeds(self):
        self.start()
        status, batch = self.call("POST", "/api/import/batches", {"project_id": demo.PROJECT_ID, "source": "files"})
        self.assertEqual(status, 200, batch)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            conn.request("POST", "/api/import/batches/%s/pdf" % batch["id"], body=b"%PDF-1.4\n", headers={
                "Content-Type": "application/pdf", "X-Relative-Path": "a.pdf", demo.HEADER: "1"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403); response.read()
        finally:
            conn.close()
        status, payload = self.call("POST", "/api/import/batches/%s/seeds" % batch["id"], {"action": "add", "keys": []})
        self.assertEqual((status, payload["reason_code"]), (403, "demo_readonly"))

    def test_without_the_demo_header_a_real_project_import_is_unchanged(self):
        status, batch = self.call("POST", "/api/import/batches", {"project_id": self.real_pid, "source": "files",
                                                                  "options": {"online": True}}, header=False)
        self.assertEqual(status, 200, batch)
        self.assertTrue(batch["options"]["online"])                                  # not forced offline outside the demo

    def test_allowed_routes_are_exactly_the_sample_import(self):
        batch = "a" * 32
        for tail in ("sidecar", "resolve", "cancel", "commit", "discard", "settle", "categories", "items/12"):
            self.assertTrue(demo.allowed("POST", "/api/import/batches/%s/%s" % (batch, tail)), tail)
        for tail in ("pdf", "seeds", "items/x", "../x", "resolve/extra"):
            self.assertFalse(demo.allowed("POST", "/api/import/batches/%s/%s" % (batch, tail)), tail)
        self.assertFalse(demo.allowed("POST", "/api/import/batches/short/commit"))
        self.assertTrue(demo.allowed("POST", "/api/import/batches")); self.assertTrue(demo.allowed("GET", "/api/import/batches/" + batch))
        self.assertFalse(demo.allowed("POST", "/api/seeds/pdf")); self.assertFalse(demo.allowed("POST", "/api/pdf"))
        self.assertEqual(demo.import_options(None), {"online": False, "include_fileless": True})


class BaiduScholarNotOfferedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)

    def write(self, **values):
        (self.data / "settings.json").write_text(json.dumps(values), encoding="utf-8")

    def test_a_stored_switch_is_ignored(self):
        self.assertFalse(user_settings.BAIDU_SCHOLAR_OFFERED)
        self.write(sourceBaiduScholar=True, sourceBaiduWeb=True)
        self.assertFalse(user_settings.baidu_scholar(self.data))
        self.assertTrue(user_settings.baidu_web(self.data))             # the Baidu search is a separate switch and is untouched
        self.assertEqual(json.loads((self.data / "settings.json").read_text())["sourceBaiduScholar"], True)   # stored data is not deleted

    def test_a_paper_only_baidu_scholar_reported_is_not_allowed_by_the_stored_switch(self):
        self.write(sourceArxiv=False, sourceOpenAlex=False, sourceBaiduScholar=True)
        paper = {"key": "baidu:x1", "title": "t"}
        self.assertFalse(user_settings.source_allowed(self.data, paper))
        policy = user_settings.source_policy(self.data)
        self.assertFalse(policy.baidu)
        self.assertTrue(SourcePolicy(False, False, True).allows(paper))   # the rule itself is unchanged; only the switch is gone

    def test_the_refresh_does_not_ask_baidu_scholar_for_a_stored_switch(self):
        self.write(sourceBaiduScholar=True, sourceBaiduWeb=False)
        import inspect
        from app import service
        source = inspect.getsource(service.App)
        self.assertIn('("baidu_scholar", user_settings.baidu_scholar(self.data)', source)   # the call site reads the gated switch
        self.assertFalse(user_settings.baidu_scholar(self.data))

    def test_saving_without_the_field_keeps_every_other_setting(self):
        saved = {"language": "en-US", "theme": "dark", "recommendCount": 7, "sourceBaiduWeb": True, "baiduScholarConfirmed": True}
        self.assertEqual(user_settings.validate(dict(saved)), saved)
        self.assertEqual(user_settings.validate({**saved, "sourceBaiduScholar": False}), {**saved, "sourceBaiduScholar": False})   # an old client still validates
        with self.assertRaises(ValueError):
            user_settings.validate({"sourceBaiduScholar": "yes"})


if __name__ == "__main__":
    unittest.main()
