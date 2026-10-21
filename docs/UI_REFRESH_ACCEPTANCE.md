# Light workbench visual refresh — 2026-10-18

The user selected a warm-white, forest-green workbench inspired by the spacing, editorial type and crafted cards in [Jiro](https://jiro.build/) and its public [Mymodz preview](https://jiro.build/templates/productivity-automation/modboard-organizer-landing-page-mymodz). No template source, paid assets or new dependencies were used.

## Changes

- Warm paper backgrounds, a light sidebar, green primary actions and a restrained serif page title.
- Working anchor navigation for source connection, task history and datasets/tools; mobile navigation, a skip link, visible focus and reduced-motion support.
- Consistent form controls, SVG icons and Safari select styling; clearer filters, selected records, history details, export and transformation panels.
- Larger, striped data cells, sticky column headers and a bounded scroll region. Existing controls, accessible names, hook ordering, processing handlers and privacy/consent text remain in place.

## Verification performed for this release

- All **18 frontend tests pass**; TypeScript and the production Vite build pass. The backend test suite was not rerun for this presentation-only change.
- Local in-app browser: desktop, 320px, 390px and 768px checks; no page-wide horizontal overflow at the measured widths, and no console warnings/errors. Narrow-screen input text is 16px to avoid automatic iOS form zoom.
- Public Safari: existing 100,000-row result loads; page two starts at row 26; dataset search returns no matches and clearing restores both records; historical CSV task details expose the existing download link; date/category selection switches and restores correctly. CSV download presence was checked; no new export/model/processing task was submitted.
- Final public JS and CSS bytes match the tested local build. Authenticated homepage/health return 200; unauthenticated homepage remains 401.
- Server read-only check: all **16 datasets remain READY / ACTIVE / Keep**, with zero active jobs. Four deployed frontend source hashes match the release manifest. Only frontend containers were rebuilt/recreated locally and on AWS; the public backend image is unchanged.

Evidence: [ui-refresh-evidence.json](ui-refresh-evidence.json). Browser screenshots and build/deploy logs are under the ignored `.runtime/ui-refresh/` directory.

## Release and rollback

- Public frontend: `sha256:7034ddf2c51cc3431c728cf8e14ca9a89ccac35b920de09452a637c99477ecb4`.
- Final four-file source archive SHA-256: `8cb9f717eabe9300af1f4a56e6230fcc5817d8369407b0a7e9facd23dec7d2f1`.
- Before-refresh image retained as `patternworks-frontend:before-ui-refresh-20261018`; source backup `/home/ubuntu/patternworks-before-ui-refresh-20261018`. A separate polish backup/tag is also retained.
- Public URL: https://patternworks.32-237-44-97.nip.io/ ; local URL: http://127.0.0.1:5173/ . Existing access protection and storage policies remain in effect.

This is a visual/browser regression acceptance, not a new million-row benchmark or a full backend rerun. External DM Sans loading retains a system-font fallback; the title uses local serif fonts. GitHub and video delivery remain deferred.
