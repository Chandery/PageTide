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
        (root / "app").mkdir(exist_ok=True)
        (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        self.app = App(root=str(root), data_dir=str(root / "data"))
        legacy_recommendation_settings(self.app)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("古汉语", "manual", ["汉语", "world model"])["project_id"]
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
        self.assertEqual(reasons["p"], "title_language_unverified")
        self.assertIsNone(reasons["english"])
        self.assertEqual(self.batch_keys(), {"english"})

    def test_an_english_abstract_keeps_the_old_title_gate(self):
        self.add("p", abstract=EN_ABSTRACT)
        self.assertEqual(self.reasons()["p"], "title_language_unverified")



class BilingualTitleTests(unittest.TestCase):
    ONE = ("汉字音源意境溯源体系:六级溯源模型 ⸺ 本土汉字造字发生学新探索|Sound-Source and Contextual Origin System of "
           "Chinese Characters: The Six-Level Tracing Model and a New Exploration of Native Character Genesis")
    TWO = "21世纪以来汉语语气副词研究综述 : A Review of the Research on Chinese Modal Adverbs since the 21st Century"
    CN = "本文综述汉语语气副词的研究现状，并讨论今后的研究方向与存在的问题。"
    EN = EN_ABSTRACT

    def zh(self, title, abstract=None):
        from app.paper_language import chinese_text_language
        return chinese_text_language(title, abstract)

    def test_the_first_segment_of_a_bilingual_title_decides(self):
        for title in (self.ONE, self.TWO):
            for abstract in (None, "", self.CN):
                with self.subTest(title=title[:12], abstract=abstract):
                    self.assertEqual(self.zh(title, abstract), "zh")
        for sep in ("|", " ⸺ ", "——", " - ", " – ", "：", ":"):
            self.assertEqual(self.zh("汉语语气副词研究综述" + sep + "A review of modal adverbs in Chinese", None), "zh", sep)

    def test_it_stays_not_chinese_when_it_should(self):
        self.assertIsNone(self.zh(self.TWO, self.EN))
        self.assertIsNone(self.zh("A Review of Modal Adverbs: 汉语语气副词研究综述", None))
        self.assertIsNone(self.zh("麒麟、祖剌法与キリン | A study of the Qilin", None))
        self.assertIsNone(self.zh("汉语语气副词研究 | 日本語の要旨", None))   # rest is not mostly Latin, whole title is not majority Han
        self.assertIsNone(self.zh("汉语 | A review of modal adverbs in Chinese", None))   # only 2 Han in the segment

    def test_a_title_that_already_passes_is_unchanged(self):
        self.assertEqual(self.zh("知识图谱构建方法综述", None), "zh")
        self.assertEqual(self.zh("知识图谱构建方法综述 | Survey", self.CN), "zh")

    def test_both_service_paths_use_it(self):
        for key, report, source in (("none", None, "title+abstract"), ("en", "en", "chinese_text_over_metadata")):
            paper = {"title": self.TWO, "abstract": self.CN, "metadata_language": report,
                     "metadata_language_source": "OpenAlex" if report else None}
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            root = Path(tmp.name)
            (root / "harness").mkdir()
            (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
            (root / "app").mkdir(exist_ok=True)
            (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
            app = App(root=str(root), data_dir=str(root / "data"))
            self.addCleanup(app.store.close)
            language = app._paper_language(paper)
            self.assertEqual(language["metadata_language"], "zh", key)
            self.assertEqual(language["metadata_source"], source, key)


QUOTING = ("This paper re-reads the chapter on human nature in Mencius, quoting 性善 and 四端 and 仁义礼智 and 恻隐之心 "
           "and 羞恶之心 beside Western readings of virtue, and argues that the usual translations miss the argument.")
MENCIUS = "《孟子》性善说新解 : A New Interpretation of Mencius"


class StricterOverrideTests(Base):
    def test_an_english_abstract_quoting_chinese_does_not_override_an_en_report(self):
        from app.paper_language import chinese_text_language
        self.assertEqual(chinese_text_language(MENCIUS, QUOTING), "zh")          # the no-report path keeps the tenth rule
        self.add("m", title=MENCIUS, abstract=QUOTING)
        language = self.app._paper_language(self.app._recommendation_rows(paper_key="m")[0])
        self.assertEqual((language["metadata_language"], language["metadata_source"]), ("en", "OpenAlex"))
        self.add("none", language=None, title=MENCIUS, abstract=QUOTING)
        language = self.app._paper_language(self.app._recommendation_rows(paper_key="none")[0])
        self.assertEqual((language["metadata_language"], language["metadata_source"]), ("zh", "title+abstract"))

    def test_a_majority_chinese_or_missing_abstract_still_overrides(self):
        self.add("a", title=MENCIUS, abstract=ABSTRACT)
        self.add("b", title=MENCIUS, abstract=None)
        for key in ("a", "b"):
            language = self.app._paper_language(self.app._recommendation_rows(paper_key=key)[0])
            self.assertEqual(language["metadata_source"], "chinese_text_over_metadata", key)


class BilingualEndToEndTests(Base):
    TITLE = "21世纪以来汉语语气副词研究综述 : A Review of the Research on Chinese Modal Adverbs since the 21st Century"

    def test_a_bilingual_title_with_an_en_report_is_eligible_in_a_chinese_project(self):
        self.add("p", title=self.TITLE)
        self.assertIsNone(self.reasons()["p"])
        self.assertEqual(self.batch_keys(), {"p"})


class BilingualEnglishOnlyTests(Base):
    allowed = ["en"]

    def test_the_same_paper_waits_for_pdf_verification_in_an_english_project(self):
        self.add("p", title=BilingualEndToEndTests.TITLE)
        self.assertEqual(self.reasons()["p"], "title_language_unverified")
        self.assertEqual(self.batch_keys(), set())
        language = self.app._paper_language(self.app._recommendation_rows(paper_key="p")[0])
        from app import eligibility
        result = eligibility.evaluate({"status": "ready", "allowed_languages": ["en"]}, {"title": BilingualEndToEndTests.TITLE, "abstract": ABSTRACT, "oa": SYNTHETIC_OA}, language)
        self.assertTrue(result["language"]["title_metadata_conflict"])

    def test_verifying_the_pdf_as_english_rescues_it(self):
        from app import eligibility
        paper = {"key": "p", "title": BilingualEndToEndTests.TITLE, "abstract": ABSTRACT, "metadata_language": "en",
                 "metadata_language_source": "OpenAlex", "verified_language": "en", "verified_method": "text",
                 "current_pdf_sha256": "abc", "oa": SYNTHETIC_OA}
        language = self.app._paper_language(paper, digest="abc")
        self.assertTrue(eligibility.evaluate({"status": "ready", "allowed_languages": ["en"]}, paper, language)["eligible"])


if __name__ == "__main__":
    unittest.main()
