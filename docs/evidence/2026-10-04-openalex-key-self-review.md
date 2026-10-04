# Self-review: 2026-10-04-openalex-api-key

Implementing agent's own review; not independent. Secret handling is a critical path.

- The real key was pasted by the owner in chat. It was not written to any repository file, test, command or log by this unit; tests use a dummy value. It exists in the session transcript, which the owner has been told.
- Storage: own file `openalex.key` in the data directory, created with mode 0600, `OPENALEX_API_KEY` environment variable takes precedence, never written to settings.json (test), never returned by `/api/settings` (test), status reports only configured/source.
- Transmission: Authorization bearer header, https and host exactly `api.openalex.org` only (tests include lookalike hosts and http); added as an unredirected header so a redirect cannot forward it; never in a URL, so cache keys (test) and error messages (test) cannot contain it. PDF fetching has no access to the key.
- Validation: 8-256 characters of `[A-Za-z0-9._~-]`; whitespace/newlines rejected before anything is written (test).
- Not verified: that OpenAlex accepts the Bearer header on real requests (docs say it is equivalent to api_key); the real allowance with a key; whether mailto still matters; the settings page in a running app. The sandbox cannot reach the API and the real key was deliberately not used.
