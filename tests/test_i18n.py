"""Interface language: settings.json "language" switches the UI pack, server prose and AI reply language."""
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import server
from app.language import language
from app.organization_facets import suggest_groups
from app.service import App
import i18n_extract

HAN = re.compile(r"[㐀-鿿]")


def set_language(data_dir, value):
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    (Path(data_dir) / "settings.json").write_text(json.dumps({"language": value}))


class LanguageSettingTests(unittest.TestCase):
    def test_only_a_supported_choice_switches_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(language(tmp), "zh-CN")   # no settings file
            for raw, expected in [('{"language": "en-US"}', "en-US"), ('{"language": "fr-FR"}', "zh-CN"),
                                  ('{"theme": "dark"}', "zh-CN"), ("not json", "zh-CN"),
                                  ('["en-US"]', "zh-CN"), ('{"language": ["en-US"]}', "zh-CN")]:
                (Path(tmp) / "settings.json").write_text(raw)
                self.assertEqual(language(tmp), expected, raw)


class EnglishServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=str(ROOT), data_dir=Path(self.tmp.name) / "app")

    def capture(self):
        seen = []

        def fake(operation, messages, **kwargs):
            seen.append((operation, messages))
            return {"ok": False, "reason": "stub"}
        return seen, patch.object(self.app.gateway, "call", side_effect=fake)

    def test_qa_triage_and_guidance_ask_for_english_only_in_english(self):
        self.app.store.upsert_papers([{"key": "p1", "title": "World models", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        session = self.app.create_guidance_session("WM", "world model planning")
        replies = {}
        for lang in ("zh-CN", "en-US"):
            set_language(self.app.data, lang)
            self.assertEqual(self.app.english(), lang == "en-US")
            seen, stub = self.capture()
            with stub:
                self.app.qa("p1", "what is this?")
                self.app.triage([{"key": "p1", "title": "World models", "abstract": "a"}])
                replies[lang] = self.app.guidance_turn(session["id"], "robotics")["reply"]
            prompts = {op: json.dumps(messages, ensure_ascii=False) for op, messages in seen}
            self.assertEqual(set(prompts), {"paper_qa", "daily_triage", "project_guidance"})
            qa_system = seen[0][1][0]["content"]
            if lang == "zh-CN":
                # The Chinese prompts are unchanged by the English option.
                self.assertEqual(qa_system, App.QA_SYSTEM)
                for text in prompts.values():
                    self.assertNotIn(App.ENGLISH_OUTPUT, text)
            else:
                self.assertEqual(qa_system, App.QA_SYSTEM_EN + App.ENGLISH_OUTPUT)
                for text in prompts.values():
                    self.assertIn("English", text)
            if lang == "en-US":
                # Instructions stay ahead of the untrusted candidate text.
                triage = prompts["daily_triage"]
                self.assertLess(triage.index("English"), triage.index("候选："))
        # A refused model call falls back to local guidance, written in the interface language.
        self.assertTrue(HAN.search(replies["zh-CN"]))
        self.assertFalse(HAN.search(replies["en-US"]), replies["en-US"])

    def test_english_counts_use_the_singular_for_one(self):
        self.app.store.upsert_papers([{"key": "p1", "title": "World models", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        set_language(self.app.data, "en-US")
        reason = self.app.build_batch(limit=5)["shortfall"]["reason"]
        self.assertIn("Only 1 paper in the project pool is neither", reason)

    def test_explanations_follow_the_interface_language(self):
        self.app.store.upsert_papers([{"key": "ref1", "title": "World Model Planning with JEPA",
                                       "abstract": "latent prediction and planning for robotics",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.store.save_to_library("ref1")
        paper = {"title": "Zero-shot planning with a world model",
                 "abstract": "latent prediction enables planning", "topic": "Robotics"}
        self.assertIn("领域：Robotics", self.app.explain(paper)["why"])
        set_language(self.app.data, "en-US")
        explanation = self.app.explain(paper)
        self.assertIn("Field: Robotics", explanation["why"])
        self.assertIn("the saved “World Model Planning with JEPA”", explanation["nearest_reference"])
        self.assertFalse(HAN.search(explanation["why"]), explanation["why"])


class EnglishSuggestionTests(unittest.TestCase):
    PAPERS = [
        {"key": f"w{i}", "title": f"World Action Model {name}", "abstract": "A world model.", "topic": "Robotics"}
        for i, name in enumerate(["for Manipulation", "Pretraining", "Benchmarks"])
    ] + [{"key": "o", "title": "Protein Folding", "abstract": "Structure.", "topic": "Biology"}]

    def test_names_and_reasons_are_english_without_the_chinese_glossary(self):
        chinese = suggest_groups(self.PAPERS, {"pinned": ["world models"]})
        english = suggest_groups(self.PAPERS, {"pinned": ["world models"], "language": "en-US"})
        self.assertIn("世界模型", [g["name"] for g in chinese["groups"]])
        self.assertIn("world models", [g["name"] for g in english["groups"]])
        for group in english["groups"]:
            self.assertFalse(HAN.search(group["name"] + group["reason"]), group)


class LanguageDataDirTests(unittest.TestCase):
    def test_settings_and_the_app_read_one_directory(self):
        # Review finding: with no PAPERDIGHELPER_DATA, the language route read <cwd>/.local/app
        # while App(root) read <root>/.local/app, so the UI and the prompts could disagree.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PAPERDIGHELPER_DATA", None)
            (Path(tmp) / "harness").mkdir()
            (Path(tmp) / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
            self.assertEqual(Path(server.data_dir(tmp)), App(root=tmp).data)
            os.environ["PAPERDIGHELPER_DATA"] = str(Path(tmp) / "elsewhere")
            self.assertEqual(Path(server.data_dir(tmp)), App(root=tmp, data_dir=os.environ["PAPERDIGHELPER_DATA"]).data)


class UserTextMarkupTests(unittest.TestCase):
    # Review finding: AI summaries, titles, abstracts and quotes were walked by the language
    # layer. The page marks them data-no-i18n; the labels around them stay translatable.
    def test_paper_and_model_text_is_marked_untranslated(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        for marked in ["<span data-no-i18n>${esc(c.summary.one_liner || '')}</span>",
                       "相关：</span><span data-no-i18n>${esc(c.summary.why_relevant)}</span>",
                       "<span data-no-i18n>${md(s.one_liner || '')}</span>",
                       "相关：</span><span data-no-i18n>${esc(s.why_relevant || '')}</span>",
                       "注意：</span><span data-no-i18n>${esc(s.caution)}</span>",
                       '<button class="paper-title" data-no-i18n>',
                       "<h2 data-no-i18n>${esc(d.title)}</h2>", "<div data-no-i18n>${md(d.abstract)}</div>",
                       "quoted.dataset.noI18n = ''", "PDHi18n.exact(q)"]:
            self.assertIn(marked, html)
        script = (ROOT / "app" / "static" / "i18n.js").read_text(encoding="utf-8")
        for container in [".org-markdown", ".org-detail-title", ".org-abstract p", "pre"]:
            self.assertIn(container, script)


class LanguagePackTests(unittest.TestCase):
    def test_every_interface_string_has_an_english_entry(self):
        self.assertEqual(i18n_extract.missing(), {})

    def test_pack_values_are_english_and_keep_their_placeholders(self):
        messages = json.loads((ROOT / "app" / "static" / "i18n" / "en-US.json").read_text())["messages"]
        for key, value in messages.items():
            values = value if isinstance(value, list) else [value]
            self.assertTrue(isinstance(value, str) or len(value) == 2, key)
            for text in values:
                self.assertIsInstance(text, str, key)
                self.assertFalse(HAN.search(text), (key, text))
                self.assertLessEqual(set(re.findall(r"\{\d+\}", text)), set(re.findall(r"\{\d+\}", key)), key)

    def test_script_carries_messages_only_in_english(self):
        chinese = server.i18n_script("zh-CN").decode()
        self.assertEqual(chinese, 'window.PDH_I18N={"lang": "zh-CN", "messages": {}};\n')
        english = server.i18n_script("en-US").decode()
        payload = json.loads(english[len("window.PDH_I18N="):-2].replace("<\\/", "</"))
        self.assertEqual(payload["lang"], "en-US")
        self.assertEqual(payload["messages"]["论文库"], "Library")
        self.assertNotIn("</", english)   # a pack value can never close the page's script element

    def test_broken_pack_falls_back_to_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "i18n").mkdir()
            (Path(tmp) / "i18n" / "en-US.json").write_text("{broken")
            with patch.object(server, "STATIC", Path(tmp)):
                self.assertIn('"lang": "zh-CN"', server.i18n_script("en-US").decode())


class LanguageRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.data = root / "data"
        env = patch.dict(os.environ, {"PAPERDIGHELPER_DATA": str(self.data)})
        env.start()
        self.addCleanup(env.stop)
        self.httpd = server.build_server(port=0, root=str(root))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def request(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode()

    def test_pages_load_the_pack_for_the_saved_language(self):
        for page in ("/", "/settings.html", "/weekly_report.html", "/project_creation.html"):
            html = self.request(page)
            self.assertRegex(html, r"<head[^>]*><script src=\"/i18n/current\.js[^\"]*\"></script>"
                                   r"<script src=\"/i18n\.js[^\"]*\"></script>", page)
        self.assertIn('"lang": "zh-CN"', self.request("/i18n/current.js"))
        self.request("/api/user_settings", {"settings": {"language": "en-US"}})
        self.assertIn('"lang": "en-US"', self.request("/i18n/current.js"))

    def test_weekly_analysis_is_written_in_the_interface_language(self):
        project = json.loads(self.request("/api/projects"))
        project_id = (project.get("projects") or project)[0]["id"]
        chinese = json.loads(self.request("/api/weekly_report/analysis", {"project_id": project_id}))
        self.assertTrue(HAN.search(chinese["analysis"]))
        set_language(self.data, "en-US")
        english = json.loads(self.request("/api/weekly_report/analysis", {"project_id": project_id}))
        self.assertIn("no change of interest is inferred", english["analysis"])
        self.assertFalse(HAN.search(english["analysis"]), english["analysis"])

    def test_english_weekly_analysis_uses_the_singular_for_one(self):
        project = json.loads(self.request("/api/projects"))
        project_id = (project.get("projects") or project)[0]["id"]
        set_language(self.data, "en-US")
        report = {"has_activity": True, "stats": {"activity": 1, "saved": 0, "negative": 0, "too_hard": 0}}
        with patch("app.weekly_report.generate_weekly_report", return_value=report):
            english = json.loads(self.request("/api/weekly_report/analysis", {"project_id": project_id}))
        self.assertTrue(english["analysis"].startswith("1 activity recorded this week."), english["analysis"])


if __name__ == "__main__":
    unittest.main()
