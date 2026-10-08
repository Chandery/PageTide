"""Local checks for bounded AI citations; these do not prove scientific truth."""
import re
from . import task_relations

TYPES = {'basic', 'observational', 'trial', 'review', 'unknown'}
ORDER = re.compile(r'requir|prerequisite|must|only after|before|必需|必要|必须|先.{0,50}再|前置', re.I)
PARAGRAPH = re.compile(r'\r\n[ \t]*\r\n|\n[ \t]*\n|\r(?!\n)[ \t]*\r(?!\n)|\f|\u2029|\u2028[ \t]*\u2028')
SULFIDE_ELECTROLYTE = re.compile(
    r'(?<!non-)(?<!non )\bsulfide[- ](?:based[- ])?(?:(?:all[- ])?solid[- ](?:state[- ])?)?'
    r'(?:electrolytes?|SSEs?|SEs?)\b|(?<!非)硫化物(?:基)?(?:全?固态)?电解质', re.I)


def sulfide_context(sentence):
    """Literal affirmative identity, not a negated mention or a coating name."""
    statuses = []
    for match in SULFIDE_ELECTROLYTE.finditer(sentence):
        before, after = sentence[max(0, match.start()-20):match.start()], sentence[match.end():match.end()+35]
        negated = bool(re.search(r'\b(?:no|without)\s+(?:a\s+)?$|未使用|没有使用', before, re.I) or
                       re.search(r'^\s*(?:(?:that|which)\s+)?(?:was|were|is|are|has|have)?\s*'
                                 r'(?:not|never|n[\'’]t)\b.{0,15}(?:used|present|included)|^.{0,8}(?:未用|未使用|没有)', after, re.I))
        statuses.append(not negated)
    return statuses


