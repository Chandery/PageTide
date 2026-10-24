"""Contrast regression test: the UI cannot silently become unreadable.

The owner reported "dark text on dark buttons". The cause was that --accent-ink
was never defined, so the primary button inherited its text colour, plus several
token pairs sitting below WCAG AA. This test parses the real token definitions out
of app/static/theme.css, resolves the light and dark PageTide palettes (the
per-user accent picker was retired on 2026-09-30), and fails if any text pair
drops below 4.5:1.
"""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
HTML = STATIC / "index.html"
THEME = STATIC / "theme.css"
# Every stylesheet that consumes the shared tokens.
CONSUMERS = ("organization.css", "profile.css", "project-creation.css")


def parse_hex(value):
    value = value.strip()
    match = re.fullmatch(r"#([0-9a-fA-F]{3,8})", value)
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    if len(digits) not in (6, 8):
        return None
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def style_text():
    text = HTML.read_text()
    match = re.search(r"<style>(.*?)</style>", text, re.S)
    return match.group(1)


def all_css():
    """index.html's inline style plus every linked stylesheet and the theme itself."""
    return "\n".join([style_text(), THEME.read_text()] + [(STATIC / name).read_text() for name in CONSUMERS])


def declarations(block):
    return {k.strip(): v.strip() for k, v in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", block)}


def _block_after(css, selector):
    """Return the declarations of the first rule with exactly this selector."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return declarations(match.group(1)) if match else {}


def _blocks_matching(css, pattern):
    out = {}
    for match in re.finditer(pattern, css, re.S):
        out[match.group(1)] = declarations(match.group(2))
    return out


def token_sets():
    """Resolve the palette from the literal selectors used in the stylesheet."""
    css = THEME.read_text()
    base = {}
    for match in re.finditer(r"(?m)^\s*:root\s*\{([^}]*)\}", css, re.S):
        base.update(declarations(match.group(1)))
    dark = {}
    for match in re.finditer(r'html\[data-mode="dark"\]\s*\{([^}]*)\}', css, re.S):
        dark.update(declarations(match.group(1)))
    accents = _blocks_matching(all_css(), r'html\[(?:data-mode="dark"\]\[)?data-accent="([a-z]+)"\]\s*\{([^}]*)\}')
    return base, dark, accents


class ContrastTests(unittest.TestCase):
    def setUp(self):
        base, dark, self.accents = token_sets()
        self.base, self.dark = base, dark
        self.assertIn("base", base, "could not parse the light palette")
        self.assertIn("base", dark, "could not parse the dark palette")

    def _ratio(self, tokens, fg, bg):
        f, b = tokens.get(fg), tokens.get(bg)
        self.assertIsNotNone(f, f"{fg} is not defined")
        self.assertIsNotNone(b, f"{bg} is not defined")
        fc, bc = parse_hex(f), parse_hex(b)
        self.assertIsNotNone(fc, f"{fg}={f} is not a hex colour")
        self.assertIsNotNone(bc, f"{bg}={b} is not a hex colour")
        return contrast(fc, bc)

    def _check(self, label, tokens):
        # Check against the WORST-CASE surface of each mode: the darkest light
        # surface and the lightest dark surface. Tuning against the best case is
        # exactly how the earlier palette ended up unreadable.
        pairs = []
        for surface in ("base", "surface-1", "surface-2", "surface-3"):
            pairs += [
                (f"text on {surface}", "text", surface),
                (f"muted on {surface}", "muted", surface),
                (f"accent-text on {surface}", "accent-text", surface),
                (f"good on {surface}", "good", surface),
                (f"bad on {surface}", "bad", surface),
                (f"ai-text on {surface}", "ai-text", surface),
                (f"mark-text on {surface}", "mark-text", surface),
            ]
        pairs.append(("accent-ink on accent fill", "accent-ink", "accent"))
        for name, fg, bg in pairs:
            with self.subTest(case=label, pair=name):
                ratio = self._ratio(tokens, fg, bg)
                self.assertGreaterEqual(round(ratio, 2), 4.5,
                                        f"{label}: {name} is {ratio:.2f}:1, below WCAG AA 4.5:1")

    def test_light_palette_is_readable(self):
        self._check("light", self.base)

    def test_dark_palette_is_readable(self):
        self._check("dark", {**self.base, **self.dark})

    def test_both_modes_define_their_own_text_tokens(self):
        """The original bug: --accent-ink was undefined, so buttons inherited a colour."""
        for label, tokens in (("light", self.base), ("dark", self.dark)):
            for token in ("accent", "accent-ink", "accent-text", "ai-text", "mark-text", "text", "muted"):
                self.assertIn(token, tokens, f"{label} does not define {token}")

    def test_index_does_not_redefine_the_palette(self):
        """theme.css is the single source; an inline :root in index.html would shadow it."""
        self.assertNotRegex(style_text(), r"(?m)^\s*:root\s*\{")
        self.assertNotRegex(style_text(), r'html\[data-mode="dark"\]\s*\{')
        for page in ("index.html", "settings.html", "project_creation.html", "weekly_report.html"):
            with self.subTest(page=page):
                self.assertIn('href="/theme.css"', (STATIC / page).read_text())

    def test_accent_picker_stays_retired(self):
        """One palette only: a stale data-accent block would silently override it."""
        self.assertEqual(self.accents, {}, "data-accent overrides are back in index.html")

    def test_every_css_variable_used_is_defined(self):
        """An undefined token silently inherits a colour - the dark-on-dark bug."""
        css = all_css()
        base, dark, _ = token_sets()
        # component-scoped tokens (e.g. --org-*, --p-*) are defined where they are used
        defined = set(base) | set(dark) | set(declarations(css))
        literal = set(base)   # tokens referenced only inside :root (e.g. --sd in shadows)
        used_without_fallback = set(re.findall(r"var\(--([a-z0-9-]+)\s*\)", css))
        missing = sorted(used_without_fallback - defined - literal)
        self.assertEqual(missing, [], f"CSS variables used but never defined: {missing}")

    def test_known_bad_pair_would_be_caught(self):
        """Guard the guard: the colours that caused the original report still fail."""
        for bad, bg in (("#7d849b", "surface-1"), ("#98a1b1", "surface-3")):
            with self.subTest(colour=bad, surface=bg):
                ratio = contrast(parse_hex(bad), parse_hex(self.base[bg]))
                self.assertLess(round(ratio, 2), 4.5)
        # and the current palette must be strictly better on the same pair
        self.assertGreaterEqual(
            round(contrast(parse_hex(self.base["muted"]), parse_hex(self.base["surface-1"])), 2), 4.5)


if __name__ == "__main__":
    unittest.main()
