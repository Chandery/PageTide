"""Whatever the reader ticks on the preview must be applicable: the page never offers a combination that fails.

Units that cannot stand alone declare what they need (`requires`), found by trying them on a private copy when
the preview is stored. Real temporary SQLite; no model call.
"""
import copy
import itertools
import json
import random
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from app import category_review as cr
from app import category_review_units as units
from app.category_review_service import _fill_empty
from app.clustering import corpus_fingerprint
from app.db import Store
from app.organization import Organization
from app.organization_facets import structure_hash


def store_and_org(keys):
    tmp = tempfile.TemporaryDirectory()
    store = Store(Path(tmp.name) / 't.sqlite'); store.init()
    store.upsert_papers([{'key': k, 'title': 'T' + k, 'abstract': 'abs'} for k in keys])
    for key in keys:
        store.save_to_library(key)
    return tmp, store, Organization(store)


class StoredUnitsTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.store, self.org = store_and_org(['a1', 'a2', 'b1', 'b2'])
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.store.close)

    def make(self, name, parent=None):
        before = {d['id'] for d in self.org.snapshot()['directions']}
        self.org.action({'action': 'direction-save', 'name': name, 'color': '#123456', **({'parent_id': parent} if parent else {})})
        return next(d['id'] for d in self.org.snapshot()['directions'] if d['id'] not in before)

    def put(self, key, *ids):
        self.org.action({'action': 'membership', 'keys': [key], 'add': list(ids)})

    def preview(self, plan):
        revision, data = self.org._load()
        plan = dict(plan, category_scope=[d['id'] for d in data['directions']], scoped=False)
        return self.org.store_ai_review(plan, revision, corpus_fingerprint(self.org._corpus(None)),
                                        structure_hash(data['directions'], data['memberships']), None)['suggestions']

    @staticmethod
    def everyone(placed):
        return [{'key': key, 'categories': ids, 'reason': 'r'} for key, ids in placed.items()]

    def apply(self, preview, ids):
        return self.org.action({'action': 'apply-ai-review', 'ai_token': preview['ai_token'],
                                'fingerprint': preview['fingerprint'], 'selection': {'units': ids}})

    def test_merging_a_parent_brings_the_merge_of_the_child_that_would_otherwise_collide(self):
        a, b = self.make('世界模型'), self.make('World Models')
        ap, bp = self.make('Planning', a), self.make('Planning', b)
        for key, ids in (('a1', [ap]), ('a2', [a]), ('b1', [bp]), ('b2', [b])):
            self.put(key, *ids)
        plan = {'categories': [{'id': a, 'action': 'keep', 'reason': 'r'}, {'id': b, 'action': 'merge', 'target': a, 'reason': '同义'},
                               {'id': ap, 'action': 'keep', 'reason': 'r'}, {'id': bp, 'action': 'merge', 'target': ap, 'reason': '同义'}],
                'new_categories': [], 'papers': [{'key': 'a1', 'categories': [ap], 'reason': 'r'}, {'key': 'a2', 'categories': [a], 'reason': 'r'},
                                                 {'key': 'b1', 'categories': [ap], 'reason': 'r'}, {'key': 'b2', 'categories': [a], 'reason': 'r'}]}
        preview = self.preview(plan)
        by_id = {u['id']: u for u in preview['ai_units']}
        self.assertIn('c:' + bp, by_id['c:' + b]['requires'])
        self.apply(preview, ['c:' + b])
        names = {d['id']: d['name'] for d in self.org.snapshot()['directions']}
        self.assertNotIn(b, names); self.assertNotIn(bp, names)
        self.assertEqual({k: v for k, v in self.mem().items() if k in ('b1', 'b2')}, {'b1': [ap], 'b2': [a]})

    def test_filing_a_paper_under_a_new_category_brings_the_deletion_of_its_same_named_sibling(self):
        # The plan deletes "Robotics" and files everything under a new "机器人" (the same name, in Chinese). Ticking
        # only a classify unit would create "机器人" beside the surviving "Robotics", which cannot apply.
        robotics = self.make('Robotics'); self.put('a1', robotics)
        plan = {'categories': [{'id': robotics, 'action': 'delete', 'reason': '统一为中文标准名'}],
                'new_categories': [{'id': 'ai-cat-zh', 'name': '机器人', 'parent_id': None, 'reason': '标准名'}],
                'papers': self.everyone({key: ['ai-cat-zh'] for key in ('a1', 'a2', 'b1', 'b2')})}
        preview = self.preview(plan)
        by_id = {u['id']: u for u in preview['ai_units']}
        self.assertIn('c:' + robotics, by_id['p:a2']['requires'])
        self.apply(preview, ['p:a2'])
        self.assertEqual([d['name'] for d in self.org.snapshot()['directions']], ['机器人'])

    def test_a_choice_that_cannot_apply_alone_is_completed_and_the_extra_is_reported(self):
        # The safety net behind the precomputed `requires`: even when the page offers a combination that cannot
        # apply (here units without any dependency information), applying completes it with the fewest label
        # changes that make it work and says which ones, instead of failing.
        a, b = self.make('世界模型'), self.make('World Models')
        ap, bp = self.make('Planning', a), self.make('Planning', b)
        for key, ids in (('a1', [ap]), ('a2', [a]), ('b1', [bp]), ('b2', [b])):
            self.put(key, *ids)
        plan = {'categories': [{'id': a, 'action': 'keep', 'reason': 'r'}, {'id': b, 'action': 'merge', 'target': a, 'reason': '同义'},
                               {'id': ap, 'action': 'keep', 'reason': 'r'}, {'id': bp, 'action': 'merge', 'target': ap, 'reason': '同义'}],
                'new_categories': [], 'papers': self.everyone({'a1': [ap], 'a2': [a], 'b1': [ap], 'b2': [a]})}
        bare = lambda org, plan, data: units.build_units(plan, data['directions'], data['memberships'])
        with unittest.mock.patch.object(Organization, '_offered_units', bare):
            preview = self.preview(plan)
            self.assertEqual([u['requires'] for u in preview['ai_units']], [[], []])
            result = self.apply(preview, ['c:' + b])
        self.assertEqual(result['apply_result']['also_applied'], ['c:' + bp])
        names = {d['id']: d['name'] for d in self.org.snapshot()['directions']}
        self.assertNotIn(b, names); self.assertNotIn(bp, names)

    def test_a_rename_into_a_sibling_s_name_brings_the_sibling_s_rename(self):
        alpha, beta = self.make('Alpha'), self.make('Beta')
        self.put('a1', alpha); self.put('a2', beta)
        plan = {'categories': [{'id': alpha, 'action': 'rename', 'name': 'Gamma', 'reason': 'r'},
                               {'id': beta, 'action': 'rename', 'name': 'Alpha', 'reason': 'r'}],
                'new_categories': [], 'papers': self.everyone({'a1': [alpha], 'a2': [beta], 'b1': [alpha], 'b2': [beta]})}
        preview = self.preview(plan)
        self.apply(preview, ['c:' + beta])
        self.assertEqual(sorted(d['name'] for d in self.org.snapshot()['directions']), ['Alpha', 'Gamma'])

    def test_a_merge_into_a_renamed_target_brings_the_rename(self):
        robot, embodied = self.make('机器人'), self.make('具身智能')
        self.put('a1', robot); self.put('a2', embodied)
        plan = {'categories': [{'id': robot, 'action': 'merge', 'target': embodied, 'reason': '同义'},
                               {'id': embodied, 'action': 'rename', 'name': 'Robotics', 'reason': '统一名称'}],
                'new_categories': [], 'papers': self.everyone({key: [embodied] for key in ('a1', 'a2', 'b1', 'b2')})}
        preview = self.preview(plan)
        by_id = {u['id']: u for u in preview['ai_units']}
        self.assertIn('c:' + embodied, by_id['c:' + robot]['requires'])
        self.apply(preview, ['c:' + robot])
        self.assertEqual([d['name'] for d in self.org.snapshot()['directions']], ['Robotics'], 'the rename came with the merge')

    def counting(self):
        """Count how many times the library is tried against a plan (each try is a full validation)."""
        calls = []
        original = Organization._apply_ai_review
        def counted(org, data, plan, *args, **kwargs):
            calls.append(plan)
            return original(org, data, plan, *args, **kwargs)
        patcher = unittest.mock.patch.object(Organization, '_apply_ai_review', counted)
        patcher.start(); self.addCleanup(patcher.stop)
        return calls

    def test_papers_are_never_tried_one_by_one_only_label_changes_and_their_pairs(self):
        # Filing a paper cannot make a plan unappliable, so storing a preview costs 1 (the whole plan) +
        # one try per label change + one per pair, however many papers there are.
        a, b, c = self.make('Alpha'), self.make('Beta'), self.make('Gamma')
        for key, ids in (('a1', [a]), ('a2', [b]), ('b1', [c]), ('b2', [a])):
            self.put(key, *ids)
        calls = self.counting()
        plan = {'categories': [{'id': a, 'action': 'rename', 'name': 'A2', 'reason': 'r'}, {'id': b, 'action': 'rename', 'name': 'B2', 'reason': 'r'},
                               {'id': c, 'action': 'rename', 'name': 'C2', 'reason': 'r'}],
                'new_categories': [], 'papers': self.everyone({'a1': [a], 'a2': [c], 'b1': [b], 'b2': [c]})}
        preview = self.preview(plan)
        structural = [u for u in preview['ai_units'] if u['section'] == 'adjust']
        papers = [u for u in preview['ai_units'] if u['section'] != 'adjust']
        self.assertEqual((len(structural), len(papers)), (3, 3))
        self.assertEqual(len(calls), 1 + 3 + 3, 'whole plan + each label change + each pair; no paper is tried alone')

    def test_a_preview_stored_before_units_existed_is_not_probed_on_every_snapshot(self):
        a = self.make('Alpha'); self.put('a1', a)
        plan = {'categories': [{'id': a, 'action': 'keep', 'reason': 'r'}], 'new_categories': [],
                'papers': self.everyone({'a1': [a], 'a2': [a], 'b1': [a], 'b2': [a]})}
        self.preview(plan)
        revision, data = self.org._load()
        del data['suggestions']['ai_units']
        from app.organization import _dump
        self.store.conn.execute('UPDATE org_projects SET data=? WHERE project=?', (_dump(data), 'default')); self.store.conn.commit()
        calls = self.counting()
        for _ in range(3):
            snapshot = self.org.snapshot()
        self.assertEqual(calls, [], 'reading the library never tries a plan')
        self.assertNotIn('ai_units', snapshot['suggestions'])

    def mem(self):
        return {i['key']: sorted(i['directions']) for i in self.org.snapshot()['items']}


