"""An imported library must not flood "today's papers".

Before library import, a paper in a project that was neither shown nor rated was a candidate. A whole imported
library is exactly that, so every old paper the person already owns would be offered back as a new recommendation.
Papers already in the project's library are the person's own and are never candidates; they still feed retrieval."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app import maintenance
from app.service import App


class SavedPapersAreNotCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(data_dir=Path(self.tmp.name))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=False)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('Learning')['project_id']
        self.app.set_project_language(self.pid, 'stem', ['en'])
        patcher = mock.patch.object(self.app.gateway, 'call', side_effect=AssertionError('No model here'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def paper(self, key, relation_kind=None):
        self.app.store.upsert_papers([{'key': key, 'title': f'World model paper {key}', 'published': '2026-01-01',
            'abstract': 'A usable abstract about world model learning and prediction.', 'language': 'en',
            **({'relation_kind': relation_kind} if relation_kind else {})}], self.pid)

    def keys(self):
        return [c['key'] for c in self.app.build_batch(project_id=self.pid, exclude_seen=False)['cards']]

    def test_a_paper_already_in_the_library_is_not_offered_again(self):
        self.paper('owned')
        self.paper('new')
        self.app.store.save_to_library('owned', project_id=self.pid)
        self.assertEqual(self.keys(), ['new'])

    def test_with_only_library_papers_there_is_nothing_to_recommend(self):
        self.paper('owned')
        self.app.store.save_to_library('owned', project_id=self.pid)
        out = self.app.build_batch(project_id=self.pid, exclude_seen=False)
        self.assertIsNone(out['batch_id'])
        self.assertEqual(out['cards'], [])

    def test_a_paper_linked_as_imported_but_not_saved_is_still_a_candidate(self):
        # Guided project creation links its chosen candidates as 'imported'; those must stay recommendable.
        self.paper('guided', relation_kind='imported')
        self.assertEqual(self.keys(), ['guided'])

    def test_library_papers_stay_in_the_pool_that_feeds_retrieval(self):
        self.paper('owned')
        self.app.store.save_to_library('owned', project_id=self.pid)
        keys = [p['key'] for p in self.app.recommendation_pool(self.pid)]
        self.assertEqual(keys, ['owned'])

    def test_saving_in_one_project_does_not_hide_the_paper_in_another(self):
        other = self.app.create_project('Other')['project_id']
        self.app.set_project_language(other, 'stem', ['en'])
        self.paper('shared')
        self.app.store.add_project_paper(other, 'shared', 'discovered')
        self.app.store.save_to_library('shared', project_id=self.pid)
        self.assertEqual(self.keys(), [])
        self.assertEqual([c['key'] for c in self.app.build_batch(project_id=other, exclude_seen=False)['cards']], ['shared'])

    def test_the_scheduler_does_not_see_library_papers_as_unseen(self):
        self.paper('owned')
        self.assertTrue(maintenance._has_unseen(self.app, self.pid))
        self.app.store.save_to_library('owned', project_id=self.pid)
        self.assertFalse(maintenance._has_unseen(self.app, self.pid))


if __name__ == "__main__":
    unittest.main()
