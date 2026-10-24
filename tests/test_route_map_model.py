"""New full-message creation/revision contracts; no provider or library access."""
import json
import unittest
from unittest import mock
from app import route_revision as rr
from app.organization import Conflict
from tests.test_route_revision import graph, patch
from tests import test_route_plan as creation_tests, test_route_store as store_tests

BRIEF = {'goal':'理解世界模型','known':'','include':'','exclude':'','structure':'补必要前置'}

CREATE = {'concepts': [{'id':'c1','name':'概率基础','terms':['概率'],'hint':1,'type':'foundation','why':'理解模型必要前置'},
                       {'id':'c2','name':'世界模型','terms':['world model'],'hint':2,'intro':'预测环境变化'}],
          'prereqs':[['c1','c2']],'targets':['c2']}


def reply(value, **extra):
    return {'ok':True,'content':json.dumps(value,ensure_ascii=False),'usage':{'total_tokens':700},**extra}


class MessageTests(unittest.TestCase):
    def test_create_and_revision_whole_messages_have_only_brief_and_compact_map(self):
        for saved,cap in [(None,3200),(graph(40),8000)]:
            messages=rr.model_messages(BRIEF,saved,english=True)
            self.assertEqual([m['role'] for m in messages],['system','user'])
            value=json.loads(messages[1]['content']);self.assertEqual(value['brief'],BRIEF)
            self.assertEqual(set(value),{'brief'} if saved is None else {'brief','map'})
            self.assertNotIn('private-',messages[1]['content'])
            if saved is not None:self.assertEqual(len(value['map']['concepts']),40)
            self.assertLessEqual(rr.message_estimate(messages,1800 if saved is None else 4000),cap)

    def test_complete_input_overflow_refused_without_truncating(self):
        saved=graph(40)
        for node in saved['concepts']:node['intro']='中'*140
        before=json.dumps(saved,sort_keys=True)
        with self.assertRaises(ValueError):rr.model_messages(BRIEF,saved)
        self.assertEqual(json.dumps(saved,sort_keys=True),before)
        brief={field:'中'*cap for field,cap in rr.BRIEF_LIMITS.items()}
        with self.assertRaises(ValueError):rr.model_messages(brief)

    def test_strict_creation_preserves_explicit_edges_and_fresh_ids(self):
        created=rr.parse_creation(json.dumps(CREATE,ensure_ascii=False))
        self.assertEqual(len(created['graph']['concepts']),2)
        self.assertTrue(all(c['id'].startswith('r-') for c in created['graph']['concepts']))
        self.assertTrue(all(c.get('intro_by')=='ai' for c in created['graph']['concepts'] if c.get('intro')))
        self.assertEqual(created['graph']['targets'],[created['graph']['concepts'][1]['id']])
        self.assertNotEqual(created['graph'],rr.parse_creation(json.dumps(CREATE))['graph'])

    def test_creation_rejects_length_duplicate_bad_refs_and_more_than_12(self):
        with self.assertRaises(ValueError):rr.parse_creation(json.dumps(CREATE),finish_reason='length')
        for value in [{**CREATE,'targets':[]},{**CREATE,'targets':['bad']},
                      {**CREATE,'prereqs':[['c1','c2'],['c1','c2']]},
                      {**CREATE,'prereqs':[['c1','c2'],['c2','c1']]},
                      {**CREATE,'extra':True}, {**CREATE,'concepts':CREATE['concepts']*7}]:
            with self.assertRaises(ValueError):rr.parse_creation(json.dumps(value))
        with self.assertRaises(ValueError):rr.parse_creation('{"concepts":[],"concepts":[]}')


