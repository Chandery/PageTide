"""Selectable units of a validated AI category-review plan.

The plan is one atomic proposal; the reader may still want only part of it. This
module splits it into units in the owner's priority order and turns a choice of
units back into a smaller plan that is valid on its own:

  classify  file a paper that has no category yet
  adjust    rename / merge / delete one existing category
  rehome    move a paper that was already classified

Papers whose only change is a consequence of a category operation have no unit of
their own: a merge moves its papers, and a delete carries the re-homing of the
papers it empties. Pure functions; no I/O, no model call, no database.
"""

SECTIONS = ('classify', 'adjust', 'rehome')


def _same(first, second):
    return set(first) == set(second)


def _unique(values):
    return list(dict.fromkeys(values))


def build_units(plan, directions, memberships):
    """Ordered units for `plan` against the current `directions` and `memberships`."""
    ops = {op['id']: op for op in plan['categories']}
    redirect = {i: op['target'] for i, op in ops.items() if op['action'] == 'merge'}
    deleted = {i for i, op in ops.items() if op['action'] == 'delete'}
    children = {}
    for direction in directions:
        children.setdefault(direction.get('parent_id'), []).append(direction['id'])
    planned = {p['key']: p for p in plan['papers']}
    holders = {}
    for paper in plan['papers']:
        for identifier in memberships.get(paper['key'], []):
            holders.setdefault(identifier, []).append(paper['key'])
    bundled = {key for identifier in deleted for key in holders.get(identifier, [])}

    found = {section: [] for section in SECTIONS}
    for paper in plan['papers']:
        key = paper['key']
        current = list(memberships.get(key, []))
        if key in bundled or _same(paper['categories'], _unique(redirect.get(i, i) for i in current)):
            continue
        found['rehome' if current else 'classify'].append(
            {'id': 'p:' + key, 'kind': 'paper', 'section': 'rehome' if current else 'classify', 'key': key,
             'from': current, 'to': list(paper['categories']), 'fallback': bool(paper.get('fallback')),
             'reason': paper.get('reason', ''), 'requires': []})
    for op in plan['categories']:
        if op['action'] == 'keep':
            continue
        unit = {'id': 'c:' + op['id'], 'kind': 'category', 'section': 'adjust', 'category': op['id'],
                'action': op['action'], 'reason': op.get('reason', ''),
                'papers': len(holders.get(op['id'], [])), 'requires': []}
        if op['action'] == 'rename':
            unit['name'] = op['name']
        elif op['action'] == 'merge':
            unit['target'] = op['target']
        else:
            unit['rehome'] = [{'key': key, 'to': list(planned[key]['categories'])} for key in holders.get(op['id'], [])]
            unit['requires'] = ['c:' + child for child in children.get(op['id'], [])
                                if ops.get(child, {}).get('action') in {'delete', 'merge'}]
        found['adjust'].append(unit)
    return [unit for section in SECTIONS for unit in found[section]]


def closure(units, selected):
    """The chosen unit IDs plus everything they need, or ValueError for an invalid choice."""
    if not isinstance(selected, (list, tuple, set, frozenset)):
        raise ValueError('选择格式无效')
    by_id = {unit['id']: unit for unit in units}
    if any(not isinstance(identifier, str) or identifier not in by_id for identifier in selected):
        raise ValueError('选择了不存在的整理项，请重新审阅')
    out, pending = set(), list(selected)
    while pending:
        identifier = pending.pop()
        if identifier not in out:
            out.add(identifier)
            pending.extend(by_id[identifier]['requires'])
    return out


