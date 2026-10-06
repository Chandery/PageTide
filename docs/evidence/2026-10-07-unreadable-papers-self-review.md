# Self-review: no recommendation for papers with no abstract and no PDF (2026-10-07)

Implementing agent, not independent.

- Rule (App.build_batch): a paper is a candidate only if it has an abstract (non-blank), or a PDF stored on disk (`pdfs`), or a PDF source known to be available (`pdf_availability` is "direct" or "page"). The same test applies on a learning map and without one. Papers stay in the project and still count for the profile, the map and the library; only the daily recommendation skips them.
- The reader's own wording was "无摘要且无 pdf"; I read "无 PDF" as no PDF source at all ("none"), so an open-access landing page counts as a way to read it.
- Mutation check: removing the filter made the new tests fail.
- No model call, no token, no migration. Not measured: how many papers of the owner's library this removes.
