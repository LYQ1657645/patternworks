# Local galaxy continuity acceptance — 2026-10-21

This document records the local preview checks. The subsequent public deployment is recorded in `GALAXY_RELEASE_ACCEPTANCE_2026-10-21.md`.

## Behavior

- The library collapses proven equal content within one source family and lifecycle. Different source families, schemas, row order, null values or full cell contents remain distinct. Missing signatures are never guessed from names or row counts.
- Original dataset and task records remain intact. A merged planet retains the latest import timestamp for library display and member IDs for resolving previews. Cancelled/failed attempts stay in Tasks.
- Edges map to visible content nodes while preserving their actual persisted before/after dataset IDs. No-op operations create no extra planet or self-edge; their execution remains in Tasks.
- Clicking a constellation volume or its label focuses that family. A second click on a planet opens data. Transparent spherical picking volumes also work when the map is rotated.
- Focus changes only the camera in the same Three.js scene. Coordinates, planet textures, spiral dust, geometry and graph data are retained. Reset returns to the prior overview camera. Preview close restores the focused camera.

## Content signatures

New ingestion computes SHA-256 from column schema and ordered per-row digests of full values before preview truncation. Temporary SQLite digest rows bound memory and make partition traversal order irrelevant.

Existing local Parquet artifacts were indexed with `manage.py index_content_identity`. The command streams complete ordered rows using Spark and updates metadata only. It skips missing artifacts and already-indexed datasets. A future public release must deploy both frontend and backend and backfill existing artifacts; this is no longer a frontend-only release. The previous `.runtime/connection-release` package does not contain this change and must not be used for this release.

## Evidence

- Frontend: 71 tests passed, including duplicate content, unknown identity, lifecycle/source isolation, edge endpoint provenance, merged preview selection and camera framing of a distant family.
- Backend: 40 tests passed, including actual Spark ingestion/transform output and full-value content identity beyond preview truncation.
- TypeScript/Vite production build passed. Existing lazy 3D chunk size advisory remains.
- Real local browser: click empty space inside contacts.xlsx constellation; inspect focused screenshot; open transformation edge; Preview after renders the expected masked data; close restores the same constellation; Reset restores overview; click empty space in Demo workbook.xlsx constellation successfully focuses it.
- Screenshots: `.runtime/galaxy-continuity/overview.png`, `.runtime/galaxy-continuity/focused.png`.

Existing cosmic art direction retained; this was an interaction change, not a visual redesign. Browser checks used the available in-app browser at desktop viewport size. No Chrome-based skill inspector was run.
