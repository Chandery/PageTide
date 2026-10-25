"""Regression boundaries from the six-discipline audit (no network or models)."""
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit
from app import ranking, pathgrowth, user_settings
from app.sources import OpenAlex, slim, clean_query
from app.db import Store
import sqlite3
from app.service import App
from app.organization_facets import suggest_groups
from app.organization_terms import category_identity
from tests.recommendation_fixtures import english_papers

class ScienceLexicalTests(unittest.TestCase):
    def test_science_spellings_share_identity_without_lowercase_element_false_positive(self):
        for a,b in [('Li₆PS₅Cl','Li6PS5Cl'), ('PD1 resistance','PD-1 resistance'), ('PDL1','PD-L1'), ('anti-PD1','anti PD-1'), ('world-models','world models'), ('solid-state','solid state'), ('tumour','tumor'), ('α phase','alpha phase')]:
            self.assertEqual(ranking.tokenize(a),ranking.tokenize(b),(a,b))
            self.assertTrue(pathgrowth.term_in_text(a,b),(a,b))
        for element in ('Li','Na','Fe'):
            self.assertTrue(ranking.tokenize(element))
            self.assertNotEqual(ranking.tokenize(element),ranking.tokenize(element.lower()))
            self.assertFalse(pathgrowth.term_in_text('plain '+element.lower(),element))
    def test_public_search_keeps_formula_and_alias_without_namespace(self):
        self.assertEqual(clean_query("Li₆PS₅Cl PD1 Li"),"Li6PS5Cl PD-1 Li")
        self.assertNotIn("element_",clean_query("Fe Na"))
    def test_category_identity_preserves_science_aliases(self):
        self.assertEqual(category_identity('硫化物固态电解质'),category_identity('Sulfide Solid Electrolytes'))
        self.assertEqual(category_identity('PD1耐药'),category_identity('PD-1 Resistance'))
        self.assertEqual(category_identity('Li₆PS₅Cl'),category_identity('Li6PS5Cl'))
        self.assertNotEqual(category_identity('Li6PS5Cl'),category_identity('Argyrodite Electrolytes'))
    def test_material_and_medical_fine_groups_are_available(self):
        for phrase,expected in [('sulfide solid electrolyte interfaces','硫化物固态电解质'),('non-small cell lung cancer PD1 resistance','非小细胞肺癌')]:
            papers=[dict(key=str(i),title=phrase,abstract=phrase,topic='') for i in range(2)]
            names=[g['name'] for g in suggest_groups(papers,{})['groups']]
            self.assertTrue(any(expected in n for n in names),names)

class SourcePolicyTests(unittest.TestCase):
    def test_review_conference_are_allowed_and_future_rejected_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            oa=OpenAlex(tmp,api_key='test-openalex-key-0000')
            works=[dict(id='https://openalex.org/W'+str(i),title='planning '+str(i),type=t,publication_date=d) for i,(t,d) in enumerate([('review','2020-01-01'),('conference-paper','2020-02-01'),('article','2099-01-01')])]
            with mock.patch.object(oa,'_fetch',return_value={'results':works}) as fetch:
                found=oa.discover_topic('planning')
            self.assertEqual(len(found),2)
            self.assertEqual([p['work_type'] for p in found],['review','conference-paper'])
            self.assertIn('review|conference-paper',parse_qs(urlsplit(fetch.call_args.args[0]).query)['filter'][0])
            self.assertIn('to_publication_date:'+datetime.date.today().isoformat(),parse_qs(urlsplit(fetch.call_args.args[0]).query)['filter'][0])
            self.assertEqual(oa.rejected_publications[0]['published'],'2099-01-01')

