# CSV scale and provider recovery verification — 27 October 2026

The reviewer report exposed two separate failure paths. Production metadata showed successful imports of 2,194,488 rows and 16 columns, followed by regex-generation failures: `RULE_EXAMPLES_FAILED`, `RULE_UNSUPPORTED`, and most recently `LLM_RATE_LIMIT` after three attempts. No source cells, instructions or credentials were read for this diagnosis. These records establish successful ingestion, not successful conversion or export of that file.

The Generate request sends the transformation instruction, not the dataset. Apply executes the validated RE2 rule inside Spark partitions. Python CSV parsing and SQLite indexing still iterate over records with bounded buffers; the implementation has not been replaced with a fully vectorized parser.

A separate synthetic CSV reproduced an Apply failure locally: 1,000,000 rows, 16 columns, 431,650,871 bytes. The old `persist(DISK_ONLY)` path failed during result statistics, with SparkContext shutdown and allocation/GC warnings. The cleanup `unpersist` then obscured the original exception. This supports a cache-path resource diagnosis, but the captured trace does not prove the exact JVM allocation that caused shutdown.

Changes:

- Regex evaluation writes intermediate results directly to temporary Parquet partitions. Statistics and final publication reuse that staged data, without building the SQL cache. The Spark driver remains configured for a 1 GiB heap; this is not a measured total-process memory ceiling.
- Preview content fingerprints use bounded SQL insert batches. Full content identity, row order and preview clipping semantics remain intact.
- Rate-limit retries wait at least 60 and 120 seconds plus jitter, honoring longer valid `Retry-After` or exhausted-bucket reset headers. A persisted cooldown fences duplicate deliveries and recovery. Delays above 15 minutes defer to a later manual retry instead of retrying too soon. Quota/billing failures are terminal for automatic retry.
- Invalid generated rules can receive one correction request per worker attempt. The correction sends only the generated rule, synthetic examples and local validation feedback. Both responses must still satisfy the original policy; unsupported instructions are not silently reinterpreted. A normal successful generation still requires one model request. Automatic task retries remain bounded at two, so an uncached Generate task can make at most six requests if correction and transport retry paths combine. Failed or uncertain requests may still be billed; the successful rule's usage is not a complete billing ledger across failed attempts.
- Oversized CSV fields report `CELL_TOO_LARGE` rather than a misleading generic CSV encoding/quoting error. No field is silently truncated.

Validation and reproducibility:

`scripts/benchmark_csv_workflow.py` generates independent values across 16 columns, including unique emails/labels, leading zeros, Unicode, nulls, literal dollar signs/backslashes, commas, quoted newlines and occasional values longer than the browser preview limit. It imports the file, generates and repairs a simulated rule, transforms two columns, exports full CSV, checks every cell against an independent expectation, and verifies the original file hash. Raw completed measurements are in `csv-scale-20261027.json`.

| Rows | Columns | CSV bytes | Import | Regex Apply | Export | Exact cells checked |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 16 | 431,650,871 | 35.429 s | 33.213 s | 9.088 s | 16,000,000 |
| 2,194,488 | 16 | 957,665,123 | 81.293 s | 112.654 s | 18.122 s | 35,111,808 |

Both runs passed all-cell export equality, original-file hash preservation and final-page checks. Each produced four final Parquet partitions. Generate used two simulated SDK responses to exercise invalid-rule correction and is excluded from timing comparisons. A small Spark regression ran concurrently near the end of the larger run, so these timings should not be used to extrapolate production throughput.

Run from the repository root with the existing virtual environment and Java installed:

```sh
.venv/bin/python scripts/benchmark_csv_workflow.py --rows 1000000 --work-dir .runtime/csv-scale-new-run
```

The work directory must not already exist. The harness uses real Spark 4.0.3, RE2, CSV parsing and persisted artifacts, with isolated SQLite/locmem cache and synchronous worker entrypoints. S3 transport and OpenAI responses are simulated. It is not a production-host memory benchmark, broker test, or a test of the reviewer's actual file. Timings are local observations, not a throughput guarantee.

The non-Spark backend suite passed 382 tests. The existing 14 Spark integration tests passed; after the staged-regex change, the affected real-Spark test was rerun and extended to verify that a late output-size failure publishes nothing, removes temporary staging and preserves the source. Migration drift and whitespace checks passed.

A separate minimal live OpenAI request using the existing production configuration succeeded. It sent only an instruction to return `OK`, with a 16-token output cap and SDK retries disabled. This confirms current basic API availability; it does not validate the reviewer's instruction or guarantee future quota/rate availability.

Production deployment on 27 October applied migration `0013_job_retry_not_before` before starting the updated backend and worker. The rebuilt production image passed all **396 backend tests**, including the 14 Spark integrations. Source, old image and database backups were retained. Before/after snapshots matched for 76 datasets, 789 artifact files (3,655,253,771 bytes), 207 jobs and 18 transformations; PostgreSQL, Redis and frontend containers were preserved.

Fresh public Safari verification passed with `demo-contacts-60.csv` from the real S3 bucket. Refresh preserved the unexpired connection. Import produced 60 rows and 6 columns; an uncached live `gpt-4.1-mini` generation used 683 input and 229 output tokens. Applying the rule to Email and Notes changed 68 cells across 45 rows, matching 75 email occurrences. The browser downloaded the actual resulting CSV; all 360 cells, header, row order, null values, unaffected columns and quoting matched an independent expected result. The downloaded file was 4,860 bytes, SHA-256 `aa5212b9888b6b5b4c7009cf83ccdd213a2732dd69490865b6187fbd5d605383`.

The same 2,194,488-row, 16-column synthetic CSV was also verified inside the rebuilt image on the production host, with the Compose worker container's 4 GiB memory limit. Import took 370.100 seconds, regex Apply 909.072 seconds, and export 98.371 seconds. All **35,111,808 cells** matched; the original file was unchanged, the last page contained 100 rows, and output used four Parquet partitions. The complete export was 856,504,893 bytes. [Raw server measurements](csv-scale-server-20261027.json) preserve the result.

This server scale run used an isolated ephemeral container, SQLite/locmem and synchronous worker entrypoints, with simulated S3 transport and model responses. It validates full-data processing on the production hardware; the separate public Safari run validates real S3, OpenAI, PostgreSQL/Redis, Celery and browser download. It is not the reviewer's actual file, nor a concurrent-load or peak-memory benchmark. The SSH client connection was interrupted when the management network address changed; the server-side run completed and its saved report was retrieved after restoring the single-address SSH rule.

HTTPS, the reviewer access gate, CSRF enforcement, secure cookies, database/Redis health and a real queued diagnostic job also passed. Frontend assets match the existing local build; this deployment does not change the interface.

Reference: [OpenAI rate-limit recovery guidance](https://developers.openai.com/api/docs/guides/rate-limits), including server delay hints, jitter, bounded attempts and avoiding nested SDK retries.
