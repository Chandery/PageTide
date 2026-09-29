import importlib.util
import unittest
from app.clustering import cluster


@unittest.skipUnless(importlib.util.find_spec("networkx"), "NetworkX optional dependency not installed")
class BroadOrganizationTests(unittest.TestCase):
    def test_shared_topic_unites_different_methods(self):
        papers = [dict(key=str(i), title=title, topic='World models') for i, title in enumerate([
            'Latent dynamics control robotics', 'Video generation diffusion pixels',
            'Autonomous driving traffic simulation', 'Reinforcement learning planning agents'])]
        result = cluster(papers, broad=True)
        self.assertEqual([g['keys'] for g in result['groups']], [['0', '1', '2', '3']])
        self.assertIn('世界模型', result['groups'][0]['name'])

    def test_cross_discipline_and_unknown_terms(self):
        papers = [dict(key=str(i), title=t) for i, t in enumerate([
            'Cancer immunotherapy immune treatment', 'Cancer immunotherapy clinical outcomes',
            'Medieval manuscript philology textual transmission',
            'Medieval manuscript philology scribal variants', 'Unrelated singular discovery'])]
        result = cluster(papers, broad=True)
        self.assertEqual([g['keys'] for g in result['groups']], [['0', '1'], ['2', '3']])
        self.assertEqual(result['pending_keys'], ['4'])
        for group in result['groups']:
            self.assertRegex(group['name'], r'[\u4e00-\u9fff]')
            self.assertTrue(group['terms'])
            self.assertTrue(group['reason'])
            self.assertEqual(group['color'], '#64748b')

    def test_chinese_papers_are_not_empty_vocabulary(self):
        result = cluster([
            {'key': 'a', 'title': '肿瘤免疫治疗的临床进展'},
            {'key': 'b', 'title': '肿瘤免疫治疗效果评估'},
            {'key': 'c', 'title': '古代文学诗歌的叙事结构'},
            {'key': 'd', 'title': '古代文学诗歌的文本分析'}], broad=True)
        self.assertEqual([g['keys'] for g in result['groups']], [['a', 'b'], ['c', 'd']])

    def test_generic_academic_language_does_not_force_grouping(self):
        result = cluster([
            {'key': 'a', 'title': 'A study of zirconium', 'abstract': 'We present results and analysis of this study.'},
            {'key': 'b', 'title': 'A study of sonnets', 'abstract': 'We present results and analysis of this study.'},
            {'key': 'c', 'title': ''}], broad=True)
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['pending_keys'], ['a', 'b', 'c'])

    def test_same_topic_survives_neighbor_cap(self):
        papers = [dict(key=str(i), title=('Video diffusion pixels generation' if i < 10 else
                                          'Robotics control planning agents'), topic='World models')
                  for i in range(20)]
        self.assertEqual(len(cluster(papers, broad=True)['groups']), 1)

    def test_abstract_only_groups_show_evidence(self):
        result = cluster([dict(key='a', title='Alpha', abstract='Chromatin structure remodeling'),
                          dict(key='b', title='Beta', abstract='Chromatin structure remodeling')], broad=True)
        self.assertTrue(result['groups'][0]['terms'])

    def test_ambiguous_words_do_not_invent_disciplines(self):
        for titles, bad in [(['Solar flare magnetic reconnection plasma', 'Solar flare coronal magnetic activity'], '太阳能'),
                            (['Literature review metal alloy fatigue', 'Literature review metal alloy stress'], '文学研究'),
                            (['古代文学诗歌的叙事结构', '古代文学诗歌的文本分析'], '代文学诗')]:
            result = cluster([dict(key=str(i), title=t) for i, t in enumerate(titles)], broad=True)
            self.assertNotIn(bad, result['groups'][0]['name'])
            self.assertIn('待命名', result['groups'][0]['name'])

    def test_broad_determinism(self):
        papers = [dict(key=str(i), title='Unknown discipline frobnication tensor analysis') for i in range(4)]
        self.assertEqual(cluster(papers, broad=True), cluster(papers[::-1], broad=True))


