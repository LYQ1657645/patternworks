// Controlled hooks/API probes against actual TSX handlers and effects.
// These do not substitute for real React scheduling or browser acceptance.
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
const jsx = (type, props) => ({ type, props: props || {} });
function harness(name, preset, modules) {
  let index = 0, refIndex = 0, states = [], refs = [], effects = [];
  const react = { lazy: () => () => null, Suspense: () => null, useRef(value) { const at = refIndex++; return refs[at] ||= { current: value }; }, useEffect: (fn, deps) => effects.push({ fn, deps }),
    useState(initial) { const at = index++; if (!(at in states)) states[at] = at in preset ? preset[at] : typeof initial === 'function' ? initial() : initial;
      return [states[at], value => { states[at] = typeof value === 'function' ? value(states[at]) : value; }]; } };
  const exports = {};
  const source = fs.readFileSync(new URL(`../src/${name}.tsx`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, Error, Date: modules.__date || Date, URLSearchParams, AbortController, setTimeout: modules.__timers?.setTimeout || setTimeout, clearTimeout: modules.__timers?.clearTimeout || clearTimeout, window: { scrollTo() {}, addEventListener() {}, removeEventListener() {}, location: { hash: "#/sources" } },
    require: id => id === 'react' ? react : id === 'react/jsx-runtime' ? { jsx, jsxs: jsx }
      : modules[id] || { __esModule: true, default: () => null } });
  return { states, render(props) { index = 0; refIndex = 0; effects = []; return exports.default(props); }, get effects() { return effects; } };
}
function nodes(root, out = []) {
  if (!root || typeof root !== 'object') return out;
  if (Array.isArray(root)) { root.forEach(x => nodes(x, out)); return out; }
  out.push(root); nodes(root.props?.children, out); return out;
}
function text(x) { return x == null || typeof x === 'boolean' ? '' : typeof x !== 'object' ? String(x)
  : Array.isArray(x) ? x.map(text).join('') : text(x.props?.children); }
const settle = () => new Promise(resolve => setImmediate(resolve));
const file = { key: 'contacts.csv', format: 'csv', size: 10, last_modified: '2026-10-18' };
const datasetId = '00000000-0000-4000-8000-000000000002';

function app(job = null, connection = 'expired-connection', apiCall = async () => { throw new ApiError('Connection expired. Please reconnect.', 410); }, options = {}) {
  const h = harness('App', { 1: false, 7: job, 8: connection, 9: [file], 11: file.key, 13: datasetId, 18: true }, {
    './api': { ApiError, api: apiCall, submissionError: e => e.message },
    './navigation': { pageFromHash: () => 'sources', pages: Object.fromEntries(['sources', 'history', 'datasets', 'transform'].map(key => [key, {title: key, icon: 'source', number: '01'}])) }, './listState': { save: options.save || (() => {}), savedId: () => null, readSaved: options.readSaved || (() => null) }, './historyLabels': { jobLabels: {} }, __timers: options.timers, __date: options.date });
  return h;
}

test('import 410 clears connection/file selection while retaining the selected result and error', async () => {
  const h = app(); let tree = h.render();
  nodes(tree).find(n => n.type === 'button' && text(n).includes('Import file')).props.onClick(); await settle();
  tree = h.render(); assert.equal(h.states[8], null); assert.equal(h.states[11], ''); assert.equal(h.states[13], datasetId);
  assert.equal(h.states[19], 'Connection expired. Please reconnect.');
  assert(!nodes(tree).some(n => n.props.className === 'connected-label'));
  assert(!nodes(tree).some(n => n.type === 'button' && text(n).includes('Import file')));
});

test('async import credential expiry clears only its current connection', () => {
  const job = { id: 'job', kind: 'IMPORT_DATASET', status: 'FAILED', error_code: 'CONNECTION_EXPIRED', connection_id: 'expired-connection', error_message: 'Reconnect.' };
  for (const current of ['expired-connection', 'new-connection']) {
    const h = app(job, current); h.render();
    h.effects.find(e => e.deps?.length === 1 && e.deps[0] === job).fn();
    assert.equal(h.states[8], current === 'expired-connection' ? null : 'new-connection');
    assert.equal(h.states[13], datasetId);
  }
});

