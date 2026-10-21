# Task history and dataset library — 2026-10-18

The public app now provides paginated **Task history** and a searchable **Datasets** library. Each page displays ten records. Previous/Next and Refresh are available; refreshing a list returns to its first page. Existing processing, preview and CSV export workflows remain available.

## Behavior

- Task history shows type, creation time, ID, status, progress and stage. Filters combine task status and type. **View task** opens persisted details, timestamps, attempts/recovery counts and safe errors. Successful tasks can open their source/result dataset; completed CSV exports offer a download link. Failed/cancelled jobs can be retried as new tasks, and queued/running jobs can be cancelled.
- Historical selection has its own detail polling. Looking at an old task never replaces the active task being tracked by Task activity. Cancel updates the active tracker only if IDs match; retry submits a new task and uses the existing busy guard.
- The dataset library searches the entire session-owned collection by file-name/path substring, worksheet substring, or exact full dataset UUID. Name search is case-insensitive; `%` and `_` are literal text. Status filters apply before pagination. A query is at most 256 characters. Search is explicitly submitted; changing filters resets the page.
- The library shows dataset type, creation time, ID, row/column counts, worksheet and status. Only READY datasets open a preview. An already selected dataset stays open when searching, paging or finding no matches.
- Filters, cursor/page stacks and selected task/dataset IDs are remembered in this tab's `sessionStorage`; no credentials or result rows are stored there. Refresh restores them. Storage is optional. An expired/invalid saved page resets to page one with a notice; an unavailable saved selection is cleared.
- Access remains scoped to the existing browser session. This feature does not add accounts or make records from other browser sessions visible. The server retains records, while list visibility still depends on the session cookie.

## API and ordering

| Endpoint | Query | Response |
| --- | --- | --- |
| `GET /api/jobs/` | `cursor`, `limit` (default 10, max 100), `status`, `kind` | `jobs`, `next_cursor` |
| `GET /api/datasets/` | `cursor`, `limit` (default 25, max 100), `status`, `q` | `datasets`, `next_cursor` |

Existing record payloads are retained. Startup asks for `jobs/?limit=1`; the library and history request ten at a time. Detail, cancellation, retry and download reuse the existing session-protected endpoints.

Both lists order by `created_at DESC, id DESC`, including a UUID tie-breaker. Pagination queries the last timestamp/ID instead of using offsets and fetches at most `limit + 1` records. Newer inserts do not duplicate or shift an ongoing forward traversal. Status values remain live; this is not a frozen snapshot of status-filter membership. Refresh starts a new traversal to see newer records.

Cursors are signed, expire after 24 hours, and are bound to resource, owning session, filters and page size. The session identifier is part of the private signing salt and is not encoded in the public cursor. Tampering, expiry or scope changes return 400. Composite owner/time/ID indexes are installed by migration `0009_history_indexes`; substring search remains a database scan within the owning session rather than a dedicated full-text search service. [Django signing](https://docs.djangoproject.com/en/5.2/topics/signing/), [Django indexes](https://docs.djangoproject.com/en/5.2/ref/models/indexes/).

## Validation

- Final local backend regression: **278 passed in 47.08 s**. Final AWS regression: **278 passed in 145.89 s**, including **12 real Spark/JVM integrations**. Frontend: **14 passed**; TypeScript/Vite, Django checks and migration consistency passed.
- Backend coverage includes 53 tied-time records across many pages, insertion of a newer record, deterministic replay, traversal beyond the old caps, empty pages, invalid bounds/filters, cursor tampering/expiry/session/resource/filter/page-size binding, literal wildcard/Unicode/UUID search and credential-field exclusion. Frontend tests cover cursor branch replacement, filter resets, state restoration/validation, unavailable storage and successful source/result resolution.
- On the deployed PostgreSQL database, internal APIClient traversal exactly matched all **37** owned job IDs across six seven-record pages and all **30** dataset IDs across five pages. File name, full UUID and Chinese worksheet queries matched explicit expected IDs. Cross-session cursor reuse returned 400. This is actual deployed Django/SQL execution, separate from the real public browser checks below.
- Safari verified Task page 2, Dataset page 3 (beyond the previous 25-record cap), old task details, old dataset preview, search for the oldest data file, Chinese worksheet search, empty search without losing the preview, combined task filters and refresh restoration of page/filter/selection. History links opened both an imported source and a processed result.
- Safari retried the real previously cancelled CSV task as `c9a2588d-f1a0-43b6-9df6-d2abdc6431c3`. While it was RUNNING, another old CANCELLED task could be viewed without interrupting it. The retry succeeded; the original cancelled record remains intact. Its 100,000-row CSV has the same 5,250,024 bytes and SHA-256 `ac29b334de9052a0f8eb2d51730dab5d15c41f208bac87e414d754b24f4f337f` as the independently checked export.
- The browser/SQL test used 28 separately marked small dataset copies and 28 explicitly labelled closed history fixtures. These history fixtures were not queued/executed tasks. All 56 test records and the copied dataset directories were removed with ID/group/dependency guards after validation. The real retry and diagnostic remain as audit records. The original 16 READY datasets remain; the prior five-dataset and 100,000-row source/result audits passed again. Final browser state shows normal lists and the actual processed result.
- HTTPS/authentication/session/CSRF/queue checks passed; published assets match the local build. All 51 backend source hashes and the complete 17-file source patch match deployment. Final active jobs, expired credential ciphertext and uncleaned cancellations are zero.

Machine-readable evidence: [history-evidence.json](history-evidence.json).

## Deployment and limits

Final 17-file patch SHA-256: `37979ad3b6a05266031516354c5d4a07f43b1d40273c3ff56df69dd92c4ccd5f`. Source rollback: `/home/ubuntu/patternworks-before-history-20261018`; image tags: `patternworks-backend:before-history`, `patternworks-frontend:before-history`. No active jobs were present before migration/restart, and data volumes were retained. The original Day 5 archive is unchanged.

These checks establish functional pagination/search and regression coverage, not a high-concurrency or million-record search benchmark. There is no total-page count, arbitrary page-number jump, account-wide history, deletion/retention policy or new multi-host Spark claim. GitHub/video delivery remains deferred.
