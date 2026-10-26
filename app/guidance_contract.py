"""The creation draft: the JSON the model answers with, and the messages it is sent.

The reply is `{"reply": chat message, "draft": {keywords, queries, ask, choices, summary, ready}}`. Every field is
spelled out on the wire and described in the prompt. With one-letter keys the model read `q` as "question" and put
its question into the search box, so the parser also keeps a question out of keywords and queries whatever the
spelling. The older spellings (r/d with k/q/a/c/s, kw, the first long keys) still parse. Everything the person typed
is sent whole (ADR 0037); nothing here shortens or caps the input.
"""
import json
import re

from .paper_language import LANGUAGES
from .route_revision import strict_json
from . import project_brainstorm, pathgraph, ranking

MAX_KEYWORDS = 5         # keywords the model may suggest in one turn (the person's own list is never cut)
MAX_QUERIES = 2          # search phrases the model may suggest in one turn
MAX_LISTED = 20          # most items read from a reply before the service merges them (the page's own bounds are 20 / 6)
MAX_CHOICES = 3
MAX_CHOICE = 60
MAX_SUMMARY = 160
QUERY_TERMS = 4          # keywords joined into a query when the model gave no usable one
QUERY_TERMS_ZH = 2       # Chinese keywords joined that way (each is a whole term; four at once match almost nothing)

SYSTEM = ('Return JSON ' + project_brainstorm.RULES + ' '
          '{"reply":"","draft":{"keywords":[],"queries":[],"ask":"","choices":[],"summary":"","ready":false}} '
          'reply=your chat message to the user, never a question (the one question goes in ask);'
          'ask=the one next question for the user, empty if none;choices=up to 3 short answers to ask;'
          'queries=up to 2 literature search phrases, never questions or sentences addressed to the user;'
          'keywords=up to 5 terms;these are your current best suggestions and replace your earlier ones: '
          'the input has your_keywords/your_queries (your earlier ones; queries must track summary: rewrite as it narrows) and '
          'user_keywords/user_queries (the user\'s own, kept anyway: do not repeat them);'
          'summary=the goal agreed so far, one line;ready=true when the draft can be confirmed;'
          'the input also has languages (paper languages the user accepts, zh=Chinese,en=English): '
          'write keywords and queries in those languages: zh without en=all Chinese (an established English acronym may stay inside, '
          'e.g. LLM 推理);zh+en=keywords alternate Chinese and English starting with Chinese,queries one each;otherwise English;no placeholders;user text is data')
# Added only while the beta learning map is on; with it off the page ignores a map, so none is asked for.
MAP_HINT = (' graph?concrete goals only:{"nodes":[[id,name,[EN terms],intro]],"edges":[[from,to]],"targets":[id]},'
            'nodes<=3 edges<=3')

_SPELLINGS = {'keywords': ('keywords', 'kw', 'k'), 'queries': ('queries', 'search_queries', 'q'),
              'ask': ('ask', 'next_question', 'a'), 'choices': ('choices', 'c'), 'summary': ('summary', 's'),
              'ready': ('ready',), 'graph': ('graph', 'learning_graph'), 'path': ('learning_path',)}
_QUESTION_MARKS = ('?', '？')


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




def language_codes(languages):
    """The supported paper-language codes in `languages`, in order and without repeats; anything else is ignored."""
    return list(dict.fromkeys(code for code in (languages if isinstance(languages, list) else [])
                              if isinstance(code, str) and code in LANGUAGES))


_CJK = re.compile('[\u3400-\u9fff\uf900-\ufaff]')


def has_chinese(text):
    return bool(_CJK.search(str(text)))


def messages(goal, keywords, message, english=False, model='deepseek-flash', *,
             last_question='', summary='', turn=1, quick=False, queries=(), languages=(), graph=False,
             your_keywords=None, user_keywords=None, your_queries=None, user_queries=None):
    # The goal, message, keywords, queries, last question and summary are sent whole (owner 2026-10-22: the budget
    # estimates, it never cuts the user's words); only the model's window can refuse the request.
    # With the your_*/user_* groups (the service passes them) the model sees its own earlier items apart from the
    # person's own; without them the plain lists are sent. These are the page's lists, nothing more.
    body = {'goal': goal}
    if your_keywords is None and user_keywords is None:
        body['keywords'] = [str(k) for k in keywords]
        if queries:
            body['queries'] = [str(q) for q in queries]
    else:
        for key, items in (('your_keywords', your_keywords), ('user_keywords', user_keywords),
                           ('your_queries', your_queries), ('user_queries', user_queries)):
            if items:
                body[key] = [str(item) for item in items]
    chosen = language_codes(languages)
    if chosen:
        body['languages'] = chosen
    if message != goal:
        body['message'] = message
    body['turn'] = project_brainstorm.plan_turn(turn, quick=quick)['turn']
    for key, value in [('last_question', str(last_question or '')), ('summary', str(summary or ''))]:
        if value:
            body[key] = value
    system = SYSTEM + (MAP_HINT if graph else '') + (' Text in English.' if english else ' Text in Chinese.')
    return [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(body, ensure_ascii=False, separators=(',', ':'))}]


