# Dataset deletion and retention acceptance — 2026-10-18

Dataset lifecycle management is deployed at <https://patternworks.32-237-44-97.nip.io/>. All existing datasets remain active without expiry. Local and AWS suites each passed **311 backend tests**, including 12 real Spark integrations; **14 frontend tests**, TypeScript and production builds passed. Results: [dataset-lifecycle-evidence.json](dataset-lifecycle-evidence.json).

## Usage and policy

1. Open **Delete / retention** beside a dataset. Review its parent, children, active or uncleaned tasks and CSV export count. **Show all dependents** opens a paginated searchable child list.
2. Active children and queued/running tasks block deletion; cancelled tasks block until cleanup finishes. No cascade deletion occurs. Handle children first.
3. Enter the complete dataset UUID. Original imports also require an explicit checkbox. The signed dependency review expires in five minutes; changed dependencies require another review. The server rechecks under a row lock.
4. Trash keeps data recoverable for seven days. In **Dataset location → Trash**, restore parents before children. Restore resets the policy to **Keep until I delete it**.
5. Processed datasets can opt into expiry in 7/30/90 days from saving the policy, with explicit acknowledgement. Original imports never auto-expire. All existing/new datasets default to Keep; saving Keep clears expiry.

| State | Access | Recovery / cleanup |
| --- | --- | --- |
| ACTIVE | Preview, processing and export allowed | Children/tasks postpone opt-in expiry |
| TRASH | Preview/processing/export blocked; download 410 | Restore before deadline; files retained pending eligible cleanup |
| PURGING | Access/restore blocked | Failed file removal retries later |
| PURGED | Content unavailable | Audit tombstone retained; no restore |

Cleanup runs approximately every 15 seconds after its other maintenance work. Each cycle handles at most 100 eligible expiries and 100 purges; blockers are excluded before the limit to prevent starvation. A parent cannot be purged until every child is PURGED. There is no force-purge UI.

## Safety and scope

- Lifecycle remains separate from processing status. Trash preserves task history.
- Source row locks serialize deletion and task creation; waiting creation rechecks ACTIVE. Multi-dataset retry/restore locks use UUID order. Workers reject unavailable sources. Dispatch stays outside database transactions.
- Signed reviews bind session, dataset and dependency snapshot. UUID/original confirmation, ownership and CSRF are enforced server-side. Unrelated sessions receive 404. History hides unavailable result/download links and disables unsafe retries.
- Purge removes this dataset's Parquet, SQLite index, CSV export attempts and leftover import directories. Stored rule/transformation previews, instructions/options, schema/metadata and job parameters are redacted. Filesystem errors leave resumable PURGING state.
- IDs, filenames, row counts, lineage and task audit states remain. S3, independent datasets, backups and previously downloaded files are unchanged. Shared Redis caches retain their existing one-hour TTL; this feature does not force-evict them.

## Verification

| Check | Result |
| --- | --- |
| Local full backend | 311 passed in 47.01 s; 12 real Spark integrations |
| AWS full backend, isolated test DB | 311 passed in 149.46 s; 12 Spark tests; test container 4 GiB, production API limit unchanged |
| Lifecycle subset | 33 passed, included in 311 |
| Final frontend | 14 passed in 271.981333 ms; TypeScript/Vite passed |
| Django/migrations | Checks clean, no missing migrations; 0010 applied in production |
| Two real PostgreSQL connections | Delete-first: waiting replacement API returns 409. Task-first: waiting deletion rejects the new reference |
| Safari | Blockers, original confirmation, Trash, restore and 7-day policy observed |
| Scheduled expiry/purge | Fixture-only timestamps aged; real cleanup service moved leaf to Trash then PURGED, without manual maintenance calls |
| Purge contents | Files, CSV attempts and previews removed; audit preserved; parent/original artifacts intact |
| Final UI synchronization | External fixture trash plus Review updated panel/list and disabled Open; Restore returned ACTIVE/Keep |
| Public protection | Homepage 200; unauthenticated 401; missing CSRF 403; unrelated-session lifecycle/export/download 404; secure cookies |
| Real async diagnostic | 1.475 s network submit round trip, then worker SUCCESS |
| Published source | 21 patch files match archive; 55 running-backend Python files match local; public JS/CSS match final local build |
| Existing data | Original 16 READY/ACTIVE/no expiry; five earlier datasets, all 100,000-row source/result cells and existing CSV hash rechecked |
| Cleanup | Only three named copies and synthetic export removed; browser returned to real data and CSV link |

Public fixtures copied an existing eight-row synthetic artifact into source → result → leaf. The synthetic export and temporary concurrency job were never dispatched. Fixture setup made no new S3/model calls. Expiry tests aged only fixture timestamps, did not wait seven calendar days, and did not change the server clock. Spark suite data was isolated. No new million-row throughput or multi-host scaling claim is made.

The 33 lifecycle tests cover original protection, no cascade, active/unclean references, stale/tampered/expired reviews, ownership/CSRF, policies, parent-first restore, no immediate re-expiry, starvation, complete cleanup, failed purge recovery, child-before-parent purge, unavailable reads/creates/applies/retries and list filters.

## Release and recovery

- Application/config/test patch: 21 files, SHA-256 `0fdfd743e7657f36d3a2483b53ffe72f828ab89846efdcec5089b2fe1c199903`. Documentation maintained separately.
- Running backend: `sha256:26b5d9e0c2949c80d6965aefaa5b108e6e156ad77be93333d3cffea3663d3804`.
- Running frontend: `sha256:d790e5b4f83f99c708d624f1ab068fa3c614ac1e490ee35c01371032dc3f3c31`.
- Eight services running; API/PostgreSQL/Redis healthy. No new cloud resources, credentials or network exposure.
- Pre-change source: `/home/ubuntu/patternworks-before-lifecycle-20261018`; images tagged `before-lifecycle`. These back up code/images, not purged dataset content.
- Migration defaults support old inserts during upgrade. Older images do not enforce lifecycle gates: do not roll back onto a public database containing Trash/PURGED records. Prefer a forward fix; otherwise block public access and plan compatible recovery. Image/migration rollback cannot restore purged files.
- Original Day 5 archive unchanged; source secret scan clean. GitHub/video delivery remains separately pending.

Implementation: [service](../backend/processing/services/lifecycle.py), [maintenance](../backend/processing/management/commands/maintain_datasets.py), [migration](../backend/processing/migrations/0010_dataset_lifecycle.py), [tests](../backend/tests/test_lifecycle.py), [UI](../frontend/src/DatasetManager.tsx). Locking follows Django's [transaction semantics](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update), with PostgreSQL behavior independently checked above.
