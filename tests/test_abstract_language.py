"""A paper whose source reported no language counts as English when its abstract is clearly English (owner, 2026-10-22).

OpenAlex reports no language for most arXiv preprints, so an English-only project excluded nearly every new preprint as
"language unknown". The fallback is local and conservative: it only fills a missing report, never overrides one, and is
not stored. A Chinese title on an English-looking abstract is still caught by the existing title-script check.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import SYNTHETIC_OA, legacy_recommendation_settings
from app import paper_language
from app.service import App

EN = ("We present a general method for learning world models from video, and we show that the model can be used "
      "for planning in a range of robotic manipulation tasks with a small amount of data.")
FR = ("Nous présentons une méthode générale pour apprendre des modèles du monde à partir de vidéos, et nous montrons "
      "que le modèle peut être utilisé pour la planification dans plusieurs tâches de manipulation robotique.")
ZH = "我们提出一种从视频中学习世界模型的通用方法，并展示该模型可以用于多种机器人操作任务的规划，所需数据很少。"


class DetectorTests(unittest.TestCase):
    def test_a_clear_english_abstract_is_english(self):
        self.assertEqual(paper_language.abstract_language(EN), "en")

    def test_other_languages_short_text_and_nothing_stay_unknown(self):
        for text in (FR, ZH, "World models for planning.", "", None, "n/a"):
            with self.subTest(text=text):
                self.assertIsNone(paper_language.abstract_language(text))


class EligibilityTests(unittest.TestCase):
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
        self.pid = self.app.create_project("World models", "manual", ["world models"])["project_id"]
        self.app.set_project_language(self.pid, "stem", ["en"])

    def add(self, key, abstract, title="World models for robotic planning", **extra):
        # no `language` field: the source reported none, exactly as OpenAlex does for most arXiv preprints
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": "2026-01-01",
                                       "oa": SYNTHETIC_OA, **extra}], project_id=self.pid)

    def reasons(self):
        return {p["key"]: p["_eligibility"]["reason"] for p in self.app.recommendation_pool(self.pid)}

    def test_an_unreported_paper_with_an_english_abstract_is_recommended(self):
        self.add("en", EN)
        self.add("fr", FR)
        self.add("zh", ZH)
        reasons = self.reasons()
        self.assertIsNone(reasons["en"])
        self.assertEqual(reasons["fr"], "language_unknown")
        self.assertEqual(reasons["zh"], "language_unknown")
        self.assertEqual({c["key"] for c in self.app.build_batch(limit=5, project_id=self.pid)["cards"]}, {"en"})

    def test_a_reported_language_is_never_overridden(self):
        self.add("reported_zh", EN, language="zh")
        self.assertEqual(self.reasons()["reported_zh"], "language_not_allowed")

    def test_a_chinese_title_on_an_english_abstract_is_still_held_back(self):
        self.add("title", EN, title="世界模型研究方法与视频预测")
        self.assertEqual(self.reasons()["title"], "title_language_unverified")

    def test_nothing_is_written_back(self):
        self.add("en", EN)
        self.reasons()
        row = self.app.store.conn.execute("SELECT metadata_language FROM papers WHERE key='en'").fetchone()
        self.assertIsNone(row[0])


if __name__ == "__main__":
    unittest.main()
