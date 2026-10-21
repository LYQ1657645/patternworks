# Public deployment preparation — single-host assessment demo

Status: the AWS instance and public HTTPS application are now running at <https://patternworks.32-237-44-97.nip.io/>. See [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md) for the actual configuration, verified checks and outstanding acceptance. This document remains the setup/redeployment guide. Local scale results are not a cloud performance guarantee.

## Proposed environment

Use the existing AWS account with one **Lightsail Linux/Unix instance with public IPv4, 2 vCPUs, 8 GB RAM and 160 GB storage**, using Ubuntu 24.04 where offered. The currently published bundle price is **USD 44/month**, billed hourly up to the monthly cap. Taxes, domain registration, snapshots and other services are outside that figure; actual account credits and the final console price must be checked before creating resources. [AWS bundle specifications](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)

The local benchmark uses Spark `local[2]`; one Celery execution slot and a 4 GiB worker limit leave room for PostgreSQL, Redis, the API, Flower and the OS on an 8 GB host. This is a single-host deployment with persistent Docker volumes, not an external Spark cluster or a highly available service. Local verification used arm64; a different server architecture requires its own live acceptance.

Before resource creation, confirm the plan/budget, region, SSH access and a DNS hostname/subdomain that can point to a static server address. This template uses hostname-based public HTTPS. A free subdomain can be considered if no domain is available; no domain purchase is necessary for the preparation work.

## What is prepared

- `compose.production.yaml` overlays local Compose. Caddy alone publishes public ports 80/443; frontend, API, PostgreSQL and Redis have no public host bindings. Flower retains only its loopback binding for SSH-tunneled administration.
- Caddy is pinned to the tested official image digest (version 2.11.7 at verification). It provides automatic HTTPS and a shared reviewer password gate; the gateway removes its Authorization header before proxying to the application. Give the reviewer password privately alongside the final URL, not in Git. [Caddy authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth), [reverse proxy behavior](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- Production mode enforces HTTPS, Secure session/CSRF cookies, CSRF validation, explicit hosts and private trusted proxy headers. The internal health check is exempt from HTTPS redirection. The proxy trust setting assumes direct API/frontend ports remain private as configured.
- Worker memory/pid limits, a shutdown grace period and rotated application/proxy logs are configured. Redis uses AOF and `noeviction`; an unavailable/full queue/cache fails visibly rather than silently evicting results.
- Offline validation checks the merged public-port layout, Caddy syntax/auth/header behavior, and actual production-mode Django requests against an ephemeral in-memory database. See [deployment checks](day5-deployment-checks.json). DNS, certificate issuance and external networking remain unverified.

## Server preparation, after the resource decision

1. Create the selected Linux instance, attach a stable public address, and point a DNS A record at it. Allow TCP 80/443 (UDP 443 is optional for HTTP/3); restrict SSH to the administrator's address. Keep 5173, 5555, PostgreSQL and Redis private.
2. Install Docker Engine and the Compose plugin using [Docker's official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/). This overlay requires Compose 2.24.4 or newer. Python 3 is needed for initialization/preflight; application dependencies are built inside Docker.
3. Transfer only the source archive produced by `python3 scripts/package_release.py`, or clone the eventual repository. The archive contains a SHA-256 file manifest and excludes real env files, credentials, runtime artifacts, dependencies and Git metadata. Do not upload `.env.local` or the local dataset volume.
4. In the unpacked `patternworks` folder, run:

```bash
python3 scripts/init_env.py --production
chmod 600 .env.production
```

This generates fresh server Django/encryption/database secrets while preserving populated values on repeat runs. It does not copy the local OpenAI key. Configure the server key privately only after confirming its destination.

Edit the server-only `.env.production` privately:

```dotenv
PUBLIC_HOST=your.actual.hostname
TLS_EMAIL=your-contact-email
DJANGO_ALLOWED_HOSTS=your.actual.hostname,localhost,127.0.0.1,backend
DJANGO_CSRF_TRUSTED_ORIGINS=https://your.actual.hostname
```

Also configure `OPENAI_API_KEY`, the reviewer username and a bcrypt password hash. Generate the hash using Caddy's interactive prompt, keeping the plaintext password out of command history:

```bash
docker run --rm -it --entrypoint caddy caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f hash-password
```

Save `DEMO_PASSWORD_HASH` in single quotes inside `.env.production` so Compose preserves its dollar signs. Keep `DJANGO_DEBUG=false`, `TRUST_PROXY_HEADERS=true` and `APP_ENV_FILE=.env.production`.

5. Perform private preflight and configuration validation. Do not print the expanded Compose configuration because it includes secrets.

```bash
python3 scripts/check_deployment.py
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml config --quiet
```

6. Once the settings and publication are authorized, build/start the production stack:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up --build -d
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml ps
```

Caddy certificate issuance requires the real hostname and inbound ports to reach this server. Do not bypass certificate errors to submit AWS credentials.

## Live acceptance still required

From an external browser, verify the trusted certificate and reviewer gate; then test CSRF/session behavior and the real HTTP → queue → worker → PostgreSQL/Redis path. Reconnect the bucket through the HTTPS form and import the existing synthetic CSV/XLSX fixtures. Verify regex generation/application, date normalization, classification, caching and pagination. Keys must be entered privately; do not post them in chat or logs.

Re-run a representative scale check on the actual server before quoting its performance. Keep Flower private, inspect disk space and container health, and retain application secrets separately from source. Volumes survive normal restarts; do not use `down -v` on data that must be preserved. Artifact retention remains manual in this compact demo.

After external acceptance, record the public URL, release identity and final demo video in the README. The current preparation is not a substitute for those final deliverables.
