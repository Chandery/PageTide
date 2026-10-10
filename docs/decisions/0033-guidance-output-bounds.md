# ADR 0033: Keep project guidance replies complete within the existing output contract

2026-10-09; task `FIX-GUIDANCE-OUTPUT-BOUNDS`; follows [ADR 0032](0032-guidance-json-protocol.md).

The project-guidance screenshot showed a local fallback beside “AI reply truncated”. The provider response had reached the existing 500-token output limit, and an earlier system example also encouraged the model to copy placeholder graph nodes. The gateway correctly discarded incomplete JSON, but the UI presented the local fallback with an assistant label and the old reason suggested shortening the user input.

The compact system example now contains no placeholder graph. It states the string-only bounded fields, allows a concrete graph only when needed, and forbids placeholder/object values. The parser still rejects malformed objects and invalid graphs. When a provider returns complete string arrays that exceed the small keyword/query limits, it keeps only the permitted bounded prefix; choices are kept to three strings and 60 characters. This is deterministic local bounding, not acceptance of a partial response. A response with `finish_reason=length` remains rejected and the saved draft is preserved.

The guided chat labels a local fallback “本地整理” so it cannot be mistaken for a partial AI answer. The failure reason identifies the output limit and incomplete structured draft. The input/output contract remains 1200/500, one request per click, no retry loop, no new provider, and no new data exposure.

The isolated development ledger recorded 14 real DeepSeek development calls across Chinese and English short/constraint cases plus a second turn. All 14 returned complete responses, parsed as AI turns, and had `finish_reason=stop` (or an omitted equivalent); the largest measured total was 426 tokens. This is response-contract evidence for these cases, not a general quality, scientific-correctness, tokenizer-parity, billing, or release claim.
