# Day 5 acceptance — scale, cancellation and recovery

Date: 2026-10-17. This is the local verification/deployment-preparation snapshot, captured before cloud resources were created. The subsequent running AWS deployment and its current verification status are recorded separately in [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md). The local metrics and fault records below remain historical evidence.

## Million-row correctness and performance

The final isolated run used one synthetic **1,000,000-row CSV, 95,763,934 bytes**, with unique nine-digit text IDs and names, plus eight repeating contact prototypes. It exercised the actual Django worker task, PostgreSQL state, Redis cache, CSV parser, Spark transformations, Parquet persistence and indexed preview artifacts. Each stage creates a new dataset; the original source remains READY and unchanged.

| Stage | Wall time | Rows/second | Peak container memory | Columns | Exact checked rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| CSV import | 50.711 s | 19,720 | 1,395.5 MiB | 6 | 1,000,000 |
| RE2 email masking | 34.036 s | 29,381 | 1,729.7 MiB | 6 | 1,000,000 |
| Date normalization, cached | 48.209 s | 20,743 | 1,784.1 MiB | 8 | 1,000,000 |
| Classification, cached | 51.259 s | 19,509 | 2,018.4 MiB | 10 | 1,000,000 |

All stages passed independent ordered row/cell equality checks against explicit expected fixture values. Preview rows are built by reading back the persisted Parquet, rather than directly from the input frame. Four Parquet partitions were present per result. The source's ordered content digest was unchanged after the chain. Regex statistics were exact: 375,000 matched/changed rows and 500,000 matches. Dates produced 1,000,000 normalized values; classification produced 500,000 USA and 500,000 Australia labels. Other source cells, nulls, text IDs and ordering were preserved.

Persisted pagination: 100 direct service requests, 25 rows per page, exact IDs without omissions/duplicates. Median **0.219 ms**, p95 **0.446 ms**, maximum **3.591 ms**. These are in-process service timings, not HTTP/browser latency.

Scope and interpretation:

- Local arm64 Docker VM: 10 CPUs and approximately 8.32 GB configured RAM; Spark 4.0.3 / Java 21, `local[2]`, four partitions, one execution slot. The harness ran in the backend container without a per-container memory cap. Memory samples include container page cache; they are not whole-machine RAM measurements.
- Timing includes task execution, Spark startup, Parquet write/readback, preview indexing and publication. Fixture generation and independent correctness scans are outside the stage timings.
- The harness invokes the worker synchronously and substitutes local CSV transport for S3. Date/category mappings are explicitly validated synthetic values preseeded into Redis; an unexpected model call raises an assertion. This benchmark measures the cached transformation path, excluding network/model latency and cost. Actual async queue behavior is covered separately below; real S3/OpenAI small-fixture acceptance is recorded in Days 2–4.
- There are eight distinct dates and six distinct category inputs. This does not validate unlimited distinct model inputs: the compact app intentionally caps full-column inference at 500 distinct non-null values and 1,024 characters per value. Million-row Excel import was not benchmarked.
- Earlier baseline and contended runs are preserved. Every stage's ordered output digest agrees across all three runs. The contended run overlapped other Spark tests and is not representative. Single local runs do not establish a controlled speedup/regression or guarantee cloud performance.

Evidence: [final isolated run](day5-million-final.json), [baseline](day5-million-baseline.json), [contended run](day5-million-contended.json), [baseline source fingerprints](day5-baseline-source-sha256.json). Reproduction harness: `scripts/benchmark_million.py`; run explicitly inside the backend image with `--rows 1000000 --output /data/datasets/a-new-report.json`. It creates retained synthetic datasets and must not be run implicitly on a public deployment.

## Reliability implementation

- An independent watchdog checks job ownership/cancellation every second and updates its heartbeat every five seconds. Cancellation calls Spark's interruptible job group, then removes unpublished output while preserving READY source data. Parsing/indexing progress is limited to twice per second; this does not delay the independent heartbeat/cancellation checks.
- Every execution claims a fresh UUID attempt token. State updates, cleanup, artifact rename and final publication check the current token. Stale/duplicate attempts cannot publish over or delete newer attempts. Queue messages contain opaque job IDs.
- A 15-second reconciler requeues a RUNNING job after 90 seconds without a heartbeat, up to two recoveries. Missing QUEUED deliveries are republished after five minutes without exhausting that budget merely for waiting. Recovery is reconciliation rather than a transactional outbox.
- Celery uses late acknowledgements and worker-loss rejection. A producer acknowledgement error only fails an unclaimed QUEUED record; it cannot overwrite a RUNNING/SUCCESS job already accepted by a worker.
- Manual retry creates a new job/output ID and preserves the old FAILED/CANCELLED record. Invalid/expired S3 connections require re-entry. Transient provider failures remain bounded; in-flight provider calls can finish or be billed again if interrupted before caching.

