# Multi-column regex replacement — 2026-10-18

The regex workflow now accepts one or more target columns. A single validated pattern and literal replacement are previewed separately for each selected column, then applied in one asynchronous Spark task to one new dataset. Original data and unselected columns remain intact.

## Behavior and compatibility

- The React form offers checkboxes, Select all and Clear selection. At least one column is required. Changing the selection invalidates the existing preview until it is regenerated; reverting to the same set does not create a false difference merely due to ordering.
- Generation accepts `columns: ["c2", "c5"]`. Legacy clients may still supply `column: "c2"`. Supply exactly one of these fields. Empty lists, duplicates, invalid keys and unknown columns are rejected before creating a rule or queueing work.
- Rules persist the selected columns. `0007_regexrule_columns` adds a JSON field; historical rules with an empty list resolve to their original single column. Read responses retain `column` as the primary/first target and also expose the resolved `columns`. Generation retries copy the complete selection and replacement.
- The model is called once per uncached instruction, regardless of target count. Cache keys remain independent of selected columns and literal replacement. A selection change regenerates local previews from the cached pattern. Actual dataset values, column names and AWS credentials are not added to the model request.
- Complete source samples are projected in one worker operation for all targets. Legacy datasets require at most one Spark context for this sample, rather than one context per column. SQLite/Spark sample iterators close on validation failure or cancellation.
- Per-column previews compute over the first 20 complete source values. Displayed examples have a shared text budget (roughly 512 KiB of UTF-8 text), reducing examples and displayed characters for wide selections. Limits are shown in the UI; clipping affects presentation only.
- Spark evaluates all selected cells through one RE2 array UDF per row and caches its results on disk for statistics and persistence. One projection updates the selected columns without changing source order or unrelated cells. Any selected-cell limit error fails the whole operation before publication.
- Exact text replacement and the two LLM date/category transformations retain their existing single-column interfaces; this feature extends natural-language regex replacement.

## Statistics

The result includes `column_stats`, keyed by column ID, with `matched_rows`, `match_count`, and `changed_rows`. Overall `matched_rows` and `changed_rows` count each source row once across all selected columns. `matched_cells`/`changed_cells` count the row-column pairs; `match_count` sums all occurrences across selected columns.

For example, one row containing an email in Email and two emails in Notes contributes **one matched row, two matched cells and three matches**. The result page displays both overall totals and a table of per-column results. Single-column totals retain their original meaning.

The preview adds `column_previews` with per-column examples/counts. Its legacy `examples` field describes the primary column; overall sampled-row counts use the union across selected columns. Existing historical previews remain readable.

## Validation

The machine-readable [multicolumn-evidence.json](multicolumn-evidence.json) records completed tests, deployment identity and live checks. Tests cover legacy/new API requests, session isolation, retry selection persistence, one cached model result across different selections, long values after the display boundary, 256-column preview payloads, empty/null inputs, literal Unicode/dollar/backslash/space replacements, exact per-column/overall counts, all-or-nothing failure, and real 256-column Spark execution.

The local full regression passed 245 tests before the final maximum-column case was added; the final feature suite passed all 19 tests including that additional case. The final cloud full regression passed **246 tests**, including **10 real Spark/JVM integrations**. Frontend tests passed **8**, and TypeScript/Vite builds plus Django system/migration checks passed. Automated tests use synthetic values, isolated SQLite and in-memory cache; actual public queue/browser checks are recorded separately in the evidence.

## Public browser and 100,000-row result

Safari selected Email and Notes from the new `ui-multicolumn-100k.csv` synthetic dataset and entered a literal replacement containing two leading/trailing spaces, `$1`, a backslash and Chinese text. The first generation made one model call (555 input / 149 output tokens). Adding Keep disabled Apply; regeneration was a cache hit and displayed Keep's own preview. Removing Keep and regenerating was another cache hit, followed by a real queued apply.

Job `5113854f-da7d-4cd6-9d11-ea90e326a8ee` succeeded; result `07840491-cf24-4c92-bae3-8bd8bd2265f0` contains 100,000 rows, four columns and four Parquet partitions. Exactly checked totals: **75,000 matched/changed rows, 100,000 matched/changed cells, 125,000 matches**. Email contributes 50,000 matching rows/occurrences; Notes contributes 50,000 matching rows and 75,000 occurrences. All 100,000 persisted source and result rows matched explicit expected values, including nulls, text IDs with leading zeros, literal replacement characters and untouched Keep values.

The real queued apply took 32.053 seconds from record creation to completion in this single observed run. It includes queueing, Spark startup, statistics, artifact persistence and publication; it is not a latency guarantee or a comparison with the earlier million-row benchmark. The synthetic import task used local fixture transport and took 23.345 seconds. While Spark was running, Safari successfully fetched source page 2 and displayed ID `000000026`. The result page displayed the correct overall totals and per-column table.

## Deployment and scope

The existing AWS application and HTTPS endpoint are retained. Source files and application images were saved for rollback, active jobs were checked before migration/restart, and existing database/Redis/dataset volumes were preserved.

- Source patch: 15 files; SHA-256 `8417780e50920e809e9a91559bb1d08e0b3f3da5d92d7f04d8d265c016776f84`.
- Source rollback: `/home/ubuntu/patternworks-before-multicolumn-20261018`.
- Image rollback: `patternworks-backend:before-multicolumn`, `patternworks-frontend:before-multicolumn`.
- Rolling back the application can leave the additional JSON column in place; no data deletion is required.

The new maximum-column test is a small synthetic correctness case, not a wide-table throughput guarantee. Existing million-row timings are historical and have not been relabeled as new multi-column benchmarks. The browser/scale check uses 100,000 synthetic CSV rows with local fixture transport instead of a fresh S3 download. Rule generation and application are submitted through the actual public React interface, model, Redis and Celery worker; changing the selected set reuses the cached pattern. Its index output is built by reading persisted Parquet, then every saved source/result cell is checked against explicit expectations. It is not an independent second-engine Parquet verification or a controlled speedup experiment.

CSV export was subsequently completed in [CSV export acceptance](CSV_EXPORT_ACCEPTANCE.md). Distinct-value limits for date/category inference and multi-host Spark remain separate. GitHub/video delivery remains deferred.
