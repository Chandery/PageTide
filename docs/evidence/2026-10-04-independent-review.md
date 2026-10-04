# Independent review: PDF acquisition and OpenAlex key (2026-10-04)

Reviewer: two separate read-only code-review agents, each started with a fresh context and no access to the author's reasoning (same model family as the author; not a human reviewer). Pass 1 reviewed commits 1f5ada9..aba281e; pass 2 verified the author's fixes in the working tree. The owner may still want a human review.

## Pass 1 findings (verdict: not ready) and disposition
1. HIGH, shared fetcher state lost: server.make_app builds a new App per request, so the per-App Fetcher forgot pacing, Crawl-delay and robots every time (verified: the packaged server logs one App start per request). FIXED: pdf_fetch.shared_fetcher (one per data dir) plus per-host locks; tests with two App objects, and a two-thread test that fails without the lock (mutation-checked).
2. MEDIUM, non-OSError failures (InvalidURL, UnicodeError, IncompleteRead, BadStatusLine) escaped fetch/download_pdf. FIXED and tested; a malformed first candidate no longer stops the next.
3. MEDIUM, redirect hops had no robots, pacing or public-host check; userinfo/port made separate host identities. FIXED: every hop must be https on a public host and passes robots and pacing; host identity normalised.
4. MEDIUM, replacing a PDF lost the old copy's provenance. FIXED: append-only pdf_versions (migration 006, backfilled) and Store.pdf_history.
5. LOW/MEDIUM, only two POST routes checked Origin. FIXED: every POST and DELETE; tests for all write routes.
6. LOW, attach upload is single-use and moves before the DB write. NOT CHANGED (accepted, documented in ADR 0011).
7. LOW, migration 005 swallowed every OperationalError. FIXED: only "duplicate column"; tested with a locked-database stub.
8. LOW, robots 429 treated as no restrictions. FIXED (429, 5xx and 3xx are unavailable).
Reviewer's sub-suggestion not adopted: counting the robots.txt request toward pacing. Reason: it would make the first arXiv download wait 15 s; the robots fetch is not counted, as is usual for crawlers.
Confirmed sound by the reviewer: OpenAlex key handling (header only, https and exact host, unredirected, never in URL/cache key/error/settings/response), path safety (stem_of, 64-hex upload ids, DB-only file serving), size/%PDF checks, stale-row handling, migration 005 idempotence, XSS escaping of the landing-page link.

## Pass 2 (verification of the fixes)
Verified correct: items 1, 2, 4, 5, 7, 8 and the removal of the contact-email feature (no dangling references; cached URLs unchanged). Item 3 partly fixed; new residual findings, all FIXED afterwards and tested:
- D1: alternate IPv4 spellings (2130706433, 0x7f.1, 127.1, 017700000001, 0) and trailing-dot or single-label hosts passed the host guard. Now a host must be a public IP literal or a dotted DNS name with a non-numeric last label; trailing dots stripped.
- D2: no test proved fetch() passes the redirect gate to the opener. Added (mutation-checked).
- D3: robots answers cached forever; 3xx from robots treated as allow-all. Now 24 h TTL and 3xx is unavailable.
- D4: history order did not show the current copy for A,B,A. Now a copy returning after another is a new last entry.
- D5: public IPv6 literals failed at the robots URL (no brackets). Fixed. NAT64-wrapped loopback (64:ff9b::7f00:1) is not covered (only reachable on NAT64 networks).
Not covered by design: a public-looking DNS name that resolves to a private address (no DNS resolution is done).

## Not verified by the reviewers
The live Tauri webview Origin header (reasoned from the Host check), any network behaviour, and the second pass did not run the full suite.
