# Dataset workflow acceptance — 2026-10-20

- Selected preview, transform action, row paging and CSV export precede the library.
- New successful imports navigate to datasets at the top. Opening another dataset scrolls to the top.
- Library defaults to three records; expansion reveals the current page and pagination. Search/filters are disclosed by a button.
- Opt-in `latest_imports` groups active original imports by bucket, object key and sheet before cursor pagination, including across reconnections. Results remain separate; trash and dependency views retain individual records. No records are deleted.
- Backend: 333 passed, 12 Spark tests deselected. Frontend: 36 passed; production build passed.
- AWS: 19 history tests passed; backend/worker/cleanup/flower/frontend containers healthy after rollout. Backup: `/home/ubuntu/dataset-flow-20261020-backup`.
- Safari public UI verified preview-first order, visible transform CTA, closed search, and reduction from five imports to two source entries (contacts.csv and contacts.xlsx with newest timestamps).
- Local browser verified transform navigation retains the selection, search disclosure and expansion. A new live S3 import was not submitted during this change. Million-row/Spark execution was not repeated for these presentation/list-query changes.
- Screenshot: `.runtime/dataset-flow/public-preview.png`.