def fragments(paper, graph=None, fixed_scope='', *, title_limit=80, abstract_limit=180):
    """Choose continuous public excerpts within the existing 80/180 limits.

    Selection is local lexical retrieval, never a relevance or evidence verdict.
    Offsets preserve provenance; no text is rewritten or concatenated.
    """
    terms = [str(t) for c in (graph or {}).get('concepts', [])
             for t in [c.get('name') or '', *(c.get('terms') or [])]]
    scope = canon(fixed_scope + ' ' + ' '.join(terms))
    patterns = []
    if 'nsclc' in scope or 'nonsmallcelllungcancer' in scope or '非小细胞肺癌' in scope:
        patterns.append(r'NSCLC|non[- ]small[- ]cell lung cancer|非小细胞肺癌')
    if 'pd1' in scope or 'pdl1' in scope:
        patterns.append(r'PD[- ]?1|PD[- ]?L1|PD[- ]?\(L\)1')
    if 'lithiummetal' in scope or '锂金属' in scope:
        patterns.append(r'lithium metal|Li metal|lithium anode|锂金属|锂负极')
    if 'sulfide' in scope or '硫化物' in scope:
        patterns.append(r'sulfide|硫化物')
    anchors = [(re.compile(p, re.I), 5) for p in patterns]
    anchors += [(re.compile(re.escape(t), re.I), 3) for t in terms if len(t) >= 4]
    anchors += [(re.compile(r'resistan\w*|interfac\w*|interphas\w*|dendrit\w*|decompos\w*|reaction\w*|failure\w*', re.I), 2)]
    anchors += [(re.compile(r'patient|cohort|in vitro|mice|mouse|measur\w*|observ\w*|characteriz\w*', re.I), 1)]
    anchors += task_relations.evidence_patterns(graph)

    def select(text, limit):
        from itertools import islice
        # Optional public-metadata retrieval is bounded independently of wire.
        text = text[:20000]
        parts, cursor = [], 0
        capped = False
        for i, split in enumerate(islice(PARAGRAPH.finditer(text), 128)):
            parts.append((cursor, split.start())); cursor = split.end()
            if i == 127:
                capped = True
        if not capped:
            parts.append((cursor, len(text)))
        candidates = []
        for low, high in parts:
            part = text[low:high]
            if not part.strip():
                continue
            starts = {0, max(0, len(part) - limit)}
            # Complete sentence starts preserve the relationship being retrieved,
            # rather than selecting an isolated late occurrence of a topic word.
            sentence_starts = {0, *(m.end() for m in islice(re.finditer(r'[.!?。！？][ \t\r\n]+', part), 128))}
            starts.update(sentence_starts)
            for pattern, _ in anchors:
                for match in islice(pattern.finditer(part), 40):
                    starts.update((max(0, match.start() - limit // 4), max(0, match.end() - limit)))
            for start in starts:
                if start and part[start-1:start+1].isalnum():
                    while start < len(part) and part[start].isalnum():
                        start += 1
                    while start < len(part) and part[start].isspace():
                        start += 1
                end = min(len(part), start + limit)
                if end < len(part) and part[end-1:end+1].isalnum():
                    while end > start and part[end-1].isalnum():
                        end -= 1
                piece = part[start:end].rstrip()
                score = sum(weight for pattern, weight in anchors if pattern.search(piece))
                score += task_relations.window_score(piece, graph, sentences)
                if start in sentence_starts:
                    score += 4
                candidates.append((score, -(low+start), piece, low+start))
        if not candidates:
            return '', 0
        _, _, piece, start = max(candidates)
        return piece, start

    if not (1 <= title_limit <= 200 and 1 <= abstract_limit <= 480):
        raise ValueError('Public excerpt limits exceed the bounded contract')
    title, title_start = select(str(paper.get('title') or ''), title_limit)
    abstract, abstract_start = select(str(paper.get('abstract') or ''), abstract_limit)
    return {'title': title, 'abstract': abstract, 'title_start': title_start, 'abstract_start': abstract_start}


def visible(paper, graph=None, fixed_scope=''):
    selected = fragments(paper, graph, fixed_scope)
    return [selected['title'], selected['abstract']]


def canon(text):
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', str(text).lower())


def clinical_context_conflict(contexts):
    """Finite same-study exclusions, not a blanket animal-background veto."""
    for text in contexts:
        for sentence in sentences(text):
            # The subject/predicate of a current-result declaration wins over
            # a later background citation, e.g. "All findings are simulations,
            # informed by prior clinical studies". Mere mentions of mice in a
            # current comparative study do not satisfy this predicate.
            if re.search(r'\b(?:all(?:\s+(?:the|reported|our))?\s+(?:findings|results|data|experiments)|'
                         r'(?:this|our|current)\s+study)\s+'
                         r'(?:(?:is|are|was|were|uses?|used|consists?|consisted)\s+)?'
                         r'(?:(?:only|exclusively|entirely|solely)\s+)?'
                         r'(?:(?:performed|conducted|carried out|based)\s+(?:in|on)\s+)?'
                         r'(?:simulat\w*|in vitro|mice|mouse|murine|animal[- ]only)\b|'
                         r'(?:本研究|全部结果|所有结果).{0,25}(?:模拟|体外|小鼠|动物)', sentence, re.I):
                return True
            if re.search(r'\b(?:separate|other|previous|prior|background|mouse arm|animal arm)\b|'
                         r'另一|既往|背景|动物组', sentence, re.I):
                continue
            if re.search(r'\b(?:only|exclusively)\b.{0,40}(?:simulat\w*|in vitro|mice|mouse|animal)\b|'
                         r'^\s*(?:no human (?:patients|participants|subjects)|'
                         r'no (?:patients|participants|subjects))\s+(?:were |are )?(?:enrolled|included)|'
                         r'(?:本研究|全部结果|所有结果).{0,25}(?:模拟|体外|小鼠|动物)|无人类受试者', sentence, re.I):
                return True
    return False


def current_basic_context(text, marker):
    """A background cue must precede the animal marker in its own clause."""
    for clause in re.split(r'[;,]|\b(?:compared with|informed by|but|however|while|whereas)\b', text, flags=re.I):
        for match in re.finditer(marker, clause, re.I):
            if not re.search(r'\b(?:separate|other|previous|prior|background|mouse arm|animal arm)\b|'
                             r'另一|既往|背景|动物组', clause[:match.start()], re.I):
                return True
    return False


def type_supported(kind, quote, adjacent=None, contexts=()):
    """A type needs quoted markers; actually sent adjacency can contradict it."""
    if kind not in TYPES:
        return False
    markers = {
        'basic': r'in vitro|cell.line|mouse|mice|murine|xenograft|体外|小鼠|动物实验',
        'observational': r'patient|cohort|human|患者|队列|人群',
        'trial': r'randomi[sz]|clinical trial|phase (?:[1-3]|i{1,3}|iv)\b|随机|临床试验',
        'review': r'review|meta.analysis|综述|系统评价'}
    context = adjacent or quote
    if kind in ('trial', 'observational') and current_basic_context(context, markers['basic']):
        return False
    if kind == 'trial' and re.search(r'\b(?:no|not|never|without)\b.{0,30}(?:clinical trial|randomi[sz]|phase [123iv])|'
                                    r'(?:clinical trial|randomized trial|phase (?:[1-3]|i{1,3}|iv)\b).{0,25}'
                                    r'(?:\bnot\b|n[\'’]t\b|\bnever\b).{0,25}(?:conduct|perform|enroll|exist|start)|'
                                    r'无临床试验|未.{0,8}临床试验', context, re.I):
        return False
    if kind in ('trial', 'observational') and clinical_context_conflict(contexts or [context]):
        return False
    return kind == 'unknown' or bool(re.search(markers[kind], quote, re.I))


def clinical_benefit_supported(citations):
    """A trial label alone cannot establish a claimed treatment benefit."""
    return bool(citations) and all(c['type'] == 'trial' and re.search(
        r'(?:improv\w*|prolong\w*|increas\w*|benefit\w*).{0,35}(?:survival|clinical outcomes?)|'
        r'(?:survival|clinical outcomes?).{0,35}(?:improv\w*|prolong\w*|increas\w*|benefit\w*)|'
        r'延长.{0,10}生存|提高.{0,10}生存|临床获益', c['quote'], re.I)
        and not re.search(r'(?:\b(?:no|not|never|without)\b|n[\'’]t\b|\bfailed? to\b).{0,35}(?:improv|benefit|prolong|increas)|'
                          r'(?:improv\w*.{0,15}survival|clinical benefit|prolong\w*.{0,15}survival).{0,35}'
                          r'(?:(?:not|never|n[\'’]t).{0,12}(?:observ|found|confirm|detect|achiev|demonstrat|occur|present)|absent)|'
                          r'\b(?:may|could|might|potential|hypothes\w*|aim\w*|expect\w*)\b.{0,40}(?:improv|benefit|prolong|increas)|'
                          r'未.{0,10}(?:获益|延长|提高)', c.get('adjacent_context') or c['quote'], re.I)
        for c in citations)


def source_evidence(value, refs, batch, graph=None, fixed_scope='', *, sent_papers=None):
    """Return citations only if each literal quote and declared object is visible."""
    if not isinstance(value, list) or len(value) > 3:
        return None
    by_ref = {f'p{i+1}': paper for i, paper in enumerate(batch)}
    found = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {'paper', 'quote', 'object', 'treatment', 'type'}:
            return None
        ref = item['paper']
        if not isinstance(ref, str) or ref not in refs or ref in found:
            return None
        if any(not isinstance(item[k], str) or len(item[k]) > cap for k, cap in [('quote', 160), ('object', 40), ('treatment', 40)]):
            return None
        quote = item['quote']
        selected = dict(fragments(by_ref[ref], graph, fixed_scope))
        if sent_papers is not None:
            sent = sent_papers.get(ref)
            if not isinstance(sent, dict):
                return None
            for field, limit in [('title', 200), ('abstract', 480)]:
                fragment = sent.get(field)
                original = str(by_ref[ref].get(field) or '')[:20000]
                if (not isinstance(fragment, str) or len(fragment) > limit or PARAGRAPH.search(fragment)
                        or fragment not in original):
                    return None
                selected[field] = fragment
                selected[field + '_start'] = original.index(fragment)
        if (len(quote.strip()) < 8 or PARAGRAPH.search(quote) or not any(quote in selected[field] for field in ('title', 'abstract'))
                or not item['object'].strip() or item['object'] not in quote
                or item['treatment'] not in quote or not isinstance(item['type'], str) or item['type'] not in TYPES):
            return None
        text = quote.lower()
        markers = {
            'basic': r'in vitro|cell.line|mouse|mice|murine|xenograft|体外|小鼠|动物实验',
            'observational': r'patient|cohort|human|患者|队列|人群',
            'trial': r'randomi[sz]|clinical trial|phase [123iv]|随机|临床试验',
            'review': r'review|meta.analysis|综述|系统评价'}
        if item['type'] in ('trial', 'observational') and re.search(markers['basic'], text):
            return None
        if item['type'] == 'trial' and re.search(r'\b(?:no|not|never|without)\b.{0,30}(?:clinical trial|randomi[sz]|phase [123iv])|无临床试验|未.{0,8}临床试验', text):
            return None
        if item['type'] != 'unknown' and not re.search(markers[item['type']], text):
            return None
        field = next(k for k in ('title', 'abstract') if quote in selected[k])
        start = selected[field + '_start'] + selected[field].index(quote)
        found[ref] = {**item, 'field': field, 'start': start, 'end': start + len(quote)}
        # Scope may be stated elsewhere in the same actually sent public field.
        # Preserve each literal sentence independently; never join it into a new
        # quotation or infer that adjacent text proves the task relationship.
        found[ref]['visible_scope'] = [{
            'field': field_name, 'quote': sentence.strip(),
            'start': selected[field_name + '_start'] + selected[field_name].index(sentence.strip()),
            'end': selected[field_name + '_start'] + selected[field_name].index(sentence.strip()) + len(sentence.strip())}
            for field_name in ('title', 'abstract') for sentence in sentences(selected[field_name])
            if 8 <= len(sentence.strip()) <= 480 and sentence.strip() in selected[field_name]]
    return list(found.values()) if set(found) == set(refs) else None


def scope_check(citations, graph, nearest=None, fixed_scope=''):
    """Distinguish contrary objects from absent scope evidence, never infer absence."""
    scope_source = fixed_scope + ' ' + ' '.join(str(c.get('name') or '') + ' ' + ' '.join(c.get('terms') or []) for c in graph['concepts'])
    scope = canon(scope_source)
    pd_scope = 'pd1' in scope or 'pdl1' in scope
    for citation in citations:
        text = canon(citation['quote'])
        primary = citation.get('adjacent_context') or citation['quote']
        primary_text = canon(primary)
        context = [citation['quote'], *(entry['quote'] for entry in citation.get('visible_scope', []))]
        if pd_scope and not any(t in primary_text for t in ('pd1', 'pdl1')) and re.search(
                r'platinum.{0,20}resistan|resistan.{0,20}platinum|KRAS.{0,20}inhibitor|铂.{0,5}耐药', primary, re.I):
            return {'status': 'explicit_scope_conflict', 'reason': 'different_treatment'}
        sulfide_electrolyte_scope = bool(SULFIDE_ELECTROLYTE.search(scope_source))
        if sulfide_electrolyte_scope:
            identities = sulfide_context(primary)
            if identities and not any(identities):
                return {'status': 'explicit_scope_conflict', 'reason': 'negated_electrolyte_identity'}
            if not any(any(sulfide_context(sentence)) for sentence in context):
                return {'status': 'missing_scope_evidence', 'reason': 'unidentified_electrolyte'}
        # A contrary object in the main quote cannot be repaired by another
        # sentence naming the intended target (for example a cross-cancer study).
        if re.search(r'melanoma|breast cancer|colorectal|hepatocellular|黑色素瘤|乳腺癌', primary, re.I) and (
                ('nsclc' in scope or 'nonsmallcelllungcancer' in scope or '非小细胞肺癌' in scope)
                and not any(d in primary_text for d in ('nsclc', 'nonsmallcelllungcancer', '非小细胞肺癌'))):
            return {'status': 'explicit_scope_conflict', 'reason': 'different_object'}
        scoped = next((s for s in context if (not pd_scope or any(t in canon(s) for t in ('pd1', 'pdl1')))
                       and (not any(d in scope for d in ('nsclc', 'nonsmallcelllungcancer', '非小细胞肺癌'))
                            or any(d in canon(s) for d in ('nsclc', 'nonsmallcelllungcancer', '非小细胞肺癌')))), None)
        scope_text = canon(scoped) if scoped else text
        if pd_scope and not ('pd1' in scope_text or 'pdl1' in scope_text):
            return {'status': 'missing_scope_evidence', 'reason': 'missing_treatment'}
        # KRAS/platinum alone cannot establish PD-(L)1 relevance, but neither
        # word vetoes an explicit PD-(L)1 mechanism in the same cited evidence.
        if ('nsclc' in scope or 'nonsmallcelllungcancer' in scope or '非小细胞肺癌' in scope):
            if not any(disease in scope_text for disease in ('nsclc', 'nonsmallcelllungcancer', '非小细胞肺癌')):
                other = re.search(r'melanoma|breast cancer|colorectal|hepatocellular|黑色素瘤|乳腺癌', citation['quote'], re.I)
                return {'status': 'explicit_scope_conflict' if other else 'missing_scope_evidence', 'reason': 'different_or_missing_object'}
            if pd_scope and not any(
                    any(d in canon(sentence) for d in ('nsclc', 'nonsmallcelllungcancer', '非小细胞肺癌'))
                    and any(t in canon(sentence) for t in ('pd1', 'pdl1'))
                    for sentence in sentences(scoped or citation['quote'])):
                return {'status': 'missing_scope_evidence', 'reason': 'missing_same_sentence_scope'}
        if nearest:
            node = next((c for c in graph['concepts'] if c.get('name') == nearest), None)
            if node:
                expected = canon(node['name'] + ' ' + ' '.join(node.get('terms', [])))
                if (('interface' in expected or 'interphase' in expected or '界面' in expected)
                        and not any(k in text for k in ('interface', 'interfacial', 'interphase', 'electrode', '界面', '电极'))):
                    return {'status': 'missing_scope_evidence', 'reason': 'missing_interface'}
                cathode = lambda s: 'cathode' in s or '正极' in s
                anode = lambda s: 'anode' in s or '负极' in s or 'lithiummetal' in s or '锂金属' in s
                if ((cathode(primary_text) and anode(expected) and not cathode(expected))
                        or (anode(primary_text) and cathode(expected) and not anode(expected))):
                    return {'status': 'explicit_scope_conflict', 'reason': 'different_electrode'}
                if ('lithiummetal' in expected and 'liquidlithium' in primary_text
                        and not any(t in primary_text for t in ('lithiummetal', 'limetal'))):
                    return {'status': 'explicit_scope_conflict', 'reason': 'liquid_not_metal_interface'}
    return {'status': 'supported_scope', 'reason': None}


def task_support(citations, graph, nearest):
    node = next((c for c in graph['concepts'] if c.get('name') == nearest), None)
    if node is None:
        return {'status': 'missing_task_relation', 'role': 'uncertain'}
    checks = [task_relations.check(node, c['quote'], split=sentences, term_match=term_match) for c in citations]
    for index, citation in enumerate(citations):
        if task_relations.contradicted(node, citation['quote'], citation.get('adjacent_context') or citation['quote'], sentences):
            checks[index] = {'status': 'contradicted_task_relation', 'role': 'uncertain'}
    return next((item for item in checks if not item['status'].startswith('supported_')), checks[0]) if checks else {
        'status': 'missing_task_relation', 'role': 'uncertain'}


def scope_conflict(citations, graph, nearest=None, fixed_scope=''):
    """Compatibility wrapper; callers can inspect the separate reason/status."""
    return (scope_check(citations, graph, nearest, fixed_scope)['status'] != 'supported_scope'
            or bool(nearest and not task_support(citations, graph, nearest)['status'].startswith('supported_')))


def sentences(quote):
    return [sentence for paragraph in PARAGRAPH.split(quote)
            for sentence in re.split(r'(?<!\d)[.!?;](?!\d)|[。！？；]', paragraph)]


def term_match(term, quote):
    words = re.findall(r'[a-z]+\d*', str(term).lower())
    aliases = {'lithium': r'\b(?:lithium|li)\b',
               'interface': r'\b(?:interfaces?|interfacial)\b',
               'interfacial': r'\b(?:interfaces?|interfacial)\b'}
    patterns = [aliases.get(word, r'\b' + re.escape(word) + r's?\b') for word in words]
    for sentence in sentences(quote):
        if any(canon(term) in canon(sentence[start:start+80]) for start in range(max(1, len(sentence)))):
            return True
        if 2 <= len(words) <= 5:
            starts = {match.start() for pattern in patterns for match in re.finditer(pattern, sentence, re.I)}
            if any(all(re.search(pattern, sentence[start:start+80], re.I) for pattern in patterns) for start in starts):
                return True
    return False


def ordered_quote(quote, before, after):
    if (re.search(r'\b(?:not|no|never|optional|may|might|could|can|cannot|without|if|unless|unproven|unnecessary)\b|n[\'’]t\b|无需|不必|不需|不必要|可选|选修|建议|可考虑|未证明|仅相关|不是', quote, re.I)
            or not re.search(r'requir|prerequisite|must|必需|必要前置|必须', quote, re.I)):
        return False
    sentences = [part for part in re.split(r'[.!?;。！？；\n]', quote) if part.strip()]
    return any(_ordered_sentence(sentence, before, after) for sentence in sentences)


def _ordered_sentence(quote, before, after):
    text = canon(quote)
    positions = lambda terms: [text.find(canon(term)) for term in terms if len(canon(term)) >= 2 and canon(term) in text]
    for a in positions(before):
        for b in positions(after):
            for marker in ('before', 'prerequisitefor'):
                middle = text.find(marker)
                if a < middle < b:
                    return True
            for marker in ('requires', '需要先', '必须先'):
                middle = text.find(marker)
                if b < middle < a:
                    return True
            first, then = text.find('先'), text.find('再')
            if 0 <= first < a < then < b:
                return True
    return False


def necessity(value, required, graph, proposal, *, missing=False):
    """A hard relationship needs a literal necessity statement already visible."""
    if not required:
        return True
    if not isinstance(value, list) or len(value) > 6:
        return False
    aliases = {f'c{i+1}': c for i, c in enumerate(graph['concepts'])}
    proved = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {'node', 'quote'}:
            return False
        ref, quote = item['node'], item['quote']
        if not isinstance(ref, str) or ref not in aliases or not isinstance(quote, str) or not 8 <= len(quote) <= 80:
            return False
        if quote not in str(aliases[ref].get('intro') or '') or not ORDER.search(quote):
            return False
        node_terms = [aliases[ref]['name'], *aliases[ref].get('terms', [])]
        new_terms = [proposal['name'], *proposal.get('terms', [])]
        if not ordered_quote(quote, new_terms if missing else node_terms, node_terms if missing else new_terms):
            return False
        proved.add(aliases[ref]['id'])
    return set(required) <= proved


def brief_quote(quote, brief):
    # The goal alone does not establish a prerequisite. Preserve uncertain
    # proposed relations as optional; user-authored/manual graph edits are separate.
    return (isinstance(quote, str) and 8 <= len(quote) <= 80 and bool(ORDER.search(quote))
            and any(quote in str((brief or {}).get(k) or '') for k in ('known', 'structure')))
