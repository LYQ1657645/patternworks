import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/galaxyModel.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports});
const planet=(id,parent_id,version)=>({id,parent_id,version,available:true,operation:parent_id?'regex_replace':'import'});
test('constellation positions keep versions distinct and compact without changing lineage',()=>{
  const input={nodes:[planet('root',null,1),planet('a','root',2),planet('b','root',3),planet('c','a',4),planet('reimport',null,5)],edges:[]};
  const snapshot=JSON.stringify(input);const result=exports.positionPlanets(input);const byId=Object.fromEntries(result.map(n=>[n.id,n]));
  assert(Math.hypot(byId.c.x,byId.c.y)<180);
  assert.equal(byId.c.parent_id,'a');
  assert.notEqual(byId.a.y,byId.b.y);assert.notEqual(byId.root.y,byId.reimport.y);
  assert.equal(JSON.stringify(input),snapshot);
  assert.equal(JSON.stringify(result),JSON.stringify(exports.positionPlanets(input)));
  assert.equal(new Set(result.map(n=>`${n.x}:${n.y}:${n.z}`)).size,5);
});
test('missing parents, cycles and empty graphs produce finite bounded coordinates',()=>{
  for(const nodes of [[],[planet('orphan','missing',1)],[planet('a','b',1),planet('b','a',2)]]){
    const result=exports.positionPlanets({nodes,edges:[]});assert.equal(result.length,nodes.length);
    result.forEach(n=>assert([n.x,n.y,n.z,n.fx,n.fy,n.fz].every(Number.isFinite)));
  }
});
test('unavailable versions are visually distinct without losing their operation',()=>{
  const n={...planet('a','root',2),available:false};
  assert.equal(exports.planetKind(n),'Regex result');assert.notEqual(exports.planetColor(n),exports.planetColor({...n,available:true}));
});
test('different files occupy separate clusters while versions remain in their own family',()=>{
  const nodes=[{...planet('a',null,1),group_id:'one'},{...planet('a2','a',2),group_id:'one'},{...planet('b',null,1),group_id:'two'}];
  const result=exports.positionPlanets({nodes,edges:[],groups:[{id:'one'},{id:'two'}]});
  const byId=Object.fromEntries(result.map(n=>[n.id,n]));
  assert(Math.hypot(byId.a2.x-byId.a.x,byId.a2.y-byId.a.y)<100);
  assert(Math.abs(byId.b.x-byId.a.x)>200);
  assert.equal(result.length,3);
  assert(result.every(n=>[n.x,n.y,n.z].every(Number.isFinite)));
});
test('failed and cancelled records are labeled as attempts, not completed versions',()=>{
  assert.equal(exports.planetKind({...planet('a','root',2),status:'FAILED',available:false}),'Failed attempt');
  assert.equal(exports.planetKind({...planet('a','root',2),status:'CANCELLED',available:false}),'Cancelled attempt');
});

test('dense file constellations retain planet clearance and deterministic layout',()=>{
  const nodes=Array.from({length:100},(_,i)=>planet(String(i),i?String(i-1):null,i+1));
  const result=exports.positionPlanets({nodes,edges:[]});
  for(let i=0;i<result.length;i++)for(let j=0;j<i;j++)assert(Math.hypot(result[i].x-result[j].x,result[i].y-result[j].y)>80);
  assert(Math.max(...result.map(n=>Math.hypot(n.x,n.y)))<880);
});
test('camera limits stay finite for empty, wide and narrow viewports and bound zoom-out',()=>{
  for(const aspect of [.3,1,2]){
    const frame=exports.cameraFrame([{x:-220,y:-90,z:0},{x:220,y:100,z:12}],aspect,50);
    assert(frame.minDistance<frame.distance && frame.maxDistance>frame.distance);
    assert(frame.maxDistance/frame.distance<2);
    assert(Object.values(frame).every(Number.isFinite));
  }
  assert(Object.values(exports.cameraFrame([],1,50)).every(Number.isFinite));
});

test('equal content collapses within its file only, retaining real operation endpoints',()=>{
  const nodes=[
    {...planet('a',null,1),group_id:'one',content_hash:'same',lifecycle:'ACTIVE',created_at:'2026-01-01'},
    {...planet('again',null,2),group_id:'one',content_hash:'same',lifecycle:'ACTIVE',created_at:'2026-01-02'},
    {...planet('result','again',3),group_id:'one',content_hash:'different',lifecycle:'ACTIVE'},
    {...planet('noop','result',4),group_id:'one',content_hash:'different',lifecycle:'ACTIVE'},
    {...planet('other',null,1),group_id:'two',content_hash:'same',lifecycle:'ACTIVE'},
    {...planet('trash',null,5),group_id:'one',content_hash:'same',lifecycle:'TRASH'},
    {...planet('cancelled',null,6),group_id:'one',status:'CANCELLED'},
  ];
  const data={nodes,edges:[{id:'apply',source:'again',target:'result'},{id:'noop',source:'result',target:'noop'}]};
  const snapshot=JSON.stringify(data);const graph=exports.distinctVersions(data);
  assert.equal(graph.nodes.length,4);assert.equal(graph.edges.length,1);
  assert.equal(graph.edges[0].source,'a');assert.equal(graph.edges[0].before_id,'again');
  assert.equal(graph.nodes[0].created_at,'2026-01-02');
  assert.equal(graph.nodes[0].member_ids.join(','),'a,again');
  assert.equal(graph.nodes.find(n=>n.id==='result').parent_id,'a');
  assert.equal(JSON.stringify(data),snapshot);
});
test('unproven equality never merges same-named files or row counts',()=>{
  const nodes=[planet('a',null,1),planet('b',null,2)].map(n=>({...n,name:'same.csv',rows:10}));
  assert.equal(exports.distinctVersions({nodes,edges:[]}).nodes.length,2);
});
test('framing one distant constellation targets its actual position without including the origin',()=>{
  const a=exports.cameraFrame([{x:900,y:400,z:0},{x:988,y:420,z:0}],1.5,50);
  const b=exports.cameraFrame([{x:0,y:0,z:0},{x:88,y:20,z:0}],1.5,50);
  assert.equal(a.distance,b.distance);assert.equal(a.x-b.x,900);assert.equal(a.y-b.y,400);
});
