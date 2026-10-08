"""Fixed user goals must reach every local learning gate; no models or network."""
from unittest import mock
import unittest
from app import learning_scope
from recommendation_fixtures import english_papers
from test_route_runtime import Fixture


class LearningScopeRepairs(Fixture):
    def medical(self):
        self.app.projects.update_project(self.pid, keywords=['NSCLC', 'PD-1'])
        self.app.route_save(self.pid, plan={'concepts': [
            {'id': 'a', 'name': '微环境耐药', 'terms': ['tumor microenvironment'], 'hint': 1, 'needs': []}], 'targets': ['a']})
        self.node = self.app.route_get(self.pid)['graph']['concepts'][0]
        self.paper('wrong', 'Tumor microenvironment of liver cancer', 'Hepatocellular carcinoma tumor microenvironment review.')
        self.paper('right', 'Tumor microenvironment in NSCLC', 'NSCLC tumor microenvironment mechanism study.')
        self.paper('comparison', 'Breast and lung cancer comparison', 'Comparing NSCLC and breast cancer tumor microenvironment mechanisms.')
        self.paper('background', 'Tumor microenvironment mechanisms', 'General tumor microenvironment immune mechanisms.')

    def test_existing_project_scope_enters_concept_materials_and_preserves_comparisons(self):
        self.medical()
        keys = {key for key, _, _ in self.app._concept_matches(self.pid, self.node)}
        self.assertNotIn('wrong', keys)
        self.assertTrue({'right', 'comparison', 'background'} <= keys)
        # Same content, different explicit scope. Do not cache by graph alone.
        self.app.projects.update_project(self.pid, keywords=['liver cancer'])
        self.assertIn('wrong', {key for key, _, _ in self.app._concept_matches(self.pid, self.node)})

    def test_wrong_object_feedback_does_not_grant_target_mastery(self):
        self.medical()
        self.paper('wrong2', 'Immune liver cancer microenvironment', 'Tumor microenvironment in liver cancer.')
        for key in ('wrong', 'wrong2'):
            self.app.store.save_to_library(key, project_id=self.pid)
            self.app.record_feedback(key, 'understood', project_id=self.pid)
        state = self.app.route_get(self.pid)
        self.assertNotEqual(state['progress'][self.node['id']]['status'], 'satisfied')
        before = self.app.home_route(self.pid)
        self.app.projects.update_project(self.pid, keywords=['liver cancer'])
        after = self.app.home_route(self.pid)
        self.assertNotEqual(before['done'], after['done'])

    def test_explicit_wrong_object_cannot_reenter_as_optional_exploration(self):
        self.medical()
        state = self.app.route_get(self.pid)
        papers = [dict(p) for p in self.app.store.papers()]
        with mock.patch.object(self.app, 'route_recall_sources', return_value={'wrong': [{'kinds': ['explore'], 'query': 'liver cancer'}]}):
            picks = self.app._route_pick(state, papers, [('wrong', 1), ('right', .8)], {}, 5, 0)
        self.assertNotIn('wrong', [p[0] for p in picks])

    def test_ordinary_candidate_pool_uses_same_scope_without_removing_sources(self):
        self.medical()
        english_papers(self.app, self.pid)
        pool = {p['key']:p for p in self.app.recommendation_pool(self.pid)}
        self.assertFalse(pool['wrong']['_eligibility']['eligible'])
        self.assertEqual(pool['wrong']['_eligibility']['reason'], 'fixed_scope_conflict')
        self.assertTrue(pool['comparison']['_eligibility']['eligible'])
        self.assertIsNotNone(self.app.store.paper('wrong'))
        receipt = pool['wrong']['_task_scope']['conflicts'][0]
        self.assertIn('NSCLC', receipt['constraint']['source'][0]['quote'])
        self.assertIn('liver cancer', receipt['paper_quote'])

    def test_scope_change_during_ordinary_selection_cannot_commit_stale_batch(self):
        self.app.projects.update_project(self.pid, keywords=['NSCLC'])
        self.paper('correct', 'NSCLC therapy', 'NSCLC therapy mechanism')
        english_papers(self.app, self.pid)
        from app import ranking
        original = ranking.mmr_select
        def changed(*args, **kwargs):
            self.app.projects.update_project(self.pid, keywords=['liver cancer'])
            return original(*args, **kwargs)
        with mock.patch.object(ranking, 'mmr_select', side_effect=changed):
            result = self.app.build_batch(project_id=self.pid)
        self.assertEqual(result['reason_code'], 'recommendation_changed')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM batches WHERE project_id=?',(self.pid,)).fetchone()[0], 0)

    def test_human_cognition_paper_cannot_be_unmatched_visual_exploration(self):
        self.app.projects.update_project(self.pid, keywords=['visual planning', 'world model'])
        self.app.route_save(self.pid, plan={'concepts':[
            {'id':'visual','name':'Visual representation','terms':['visual representation','latent state'],'hint':1,'needs':[]}], 'targets':['visual']})
        self.paper('psych','Metacognitive dynamics in reasoning and planning',
                   'Latent metacognitive states are inferred from response choices, response times and confidence judgments.')
        state=self.app.route_get(self.pid)
        picks=self.app._route_pick(state,[dict(self.app.store.paper('psych'))],[('psych',1)],{},5,0)
        self.assertEqual(picks,[])

    def sourced_candidate(self):
        self.medical()
        self.paper('new','NSCLC immune cell architecture','NSCLC immune cell architecture study.')
        english_papers(self.app,self.pid)
        return mock.patch.object(self.app,'route_recall_sources',return_value={
            'new':[{'kinds':['explore'],'query':'immune cell architecture','observed_at':123}]})

    def test_actual_public_purpose_survives_restart_without_live_source(self):
        with self.sourced_candidate():
            result=self.app.build_batch(project_id=self.pid)
        card=next(c for c in result['cards'] if c['key']=='new')
        proof=card['route']['exploration_evidence']
        self.assertEqual(proof['kind'],'public_query')
        self.assertEqual(proof['query'],'immune cell architecture')
        self.assertIn(proof['quote'],'NSCLC immune cell architecture NSCLC immune cell architecture study.')
        from app.service import App
        cold=App(root=str(self.root),data_dir=str(self.app.data));self.addCleanup(cold.store.close)
        with mock.patch.object(cold,'route_recall_sources',return_value={}):
            again=next(c for c in cold.cards(result['batch_id'],self.pid) if c['key']=='new')
        self.assertEqual(again['route']['exploration_evidence'],proof)

    def test_evidence_insert_failure_rolls_back_batch_and_exposure(self):
        import sqlite3
        original=self.app.store.conn
        class FailReceipt:
            def __getattr__(self,name):return getattr(original,name)
            def __enter__(self):original.__enter__();return self
            def __exit__(self,*args):return original.__exit__(*args)
            def execute(self,sql,parameters=()):
                if sql.startswith('INSERT INTO settings') and parameters and str(parameters[0]).startswith('route_exploration_evidence_'):
                    raise sqlite3.OperationalError('deterministic receipt write failure')
                return original.execute(sql,parameters)
        with self.sourced_candidate():
            self.app.store.conn=FailReceipt()
            try:
                with self.assertRaises(sqlite3.OperationalError):self.app.build_batch(project_id=self.pid)
            finally:self.app.store.conn=original
        self.assertEqual(original.execute('SELECT COUNT(*) FROM batches WHERE project_id=?',(self.pid,)).fetchone()[0],0)
        self.assertEqual(original.execute('SELECT COUNT(*) FROM exposures').fetchone()[0],0)
        self.assertFalse(original.in_transaction)


