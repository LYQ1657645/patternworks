# Workflow deployment acceptance — 2026-10-21

The current workflow and cosmic frontend are deployed at
[Patternworks](https://patternworks.32-237-44-97.nip.io/).
Reviewer authentication remains required.

## Real browser workflow

Local browser:

1. Reconnected the existing read-only S3 bucket.
2. Selected `contacts.xlsx`; worksheet discovery selected `Contacts` automatically.
3. Imported 8 rows and 6 columns. The data preview opened automatically.
4. Entered Transform from the preview and selected Email and Notes.
5. Generated a real, uncached OpenAI regex preview for email replacement.
6. Applied the rule, opened the result, exported and downloaded CSV.
7. Verified 6 Email replacements and 4 replacements across 3 Notes cells.
   Nulls, non-email text and the quoted comma example were preserved.

Public Safari:

1. The user's renewed S3 connection survived the frontend update.
2. Imported `contacts.csv` and verified the automatic preview handoff.
3. Generated a real, uncached rule for Email and Notes.
4. Changed the replacement value and confirmed Apply became disabled.
   Restoring the validated value enabled Apply.
5. Applied the rule and opened the new version through View result.
6. Exported and downloaded the actual CSV, then compared its parsed records
   with the local Excel-derived result: all 8 records and 6 columns matched.
7. Refreshed the final release, opened the successful export through Tasks,
   and verified the corrected result layout and Download CSV action.

The public run used `gpt-4.1-mini`: 563 input and 188 output tokens. Import,
generation, application and export all completed successfully. The source/result
parent relationship and task associations were checked using read-only aggregates.
The CSV contains 9 changed cells and 10 replacements, and is 633 bytes.

## Problems found and fixed

- A delayed saved-rule or transformation response could overwrite an edited draft.
  Both editors now preserve user edits; explicit generation still loads its result.
- Local Spark's default Python worker used system Python 3.9 while the driver used
  virtual-environment Python 3.12. The real Apply failed with
  `PYTHON_VERSION_MISMATCH`. The local launcher now defaults to the driver's
  interpreter and discovers the existing local Java runtime. Retrying the failed
  task through the UI succeeded. Production Docker already supplies its Python
  worker environment; no production backend change was necessary.
- Connected file loading briefly instructed the user to connect S3 again.
  That contradictory caption was removed.
- A legacy column layout applied flex-basis values as large vertical heights in
  resized desktop windows. The data-preview header now wraps in a row, keeping
  the table and controls visible. This was verified in local browser measurements
  and the final public Safari screenshot.

## Verification and release

- 63 frontend tests passed; TypeScript and production Vite build passed.
- 2 local-launcher regression tests passed. An independent two-row real Spark
  RE2 UDF also passed with the corrected interpreter.
- 62 allowlisted frontend source files matched the release SHA-256 manifest.
- Public JavaScript, CSS and lazy Three.js assets all matched the local final build.
- HTTPS verification, reviewer gate (401), CSRF rejection without a token (403),
  secure cookies, database/cache health and a real asynchronous diagnostic passed.
- Only the frontend container was rebuilt. Backend, worker, PostgreSQL and Redis
  container identities, images and start times remained unchanged at each switch.
- Original rollback source/image: `/home/ubuntu/workflow-20261021-backup`.
- Final frontend image:
  `sha256:71907eb649206a3ffc2e23c0808238cde73f0b907a05a7f3e45f6041c757b1a6`.
- Runtime evidence, manifests, logs and screenshots:
  `.runtime/workflow-release/`.
- Final public screenshot: `.runtime/workflow-release/public-result.png`.
- Downloaded public result:
  `/Users/ian/Downloads/patternworks-030f8606-68a4-4336-b16d-b3c61a19461c.csv`.

No S3 writes, dataset deletion, schema migration or credential recovery was
performed. The test inputs are the existing synthetic contacts files. This release
does not claim a new million-row benchmark or new date/category model acceptance.
The existing lazy graph bundle size warning remains.
