# Public galaxy release — 2026-10-21

Published to https://patternworks.32-237-44-97.nip.io/ with user authorization.

## Included

- S3 connection restoration after refresh and explicit disconnect.
- Equal-content version merging while retaining dataset and task records.
- Whole-constellation picking and camera-only focus in the existing scene.
- Replacement text explanation, aligned preview actions, and clearer animation preferences.
- Local development script creates its runtime directory only when started, rather than when imported by tests.

## Release evidence

- Source archive SHA-256: `9b6e7e2ea270d31713d85ff361d45554e5e11bf61be06eebb295662c1c048052`; 230 source files verified on the server.
- Frontend validation before packaging: 71 tests and production build passed.
- Backend local targeted validation: 40 tests, including actual Spark output and content identities. The development script adjustment passed its two targeted tests.
- Server container regression: 344 passed, 12 Spark tests deselected.
- The first attempt stopped before service switching because a development-script import tried to create `/app/.runtime`. The rollback restored source and image tags; the original application remained running. The corrected attempt passed.
- Full-content identity backfill completed for all 45 READY datasets, covering 8,200,262 rows using real Spark reads. This is maintenance evidence, not a new transformation performance benchmark.
- Dataset count remained 49. Jobs changed from 119 to 120 due to the explicit post-release diagnostic. PostgreSQL and Redis container IDs, images and start times were unchanged.
- HTTPS certificate validation, reviewer access gate (401 without credentials), CSRF rejection (403 without token), secure cookies, database/Redis health and a real successful worker/cache diagnostic passed.
- All served JavaScript/CSS assets, including lazy 3D chunks, match the local production build byte for byte.
- Safari displayed the new Animations label, merged original nodes, result nodes and data preview with aligned Export CSV and Transform controls. Further scripted camera actions were interrupted by the user interacting with Safari; the full controlled camera walkthrough remains documented in local acceptance. No fresh public S3 import or OpenAI generation was rerun for this release.

## Operations and artifacts

- SSH remains restricted to one current management IPv4 /32, plus the existing Lightsail browser SSH access. HTTP/HTTPS rules were unchanged.
- Backup: `/home/ubuntu/galaxy-20261021-backup-v2`, including source archive, database dump and original image IDs.
- Backend and worker image: `sha256:8b1f935810468f34477dea45e3df24d2f6caea200e7480aeb5f4f740a80dbc21`.
- Frontend image: `sha256:0a1a0bd68e04e61f31aa85b738c6c2116154e9f5e9b1eba3067bc51e5f999222`.
- Local evidence: `.runtime/galaxy-release/public-smoke.json`, `deployment-v2.log`, `data-before.json`, `data-after.txt`, `public-preview.png` and `firewall-updated.png`.
- Existing S3 objects and dataset artifacts were preserved. GitHub publication remains deferred.
