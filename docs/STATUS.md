> Current release: [planet release acceptance](PLANET_RELEASE_ACCEPTANCE_2026-10-21.md), 2026-10-21: 77 frontend tests, 368 backend tests including 12 real Spark integrations, and fresh public S3 Excel import → two-column regex → downloaded CSV acceptance passed. The [README](../README.md) is the current setup and delivery entry point. All entries below are historical snapshots, including older references to pending features and deferred GitHub delivery.

> Latest frontend update: [four-page navigation acceptance](NAVIGATION_ACCEPTANCE.md), 2026-10-18.

# Project status — session and workspace state fixes

**2026-10-18 design revision:** the paper-and-collage data studio is now deployed locally and publicly: coral actions, lilac/blue/apricot functional areas, neutral data tables and a dark task panel. 18 frontend tests/build and responsive/public Safari checks pass. See [studio acceptance](UI_STUDIO_ACCEPTANCE.md). Previous design reports below are historical.

**2026-10-18 UI refresh:** warm-white/forest-green workbench, section navigation, responsive forms/tables and Safari select styling are deployed locally and publicly. 18 frontend tests and production build pass; public browser/asset checks pass. Backend unchanged; all 16 datasets remain READY/ACTIVE/Keep. See [visual acceptance](UI_REFRESH_ACCEPTANCE.md). Earlier test counts below retain their original scope.

**Latest update:** R1–R5 session/revocation, connection-expiry UI, terminal history refresh, shared retry policy and README fixes are deployed. Local/cloud backend suites each pass 328 tests (12 real Spark); frontend 18 tests/build pass. See [fix acceptance](SESSION_AND_STATE_FIXES_ACCEPTANCE.md). GitHub remains deferred. Earlier snapshots below retain their original scope.

**Latest feature (311 local/cloud backend tests, 14 frontend tests):** dependency review, original confirmation, seven-day Trash/restore, opt-in 7/30/90-day retention and resumable scheduled purge are deployed. Active children/tasks block deletion; originals never auto-expire and S3 is untouched. Public Safari, automatic cleanup and two-connection PostgreSQL races passed. Original 16 datasets remain ACTIVE/Keep, with earlier results and CSV verified. See [lifecycle acceptance](DATASET_LIFECYCLE_ACCEPTANCE.md). Earlier sections below are historical snapshots.

**Latest feature (278 local/cloud backend tests, 14 frontend tests):** signed cursor pagination for task history and datasets, status/type filters, file/worksheet/UUID search, independent historical details and tab-local restoration. Safari and PostgreSQL traversal passed beyond the old caps; a real historical CSV retry succeeded without interrupting active tracking. Temporary browsing fixtures were cleaned and all original datasets remain intact. See [history acceptance](HISTORY_ACCEPTANCE.md).

**Previous CSV snapshot (260 cloud backend tests, eight frontend tests):** complete-value CSV export, async progress/cancel/retry, session-protected streamed download, duplicate-export reuse and refresh restoration. The real 100,000-row Safari download passed exact cell validation after cancellation/retry. See [CSV export acceptance](CSV_EXPORT_ACCEPTANCE.md).

**Previous multi-column snapshot (246 cloud backend tests, eight frontend tests):** multi-column regex selection, bounded per-column previews, one atomic Spark result, shared prompt cache, exact row/cell/occurrence statistics and per-column result counts. Legacy single-column rules and requests remain compatible. See [multi-column acceptance](MULTICOLUMN_ACCEPTANCE.md).

**2026-10-18 audit fixes: F1–F7 closed and deployed.** The audit-fix snapshot passed 227 tests locally and on AWS, including six real Spark integrations; five frontend API/error tests and the production build pass. Real queued long-cell replacement, native Excel date normalization, timestamp preservation, retry and real model counterexamples passed. See [fix acceptance](AUDIT_FIXES_ACCEPTANCE_2026-10-18.md) and its evidence; the [original audit](FUNCTIONAL_AUDIT_2026-10-18.md) is the historical before-fix snapshot. Additional scope improvements and GitHub/video delivery remain pending.

Earlier Day 6 snapshot: explicit regex replacement input, prompt-cache reuse across replacement values and persisted-output acceptance have passed. Those earlier images passed 211 local and 211 cloud tests; see [Day 6 functional checks](DAY6_FUNCTIONAL_ACCEPTANCE.md). Local million-row scale validation and reliability are implemented; the AWS production application is running at <https://patternworks.32-237-44-97.nip.io/> with trusted HTTPS and a reviewer gate. See [Day 5 acceptance](DAY5_ACCEPTANCE.md) for the local snapshot and [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md) for current cloud evidence and outstanding checks. Final GitHub/video submission remains pending. Historical Day 1–4 results below describe their respective snapshots.

