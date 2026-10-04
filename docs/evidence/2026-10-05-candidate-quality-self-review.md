# Self-review: 2026-10-05-candidate-quality (Route Mode slice 1)

Implementing agent's own review; not independent.

- Window: creation candidates default to the last 10 years, the page has an explicit "不限年份" toggle that is sent as `all_years` (server passes it through, tested). The refreshed feed uses a relative five-year window instead of the fixed 2024-01-01 (which would have kept shrinking the window); both lengths are proposals.
- PDF preference is block-wise (6 results): inside a block direct-PDF papers come first in relevance order, nothing crosses a block boundary, nothing is dropped, and the date-ordered feed is not regrouped. This is a presentation preference, not a filter.
- Status is a label, not a claim of permission: "direct" means arXiv or an https link OpenAlex reports; the download path still obeys robots, paywalls and the 403 handling from ADR 0011.
- No new outbound data and no model call. Only fields already fetched (open-access data) are used.
- Not done on purpose: an "open access only" filter. The live numbers show it would remove most materials-science candidates; it can be offered later as a toggle if the owner wants it.
- Weak spots: the 10-year and 5-year windows and the block size 6 are unvalidated defaults; badges for papers stored before open-access data was kept show "none" until a refresh or download fetches their record.
