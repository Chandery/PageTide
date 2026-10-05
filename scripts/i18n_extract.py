#!/usr/bin/env python3
"""List the Chinese UI strings in app/static so every one has an English entry.

The UI keeps Chinese source text inline; app/static/i18n.js translates rendered
text by exact key or by a "{0}" pattern key. This extractor finds the same
pieces statically: JS string/template literals (comments skipped, "${...}"
becomes "{0}", "{1}"...) and HTML text/attribute values, split at tags and
trimmed. A piece that contains no CJK character is not a key.

    python3 scripts/i18n_extract.py            # print keys missing from en-US.json
    python3 scripts/i18n_extract.py --all      # print every key
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
PACK = STATIC / "i18n" / "en-US.json"
# Not UI text: figure-intent.js holds Chinese only inside question-matching regexes.
FILES = ["index.html", "settings.html", "project_creation.html", "weekly_report.html",
         "organization.js", "profile-ui.js", "project-switcher.js", "project-creation.js", "route-editor.js", "route.html", "route-page.js"]
CJK = re.compile(r"[㐀-鿿！-～　-〿]")
HAN = re.compile(r"[㐀-鿿]")
TAG = re.compile(r"<[^<>]*>")
ATTR = re.compile(r"""\b(?:title|placeholder|aria-label|alt|data-tip|content)\s*=\s*(["'])(.*?)\1""", re.S)
# An HTML element with this attribute is never translated (i18n.js skips it), so its text is no key.
NO_I18N = re.compile(r"<(\w+)\b[^<>]*\bdata-no-i18n\b[^<>]*>.*?</\1\s*>", re.S)


def _skip_regex_literal(src, i):
    """At a '/', return the index after a regex literal, or None if it is division."""
    j = i - 1
    while j >= 0 and src[j] in " \t":
        j -= 1
    prev = src[j] if j >= 0 else ""
    if prev and (prev.isalnum() or prev in "_$)]}\"'`"):
        return None
    k, in_class = i + 1, False
    while k < len(src):
        c = src[k]
        if c == "\\":
            k += 2
            continue
        if c == "\n":
            return None
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            return k + 1
        k += 1
    return None


def js_strings(src):
    """Yield (text, line) for every string or template literal; ${} -> {n}."""
    out = []

    def template(i):
        # src[i] is just after the opening backtick; returns (text, end_index)
        buf, n = [], 0
        while i < len(src):
            c = src[i]
            if c == "\\":
                buf.append(src[i:i + 2])
                i += 2
            elif c == "`":
                return "".join(buf), i + 1
            elif c == "$" and src[i + 1:i + 2] == "{":
                buf.append("{%d}" % n)
                n += 1
                i = code(i + 2, "}")
            else:
                buf.append(c)
                i += 1
        return "".join(buf), i

    def code(i, until=None):
        depth = 0
        while i < len(src):
            c = src[i]
            if until and c == until and depth == 0:
                return i + 1
            if c in "{([":
                depth += 1
            elif c in "})]":
                depth -= 1
            if src.startswith("//", i):
                i = src.find("\n", i)
                i = len(src) if i < 0 else i
                continue
            if src.startswith("/*", i):
                i = src.find("*/", i + 2)
                i = len(src) if i < 0 else i + 2
                continue
            if c == "/":
                end = _skip_regex_literal(src, i)
                if end:
                    i = end
                    continue
            if c in "'\"":
                j, buf = i + 1, []
                while j < len(src) and src[j] != c and src[j] != "\n":
                    if src[j] == "\\":
                        buf.append(src[j:j + 2])
                        j += 2
                    else:
                        buf.append(src[j])
                        j += 1
                out.append(("".join(buf), src.count("\n", 0, i) + 1))
                i = j + 1
                continue
            if c == "`":
                start = i
                text, i = template(i + 1)
                out.append((text, src.count("\n", 0, start) + 1))
                continue
            i += 1
        return i

    code(0)
    return out


def pieces(text):
    """Split rendered text at tags; keep trimmed pieces with Han characters."""
    text = text.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
    found = []
    for attr in ATTR.finditer(text):
        found.append(attr.group(2))
    for part in TAG.split(text):
        found.append(part)
    keys = []
    for part in found:
        part = re.sub(r"\s+", " ", part).strip()
        if HAN.search(part) and '="' not in part:   # a tag cut by "${...}" leaves attribute fragments
            keys.append(renumber(part))
    return keys


def renumber(key):
    """Placeholders numbered from 0 in order of appearance within the piece."""
    seen = {}
    return re.sub(r"\{(\d+)\}", lambda m: "{%d}" % seen.setdefault(m.group(1), len(seen)), key)


def html_parts(src):
    """(non-script html, [script bodies]) for an HTML file."""
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", src, re.S)
    html = re.sub(r"<script(?:\s[^>]*)?>.*?</script>", "", src, flags=re.S)
    html = re.sub(r"<style(?:\s[^>]*)?>.*?</style>", "", html, flags=re.S)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    return NO_I18N.sub("", html), scripts


def extract():
    keys = {}
    for name in FILES:
        src = (STATIC / name).read_text(encoding="utf-8")
        if name.endswith(".html"):
            html, scripts = html_parts(src)
            for key in pieces(html):
                keys.setdefault(key, name)
        else:
            scripts = [src]
        for body in scripts:
            for text, _line in js_strings(body):
                for key in pieces(NO_I18N.sub("", text)):
                    keys.setdefault(key, name)
    return keys


def missing(keys=None, pack=None):
    keys = extract() if keys is None else keys
    messages = (pack or json.loads(PACK.read_text(encoding="utf-8")))["messages"]
    return {k: v for k, v in keys.items() if k not in messages}


if __name__ == "__main__":
    keys = extract()
    show = keys if "--all" in sys.argv else missing(keys)
    for key, name in show.items():
        print(f"{name}\t{key}")
    print(f"# {len(show)} of {len(keys)}", file=sys.stderr)
