"""AI preview covers a whole recommendation batch (owner 2026-10-25): one call for up to 20 cards, a fuller summary per
card, and no more than 20. The model is replaced by a synthetic reply; no request leaves the machine."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_gateway_budget import _ok
from app.service import App

ROOT = Path(__file__).resolve().parents[1]


class TriageBatchOfTwentyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "PAGETIDE_DEV": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name) / "app")
        self.project = self.app.create_project("P", "manual", ["world model"])["project_id"]
        papers = [{"key": f"p{i}", "title": f"World Model Paper {i}", "abstract": f"Abstract {i} " + "x" * 900,
                   "published": "2026-08-01"} for i in range(21)]
        self.app.store.upsert_papers(papers, project_id=self.project)
        self.cards = [{"key": p["key"], "title": p["title"], "abstract": p["abstract"]} for p in papers]

    def reply(self, keys):
        items = [{"paper_id": k, "one_liner": "问题。方法。结果。", "why_relevant": "与 world model 相关。", "caution": ""}
                 for k in keys]
        return _ok({"choices": [{"message": {"content": json.dumps({"items": items}, ensure_ascii=False)},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}})

    def test_twenty_cards_go_out_in_one_call_and_all_get_a_preview(self):
        cards = self.cards[:20]
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=self.reply([c["key"] for c in cards])) as urlopen:
            result = self.app.triage(cards, project_id=self.project)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["items"]), 20)
        self.assertEqual(urlopen.call_count, 1)
        body = json.loads(urlopen.call_args[0][0].data)
        prompt = body["messages"][0]["content"]
        self.assertEqual(body["max_tokens"], self.app.gateway.config["operations"]["daily_triage"]["cap"]["output"])
        self.assertIn("one_liner 写2到3句", prompt)
        fragments = re.findall(r"abstract=(.*?) \| title_truncated", prompt)
        self.assertEqual([len(f) for f in fragments], [800] * 20)            # 800-character abstract fragments

    def test_card_level_choice_accepts_twenty_and_refuses_twenty_one(self):
        keys = [c["key"] for c in self.cards]
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=self.reply(keys[:20])):
            self.assertTrue(self.app.triage(self.cards, project_id=self.project, keys=keys[:20])["ok"])
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "1 到 20"):
                self.app.triage(self.cards, project_id=self.project, keys=keys)
            with self.assertRaisesRegex(ValueError, "1至20"):
                self.app.triage(self.cards, project_id=self.project)
        urlopen.assert_not_called()

    def test_budget_entry_matches_a_batch_of_twenty(self):
        op = self.app.gateway.config["operations"]["daily_triage"]
        self.assertEqual(sum(op["input_cap_components"].values()), op["cap"]["input"])
        self.assertIn("twenty", op["scope"])


if __name__ == "__main__":
    unittest.main()
