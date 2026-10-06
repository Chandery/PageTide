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
import select
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.service import App
from app import route_recall


def launch(executable, data, home, check):
    env = dict(os.environ, HOME=str(home), PAPERDIGHELPER_DATA=str(data), DEEPSEEK_API_KEY='', PDH_DEV='0',
               http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9',
               HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
               NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
    with tempfile.TemporaryFile(mode='w+') as errors:
        process = subprocess.Popen([str(executable)], cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            if not select.select([process.stdout], [], [], 30)[0]:
                raise AssertionError('Backend did not announce readiness')
            line = process.stdout.readline()
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
        batch_pid=app.create_project('Batch fixture',keywords=['epitaxy'],language_policy={'discipline':'stem','allowed_languages':['en']})['project_id']
        batch_route=app.route_save(batch_pid,plan={'concepts':[
            {'id':'a','name':'Crystal foundation','terms':['crystal lattice'],'hint':1,'needs':[]},
            {'id':'b','name':'Epitaxy task','terms':['epitaxy'],'hint':2,'needs':['a']}], 'targets':['b']})
        batch_ids={c['name']:c['id'] for c in batch_route['graph']['concepts']}
        app.route_manual(batch_pid,batch_ids['Crystal foundation'],'mastered')
        app.route_watch(batch_pid,batch_ids['Crystal foundation'],True)
        app.store.upsert_papers([{'key':kind+str(i),'title':term+' study '+str(i),'abstract':term+' methods and measurement',
                 'language':'en','published':'2026-01-01'} for kind,term in [('bp','epitaxy'),('bx','photonic calibration'),('bw','crystal lattice')] for i in range(6)],batch_pid)
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
        pdf=data/'body.pdf'; raw=b'%PDF-1.4\nversioned fixture\n%%EOF';pdf.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest();app.store.record_pdf('body',pdf,sha256=sha)
        app.save_fulltext('body',[{'page':1,'text':'Meaningful model learning and prediction. '*20}],source_pdf_sha256=sha)
        for key,pages in [('late-page',[{'page':7,'text':'Meaningful model learning. '*30}]),
                          ('late-text',[{'page':1,'text':'.'*2000+'Meaningful model learning. '*30}])]:
            app.store.upsert_papers([{'key':key,'title':key,'abstract':'','language':'en','published':'2026-01-01'}],pid)
            path=data/(key+'.pdf'); content=b'%PDF-1.4\n'+key.encode()+b'\n%%EOF';path.write_bytes(content)
            version=hashlib.sha256(content).hexdigest();app.store.record_pdf(key,path,sha256=version)
            app.save_fulltext(key,pages,source_pdf_sha256=version)
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
            refresh(call,recall_plans[0])
            full=call('/api/daily',{'project_id':batch_pid})
            assert Counter(c['route']['kind'] for c in full['cards'])=={'route':3,'explore':1,'watch':1},full
            route=call('/api/route?project_id='+batch_pid)
            completed=call('/api/route',{'action':'manual','project_id':batch_pid,'concept':batch_ids['Epitaxy task'],'value':'mastered','revision':route['revision']})
            assert completed['goal_status']=='completed'
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
            pdf.write_bytes(b'%PDF-1.4\nchanged externally\n%%EOF')
            assert call('/api/fulltext?key=body&text=1')['pages']==0
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
            assert 'data-route-watch' in call('/route-editor.js',raw=True)
        launch(executable,data,home,first)
        def restart(call):
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
            resumed=call('/api/route',{'action':'mode','project_id':route_pid,'mode':'route','revision':stored['revision']})
            assert resumed['goal_status']=='completed' and resumed['watch']==resumed['watched_satisfied']
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
    print('PASS fresh packaged backend: authentication, pending/history, STEM/humanities, shared quality, body bounds, versioned text, goal scope, watch/mastery, undo/mode/restart, batch 3+1+1, completed daily discovery/reuse/restart, cached three-purpose refresh, rotation/paging/provenance after restart, assets, isolated HOME, outbound network blocked')


if __name__=='__main__': main()
