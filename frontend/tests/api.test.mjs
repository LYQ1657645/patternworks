import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const javascript = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
} }).outputText;
let moduleNumber = 0;
const failed = { id: '00000000-0000-0000-0000-000000000001', status: 'FAILED',
  kind: 'DIAGNOSTIC', error_code: 'QUEUE_UNAVAILABLE', error_message: 'Queue unavailable', retry_allowed: true };
async function client(response) {
  globalThis.fetch = async (url) => url === '/api/session/'
    ? new Response(JSON.stringify({ csrf_token: 'test-token' }), { status: 200 })
    : typeof response === 'function' ? response() : response;
  return import('data:text/javascript;base64,' + Buffer.from(javascript).toString('base64') + '#' + moduleNumber++);
}
test('503 preserves failed job and immediately exposes it to task activity', async () => {
  const { api, ApiError, submissionError } = await client(new Response(JSON.stringify(failed), { status: 503 }));
  let displayedJob;
  await assert.rejects(api('/diagnostics/', {}), error => {
    assert.ok(error instanceof ApiError); assert.equal(error.status, 503);
    assert.equal(error.code, 'QUEUE_UNAVAILABLE'); assert.deepEqual(error.job, failed);
    assert.equal(submissionError(error, job => { displayedJob = job; }), 'Queue unavailable');
    return true;
  });
  assert.equal(displayedJob.id, failed.id); assert.equal(displayedJob.retry_allowed, true);
});
test('validation errors show the field and do not replace the current job', async () => {
  const { api, ApiError, submissionError } = await client(new Response(JSON.stringify({ bucket: ['Invalid name'] }), { status: 400 }));
  await assert.rejects(api('/connections/', {}), error => {
    assert.ok(error instanceof ApiError); assert.equal(error.job, undefined);
    assert.equal(submissionError(error, () => assert.fail('must not change current job')), 'bucket: Invalid name');
    return true;
  });
});
test('accepted jobs remain normal return values', async () => {
  const accepted = { ...failed, status: 'QUEUED', error_code: '', error_message: '', retry_allowed: false };
  const { api } = await client(new Response(JSON.stringify(accepted), { status: 202 }));
  assert.deepEqual(await api('/diagnostics/', {}), accepted);
});
test('a network failure remains an error with no invented job', async () => {
  const { api, submissionError } = await client(() => { throw new TypeError('Network unavailable'); });
  await assert.rejects(api('/diagnostics/', {}), error => {
    assert.equal(submissionError(error, () => assert.fail('no persisted job was received')), 'Network unavailable');
    return true;
  });
});
test('non-JSON responses display a useful error', async () => {
  const { api } = await client(new Response('<html>Bad gateway</html>', { status: 502 }));
  await assert.rejects(api('/diagnostics/', {}), /unreadable response/);
});