class RevisionModelTests(store_tests.Fixture):
    def setUp(self):
        super().setUp()
        self.app.route_save(self.pid,plan=store_tests.PLAN)
        for i in range(2):
            key='p'+str(i)
            self.add(key,'Crystal growth epitaxy review','Crystal growth lattice epitaxy foundational theory')
            self.app.record_feedback(key,'useful',project_id=self.pid)
            self.app.record_feedback(key,'understood',project_id=self.pid)

    def semantic(self):return patch({'op':'update_node','ref':'c1','changes':{'name':'Revised crystal basics'}})
    def preview(self):return self.app.route_revision_preview(self.pid,BRIEF,patch())

    def test_generate_keeps_map_and_saves_valid_preview_only_after_one_new_operation(self):
        before=self.app.route_get(self.pid)
        with mock.patch.object(self.app.gateway,'call',return_value=reply(self.semantic())) as call:
            out=self.app.route_revision_generate(self.pid,BRIEF,revision=before['revision'])
        self.assertTrue(out['ok']);self.assertEqual(call.call_count,1)
        self.assertEqual(call.call_args.args[0],'route_map_revision')
        self.assertEqual(self.app.route_get(self.pid),before)
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],out['preview']['draft_id'])
        self.assertEqual(out['attempts_left'],1)

    def test_truncated_valid_json_and_invalid_reply_retain_previous_preview(self):
        previous=self.preview()
        for value in [reply(patch(),finish_reason='length'),reply({'unknown':True})]:
            with mock.patch.object(self.app.gateway,'call',return_value=value):
                out=self.app.route_revision_generate(self.pid,BRIEF)
            self.assertFalse(out['ok']);self.assertEqual(out['reason_code'],'bad_reply')
            self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],previous['draft_id'])
        with mock.patch.object(self.app.gateway,'call',side_effect=AssertionError('limit')):
            with self.assertRaises(ValueError):self.app.route_revision_generate(self.pid,BRIEF)

    def test_not_approved_refunds_unknown_billing_retains_and_restart_preserves_limit(self):
        with mock.patch.object(self.app.gateway,'call',return_value={'ok':False,'reason':'operation awaiting owner approval: route_map_revision'}):
            out=self.app.route_revision_generate(self.pid,BRIEF)
        self.assertEqual((out['reason_code'],out['attempts_left']),('not_approved',2))
        with mock.patch.object(self.app.gateway,'call',return_value={'ok':False,'usage_unknown':True,'reason':'TimeoutError'}):
            out=self.app.route_revision_generate(self.pid,BRIEF)
        self.assertEqual(out['attempts_left'],1)
        self.assertEqual(self.app.store.get_setting('route_revision_attempt_'+self.pid)['attempts'],1)

    def test_effective_feedback_change_during_model_call_refuses_to_save_stale_preview(self):
        previous=self.preview();before=self.app.route_get(self.pid)['graph']
        def moved(*args,**kw):
            self.app.undo_feedback(self.app.latest_feedback(self.pid)['p1']['familiar']['id'],self.pid)
            return reply(self.semantic())
        with mock.patch.object(self.app.gateway,'call',side_effect=moved):
            with self.assertRaises(Conflict):self.app.route_revision_generate(self.pid,BRIEF)
        self.assertEqual(self.app.route_get(self.pid)['graph'],before)
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],previous['draft_id'])

    def test_invalid_and_over_budget_request_does_not_reserve_or_call(self):
        oversized=graph(40)
        for node in oversized['concepts']:node['intro']='中'*140
        self.app.route_save(self.pid,graph=oversized)
        with mock.patch.object(self.app.gateway,'call',side_effect=AssertionError('must not call')):
            with self.assertRaises(ValueError):self.app.route_revision_generate(self.pid,BRIEF)
        self.assertIsNone(self.app.store.get_setting('route_revision_attempt_'+self.pid))

    def test_http_refusal_refunds_but_unknown_5xx_retains_and_restart_keeps_limit(self):
        from app.service import App
        for result,count in [({'ok':False,'reason':'HTTPError: 400','usage_unknown':False},0),
                             ({'ok':False,'reason':'HTTPError: 503','usage_unknown':True},1)]:
            with mock.patch.object(self.app.gateway,'call',return_value=result):
                out=self.app.route_revision_generate(self.pid,BRIEF)
            self.assertFalse(out['ok'])
            self.assertEqual(self.app.store.get_setting('route_revision_attempt_'+self.pid)['attempts'],count)
        restarted=App(root=str(self.root),data_dir=str(self.app.data));self.addCleanup(restarted.store.close)
        with mock.patch.object(restarted.gateway,'call',return_value=reply(patch())):
            self.assertEqual(restarted.route_revision_generate(self.pid,BRIEF)['attempts_left'],0)
        with mock.patch.object(restarted.gateway,'call',side_effect=AssertionError('limit')):
            with self.assertRaises(ValueError):restarted.route_revision_generate(self.pid,BRIEF)
        with mock.patch('app.service.time.strftime',return_value='2099-01-01'),mock.patch.object(restarted.gateway,'call',return_value=reply(patch())):
            self.assertEqual(restarted.route_revision_generate(self.pid,BRIEF)['attempts_left'],1)


