"""Frozen literal-reference boundaries; logical controls are not science gold."""
import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from app import ai_evidence, growthproposal, snippet_contract, learning_scope
from app.gateway import input_bound, request_envelope
from test_public_task_relations import PUBLIC


class SnippetContractTests(unittest.TestCase):
    def graph(self, name='动作条件动力学', terms=None):
        return {'concepts': [{'id': 'task', 'name': name, 'terms': terms or ['world model']}],
                'prereqs': [], 'targets': ['task']}

    def payload(self, abstract, graph=None, title='Public source', scope=''):
        graph = graph or self.graph()
        paper = {'key': 'public-control', 'title': title, 'abstract': abstract}
        messages = growthproposal.messages([paper], graph, [], fixed_scope=scope)
        sent = json.loads(messages[-1]['content'])['papers']
        return paper, graph, sent, messages

    def reference(self, sent, text=None, kind='unknown'):
        table = sent['p1']['snippets']
        sid = next((sid for sid, option in table.items() if text and text in option['text']),
                   next(iter(table)))
        return {'snippet': sid, 'type': kind}

    def outcome(self, paper, graph, sent, evidence, scope='', reason='Literal task relation'):
        return growthproposal.validate_result({'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1',
            'reason': reason, 'evidence': evidence}, [paper], graph, [], fixed_scope=scope, sent_papers=sent)

    def literal_option(self, sent, text):
        """A bounded actual-wire option exercising selected vs enclosing text."""
        field = next(f for f in ('title', 'abstract') if text in sent['p1'][f])
        start = sent['p1'][field+'_start'] + sent['p1'][field].index(text)
        sent['p1']['snippets'] = {'p1.a1': {'field': field, 'start': start, 'end': start+len(text), 'text': text}}
        return {'snippet': 'p1.a1', 'type': 'unknown'}

    def test_real_public_task_relationships_survive_reference_expansion(self):
        controls = [('2405.15223', self.graph(), 'action-conditioned video prediction', 'prediction', ''),
                    ('2602.02110', self.graph('规划泛化评估', ['generalization']), 'visual planning tasks', 'evaluation', ''),
                    ('s12943-021-01448-x', self.graph('微环境耐药', ['tumor microenvironment']),
                     'CD8', 'mechanism', 'NSCLC PD-1 resistance')]
        for suffix, graph, term, role, scope in controls:
            with self.subTest(paper=suffix):
                paper = next(p for p in PUBLIC if p['key'].endswith(suffix))
                messages = growthproposal.messages([paper], graph, [], fixed_scope=scope)
                sent = json.loads(messages[-1]['content'])['papers']
                out, error = self.outcome(paper, graph, sent, {'p1': self.reference(sent, term)}, scope)
                self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
                citation = out['source_evidence'][0]
                self.assertEqual(out['support_role'], role)
                self.assertEqual(paper[citation['field']][citation['start']:citation['end']], citation['quote'])
                self.assertEqual(citation['snippet_snapshot_sha256'], snippet_contract.fingerprint(sent))
                self.assertEqual(citation['object'], ''); self.assertEqual(citation['treatment'], '')

    def test_reference_field_and_paper_boundaries_reject_without_conversion(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        base = self.reference(sent, 'predicts')
        bad = [dict(base, snippet='p1.a99'), dict(base, snippet='p2.a1'), dict(base, paper='p2'),
               dict(base, quote='free quote'), dict(base, type='clinical'),
               {'paper':'p1','quote':paper['abstract'],'object':'','treatment':'','type':'unknown'}]
        for evidence in bad:
            with self.subTest(evidence=evidence):
                out, error = self.outcome(paper, graph, sent, {'p1':evidence})
                self.assertIsNone(out); self.assertIn(error, ('invalid_evidence', 'invalid_snippet_reference'))
        out, error = self.outcome(paper, graph, sent, [base, base])
        self.assertIsNone(out); self.assertEqual(error, 'invalid_evidence')
        self.assertIsNone(ai_evidence.source_evidence(bad[-1:], ['p1'], [paper], graph))

    def test_keyed_singleton_has_complete_papers_and_rejects_old_array_values(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        ref = self.reference(sent, 'predicts')
        for value in ([{'paper':'p1', **ref}], {'p1':[ref]}, {'p1':{'snippet':[ref['snippet']], 'type':'unknown'}},
                      {'p2':ref}, {'p1':ref,'p2':ref}, {'p1':None}, {'p1':{**ref,'paper':'p1'}}):
            with self.subTest(evidence=value):
                out, error = self.outcome(paper, graph, sent, value)
                self.assertIsNone(out); self.assertEqual(error, 'invalid_evidence')
        second = {**paper, 'key':'second'}
        second_sent = json.loads(growthproposal.messages([paper,second],graph,[])[1]['content'])['papers']
        sid = next(iter(second_sent['p2']['snippets']))
        value = {'p1':self.reference(second_sent), 'p2':{'snippet':sid,'type':'unknown'}}
        citations, error = snippet_contract.evidence(value,['p1','p2'],[paper,second],second_sent)
        self.assertIsNone(error); self.assertEqual([c['paper'] for c in citations],['p1','p2'])
        value['p2']['snippet'] = value['p1']['snippet']
        citations, error = snippet_contract.evidence(value,['p1','p2'],[paper,second],second_sent)
        self.assertIsNone(citations); self.assertEqual(error,'invalid_snippet_reference')

    def test_raw_duplicate_json_keys_cannot_be_overwritten_or_repaired(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        sid = self.reference(sent, 'predicts')['snippet']
        entry = json.dumps({'snippet':sid,'type':'unknown'})
        prefix = '{"results":[{"papers":["p1"],"verdict":"covered","nearest":"c1","reason":"Literal",'
        for evidence in ('{"p1":'+entry+',"p1":'+entry+'}',
                         '{"p1":{"snippet":"bad","snippet":'+json.dumps(sid)+',"type":"unknown"}}',
                         '{"p1":{"snippet":'+json.dumps(sid)+',"type":"trial","type":"unknown"}}'):
            groups, error = growthproposal.parse_result(prefix+'"evidence":'+evidence+'}]}')
            self.assertEqual(groups,[]); self.assertEqual(error,'invalid_json')
        groups, error = growthproposal.parse_result(prefix+'"evidence":{"p1":'+entry+'}}]}')
        self.assertIsNone(error)
        out, error = growthproposal.validate_result(groups[0],[paper],graph,[],sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'],'covered')

    def test_v1_marker_cannot_silently_accept_v2_or_free_quotes(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        old = copy.deepcopy(sent); old['p1']['evidence_contract'] = 'public-snippet-ref-v1'
        for value in ({'p1':self.reference(sent,'predicts')},
                      [{'paper':'p1','quote':paper['abstract'],'object':'actions','treatment':'','type':'unknown'}]):
            out, error = self.outcome(paper,graph,old,value)
            self.assertIsNone(out); self.assertEqual(error,'invalid_snippet_reference')

    def test_actual_r39_next_batch_states_admit_by_reducing_optional_options(self):
        cases = json.loads((Path(__file__).parent/'fixtures/snippet_packing_r39_public.json').read_text())['cases']
        original = snippet_contract.options
        for case in cases:
            with self.subTest(case=case['case']):
                def always_three(selected, ref, graph, **kwargs):
                    return original(selected,ref,graph,max_options=3)
                with mock.patch.object(snippet_contract,'options',side_effect=always_three):
                    with self.assertRaisesRegex(ValueError,'没有截断Map'):
                        growthproposal.messages(case['papers'],case['graph'],case['directions'],case['english'],
                                                fixed_scope=case['fixed_scope'])
                messages = growthproposal.messages(case['papers'],case['graph'],case['directions'],case['english'],
                                                   fixed_scope=case['fixed_scope'])
                body = json.loads(messages[1]['content'])
                self.assertLessEqual(input_bound(request_envelope('route_growth_judge','deepseek-flash',1000,messages)),8000)
                self.assertEqual(len(body['map']['concepts']),len(case['graph']['concepts']))
                self.assertEqual(len(body['map']['prereqs']),len(case['graph']['prereqs']))
                self.assertEqual(body['directions'],{f'd{i+1}':{k:d.get(k) for k in ('name','intro','proposal_type')}
                                                     for i,d in enumerate(case['directions'])})
                self.assertTrue(any(len(p['snippets']) < 3 for p in body['papers'].values()))
                refs = {}
                for i,paper in enumerate(case['papers']):
                    alias=f'p{i+1}';record=body['papers'][alias]
                    self.assertGreaterEqual(len(record['snippets']),1)
                    for field in ('title','abstract'):
                        start=record[field+'_start']
                        self.assertEqual(paper[field][start:start+len(record[field])],record[field])
                    for sid,option in record['snippets'].items():
                        self.assertEqual(paper[option['field']][option['start']:option['end']],option['text'])
                    refs[alias]={'snippet':next(iter(record['snippets'])),'type':'unknown'}
                citations,error=snippet_contract.evidence(refs,list(refs),case['papers'],body['papers'])
                self.assertIsNone(error);self.assertEqual(len(citations),3)

    def test_optional_options_keep_best_existing_score_and_do_not_rescue_large_map(self):
        paper,graph,sent,_=self.payload('Unrelated background. The model predicts future video conditioned on actions.')
        selected=sent['p1']
        for count in (1,2,3):
            table=snippet_contract.options(selected,'p1',graph,max_options=count)
            self.assertLessEqual(len(table),count);self.assertTrue(table)
            self.assertTrue(any('predicts' in option['text'] for option in table.values()))
        for invalid in (0,4,True):
            with self.assertRaises(ValueError):snippet_contract.options(selected,'p1',graph,max_options=invalid)
        graph['concepts'][0]['intro']='Complete user Map text '*1000
        with self.assertRaisesRegex(ValueError,'没有截断Map'):
            growthproposal.messages([paper],graph,[])

    def test_frozen_offsets_and_sent_field_must_both_agree(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        ref = self.reference(sent, 'predicts')
        for change in ('start', 'end', 'text', 'field', 'bool', 'sent', 'offset', 'outside'):
            altered = copy.deepcopy(sent); option = altered['p1']['snippets'][ref['snippet']]
            if change in ('start', 'end'): option[change] += 1
            elif change == 'text': option['text'] = 'Invented action-conditioned prediction'
            elif change == 'field': option['field'] = 'body'
            elif change == 'bool': option['start'] = True
            elif change == 'sent': altered['p1']['abstract'] = 'Invented task context'
            elif change == 'offset': altered['p1']['abstract_start'] += 1
            elif change == 'outside': option.update(start=20001, end=20020)
            with self.subTest(change=change):
                out, error = self.outcome(paper, graph, altered, {'p1': ref})
                self.assertIsNone(out); self.assertEqual(error, 'invalid_snippet_reference')

    def test_nearby_actual_negation_cannot_be_hidden_by_a_selected_short_ref(self):
        for text, selected, graph, scope in [
            ('Action-conditioned video prediction is not used by this model.', 'Action-conditioned video prediction', self.graph(), ''),
            ('No experiments or planning evaluations were performed.', 'planning evaluations', self.graph('规划泛化评估', ['generalization']), ''),
            ('The lithium metal interface used a sulfide coating; a sulfide electrolyte was not used.',
             'sulfide electrolyte', self.graph('锂金属界面反应', ['lithium metal interface']), 'sulfide electrolyte')]:
            paper, graph, sent, _ = self.payload(text, graph, scope=scope)
            ref = self.literal_option(sent, selected)
            out, error = self.outcome(paper, graph, sent, {'p1': ref}, scope)
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'unclear')

    def test_blank_objects_do_not_bypass_actual_target_conflicts(self):
        controls = [
            ('PD-1 resistance in melanoma was studied in vitro.', self.graph('PD-1 resistance', ['PD-1 resistance']), 'NSCLC PD-1 resistance'),
            ('NSCLC platinum-resistant cells were studied in vitro.', self.graph('PD-1 resistance', ['PD-1 resistance']), 'NSCLC PD-1 resistance'),
            ('Sulfide electrolyte bulk ionic conductivity was measured.', self.graph('Cathode interface', ['cathode interface']), 'sulfide electrolyte interface'),
            ('The liquid lithium interface used a sulfide electrolyte.', self.graph('锂金属界面反应', ['lithium metal interface']), 'sulfide electrolyte')]
        for abstract, graph, scope in controls:
            paper, graph, sent, _ = self.payload(abstract, graph, title='NSCLC PD-1 comparison', scope=scope)
            ref = self.literal_option(sent, abstract)
            out, error = self.outcome(paper, graph, sent, {'p1': ref}, scope)
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'unclear')

    def test_fixed_sulfide_identity_survives_removing_the_foundation_node(self):
        graph = self.graph('锂金属界面反应', ['lithium metal interface'])
        for goal in ('Study the lithium metal interface with sulfide electrolyte.',
                     'Study the lithium metal interface with sulfide solid-state electrolyte.',
                     'Study the lithium metal interface with a sulfide all-solid-state electrolyte.'):
            scope = learning_scope.as_text(learning_scope.make({'goal':goal}))
            self.assertIn('sulfide', scope)
            for text, expected in [
                ('The lithium metal interface used a sulfide coating.', 'unclear'),
                ('The lithium metal interface used a sulfide electrolyte.', 'covered'),
                ('The lithium metal interface with a sulfide all-solid-state electrolyte was measured.', 'covered'),
                ('The lithium metal interface used a sulfide electrolyte that was not present.', 'unclear')]:
                paper, graph, sent, _ = self.payload(text, graph, scope=scope)
                out, error = self.outcome(paper, graph, sent, {'p1': self.reference(sent, text)}, scope)
                self.assertIsNone(error); self.assertEqual(out['proposal_type'], expected)
        for goal in ('Exclude sulfide electrolyte.', 'Study non-sulfide electrolyte.',
                     'Sulfide coating with oxide electrolyte.', '不研究硫化物电解质，只研究氧化物电解质。'):
            self.assertFalse(any(c['kind']=='sulfide_electrolyte'
                for c in learning_scope.make({'goal':goal}, ['sulfide electrolyte'])['constraints']))
        for goal in ('Sulfide coating and electrolyte studies.', 'Sulfide. Electrolyte studies.'):
            self.assertFalse(any(c['kind']=='sulfide_electrolyte' for c in learning_scope.make({'goal':goal})['constraints']))
        generic = learning_scope.make({'goal':'Study lithium metal interface with an electrolyte.'}, ['sulfide electrolyte'])
        self.assertTrue(any(c['kind']=='sulfide_electrolyte' for c in generic['constraints']))

    def test_typed_claim_needs_quoted_markers_and_cannot_hide_basic_study(self):
        text = 'The clinical trial was simulated in mice with no clinical trial conducted.'
        paper, graph, sent, _ = self.payload(text, self.graph('PD-1 resistance', ['PD-1 resistance']),
                                              title='NSCLC PD-1 resistance study', scope='NSCLC PD-1')
        ref = self.literal_option(sent, 'clinical trial'); ref['type'] = 'trial'
        out, error = self.outcome(paper, graph, sent, {'p1': ref}, 'NSCLC PD-1', 'Clinical benefit improves survival')
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'unclear')
        ref['type'] = 'basic'
        citations, error = snippet_contract.evidence({'p1': ref}, ['p1'], [paper], sent)
        self.assertIsNone(error); self.assertIsNone(citations)  # Marker is outside chosen quote.

    def test_unknown_and_optional_relations_do_not_become_hard_prerequisites(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        item = {'papers':['p1'], 'verdict':'new_task', 'parent':'c1', 'name':'New Condition',
                'terms':['new condition'], 'intro':'Compare a new condition.', 'barrier':'', 'reason':'Possible comparison',
                'needs':[], 'evidence':{'p1':self.reference(sent, 'predicts')}}
        out, error = growthproposal.validate_result(item, [paper], graph, [], sent_papers=sent)
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'new_branch')
        self.assertEqual(out['needs'], []); self.assertIsNone(out['parent']); self.assertTrue(out['optional_relation'])

    def test_entire_study_simulation_veto_is_distinct_from_separate_mouse_comparison(self):
        first = 'NSCLC PD-1 resistance was assessed in a randomized clinical trial.'
        graph = self.graph('PD-1 resistance', ['PD-1 resistance'])
        for tail, expected in [
            (' All reported findings are simulations in mice; no human patients were enrolled.', 'unclear'),
            (' All reported findings are simulations in mice, informed by prior clinical studies.', 'unclear'),
            (' This study uses simulations in mice compared with prior clinical studies.', 'unclear'),
            (' No human patients were enrolled.', 'unclear'),
            (' Separate mouse experiments were performed to compare the mechanism.', 'covered'),
            (' Prior mouse studies motivated the current patient trial.', 'covered'),
            (' Prior study used mice; current trial enrolled human patients.', 'covered'),
            (' This study used patient data compared with prior mouse experiments.', 'covered')]:
            paper, graph, sent, _ = self.payload(first+tail, graph, scope='NSCLC PD-1')
            ref = self.reference(sent, first, 'trial')
            out, error = self.outcome(paper, graph, sent, {'p1': ref}, 'NSCLC PD-1', 'Randomized resistance study')
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], expected)
        text = 'A randomized clinical trial of NSCLC PD-1 resistance enrolled patients, compared with prior mouse experiments.'
        paper, graph, sent, _ = self.payload(text, graph, scope='NSCLC PD-1')
        out, error = self.outcome(paper, graph, sent, {'p1': self.reference(sent, text, 'trial')}, 'NSCLC PD-1')
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')

    def test_trial_marker_alone_does_not_prove_survival_benefit(self):
        graph = self.graph('PD-1 resistance', ['PD-1 resistance'])
        for text, expected in [
            ('NSCLC PD-1 resistance was assessed in a randomized clinical trial.', 'unclear'),
            ('A randomized clinical trial reported improved survival after PD-1 treatment in NSCLC resistance.', 'covered'),
            ('A randomized clinical trial found no improved survival after PD-1 treatment in NSCLC resistance.', 'unclear'),
            ('A randomized clinical trial failed to improve survival after PD-1 treatment in NSCLC resistance.', 'unclear'),
            ("A randomized clinical trial didn't improve survival after PD-1 treatment in NSCLC resistance.", 'unclear'),
            ('In a clinical trial of NSCLC PD-1 resistance, improved survival was not observed.', 'unclear'),
            ('The clinical trial in NSCLC PD-1 resistance found improved survival was absent.', 'unclear'),
            ('A clinical trial in NSCLC PD-1 resistance evaluated whether treatment could improve survival.', 'unclear')]:
            paper, graph, sent, _ = self.payload(text, graph, scope='NSCLC PD-1')
            ref = self.reference(sent, text, 'trial')
            out, error = self.outcome(paper, graph, sent, {'p1': ref}, 'NSCLC PD-1', 'Clinical benefit improves survival')
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], expected)

    def test_options_are_bounded_literal_ranges_and_preserve_formula_abbreviations(self):
        text = 'U.S. researchers used Li2S.P2S5 and e.g. Li6PS5Cl. The model predicts video from actions.'
        paper, graph, sent, messages = self.payload(text)
        ranges = list(snippet_contract.sentence_ranges(text))
        self.assertEqual(text[ranges[0][0]:ranges[0][1]], 'U.S. researchers used Li2S.P2S5 and e.g. Li6PS5Cl.')
        self.assertLessEqual(len(sent['p1']['snippets']), 3)
        for sid, option in sent['p1']['snippets'].items():
            self.assertTrue(sid.startswith('p1.')); self.assertLessEqual(len(option['text']), 160)
            self.assertEqual(paper[option['field']][option['start']:option['end']], option['text'])
        self.assertLessEqual(input_bound(request_envelope('route_growth_judge', 'deepseek-flash', 1000, messages)), 8000)
        numeric = 'A value of 0.25 was measured at 934. The model predicts video from actions.'
        first = next(snippet_contract.sentence_ranges(numeric))
        self.assertEqual(numeric[first[0]:first[1]], 'A value of 0.25 was measured at 934.')

    def test_repeated_text_uses_frozen_offset_and_not_first_substring_match(self):
        text = 'The model predicts video from actions.'
        paper = {'key':'repeated', 'title':'Public repeated source', 'abstract':text+' Background. '+text}
        graph = self.graph()
        start = paper['abstract'].rindex(text)
        sent = {'p1': {'title':paper['title'], 'title_start':0, 'abstract':text, 'abstract_start':start,
                      'evidence_contract':snippet_contract.VERSION,
                      'snippets':{'p1.a1':{'field':'abstract','start':start,'end':start+len(text),'text':text}}}}
        citations, error = snippet_contract.evidence({'p1':{'snippet':'p1.a1','type':'unknown'}}, ['p1'], [paper], sent)
        self.assertIsNone(error); self.assertEqual(citations[0]['start'], start)
        altered = copy.deepcopy(sent); altered['p1']['snippets']['p1.a1'].update(start=0, end=len(text))
        citations, error = snippet_contract.evidence({'p1':{'snippet':'p1.a1','type':'unknown'}}, ['p1'], [paper], altered)
        self.assertIsNone(citations); self.assertEqual(error, 'invalid_snippet_reference')

    def test_selected_reference_cannot_hide_conflicting_electrode_or_liquid_object(self):
        graph = self.graph('锂金属界面反应', ['lithium metal interface'])
        for text, selected in [
            ('The cathode interface used a sulfide electrolyte.', 'interface used a sulfide electrolyte'),
            ('The liquid lithium interface used a sulfide electrolyte.', 'interface used a sulfide electrolyte')]:
            paper, graph, sent, _ = self.payload(text, graph, scope='sulfide electrolyte')
            ref = self.literal_option(sent, selected)
            out, error = self.outcome(paper, graph, sent, {'p1': ref}, 'sulfide electrolyte')
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'unclear')
            self.assertEqual(out['support_status'], 'explicit_scope_conflict')

    def test_empty_or_missing_proof_is_uncertain_but_long_or_paragraph_refs_reject(self):
        paper, graph, sent, _ = self.payload('The model predicts future video conditioned on actions.')
        for evidence in ({}, None):
            item = {'papers':['p1'], 'verdict':'covered', 'nearest':'c1', 'reason':'Insufficient'}
            if evidence is not None: item['evidence'] = evidence
            out, error = growthproposal.validate_result(item, [paper], graph, [], sent_papers=sent)
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'unclear')
        for separator in ('\n\n', '\r\n\r\n', '\f', '\u2029'):
            altered = copy.deepcopy(sent)
            text = 'Actions' + separator + 'predict future video'
            altered['p1']['abstract'] = text
            altered['p1']['snippets'] = {'p1.a1': {'field':'abstract','start':0,'end':len(text),'text':text}}
            changed = {**paper, 'abstract':text}
            out, error = self.outcome(changed, graph, altered, {'p1':{'snippet':'p1.a1','type':'unknown'}})
            self.assertIsNone(out); self.assertEqual(error, 'invalid_snippet_reference')


if __name__ == '__main__':
    unittest.main()