function history() {
  const detail = { id: 'job', kind: 'EXPORT_CSV', status: 'SUCCESS', dataset_id: datasetId, dataset_available: true, progress: 100, stage: 'Completed', created_at: '2026-10-18', attempt_count: 1 };
  let server = detail, refreshes = 0;
  const list = { loading: false, items: [], state: { filters: { status: '', kind: '' }, page: 0 }, refresh() { refreshes++; } };
  const h = harness('TaskHistory', { 0: 'job', 1: detail }, { './api': { ApiError, api: async () => server },
    './historyLabels': { jobLabels: { EXPORT_CSV: 'CSV export' }, timeLabel: x => x, jobDataset: j => j.dataset_available === false ? null : j.dataset_id },
    './listState': { save() {}, savedId: () => 'job' }, './useCursorList': { useCursorList: () => list } });
  return { h, props: { job: null, datasetRevision: 0, busy: false }, trash() { server = { ...detail, dataset_available: false }; }, restore() { server = detail; }, get refreshes() { return refreshes; } };
}
const download = tree => nodes(tree).some(n => n.type === 'a' && text(n) === 'Download CSV');

test('manual history refresh reloads terminal detail and removes a trashed dataset download', async () => {
  const f = history(); let tree = f.h.render(f.props); assert(download(tree)); f.trash();
  nodes(tree).find(n => n.type === 'button' && text(n) === 'Refresh').props.onClick();
  f.h.render(f.props); await f.h.effects[1].fn(); await settle();
  tree = f.h.render(f.props); assert(!download(tree)); assert.equal(f.refreshes, 1);
});

test('dataset lifecycle revision refreshes terminal detail on trash and restore', async () => {
  const f = history(); f.h.render(f.props); const before = f.h.effects[1].deps;
  f.trash(); f.props.datasetRevision++; f.h.render(f.props); assert.notDeepEqual(f.h.effects[1].deps, before);
  await f.h.effects[1].fn(); await settle(); assert(!download(f.h.render(f.props)));
  f.restore(); f.props.datasetRevision++; f.h.render(f.props); await f.h.effects[1].fn(); await settle();
  assert(download(f.h.render(f.props)));
});

test('navigation preserves dataset state while Activity opens independently', () => {
  const h = app(); h.render();
  for (const view of ['sources', 'datasets', 'transform']) {
    h.states[22] = view;
    const tree = h.render();
    const containers = nodes(tree).filter(n => n.type === 'div' && typeof n.props.hidden === 'boolean');
    assert.equal(containers.length, 3);
    assert.equal(containers.filter(n => !n.props.hidden).length, 1);
    assert.equal(h.states[13], datasetId);
    const links = nodes(tree).filter(n => n.type === 'a' && n.props['aria-current'] === 'page');
    assert.equal(links.length, 1);
    assert.equal(links[0].props.href, `#/${view}`);
    assert(!nodes(tree).some(n => n.type === 'a' && n.props.href === '#/history' && n.props['aria-current']));
    nodes(tree).find(n => n.props.className === 'nav-activity').props.onClick();
    const opened = h.render();
    assert.equal(nodes(opened).find(n => n.props.id === 'workspace-activity').props.hidden, false);
    assert.equal(h.states[13], datasetId);
    nodes(opened).find(n => n.type === 'button' && text(n) === 'Close').props.onClick();
  }
});

test('worksheet picker defaults to first tab, preserves Unicode, and ignores a departed file response', async () => {
  let resolve;
  const choices = [];
  const h = harness('WorksheetPicker', {}, { './api': { ApiError, api: () => new Promise(r => { resolve = r; }) } });
  const props = { connection: 'connection', sourceKey: 'book.xlsx', value: '', disabled: false, onChange: x => choices.push(x), onExpired() {}, onJob() {} };
  h.render(props);
  const cleanup = h.effects[0].fn();
  resolve({ id: 'sheet-job', status: 'SUCCESS', result: { source_key: 'book.xlsx', sheet_names: ['Contacts', '客户 数据'] } }); await settle();
  assert.deepEqual(choices, ['', 'Contacts']);
  assert.deepEqual(Array.from(h.states[0]), ['Contacts', '客户 数据']);
  h.render({ ...props, sourceKey: 'other.xlsx' });
  const departed = h.effects[0].fn(); departed();
  resolve({ id: 'old', status: 'SUCCESS', result: { source_key: 'book.xlsx', sheet_names: ['Wrong file'] } }); await settle();
  assert(!choices.includes('Wrong file')); cleanup();
});

