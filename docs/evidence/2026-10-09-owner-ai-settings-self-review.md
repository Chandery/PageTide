# 2026-10-09 owner AI settings — self-review

Reviewer: root. Class critical (gateway policy, prompt/operation, IPC). Baseline local main `f745009`; owner work from the preceding unit was committed locally before this coherent unit. No remote operation or formal user data change.

## Specification and cost

Human authorization is quoted in task `FIX-AI-SETTINGS-TITLE` and ADR0031. Runtime aggregate day/month token and USD caps are disabled by the registered flag; effective limits are null, existing usage retained. Developer limits, existing operation approvals/counts, single-call complete-input/output bounds, default switch state, one gateway and no retries remain. Core daily required models remain0. Aggregate optional spend is unbounded/unknown, never0. New explicit fixed test: registered768/16 envelope, reference128/4; arithmetic $0.0002496 peak cache-miss per call, not actual billing. General release approval remains false.

The test endpoint has existing desktop authentication, host/same-origin protections,8KB length guard, optional-string-only schema and cross-instance manual-test lock. The temporary key is validation-only and used solely in the fixed provider header. It is not saved, logged, returned, put into messages or allowed as an ordinary operation override. Testing while disabled leaves the marker unchanged. The result excludes raw prose, reported model, response body and exception text; known usage fields are whitelisted. UI stale-input/late-response checks, elapsed timer, pending button and key masking support this lifecycle.

Accounting failures are distinct from provider/network failures. Initial reservation write failure refuses before transport with no invented spend/reservation; after-send failure retains the actual recorded reservation and labels uncertainty. A generic exception cannot prove a saved reservation. A rejected provider response plus failed release records both causes. Known prompt+completion usage without total is displayed as their sum; unknown without a saved reservation does not claim one. Independent failed-first findings drove these corrections.

Title screening is deterministic, offline and linear in current full title length. Per-character NFKC only informs script counts, preserving source title/report. Strong nonLatin-majority and source English conflict is excluded for English-only projects until current-PDF verification. Current verified language has priority; stale PDF/hash, title changes and snapshot races retain existing gates. Multi-language projects may retain a warning. This is a heuristic screen, not general language classification or a proof of scientific quality.

## Regression and review findings

New App/HTTP and UI tests failed before implementation. Early integration caught a missing service module import. Independent reviews caught mathematical Latin fonts incorrectly flagged and a Python local import shadow making the busy endpoint return503; each corrected and rechecked. Later actual HTTP→App→Gateway probes caught initial accounting failure mislabeled network/reserved, then the known-usage UI edge case. An additional entry-lock I/O failure was independently reproduced; structured pre-send failure and a separate exit-lock result preserve already confirmed usage. Dedicated staged-failure regressions were added. Root and reviewers reran affected checks; final full counts/build are in the companion checks evidence.

First full2095 Python run ended with one error: an old Chinese lexical-ranking fixture deliberately assigned English metadata and an English-only policy. It now explicitly declares Chinese policy/report and retains the same ranking assertion; dedicated title-conflict tests still assert rejection. An oversized-body test was made deterministic by sending only an oversized Content-Length, verifying pre-read413 without unread payload resetting the macOS socket. Production body enforcement is unchanged.

Independent reviews cover authored boundaries separately: organization_ai reviews title/backend, creation_ui reviews App/API/Gateway integration, ai_guide reviews gateway/budget/UI and root follow-up changes. Self-review does not substitute for these documents. Final checks evidence also captures the source/bundle fingerprints and release gates that remain unpassed.

## Limitations

No live paid model call in this unit, no formal library read/write/reset, no migration or new data schema. Browser verification used a disposable no-key/off dataset and confirmed a specific inline failure, with zero outbound model requests. Package verification uses separate temporary datasets, synthetic papers and no key. Mocks and no-key checks do not establish live authentication/provider quality, scientific recommendation benefit, tokenizer/invoice parity, native window acceptance or all-product release readiness. Previous unrelated live-test usage remains in its preceding work-unit record.
