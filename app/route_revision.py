"""Local, bounded Route requirements and revision patches. No model or persistence.

The caller must bind a preview to its graph and effective-feedback snapshot and
recompute this patch in the confirmation transaction. A cutoff here is a preview
calculation, never permission to accept an AI/client-authored cutoff.
"""
import copy
import json
import re
import uuid

from . import pathgraph

BRIEF_LIMITS = {'goal': 250, 'known': 150, 'include': 150, 'exclude': 150, 'structure': 500}
MAX_OPERATIONS = 400
MAX_RESPONSE_BYTES = 131072
NODE_FIELDS = {'name', 'terms', 'hint', 'type', 'why', 'intro'}


def _utf8(text):
    try:
        text.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('文本含无效Unicode字符') from exc
    return text


def validate_brief(value):
    if not isinstance(value, dict) or set(value) - set(BRIEF_LIMITS):
        raise ValueError('学习需求必须使用固定五字段')
    clean = {}
    for field, cap in BRIEF_LIMITS.items():
        text = value.get(field, '')
        if not isinstance(text, str) or len(text) > cap:
            raise ValueError(f'{field}必须是文本且不超过{cap}个字符')
        clean[field] = _utf8(text).strip()
    if not clean['goal']:
        raise ValueError('请填写学习目标')
    return clean


def progress_cutoff(project_max, freeze=None):
    """IDs are global; an explicit reset cannot predate its frozen snapshot."""
    frozen = (freeze or {}).get('through_feedback_id', 0)
    if any(type(value) is not int or not 0 <= value <= 2**63 - 1 for value in (project_max, frozen)):
        raise ValueError('invalid progress feedback cutoff')
    return max(project_max, frozen)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('修改补丁含重复JSON字段')
        value[key] = item
    return value


