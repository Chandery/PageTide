# ADR 0006: Editable Library and Local Knowledge Graph

2026-09-14. Implementation requested by the owner ("实施计划"). This is not release approval.

## Scope

READ-01 and GRAPH-01: flat editable research directions, multiple memberships per saved paper,
versioned Markdown notes, project-local graph positions, classification preview and explicit apply.
The existing saved library is the corpus; paper/PDF identities remain unchanged. PDF reader changes,
highlights, citation ingestion and viewpoint inference are outside this slice.

## Reuse

- Cytoscape.js 3.33.1 (MIT), vendored locally, supplies the compound canvas and interaction engine.
- NetworkX 3.2.1 (BSD-3-Clause), compatible with the existing Python 3.9 build environment,
  supplies seeded Louvain communities over existing sparse TF-IDF similarities.
- Similarity is not citation or agreement. Automatic group names are keyword suggestions, not
  evaluated semantic categories. User edits remain authoritative.

Official references: [Cytoscape](https://js.cytoscape.org/),
[NetworkX version](https://pypi.org/project/networkx/3.2.1/),
[Louvain](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html).

## Data and Lifecycle

Additive SQLite organization tables preserve existing records and legacy notes. Back up before
initial migration. Notes append versions; conflicting saves must fail visibly without losing drafts.
Organization data is project-scoped; this single-project app uses stable ID `default`.
An undo log and JSON export retain human edits. Canvas proxies share one underlying paper note.

Classification runs in one local subprocess at a time, with a 120-second timeout and a bounded
saved-paper corpus. No network, model, weights, note upload or paid fallback. Stale corpus proposals
must be rejected. Missing dependencies fail explicitly. New HTTP writes reject foreign origins.

## Budget and Gates

Incremental runtime model use: 0 input tokens, 0 output tokens, USD 0. This is an architectural
property of this slice, not a measured full-app cost. Developer token use is unavailable.
Memory/performance on the 8 GB reference target and human classification quality remain unmeasured.
Independent review, behavioral persistence tests and macOS package verification are required before
release. READ-01/GRAPH-01 remain in progress until their broader acceptance criteria are met.
