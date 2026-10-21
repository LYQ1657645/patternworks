# Four-page workspace acceptance — 2026-10-18

The studio visual style is retained. Four hash routes replace the long single page: `#/sources`, `#/history`, `#/datasets`, `#/transform`. Legacy named anchors resolve to matching pages. Navigation updates the title, selected sidebar link and heading focus, and supports browser back/forward and refresh.

Views remain mounted behind native hidden containers to retain in-memory form drafts, tool choice, selected dataset and preview pagination. Task polling remains at application level. A completion does not force navigation; View result opens the current job output. Drafts are preserved during navigation, not guaranteed after a full reload.

Transformation tools have three selectors: regex replacement, dates/categories, exact text replacement. Dataset selection and CSV export live in the dataset page. Lists and preview tables have bounded scrolling. Technical IDs, engine/cache counters, per-column results and CSV format explanations are available in disclosures. AI value-transfer consent, value limits, connection expiry and lifecycle safeguards remain available before consequential actions.

## Verification

- 20 frontend tests pass, including route fallback and visibility/selection regression probes. TypeScript/Vite production build passes.
- Local browser: four-page routing, browser back with source draft retained, direct tools-page refresh, 390px layout without horizontal overflow, no console errors.
- Public Safari: existing 100,000-row dataset opened, page 2 shows rows 26–50; page 2 survives a tools round trip. Regex draft survives switching tools and visiting datasets; synthetic draft cleared afterwards. Dates consent remains unchecked and preview disabled. Existing CSV download remains available. No transformation or paid model calls submitted.
- HTTPS returns 200 with existing authentication, 401 without; health is ok. JS/CSS exactly match local dist.
- Server source hash check passes for 11 deployed files. Backend image unchanged. All 16 datasets remain READY/ACTIVE with retention disabled; zero active jobs at audit.
- Source scan: 171 files, five configured secret values checked, zero matches. Frozen Day 5 archive unchanged.

## Deployment

Frontend image: `sha256:50c8d1bb471311d2ac6af5abb76d7e171e1ca01feb350a862f5ca45a79a27f77`.
Source backup: `/home/ubuntu/patternworks-before-navigation-20261018`.
Rollback frontend image: `patternworks-frontend:before-navigation-20261018`.
Local evidence: `.runtime/navigation/`; no GitHub changes or new cloud resources.

Scope: frontend navigation and copy only. Backend full suite and million-row benchmarks were not rerun for this release; earlier acceptance records remain historical evidence.
