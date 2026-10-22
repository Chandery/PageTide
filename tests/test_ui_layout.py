"""Presentation contracts for the local UI; geometry is checked in-browser."""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "app/static/index.html"
ORG_CSS = Path(__file__).resolve().parents[1] / "app/static/organization.css"
ORG_JS = Path(__file__).resolve().parents[1] / "app/static/organization.js"


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.html = HTML.read_text()
        self.css = re.search(r"<style>(.*?)</style>", self.html, re.S).group(1)

    def test_navigation_is_keyboard_operable(self):
        for view in ("today", "library", "profile"):
            self.assertRegex(self.html, rf'<button[^>]+data-view="{view}"')

    def test_paper_titles_are_keyboard_operable(self):
        self.assertIn('class="paper-title"', self.html)   # the recommendation card's title; the library page draws its own rows

    def test_paper_detail_uses_a_reading_rail(self):
        self.assertIn('id="detail" class="page detail-page hidden"', self.html)
        self.assertIn('class="detail-scrim"', self.html)
        self.assertIn('class="detail-panel page-inner"', self.html)
        self.assertIn('role="dialog" aria-modal="true" aria-label="论文详情"', self.html)
        self.assertIn('class="detail-actions"', self.html)

    def test_knowledge_detail_folds_the_abstract_and_groups_metadata(self):
        org_css = ORG_CSS.read_text()
        org_js = ORG_JS.read_text()
        self.assertIn('class="org-detail-meta"', org_js)
        self.assertIn('class="org-detail-badges"', org_js)
        self.assertIn('class="org-notes"', org_js)
        self.assertIn('<details class="org-abstract">', org_js)       # the user's note comes first; the abstract is folded
        self.assertIn('.org-detail.has-paper', org_css)

    def test_knowledge_detail_header_rules_do_not_leak_into_notes(self):
        # The notes section head is also a :first-child; unscoped rules shrank 笔记 to 12px and
        # blew its edit/preview buttons up to 21px.
        org_css = ORG_CSS.read_text()
        self.assertNotIn('.org-detail.has-paper .org-section-head:first-child', org_css)
        self.assertIn('.org-detail.has-paper > .org-section-head:first-child', org_css)
        # A list row is one dense line (glyph, title, mark, year); the pane carries the categories and the note.
        self.assertIn('.org-paper-title { flex:1; min-width:0;', org_css)

    def test_assistant_quote_stays_compact_and_log_keeps_room(self):
        # A quoted selection once filled the whole panel and squeezed the log to nothing.
        self.assertRegex(self.css, r"\.refcard \.rsnip \{[^}]*-webkit-line-clamp:2")
        self.assertRegex(self.css, r"\.refcard\.expanded \.rsnip \{[^}]*max-height:30vh")
        self.assertRegex(self.css, r"\.plog \{[^}]*min-height:140px")
        self.assertIn(".petpanel > header, .pcompose { flex:0 0 auto; }", self.css)
        # The quote lives in the composer, below the log.
        panel = self.html[self.html.index('id="petPanel"'):self.html.index('id="pet"')]
        self.assertLess(panel.index('id="petLog"'), panel.index('id="petRef"'))
        self.assertLess(panel.index('id="petRef"'), panel.index('id="petInput"'))

    def test_assistant_input_respects_ime_and_keeps_pending_questions(self):
        self.assertIn("e.isComposing || e.keyCode === 229", self.html)
        send = self.html[self.html.index("function sendInput()"):self.html.index("function growInput()")]
        self.assertLess(send.index("if (pet.busy"), send.index("input.value = ''"))

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

    def test_profile_visuals_use_explainable_evidence_sections(self):
        self.assertIn("/api/profile/insights", self.html)
        self.assertIn('src="/profile-ui.js"', self.html)
        self.assertIn('href="/profile.css"', self.html)
        self.assertIn('aria-label="用户画像"', self.html)
        self.assertNotIn('id="profileActivityTotal"', self.html)
        self.assertNotIn('id="profileInterestScore"', self.html)
        self.assertNotIn('id="aiSummaryPanel"', self.html)
        self.assertNotIn("Math.random()", self.html)

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
        render_start = self.html.find("function renderPage")
        render_end = self.html.find("function ", render_start + 1)
        render_block = self.html[render_start:render_end if render_end >= 0 else None]
        self.assertIn(
            "const vp = page.getViewport({ scale: R.renderedScale || pageScale(page) });",
            render_block,
        )

    def test_pdf_layout_sets_tree_scale_before_lazy_page_observers(self):
        scale_line = "const usedScale = R.fit ? pageScale(R.pages[0]) : (R.renderedScale || R.scale || 1.2);"
        self.assertIn(scale_line, self.html)
        self.assertIn("R.renderedScale = usedScale;", self.html)
        self.assertLess(self.html.find("R.renderedScale = usedScale;"), self.html.find("for (let i = 0; i < R.pages.length; i++)"))

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