class CreationModelTests(creation_tests.Fixture):
    def test_session_create_uses_new_operation_and_caches_matching_brief(self):
        calls=self.gateway(reply(CREATE))
        out=self.app.route_brief_plan(BRIEF,session_id=self.session)
        self.assertTrue(out['ok']);self.assertEqual(calls[0][0],'route_map_create')
        self.assertEqual(out['brief'],BRIEF)
        self.assertEqual(self.app.route_brief_plan(BRIEF,session_id=self.session)['mode'],'kept')
        self.assertEqual(len(calls),1)
        self.assertEqual(self.app.guidance_session_view(self.session)['draft']['route_plan']['brief'],BRIEF)
        with self.assertRaises(ValueError):self.app.route_brief_plan({**BRIEF,'goal':'changed'},session_id=self.session)

    def test_existing_project_creation_only_without_map(self):
        pid=self.app.create_project('empty',keywords=['model'])['project_id']
        calls=self.gateway(reply(CREATE))
        out=self.app.route_brief_plan(BRIEF,project_id=pid)
        self.assertTrue(out['ok']);self.assertIsNone(self.app.route_get(pid)['graph'])
        self.app.route_save(pid,graph=out['graph'],brief=BRIEF)
        with self.assertRaises(ValueError):self.app.route_brief_plan(BRIEF,project_id=pid)
        self.assertEqual(len(calls),1)

    def test_create_project_stores_brief_and_does_not_infer_mastery_from_known_text(self):
        graph=rr.parse_creation(json.dumps(CREATE))['graph']
        result=self.app.create_project('new',keywords=['world model'],route={'graph':graph,'mastered':[],'brief':{**BRIEF,'known':'已经学会所有基础'}})
        route=self.app.route_get(result['project_id'])
        self.assertEqual(route['brief']['known'],'已经学会所有基础');self.assertEqual(route['manual'],{})
        before=len(self.app.projects.list_projects())
        with self.assertRaises(ValueError):self.app.create_project('invalid',keywords=['model'],route={'graph':graph,'brief':{}})
        self.assertEqual(len(self.app.projects.list_projects()),before)

class LifecycleTests(creation_tests.Fixture):
    def second(self):
        from app.service import App
        app=App(root=str(self.root),data_dir=str(self.app.data))
        self.addCleanup(app.store.close)
        return app

    def test_new_and_old_creation_share_claim_and_never_erase_paid_count(self):
        seen=[]
        def pending(*a,**kw):
            with self.assertRaises(ValueError):self.app.route_plan(self.session,regenerate=True)
            seen.append(True)
            return {'ok':False,'reason':'operation awaiting owner approval: route_map_create'}
        with mock.patch.object(self.app.gateway,'call',side_effect=pending):
            self.assertFalse(self.app.route_brief_plan(BRIEF,session_id=self.session)['ok'])
        self.assertEqual(seen,[True]);self.assertEqual(self.app.route_plan_state(self.session)['attempts'],0)
        self.gateway(reply(creation_tests.GOOD));self.assertTrue(self.app.route_plan(self.session)['ok'])
        with self.assertRaises(ValueError):self.app.route_brief_plan(BRIEF,session_id=self.session)
        self.assertEqual(self.app.route_plan_state(self.session)['attempts'],1)

    def test_cancel_during_refused_or_paid_reply_never_resurrects_cache(self):
        other=self.second()
        for old in (False,True):
            for paid in (False,True):
                sid=self.app.create_guidance_session('trial','goal')['id']
                def pending(*a,**kw):
                    other.cancel_guidance(sid)
                    return reply(creation_tests.GOOD if old else CREATE) if paid else {'ok':False,'reason':'operation awaiting owner approval'}
                with mock.patch.object(self.app.gateway,'call',side_effect=pending):
                    if paid:
                        with self.assertRaises(Conflict):
                            self.app.route_plan(sid) if old else self.app.route_brief_plan(BRIEF,session_id=sid)
                    else:
                        out=self.app.route_plan(sid) if old else self.app.route_brief_plan(BRIEF,session_id=sid)
                        self.assertFalse(out['ok'])
                self.assertEqual(self.app.store.guidance_session(sid)['status'],'cancelled')
                self.assertIsNone(self.app.store.get_setting('route_plan_'+sid))

    def test_cancel_and_finalize_cannot_commit_an_outer_transaction(self):
        for method in (self.app.cancel_guidance,self.app.finalize_guidance):
            self.app.store.conn.execute('BEGIN IMMEDIATE')
            self.app.store.conn.execute("INSERT INTO settings VALUES ('rollback-probe','1')")
            with self.assertRaises(RuntimeError):method(self.session)
            self.app.store.conn.rollback()
            self.assertIsNone(self.app.store.get_setting('rollback-probe'))
            self.assertEqual(self.app.store.guidance_session(self.session)['status'],'draft')

    def test_reservation_failure_releases_claim_and_allows_retry(self):
        import sqlite3
        with mock.patch.object(self.app,'_growth_write_setting',side_effect=sqlite3.OperationalError('probe')):
            with self.assertRaises(sqlite3.OperationalError):self.app.route_plan(self.session)
        calls=self.gateway(reply(creation_tests.GOOD))
        self.assertTrue(self.app.route_plan(self.session)['ok']);self.assertEqual(len(calls),1)

    def test_cross_process_creation_claim_refuses_before_gateway(self):
        import subprocess,sys
        code="from app.operation_lock import claim;import sys;\nwith claim(sys.argv[1], 'brief-session:'+sys.argv[2]):\n print('ready',flush=True);sys.stdin.read()"
        process=subprocess.Popen([sys.executable,'-c',code,str(self.app.data),self.session],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'ready')
            with mock.patch.object(self.app.gateway,'call') as called:
                with self.assertRaises(ValueError):self.app.route_brief_plan(BRIEF,session_id=self.session)
                with self.assertRaises(ValueError):self.app.route_plan(self.session)
                called.assert_not_called()
        finally:
            process.stdin.close();process.wait(timeout=5);process.stdout.close()
        self.assertEqual(process.returncode,0)


