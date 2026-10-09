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
from recommendation_fixtures import english_papers
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
        # These historic ceiling fixtures explicitly exercise the retained
        # opt-in policy; shipped runtime policy is covered in test_gateway_policy.
        self.gateway.config['policy']['aggregate_limits_enabled'] = True

    def test_invalid_unicode_serialization_refuses_before_reservation_or_network(self):
        with mock.patch('app.gateway.urllib.request.urlopen') as opened:
            out=self.gateway.call('paper_qa',[{'role':'user','content':'\ud800'}])
        opened.assert_not_called()
        self.assertFalse(out['ok']);self.assertTrue(out['invalid_input']);self.assertFalse(out['usage_unknown'])
        self.assertFalse(self.gateway.ledger.exists())

    def test_new_map_request_wire_matches_complete_estimate(self):
        from app import route_revision as rr
        self.gateway.config['operations'][rr.CREATE_OPERATION]['owner_approved']=True
        messages=rr.model_messages({'goal':'理解模型'},model=self.gateway.config['provider']['model'])
        seen=[]
        def fake(request,**kw):
            seen.append(request.data)
            return _ok({'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],
                        'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}})
        with mock.patch('app.gateway.urllib.request.urlopen',side_effect=fake):
            out=self.gateway.call(rr.CREATE_OPERATION,messages)
        self.assertTrue(out['ok']);self.assertEqual(len(seen),1)
        self.assertEqual(len(seen[0])+256,rr.message_estimate(messages,1800,self.gateway.config['provider']['model']))
        self.assertIn('理解模型',seen[0].decode('utf-8'))

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

    def test_structured_operations_use_json_format_and_zero_temperature_without_extra_attempt(self):
        payload = {"model": "deepseek-flash", "choices": [{"message": {"content": "{}"}}],
                   "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}
        structured = ['route_growth_judge', 'daily_triage', 'project_guidance', 'route_map_create', 'route_map_revision', 'category_review']
        for operation in structured + ['paper_qa']:
            with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)) as urlopen:
                result = self.gateway.call(operation, [{"role": "user", "content": "Return JSON."}])
            self.assertTrue(result["ok"])
            self.assertEqual(urlopen.call_count, 1)
            body = json.loads(urlopen.call_args[0][0].data)
            self.assertEqual(body["thinking"], {"type": "disabled"})
            self.assertEqual(body["max_tokens"], self.gateway.config["operations"][operation]["cap"]["output"])
            if operation in structured:
                self.assertEqual(body["temperature"], 0)
                self.assertEqual(body["response_format"], {"type": "json_object"})
            else:
                self.assertNotIn("temperature", body)
                self.assertNotIn("response_format", body)

    def test_finish_reason_reaches_callers_with_known_and_unknown_usage(self):
        for usage in ({'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}, None):
            payload = {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'length'}]}
            if usage is not None:
                payload['usage'] = usage
            with mock.patch('app.gateway.urllib.request.urlopen', return_value=_ok(payload)):
                out = self.gateway.call('daily_triage', [{'role': 'user', 'content': 'x'}])
            self.assertFalse(out['ok']); self.assertTrue(out['bad_reply'])
            self.assertEqual(out['finish_reason'], 'length')
            self.assertEqual(out.get('usage_unknown', False), usage is None)

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

    def test_server_http_failure_reports_unknown_usage_and_keeps_reservation(self):
        error = urllib.error.HTTPError('u', 503, 'unavailable', {}, io.BytesIO(b''))
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=error):
            out = self.gateway.call('daily_triage', [])
        self.assertTrue(out['usage_unknown'])
        self.assertEqual(out['http_status'], 503)
        self.assertEqual([r['status'] for r in self._rows()], ['reserved'])

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
        self.assertEqual(json.loads(urlopen.call_args[0][0].data)["max_tokens"], 1500)
        self.assertEqual([r["operation"] for r in self._rows()], ["learning_path_plan", "learning_path_plan"])

    def test_approved_category_review_sends_once_with_its_own_cap_and_reconciles_usage(self):
        from app import category_review as cr
        self.assertIs(self.gateway.config['operations'][cr.OPERATION]['owner_approved'], True)
        prepared = cr.prepare([{'id':'local-world-id','name':'世界模型','parent_id':None}],
                              [{'key':'local-paper-id','title':'World Model Planning','categories':['local-world-id']}])
        reply = {'categories':[{'id':'c1','action':'keep','reason':'明确研究方向'}],
                 'papers':[{'id':'p1','categories':['c1'],'reason':'公开标题支持'}], 'new_categories':[]}
        payload = {'model':'deepseek-flash','choices':[{'message':{'content':json.dumps(reply)},'finish_reason':'stop'}],
                   'usage':{'prompt_tokens':200,'completion_tokens':100,'total_tokens':300}}
        observed = []
        def fake(request, timeout):
            observed.extend(self._rows())
            return _ok(payload)
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=fake) as opened:
            result = self.gateway.call(cr.OPERATION, prepared['messages'])
        self.assertTrue(result['ok']); opened.assert_called_once()
        wire = json.loads(opened.call_args[0][0].data)
        self.assertEqual(wire['max_tokens'], 2000)
        self.assertEqual(wire['thinking'], {'type':'disabled'})
        self.assertEqual(wire['messages'], prepared['messages'])
        self.assertNotIn('local-world-id', json.dumps(wire)); self.assertNotIn('local-paper-id', json.dumps(wire))
        self.assertEqual([(r['operation'],r['status'],r['input'],r['output']) for r in observed],
                         [('category_review','reserved',8000,2000)])
        self.assertEqual(observed[0]['usd'], '0.0048')
        rows = self._rows()
        self.assertEqual([(r['operation'],r['status']) for r in rows],
                         [('category_review','reserved'),('category_review','reconciled')])
        self.assertEqual(rows[0]['id'], rows[1]['id'])
        self.assertEqual((rows[1]['input'],rows[1]['output'],rows[1]['total']), (200,100,300))
        self.assertEqual(self.gateway.usage_today()['tokens'], 300)
        self.assertEqual(cr.parse(result['content'],prepared['context'],finish_reason=result['finish_reason'])['papers'][0]['key'],
                         'local-paper-id')

    def test_category_review_revoked_fixture_refuses_before_key_or_network_and_writes_no_ledger(self):
        operations = self.gateway.config['operations']
        operations['category_review'] = {**operations['category_review'], 'owner_approved':False}
        with mock.patch.object(self.gateway,'_load_key') as load_key, mock.patch('app.gateway.urllib.request.urlopen') as opened:
            result = self.gateway.call('category_review', [])
        load_key.assert_not_called(); opened.assert_not_called()
        self.assertFalse(result['ok']); self.assertIn('owner approval',result['reason'])
        self.assertEqual(self._rows(), [])
        self.assertFalse(self.gateway.ledger.exists())

    def test_category_review_ai_off_blocks_normal_and_dry_run_before_key_or_network(self):
        self.gateway.set_enabled(False)
        with mock.patch.object(self.gateway,'_load_key') as load_key, mock.patch('app.gateway.urllib.request.urlopen') as opened:
            for dry_run in (False, True):
                with self.subTest(dry_run=dry_run):
                    result = self.gateway.call('category_review', [], dry_run=dry_run)
                    self.assertFalse(result['ok']); self.assertTrue(result['disabled'])
        load_key.assert_not_called(); opened.assert_not_called()
        self.assertEqual(self._rows(), [])
        self.assertFalse(self.gateway.ledger.exists())

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
            english_papers(self.app, self.project)
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
        english_papers(self.app, self.project)
        cards = self.app.build_batch(project_id=self.project)["cards"]
        with mock.patch("app.gateway.urllib.request.urlopen",
                        side_effect=urllib.error.URLError("offline")) as urlopen:
            triage = self.app.triage(cards, project_id=self.project)
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(triage["degraded"])
        self.assertEqual(triage["mode"], "sparse")
        self.assertEqual(len(self.app.cards(project_id=self.project)), 1)

    def test_a_card_level_triage_sends_only_the_chosen_cards_and_saves_only_their_summaries(self):
        self.app.store.upsert_papers([{"key": "p2", "title": "Other Planning Paper", "abstract": "other",
                                       "published": "2026-08-02"}], project_id=self.project)
        english_papers(self.app, self.project)
        cards = self.app.build_batch(project_id=self.project)["cards"]
        self.assertEqual({c["key"] for c in cards}, {"p1", "p2"})
        reply = [{"paper_id": "p2", "one_liner": "about other", "why_relevant": "w", "caution": ""}]
        payload = {"choices": [{"message": {"content": json.dumps(reply)}}], "model": "m",
                   "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}}
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)) as urlopen:
            result = self.app.triage(cards, project_id=self.project, keys=["p2"])
        sent = json.loads(urlopen.call_args[0][0].data)["messages"][-1]["content"]
        self.assertIn("id=p2", sent)
        self.assertNotIn("id=p1", sent)
        self.assertNotIn("World Model Planning", sent)
        self.assertTrue(result["ok"])
        summaries = self.app.store.summaries()
        self.assertIn("p2", summaries)
        self.assertNotIn("p1", summaries)

    def test_a_card_level_triage_refuses_empty_oversized_foreign_and_non_text_keys_without_a_request(self):
        english_papers(self.app, self.project)
        cards = self.app.build_batch(project_id=self.project)["cards"]
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            for bad in ([], ["not-in-batch"], [1], "p1", ["a"] * 6, [None]):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    self.app.triage(cards, project_id=self.project, keys=bad)
        urlopen.assert_not_called()

    def test_a_card_level_triage_respects_the_ai_switch(self):
        english_papers(self.app, self.project)
        cards = self.app.build_batch(project_id=self.project)["cards"]
        self.app.gateway.set_enabled(False)
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            result = self.app.triage(cards, project_id=self.project, keys=["p1"])
        urlopen.assert_not_called()
        self.assertTrue(result["degraded"])

    def test_triage_unparseable_reply_degrades(self):
        english_papers(self.app, self.project)
        cards = self.app.build_batch(project_id=self.project)["cards"]
        payload = {"choices": [{"message": {"content": "[not json"}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=_ok(payload)):
            triage = self.app.triage(cards, project_id=self.project)
        self.assertFalse(triage["ok"])
        self.assertTrue(triage["degraded"])


if __name__ == "__main__":
    unittest.main()