class SettingsContractTests(unittest.TestCase):
    def test_settings_keep_zero_and_reject_invalid_visible_values(self):
        self.assertEqual(user_settings.validate({'newPaperBoost':0})['newPaperBoost'],0)
        for value in ({'recommendCount':0},{'decayWindow':999},{'newPaperBoost':None},{'theme':'blue'},{'sourceArxiv':'false'}):
            with self.assertRaises(ValueError):user_settings.validate(value)
    def test_type_migration_backs_up_original_and_is_additive(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'original.sqlite';store=Store(path);store.init()
            store.upsert_papers([dict(key='p',title='Keep me')]);store.conn.execute('ALTER TABLE papers DROP COLUMN work_type');store.conn.commit();store.close()
            reopened=Store(path);reopened.init()
            self.assertEqual(reopened.paper('p')['title'],'Keep me');self.assertIsNone(reopened.paper('p')['work_type']);reopened.close()
            backup=sqlite3.connect(str(path.with_name('original.sqlite.pre-work-type.bak')))
            self.assertNotIn('work_type',[r[1] for r in backup.execute('PRAGMA table_info(papers)')])
            self.assertEqual(backup.execute("SELECT title FROM papers WHERE key='p'").fetchone()[0],'Keep me');backup.close()
    def test_work_type_backup_failure_cleans_partial_and_does_not_modify_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'old.sqlite';store=Store(path);store.init()
            store.upsert_papers([dict(key='p',title='Original')]);store.conn.execute('ALTER TABLE papers DROP COLUMN work_type');store.conn.commit();store.close()
            reopened=Store(path)
            def failed(target):
                target.write_bytes(b'partial')
                raise OSError('injected backup failure')
            with mock.patch.object(reopened,'backup',side_effect=failed),self.assertRaises(OSError):reopened.init()
            self.assertNotIn('work_type',[r[1] for r in reopened.conn.execute('PRAGMA table_info(papers)')])
            self.assertEqual(reopened.paper('p')['title'],'Original');reopened.close()
            self.assertFalse(path.with_name('old.sqlite.pre-work-type.bak').exists())
    def test_work_type_existing_backup_never_suppresses_fresh_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'old.sqlite';store=Store(path);store.init()
            store.upsert_papers([dict(key='p',title='Original')]);store.conn.execute('ALTER TABLE papers DROP COLUMN work_type');store.conn.commit();store.close()
            older=path.with_name('old.sqlite.pre-work-type.bak');older.write_bytes(b'existing artifact')
            reopened=Store(path);reopened.init();reopened.close()
            self.assertEqual(older.read_bytes(),b'existing artifact')
            fresh=list(path.parent.glob('old.sqlite.pre-work-type-*.bak'));self.assertEqual(len(fresh),1)
            conn=sqlite3.connect(str(fresh[0]));self.assertEqual(conn.execute("SELECT title FROM papers WHERE key='p'").fetchone()[0],'Original');conn.close()

class DiscoveryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.app=App(root='.',data_dir=Path(self.tmp.name)/'app');self.addCleanup(self.app.store.close)
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=False)
        self.pid=self.app.create_project('science','manual',['visual planning'])['project_id']
    def setting(self,**kw):
        (self.app.data/'settings.json').write_text(json.dumps({'timePreference':'all',**kw}))   # old synthetic papers: owner chose all time
    def add(self,key,title='visual planning',published='2026-01-01',seed=False):
        self.app.store.upsert_papers([dict(key=key,title=title,abstract='visual planning and dynamic prediction relevant research',published=published)],project_id=self.pid)
        if seed:
            self.app.store.add_project_paper(self.pid,key,'seed')
            configured=self.app.store.get_setting(f'seed_keys_{self.pid}',[])
            self.app.store.set_setting(f'seed_keys_{self.pid}',configured+[key])
    def test_saved_count_and_seed_exclusion(self):
        self.add('seed',seed=True)
        self.assertIn('seed',self.app.profile(self.pid)['positive_seeds'])
        for i in range(4): self.add('new'+str(i))
        self.setting(recommendCount=1)
        english_papers(self.app,self.pid)
        cards=self.app.build_batch(project_id=self.pid)['cards']
        self.assertEqual(len(cards),1);self.assertNotEqual(cards[0]['key'],'seed')
    def test_sources_off_produce_no_calls(self):
        self.setting(sourceArxiv=False,sourceOpenAlex=False)
        with mock.patch.object(self.app.source,'discover_topic',side_effect=AssertionError('source disabled')):
            self.assertEqual(self.app.refresh_candidates(project_id=self.pid)['fetched'],0)
    def test_disabled_sources_also_filter_cached_candidates(self):
        self.add('cached')
        self.setting(sourceArxiv=False,sourceOpenAlex=False)
        english_papers(self.app,self.pid)
        result=self.app.build_batch(project_id=self.pid)
        self.assertEqual(result['cards'],[])
        self.assertEqual(result['eligibility']['excluded']['source_disabled'],1)
    def test_date_preference_and_future_filters(self):
        self.setting(timePreference='recent')
        today=datetime.date.today()
        self.add('fresh',published=today.isoformat());self.add('old',published=(today-datetime.timedelta(days=20)).isoformat());self.add('future',published='2099-01-01')
        english_papers(self.app,self.pid)
        cards=self.app.build_batch(project_id=self.pid)['cards']
        self.assertEqual([c['key'] for c in cards],['fresh'])
        self.assertEqual(self.app.store.get_setting('recommendation_eligibility_'+self.pid)['excluded']['future_publication_date'],1)
    def test_source_selection_is_wired_and_time_window_sent(self):
        self.setting(sourceArxiv=True,sourceOpenAlex=False,timePreference='month')
        with mock.patch.object(self.app.source,'discover_topic',return_value=[]) as fetch:
            self.app.refresh_candidates(project_id=self.pid)
        self.assertFalse(fetch.call_args.kwargs['source_openalex'])
        self.assertTrue(fetch.call_args.kwargs['source_arxiv'])
        self.assertEqual(fetch.call_args.kwargs['from_date'],(datetime.date.today()-datetime.timedelta(days=30)).isoformat())
    def test_zero_novelty_is_exact_and_nonzero_never_adds_relevance(self):
        self.assertEqual(ranking.novelty_score(.4,datetime.date.today().isoformat(),0),.4)
        self.assertGreater(ranking.novelty_score(.4,datetime.date.today().isoformat(),.2),.4)
        self.assertEqual(ranking.novelty_score(0,datetime.date.today().isoformat(),1),0)
    def test_feedback_decay_changes_profile_but_seed_and_freeze_keep_their_meaning(self):
        self.add('liked',title='ionic conductivity electrode')
        self.add('seed',title='visual planning dynamics',seed=True)
        self.app.record_feedback('liked','useful',project_id=self.pid)
        old=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=90)).isoformat()
        self.app.store.conn.execute("UPDATE feedback SET created_at=?",(old,));self.app.store.conn.commit()
        papers={p['key']:dict(p) for p in self.app.store.conn.execute('SELECT * FROM papers')}
        idf=ranking.build_idf([ranking.tokenize(p['title']) for p in papers.values()])
        self.setting(decayWindow=365)
        baseline=self.app.profile_vector(papers,idf,self.pid)
        self.setting(decayWindow=7)
        decayed=self.app.profile_vector(papers,idf,self.pid)
        self.assertLess(decayed['ionic'],baseline['ionic'])
        self.assertGreater(decayed['visual'],baseline['visual'])
        self.app.set_profile_frozen(True,self.pid)
        frozen=self.app.profile_vector(papers,idf,self.pid)
        self.assertEqual(frozen,self.app.profile_vector(papers,idf,self.pid))
    def test_work_type_round_trips_as_independent_metadata(self):
        self.app.store.upsert_papers([dict(key='review',title='A systematic review',work_type='review')],project_id=self.pid)
        self.app.store.upsert_papers([dict(key='review',title='A systematic review')],project_id=self.pid)
        self.assertEqual(self.app.store.paper('review')['work_type'],'review')
        self.assertEqual(pathgrowth.paper_role(self.app.store.paper('review')),'intro')
    def test_multiword_science_reason(self):
        self.app.pin_terms(['visual planning','PD1','Li₆PS₅Cl'],self.pid)
        why=self.app.explain(dict(title='Visual planning using PD-1 and Li6PS5Cl',abstract=''),self.pid)
        self.assertEqual(why['matched_terms'],['visual planning','PD1','Li₆PS₅Cl'])
    def test_inventory_is_not_interest_evidence(self):
        self.add('inventory',title='acting 1488 450 visual planning')
        self.app.store.save_to_library('inventory',project_id=self.pid)
        result=self.app.profile_insights(self.pid)
        self.assertEqual(result['keyword_evidence']['papers'],0)
        self.assertEqual(result['keyword_distribution'],[])
        self.assertGreater(result['inventory_evidence']['papers'],0)
        self.assertNotIn('1488',[x['term'] for x in result['inventory_distribution']])
        self.assertEqual(self.app.profile(self.pid)['positive_feedback'],[])
        self.assertIsNone(self.app.explain(dict(title='visual planning',abstract=''),self.pid)['nearest_reference'])
        event=self.app.record_feedback('inventory','useful',project_id=self.pid)
        learned={x['term'] for x in self.app.profile_insights(self.pid)['keyword_distribution']}
        self.assertFalse(learned & {'1488','450','acting'})
        self.app.undo_feedback(event['feedback_id'],self.pid)
        self.assertEqual(self.app.profile_insights(self.pid)['keyword_distribution'],[])
        self.assertEqual(self.app.profile_insights(self.pid)['inventory_evidence']['papers'],1)

if __name__=='__main__':unittest.main()
