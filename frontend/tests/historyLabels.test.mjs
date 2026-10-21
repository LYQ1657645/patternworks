import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/historyLabels.ts',import.meta.url),'utf8');
const javascript=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {jobDataset,jobLabels}=await import('data:text/javascript;base64,'+Buffer.from(javascript).toString('base64'));
test('history opens only successful results and resolves preview sources separately',()=>{
 assert.equal(jobDataset({status:'FAILED',dataset_id:'pending-output',result:{}}),null);
 assert.equal(jobDataset({status:'SUCCESS',dataset_id:'trashed-output',dataset_available:false,result:{}}),null);
 assert.equal(jobDataset({status:'SUCCESS',dataset_id:'result',result:{source_dataset_id:'source'}}),'result');
 assert.equal(jobDataset({status:'SUCCESS',dataset_id:null,result:{source_dataset_id:'source'}}),'source');
 assert.equal(jobDataset({status:'SUCCESS',dataset_id:null,result:{source_dataset_id:42}}),null);
});
test('all supported task types have product labels including exports',()=>{
 assert.equal(Object.keys(jobLabels).length,10);assert.equal(jobLabels.LIST_WORKSHEETS, 'Read Excel worksheets');
 assert.equal(jobLabels.EXPORT_CSV,'CSV export');
});
