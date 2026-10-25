"""Every stylesheet takes its type sizes, radii and shadows from the scales in theme.css, and none of the habits the
Kill-AI-Slop review flagged (hover lifts, spring easing, glass, atmosphere gradients, left colour bars) comes back."""
import pathlib
import re
import unittest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "app" / "static"
SHEETS = {p.name: p.read_text() for p in sorted(STATIC.glob("*.css")) + sorted(STATIC.glob("*.html"))}
THEME = SHEETS["theme.css"]
FS = ("xs", "sm", "md", "lg", "xl", "2xl", "3xl")
RADII = ("xs", "sm", "md", "lg")


def token(kind, names):
    return rf"var\(--{kind}-(?:{'|'.join(names)})(?:,[\d.]+px)?\)"


class ScaleTests(unittest.TestCase):
    def test_the_scales_are_defined_once_in_the_theme(self):
        sizes = [float(re.search(rf"--fs-{n}:([\d.]+)px", THEME).group(1)) for n in FS]
        for small, big in zip(sizes, sizes[1:]):
            self.assertGreaterEqual(big / small, 1.15, f"{small}px and {big}px are too close to be two steps")
        self.assertIn("--r-md:10px", THEME)   # project-switcher.js animates a window corner to this value
        for name, text in SHEETS.items():
            if name != "theme.css":
                self.assertNotRegex(text, r"--(?:fs|r|sh)-[\w-]+\s*:", f"{name} redefines a theme scale")

    def test_every_font_size_is_a_step(self):
        step = token("fs", FS)
        allowed = re.compile(rf"(?:calc\({step} \* var\(--s\)\)|{step}|inherit|[\d.]+em|\d+%)")
        for name, text in SHEETS.items():
            for value in re.findall(r"font-size:\s*([^;}\"!]+?)\s*(?=[;}\"!])", text):
                self.assertRegex(value, allowed, f"{name}: font-size:{value}")
            self.assertNotRegex(text, r"\bfont:\s*(?:\d{3}\s+)?(?:calc\()?[\d.]+px", f"{name}: a font shorthand with a raw size")

    def test_every_radius_is_a_step_a_pill_or_a_circle(self):
        step = token("r", RADII)
        part = rf"(?:calc\({step} \* var\(--s\)\)|{step}|0|999px|50%|inherit)"
        allowed = re.compile(rf"{part}(?:\s+{part}){{0,3}}")
        for name, text in SHEETS.items():
            for value in re.findall(r"border-radius:\s*([^;}\"!]+?)\s*(?=[;}\"!])", text):
                self.assertRegex(value, allowed, f"{name}: border-radius:{value}")

    def test_no_shadow_is_larger_than_the_floating_step(self):
        for name, text in SHEETS.items():
            for shadow in re.findall(r"box-shadow:\s*([^;}]+)", text):
                for blur in re.findall(r"-?\d+px\s+-?\d+px\s+(\d+)px", shadow):
                    self.assertLessEqual(int(blur), 24, f"{name}: box-shadow:{shadow}")


class SlopTests(unittest.TestCase):
    def test_hover_never_lifts_or_grows(self):
        for name, text in SHEETS.items():
            self.assertNotRegex(text, r":hover[^{]*\{[^}]*transform:\s*(?:translate|scale)", name)

    def test_no_spring_easing_glass_or_atmosphere(self):
        for name, text in SHEETS.items():
            self.assertNotIn("ease-spring", text, name)
            self.assertNotIn("backdrop-filter:blur", text.replace(" ", ""), name)
            self.assertNotIn("radial-gradient", text, name)
            for line in text.splitlines():   # gradients only draw the loading shimmer and the tree guides, never a surface
                if "linear-gradient" in line:
                    self.assertRegex(line, r"\.skeleton|repeating-linear-gradient", name)

    def test_no_coloured_left_bars(self):
        for name, text in SHEETS.items():
            self.assertNotRegex(text, r"border-left:\s*[2-9]px solid var\(--(?:accent|ai|ai-text|good|bad|warn|mark)\)", name)
            self.assertNotIn("border-left-color", text, name)

    def test_labels_are_not_shouted(self):
        for name, text in SHEETS.items():
            self.assertNotIn("uppercase", text, name)
        self.assertNotIn("✦", THEME)


if __name__ == "__main__":
    unittest.main()
