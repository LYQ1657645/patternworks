#!/usr/bin/env python3
"""Offline Compose/Caddy + production-mode Django acceptance, using fake secrets.

Only a temporary backend container runs, with an in-memory database. No ports are
published, no cloud resources created, and no model calls made.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

from check_deployment import read_env, validate

ROOT = Path(__file__).resolve().parents[1]
DOCKER = os.environ.get('DOCKER_BIN') or shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
IMAGE = 'caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f'
ENV = {**os.environ, 'PATH': f'{Path(DOCKER).parent}:{os.environ.get("PATH", "")}'}


def run(args, **kwargs):
    result = subprocess.run(args, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=90, **kwargs)
    if result.returncode:
        raise RuntimeError(f'Offline deployment verification command failed (exit {result.returncode}).')
    return result.stdout


def main():
    (ROOT / '.runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='deploy-check-', dir=ROOT / '.runtime') as work:
        work = Path(work)
        password_hash = run([DOCKER, 'run', '--rm', '--network', 'none', '--entrypoint', 'caddy', IMAGE,
                             'hash-password', '--plaintext', 'synthetic-config-check-only', '--algorithm', 'bcrypt']).strip()
        password = secrets.token_urlsafe(24)
        values = {'APP_ENV_FILE': '.env.production', 'PUBLIC_HOST': 'review.company.org', 'TLS_EMAIL': 'tls@example.org',
            'DEMO_USER': 'reviewer', 'DEMO_PASSWORD_HASH': password_hash, 'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
            'CONNECTION_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            'POSTGRES_PASSWORD': password, 'DATABASE_URL': f'postgresql://regex:{password}@postgres:5432/regex',
            'OPENAI_API_KEY': 'synthetic-offline-test-only', 'OPENAI_MODEL': 'gpt-4.1-mini',
            'DJANGO_DEBUG': 'false', 'TRUST_PROXY_HEADERS': 'true',
            'DJANGO_ALLOWED_HOSTS': 'review.company.org,localhost,127.0.0.1,backend',
            'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://review.company.org',
            'CACHE_URL': 'redis://redis:6379/2', 'CELERY_BROKER_URL': 'redis://redis:6379/0',
            'CELERY_RESULT_BACKEND': 'redis://redis:6379/1'}
        path = work / 'settings.env'
        path.write_text(''.join(f"{key}='{value}'\n" for key, value in values.items()))
        path.chmod(0o600)
        assert validate(read_env(path)) == []
        relative = str(path.relative_to(ROOT))
        # The actual server uses .env.production; only this verification process
        # points Compose at the disposable synthetic settings file instead.
        ENV['APP_ENV_FILE'] = relative
        compose = [DOCKER, 'compose', '--env-file', relative, '-f', 'compose.yaml', '-f', 'compose.production.yaml']
        config = json.loads(run(compose + ['config', '--format', 'json']))
        public = {}
        for name, service in config['services'].items():
            bindings = [port for port in service.get('ports', []) if port.get('host_ip', '') not in {'127.0.0.1', '::1'}]
            if bindings:
                public[name] = [str(port['published']) for port in bindings]
        assert set(public) == {'caddy'} and set(public['caddy']) == {'80', '443'}
        assert not config['services']['frontend'].get('ports')
        assert config['services']['backend']['environment']['DJANGO_DEBUG'] == 'false'
        assert int(config['services']['worker']['mem_limit']) == 4 * 1024 ** 3
        caddy_env = work / 'caddy.env'
        caddy_env.write_text(''.join(f'{key}={values[key]}\n' for key in ['PUBLIC_HOST', 'TLS_EMAIL', 'DEMO_USER', 'DEMO_PASSWORD_HASH']))
        caddy_env.chmod(0o600)
        base = [DOCKER, 'run', '--rm', '--network', 'none', '--env-file', str(caddy_env),
            '-v', f'{ROOT / "deploy/Caddyfile"}:/etc/caddy/Caddyfile:ro', '--entrypoint', 'caddy', IMAGE]
        run(base + ['validate', '--config', '/etc/caddy/Caddyfile'])
        adapted = json.loads(run(base + ['adapt', '--config', '/etc/caddy/Caddyfile']))
        handlers = []
        def walk(node):
            if isinstance(node, dict):
                if 'handler' in node:
                    handlers.append(node)
                for value in node.values(): walk(value)
            elif isinstance(node, list):
                for value in node: walk(value)
        walk(adapted)
        assert any(node.get('handler') == 'authentication' for node in handlers)
        proxies = [node for node in handlers if node.get('handler') == 'reverse_proxy']
        assert proxies and 'Authorization' in proxies[0]['headers']['request']['delete']
        runtime_code = """
import json
from unittest.mock import patch
from django.core.management import call_command
from rest_framework.test import APIClient
call_command('migrate', verbosity=0)
client = APIClient(enforce_csrf_checks=True)
host = {'HTTP_HOST': 'review.company.org'}
assert client.get('/api/session/', **host).status_code == 301
assert client.get('/api/health/', **host).status_code == 200
secure = {**host, 'HTTP_X_FORWARDED_PROTO': 'https'}
session = client.get('/api/session/', **secure)
assert session.status_code == 200 and session.cookies['sessionid']['secure'] and session.cookies['csrftoken']['secure']
assert client.post('/api/diagnostics/', {}, format='json', **secure).status_code == 403
with patch('processing.views.dispatch', return_value=True):
    accepted = client.post('/api/diagnostics/', {}, format='json', **secure,
        HTTP_X_CSRFTOKEN=session.data['csrf_token'], HTTP_ORIGIN='https://review.company.org')
assert accepted.status_code == 202
print(json.dumps({'https_redirect': True, 'private_health_exemption': True, 'secure_session_and_csrf_cookies': True,
    'csrf_rejects_missing_token': True, 'https_mutation_returns_202': True, 'database': 'ephemeral in-memory SQLite'}))
"""
        runtime = run(compose + ['run', '--rm', '--no-deps', '-T', '-e', 'DATABASE_URL=sqlite:///:memory:',
                                 'backend', 'python', 'manage.py', 'shell', '-c', runtime_code])
        django_result = json.loads(runtime.strip().splitlines()[-1])
        version = run([DOCKER, 'run', '--rm', '--network', 'none', '--entrypoint', 'caddy', IMAGE, 'version']).strip()
        evidence = {'complete': True, 'production_env_preflight': True, 'compose_merged_config': True,
            'public_services': public, 'caddy_validation': True, 'gateway_authentication_required': True,
            'authorization_removed_before_application': True, 'caddy_version': version, 'django_production_mode': django_result,
            'scope': 'offline syntax/security checks and in-memory app requests; no DNS/ACME/public runtime verification'}
        (ROOT / 'docs/day5-deployment-checks.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
