import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Controlled hooks check action safety and preview selection without calling the model.
function component(name, preset = {}, apiResponse) {
  let index = 0, refIndex = 0, effects = [];
  const states = [], refs = [], calls = [], exports = {};
  const react = {
    useEffect(fn) { effects.push(fn); },
    useRef(value) { const key = refIndex++; return refs[key] ||= { current: value }; },
    useState(initial) {
      const key = index++;
      if (!(key in states)) states[key] = key in preset ? preset[key] : initial;
      return [states[key], value => { states[key] = typeof value === 'function' ? value(states[key]) : value; }];
    },
  };
  const jsx = (type, props) => ({ type, props: props || {} });
  const modules = {
    react,
    'react/jsx-runtime': { jsx, jsxs: jsx },
    './api': {
      api: async (path, body) => { calls.push({ path, body }); return apiResponse ? apiResponse(path, body) : { id: 'new-job' }; },
      submissionError: error => error.message,
    },
    './ruleSelection': {
      sameColumns: (a, b) => a.length === b.length && [...a].sort().join('|') === [...b].sort().join('|'),
      toggleColumn: () => [],
    },
  };
  const source = fs.readFileSync(new URL(`../src/${name}.tsx`, import.meta.url), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports, require: id => modules[id] || { __esModule: true, default: () => null } });
  return {
    calls, states,
    get effects() { return effects; },
    render(props) { index = 0; refIndex = 0; effects = []; return exports.default(props); },
  };
}
function nodes(root, found = []) {
  if (!root || typeof root !== 'object') return found;
  if (Array.isArray(root)) root.forEach(child => nodes(child, found));
  else { found.push(root); nodes(root.props?.children, found); }
  return found;
}
const text = node => node == null || typeof node === 'boolean' ? '' : typeof node !== 'object' ? String(node)
  : Array.isArray(node) ? node.map(text).join('') : text(node.props?.children);
const button = (tree, label) => nodes(tree).find(node => node.type === 'button' && text(node) === label);
const settle = () => new Promise(resolve => setImmediate(resolve));
const dataset = { id: 'source', columns: [{ key: 'email', name: 'Email' }, { key: 'note', name: 'Notes' }] };
const props = { dataset, busy: false, job: null, onJob() {}, rows: [] };
const example = (before, after) => ({ row_number: 1, before, after, matched: true, match_count: 1 });
const rule = {
  id: 'rule', dataset_id: 'source', status: 'READY', columns: ['email', 'note'], column: 'email',
  instruction: 'Find emails', replacement: '[EMAIL]', pattern: 'email', explanation: '', ignore_case: true, model: 'test', cache_hit: true,
  preview: {
    sampled_rows: 1, matched_rows: 1, cell_character_limit: 1000, full_values: true,
    column_previews: [
      { column: 'email', name: 'Email', sampled_rows: 1, matched_rows: 1, examples: [example('a@example.com', '[EMAIL]')] },
      { column: 'note', name: 'Notes', sampled_rows: 1, matched_rows: 1, examples: [example('Contact b@example.com', 'Contact [EMAIL]')] },
    ],
  },
};
const rulePreset = { 0: ['email', 'note'], 1: 'Find emails', 2: '[EMAIL]', 3: rule };

test('ready regex gives Apply the primary action and lets users inspect each selected column', () => {
  const h = component('RulePanel', rulePreset);
  let tree = h.render(props);
  assert.equal(button(tree, 'Apply').props.className, 'primary-button');
  assert.equal(button(tree, 'Update preview').props.className, 'secondary-button');
  nodes(tree).find(node => node.props['aria-label'] === 'Preview column').props.onChange({ target: { value: 'note' } });
  tree = h.render(props);
  const loom = nodes(tree).find(node => Array.isArray(node.props.rows) && node.props.title === 'Notes');
  assert.equal(loom.props.rows[0].before, 'Contact b@example.com');
  assert.equal(loom.props.rows[0].after, 'Contact [EMAIL]');
});

