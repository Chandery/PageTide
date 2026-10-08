"""Finite public-task relation checks, not a scientific semantic classifier.

Names/introductions constrain broad retrieval aliases. These reusable bilingual
relations contain no paper IDs, dataset labels or evaluation-persona overrides.
Unknown wording remains reviewable uncertainty; no mastery or prerequisites.
"""
import re


DEFINITIONS = {
    'action_prediction': (r'action[- ]condition|动作条件',
        [r'action[- ]condition\w*', r'condition\w*.{0,45}(?:actions?|control inputs?)',
         r'(?:actions?|control inputs?).{0,35}(?:condition|input)', r'动作.{0,12}(?:条件|输入)'],
        [r'predict\w*|forecast\w*|dynamics?|transition\w*|预测|动力学|转移']),
    'planning_evaluation': (r'(?:planning|规划).*(?:evaluat|评估)|(?:evaluat|评估).*(?:planning|规划)',
        [r'plann\w*|规划'],
        [r'experiment\w*|evaluat\w*|compar\w*|benchmark\w*|test\w*|measur\w*|对比|实验|评估|测量']),
    'immune_environment': (r'microenvironment|微环境|T.cell exhaustion',
        [r'microenvironment|CD8\+?|T[- ]cells?|macrophag\w*|neutrophil\w*|微环境|巨噬|中性粒|T细胞'],
        [r'dysfunction|exhaust\w*|infiltrat\w*|immunosuppres\w*|resistan\w*|'
         r'(?:inhibit|impair|suppress)\w*.{0,25}(?:function|activat)|耐药|耗竭|浸润|免疫抑制']),
    'resistance_evaluation': (r'(?:resistan\w*|耐药).*(?:evaluat|评估|证据)',
        [r'resistan\w*|response\w*|耐药|应答|响应'],
        [r'patient\w*|cohort\w*|associat\w*|predict\w*|biomarker\w*|signature\w*|trial\w*|患者|队列|关联|预测|标志物']),
    'planning': (r'planning|规划', [r'plann\w*|MPC|MPPI|model predictive control|规划'], []),
}


def profiles(node):
    # The user's precise ability takes precedence over permissive search words.
    text = str(node.get('name') or '') + ' ' + str(node.get('intro') or '')
    found = [name for name, (pattern, _, _) in DEFINITIONS.items() if re.search(pattern, text, re.I)]
    return [name for name in found if not (name == 'planning' and 'planning_evaluation' in found)]


def evidence_patterns(graph):
    kinds = set(kind for node in (graph or {}).get('concepts', []) for kind in profiles(node))
    return [(re.compile(pattern, re.I), 3) for kind in sorted(kinds)
            for patterns in DEFINITIONS[kind][1:] for pattern in patterns]


def relation(kind, quote, split):
    first, second = DEFINITIONS[kind][1:]
    for sentence in [clause for sentence in split(quote)
                     for clause in re.split(r'\b(?:but|however)\b|但是|但(?=仍|有|进行)', sentence, flags=re.I)]:
        # Bounds are clause-local; unrelated mentions and long gaps cannot prove
        # an input/output relationship merely by sharing a paragraph.
        if len(sentence) > 180:
            continue
        if kind == 'action_prediction' and re.search(
                r'\b(?:not|no|never|without)\b.{0,20}action[- ]condition|'
                r'\b(?:no|without)\s+(?:actions?|control inputs?)\b|'
                r'\bactions?\b.{0,15}(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,20}(?:input|condition|used)|'
                r'(?:\bnot\b|n[\'’]t\b|\bnever\b)\s+(?:predict|forecast)|'
                r'(?:prediction|forecast\w*|action[- ]condition\w*).{0,20}(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,15}(?:used|implement\w*|performed)|'
                r'非动作条件|不以动作', sentence, re.I):
            continue
        if kind == 'planning_evaluation' and re.search(
                r'\b(?:no|without|never)\b.{0,20}(?:experiment\w*|evaluat\w*|test\w*)|'
                r'(?:experiment\w*|evaluat\w*|test\w*).{0,30}(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,20}(?:performed|conducted|used)|'
                r'未.{0,8}(?:实验|评估|测试)|没有.{0,8}(?:实验|评估|测试)', sentence, re.I):
            continue
        if any(re.search(p, sentence, re.I) for p in first) and (
                not second or any(re.search(p, sentence, re.I) for p in second)):
            return True
    return False


def check(node, quote, *, split, term_match):
    """A supported coarse task relation does not establish all task conditions."""
    task_profiles = profiles(node)
    label = str(node.get('name') or '')
    is_pd_foundation = (node.get('type') == 'foundation' and
                       re.search(r'PD[- /]?1|PD[- /]?L1', label, re.I))
    if is_pd_foundation and re.search(
            r'predictor|biomarker|signature|associat\w*|synerg\w*|impair\w*|resistan\w*|dysfunction|'
            r'耐药|标志物|预测|协同|增敏|抑制.{0,8}功能', quote, re.I):
        return {'status': 'specific_task_not_foundation', 'role': 'uncertain'}
    if task_profiles:
        # A critical qualifier in the name cannot be overridden by 'world model'.
        if all(relation(kind, quote, split) for kind in task_profiles):
            role = {'action_prediction': 'prediction', 'planning_evaluation': 'evaluation',
                    'resistance_evaluation': 'evidence', 'immune_environment': 'mechanism',
                    'planning': 'planning'}[task_profiles[0]]
            if role == 'mechanism' and re.search(r'associat\w*|predict\w*|cohort|回顾|关联|队列', quote, re.I):
                role = 'evidence'  # An immune-cell correlation is not causality.
            return {'status': 'supported_relation', 'role': role}
        return {'status': 'missing_task_relation', 'role': 'uncertain'}
    terms = [t for t in [label, *node.get('terms', [])] if len(str(t)) >= 3]
    return {'status': 'supported_literal_task' if any(term_match(t, quote) for t in terms) else 'missing_task_relation',
            'role': 'task' if any(term_match(t, quote) for t in terms) else 'uncertain'}


