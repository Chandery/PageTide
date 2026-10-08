"""Observed learning-match regressions; keep primary-only mastery and strict language eligibility."""
import unittest
from unittest import mock
import sys

from app import pathgrowth, route_batch, ranking, organization_facets


def graph():
    return {'concepts': [
        {'id': 'visual', 'name': '视觉状态表征', 'terms': ['visual representation', 'latent state'], 'state': 'active'},
        {'id': 'dynamics', 'name': '动作条件动力学', 'terms': ['world model', 'latent dynamics'], 'state': 'active'},
        {'id': 'planning', 'name': '模型规划', 'terms': ['model predictive control', 'visual planning'], 'state': 'active'}]}


class LearningMatchRepairs(unittest.TestCase):
    def test_normalization_cache_has_byte_entry_and_text_length_bounds(self):
        for i in range(300):
            ranking.scientific_text(str(i) + ' α Li₆PS₅Cl ' * 500)
        self.assertLessEqual(len(ranking._SCIENCE_CACHE), ranking.SCIENCE_CACHE_ENTRIES)
        self.assertLessEqual(ranking._SCIENCE_CACHE_BYTES, ranking.SCIENCE_CACHE_BYTES)
        text = 'long scientific text ' * 1000
        self.assertEqual(ranking.scientific_text(text), ranking._scientific_text(text))
        self.assertNotIn(text, ranking._SCIENCE_CACHE)
        for text in (' '.join(['a']*128), 'x'*256, 'α'*256):
            pattern = pathgrowth._pattern(text)
            self.assertLessEqual(sys.getsizeof(pattern)+sys.getsizeof(pattern.pattern),8192)
        self.assertEqual(pathgrowth._pattern.cache_info().maxsize,256)

    def test_normalization_and_category_reuse_do_not_rescan_every_term(self):
        text = 'Unique repeated normalization probe PD1 Li₆PS₅Cl'
        with mock.patch.object(ranking.unicodedata, 'normalize', wraps=ranking.unicodedata.normalize) as normalize:
            for _ in range(20):
                ranking.scientific_text(text)
            self.assertLessEqual(normalize.call_count, 1)
        papers = [{'key': str(i), 'title': 'Sulfide solid electrolyte interface stability',
                   'abstract': 'Lithium metal interfaces cause interfacial degradation.'} for i in range(25)]
        with mock.patch.object(organization_facets, '_segments', wraps=organization_facets._segments) as segments:
            groups = organization_facets.suggest_groups(papers)
        self.assertTrue(groups)
        self.assertLessEqual(segments.call_count, len(papers)*2)

    def test_supported_qualifier_keeps_scientific_phrase_identity(self):
        self.assertTrue(pathgrowth.term_in_text('learns latent Graph dynamics for deformable object manipulation', 'latent dynamics'))
        self.assertTrue(pathgrowth.term_in_text('sulfide solid electrolyte interface', 'sulfide electrolyte'))
        self.assertTrue(pathgrowth.term_in_text('visual state representation for planning', 'visual representation'))
        self.assertFalse(pathgrowth.term_in_text('latent metacognitive dynamics', 'latent dynamics'))
        self.assertFalse(pathgrowth.term_in_text('visual. State representation', 'visual representation'))

    def test_phrase_keeps_one_line_wrap_but_never_stitches_paragraphs(self):
        for matcher in (ranking.term_in_text, pathgrowth.term_in_text):
            for separator in (' ', '\t', '-', '\n', '\r\n', ' \n  '):
                self.assertTrue(matcher('Visual'+separator+'representation supports image planning.', 'visual representation'))
            for separator in ('\n\n', '\n \n', '\r\n\r\n', '\f', '\u2029', '.\n'):
                self.assertFalse(matcher('Visual'+separator+'representation theory is a topic of algebra.', 'visual representation'))
        self.assertTrue(pathgrowth.term_in_text('latent\ngraph dynamics', 'latent dynamics'))
        self.assertFalse(pathgrowth.term_in_text('latent\n\ngraph dynamics', 'latent dynamics'))
        self.assertFalse(pathgrowth.term_in_text('latent graph\n\ndynamics', 'latent dynamics'))

    def test_gdoom_gets_dynamics_without_rewriting_terms(self):
        g = graph()
        p = {'key': 'gdoom', 'title': 'Learning Latent Graph Dynamics for Deformable Object Manipulation',
             'abstract': 'We learn latent graph dynamics from keypoints and use model-predictive control for manipulation planning.'}
        self.assertIn('dynamics', pathgrowth.assign(g, [p])['gdoom'])
        self.assertEqual(g['concepts'][1]['terms'], ['world model', 'latent dynamics'])

    def test_visual_foundation_needs_visual_evidence_for_generic_latent_state(self):
        p = {'key': 'psych', 'title': 'Dissociating Reasoning and Planning through Metacognitive Dynamics',
             'abstract': 'Human response choices reflect latent states and metacognitive uncertainty in reasoning tasks.'}
        self.assertNotIn('visual', pathgrowth.assign(graph(), [p]).get('psych', []))

    def test_visual_encoding_surfaces_have_raw_evidence(self):
        p = {'key': 'encoder', 'title': 'Visual features for world model planning',
             'abstract': 'Frozen visual features are projected into a learned latent space for planning and control.'}
        self.assertIn('visual', pathgrowth.assign(graph(), [p])['encoder'])
        evidence = pathgrowth.match_evidence(graph()['concepts'][0], p)
        self.assertTrue(evidence)
        for item in evidence:
            self.assertIn(item['quote'], p['title'] + ' ' + p['abstract'])
            self.assertIn(item['term'], graph()['concepts'][0]['terms'])

    def test_latent_space_without_visual_context_does_not_expand_visual_foundation(self):
        p = {'key': 'language', 'title': 'Language latent spaces',
             'abstract': 'Text is embedded into a latent representation for business decisions.'}
        self.assertNotIn('visual', pathgrowth.assign(graph(), [p]).get('language', []))

    def test_scientific_subtype_and_stability_surfaces_keep_original_evidence(self):
        examples = [
            ({'terms': ['interferon'], 'name': '肿瘤内在耐药'},
             {'title': 'Acquired resistance in lung cancer', 'abstract': 'Tumors remained responsive to IFNγ despite reduced MHC-I levels.'}, 'IFN gamma'),
            ({'terms': ['interfacial stability'], 'name': '界面稳定性评估'},
             {'title': 'Interfacial Stabilization in Sulfide Batteries', 'abstract': 'The additive stabilizes the interface against lithium metal.'}, 'interfacial stabilization'),
        ]
        for concept, paper, surface in examples:
            evidence = pathgrowth.match_evidence(concept, paper)
            self.assertEqual(evidence[0]['matched_via'], surface)
            self.assertIn(evidence[0]['quote'], paper['title']+' '+paper['abstract'])
        self.assertFalse(pathgrowth.match_evidence({'terms': ['interferon'], 'name': '内在耐药'},
                         {'title': 'IFN tensor factorization', 'abstract': 'An unrelated acronym without a cytokine subtype.'}))
        self.assertFalse(pathgrowth.match_evidence({'terms': ['interfacial stability'], 'name': '稳定性'},
                         {'title': 'Stable cycling', 'abstract': 'Improved generic capacity stability without interface evidence.'}))

    def test_locked_primary_can_support_an_explicit_matching_frontier_secondary(self):
        g = graph()
        route = {'graph': g, 'frontier': ['visual'], 'goal_status': 'learning', 'goal_scope': ['visual','dynamics','planning'],
                 'progress': {c['id']: {'status': 'locked' if c['id'] != 'visual' else 'open', 'shown': 0, 'low_interest': False}
                              for c in g['concepts']}}
        p = {'key': 'dual', 'title': 'Latent dynamics world model',
             'abstract': 'World models learn latent dynamics and visual representation for control.'}
        self.assertEqual(pathgrowth.assign(g, [p])['dual'][0], 'dynamics')
        chosen = route_batch.choose(route, [p], [('dual', 1)], 5)
        self.assertEqual(chosen[0][:3], ('dual', 'visual', 'route'))
        self.assertEqual(pathgrowth.assign(g, [p])['dual'][0], 'dynamics')

    def test_satisfied_primary_is_not_redirected_to_fill_frontier(self):
        g = graph()
        route = {'graph': g, 'frontier': ['visual'], 'goal_status': 'learning', 'goal_scope': ['visual','dynamics','planning'],
                 'progress': {c['id']: {'status': 'satisfied' if c['id'] == 'dynamics' else 'open', 'shown': 0, 'low_interest': False}
                              for c in g['concepts']}}
        p = {'key': 'dual', 'title': 'Latent dynamics world model',
             'abstract': 'World models learn latent dynamics and visual representation for control.'}
        self.assertEqual(route_batch.choose(route, [p], [('dual', 1)], 5), [])

    def test_unmatched_paper_needs_a_real_public_purpose_not_an_empty_exploration_slot(self):
        g=graph();route={'graph':g,'frontier':['visual'],'goal_status':'learning','goal_scope':['visual','dynamics','planning'],
            'progress':{c['id']:{'status':'open','shown':0,'low_interest':False} for c in g['concepts']}}
        paper={'key':'other','title':'Photonic calibration methods','abstract':'Photonic calibration instruments.'}
        self.assertEqual(route_batch.choose(route,[paper],[('other',1)],5),[])
        self.assertEqual(route_batch.choose(route,[paper],[('other',1)],5,sources={'other':[{'kinds':['explore'],'query':'unrelated climate'}]}),[])
        proof={}
        chosen=route_batch.choose(route,[paper],[('other',1)],5,
            sources={'other':[{'kinds':['explore'],'query':'photonic calibration','observed_at':1}]},evidence=proof)
        self.assertEqual(chosen[0][0],'other')
        self.assertEqual(proof['other']['kind'],'public_query')
        self.assertIn(proof['other']['quote'],paper['title']+' '+paper['abstract'])

    def test_explicit_side_branch_and_direction_have_distinct_bounded_purposes(self):
        g=graph();g['concepts'].append({'id':'side','name':'Photonic calibration','terms':['photonic calibration'],'state':'active'})
        route={'graph':g,'frontier':['visual'],'goal_status':'learning','goal_scope':['visual','dynamics','planning'],
            'progress':{c['id']:{'status':'open','shown':0,'low_interest':False} for c in g['concepts']}}
        paper={'key':'other','title':'Photonic calibration methods','abstract':'Photonic calibration instruments.'}
        proof={};picks=route_batch.choose(route,[paper],[('other',1)],5,evidence=proof)
        self.assertEqual(picks[0][1],'side');self.assertEqual(proof['other']['kind'],'side_branch')
        g['concepts'].pop();route['progress'].pop('side');proof={}
        picks=route_batch.choose(route,[paper],[('other',1)],5,
            directions=[{'name':'Calibration','papers':['other'],'positive_basis':[{'key':'liked','title':'Calibration reference'}]}],evidence=proof)
        self.assertEqual(picks[0][2],'explore_new');self.assertEqual(proof['other']['kind'],'direction_proposal')
        self.assertEqual(proof['other']['positive_basis'][0]['key'],'liked')


if __name__ == '__main__':
    unittest.main()
