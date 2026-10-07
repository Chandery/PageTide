"""One explicit AI review job: frozen metadata, bounded calls, a complete preview.

Only the budgeted gateway can send requests. This module never applies categories,
retries a request, or marks a failed partial job as reviewed.
"""
import copy
import hashlib
import json

from . import category_review, operation_lock
from .clustering import corpus_fingerprint
from .organization import Conflict, Organization
from .organization_facets import review, structure_hash
from .organization_terms import category_identity


class _ReviewCancelled(ValueError):
    pass


def _check_cancel(cancelled):
    if cancelled is not None and cancelled():
        raise _ReviewCancelled('AI 分类审阅已取消，停止后续批次；没有保存或应用不完整方案')


def _capture(org, scope):
    with org._transaction(write=False):
        revision, data = org._load()
        papers = org._corpus(scope)
        directions = copy.deepcopy(data['directions'])
        memberships = copy.deepcopy(data['memberships'])
        return dict(revision=revision, papers=papers, directions=directions,
                    memberships=memberships, fingerprint=corpus_fingerprint(papers),
                    structure=structure_hash(directions, memberships))


def _current(org, scope, frozen):
    live = _capture(org, scope)
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
    """Preflight every batch before spending; decrease paper count, never trim the tree."""
    papers = [dict(p, categories=list(frozen['memberships'].get(p['key'], []))) for p in frozen['papers']]
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

    mapping = {}
    for identifier in new:
        identity = json.dumps(path(identifier), ensure_ascii=False, separators=(',', ':'))
        stable = 'ai-cat-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
        if stable in old:
            raise ValueError('AI 新类别编号与现有类别冲突')
        mapping[identifier] = stable
    convert = lambda identifier: mapping.get(identifier, identifier)
    categories = [dict(op, **({'target': convert(op['target'])} if 'target' in op else {})) for op in parsed['categories']]
    papers = [dict(p, categories=[convert(i) for i in p['categories']]) for p in parsed['papers']]
    created = [dict(d, id=mapping[d['id']], parent_id=convert(d.get('parent_id'))) for d in parsed['new_categories']]
    return dict(categories=categories, papers=papers, new_categories=created)


def _action_identity(op):
    return (op['action'], category_identity(op['name']) if 'name' in op else None, op.get('target'))


def _safe_plan(plan, frozen):
    """Validate cross-batch state and all global membership holders, including archived papers."""
    old = {d['id']: d for d in frozen['directions']}
    ops = {op['id']: op for op in plan['categories']}
    new = {d['id']: d for d in plan['new_categories']}
    keys = {p['key'] for p in frozen['papers']}
    if set(ops) != set(old) or {p['key'] for p in plan['papers']} != keys or len(plan['papers']) != len(keys):
        raise ValueError('AI 方案没有完整覆盖分类目录或本次全部论文')
    deleted = {i for i, op in ops.items() if op['action'] == 'delete'}
    for key, memberships in frozen['memberships'].items():
        if key not in keys and deleted.intersection(memberships):
            raise ValueError('待删除类别仍有本次范围外或已归档论文，未完整审阅，不能删除')
    redirect = {i: op['target'] for i, op in ops.items() if op['action'] == 'merge'}
    retained = (set(old) - deleted - set(redirect)) | set(new)
    parents, names = {}, {}
    for identifier in retained:
        item = new.get(identifier, old.get(identifier))
        parent = item.get('parent_id')
        parents[identifier] = redirect.get(parent, parent)
        names[identifier] = ops[identifier].get('name', item['name']) if identifier in old else item['name']
        if parents[identifier] is not None and parents[identifier] not in retained:
            raise ValueError('AI 完整方案留下悬空子类')
    identities = set()
    for identifier in retained:
        signature = (parents[identifier], category_identity(names[identifier]))
        if signature in identities:
            raise ValueError('AI 各批合并后仍有重复同义类别')
        identities.add(signature)
        seen, current = set(), identifier
        while current is not None:
            if current in seen:
                raise ValueError('AI 完整方案留下循环分类')
            seen.add(current)
            current = parents[current]
    if any(not set(p['categories']) <= retained for p in plan['papers']):
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
                     total_batches=0, calls=0, total_tokens=0, tokens_known=True, error=None)
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
                stats['calls'] += 1
                try:
                    result = app.gateway.call(category_review.OPERATION, prepared['messages'], dry_run=dry_run) or {}
                except Exception as exc:
                    result = {'ok': False, 'reason': str(exc), 'usage_unknown': True}
                if result.get('usage_unknown'):
                    stats.update(tokens_known=False, total_tokens=None)
                    _check_cancel(cancelled)
                    raise ValueError('AI 分类审阅的用量尚未确认；预算预留保留，本次已停止后续批次，方案未保存')
                if not result.get('ok'):
                    _check_cancel(cancelled)
                    raise ValueError(result.get('reason') or 'AI 没有完成分类审阅')
                if dry_run or result.get('dry_run'):
                    _check_cancel(cancelled)
                    stats.update(status='dry_run', error='仅检查预算和输入；没有调用模型或生成 AI 方案')
                    return _offline(org, scope_project, profile, stats)
                usage = (result.get('usage') or {}).get('total_tokens')
                if isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0:
                    if stats['tokens_known']:
                        stats['total_tokens'] += usage
                else:
                    stats.update(tokens_known=False, total_tokens=None)
                    _check_cancel(cancelled)
                    raise ValueError('AI 分类审阅没有返回实际用量，本次已停止后续批次，方案未保存')
                _check_cancel(cancelled)
                parsed = category_review.parse(result.get('content'), prepared['context'], finish_reason=result.get('finish_reason'))
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
            _safe_plan(plan, frozen)
            _current(org, scope_project, frozen)
            _check_cancel(cancelled)
            stats['status'] = 'complete'
            plan['stats'] = dict(stats)
            snapshot = org.store_ai_review(plan, frozen['revision'], frozen['fingerprint'], frozen['structure'], scope_project)
            snapshot['ai_review'] = dict(stats)
            return snapshot
        except _ReviewCancelled as exc:
            stats.update(status='cancelled', error=str(exc))
            return _offline(org, scope_project, profile, stats)
        except ValueError as exc:
            stats.update(status='failed', error=str(exc))
            return _offline(org, scope_project, profile, stats)
