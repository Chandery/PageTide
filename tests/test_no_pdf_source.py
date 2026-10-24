"""A paper with no PDF source is never recommended, even when it has an abstract.

"PDF source" means any legal way to get the PDF: an arXiv id, an https PDF link reported by the source, an open-access
landing page, or a PDF already stored on this computer. The paper stays in the project; it only is not offered.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import english_papers, legacy_recommendation_settings
from app import eligibility
from app.service import App

ABSTRACT = "A real abstract about crystal lattice growth."
PLAN = {"concepts": [{"id": "a", "name": "Crystal basics", "terms": ["crystal lattice"], "hint": 1, "needs": []}], "targets": ["a"]}
DIRECT = {"pdf_urls": ["https://example.org/a.pdf"], "landing_page": None}
PAGE = {"pdf_urls": [], "landing_page": "https://example.org/landing"}
CLOSED = {"pdf_urls": [], "landing_page": None}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        legacy_recommendation_settings(self.app, route_beta=True)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("Crystals", "manual", ["crystal lattice"])["project_id"]

    def add(self, key, abstract=ABSTRACT, **extra):
        self.app.store.upsert_papers([{"key": key, "title": f"Crystal lattice study {key}", "abstract": abstract,
                                       "published": "2026-01-01", **extra}], project_id=self.pid)

    def papers(self):
        self.add("nosrc")                                    # abstract, but nowhere to get a PDF
        self.add("closed", oa=CLOSED)                        # open-access report with nothing to open
        self.add("arx", arxiv_id="2601.00001")               # arXiv always has a PDF
        self.add("direct", oa=DIRECT)
        self.add("page", oa=PAGE)                            # a landing page is a source
        self.add("local")                                    # no source in the metadata, but the PDF is stored here
        self.app.store.record_pdf("local", str(self.root / "local.pdf"))

    def shown(self, route):
        if route:
            self.app.route_save(self.pid, plan=PLAN)
        english_papers(self.app, self.pid, pdf_source=False)
        out = self.app.build_batch(limit=10, project_id=self.pid)
        return {c["key"] for c in out["cards"]}, out


class NoPdfSourceTests(Fixture):
    expected = {"arx", "direct", "page", "local"}

    def test_without_a_map(self):
        self.papers()
        self.assertEqual(self.shown(route=False)[0], self.expected)

    def test_with_a_map(self):
        self.papers()
        self.assertEqual(self.shown(route=True)[0], self.expected)

    def test_the_papers_stay_in_the_project(self):
        self.papers()
        self.shown(route=False)
        keys = {r[0] for r in self.app.store.conn.execute("SELECT paper_key FROM project_papers WHERE project_id=?", (self.pid,))}
        self.assertTrue({"nosrc", "closed"} <= keys)

    def test_the_filtered_count_is_reported_with_its_own_reason(self):
        self.papers()
        _, out = self.shown(route=False)
        self.assertEqual(out["eligibility"]["excluded"].get("no_pdf_source"), 2)
        self.assertIn("no_pdf_source", eligibility.REASONS)
        self.assertTrue(all(eligibility.REASONS["no_pdf_source"]))

    def test_a_paper_with_neither_abstract_nor_source_keeps_the_older_reason(self):
        self.add("bare", abstract="")
        english_papers(self.app, self.pid, pdf_source=False)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(out["cards"], [])
        self.assertEqual(out["eligibility"]["excluded"], {"no_readable_content": 1})

    def test_when_only_sourceless_papers_are_left_there_is_no_batch(self):
        self.add("nosrc")
        english_papers(self.app, self.pid, pdf_source=False)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(out["cards"], [])
        self.assertIsNotNone(out["shortfall"])

    def test_maintenance_does_not_think_a_sourceless_paper_is_news(self):
        from app import maintenance
        self.add("nosrc")
        english_papers(self.app, self.pid, pdf_source=False)
        self.assertFalse(maintenance._has_unseen(self.app, self.pid))
        self.add("direct", oa=DIRECT)
        english_papers(self.app, self.pid, pdf_source=False)
        self.assertTrue(maintenance._has_unseen(self.app, self.pid))


class EvaluateTests(unittest.TestCase):
    policy = {"status": "ready", "allowed_languages": ["en"]}
    language = {"metadata_language": "en"}

    def check(self, **paper):
        return eligibility.evaluate(self.policy, {"title": "Crystal lattice growth", "abstract": ABSTRACT, **paper}, self.language)

    def test_source_kinds(self):
        self.assertEqual(self.check()["reason"], "no_pdf_source")
        self.assertEqual(self.check(oa_json=json.dumps(CLOSED))["reason"], "no_pdf_source")
        for paper in ({"arxiv_id": "2601.1"}, {"oa_json": json.dumps(DIRECT)}, {"oa": DIRECT}, {"oa_json": json.dumps(PAGE)},
                      {"current_pdf_path": "/tmp/x.pdf"}):
            with self.subTest(paper=paper):
                self.assertTrue(self.check(**paper)["eligible"])

    def test_an_insecure_link_is_not_a_source(self):
        self.assertEqual(self.check(oa={"pdf_urls": ["http://example.org/a.pdf"], "landing_page": "http://example.org"})["reason"],
                         "no_pdf_source")


if __name__ == "__main__":
    unittest.main()