class NewerPreviewTests(RevisionModelTests):
    def test_late_paid_reply_never_overwrites_a_newer_local_preview(self):
        newest=[]
        def moved(*args,**kw):
            newest.append(self.app.route_revision_preview(self.pid,{**BRIEF,'structure':'new teacher text'},patch()))
            return reply(self.semantic())
        with mock.patch.object(self.app.gateway,'call',side_effect=moved):
            with self.assertRaises(Conflict):self.app.route_revision_generate(self.pid,BRIEF)
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],newest[0]['draft_id'])
        self.assertEqual(self.app.route_revision_draft(self.pid)['brief']['structure'],'new teacher text')


class RegistryAndPromptTests(unittest.TestCase):
    def test_new_scope_has_direct_owner_approval_stays_default_off_and_prompts_match(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1];cfg=json.loads((root/'harness/budget.json').read_text())
        for op,system,cap in [(rr.CREATE_OPERATION,rr.CREATE_SYSTEM,(3200,1800)),(rr.REVISION_OPERATION,rr.REVISION_SYSTEM,(8000,4000))]:
            spec=cfg['operations'][op]
            self.assertTrue(spec['owner_approved']);self.assertIn('授权啊，全都授权',spec['approval_note']);self.assertFalse(spec['enabled_by_default'])
            self.assertEqual((spec['cap']['input'],spec['cap']['output']),cap)
            self.assertIn(system,(root/spec['prompt']).read_text())
        human=graph();ai=graph()
        for node in ai['concepts']:node['intro_by']='ai'
        self.assertEqual(rr.graph_context(human)['intro_protected'],['c1','c2','c3'])
        self.assertEqual(rr.graph_context(ai)['intro_protected'],[])

