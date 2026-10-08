"""Local creation-map drafts, requiring no additional model request.

Learning stages are independent targets, not evidence of prerequisites or
mastery. A person reviews this map before it is saved to a project.
"""

from . import pathgraph, ranking


def local_route_draft(draft):
    """Turn the current visible stages into a bounded editable concept map.

    The index-based stage ids let the page keep the stage editor and map in
    sync. Intro authorship follows the text's origin; local rendering never
    turns AI prose into a user-authored note. No ordering is treated as a hard
    prerequisite, and a copied paper title/link is not a concept.
    """
    draft = draft if isinstance(draft, dict) else {}
    goal = str(draft.get('goal') or '').strip()
    if draft.get('learning_graph') is not None:
        graph = pathgraph.validate(draft['learning_graph'], explicit=True)
        if len(graph['concepts']) > 3 or len(graph['prereqs']) > 3:
            raise ValueError('引导学习图最多3个概念和3条前置')
        return {'graph': graph, 'brief': {'goal': (goal or graph['concepts'][-1]['name'])[:250],
                'known': '', 'include': '', 'exclude': '', 'structure': ''},
                'source': 'ai_guidance', 'stage_ids': [node['id'] for node in graph['concepts']]}
    keywords = [str(term).strip()[:60] for term in (draft.get('keywords') or [])[:20]
                if str(term).strip() and not pathgraph.paper_shaped({'name': str(term)})]
    stages = draft.get('learning_path') if isinstance(draft.get('learning_path'), list) else []
    author = 'ai' if draft.get('learning_path_origin') == 'ai' else 'user'
    concepts, stage_ids, seen = [], [], {}
    for index, stage in enumerate(stages[:8]):
        name = pathgraph._text(stage.get('title'), 60) if isinstance(stage, dict) else ''
        if not name or not pathgraph._key(name) or pathgraph.paper_shaped({'name': name}):
            stage_ids.append(None)
            continue
        normalized = pathgraph._key(name)
        if normalized in seen:
            stage_ids.append(seen[normalized])
            continue
        node_id = 'stage%d' % (index + 1)
        seen[normalized] = node_id
        stage_ids.append(node_id)
        purpose = pathgraph._prose(stage.get('purpose'), pathgraph.INTRO_LIMIT)
        terms = [name.lower()] if name.isascii() else []
        if not terms:
            terms = [term for term in keywords if name.casefold() in term.casefold() or term.casefold() in purpose.casefold()]
        terms = (terms or keywords or ranking.words(purpose))[:2]
        concepts.append({'id': node_id, 'name': name, 'terms': terms, 'hint': 2,
                         'type': 'topic', 'origin': 'plan' if author == 'ai' else 'user', 'state': 'active',
                         **({'intro': purpose, 'intro_by': author} if purpose else {})})
    if not concepts:
        name = pathgraph._text(goal, 60)
        if not name or not pathgraph._key(name) or pathgraph.paper_shaped({'name': name}):
            name = next(iter(keywords), '学习目标')
        terms = [name.lower()] if name.isascii() else keywords[:2]
        concepts = [{'id': 'goal1', 'name': name, 'terms': terms, 'hint': 2, 'type': 'topic',
                     'origin': 'user', 'state': 'active',
                     **({'intro': pathgraph._prose(goal, pathgraph.INTRO_LIMIT), 'intro_by': 'user'} if goal else {})}]
        source = 'local_goal'
    else:
        source = 'local_stages'
    graph = pathgraph.validate({'concepts': concepts, 'prereqs': [],
                               'targets': [node['id'] for node in concepts]}, explicit=True)
    return {'graph': graph, 'brief': {'goal': (goal or graph['concepts'][-1]['name'])[:250],
            'known': '', 'include': '', 'exclude': '', 'structure': ''},
            'source': source, 'stage_ids': stage_ids}
