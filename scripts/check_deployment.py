#!/usr/bin/env python3
"""Read-only production configuration preflight; never prints setting values."""
import argparse
import base64
from pathlib import Path
import re
import shlex
from urllib.parse import unquote, urlparse


def read_env(path):
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator:
            raise ValueError(f'Invalid env assignment on line {number}.')
        parsed = shlex.split(value, comments=True)
        if len(parsed) > 1:
            raise ValueError(f'Quote the setting on line {number}.')
        values[key.strip()] = parsed[0] if parsed else ''
    return values


def validate(values):
    errors = []
    required = ['APP_ENV_FILE', 'PUBLIC_HOST', 'TLS_EMAIL', 'DEMO_USER', 'DEMO_PASSWORD_HASH',
        'DJANGO_SECRET_KEY', 'CONNECTION_ENCRYPTION_KEY', 'POSTGRES_PASSWORD', 'DATABASE_URL', 'OPENAI_API_KEY']
    errors += [f'Missing {name}.' for name in required if not values.get(name)]
    host = values.get('PUBLIC_HOST', '')
    if (not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', host)
            or '.' not in host or '..' in host or host in {'example.com', 'localhost'}
            or host.endswith(('.example', '.invalid', '.test')) or re.fullmatch(r'[0-9.]+', host)):
        errors.append('PUBLIC_HOST must be a real DNS hostname; IP-only HTTPS is outside this template.')
    if values.get('APP_ENV_FILE') != '.env.production':
        errors.append('APP_ENV_FILE must select .env.production.')
    if values.get('DJANGO_DEBUG', '').lower() != 'false':
        errors.append('DJANGO_DEBUG must be false.')
    if values.get('TRUST_PROXY_HEADERS', '').lower() != 'true':
        errors.append('TRUST_PROXY_HEADERS must be true behind the private gateway.')
    if host not in values.get('DJANGO_ALLOWED_HOSTS', '').split(',') or '*' in values.get('DJANGO_ALLOWED_HOSTS', ''):
        errors.append('DJANGO_ALLOWED_HOSTS must include PUBLIC_HOST and exclude wildcards.')
    if f'https://{host}' not in values.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(','):
        errors.append('CSRF trusted origins must include the exact HTTPS public origin.')
    if any(origin and not origin.startswith('https://') for origin in values.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')):
        errors.append('Production CSRF origins must use HTTPS.')
    if len(values.get('DJANGO_SECRET_KEY', '')) < 50 or values.get('DJANGO_SECRET_KEY', '').startswith('django-insecure-'):
        errors.append('Generate a fresh strong DJANGO_SECRET_KEY.')
    if len(values.get('POSTGRES_PASSWORD', '')) < 24:
        errors.append('Generate a strong POSTGRES_PASSWORD.')
    try:
        if len(base64.urlsafe_b64decode(values.get('CONNECTION_ENCRYPTION_KEY', '').encode())) != 32:
            raise ValueError()
    except (ValueError, TypeError):
        errors.append('CONNECTION_ENCRYPTION_KEY must be a valid 32-byte Fernet key.')
    db = urlparse(values.get('DATABASE_URL', ''))
    if (db.scheme not in {'postgres', 'postgresql'} or db.hostname != 'postgres'
            or unquote(db.password or '') != values.get('POSTGRES_PASSWORD')):
        errors.append('DATABASE_URL must use the private PostgreSQL service and matching password.')
    if not re.fullmatch(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}', values.get('DEMO_PASSWORD_HASH', '')):
        errors.append('DEMO_PASSWORD_HASH must be a bcrypt hash, never plaintext.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', values.get('DEMO_USER', '')):
        errors.append('DEMO_USER must be a simple reviewer username.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', values.get('TLS_EMAIL', '')):
        errors.append('Provide a TLS contact email.')
    if any('${' in value or 'CHANGE_ME' in value for value in values.values()):
        errors.append('Resolve placeholder/interpolated values before deployment.')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, default=Path('.env.production'))
    args = parser.parse_args()
    if args.env.is_symlink() or not args.env.is_file():
        raise SystemExit('Create a regular server-only .env.production first.')
    if args.env.stat().st_mode & 0o077:
        raise SystemExit('Restrict the env file to its owner (chmod 600).')
    errors = validate(read_env(args.env))
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Production settings passed offline preflight. DNS, certificates and remote runtime still need live verification.')


if __name__ == '__main__':
    main()