test('worksheet read failure offers reload and does not enable a worksheet', async () => {
  const choices = [];
  const h = harness('WorksheetPicker', {}, { './api': { ApiError, submissionError: e => e.message, api: async () => { throw new ApiError('Cannot read workbook.', 400); } } });
  const props = { connection: 'connection', sourceKey: 'book.xlsx', value: '', disabled: false, onChange: x => choices.push(x), onExpired() {}, onJob() {} };
  h.render(props); h.effects[0].fn(); await settle();
  const tree = h.render(props);
  assert.equal(h.states[2], 'Cannot read workbook.');
  assert.deepEqual(choices, ['']);
  const retry = nodes(tree).find(n => n.type === 'button' && text(n) === 'Reload worksheets');
  retry.props.onClick(); assert.equal(h.states[3], 1);
});

test('new transformation forms require explicit columns instead of defaulting to ID', () => {
  const dataset = { id: datasetId, columns: [{ key: 'c0', name: 'ID' }, { key: 'c1', name: 'JoinDate' }] };
  const h = harness('TransformPanel', {}, {});
  let tree = h.render({ dataset, busy: false, job: null });
  assert.equal(h.states[1], '');
  assert(nodes(tree).some(n => n.type === 'option' && text(n) === 'Choose a column to transform'));
  h.states[1] = 'c1'; h.states[6] = true;
  tree = h.render({ dataset, busy: false, job: null });
  nodes(tree).find(n => n.props['aria-label'] === 'Transformation').props.onChange({ target: { value: 'CATEGORY' } });
  assert.equal(h.states[1], '');
  const rule = harness('RulePanel', {}, { './ruleSelection': { sameColumns: () => true, toggleColumn() {} } });
  rule.render({ dataset, busy: false, job: null });
  assert.equal(rule.states[0].length, 0);
});

 test('classification requires user labels and a matching fallback before preview', () => {
  const h = harness('TransformPanel', { 0: 'CATEGORY', 1: 'c1', 6: true }, {});
  const props = { dataset: { id: datasetId, columns: [{ key: 'c1', name: 'Country' }] }, busy: false, job: null };
  const submit = tree => nodes(tree).find(n => n.type === 'button' && text(n) === 'Preview');
  assert.equal(submit(h.render(props)).props.disabled, true);
  h.states[3] = 'United States\nAustralia\nOther'; h.states[4] = 'Other';
  assert.equal(submit(h.render(props)).props.disabled, false);
  h.states[3] = 'Other\nOther';
  assert.equal(submit(h.render(props)).props.disabled, true);
});


test('worksheet polling reconnects to the same job and only enables tabs after SUCCESS', async () => {
  const timers = []; const calls = []; const choices = []; const jobs = [];
  let polls = 0;
  const queued = { id: 'tabs-job', kind: 'LIST_WORKSHEETS', status: 'QUEUED', stage: 'Waiting', progress: 0, result: {} };
  const h = harness('WorksheetPicker', {}, {
    __timers: { setTimeout: fn => { timers.push(fn); return timers.length; }, clearTimeout() {} },
    './api': { ApiError, submissionError: e => e.message, api: async (url, body) => {
      calls.push([url, body]);
      if (body) return queued;
      if (++polls === 1) throw new Error('Network interrupted');
      return { ...queued, status: 'SUCCESS', result: { source_key: 'book.xlsx', sheet_names: ['First', 'Second'] } };
    } }
  });
  const props = { connection: 'conn', sourceKey: 'book.xlsx', value: '', disabled: false, onChange: x => choices.push(x), onExpired() {}, onJob: x => jobs.push(x) };
  h.render(props); h.effects[0].fn(); await settle();
  assert.equal(h.states[1], true); assert.deepEqual(choices, ['']);
  await timers.shift()(); await settle();
  assert(h.states[5].includes('same task')); assert.equal(h.states[1], true);
  await timers.shift()(); await settle();
  assert.equal(h.states[1], false); assert.deepEqual(choices, ['', 'First']);
  assert.equal(calls.filter(([,body]) => body).length, 1);
  assert.equal(calls[1][0], calls[2][0]); assert.equal(jobs[0].id, 'tabs-job');
});