def strict_json(content):
    """Strict JSON shared by model replies and the raw Route HTTP boundary."""
    try:
        return json.loads(content, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非有限JSON数值')))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError('修改请求不是完整严格JSON') from exc


def parse(content, *, finish_reason=None):
    if finish_reason == 'length':
        raise ValueError('修改回复已截断，原学习图未修改')
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_RESPONSE_BYTES:
        raise ValueError('修改回复超出本地解析上限')
    value = strict_json(content)
    _operations(value)
    return value


def _operations(value):
    if not isinstance(value, dict) or set(value) != {'operations'}:
        raise ValueError('修改补丁只能包含operations')
    operations = value['operations']
    if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
        raise ValueError('修改操作超限或格式无效')
    return operations


def _validated_graph(graph):
    if not isinstance(graph, dict) or not isinstance(graph.get('concepts'), list):
        raise ValueError('not a map')
    names = [pathgraph._key(c.get('name')) for c in graph['concepts'] if isinstance(c, dict)]
    # A legacy Map needing target repair must be available to a set_targets patch.
    # Never infer targets; the merged result below still requires active targets.
    clean = pathgraph.validate(graph, tolerate=names, explicit=True, require_active_targets=False)
    _utf8(json.dumps(clean, ensure_ascii=False, allow_nan=False))
    return clean


def graph_context(graph):
    """Complete compact graph with request-local aliases; no private IDs/feedback."""
    clean = _validated_graph(graph)
    aliases = {c['id']: f'c{i+1}' for i, c in enumerate(clean['concepts'])}
    fields = ('name', 'terms', 'hint', 'type', 'why', 'intro', 'state')
    return {'concepts': {aliases[c['id']]: {k: c[k] for k in fields if k in c}
                         for c in clean['concepts']},
            'prereqs': [[aliases[e['from']], aliases[e['to']], e['state']] for e in clean['prereqs']],
            'targets': [aliases[t] for t in clean['targets']]}


def _node_changes(value):
    if not isinstance(value, dict) or not value or set(value) - NODE_FIELDS:
        raise ValueError('节点修改包含未知字段或为空')
    clean = {}
    for key, cap in [('name', 60), ('why', 120), ('intro', pathgraph.INTRO_LIMIT)]:
        if key in value:
            text = value[key]
            if not isinstance(text, str) or len(text) > cap or (key == 'name' and not pathgraph._key(text)):
                raise ValueError(f'无效节点字段：{key}')
            clean[key] = pathgraph._prose(_utf8(text), cap)
    if 'terms' in value:
        terms = value['terms']
        if not isinstance(terms, list) or not 1 <= len(terms) <= 2 or any(
                not isinstance(t, str) or len(t) > 60 or not pathgraph._key(t) for t in terms):
            raise ValueError('检索词必须是1至2个不超过60字符的文本')
        if len({pathgraph._key(t) for t in terms}) != len(terms):
            raise ValueError('检索词重复')
        clean['terms'] = [pathgraph._prose(_utf8(t), 60) for t in terms]
    if 'hint' in value:
        if type(value['hint']) is not int or not 1 <= value['hint'] <= 4:
            raise ValueError('难度必须是1至4的整数')
        clean['hint'] = value['hint']
    if 'type' in value:
        if not isinstance(value['type'], str) or value['type'] not in pathgraph.TYPES:
            raise ValueError('未知概念类型')
        clean['type'] = value['type']
    return clean


def semantic_key(node):
    return (pathgraph._key(node['name']),
            tuple(sorted(pathgraph._key(t) for t in node.get('terms', []))), node.get('type'))


def apply_patch(graph, patch, *, through_feedback_id=0, new_ids=None):
    """Apply an allowlisted patch to a copy; return changes, reset IDs and warnings.

    c# refers to a node in the original full graph. n# refers to a fresh node.
    Operations are declarative: new nodes may be referenced before their add.
    A node may be updated or removed once; an edge may be touched once. No
    remove+add trick can reuse old identity or silently replace an existing edge.
    """
    if type(through_feedback_id) is not int or not 0 <= through_feedback_id <= 2**63 - 1:
        raise ValueError('invalid progress feedback cutoff')
    before = _validated_graph(graph)
    result = copy.deepcopy(before)
    operations = _operations(patch)
    if new_ids is not None and (not isinstance(new_ids, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r'n[1-9]\d{0,2}', k)
            or not isinstance(v, str) or not re.fullmatch(r'r-[0-9a-f]{32}', v) for k, v in new_ids.items())
            or len(set(new_ids.values())) != len(new_ids)):
        raise ValueError('invalid saved preview identities')
    aliases = {f'c{i+1}': c['id'] for i, c in enumerate(before['concepts'])}
    old = {c['id']: c for c in before['concepts']}
    nodes = {c['id']: c for c in result['concepts']}
    removed, added, touched_nodes, touched_edges = [], [], set(), set()
    targets_op = None
    edges = {(e['from'], e['to']): e for e in result['prereqs']}
    edge_ops = []

    # Validate shapes and collect all new aliases before resolving references.
    shapes = {'add_node': {'op', 'ref', 'node'}, 'update_node': {'op', 'ref', 'changes'},
              'remove_node': {'op', 'ref'}, 'add_edge': {'op', 'from', 'to'},
              'remove_edge': {'op', 'from', 'to'}, 'set_targets': {'op', 'refs'}}
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get('op'), str):
            raise ValueError('无效修改操作')
        kind = operation['op']
        if kind not in shapes or set(operation) != shapes[kind]:
            raise ValueError('未知修改操作或字段')
        if kind == 'add_node':
            ref = operation['ref']
            if not isinstance(ref, str) or not re.fullmatch(r'n[1-9]\d{0,2}', ref) or ref in aliases:
                raise ValueError('新增节点必须使用唯一n#别名')
            changes = _node_changes(operation['node'])
            if not {'name', 'terms'} <= set(changes):
                raise ValueError('新增节点需要名称和检索词')
            if new_ids is not None and ref not in new_ids:
                raise ValueError('saved preview identity missing')
            node_id = new_ids[ref] if new_ids is not None else 'r-' + uuid.uuid4().hex
            if node_id in nodes:
                raise ValueError('新增节点身份冲突，请重新预览')
            aliases[ref] = node_id
            node = {'id': node_id, 'hint': 2, 'origin': 'plan', 'state': 'active',
                    **changes, 'progress_since_feedback_id': through_feedback_id}
            if 'intro' in changes:
                node['intro_by'] = 'ai'
            nodes[node_id] = node
            added.append(node_id)
            result['concepts'].append(node)

    assigned_ids = {ref: identifier for ref, identifier in aliases.items() if ref.startswith('n')}
    if new_ids is not None and set(new_ids) != set(assigned_ids):
        raise ValueError('saved preview contains unused identities')

    def resolve(ref):
        if not isinstance(ref, str) or ref not in aliases:
            raise ValueError('修改引用了未知节点')
        return aliases[ref]

    for operation in operations:
        kind = operation['op']
        if kind == 'add_node':
            continue
        if kind in ('remove_node', 'update_node'):
            node_id = resolve(operation['ref'])
            if node_id not in old or node_id in touched_nodes:
                raise ValueError('节点修改重复、冲突或引用新增节点')
            touched_nodes.add(node_id)
            if kind == 'remove_node':
                removed.append(node_id)
            else:
                changes = _node_changes(operation['changes'])
                if 'intro' in changes and nodes[node_id].get('intro') and nodes[node_id].get('intro_by', 'user') == 'user':
                    raise ValueError('AI不能覆盖人工简介，请使用手动编辑')
                nodes[node_id].update(changes)
                if 'intro' in changes:
                    nodes[node_id]['intro_by'] = 'ai'
        elif kind in ('add_edge', 'remove_edge'):
            pair = (resolve(operation['from']), resolve(operation['to']))
            if pair in touched_edges:
                raise ValueError('依赖修改重复或冲突')
            touched_edges.add(pair)
            edge_ops.append((kind, pair))
        elif kind == 'set_targets':
            refs = operation['refs']
            if targets_op is not None or not isinstance(refs, list) or not refs:
                raise ValueError('必须明确设置一组新目标')
            targets_op = [resolve(ref) for ref in refs]
            if len(set(targets_op)) != len(targets_op):
                raise ValueError('目标引用重复')

    if set(removed) & set(before['targets']) and targets_op is None:
        raise ValueError('删除目标时必须明确设置新目标')
    for kind, pair in edge_ops:
        if set(pair) & set(removed):
            raise ValueError('依赖修改引用了已删除节点')
        if kind == 'remove_edge':
            if pair not in edges:
                raise ValueError('要删除的依赖不存在')
            del edges[pair]
        else:
            if pair in edges:
                raise ValueError('新增依赖已存在')
            edges[pair] = {'from': pair[0], 'to': pair[1], 'support': None, 'origin': 'plan', 'state': 'active'}
    result['concepts'] = [c for c in result['concepts'] if c['id'] not in removed]
    result['prereqs'] = [e for pair, e in edges.items() if not set(pair) & set(removed)]
    if targets_op is not None:
        result['targets'] = targets_op
    reset = list(added)
    for node in result['concepts']:
        previous = old.get(node['id'])
        if previous and semantic_key(node) != semantic_key(previous):
            reset.append(node['id'])
            node['progress_since_feedback_id'] = max(through_feedback_id, previous.get('progress_since_feedback_id', 0))
    # Existing paper-shaped names may be kept unchanged, but cannot be introduced by an update.
    tolerated = [pathgraph._key(c['name']) for c in result['concepts']
                 if c['id'] in old and semantic_key(c) == semantic_key(old[c['id']])]
    result = pathgraph.validate(result, tolerate=tolerated, explicit=True)
    by_id = {c['id']: c for c in result['concepts']}
    warnings = [{'kind': 'hint_inversion', 'from': e['from'], 'to': e['to']}
                for e in result['prereqs'] if by_id[e['from']]['hint'] > by_id[e['to']]['hint']]
    return {'graph': result, 'reset': reset, 'added': added, 'removed': removed, 'new_ids': assigned_ids,
            'updated': [c['id'] for c in result['concepts'] if c['id'] in old and c != old[c['id']]],
            'warnings': warnings, 'targets_changed': result['targets'] != before['targets'],
            'changed': result != before}
