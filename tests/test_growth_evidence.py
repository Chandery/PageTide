"""Effective interest evidence for Route growth, using isolated project stores."""
from test_route_growth import Fixture


class GrowthEvidenceTests(Fixture):
    def positive(self):
        return set(self.app._positive_evidence(self.pid)[0])

    def pending(self):
        return {p['key'] for p in self.app._pending_growth(self.pid)}

    def choose_seed(self, key):
        self.app.store.add_project_paper(self.pid, key, 'seed')
        self.app.store.set_setting(f'seed_keys_{self.pid}', [key])

    def direction(self, keys):
        self.app.store.set_setting(f'route_directions_{self.pid}', {
            'directions': [{'id': 'd-test', 'name': 'Strain', 'terms': ['strain'],
                            'papers': keys, 'needs': [], 'context': self.app._growth_context(self.pid, keys)}], 'judged': {}})

    def visible(self):
        return self.app._visible_directions(self.pid, self.app.route_get(self.pid))

    def test_understanding_is_not_interest(self):
        self.say(('s1', 'understood'))
        self.assertEqual(self.positive(), set())

    def test_undo_useful_does_not_leave_understanding_as_interest(self):
        self.say(('s1', 'useful'), ('s1', 'understood'))
        useful_id = self.app.latest_feedback(self.pid)['s1']['id']
        self.app.undo_feedback(useful_id)
        self.assertTrue(self.app.latest_feedback(self.pid)['s1']['familiar'])
        self.assertEqual(self.positive(), set())

    def test_useful_path_and_unexposed_papers_are_pending(self):
        self.shown('s1', kind='route')
        self.say(('s1', 'useful'), ('s2', 'useful'))
        self.assertEqual(self.pending(), {'s1', 's2'})

    def test_selected_seed_is_pending_but_import_alone_is_not(self):
        self.choose_seed('s1')
        self.assertEqual(self.pending(), {'s1'})

    def test_silence_saved_and_understood_do_not_supply_growth_evidence(self):
        self.shown('s1')
        self.app.store.save_to_library('s2', project_id=self.pid)
        self.say(('s3', 'understood'), ('s4', 'too_hard'))
        self.assertEqual(self.pending(), set())

    def test_seed_with_explicit_rejection_does_not_count(self):
        self.choose_seed('s1')
        self.say(('s1', 'irrelevant'))
        self.assertEqual(self.pending(), set())

    def test_seed_keeps_counting_when_only_difficulty_was_reported(self):
        self.choose_seed('s1')
        self.say(('s1', 'too_hard'))
        self.assertEqual(self.pending(), {'s1'})

    def test_visible_direction_uses_seed_without_requiring_feedback(self):
        self.choose_seed('s1')
        self.direction(['s1'])
        self.assertEqual(self.visible()[0]['papers'], ['s1'])

    def test_visible_direction_drops_undone_useful_even_with_understanding(self):
        self.say(('s1', 'useful'), ('s1', 'understood'))
        self.direction(['s1'])
        useful_id = self.app.latest_feedback(self.pid)['s1']['id']
        self.app.undo_feedback(useful_id)
        self.assertEqual(self.visible(), [])
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'][0]['papers'], [])

    def test_growth_pending_obeys_frozen_effective_interest(self):
        self.say(('s1', 'useful'))
        self.app.set_profile_frozen(True, self.pid)
        self.say(('s2', 'useful'))
        self.assertEqual(self.pending(), {'s1'})
        self.app.undo_feedback(self.app.latest_feedback(self.pid)['s1']['id'])
        self.assertEqual(self.pending(), set())

    def test_pending_does_not_include_other_projects(self):
        self.add('other-paper', 'Other', 'Other abstract', 'other', pid=self.other)
        self.app.record_feedback('other-paper', 'useful', project_id=self.other)
        self.assertEqual(self.pending(), set())

    def test_reads_never_invoke_model(self):
        self.say(('s1', 'useful'))
        calls = self.gateway({'ok': False})
        self.pending()
        self.app.route_candidates(self.pid)
        self.assertEqual(calls, [])
