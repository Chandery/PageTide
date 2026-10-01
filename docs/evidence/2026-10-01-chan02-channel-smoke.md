# Channel smoke 2026-10-01T23:12:38+08:00

Live public queries, one per channel and script. `error` rows are failures, not passes.

Not a verdict on the services: this run was made inside the agent sandbox, whose network policy denied export.arxiv.org, api.openalex.org and api.crossref.org ("user denied"), so every row is the sandbox refusing the connection. The live smoke (E-CHANNELS) stays `not_run` until it is run outside the sandbox.

| channel | term | status | results | first title | error kind |
|---|---|---|---|---|---|
| arxiv | world model | error | 0 |  | network_error |
| openalex | world model | error | 0 |  | network_error |
| openalex | 数字人文 | error | 0 |  | network_error |
| crossref | world model | error | 0 |  | network_error |
| crossref | 数字人文 | error | 0 |  | network_error |
