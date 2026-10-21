import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const stateSource = fs.readFileSync(new URL('../src/motionState.ts', import.meta.url), 'utf8');
const stateJs = ts.transpileModule(stateSource, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const motionState = await import('data:text/javascript;base64,' + Buffer.from(stateJs).toString('base64'));
const jsx = (type, props) => ({ type, props: props || {} });
const exports = {};
const code = ts.transpileModule(fs.readFileSync(new URL('../src/LoomPreview.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
vm.runInNewContext(code, {
  exports,
  require: id => ({
    react: { useRef: () => ({ current: null }) },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    '@gsap/react': { useGSAP() {} },
    gsap: { gsap: {} },
    './motion': { useAppearance: () => ({ reduced: true }) },
    './motionState': motionState,
  }[id] || {}),
});
function nodes(root, output = []) {
  if (!root || typeof root !== 'object') return output;
  if (Array.isArray(root)) { root.forEach(child => nodes(child, output)); return output; }
  output.push(root); nodes(root.props?.children, output); return output;
}
const props = {
  rows: [{ id: 'one', label: 'Row 1', before: 'one@example.com', after: '[EMAIL]', status: 'matched' }],
  ready: true, active: true, job: null, title: 'Email',
};

test('ready loom cards retain both original and result, including blank and missing values', () => {
  const output = nodes(exports.default({ ...props, rows: [
    ...props.rows,
    { id: 'two', label: 'Row 2', before: '', after: null, status: 'invalid' },
  ] }));
  const values = output.filter(node => node.type === 'code');
  assert.equal(values.find(node => node.props['aria-label'] === 'Row 1 original value').props.children, 'one@example.com');
  assert.equal(values.find(node => node.props['aria-label'] === 'Row 1 result').props.children, '[EMAIL]');
  assert.equal(values.find(node => node.props['aria-label'] === 'Row 2 original value').props.children, '(empty)');
  assert.equal(values.find(node => node.props['aria-label'] === 'Row 2 result').props.children, 'null');
  assert(output.some(node => node.props.className === 'loom-review-status' && node.props.children === 'invalid'));
});

test('stale loom preview hides old results and asks for a new preview', () => {
  const output = nodes(exports.default({ ...props, stale: true }));
  assert.equal(output.filter(node => node.type === 'code').length, 1);
  assert.equal(output.find(node => node.type === 'code').props.children, 'one@example.com');
  assert(output.some(node => node.props.role === 'status' && node.props.children === 'Options changed. Preview again.'));
});
