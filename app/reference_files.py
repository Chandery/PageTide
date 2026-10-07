"""Reading the export files of a reference manager: BibTeX, RIS and CSL-JSON (what Zotero writes).

Standard library only, linear in the size of the file, and defensive: the file comes from the person's disk but its
content is untrusted text. Nothing here follows a path, opens an attachment or touches the network; an entry is just
a dict of normalised fields, and `files` are the relative paths the export names (the importer matches those against
the PDFs that were actually picked). A broken entry is reported in `errors` and skipped; the rest is kept."""
import json
import re
import unicodedata

MAX_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 20000
MAX_FIELD = 100_000
MAX_DEPTH = 50
MAX_TITLE = 500
MAX_ABSTRACT = 5000
MAX_AUTHORS = 50

FORMATS = {"bib": "bibtex", "bibtex": "bibtex", "ris": "ris", "json": "csljson", "csljson": "csljson"}

_DOI = re.compile(r"10\.\d{4,9}/\S+", re.I)
_ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
_ARXIV_IN_TEXT = re.compile(r"arxiv(?:\.org/(?:abs|pdf)/|\s*:\s*)(\d{4}\.\d{4,5})", re.I)
_YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
_HEAD = re.compile(r"@\s*([A-Za-z]+)\s*([{(])")
_FIELD = re.compile(r"\s*([A-Za-z][A-Za-z0-9_\-:]*)\s*=\s*")
_SKIPPED_KINDS = {"comment", "string", "preamble"}


def format_of(filename):
    """'bibtex' | 'ris' | 'csljson' from a file name, or None."""
    dot = str(filename).rfind(".")
    return FORMATS.get(str(filename)[dot + 1:].lower()) if dot >= 0 else None


# --------------------------------------------------------------------------- shared helpers
_ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "=": "\u0304", ".": "\u0307",
            "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b", "r": "\u030a"}
_SPECIAL = {"ss": "ß", "o": "ø", "O": "Ø", "ae": "æ", "AE": "Æ", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł",
            "i": "i", "j": "j", "oe": "œ", "OE": "Œ"}
_SPECIAL_RE = re.compile(r"\\(ss|ae|AE|aa|AA|oe|OE|[oOlLij])(?![A-Za-z])\s?")
_SYMBOL_ACCENT_RE = re.compile(r"\\(['`^\"~=.])\s*\{?([A-Za-z])\}?")      # one run of spaces at most: linear on hostile input
_LETTER_ACCENT_RE = re.compile(r"\\([cvuHr])(?:\s*\{|\s+)([A-Za-z])\}?")
_ESCAPED_RE = re.compile(r"\\([&%$#_{}:;])")
_COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?\s*")


def latex(text):
    """LaTeX markup in a field as plain text: accents, escapes, protective braces."""
    text = _SPECIAL_RE.sub(lambda m: _SPECIAL[m.group(1)], str(text))
    text = _SYMBOL_ACCENT_RE.sub(lambda m: m.group(2) + _ACCENTS[m.group(1)], text)
    text = _LETTER_ACCENT_RE.sub(lambda m: m.group(2) + _ACCENTS[m.group(1)], text)
    text = _ESCAPED_RE.sub(lambda m: m.group(1) if m.group(1) not in "{}" else "\0" + m.group(1), text)
    text = _COMMAND_RE.sub("", text).replace("{", "").replace("}", "").replace("\0", "")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text.replace("~", " "))).strip()


def _clean(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _doi(value):
    text = str(value or "").strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.I)
    match = _DOI.match(text)
    return match.group(0).rstrip(".,;)").lower() if match else None


def _arxiv(*values):
    for value in values:
        match = _ARXIV_IN_TEXT.search(str(value or ""))
        if match:
            return match.group(1)
    return None


def _year(value):
    match = _YEAR.search(str(value or ""))
    return int(match.group(1)) if match else None


def _entry(identifier, title, authors, year, doi, arxiv, abstract, venue, files):
    return {"id": _clean(identifier, 200) or None, "title": _clean(title, MAX_TITLE),
            "authors": [a for a in (_clean(a, 200) for a in authors) if a][:MAX_AUTHORS], "year": year,
            "doi": doi, "arxiv": arxiv, "abstract": _clean(abstract, MAX_ABSTRACT) or None,
            "venue": _clean(venue, 300) or None, "files": [f for f in files if f]}


