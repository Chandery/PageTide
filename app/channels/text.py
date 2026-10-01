"""Script-aware text helpers: CJK runs, width folding, title keys, language.

Text without CJK or full-width characters passes through unchanged, so English
tokens and title keys stay byte-identical to the pre-CJK behaviour.
"""
import re
import unicodedata

HAN = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff"
KANA = "\u3040-\u30ff\u31f0-\u31ff"
HANGUL = "\u1100-\u11ff\u3130-\u318f\uac00-\ud7af"
CJK = HAN + KANA + HANGUL

_CJK_CHAR = re.compile(f"[{CJK}]")
_CJK_RUN = re.compile(f"[{CJK}]+")
_COMPAT_HAN = re.compile("[\uf900-\ufaff]")
_FULLWIDTH = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
_FULLWIDTH[0x3000] = 0x20

# Particles that end a run; bigrams across them are noise.
RUN_BREAKS = "的了"
# Chinese counterparts of the English STOPWORDS: frame words of abstracts.
CJK_STOPWORDS = {
    "本文", "基于", "一种", "研究", "进行", "通过", "以及", "对于", "作为", "可以", "我们",
    "结果", "提出", "方法", "分析", "主要", "相关", "其中", "这些", "这种", "具有",
}


def fold(text):
    """Map full-width ASCII and the ideographic space to ASCII, compatibility ideographs to unified ones."""
    text = (text or "").translate(_FULLWIDTH)
    return _COMPAT_HAN.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)


def has_cjk(text):
    return bool(_CJK_CHAR.search(text or ""))


def cjk_tokens(text):
    """Character bigrams of each CJK run; runs of one character give nothing."""
    tokens = []
    for run in _CJK_RUN.findall(fold(text)):
        for part in re.split(f"[{RUN_BREAKS}]", run):
            tokens.extend(b for b in (part[i:i + 2] for i in range(len(part) - 1)) if b not in CJK_STOPWORDS)
    return tokens


# Phrase splitting for user-editable keywords, not for ranking: no dictionary,
# so phrases are cut at punctuation and common connectives and then trimmed.
PHRASE_BREAKS = "的了和与及或"
FRAME_PREFIXES = ("我想", "我要", "想要", "希望", "关于", "有关", "了解", "重点", "关注", "偏向", "侧重")


def cjk_phrases(text, max_len=16):
    """CJK phrases of 2..max_len characters, frame words stripped from the front."""
    phrases = []
    for run in _CJK_RUN.findall(fold(text)):
        for part in re.split(f"[{PHRASE_BREAKS}]", run):
            stripped = True
            while stripped:
                stripped = False
                for prefix in FRAME_PREFIXES + tuple(CJK_STOPWORDS):
                    if part.startswith(prefix) and len(part) > len(prefix):
                        part, stripped = part[len(prefix):], True
            if 2 <= len(part) <= max_len and part not in CJK_STOPWORDS and part not in phrases:
                phrases.append(part)
    return phrases


def normalize_title(text):
    """Lowercase, punctuation to spaces; CJK kept, and spacing next to CJK ignored."""
    text = fold(text).lower()
    text = re.sub(f"[^a-z0-9{CJK}]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(f"(?<=[{CJK}]) | (?=[{CJK}])", "", text)


def detect_language(text):
    """Script-based guess: zh, ja, ko, en (any Latin script) or und."""
    text = text or ""
    if re.search(f"[{KANA}]", text):
        return "ja"
    if re.search(f"[{HANGUL}]", text):
        return "ko"
    if re.search(f"[{HAN}]", text):
        return "zh"
    if re.search(r"[A-Za-z]", fold(text)):
        return "en"
    return "und"