class ModelHttpTests(creation_tests.Fixture):
    serve=creation_tests.HttpTests.serve
    post=creation_tests.HttpTests.post

    def test_new_http_create_revision_preview_and_confirm_have_explicit_scope(self):
        port=self.serve()
        pid=self.app.create_project('http',keywords=['world model'])['project_id']
        with mock.patch.dict('os.environ',{'PAGETIDE_DATA':str(self.app.data)}):
            with mock.patch('app.gateway.Gateway.call',return_value=reply(CREATE)) as called:
                status,created=self.post(port,'/api/route',{'action':'brief-plan','project_id':pid,'brief':BRIEF})
                self.assertEqual(status,200);self.assertTrue(created['ok']);self.assertEqual(called.call_args.args[0],rr.CREATE_OPERATION)
            status,saved=self.post(port,'/api/route',{'action':'save','project_id':pid,'graph':created['graph'],'brief':BRIEF,'revision':0})
            self.assertEqual(status,200)
            with mock.patch('app.gateway.Gateway.call',return_value=reply(patch())) as called:
                status,result=self.post(port,'/api/route',{'action':'revision-generate','project_id':pid,'revision':saved['revision'],'brief':{**BRIEF,'structure':'老师新意见'}})
                self.assertEqual(status,200);self.assertTrue(result['ok']);self.assertEqual(called.call_args.args[0],rr.REVISION_OPERATION)
            status,pending=self.post(port,'/api/route',{'action':'revision-draft','project_id':pid})
            self.assertEqual(status,200);self.assertEqual(pending['draft']['draft_id'],result['preview']['draft_id'])
            status,done=self.post(port,'/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':pending['draft']['draft_id']})
            self.assertEqual(status,200);self.assertEqual(done['brief']['structure'],'老师新意见')

    def test_valid_full_graph_above_response_cap_remains_manually_saveable(self):
        ids=[str(i).zfill(3)+'甲'*197 for i in range(40)]
        graph={'concepts':[{'id':identity,'name':'Task '+str(i),'terms':['topic '+str(i)],'hint':2,'state':'active'} for i,identity in enumerate(ids)],
               'prereqs':[{'from':ids[j],'to':ids[i]} for i in range(1,40) for j in range(max(0,i-3),i)],'targets':[ids[-1]]}
        pid=self.app.create_project('Large identity fixture',keywords=['task'])['project_id']
        body={'action':'save','project_id':pid,'graph':graph,'revision':0}
        self.assertGreater(len(json.dumps(body,ensure_ascii=False).encode()),131072)
        port=self.serve()
        with mock.patch.dict('os.environ',{'PAGETIDE_DATA':str(self.app.data)}),mock.patch('app.gateway.Gateway.call') as called:
            status,saved=self.post(port,'/api/route',body)
            self.assertEqual(status,200);self.assertEqual(len(saved['graph']['concepts']),40)
            self.assertEqual(len(saved['graph']['prereqs']),114);called.assert_not_called()

    def test_unapproved_or_disabled_new_operation_sends_no_provider_request(self):
        port=self.serve()
        with mock.patch.dict('os.environ',{'PAGETIDE_DATA':str(self.app.data)}),mock.patch('app.gateway.urllib.request.urlopen',side_effect=AssertionError('no model network')):
            # urllib client itself needs urlopen, so HTTP use http.client instead.
            import http.client
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            for disabled,code in [(False,'not_approved'),(True,'ai_off')]:
                self.app.gateway.set_enabled(not disabled)
                cfg=json.loads((self.root/'harness/budget.json').read_text())
                cfg['operations'][rr.CREATE_OPERATION]['owner_approved']=False
                (self.root/'harness/budget.json').write_text(json.dumps(cfg))
                conn.request('POST',f'/api/project-guidance/sessions/{self.session}/route',json.dumps({'brief':BRIEF}),{'Content-Type':'application/json'})
                response=conn.getresponse();value=json.loads(response.read());self.assertEqual(response.status,200)
                self.assertEqual(value['reason_code'],code);self.assertEqual(self.app.route_plan_state(self.session)['attempts'],0)
            conn.close()

    def test_raw_duplicate_fields_and_oversized_session_request_refused_before_model(self):
        import http.client
        port=self.serve();conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        with mock.patch.dict('os.environ',{'PAGETIDE_DATA':str(self.app.data)}),mock.patch('app.gateway.Gateway.call') as called:
            for body in ['{"brief":{"goal":"first","goal":"second"}}','{"brief":{"goal":"'+('a'*131072)+'"}}']:
                conn.request('POST',f'/api/project-guidance/sessions/{self.session}/route',body,{'Content-Type':'application/json'})
                response=conn.getresponse();response.read();self.assertEqual(response.status,400)
            status,_=self.post(port,f'/api/project-guidance/sessions/{self.session}/route',{'brief':BRIEF,'boundary':{}})
            self.assertEqual(status,400)
            for options in [{'regenerate':'false'},{'dry_run':1}]:
                status,_=self.post(port,f'/api/project-guidance/sessions/{self.session}/route',{'brief':BRIEF,**options})
                self.assertEqual(status,400)
            called.assert_not_called()
        conn.close()
