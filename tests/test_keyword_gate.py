"""No relation, no paper (owner, 2026-10-26): a paper is stored by a fetch and recommended only when it mentions one of the
project's terms (its keywords, and with a learning map its concepts' terms). The case that started it is a real one: a
"国际中文教育" project was recommended 《新质生产力背景下企业人才发展机制研究》 at rank 1."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import keyword_gate  # noqa: E402
from app.keyword_gate import Gate  # noqa: E402

ZH = ["国际中文教育", "语法教学", "二语习得", "教学法", "汉语语法"]
REPORTED = {"key": "https://doi.org/10.33142/mem.v7i5.20540", "title": "新质生产力背景下企业人才发展机制研究",
            "abstract": "新质生产力是以科技创新为动力源、以高质量发展为取向的先进生产力形态……对企业的人才发展机制存在的结构性短板进行分析，"
                        "从引育并举和产业需求对接、多元化评价和差异化激励、职业发展和晋升通道拓宽、人才和技术创新协同发展四个方面提出优化策略。"}


class MatchingTests(unittest.TestCase):
    def test_the_reported_paper_mentions_no_keyword_and_is_dropped(self):
        self.assertFalse(Gate(ZH).matches(REPORTED))

    def test_a_chinese_keyword_matches_only_as_one_phrase(self):
        gate = Gate(["语法教学"])
        self.assertTrue(gate.matches({"title": "国际中文教育中的语法教学研究"}))
        self.assertTrue(gate.matches({"title": "语法 教学的新路径"}))              # spaces inside are ignored
        self.assertFalse(gate.matches({"title": "教学语法与语言学"}))              # the same characters, another order
        self.assertFalse(gate.matches({"title": "语言教学中的法律问题"}))          # single characters are not enough

    def test_mixed_terms_like_si_epitaxy(self):
        gate = Gate(["Si 同质外延", "CVD 外延"])
        self.assertTrue(gate.matches({"abstract": "本文研究了Si同质外延的缺陷"}))
        self.assertFalse(gate.matches({"abstract": "化学气相沉积制备石墨烯"}))

    def test_an_english_term_needs_every_word_in_any_form(self):
        gate = Gate(["world models", "model-based reinforcement learning"])
        self.assertTrue(gate.matches({"title": "Learning a World Model for robots"}))
        self.assertTrue(gate.matches({"abstract": "a model based approach to reinforcement learning"}))
        self.assertFalse(gate.matches({"title": "World cup forecasting"}))
        self.assertFalse(gate.matches({"title": "Reinforcement learning for games"}))   # misses "model"

    def test_common_english_word_forms_are_one_word(self):
        for term, text in (("modelling", "a model of"), ("model", "modelling the sea"), ("analysis", "three analyses"),
                           ("learning", "learned policies"), ("networks", "a network"), ("studies", "a case study")):
            self.assertTrue(Gate([term]).matches({"title": text}), (term, text))
        self.assertFalse(Gate(["mouse"]).matches({"title": "mice"}))            # irregular forms are not guessed

    def test_an_english_paper_never_matches_a_project_with_only_chinese_terms(self):
        self.assertFalse(Gate(ZH).matches({"title": "Grammar teaching in Chinese as a second language"}))

    def test_case_and_width_do_not_matter(self):
        self.assertTrue(Gate(["LLM"]).matches({"title": "ｌｌｍ agents"}))

    def test_cnki_keywords_count_but_an_openalex_topic_does_not(self):
        gate = Gate(["二语习得"])
        self.assertTrue(gate.matches({"key": "cnki:CJFD:X1", "title": "补语研究", "topic": "二语习得"}))
        self.assertFalse(gate.matches({"key": "https://doi.org/x", "title": "补语研究", "topic": "二语习得"}))

    def test_no_terms_means_no_gate(self):
        self.assertTrue(Gate([]).matches({"title": "anything"}))
        self.assertFalse(Gate([]).active)

    def test_learning_map_terms_count_as_relation(self):
        route = {"graph": {"concepts": [{"id": "c1", "name": "偏误分析", "terms": ["偏误分析", "error analysis"]}]}}
        gate = Gate(ZH + keyword_gate.route_terms(route))
        self.assertTrue(gate.matches({"title": "留学生偏误分析"}))
        self.assertEqual(keyword_gate.route_terms(None), [])


class ServiceTests(unittest.TestCase):
    """Wiring: the fetch does not store an unrelated paper, and one already stored is never recommended."""

    def setUp(self):
        from app import server
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "app").mkdir()
        (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        self.app = server.make_app(str(root))
        self.addCleanup(self.app.store.close)
        self.pid = self.app.projects.create_project("国际中文教育", "manual", ZH)
        if isinstance(self.pid, dict):
            self.pid = self.pid.get("id") or self.pid.get("project_id")
        self.app.set_project_language(self.pid, "humanities", ["zh"])

    def add(self, key, title, abstract):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": "2026-10-20",
                                       "source": "t", "group": "field", "project_id": self.pid}])
        self.app.store.conn.execute("UPDATE papers SET oa_json=? WHERE key=?",   # a PDF source, so only the keyword rule decides
                                    (json.dumps({"is_oa": True, "pdf_urls": ["https://example.org/a.pdf"]}), key))
        self.app.store.conn.commit()

    def test_a_stored_unrelated_paper_is_not_recommendable(self):
        self.add(REPORTED["key"], REPORTED["title"], REPORTED["abstract"])
        self.add("https://doi.org/related", "国际中文教育语法教学的课堂设计", "本文讨论国际中文教育中的语法教学。" * 3)
        reasons = {p["key"]: p["_eligibility"].get("reason") for p in self.app.recommendation_pool(self.pid)}
        self.assertEqual(reasons[REPORTED["key"]], "no_keyword_match")
        self.assertNotEqual(reasons["https://doi.org/related"], "no_keyword_match")

    def test_the_daily_fetch_does_not_store_an_unrelated_paper(self):
        class Source:
            api_key = "k"
            rejected_publications = []

            def discover_topic(self, keyword, **kwargs):
                return [{**REPORTED, "published": "2026-10-20", "source": "t", "group": "field"},
                        {"key": "https://doi.org/related", "title": "二语习得视角下的汉语语法", "abstract": "汉语语法", "published": "2026-10-20",
                         "source": "t", "group": "field"}]
        self.app.source = Source()
        out = self.app.refresh_candidates(project_id=self.pid)
        keys = {r[0] for r in self.app.store.conn.execute("SELECT paper_key FROM project_papers WHERE project_id=?", (self.pid,))}
        self.assertIn("https://doi.org/related", keys)
        self.assertNotIn(REPORTED["key"], keys)
        self.assertEqual(out.get("unrelated"), 1)


if __name__ == "__main__":
    unittest.main()
