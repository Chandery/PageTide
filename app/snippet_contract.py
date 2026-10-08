"""Immutable references to literal, actually transmitted public excerpts.

This is a citation transport contract, not a scientific classifier. No source
outside the frozen title/abstract fields can repair a citation or task claim.
"""
import hashlib
import json
import re

from . import ai_evidence, task_relations

VERSION = 'public-snippet-ref-v2'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def sentence_ranges(text):
    """Bounded source ranges; ordinary abbreviations/formulas stay intact."""
    cursor = 0
    for match in re.finditer(r'[!?;。！？；]|\.(?=\s|$)', text):
        prefix = text[max(cursor, match.start()-14):match.start()]
        if match[0] == '.' and (re.search(r'\b(?:e\.g|i\.e|Fig|Dr|Mr|Ms|vs|etc|al)$', prefix, re.I)
                               or re.search(r'\b(?:[A-Z]\.)+[A-Z]$', prefix)):
            continue
        yield cursor, match.end()
        cursor = match.end()
    if cursor < len(text):
        yield cursor, len(text)


def options(selected, ref, graph, *, max_options=3):
    """At most three short candidates inside the same continuous sent fields."""
    if type(max_options) is not int or not 1 <= max_options <= 3:
        raise ValueError('A public paper needs one to three immutable snippet options')
    candidates = []
    words = [str(term) for node in graph.get('concepts', [])
             for term in [node.get('name') or '', *node.get('terms', [])] if len(str(term)) >= 3]
    for field in ('title', 'abstract'):
        text = selected[field]
        for low, high in sentence_ranges(text):
            starts = [low] if high-low <= 160 else [m.start() for m in re.finditer(r'\S+', text[low:high])][:80]
            if high-low > 160:
                starts = [low+s for s in starts]
            for start in starts:
                end = min(high, start+160)
                if end < high and text[end-1:end+1].isalnum():
                    while end > start and text[end-1].isalnum():
                        end -= 1
                while start < end and text[start].isspace():
                    start += 1
                while end > start and text[end-1].isspace():
                    end -= 1
                piece = text[start:end]
                if not 8 <= len(piece) <= 160 or ai_evidence.PARAGRAPH.search(piece):
                    continue
                score = task_relations.window_score(piece, graph, ai_evidence.sentences)
                score += sum(3 for term in words if term.lower() in piece.lower())
                if start == low or text[low:start].isspace():
                    score += 1
                candidates.append((score, -(selected[field+'_start']+start), field, start, end, piece))
    chosen = []
    for candidate in sorted(candidates, reverse=True):
        _, _, field, start, end, _ = candidate
        if sum(item[2] == field for item in chosen) >= (1 if field == 'title' else 2):
            continue
        if any(item[2] == field and max(0, min(end, item[4])-max(start, item[3]))
               >= .7 * min(end-start, item[4]-item[3]) for item in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == max_options:
            break
    table = {}
    counts = {'title': 0, 'abstract': 0}
    for _, _, field, start, end, piece in sorted(chosen, key=lambda item: (item[2], item[3])):
        counts[field] += 1
        sid = ref + ('.t' if field == 'title' else '.a') + str(counts[field])
        offset = selected[field+'_start']+start
        table[sid] = {'field': field, 'start': offset, 'end': offset+len(piece), 'text': piece}
    return table


def enabled(sent_papers):
    return bool(sent_papers) and all(isinstance(value, dict) and value.get('evidence_contract') == VERSION
                                    for value in sent_papers.values())


def evidence(value, refs, batch, sent_papers):
    """Return (literal citations or None, structural reference error or None)."""
    if value is None or value == {}:
        return None, None  # Lack of proof is uncertainty, never coverage.
    if not isinstance(value, dict) or len(value) > 3 or set(value) != set(refs):
        return None, 'invalid_evidence'
    if not enabled(sent_papers):
        return None, 'invalid_snippet_reference'
    by_ref = {f'p{i+1}': paper for i, paper in enumerate(batch)}
    found = {}
    for ref, item in value.items():
        if (not isinstance(item, dict) or set(item) != {'snippet', 'type'}
                or any(not isinstance(v, str) for v in item.values())):
            return None, 'invalid_evidence'
        sid = item['snippet']
        if ref not in refs or ref not in by_ref or ref in found:
            return None, 'invalid_evidence'
        if item['type'] not in ai_evidence.TYPES:
            return None, 'invalid_evidence'
        sent = sent_papers.get(ref)
        table = sent.get('snippets') if isinstance(sent, dict) else None
        if (not isinstance(table, dict) or sid not in table or not sid.startswith(ref+'.')
                or len(table) > 3):
            return None, 'invalid_snippet_reference'
        snippet = table[sid]
        if (not isinstance(snippet, dict) or set(snippet) != {'field', 'start', 'end', 'text'}
                or snippet['field'] not in ('title', 'abstract') or not isinstance(snippet['text'], str)
                or any(type(snippet[k]) is not int for k in ('start', 'end'))):
            return None, 'invalid_snippet_reference'
        field, start, end, quote = (snippet[k] for k in ('field', 'start', 'end', 'text'))
        original = str(by_ref[ref].get(field) or '')[:20000]
        continuous = sent.get(field)
        position = sent.get(field+'_start')
        if (not isinstance(continuous, str) or type(position) is not int or position < 0
                or len(continuous) > (200 if field == 'title' else 480)
                or original[position:position+len(continuous)] != continuous
                or not 8 <= len(quote) <= 160 or ai_evidence.PARAGRAPH.search(quote)
                or ai_evidence.PARAGRAPH.search(continuous) or start < position
                or end > position+len(continuous) or end-start != len(quote)
                or original[start:end] != quote or continuous[start-position:end-position] != quote):
            return None, 'invalid_snippet_reference'
        selected = {}
        for name, limit in [('title', 200), ('abstract', 480)]:
            text, offset = sent.get(name), sent.get(name+'_start')
            original_field = str(by_ref[ref].get(name) or '')[:20000]
            if (not isinstance(text, str) or type(offset) is not int or offset < 0 or len(text) > limit
                    or ai_evidence.PARAGRAPH.search(text) or original_field[offset:offset+len(text)] != text):
                return None, 'invalid_snippet_reference'
            selected[name] = (text, offset)
        local_start = start-position
        adjacent = next((continuous[low:high] for low, high in sentence_ranges(continuous)
                         if low <= local_start and end-position <= high), quote)
        if not ai_evidence.type_supported(item['type'], quote, adjacent,
                                          [text for text, offset in selected.values()]):
            return None, None
        contexts = [{'field': name, 'quote': text[low:high], 'start': offset+low, 'end': offset+high}
                    for name, (text, offset) in selected.items() for low, high in sentence_ranges(text)
                    if 8 <= high-low <= 480]
        found[ref] = {'paper': ref, 'quote': quote, 'object': '', 'treatment': '', 'type': item['type'],
                      'field': field, 'start': start, 'end': end, 'visible_scope': contexts,
                      'adjacent_context': adjacent, 'snippet_id': sid, 'evidence_contract': VERSION,
                      'snippet_snapshot_sha256': fingerprint(sent_papers)}
    if set(found) != set(refs):
        return None, 'invalid_evidence'
    return list(found.values()), None
