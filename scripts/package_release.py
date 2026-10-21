#!/usr/bin/env python3
"""Package allowlisted project source and evidence, excluding runtime data/secrets."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from check_deployment import read_env

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DIRS = {'backend', 'frontend', 'scripts', 'docs', 'deploy', 'samples', '.github'}
ALLOWED_ROOT = {'.gitignore', '.dockerignore', '.env.example', 'README.md', 'compose.yaml', 'compose.production.yaml', 'pytest.ini'}
SECRET_NAMES = ['OPENAI_API_KEY', 'DJANGO_SECRET_KEY', 'POSTGRES_PASSWORD', 'CONNECTION_ENCRYPTION_KEY']


def main():
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).split(b'\0')
    protected = []
    for env_name in ['.env.local', '.env.production']:
        env = ROOT / env_name
        if env.is_file() and not env.is_symlink():
            values = read_env(env)
            protected.extend(values[name].encode() for name in SECRET_NAMES if values.get(name))
    manifest = {}
    for item in paths:
        if not item:
            continue
        relative = Path(item.decode())
        if relative.parts[0] not in ALLOWED_DIRS and str(relative) not in ALLOWED_ROOT:
            continue
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise SystemExit('Release source contains an unsupported path.')
        data = path.read_bytes()
        if any(secret in data for secret in protected):
            raise SystemExit(f'Refusing to package a configured secret found in {relative}.')
        manifest[str(relative)] = hashlib.sha256(data).hexdigest()
    output = ROOT / '.runtime/patternworks-day5-source.tar.gz'
    output.parent.mkdir(exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for relative in sorted(manifest):
            archive.add(ROOT / relative, arcname=f'patternworks/{relative}', recursive=False)
        data = (json.dumps({'files': manifest, 'file_count': len(manifest)}, indent=2) + '\n').encode()
        info = tarfile.TarInfo('patternworks/RELEASE_MANIFEST.json')
        info.size = len(data)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(data))
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'archive': str(output), 'sha256': digest, 'source_files': len(manifest), 'configured_secrets_checked': len(protected)}))


if __name__ == '__main__':
    main()
