# Self-review: 2026-10-04-migration-collision-fix

Implementing agent's own review; not independent. Migrations are a critical path.

- Per-number tracking: `applied_versions` reads every recorded number; a migration runs when its number is absent. Older databases (1..N contiguous) behave as before. A database recorded by the other branch (1..5) now runs 6 and 7. A database recorded by this branch's old numbering (5 = PDF) gets 6 (idempotent: duplicate-column errors ignored) and 7.
- Reserved slot 5: never run, never recorded, never counted as pending; calling it raises, so it cannot silently succeed.
- Atomicity: `BEGIN` before each migration and `rollback()` on any exception; SQLite DDL is transactional, so a crash after CREATE TABLE no longer leaves the table behind (test with an injected failing migration). Earlier migrations contain no internal commit.
- Backward compatibility: `get_schema_version` is still the maximum, used for the backup name; the channels branch opening a database recorded 1..7 sees no pending work for its own five migrations and ignores the extra tables.
- Backup: Store.init still backs up before pending migrations and never overwrites an existing `.pre-vN.bak`; on the real database the existing `.pre-v5.bak` (taken just before the failed attempt, content identical to the pre-state) is reused.
- Why it was missed: all earlier tests used fresh temporary databases; none reproduced a real database that had run another branch's migration. The new test builds that state.
- Not verified: opening the rebuilt app on the real data directory (not done by the agent); the merge with the channels branch.
