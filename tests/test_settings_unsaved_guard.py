"""Leaving the settings page with unsaved edits asks first."""
import pathlib
import unittest

HTML = (pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "settings.html").read_text(encoding="utf-8")


class UnsavedGuardTests(unittest.TestCase):
    def test_loaded_state_is_the_baseline(self):
        self.assertIn("savedState = formState();", HTML)

    def test_cancel_and_back_link_ask_before_leaving(self):
        self.assertIn("leave('/')", HTML)
        self.assertIn("设置有修改还没保存", HTML)

    def test_browser_close_or_reload_is_guarded(self):
        self.assertIn("window.onbeforeunload", HTML)

    def test_a_typed_key_is_compared_by_presence_only(self):
        self.assertIn("el.type === 'password' ? !!el.value.trim()", HTML)


if __name__ == "__main__":
    unittest.main()