This file records implemented work separately from live infrastructure verification. Docker Desktop and the Compose/PostgreSQL stack are running. Day 1 acceptance is complete: the 31-test foundation suite, containerized asynchronous smoke check, live S3 connection/file discovery and Flower dashboard all passed. Day 2 CSV/XLSX ingestion, real Spark processing, persisted previews and literal replacement have passed automated and live S3 acceptance. See [Day 2 acceptance](DAY2_ACCEPTANCE.md).

## Implemented

- Django API and durable jobs with QUEUED / RUNNING / SUCCESS / FAILED / CANCELLED states.
- Real Celery worker and Redis broker/result/cache configuration.
- React interface with asynchronous status polling, errors, cancellation and file selection.
- Encrypted, expiring AWS credentials; session-scoped connection/job access and CSRF enforcement.
- Async S3 bucket access check; paginated supported-file listing with optional prefix.
- PostgreSQL schema/migration; Compose startup for web/API/database/queue/worker/Flower/cleanup.
- Ignored local env secrets, initialized through a script that preserves existing values.
- Test suite, production frontend build and HTTP asynchronous smoke-check script.

## Verified locally

- Backend: 31 tests passed (SQLite test database; S3 requests stubbed, no real AWS access).
- Django system checks passed; initial migration applied to the local preview database.
- Frontend TypeScript + Vite production build passed.
- Real HTTP → Redis → separate Celery worker → SQLite/cache smoke check passed. Initial response HTTP 202 in approximately 0.054 seconds, final database job state SUCCESS. Celery eager mode was not used.
- OpenAI API: one minimal real Responses API call passed. S3 credentials/data were not sent.
- Browser: live service indicators and the diagnostic job's QUEUED → SUCCESS state were observed.
- [Browser verification screenshot](day1-task-success.png).
- Docker Desktop 4.95.0 is installed in `/Applications/Docker.app`; its Docker Inc signature and macOS notarization assessment passed.
- Docker Engine 29.8.2 and Compose v5.6.0 respond successfully. The official `hello-world` container ran successfully and was automatically removed.
- Docker-native Compose configuration validation (`config --quiet`) and `up --build -d` passed. All seven services are running; PostgreSQL, Redis and backend report healthy.
- Containerized HTTP → Redis → separate Celery worker → PostgreSQL/cache smoke check passed on 2026-10-17: HTTP 202 in approximately 0.042 seconds, initial QUEUED, final SUCCESS. Flower's dashboard returned HTTP 200 with its dashboard HTML verified.
- Two synthetic S3 fixtures are available in `samples/contacts.csv` and `samples/contacts.xlsx`. Independent readback confirmed identical content: eight records and six columns each.
- AWS console verification on 2026-10-17: private bucket `patternworks-test-20261017-k7m3` in `ap-southeast-2`, Block all public access enabled, ACLs disabled. Both fixture uploads show successful (2 files, 0 failures). This is console evidence, not an application SDK connection test.
- Live application S3 acceptance on 2026-10-17: CONNECT_S3 jobs reached SUCCESS/100%, connections reached READY, and the browser listed `contacts.csv` (831 B) and `contacts.xlsx` (4.2 KB). Only status metadata was inspected in PostgreSQL; credentials were not read or printed. The dedicated IAM user has the single bucket-scoped inline policy `PatternworksTestBucketReadOnly` and console login disabled.

## Day 2 implementation and acceptance

- CSV/XLSX/XLS parsing is worker-only, with explicit text schema, stable source row IDs, worksheet selection and safe format/size errors.
- Real PySpark DataFrame ingestion, four-partition Parquet, and a separate SQLite cursor-pagination index; no full-dataset collect or pandas loading.
- Async literal replacement creates a separate dataset; original rows/artifacts are preserved.
- React import, preview/schema, cursor navigation, source/restored dataset selection, and literal replacement controls.
- Java runtime and shared dataset volume added to Compose; worker concurrency reduced to one to bound local Spark memory.
- Final container suite: 62 tests passed, including two real JVM/Spark integration tests; no test shutdown logging errors remain. Local non-Spark suite: 60 passed. TypeScript/Vite build, Django checks and migration consistency passed.
- Live browser imports of S3 `contacts.csv` and `contacts.xlsx` (sheet `Contacts`) each reached SUCCESS with 8 rows, 6 columns and 4 Parquet partitions. Both exactly match the local fixture. Literal Country replacement `USA` → `United States` reached SUCCESS and preserved the original dataset.
- Independent artifact checks returned cursor pages of 3 / 3 / 2 rows, without losses or duplicates. The same checks passed after all application containers were rebuilt/restarted, confirming shared-volume persistence.
- Final HTTP diagnostic returned 202 in approximately 0.191 seconds, then SUCCESS through the real worker/cache. Flower's browser dashboard showed one online worker and received the diagnostic SUCCESS event. Configured application secrets scan found no matches in source files.
- Full evidence and timings: [Day 2 acceptance](DAY2_ACCEPTANCE.md). No million-row performance claim is made from the eight-row fixtures.

## Day 3 regex / validation / cache acceptance

