# Self-review: 2026-10-04-pdf-acquisition

Implementing agent's own review of tool behaviour; not an independent review and not a statement about recommendation quality.

- Privacy: outbound requests are OpenAlex lookups by the stored paper ID, plus robots.txt and the PDF from the source host. The contact email goes only into the OpenAlex `mailto`, never to PDF hosts or a User-Agent. No seed list, profile, note or full text leaves the machine.
- Paywalls and credentials: 401/403 are reported and not retried; nothing sends credentials; robots.txt disallow is reported, not bypassed. Only https, including redirects.
- Rate limits: arXiv floor 3 s, robots Crawl-delay honoured up to 60 s (arXiv currently 15 s); one retry for 429/5xx; Retry-After wait bounded to 10 s. A first download is never delayed.
- Integrity: temp file then atomic rename; 60 MB cap checked by header and while streaming; `%PDF-` required; sha256 recorded; unchanged content reuses the file, changed content keeps the old file.
- Data: migration 005 only adds nullable columns; the existing pre-vN backup applies; the `pdfs` row for user imports now records `source_kind=user_import`.
- Behaviour change to note: a paper that already has any `pdfs` row with an existing file is now returned as cached without any request (previously only an arXiv-named file counted). `refresh=True` forces a new download.
- Bug risk checked: a failed download returns a result and never raises for source problems; the reader previously showed no reason, now shows one.
- Not verified: real downloads; OpenAlex OA values and coverage on real records; the reader and settings UI in the app; the arXiv access policy beyond robots.txt.
- Gap against the approved plan: no manual "attach a PDF to an existing paper" entry (plan step 4 mentioned it as a fallback); the reader shows the reason only.
