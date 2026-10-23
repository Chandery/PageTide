"""OpenAlex often labels Chinese works "en". A clearly Chinese title and abstract overrides only that "en" report.

Local, conservative and never stored: other reported languages, kana/hangul text, English abstracts and a verified
full-text language are untouched. An English-only project still never receives such a paper.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import SYNTHETIC_OA, legacy_recommendation_settings
from app.service import App

TITLE = "ChatGPT辅助汉语二语写作反馈研究"
ABSTRACT = "本文研究生成式人工智能辅助汉语二语写作反馈的效果，并讨论教学中的应用方式与存在的问题。"
EN_ABSTRACT = ("We present a general method for learning world models from video, and we show that the model can be used "
               "for planning in a range of robotic manipulation tasks with a small amount of data.")


class Base(unittest.TestCase):
    allowed = ["zh"]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(root), data_dir=str(root / "data"))
        legacy_recommendation_settings(self.app)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("古汉语", "manual", ["汉语"])["project_id"]
        self.app.set_project_language(self.pid, None, self.allowed)

    def add(self, key, language="en", title=TITLE, abstract=ABSTRACT):
        extra = {"language": language, "metadata_language_source": "OpenAlex"} if language else {}
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": "2026-01-01",
                                       "oa": SYNTHETIC_OA, **extra}], project_id=self.pid)

    def reasons(self):
        return {p["key"]: p["_eligibility"]["reason"] for p in self.app.recommendation_pool(self.pid)}

    def batch_keys(self):
        return {c["key"] for c in self.app.build_batch(limit=5, project_id=self.pid)["cards"]}


class ChineseProjectTests(Base):
    def test_chinese_text_overrides_an_english_report_and_is_recommended(self):
        self.add("p")
        self.assertIsNone(self.reasons()["p"])
        self.assertEqual(self.batch_keys(), {"p"})

    def test_the_language_source_is_honest_and_nothing_is_stored(self):
        self.add("p")
        language = self.app._paper_language(self.app._recommendation_rows(paper_key="p")[0])
        self.assertEqual((language["metadata_language"], language["metadata_source"]), ("zh", "chinese_text_over_metadata"))
        self.assertFalse(language["title_metadata_conflict"])
        row = self.app.store.conn.execute("SELECT metadata_language, metadata_language_source FROM papers WHERE key='p'").fetchone()
        self.assertEqual(tuple(row), ("en", "OpenAlex"))

    def test_only_an_en_report_is_overridden(self):
        self.add("fr", language="fr")
        self.add("ja", language="ja")
        self.assertEqual(self.reasons(), {"fr": "language_not_allowed", "ja": "language_not_allowed"})
        for key in ("fr", "ja"):
            language = self.app._paper_language(self.app._recommendation_rows(paper_key=key)[0])
            self.assertEqual(language["metadata_source"], "OpenAlex")

    def test_japanese_or_korean_text_and_english_abstracts_are_not_overridden(self):
        self.add("kana", title="汉语二语写作反馈の研究について", abstract="日本語の要旨です。ひらがなとカタカナを含みます。")
        self.add("english_abstract", abstract=EN_ABSTRACT)
        self.add("latin", title="Chinese second language writing feedback", abstract=EN_ABSTRACT)
        reasons = self.reasons()
        self.assertEqual(reasons["latin"], "language_not_allowed")
        self.assertEqual(reasons["english_abstract"], "language_not_allowed")
        self.assertEqual(reasons["kana"], "language_not_allowed")

    def test_a_verified_full_text_language_wins(self):
        paper = {"key": "p", "title": TITLE, "abstract": ABSTRACT, "metadata_language": "en",
                 "metadata_language_source": "OpenAlex", "verified_language": "en", "verified_method": "text",
                 "current_pdf_sha256": "abc"}
        language = self.app._paper_language(paper, digest="abc")
        self.assertEqual(language["fulltext_language"], "en")
        from app import eligibility
        result = eligibility.evaluate({"status": "ready", "allowed_languages": ["zh"]}, {**paper, "oa": SYNTHETIC_OA}, language)
        self.assertEqual(result["reason"], "language_not_allowed")


class EnglishOnlyProjectTests(Base):
    allowed = ["en"]

    def test_such_a_paper_is_still_not_recommended(self):
        self.add("p")
        self.add("english", language="en", title="World models for robotic planning", abstract=EN_ABSTRACT)
        reasons = self.reasons()
        self.assertEqual(reasons["p"], "language_not_allowed")
        self.assertIsNone(reasons["english"])
        self.assertEqual(self.batch_keys(), {"english"})

    def test_an_english_abstract_keeps_the_old_title_gate(self):
        self.add("p", abstract=EN_ABSTRACT)
        self.assertEqual(self.reasons()["p"], "title_language_unverified")


if __name__ == "__main__":
    unittest.main()
