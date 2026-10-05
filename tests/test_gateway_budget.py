"""AI-01: the single budgeted gateway reserves before sending and degrades explicitly.

No test here performs a network request: urlopen is always replaced.
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.gateway import BudgetExceeded, Gateway
from app.service import App

ROOT = Path(__file__).resolve().parents[1]
DAY, MONTH = "2026-09-30", "2026-09"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ok(payload):
    return _Response(json.dumps(payload).encode())


class GatewayBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "PDH_DEV": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.gateway = Gateway(root=ROOT, data_dir=self.data, dev=False)

    def _ledger(self, *entries):
        with self.gateway.ledger.open("a") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def _rows(self):
        if not self.gateway.ledger.exists():
            return []
        return [json.loads(line) for line in self.gateway.ledger.read_text().splitlines() if line.strip()]

    def test_daily_ceiling_uses_only_today(self):
        # 50k tokens earlier this month must not count against today's 55k ceiling.
        self._ledger({"date": "2026-09-10", "operation": "paper_qa", "input": 40000, "output": 10000, "usd": "0.02"})
        self.gateway.admit("daily_triage", DAY, MONTH)
        self._ledger({"date": DAY, "operation": "paper_qa", "input": 40000, "output": 10000, "usd": "0.02"})
        with self.assertRaisesRegex(BudgetExceeded, "daily token"):
            self.gateway.admit("daily_triage", DAY, MONTH)

    def test_monthly_ceiling_counts_the_whole_month(self):
        monthly = self.gateway.limits()["monthly_total_tokens"]
        self._ledger({"date": "2026-09-02", "operation": "paper_qa", "input": monthly - 1000, "output": 0, "usd": "0"})
        with self.assertRaisesRegex(BudgetExceeded, "monthly token"):
            self.gateway.admit("daily_triage", DAY, MONTH)

    def test_daily_usd_ceiling_refuses(self):
        self._ledger({"date": DAY, "operation": "paper_qa", "input": 0, "output": 0,
                      "usd": self.gateway.limits()["daily_usd"]})
        with self.assertRaisesRegex(BudgetExceeded, "daily USD"):
            self.gateway.admit("daily_triage", DAY, MONTH)

    def test_budget_refusal_makes_no_request(self):
        self._ledger({"date": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat(),
                      "operation": "paper_qa", "input": 60000, "output": 0, "usd": "0"})
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            result = self.gateway.call("daily_triage", [{"role": "user", "content": "x"}])
        urlopen.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result["degraded"])

    def test_reservation_is_written_before_send_and_reconciled(self):
        seen = {}

        def fake(request, timeout):
            seen["rows"] = self._rows()
            return _ok({"model": "deepseek-flash", "choices": [{"message": {"content": "hi"}}],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})

        with mock.patch("app.gateway.urllib.request.urlopen", side_effect=fake) as urlopen:
            result = self.gateway.call("daily_triage", [{"role": "user", "content": "x"}])
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(result["ok"])
        self.assertEqual([r["status"] for r in seen["rows"]], ["reserved"])
        self.assertEqual(seen["rows"][0]["input"], self.gateway.config["operations"]["daily_triage"]["cap"]["input"])
        self.assertEqual(self.gateway.usage_today()["tokens"], 120)
        body = json.loads(urlopen.call_args[0][0].data)
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["model"], self.gateway.config["provider"]["model"])

    def test_in_flight_reservation_blocks_concurrent_admission(self):
        cap = self.gateway.config["operations"]["daily_triage"]["cap"]
        per_call = cap["input"] + cap["output"]
        room = self.gateway.limits()["daily_total_tokens"]
        today = self.gateway.usage_today
        # Fill the day so exactly one more envelope fits.
        filler = room - per_call - 1
        import datetime
        date = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        self._ledger({"date": date, "operation": "paper_qa", "input": filler, "output": 0, "usd": "0"})
        observed = []

        def fake(request, timeout):
            observed.append(self.gateway.call("daily_triage", [{"role": "user", "content": "y"}]))
            raise TimeoutError("slow")

        with mock.patch("app.gateway.urllib.request.urlopen", side_effect=fake):
            first = self.gateway.call("daily_triage", [{"role": "user", "content": "x"}])
        self.assertFalse(first["ok"])
        self.assertTrue(first["usage_unknown"])
        self.assertFalse(observed[0]["ok"])
        self.assertIn("daily token", observed[0]["reason"])
        # The timed-out request keeps its reservation charged.
        self.assertEqual(today()["tokens"], filler + per_call)

    def test_missing_usage_keeps_the_reservation(self):
        payload = {"choices": [{"message": {"content": "x"}}]}
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)):
            result = self.gateway.call("daily_triage", [])
        cap = self.gateway.config["operations"]["daily_triage"]["cap"]
        self.assertTrue(result["usage_unknown"])
        self.assertEqual(self.gateway.usage_today()["tokens"], cap["input"] + cap["output"])
        self.assertEqual([r["status"] for r in self._rows()], ["reserved", "unknown"])

    def test_client_rejection_releases_and_network_failure_does_not_retry(self):
        error = urllib.error.HTTPError("u", 401, "unauthorized", {}, io.BytesIO(b""))
        with mock.patch("app.gateway.urllib.request.urlopen", side_effect=error) as urlopen:
            rejected = self.gateway.call("daily_triage", [])
        self.assertEqual(urlopen.call_count, 1)
        self.assertFalse(rejected["ok"])
        self.assertEqual(self.gateway.usage_today()["tokens"], 0)
        with mock.patch("app.gateway.urllib.request.urlopen",
                        side_effect=urllib.error.URLError("offline")) as urlopen:
            failed = self.gateway.call("daily_triage", [])
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(failed["degraded"])
        self.assertTrue(failed["usage_unknown"])

    def test_no_key_degrades_without_request(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "",
                                          "PAPERDIGHELPER_KEY_FILE": str(self.data / "none.env")}), \
                mock.patch.object(Gateway, "_key_candidates", return_value=iter(())), \
                mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            result = self.gateway.call("daily_triage", [])
        urlopen.assert_not_called()
        self.assertEqual(result["reason"], "no API key")
        self.assertEqual(self._rows(), [])

    def test_unapproved_operation_never_sends(self):
        ops = self.gateway.config["operations"]
        ops["project_guidance"] = {**ops["project_guidance"], "owner_approved": False}
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            result = self.gateway.call("project_guidance", [])
        urlopen.assert_not_called()
        self.assertIn("owner approval", result["reason"])
        self.assertEqual(self._rows(), [])

    def test_approved_project_guidance_sends_once_within_its_cap(self):
        payload = {"model": "deepseek-flash", "choices": [{"message": {"content": "{}"}}],
                   "usage": {"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400}}
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)) as urlopen:
            result = self.gateway.call("project_guidance", [{"role": "user", "content": "x"}])
        self.assertTrue(result["ok"])
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(json.loads(urlopen.call_args[0][0].data)["max_tokens"],
                         self.gateway.config["operations"]["project_guidance"]["cap"]["output"])
        self.assertEqual([r["operation"] for r in self._rows()], ["project_guidance", "project_guidance"])

    def test_approved_learning_path_plan_sends_once_with_its_own_cap_and_is_ledgered(self):
        payload = {"model": "deepseek-flash", "choices": [{"message": {"content": "{}"}}],
                   "usage": {"prompt_tokens": 500, "completion_tokens": 600, "total_tokens": 1100}}
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)) as urlopen:
            result = self.gateway.call("learning_path_plan", [{"role": "user", "content": "x"}])
        self.assertTrue(result["ok"])
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(json.loads(urlopen.call_args[0][0].data)["max_tokens"], 900)
        self.assertEqual([r["operation"] for r in self._rows()], ["learning_path_plan", "learning_path_plan"])

    def test_learning_path_plan_is_refused_when_unapproved(self):
        ops = self.gateway.config["operations"]
        ops["learning_path_plan"] = {**ops["learning_path_plan"], "owner_approved": False}
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            result = self.gateway.call("learning_path_plan", [])
        urlopen.assert_not_called()
        self.assertIn("owner approval", result["reason"])
        self.assertEqual(self._rows(), [])

    def test_ai_off_blocks_every_request_including_dry_run(self):
        self.gateway.set_enabled(False)
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            for operation in ("daily_triage", "paper_qa", "selection_translate", "project_guidance", "learning_path_plan"):
                result = self.gateway.call(operation, [])
                self.assertTrue(result["disabled"])
            dry = self.gateway.call("daily_triage", [], dry_run=True)
        urlopen.assert_not_called()
        self.assertTrue(dry["disabled"])
        self.assertEqual(self._rows(), [])
        self.assertTrue(self.gateway.set_enabled(True))


class ServiceDegradeTests(unittest.TestCase):
    """Features stay local when AI is off, unapproved or failing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "PDH_DEV": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name) / "app")
        self.project = self.app.create_project("P", "manual", ["world", "model"])["project_id"]
        self.app.store.upsert_papers([{"key": "p1", "title": "World Model Planning", "abstract": "latent",
                                       "published": "2026-08-01"}], project_id=self.project)

    def test_ai_off_triage_guidance_and_creation_make_zero_requests(self):
        self.app.gateway.set_enabled(False)
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            cards = self.app.build_batch(project_id=self.project)["cards"]
            triage = self.app.triage(cards, project_id=self.project)
            session = self.app.create_guidance_session("Q", "world model planning")
            turn = self.app.guidance_turn(session["id"], "robotics")
            with mock.patch.object(self.app.source, "discover_topic", return_value=[]):
                self.app.guidance_preview(session["id"])
            created = self.app.finalize_guidance(session["id"])
        urlopen.assert_not_called()
        self.assertTrue(triage["degraded"])
        self.assertEqual(turn["mode"], "local")
        self.assertTrue(created["project_id"])
        self.assertEqual(len(cards), 1)

    def test_triage_network_failure_keeps_local_cards(self):
        cards = self.app.build_batch(project_id=self.project)["cards"]
        with mock.patch("app.gateway.urllib.request.urlopen",
                        side_effect=urllib.error.URLError("offline")) as urlopen:
            triage = self.app.triage(cards, project_id=self.project)
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(triage["degraded"])
        self.assertEqual(triage["mode"], "sparse")
        self.assertEqual(len(self.app.cards(project_id=self.project)), 1)

    def test_triage_unparseable_reply_degrades(self):
        cards = self.app.build_batch(project_id=self.project)["cards"]
        payload = {"choices": [{"message": {"content": "[not json"}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)):
            triage = self.app.triage(cards, project_id=self.project)
        self.assertFalse(triage["ok"])
        self.assertTrue(triage["degraded"])


if __name__ == "__main__":
    unittest.main()
