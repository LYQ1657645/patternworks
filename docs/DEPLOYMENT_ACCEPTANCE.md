> Current frontend release: [Loom deployment acceptance](LOOM_DEPLOYMENT_ACCEPTANCE_2026-10-20.md), 2026-10-20. Current backend acceptance: [async worksheet and regex acceptance](ASYNC_WORKSHEETS_AND_REGEX_ACCEPTANCE_2026-10-20.md). Earlier entries below are historical snapshots.

> Latest frontend update: [four-page navigation acceptance](NAVIGATION_ACCEPTANCE.md), 2026-10-18.

# AWS deployment acceptance — 2026-10-17

**2026-10-18 design revision:** the paper-and-collage data studio is now deployed locally and publicly: coral actions, lilac/blue/apricot functional areas, neutral data tables and a dark task panel. 18 frontend tests/build and responsive/public Safari checks pass. See [studio acceptance](UI_STUDIO_ACCEPTANCE.md). Previous design reports below are historical.

**2026-10-18 UI refresh:** warm-white/forest-green workbench, section navigation, responsive forms/tables and Safari select styling are deployed locally and publicly. 18 frontend tests and production build pass; public browser/asset checks pass. Backend unchanged; all 16 datasets remain READY/ACTIVE/Keep. See [visual acceptance](UI_REFRESH_ACCEPTANCE.md). Earlier test counts below retain their original scope.

**Latest update — session/state fixes:** R1–R5 are fixed and deployed; local/cloud 328 backend tests, 18 frontend tests and builds pass. See [acceptance](SESSION_AND_STATE_FIXES_ACCEPTANCE.md). Earlier entries are historical snapshots.

**Latest update — dataset deletion and retention (2026-10-18):** 311 backend tests locally/on AWS (12 real Spark integrations), 14 frontend tests and builds passed. Dependency review, original protection, seven-day Trash/restore and opt-in retention are deployed. Public Safari, scheduled expiry/purge and two-connection PostgreSQL races passed. All original 16 datasets remain ACTIVE/Keep and earlier results/CSV match. See [lifecycle acceptance](DATASET_LIFECYCLE_ACCEPTANCE.md); earlier snapshots below retain their original scope.

**Latest update — task history and dataset library:** 278 backend tests locally/on AWS (12 real Spark integrations), 14 frontend tests and production builds passed. Real Safari pagination/search/restoration and PostgreSQL ordered traversal passed. A historical CSV retry completed while another old task was viewed; the original 16 datasets remain intact after temporary-fixture cleanup. See [history acceptance](HISTORY_ACCEPTANCE.md). Earlier snapshots retain their original scope.

**Previous CSV export update:** 260 cloud backend tests (12 real Spark integrations), eight frontend tests and production builds passed. Safari cancelled/retried a real export, downloaded the 100,000-row processed result and restored its link after refresh. Every downloaded cell matched expectations; prior datasets remain intact. See [CSV export acceptance](CSV_EXPORT_ACCEPTANCE.md). Earlier snapshots below keep their original scope.

Latest multi-column update (2026-10-18): 246 cloud backend tests, eight frontend tests, and exact public browser/100,000-row multi-column acceptance passed. See [multi-column acceptance](MULTICOLUMN_ACCEPTANCE.md). Earlier snapshots below keep their original scope.

2026-10-18 audit-fix update: seven audited issues are fixed in the current deployment. Final backend regression is 227 passing tests; the frontend has five passing error-handling tests. See [fix acceptance](AUDIT_FIXES_ACCEPTANCE_2026-10-18.md) for current source patches, live checks, migration, rollback and limitations. Historical measurements below remain unchanged.

**2026-10-18 functional update:** the explicit regex replacement field and its local/cache behavior are deployed. The final backend passed 211 tests locally and 211 on AWS. See [Day 6 acceptance](DAY6_FUNCTIONAL_ACCEPTANCE.md) for the two source patches, current running image IDs and live output audit. The initial deployment identity and million-row measurements below remain the 2026-10-17 baseline.

