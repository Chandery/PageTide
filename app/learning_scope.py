"""Known explicit object conflicts for local learning; never a semantic judge.

Read only existing positive user goal/include/keywords. Unknown targets and
generic background remain unclassified. A named comparison containing a target
is preserved. No paper IDs, audit labels, AI, or learned preference inference.
"""
import re
from . import eligibility

_CANCERS = {
    'NSCLC': r'\bNSCLC\b|\bnon[- ]small[- ]cell[- ]lung[- ](?:cancer|carcinoma)\b|非小细胞肺癌',
    'breast cancer': r'\b(?:breast (?:cancer|carcinoma)|TNBC)\b|乳腺癌',
    'liver cancer': r'\b(?:liver cancer|hepatocellular carcinoma|HCC)\b|肝癌',
    'melanoma': r'\bmelanoma\b|黑色素瘤',
    'glioblastoma': r'\bglioblastoma\b|胶质母细胞瘤',
    'colorectal cancer': r'\b(?:colorectal|colon|rectal) cancer\b|结直肠癌',
    'pancreatic cancer': r'\bpancreatic cancer\b|胰腺癌',
    'renal cancer': r'\b(?:renal cell carcinoma|kidney cancer)\b|肾癌',
    'small cell lung cancer': r'\bSCLC\b|(?<!non-)(?<!non )\bsmall cell lung cancer\b|(?<!非)小细胞肺癌',
}
_PD = r'\bPD[- _]?(?:L[- _]?)?1\b|programmed (?:cell )?death[- ](?:ligand[- ])?1'
_VISUAL = r'\bvisual\b|视觉'
_PLAN = r'\b(?:world[- ]models?|planning|robotics?)\b|世界模型|规划|机器人'
_LITHIUM = r'\b(?:lithium metal|metallic lithium|Li metal|Li anodes?)\b|锂金属'
_INTERFACE = r'\b(?:interfaces?|interphases?)\b|界面'
_SULFIDE_EN = r'\bsulfide[- ](?:based[- ])?(?:(?:all[- ])?solid[- ](?:state[- ])?)?electrolytes?\b'
_SULFIDE_ZH = r'硫化物(?:基)?(?:全?固态)?电解质'
_SULFIDE_IDENTITY = _SULFIDE_EN + '|' + _SULFIDE_ZH
_SULFIDE_ELECTROLYTE = r'(?<!non-)(?<!non )' + _SULFIDE_EN + r'|(?<!非)' + _SULFIDE_ZH
_OXIDE_ELECTROLYTE = (r'\boxide[- ](?:based[- ])?(?:solid[- ](?:state[- ])?)?electrolytes?\b|'
                      r'氧化物(?:基)?(?:全?固态)?电解质')


def _has(pattern, text):
    return bool(re.search(pattern, text, re.I | re.ASCII))


def _trace(fields, pattern):
    for field, value in fields:
        for match in re.finditer(pattern, value, re.I | re.ASCII):
            before = re.split(r'[.!?;\n。！？；]', value[:match.start()])[-1]
            after = re.split(r'[.!?;\n。！？；]', value[match.end():])[0]
            # Only positive user scope establishes a target, never an exclusion.
            if re.search(r'\b(?:not|no|exclude|excluding|without)\b|排除|不研究|不纳入|不包括', before, re.I | re.ASCII):
                continue
            if re.search(r'^\s*(?:(?:(?:studies|patients|papers|reports)\s+)?(?:is|are|was|were|will be)\s+(?:excluded|not included|not studied|out of scope)\b|(?:相关)?(?:材料|研究|论文|患者)?(?:不纳入|不研究|排除|不包括|不考虑))', after, re.I | re.ASCII):
                continue
            return {'field': field, 'matched_text': match.group(),
                    'quote': value[max(0, match.start()-80):match.end()+80]}
    return None


