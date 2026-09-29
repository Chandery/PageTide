"""Presentation contracts for the local UI; geometry is checked in-browser."""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "app/static/index.html"


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.html = HTML.read_text()
        self.css = re.search(r"<style>(.*?)</style>", self.html, re.S).group(1)

    def test_navigation_is_keyboard_operable(self):
        for view in ("today", "library", "profile"):
            self.assertRegex(self.html, rf'<button[^>]+data-view="{view}"')

    def test_paper_titles_are_keyboard_operable(self):
        self.assertIn('class="paper-title"', self.html)
        self.assertIn('class="library-title"', self.html)

    def test_motion_has_final_reduced_motion_override(self):
        self.assertIn("@keyframes viewEnter", self.css)
        self.assertRegex(
            self.css,
            r"@media \(prefers-reduced-motion: reduce\)\s*\{[^}]+"
            r"animation:none!important;transition:none!important;",
        )

    def test_no_network_visual_dependencies(self):
        self.assertNotRegex(self.html, r'<(?:script|link)[^>]+(?:src|href)="https?://')
        self.assertIn('url("/icons/book-open.svg")', self.css)

    def test_no_viewport_scaled_fonts_or_negative_tracking(self):
        self.assertNotRegex(self.css, r"font-size:[^;}]*vw")
        self.assertNotRegex(self.css, r"letter-spacing:\s*-")

    def test_pinch_anchor_scales_pointer_offset_before_rerender(self):
        # Regression for the trackpad release jump: the point under the pointer
        # is kept inside one transformed surface, then measured again only when
        # the gesture has ended.
        self.assertIn(
            "surface.style.transform = `translateX(${centerOffset}px) scale(${k})`;",
            self.html,
        )
        self.assertIn("const surfaceTop = contentTopOf(surface, box);", self.html)
        self.assertIn("function commitZoom()", self.html)
        self.assertIn("zoomTimer = setTimeout(commitZoom, 260);", self.html)
        self.assertIn("commitZoom();", self.html)
        self.assertIn(
            "box.scrollLeft + localX - contentLeftOf(anchorWrap, box)",
            self.html,
        )
        self.assertIn(
            "Math.exp(-event.deltaY * 0.0042)",
            self.html,
        )

    def test_pinch_visual_phase_reserves_scaled_page_geometry(self):
        self.assertIn("stage.style.width = `${Math.max(box.clientWidth, visualWidth)}px`;", self.html)
        self.assertIn("stage.style.height = `${base.baseHeight * k}px`;", self.html)
        self.assertIn("surface.style.gap = `${pendingBeforeLayout?.gap ?? 22}px`;", self.html)
        self.assertIn("R.zoomBase.finalGap = R.zoomBase.gap * k;", self.html)
        self.assertNotIn("num.className = 'pgno'", self.html)
        self.assertNotIn("num.textContent = `${i + 1} / ${R.pages.length}`", self.html)
        self.assertIn(".reader .page-stage {", self.css)
        self.assertIn("min-width:0", self.css)
        self.assertIn("flex:0 0 auto", self.css)

    def test_plain_trackpad_scroll_is_not_cancelled(self):
        self.assertIn("if (!zoomModifier) return;", self.html)
        self.assertNotIn(
            "pagesBox.addEventListener('wheel', (event) => { if (gestureBase !== null) event.preventDefault();",
            self.html,
        )

    def test_provider_settings_ui_is_wired_and_keeps_the_key_off_client_storage(self):
        # The desktop app previously had no way to provision the runtime key, so
        # every AI feature degraded to local mode. The key is entered here and
        # stored server-side only; it must never land in webview storage.
        self.assertIn('id="settingsBtn"', self.html)
        self.assertIn('id="settingsPage"', self.html)
        self.assertIn("api('/api/settings')", self.html)
        self.assertIn("api('/api/settings', { api_key: value })", self.html)
        self.assertIn('type="password"', self.html)
        self.assertNotIn("localStorage.setItem('pdh-api-key", self.html)
        self.assertNotIn("localStorage.getItem('pdh-api-key", self.html)

    def test_zoom_commit_keeps_visible_pdf_tree(self):
        self.assertIn("Never rebuild the visible PDF tree at gesture end.", self.html)
        self.assertIn("R.pendingZoom = null;", self.html)
        self.assertNotIn("R.renderedScale = R.scale;", self.html)
        self.assertNotIn("layoutPages();\n}", self.html[self.html.find("function commitZoom()"):self.html.find("function setScale")])

    def test_lazy_pages_use_the_existing_tree_scale_during_zoom(self):
        self.assertIn(
            "scale: R.renderedScale || pageScale(page)",
            self.html,
        )

    def test_repeated_zoom_converts_transformed_anchor_back_to_base_space(self):
        self.assertIn("const activeK = R.fit ? 1 : (R.scale / renderedScale);", self.html)
        self.assertIn(
            "(contentTopOf(anchorWrap, box) - surfaceTop) / activeK",
            self.html,
        )
        self.assertIn(
            "(box.scrollTop + localY - contentTopOf(anchorWrap, box)) / activeK",
            self.html,
        )


if __name__ == "__main__":
    unittest.main()
