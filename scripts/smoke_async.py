#!/usr/bin/env python3
"""Exercise the real HTTP → broker → worker → DB/cache path, no eager tasks."""
import argparse
import http.cookiejar
import json
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:5173')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, body=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-CSRFToken'] = token
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with opener.open(req, timeout=10) as response:
            return response.status, json.load(response)

    _, session = call('/api/session/')
    started = time.monotonic()
    code, job = call('/api/diagnostics/', {}, session['csrf_token'])
    elapsed = time.monotonic() - started
    assert code == 202, 'Submission must return HTTP 202'
    assert job['status'] == 'QUEUED', 'Submission should return a queued job'
    print(f'HTTP {code}, returned job ID in {elapsed:.3f}s; initial status={job["status"]}')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        _, result = call(f'/api/jobs/{job["id"]}/')
        if result['status'] in {'SUCCESS', 'FAILED', 'CANCELLED'}:
            print('Final status:', result['status'])
            if result['status'] != 'SUCCESS':
                raise SystemExit(result.get('error_message', 'Diagnostic failed'))
            assert result['result']['cache'] == 'ok'
            print('Verified real asynchronous worker and shared cache.')
            return
        time.sleep(0.25)
    raise SystemExit('Timed out: check worker availability.')


if __name__ == '__main__':
    main()
