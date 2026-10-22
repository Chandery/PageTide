"""Explicit project paper-language policy, independent of interface language.

The initial editor offers a bounded set of languages, including classical-language
research. Metadata is a report, never evidence of the PDF's actual language.
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
    if discipline not in ('stem', 'humanities'):
        raise ValueError('请选择理工科或文科')
    if not isinstance(allowed, list) or not allowed or len(allowed) > len(LANGUAGES):
        raise ValueError('请至少选择一种允许的论文语言')
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
    import json
    return {'discipline': row['discipline'],
            'allowed_languages': json.loads(row['allowed_languages'] or '[]'),
            'revision': row['language_policy_revision'],
            'status': 'ready' if row['discipline'] and row['language_policy_revision'] > 0 else 'pending'}
