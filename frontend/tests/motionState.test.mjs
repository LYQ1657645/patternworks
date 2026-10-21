import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/motionState.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const {taskPresentation, isNewDatasetResult, layoutRows, isFlagged} = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

test('100 percent RUNNING is still processing; only SUCCESS completes a task', () => {
  assert.equal(taskPresentation({status:'RUNNING',progress:100,stage:'Saving'}).state, 'running');
  assert.equal(taskPresentation({status:'RUNNING',progress:100,stage:'Saving'}).label, 'Saving');
  assert.equal(taskPresentation({status:'SUCCESS',progress:100}).label, 'Complete');
});
test('queue, failure and cancellation stop running motion without inventing completion', () => {
  for (const status of ['QUEUED','FAILED','CANCELLED']) {
    const state = taskPresentation({status,progress:38});
    assert.equal(state.running,false); assert.equal(state.progress,38); assert.notEqual(state.label,'Complete');
  }
  assert.equal(taskPresentation({status:'RUNNING',progress:NaN}).progress,0);
  assert.equal(taskPresentation({status:'RUNNING',progress:150}).progress,100);
});
test('arrival requires this available READY dataset and an actual successful creation job', () => {
  const dataset={id:'result',status:'READY',lifecycle:'ACTIVE'};
  const job={status:'SUCCESS',dataset_id:'result',kind:'APPLY_RULE'};
  assert.equal(isNewDatasetResult(job,dataset),true);
  for (const patch of [{status:'RUNNING'},{status:'FAILED'},{kind:'EXPORT_CSV'},{dataset_id:'other'},{dataset_available:false}]) assert.equal(isNewDatasetResult({...job,...patch},dataset),false);
  for (const patch of [{status:'PENDING'},{lifecycle:'TRASH'}]) assert.equal(isNewDatasetResult(job,{...dataset,...patch}),false);
});
test('category layout groups only actual returned values and retains row identities', () => {
  const rows=[{id:'1',after:'Software'},{id:'2',after:'Cloud'},{id:'3',after:'Software'},{id:'4',after:null},{id:'5',after:'Other'},{id:'6',after:'Cloud'}];
  const result=layoutRows(rows,true,true);
  assert.deepEqual(result.map(r=>r.id),['1','3','2','4','5']);
  assert.equal(result[0].count,2);
  assert.equal(result[3].group,'No result');
  assert.equal(new Set(result.map(r=>r.id)).size,5);
  assert.deepEqual(rows.map(r=>r.id),['1','2','3','4','5','6']);
  assert.deepEqual(layoutRows(rows,false,true).map(r=>r.id),['1','2','3','4','5']);
});
test('ambiguous, invalid, missing and fallback stay explicit review states', () => {
  for(const status of ['ambiguous','invalid','missing','fallback']) assert.equal(isFlagged(status),true);
  for(const status of ['normalized','classified','matched','no match',undefined]) assert.equal(isFlagged(status),false);
});