test('cancelled worksheet task never selects a sheet', async () => {
  const choices = [];
  const h = harness('WorksheetPicker', {}, { './api': { api: async () => ({ id: 'cancelled', status: 'CANCELLED', result: {} }) } });
  const props = { connection: 'conn', sourceKey: 'book.xlsx', value: '', onChange: x => choices.push(x), onJob() {}, onExpired() {} };
  h.render(props); h.effects[0].fn(); await settle();
  assert.equal(h.states[1], false); assert.equal(h.states[2], 'Worksheet reading was cancelled.');
  assert.deepEqual(choices, ['']);
});


test('source screen shows only the connection step before connecting', () => {
  const h = app(null, null); const tree = h.render();
  assert(nodes(tree).some(n => n.type === 'input' && n.props.id === 'bucket'));
  assert(!nodes(tree).some(n => n.type === 'h2' && text(n) === 'Source files'));
  assert(!text(tree).includes('System status'));
});

test('connected source screen hides credentials and places import progress next to action', () => {
  const h = app({ id: 'job', kind: 'IMPORT_DATASET', status: 'SUCCESS', connection_id: 'expired-connection', progress: 100 });
  h.states[24] = { key: file.key, sheet: '' };
  const tree = h.render();
  assert(!nodes(tree).some(n => n.type === 'input' && n.props.id === 'access'));
  assert(nodes(tree).some(n => n.type === 'button' && text(n) === 'Disconnect S3'));
  const command = nodes(tree).find(n => n.props.className === 'import-command');
  assert(text(command).includes('Import file'));
  assert(text(command).includes('Import complete'));
  assert(!nodes(tree).some(n => n.props.className?.startsWith('global-task')));
});

test('switching source files hides another file import result but keeps its task', () => {
  const job = { id: 'import-one', kind: 'IMPORT_DATASET', status: 'SUCCESS', connection_id: 'expired-connection', progress: 100 };
  const h = app(job);
  h.states[24] = { key: file.key, sheet: '' };
  assert(text(h.render()).includes('Import complete'));
  h.states[11] = 'other.csv';
  assert(!text(h.render()).includes('Import complete'));
  assert.equal(h.states[7].id, 'import-one');
  h.states[11] = file.key;
  h.states[12] = 'Another sheet';
  assert(!text(h.render()).includes('Import complete'));
});

test('a completed import requests its data sheet, not just a library selection', () => {
  const Dataset = () => null;
  const job = { id: 'fresh-import', kind: 'IMPORT_DATASET', status: 'SUCCESS', dataset_id: datasetId, result: {} };
  const h = app(job);
  h.states[13] = null;
  h.render();
  h.effects.find(e => e.deps?.length === 1 && e.deps[0] === job).fn();
  assert.equal(h.states[13], datasetId);
  const request = h.states[23];
  assert.equal(request.id, datasetId);
  assert.equal(request.nonce, 1);
  const panel = harness('DatasetPanel', {}, {
    './GalaxyExplorer': { __esModule: true, default: Dataset },
    './motion': { motionScrollBehavior: () => 'auto' },
  });
  const props = { visible: true, view: 'datasets', datasetId, openRequest: request, job: null, onSelect() {} };
  assert(nodes(panel.render(props)).find(n => n.props.id === 'dataset-preview').props.hidden);
  panel.effects.find(e => e.deps?.[0] === request).fn();
  assert.equal(nodes(panel.render(props)).find(n => n.props.id === 'dataset-preview').props.hidden, false);
});

test('literal preview treats regex symbols and replacement dollars as text and preserves nulls', () => {
  const Loom = () => null;
  const dataset = { id: datasetId, source_key: 'contacts.csv', columns: [{ key: 'c0', name: 'Contact' }], row_count: 3, metadata: {} };
  const page = { rows: [
    { row_number: 1, cells: ['a.b.c'] },
    { row_number: 2, cells: [null] },
    { row_number: 3, cells: ['abc'] },
  ], next_cursor: null };
  const h = harness('DatasetPanel', { 0: dataset, 1: page, 7: 'c0', 8: '.', 9: '$1', 10: 'text' }, {
    './LoomPreview': { __esModule: true, default: Loom },
    './motionState': { isNewDatasetResult: () => false },
  });
  const tree = h.render({ view: 'transform', datasetId, job: null, onSelect() {} });
  const preview = nodes(tree).find(n => n.type === Loom);
  assert.equal(preview.props.ready, true);
  assert.deepEqual(Array.from(preview.props.rows, r => r.after), ['a$1b$1c', null, 'abc']);
  h.states[8] = '';
  const empty = h.render({ view: 'transform', datasetId, job: null, onSelect() {} });
  assert.equal(nodes(empty).find(n => n.type === Loom).props.ready, false);
  assert.equal(nodes(empty).find(n => n.type === 'button' && text(n) === 'Apply replacement').props.disabled, true);
  h.states[8] = '.';
  h.states[1] = { ...page, preview_cell_limit: 5 };
  const limited = h.render({ view: 'transform', datasetId, job: null, onSelect() {} });
  const sample = nodes(limited).find(n => n.type === Loom).props.rows[0];
  assert.equal(sample.shortened, true);
  assert.equal(sample.after, undefined);
  assert(text(limited).includes('Apply uses the complete value'));
});

