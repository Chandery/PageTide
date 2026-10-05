# Self-review: 2026-10-05-overview-placeholder

Owner report (screenshot): in the project overview on a large display, projects not opened in this session show a tall narrow column with the title one character per line. Cause: the placeholder page's content box had max-width 1200 px and also side padding of (100% - 1200px)/2, which collapsed it to 0 px on windows wider than about 1260 px (the problem predates the large-screen change but grows with window width). Fix: one line of CSS, centre by padding only. The live thumbnails (clones of the page you are on) were already centred and are unchanged.

Weak spot: checked by reading layout boxes in a Chromium-based preview, not by comparing a picture, and not in the Tauri/WebKit window.
