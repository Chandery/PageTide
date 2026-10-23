"""Explicit project paper-language policy, independent of interface language.

A project's policy is the list of languages it accepts. The editor offers Chinese and English as check boxes;
projects saved earlier with other languages keep them. Metadata is a report, never evidence of the PDF's actual
language.
"""
import re
import unicodedata


LANGUAGES = {
    'en': '英文', 'zh': '中文', 'ja': '日文', 'ko': '韩文', 'fr': '法文',
    'de': '德文', 'es': '西班牙文', 'pt': '葡萄牙文', 'ru': '俄文',
    'ar': '阿拉伯文', 'it': '意大利文', 'el': '希腊文', 'la': '拉丁文',
}


def metadata_code(value):
    # Preserve other two-letter reports for display, although the initial editor
    # exposes only LANGUAGES. Missing/invalid reports remain unknown.
    return value.lower() if isinstance(value, str) and len(value) == 2 and value.isascii() and value.isalpha() else None


_EN_FUNCTION_WORDS = frozenset('the of and to in a is for we that on with this by are an as from be our which it can'.split())


def abstract_language(abstract):
    """'en' when an abstract is clearly English, else None. Used only when the source reported no language: OpenAlex
    leaves it empty for most arXiv preprints. Conservative and local: at least 20 words, nearly all letters Latin, and
    English function words common enough that French, German or Spanish text does not pass."""
    text = abstract if isinstance(abstract, str) else ''
    words = [w.lower() for w in re.findall(r'[A-Za-z]+', text)]
    if len(words) < 20:
        return None
    letters = [c for c in text if c.isalpha()]
    latin = sum(1 for c in letters if c.isascii())
    if latin / len(letters) < 0.97:
        return None
    return 'en' if sum(w in _EN_FUNCTION_WORDS for w in words) / len(words) > 0.12 else None


_HAN = re.compile('[\u3400-\u9fff\uf900-\ufaff]')
_KANA_HANGUL = re.compile('[\u3040-\u30ff\u31f0-\u31ff\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]')


_SEPARATORS = re.compile(r'\||⸺|——|\s[-–]\s|\s:\s|[:：](?=\s*[A-Za-z])')


def _first_segment(title):
    """The part of a bilingual title before the first separator ('|', '⸺', '——', ' - ', ' – ', ' : ', or ':' / '：' followed
    by Latin text) whose remainder is mostly Latin letters; the whole title when there is none."""
    for match in _SEPARATORS.finditer(title):
        rest = [c for c in title[match.end():] if c.isalpha()]
        if rest and sum(1 for c in rest if c.isascii()) * 2 > len(rest):
            return title[:match.start()]
    return title


def chinese_text_language(title, abstract):
    """'zh' when a title and abstract are clearly Chinese, else None. Used only when the source reported no language (Baidu
    Scholar reports none): at least four Han characters in the title and a strict majority of its letters, no kana or hangul
    anywhere (that would be Japanese or Korean), and an abstract, when there is a real one, with at least ten Han characters
    making up a tenth or more of its letters (an English abstract with a few Chinese terms does not pass; a bilingual one does).
    The title test also accepts the first segment of a bilingual title ("中文题名 | English title", see _first_segment), so a
    long English translation does not hide a plainly Chinese title. Local and conservative; never stored back."""
    title = title if isinstance(title, str) else ''
    abstract = abstract if isinstance(abstract, str) else ''
    if _KANA_HANGUL.search(title) or _KANA_HANGUL.search(abstract):
        return None
    for candidate in (title, _first_segment(title)):
        han = len(_HAN.findall(candidate))
        letters = sum(1 for c in candidate if c.isalpha())
        if han >= 4 and han * 2 > letters:
            break
    else:
        return None
    if sum(1 for c in abstract if c.isalnum()) >= 10:
        abstract_han = len(_HAN.findall(abstract))
        if abstract_han < 10 or abstract_han * 10 < sum(1 for c in abstract if c.isalpha()):
            return None
    return 'zh'


def title_metadata_evidence(title, metadata_language):
    """Derive a script warning without rewriting source or body-language reports.

    Inspect the whole title so a bilingual suffix cannot be silently dropped.
    Non-Latin script is not a language detector: four alphabetic characters and
    a strict majority only flag a conflict with an English metadata report.
    Digits, punctuation, emoji and combining marks do not vote. Normalize each
    character for this derived count so mathematical/fullwidth Latin fonts
    remain Latin; the stored title is unchanged. Cost is one local linear scan,
    with no cache, retained title copy, model or external exposure.
    """
    alphabetic, non_latin = 0, 0
    for original in title if isinstance(title, str) else '':
        for char in unicodedata.normalize('NFKC', original):
            if char.isalpha():
                alphabetic += 1
                if 'LATIN' not in unicodedata.name(char, ''):
                    non_latin += 1
    majority = non_latin >= 4 and non_latin * 2 > alphabetic
    conflict = majority and metadata_code(metadata_language) == 'en'
    return {'title_metadata_conflict': conflict,
            'title_warning': 'title_metadata_conflict' if conflict else None,
            'title_evidence': {'source': 'title_script', 'alphabetic_chars': alphabetic,
                               'non_latin_chars': non_latin, 'non_latin_majority': majority}}


def validate_policy(discipline, allowed):
    """The allowed paper languages of a project: a policy is its language list.

    `discipline` is a legacy value (the old stem/humanities choice) that people are no longer asked for. None means
    only languages were chosen. A caller that still sends 'stem' keeps the old rule that it means English only."""
    if discipline not in (None, 'stem', 'humanities'):
        raise ValueError('论文语言设置格式无效')
    if not isinstance(allowed, list) or not allowed or len(allowed) > len(LANGUAGES):
        raise ValueError('请至少选择一种论文语言')
    if any(not isinstance(code, str) or code not in LANGUAGES for code in allowed):
        raise ValueError('论文语言不在支持的选项中')
    allowed = list(dict.fromkeys(allowed))
    if discipline == 'stem' and allowed != ['en']:
        raise ValueError('理工科项目只推荐英文论文')
    return allowed


def validate_value(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {'discipline', 'allowed_languages'}:
        raise ValueError('论文语言设置格式无效')
    return {'discipline': value.get('discipline'),
            'allowed_languages': validate_policy(value.get('discipline'), value.get('allowed_languages'))}


def policy_from_row(row):
    """Ready once languages were chosen (revision above zero). The legacy `discipline` column is reported as it
    is, but it never decides readiness: a database default such as 'cs_ai' is not a choice."""
    import json
    allowed = json.loads(row['allowed_languages'] or '[]')
    return {'discipline': row['discipline'],
            'allowed_languages': allowed,
            'revision': row['language_policy_revision'],
            'status': 'ready' if allowed and row['language_policy_revision'] > 0 else 'pending'}
