"""Links and unextracted PDFs do not replace readable text for recommendation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import english_papers
from app.service import App

PLAN = {"concepts": [{"id": "a", "name": "Crystal basics", "terms": ["crystal lattice"], "hint": 1, "needs": []}], "targets": ["a"]}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=False)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("Crystals", "manual", ["crystal lattice"])["project_id"]

    def add(self, key, abstract, **extra):
        self.app.store.upsert_papers([{"key": key, "title": f"Crystal lattice study {key}", "abstract": abstract, "published": "2026-01-01", **extra}], project_id=self.pid)

    def shown(self, route):
        if route:
            self.app.route_save(self.pid, plan=PLAN)
        english_papers(self.app, self.pid)
        return {c["key"] for c in self.app.build_batch(limit=10, project_id=self.pid)["cards"]}


class UnreadableTests(Fixture):
    def papers(self):
        self.add("bare", "")                                                   # nothing to read
        self.add("blank", "   \n")                                             # whitespace is nothing
        self.add("nullabs", None)
        self.add("abs", "A real abstract about crystal lattice growth.")        # an abstract is enough
        self.add("arx", "", arxiv_id="2601.00001")                              # a link alone is insufficient
        self.add("oa", "", oa={"pdf_urls": ["https://example.org/a.pdf"], "landing_page": None})
        self.add("page", "", oa={"pdf_urls": [], "landing_page": "https://example.org/landing"})   # a landing page alone is insufficient
        self.add("closed", "", oa={"pdf_urls": [], "landing_page": None})       # open-access report with nothing to open
        self.add("local", "")
        self.app.store.record_pdf("local", str(self.root / "local.pdf"))        # a stored PDF without body extraction is insufficient

    def test_without_a_map(self):
        self.papers()
        self.assertEqual(self.shown(route=False), {"abs"})

    def test_with_a_map(self):
        self.papers()
        self.assertEqual(self.shown(route=True), {"abs"})

    def test_a_paper_without_either_stays_in_the_project(self):
        self.papers()
        self.shown(route=False)
        keys = {r[0] for r in self.app.store.conn.execute("SELECT paper_key FROM project_papers WHERE project_id=?", (self.pid,))}
        self.assertTrue({"bare", "blank", "nullabs", "closed"} <= keys)

    def test_when_only_unreadable_papers_are_left_there_is_no_batch_and_it_says_so(self):
        self.add("bare", "")
        english_papers(self.app, self.pid)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(out["cards"], [])


if __name__ == "__main__":
    unittest.main()