test('edited or legacy regex previews cannot apply through either the button or its handler', async () => {
  for (const patch of [{ 1: 'Changed instruction' }, { 3: { ...rule, preview: { ...rule.preview, full_values: false } } }]) {
    const h = component('RulePanel', { ...rulePreset, ...patch });
    const tree = h.render(props), apply = button(tree, 'Apply');
    assert.equal(apply.props.disabled, true);
    assert.equal(button(tree, 'Update preview').props.className, 'primary-button');
    apply.props.onClick(); await settle();
    assert.equal(h.calls.length, 0);
  }
});

const transformation = {
  id: 'transform', dataset_id: 'source', status: 'READY', kind: 'DATE', column: 'email', instruction: '',
  options: { date_order: 'REJECT' }, model: 'test',
  preview: { sampled_rows: 1, counts: { ambiguous: 1 }, examples: [{ row_number: 1, before: '03/04/2026', after: null, status: 'ambiguous' }] },
  usage: { model_calls: 0, cached_values: 1, unique_values: 1 },
};
const transformPreset = { 1: 'email', 6: true, 7: transformation };

test('date preview keeps flagged results visible and stale options or withdrawn consent block Apply', async () => {
  const ready = component('TransformPanel', transformPreset).render(props);
  assert(text(ready).includes('1 sample value needs review'));
  assert.equal(button(ready, 'Apply').props.disabled, false);
  assert.equal(button(ready, 'Update preview').props.className, 'secondary-button');
  for (const patch of [{ 2: 'DAY_FIRST' }, { 6: false }]) {
    const h = component('TransformPanel', { ...transformPreset, ...patch });
    const tree = h.render(props), apply = button(tree, 'Apply');
    assert.equal(apply.props.disabled, true);
    apply.props.onClick(); await settle();
    assert.equal(h.calls.length, 0);
  }
});

test('valid Apply submits the existing reviewed rule or transformation with consent', async () => {
  const regex = component('RulePanel', rulePreset);
  button(regex.render(props), 'Apply').props.onClick(); await settle();
  assert.equal(regex.calls[0].path, '/rules/rule/apply/');
  const dates = component('TransformPanel', transformPreset);
  button(dates.render(props), 'Apply').props.onClick(); await settle();
  assert.equal(dates.calls[0].path, '/transformations/transform/apply/');
  assert.equal(dates.calls[0].body.allow_send_values, true);
});

test('late saved regex responses preserve user input while new Generate results still load', async () => {
  let resolveSaved;
  const savedResponse = new Promise(resolve => { resolveSaved = resolve; });
  const h = component('RulePanel', {}, path => path.endsWith('/rules/') ? savedResponse : rule);
  h.render(props); h.effects[0]();
  let tree = h.render(props);
  nodes(tree).find(node => node.type === 'textarea').props.onChange({ target: { value: 'My new instruction' } });
  button(tree, 'Select all').props.onClick();
  resolveSaved({ rules: [rule] }); await settle();
  tree = h.render(props);
  assert.equal(nodes(tree).find(node => node.type === 'textarea').props.value, 'My new instruction');
  assert.equal(button(tree, 'Apply'), undefined);
  assert.equal(nodes(tree).filter(node => node.type === 'input' && node.props.type === 'checkbox' && node.props.checked).length, 2);

  h.render({ ...props, job: { kind: 'GENERATE_RULE', status: 'SUCCESS', rule_id: rule.id } });
  h.effects[1](); await settle();
  tree = h.render(props);
  assert.equal(nodes(tree).find(node => node.type === 'textarea').props.value, rule.instruction);
  assert.equal(button(tree, 'Apply').props.disabled, false);
});

test('late saved date responses preserve date options while untouched drafts restore', async () => {
  for (const edit of [false, true]) {
    let resolveSaved;
    const response = new Promise(resolve => { resolveSaved = resolve; });
    const h = component('TransformPanel', {}, () => response);
    h.render(props); h.effects[0]();
    let tree = h.render(props);
    if (edit) nodes(tree).find(node => node.props['aria-label'] === 'Ambiguous dates').props.onChange({ target: { value: 'DAY_FIRST' } });
    resolveSaved({ transformations: [transformation] }); await settle();
    tree = h.render(props);
    assert.equal(nodes(tree).find(node => node.props['aria-label'] === 'Ambiguous dates').props.value, edit ? 'DAY_FIRST' : 'REJECT');
    assert.equal(Boolean(button(tree, 'Apply')), !edit);
  }
});
