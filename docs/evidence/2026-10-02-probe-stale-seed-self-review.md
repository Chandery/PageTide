# Self-review: 2026-10-02-probe-stale-seed

Scope: tools/data_probe.py 404 handling, one seed identifier, one DOMAIN.md line, one regression test.
This is the implementing agent's own review of tool behavior, not an independent review and not a statement about recommendation quality.

- Behavior: 404 raises NotFound immediately (no retry); only the explicit-ID seed path catches it and records status not_found with a `+http_404` resolution suffix. Other failures (429, network) still retry and still raise.
- No silent substitution: a 404 seed is not replaced by a title search; the seed ID itself was changed in seeds.json on evidence from the owner's live curl (single exact-title match).
- Privacy/budget: no model call; only public metadata requests; no private seed/profile IDs sent anywhere new.
- Not verified: live probe rerun after the fix; app/sources.py search_works under OpenAlex fulltext search semantics; whether OpenAlex bills anonymous calls.
