"""Explicit whole-queue growth jobs with synthetic metadata and provider fixtures."""
import json
import io
from unittest import mock
from test_route_growth import Fixture, reply, new
from app.organization import Conflict


class GrowthBatchTests(Fixture):
    def queue(self, count):
        for i in range(count):
            self.add(f'b{i}', f'Paper {i}', 'Public abstract', 'synthetic')
            self.say((f'b{i}', 'useful'))
        return [p['key'] for p in self.app._pending_growth(self.pid)]

    def cover(self, messages):
        body = json.loads(messages[1]['content'])
        return reply([{'papers': list(body['papers']), 'verdict': 'covered', 'nearest': 'c2'}])

    def dynamic_gateway(self, respond):
        calls=[]
        def fake(operation, messages, dry_run=False):
            calls.append(messages)
            return respond(messages, len(calls))
        self.app.gateway.call = fake
        return calls

    def test_twenty_papers_finish_in_one_click_and_one_daily_job(self):
        keys = self.queue(20)
        calls = self.dynamic_gateway(lambda m, n: self.cover(m))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(out['pending'], 0)
        self.assertEqual((out['requested'], out['processed'], out['complete']), (20,20,True))
        self.assertEqual((out['model_calls'],len(calls),out['judges_left']), (7,7,9))
        self.assertEqual(len(self.app._directions_store(self.pid)['judged']),len(keys))
        self.assertTrue(all(1 <= len(json.loads(m[1]['content'])['papers']) <= 3 for m in calls))

    def test_a_second_batch_failure_preserves_first_batch_and_single_job(self):
        self.queue(8)
        calls = self.dynamic_gateway(lambda m, n: self.cover(m) if n==1 else {'ok':False,'reason':'timeout','usage_unknown':True})
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['requested'],out['complete'],out['pending']), (3,8,False,5))
        self.assertEqual((out['model_calls'],len(calls),out['judges_left']), (2,2,9))
        self.assertEqual(out['reason_code'],'network')
        self.assertEqual(len(self.app._directions_store(self.pid)['judged']),3)

    def test_budget_refusal_after_success_does_not_refund_the_job(self):
        self.queue(4)
        self.dynamic_gateway(lambda m,n:self.cover(m) if n==1 else {'ok':False,'reason':'daily token ceiling'})
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['judges_left']), (3,1,9))
        self.assertEqual(out['reason_code'],'budget')

    def test_no_key_before_any_send_refunds_entire_job(self):
        self.queue(20)
        calls=self.dynamic_gateway(lambda m,n:{'ok':False,'reason':'no API key'})
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['judges_left']), (0,20,10))
        self.assertEqual(len(calls),1)

    def test_a_partial_answer_cannot_be_reported_as_complete(self):
        self.queue(5)
        calls=self.dynamic_gateway(lambda m,n:reply([{'papers':['p1'],'verdict':'covered','nearest':'c2'}]))
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['complete']), (1,4,False))
        self.assertEqual(len(calls),1) # no retry or continued spend after an incomplete answer

    def test_new_interest_during_run_is_not_silently_added_to_this_job(self):
        self.queue(4)
        def response(m,n):
            if n==1:
                self.add('later','New arrival','New abstract','synthetic')
                self.say(('later','useful'))
            return self.cover(m)
        calls=self.dynamic_gateway(response)
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['requested'],out['processed'],out['complete'],out['pending']), (4,4,True,1))
        self.assertEqual(len(calls),2)
        self.assertEqual(self.app._pending_growth(self.pid)[0]['key'],'later')

    def test_revoking_selected_interest_halts_remaining_calls(self):
        keys=self.queue(5)
        def response(m,n):
            if n==1:self.app.undo_feedback(self.app.latest_feedback(self.pid)[keys[-1]]['id'])
            return self.cover(m)
        calls=self.dynamic_gateway(response)
        with self.assertRaises(Conflict):self.app.route_direction_judge(self.pid)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.app._directions_store(self.pid)['judged'],{})

    def test_many_groups_across_batches_are_preserved_and_reusable(self):
        self.queue(6)
        def response(m,n):
            labels=list(json.loads(m[1]['content'])['papers'])
            return reply([new([label],name=f'Task {n}-{i}') for i,label in enumerate(labels)])
        self.dynamic_gateway(response)
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['complete']), (6,0,True))
        self.assertEqual(len(self.app._directions_store(self.pid)['directions']),6)

    def test_dry_run_only_preflights_first_request_without_consuming_job(self):
        self.queue(20)
        calls=self.dynamic_gateway(lambda m,n:self.cover(m))
        out=self.app.route_direction_judge(self.pid,dry_run=True)
        self.assertEqual((out['processed'],out['pending'],out['judges_left']), (0,20,10))
        self.assertEqual(len(calls),1)

    def test_valid_response_with_unknown_usage_is_saved_but_stops_new_spend(self):
        self.queue(5)
        calls=self.dynamic_gateway(lambda m,n:{**self.cover(m),'usage_unknown':True,'usage':None})
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['judges_left']), (3,2,9))
        self.assertEqual((out['complete'],out['reason_code'],out['tokens']), (False,'network',None))
        self.assertEqual(len(calls),1)

    def test_real_gateway_cap_refusal_preserves_eighteen_of_twenty(self):
        self.queue(20)
        sent=[]
        def response(request, **kwargs):
            body=json.loads(request.data)
            messages=body['messages']
            sent.append(body)
            outcome=self.cover(messages)
            payload={'choices':[{'message':{'content':outcome['content']},'finish_reason':'stop'}],
                     'usage':{'prompt_tokens':8000,'completion_tokens':1000,'total_tokens':9000}}
            return io.BytesIO(json.dumps(payload).encode())
        with mock.patch.object(self.app.gateway,'_load_key',return_value=('synthetic-key','fixture')), \
             mock.patch('urllib.request.urlopen',side_effect=response):
            out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['complete'],out['judges_left']), (18,2,False,9))
        self.assertEqual((len(sent),out['model_calls'],out['reason_code']), (6,7,'budget'))
        self.assertEqual(self.app.gateway.usage_today()['tokens'],54000)

    def test_restart_resumes_only_unfinished_papers_without_retrying_completed(self):
        self.queue(7)
        self.dynamic_gateway(lambda m,n:self.cover(m) if n==1 else {'ok':False,'reason':'no API key'})
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending']), (3,4))
        self.app.store.close()
        from app.service import App
        self.app=App(root=str(self.root),data_dir=str(self.root/'data'))
        self.addCleanup(self.app.store.close)
        calls=self.dynamic_gateway(lambda m,n:self.cover(m))
        resumed=self.app.route_direction_judge(self.pid)
        self.assertEqual((resumed['requested'],resumed['processed'],resumed['pending'],resumed['judges_left']), (4,4,0,8))
        self.assertEqual(len(calls),2)

    def test_third_batch_can_join_a_second_batch_proposal(self):
        self.queue(9)
        sent=[]
        def response(m,n):
            body=json.loads(m[1]['content']);sent.append(body)
            if n < 3:
                return reply([new([p],name=f'Task {n}-{i}') for i,p in enumerate(body['papers'])])
            target=next((d for d,value in body['directions'].items() if value['name']=='Task 2-2'),None)
            self.assertIsNotNone(target)
            return reply([{'papers':list(body['papers']),'verdict':'join','direction':target}])
        self.dynamic_gateway(response)
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['complete']), (9,True))
        target=next(d for d in self.app._directions_store(self.pid)['directions'] if d['name']=='Task 2-2')
        self.assertEqual(len(target['papers']),4)

    def test_visible_proposal_evidence_revoked_during_call_cannot_be_joined(self):
        self.say(('s1','useful'))
        self.dynamic_gateway(lambda m,n:reply([new(['p1'])]))
        self.app.route_direction_judge(self.pid)
        self.say(('s2','useful'))
        def response(m,n):
            self.app.undo_feedback(self.app.latest_feedback(self.pid)['s1']['id'])
            return reply([{'papers':['p1'],'verdict':'join','direction':'d1'}])
        self.dynamic_gateway(response)
        with self.assertRaises(Conflict):self.app.route_direction_judge(self.pid)
        self.assertTrue(self.app.route_candidates(self.pid)['candidates'][0]['stale'])
        self.assertEqual([p['key'] for p in self.app._pending_growth(self.pid)],['s2'])

    def test_saved_batches_are_not_described_as_unsaved_after_failure(self):
        self.queue(5)
        self.dynamic_gateway(lambda m,n:self.cover(m) if n==1 else {'ok':False,'reason':'daily token ceiling'})
        out=self.app.route_direction_judge(self.pid)
        self.assertNotIn('未保存判断',out['reason'])
        self.assertIn('已保存',out['reason'])

    def test_terminal_attempt_count_uses_current_day_after_midnight(self):
        self.queue(4)
        day=['2026-10-06']
        def response(m,n):
            if n==2:day[0]='2026-10-07'
            return self.cover(m)
        self.dynamic_gateway(response)
        with mock.patch('app.service.time.strftime',side_effect=lambda *args:day[0]):
            out=self.app.route_direction_judge(self.pid)
            current=self.app.route_candidates(self.pid)
        self.assertEqual((out['judges_left'],current['judges_left']), (10,10))
        self.assertEqual(self.app.store.get_setting(f'direction_judge_{self.pid}'),{'day':'2026-10-06','attempts':1})

    def test_extra_invalid_or_duplicate_groups_stop_after_valid_batch(self):
        for extra in ('p999','p1'):
            with self.subTest(extra=extra):
                keys=self.queue(5)
                def response(m,n):
                    out=self.cover(m)
                    raw=json.loads(out['content'])
                    raw['results'].append({'papers':[extra],'verdict':'covered','nearest':'c2'})
                    return {**out,'content':json.dumps(raw)}
                calls=self.dynamic_gateway(response)
                out=self.app.route_direction_judge(self.pid)
                self.assertEqual((out['processed'],out['pending'],out['complete']), (3,2,False))
                self.assertEqual((len(calls),out['reason_code']), (1,'bad_reply'))
                # Remove this synthetic fixture's interest before the next case.
                for key in keys:self.app.record_feedback(key,'irrelevant',project_id=self.pid)

    def test_duplicate_paper_reference_in_one_group_is_not_silently_deduplicated(self):
        self.queue(3)
        self.dynamic_gateway(lambda m,n:reply([{'papers':['p1','p1','p2','p3'],'verdict':'covered','nearest':'c2'}]))
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'],out['pending'],out['complete']), (0,3,False))
