"""One explicit AI review job: frozen metadata, bounded calls, a complete preview.

Only the budgeted gateway can send requests. This module never applies categories,
retries a request, or marks a failed partial job as reviewed.
"""
import copy
import hashlib
import json

from . import category_review, category_review_units, operation_lock
from .clustering import corpus_fingerprint
from .creation import degrade_reason
from .organization import Conflict, Organization
from .organization_facets import review, structure_hash
from .organization_terms import category_identity

FALLBACK_NAMES = {'其他', '其它', 'other', 'others', 'misc', 'miscellaneous'}
FALLBACK_TEXT = {   # server-written wording (name, paper reason, category reason, kept reason); follows the interface language
    'zh-CN': ('其他', '依据不足，暂放「其他」，可稍后手动归类', '依据不足的论文暂放此处，之后可手动归类',
              '模型没有给出新的归属，保持原有类别'),
    'en-US': ('Other', 'Not enough evidence; placed in “Other” for now. Sort it later.',
              'Papers without enough evidence are placed here for now; sort them later.',
              'The model gave no new placement, so the current categories are kept.'),
}


class _ReviewCancelled(ValueError):
    pass


def _check_cancel(cancelled):
    if cancelled is not None and cancelled():
        raise _ReviewCancelled('AI 分类审阅已取消，停止后续批次；没有保存或应用不完整方案')


def _capture(org, scope, view=True):
    """Freeze what is reviewed: the scope's papers and the categories the left directory shows for it.

    A project tab shows the categories its papers use (and empty ones); categories only other projects use are
    neither sent nor changed. Shown categories other projects also use are read-only (see scope_directory).
    `view=False` skips the directory work for the cheap "did anything change" re-checks."""
    with org._transaction(write=False):
        revision, data = org._load()
        papers = org._corpus(scope)
        saved = org._corpus(None) if scope and view else papers
        owners = org._owners() if scope and view and hasattr(org, '_owners') else {}
        directions = copy.deepcopy(data['directions'])
        memberships = copy.deepcopy(data['memberships'])
    if scope and view:
        shown, locked = category_review_units.scope_directory(
            directions, memberships, {p['key'] for p in papers}, {p['key'] for p in saved}, owners, scope)
    else:
        shown, locked = [d['id'] for d in directions], set()
    visible = [dict(d, locked=d['id'] in locked) for d in directions if d['id'] in set(shown)]
    return dict(revision=revision, papers=papers, directions=visible, all_directions=directions,
                memberships=memberships, fingerprint=corpus_fingerprint(papers),
                structure=structure_hash(directions, memberships), scoped=bool(scope))


def _current(org, scope, frozen):
    live = _capture(org, scope, view=False)
    if any(live[key] != frozen[key] for key in ('revision', 'fingerprint', 'structure')):
        raise Conflict('分类目录或论文在审阅期间变化，AI 方案已失效，请重新审阅')


def _offline(org, scope, profile, stats):
    """A read-only local fallback; it is deliberately not a stored/applicable preview."""
    with org._transaction(write=False):
        _, data = org._load()
        papers = org._corpus(scope)
        snapshot = org._snapshot()
    try:
        suggestions = review(papers, data['directions'], data['memberships'], data.get('reviewed') or {}, profile)
    except ValueError:
        suggestions = dict(groups=[], merges=[], moves=[], pending_keys=[p['key'] for p in papers],
                           evaluated=[], scope_size=len(papers))
    stats = dict(stats, source='local')
    suggestions.update(source='local', stored=False, scope=scope, review_stats=stats)
    snapshot.update(suggestions=suggestions, ai_review=stats)
    return snapshot


