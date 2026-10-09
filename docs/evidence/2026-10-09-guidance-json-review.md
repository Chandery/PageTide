# Independent review: project-guidance JSON contract

Date: 2026-10-09. Task: `FIX-GUIDANCE-JSON-PROTOCOL`. Change: `2026-10-09-guidance-json-protocol`. Baseline: `06b23be`. Reviewer: `creation_ui`, who wrote no production source or committed regression tests in this unit. Review status: **passed for this bounded fix; no blocking finding**. Desktop build, signed-package acceptance and broader product gates belong to the owner agent's separate evidence.

## Finding and resolution

The baseline project-guidance system contained a JSON-shaped example but never the word `json`, while its actual Gateway envelope enabled `response_format=json_object`. The settings connection test uses a fixed ordinary text request and therefore does not validate that guidance contract. [DeepSeek's official JSON Output guide](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) was read directly on this date; it requires the word json and a format example in a system/user prompt. The actual system now starts with `Return JSON`; all brainstorm rules and the compact output example remain present.

The historical screenshot's provider response body was not captured. The source defect and protocol-aware synthetic reproduction support this diagnosis; they do **not** prove the exact historical upstream message or a successful live provider request. No live model calls were made during this unit or review.

Gateway now reads at most 8193 bytes only for HTTP 400, accepts at most 8192 bytes of valid UTF-8 JSON, and recognizes one narrow missing-JSON-instruction message. It returns only the fixed `json_instruction_missing` classification, never raw message/code/param/body, key, exception prose or request text. Malformed, oversized, unrelated and unreadable errors retain their generic status. HTTPError streams close even when the diagnostic read fails. Known 4xx release accounting remains intact; 5xx skips body parsing and keeps the unknown reservation. Connection-test release-write failure also keeps its real reservation and safe classification.

The creation service converts this classification into a fixed Chinese/English `request_format` cause. Actual App→Gateway private probes confirmed that both languages and both creation modes keep the cause on the latest assistant entry, retain original goal, user-edited keyword and learning-stage rows, leave the accepted-turn count unchanged, create no project and release the known rejected request. The current quick and guided UI handlers both use the actual `turnMeta` renderer; its extracted production function displays this cause beside the current answer, escapes text and does not invent a pending charge for known 400.

## Checks executed independently

All Python checks unset formal data/key overrides, use temporary explicit App data directories and synthetic credentials, and load a guard that blocks any unmocked DeepSeek request. The private probe also installs a fail-closed transport before App construction. No formal user database, key file or usage ledger was opened for the review. Private synthetic data was temporary. Logs below remain under ignored `.local/guidance-json-verification/`.

```sh
env -u PAPERDIGHELPER_DATA -u DEEPSEEK_API_KEY -u PAPERDIGHELPER_KEY_FILE PDH_DEV=0 PYTHONPATH=.local/creation-ai-ux-verification/network-guard:tests:. python3 -m unittest tests.test_guidance_json_protocol tests.test_gateway_http_diagnostics tests.test_guidance_error_diagnostics tests.test_creation_brainstorm tests.test_project_chain tests.test_ai_failure_explanations tests.test_gateway_policy tests.test_gateway_budget -q
```

Result: exit 0, **102 tests passed in 0.720 s**; log `independent-review-tests.txt`. Coverage includes the actual App→Gateway old-contract 400 followed by one explicit fixed-contract retry, all language/mode combinations, full-wire bounds, preserved originals and truncation notice, diagnostic read/close failures, exact 8192-byte boundary, malformed/nonfinite/oversized JSON, secret non-disclosure, 4xx release, 5xx pending and connection accounting failure.

```sh
env -u PAPERDIGHELPER_DATA -u DEEPSEEK_API_KEY -u PAPERDIGHELPER_KEY_FILE PDH_DEV=0 PYTHONPATH=.local/creation-ai-ux-verification/network-guard:tests:. python3 .local/guidance-json-verification/independent-review-probe.py
node .local/guidance-json-verification/independent-review-render.cjs
node --test tests/test_creation_brief_page.cjs tests/test_creation_review_fixes.cjs tests/test_creation_quit_fixes.cjs
python3 scripts/budget.py --check
git diff --check
python3 scripts/harness.py impact
```

All exited 0. The private App probe passed four language/mode cases, one synthetic request each, all released: synthetic charged tokens/USD 0; live provider calls 0. Render probe passed the actual production function checks. Existing UI behavior regressions: **22 passed, 0 failed**. Budget parity and whitespace checks passed; impact correctly classified the unit as critical. These are offline checks, not provider billing or output-quality measurements.

## Scope, limits and other JSON operations

The +12 UTF-8 bytes are not a measured token increase. Full-wire input admission remains 1200, output remains 500, thinking stays disabled, and quick/guided limits remain 1/6 accepted turns. No operation, external scope, automatic retry, model fallback or AI-switch exception was added. Optional memory still cannot shrink an already admitted current answer. Long BMP Chinese goals/answers fit the unchanged conservative bound; complete originals and omitted-context notices remain local.

An independent 1/2/3/4-byte-character probe found that extreme supplementary Unicode can still exceed the bound at the excerpt floor and be refused before sending. Loading the baseline contract reproduced the same 4-byte limitation. This is an existing limitation, not a new live 400 or a full-Unicode guarantee. The owner narrowed the prompt record and [ADR 0032](../decisions/0032-guidance-json-protocol.md) accordingly; both were re-read after that update. Large quote/backslash inputs also remain eligible for a local safe refusal. This review does not broaden that separate behavior.

Read-only inspection covered every other operation for which `request_envelope` enables JSON mode: `daily_triage` (service instruction), `route_growth_judge` (`growthproposal.SYSTEM`), `route_map_create`/`route_map_revision` (`route_revision.CREATE_SYSTEM`/`REVISION_SYSTEM`) and `category_review` (`category_review.SYSTEM`). All already contain an explicit JSON instruction. No changes were needed to those operations.

Live response quality, structured-map scientific correctness, actual token use and tokenizer/billing parity remain **not measured**. The core daily search, dedupe, ranking, profile, archive and database minimum remains zero model tokens. The unchanged optional 1200/500 peak cache-miss ceiling is arithmetic $0.00096 per attempt, not a measurement; runtime aggregate usage remains uncapped and unknown under the owner's prior instruction.

## Reviewed source hashes (SHA-256)

| File | Hash |
| --- | --- |
| app/gateway.py | 0bb166eac63ab19ae0c08d5166c7a35ec1beff5f9cf4ed5296c79dc35479aef8 |
| app/guidance_contract.py | 41a36808abbbde9136f9bcdfc23c4871547aa8d296789cd23489bc433c95ec13 |
| app/creation.py | 8c24f98a06eba61fab65e0311255673026ef7014ad5f1d2392c31111269a380d |
| prompts/project-guidance.md | e962a922b3ccef255ae3fd9d299e257eb32a5d72fae3b87633a73cfa32bc4047 |
| tests/test_gateway_http_diagnostics.py | 1e7c73bfd69ebe253a8ac120ef8df05066f911d31ea192071ccdff6c224b6f30 |
| tests/test_guidance_error_diagnostics.py | bc8dd12e57310464ce4b6dde08778aeea3fecfb8ca22b87707fcb50ed6c55bb1 |
| tests/test_guidance_json_protocol.py | ee638ec636fab03e6eefb38eb059309bdf7c2c6bb83505566b0e383d02e86fba |
