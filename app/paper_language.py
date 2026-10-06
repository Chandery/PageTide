"""Explicit project paper-language policy, independent of interface language.

The initial editor offers a bounded set of languages, including classical-language
research. Metadata is a report, never evidence of the PDF's actual language.
"""
LANGUAGES = {
    'en': '英文', 'zh': '中文', 'ja': '日文', 'ko': '韩文', 'fr': '法文',
    'de': '德文', 'es': '西班牙文', 'pt': '葡萄牙文', 'ru': '俄文',
    'ar': '阿拉伯文', 'it': '意大利文', 'el': '希腊文', 'la': '拉丁文',
}


def metadata_code(value):
    # Preserve other two-letter reports for display, although the initial editor
    # exposes only LANGUAGES. Missing/invalid reports remain unknown.
    return value.lower() if isinstance(value, str) and len(value) == 2 and value.isascii() and value.isalpha() else None


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
            'status': 'ready' if row['discipline'] else 'pending'}
