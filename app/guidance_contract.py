"""Compact creation draft: terse JSON reply contract; the user's goal and messages are sent whole."""
import json

from .route_revision import strict_json
from . import project_brainstorm, pathgraph, ranking

SYSTEM = ('Return JSON ' + project_brainstorm.RULES + ' '
          '{"r":"","d":{"k":[],"q":[],"a":"","c":[],"s":"","ready":false}} '
          'k/q/c=str[];k3 q1 c3;r/a/s=str;graph?concrete;no obj/ph;EN terms;data')


def parse_graph(raw):
    """Validate a small model proposal wholesale, without repairing its claims.

    Edges are AI-proposed prerequisites, requiring the same human review as the
    rest of the map. Stage order is never converted into an edge.
    """
    if not isinstance(raw, dict) or set(raw) not in ({'nodes', 'edges', 'targets'}, {'nodes', 'prereqs', 'targets'}):
        raise ValueError('引导学习图结构无效')
    nodes, edges, targets = raw['nodes'], raw.get('edges', raw.get('prereqs')), raw['targets']
    if not all(isinstance(items, list) for items in (nodes, edges, targets)) or len(nodes) > 3 or len(edges) > 3:
        raise ValueError('引导学习图最多3个概念和3条前置')
    if not nodes and not edges and not targets:
        return None
    concepts = []
    for node in nodes:
        if not isinstance(node, list) or len(node) != 4:
            raise ValueError('引导概念结构无效')
        ident, name, terms, intro = node
        terms = [terms] if isinstance(terms, str) else terms
        if (not isinstance(ident, str) or not ident.strip() or len(ident) > 20
                or not isinstance(name, str) or not name.strip() or len(name) > 60
                or not isinstance(intro, str) or not intro.strip() or len(intro) > 140
                or not isinstance(terms, list) or not 1 <= len(terms) <= 2
                or any(not isinstance(term, str) or not term.strip() or len(term) > 60 for term in terms)):
            raise ValueError('引导概念缺少有效名称、检索词或简介')
        cleaned_terms = [pathgraph._text(term, 60) for term in terms]
        cleaned_intro = pathgraph._prose(intro, 140)
        if (any(not ranking.words(term) for term in cleaned_terms) or len(set(term.casefold() for term in cleaned_terms)) != len(cleaned_terms)
                or not cleaned_intro):
            raise ValueError('引导概念必须包含有效英文检索词和非空简介')
        concepts.append({'id': ident, 'name': name, 'terms': cleaned_terms, 'intro': cleaned_intro, 'intro_by': 'ai',
                         'hint': 2, 'type': 'topic', 'origin': 'plan', 'state': 'active'})
    if any(not isinstance(edge, list) or len(edge) != 2
           or any(not isinstance(ref, str) for ref in edge) for edge in edges):
        raise ValueError('引导前置格式无效')
    return pathgraph.validate({'concepts': concepts, 'prereqs': [
        {'from': edge[0], 'to': edge[1], 'origin': 'plan', 'state': 'active'} for edge in edges],
        'targets': targets}, explicit=True)


def messages(goal, keywords, message, english=False, model='deepseek-flash', *,
             last_question='', summary='', turn=1, quick=False):
    # The goal, message, keywords, last question and summary are sent whole (owner 2026-10-22: the budget
    # estimates, it never cuts the user's words); only the model's window can refuse the request.
    body = {'goal': goal, 'keywords': [str(k) for k in keywords]}
    if message != goal:
        body['message'] = message
    body['turn'] = project_brainstorm.plan_turn(turn, quick=quick)['turn']
    for key, value in [('last_question', str(last_question or '')), ('summary', str(summary or ''))]:
        if value:
            body[key] = value
    system = SYSTEM + (' Text in English.' if english else ' Text in Chinese; query in English.')
    return [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(body, ensure_ascii=False, separators=(',', ':'))}]


