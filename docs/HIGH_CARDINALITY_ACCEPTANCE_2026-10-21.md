# High-cardinality transformations and requirement audit — 2026-10-21

Status: implemented and published. Fresh public acceptance is recorded in [the release audit](HIGH_CARDINALITY_RELEASE_2026-10-21.md); it covers the actual S3/model/download path and preserved data. Repository delivery is tracked by its commit/Actions checks. Recording is paused. Earlier dated reports retain their original scope; the former 500-distinct-value limit is not the current local implementation.

## What changed

- Removed the 500-distinct-value rejection and aligned transformation cells with the 65,536-character ingestion limit. Full sample/Parquet values are used, not shortened display text. Requests are limited by both value count (12) and UTF-8 payload target (64 KiB; long cells run alone).
- Streamed distinct values and validated mappings live in a private on-disk SQLite checkpoint under the source artifact. No full-column Python dictionary, all-values collect, unconditional Spark broadcast or executor-side provider request is used. Spark merges the validated mapping across partitions and publishes only a complete result.
- Each 25-request slice saves progress and queues the same durable job ID. Its progress no longer jumps backwards between slices. Transient retries, manual retries and worker recovery retain completed mappings and the cumulative request ledger.
- Preview reports the full column's distinct values and remaining request estimate. The default 100-request limit is adjustable up to 1,000,000. Increasing it and applying the same reviewed plan resumes saved work. This is a spending control, not a replacement distinct-value rejection.
- Reservations happen before transmission. Confirmed token counts and requests with uncertain outcomes remain distinguishable. Known successful usage from earlier releases is migrated; historical failed calls without recorded usage cannot be reconstructed.
- A dedicated evictable Redis cache is separate from the non-evicting broker/result server in Compose. This prevents value-cache pressure from evicting task delivery state. Durable mappings survive cache eviction/expiry. Cache misses in separate plans are still not globally coalesced.
- Existing pre-upgrade previews with an empty plan render safely. Duplicate active Apply submissions reuse the same job. Budget edits do not invalidate semantic previews or get overwritten by a late saved-plan response.

## Current checks

- Complete backend suite: **383 passed**, including **14 real JVM/Spark integrations**. The rebuilt Linux Docker worker image also passed all 383 tests in 63.07 seconds. Tests use SQLite for application records, with mocked S3/provider boundaries unless specifically stated.
- Frontend: **81 passed**; TypeScript and Vite production build passed. Existing lazy 3D bundle size warning remains.
- [Isolated PostgreSQL checks](high-cardinality-postgres-20261021.json) passed: migration 0011 → 0012 retained known usage; two simultaneous reservations for one remaining request accepted only one; concurrent Apply submissions created one job. The guarded reproduction script is `scripts/verify_transform_postgres.py` and refuses a non-test/nonempty database.
- Django migration consistency passed. Migration 0012 adds counters/plan fields and widens job attempt count; it preserves known successful legacy usage.
- An isolated rebuilt Compose stack started successfully with PostgreSQL, separate broker/cache, API, worker, frontend, cleanup and Flower. Real HTTP diagnostics returned 202 in 0.318/0.296 seconds and completed SUCCESS before/after cache pressure. A deliberately reduced disposable cache limit caused 426 evictions while a separate broker marker survived. The test stack had no OpenAI key. See [Compose evidence](high-cardinality-compose-20261021.json).
- All 21 pre-existing local dataset records compare exactly with the pre-migration backup. The final local preview is running on port 5173.
- Merged development/production Compose configuration parsed successfully. Backend, worker, Flower and cleanup all route cache operations to the dedicated internal cache. Broker/cache have no published ports.
- Repository configured-secret/publishable-file scan passed with no findings; ignored runtime databases, credentials and generated scale fixtures are excluded.

Specific regressions cover 1,201 uncached distinct values, >500 valid dates, full-column budget refusal before Apply calls, raising a budget without losing progress, unknown provider outcomes, Redis failure after receiving a batch, Redis expiry, invalid labels, cancellation before checkpoint publication, preserved preview-retry counters, long complete sample values, same-job continuations, and atomic new-version output. Real Spark verifies source row IDs/nulls and 1,201-value distributed joins, plus 5,000/65,536-character and multibyte full-value previews.

## Scale evidence

The reproducible harness is `scripts/benchmark_high_cardinality.py`. It creates a new isolated SQLite application DB and separate local Redis broker/cache processes. S3 download is replaced by a synthetic local XLSX copy; the OpenAI client and boto3 client are guarded against use. Model responses are deterministic fixtures. **There are no paid API requests in these checks.**

- [Real queue evidence](high-cardinality-queue-20261021.json): separate Celery worker, 1,204 XLSX rows, 1,201 distinct category values. Both date and category transformations used 101 simulated requests and five deliveries of their same job ID. Import → date → category → actual CSV export passed exact-cell checks and source preservation.
- [Million-row evidence](high-cardinality-million-20261021.json): 1,000,000 XLSX data rows, 30,003 distinct date strings and 1,000,000 distinct category strings. Uses the real worker entrypoint synchronously with persisted continuation slices, not a million-row broker/browser benchmark. All final 7,000,000 CSV cells are independently compared against the generator's expected row values. Original content and fixture hash are verified after the chain; beginning/middle/end pagination is checked.
The final local million-row run measured 52.146 s for XLSX import, 22.579 s for date processing, 416.035 s for classification and 3.556 s for CSV generation. Exact-cell verification time is separate. The synthetic workbook is 24,952,037 bytes. Dates used 2,501 simulated requests over 101 slices; classification used 83,334 over 3,334 slices. The final separate cache/broker policy was used. These timings include mocked provider responses, not real model latency.

