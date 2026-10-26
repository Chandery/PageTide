"""An empty day of recommendations says, in one plain sentence, what to do (owner, 2026-10-26: "很多地方边界没做好而导致进去
推荐不出论文"): fetch first, fix the cause most candidates were excluded for, or fetch new ones when all were seen."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class EmptyBatchReasonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "app").mkdir()
        (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        from app.service import App
        self.app = App(root=str(root), data_dir=str(root / "data"))
        self.addCleanup(self.app.store.close)

    def test_no_candidates_says_to_fetch_and_what_to_check(self):
        reason = self.app._empty_pool_reason([], {})
        self.assertIn("抓取新论文", reason)
        self.assertIn("论文语言", reason)

    def test_all_excluded_names_the_main_cause_and_the_fix(self):
        papers = [{"key": str(n)} for n in range(5)]
        reason = self.app._empty_pool_reason(papers, {"language_not_allowed": 4, "no_readable_content": 1})
        self.assertIn("论文语言", reason)
        self.assertIn("项目设置", reason)
        reason = self.app._empty_pool_reason(papers, {"source_disabled": 5})
        self.assertIn("数据源", reason)
        self.assertIn("换个关键词", self.app._empty_pool_reason(papers, {"something_new": 5}))

    def test_some_eligible_but_all_seen_says_to_fetch_new_ones(self):
        papers = [{"key": str(n)} for n in range(5)]
        self.assertIn("都已看过或反馈过", self.app._empty_pool_reason(papers, {"language_not_allowed": 2}))

    def test_no_reason_code_reaches_the_sentence(self):
        papers = [{"key": "1"}]
        for code in ("language_not_allowed", "source_disabled", "no_readable_content", "no_pdf_source", "language_unknown"):
            self.assertNotIn(code, self.app._empty_pool_reason(papers, {code: 1}))

    def test_an_empty_project_batch_uses_it(self):
        pid = self.app.create_project("空项目", "manual", ["world model"])["project_id"]
        self.app.set_project_language(pid, None, ["en"])
        result = self.app.build_batch(project_id=pid)
        self.assertEqual(result["cards"], [])
        self.assertIn("抓取新论文", result["reason"])


if __name__ == "__main__":
    unittest.main()
