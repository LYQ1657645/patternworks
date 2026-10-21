#!/usr/bin/env python3
"""Check publishable Git files without printing credentials or matched values."""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private key': rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----',
    'OpenAI key': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
    'GitHub token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})',
    'AWS access key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'Slack token': rb'\bxox[baprs]-[A-Za-z0-9-]{24,}',
}
PRIVATE_PARTS = {'.runtime', '.aws', '.codex', '.agents', '.venv', '.tools',
                 '.pnpm-store', '.taste-skill', 'node_modules', '__pycache__', 'dist'}
PRIVATE_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.sqlite3', '.db', '.dump'}
SECRET_FIELDS = {'OPENAI_API_KEY', 'DJANGO_SECRET_KEY', 'CONNECTION_ENCRYPTION_KEY',
                 'POSTGRES_PASSWORD', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                 'AWS_SESSION_TOKEN', 'DEMO_PASSWORD_HASH', 'GITHUB_TOKEN', 'GH_TOKEN'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def configured_values():
    """Compare local secrets only in memory; never include them in a report."""
    values = set()
    for name in ('.env', '.env.local', '.env.production'):
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            continue
        for line in path.read_text().splitlines():
            key, separator, value = line.partition('=')
            value = value.strip().strip('\"\'')
            if separator and key.strip() in SECRET_FIELDS and len(value) >= 8:
                values.add(value.encode())
    reviewer = ROOT / '.runtime/deployment/reviewer-access.json'
    if reviewer.is_file() and not reviewer.is_symlink():
        for key, value in json.loads(reviewer.read_text()).items():
            if ('password' in key.lower() or 'secret' in key.lower()) and isinstance(value, str) and len(value) >= 8:
                values.add(value.encode())
    return values


def scan(staged=False):
    args = ['ls-files', '--cached', '-z']
    if not staged:
        args.extend(['--others', '--exclude-standard'])
    names = sorted(set(p.decode() for p in git(*args).split(b'\0') if p))
    secrets = configured_values()
    findings, total = [], 0
    for name in names:
        path = Path(name)
        local = ROOT / path
        private_env = (path.name == '.env' or path.name.startswith('.env.')) and path.name != '.env.example'
        if (PRIVATE_PARTS.intersection(path.parts) or path.suffix in PRIVATE_SUFFIXES
                or private_env or path.name in {'credentials', 'reviewer-access.json'}):
            findings.append({'file': name, 'rule': 'private file path'})
            continue
        if local.is_symlink():
            findings.append({'file': name, 'rule': 'symlink requires explicit review'})
            continue
        if staged:
            data = git('show', ':' + name)
        elif local.is_file():
            data = local.read_bytes()
        else:
            continue
        total += len(data)
        for label, pattern in PATTERNS.items():
            for match in re.finditer(pattern, data):
                findings.append({'file': name, 'line': data[:match.start()].count(b'\n') + 1, 'rule': label})
        if any(value in data for value in secrets):
            findings.append({'file': name, 'rule': 'configured local secret'})
    return {'files': len(names), 'bytes': total, 'mode': 'staged' if staged else 'working tree',
            'configured_values_compared': len(secrets), 'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Read exactly the Git index blobs.')
    result = scan(parser.parse_args().staged)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['findings']))


if __name__ == '__main__':
    main()