# --------------------------------------------------------------------------- BibTeX
def _find_close(text, start, opener, closer):
    """Index of the character that closes the entry opened just before `start`, -1 if it never closes, -2 if the
    braces nest too deeply. Backslash escapes the next character, as in the fields themselves."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
            if depth > MAX_DEPTH:
                return -2
        elif c == "}":
            if depth == 0 and closer == "}":
                return i
            depth -= 1
        elif c == closer and depth == 0 and opener == "(":
            return i
        i += 1
    return -1


def _read_value(body, i):
    """(raw value, next index) of one field value starting at body[i]: {balanced}, "quoted" or a bare token."""
    n = len(body)
    if i < n and body[i] == "{":
        depth, j = 0, i
        while j < n:
            c = body[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return body[i + 1:j][:MAX_FIELD], j + 1
            j += 1
        raise ValueError("字段没有结束")
    if i < n and body[i] == '"':
        depth, j = 0, i + 1
        while j < n:
            c = body[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == '"' and depth <= 0:
                return body[i + 1:j][:MAX_FIELD], j + 1
            j += 1
        raise ValueError("字段没有结束")
    j = i
    while j < n and body[j] not in ",\n":
        j += 1
    return body[i:j].strip(), j


def _fields(body):
    fields, i, n = {}, 0, len(body)
    while i < n:
        match = _FIELD.match(body, i)
        if not match:
            if body[i:].strip(" \t\r\n,"):
                raise ValueError("字段格式不对")
            break
        value, i = _read_value(body, match.end())
        fields.setdefault(match.group(1).lower(), value)
        while i < n and body[i] in " \t\r\n,":
            i += 1
    return fields


def _split_top(text, separator):
    """Split on `separator` (a word such as ' and ') outside braces."""
    parts, depth, last, i, lower = [], 0, 0, 0, text.lower()
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 0 and lower.startswith(separator, i):
            parts.append(text[last:i])
            i += len(separator)
            last = i
            continue
        i += 1
    parts.append(text[last:])
    return parts


def _unescaped_split(text, separator):
    parts, buf, i = [], [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            buf.append(text[i:i + 2])
            i += 2
            continue
        if c == separator:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _bibtex_files(raw):
    r"""PDF paths from a Zotero `file` field: 'description:path:mimetype' items joined by ';', with `\:` and `\;` escaped."""
    found = []
    for item in _unescaped_split(raw or "", ";"):
        if not item.strip():
            continue
        parts = _unescaped_split(item, ":")
        path = parts[1] if len(parts) >= 2 else parts[0]
        mime = parts[2].strip().lower() if len(parts) >= 3 else ""
        path = re.sub(r"\\(.)", r"\1", path).strip()
        if path.lower().endswith(".pdf") or mime == "application/pdf":
            found.append(path[2:] if path.startswith("./") else path)
    return found


def _bibtex_entry(key, fields):
    title = latex(fields.get("title", ""))
    if not title:
        raise ValueError(f"条目 {key} 没有标题")
    authors = [latex(a) for a in _split_top(fields.get("author", ""), " and ")] if fields.get("author") else []
    venue = next((latex(fields[name]) for name in ("journaltitle", "journal", "booktitle", "publisher", "series") if fields.get(name)), None)
    eprint = fields.get("eprint", "").strip()
    kind = (fields.get("eprinttype") or fields.get("archiveprefix") or "").strip().lower()
    arxiv = None
    if eprint and (kind == "arxiv" or _ARXIV_ID.fullmatch(eprint)):
        match = _ARXIV_ID.match(eprint.lower().replace("arxiv:", "").strip())
        arxiv = match.group(1) if match else None
    arxiv = arxiv or _arxiv(fields.get("url"), fields.get("journal"), fields.get("journaltitle"), fields.get("note"))
    doi = _doi(latex(fields.get("doi", ""))) or _doi(latex(fields.get("url", "")))
    return _entry(key, title, authors, _year(fields.get("year") or fields.get("date")), doi, arxiv,
                  latex(fields["abstract"]) if fields.get("abstract") else None, venue, _bibtex_files(fields.get("file")))


def parse_bibtex(text):
    entries, errors, i = [], [], 0
    while len(entries) < MAX_ENTRIES:
        at = text.find("@", i)
        if at < 0:
            break
        head = _HEAD.match(text, at)
        if not head:
            i = at + 1
            continue
        kind, opener = head.group(1).lower(), head.group(2)
        end = _find_close(text, head.end(), opener, "}" if opener == "{" else ")")
        if end == -2:
            errors.append("有一个条目的括号嵌套过深，已跳过")
            i = head.end()
            continue
        if end < 0:
            errors.append(f"有一个条目没有结束：{text[head.end():head.end() + 40].strip()}")
            break
        i = end + 1
        if kind in _SKIPPED_KINDS:
            continue
        key, _, rest = text[head.end():end].partition(",")
        key = key.strip()
        try:
            entries.append(_bibtex_entry(key, _fields(rest)))
        except ValueError as exc:
            errors.append(str(exc) if key in str(exc) else f"条目 {key or '?'}：{exc}")
    else:
        errors.append(f"条目超过上限 {MAX_ENTRIES}，多出的没有读取")
    return {"entries": entries, "errors": errors[:50]}


# --------------------------------------------------------------------------- RIS
_RIS_LINE = re.compile(r"^([A-Z][A-Z0-9])  -(?: (.*))?$")


def _ris_entry(fields, number):
    first = lambda *tags: next((v[0] for t in tags for v in [fields.get(t)] if v), None)
    title = first("TI", "T1")
    if not title:
        raise ValueError(f"第 {number} 条记录没有标题")
    urls = " ".join(fields.get("UR", []))
    doi = _doi(first("DO")) or _doi(urls)
    files = [p.strip() for p in fields.get("L1", []) + fields.get("L2", []) if p.strip().lower().endswith(".pdf")]
    return _entry(first("ID"), title, fields.get("AU") or fields.get("A1") or [], _year(first("PY", "Y1", "DA")), doi,
                  _arxiv(urls, first("N1"), first("JO", "JF", "T2")), first("AB", "N2"), first("JO", "JF", "T2"), files)


def _ris_join(fields):
    return {tag: [" ".join(parts)[:MAX_FIELD] for parts in values] for tag, values in fields.items()}


def parse_ris(text):
    entries, errors, fields, last, number, size = [], [], {}, None, 0, 0
    for raw in text.lstrip("﻿").splitlines():
        line = raw.rstrip()
        match = _RIS_LINE.match(line)
        if match:
            tag, value = match.group(1), (match.group(2) or "").strip()
            if tag == "ER":
                number += 1
                if len(entries) >= MAX_ENTRIES:
                    errors.append(f"条目超过上限 {MAX_ENTRIES}，多出的没有读取")
                    break
                try:
                    entries.append(_ris_entry(_ris_join(fields), number))
                except ValueError as exc:
                    errors.append(str(exc))
                fields, last = {}, None
            elif tag != "TY":
                fields.setdefault(tag, []).append([value[:MAX_FIELD]])
                last, size = tag, len(value)
        elif line.strip() and last and fields.get(last) and size < MAX_FIELD:
            piece = line.strip()
            fields[last][-1].append(piece)   # a wrapped value: pieces are joined once, and collection stops at the cap
            size += len(piece) + 1
    return {"entries": entries, "errors": errors[:50]}


# --------------------------------------------------------------------------- CSL-JSON
def _csl_text(value):
    """A CSL field that may be a string or a list of strings (take the first)."""
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str) and v.strip()), "")
    return value if isinstance(value, str) else ""


def _csl_author(author):
    if not isinstance(author, dict):
        return ""
    if isinstance(author.get("literal"), str) and author["literal"].strip():
        return author["literal"]
    return ", ".join(p for p in (author.get("family"), author.get("given")) if isinstance(p, str) and p.strip())


def _csl_year(issued):
    """The year of a CSL 'issued': {"date-parts": [[2020, 5]]}, a bare [2020], numbers or strings, or {"raw": "2018-03-04"}."""
    if not isinstance(issued, dict):
        return None
    parts = issued.get("date-parts")
    first = parts[0] if isinstance(parts, list) and parts else None
    if isinstance(first, list):
        first = first[0] if first else None
    year = _year(first) if isinstance(first, (int, str)) and not isinstance(first, bool) else None
    return year or _year(issued.get("raw") or issued.get("literal"))


def _csl_entry(item):
    title = _csl_text(item.get("title")).strip()
    if not title:
        raise ValueError("没有标题")
    authors = item.get("author") if isinstance(item.get("author"), list) else []
    return _entry(item.get("id") if isinstance(item.get("id"), (str, int)) else None, title, [_csl_author(a) for a in authors],
                  _csl_year(item.get("issued")), _doi(_csl_text(item.get("DOI"))) or _doi(_csl_text(item.get("URL"))),
                  _arxiv(_csl_text(item.get("URL")), _csl_text(item.get("note"))), _csl_text(item.get("abstract")),
                  _csl_text(item.get("container-title")), [])


def parse_csl_json(text):
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):   # not JSON, or nested far deeper than any real export
        return {"entries": [], "errors": ["这不是有效的 JSON 文件"]}
    if not isinstance(data, list):
        return {"entries": [], "errors": ["CSL-JSON 导出应该是一个列表"]}
    entries, errors = [], []
    for number, item in enumerate(data, 1):
        if len(entries) >= MAX_ENTRIES:
            errors.append(f"条目超过上限 {MAX_ENTRIES}，多出的没有读取")
            break
        try:
            if not isinstance(item, dict):
                raise ValueError("不是一个条目")
            entries.append(_csl_entry(item))
        except Exception as exc:   # one odd item must not lose the rest of the export
            errors.append(f"第 {number} 项没有读取：{exc}"[:200])
    return {"entries": entries, "errors": errors[:50]}


PARSERS = {"bibtex": parse_bibtex, "ris": parse_ris, "csljson": parse_csl_json}


def parse(fmt, data):
    """Entries and errors from the bytes of an export file."""
    if fmt not in PARSERS:
        raise ValueError("不支持的导出文件格式")
    if len(data) > MAX_BYTES:
        raise ValueError("导出文件超过 20 MB")
    return PARSERS[fmt](bytes(data).decode("utf-8-sig", errors="replace"))
