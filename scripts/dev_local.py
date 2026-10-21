#!/usr/bin/env python3
"""Local development only: real Redis/Celery, explicit SQLite; not Compose acceptance."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / '.runtime'


def local_runtime_environment():
    environment = dict(os.environ)
    # Python UDFs must use the same environment as the Celery driver, including RE2.
    environment.setdefault('PYSPARK_PYTHON', sys.executable)
    java_home = environment.get('JAVA_HOME')
    if not java_home or not (Path(java_home) / 'bin/java').is_file():
        java_home = next((str(path) for path in sorted(
            (ROOT / '.tools/loom-java').glob('*/Contents/Home'), reverse=True)
            if (path / 'bin/java').is_file()), None)
        if java_home:
            environment['JAVA_HOME'] = java_home
    if java_home:
        java_bin = str(Path(java_home) / 'bin')
        path_entries = environment.get('PATH', '').split(os.pathsep)
        environment['PATH'] = os.pathsep.join([java_bin] + [entry for entry in path_entries if entry != java_bin])
    return environment


def main():
    RUNTIME.mkdir(exist_ok=True)
    node = shutil.which('node') or str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
    redis = shutil.which('redis-server') or str(ROOT / '.tools/redis-7.4.2/src/redis-server')
    for path in [node, redis]:
        if not Path(path).is_file():
            raise SystemExit('Local Node/Redis is unavailable. Use the Docker Compose instructions instead.')
    for port in [6387, 8000, 5173]:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Port {port} is already in use; stop its existing service first.')
    environment = local_runtime_environment()
    environment.update({
        'DATABASE_URL': 'sqlite:///' + str(RUNTIME / 'day1.sqlite3'),
        'CELERY_BROKER_URL': 'redis://127.0.0.1:6387/0',
        'CELERY_RESULT_BACKEND': 'redis://127.0.0.1:6387/1',
        'CACHE_URL': 'redis://127.0.0.1:6387/2',
        'DJANGO_DEBUG': 'true',
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1',
    })
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=ROOT / 'backend', env=environment, check=True)
    services = []
    handles = []

    def start(name, command, cwd):
        log = (RUNTIME / f'{name}.log').open('a')
        handles.append(log)
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT)
        services.append(process)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        start('redis', [redis, '--bind', '127.0.0.1', '--port', '6387', '--save', '', '--appendonly', 'no'], ROOT)
        start('worker', [sys.executable, '-m', 'celery', '-A', 'config', 'worker', '--pool=solo', '--loglevel=INFO', '--events'], ROOT / 'backend')
        start('backend', [sys.executable, 'manage.py', 'runserver', '127.0.0.1:8000', '--noreload'], ROOT / 'backend')
        start('frontend', [node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1'], ROOT / 'frontend')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in services):
                raise SystemExit('A service exited. Check .runtime/*.log (do not share credentials).')
            try:
                with urllib.request.urlopen('http://127.0.0.1:5173/api/health/', timeout=1) as response:
                    if response.status == 200:
                        print('Local preview ready: http://127.0.0.1:5173', flush=True)
                        print('Real Redis + Celery; local SQLite. Docker/PostgreSQL is not verified by this preview.', flush=True)
                        break
            except Exception:
                time.sleep(0.25)
        else:
            raise SystemExit('Services did not become ready. Check .runtime logs.')
        while all(process.poll() is None for process in services):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for process in services:
            if process.poll() is None:
                process.terminate()
        for process in services:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    main()