test('disconnect clears source state and credentials but preserves imported dataset selection', async () => {
  const calls=[];
  const h=app(null, 'connection', async (url) => { calls.push(url); return {disconnected:true}; });
  h.states[2]='access'; h.states[3]='secret';
  const tree=h.render();
  await nodes(tree).find(n => n.type==='button' && text(n)==='Disconnect S3').props.onClick(); await settle();
  assert.deepEqual(calls, ['/connections/disconnect/']);
  assert.equal(h.states[8], null); assert.equal(h.states[9].length,0); assert.equal(h.states[11],'');
  assert.equal(h.states[2],''); assert.equal(h.states[3],''); assert.equal(h.states[13],datasetId);
  assert(nodes(h.render()).some(n => n.props.id==='bucket'));
});

test('failed disconnect keeps the connected view available for retry', async () => {
  const h=app(null, 'connection', async () => { throw new Error('Network interrupted'); });
  await nodes(h.render()).find(n => n.type==='button' && text(n)==='Disconnect S3').props.onClick(); await settle();
  assert.equal(h.states[8],'connection'); assert.equal(h.states[19],'Network interrupted');
});

const restoreConnectionEffect = h => h.effects.find(e => e.fn.toString().includes('"/connections/"'));
const validConnection = { id: 'live-connection', bucket: 'test-bucket', region: 'ap-southeast-2', expires_at: '2099-01-01T00:00:00Z' };

test('refresh waits for server confirmation then shows files without the credential form', async () => {
  let resolve; const calls = [];
  const h = app(null, null, async url => {
    calls.push(url);
    if (url === '/connections/') return new Promise(r => { resolve = r; });
    return { files: [file], next_cursor: null };
  });
  h.states[1] = true;
  assert(!nodes(h.render()).some(n => n.props.id === 'access'));
  const cleanup = restoreConnectionEffect(h).fn();
  resolve({ connections: [validConnection] }); await settle();
  const tree = h.render();
  assert.equal(h.states[8], 'live-connection');
  assert.equal(h.states[5], 'test-bucket');
  assert.equal(h.states[6], 'ap-southeast-2');
  assert(!nodes(tree).some(n => n.props.id === 'access'));
  assert(nodes(tree).some(n => n.type === 'button' && text(n) === 'Disconnect S3'));
  assert(calls.some(url => url.startsWith('/connections/live-connection/files/')));
  cleanup();
});

test('network failure during restoration retries and offers retry instead of a misleading login', async () => {
  const timers = []; let healthy = false, calls = 0;
  const h = app(null, null, async url => {
    if (url !== '/connections/') return { files: [file], next_cursor: null };
    calls++;
    if (!healthy) throw new Error('Network unavailable');
    return { connections: [validConnection] };
  }, { timers: { setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {} } });
  h.render(); const cleanup = restoreConnectionEffect(h).fn(); await settle();
  assert(!nodes(h.render()).some(n => n.props.id === 'access'));
  timers.shift()(); await settle(); timers.shift()(); await settle();
  let tree = h.render(); assert.equal(calls, 3);
  assert(!nodes(tree).some(n => n.props.id === 'access'));
  healthy = true;
  nodes(tree).find(n => n.type === 'button' && text(n) === 'Retry connection').props.onClick();
  h.render(); cleanup(); restoreConnectionEffect(h).fn(); await settle();
  assert.equal(h.states[8], 'live-connection');
  assert(!text(h.render()).includes('Could not check'));
});

