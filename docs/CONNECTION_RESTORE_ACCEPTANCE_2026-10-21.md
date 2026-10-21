# S3 connection restoration — 2026-10-21

The connection screen follows the server's active S3 connection, independently
from the lifetime of imported dataset versions.

## Behavior

- On refresh, show a connection check before deciding which screen to render.
- A live server connection restores bucket, region, expiry and the file browser.
  No credential form is shown and no secret is stored in browser storage.
- Transient restoration failures retry twice. If checking still fails, offer
  Retry connection rather than claiming that the user is disconnected.
- Explicit Disconnect S3 revokes the owner's saved S3 connections, clears the
  source selection, and returns to the connection form. Datasets remain available.
- The existing one-hour S3 limit is unchanged. An expiry timer and window-focus
  check return to the form at expiry with a clear explanation. An expiry timestamp
  alone is retained in tab storage for the next refresh's explanatory message;
  it cannot grant access and is cleared on explicit disconnection.
- Completing a fresh connection confirms its metadata through the active
  connections endpoint instead of relying on a historical task as authorization.

## Verification

- 68 frontend tests passed, including delayed restoration, retry after network
  failure, expiry, preserved dataset selection and stale-response rejection.
- TypeScript and Vite production build passed. Existing graph chunk size warning
  remains.
- Live local browser: a new real read-only S3 connection survived two full
  refreshes, with both contacts files visible and the credential form absent.
  Explicit Disconnect S3 returned to the form; a subsequent refresh kept it
  disconnected. The dataset library still contained the previously imported
  original and transformed versions.
- Local screenshot: `.runtime/connection-release/local-restored.png`.
- Published with the subsequent full galaxy release. See
  `GALAXY_RELEASE_ACCEPTANCE_2026-10-21.md` for public verification and rollback details.
  The earlier frontend-only `.runtime/connection-release/` package is superseded.

The graph's version numbers enumerate records within a source family. Original
nodes can be repeat imports of the same S3 object. Result nodes contain saved
transformation outputs; cancelled attempts are not successful copies. Importing
an object does not upload a replacement to S3.