def select_plan(plan, units, selected, memberships):
    """The part of `plan` that the chosen units stand for, valid without the rest."""
    chosen = closure(units, selected)
    active, merged = set(), {}
    for unit in units:
        if unit['id'] not in chosen:
            continue
        if unit['kind'] == 'paper':
            active.add(unit['key'])
        elif unit['action'] == 'merge':
            merged[unit['category']] = unit['target']
        elif unit['action'] == 'delete':
            active.update(row['key'] for row in unit['rehome'])
    categories = [op if op['action'] == 'keep' or 'c:' + op['id'] in chosen
                  else {'id': op['id'], 'action': 'keep', 'reason': op.get('reason', '')}
                  for op in plan['categories']]
    papers = []
    for paper in plan['papers']:
        if paper['key'] in active:
            papers.append(dict(paper))
        else:
            kept = _unique(merged.get(i, i) for i in memberships.get(paper['key'], []))
            papers.append({'key': paper['key'], 'categories': kept, 'reason': paper.get('reason', '')})
    fresh = {item['id']: item for item in plan['new_categories']}
    needed = set()
    for paper in papers:
        for identifier in paper['categories']:
            while identifier in fresh and identifier not in needed:
                needed.add(identifier)
                identifier = fresh[identifier].get('parent_id')

    def depth(identifier):
        level = 0
        while fresh[identifier].get('parent_id') in fresh:
            identifier, level = fresh[identifier]['parent_id'], level + 1
        return level
    created = sorted((item for item in plan['new_categories'] if item['id'] in needed), key=lambda item: depth(item['id']))
    return dict(plan, categories=categories, papers=papers, new_categories=created)


def outside_keys(memberships, scope_keys, owners=None, scope_project=None):
    """Papers that make a category shared: not in this scope (another project's, archived, unowned) or, for a
    project scope, saved by another project too (the page marks such categories 跨项目)."""
    found = {key for key in memberships if key not in scope_keys}
    if scope_project is not None and owners:
        found.update(key for key in scope_keys if any(owner != scope_project for owner in owners.get(key, [])))
    return found


def locked_categories(directions, memberships, outside, visible_ids):
    """Shown categories a review may fill but not change.

    A category is shared when a paper in `outside` holds it, or when it has a sub-category the directory hides;
    its ancestors are shared with it, because merging or deleting an ancestor would move the shared category in
    the other project's tree. Renaming, merging or deleting a shared category reaches beyond the papers being
    organized, so it can only receive papers."""
    visible = set(visible_ids)
    parent = {d['id']: d.get('parent_id') for d in directions}
    marked = {identifier for identifier in parent if identifier not in visible}
    for key in outside:
        marked.update(memberships.get(key, []))
    locked = set()
    for start in marked:
        current = start
        while current is not None and current not in locked:
            locked.add(current)
            current = parent.get(current)
    return locked & visible


def scope_directory(directions, memberships, scope_keys, saved_keys, owners=None, scope_project=None):
    """(shown category IDs in order, locked category IDs) for one project tab of the library page.

    Same rule as the page's left directory: a category is not shown in a project tab when saved papers hold it
    (or one of its sub-categories) but none of this project's papers do; a sub-category of a hidden category is
    hidden with it. A category nobody holds stays shown. Read-only for a review: see `locked_categories`;
    `owners` ({paper: [project ids]}) and `scope_project` tell which in-scope papers another project saved too."""
    children = {}
    for direction in directions:
        children.setdefault(direction.get('parent_id'), []).append(direction['id'])
    holders = {}
    for key, categories in memberships.items():
        for identifier in categories:
            holders.setdefault(identifier, set()).add(key)

    def subtree(identifier):
        found, pending = set(), [identifier]
        while pending:
            current = pending.pop()
            if current not in found:
                found.add(current)
                pending.extend(children.get(current, []))
        return found
    scope_keys, saved_keys = set(scope_keys), set(saved_keys)
    hidden = set()
    for direction in directions:
        tree = subtree(direction['id'])
        held = set().union(*(holders.get(i, set()) for i in tree)) & saved_keys
        if held and not held & scope_keys:
            hidden.update(tree)
    shown = [d['id'] for d in directions if d['id'] not in hidden]
    return shown, locked_categories(directions, memberships, outside_keys(memberships, scope_keys, owners, scope_project), shown)