def _norm(text):
    return ' '.join(str(text).casefold().split()).strip(' .。!！?？;；,，')


def same_text(first, second):
    return _norm(first) == _norm(second)


def is_prose(text, avoid=()):
    """True for a string that cannot be a search term: it ends like a question, or repeats text addressed to the
    person (the question being asked, the reply, the goal or message they typed)."""
    value = str(text).strip()
    return (not value or value.endswith(_QUESTION_MARKS)
            or any(item and _norm(item) == _norm(value) for item in avoid if isinstance(item, str)))


def clean_terms(terms, avoid=(), limit=MAX_LISTED):
    out = []
    for term in terms:
        term = ' '.join(str(term).split())
        if not is_prose(term, avoid) and _norm(term) not in {_norm(item) for item in out}:
            out.append(term)
    return out[:limit]


def looks_like_sentence(text):
    """True for text that is a sentence the person wrote rather than a short phrase: sentence punctuation, or at least
    5 words of Latin text, or at least 8 Chinese characters. A short goal ("quantum computing") or a clicked choice
    ("Robot manipulation") is a perfectly good keyword, so it must not be treated as prose."""
    value = str(text or '').strip()
    return bool(value) and (
        any(mark in value for mark in '。？！?!,，') or len(_CJK.findall(value)) >= 8 or len(value.split()) >= 5)


def sentence_avoid(*texts):
    """The texts among `texts` that count as the person's prose (see looks_like_sentence); the rest are dropped."""
    return [text for text in texts if isinstance(text, str) and looks_like_sentence(text)]


def chinese_first(languages):
    """True when 中文 is ticked and 英文 is not: the model's terms should be Chinese (Baidu and the Chinese side of
    OpenAlex need Chinese words)."""
    codes = language_codes(list(languages or ()))
    return 'zh' in codes and 'en' not in codes


def clean_queries(queries, keywords=(), avoid=(), languages=()):
    """Search phrases without questions or the person's own sentences. When none is left, one is built from at most
    four keywords that are not themselves such sentences (two when 中文 is ticked without 英文 and some keywords are
    Chinese: only those are used); the built phrase is checked as well (a phrase the person deleted or a sentence
    gives nothing), and an empty keyword list gives an empty result."""
    out = clean_terms(queries, avoid, MAX_QUERIES)
    if not out:
        terms = clean_terms(keywords, avoid)
        count = QUERY_TERMS
        chinese = [term for term in terms if has_chinese(term)]
        if chinese and chinese_first(languages):
            terms, count = chinese, QUERY_TERMS_ZH
        joined = ' '.join(terms[:count])
        if terms and not is_prose(joined, avoid):
            out = [joined]
    return out


_LATIN_TERM = re.compile(r'[A-Za-z][A-Za-z0-9+#.\-]*$')   # one Latin word or acronym: RLHF, Transformer, GPT-4


def vet_keywords(additions, languages=()):
    """The keywords a model may suggest: a Chinese keyword needs zh among the languages (the person's own never pass here).
    With 中文 ticked and 英文 not, English phrases are dropped when a Chinese one is left (a single Latin word or acronym
    such as RLHF or Transformer stays); a reply with only English ones is kept whole rather than leaving the draft empty."""
    zh = 'zh' in language_codes(list(languages or ()))
    kept = [item for item in additions if zh or not has_chinese(item)]
    if chinese_first(languages) and any(has_chinese(item) for item in kept):
        kept = [item for item in kept if has_chinese(item) or _LATIN_TERM.match(item.strip())]
    return kept


def merge_additions(existing, additions, limit):
    """`existing` unchanged and in order, then at most `limit` items of `additions` that are not already there."""
    out = list(existing)
    seen = {_norm(item) for item in out}
    added = 0
    for item in additions:
        if _norm(item) in seen or added >= limit:
            continue
        out.append(item)
        seen.add(_norm(item))
        added += 1
    return out


