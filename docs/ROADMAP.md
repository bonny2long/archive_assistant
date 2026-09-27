# Roadmap

## Done

- Core v1 locked; v2 Metadata Assist complete.
- AA-QA1 all-media acceptance and AA-SYSTEM1 scoped-object contract.
- Local NAS acceptance with Intake Watcher, Cleaner, and BM Radio (runbook v11, 2026-08-26).
- Quarantine lifecycle: restore, discard with reason, undo discard, disposition records for Cleaner (2026-09-26).
- Multi-disc albums and audiobooks grouped as one release; stray per-disc title or author tags tolerated with evidence (2026-09-26).
- Recovery dead ends removed; test-run rows can be retired with `repair_foreign_root_batches.py`.
- OVA specials routed to `Specials/`; release-folder noise cleaned from suggestions (2026-09-27).

## Next

- Scheduled scan of `ready`, so new downloads reach review without clicking Scan ingest. Approval stays manual.
- A read-only API for Cleaner to ask whether any batch from a source folder is still pending.
- Allow damaged recognized media into quarantine (needs a guard for folders shared by several batches).
- Optional local-AI naming suggestions, feeding the existing candidate system and never approving on their own.

## Later

- TrueNAS deployment: SQLite database on the fast NVMe pool, media on the rust-pool, dev tools and API docs disabled.

Cleaner owns all cleanup and deletion. Archive Assistant must not gain automatic cleanup or delete behavior.