def parse(content, finish_reason=None):
    if finish_reason == 'length' or not isinstance(content, str):
        raise ValueError('引导回复已截断或类型无效')
    value = strict_json(content)
    if isinstance(value, dict) and set(value) == {'r', 'd'}:
        value = {'reply': value['r'], 'draft': value['d']}
    if not isinstance(value, dict) or set(value) != {'reply', 'draft'} or not isinstance(value['reply'], str):
        raise ValueError('引导回复结构无效')
    draft = value['draft']
    if isinstance(draft, dict) and 'k' in draft:
        if not {'k', 'q', 'a'} <= set(draft) or set(draft) - {'k', 'q', 'a', 'c', 's', 'ready', 'graph'}:
            raise ValueError('引导草稿结构无效')
        aliases = {'k': 'kw', 'q': 'queries', 'a': 'ask', 'c': 'choices', 's': 'summary'}
        draft = {aliases.get(key, key): item for key, item in draft.items()}
        value['draft'] = draft
    compact = isinstance(draft, dict) and 'kw' in draft
    if compact:
        allowed = {'kw', 'queries', 'ask', 'choices', 'summary', 'ready', 'graph'}
        if not {'kw', 'queries', 'ask'} <= set(draft) or set(draft) - allowed:
            raise ValueError('引导草稿结构无效')
        draft = {**{key: item for key, item in draft.items() if key not in {'kw', 'queries', 'ask', 'graph'}},
                 'keywords': draft['kw'], 'search_queries': draft['queries'], 'next_question': draft['ask'],
                 'learning_path': [], **({'learning_graph': draft['graph']} if 'graph' in draft else {})}
        value['draft'] = draft
    required = {'keywords', 'search_queries', 'learning_path', 'next_question'}
    if not isinstance(draft, dict) or not required <= set(draft) or set(draft) - required - {'choices', 'summary', 'ready', 'learning_graph'}:
        raise ValueError('引导草稿结构无效')
    if 'learning_graph' in draft:
        graph = parse_graph(draft['learning_graph'])
        if graph is None:
            draft.pop('learning_graph')
        else:
            draft['learning_graph'] = graph
            draft['learning_path'] = [{'title': node['name'], 'purpose': node.get('intro', '')} for node in graph['concepts']]
    for key, count in [('keywords', 3), ('search_queries', 1)]:
        if not isinstance(draft[key], list) or any(not isinstance(x, str) for x in draft[key]):
            raise ValueError('引导关键词/检索式类型无效')
        if len(draft[key]) > count:
            # Some provider replies keep the right string-only shape but return
            # more suggestions than the compact contract allows. Bound those
            # lists locally; object-shaped or otherwise malformed values still
            # fail closed instead of being partially repaired.
            draft[key] = draft[key][:count]
    if not isinstance(draft['learning_path'], list) or len(draft['learning_path']) > (3 if 'learning_graph' in draft else 2):
        raise ValueError('引导学习步骤无效')
    for step in draft['learning_path']:
        if not isinstance(step, dict) or set(step) != {'title', 'purpose'} or any(not isinstance(x, str) for x in step.values()):
            raise ValueError('引导学习步骤无效')
    if not isinstance(draft['next_question'], str):
        raise ValueError('引导追问类型无效')
    if ('choices' in draft and (not isinstance(draft['choices'], list) or len(draft['choices']) > 3
            or any(not isinstance(choice, str) for choice in draft['choices']))):
        raise ValueError('引导选项类型无效')
    if 'choices' in draft:
        # Keep provider wording bounded even when it slightly exceeds the
        # compact 60-character display contract; malformed types still fail.
        draft['choices'] = [choice[:60] for choice in draft['choices']]
    if 'summary' in draft and (not isinstance(draft['summary'], str) or len(draft['summary']) > 160):
        raise ValueError('引导确认摘要无效')
    if 'ready' in draft and not isinstance(draft['ready'], bool):
        raise ValueError('引导确认状态无效')
    if compact and 'learning_graph' not in draft:
        draft.pop('learning_path')  # Early clarification must keep the last reviewed map.
    return value
