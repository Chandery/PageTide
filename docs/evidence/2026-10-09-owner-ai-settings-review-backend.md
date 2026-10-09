# 2026-10-09 independent title/backend review

Reviewer: `organization_ai`; implementation authors for this scope: `ai_guide` (title helper/gate) and `root` (App/HTTP integration). Review status: **passed**, with two reproduced P2 findings corrected and independently rechecked. This review excludes the gateway, budget registry, budget script and budget documentation written by this reviewer; their independent review belongs to `ai_guide`. It does not certify the desktop build or a live provider connection.

## Scope and findings

The review traced original provider title/report fields through stored paper metadata, `App._paper_language`, current-PDF verification, `eligibility.evaluate`, recommendation selection and the final batch transaction. A title warning is derived locally from the whole current title; it neither rewrites the stored title/source language nor asserts a PDF body language. English-only projects hold an unverified majority non-Latin title with an English source report. Humanities projects allowing multiple languages retain the source/body/warning distinctions. Verified current-PDF English takes precedence; verified Chinese is rejected under English-only policy, and replacing/changing the PDF invalidates the old proof. Existing callers that provide only `fulltext_language` retain the legacy priority contract; the production App path always supplies explicit status and current-file proof.

- **P2, closed — mathematical Latin fonts were mistaken for non-Latin.** Before correction, `𝐖𝐨𝐫𝐥𝐝 𝐌𝐨𝐝𝐞𝐥𝐬 𝐟𝐨𝐫 𝐑𝐨𝐛𝐨𝐭𝐢𝐜𝐬` and its mathematical sans-serif form counted 22/22 letters as non-Latin and were rejected as `title_language_unverified`. Unicode character names contain `MATHEMATICAL`, rather than `LATIN`. The author now applies NFKC to each character solely for the derived count. Independent replay yields 0/22 non-Latin and eligibility for both English titles; Chinese and Greek controls still yield 13/13 and the verification hold. The real App regression confirms the original styled title survives in storage and the recommendation card. No whole-title normalized copy is retained and no model is called.
- **P2, closed — the busy connection test returned HTTP 503.** Independent HTTP regression reproduced 503 instead of 409. Later imports of `Conflict` inside `do_POST` made that name local throughout the function, so the earlier new exception handler raised `UnboundLocalError`. The root implementation now imports `OrganizationConflict` at module scope and catches that distinct alias for `/api/ai-test`. Independent rerun confirms the busy response is 409 and there is no second attempt.

Read-only review of `App.test_ai_connection` and the HTTP branch confirms one explicit fixed-test method call, optional transient credential validation, no key save or switch change, same-origin/session and body-shape guards, and a claim preventing simultaneous duplicate tests. The response uses the configured provider/model, whitelists nonnegative integer usage fields, omits provider content, sanitizes failures through the existing cause helper, and exposes unknown reservations separately with measured usage/USD null. Tests use synthetic secrets in content/model/usage/errors to verify that these are not returned. This is a review of the feature integration, not an independent rating of the gateway implementation.

## Independently executed evidence

All databases/files were disposable; provider transport was mocked. No formal user library, paid development call or external request was used.

| Check | Actual result |
| --- | --- |
| `python3 -m unittest tests.test_title_language_gate` before font correction | 13 tests passed; the separate mathematical-font replay then exposed the uncovered P2 |
| Same title suite after correction | 15 tests passed, including current-PDF/hash replacement, route/maintenance gates, stale-title transaction rejection, source preservation and styled-title card behavior |
| Independent four-title replay after correction | Two mathematical-font English titles eligible; Chinese/Greek titles held; source/title fields unchanged |
| `PYTHONPATH=tests python3 -m unittest tests.test_ai_connection` before alias correction | 11 tests, one failure: busy HTTP 503 versus expected 409, with `UnboundLocalError` reproduced |
| Same App/HTTP suite after alias correction | 11 tests passed; 2.128 seconds |

Local temporary logs: `/tmp/pdh-title-independent-after.txt` and `/tmp/pdh-ai-connection-independent-after.txt`. The results above are included here so the evidence does not depend on retaining those temporary logs. The first connection-suite invocation without `PYTHONPATH=tests` encountered the existing `recommendation_fixtures` import-path dependency; it was rerun with the repository test path, not counted as behavior coverage.

Not measured by this review: provider correctness, actual API billing, PDF language detection quality, live connection latency, UI visual quality, full-suite release status or desktop build. The script heuristic is a warning/hold rule, not a body-language detector; a translated or bilingual title can still require body verification. No remaining blocking defect was found in this reviewed backend scope.

## Late App receipt correction

`creation_ui` independently found that a pre-send ledger-write exception could be presented by App as unknown usage with a retained reservation despite zero transport calls and no ledger. The gateway correction was authored by this reviewer and is explicitly excluded from this independent review; `ai_guide` reviews it separately. This follow-up reviews only the root's App receipt/translation correction: the generic exception path now reports uncertainty without inventing `usage_reserved` or a reservation, while structured known pre-send failures report unused/no-send. Confirmed pending reservations remain present with measured usage/USD null. An HTTP rejection plus failed release-recording reports both the provider rejection and local accounting problem, without exposing exception text.

Independent command (synthetic gateway receipts and disposable App databases):

```sh
PYTHONPATH=tests python3 -m unittest tests.test_ai_connection.AIConnectionTests.test_presend_accounting_failure_is_known_unused_without_reservation tests.test_ai_connection.AIConnectionTests.test_unexpected_failure_does_not_invent_a_preserved_reservation tests.test_ai_connection.AIConnectionTests.test_postsend_accounting_failure_keeps_recorded_reservation_unknown tests.test_ai_connection.AIConnectionTests.test_rejected_request_with_release_failure_explains_both_causes
```

Actual result: **4 tests passed**, 0.026 seconds; `/tmp/pdh-connection-receipt-independent.txt`. No provider call, retry or formal user data was used. These are App receipt/diagnostic checks, not a claim of live accounting quality. No remaining blocking defect was found in the updated App response handling.

## Reviewed source snapshots (SHA-256)

```text
app/paper_language.py 415b66744990872e0ed67c430b5fe201551f7d29a3422af8b09848127673067b
app/eligibility.py 218e8753ddba9db17445cd34f5df8ef367b28e8b17d0f8825c6ecdbb9ac7f078
app/service.py 9c934551c89ddaa60647b6072a9648645df773071ea5b1aa317d6d53133041a1
app/server.py f27bdd22034a688b2d244d25823a4acd09d0fb80505c30bd28be19740ebc0528
tests/test_title_language_gate.py 21371418bd0b61643444e0e422c7a9218469e5e7fea87af6200a0bb25ef34f98
tests/test_ai_connection.py afbb28596d2e43444f40d60f097b8213f593cee14d3e3ed6ea6a949bbd2e9ce5
```
