# CSV export acceptance — 2026-10-18

The existing public application now exports any READY dataset, including regex/date/category results, as a downloadable CSV. Select a result, choose **Prepare CSV download**, wait for completion, then **Download CSV**. The finished link is restored after a page refresh.

## Data and execution

- A persisted `EXPORT_CSV` job runs through Redis/Celery. Spark reads the complete Parquet source, orders by `_row_id`, and writes temporary JSON parts. Python streams those parts into a CSV without collecting the table or a Spark partition in the API/driver. Continuous row IDs and the final row count are verified before publication.
- All columns appear in schema order with their display names as headers; `_row_id` is omitted. All data rows appear in original order. Long cells use complete values, independently of clipped browser previews or legacy sample indexes.
- CSV uses UTF-8 with BOM, commas, CRLF records and standard quoting for commas, quotes and embedded newlines. Null and empty text both become blank fields. Values are not escaped into formulas or modified: when opening with Excel, import columns as Text to retain leading zeros and formula-like strings. CSV has no native null/type metadata.
- A header-only dataset exports a header. Each worksheet is already represented by its own selected dataset; the download does not combine worksheets.
- Generation uses existing task progress, cancellation, heartbeat, fenced publication and recovery. Cancellation/failure removes the export and temporary files while retaining the READY source. Retry creates a new job against the same dataset. Normal duplicate submissions reuse an active or available completed export. Missing finished files can be generated again.
- Download is a session-scoped `FileResponse` attachment with a known content length and `Cache-Control: no-store`; the browser streams it directly instead of buffering a Blob in JavaScript. Shared-volume files are private; IDs never grant another session access. S3 credentials and OpenAI calls are not needed to export an existing result.

## API

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/datasets/{id}/export/` | Latest export job plus `download_available` |
| POST | `/api/datasets/{id}/export/` | 202 for new/active export; 200 for an available completed export |
| GET | `/api/jobs/{id}/download/` | Finished CSV attachment; 409 before success, 410 if missing, 404 for another session/non-export job |

Mutation requires CSRF and a READY session-owned dataset. Download paths and filenames use server-owned UUIDs; request/source filenames do not become paths. Migration `0008_alter_job_kind` records the additional task kind.

## Tests and live acceptance

The local full regression passed **257 tests in 46.70 s** before three final boundary cases were added. The final focused non-Spark export tests passed **12** (overlapping that regression). The final AWS full suite passed **260 tests in 143.50 s**, including **12 real Spark/JVM integrations**. The frontend's eight regression tests, TypeScript/Vite build, Django checks and migration consistency passed. The initial local attempt used the wrong test-container working directory and failed existing Spark Python imports; the successful rerun used the application's backend directory.

Coverage includes authorization, CSRF, not-ready sources, duplicate submits, missing exports/regeneration, queue failure, cleanup/retry/recovery fencing, incomplete/out-of-order rows, cancellation before publication, literal values, Unicode, quoting, embedded newlines, nulls, 5,000-character values and a real Spark header-only file. Test execution uses isolated databases and synthetic data.

In Safari on the public deployment:

1. The existing 100,000-row, four-column processed dataset `07840491-cf24-4c92-bae3-8bd8bd2265f0` was selected.
2. Export `8c274f7a-3caf-4e08-886d-38ba5ccc7dc9` was cancelled while RUNNING. Cleanup completed and its published file was absent; source data stayed READY.
3. **Retry as a new task** created `9b542a0d-c550-40be-b15f-44418221969a`, which succeeded in **8.004 s** from creation to completion in this observed run.
4. Safari downloaded the actual attachment to the computer. Every one of its 100,000 rows/four cells was compared against explicit expected values, including leading-zero IDs, literal spaces/dollar/backslash/Chinese replacements, blank nulls and untouched Keep values. The 5,250,024-byte download and server file share SHA-256 `ac29b334de9052a0f8eb2d51730dab5d15c41f208bac87e414d754b24f4f337f`.
5. Refresh restored the same download link. The earlier five-dataset audit and the 100,000-row source/result audit passed again. Authenticated health/queue checks passed; CSRF rejection was 403, cross-session export/read/download was 404, and unauthenticated download was 401. Published JS/CSS match the fresh local build.

Machine-readable evidence: [csv-export-evidence.json](csv-export-evidence.json).

## Deployment and limits

Fourteen source files are identified by the final patch manifest; archive SHA-256 is `90a32b6968fdab4a26e7c3d8dd98072c83301175a08574b28216d013d04e2d41`. Previous source is saved at `/home/ubuntu/patternworks-before-csv-export-20261018`; prior image tags are `patternworks-backend:before-csv-export` and `patternworks-frontend:before-csv-export`. Active jobs were checked before restart; existing database, Redis and dataset volumes were preserved. The original Day 5 archive is unchanged.

The 100,000-row time is a single synthetic observation, not an SLA, a million-row export benchmark or a multi-host Spark test. Export requires temporary JSON disk space plus its completed CSV; output is retained on the existing dataset volume and there is no automatic retention policy in this feature. Downloads depend on the browser session and reviewer login; Safari may request the existing reviewer login and permission for its first download. GitHub/video delivery remains deferred.

Implementation references: [Django FileResponse](https://docs.djangoproject.com/en/5.2/ref/request-response/#fileresponse-objects); [Spark iterator memory behavior](https://spark.apache.org/docs/4.0.2/api/python/reference/api/pyspark.RDD.toLocalIterator.html) informed the disk-backed worker path used here.
