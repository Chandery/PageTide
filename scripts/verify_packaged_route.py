"""Verify the freshly built backend against disposable language/quality fixtures.

Usage: python3 scripts/verify_packaged_route.py <bundled-backend-executable>
No provider calls, live source requests or real library access. Cached public
metadata fixtures exercise candidate refresh. This is a backend
package check, not a native-window or recommendation-value evaluation.
"""
import hashlib
from collections import Counter
import http.cookiejar
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.service import App
from app import route_recall


def read_line(stream, timeout):
    """One line from a pipe within `timeout` seconds, or None (select.select cannot wait on pipes on Windows)."""
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        return None


def launch(executable, data, home, check):
    env = dict(os.environ, PAPERDIGHELPER_DATA=str(data), PAPERDIGHELPER_KEY_FILE=str(home/'missing-key.env'), DEEPSEEK_API_KEY='', PDH_DEV='0',
               http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9',
               HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
               NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
    # Preserve HOME and replace the inherited KEY_FILE with a private absent path.
    # The private data/bundled resources also contain no keys; AI_DISABLED blocks calls.
    assert env.get('HOME') == os.environ.get('HOME')
    with tempfile.TemporaryFile(mode='w+') as errors:
        process = subprocess.Popen([str(executable)], cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            line = read_line(process.stdout, 30)
            if line is None:
                raise AssertionError('Backend did not announce readiness')
            if not line.startswith('PDH_READY '):
                errors.seek(0)
                raise AssertionError('Backend startup failed: '+errors.read()[-1000:])
            url = line.strip().split(' ',1)[1]; base=url.split('/_desktop/',1)[0]
            try:
                urllib.request.urlopen(base+'/api/state', timeout=10)
            except urllib.error.HTTPError as exc:
                assert exc.code==403; exc.close()
            else:
                raise AssertionError('Unauthenticated API was accessible')
            opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with opener.open(url,timeout=10) as response: assert response.status==200
            def call(path, payload=None, raw=False):
                request=urllib.request.Request(base+path, data=json.dumps(payload).encode() if payload is not None else None,
                    headers={'Content-Type':'application/json'})
                with opener.open(request,timeout=15) as response: body=response.read()
                return body.decode() if raw else json.loads(body)
            check(call)
            process.stdin.close(); assert process.wait(timeout=15)==0
            errors.seek(0); assert 'PDH_BOOTSTRAP_FAILED' not in errors.read()
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=5)
            process.stdout.close()
            if not process.stdin.closed: process.stdin.close()


def main():
    executable=Path(sys.argv[1]).resolve(); assert executable.is_file()
    with tempfile.TemporaryDirectory(prefix='pdh-packaged-route-') as tmp:
        root=Path(tmp); data=root/'data'; home=root/'home';home.mkdir();data.mkdir()
        marker=home/'default-library-marker'; marker.write_bytes(b'untouched default library')
        (data/'AI_DISABLED').touch()
        app=App(data_dir=data)
        pid=app.create_project('Quality fixture',keywords=['model'],language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        pending=app.create_project('Legacy pending')['project_id']
        route_pid=app.create_project('Goal fixture',keywords=['model'],language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        recall_pid=app.create_project('Recall fixture',keywords=['recall topic'],language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        batch_pid=app.create_project('Batch fixture',keywords=['epitaxy','photonic calibration'],language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        batch_route=app.route_save(batch_pid,plan={'concepts':[
            {'id':'a','name':'Crystal foundation','terms':['crystal lattice'],'hint':1,'needs':[]},
            {'id':'b','name':'Epitaxy task','terms':['epitaxy'],'hint':2,'needs':['a']}], 'targets':['b']})
        batch_ids={c['name']:c['id'] for c in batch_route['graph']['concepts']}
        app.route_manual(batch_pid,batch_ids['Crystal foundation'],'mastered')
        app.route_watch(batch_pid,batch_ids['Crystal foundation'],True)
        app.store.upsert_papers([{'key':kind+str(i),'title':term+' study '+str(i),'abstract':term+' methods and measurement',
                 'language':'en','published':'2026-01-01'} for kind,term in [('bp','epitaxy'),('bx','photonic calibration'),('bw','crystal lattice')] for i in range(6)],batch_pid)
        def cache_batch_exploration(fixture_app):
            # Synthetic cached public query results, rather than purposeless fillers.
            state={}
            public=[dict(fixture_app.store.paper('bx'+str(i))) for i in range(6)]
            for _ in range(8):
                planned=fixture_app._route_recall_plan(batch_pid,fixture_app.route_get(batch_pid),state)
                results=[(q,public if q['query']=='photonic calibration' else []) for q in planned['queries']]
                state=route_recall.record(planned,state,results,time.time())
                if any(q['query']=='photonic calibration' for q in planned['queries']):
                    fixture_app.store.set_setting('route_recall_'+batch_pid,state)
                    assert fixture_app.route_recall_sources(batch_pid)['bx0'][0]['query']=='photonic calibration'
                    return
            raise AssertionError('Synthetic public exploration query was not planned')
        cache_batch_exploration(app)
        recall=app.route_save(recall_pid,plan={'concepts':[
            {'id':'a','name':'Recall foundations','terms':['recall foundations'],'hint':1,'needs':[]},
            {'id':'b','name':'Recall methods','terms':['recall methods'],'hint':2,'needs':['a']},
            {'id':'c','name':'Recall evaluation','terms':['recall evaluation'],'hint':2,'needs':['a']}], 'targets':['b','c']})
        recall_ids={c['name']:c['id'] for c in recall['graph']['concepts']}
        app.route_manual(recall_pid,recall_ids['Recall foundations'],'mastered')
        app.route_watch(recall_pid,recall_ids['Recall foundations'],True)
        # Populate every URL required by three future refreshes. The frozen
        # backend must read these fixtures; its outbound proxy cannot go live.
        def cached_fixture(url, **kwargs):
            digest=hashlib.sha256(url.encode()).hexdigest()[:16]
            number=int(digest[:8],16)
            payload={'results':[{'id':f'https://openalex.org/W{number}{i:02d}',
                'title':f'Recall public study {number} {i}', 'publication_date':'2026-01-01',
                'language':'en','ids':{}} for i in range(50)]}
            (app.source.cache/(digest+'.json')).write_text(json.dumps(payload))
            return payload
        recall_state={}; recall_plans=[]
        with mock.patch.object(app.source,'_fetch',side_effect=cached_fixture):
            for _ in range(3):
                planned=app._route_recall_plan(recall_pid,app.route_get(recall_pid),recall_state)
                fetched=[(q,app.source.discover_topic(q['query'],**{k:q[k] for k in ('order','from_date','to_date','per_page','page')})) for q in planned['queries']]
                recall_plans.append(planned['queries'])
                recall_state=route_recall.record(planned,recall_state,fetched,time.time())
        papers=[{'key':key,'title':'Model study '+key,'abstract':abstract,'language':lang,'published':'2026-01-01'}
                for key,lang,abstract in [('en','en','Useful model learning abstract'),('zh','zh','有效中文论文摘要'),
                    ('unknown',None,'An English abstract is not a language report'),('link','en',''),('body','en','')]]
        papers[3]['oa']={'pdf_urls':['https://example.org/link.pdf']}
        app.store.upsert_papers(papers,pid)
        app.store.add_project_paper(pending,'link','imported')
        app.store.create_batch('2026-01-01',['link'],project_id=pending)
        # Internal version/fulltext fixtures bypass the import boundary; they do not test valid PDF acceptance.
        pdf=data/'body.pdf'; raw=b'%PDF-1.4\nversioned fixture\n%%EOF';pdf.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest();app.store.record_pdf('body',pdf,sha256=sha)
        app.save_fulltext('body',[{'page':1,'text':'Meaningful model learning and prediction. '*20}],source_pdf_sha256=sha)
        body_pid=app.create_project('Body match fixture',language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        body_map=app.route_save(body_pid,plan={'concepts':[{'id':'a','name':'Prediction','terms':['prediction'],'hint':1,'needs':[]}],'targets':['a']})
        body_unit=body_map['graph']['concepts'][0]['id']
        app.store.save_to_library('body',project_id=body_pid)
        for key,pages in [('late-page',[{'page':7,'text':'Meaningful model learning. '*30}]),
                          ('late-text',[{'page':1,'text':'.'*2000+'Meaningful model learning. '*30}])]:
            app.store.upsert_papers([{'key':key,'title':key,'abstract':'','language':'en','published':'2026-01-01'}],pid)
            path=data/(key+'.pdf'); content=b'%PDF-1.4\n'+key.encode()+b'\n%%EOF';path.write_bytes(content)
            version=hashlib.sha256(content).hexdigest();app.store.record_pdf(key,path,sha256=version)
            app.save_fulltext(key,pages,source_pdf_sha256=version)
        growth_pid=app.create_project('Growth fixture',keywords=['growth'],language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        growth_map=app.route_save(growth_pid,plan={'concepts':[
            {'id':'a','name':'Growth basis','terms':['growth basis'],'hint':1,'needs':[]},
            {'id':'b','name':'Growth goal','terms':['growth goal'],'hint':2,'needs':['a']}], 'targets':['b']})
        for concept in growth_map['graph']['concepts']:
            if concept['name']=='Growth goal':
                concept.update(intro='Calibration task is required before Growth goal.',intro_by='user')
        growth_map=app.route_save(growth_pid,graph=growth_map['graph'])
        for concept in growth_map['graph']['concepts']:
            app.route_manual(growth_pid,concept['id'],'mastered')
        app.store.upsert_papers([{'key':'growth-proof','title':'Calibration method',
            'abstract':'Calibration method and measurement techniques','language':'en'}],growth_pid)
        app.record_feedback('growth-proof','useful',project_id=growth_pid)
        # Public fixture answer creates a local proposal; no claim of real model quality.
        fixture={'results':[{'papers':['p1'],'verdict':'missing_prerequisite','name':'Calibration task',
            'terms':['calibration'],'intro':'A prerequisite calibration task','barrier':'Measurement basics',
            'needs':[],'required_by':['c2'],'reason':'Fixture prerequisite',
            'necessity':[{'node':'c2','quote':'Calibration task is required before Growth goal.'}]}]}
        def public_fixture_reply(operation,messages,**kwargs):
            assert operation == 'route_growth_judge'
            body = json.loads(messages[-1]['content'])
            result = dict(fixture['results'][0])
            result['evidence'] = {}
            for alias in result['papers']:
                record = body['papers'][alias]
                sid = next(sid for sid, option in record['snippets'].items()
                           if option['field'] == 'abstract' and option['text'] == record['abstract'])
                result['evidence'][alias] = {'snippet':sid,'type':'unknown'}
            return {'ok':True,'content':json.dumps({'results':[result]})}
        with mock.patch.object(app.gateway,'call',side_effect=public_fixture_reply):
            proposal=app.route_direction_judge(growth_pid)
        growth_id=proposal['results'][0]['direction']
        assert proposal['ok'] and growth_id, proposal
        app.store.add_project_paper(route_pid,'en','shared')
        app.store.save_to_library('en',project_id=route_pid)
        queue_pid=app.create_project('Whole queue fixture',language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        app.route_save(queue_pid,plan={'concepts':[{'id':'basis','name':'Queue basis','terms':['basis'],'hint':1,'needs':[]}], 'targets':['basis']})
        for number in range(20):
            key='queue-'+str(number)
            app.store.upsert_papers([{'key':key,'title':'Queue paper '+str(number),'abstract':'Public synthetic study metadata','language':'en'}],queue_pid)
            app.record_feedback(key,'useful',project_id=queue_pid)
        app.store.close()
        def refresh(call, expected):
            job=call('/api/refresh',{'project_id':recall_pid})
            deadline=time.monotonic()+15
            while job['state']=='running' and time.monotonic()<deadline:
                time.sleep(.05); job=call('/api/jobs/'+job['id'])
            assert job['state']=='done',job
            result=job['result']
            assert result['errors']==[],result
            assert result['fetched']>0 and result['query_plan']==expected,result
        def first(call):
            pending_queue=call('/api/route',{'action':'candidates','project_id':queue_pid})
            assert len(pending_queue['pending'])==20 and pending_queue['judges_left']==10
            refused_queue=call('/api/route',{'action':'direction-judge','project_id':queue_pid})
            assert refused_queue['reason_code']=='ai_off'
            assert (refused_queue['requested'],refused_queue['processed'],refused_queue['complete'],refused_queue['pending'],refused_queue['judges_left'])==(20,0,False,20,10)
            assert 'judgeProgress' in call('/route-editor.js',raw=True)
            listed=call('/api/route',{'action':'candidates','project_id':growth_pid})
            candidate=next(c for c in listed['candidates'] if c['id']==growth_id)
            assert candidate['can_accept'] and candidate['goal_impact']=='adds_prerequisite', candidate
            accepted=call('/api/route',{'action':'candidate-accept','project_id':growth_pid,'candidate':growth_id,'revision':listed['revision']})
            assert accepted['goal_status']=='learning' and accepted['goal_total']==3
            restored=call('/api/route',{'action':'undo','project_id':growth_pid,'revision':accepted['revision']})
            assert restored['goal_status']=='completed' and restored['goal_total']==2
            graph=restored['graph'];graph['concepts'][0]['name']='Changed basis'
            call('/api/route',{'action':'save','project_id':growth_pid,'graph':graph,'revision':restored['revision']})
            stale=call('/api/route',{'action':'candidates','project_id':growth_pid})['candidates'][0]
            assert stale['stale'] and not stale['can_accept']
            refused=call('/api/route',{'action':'direction-judge','project_id':growth_pid})
            assert not refused['ok'] and refused['reason_code']=='ai_off'
            assert 'judgementsHTML' in call('/route-editor.js',raw=True)
            refresh(call,recall_plans[0])
            full=call('/api/daily',{'project_id':batch_pid})
            assert Counter(c['route']['kind'] for c in full['cards'])=={'route':3,'explore':1,'watch':1},full
            selected=next(c['key'] for c in full['cards'] if c['route']['kind']=='explore')
            selected_card=next(c for c in full['cards'] if c['key']==selected)
            assert selected_card['route']['exploration_evidence']['query']=='photonic calibration'
            saved=call('/api/feedback',{'key':selected,'action':'useful','project_id':batch_pid})
            detail=call('/api/detail',{'key':selected,'project_id':batch_pid})['context']
            assert detail['saved_in_project'] and detail['units']==[] and detail['recommendation']['kind']=='explore'
            drawn=call('/api/organization',{'action':'route-detail','project_id':batch_pid,'focus_key':selected})
            assert selected in drawn['unmatched'] and drawn['unmatched_total']>=1
            call('/api/undo',{'feedback_id':saved['feedback_id'],'project_id':batch_pid})
            assert call('/api/detail',{'key':selected,'project_id':batch_pid})['context']['saved_in_project']
            assert 'data-action="graph-navigate"' in call('/paper-context.js',raw=True)
            assert '/paper-context.js' in call('/',raw=True)
            route=call('/api/route?project_id='+batch_pid)
            completed=call('/api/route',{'action':'manual','project_id':batch_pid,'concept':batch_ids['Epitaxy task'],'value':'mastered','revision':route['revision']})
            assert completed['goal_status']=='completed'
            fixture_app=App(data_dir=data)
            try:
                cache_batch_exploration(fixture_app)
            finally:
                fixture_app.store.close()
            discovery=call('/api/daily',{'project_id':batch_pid})
            assert len(discovery['cards'])==1 and discovery['cards'][0]['route']['kind']=='explore'
            repeated=call('/api/daily',{'project_id':batch_pid,'run_date':'2099-01-01'})
            assert repeated['reused'] and repeated['batch_id']==discovery['batch_id']
            assert repeated['reason_code']=='completed_daily_limit'
            assert 'function dailyButtonText()' in call('/',raw=True)
            assert 'const languages' in call('/paper-policy.js',raw=True)
            assert 'getData' in call('/reader-source.js',raw=True)
            blocked=call('/api/daily',{'project_id':pending})
            assert blocked['batch_id'] is None and blocked['reason_code']=='language_policy_required'
            assert call('/api/state?project_id='+pending)['cards'][0]['key']=='link'
            batch=call('/api/daily',{'project_id':pid})
            assert {p['key'] for p in batch['cards']}=={'en','body'}
            assert all(p['language']['fulltext_status']=='unverified' for p in batch['cards'])
            assert batch['eligibility']['excluded']=={'language_not_allowed':1,'language_unknown':1,'no_readable_content':3}
            assert call('/api/fulltext?key=body&text=1&source_pdf_sha256='+sha)['pages']==1
            policy=call('/api/projects/'+pid,{'action':'language','discipline':'humanities','allowed_languages':['zh']})
            assert policy['project']['language_policy']['allowed_languages']==['zh']
            assert {p['key'] for p in call('/api/state?project_id='+pid)['cards']}=={'en','body'}
            assert [p['key'] for p in call('/api/daily',{'project_id':pid})['cards']]==['zh']
            body_context=call('/api/detail',{'key':'body','project_id':body_pid})['context']
            assert body_context['units']==[{'id':body_unit,'name':'Prediction'}] and body_context['matching_source']=='local_body'
            body_graph=call('/api/organization',{'action':'route-detail','project_id':body_pid})
            assert [(m['paper'],m['unit'],m['source'],m['terms']) for m in body_graph['matches']]==[('body',body_unit,'local_body',['prediction'])]
            assert body_graph['pending']==[] and body_graph['unmatched']==[]
            call('/api/route',{'action':'mode','project_id':body_pid,'mode':'off','revision':body_map['revision']})
            assert call('/api/detail',{'key':'body','project_id':body_pid})['context']['units']==body_context['units']
            pdf.write_bytes(b'%PDF-1.4\nchanged externally\n%%EOF')
            assert call('/api/fulltext?key=body&text=1')['pages']==0
            assert call('/api/detail',{'key':'body','project_id':body_pid})['context']['units']==[]
            changed=call('/api/organization',{'action':'route-detail','project_id':body_pid})
            assert changed['matches']==[] and changed['unmatched']==['body']
            plan={'concepts':[
                {'id':'a','name':'Model basics','terms':['model basics'],'hint':1,'needs':[]},
                {'id':'b','name':'Model prediction','terms':['model prediction'],'hint':2,'needs':['a']},
                {'id':'side','name':'Model rendering','terms':['model rendering'],'hint':2,'needs':['a']}], 'targets':['b']}
            saved=call('/api/route',{'action':'save','project_id':route_pid,'plan':plan})
            ids={c['name']:c['id'] for c in saved['graph']['concepts']}
            assert (saved['goal_status'],saved['goal_total'])==('learning',2)
            assert ids['Model rendering'] not in saved['goal_scope']
            cid=ids['Model prediction']
            watched=call('/api/route',{'action':'watch','project_id':route_pid,'concept':cid,'value':True,'revision':saved['revision']})
            assert watched['watch']==[cid] and watched['watched_satisfied']==[]
            for name in ['Model basics','Model prediction']:
                watched=call('/api/route',{'action':'manual','project_id':route_pid,'concept':ids[name],'value':'mastered','revision':watched['revision']})
            assert watched['goal_status']=='completed' and watched['watched_satisfied']==[cid]
            assert watched['progress'][ids['Model rendering']]['status']=='unlocked'
            cleared=call('/api/route',{'action':'watch','project_id':route_pid,'concept':cid,'value':False,'revision':watched['revision']})
            undone=call('/api/route',{'action':'undo','project_id':route_pid,'revision':cleared['revision']})
            assert undone['watch']==[cid]
            switched=call('/api/route',{'action':'mode','project_id':route_pid,'mode':'off','revision':undone['revision']})
            assert switched['watch']==[cid] and not switched['enabled']
            context=call('/api/detail',{'key':'en','project_id':route_pid})['context']
            assert context['map_available'] and context['saved_in_project'] and not context['route_enabled']
            assert context['project_id']==route_pid
            assert 'data-route-watch' in call('/route-editor.js',raw=True)
            draft=call('/api/route',{'action':'revision-preview','project_id':route_pid,'revision':switched['revision'],
                'brief':{'goal':'Revision fixture','structure':'Add a side task'},'patch':{'operations':[
                    {'op':'update_node','ref':'c1','changes':{'name':'Revised model basics'}},
                    {'op':'add_node','ref':'n1','node':{'name':'New side task','terms':['new side task']}}]}})
            assert call('/api/route?project_id='+route_pid)['graph']==switched['graph']
            assert draft['after']['goal_status']=='learning' and draft['changes']['reset']
            confirmed=call('/api/route',{'action':'revision-confirm','project_id':route_pid,'draft_id':draft['draft_id']})
            assert confirmed['graph']==draft['after']['graph'] and confirmed['brief']['goal']=='Revision fixture'
            assert confirmed['watch']==[cid] and ids['Model basics'] not in confirmed['manual']
            assert all(type(c['progress_since_feedback_id']) is int for c in confirmed['graph']['concepts'] if c['id'] in draft['changes']['reset'])
            assert call('/api/route',{'action':'revision-confirm','project_id':route_pid,'draft_id':draft['draft_id']})['duplicate']
            restored=call('/api/route',{'action':'undo','project_id':route_pid,'revision':confirmed['revision']})
            for field in ['graph','manual','watch','brief']:
                assert restored.get(field)==switched.get(field),field
            call('/api/route',{'action':'revision-preview','project_id':route_pid,'revision':restored['revision'],
                'brief':{'goal':'Persist pending revision'},'patch':{'operations':[]}})
        launch(executable,data,home,first)
        def brief_contract(call):
            brief={'goal':'Learn latent models','known':'Teacher says background is strong','structure':'Probability before latent models'}
            session=call('/api/project-guidance/sessions',{'name':'Brief fixture','goal':'Learn latent models'})['session']
            endpoint='/api/project-guidance/sessions/'+session['id']+'/route'
            for disabled,reason in [(True,'ai_off'),(False,'no_key')]:
                if disabled:(data/'AI_DISABLED').touch()
                else:(data/'AI_DISABLED').unlink()
                refused=call(endpoint,{'brief':brief})
                assert not refused['ok'] and refused['reason_code']==reason
                refused=call('/api/route',{'action':'revision-generate','project_id':route_pid,'brief':brief})
                assert not refused['ok'] and refused['reason_code']==reason
            (data/'AI_DISABLED').touch()
            graph={'concepts':[{'id':'manual-one','name':'Probability','terms':['probability'],'hint':2,'state':'active'},
                               {'id':'manual-two','name':'Latent model','terms':['latent model'],'hint':1,'state':'active'}],
                   'prereqs':[{'from':'manual-one','to':'manual-two'}],'targets':['manual-two']}
            created=call('/api/project-guidance/sessions/'+session['id']+'/finalize',
                         {'selected_keys':[],'route':{'graph':graph,'mastered':[],'brief':brief}})
            saved=call('/api/route?project_id='+created['project_id'])
            assert saved['brief']['known']==brief['known'] and saved['manual']=={}
            assert len(saved['graph']['prereqs'])==1 and saved['graph']['targets']==['manual-two']
            assert 'data-brief' in call('/route-brief.js',raw=True)
            page=call('/route-page.js',raw=True)
            assert "action: 'revision-generate'" in page and "action: 'brief-plan'" in page
            assert "action: 'plan'" not in page and "action: 'revision-confirm', draft_id: preview.draft_id" in page
            assert 'mapBrief' in call('/project_creation.html',raw=True)
        launch(executable,data,home,brief_contract)
        def restart(call):
            stale=call('/api/route',{'action':'candidates','project_id':growth_pid})['candidates'][0]
            assert stale['stale'] and not stale['can_accept']
            daily=call('/api/daily',{'project_id':batch_pid})
            assert daily['reused'] and daily['reason_code']=='completed_daily_limit' and len(daily['cards'])==1
            refresh(call,recall_plans[1])
            refresh(call,recall_plans[2])
            projects=call('/api/projects')['projects']; project=next(p for p in projects if p['id']==pid)
            assert project['language_policy']['discipline']=='humanities'
            assert project['language_policy']['allowed_languages']==['zh']
            assert [p['key'] for p in call('/api/state?project_id='+pid)['cards']]==['zh']
            stored=call('/api/route?project_id='+route_pid)
            assert stored['watch']==[stored['graph']['targets'][0]] and not stored['enabled']
            pending_revision=call('/api/route',{'action':'revision-draft','project_id':route_pid})['draft']
            assert not pending_revision['stale'] and not pending_revision['confirmed']
            changed=call('/api/route',{'action':'watch','project_id':route_pid,'concept':stored['graph']['targets'][0],
                'value':False,'revision':stored['revision']})
            try:
                call('/api/route',{'action':'revision-confirm','project_id':route_pid,'draft_id':pending_revision['draft_id']})
            except urllib.error.HTTPError as exc:
                assert exc.code==409;exc.close()
            else:raise AssertionError('Stale revision confirmed')
            assert call('/api/route',{'action':'revision-draft','project_id':route_pid})['draft']['draft_id']==pending_revision['draft_id']
            stored=call('/api/route',{'action':'undo','project_id':route_pid,'revision':changed['revision']})
            resumed=call('/api/route',{'action':'mode','project_id':route_pid,'mode':'route','revision':stored['revision']})
            assert resumed['goal_status']=='completed' and resumed['watch']==resumed['watched_satisfied']
            org=call('/api/organization')
            assert route_pid in org['route_projects'] and batch_pid in org['route_projects']
        launch(executable,data,home,restart)
        assert marker.read_bytes()==b'untouched default library'
        assert not (home/'Library/Application Support/PaperDigHelper').exists()
        inspected=App(data_dir=data)
        try:
            provenance=inspected.route_recall_sources(recall_pid)
            assert provenance and len(provenance)<=route_recall.MAX_SOURCE_PAPERS
            assert all(len(v)<=route_recall.MAX_PAPER_SOURCES for v in provenance.values())
            assert any(e['page']==2 for entries in provenance.values() for e in entries)
        finally:
            inspected.store.close()
    print('PASS fresh packaged backend: authentication, pending/history, STEM/humanities, shared quality, body bounds, versioned text, goal scope, watch/mastery, undo/mode/restart, batch 3+1+1, completed daily discovery/reuse/restart, cached three-purpose refresh, rotation/paging/provenance after restart, typed growth preview/confirm/goal-reopen/undo/stale/restart/AI-off fallback, revision preview/stable new IDs/cutoff/atomic confirm/idempotence/undo/pending restart/409 draft retention, shared brief assets/manual creation/known-not-mastery/owner-approved new-operation AI-off and no-key no-call, whole-queue20 AI-off pending/refund/current assets, isolated DATA and absent key, HOME preserved, outbound network blocked')


if __name__=='__main__': main()