- Natural-language rule generation, strict structured output, RE2/policy validation and local before/after previews are implemented in Celery.
- Validated rules are cached in Redis with session/model/prompt/policy-scoped hashed keys and a one-hour TTL; rows and credentials are excluded from model requests and cache payloads.
- The generate → inspect → apply UI executes the same RE2 logic in Spark, produces new persisted datasets and reports full-data match statistics.
- Full container suite: 115 passed, including three real Spark tests. Local non-Spark suite: 112 passed. Frontend build, Django checks and migration consistency passed.
- Live OpenAI test generated a valid email-masking rule (348 input / 166 output tokens). After restarting the worker, the same instruction hit physical Redis cache with 0 model tokens.
- Live Spark application produced exact expected results: 8 rows, 6 columns, 3 matched rows / 4 matches / 3 changed rows, four Parquet partitions. Original source and other columns were preserved; pagination remained exact.
- Evidence: [Day 3 acceptance](DAY3_ACCEPTANCE.md). This completes the local regex/cache scope; the original plan's first public deployment remains pending.

## Required external preparation

1. S3 preparation and live connection/file discovery are complete. Credentials expire from the app after one hour; enter them directly in the app again when needed, rather than in chat.
2. AWS environment/budget and server key destination are confirmed. The user created the Lightsail instance and the public HTTPS stack is running; see the separate deployment acceptance record for remaining checks.

## Day 4 dates / categories acceptance

- Implemented two actual LLM transformations: date-only normalization to `YYYY-MM-DD`, and classification into user-selected labels with an explicit fallback.
- Explicit selected-value disclosure and consent in the UI/API; preview and full application run in Celery. A result/status column pair is appended to a new dataset, preserving all source columns, nulls and row IDs.
- Independent Gregorian date validation, configurable numeric-date ambiguity, strict batch-ID/label validation, per-value Redis cache isolation and pinned models. At most 12 values per request, 500 distinct non-null values per full column, 1,024 characters per value; no silent truncation or paid executor-side calls.
- Real OpenAI previews passed on the previously imported synthetic Excel dataset. Eight mixed-format dates normalized exactly; six distinct country spellings classified into USA/Australia across eight rows.
- Application container rebuild preserved data/cache. Repeated classification preview used zero model calls/tokens. Both full-column applications reused all preview values (eight date values, six category values).
- Independent output checks confirmed a valid 6 → 8 → 10 column chain, four USA/four Australia labels, source preservation, four Parquet partitions per dataset and exact cursor pagination.
- Final container suite: 168 passed in 38.71 seconds, including five real Spark integration tests. Frontend build, Django checks, migration consistency, real HTTP asynchronous smoke checks and final-image persisted-output verification passed. No configured application secret was found in source scanning.
- Detailed evidence and scope limits: [Day 4 acceptance](DAY4_ACCEPTANCE.md), [machine-readable live evidence](day4-live-evidence.json).

## Day 5 scale / reliability / deployment preparation

- Final isolated CSV import → RE2 masking → cached date normalization → cached classification processed 1,000,000 rows at each stage. Exact row/cell checks, four Parquet partitions, stable row IDs, source preservation and cross-run output digests all passed. Stage times: 50.711 / 34.036 / 48.209 / 51.259 seconds; maximum sampled container memory 2,018.4 MiB. These are local timings with fixture transport and validated synthetic LLM cache, excluding real S3/model calls.
- Persisted page-service p95 was 0.446 ms across 100 exact 25-row reads; this excludes HTTP/browser overhead.
- Added independent heartbeat/Spark cancellation, token-fenced publication/cleanup, bounded abandoned-job recovery, missing-delivery republishing and new-task retries. Failed records and READY source data are preserved.
- Final image: 204 tests passed in 65.66 seconds, including five real Spark tests. Real local cancellation, hard-worker-crash recovery, manual retry and broker-outage tests have dedicated synthetic million-row evidence. The browser retry button generated a successful new task while the controlled old failure remained FAILED; existing Day 4 source/result datasets remain READY with their original dimensions.
- Production Compose/Caddy configuration, fresh private server settings, preflight and source packaging are prepared. Offline merged-port/auth/HTTPS/cookie/CSRF checks passed. No paid resource or public URL exists yet.
- Evidence and exact scope: [Day 5 acceptance](DAY5_ACCEPTANCE.md), [deployment guide](DEPLOYMENT.md).

## Pending assessment work

- Public acceptance passed in Safari: S3 CSV/XLSX import, live natural-language regex and cache reuse, date normalization, country classification and refresh restoration. The 204-test cloud suite and four cached million-row stages also passed. The /32 SSH rule was updated after the management network changed; a new SSH connection and the read-only five-dataset persisted-output audit passed. See the deployment acceptance record.
- Final GitHub submission and demo video are deferred while functionality is finalized; the README already contains the verified public URL.
- Dataset artifact retention remains manual in this compact demo. Million-row correctness/performance and local failure/cancellation recovery are covered by Day 5 evidence; million-row Excel import and high-cardinality paid model inference have not been benchmarked.