test('expired receipt explains reconnection while imported data stays selected', async () => {
  const saved = [];
  const h = app(null, null, async () => ({ connections: [] }), {
    readSaved: () => '2020-01-01T00:00:00Z', save: (...args) => saved.push(args),
  });
  h.render(); restoreConnectionEffect(h).fn(); await settle();
  const tree = h.render();
  assert(text(tree).includes('Your S3 connection expired'));
  assert(nodes(tree).some(n => n.props.id === 'access'));
  assert.equal(h.states[13], datasetId);
  assert(saved.some(([key, value]) => key === 'patternworks-s3-expires' && value === ''));
});

test('expiry timer returns to connection form without deleting imported datasets', async () => {
  const timers = []; let now = Date.now();
  class ClockDate extends Date { static now() { return now; } }
  const record = { ...validConnection, expires_at: new Date(now + 60000).toISOString() };
  const h = app(null, null, async url => url === '/connections/' ? { connections: [record] } : { files: [file], next_cursor: null }, {
    date: ClockDate, timers: { setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {} },
  });
  h.render(); restoreConnectionEffect(h).fn(); await settle(); h.render();
  const effect = h.effects.find(e => e.deps?.[0] === record.id && e.deps?.[1] === record.expires_at);
  const cleanup = effect.fn(); now += 60001; timers[0]();
  assert.equal(h.states[8], null); assert.equal(h.states[13], datasetId);
  assert(text(h.render()).includes('Your S3 connection expired')); cleanup();
});

test('departed restoration cannot re-establish a disconnected connection', async () => {
  let resolve;
  const h = app(null, null, async () => new Promise(r => { resolve = r; }));
  h.render(); const cleanup = restoreConnectionEffect(h).fn(); cleanup();
  resolve({ connections: [validConnection] }); await settle();
  assert.equal(h.states[8], null);
});

test('dataset library starts with three rows and closed filters; expand and search are independent', () => {
  const items = Array.from({length: 5}, (_,i) => ({id:String(i),source_key:`file-${i}.csv`,row_count:8,columns:[],status:'READY',lifecycle:'ACTIVE'}));
  let refreshed = 0;
  const h = harness('DatasetBrowser', {}, {
    './historyLabels': {datasetLabel:()=> 'Imported',timeLabel:()=> 'Today'},
    './useCursorList': {useCursorList:()=>({items,state:{filters:{q:'',status:'',scope:'ACTIVE'},page:0},refresh(){refreshed++},loading:false,next:null})},
  });
  const props = {selectedId:null,onSelect(){},refreshKey:'',onChanged(){}};
  let tree=h.render(props);
  assert.equal(nodes(tree).filter(n=>n.type==='li').length,3);
  assert.equal(nodes(tree).find(n=>n.type==='form').props.hidden,true);
  nodes(tree).find(n=>n.type==='button'&&text(n)==='Show all datasets →').props.onClick();
  tree=h.render(props); assert.equal(nodes(tree).filter(n=>n.type==='li').length,5);
  nodes(tree).find(n=>n.type==='button'&&text(n)==='Search & filters').props.onClick();
  tree=h.render(props); assert.equal(nodes(tree).find(n=>n.type==='form').props.hidden,false);
  nodes(tree).find(n=>n.type==='button'&&text(n)==='Show less').props.onClick();
  assert.equal(nodes(h.render(props)).filter(n=>n.type==='li').length,3); assert.equal(refreshed,1);
});


test('the library loads without selecting a dataset first and searches on the server', async () => {
  const requests=[];
  const h=harness('GalaxyExplorer',{}, {'./api':{ApiError,api:async path=>{requests.push(path);return {nodes:[],edges:[],groups:[],next_cursor:null};}}, './motion':{motionScrollBehavior:()=> 'auto'}});
  const props={datasetId:null,revision:'0',active:true,job:null,onOpen(){},onTransform(){},onActivity(){},onChanged(){}};
  h.render(props);h.effects[0].fn();await settle();let tree=h.render(props);
  assert(requests[0].startsWith('/datasets/galaxy/?'));
  assert(!requests[0].includes('/null/'));
  nodes(tree).find(n=>n.type==='button'&&text(n).includes('Search')).props.onClick();tree=h.render(props);
  nodes(tree).find(n=>n.type==='input').props.onChange({target:{value:'orders.xlsx'}});tree=h.render(props);
  nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});h.render(props);h.effects[0].fn();await settle();
  assert(requests.at(-1).includes('q=orders.xlsx'));
});

