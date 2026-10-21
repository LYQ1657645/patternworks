# Galaxy library acceptance — 2026-10-20

This change replaces the Dataset library itself with a multi-file star map. It supersedes the earlier version-only galaxy above the traditional list. The old list is no longer rendered. Data preview is initially closed and opens from a planet; closing it returns to the library.

## Behavior

- Files/worksheets form separate constellations. Group identity uses the original bucket, object key and worksheet, with owner-scoped ancestry resolution. Missing provenance is never merged by filename alone.
- Saved versions are solid planets. Non-ready attempts are wireframes, with progress/retry directed to Activity. Only persisted parent relationships between READY datasets form operation edges.
- Search, status and lifecycle filters are collapsed behind Search & filters. Trash records retain the existing management/recovery flow. Purged records are excluded from the library.
- Each metadata page contains at most 100 records with session/filter/resource-bound signed cursors. Off-page parents are identified without inventing links. Focus this file opens up to 500 saved versions, with truncation disclosed.
- Planet details provide Preview, Transform, file focus and version management. Operation details retain before/after previews and multi-column statistics.
- Activity still handles cancellation, failure, retry and exports; these tasks do not all produce dataset versions.
- No schema migration, S3 write, row transformation or model call is introduced.

## Verified locally

- Backend: 340 passed, 12 Spark tests deselected.
- Frontend: 43 passed; TypeScript and Vite production build passed.
- New automated coverage: multi-source grouping, reimports, bucket/worksheet boundaries, incomplete attempts, search/status/lifecycle/dependency filters, cursor isolation, off-page parents and source-family layout.
- Browser: two labeled synthetic source constellations, file search, file-history focus and return, empty Trash, version-management entry, preview opening and closing. No deletion of user data was performed.
- Fresh load has no expanded preview or legacy dataset list. Desktop DOM width matched the viewport (1280 CSS px). A viewport override did not change this browser's reported width, so no new mobile acceptance is claimed.
- Local screenshot: `.runtime/galaxy-library/local-library.png`. Test/build logs share this directory.
- The existing lazy graph bundle remains about 320 KB gzip, plus about 61 KB gzip for the lazy planet/Three module. No GPU stress benchmark or new million-row processing benchmark was run.

## Delivery status

Public deployment completed after updating the existing SSH source restriction to the current management network's single IPv4 address (/32). AWS confirmed the update; no unrestricted SSH rule was introduced. Preflight found zero active tasks.

- Server build passed; 68 targeted tests passed inside the new backend image.
- Backend, worker, cleanup, Flower and frontend restarted successfully. Backend, PostgreSQL and Redis reported healthy; existing data volumes and gateway configuration were retained.
- All 13 released files matched the local SHA-256 manifest before this final documentation update.
- Public Safari showed the whole library: 2 source files, 6 dataset records and 1 actual transformation. Search narrowed to contacts.xlsx / Contacts with one record; Preview data displayed its existing 8 rows and 6 columns.
- Local regression results remain 340 backend tests and 43 frontend checks passed. No user datasets were modified during this release.
- Source rollback backup: `/home/ubuntu/galaxy-library-20261020-backup`. Logs and screenshots: `.runtime/galaxy-library/`.
- Public URL: https://patternworks.32-237-44-97.nip.io/#/datasets . The release archive contains only named source/documentation files, without local datasets, credentials or runtime state.
