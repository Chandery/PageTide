# Self-review: 2026-10-05-auto-maintenance (Route Mode slice 2)

Implementing agent's own review; not independent. Touches the no-debt requirement, so read against R-NODEBT / E-NO-DEBT / E-OFFLINE.

- Debt: there is no clock-driven state. A skipped week produces one refresh and one batch for the day you open the app, not seven. Nothing counts unread or pending papers; the status object has times, the chosen frequency and the last error, and a test forbids count-like keys.
- Models: maintenance never calls the gateway (tests make any call raise). The batch is only the five papers; AI summaries stay behind the existing user toggle and are not started here.
- Network: a refresh is public OpenAlex metadata with the project's keywords (the disclosure from ADR 0012 applies). Failures are bounded (30-minute retry gap), visible on the page, and do not block building the batch from papers already in the project.
- Frequency: finally reads the existing 更新频率 setting (daily / weekly / manual); manual means nothing happens automatically.
- Weak spots: "today" for the batch is a label (`run_date`), so a manual batch made around midnight UTC could be counted as yesterday's or today's; a refresh is skipped only after a successful one, so a persistently failing network is retried every 30 minutes while the app is opened; the server-side lock is per process.
- Settings keys `timePreference`, `recommendCount`, `decayWindow`, `newPaperBoost` are still stored and unused.
