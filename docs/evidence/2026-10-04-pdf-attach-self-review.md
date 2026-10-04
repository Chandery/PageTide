# Self-review: 2026-10-04-pdf-attach-and-landing

Implementing agent's own review; not independent. A new route and a state-changing file move are critical paths.

- Attach reuses the existing, already-tested upload (`/api/seeds/pdf`: same-origin check, 60 MB cap, `%PDF` check, content-addressed `imports/<sha256>.pdf`) and `take_imported_pdf` (strict 64-hex id, moves the original bytes untouched). The paper is validated before the file is moved, so a bad key leaves the upload in place (test).
- Nothing is deleted: a previously downloaded file stays on disk; the `pdfs` row points to the newest copy (test).
- The pdf_id is the SHA-256 of the bytes, so the recorded sha256 is exact without rereading the file.
- No new outbound request. The landing-page link is opened by the user's browser/OS (target _blank, rel noreferrer); the app does not fetch it. Only https landing pages are offered.
- The attach route returns 400 with a message for unknown paper, malformed id, expired upload, or non-PDF; the UI shows it and records nothing (browser check).
- Evaluation status: E-PDF-ARCHIVE set to passed on self-run evidence only. Byte-range resume is not implemented and the evaluator's "retry/resume" is read as one bounded retry; this reading is stated in the evaluation text so the owner can disagree.
- Not verified: the Tauri window (same static pages checked in a browser), OS-level opening of the landing-page link inside the desktop shell, Unpaywall value.