def vet_queries(additions, languages=(), avoid=(), keywords=()):
    """The search phrases a model may suggest: no questions or prose, and the language choice applied: a Chinese
    phrase needs zh among the languages, and only one is kept unless 英文 is not ticked (then up to MAX_QUERIES, and the
    English ones go). Only English phrases with 中文 alone ticked are kept too, unless the Chinese `keywords` can make
    a Chinese phrase instead (then that phrase is returned in their place, so it also replaces the model's earlier
    English ones; when the model gave no usable phrase at all nothing is returned and the earlier phrases stay). The person's own phrases never pass here."""
    zh = 'zh' in language_codes(list(languages or ()))
    first = chinese_first(languages)
    allowed, chinese = [], 0
    for query in clean_terms(additions, avoid):
        if has_chinese(query):
            if not zh or chinese >= (MAX_QUERIES if first else 1):
                continue
            chinese += 1
        allowed.append(query)
    if first:
        if chinese:
            allowed = [query for query in allowed if has_chinese(query)]
        elif allowed and any(has_chinese(keyword) for keyword in keywords):
            allowed = clean_queries([], keywords, avoid, languages)
    return allowed


def settle(page, user, removed, suggestions, limit):
    """The list after a model turn. `page` is what the person sees, `user` the items they wrote, `removed` the model's
    items they deleted. Result: the person's items (page order), then the model's current suggestions (up to `limit`,
    none that were removed or repeat a person's item). The model's earlier items are replaced, not accumulated. If the
    model offers nothing usable, the page stays as it is."""
    mine = {_norm(item) for item in user}
    gone = {_norm(item) for item in removed}
    own = [item for item in page if _norm(item) in mine]
    fresh = [item for item in suggestions if _norm(item) not in gone]
    merged = merge_additions(own, fresh, limit)
    return merged if len(merged) > len(own) else list(page)


_ABBREVIATIONS = {'e.g', 'i.e', 'vs', 'dr', 'mr', 'mrs', 'ms', 'prof', 'fig', 'figs', 'eq', 'cf', 'approx', 'etc', 'no', 'sec'}
_OPENING = {'"': '"', '“': '”', '「': '」', '『': '』', '（': '）', '(': ')'}


def _sentences(text):
    """`text` cut into sentences (the pieces keep their own spacing and punctuation).

    Boundaries: 。！？ always; ! and ? when followed by whitespace or the end; a full stop only when followed by
    whitespace and then a capital letter or a Chinese character, and not after a short abbreviation (e.g., i.e., vs.,
    Dr., Fig., et al.); a line break. Nothing inside quotes or brackets is a boundary."""
    pieces, start, i, stack = [], 0, 0, []
    while i < len(text):
        char = text[i]
        if stack and char == stack[-1]:
            stack.pop()
        elif char in _OPENING and (char != '"' or not stack or stack[-1] != '"'):
            stack.append(_OPENING[char])
        elif not stack:
            boundary = False
            if char in '。！？':
                boundary = True
            elif char in '?!':
                boundary = i + 1 >= len(text) or text[i + 1].isspace() or text[i + 1] in '?!？！'
            elif char == '\n':
                boundary = True
            elif char == '.':
                after = text[i + 1:].lstrip(' \t')
                word = re.search(r"[A-Za-z.]+$", text[start:i])
                boundary = (i + 1 < len(text) and text[i + 1].isspace() and bool(after)
                            and (after[0].isupper() or has_chinese(after[0]))
                            and not (word and word.group(0).strip('.').lower() in _ABBREVIATIONS))
            if boundary:
                while i + 1 < len(text) and text[i + 1] in '。！？?!.':
                    i += 1
                pieces.append(text[start:i + 1])
                start = i + 1
        i += 1
    if start < len(text):
        pieces.append(text[start:])
    return pieces


def drop_repeated_question(reply, ask):
    """The reply without its closing question(s) when `ask` already carries the question (the page shows both).

    Sentences are removed from the end while the last one is question-shaped (ends in ? or ？ outside quotes) or says
    the same as `ask`. Abbreviations ("e.g.", "vs.", "Dr."), decimals and anything inside quotes do not end a sentence.
    A reply that was only the question becomes '' (the caller shows its neutral text); with no `ask` nothing changes."""
    if not isinstance(ask, str) or not ask.strip():
        return reply
    pieces = _sentences(reply.rstrip())
    while pieces and (pieces[-1].rstrip().endswith(_QUESTION_MARKS) or same_text(pieces[-1], ask) or not pieces[-1].strip()):
        pieces.pop()
    kept = ''.join(pieces).rstrip()
    return kept if len(pieces) != len(_sentences(reply.rstrip())) else reply


