#!/usr/bin/env python3
"""Generate local app secrets without printing or replacing existing secrets."""
import base64
import argparse
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--production', action='store_true', help='Prepare a separate .env.production; never copy a local OpenAI key.')
args = parser.parse_args()
target = ROOT / ('.env.production' if args.production else '.env.local')
if target.is_symlink():
    raise SystemExit('Refusing a symlink env file.')
text = target.read_text() if target.exists() else ((ROOT / 'deploy/production.env.example').read_text() if args.production else '')
existing = {}
for line in text.splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, value = line.split('=', 1)
        existing[key.strip()] = value.strip()
password = existing.get('POSTGRES_PASSWORD') or secrets.token_urlsafe(24)
defaults = {
    'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
    'CONNECTION_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'POSTGRES_PASSWORD': password,
    'DATABASE_URL': f'postgresql://regex:{password}@postgres:5432/regex',
    'DJANGO_DEBUG': 'false' if args.production else 'true',
    'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend',
    'DJANGO_CSRF_TRUSTED_ORIGINS': '' if args.production else 'http://localhost:5173,http://127.0.0.1:5173',
    'CELERY_BROKER_URL': 'redis://redis:6379/0',
    'CELERY_RESULT_BACKEND': 'redis://redis:6379/1',
    'CACHE_URL': 'redis://redis:6379/2',
    'OPENAI_MODEL': 'gpt-4.1-mini',
    'CONNECTION_TTL_SECONDS': '3600',
}
for key, value in defaults.items():
    if not existing.get(key) or (key == 'DATABASE_URL' and 'CHANGE_ME' in existing[key]):
        # Replace an empty template entry; never duplicate it or overwrite a populated secret.
        lines = text.splitlines()
        lines = [line for line in lines if not (line.split('=', 1)[0].strip() == key and '=' in line)]
        text = '\n'.join(lines).rstrip() + f'\n{key}={value}\n'
target.write_text(text.lstrip('\n'))
os.chmod(target, 0o600)
print(f'Settings ready: {target.name} (existing values preserved; secrets hidden).')
if args.production:
    print('Complete public host, HTTPS origins, TLS email, demo password hash and OpenAI key privately before deployment checks.')