PLAIN = ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta', 'Theta']
SYNONYMS = ['世界模型', 'World Models', '机器人', 'Robotics']


class EverySubsetTests(unittest.TestCase):
    """Random valid plans, every subset of their units, on a private copy: none may raise."""
    KEYS = ['p%d' % i for i in range(5)]
    ATTEMPTS, PLANS, MAX_UNITS = 900, 150, 8

    def setUp(self):
        self.tmp, self.store, self.org = store_and_org(self.KEYS)
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.store.close)

    def world(self, rng):
        count = rng.randint(3, 7)
        pool = PLAIN[:]; rng.shuffle(pool)
        names = [rng.choice(SYNONYMS) if rng.random() < 0.3 else pool.pop() for _ in range(count)]
        directions = [{'id': 'c%d' % i, 'name': names[i], 'color': '#000', 'rank': i, 'manual': True,
                       'parent_id': 'c%d' % rng.randrange(i) if i and rng.random() < 0.6 else None} for i in range(count)]
        memberships = {k: rng.sample([d['id'] for d in directions], rng.randint(1, min(2, count)))
                       for k in self.KEYS if rng.random() < 0.7}
        return {'directions': directions, 'memberships': memberships, 'positions': {}, 'protected': [], 'collapsed': []}

    def reply(self, rng, data):
        alias = {d['id']: 'c%d' % (i + 1) for i, d in enumerate(data['directions'])}
        ops = [{'id': alias[d['id']], 'action': rng.choices(['keep', 'rename', 'merge', 'delete'], [4, 1.5, 2.5, 1.5])[0], 'reason': 'r'}
               for d in data['directions']]
        keepers = [o['id'] for o in ops if o['action'] in ('keep', 'rename')]
        for o in ops:
            if o['action'] == 'rename':
                o['name'] = rng.choice(PLAIN + ['Lambda', 'Mu'] + SYNONYMS)
            if o['action'] == 'merge':
                if keepers:
                    o['target'] = rng.choice(keepers)
                else:
                    o['action'] = 'keep'
        # New categories may repeat a name an existing one has or is renamed to (the cases that need a sibling's change)
        new = [{'id': 'n%d' % (j + 1), 'name': rng.choice(PLAIN + SYNONYMS + ['Lambda']), 'reason': 'r'} for j in range(rng.choice([0, 0, 1, 2]))]
        for j, item in enumerate(new):
            parent = rng.choice(keepers + [x['id'] for x in new[:j]] + [None, None])
            if parent:
                item['parent'] = parent
        pool = keepers + [x['id'] for x in new]
        if not pool:
            return None
        redirect = {o['id']: o['target'] for o in ops if o['action'] == 'merge'}
        papers = []
        for index, key in enumerate(self.KEYS):
            current = [alias[c] for c in data['memberships'].get(key, [])]
            base = [c for c in dict.fromkeys(redirect.get(c, c) for c in current) if c in keepers]
            roll = rng.random()
            cats = base if roll < 0.45 and base else [] if roll < 0.5 else rng.sample(pool, rng.randint(1, min(2, len(pool))))
            papers.append({'id': 'p%d' % (index + 1), 'categories': cats, 'reason': 'r'})
        return {'categories': ops, 'papers': papers, 'new_categories': new}

    def test_no_subset_of_the_offered_units_fails_to_apply(self):
        rng = random.Random(20261010)
        checked = subsets = expanded = 0
        for _ in range(self.ATTEMPTS):
            data = self.world(rng)
            reply = self.reply(rng, data)
            if reply is None:
                continue
            papers = [{'key': k, 'title': 't', 'abstract': 'a', 'categories': list(data['memberships'].get(k, []))} for k in self.KEYS]
            try:
                plan = cr.parse(json.dumps(reply), cr.prepare(data['directions'], papers)['context'])
            except ValueError:
                continue
            plan = _fill_empty(plan, {'all_directions': data['directions'], 'memberships': data['memberships']})
            try:
                self.org._apply_ai_review(copy.deepcopy(data), plan)
            except ValueError:
                continue                      # the model's whole plan is not applicable: never stored
            offered = units.build_units(plan, data['directions'], data['memberships'])
            if not 2 <= len(offered) <= self.MAX_UNITS:
                continue
            offered = self.org._offered_units(plan, data)
            checked += 1
            ids = [u['id'] for u in offered]
            for size in range(1, len(ids) + 1):
                for combo in itertools.combinations(ids, size):
                    subsets += 1
                    # What applying does: the choice, its requirements, and (if that still cannot apply) the fewest more
                    # label changes that make it work. Whatever the page offers, applying must not fail.
                    resolved = self.org._resolve_selection(plan, offered, list(combo), data)
                    expanded += resolved != units.closure(offered, list(combo))
                    sub = units.select_plan(plan, offered, resolved, data['memberships'])
                    try:
                        self.org._apply_ai_review(copy.deepcopy(data), sub)
                    except ValueError as error:
                        self.fail('%s -> %s\ndata=%s\nplan=%s' % (combo, error, json.dumps(data, ensure_ascii=False), json.dumps(plan, ensure_ascii=False)))
            if checked >= self.PLANS:
                break
        self.assertGreaterEqual(checked, min(40, self.PLANS), 'the corpus must contain enough plans with several units')
        self.assertGreater(subsets, min(500, self.PLANS * 5))
        self.assertLess(expanded, subsets * 0.02, 'the precomputed requirements must make the safety net rare (%d of %d)' % (expanded, subsets))


if __name__ == '__main__':
    unittest.main()