## Verification

- Final backend image: **204 tests passed in 65.66 seconds**, including five real JVM/Spark integration tests. Coverage includes stale-attempt fencing, heartbeat/cancellation, cleanup, bounded recovery, missing delivery, acknowledgement-loss races, retry ownership/CSRF, output separation and production configuration.
- Frontend TypeScript/Vite production build, Django system checks and migration consistency passed.
- Real local HTTP/queue fault tests exercise cancellation during a million-row Spark RE2 stage, SIGKILL of the worker container with automatic recovery, permanent failure followed by a separate manual retry, and Redis outage returning HTTP 503 followed by successful retry. Each successful million-row recovery/retry output is checked cell-by-cell against its source. Final measurements are in [fault evidence](day5-fault-evidence.json); the earlier passing snapshot is retained as [initial fault evidence](day5-fault-initial.json).
- Browser retry passed: synthetic failed diagnostic `61b7a153-935d-4263-adc3-e4cbda88370e` was retried through the visible button, creating successful job `6c9323c7-809e-4756-9931-fc9555a2cd30`. This was an explicitly labelled controlled failure; it does not indicate a real user operation failed. [Before](day5-retry-before.png), [success](day5-retry-success.png).
- Fault tests use dedicated synthetic sessions/data, never AWS credentials or live OpenAI calls. Existing user datasets and Day 4 results remain intact.
- After fault injection, all seven local services were running; backend, PostgreSQL and Redis were healthy. The final real asynchronous HTTP smoke check returned 202 in 0.048 s, then SUCCESS with the shared cache verified. [Final checks](day5-final-checks.json) also records the read-only database verification of browser retry and the retained eight-row Day 4 datasets. [Final source fingerprints](day5-final-source-sha256.json) identify the implementation snapshot.

Final real fault measurements:

| Scenario | Observed result |
| --- | --- |
| Cancel during million-row Spark RE2 stage | CANCELLED; no output artifact; source READY; next queued diagnostic completed within 1.923 s of cancellation |
| SIGKILL worker container | Same job SUCCESS after 143.708 s, including the heartbeat timeout and reprocessing; attempt count 2, recovery count 1 |
| Invalid stored synthetic rule, then correct/retry | Original remains FAILED; new job and separate dataset SUCCESS |
| Stop Redis, submit, restart Redis, retry | HTTP 503 / QUEUE_UNAVAILABLE; new task SUCCESS after restart |
| Recovered and manually retried outputs | Exactly 1,000,000 independently checked rows per result; source READY |

The 1.923-second figure measures cancellation-to-next-diagnostic completion, including cleanup and queue work; it is not a universal Spark interruption bound. The 143.708-second figure is an observed complete recovery time, not an SLA. An active external model request cannot be forcibly unbilled.

## Public deployment preparation

Prepared and checked: production Compose overlay, pinned Caddy gateway, public HTTPS settings, reviewer password authentication, private application/database/queue ports, fresh server-secret initialization, resource/log limits, read-only preflight and source packaging with a SHA-256 manifest. Offline verification passed for merged ports, Caddy syntax/auth/header stripping, HTTPS redirects, Secure cookies and CSRF rejection/acceptance using an ephemeral database. See [machine-readable checks](day5-deployment-checks.json) and [deployment guide](DEPLOYMENT.md).

Recommended first server: the existing AWS account, Lightsail Linux with 2 vCPUs / 8 GB RAM / 160 GB disk and public IPv4. The guide links current official pricing. Budget/region/DNS and the private server credential destination still need confirmation before resource creation or publication. Live DNS/ACME, architecture compatibility, external HTTPS and a real S3/LLM demo must be verified on that server.

Remaining final delivery work: public deployment acceptance, final GitHub submission, README URL and demo video. Dataset artifact retention is manual. The current setup is one server running local Spark parallelism, rather than an external multi-host Spark cluster or highly available service.
