# Planet appearance release audit — 2026-10-21

Status: published to https://patternworks.32-237-44-97.nip.io/. Local workflow, public infrastructure/asset checks and the renewed public S3 browser walkthrough passed.

## Scope

Four deterministic texture families (bands, clouds, continents, craters) remain stable within a source file. Operation colors remain gold, purple, cyan and peach. Original spiral dust and quiet rotation are retained; interaction glow, acceleration and file-name underlines are removed. The shared background is slightly more visible. The separate design comparison page is not a production entry point.

The release also includes the previously reviewed regex match-field correction: Chinese/English email nouns are supported shorthand, while extraction and unsupported regex features remain rejected. Model prompt cache version is incremented. Duplicate generation error banners are avoided.

## Current checks

- Frontend: 77 tests and TypeScript/Vite production build passed.
- Local backend: 356 passed, 12 JVM/Spark tests deselected. The AWS worker image passed all 368 tests, including those 12 real Spark integrations, in 176.03 seconds.
- Build retains the existing lazy 3D bundle size warning.
- Historical million-row evidence is unchanged. No new million-row timing is claimed for this visual release.



## Local browser workflow

A renewed read-only S3 connection listed the two existing synthetic fixtures. XLSX worksheet discovery selected Contacts, import opened an eight-row/six-column preview, and the Chinese match description 邮件 produced a validated rule for Email and Notes. Editing target columns/replacement disabled stale Apply. Applying saved a new version; the actual downloaded CSV matched all 48 independently expected data cells. Tasks retained connection, worksheet, import, Generate, Apply and export records. Manage kept IDs/details collapsed and required a file-name confirmation before Trash.

An initial local worksheet request exposed SQLite deferred transaction lock-upgrade contention. Local SQLite now uses IMMEDIATE transactions with a 20-second busy timeout; a two-connection read/write test confirms both updates survive contention. The successful workflow was repeated after restart. Production continues to use PostgreSQL with unchanged settings.

The local chain continued through real date normalization and categorization. All 80 final data cells matched independently specified expected values, and all 48 original cells stayed unchanged. The regex generation was a fresh model response (cache_hit=false). The standalone comparison page is static and makes no model requests.

## Public release evidence

- Source archive SHA-256: `49978a2f68b29ad65e237a18fc122ceaea89be204f08920cf39bfd3e3d81201b`; all 237 packaged source files verified on the server before build.
- Backup: `/home/ubuntu/planet-20261021-backup`, containing previous source, database dump, image identities and build/test logs. Automatic error rollback was prepared and was not needed.
- Backend/worker image: `sha256:46da58a8daa59b9737ba8500b6972965b9c78c6744957f3c0d1e8f9343dbf5c0`.
- Frontend image: `sha256:8bcdd51e028301b5554a091bc21799c295b7d38942987712276838144d2b04e4`.
- PostgreSQL and Redis container identities/start times were preserved. All 49 existing dataset records had the same aggregate metadata digest before/after switching. S3 objects were not modified.
- Validated HTTPS certificate, 401 reviewer gate without credentials, 403 CSRF rejection without token and Secure cookies. Database/Redis health passed; a new diagnostic completed through the real worker/cache.
- All four served JS/CSS assets match the local production build byte for byte, including the lazy planet and 3D-library chunks. The dev comparison HTML is not included in the production dist entry points.
- Evidence: `.runtime/planet-release/{deployment.log,local-workflow.json,public-smoke.json,data-before.json,data-after.json,local-result.png}`. Runtime evidence is not included in Git; this report provides the non-secret summary.

Documentation was refreshed after the source archive was built to record observed results and current button names. These documentation-only additions do not change the application image hashes above.

## Final public browser workflow

After the user renewed the public read-only S3 connection in Safari, refreshing retained the connected file list. Selecting contacts.xlsx automatically loaded and selected its Contacts worksheet. Import completed with eight rows and six columns. The Chinese match description 邮件 generated a validated preview for Email and Notes; Apply created a new saved version. Export completed, and Safari downloaded the actual CSV. All 48 data cells matched an independently computed expected result, including nulls, unmatched text and quoted commas.

A separate read-only server check confirmed all 48 original cells remained unchanged, all 48 result cells were correct, and pagination returned 3/3/2 rows without omissions or duplicates. Import, Apply and export jobs were SUCCESS. Result dataset: `70da244d-0e7a-4eeb-b0ec-87687f819c6e`; source: `4cb81ea9-f52b-4aae-bae3-7407f80d66f8`; export job: `570778e5-8ff7-47ca-8f56-b94540cf1532`.

Additional local evidence: `.runtime/planet-release/public-workflow.json`, `public-data-verification.json` and `public-result.png`. Fresh acceptance adds new datasets/jobs after the preservation snapshot; the 49-record preservation count refers to the pre-release records, not the final database total.

## Scale evidence and remaining delivery

The existing 2026-10-20 AWS benchmark processed a synthetic 1,000,000-row CSV through real Spark worker entry points: import 81.139 s, regex 73.848 s, cached date normalization 48.177 s and cached categorization 51.384 s. Each stage passed independent exact-cell checks and preserved its source. Highest sampled memory was 1974.6 MiB under a 4 GiB worker limit. See `million-acceptance-20261020.json` and `ASYNC_WORKSHEETS_AND_REGEX_ACCEPTANCE_2026-10-20.md`.

These are single-host results with a local synthetic fixture transport and prevalidated date/category caches, excluding S3 transport and live model latency. They do not establish million-row Excel, high-cardinality model inference or multi-machine scaling. Date/category columns remain limited to 500 distinct non-null values. This release did not rerun or claim new million-row timings.

GitHub submission and the recorded demonstration remain the next delivery stage. No repository or video publication is claimed by this acceptance.
