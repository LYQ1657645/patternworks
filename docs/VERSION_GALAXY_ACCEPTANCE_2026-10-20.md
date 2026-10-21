# Version galaxy acceptance — 2026-10-20

The dataset page now presents saved versions as textured 3D planets, with operation-colored paths for persisted parent relationships. Sources and Transform remain separate pages. Activity replaces the standalone History navigation item with a keyboard-accessible drawer, retaining task filters, pagination, cancellation, retry eligibility, errors and export links.

## Data semantics

- A successful Apply creates a saved result planet. Generate creates a rule/preview, not a result planet. The inspector can reopen the latest saved regex rule for review.
- Multiple target columns remain one regex operation; column-level changes appear in the edge inspector. This release does not add multi-rule pipelines.
- The graph is scoped to the current live application session. It groups imports by bucket/object key/worksheet across reconnections, while each import remains an independent root. Edges always use Dataset.parent; imports are not connected by invented transformations.
- Only READY datasets become planets. Failed/cancelled attempts remain in Activity. Trashed/purged versions keep their lineage but cannot be opened as data. No source data, dataset files or S3 objects are changed by browsing the graph.
- The read-only lineage endpoint defaults to 200 records, accepts 50–500, pins selected ancestry and explicitly reports truncation. Limits apply to metadata records, not data rows.
- Planet colors distinguish imports, regex, dates, categories and unavailable versions. Background stars are decorative. A version list provides a keyboard-accessible alternative; missing WebGL or a failed 3D module load does not remove the list.

## Validation

- Local backend: **338 passed, 12 Spark tests deselected**. New coverage checks session isolation, grouping boundaries, reimports, branching, Generate vs Apply, unavailable ancestry, operation details, bounded graph loading and cycle termination.
- Frontend: **39 checks passed**; TypeScript and production Vite build passed. Controlled hook tests are not a substitute for browser acceptance.
- Server Docker image: **66 targeted tests passed**, covering lineage, history, sessions and lifecycle. The pytest test-settings database is separate from live PostgreSQL.
- Existing million-row/Spark processing was not changed or rerun for this presentation/read-only metadata feature.
- Local browser QA used explicitly labeled synthetic copies of existing acceptance data. Safari verified direct planet clicks with camera focus and direct path clicks with operation details. The in-app browser verified version-list selection, returning to Transform, hidden star map outside Datasets, Activity focus/Escape behavior and layouts observed at desktop, tablet and narrow mobile CSS widths. No page-level horizontal overflow was found at the inspected widths (1280, 960 and 300 CSS px; browser zoom affects requested viewport dimensions).
- Production Safari loaded the new galaxy against existing contacts.csv data: **4 saved versions and 1 actual transformation**. The edge inspector showed Email, the recorded instruction and 6 changed rows. Preview before opened the original email values; the transformed preview retained redacted values. Activity listed the cancelled import and correctly explained that its expired source connection must be reconnected before importing again.

## Rendering and delivery

- Three.js / 3d-force-graph use procedural local planet textures and a decorative starfield; no external planet assets or data services are required.
- 3D modules load on the dataset route. The scene is disposed on departure, hidden-tab rendering pauses, and reduced motion disables planet rotation, path particles and camera transitions. Device pixel ratio is capped at 1.75.
- Final visual review corrected initial camera distance using actual camera field of view, so multiple independent import roots fit without initial clipping. Camera controls occupy a separate toolbar so they cannot obscure bottom planet labels. Single-column operation statistics are no longer repeated.
- A sizeable lazy graph chunk remains (~320 KB gzip, plus the lazy planet/Three chunk ~61 KB gzip). This is an intentional cost of the 3D renderer. No formal GPU/FPS benchmark or 500-planet browser stress test is claimed.
- Public deployment: https://patternworks.32-237-44-97.nip.io/#/datasets . Backend/worker/cleanup/flower/frontend images updated; PostgreSQL, Redis and Caddy volumes/configuration preserved. No schema migration required. Deployment preflight found zero active jobs.
- Server rollback source backup: `/home/ubuntu/galaxy-20261020-backup`. Local evidence: `.runtime/galaxy/` (test/build/deployment logs and screenshots; excluded from source delivery).
