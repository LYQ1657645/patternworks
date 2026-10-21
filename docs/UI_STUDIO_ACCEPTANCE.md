# Paper-and-collage data studio — 2026-10-18

The user asked for a more distinctive design and less green. This revision takes visual inspiration from the public [Jiro Mymodz preview](https://jiro.build/templates/productivity-automation/modboard-organizer-landing-page-mymodz): paper grids, editorial headings, layered notes and restrained complementary colour.

## Design delivered

- Warm neutral surfaces and charcoal type/navigation; coral primary actions, lilac regex/history surfaces, blue datasets/exports and apricot date/category tools. Green is reserved for positive status cues.
- A responsive grid-paper hero with a code-native data-card collage, a taped note, a hand-drawn arrow and a serif headline. The illustration is decorative (`aria-hidden`), not live application output.
- Layered CSV/Excel empty-state cards, a lavender sidebar note and a charcoal task panel with light progress text.
- Existing form labels, controls, input handlers, consent requirements, data selection and job behaviour are retained. No new packages or downloaded template assets.

## Verification in this revision

- 18 frontend tests pass; TypeScript and Vite production build pass.
- Local in-app browser verified at 320, 390, 768, 1024, 1280 and 1440 CSS-pixel widths. Measured document widths stay within the viewport; the 1280×900 sidebar has no internal overflow. Mobile artwork is suppressed to leave room for controls.
- Public Safari: refreshed final design, 100,000-row existing result, source/summary/table readability, page-two row 26 and return to page one, existing CSV download link, regex and date/category form layout, and populated dark task panel checked.
- Public JS/CSS bytes match the local build; authenticated homepage and health succeed; unauthenticated homepage remains 401.
- Three deployed source files match the release manifest. All 16 datasets remain READY/ACTIVE with no automatic retention, and no jobs are active. No new LLM or transformation job was submitted for visual verification.
- Only the frontend containers were recreated. This is a frontend visual regression acceptance; the backend suite and million-row benchmark were not rerun.

Evidence: [ui-studio-evidence.json](ui-studio-evidence.json). Screenshots and build/deployment logs are retained under ignored `.runtime/ui-studio/`.

## Release

- Public frontend image: `sha256:c4d6e9a61347df228ec1aaea46732a487bd4dce55617d03167bffd6ac5342cd5`.
- Source archive SHA-256: `cca3e0d7a8883fc31f184269156a24f8745938ff00e52dfdc726d22bf702535e`.
- Previous design retained as image `patternworks-frontend:before-ui-studio-20261018`, with source backup `/home/ubuntu/patternworks-before-ui-studio-20261018`.
- Local: http://127.0.0.1:5173/ ; public: https://patternworks.32-237-44-97.nip.io/ .

GitHub and video delivery remain deferred. The prior green workbench acceptance remains a historical snapshot.