test('dataset preview is opened from the library rather than showing a second library list', () => {
  const Galaxy=()=>null;let selected=null;
  const h=harness('DatasetPanel',{}, {'./GalaxyExplorer':{__esModule:true,default:Galaxy},'./motion':{motionScrollBehavior:()=> 'auto'}});
  const props={view:'datasets',datasetId:null,onSelect:id=>{selected=id;},onJob(){},busy:false,job:null,datasetRevision:0,onDatasetChanged(){}};
  let tree=h.render(props);const library=nodes(tree).find(n=>n.type===Galaxy);assert(library);
  assert.equal(nodes(tree).find(n=>n.props.id==='dataset-preview').props.hidden,true);
  library.props.onOpen(datasetId);tree=h.render(props);
  assert.equal(selected,datasetId);assert.equal(nodes(tree).find(n=>n.props.id==='dataset-preview').props.hidden,false);
  assert.equal(nodes(tree).filter(n=>n.type===Galaxy).length,1);
});


test('deleting a version requires its file name and preserves server identity and review token', async () => {
  const review={is_original:true,lifecycle:'ACTIVE',can_trash:true,children:[],children_count:0,active_children_count:0,active_jobs_count:0,export_count:0,blockers:[],review_token:'fresh-review',retention_days:0};
  const calls=[];
  const h=harness('DatasetManager',{0:review,2:false},{'./api':{api:async (path,body)=>{calls.push({path,body});return {id:datasetId};}},'./historyLabels':{timeLabel:x=>x}});
  const props={target:{id:datasetId,source_key:'contacts.csv'},onClose(){},onChanged(){},onDependencies(){},onParent(){},onReviewed(){}};
  const button=()=>nodes(h.render(props)).find(n=>n.type==='button'&&text(n)==='Move to Trash');
  assert.equal(button().props.disabled,true);
  await button().props.onClick();assert.equal(calls.length,0);
  h.states[4]='contacts.csv';assert.equal(button().props.disabled,true);
  h.states[5]=true;assert.equal(button().props.disabled,false);
  await button().props.onClick();await settle();
  assert.equal(calls.length,1);assert.equal(calls[0].body.confirm_id,datasetId);assert.equal(calls[0].body.review_token,'fresh-review');
  h.states[0]={...review,can_trash:false};await button().props.onClick();assert.equal(calls.length,1);
  const details=nodes(h.render(props)).find(n=>n.type==='details'&&n.props.className==='management-details');
  assert(!details.props.open);assert(text(details).includes(datasetId));
});

test('constellation selection focuses a file before a second planet click opens data', () => {
  const record={id:datasetId,available:true,name:'contacts.csv',version:1,group_id:'contacts',member_ids:[datasetId,'repeat-import']};const opened=[];
  const h=harness('GalaxyExplorer',{0:{nodes:[record],edges:[],groups:[]}}, {'./api':{ApiError},'./galaxyModel':{planetKind:()=> 'Original',planetColor:()=> '#fff'},'./historyLabels':{timeLabel:()=> 'today'}});
  const props={datasetId:null,revision:'0',active:true,job:null,onOpen:id=>opened.push(id),onTransform(){},onActivity(){},onChanged(){}};
  const scene=()=>nodes(h.render(props)).find(n=>n.props.onPlanet);
  assert.equal(scene().props.focusedGroup,null);
  props.previewId='repeat-import';assert.equal(scene().props.previewId,datasetId);props.previewId=null;
  const originalSceneData=scene().props.data;
  scene().props.onGroup('contacts');assert.equal(scene().props.data,originalSceneData);assert.equal(opened.length,0);assert.equal(scene().props.focusedGroup,'contacts');
  scene().props.onPlanet(record);assert.deepEqual(opened,[datasetId]);
  scene().props.onReset();assert.equal(scene().props.focusedGroup,null);
  scene().props.onGroup('contacts');assert.equal(scene().props.focusedGroup,'contacts');assert.equal(opened.length,1);
  scene().props.onPlanet({...record,available:false,lifecycle:'TRASH'});assert.equal(opened.length,1);
  assert(nodes(h.render(props)).some(n=>n.props.label==='Manage version'&&n.props.open));
});