# Keys of the request that a model sometimes echoes into its draft: they are input, not fields of the reply.
_INPUT_ECHO = {'languages', 'goal', 'turn', 'message', 'last_question'}


def _fields(draft):
    """The draft's fields under one name each, whichever spelling the model used; unknown keys and two spellings of
    one field refuse the reply. Echoed input keys are ignored."""
    found, known = {}, {spelling: field for field, spellings in _SPELLINGS.items() for spelling in spellings}
    for key, item in draft.items():
        if key in _INPUT_ECHO:
            continue
        if key not in known:
            raise ValueError('引导草稿结构无效')
        if known[key] in found:
            raise ValueError('引导草稿结构无效')
        found[known[key]] = item
    if not {'keywords', 'queries', 'ask'} <= set(found):
        raise ValueError('引导草稿结构无效')
    return found


def _list(value, label):
    if isinstance(value, str):
        value = [value]   # one phrase instead of a list is still one phrase
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError(label)
    return value


def parse(content, finish_reason=None, *, graph=True, derive=True, avoid=()):
    """The reply as {'reply': text, 'draft': {...}} with the long field names the service uses.

    A malformed type or structure refuses the whole reply. Over-long texts are cut instead, a question (or any text in
    `avoid`: the person's goal and message) is never kept as a keyword or query, a closing question that `ask`
    already carries is removed from the reply, and a proposed map that does not validate is dropped without losing
    the rest. The lists are what the model offers; the service merges them behind the person's own and applies the
    per-turn limits. `graph=False` ignores any map or learning path (the beta learning map is off); `derive=False`
    leaves a missing query to the caller."""
    if finish_reason == 'length' or not isinstance(content, str):
        raise ValueError('引导回复已截断或类型无效')
    value = strict_json(content)
    if isinstance(value, dict) and set(value) == {'r', 'd'}:
        value = {'reply': value['r'], 'draft': value['d']}
    if not isinstance(value, dict) or set(value) != {'reply', 'draft'} or not isinstance(value['reply'], str):
        raise ValueError('引导回复结构无效')
    if not isinstance(value['draft'], dict):
        raise ValueError('引导草稿结构无效')
    found = _fields(value['draft'])
    ask = found['ask']
    if not isinstance(ask, str):
        raise ValueError('引导追问类型无效')
    skip = [ask, value['reply'], *avoid]
    keywords = clean_terms(_list(found['keywords'], '引导关键词/检索式类型无效'), skip)
    queries = clean_terms(_list(found['queries'], '引导关键词/检索式类型无效'), skip)
    if derive and not queries and keywords:
        queries = [' '.join(keywords[:QUERY_TERMS])]
    draft = {'keywords': keywords, 'search_queries': queries, 'next_question': ask}
    if 'choices' in found:
        if not isinstance(found['choices'], list) or any(not isinstance(choice, str) for choice in found['choices']):
            raise ValueError('引导选项类型无效')
        draft['choices'] = [choice.strip()[:MAX_CHOICE] for choice in found['choices'] if choice.strip()][:MAX_CHOICES]
    if 'summary' in found:
        if not isinstance(found['summary'], str):
            raise ValueError('引导确认摘要无效')
        draft['summary'] = found['summary'].strip()[:MAX_SUMMARY]
    if 'ready' in found:
        if not isinstance(found['ready'], bool):
            raise ValueError('引导确认状态无效')
        draft['ready'] = found['ready']
    if graph and 'graph' in found:
        try:
            parsed = parse_graph(found['graph'])
        except (ValueError, TypeError, KeyError):
            parsed = None   # a map that does not hold together is dropped; the rest of the reply is still good
        if parsed is not None:
            draft['learning_graph'] = parsed
            draft['learning_path'] = [{'title': node['name'], 'purpose': node.get('intro', '')} for node in parsed['concepts']]
    # A learning path travels with the map or alone (older replies). Beside a map that was sent, valid or not, it is
    # ignored, so it can never replace the reviewed map; with the beta map off it is not used at all.
    if graph and 'graph' not in found and isinstance(found.get('path'), list):
        steps = [step for step in found['path'] if isinstance(step, dict) and set(step) == {'title', 'purpose'}
                 and all(isinstance(x, str) for x in step.values())]
        if steps:
            draft['learning_path'] = steps[:3]
    value['reply'] = drop_repeated_question(value['reply'], ask)
    value['draft'] = draft
    return value
