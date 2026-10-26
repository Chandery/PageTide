"""Owner's polish list of 2026-10-25: where text can be selected, the dark confirm dialog, hiding scrollbars, the settings
page's bordered buttons and coloured results, emoji-free READMEs, and close-to-tray on Windows."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
read = lambda name: (STATIC / name).read_text()
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐]")


class SelectionTests(unittest.TestCase):
    def test_only_abstracts_the_pdf_and_fields_can_be_selected(self):
        theme = read("theme.css")
        self.assertIn("body { -webkit-user-select:none; user-select:none; }", theme)
        allowed = theme[theme.index("input, textarea"):].split("{")[0]
        for selector in ("input", "textarea", "#detail .detail-section .full", ".org-abstract > :not(summary)", ".reader .textLayer"):
            self.assertIn(selector, allowed)
        for name in ("index.html", "organization.css", "profile.css", "project-creation.css", "settings.html"):
            self.assertNotRegex(read(name), r"user-select:\s*(?:text|auto|all)", f"{name} reopens selection")


class DialogTests(unittest.TestCase):
    def test_the_confirm_dialog_and_notices_use_theme_surfaces(self):
        css = read("dialogs.css")
        self.assertNotIn("var(--surface,", css)          # an undefined token fell back to white in dark mode
        self.assertIn("background:var(--surface-1,#fff)", css)

    def test_results_are_green_with_a_tick_or_red_with_a_cross(self):
        css = read("dialogs.css")
        self.assertRegex(css, r"\[data-pt-status\]\[data-kind=success\][^{]*\{color:var\(--good")
        self.assertRegex(css, r"\[data-pt-status\]\[data-kind=error\][^{]*\{color:var\(--bad")
        self.assertIn('url("/icons/check.svg")', css)
        self.assertIn('url("/icons/x.svg")', css)
        self.assertTrue((STATIC / "icons" / "x.svg").is_file())


class ScrollbarTests(unittest.TestCase):
    def test_bars_show_while_scrolling_and_hide_three_seconds_later(self):
        theme, js = read("theme.css"), read("theme.js")
        self.assertIn("scrollbar-color:transparent transparent", theme)
        self.assertIn(".pt-scrolling { scrollbar-color:var(--scroll-thumb) transparent; }", theme)
        self.assertIn(".pt-scrolling::-webkit-scrollbar-thumb", theme)
        self.assertIn("SCROLL_IDLE=3000", js)
        self.assertIn("document.addEventListener?.('scroll'", js)
        self.assertIn("capture:true", js)               # element scrolls do not bubble


class SettingsTests(unittest.TestCase):
    def test_every_settings_button_has_an_edge_and_switches_are_switches(self):
        html = read("settings.html")
        self.assertNotIn('class="ghost"', html)
        self.assertRegex(html, r"button \{[^}]*border: 1px solid var\(--line-strong\)")
        self.assertNotIn('class="inline"', html)
        for box in ("aiEnabled", "autoCheckUpdates", "routeBeta", "sourceArxiv", "sourceOpenAlex", "sourceBaiduWeb"):
            self.assertRegex(html, rf'<input type="checkbox" id="{box}" class="switch"')
            self.assertIn(f'<label for="{box}">', html)


class ReadmeTests(unittest.TestCase):
    def test_the_readmes_have_no_emoji_and_their_anchors_match_the_headings(self):
        for name in ("README.md", "README-zh.md"):
            text = (ROOT / name).read_text()
            self.assertIsNone(EMOJI.search(text), name)
            self.assertNotRegex(text, r"\]\(#-", name)


class TrayTests(unittest.TestCase):
    def test_windows_close_hides_to_the_tray_and_quit_stays_guarded(self):
        rust = (ROOT / "src-tauri" / "src" / "main.rs").read_text()
        self.assertIn('features = ["tray-icon"]', (ROOT / "src-tauri" / "Cargo.toml").read_text())
        first = rust[rust.index("WindowEvent::CloseRequested"):]
        cnki = first[:first.index("RunEvent::WindowEvent")]                      # the 知网 window (ADR 0045) only hides
        self.assertIn("if label == cnki::LABEL", cnki)
        self.assertIn("cnki::on_close_requested", cnki)
        self.assertNotIn("prepare_quit", cnki)
        close = rust[rust.index("if label != cnki::LABEL"):][:600]
        self.assertIn("if cfg!(windows)", close)
        self.assertIn("hide_to_tray(&window)", close)
        self.assertIn("prepare_quit(handle)", close)      # macOS keeps the guarded quit
        tray = rust[rust.index("fn install_tray"):][:1800]
        self.assertIn("QUIT => {\n                show_main_window(handle);\n                prepare_quit(handle);", tray)


class AssistantTests(unittest.TestCase):
    def test_questions_are_asked_only_in_the_pdf_reader(self):
        index = read("index.html")
        self.assertNotIn('id="pet"', index)                      # no floating assistant button on the home page
        self.assertNotRegex(index, r"\.pet\s*\{")
        self.assertIn("$('#readerAsk').onclick = () => { openPet();", index)   # the reader keeps its own ask button
        self.assertIn("""$('#selbar [data-sel="ask"]').classList.toggle('hidden', !e.target.closest('#readerPages'));""", index)


if __name__ == "__main__":
    unittest.main()
