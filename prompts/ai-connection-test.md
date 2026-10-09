---
contract: implemented
operation: ai_connection_test
---
# operation: ai_connection_test

## Fixed user message

Reply only OK.

## Scope and lifecycle

One explicit Settings “测试AI” button click sends this fixed English message
through the single Gateway. It carries no project, paper, note, profile or
conversation content. Input cap768 covers the complete encoded request and
framing; output cap16. Reference128/4 is planning arithmetic, not measured usage.
The configured runtime model and thinking-disabled contract are unchanged.

Only this operation accepts an optional temporary API key. The key is used in
the provider Authorization header and is never saved, put into the prompt,
ledger or returned diagnostic. None uses the existing configured key; blank or
invalid supplied keys refuse before a request. Only this explicit test can run
while the AI switch is off; it never changes that switch.

One call only, no retry or fallback. Known usage is reconciled; unknown or
in-flight usage retains its reservation across restart. HTTP auth/rate/balance
rejections release a known unused reservation; HTTP5xx/network uncertainty does
not. The response does not expose provider prose or raw HTTP error bodies.
No paid developer call was made for this contract.
