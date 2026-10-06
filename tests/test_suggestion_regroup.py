"""Legacy regroup mode of suggest-apply: only untouched automatic groups are replaced."""
import unittest
from unittest.mock import patch


def whole_library_preview(org):
    """The old suggester's answer (groups for every saved paper), injected: the legacy regroup mode of
    suggest-apply is still supported even though the review no longer proposes re-grouping organised papers."""
    from app.organization_facets import suggest_groups
    with patch('app.organization.review_papers', side_effect=lambda papers, *a, **k: suggest_groups(papers)):
        return org.action({'action': 'suggest'})['suggestions']


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
                    preview = whole_library_preview(org)
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
                    next_preview = whole_library_preview(org)
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
            with patch('app.organization.review_papers', return_value=old):
                org.action({'action': 'suggest'})
            org.action(dict(action='suggest-apply', fingerprint=old['fingerprint']))
            # A manual rename protects its existing memberships too.
            org.action(dict(action='direction-save', id='old-c', name='手动方向', color='#123456'))
            before = org.snapshot()
            preview = whole_library_preview(org)
            result = org.action(dict(action='suggest-apply', fingerprint=preview['fingerprint'], regroup_auto=True))
            by_key = {p['key']: p['directions'] for p in result['items']}
            self.assertEqual(by_key['a'], by_key['b'])
            self.assertNotEqual(by_key['a'], ['old-a'])
            self.assertEqual(by_key['c'], ['old-c'])
            self.assertFalse({'old-a', 'old-b'} & {d['id'] for d in result['directions']})
            undone = org.action({'action': 'undo'})
            self.assertEqual(undone['directions'], before['directions'])
            self.assertEqual(undone['items'], before['items'])