Public endpoint: <https://patternworks.32-237-44-97.nip.io/>. A shared reviewer login is required; credentials are delivered privately and are excluded from source/package/Git. A public deployment is running; Safari rendering and a browser-triggered worker task passed. Fresh public CSV/XLSX imports and the live regex → date → category chain also passed on the eight-row synthetic fixture.

## Runtime and source identity

- User-created Lightsail instance: `patternworks-demo`, Sydney `ap-southeast-2a`, general purpose / dual-stack, 2 vCPUs, 8 GB RAM and 160 GB SSD.
- Static IPv4 `32.237.44.97`, resource `patternworks-demo-ip`, is attached to this instance. The free nip.io hostname resolves to that address. Attached Lightsail static IPs have no additional charge; release unused resources when retiring the demo. [AWS billing](https://docs.aws.amazon.com/en_en/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html)
- Ubuntu 24.04.4 LTS, x86_64; reported memory 7.6 GiB and root disk 154 GiB. Docker Engine 29.9.1 and Compose 5.6.0 installed from Docker's official apt repository using `scripts/bootstrap_server.sh`.
- Uploaded source archive SHA-256: `b5d777dcb66536b233252adf0c1c8ab99e4c82779be73770e6bbc07494b50180`. All 110 source-file hashes in its manifest were checked on the server before building. This identifies the deployment input; later documentation updates do not silently change that record.
- Both application images were built on the server's actual x86 architecture. Production preflight and Compose validation passed. Backend, Caddy, cleanup, Flower, frontend, PostgreSQL, Redis and worker are running; backend/database/cache health checks passed.
- The user's existing OpenAI key was saved only to the explicitly approved server path `/home/ubuntu/patternworks/.env.production` over SSH. Server Django/database/encryption secrets are independent of local settings. Environment file mode is 0600. Local `.env.local`, databases and dataset volumes were not uploaded.

## Verified externally

- HTTP returns 308 to the exact HTTPS endpoint. TLS validation passed with the system trust store, including hostname validation; certificate issuer is Let's Encrypt (YE1), with expiry `2027-01-15 00:40:51 UTC`. Certificate verification was never disabled.
- Unauthenticated HTTPS requests return 401 at the reviewer gateway. The gateway strips its Authorization header before the application.
- Authenticated session establishment succeeded with Secure cookies. A mutation without a CSRF token returned 403. A scripted HTTPS mutation needs the correct CSRF token and same-origin Origin/Referer, as a browser supplies.
- Real public HTTP → Redis broker → independent Celery worker → PostgreSQL/shared cache diagnostic passed: HTTP 202 in 1.237 seconds, final SUCCESS, cache `ok`. Job ID: `f359b818-b124-451a-ac7b-ab04f7d75e8c`.
- Authenticated public health endpoint reports database/Redis ready and OpenAI configured. A separate minimal real OpenAI request from the cloud worker passed; no S3 credentials or dataset values were sent by that check.
- The authenticated frontend HTML and both referenced JavaScript/CSS assets returned 200 with the expected title/content types. This verifies delivery of build artifacts, not browser rendering/interactions. External connection checks found ports 5432, 6379, 5555 and 5173 unreachable, consistent with the private service layout.
- The full cloud test suite passed: **204 tests in 78.16 seconds**, including five real Spark integration tests. Tests used a separate 4 GiB container/test database and did not call real S3/OpenAI services.

## Cloud million-row correctness and performance

Measured inside the actual production worker with a 4 GiB memory limit, Spark `local[2]` and four partitions. Each stage processed and checked all **1,000,000 rows** with exact cell equality; every ordered output digest matches the local final benchmark. The original source remained unchanged after the full chain.

| Stage | Processing seconds | Rows/second | Peak container MiB |
| --- | ---: | ---: | ---: |
| CSV import | 72.321 | 13,827 | 1,482.7 |
| RE2 replacement | 175.544 | 5,697 | 2,016.7 |
| Date normalization, cached | 138.938 | 7,197 | 1,760.8 |
| Categorization, cached | 138.573 | 7,216 | 2,082.4 |

Synthetic local CSV transport and preseeded validated LLM value caches were used; these timings exclude S3 network transfer and live model latency. Correctness verification runs separately and is not included in processing time. One hundred persisted-page requests of 25 rows each returned exact row IDs: median 0.328 ms, p95 0.363 ms. This measures the direct page service, not HTTP. All eight production services remained running after the benchmark, with backend/PostgreSQL/Redis healthy. Raw evidence: [deployment-million-evidence.json](deployment-million-evidence.json).

SSH uses key authentication with password authentication disabled. The cloud firewall now restricts ordinary SSH ingress to the current administrator IPv4 /32, retaining Lightsail browser SSH as a recovery path. AWS confirmed the saved rule, and a new SSH connection succeeded afterwards. The management address is kept in private evidence, not published here; update the rule through Lightsail browser access if the administrator address changes.

## Live public browser acceptance

Safari authenticated over trusted HTTPS and displayed the expected homepage and health indicators. The connection-check button completed at 100% / SUCCESS. The user entered the saved bucket-scoped read-only credentials directly into the app; neither credential was recovered or printed by the agent.

| Public UI check | Observed result |
| --- | --- |
| S3 discovery | `contacts.csv` and `contacts.xlsx` listed |
| CSV import | SUCCESS; 8 rows / 6 columns |
| Excel import | SUCCESS; Contacts worksheet, 8 rows / 6 columns |
| Natural-language regex | Real model generation, validated RE2 preview, then repeated generation showed Redis cache hit / no model call |
| Regex application | SUCCESS; 3 matched rows, 4 email matches, 3 changed rows |
| Date conversion | Real model preview; 8 normalized values; full application used 8 cached values / zero model calls; 8 columns |
| Country classification | Real model preview; 4 USA / 4 Australia; full application used 6 cached values / zero model calls; 10 columns |
| Browser refresh | Final SUCCESS task and 8-row / 10-column result restored |

These are genuine public HTTPS → Celery → S3/OpenAI/Redis/Spark operations on synthetic contacts, separate from the cached million-row benchmark. [Browser evidence and task IDs](deployment-browser-evidence.json). Chrome was not installed; the in-app browser separately blocked nip.io. The successful browser checks used Safari.

## Independent persisted-output audit

A read-only server audit passed after SSH access was restored. All five browser-created datasets (CSV import, Excel import, regex output, date output, category output) have eight rows. Every persisted page cell matched explicit fixture expectations; original source cells remained unchanged. Three-row cursor pages returned row IDs 1–8 exactly once for each dataset, and each artifact has four Parquet partition files. The audit checked persisted page contents and partition presence; it did not independently re-read Parquet values with a second engine.

All 11 browser-session jobs were SUCCESS. Regex generation was a real model call followed by a validated cache hit. Date and category previews each used one real model call; their full-column applications each reused cached values with zero additional calls. No new S3/model requests were made by this audit. [Full audit evidence](deployment-artifact-evidence.json).

## Administration and remaining delivery

- The administrator address was refreshed after a network change; a new strict-host-key SSH connection passed. The rule still permits only the current administrator IPv4 /32 plus Lightsail browser SSH. Future network-address changes require updating this rule through the console.
- Final GitHub submission and README demo video remain pending. This is a single-host local-Spark demo with manual artifact retention.

## Cost and shutdown

The approved instance plan is USD 44/month, billed hourly up to the monthly instance cap. The user's promotional credit applicability to Lightsail was checked privately before resource creation. Actual credit application/remaining balance depends on billing updates and other account usage; personal credit balances/identifiers are not part of the source report. Snapshots, unused IPs and other optional resources can incur separate costs. Stopping the instance does not stop instance billing. Back up needed data, then delete the instance and release unused associated resources when the review period ends. [AWS billing behavior](https://docs.aws.amazon.com/en_en/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html)
