import base64
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('deployment_preflight', ROOT / 'scripts/check_deployment.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def config():
    password = 'test-only-database-password-123456'
    return {'APP_ENV_FILE': '.env.production', 'PUBLIC_HOST': 'review.company.org', 'TLS_EMAIL': 'review@example.org',
        'DEMO_USER': 'reviewer', 'DEMO_PASSWORD_HASH': '$2a$12$' + 'a' * 53,
        'DJANGO_SECRET_KEY': 'test-only-production-preflight-' + 'x' * 40,
        'CONNECTION_ENCRYPTION_KEY': base64.urlsafe_b64encode(b'x' * 32).decode(),
        'POSTGRES_PASSWORD': password, 'DATABASE_URL': f'postgresql://regex:{password}@postgres:5432/regex',
        'OPENAI_API_KEY': 'test-only-not-an-api-key', 'DJANGO_DEBUG': 'false', 'TRUST_PROXY_HEADERS': 'true',
        'DJANGO_ALLOWED_HOSTS': 'review.company.org,localhost,127.0.0.1,backend',
        'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://review.company.org'}


def test_production_preflight_accepts_explicit_private_proxy_configuration():
    assert preflight.validate(config()) == []


@pytest.mark.parametrize('key,value', [('DJANGO_DEBUG', 'true'), ('TRUST_PROXY_HEADERS', 'false'),
    ('DJANGO_ALLOWED_HOSTS', '*'), ('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://review.company.org'),
    ('PUBLIC_HOST', '127.0.0.1'), ('PUBLIC_HOST', 'example.com'), ('APP_ENV_FILE', '.env.local'),
    ('DEMO_PASSWORD_HASH', 'plaintext-password'), ('POSTGRES_PASSWORD', 'short'),
    ('DJANGO_SECRET_KEY', 'weak'), ('CONNECTION_ENCRYPTION_KEY', 'bad'), ('OPENAI_API_KEY', '')])
def test_production_preflight_rejects_unsafe_or_missing_settings_without_echoing_values(key, value):
    values = {**config(), key: value}
    errors = preflight.validate(values)
    assert errors
    for name in ['OPENAI_API_KEY', 'DJANGO_SECRET_KEY', 'DEMO_PASSWORD_HASH', 'POSTGRES_PASSWORD']:
        if len(values.get(name, '')) > 15:
            assert values[name] not in '\n'.join(errors)


def test_env_reader_preserves_single_quoted_bcrypt_dollar_signs(tmp_path):
    path = tmp_path / 'test.env'
    path.write_text("DEMO_PASSWORD_HASH='$2a$12$example.hash'\nEMPTY=\n# ignored\n")
    assert preflight.read_env(path) == {'DEMO_PASSWORD_HASH': '$2a$12$example.hash', 'EMPTY': ''}


def test_production_initializer_uses_fresh_secrets_and_never_copies_local_api_key(tmp_path):
    (tmp_path / 'scripts').mkdir(); (tmp_path / 'deploy').mkdir()
    shutil.copyfile(ROOT / 'scripts/init_env.py', tmp_path / 'scripts/init_env.py')
    shutil.copyfile(ROOT / 'deploy/production.env.example', tmp_path / 'deploy/production.env.example')
    local = tmp_path / '.env.local'
    local.write_text('OPENAI_API_KEY=local-test-sentinel\n')
    original = local.read_bytes()
    result = subprocess.run([sys.executable, str(tmp_path / 'scripts/init_env.py'), '--production'], capture_output=True, text=True)
    assert result.returncode == 0 and 'local-test-sentinel' not in result.stdout + result.stderr
    target = tmp_path / '.env.production'
    values = preflight.read_env(target)
    assert local.read_bytes() == original and values['OPENAI_API_KEY'] == ''
    assert len(values['DJANGO_SECRET_KEY']) >= 50 and values['DJANGO_DEBUG'] == 'false'
    assert target.stat().st_mode & 0o077 == 0
    before = target.read_bytes()
    subprocess.run([sys.executable, str(tmp_path / 'scripts/init_env.py'), '--production'], check=True, capture_output=True)
    assert target.read_bytes() == before