class ScopeBoundaryTests(unittest.TestCase):
    def check(self, goal, paper, **brief):
        return learning_scope.check(learning_scope.make({'goal':goal, **brief}), paper)

    def test_saved_positive_brief_only_never_wide_subject_or_excluded_target(self):
        wrong = {'title':'Liver cancer tumor microenvironment', 'abstract':'Liver cancer study.'}
        self.assertFalse(self.check('研究NSCLC抗PD1耐药', wrong)['compatible'])
        self.assertTrue(self.check('肿瘤学研究', wrong)['compatible'])
        self.assertTrue(self.check('Exclude NSCLC', wrong)['compatible'])
        self.assertTrue(self.check('Study cancer', wrong, exclude='NSCLC')['compatible'])
        self.assertTrue(self.check('Compare NSCLC and liver cancer', wrong)['compatible'])

    def test_long_negative_clause_is_not_positive_scope_and_cannot_override_fixed_brief(self):
        nsclc = {'title':'NSCLC tumor microenvironment', 'abstract':'NSCLC tumor microenvironment study.'}
        melanoma = {'title':'Melanoma immune checkpoint response', 'abstract':'Melanoma mechanism.'}
        for goal in ('Study melanoma. Exclude treatment-response reports from NSCLC.',
                     '研究黑色素瘤。排除使用PD-1治疗获得的非小细胞肺癌相关材料。'):
            scope = learning_scope.make({'goal':goal}, ['NSCLC'])
            self.assertFalse(learning_scope.check(scope, nsclc)['compatible'])
            self.assertTrue(learning_scope.check(scope, melanoma)['compatible'])
            self.assertNotIn('NSCLC', learning_scope.as_text(scope))
        self.assertTrue(self.check('Exclude NSCLC studies. Study melanoma.', melanoma)['compatible'])
        self.assertFalse(learning_scope.check(learning_scope.make({'goal':'Study NSCLC'}, ['liver cancer']),
                                             {'title':'Liver cancer study', 'abstract':'Liver cancer.'})['compatible'])

    def test_direct_post_object_exclusion_is_not_positive_scope(self):
        nsclc={'title':'NSCLC tumor microenvironment', 'abstract':'NSCLC mechanism.'}
        for goal in ('Study melanoma; NSCLC is excluded.', '研究黑色素瘤；非小细胞肺癌不纳入。'):
            self.assertFalse(self.check(goal,nsclc)['compatible'])
        self.assertTrue(self.check('Study NSCLC; melanoma is excluded.',nsclc)['compatible'])
        self.assertTrue(self.check('Study NSCLC and melanoma.',nsclc)['compatible'])

    def test_treatment_conflict_and_multitreatment_comparison(self):
        wrong = {'title':'Platinum resistance in NSCLC', 'abstract':'Platinum-resistant NSCLC mechanism.'}
        self.assertFalse(self.check('NSCLC PD-1 resistance',wrong)['compatible'])
        self.assertTrue(self.check('NSCLC platinum resistance',wrong)['compatible'])
        self.assertTrue(self.check('NSCLC PD-1 resistance', {**wrong,'abstract':'Comparing platinum and anti-PD1 resistance in NSCLC.'})['compatible'])

    def test_environment_and_electrode_conflicts_preserve_actual_comparisons(self):
        business = {'title':'Business World Model', 'abstract':'A business-state simulator rather than physical environments.'}
        self.assertFalse(self.check('视觉世界模型规划', business)['compatible'])
        self.assertTrue(self.check('Business world model planning', business)['compatible'])
        psych={'title':'Metacognitive dynamics in reasoning and planning', 'abstract':'Latent metacognitive states, response choices and confidence judgments in human cognition.'}
        self.assertFalse(self.check('视觉世界模型规划',psych)['compatible'])
        self.assertTrue(self.check('人类认知规划',psych)['compatible'])
        self.assertTrue(self.check('视觉世界模型规划',{**psych,'abstract':'Compares human confidence judgments and visual representations for robot planning.'})['compatible'])
        si = {'title':'Silicon/Sulfide electrolyte interface', 'abstract':'A silicon anode SEI interface study.'}
        self.assertFalse(self.check('锂金属硫化物界面失效', si)['compatible'])
        self.assertTrue(self.check('硅负极界面失效', si)['compatible'])
        self.assertTrue(self.check('锂金属硫化物界面失效', {**si, 'abstract':'Compares silicon anodes and lithium metal interfaces.'})['compatible'])


if __name__ == '__main__':
    import unittest
    unittest.main()
