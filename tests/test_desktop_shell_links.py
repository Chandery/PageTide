"""Windows shell: target="_blank" links and window.open reach the default browser instead of being dropped.
WebView2 asks for a new window (no navigation event), which Tauri refuses silently without a handler. The Rust
code is only compiled by the Windows CI job, so this reads the source."""
import re
import unittest
from pathlib import Path

MAIN = (Path(__file__).resolve().parents[1] / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")


class NewWindowLinkTests(unittest.TestCase):
    def test_windows_registers_a_new_window_handler(self):
        block = re.search(r"#\[cfg\(windows\)\]\s*let window = window\.on_new_window\(move \|url, _features\| \{(.*?)\}\);",
                          MAIN, re.S)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn("if url.origin() != new_window_origin", body)       # our own origin never opens externally
        self.assertIn("open_external(&url)", body)
        self.assertIn("NewWindowResponse::Deny", body)                    # never a second app window
        self.assertIn("window.build()?;", MAIN)

    def test_open_external_still_accepts_only_http_and_https(self):
        self.assertIn('matches!(url.scheme(), "http" | "https")', MAIN)


if __name__ == "__main__":
    unittest.main()