def _batches(frozen, model):
    """Preflight every batch before spending; decrease paper count, never trim the tree.

    Papers without a category come first: filing them is the review's first priority."""
    papers = [dict(p, categories=list(frozen['memberships'].get(p['key'], []))) for p in frozen['papers']]
    papers.sort(key=lambda p: bool(p['categories']))
    out, offset = [], 0
    if not papers:
        return [category_review.prepare(frozen['directions'], [], model=model)]
    while offset < len(papers):
        count = min(category_review.MAX_PAPERS, len(papers) - offset)
        while True:
            try:
                prepared = category_review.prepare(frozen['directions'], papers[offset:offset + count], model=model)
                break
            except ValueError as exc:
                if count == 1 or '超出输入预算' not in str(exc):
                    raise
                count = max(1, count // 2)
        out.append(prepared)
        offset += count
    return out


def _stable_id(path):
    identity = json.dumps(path, ensure_ascii=False, separators=(',', ':'))
    return 'ai-cat-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]


def _stable_batch(parsed, directions):
    """Replace request-local n aliases with identities derived from canonical paths."""
    old = {d['id']: d for d in directions}
    ops = {op['id']: op for op in parsed['categories']}
    new = {d['id']: d for d in parsed['new_categories']}
    cache = {}

    def path(identifier, seen=()):
        if identifier is None:
            return ()
        if identifier in seen:
            raise ValueError('AI 新类别的父级存在循环')
        if identifier in cache:
            return cache[identifier]
        if identifier in new:
            item = new[identifier]
            result = path(item.get('parent_id'), seen + (identifier,)) + (category_identity(item['name']),)
        elif identifier in old:
            op = ops[identifier]
            if op['action'] == 'merge':
                result = path(op['target'], seen + (identifier,))
            elif op['action'] == 'delete':
                raise ValueError('AI 新类别引用待删除父类')
            else:
                result = path(old[identifier].get('parent_id'), seen + (identifier,)) + (category_identity(op.get('name', old[identifier]['name'])),)
        else:
            raise ValueError('AI 新类别引用未知父级')
        cache[identifier] = result
        return result

    # An ID derived from the canonical path can already belong to a category an earlier review created and its
    # owner since renamed or moved. Salt it now, while the model's references to that category and to the new one
    # are still different aliases (the salt follows from the path, so every batch agrees).
    taken = set(old)
    mapping = {identifier: _fresh_id(path(identifier), taken) for identifier in new}
    convert = lambda identifier: mapping.get(identifier, identifier)
    categories = [dict(op, **({'target': convert(op['target'])} if 'target' in op else {})) for op in parsed['categories']]
    papers = [dict(p, categories=[convert(i) for i in p['categories']]) for p in parsed['papers']]
    created = [dict(d, id=mapping[d['id']], parent_id=convert(d.get('parent_id'))) for d in parsed['new_categories']]
    return dict(categories=categories, papers=papers, new_categories=created)


def _action_identity(op):
    return (op['action'], category_identity(op['name']) if 'name' in op else None, op.get('target'))


def _is_fallback(name):
    return ' '.join(str(name).casefold().split()) in FALLBACK_NAMES


def _fresh_id(path, used):
    """The ID derived from `path`, or the first salted variant of it that is not in `used`."""
    candidate, salt = _stable_id(path), 0
    while candidate in used:
        salt += 1
        candidate = _stable_id(tuple(path) + (str(salt),))
    return candidate


def _unique_ids(plan, frozen):
    """A new category whose derived ID is taken by a category the directory does not show gets a fresh ID.

    Runs before _reuse_outside, so every reference to such an ID in the plan still means the new category."""
    used = {d['id'] for d in frozen['all_directions']} | {c['id'] for c in plan['new_categories']}
    mapping = {}
    for category in plan['new_categories']:
        if category['id'] in {d['id'] for d in frozen['all_directions']}:
            mapping[category['id']] = _fresh_id((category['id'],), used)
            used.add(mapping[category['id']])
    if not mapping:
        return plan
    convert = lambda identifier: mapping.get(identifier, identifier)
    created = [dict(c, id=convert(c['id']), parent_id=convert(c.get('parent_id'))) for c in plan['new_categories']]
    papers = [dict(p, categories=[convert(i) for i in p['categories']]) for p in plan['papers']]
    return dict(plan, new_categories=created, papers=papers)


def _keep_names_outside(plan, frozen):
    """A rename or merge that would repeat a name the left directory cannot see, at the same level, is dropped.

    The model prefers the standard Chinese name, and another project's part of the shared tree may already have
    it. Renaming X to it, or merging X into a category whose hidden child has the name of one of X's children,
    would make a same-level duplicate there, so that one proposal is dropped instead of failing the whole plan.
    Returns the plan and how many proposals were dropped."""
    shown = {d['id']: d for d in frozen['directions']}
    outside = {(d.get('parent_id'), category_identity(d['name'])) for d in frozen['all_directions'] if d['id'] not in shown}
    ops = {op['id']: op for op in plan['categories']}
    redirect = {i: op['target'] for i, op in ops.items() if op['action'] == 'merge'}
    children = {}
    for direction in frozen['directions']:
        children.setdefault(direction.get('parent_id'), []).append(direction['id'])
    keep = lambda op: {'id': op['id'], 'action': 'keep', 'reason': op['reason']}
    dropped = 0
    for identifier, op in list(ops.items()):                     # renames first: they decide the names merges move
        if op['action'] == 'rename':
            parent = shown[identifier].get('parent_id')
            if (redirect.get(parent, parent), category_identity(op['name'])) in outside:
                ops[identifier], dropped = keep(op), dropped + 1
    for identifier, op in list(ops.items()):
        if op['action'] == 'merge':
            moving = [c for c in children.get(identifier, []) if ops[c]['action'] not in {'merge', 'delete'}]
            if any((op['target'], category_identity(ops[c].get('name', shown[c]['name']))) in outside for c in moving):
                ops[identifier], dropped = keep(op), dropped + 1
    if not dropped:
        return plan, 0
    return dict(plan, categories=[ops[op['id']] for op in plan['categories']]), dropped


def _reuse_outside(plan, frozen):
    """A new category that repeats one the left directory does not show reuses that one.

    The model never sees categories only other projects use, so it may propose a label that already exists
    there. Creating it again would be a same-level duplicate; the papers join the existing category instead.
    Mapping repeats until nothing changes, so the order the reply lists parents and children does not matter."""
    shown = {d['id'] for d in frozen['directions']}
    outside = {(d.get('parent_id'), category_identity(d['name'])): d['id']
               for d in frozen['all_directions'] if d['id'] not in shown}
    mapping, changed = {}, True
    while changed:
        changed = False
        for category in plan['new_categories']:
            if category['id'] in mapping:
                continue
            parent = mapping.get(category.get('parent_id'), category.get('parent_id'))
            found = outside.get((parent, category_identity(category['name'])))
            if found:
                mapping[category['id']], changed = found, True
    if not mapping:
        return plan
    created = [dict(c, parent_id=mapping.get(c.get('parent_id'), c.get('parent_id')))
               for c in plan['new_categories'] if c['id'] not in mapping]
    papers = [dict(p, categories=list(dict.fromkeys(mapping.get(i, i) for i in p['categories']))) for p in plan['papers']]
    return dict(plan, new_categories=created, papers=papers)


def _fill_empty(plan, frozen, language='zh-CN'):
    """Every reviewed paper ends with a category.

    The model is told to give each paper a category; this is the local guarantee behind that, so a review never
    ends with papers still unclassified. A paper the model left empty keeps the categories it has now (after the
    plan's merges and deletions); only one left with nothing goes to the top-level 其他, marked so the preview can
    say why it is there."""
    name, reason, why, kept_reason = FALLBACK_TEXT.get(language, FALLBACK_TEXT['zh-CN'])
    ops = {op['id']: op for op in plan['categories']}
    redirect = {i: op['target'] for i, op in ops.items() if op['action'] == 'merge'}
    deleted = {i for i, op in ops.items() if op['action'] == 'delete'}

    def current(key):
        return list(dict.fromkeys(redirect.get(i, i) for i in frozen['memberships'].get(key, []) if i not in deleted))

    def existing():
        for direction in frozen['all_directions']:
            op = ops.get(direction['id'])
            if op and op['action'] in {'merge', 'delete'}:
                continue
            if direction.get('parent_id') is None and _is_fallback((op or {}).get('name', direction['name'])):
                return direction['id']
        for category in plan['new_categories']:
            if category.get('parent_id') is None and _is_fallback(category['name']):
                return category['id']
        return None
    empty = [p for p in plan['papers'] if not p['categories']]
    if not empty:
        return plan
    homeless = [p for p in empty if not current(p['key'])]
    target, created = existing(), list(plan['new_categories'])
    if homeless and target is None:
        used = {d['id'] for d in frozen['all_directions']} | {c['id'] for c in created}
        target = _fresh_id((category_identity(name),), used)
        created.append({'id': target, 'name': name, 'parent_id': None, 'reason': why})
    papers = []
    for p in plan['papers']:
        if not p['categories']:
            kept = current(p['key'])
            p = (dict(p, categories=kept, reason=kept_reason) if kept
                 else dict(p, categories=[target], fallback=True, reason=reason))
        papers.append(p)
    return dict(plan, new_categories=created, papers=papers)


def _demote(plan, identifiers):
    """The plan with those label changes turned into keep; papers and new categories are untouched."""
    identifiers = set(identifiers)
    return dict(plan, categories=[{'id': op['id'], 'action': 'keep', 'reason': op['reason']} if op['id'] in identifiers else op
                                  for op in plan['categories']])


def _repair(org, plan):
    """A plan the library cannot take as it stands loses label changes, never papers, instead of failing the review.

    Dropping a proposal for scope reasons can leave another one that relied on it unappliable (a merge into a target
    whose rename was dropped, a swap of two names of which one was dropped). The model call is already paid for, so
    this starts from the plan without any label change (which must apply) and brings the proposals back one by one,
    keeping each that still applies, so unrelated proposals survive. Returns the plan and how many label changes were
    dropped; what cannot be repaired is left for storing to report."""
    problem = getattr(org, 'plan_error', None)
    if problem is None or problem(plan) is None:
        return plan, 0
    changing = [op for op in plan['categories'] if op['action'] != 'keep']
    current = _demote(plan, [op['id'] for op in changing])        # no label change at all: the base that must apply
    if problem(current) is not None:
        return plan, 0
    for op in changing:                                           # bring each proposal back if it still applies
        candidate = dict(current, categories=[op if item['id'] == op['id'] else item for item in current['categories']])
        if problem(candidate) is None:
            current = candidate
    return current, sum(1 for item in current['categories'] if item['action'] == 'keep') - sum(1 for item in plan['categories'] if item['action'] == 'keep')


def _safe_plan(plan, frozen):
    """Validate cross-batch state and all global membership holders, including archived papers."""
    old = {d['id']: d for d in frozen['directions']}
    ops = {op['id']: op for op in plan['categories']}
    new = {d['id']: d for d in plan['new_categories']}
    keys = {p['key'] for p in frozen['papers']}
    if set(ops) != set(old) or {p['key'] for p in plan['papers']} != keys or len(plan['papers']) != len(keys):
        raise ValueError('AI 方案没有完整覆盖分类目录或本次全部论文')
    if any(ops[i]['action'] != 'keep' for i, d in old.items() if d.get('locked')):
        raise ValueError(category_review.LOCKED_MESSAGE)
    if any(not p['categories'] for p in plan['papers']):
        raise ValueError('AI 方案仍有论文没有类别')
    deleted = {i for i, op in ops.items() if op['action'] == 'delete'}
    for key, memberships in frozen['memberships'].items():
        if key not in keys and deleted.intersection(memberships):
            raise ValueError('待删除类别仍有本次范围外或已归档论文，未完整审阅，不能删除')
    redirect = {i: op['target'] for i, op in ops.items() if op['action'] == 'merge'}
    # Categories the directory does not show stay as they are; a plan may file papers under them or hang a
    # new category below them (a label that already exists there is reused), never change them.
    outside = {d['id'] for d in frozen['all_directions']} - set(old)
    retained = (set(old) - deleted - set(redirect)) | set(new)
    parents, names = {}, {}
    for identifier in retained:
        item = new.get(identifier, old.get(identifier))
        parent = item.get('parent_id')
        parents[identifier] = redirect.get(parent, parent)
        names[identifier] = ops[identifier].get('name', item['name']) if identifier in old else item['name']
        if parents[identifier] is not None and parents[identifier] not in retained | outside:
            raise ValueError('AI 完整方案留下悬空子类')
    identities = set()
    for identifier in retained:
        signature = (parents[identifier], category_identity(names[identifier]))
        if signature in identities:
            raise ValueError('AI 各批合并后仍有重复同义类别')
        identities.add(signature)
        seen, current = set(), identifier
        while current is not None and current in parents:
            if current in seen:
                raise ValueError('AI 完整方案留下循环分类')
            seen.add(current)
            current = parents[current]
    if any(not set(p['categories']) <= retained | outside for p in plan['papers']):
        raise ValueError('AI 论文归属引用被移除或未知类别')


def run_review(app, scope_project, profile, dry_run=False, cancelled=None):
    """Return Organization snapshot + preview; one explicit job, no automatic application."""
    if scope_project is not None and (not isinstance(scope_project, str) or not scope_project.strip()):
        raise ValueError('分类审阅范围必须是项目编号或全部论文库')
    with operation_lock.claim(app.data, 'category-review:default'):
        org = Organization(app.store)
        frozen = _capture(org, scope_project)
        stats = dict(source='ai', status='in_progress', total_papers=len(frozen['papers']),
                     processed_papers=0, remaining_papers=len(frozen['papers']), completed_batches=0,
                     total_batches=0, calls=0, total_tokens=0, tokens_known=True, error=None,
                     error_code=None, usage_unknown=False)
        try:
            _check_cancel(cancelled)
            model = (app.gateway.config.get('provider') or {}).get('model', 'deepseek-flash')
            batches = _batches(frozen, model)
            stats['total_batches'] = len(batches)
            combined, actions, created = [], None, {}
            for prepared in batches:
                _check_cancel(cancelled)
                _current(org, scope_project, frozen)
                _check_cancel(cancelled)
                if actions is not None:
                    by_key = {p['key']: p for p in frozen['papers']}
                    current_papers = [dict(by_key[p['key']], categories=list(frozen['memberships'].get(p['key'], [])))
                                      for p in prepared['context']['papers']]
                    prepared = category_review.prepare(frozen['directions'], current_papers, model=model,
                                                       fixed_actions=list(actions.values()))
                stats['calls'] += 1
                try:
                    result = app.gateway.call(category_review.OPERATION, prepared['messages'], dry_run=dry_run) or {}
                except Exception as exc:
                    result = {'ok': False, 'reason': str(exc), 'usage_unknown': True}
                # The gateway can reconcile usage before rejecting reply content.
                # Preserve that measurement even though this batch has no plan.
                if not result.get('ok') and not (result.get('usage_unknown') or result.get('usage_reserved')):
                    usage = (result.get('usage') or {}).get('total_tokens')
                    if isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0 and stats['tokens_known']:
                        stats['total_tokens'] += usage
                if result.get('usage_unknown') or not result.get('ok'):
                    if result.get('usage_unknown'):
                        stats.update(tokens_known=False, total_tokens=None, usage_unknown=True)
                    code, message = degrade_reason(result, profile.get('language') == 'en-US')
                    if result.get('ok') and result.get('usage_unknown'):
                        code = 'usage_unknown'
                        message = ('The AI usage is not confirmed; the reserved budget is retained.'
                                   if profile.get('language') == 'en-US' else 'AI 分类审阅的用量尚未确认；记录已保留。')
                    elif result.get('usage_unknown') and '预留' not in message and 'reserved' not in message.lower():
                        message += (' The reserved budget is retained until usage is confirmed.'
                                    if profile.get('language') == 'en-US' else ' 用量尚未确认，记录已保留。')
                    stats.update(error_code=code, http_status=result.get('http_status'),
                                 usage_reserved=bool(result.get('usage_reserved') or result.get('usage_unknown')))
                    _check_cancel(cancelled)
                    raise ValueError(message)
                if dry_run or result.get('dry_run'):
                    _check_cancel(cancelled)
                    stats.update(status='dry_run', error='仅检查预算和输入；没有调用模型或生成 AI 方案')
                    return _offline(org, scope_project, profile, stats)
                usage = (result.get('usage') or {}).get('total_tokens')
                if isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0:
                    if stats['tokens_known']:
                        stats['total_tokens'] += usage
                else:
                    stats.update(tokens_known=False, total_tokens=None, usage_unknown=True, error_code='usage_unknown')
                    _check_cancel(cancelled)
                    raise ValueError('AI 分类审阅没有返回实际用量，本次已停止后续批次，方案未保存')
                _check_cancel(cancelled)
                try:
                    parsed = category_review.parse(result.get('content'), prepared['context'], finish_reason=result.get('finish_reason'))
                except ValueError:
                    stats['error_code'] = 'bad_reply'
                    raise
                batch = _stable_batch(parsed, frozen['directions'])
                if actions is not None and {i: _action_identity(op) for i, op in actions.items()} != {op['id']: _action_identity(op) for op in batch['categories']}:
                    raise ValueError('不同批次对同一已有类别的修改建议冲突，整份 AI 方案未保存')
                actions = actions or {op['id']: op for op in batch['categories']}
                combined.extend(batch['papers'])
                for category in batch['new_categories']:
                    previous = created.get(category['id'])
                    if previous and (category_identity(previous['name']), previous['parent_id']) != (category_identity(category['name']), category['parent_id']):
                        raise ValueError('不同批次对新增类别的父级建议冲突')
                    created.setdefault(category['id'], category)
                plan = dict(categories=list(actions.values()), papers=combined, new_categories=list(created.values()))
                # Reject an unsafe deletion before paying for further batches.
                deleted = {op['id'] for op in plan['categories'] if op['action'] == 'delete'}
                scope_keys = {p['key'] for p in frozen['papers']}
                if any(key not in scope_keys and deleted.intersection(ids) for key, ids in frozen['memberships'].items()):
                    raise ValueError('待删除类别仍有本次范围外或已归档论文，未完整审阅，不能删除')
                _current(org, scope_project, frozen)
                stats['completed_batches'] += 1
                stats['processed_papers'] += len(batch['papers'])
                stats['remaining_papers'] = stats['total_papers'] - stats['processed_papers']
            plan, kept_by_scope = _keep_names_outside(plan, frozen)
            plan = _fill_empty(_reuse_outside(_unique_ids(plan, frozen), frozen), frozen, profile.get('language') or 'zh-CN')
            stats['kept_by_scope'] = kept_by_scope
            plan.update(category_scope=[d['id'] for d in frozen['directions']], scoped=frozen['scoped'],
                        scope_project=scope_project if frozen['scoped'] else None)
            plan, stats['demoted_for_validity'] = _repair(org, plan)
            stats.update(unclassified_papers=sum(1 for p in frozen['papers'] if not frozen['memberships'].get(p['key'])),
                         fallback_papers=sum(1 for p in plan['papers'] if p.get('fallback')))
            _safe_plan(plan, frozen)
            _current(org, scope_project, frozen)
            _check_cancel(cancelled)
            stats['status'] = 'complete'
            plan['stats'] = dict(stats)
            snapshot = org.store_ai_review(plan, frozen['revision'], frozen['fingerprint'], frozen['structure'], scope_project)
            snapshot['ai_review'] = dict(stats)
            return snapshot
        except _ReviewCancelled as exc:
            stats.update(status='cancelled', error=str(exc), error_code='cancelled')
            return _offline(org, scope_project, profile, stats)
        except ValueError as exc:
            stats.update(status='failed', error=str(exc), error_code=stats.get('error_code') or
                         ('invalid_input' if not stats['calls'] else 'error'))
            return _offline(org, scope_project, profile, stats)
