"""Verify the freshly built backend against disposable language/quality fixtures.

Usage: python3 scripts/verify_packaged_route.py <bundled-backend-executable>
No provider calls, candidate refresh or real library access. This is a backend
package check, not a native-window or recommendation-value evaluation.
"""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.service import App


def launch(executable, data, home, check):
    env = dict(os.environ, HOME=str(home), PAPERDIGHELPER_DATA=str(data), DEEPSEEK_API_KEY='', PDH_DEV='0')
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
        def first(call):
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
        launch(executable,data,home,first)
        def restart(call):
            projects=call('/api/projects')['projects']; project=next(p for p in projects if p['id']==pid)
            assert project['language_policy']['discipline']=='humanities'
            assert project['language_policy']['allowed_languages']==['zh']
            assert [p['key'] for p in call('/api/state?project_id='+pid)['cards']]==['zh']
        launch(executable,data,home,restart)
        assert marker.read_bytes()==b'untouched default library'
        assert not (home/'Library/Application Support/PaperDigHelper').exists()
    print('PASS fresh packaged backend: authentication, pending/history, STEM/humanities, shared quality, body bounds, versioned text, assets, restart, isolated HOME')


if __name__=='__main__': main()
