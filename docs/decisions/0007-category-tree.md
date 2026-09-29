# ADR 0007: Category directories with multiple paper memberships

2026-09-15. Owner explicitly requested editable existing categories and memberships,
deletable categories, nested directories and multiple subdirection memberships per paper.
Supersedes the flat-direction scope of ADR 0006, not its note/privacy/undo guarantees.

## Contract

- Categories form a rooted forest. Each category has one optional `parent_id`; old rows
  without it are roots. Paper membership remains a separate many-to-many relationship.
- Validate parents in the same project and reject self/descendant cycles atomically.
  Changing parent moves the category subtree without touching paper IDs or memberships.
- Parent filtering includes descendant papers, deduplicated by paper key. Counts use the
  same union; membership editing shows full paths and direct memberships only.
- Deleting a category removes only its direct membership links; direct child categories
  move to its parent (or become roots). Papers, PDFs, notes, descendants and other links
  are preserved. An in-app confirmation describes this effect; undo restores the prior state.
- Categories appear as compact one-line folder rows with hierarchy guides and counts; commands
  live in the visible per-row more menu. Single-paper editing uses checked boxes for
  existing links; bulk editing retains explicit keep/add/remove semantics.
- Graph shows ancestor categories and distinct hierarchy links, retaining one node per paper.
  Collapsing an ancestor hides its subtree; a paper with a visible membership elsewhere stays visible.

## Persistence and compatibility

`parent_id` is an additive field in the existing project JSON and export. No SQL schema rewrite
or backfill runs; old records are interpreted as roots. The existing transaction/CAS/undo log
covers parent changes and deletion, including graph positions. Automatic regrouping may not
remove a category that still has children. Older app versions do not implement this contract;
use the updated app when editing hierarchy. Export retains parent IDs; Markdown displays paths.

## Resource/privacy impact and evidence

Local deterministic code only, zero incremental model tokens/network requests/dependencies.
No PDF or notes are duplicated for multi-membership. Tree helpers use iterative traversal;
large/deep-tree UI performance remains unmeasured. Record tests, native/browser QA and independent
review in the category-tree change record; broad reading/release gates remain separate.

## Explicit suggestion acceptance (2026-09-16)

The UI sends `apply_mode: add` with an explicit selection and the validated preview fingerprint.
Add selected memberships even for already-classified/protected papers; preserve all prior links,
manual labels, parents and notes. Conflicting suggestion IDs allocate a distinct category and
retain source identity for idempotent repeat. Return actual membership/category/paper counts.
Empty selections fail; no-op repeats leave revision and undo history unchanged. Successful adds
are undoable and treated as explicit edits. Legacy automatic regroup protection remains unchanged.
