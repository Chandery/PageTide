#!/usr/bin/env python3
"""Isolated real-provider regression after audit bug fixes. Adapted from the original audit. Never edits live data.

Run with the pinned local tokenizer environment. Receipts stay private under
.local/ai-fixes-20261008/real-ai; only a sanitized report belongs in Git.
No request is retried. A capture-only pass must precede a live pass.
"""
import argparse
import base64
import copy
import datetime
import fcntl
import hashlib
import json
import os
import sys
import traceback
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.service import App
from app.gateway import Gateway, request_envelope, input_bound
from app.organization import Organization
from app.category_review_service import run_review

BASE = ROOT / '.local/ai-fixes-20261008/real-ai'
OLD_BASE = Path('/Users/chandery/.codex/worktrees/multidiscipline-audit/PaperDigHelper/.local/multidiscipline-audit-20261007/ai')
KEY = Path('/Users/chandery/Library/Application Support/PageTide/deepseek.env')
TOKENIZER = Path('/Users/chandery/PaperDigHelper/.local/route-native-20261007/tokenizer/deepseek_v4_tokenizer/tokenizer.json')
SENTINEL = 'AUDIT_PRIVATE_NOTE_DO_NOT_SEND'
SOFT_TOKENS = 3_000_000
SOFT_USD = Decimal('2.00')
EXPECTED_CALLS = {'project_guidance':63, 'route_map_create':18,
    'route_map_revision':18, 'concept_intro':18, 'daily_triage':18,
    'paper_qa':36, 'paper_vision_qa':18, 'selection_translate':18,
    'route_growth_judge':63, 'category_review':45}


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
    temp.chmod(0o600)
    temp.replace(path)


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class AuditGateway:
    """One shared real Gateway; validation is test-side, not an app modification."""
    def __init__(self, gateway, tokenizer, live):
        self.shared = gateway
        self.config = gateway.config
        self.tokenizer = tokenizer
        self.live = live
        self.case = None
        self.requests = []
        self.halt = None

    def __getattr__(self, name):
        return getattr(self.shared, name)

    def start(self, case):
        self.case = case
        self.requests = []

    def inspect(self, operation, messages):
        op = self.config['operations'][operation]
        envelope = request_envelope(operation, self.config['provider']['model'], op['cap']['output'], messages)
        wire = json.dumps(envelope, ensure_ascii=False)
        # Count text plus a separately documented upper bound for the one image.
        counted = copy.deepcopy(envelope)
        images = []
        for message in counted['messages']:
            if isinstance(message.get('content'), list):
                parts = []
                for part in message['content']:
                    if part.get('type') == 'image_url':
                        url = part['image_url']['url']
                        if not url.startswith('data:image/') or len(url) > 8 * 1024 * 1024:
                            raise ValueError('non-inline or oversized image')
                        base64.b64decode(url.split(',', 1)[1], validate=True)
                        images.append({'sha256':hashlib.sha256(url.encode()).hexdigest(), 'data_url_chars':len(url)})
                    else:
                        parts.append(part)
                message['content'] = parts
        if images and (operation != 'paper_vision_qa' or len(images) != 1):
            raise ValueError('image outside one-page vision scope')
        text_wire = json.dumps(counted, ensure_ascii=False)
        text_tokens = len(self.tokenizer.encode(text_wire).ids)
        estimate = text_tokens + 256 + 1024 * len(images)
        issues = []
        product_bound = input_bound(envelope)
        if estimate > op['cap']['input']:
            issues.append('complete_input_exceeds_registered_cap')
        if product_bound > op['cap']['input']:
            issues.append('product_conservative_bound_exceeds_cap')
        if SENTINEL in wire or any(identifier in wire for identifier in self.case.get('private_ids', [])):
            issues.append('private_identifier_or_note_on_wire')
        if operation not in EXPECTED_CALLS:
            issues.append('operation_outside_audit_matrix')
        if op.get('owner_approved') is False or not self.config.get('approved_by_owner'):
            issues.append('unapproved_operation')
        # Source payloads are checked in addition to the overall token envelope.
        if operation in ('route_growth_judge', 'category_review', 'concept_intro'):
            body = json.loads(messages[-1]['content'])
            papers = body.get('papers', [])
            papers = list(papers.values()) if isinstance(papers, dict) else papers
            maximum = 12 if operation == 'category_review' else 3
            if len(papers) > maximum:
                issues.append('paper_count_exceeds_scope')
            for paper in papers:
                max_abstract = {'route_growth_judge':480,'category_review':160,'concept_intro':200}[operation]
                max_title = 200 if operation == 'route_growth_judge' else 80
                if len(paper.get('title', '')) > max_title or len(paper.get('abstract', '')) > max_abstract:
                    issues.append('public_metadata_fragment_exceeds_scope')
            if operation == 'route_growth_judge':
                from app import snippet_contract
                for alias, paper in body.get('papers', {}).items():
                    table = paper.get('snippets', {})
                    if paper.get('evidence_contract') != snippet_contract.VERSION or not isinstance(table, dict) or len(table) > 3:
                        issues.append('invalid_snippet_table_contract')
                        continue
                    for sid, option in table.items():
                        if not isinstance(sid, str) or not isinstance(option, dict):
                            issues.append('invalid_snippet_table_contract')
                            continue
                        field = option.get('field')
                        start, end = option.get('start'), option.get('end')
                        offset = paper.get(str(field)+'_start')
                        if (not sid.startswith(alias+'.') or field not in ('title', 'abstract')
                            or any(type(n) is not int for n in (start, end, offset))
                            or not isinstance(option.get('text'), str) or not 8 <= len(option['text']) <= 160
                            or start < offset or end > offset+len(paper[field])
                            or end-start != len(option['text'])
                            or paper[field][start-offset:end-offset] != option['text']):
                            issues.append('snippet_outside_transmitted_continuous_field')
            if operation == 'category_review' and len(body.get('categories', [])) > 60:
                issues.append('directory_exceeds_scope')
        return dict(wire_utf8_bytes=len(wire.encode()), wire_sha256=hashlib.sha256(wire.encode()).hexdigest(),
            text_wire_offline_tokens=text_tokens, input_estimate_with_margin=estimate,
            product_input_bound=product_bound, registered_cap=op['cap'], images=images, scope_issues=sorted(set(issues)),
            tokenizer_sha256=hashlib.sha256(TOKENIZER.read_bytes()).hexdigest(),
            counting_note='Complete JSON text wire +256 audit margin; one image <=1024 official tokens. Not provider parity.')

    def call(self, operation, messages, **kwargs):
        index = len(self.requests) + 1
        path = self.case['directory'] / ('request-%03d.json' % index)
        request = dict(operation=operation, messages=messages, attempted_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            request['preflight'] = self.inspect(operation, messages)
        except Exception as exc:
            request['preflight'] = {'scope_issues':['preflight_exception'], 'error':type(exc).__name__ + ': ' + str(exc)}
        problems = request['preflight']['scope_issues']
        if problems or self.halt:
            request.update(sent=False, result={'ok':False,'degraded':True,'invalid_input':True,
                'usage_unknown':False,'reason':'audit preflight refused: ' + ','.join(problems or [self.halt])})
        elif not self.live:
            request.update(sent=False, capture_only=True, result={'ok':False,'degraded':True,
                'reason':'audit capture only; nothing sent','usage_unknown':False})
        else:
            old = Gateway(root=ROOT, data_dir=OLD_BASE/'ledger', dev=True)
            entries = self.shared._entries() + old._entries()
            used_tokens = sum(max(0, int(e.get('input',0))) + max(0, int(e.get('output',0))) for e in entries)
            used_usd = sum((max(Decimal(0), Decimal(e.get('usd','0'))) for e in entries), Decimal(0))
            cap = self.config['operations'][operation]['cap']
            reserve_usd = (Decimal(cap['input']) * Decimal('.30') + Decimal(cap['output']) * Decimal('1.20')) / 1_000_000
            if used_tokens + cap['input'] + cap['output'] > SOFT_TOKENS or used_usd + reserve_usd > SOFT_USD:
                self.halt = 'developer_soft_budget_before_next_request'
                request.update(sent=False,result={'ok':False,'degraded':True,'reason':self.halt,'usage_unknown':False})
            else:
                # Persist the intent before network I/O; never silently repeat it.
                request.update(sent=True, state='in_flight')
                dump(path, request)
                try:
                    request['result'] = self.shared.call(operation, messages, timeout=90)
                except Exception as exc:
                    request['result'] = {'ok':False,'usage_unknown':True,'reason':type(exc).__name__ + ': ' + str(exc)}
                request['state'] = 'returned'
                result = request['result']
                usage = result.get('usage', {})
                if result.get('ok') and not result.get('usage_unknown'):
                    valid = all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens','completion_tokens'))
                    if not valid:
                        self.halt = 'invalid_provider_usage'
                if result.get('http_status') in (401,402,403,429):
                    self.halt = 'provider_auth_balance_or_rate_limit'
        self.requests.append(request)
        dump(path, request)
        return request['result']


def graph_for(domain, persona):
    graph = copy.deepcopy(persona.get('route_graph') or persona.get('graph') or domain.get('graph') or domain.get('route_graph'))
    for node in graph['concepts']:
        if node.get('type') == 'foundation' and not node.get('why'):
            node['why'] = 'Synthetic manual prerequisite fixture for the stated learning goal.'
    return graph


def brief_for(persona):
    return {k:str(persona.get(k, '')) for k in ('goal','known','include','exclude','structure')}


def new_app(case, domain, persona, papers, audit, graph=False):
    data = case['directory'] / 'data'
    app = App(root=ROOT, data_dir=data)
    app.gateway = audit
    dump(data/'settings.json', {'language':persona.get('language','zh-CN')})
    pinned = persona.get('pinned') or persona.get('keywords') or domain.get('keywords') or []
    pid = app.create_project('Public audit ' + domain['id'], keywords=pinned,
        language_policy=persona.get('language_policy') or {'discipline':'stem', 'allowed_languages':['en']})['project_id']
    normalized = [{**paper,'group_name':'discovered'} for paper in papers]
    app.store.upsert_papers(normalized, project_id=pid)
    if graph:
        app.route_save(pid, graph=graph_for(domain, persona), brief=brief_for(persona))
    case['private_ids'] = [pid]
    return app, pid


def synthetic_paper(domain, row):
    return dict(key='synthetic-audit-' + domain['id'], title='Synthetic test fixture: ' + row['title'],
        abstract='Explicitly synthetic chart and table for software testing; NOT research or clinical evidence.',
        published='2026-10-07',source='synthetic audit',topic=domain['id'],metadata_language='en')


def execute_case(case, domain, persona, papers, audit, vision):
    kind = case['kind']
    use_graph = kind in ('revision','intro','growth')
    chosen = papers[:case.get('paper_count', 25)]
    app, pid = new_app(case, domain, persona, chosen, audit, use_graph)
    try:
        if kind in ('quick','guided'):
            session = app.create_guidance_session('Public audit '+domain['id'],persona['goal'],
                creation_mode='quick' if kind=='quick' else 'ai_guided')
            messages = [persona['goal'], 'Please make the scope specific.',
                'Keep the explicit exclusions and known background.',
                'What prerequisite concepts are necessary?',
                'Give two useful public-metadata search queries.',
                'Summarize a bounded research direction for the draft.']
            outcomes=[]
            for message in messages[:1 if kind=='quick' else 6]:
                out = app.guidance_turn(session['id'],message)
                outcomes.append(out)
                if out.get('mode') != 'ai':
                    break
            return {'turns':outcomes,'complete':len(outcomes)==(1 if kind=='quick' else 6) and all(o.get('mode')=='ai' for o in outcomes)}
        if kind == 'create':
            return app.route_brief_plan(brief_for(persona), project_id=pid)
        if kind == 'revision':
            brief = brief_for(persona)
            brief['include'] = (brief['include'] + '; add a source-evidence assessment task')[:150]
            return app.route_revision_generate(pid,brief,revision=app.route_get(pid)['revision'])
        if kind == 'intro':
            nodes = app.route_get(pid)['graph']['concepts']
            return app.route_concept_intro(pid,nodes[min(case['variant'],len(nodes)-1)]['id'])
        if kind == 'triage':
            cards = [dict(p,rank=i+1,why='audit public fixture',mode='sparse',url=p.get('doi') or '') for i,p in enumerate(chosen[:5])]
            result = app.triage(cards,project_id=pid)
            expected = {p['key'] for p in cards}
            found = [i.get('paper_id') for i in result.get('items',[])]
            result['audit_item_validation'] = dict(exact_keys=set(found)==expected and len(found)==len(expected),
                valid_fields=all(all(isinstance(i.get(k),str) and i[k].strip() for k in ('one_liner','why_relevant','caution')) for i in result.get('items',[])))
            return result
        if kind == 'growth':
            for paper in chosen[:20]:
                app.record_feedback(paper['key'],'useful',project_id=pid)
            return app.route_direction_judge(pid)
        if kind == 'category':
            org = Organization(app.store)
            nodes = graph_for(domain, persona)['concepts']
            category_ids=[]
            for i,node in enumerate(nodes[:5]):
                saved=org.action({'action':'direction-save','name':node['name'],'color':'#558877'})
                category_ids.append(next(d['id'] for d in saved['directions'] if d['name']==node['name']))
            case['private_ids'].extend(category_ids)
            for i,p in enumerate(chosen):
                app.store.save_to_library(p['key'],note=SENTINEL,project_id=pid)
                if i%3 != 0:
                    org.action({'action':'membership','keys':[p['key']],'add':[category_ids[i%len(category_ids)]]})
            result=run_review(app,pid,app.profile(pid))
            return {'ai_review':result.get('ai_review'), 'suggestions':result.get('suggestions')}
        if kind in ('vision','qa'):
            variant = case['variant']
            if kind == 'vision' or variant == 3:
                rows = [r for r in vision if r['domain']==domain['id']]
                row = rows[variant if kind=='vision' else 0]
                paper = synthetic_paper(domain,row)
                app.store.upsert_papers([paper],project_id=pid)
                pdf_digest=hashlib.sha256(Path(row['pdf']).read_bytes()).hexdigest()
                app.store.record_pdf(paper['key'],row['pdf'],'synthetic audit fixture',sha256=pdf_digest,
                    size=Path(row['pdf']).stat().st_size,source_kind='user_import')
                app.save_fulltext(paper['key'],[{'page':r['page'],'text':r['text']} for r in rows],source_pdf_sha256=pdf_digest)
                label='Figure 1' if row['page']==1 else 'Table 1'
                question='Using '+label+', report the values of A, B, C and their units. Which is largest? State that these are synthetic test data.'
                if kind=='vision':
                    image='data:image/png;base64,'+base64.b64encode(Path(row['image']).read_bytes()).decode()
                    return app.qa(paper['key'],question,image=image,page_hint=row['page'],project_id=pid)
                app.store.add_qa(paper['key'],'user','What does the fixture measure?',project_id=pid)
                app.store.add_qa(paper['key'],'assistant','It is explicitly synthetic; the table and figure use '+row['unit']+'.',project_id=pid)
                return app.qa(paper['key'],question,context='full',project_id=pid)
            paper=chosen[variant]
            if variant==0:
                question='Using only this abstract, summarize the research question and the stated method. Do not invent results.'
                selection=None
            elif variant==1:
                question='Explain the research claim in the selected passage. Distinguish what it states from what it does not establish.'
                selection=(paper.get('abstract') or '')[:400]
            else:
                question='What is the exact size of every evaluation sample and all numerical results in the full paper? If unavailable in the supplied evidence, say so.'
                selection=None
            return app.qa(paper['key'],question,selection=selection,project_id=pid)
        if kind == 'translate':
            available=[p for p in chosen if p.get('abstract')]
            text=(available[case['variant']].get('abstract') or '')[:600]
            return app.translate(text)
        raise ValueError('unknown audit case')
    finally:
        app.store.close()


def cases_for(domain, kinds=('quick','guided','create','revision','triage','growth','category','qa')):
    # Three independent runs per fixed goal. Every database and session is new.
    for repeat in range(1,4):
        for persona in range(2):
            for kind in kinds:
                yield dict(kind=kind,persona=persona,repeat=repeat,variant=persona,
                    paper_count=20 if kind=='growth' else (13 if persona==0 else 25))


def summarize(base, live):
    result={'live':live,'cases':[],'operations':{},'expected_reference_calls':EXPECTED_CALLS}
    for path in sorted((base/'cases').glob('*/outcome.json')):
        row=json.loads(path.read_text());result['cases'].append({k:row[k] for k in ('id','domain','kind','status','calls','sent','reason') if k in row})
        for request in (path.parent).glob('request-*.json'):
            r=json.loads(request.read_text());op=r['operation'];bucket=result['operations'].setdefault(op,{'captured':0,'sent':0,'reconciled':0,'unknown':0,'tokens':0,'usd_peak_ledger':'0','preflight_rejections':0})
            bucket['captured']+=1;bucket['sent']+=int(r.get('sent',False))
            bucket['preflight_rejections']+=bool(r.get('preflight',{}).get('scope_issues'))
            value=r.get('result') or {};u=value.get('usage') or {}
            if r.get('sent') and value.get('ok') and not value.get('usage_unknown'):
                bucket['reconciled']+=1;bucket['tokens']+=u.get('total_tokens',0)
                bucket['usd_peak_ledger']=str(Decimal(bucket['usd_peak_ledger'])+Decimal(value.get('usd','0')))
            bucket['unknown']+=int(value.get('usage_unknown',False))
    dump(base/'summary.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--bootstrap',type=Path,required=True)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--only',default='')
    parser.add_argument('--kinds', default='quick,guided,create,revision,triage,growth,category,qa')
    parser.add_argument('--round',type=int,default=1)
    args=parser.parse_args()
    kinds = tuple(args.kinds.split(','))
    if len(set(kinds)) != len(kinds) or any(k not in {'quick','guided','create','revision','intro','triage','growth','category','qa','vision','translate'} for k in kinds):
        raise SystemExit('invalid or duplicated audit operation')
    if ROOT == Path('/Users/chandery/PaperDigHelper'):
        raise SystemExit('refuse primary checkout')
    from tokenizers import Tokenizer
    tokenizer=Tokenizer.from_file(str(TOKENIZER))
    manifest=json.loads(args.manifest.read_text())
    bootstrap=json.loads(args.bootstrap.read_text())
    if 'domains' in manifest:
        domains=manifest['domains']
    else:
        domains=[]
        for identifier in ('cs','materials','medicine'):
            personas=[p for p in manifest['personas'] if p['discipline']==identifier]
            for i,persona in enumerate(personas):
                persona.setdefault('language','zh-CN' if i==0 else 'en-US')
            domains.append({'id':identifier,'personas':personas})
    if 'disciplines' in bootstrap:
        bootstrap=bootstrap['disciplines']
    if args.round < 1:
        raise SystemExit('round must be positive')
    suffix = '' if args.round == 1 else '-r' + str(args.round)
    run=BASE/(('live' if args.live else 'capture') + suffix)
    run.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.environ['PAGETIDE_KEY_FILE']=str(KEY)
    os.environ['DEEPSEEK_API_KEY']=''
    os.environ['PDH_DEV']='1'
    shared=Gateway(root=ROOT,data_dir=BASE/'ledger',dev=True)
    if args.live and not (BASE/('capture'+suffix)/'summary.json').exists():
        raise SystemExit('capture first')
    if args.live and not shared.provider_status()['configured']:
        raise SystemExit('no configured runtime key; no request')
    if not shared.dev or shared.ledger.name!='usage-dev.jsonl':
        raise SystemExit('ledger isolation assertion')
    vision=json.loads((OLD_BASE/'vision/manifest.json').read_text())
    audit=AuditGateway(shared,tokenizer,args.live)
    dump(run/'source-snapshot.json', {'round': args.round, 'source_sha256': {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT/'app').glob('*.py'))},
        'budget_sha256': hashlib.sha256((ROOT/'harness/budget.json').read_bytes()).hexdigest(),
        'cumulative_before': shared._usage(datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                    datetime.datetime.now(datetime.timezone.utc).date().isoformat()[:7])})
    lock=(BASE/'audit.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        for domain in domains:
            papers=bootstrap[domain['id']]['papers']
            for case in cases_for(domain, kinds):
                identifier='%s-%s-v%d-r%d'%(domain['id'],case['kind'],case['variant'],case['repeat'])
                if args.only and not any(part in identifier for part in args.only.split(',')):
                    continue
                case.update(id=identifier,domain=domain['id'],directory=run/'cases'/identifier)
                if (case['directory']/'started.json').exists():
                    print('SKIP already-started '+identifier,flush=True);continue
                if audit.halt:
                    print('HALT '+audit.halt,flush=True);break
                dump(case['directory']/'started.json',{'case':{k:v for k,v in case.items() if k!='directory'},'live':args.live,
                    'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                    'bootstrap_sha256':hashlib.sha256(args.bootstrap.read_bytes()).hexdigest()})
                audit.start(case)
                persona=domain['personas'][case['persona']]
                try:
                    value=execute_case(case,domain,persona,papers,audit,vision)
                    if not args.live:
                        status='capture_only'
                    elif any(r['preflight'].get('scope_issues') for r in audit.requests):
                        status='not_sent_input_rejected'
                    elif case['kind']=='category':
                        status='passed_parser' if (value.get('ai_review') or {}).get('status')=='complete' else 'failed'
                    elif case['kind']=='growth':
                        status='passed_parser' if (value.get('complete') and not value.get('reason_code')
                            and not value.get('reply_error_code')
                            and all(item.get('verdict') != 'unusable' for item in value.get('results', []))) else 'failed'
                    elif case['kind'] in ('quick','guided'):
                        status='passed_parser' if value.get('complete') else 'failed'
                    else:
                        status='passed_parser' if value.get('ok') else 'failed'
                    outcome=dict(id=identifier,domain=domain['id'],kind=case['kind'],status=status,value=value,
                        calls=len(audit.requests),sent=sum(int(r['sent']) for r in audit.requests),
                        reason=value.get('reason') or (value.get('ai_review') or {}).get('error'))
                except Exception as exc:
                    outcome=dict(id=identifier,domain=domain['id'],kind=case['kind'],status='failed_exception',
                        reason=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc(),
                        calls=len(audit.requests),sent=sum(int(r['sent']) for r in audit.requests))
                dump(case['directory']/'outcome.json',outcome)
                dossier={'case':{k:v for k,v in case.items() if k not in ('directory','private_ids')},'persona':persona,
                    'sources':[{k:p.get(k) for k in ('key','title','abstract','doi','openalex_id','published')} for p in papers[:case.get('paper_count',25)]],
                    'expected_evidence':'Public source content only; unknown must remain unknown; no automatic graph/category application.',
                    'outcome':outcome,'request_files':sorted(p.name for p in case['directory'].glob('request-*.json'))}
                if case['kind']=='vision' or (case['kind']=='qa' and case['variant']==3):
                    dossier['synthetic_reference']=[r for r in vision if r['domain']==domain['id']]
                dump(case['directory']/'dossier.json',dossier)
                summarize(run,args.live)
                print(json.dumps({k:outcome.get(k) for k in ('id','status','calls','sent','reason')},ensure_ascii=False),flush=True)
        summary=summarize(run,args.live)
        print('COMPLETE cases='+str(len(summary['cases']))+'; semantic review separate',flush=True)
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


if __name__=='__main__':
    main()