def contradicted(node, quote, adjacent, split):
    """Only actually sent, enclosing-clause negation may veto a short quote."""
    for sentence in split(adjacent):
        for clause in re.split(r'\b(?:but|however)\b|但是|但(?=仍|有|进行)', sentence, flags=re.I):
            if quote.strip().rstrip('.;。；') not in clause:
                continue
            negatives = {
                'action_prediction': r'\b(?:not|no|never|without)\b.{0,20}action[- ]condition|'
                    r'\b(?:no|without)\s+(?:actions?|control inputs?)\b|'
                    r'\bactions?\b.{0,15}(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,20}(?:input|condition|used)|'
                    r'(?:\bnot\b|n[\'’]t\b|\bnever\b)\s+(?:predict|forecast)|'
                    r'(?:prediction|forecast\w*|action[- ]condition\w*).{0,20}(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,15}(?:used|implement\w*|performed)|非动作条件|不以动作',
                'planning_evaluation': r'\b(?:no|without|never)\b.{0,20}(?:experiment\w*|evaluat\w*|test\w*)|'
                    r'(?:experiment\w*|evaluat\w*|test\w*).{0,30}(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,20}(?:performed|conducted|used)|'
                    r'未.{0,8}(?:实验|评估|测试)|没有.{0,8}(?:实验|评估|测试)',
                'planning': r'\b(?:no|without|never)\b.{0,20}planning|planning.{0,20}(?:not|never).{0,20}(?:used|performed)|无规划|未规划'}
            if any(re.search(negatives[kind], clause, re.I) for kind in profiles(node) if kind in negatives):
                return True
    return False


def window_score(piece, graph, split):
    # This only retrieves visible evidence. It does not assign a paper to a task.
    return sum(8 for kind in set(kind for node in (graph or {}).get('concepts', []) for kind in profiles(node))
               if relation(kind, piece, split))


def _ability_name(node):
    """Only a narrow equivalent ability name, never broad domain keywords."""
    name = str(node.get('name') or '').lower()
    if not re.search(DEFINITIONS['action_prediction'][0], name, re.I):
        return None
    # Media and representation terminology do not make another action-input
    # prediction ability. Remaining conditions/methods are deliberately kept.
    name = re.sub(r'action[- ]condition(?:ed|ing)?|动作条件', '', name, flags=re.I)
    name = re.sub(r'\b(?:video|visual|world|model|models|latent|dynamics?|transition|prediction|predictive|forecasting)\b|'
                  r'视频|视觉|世界模型|模型|潜在|潜空间|动力学|状态转移|预测', '', name, flags=re.I)
    return 'action_prediction' if not re.sub(r'[\s\W_]+', '', name) else None


def duplicate_ability(proposal, graph, citations, *, split, term_match):
    """Resolve only a proved equivalent ability, not a new condition/subtask.

    Broad planning/immune keywords cannot establish equivalence. A named new
    constraint (or one made explicit in its introduction) remains a proposal.
    This finite check is not a general semantic deduplicator.
    """
    signature = _ability_name(proposal)
    if signature is None or not citations:
        return None
    def qualifiers(node):
        text = ' '.join([str(node.get('name') or ''), str(node.get('intro') or ''), *node.get('terms', [])]).lower()
        conditions = set()
        for match in re.finditer(r'\b([\w]+)[- ](aware|conditioned|constrained|guided|specific|dependent)\b', text):
            if match[2] == 'conditioned' and re.match(r'\s+(?:on|by)\b', text[match.end():]):
                # "video conditioned on control inputs" names the prediction
                # output, not a new "video" constraint. Read its stated input.
                continue
            conditions.add(match[1])
        conditions.update(re.findall(r'\b([\w]+)\s+(?:constraints?|conditions?)\b', text))
        for match in re.finditer(r'(?:condition(?:ed|ing)\s+(?:on|by)|'
                                r'(?:from|given|using)\s+(?=actions?\b|control inputs?\b))\s*([^.;!?\n]{1,100})', text):
            phrase = re.split(r'\b(?:under|for|to|using|where|which)\b', match[1], maxsplit=1)[0]
            for declared_input in re.split(r'\s+(?:and|plus|with)\s+|,', phrase):
                declared_input = re.sub(r'\s+', ' ', declared_input).strip()
                declared_input = re.sub(r'^(?:the|an?)\s+', '', declared_input)
                if declared_input:
                    conditions.add('action' if re.fullmatch(r'actions?(?: inputs?)?|control inputs?', declared_input) else declared_input)
        conditions.update(re.findall(r'\b(?:online|offline|robust\w*|generaliz\w*|safe\w*|quantiz\w*|few[- ]shot)\b', text))
        return conditions
    proposed_conditions = qualifiers(proposal)
    for node in graph.get('concepts', []):
        if node.get('state', 'active') != 'active' or _ability_name(node) != signature:
            continue
        # The signature itself proves the action qualifier across languages.
        conditions = qualifiers(node) | {'action'}
        if proposed_conditions | {'action'} != conditions:
            continue
        support = [check(node, citation['quote'], split=split, term_match=term_match) for citation in citations]
        if all(result['status'] == 'supported_relation' for result in support):
            return {'name': node['name'], 'role': support[0]['role']}
    return None
