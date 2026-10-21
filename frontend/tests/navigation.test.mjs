import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/navigation.ts', import.meta.url),'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports});
test('direct page URLs and legacy anchors resolve; unknown and prototype keys fall back safely', () => {
  for (const key of Object.keys(exports.pages)) {
    assert.equal(exports.pageFromHash(`#/${key}`),key);
    assert.equal(exports.pageFromHash(`#${key}`),key);
  }
  for (const hash of ['', '#workspace', '#/missing', '#/__proto__', '#/constructor']) assert.equal(exports.pageFromHash(hash),'sources');
});
