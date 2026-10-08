"""Real public-source task relationships; finite guards, never scientific gold."""
import json
import unittest
from pathlib import Path

from app import ai_evidence, growthproposal
from app.gateway import input_bound, request_envelope


PUBLIC = json.loads((Path(__file__).parent / 'fixtures/task_relations_public.json').read_text())['papers']


class PublicTaskRelationTests(unittest.TestCase):
    def paper(self, suffix):
        return next(p for p in PUBLIC if p['key'].endswith(suffix))

    def graph(self, name, terms, kind='topic'):
        return {'concepts': [{'id': 'task', 'name': name, 'terms': terms, 'type': kind}],
                'prereqs': [], 'targets': ['task']}

    def judge(self, paper, graph, quote, obj, scope='', reason='Literal task relation'):
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': reason,
                'evidence': [{'paper': 'p1', 'quote': quote, 'object': obj, 'treatment': '', 'type': 'unknown'}]}
        out, error = growthproposal.validate_result(item, [paper], graph, [], fixed_scope=scope)
        self.assertIsNone(error)
        return out

    def ref_reply(self, item, sent):
        """Select a real frozen option for an explicitly positive fixture."""
        result = dict(item)
        result['evidence'] = {entry['paper']: {'type': entry['type'],
            'snippet': next(sid for sid, option in sent[entry['paper']]['snippets'].items()
                            if entry['quote'] in option['text'])} for entry in item['evidence']}
        return result

    def test_action_input_prediction_without_literal_graph_alias_is_supported(self):
        paper = self.paper('2405.15223')
        graph = self.graph('动作条件动力学', ['world model', 'latent dynamics'])
        quote = 'action-conditioned video prediction, visual planning'
        out = self.judge(paper, graph, quote, 'action-conditioned video prediction')
        self.assertEqual(out['proposal_type'], 'covered')
        self.assertEqual(out['support_role'], 'prediction')
        citation = out['source_evidence'][0]
        self.assertEqual(paper[citation['field']][citation['start']:citation['end']], quote)

    def test_group_contract_examples_and_singular_field_rejection(self):
        graph = self.graph('动作条件动力学', ['world model'])
        paper = self.paper('2405.15223')
        system = growthproposal.messages([paper], graph, [])[0]['content']
        self.assertIn('"papers":["p1"]', system)
        self.assertIn('evidence以p为键，不是数组', system)
        out, error = growthproposal.validate_result({'paper': 'p1', 'verdict': 'unclear', 'reason': 'Unknown'}, [paper], graph, [])
        self.assertIsNone(out); self.assertEqual(error, 'unexpected_fields')

    def test_proved_same_action_ability_does_not_create_duplicate_task(self):
        paper = self.paper('2405.15223')
        graph = self.graph('动作条件动力学', ['world model', 'latent dynamics'])
        sent = json.loads(growthproposal.messages([paper], graph, [])[1]['content'])['papers']
        raw = {'papers':['p1'], 'verdict':'new_task', 'parent':'c1', 'needs':['c1'],
               'name':'Action-Conditioned Video World Model', 'terms':['action-conditioned video prediction'],
               'intro':'Predict future video from action inputs.', 'barrier':'Training data', 'reason':'New model method',
               'evidence':[{'paper':'p1', 'quote':'action-conditioned video prediction, visual planning',
                            'object':'action-conditioned video prediction', 'treatment':'', 'type':'unknown'}]}
        raw = self.ref_reply(raw, sent)
        out, error = growthproposal.validate_result(raw, [paper], graph, [], sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
        self.assertEqual(out['nearest'], '动作条件动力学')
        self.assertEqual(out['needs'], []); self.assertEqual(out['support_status'], 'supported_existing_ability')
        self.assertEqual(graph['prereqs'], [])
        invalid = {**raw, 'parent':'c99'}
        out, error = growthproposal.validate_result(invalid, [paper], graph, [], sent_papers=sent)
        self.assertIsNone(out); self.assertEqual(error, 'invalid_parent')

    def test_new_condition_and_planning_comparison_are_not_duplicate_by_keyword(self):
        graph = self.graph('动作条件动力学', ['world model', 'latent dynamics'])
        quote = 'Contact-aware action-conditioned video prediction uses contact constraints for visual planning.'
        paper = {'key':'public-control', 'title':'Contact-aware prediction', 'abstract':quote}
        sent = json.loads(growthproposal.messages([paper], graph, [])[1]['content'])['papers']
        raw = {'papers':['p1'], 'verdict':'new_branch', 'name':'Contact-aware Action Prediction',
               'terms':['contact constraints'], 'intro':'Action-conditioned prediction under contact constraints.',
               'barrier':'Contact modeling', 'reason':'Compare contact-constrained predictions.', 'needs':[],
               'evidence':[{'paper':'p1','quote':quote,'object':'contact constraints','treatment':'','type':'unknown'}]}
        raw = self.ref_reply(raw, sent)
        out, error = growthproposal.validate_result(raw, [paper], graph, [], sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'new_branch')
        hidden_condition = {**raw, 'name':'Action-Conditioned Video Model', 'intro':'Contact-aware prediction from actions.'}
        out, error = growthproposal.validate_result(hidden_condition, [paper], graph, [], sent_papers=sent)
        self.assertEqual(out['proposal_type'], 'new_branch')
        graph = self.graph('Visual planning', ['planning'])
        raw.update(name='Risk-constrained Planning', intro='Compare risk-constrained planning.', terms=['risk constraint'])
        out, error = growthproposal.validate_result(raw, [paper], graph, [], sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'new_branch')

    def test_duplicate_conditions_are_bidirectional_and_input_predicate_is_core(self):
        ordinary = 'The model predicts future video conditioned on control inputs.'
        contact = 'The model predicts future video conditioned on control inputs under contact constraints.'
        forces = 'The model predicts future video conditioned on actions and contact forces.'
        for existing_intro, proposed_intro, quote, expected in [
            ('', 'Predict future video from actions under contact constraints.', contact, 'new_branch'),
            ('', 'Predict future video conditioned on actions and contact forces.', forces, 'new_branch'),
            ('Contact-aware action-conditioned prediction under contact constraints.', 'Predict future video from actions.', ordinary, 'new_branch'),
            ('', 'Predict future video conditioned on control inputs.', ordinary, 'covered')]:
            with self.subTest(existing=existing_intro, proposed=proposed_intro):
                graph = self.graph('动作条件动力学', ['world model'])
                graph['concepts'][0]['intro'] = existing_intro
                paper = {'key':'control', 'title':'Action-conditioned prediction', 'abstract':quote}
                sent = json.loads(growthproposal.messages([paper], graph, [])[1]['content'])['papers']
                raw = {'papers':['p1'], 'verdict':'new_branch', 'name':'Action-Conditioned Video World Model',
                       'terms':['action-conditioned prediction'], 'intro':proposed_intro, 'barrier':'', 'reason':'Proposed ability', 'needs':[],
                       'evidence':[{'paper':'p1','quote':quote,'object':'actions' if quote == forces else 'control inputs','treatment':'','type':'unknown'}]}
                raw = self.ref_reply(raw, sent)
                out, error = growthproposal.validate_result(raw, [paper], graph, [], sent_papers=sent)
                self.assertIsNone(error); self.assertEqual(out['proposal_type'], expected)

    def test_historical_observation_prediction_does_not_prove_action_conditioning(self):
        paper = self.paper('2608.20284')
        graph = self.graph('动作条件动力学', ['world model', 'latent dynamics'])
        quote = 'forecasts future visual states and instrument trajectories from historical surgical observations'
        out = self.judge(paper, graph, quote, 'historical surgical observations')
        self.assertEqual(out['proposal_type'], 'unclear')

    def test_planning_evaluation_is_selected_and_not_excluded_as_model_compression(self):
        paper = self.paper('2602.02110')
        graph = self.graph('规划泛化评估', ['model uncertainty', 'generalization'])
        quote = 'We conduct extensive experiments on different visual planning tasks across a wide range of bit-widths, quantization granularities, and planning horizons'
        selected = ai_evidence.fragments(paper, graph)
        self.assertIn(quote, selected['abstract'])
        out = self.judge(paper, graph, quote, 'visual planning tasks')
        self.assertEqual(out['proposal_type'], 'covered')
        self.assertEqual(out['support_role'], 'evaluation')

    def test_specific_response_finding_is_not_basic_ligand_axis_coverage(self):
        paper = self.paper('uxac020')
        graph = self.graph('PD1/PDL1免疫轴', ['PD-1', 'PD-L1'], 'foundation')
        quote = paper['title']
        out = self.judge(paper, graph, quote, 'CD155 expression', 'NSCLC PD-1 resistance')
        self.assertEqual(out['proposal_type'], 'unclear')
        self.assertEqual(out['support_status'], 'specific_task_not_foundation')

    def test_unknown_electrolyte_cannot_be_declared_proven_nonsulfide(self):
        graph = self.graph('锂金属界面反应', ['lithium metal interface'])
        paper = {'key': 'unidentified', 'title': 'Electrolyte interface stability', 'abstract': ''}
        raw = {'papers': ['p1'], 'verdict': 'unclear', 'reason': 'The electrolyte is non-sulfide and unrelated.'}
        out, error = growthproposal.validate_result(raw, [paper], graph, [], fixed_scope='sulfide electrolyte')
        self.assertIsNone(error)
        self.assertNotIn('non-sulfide', out['reason'])
        self.assertIn('尚未确认', out['reason'])

    def test_small_map_uses_existing_wire_headroom_and_validates_actual_sent_context(self):
        paper = self.paper('s12943-021-01448-x')
        graph = self.graph('微环境耐药', ['tumor microenvironment', 'T cell exhaustion'])
        messages = growthproposal.messages([paper], graph, [], fixed_scope='NSCLC PD-1 resistance')
        sent = json.loads(messages[1]['content'])['papers']
        self.assertEqual(sent['p1']['title'], paper['title'])
        self.assertGreater(len(sent['p1']['abstract']), 180)
        self.assertLessEqual(len(sent['p1']['abstract']), 480)
        self.assertLessEqual(input_bound(request_envelope('route_growth_judge', 'deepseek-flash', 1000, messages)), 8000)
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'CD8 cell dysfunction',
                'evidence': [{'paper': 'p1', 'quote': paper['title'], 'object': 'CD8+ T cell', 'treatment': 'anti-PD1', 'type': 'unknown'}]}
        item = self.ref_reply(item, sent)
        out, error = growthproposal.validate_result(item, [paper], graph, [], fixed_scope='NSCLC PD-1 resistance', sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
        self.assertEqual(out['support_role'], 'mechanism')
        self.assertEqual(out['source_evidence'][0]['start'], 0)
        altered = {'p1': {**sent['p1'], 'title': 'Invented NSCLC PD-1 mechanism'}}
        out, error = growthproposal.validate_result(item, [paper], graph, [], fixed_scope='NSCLC PD-1 resistance', sent_papers=altered)
        self.assertIsNone(out); self.assertEqual(error, 'invalid_snippet_reference')

    def test_scope_evidence_is_separate_literal_context_not_a_joined_quote(self):
        graph = self.graph('微环境耐药', ['tumor microenvironment', 'T cell exhaustion'])
        paper = {'key': 'synthetic-control', 'title': 'NSCLC PD-1 resistance study',
                 'abstract': 'CD8 T cell dysfunction was measured in vitro.'}
        sent = json.loads(growthproposal.messages([paper], graph, [], fixed_scope='NSCLC PD-1')[1]['content'])['papers']
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Quoted immune function',
                'evidence': [{'paper': 'p1', 'quote': paper['abstract'], 'object': 'CD8 T cell', 'treatment': '', 'type': 'basic'}]}
        item = self.ref_reply(item, sent)
        out, error = growthproposal.validate_result(item, [paper], graph, [], fixed_scope='NSCLC PD-1', sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
        citation = out['source_evidence'][0]
        self.assertEqual(citation['quote'], paper['abstract'])
        for context in citation['visible_scope']:
            self.assertEqual(paper[context['field']][context['start']:context['end']], context['quote'])
        # Actual wrong object cannot be excused by a target named in the title.
        wrong = {**paper, 'abstract': 'CD8 T cell dysfunction in melanoma was measured in vitro.'}
        sent = json.loads(growthproposal.messages([wrong], graph, [], fixed_scope='NSCLC PD-1')[1]['content'])['papers']
        item['evidence']['p1']['snippet'] = next(sid for sid, option in sent['p1']['snippets'].items()
                                            if wrong['abstract'] in option['text'])
        out, error = growthproposal.validate_result(item, [wrong], graph, [], fixed_scope='NSCLC PD-1', sent_papers=sent)
        self.assertEqual(out['proposal_type'], 'unclear')
        self.assertEqual(out['support_status'], 'explicit_scope_conflict')

    def test_broad_alias_never_overrides_action_qualifier_or_treatment(self):
        graph = self.graph('动作条件动力学', ['world model'])
        for quote in ('A world model predicts from historical observations.',
                      'The model is not action-conditioned and predicts video.',
                      'Actions are not used as inputs for visual prediction.',
                      "Actions aren't inputs to video prediction.",
                      'An action-conditioned model does not predict video.',
                      'Action-conditioned video prediction is not used by this model.',
                      'Actions occur. Prediction is performed separately.'):
            paper = {'key': 'control', 'title': quote, 'abstract': quote}
            out = self.judge(paper, graph, quote, 'model' if 'model' in quote else 'Actions')
            self.assertEqual(out['proposal_type'], 'unclear')
        graph = self.graph('PD-1 resistance', ['PD-1 resistance'])
        quote = 'NSCLC platinum-resistant cells were studied in vitro.'
        paper = {'key': 'control', 'title': 'NSCLC PD-1 comparison', 'abstract': quote}
        sent = json.loads(growthproposal.messages([paper], graph, [], fixed_scope='NSCLC PD-1')[1]['content'])['papers']
        item = {'papers':['p1'], 'verdict':'covered', 'nearest':'c1', 'reason':'Control',
                'evidence':[{'paper':'p1', 'quote':quote, 'object':'NSCLC', 'treatment':'platinum', 'type':'basic'}]}
        item = self.ref_reply(item, sent)
        out, _ = growthproposal.validate_result(item, [paper], graph, [], fixed_scope='NSCLC PD-1', sent_papers=sent)
        self.assertEqual(out['proposal_type'], 'unclear')
        self.assertEqual(out['support_status'], 'explicit_scope_conflict')

    def test_negated_performance_is_not_execution_but_affirmative_contrast_survives(self):
        graph = self.graph('规划泛化评估', ['model uncertainty', 'generalization'])
        for quote, expected in [('No experiments or planning evaluations were performed.', 'unclear'),
                                ('Planning experiments were not performed.', 'unclear'),
                                ('No extra experiments, but planning evaluations were performed.', 'covered')]:
            paper = {'key': 'control', 'title': 'Public comparison', 'abstract': quote}
            out = self.judge(paper, graph, quote, 'planning' if 'planning' in quote else 'Planning')
            self.assertEqual(out['proposal_type'], expected)

    def test_sulfide_coating_is_not_proof_of_sulfide_electrolyte(self):
        graph = self.graph('锂金属界面反应', ['lithium metal interface', 'interphase'])
        quote = 'Metal sulfide artificial interphase on lithium metal was studied.'
        paper = {'key': 'control', 'title': quote, 'abstract': quote}
        out = self.judge(paper, graph, quote, 'lithium metal', 'sulfide electrolyte interface')
        self.assertEqual(out['proposal_type'], 'unclear')
        self.assertEqual(out['support_status'], 'missing_scope_evidence')
        self.assertNotIn('非硫化物', out['reason'])
        quote = 'The lithium metal interface used a sulfide coating; a sulfide electrolyte was not used.'
        paper = {'key': 'control', 'title': quote, 'abstract': quote}
        out = self.judge(paper, graph, quote, 'lithium metal', 'sulfide solid electrolyte')
        self.assertEqual(out['proposal_type'], 'unclear')
        self.assertEqual(out['support_status'], 'explicit_scope_conflict')


if __name__ == '__main__':
    unittest.main()
