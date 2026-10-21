import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/ruleSelection.ts', import.meta.url), 'utf8');
const javascript = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText;
const { toggleColumn, sameColumns } = await import('data:text/javascript;base64,' + Buffer.from(javascript).toString('base64'));
test('checkbox selections follow source order without losing earlier selections', () => {
  assert.deepEqual(toggleColumn(['c0','c1','c2'], ['c2'], 'c0', true), ['c0','c2']);
  assert.deepEqual(toggleColumn(['c0','c1','c2'], ['c0','c2'], 'c0', false), ['c2']);
});
test('clearing the last checkbox yields an empty selection for the submit guard', () => {
  assert.deepEqual(toggleColumn(['c0','c1'], ['c0'], 'c0', false), []);
});
test('changing the target set invalidates a preview, mere ordering does not', () => {
  assert.equal(sameColumns(['c0','c1'], ['c1','c0']), true);
  assert.equal(sameColumns(['c0','c1'], ['c0']), false);
  assert.equal(sameColumns(['c0','c1'], ['c0','c2']), false);
});
