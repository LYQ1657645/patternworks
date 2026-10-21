# Usability improvements — 2026-10-19

## Review and changes

The guided customer walkthrough exposed five concrete problems, beyond basic feature completeness:

1. Excel tab names had to be guessed or obtained outside the application. Selecting XLSX/XLS now reads tabs automatically, preserving workbook order, defaulting to the first, and allowing dropdown selection. CSV has no tab field. Failures offer a reload action; import is disabled until discovery succeeds. Switching files unmounts the old picker and ignores late responses. Re-clicking the current file retains its sheet.
2. New transformation forms silently selected the first column, frequently ID. All three tools now start with an explicit selection placeholder/empty checkbox set. Date/category mode changes reset the column, and identifier-like columns display a warning. Previously saved, intentional previews still restore their settings.
3. Appended date/category results could be mistaken for unchanged source data. The selected dataset shows operation and creation time; a visible result summary names the last two output columns and shows counts, with a direct horizontal scroll button. Any non-normalized/non-classified statuses request review. The source columns remain intact.
4. Retrying a missing worksheet repeated a permanent input error. Retry eligibility now directs users to correct the file/worksheet and import again. Cancellation and transient errors remain retryable. Import errors also no longer appear inside the successful S3 connection box.

5. Classification no longer pre-fills Sales/Support/Other as actual inputs. Users provide their own labels and choose a valid fallback; duplicate labels and invalid counts are blocked before preview.

## Verification

- Local backend: 322 passing non-Spark tests; 12 Spark tests reserved for the server runtime.
- Frontend: 24 passing tests and TypeScript/Vite build.
- New tests cover ordered/Unicode tabs, legacy XLS adapter, corrupt/oversized workbooks, session ownership/expiry, no dataset/job creation on discovery, permanent-input retry policy, default first tab, stale-response rejection, reload on failure, and explicit target columns.
- The frontend hook harness checks actual component logic but does not replace browser verification.
- Initial server full-suite run used the web backend service limit (768 MB), causing JVM disconnects in four Spark tests: 330 passed, 4 failed. The release gate remained closed. Full-suite validation was moved to the actual worker service configuration (4 GB); final result recorded below.
- Server release and browser checks: recorded after deployment below.

## Boundaries

Discovery reads S3 once and import reads it again; it does not cache source files or create datasets. Existing source/expanded Excel size limits apply. XLSX discovery reads workbook XML rather than rows or shared strings; S3 download progress has a 15-second deadline and returns an actionable retry error. Large/slow file discovery is still synchronous; resumable metadata loading is not implemented.

No data-grid editing, column type inference, team accounts, source-file mutation or retention-policy changes were added. These would change the product scope and deserve separate design. Source data, existing job history and dataset artifacts are retained. GitHub publication remains deferred.

## Final deployment acceptance

- Server full suite in the worker configuration: **334 passed**, including all 12 Spark tests, in 146.96 seconds. Frontend: **24 passed**, TypeScript/Vite production build passed.
- All eight production services are running; backend, PostgreSQL and Redis health checks pass. Twelve changed source-file hashes matched the final local manifest. Prior application images and changed sources were retained for rollback.
- Public Safari: selecting `contacts.xlsx` automatically displayed `Contacts`; selecting the file again kept the chosen tab. Import succeeded at 22:32:56 Australia/Melbourne with 8 rows and 6 columns. One new test import was created; pre-existing datasets/history remained available.
- Public Safari: new regex selection was empty; dates displayed Choose a column to transform. Explicit ID selection displayed the identifier warning. Switching to classification cleared the column and displayed empty labels/fallback. No LLM preview or transformation was submitted during these checks.
- Public Safari: the existing 18:26:15 date result displayed 8 normalized and the two appended column names; Show result columns scrolled both result and status into view. The third row showed original `03 Oct 2026` alongside result `2026-10-03`.
- Browser screenshots are retained under ignored `.runtime/usability/`; machine-readable deployment identities are in `usability-deployment-evidence.json`.
