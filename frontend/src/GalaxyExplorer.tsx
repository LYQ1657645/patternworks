import { lazy, Suspense, useEffect, useState } from 'react';
import { api, ApiError } from './api';
import type { Dataset, Job } from './api';
import type { Constellation, Planet, Flight } from './galaxyModel';
import { distinctVersions, planetColor, planetKind } from './galaxyModel';
import { timeLabel, jobLabels } from './historyLabels';
const PlanetScene = lazy(() => import('./PlanetScene').catch(() => ({ default: () => <p className="galaxy-status" role="status">Could not load the star map. Open Search to browse your files, or reload the page.</p> })));
import DatasetManager from './DatasetManager';
import FloatingPanel from './FloatingPanel';

type Props={previewId?:string|null;manageRequest?:{id:string;source_key:string}|null;datasetId:string|null;revision:string;active:boolean;job:Job|null;onOpen:(id:string)=>void;onTransform:(id:string)=>void;onActivity:()=>void;onChanged:(dataset:Dataset)=>void};
export default function GalaxyExplorer({datasetId,revision,active,job,onOpen,onActivity,onChanged,manageRequest,previewId}:Props){
  const [data,setData]=useState<Constellation|null>(null);const [error,setError]=useState('');const [loading,setLoading]=useState(false);
  const [reload,setReload]=useState(0);
  const [focus,setFocus]=useState<string|null>(datasetId);const [flight,setFlight]=useState<Flight|null>(null);

  const [searchOpen,setSearchOpen]=useState(false);const [draft,setDraft]=useState('');
  const [filters,setFilters]=useState({q:'',scope:'ACTIVE',status:'',parent_id:''});
  const [cursors,setCursors]=useState(['']);const [page,setPage]=useState(0);
  const [family,setFamily]=useState<string|null>(null);
  const [managed,setManaged]=useState<{id:string;source_key:string}|null>(null);
  const query=new URLSearchParams({...filters,cursor:cursors[page] || '',limit:'100'}).toString();
  function filter(values:Partial<typeof filters>){setManaged(null);setFilters(old=>({...old,...values}));setCursors(['']);setPage(0);setFamily(null);setFlight(null);}
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();let alive=true;setLoading(true);setError('');setData(null);
    api<Constellation>(`/datasets/galaxy/?${query}`,undefined,controller.signal)
      .then(raw=>{if(alive){const d=distinctVersions(raw);setData(d);setFocus(current=>d.nodes.some(n=>n.id===current)?current:d.nodes.some(n=>n.id===datasetId)?datasetId:d.nodes[0]?.id || null);setFlight(null);}})
      .catch(e=>{if(alive){if(e instanceof ApiError && e.status===400 && page>0){setCursors(['']);setPage(0);}else setError(e instanceof Error?e.message:'Could not load the dataset library.');}})
      .finally(()=>{if(alive)setLoading(false);});
    return()=>{alive=false;controller.abort();};
  },[query,revision,reload,active]);
  useEffect(()=>{const node=data?.nodes.find(n=>n.id===datasetId||n.member_ids?.includes(datasetId||''));if(node){setFocus(node.id);setFlight(null);}},[datasetId,data]);
  useEffect(()=>{if(manageRequest)setManaged(manageRequest);},[manageRequest]);
  function openVersion(n:Planet){setFocus(n.id);setFlight(null);setSearchOpen(false);if(n.available){setManaged(null);onOpen(n.id);}else setManaged({id:n.id,source_key:n.name});}
  function select(n:Planet){if(!family){setFamily(n.group_id||null);setFocus(n.id);setFlight(null);}else openVersion(n);}
  const scenePreviewId=previewId ? data?.nodes.find(n=>n.id===previewId||n.member_ids?.includes(previewId))?.id || previewId : null;
  const currentTask=job&&['QUEUED','RUNNING'].includes(job.status)?job:null;
  return <><section className={`galaxy library-galaxy ${previewId ? "is-previewing" : ""}`} aria-label="Dataset library">
    <div className="universe-toolbar"><div><h1>{family ? data?.groups?.find(g=>g.id===family)?.name || 'File versions' : 'Library'}</h1><p>{family ? 'Select a planet to open its data' : 'Select a constellation to explore a file'}</p></div>
      <button type="button" aria-expanded={searchOpen} onClick={()=>setSearchOpen(true)}>Search</button>
    </div>
    <FloatingPanel open={searchOpen&&active} onClose={()=>setSearchOpen(false)} label="Find a file" className="universe-search-panel">
      <div className="list-heading"><h2>Find a file</h2><button className="text-button" onClick={()=>setSearchOpen(false)}>Close</button></div>
    <form id="galaxy-search" className="galaxy-search" onSubmit={e=>{e.preventDefault();filter({q:draft.trim()});}}>
      <div className="galaxy-search-query"><label>Find a file<input value={draft} maxLength={256} placeholder="File name or worksheet" onChange={e=>setDraft(e.target.value)}/></label><button type="submit">Find</button></div><div className="galaxy-search-filters">
      <label>Location<select value={filters.scope} onChange={e=>filter({scope:e.target.value})}><option value="ACTIVE">Available</option><option value="TRASH">Trash</option><option value="ALL">All files</option></select></label>
      <label>Status<select value={filters.status} onChange={e=>filter({status:e.target.value})}><option value="">All statuses</option>{['READY','PENDING','FAILED','CANCELLED'].map(s=><option key={s} value={s}>{s === 'READY' ? 'Ready' : s === 'PENDING' ? 'Processing' : s === 'FAILED' ? 'Failed' : 'Cancelled'}</option>)}</select></label>
      <button type="button" onClick={()=>{setDraft('');filter({q:'',scope:'ACTIVE',status:'',parent_id:''});}}>Clear</button></div>
    </form>
    {loading && <p role="status">Loading files</p>}
    {error && <p role="alert">{error}</p>}
    {data && <div className="search-versions">{data.nodes.map(n=><div className="search-version-row" key={n.id}><button type="button" onClick={()=>openVersion(n)}><i style={{background:planetColor(n)}}/><span>{n.name}<small>{planetKind(n)}{n.sheet ? ` · ${n.sheet}` : ''}</small></span><time>{timeLabel(n.created_at)}</time></button>{data.edges.filter(e=>e.target===n.id).map(e=><button className="search-operation" key={e.id} onClick={()=>{setSearchOpen(false);setFlight(e);}}>View operation</button>)}</div>)}</div>}
      {data&&!family&&(data.next_cursor||page>0)&&<nav className="galaxy-pagination" aria-label="Library pages"><span>Page {page+1}</span><button disabled={loading||page===0} onClick={()=>setPage(p=>p-1)}>Previous</button><button disabled={loading||!data.next_cursor} onClick={()=>{setCursors(old=>[...old.slice(0,page+1),data.next_cursor!]);setPage(p=>p+1);}}>Next</button></nav>}
    {data?.nodes.length === 0 && <p>No files match these filters.</p>}
    <button className="text-button" disabled={loading} onClick={()=>setReload(v=>v+1)}>Refresh</button>
    </FloatingPanel>
    {filters.parent_id&&!family&&<p className="galaxy-status">Showing dependent datasets. <button onClick={()=>filter({parent_id:''})}>Show all files</button></p>}
    {error&&<p className="galaxy-error" role="alert">{error} <button onClick={()=>setReload(v=>v+1)}>Try again</button></p>}
    {loading&&<p className="galaxy-status" role="status">Loading version history…</p>}
    {!loading&&(!data||data.nodes.length===0)&&<div className="galaxy-camera"><button onClick={()=>{setFamily(null);filter({q:"",scope:"ACTIVE",status:"",parent_id:""});setReload(v=>v+1);}}>Reset</button></div>}
    {data&&<>
      {data.nodes.length===0?<div className="galaxy-empty"><h3>{filters.scope==='TRASH'?'Trash is empty.':'No datasets to show.'}</h3><p>{filters.q||filters.status?'Try a different search or reset the filters.':filters.scope==='TRASH'?'Deleted versions appear here during their recovery period.':'Import a CSV or Excel file to begin your constellation.'}</p><a href="#/sources">Import a file</a></div>:<div className="galaxy-body">
        <div className="galaxy-space">{active && <Suspense fallback={<p className="galaxy-status">Loading star map…</p>}><PlanetScene data={data} selected={focus} selectedFlight={flight?.id || null} active={active} previewId={scenePreviewId} focusedGroup={family} onReset={()=>{setFamily(null);setFlight(null);}} onPlanet={select} onGroup={id=>{setFamily(id);setFlight(null);}} onFlight={e=>{setManaged(null);setFlight(e);}}/></Suspense>}
        </div>
        <FloatingPanel open={!!flight&&active} onClose={()=>setFlight(null)} label="Transformation" className="operation-panel">
          {flight&&<>
            <div className="inspector-top"><span>TRANSFORMATION</span><button aria-label="Close transformation" onClick={()=>setFlight(null)}>Close</button></div>
            <h3>{flight.label}</h3><p className="flight-route">V{data.nodes.find(n=>n.id===flight.source)?.version} <span>→</span> V{data.nodes.find(n=>n.id===flight.target)?.version}</p>
            <p>{flight.columns.join(' · ')||'Column details unavailable'}</p>
            {typeof flight.details.instruction==='string'&&flight.details.instruction&&<p className="operation-instruction">{flight.details.instruction}</p>}
            {flight.changed_rows!==null&&flight.changed_rows!==undefined&&<p><strong>{flight.changed_rows.toLocaleString()}</strong> rows changed</p>}
            {flight.column_stats.length>1&&flight.column_stats.map(s=><div className="flight-stat" key={s.column}><span>{s.column}</span><strong>{s.changed_rows??0} rows changed</strong></div>)}
            {Object.keys(flight.status_counts).length>0&&<p>{Object.entries(flight.status_counts).map(([key,value])=>`${value} ${key}`).join(' · ')}</p>}
            <details><summary>Rule details</summary>{Object.entries(flight.details).filter(([,v])=>v!==null&&v!==undefined).map(([k,v])=><div className="operation-value" key={k}><span>{k.replaceAll('_',' ')}</span><code>{typeof v==='object'?JSON.stringify(v,null,2):String(v)}</code></div>)}</details>
            <div className="inspector-actions"><button disabled={!data.nodes.find(n=>n.id===flight.source)?.available} onClick={()=>{setFocus(flight.source);setFlight(null);onOpen(flight.before_id || flight.source);}}>Preview before</button><button disabled={!data.nodes.find(n=>n.id===flight.target)?.available} onClick={()=>{setFocus(flight.target);setFlight(null);onOpen(flight.after_id || flight.target);}}>Preview after</button></div>
          </>}
        </FloatingPanel>
      </div>}
      {currentTask&&<button className="galaxy-task" onClick={onActivity}><span className="task-pulse"/>{jobLabels[currentTask.kind]} · {currentTask.progress}%<span>View task</span></button>}

      {(data.truncated||data.ancestry_incomplete)&&<p className="galaxy-status">Some older history is outside this view. Use search or the library pages to find it.</p>}
    </>}
  </section>
    <FloatingPanel open={!!managed&&active} onClose={()=>setManaged(null)} label="Manage version" className="management-overlay">{managed&&<div className="galaxy-management"><DatasetManager key={managed.id} target={managed} onClose={()=>setManaged(null)} onParent={setManaged} onReviewed={()=>{}}
      onChanged={record=>{onChanged(record);setReload(v=>v+1);}}
      onDependencies={id=>{setManaged(null);setSearchOpen(true);setDraft('');filter({parent_id:id,scope:'ALL',q:'',status:''});}}/></div>}</FloatingPanel>
  </>;
}
