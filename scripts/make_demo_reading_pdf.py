#!/usr/bin/env python3
"""Write app/static/demo/reading-material.pdf, the demo project's reading material, from app/demo_fixture.READING.

Pure standard library and deterministic (no dates, no random ids), so tests can regenerate it and compare the bytes:

    python3 scripts/make_demo_reading_pdf.py            # rewrite the committed file
    python3 scripts/make_demo_reading_pdf.py --check    # exit 1 when the committed file differs

The text is original to this repository (see the note above READING_QA in app/demo_fixture.py); the paper's own PDF is not
redistributed. Fonts are the PDF standard Helvetica and Helvetica-Bold (nothing embedded), so the file has a real text layer
that pdf.js can select. The sentences that app/demo_fixture.READING_QA marks `highlight` are painted pale yellow behind the text.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import demo_fixture as fixture  # noqa: E402

OUT = ROOT / "app" / "static" / "demo" / fixture.READING_FILE

PAGE_W, PAGE_H, MARGIN = 612, 792, 72
BODY, LEAD = 11, 16
GREY = "0.42 0.42 0.42 rg"
BLACK = "0 g"
HIGHLIGHT = "1 0.92 0.45 rg"

# Adobe Helvetica / Helvetica-Bold advance widths (1/1000 em) for ASCII 32..126, from the standard AFM files.
_REGULAR = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556,
            556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
            667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
            556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556,
         556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
         667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611,
         611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]


def width(text, size, bold=False):
    table = _BOLD if bold else _REGULAR
    return sum(table[ord(c) - 32] for c in text) * size / 1000.0


def escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def num(value):
    text = ("%.2f" % value).rstrip("0").rstrip(".")
    return text or "0"


def paragraph_words(text):
    """[(word, highlighted)] for one paragraph: the words of a sentence marked `highlight` in READING_QA are flagged."""
    words = text.split(" ")
    flags = [False] * len(words)
    for entry in fixture.READING_QA:
        if not entry.get("highlight"):
            continue
        target = entry["sentence"].split(" ")
        for start in range(len(words) - len(target) + 1):
            if words[start:start + len(target)] == target:
                for i in range(start, start + len(target)):
                    flags[i] = True
    return list(zip(words, flags))


def wrap(words, size, limit):
    lines, current = [], []
    for word, flag in words:
        trial = current + [(word, flag)]
        if current and width(" ".join(w for w, _ in trial), size) > limit:
            lines.append(current)
            current = [(word, flag)]
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


class Pages:
    def __init__(self):
        self.pages = [[]]
        self.y = PAGE_H - MARGIN

    def room(self, needed):
        if self.y - needed < MARGIN:
            self.pages.append([])
            self.y = PAGE_H - MARGIN

    def text(self, x, size, content, bold=False, color=BLACK):
        font = "F2" if bold else "F1"
        self.pages[-1].append("BT %s /%s %s Tf %s Td (%s) Tj ET" % (color, font, num(size), "%s %s" % (num(x), num(self.y)), escape(content)))

    def rect(self, x, y, w, h, color):
        self.pages[-1].append("%s %s %s %s %s re f" % (color, num(x), num(y), num(w), num(h)))


def layout():
    doc = fixture.READING
    pages = Pages()
    limit = PAGE_W - 2 * MARGIN
    pages.y -= 9
    pages.text(MARGIN, 9, doc["banner"], color=GREY)
    pages.y -= 34
    pages.text(MARGIN, 22, doc["title"], bold=True)
    pages.y -= 20
    pages.text(MARGIN, 11, doc["subtitle"], color=GREY)
    pages.y -= 14
    for heading, paragraphs in doc["sections"]:
        pages.y -= 20
        pages.room(30 + 2 * LEAD)
        pages.text(MARGIN, 13, heading, bold=True)
        pages.y -= 8
        for paragraph in paragraphs:
            lines = wrap(paragraph_words(paragraph), BODY, limit)
            for line in lines:
                pages.y -= LEAD
                pages.room(LEAD)
                # The highlight is drawn first so the text stays on top of it.
                flagged = [i for i, (_, flag) in enumerate(line) if flag]
                if flagged:
                    before = " ".join(w for w, _ in line[:flagged[0]])
                    through = " ".join(w for w, _ in line[:flagged[-1] + 1])
                    x0 = MARGIN + (width(before + " ", BODY) if before else 0)
                    x1 = MARGIN + width(through, BODY)
                    pages.rect(x0 - 1.5, pages.y - 3.6, x1 - x0 + 3, BODY + 4.4, HIGHLIGHT)
                pages.text(MARGIN, BODY, " ".join(w for w, _ in line))
            pages.y -= 7
    return pages.pages


def build():
    pages = layout()
    objects = []   # object n is objects[n - 1] (bytes)

    def add(body):
        objects.append(body if isinstance(body, bytes) else body.encode("latin-1"))
        return len(objects)

    catalog = add(b"")        # 1, filled in below
    tree = add(b"")           # 2
    regular = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    info = add("<< /Title (%s) /Subject (Demo reading material, not the paper's original text) /Producer (PageTide scripts/make_demo_reading_pdf.py) >>"
               % escape(fixture.READING["title"] + ": demo reading notes"))
    kids = []
    for commands in pages:
        stream = ("\n".join(commands) + "\n").encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
        kids.append(add("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                        % (tree, PAGE_W, PAGE_H, regular, bold, content)))
    objects[catalog - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % tree).encode("latin-1")
    objects[tree - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % k for k in kids), len(kids))).encode("latin-1")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, info, xref)
    return bytes(out)


def main(argv):
    data = build()
    if "--check" in argv:
        same = OUT.is_file() and OUT.read_bytes() == data
        print("up to date" if same else "differs from %s" % OUT)
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print("wrote %s (%d bytes)" % (OUT, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
