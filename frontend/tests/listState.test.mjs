import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/listState.ts',import.meta.url),'utf8');
const javascript=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {listReducer,restoreList,save,savedId}=await import('data:text/javascript;base64,'+Buffer.from(javascript).toString('base64'));
const fresh={filters:{q:'',status:''},cursors:[''],page:0};
test('changing a search/filter resets cursors and page, preserving other filters',()=>{
 const page2=listReducer(fresh,{type:'next',cursor:'a'});
 const filtered=listReducer(page2,{type:'filter',values:{q:'report'}});
 assert.deepEqual(filtered,{filters:{q:'report',status:''},cursors:[''],page:0});
 assert.deepEqual(listReducer(filtered,{type:'filter',values:{status:'READY'}}).filters,{q:'report',status:'READY'});
});
test('back/next replaces the old branch and refresh returns to page one',()=>{
 let state=listReducer(listReducer(fresh,{type:'next',cursor:'a'}),{type:'next',cursor:'b'});
 state=listReducer(state,{type:'previous'});
 state=listReducer(state,{type:'next',cursor:'new-b'});
 assert.deepEqual(state.cursors,['','a','new-b']);assert.equal(state.page,2);
 assert.deepEqual(listReducer(state,{type:'first'}),fresh);
 assert.equal(listReducer(fresh,{type:'previous'}).page,0);
});
test('restore only valid bounded filters/page state, ignoring extra fields',()=>{
 const saved={filters:{q:'客户',status:'READY',secret:'ignored'},cursors:['','cursor'],page:1,credential:'ignored'};
 assert.deepEqual(restoreList(JSON.stringify(saved),fresh.filters),{filters:{q:'客户',status:'READY'},cursors:['','cursor'],page:1});
 for(const raw of ['bad','null',JSON.stringify({...saved,page:20}),JSON.stringify({...saved,cursors:['bad']}),JSON.stringify({...saved,cursors:['',null]}),JSON.stringify({...saved,filters:{q:3,status:''}})]) assert.deepEqual(restoreList(raw,fresh.filters),fresh);
});
test('storage failures are optional and only a valid UUID can restore a selected record',()=>{
 globalThis.sessionStorage={getItem:()=>{throw new Error('disabled')},setItem:()=>{throw new Error('disabled')}};
 assert.equal(savedId('selection'),null);assert.doesNotThrow(()=>save('selection','value'));
 globalThis.sessionStorage={getItem:()=>'/arbitrary/path'};assert.equal(savedId('selection'),null);
 globalThis.sessionStorage={getItem:()=> '07840491-cf24-4c92-bae3-8bd8bd2265f0'};
 assert.equal(savedId('selection'),'07840491-cf24-4c92-bae3-8bd8bd2265f0');
});
