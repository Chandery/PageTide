import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone

from recommendation_fixtures import SYNTHETIC_OA
from app import maintenance
from app.service import App


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.app = App(data_dir=self.data)
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=True)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('Learning','manual',['publication','photonic calibration','world model'])['project_id']
        patcher = mock.patch.object(self.app.gateway, 'call', side_effect=AssertionError('No model in eligibility'))
        patcher.start(); self.addCleanup(patcher.stop)

    def policy(self, discipline='stem', allowed=None):
        self.app.set_project_language(self.pid, discipline, allowed or ['en'])

    def paper(self, key, language='en', abstract='A usable abstract about world model learning and prediction.', **extra):
        self.app.store.upsert_papers([{'key': key, 'title': 'An English world model title',
            'abstract': abstract, 'published': '2026-01-01', 'language': language, 'oa': SYNTHETIC_OA, **extra}], self.pid)

    def pdf(self, key, suffix='first'):
        path = self.data / (key + suffix + '.pdf')
        raw = b'%PDF-1.4\n' + suffix.encode() + b'\n%%EOF'
        path.write_bytes(raw); sha = hashlib.sha256(raw).hexdigest()
        self.app.store.record_pdf(key, path, sha256=sha)
        return path, sha

    def keys(self, **kw):
        return [c['key'] for c in self.app.build_batch(project_id=self.pid, exclude_seen=False, **kw)['cards']]

    def test_pending_policy_blocks_new_batch_but_keeps_old_history(self):
        self.paper('old')
        bid = self.app.store.create_batch('2026-10-01', ['old'], project_id=self.pid)
        out = self.app.build_batch(project_id=self.pid)
        self.assertIsNone(out['batch_id'])
        self.assertEqual(out['reason_code'], 'language_policy_required')
        self.assertEqual(self.app.cards(bid, self.pid)[0]['key'], 'old')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM batches').fetchone()[0], 1)

    def test_stem_metadata_language_gate_and_unverified_label(self):
        self.policy()
        self.paper('en'); self.paper('zh', 'zh'); self.paper('unknown', None)
        self.assertEqual(self.keys(), ['en'])
        card = self.app.cards(project_id=self.pid)[0]
        self.assertEqual(card['language']['fulltext_status'], 'unverified')
        self.assertEqual(card['language']['metadata_language'], 'en')

    def test_humanities_and_policy_change_recompute_eligibility(self):
        self.paper('en'); self.paper('zh', 'zh')
        self.policy('humanities', ['en', 'zh'])
        self.assertEqual(set(self.keys()), {'en', 'zh'})
        self.policy('humanities', ['zh'])
        self.assertEqual(self.keys(), ['zh'])

    def test_verified_fulltext_overrides_english_metadata(self):
        self.policy(); self.paper('mixed')
        _, sha = self.pdf('mixed')
        self.app.store.record_fulltext_language('mixed', 'zh', sha, 'manual')
        self.assertEqual(self.keys(), [])
        self.pdf('mixed', 'new')
        self.assertEqual(self.keys(), ['mixed'])
        self.assertEqual(self.app.cards(project_id=self.pid)[0]['language']['fulltext_status'], 'unverified')

    def test_links_or_pdf_without_usable_body_cannot_replace_abstract(self):
        self.policy()
        self.paper('url', abstract='', oa={'pdf_urls':['https://example.org/a.pdf']})
        self.paper('landing', abstract='', oa={'landing_page':'https://example.org/p'})
        self.paper('file', abstract=''); self.pdf('file')
        self.paper('blank', abstract=' \n ')
        self.paper('placeholder', abstract='No abstract available.')
        self.assertEqual(self.keys(), [])
        self.assertEqual(len(self.app.store.project_papers(self.pid)), 5)

    def test_current_local_body_is_usable_but_old_unbound_or_changed_pdf_is_not(self):
        self.policy(); self.paper('body', abstract='')
        path, sha = self.pdf('body')
        pages=[{'page':1,'text':'Learning predictive world models from continuous observations. ' * 10}]
        self.app.save_fulltext('body', pages)
        self.assertEqual(self.keys(), [])
        self.app.save_fulltext('body', pages, source_pdf_sha256=sha)
        self.assertEqual(self.keys(), ['body'])
        path.write_bytes(b'%PDF-1.4\nexternally changed\n%%EOF')
        self.assertEqual(self.keys(), [])
        path, new_sha = self.pdf('body', 'new')
        self.assertEqual(self.keys(), [])
        self.app.save_fulltext('body', pages, source_pdf_sha256=new_sha)
        self.assertEqual(self.keys(), ['body'])
        path.unlink()
        self.assertEqual(self.keys(), [])

    def test_current_reads_never_mix_previous_pdf_text(self):
        self.paper('read'); _, sha = self.pdf('read')
        self.app.save_fulltext('read', [{'page':1,'text':'Old text'}], source_pdf_sha256=sha)
        self.pdf('read','new')
        self.assertEqual(self.app.fulltext_status('read')['pages'], 0)
        self.assertEqual(self.app.passages('read','Old'), [])
        self.assertEqual(self.app.store.fulltext_pages('read')[0]['text'], 'Old text')

    def test_route_uses_the_same_gate(self):
        self.policy(); self.paper('en'); self.paper('zh', 'zh')
        self.app.route_save(self.pid, plan={'concepts':[{'id':'a','name':'World model','terms':['world model'],'hint':1,'needs':[]}], 'targets':['a']})
        self.assertEqual(self.keys(), ['en'])

    def test_maintenance_does_not_offer_an_ineligible_batch(self):
        self.paper('zh', 'zh'); self.policy()
        now = datetime(2026,10,7,12,tzinfo=timezone.utc)
        self.app.store.set_setting('last_refresh_'+self.pid, now.isoformat())
        self.assertFalse(maintenance.plan(self.app,self.pid,now)['batch'])
        out = maintenance.run(self.app,self.pid,now)
        self.assertFalse(out['batch'])

    def test_creation_validates_before_writing_and_guidance_keeps_policy(self):
        count=len(self.app.projects.list_projects())
        with self.assertRaises(ValueError):
            self.app.create_project('Invalid', language_policy={'discipline':'stem','allowed_languages':['zh']})
        self.assertEqual(len(self.app.projects.list_projects()), count)
        policy={'discipline':'humanities','allowed_languages':['zh','la']}
        made=self.app.create_project('History', language_policy=policy)['project_id']
        self.assertEqual(self.app.projects.get_project(made)['language_policy']['allowed_languages'], ['zh','la'])
        session=self.app.create_guidance_session('Guided', 'History')
        made=self.app.finalize_guidance(session['id'], language_policy=policy)['project_id']
        self.assertEqual(self.app.projects.get_project(made)['language_policy']['allowed_languages'], ['zh','la'])

    def test_placeholder_abstract_uses_body_for_route_matching_and_feedback_profile(self):
        from app import eligibility, pathgrowth, ranking
        self.policy(); self.paper('body', abstract='No abstract available.', title='Generic publication')
        _, sha=self.pdf('body')
        self.app.save_fulltext('body',[{'page':1,'text':'Epitaxy growth methods and crystal engineering. '*15}],source_pdf_sha256=sha)
        plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']}
        self.app.route_save(self.pid,plan=plan)
        pool=self.app.recommendation_pool(self.pid)
        graph=self.app.route_get(self.pid)['graph']
        self.assertEqual(pathgrowth.assign(graph,pool)['body'], [graph['concepts'][0]['id']])
        self.assertNotIn('No abstract',eligibility.retrieval_text(pool[0]))
        self.app.record_feedback('body','useful',project_id=self.pid)
        idf=ranking.build_idf([ranking.tokenize(eligibility.retrieval_text(pool[0]))])
        vector=self.app.profile_vector({'body':pool[0]},idf,self.pid)
        self.assertGreater(vector.get('epitaxy',0),0)

    def test_punctuation_and_blank_body_are_not_usable(self):
        self.policy(); self.paper('punct',abstract='')
        _,sha=self.pdf('punct')
        for text in ('.'*300,' \n '*300):
            self.app.save_fulltext('punct',[{'page':1,'text':text}],source_pdf_sha256=sha)
            self.assertEqual(self.keys(),[])

    def test_body_only_route_papers_advance_the_card_node_and_invalidate_home_cache(self):
        self.policy()
        plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']}
        route=self.app.route_save(self.pid,plan=plan);cid=route['graph']['concepts'][0]['id']
        for key in ['body1','body2']:
            self.paper(key,abstract='No abstract available.',title='Generic publication')
            _,sha=self.pdf(key)
            self.app.save_fulltext(key,[{'page':1,'text':'Epitaxy growth methods and engineering. '*15}],source_pdf_sha256=sha)
        result=self.app.build_batch(project_id=self.pid)
        self.assertEqual({c['route']['node'] for c in result['cards']},{cid})
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['shown'],2)
        for key in ['body1','body2']:
            self.app.store.save_to_library(key,project_id=self.pid)
            self.app.record_feedback(key,'understood',project_id=self.pid)
        self.assertEqual(self.app.home_route(self.pid)['goal_status'],'completed')
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['understood'],2)
        self.app.set_project_language(self.pid,'humanities',['zh'])
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['understood'],2)
        self.app.store.conn.execute("UPDATE fulltext SET content='Unrelated unrelated text' WHERE paper_key='body2'")
        self.app.store.conn.commit()
        self.assertEqual(self.app.home_route(self.pid)['goal_status'],'learning')

    def test_learning_graph_and_paper_context_share_current_body_matches_with_progress(self):
        self.policy()
        route=self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        cid=route['graph']['concepts'][0]['id']
        paths={}
        for key in ['body-one','body-two']:
            self.paper(key,abstract='No abstract available.',title='Generic publication')
            path,sha=self.pdf(key); paths[key]=path
            self.app.save_fulltext(key,[{'page':1,'text':'Epitaxy methods and measurement. '*20}],source_pdf_sha256=sha)
            self.app.store.save_to_library(key,project_id=self.pid)
            self.app.record_feedback(key,'understood',project_id=self.pid)
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['understood'],2)
        detail=self.app.route_detail(self.pid)
        self.assertEqual({(m['paper'],m['unit']) for m in detail['matches']},{('body-one',cid),('body-two',cid)})
        self.assertTrue(all(m['source']=='local_body' and m['terms']==['epitaxy'] for m in detail['matches']))
        context=self.app.paper_detail('body-one',self.pid)['context']
        self.assertEqual(context['units'],[{'id':cid,'name':'Epitaxy'}])
        self.assertEqual(context['matching_source'],'local_body')
        self.app.set_project_language(self.pid,'humanities',['zh'])
        self.assertEqual(self.app.paper_detail('body-one',self.pid)['context']['units'],context['units'])
        self.app.route_mode(self.pid,'off')
        self.assertEqual(self.app.paper_detail('body-one',self.pid)['context']['units'],context['units'])
        paths['body-one'].write_bytes(b'%PDF-1.4\nchanged\n%%EOF')
        self.assertEqual(self.app.paper_detail('body-one',self.pid)['context']['units'],[])
        self.assertNotIn('body-one',{m['paper'] for m in self.app.route_detail(self.pid)['matches']})

    def test_unverified_body_matches_are_pending_rather_than_unmatched_and_resume_boundedly(self):
        from app import eligibility
        self.policy()
        route=self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        self.paper('pending-body',abstract='',title='Generic publication')
        path,sha=self.pdf('pending-body')
        self.app.save_fulltext('pending-body',[{'page':1,'text':'Epitaxy methods and measurement. '*20}],source_pdf_sha256=sha)
        self.app.store.save_to_library('pending-body',project_id=self.pid)
        eligibility._PDF_CACHE.clear()
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',0):
            graph=self.app.route_detail(self.pid)
            context=self.app.paper_detail('pending-body',self.pid)['context']
        self.assertEqual(graph['pending'],['pending-body'])
        self.assertNotIn('pending-body',graph['unmatched'])
        self.assertEqual(graph['unmatched_total'],0)
        self.assertEqual(context['matching_status'],'pending')
        self.assertEqual(context['units'],[])
        self.assertEqual(self.app.route_detail(self.pid)['pending'],[])
        self.assertEqual(self.app.paper_detail('pending-body',self.pid)['context']['matching_status'],'ready')

    def test_learning_graph_progress_and_detail_language_share_a_physical_read_budget(self):
        from app import eligibility
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        for key in ['budget-one','budget-two','budget-three']:
            self.paper(key,abstract='',title='Generic publication')
            path,sha=self.pdf(key)
            self.app.save_fulltext(key,[{'page':1,'text':'Epitaxy methods and measurement. '*20}],source_pdf_sha256=sha)
            self.app.store.record_fulltext_language(key,'en',sha,'manual')
            if key != 'budget-three':
                self.app.store.save_to_library(key,project_id=self.pid)
            self.app.record_feedback(key,'too_hard' if key == 'budget-three' else 'understood',project_id=self.pid)
        eligibility._PDF_CACHE.clear(); eligibility._SCAN_CURSOR.clear()
        self.app.store.conn.execute("DELETE FROM settings WHERE key LIKE 'pdf_verification_%'"); self.app.store.conn.commit()
        maximum=path.stat().st_size*2; used=[]; real=eligibility.pdf_digest
        def measured(path,budget=None):
            self.assertIsNotNone(budget)
            before=budget['remaining']; result=real(path,budget)
            used.append(before-budget['remaining']); return result
        with mock.patch.object(eligibility,'MAX_CACHED_DIGESTS',1), mock.patch.object(eligibility,'MAX_VERIFY_BYTES',maximum), mock.patch.object(eligibility,'pdf_digest',side_effect=measured):
            graph=self.app.route_detail(self.pid)
        self.assertEqual(sum(used),maximum)
        self.assertEqual(len(graph['matches']),2)
        self.assertTrue(graph['progress_verification_deferred'])
        self.assertEqual(graph['pending_total'],0)
        # The remaining paper's detail checks once for both its matching text and language.
        used.clear()
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',path.stat().st_size), mock.patch.object(eligibility,'pdf_digest',side_effect=measured):
            detail=self.app.paper_detail('budget-three',self.pid)
        self.assertEqual(sum(used),path.stat().st_size)
        self.assertEqual(detail['language']['fulltext_status'],'verified')
        self.assertEqual(detail['context']['matching_source'],'local_body')

    def test_usable_abstract_matches_survive_deferred_fulltext_language_check(self):
        from app import eligibility
        self.policy()
        route=self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        cid=route['graph']['concepts'][0]['id']
        self.paper('abstract',title='Generic publication',abstract='Epitaxy growth methods and measurement')
        _,sha=self.pdf('abstract'); self.app.store.record_fulltext_language('abstract','en',sha,'manual')
        self.app.store.save_to_library('abstract',project_id=self.pid)
        self.app.record_feedback('abstract','understood',project_id=self.pid)
        eligibility._PDF_CACHE.clear(); self.app.store.conn.execute("DELETE FROM settings WHERE key LIKE 'pdf_verification_%'"); self.app.store.conn.commit()
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',0):
            graph=self.app.route_detail(self.pid); detail=self.app.paper_detail('abstract',self.pid)
        self.assertEqual(graph['pending_total'],0)
        self.assertFalse(graph['progress_verification_deferred'])
        self.assertEqual(graph['matches'][0]['unit'],cid)
        self.assertEqual(detail['context']['matching_status'],'ready')
        self.assertEqual(detail['context']['units'][0]['id'],cid)
        self.assertEqual(detail['language']['fulltext_status'],'unverified')

    def test_graph_rejects_pdf_or_body_changes_between_matching_and_progress(self):
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        self.paper('changing',abstract='',title='Generic publication');path,sha=self.pdf('changing')
        pages=[{'page':1,'text':'Epitaxy methods and measurement. '*20}]
        self.app.save_fulltext('changing',pages,source_pdf_sha256=sha)
        self.app.store.save_to_library('changing',project_id=self.pid)
        self.app.record_feedback('changing','understood',project_id=self.pid)
        original=self.app.route_get
        def change_pdf(*args,**kwargs):
            result=original(*args,**kwargs)
            path.write_bytes(b'%PDF-1.4\nchanged during read\n%%EOF')
            return result
        with mock.patch.object(self.app,'route_get',side_effect=change_pdf):
            with self.assertRaisesRegex(ValueError,'版本已变化'):
                self.app.route_detail(self.pid)
        path,sha=self.pdf('changing','new')
        self.app.save_fulltext('changing',pages,source_pdf_sha256=sha)
        def change_text(*args,**kwargs):
            result=original(*args,**kwargs)
            self.app.save_fulltext('changing',[{'page':1,'text':'Photonic calibration methods. '*20}],source_pdf_sha256=sha)
            return result
        with mock.patch.object(self.app,'route_get',side_effect=change_text):
            with self.assertRaisesRegex(ValueError,'版本已变化'):
                self.app.route_detail(self.pid)

    def test_detail_rejects_pdf_change_after_capturing_matching_body(self):
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        self.paper('changing',abstract='',title='Generic publication');path,sha=self.pdf('changing')
        self.app.save_fulltext('changing',[{'page':1,'text':'Epitaxy methods and measurement. '*20}],source_pdf_sha256=sha)
        original=self.app.recommendation_pool
        def change_pdf(*args,**kwargs):
            result=original(*args,**kwargs)
            path.write_bytes(b'%PDF-1.4\nchanged during detail\n%%EOF')
            return result
        with mock.patch.object(self.app,'recommendation_pool',side_effect=change_pdf):
            with self.assertRaisesRegex(ValueError,'版本已变化'):
                self.app.paper_detail('changing',self.pid)
        path,sha=self.pdf('changing','new')
        self.app.save_fulltext('changing',[{'page':1,'text':'Epitaxy methods and measurement. '*20}],source_pdf_sha256=sha)
        explanation=self.app.explain
        def change_during_response(*args,**kwargs):
            result=explanation(*args,**kwargs)
            path.write_bytes(b'%PDF-1.4\nchanged after matching\n%%EOF')
            return result
        with mock.patch.object(self.app,'explain',side_effect=change_during_response):
            with self.assertRaisesRegex(ValueError,'版本已变化'):
                self.app.paper_detail('changing',self.pid)

    def test_changed_body_during_selection_cannot_save_a_stale_route_assignment(self):
        self.policy();self.paper('body',abstract='',title='Generic publication')
        _,sha=self.pdf('body')
        self.app.save_fulltext('body',[{'page':1,'text':'Epitaxy growth methods. '*20}],source_pdf_sha256=sha)
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        original=self.app._route_pick
        def changed(*args,**kwargs):
            picks=original(*args,**kwargs)
            self.app.save_fulltext('body',[{'page':1,'text':'Photonic calibration unrelated methods. '*20}],source_pdf_sha256=sha)
            return picks
        with mock.patch.object(self.app,'_route_pick',side_effect=changed):result=self.app.build_batch(project_id=self.pid)
        self.assertEqual(result['reason_code'],'recommendation_changed')

    def test_deferred_body_progress_is_not_cached_as_final_home_progress(self):
        from app import eligibility
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        for key in ['b1','b2']:
            self.paper(key,abstract='',title='Generic publication')
            path,sha=self.pdf(key)
            self.app.save_fulltext(key,[{'page':1,'text':'Epitaxy growth methods. '*20}],source_pdf_sha256=sha)
            self.app.store.save_to_library(key,project_id=self.pid)
            self.app.record_feedback(key,'understood',project_id=self.pid)
        eligibility._PDF_CACHE.clear();eligibility._SCAN_CURSOR.clear()
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',path.stat().st_size):
            first=self.app.home_route(self.pid)
            self.assertTrue(first['progress_verification_deferred'])
            second=self.app.home_route(self.pid)
        self.assertFalse(second['progress_verification_deferred'])
        self.assertEqual(second['goal_status'],'completed')

    def test_pending_body_difficulty_cannot_consume_completed_daily_cap(self):
        from app import eligibility
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        for key in ['known1','known2']:
            self.paper(key,title='Epitaxy study',abstract='Epitaxy growth methods')
            self.app.store.save_to_library(key,project_id=self.pid)
            self.app.record_feedback(key,'understood',project_id=self.pid)
        for i in range(12):
            key='body'+str(i);self.paper(key,title='Generic publication',abstract='')
            path,sha=self.pdf(key)
            text='Epitaxy difficult methods. '*20 if i==11 else 'Photonic calibration methods. '*20
            self.app.save_fulltext(key,[{'page':1,'text':text}],source_pdf_sha256=sha)
            self.app.record_feedback(key,'too_hard' if i==11 else 'irrelevant',project_id=self.pid)
        self.paper('new',title='Photonic calibration',abstract='Photonic calibration methods')
        eligibility._PDF_CACHE.clear();eligibility._SCAN_CURSOR.clear()
        real_digest=eligibility.pdf_digest;used=[]
        def measured(path,budget=None):
            before=budget['remaining'] if budget is not None else 0
            result=real_digest(path,budget)
            if budget is not None:used.append(before-budget['remaining'])
            return result
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',path.stat().st_size):
            with mock.patch.object(eligibility,'pdf_digest',side_effect=measured):result=self.app.build_batch(project_id=self.pid)
            self.assertEqual(result['reason_code'],'route_progress_verification_pending')
            self.assertEqual(sum(used),path.stat().st_size)
            self.assertFalse(self.app.store.conn.execute('SELECT 1 FROM batches').fetchone())
            for _ in range(12):route=self.app.route_get(self.pid)
        self.assertFalse(route['progress_verification_deferred'])
        self.assertEqual(route['goal_status'],'learning')

    def test_batch_card_language_after_digest_eviction_stays_within_shared_budget(self):
        from app import eligibility
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        for key in ['v1','v2']:
            self.paper(key,title='Epitaxy study',abstract='Epitaxy growth methods')
            path,sha=self.pdf(key)
            self.app.store.record_fulltext_language(key,'en',sha,'manual')
        maximum=2*path.stat().st_size;used=[];real=eligibility.pdf_digest
        def measured(path,budget=None):
            self.assertIsNotNone(budget)
            before=budget['remaining'];result=real(path,budget);used.append(before-budget['remaining']);return result
        eligibility._PDF_CACHE.clear();eligibility._SCAN_CURSOR.clear()
        with mock.patch.object(eligibility,'MAX_CACHED_DIGESTS',1),mock.patch.object(eligibility,'MAX_VERIFY_BYTES',maximum),mock.patch.object(eligibility,'pdf_digest',side_effect=measured):
            result=self.app.build_batch(project_id=self.pid)
        self.assertEqual(len(result['cards']),2)
        self.assertEqual(sum(used),maximum)
        self.assertEqual({c['language']['fulltext_status'] for c in result['cards']},{'verified'})

    def test_verification_has_one_shared_hash_and_a_total_read_budget(self):
        from app import eligibility
        self.policy(); self.paper('bound',abstract='')
        path,sha=self.pdf('bound')
        self.app.save_fulltext('bound',[{'page':1,'text':'Meaningful predictive learning. '*20}],source_pdf_sha256=sha)
        self.app.store.record_fulltext_language('bound','en',sha,'manual')
        eligibility._PDF_CACHE.clear()
        with mock.patch.object(eligibility,'pdf_digest',wraps=eligibility.pdf_digest) as digest:
            self.assertTrue(self.app.recommendation_pool(self.pid)[0]['_eligibility']['eligible'])
            self.assertEqual(digest.call_count,1)
        # An unchanged file reuses evidence, even with zero new read allowance.
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',0):
            self.assertTrue(self.app.recommendation_pool(self.pid)[0]['_eligibility']['eligible'])
        eligibility._PDF_CACHE.clear()
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',path.stat().st_size-1):
            self.app.store.conn.execute("DELETE FROM settings WHERE key LIKE 'pdf_verification_%'");self.app.store.conn.commit()
            result=self.app.recommendation_pool(self.pid)[0]['_eligibility']
            self.assertFalse(result['eligible']);self.assertEqual(result['reason'],'source_verification_deferred')
        self.assertEqual(self.keys(),['bound'])

    def test_route_verification_finishes_across_lru_eviction_budget_and_restart(self):
        from app import eligibility
        self.policy()
        self.app.route_save(self.pid,plan={'concepts':[{'id':'a','name':'Epitaxy','terms':['epitaxy'],'hint':1,'needs':[]}],'targets':['a']})
        for key in ['e1','e2']:
            self.paper(key,title='Generic publication',abstract='')
            path,sha=self.pdf(key)
            self.app.save_fulltext(key,[{'page':1,'text':'Epitaxy growth methods. '*20}],source_pdf_sha256=sha)
            self.app.store.save_to_library(key,project_id=self.pid)
            self.app.record_feedback(key,'understood',project_id=self.pid)
        self.paper('new',title='Photonic calibration',abstract='Photonic calibration methods')
        eligibility._PDF_CACHE.clear();eligibility._SCAN_CURSOR.clear()
        public={'new':[{'query':'photonic calibration','kinds':['explore'],'observed_at':'2026-01-01'}]}
        with mock.patch.object(eligibility,'MAX_CACHED_DIGESTS',1),mock.patch.object(eligibility,'MAX_VERIFY_BYTES',path.stat().st_size),mock.patch.object(self.app,'route_recall_sources',return_value=public):
            attempts=[self.app.build_batch(project_id=self.pid) for _ in range(4)]
        self.assertEqual(attempts[0]['reason_code'],'route_progress_verification_pending')
        ready=next(r for r in attempts if r['cards'])
        self.assertEqual(ready['route_goal_status'],'completed')
        self.assertEqual([c['key'] for c in ready['cards']],['new'])
        self.assertEqual(ready['cards'][0]['route']['exploration_evidence']['query'],'photonic calibration')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM batches').fetchone()[0],1)
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM settings WHERE key LIKE 'pdf_verification_%'").fetchone()[0],2)
        again=App(data_dir=self.data);self.addCleanup(again.store.close)
        eligibility._PDF_CACHE.clear()
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',0),mock.patch.object(eligibility,'pdf_digest',side_effect=AssertionError('proof must survive restart')):
            self.assertEqual(again.route_get(self.pid)['goal_status'],'completed')
        path.write_bytes(b'%PDF-1.4\nexternally changed\n%%EOF')
        with mock.patch.object(eligibility,'MAX_VERIFY_BYTES',0):
            self.assertTrue(again.route_get(self.pid)['progress_verification_deferred'])

    def test_pdf_proofs_do_not_commit_outer_transaction_and_new_pdf_clears_them(self):
        self.policy();self.paper('proof',abstract='')
        path,sha=self.pdf('proof')
        self.app.save_fulltext('proof',[{'page':1,'text':'Epitaxy growth methods. '*20}],source_pdf_sha256=sha)
        self.app.store.conn.execute('BEGIN IMMEDIATE')
        self.app.recommendation_pool(self.pid)
        self.assertTrue(self.app.store.conn.in_transaction)
        self.assertIsNotNone(self.app.store.get_setting('pdf_verification_proof'))
        self.app.store.conn.rollback()
        self.assertIsNone(self.app.store.get_setting('pdf_verification_proof'))
        self.app.recommendation_pool(self.pid)
        self.assertIsNotNone(self.app.store.get_setting('pdf_verification_proof'))
        self.pdf('proof',suffix='new')
        self.assertIsNone(self.app.store.get_setting('pdf_verification_proof'))

    def test_frozen_import_preserves_reported_languages_without_inventing_english(self):
        self.policy()
        path=self.data/'candidates.json'
        path.write_text(json.dumps([{'key':'zh','title':'English title','abstract':'Useful abstract','language':'zh'},
                                   {'key':'unknown','title':'English title','abstract':'Useful abstract'}]))
        self.app.import_candidates(path,self.pid)
        self.assertEqual(self.keys(),[])
        self.assertEqual(self.app.store.paper('zh')['metadata_language'],'zh')
        self.assertIsNone(self.app.store.paper('unknown')['metadata_language'])

    def test_legacy_pdf_preparation_establishes_hash_but_changed_file_cannot_relabel_old_text(self):
        self.paper('old'); path,sha=self.pdf('old')
        self.app.store.conn.execute('UPDATE pdfs SET sha256=NULL WHERE paper_key=?',('old',));self.app.store.conn.commit()
        self.app.save_fulltext('old',[{'page':1,'text':'Legacy extraction'}])
        out=self.app.download_pdf('old')
        self.assertTrue(out['ok']);self.assertEqual(out['sha256'],sha)
        self.assertEqual(self.app.fulltext_status('old')['pages'],0)
        path.write_bytes(b'%PDF-1.4\nexternally replaced\n%%EOF')
        out=self.app.download_pdf('old')
        self.assertFalse(out['ok']);self.assertEqual(out['reason'],'pdf_changed')
        self.assertEqual(self.app.store.conn.execute('SELECT sha256 FROM pdfs WHERE paper_key=?',('old',)).fetchone()[0],sha)

    def test_deferred_verification_eventually_reaches_the_tail_of_a_large_pool(self):
        from app import eligibility
        self.policy(); size=0
        for i in range(5):
            key='p'+str(i);self.paper(key,abstract='')
            path,sha=self.pdf(key,'n'+str(i));size=path.stat().st_size
            self.app.save_fulltext(key,[{'page':1,'text':'Meaningful learning text. '*20}],source_pdf_sha256=sha)
        eligibility._PDF_CACHE.clear()
        eligible=set()
        with mock.patch.object(eligibility,'MAX_CACHED_DIGESTS',2), mock.patch.object(eligibility,'MAX_VERIFY_BYTES',size*2):
            for _ in range(6):
                eligible.update(p['key'] for p in self.app.recommendation_pool(self.pid) if p['_eligibility']['eligible'])
        self.assertEqual(eligible,{'p0','p1','p2','p3','p4'})

    def test_pdf_growth_during_hash_cannot_exceed_the_reserved_read_bytes(self):
        from app import eligibility
        self.paper('grow');path,_=self.pdf('grow')
        original_open=Path.open; size=path.stat().st_size; reads=[]
        class Tracked:
            def __init__(self,handle): self.handle=handle
            def __enter__(self):return self
            def __exit__(self,*args):self.handle.close()
            def read(self,count):
                data=self.handle.read(count);reads.append(len(data));return data
        def changed_open(target,*args,**kw):
            handle=original_open(target,*args,**kw)
            with original_open(target,'ab') as writer: writer.write(b'x'*1024)
            return Tracked(handle)
        eligibility._PDF_CACHE.clear()
        with mock.patch.object(Path,'open',changed_open):
            self.assertIsNone(eligibility.pdf_digest(path,{'remaining':size,'deferred':False}))
        self.assertLessEqual(sum(reads),size)

    def test_policy_change_during_selection_cannot_relabel_old_eligibility_as_new_policy(self):
        from app import eligibility
        self.policy('humanities',['zh']);self.paper('zh','zh',abstract='')
        _,sha=self.pdf('zh');self.app.save_fulltext('zh',[{'page':1,'text':'中文文献的有效正文。'*50}],source_pdf_sha256=sha)
        real=eligibility.pdf_digest; switched=False
        def switching(*args,**kw):
            nonlocal switched
            result=real(*args,**kw)
            if not switched:
                switched=True;self.policy('stem',['en'])
            return result
        with mock.patch.object(eligibility,'pdf_digest',side_effect=switching):out=self.app.build_batch(project_id=self.pid)
        self.assertIsNone(out['batch_id']);self.assertEqual(out['reason_code'],'recommendation_changed')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)

    def test_replacement_during_verification_rejects_previous_body_even_in_the_pool(self):
        from app import eligibility
        self.policy();self.paper('changed',abstract='')
        _,sha=self.pdf('changed');self.app.save_fulltext('changed',[{'page':1,'text':'Meaningful current text. '*20}],source_pdf_sha256=sha)
        real=eligibility.pdf_digest; changed=False
        def replacing(*args,**kw):
            nonlocal changed
            result=real(*args,**kw)
            if not changed:
                changed=True;self.pdf('changed','new')
            return result
        with mock.patch.object(eligibility,'pdf_digest',side_effect=replacing):row=self.app.recommendation_pool(self.pid)[0]
        self.assertFalse(row['_eligibility']['eligible']);self.assertEqual(row['_local_body'],'')

    def test_final_write_rejects_pdf_replaced_after_ranking_without_an_exposure(self):
        from app import ranking
        self.policy();self.paper('changing',abstract='')
        _,sha=self.pdf('changing');self.app.save_fulltext('changing',[{'page':1,'text':'Meaningful current text. '*20}],source_pdf_sha256=sha)
        real=ranking.mmr_select
        def replacement(*args,**kw):
            chosen=real(*args,**kw);self.pdf('changing','new');return chosen
        with mock.patch.object(ranking,'mmr_select',side_effect=replacement):out=self.app.build_batch(project_id=self.pid)
        self.assertIsNone(out['batch_id']);self.assertEqual(out['reason_code'],'recommendation_changed')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM exposures').fetchone()[0],0)

    def test_project_deleted_after_pool_does_not_recreate_its_eligibility_cache(self):
        self.policy();self.paper('delete')
        real=self.app.recommendation_pool
        def deleted(*args,**kw):
            rows=real(*args,**kw);self.app.delete_project(self.pid);return rows
        with mock.patch.object(self.app,'recommendation_pool',side_effect=deleted):
            out=self.app.build_batch(project_id=self.pid)
        self.assertIsNone(out['batch_id']);self.assertEqual(out['reason_code'],'recommendation_changed')
        self.assertIsNone(self.app.store.get_setting('recommendation_eligibility_'+self.pid))

    def test_project_deleted_after_ranking_aborts_the_batch_cleanly(self):
        from app import ranking
        self.policy();self.paper('delete')
        real=ranking.mmr_select
        def deleted(*args,**kw):
            keys=real(*args,**kw);self.app.delete_project(self.pid);return keys
        with mock.patch.object(ranking,'mmr_select',side_effect=deleted):out=self.app.build_batch(project_id=self.pid)
        self.assertIsNone(out['batch_id']);self.assertEqual(out['reason_code'],'recommendation_changed')
        self.assertIsNone(self.app.store.get_setting('recommendation_eligibility_'+self.pid))
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)

    def test_snapshot_sql_does_not_write_when_an_earlier_project_read_has_gone_stale(self):
        self.policy();self.paper('stale')
        original_get=self.app.projects.get_project; old=original_get(self.pid); original_pool=self.app.recommendation_pool
        def deleted(*args,**kw):
            rows=original_pool(*args,**kw);self.app.projects.delete_project(self.pid);return rows
        def stale_get(pid):return old if pid==self.pid else original_get(pid)
        with mock.patch.object(self.app.projects,'get_project',side_effect=stale_get), mock.patch.object(self.app,'recommendation_pool',side_effect=deleted):
            out=self.app.build_batch(project_id=self.pid)
        self.assertIsNone(out['batch_id']);self.assertEqual(out['reason_code'],'recommendation_changed')
        self.assertIsNone(self.app.store.get_setting('recommendation_eligibility_'+self.pid))

    def test_body_eligibility_respects_pdf_page_and_per_page_text_bounds(self):
        self.policy();self.paper('late-page',abstract='');self.paper('late-text',abstract='')
        for key,pages in [('late-page',[{'page':7,'text':'Meaningful model learning. '*30}]),
                          ('late-text',[{'page':1,'text':'.'*2000+'Meaningful model learning. '*30}])]:
            _,sha=self.pdf(key);self.app.save_fulltext(key,pages,source_pdf_sha256=sha)
        self.assertEqual(self.keys(),[])