def make(brief=None, keywords=()):
    brief = brief if isinstance(brief, dict) else {}
    fixed = [(key, str(brief.get(key) or '')[:8000]) for key in ('goal', 'include')]
    keyword_fields = [('keyword', str(value)[:120]) for value in list(keywords or ())[:40]]
    fields = fixed + keyword_fields
    constraints = []
    # Explicit objects in the fixed brief take priority over broader search
    # keywords. Keywords fill an absent object, never widen a saved target.
    disease_fields = fixed if any(_trace(fixed, pattern) for pattern in _CANCERS.values()) else keyword_fields
    diseases = [(name, trace) for name, pattern in _CANCERS.items() if (trace := _trace(disease_fields, pattern))]
    if diseases:
        constraints.append({'kind': 'disease', 'allowed': [name for name, _ in diseases],
                            'source': [trace for _, trace in diseases]})
    pd = _trace(fields, _PD)
    if pd:
        constraints.append({'kind': 'treatment', 'target': 'PD-1/PD-L1', 'source': [pd]})
    visual, plan = _trace(fields, _VISUAL), _trace(fields, _PLAN)
    if visual and plan and not _trace(fields, r'\bbusiness\b|商业'):
        constraints.append({'kind': 'visual_planning', 'source': [visual, plan]})
    lithium, interface = _trace(fields, _LITHIUM), _trace(fields, _INTERFACE)
    if lithium and interface:
        constraints.append({'kind': 'lithium_metal_interface', 'source': [lithium, interface]})
    # Fixed named identity/exclusion wins; a generic "an electrolyte" still
    # permits an explicit user keyword to fill absent composition. This finite
    # oxide contrast is the observed scope conflict, not a chemistry ontology.
    generic_electrolyte = r'\belectrolytes?\b|电解质'
    fixed_identity = any(_has(_SULFIDE_IDENTITY + '|' + _OXIDE_ELECTROLYTE, value)
                         for field, value in fixed)
    fixed_exclusion = (any(_has(generic_electrolyte, value) for field, value in fixed)
                       and not _trace(fixed, generic_electrolyte))
    electrolyte_fields = fixed if fixed_identity or fixed_exclusion else keyword_fields
    sulfide_electrolyte = _trace(electrolyte_fields, _SULFIDE_ELECTROLYTE)
    if sulfide_electrolyte:
        constraints.append({'kind': 'sulfide_electrolyte', 'source': [sulfide_electrolyte]})
    return {'constraints': constraints}


def check(scope, paper):
    """A receipt for explicit contrary focus; absence of conflict is not useful.

    General/basic papers need not repeat the object. Only an explicit alternative
    object/treatment is rejected, and a real comparison containing the user's
    target remains compatible. This intentionally does not certify clinical or
    personal value, and does not claim a complete biomedical ontology.
    """
    title = str(paper.get('title') or '')
    text = eligibility.retrieval_text(paper)
    conflicts = []
    for constraint in (scope or {}).get('constraints') or []:
        kind = constraint['kind']
        reason = None
        if kind == 'disease':
            allowed = constraint['allowed']
            other = [name for name, pattern in _CANCERS.items() if name not in allowed and _has(pattern, title)]
            if other and not any(_has(_CANCERS[name], text) for name in allowed):
                reason = 'different_disease_focus'
        elif kind == 'treatment':
            if (_has(r'\b(?:platinum|cisplatin|EGFR|TKI|tyrosine kinase inhibitor)\b.{0,50}\b(?:resistan|refractor)|铂.{0,12}耐药|靶向.{0,12}耐药', title)
                    and not _has(_PD, text)):
                reason = 'different_treatment_focus'
        elif kind == 'visual_planning':
            if (_has(r'\b(?:business|organizational|marketing)\b|商业|市场营销', title)
                    and not _has(_VISUAL + r'|\brobotics?\b|机器人', title)
                    and _has(r'rather than physical|not directly applicable|business[- ](?:practice|states?|environments?)|商业环境', text)):
                reason = 'different_environment_focus'
            elif (_has(r'\b(?:metacognitive|psychological|cognitive dynamics)\b|元认知|心理学', title)
                    and _has(r'confidence judgments?|response choices?|response times?|human participants?|cognitive dynamics|人类认知|被试', text)
                    and not _has(r'\b(?:robots?|robotics|visual (?:states?|representations?|features?|observations?|planning)|vision[- ]based)\b|机器人|视觉表征|视觉规划', text)):
                reason = 'different_environment_focus'
        elif kind == 'lithium_metal_interface':
            if (_has(r'\b(?:silicon|Si)[/ -](?:sulfide|anode|electrolyte)|\b(?:silicon anode|cathode|lithium iron phosphate)\b|硅负极|正极', title)
                    and not _has(_LITHIUM, text)):
                reason = 'different_electrode_focus'
        if reason:
            conflicts.append({'reason_code': reason, 'constraint': constraint,
                              'paper_quote': title})
    return {'compatible': not conflicts, 'conflicts': conflicts,
            'status': 'known_conflict' if conflicts else 'no_known_conflict',
            'semantic_value_judged': False}


def as_text(scope):
    """Positive user source only, for the existing local AI citation guard."""
    return ' '.join(dict.fromkeys(source['matched_text']
        for constraint in (scope or {}).get('constraints') or []
        for source in constraint.get('source') or []))
