"""The review's scope is the library page's left directory: the server rule and the page rule share one set of cases.

tests/test_organization_ui.cjs runs the same fixture through the page's own function (otherProjectCategories).
"""
import json
import unittest
from pathlib import Path

from app.category_review_units import scope_directory

CASES = json.loads((Path(__file__).parent / 'fixtures' / 'scope_directory_cases.json').read_text(encoding='utf-8'))


class ScopeDirectoryTests(unittest.TestCase):
    def test_server_rule_matches_every_shared_case(self):
        for case in CASES:
            with self.subTest(case['name']):
                papers = case['papers']
                memberships = {key: list(p['directions']) for key, p in papers.items()}
                saved = {key for key, p in papers.items() if p['saved']}
                scope = {key for key, p in papers.items() if p['saved'] and case['scope'] in p['projects']}
                shown, _ = scope_directory(case['directions'], memberships, scope, saved)
                self.assertEqual(shown, case['shown'])

    def test_a_category_other_projects_also_hold_is_read_only_but_still_shown(self):
        directions = [{'id': 'S', 'parent_id': None}, {'id': 'T', 'parent_id': None}]
        memberships = {'mine': ['S', 'T'], 'theirs': ['S']}
        shown, locked = scope_directory(directions, memberships, {'mine'}, {'mine', 'theirs'})
        self.assertEqual(shown, ['S', 'T'])
        self.assertEqual(locked, {'S'}, 'T has no outside holder')

    def test_a_category_with_a_hidden_sub_category_is_read_only(self):
        directions = [{'id': 'T', 'parent_id': None}, {'id': 'U', 'parent_id': 'T'}]
        memberships = {'mine': ['T'], 'theirs': ['U']}
        shown, locked = scope_directory(directions, memberships, {'mine'}, {'mine', 'theirs'})
        self.assertEqual(shown, ['T'])
        self.assertEqual(locked, {'T'})

    def test_the_ancestors_of_a_shared_category_are_read_only_too(self):
        # Merging or deleting Alpha would move Beta, which project two also shows below Alpha.
        directions = [{'id': 'Alpha', 'parent_id': None}, {'id': 'Beta', 'parent_id': 'Alpha'},
                      {'id': 'Gamma', 'parent_id': None}]
        memberships = {'mine': ['Beta', 'Gamma'], 'theirs': ['Beta']}
        shown, locked = scope_directory(directions, memberships, {'mine'}, {'mine', 'theirs'})
        self.assertEqual(shown, ['Alpha', 'Beta', 'Gamma'])
        self.assertEqual(locked, {'Alpha', 'Beta'}, 'Gamma is only this project\'s')

    def test_a_paper_another_project_also_saved_makes_its_category_read_only(self):
        # The paper is in this scope, but the other project's directory shows its category too ("跨项目").
        directions = [{'id': 'S', 'parent_id': None}, {'id': 'T', 'parent_id': None}]
        memberships = {'both': ['S'], 'mine': ['T']}
        owners = {'both': ['one', 'two'], 'mine': ['one']}
        shown, locked = scope_directory(directions, memberships, {'both', 'mine'}, {'both', 'mine'}, owners, 'one')
        self.assertEqual((shown, locked), (['S', 'T'], {'S'}))
        self.assertEqual(scope_directory(directions, memberships, {'both', 'mine'}, {'both', 'mine'})[1], set(),
                         'without ownership data only papers outside the scope count')

    def test_archived_holders_make_a_shown_category_read_only(self):
        directions = [{'id': 'X', 'parent_id': None}]
        shown, locked = scope_directory(directions, {'mine': ['X'], 'archived': ['X']}, {'mine'}, {'mine'})
        self.assertEqual((shown, locked), (['X'], {'X'}))


if __name__ == '__main__':
    unittest.main()
