# High-cardinality public release — 2026-10-21

Published at <https://patternworks.32-237-44-97.nip.io/>. The full public import/transformation/download walkthrough passed before repository synchronization. Video recording remains paused.

## Release and preservation

- Initial source archive SHA-256: `d311a0fbda19364e42fad2c3c4127e8b03f32bd8ea3a0c3bdb9c3b20d520c82b`; all 251 packaged files were checked before building. README and acceptance documents were subsequently updated to record observed results; application code was not changed after the build.
- Backup retained at `/home/ubuntu/highcard-20261021-backup`: previous source/images, PostgreSQL dump, migration, build/test logs and preservation snapshots. A quiet migration window was used after checking that no work was active. Automatic rollback was prepared and not needed.
- Migration 0012 applied successfully. The dedicated internal cache started; PostgreSQL and the broker Redis retained their existing container identities/start times. The backend/worker now use `redis://cache:6379/0` for cache operations.
- All **51 existing dataset records** and **511 artifact files / 1,480,097,215 bytes** had identical pre/post-migration digests. Their data was not rewritten by this release. Five new dataset records were then created by acceptance (CSV import, Excel import and three transformations).
- Backend/worker image: `sha256:b03bbdf2e515df3ce80aaf2431c5f2c568853ddc6bdc933f8eb42a8dc06613ca`.
- Frontend image: `sha256:c610c7413a86ad21d989e141425b416d4bece0838cb7b43bf9b0e2d07c945fd8`.
- New cache image: `sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`.

## Tests and public infrastructure

The AWS worker image passed **383 backend tests**, including **14 real Spark integrations**, in 187.65 seconds. Local checks also passed all 383 tests, 81 frontend tests, TypeScript/Vite build, migration consistency, PostgreSQL reservation/duplicate-Apply races, isolated Compose and cache-pressure checks. See [implementation and requirement audit](HIGH_CARDINALITY_ACCEPTANCE_2026-10-21.md).

Public verification confirmed trusted HTTPS, HTTP 401 without reviewer credentials, HTTP 403 without a CSRF token, Secure session cookies, healthy database/cache and a successful real HTTP → Celery → PostgreSQL/cache diagnostic. All four served JS/CSS chunks, including the lazy planet/3D modules, match the local production build byte for byte.

## Fresh Safari walkthrough

1. The user entered a new read-only S3 connection in Safari. Both `contacts.csv` and `contacts.xlsx` were listed from their actual bucket. A connection that expired during the earlier pause was renewed before this walkthrough; no expired credentials were recovered or reused.
2. CSV import succeeded with 8 rows and 6 columns. Every one of its 48 data cells matches the synthetic source fixture.
3. Selecting the actual Excel file discovered `Contacts` asynchronously and selected it by default. Import opened its 8-row/6-column preview.
4. From the preview, **Transform** opened the selected dataset. `Find every email address` generated a real model rule for **Email and Notes**, with literal replacement `[EMAIL]`. The preview was reviewed and Apply saved a separate version. All 48 resulting cells were checked independently, including null, unmatched and multiple-email cells.
5. Date normalization of **JoinDate** used a deliberately small **one-request budget**. All eight distinct date strings normalized correctly. Before Apply, the UI reported eight distinct values, **zero additional requests** and zero remaining requests; Apply successfully reused the saved mappings. The total remained one request (611 confirmed input / 142 output tokens).
6. Classification of **Country** used labels `United States`, `Australia`, `Other`, fallback `Other`, and guidance to group country names/abbreviations. Another one-request budget processed six distinct values across eight rows. Apply reused saved results. The total remained one request (571 input / 81 output tokens). All eight rows were classified correctly into four United States/four Australia results.
7. The final dataset has **8 rows and 10 columns**. Export ran asynchronously; Safari downloaded the actual CSV. All **80 data cells and all column headers** matched independently specified expectations, including CSV quoting, empty values, unchanged source columns and appended result/status columns.
8. Server-side checks independently verified each source/intermediate/final artifact, 3/3/2-row pagination at every stage, all successful jobs, actual request ledgers and all 48 original Excel source cells remaining unchanged.

Final dataset: `c89b5ebf-c117-465f-8f28-23d2d97fa727`. Export job: `513f60c6-44a1-42df-9e98-996d159e6784`. Download: 1,081 bytes; SHA-256 `c99caeefba9e6b8e5244203f90b23322b2d72f5958c5e04683f211ff2fb6e5ff`.

Non-secret measurements are in [public release evidence](high-cardinality-release-20261021.json). Local screenshots and private operational logs remain ignored under `.runtime/highcard-release`; credentials are not included in the repository.

## Evidence boundary and delivery

The fresh public walkthrough used actual S3 transport and small real model requests. The [million-row/high-cardinality checks](high-cardinality-million-20261021.json) use real local parsing/Spark and a simulated provider; the prior [server CSV benchmark](million-acceptance-20261020.json) used preseeded mappings. This release does not claim a live million-value provider benchmark, a new million-value AWS throughput measurement, multi-host scaling or high-concurrency acceptance.

Source and acceptance records are delivered through the private `LYQ1657645/patternworks` repository. GitHub Actions records the checks for each pushed commit. The remaining demonstration video is still unrecorded/unembedded, and assessors still require repository/demo access supplied privately.
