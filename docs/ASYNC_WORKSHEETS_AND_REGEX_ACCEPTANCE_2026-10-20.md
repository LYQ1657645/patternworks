# Async worksheet discovery and core regex acceptance — 2026-10-20

## Scope

Excel worksheet discovery now runs in Celery instead of downloading/parsing the workbook in the Django request. `POST /api/connections/{id}/worksheets/` validates ownership, expiry and the Excel key, then returns HTTP 202 with a durable `LIST_WORKSHEETS` job. The browser polls the job, shows progress/cancellation, and selects the first worksheet when successful. Importing that worksheet remains a separate task.

Pending duplicate requests for the same connection/key reuse one job. A polling network interruption rechecks the same job. Cancellation and worker-loss recovery share the existing attempt fencing, heartbeat and staging cleanup. No dataset is created during discovery. XLSX discovery reads workbook metadata rather than cells/shared strings; source/expanded-workbook limits remain enforced. Recovery restarts a download; it is not byte-range resume.

## Automated verification

- Local backend: **329 passed**, 12 Spark tests excluded from the macOS run.
- AWS worker image: **341 passed**, including all 12 real Spark integrations, in 156.96 seconds.
- Frontend: **26 passed**; TypeScript/Vite production build passed.
- Migration consistency check passed; migration 0011 adds the job kind choice.
- Worksheet checks cover worker-only I/O, ordered/unicode tabs, XLS metadata adapter, malformed/oversized files, session ownership, expiry, CSRF, duplicate requests, cancellation, stale attempts, retry/recovery and staging cleanup.
- Frontend controlled-hook tests cover async success, ignoring stale results, interrupted polling without a duplicate submission, cancellation and task labels. These tests do not substitute for real browser verification.

## Live model and persisted regex results

`scripts/verify_regex_acceptance.py` ran in an isolated acceptance session against the configured live model, Redis and Spark. Three synthetic prompts (two English and one Chinese) generated working email patterns. Each passed positive, multiple-address, no-match and null-cell checks. Repeating the first prompt hit Redis with the model function guarded against invocation.

The generated rule replaced emails in **Email and Notes together**; every resulting cell and paginated row matched independently specified expected values. The original dataset remained unchanged. A no-match rule preserved all original cells. Invalid syntax, nested repetition, backreferences and lookarounds were rejected.

Scope: import transport copies a local synthetic fixture, not S3; worker entry points are invoked synchronously for this acceptance script. Three prompts establish these examples, not universal natural-language correctness or complete RFC email support. Existing bounded provider retry behavior applies. The million-row fixture uses prevalidated cached transformations, not one million model requests.

## Reproducing the core acceptance

Run the explicit acceptance script in the configured worker container: `python /app/scripts/verify_regex_acceptance.py /data/datasets/regex-acceptance.json`. It creates isolated synthetic records and makes live model requests; it does not read user files. Run the existing `scripts/benchmark_million.py --rows 1000000 --output /data/datasets/million-acceptance.json` in that same worker environment for scale evidence. Use the worker memory allocation, not the smaller web service.

## Deployment and scale evidence

All four million-row stages passed exact cell equality against independent expected values and retained four Parquet partitions:

| Stage | Processing seconds | Peak container MiB |
| --- | ---: | ---: |
| CSV import | 81.139 | 1322.4 |
| Regex replacement | 73.848 | 1530.1 |
| Date normalization, cached | 48.177 | 1667.9 |
| Classification, cached | 51.384 | 1974.6 |

The regex stage matched 500,000 occurrences across 375,000 rows. Original-data digest was unchanged after the complete chain. All 100 pagination probes returned the exact expected rows (direct persisted-page service p95 0.379 ms, not HTTP latency). These are single-host Spark `local[2]` measurements, not multi-node scaling evidence. Processing timings exclude the subsequent independent verification pass.

Evidence: [live regex](regex-acceptance-20261020.json), [million rows](million-acceptance-20261020.json).

New backend/worker/cleanup/Flower/frontend images are running on the existing AWS instance. Migration 0011 is applied. A public HTTPS diagnostic returned HTTP 202 in 0.957 seconds and completed through the actual broker/worker/database/cache; the expected frontend bundle was served. No new infrastructure or permissions were created. GitHub publication and recording remain deferred.


Public Safari verification with the user's renewed read-only S3 connection passed: selecting `contacts.xlsx` showed worksheet submission, completed as a separate task, defaulted to `Contacts`, and imported 8 rows / 6 columns. Independent persisted-cell comparison matched the synthetic fixture exactly. Worksheet discovery itself created no dataset. Cancellation/network interruption/recovery were exercised in automated tests; the live browser check exercised the successful path. See [deployment evidence](async-worksheets-deployment-evidence.json).

Rollback copies of changed source and prior backend/frontend image tags are retained at `/home/ubuntu/async-worksheets-backup` and `*:before-async-worksheets`.