- The existing [AWS million-row CSV evidence](million-acceptance-20261020.json) separately covers real Spark regex replacement, cached dates/categories and exact cells on the server. That earlier test used low-cardinality preseeded mappings and local fixture transport.

These tests establish parser, mapping, continuation, Spark and export correctness at their stated scale. They do **not** establish live model latency, semantic accuracy for arbitrary classification input, real S3 throughput for a million-row object, production-host high-cardinality resource usage or multi-user concurrency. Local timings must not be presented as live OpenAI timings.

To reproduce (Python/Redis/Java dependencies installed):

```bash
.venv/bin/python scripts/benchmark_high_cardinality.py \
  --directory .runtime/scale-queue-new --rows 1204 --distinct 1201 \
  --port 6403 --queue --output .runtime/queue-evidence.json
.venv/bin/python scripts/benchmark_high_cardinality.py \
  --directory .runtime/scale-million-new --port 6401 \
  --output .runtime/million-evidence.json
```

Use NEW directories and two unused adjacent Redis ports. The script refuses to overwrite an existing acceptance directory. Fixtures/checkpoints remain under ignored `.runtime` for inspection; child Redis/worker processes stop on exit. No user data or existing application database is used.

## Calling cost and recovery semantics

For short uncached values, approximately `ceil(distinct_nonblank_values / 12)` requests are needed: 1,000 → 84; 10,000 → 834; 1,000,000 → 83,334. Long text, preview batch boundaries and failed/uncertain responses can increase this. Redis and completed checkpoints reduce calls. The UI displays the current plan's additional estimate before Apply; it does not hide the work behind the sample-row count.

Currency depends on model token pricing and actual input/output usage. Instructions/options repeat per batch. No dollar-price claim is made here, and a request budget is not a monetary ceiling. Provider-level project limits remain appropriate for monetary control. Creating a new plan creates a new plan budget. Exactly-once billing cannot be promised: a crash after provider acceptance but before durable checkpoint commit can require that batch again; its reservation stays counted.

## Requirement-by-requirement review

Mapped to the original assessment's mandatory modules, rather than treating visual polish or a running container as acceptance:

| Requirement | Implementation and evidence | Remaining verification/delivery |
| --- | --- | --- |
| React frontend and Django backend | Existing source and current frontend/backend suites | New public UI passed fresh Safari acceptance |
| User-owned S3 credentials/bucket and supported-file listing | Encrypted expiring credentials, session ownership, read-only S3 APIs; session/foundation tests and dated public acceptance | Fresh public S3 CSV/Excel walkthrough passed; see release audit |
| CSV and Excel import, real worksheet selection | Worker parsing, async worksheet discovery; worksheet tests and actual million-row XLSX pipeline | Million-row XLSX transport was local, not S3; legacy XLS has its format's row limit |
| Heavy work is asynchronous; immediate job ID | Celery/Redis, persisted job states; real separate-worker queue chain | Million-row harness calls worker entrypoints synchronously; queue behavior tested separately |
| Progress, cancellation, failures and retries | Attempt fences, watchdog/recovery, checkpoints and shared budgets; recovery/cancel tests plus real queued continuations | No new live-provider process-kill test; uncertain external outcomes can be billed |
| PySpark partitioned large-data transformations | Existing million-row CSV RE2 evidence; new million-row XLSX/date/category exact-cell evidence | Single-host `local[2]`/four partitions; no multi-host or concurrent-user throughput claim |
| Natural language to regex, validation and Redis caching | RE2 validation, varied instruction fixtures, prior real model/public evidence; rules/multicolumn tests | A sample set does not guarantee every natural-language instruction or unsupported regex feature |
| Two additional LLM transformations | Date normalization and label classification use actual provider implementation and the async/Spark pipeline; >500 limit removed | High-cardinality provider behavior is simulated in scale checks; semantic classification still requires review |
| Paginated results | Persisted row index, history cursors and beginning/middle/end million-row checks | Graph view windows bound versions, not dataset rows; full data remains in export |
| Docker Compose and observable tasks/Spark | Separate broker/cache configuration; health checks, Flower, durable jobs, Spark metadata, test/verification scripts | Rebuilt public stack and real HTTP/Safari acceptance passed |
| Public URL and reviewer access | Existing HTTPS reviewer-gated deployment; private repository already exists | New code/Compose/migration deployed; repository access still required for assessors |
| README architecture/setup/tradeoffs and demonstration | README updated with accurate limits, cost/recovery and scale scope; script/recording guide are drafts | Video recording and README embedding remain paused/pending |

## Explicit boundaries and next release gate

The former distinct-value rejection was an implementation gap affecting the required additional transformations; it is not described as an assessment exemption. Resource limits still apply: CSV up to 1 GiB, Excel up to 100 MiB compressed/512 MiB expanded, 256 source columns and 65,536 characters per cell. Additional transformations require room for two result columns. Supported date-only formats/ambiguity policy and 2–12 category labels are documented in README. This is a session-owned single-host demonstration, not a multi-tenant account platform.

The backed-up public upgrade and fresh S3 → preview → Apply → CSV walkthrough have passed. Source and acceptance are delivered in the private repository with per-commit GitHub Actions checks. Assessor access, video recording and README video embedding remain final submission tasks. Million-value live-provider throughput and multi-user/multi-host behavior remain outside the measured evidence; no simulated test is presented as proof of those properties.
