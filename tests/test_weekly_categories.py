"""Legacy bilingual categories share weekly buckets without rewriting library data."""
import json
import sqlite3
import unittest

from app.profile_insights import library_tree, weekly, weekly_directions, weekly_picks


class WeeklyCategoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.execute('CREATE TABLE org_projects (project TEXT, data TEXT)')
        self.papers = {key: {'title': f'Paper {key}', 'abstract': 'text'} for key in ('a', 'b', 'c')}

    def tree(self, directions, memberships):
        self.data = json.dumps({'directions': directions, 'memberships': memberships}, ensure_ascii=False)
        self.conn.execute('DELETE FROM org_projects')
        self.conn.execute('INSERT INTO org_projects VALUES (?, ?)', ('default', self.data))
        self.conn.commit()
        self.changes_before_tree_read = self.conn.total_changes
        return library_tree(self.conn, self.papers)

    def ctx(self, tree):
        return {'tree': tree, 'papers': self.papers, 'route': lambda keys: None}

    def event(self, key='a', kind='positive', feedback_id=1):
        return {'key': key, 'kind': kind, 'time': '2026-10-07T10:00:00+00:00', 'feedback_id': feedback_id}

    def test_legacy_bilingual_roots_merge_and_a_shared_paper_event_counts_once(self):
        tree = self.tree([{'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'}],
                         {'a': ['en', 'en', 'zh'], 'b': ['en'], 'c': ['zh']})
        rows = weekly_directions(self.ctx(tree), [self.event(k) for k in self.papers], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], '世界模型')
        self.assertEqual((rows[0]['current']['papers'], rows[0]['current']['positive']), (3, 3))
        self.assertEqual({p['key'] for p in rows[0]['papers']}, set(self.papers))

    def test_bilingual_ancestor_paths_merge_matching_children(self):
        tree = self.tree([
            {'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'},
            {'id': 've', 'name': 'Video World Model', 'parent_id': 'en'},
            {'id': 'vz', 'name': '视频世界模型', 'parent_id': 'zh'}], {'a': ['ve', 'vz']})
        rows = weekly_directions(self.ctx(tree), [self.event()], [])
        self.assertEqual([(r['name'], r['current']['positive']) for r in rows], [('世界模型 / 视频世界模型', 1)])

    def test_same_concept_below_different_parents_stays_two_directions(self):
        tree = self.tree([
            {'id': 'wm', 'name': 'World Models'}, {'id': 'robot', 'name': 'Robotics'},
            {'id': 'a', 'name': 'JEPA', 'parent_id': 'wm'},
            {'id': 'b', 'name': 'JEPA', 'parent_id': 'robot'}], {'a': ['a', 'b']})
        rows = weekly_directions(self.ctx(tree), [self.event()], [])
        self.assertEqual({r['name'] for r in rows}, {'世界模型 / JEPA', '机器人 / JEPA'})
        self.assertTrue(all(r['current']['papers'] == 1 for r in rows))

    def test_distinct_concepts_and_custom_names_are_retained(self):
        tree = self.tree([
            {'id': 'wm', 'name': 'World Models'}, {'id': 'ws', 'name': 'World States'},
            {'id': 'custom', 'name': '我的研究路线 / 待核验'}], {'a': ['wm'], 'b': ['ws'], 'c': ['custom']})
        rows = weekly_directions(self.ctx(tree), [self.event(k) for k in self.papers], [])
        self.assertEqual(len(rows), 3)
        self.assertIn('我的研究路线 / 待核验', [r['name'] for r in rows])
        self.assertNotEqual(tree['by_paper']['a'], tree['by_paper']['b'])

    def test_weekly_picks_use_the_same_normalized_paths_once(self):
        tree = self.tree([{'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'}],
                         {'a': ['en', 'zh']})
        picks = weekly_picks(self.ctx(tree), [self.event()])
        self.assertEqual(picks[0]['directions'], ['世界模型'])

    def test_before_and_after_language_variations_share_one_comparison(self):
        tree = self.tree([{'id': 'en', 'name': 'world model'}, {'id': 'zh', 'name': '世界模型'}],
                         {'a': ['en'], 'b': ['zh']})
        rows = weekly_directions(self.ctx(tree), [self.event('b')], [self.event('a')])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['current']['papers'], rows[0]['previous']['papers'], rows[0]['status']), (1, 1, 'same'))

    def test_robotics_explicit_aliases_share_a_bucket(self):
        tree = self.tree([{'id': 'en', 'name': 'Robotics'}, {'id': 'zh', 'name': '机器人'}],
                         {'a': ['en', 'zh']})
        rows = weekly_directions(self.ctx(tree), [self.event()], [])
        self.assertEqual([(r['name'], r['current']['papers']) for r in rows], [('机器人', 1)])

    def test_jepa_and_its_full_name_share_a_bucket(self):
        tree = self.tree([{'id': 'short', 'name': 'JEPA'},
                          {'id': 'full', 'name': 'Joint Embedding Predictive Architecture'}],
                         {'a': ['short', 'full']})
        rows = weekly_directions(self.ctx(tree), [self.event()], [])
        self.assertEqual([(r['name'], r['current']['positive']) for r in rows], [('JEPA', 1)])

    def test_normalization_reads_preserve_original_tree_and_memberships(self):
        tree = self.tree([{'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'}],
                         {'a': ['en', 'zh']})
        weekly_directions(self.ctx(tree), [self.event()], [])
        self.assertEqual(self.conn.execute('SELECT data FROM org_projects').fetchone()[0], self.data)
        self.assertEqual(self.conn.total_changes, self.changes_before_tree_read)

    def test_separate_feedback_events_are_preserved_after_alias_deduplication(self):
        tree = self.tree([{'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'}],
                         {'a': ['en', 'zh']})
        rows = weekly_directions(self.ctx(tree), [self.event(feedback_id=1), self.event(feedback_id=2)], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['current']['papers'], rows[0]['current']['positive']), (1, 2))

    def test_weekly_reports_explain_when_legacy_aliases_are_grouped(self):
        tree = self.tree([{'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'}],
                         {'a': ['en', 'zh']})
        ctx = self.ctx(tree)
        ctx.update(events=[], saved={})
        report = weekly(ctx)
        self.assertEqual(report['category_normalization']['merged_groups'], 1)
        self.assertEqual(report['category_normalization']['merged_categories'], 1)
        self.assertIn('同义', report['category_normalization']['message'])


if __name__ == '__main__':
    unittest.main()