@unittest.skipUnless(importlib.util.find_spec("networkx"), "NetworkX optional dependency not installed")
class RegroupTests(unittest.TestCase):
    def test_echoed_preview_color_preserves_automatic_status_but_edits_protect(self):
        import tempfile
        from pathlib import Path
        from app.db import Store
        from app.organization import Organization
        for edited in (False, True):
            with self.subTest(edited_color=edited), tempfile.TemporaryDirectory() as root:
                store = Store(Path(root) / 'test.sqlite')
                try:
                    store.init()
                    papers = [dict(key=k, title='Robot control planning') for k in ('a', 'b', 'c')]
                    store.upsert_papers(papers)
                    for key in ('a', 'b'):
                        store.save_to_library(key)
                    org = Organization(store)
                    preview = org.action({'action': 'suggest'})['suggestions']
                    selection = {field: preview['groups'][0][field]
                                 for field in ('id', 'name', 'color', 'keys')}
                    self.assertEqual(selection['color'], '#64748b')
                    if edited:
                        selection['color'] = '#123456'
                    org.action(dict(action='apply-suggestions', fingerprint=preview['fingerprint'],
                                    suggestions=[selection], regroup_auto=True))
                    saved = org.action({'action': 'export'})['organization']['directions'][0]
                    self.assertEqual(saved['manual'], edited)
                    self.assertEqual(saved['color'], selection['color'])
                    old_id = selection['id']
                    store.save_to_library('c')
                    next_preview = org.action({'action': 'suggest'})['suggestions']
                    next_selection = {field: next_preview['groups'][0][field]
                                      for field in ('id', 'name', 'color', 'keys')}
                    self.assertNotEqual(next_selection['id'], old_id)
                    result = org.action(dict(action='apply-suggestions',
                                             fingerprint=next_preview['fingerprint'],
                                             suggestions=[next_selection], regroup_auto=True))
                    memberships = {paper['key']: paper['directions'] for paper in result['items']}
                    self.assertEqual(memberships['a'], [old_id if edited else next_selection['id']])
                    self.assertEqual(memberships['b'], memberships['a'])
                    self.assertEqual(memberships['c'], [next_selection['id']])
                    self.assertEqual(old_id in {d['id'] for d in result['directions']}, edited)
                finally:
                    store.close()

    def test_replaces_only_untouched_automatic_groups_and_undo_restores(self):
        import tempfile
        from pathlib import Path
        from app.db import Store
        from app.organization import Organization
        from unittest.mock import patch
        from app.clustering import corpus_fingerprint
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root) / 'test.sqlite')
            self.addCleanup(store.close)
            store.init()
            papers = [dict(key=k, title='Robot control planning') for k in ('a', 'b', 'c')]
            store.upsert_papers(papers)
            for p in papers:
                store.save_to_library(p['key'])
            org = Organization(store)
            old = dict(fingerprint=corpus_fingerprint(papers), groups=[
                dict(id='old-' + p['key'], name='Old label', keys=[p['key']]) for p in papers])
            with patch('app.organization.cluster', return_value=old):
                org.action({'action': 'suggest'})
            org.action(dict(action='suggest-apply', fingerprint=old['fingerprint']))
            # A manual rename protects its existing memberships too.
            org.action(dict(action='direction-save', id='old-c', name='手动方向', color='#123456'))
            before = org.snapshot()
            preview = org.action({'action': 'suggest'})['suggestions']
            result = org.action(dict(action='suggest-apply', fingerprint=preview['fingerprint'], regroup_auto=True))
            by_key = {p['key']: p['directions'] for p in result['items']}
            self.assertEqual(by_key['a'], by_key['b'])
            self.assertNotEqual(by_key['a'], ['old-a'])
            self.assertEqual(by_key['c'], ['old-c'])
            self.assertFalse({'old-a', 'old-b'} & {d['id'] for d in result['directions']})
            undone = org.action({'action': 'undo'})
            self.assertEqual(undone['directions'], before['directions'])
            self.assertEqual(undone['items'], before['items'])
