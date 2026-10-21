import { useState } from "react";
import type { FormEvent } from "react";
import type { Dataset } from "./api";
import { datasetLabel, timeLabel } from "./historyLabels";
import { useCursorList } from "./useCursorList";
import DatasetManager from "./DatasetManager";

export default function DatasetBrowser({ selectedId, onSelect, refreshKey, onChanged }: {
  selectedId: string | null; onSelect: (id: string) => void; refreshKey: string; onChanged: (dataset: Dataset) => void;
}) {
  const list = useCursorList<Dataset>("datasets", { q: "", status: "", scope: "ACTIVE", parent_id: "", latest_imports: "true" }, refreshKey);
  const [expanded, setExpanded] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [draft, setDraft] = useState(list.state.filters.q);
  const [managed, setManaged] = useState<{id:string;source_key:string}|null>(null);
  function search(event: FormEvent) { event.preventDefault(); list.filter({ q: draft.trim() }); }
  return <section className="dataset-browser" aria-label="Dataset library">
    <div className="list-heading"><h3>Dataset library</h3><button className="secondary-button" aria-expanded={searchOpen} aria-controls="dataset-search" onClick={() => setSearchOpen(!searchOpen)}>Search & filters{list.state.filters.q || list.state.filters.status || list.state.filters.scope !== "ACTIVE" ? " · active" : ""}</button><button className="text-button" disabled={list.loading} onClick={list.refresh}>Refresh datasets</button></div>
    <form id="dataset-search" hidden={!searchOpen} className="list-filters" onSubmit={search}>
      <label>Search datasets<input value={draft} maxLength={256} onChange={(event) => setDraft(event.target.value)} placeholder="File name, worksheet or full dataset ID" /></label>
      <button className="secondary-button" type="submit">Search datasets</button>
      <button className="text-button" type="button" onClick={() => { setDraft(""); list.filter({ q: "" }); }}>Clear search</button>
      <label>Dataset status<select value={list.state.filters.status} onChange={(event) => list.filter({ status: event.target.value })}>
        <option value="">All statuses</option>{["READY", "PENDING", "FAILED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}
      </select></label>
      <label>Dataset location<select value={list.state.filters.scope} onChange={(event) => list.filter({ scope: event.target.value })}>
        <option value="ACTIVE">Active datasets</option><option value="TRASH">Trash</option><option value="ALL">Active & Trash</option>
      </select></label>
    </form>
    {list.state.filters.parent_id && <p>Dependencies of {list.state.filters.parent_id} <button className="text-button" onClick={() => list.filter({parent_id:""})}>Clear dependency filter</button></p>}
    {list.error && <p role="alert">{list.error} Use Refresh datasets to retry.</p>}
    {list.notice && <p role="status">{list.notice}</p>}
    {list.loading ? <p role="status">Loading datasets…</p> : <>
      <ul className="record-list" aria-label="Dataset results">{(expanded ? list.items : list.items.slice(0, 3)).map((dataset) => <li key={dataset.id} className={dataset.id === selectedId ? "selected-record" : ""}>
        <div><strong>{dataset.source_key}</strong><small>{datasetLabel(dataset)} · {timeLabel(dataset.created_at)}</small>
          {dataset.sheet_name && <small>Sheet: {dataset.sheet_name}</small>}
          <span>{dataset.row_count.toLocaleString()} rows · {dataset.columns.length} columns · {dataset.status} · {dataset.lifecycle}</span>
          <small>{dataset.expires_at ? `Expires ${timeLabel(dataset.expires_at)}` : ""}{dataset.purge_after ? ` · Trash recovery ends ${timeLabel(dataset.purge_after)}` : ""}</small></div>
        <div className="record-actions"><button className="secondary-button" disabled={dataset.status !== "READY" || dataset.lifecycle !== "ACTIVE"} aria-pressed={dataset.id === selectedId}
          onClick={() => onSelect(dataset.id)}>{dataset.id === selectedId ? "Viewing dataset" : "Open dataset"}</button>
          <button className="text-button" onClick={() => setManaged(dataset)}>Delete / retention</button></div>
      </li>)}</ul>
      {!list.items.length && <p className="dataset-empty">No datasets match these filters.</p>}
    </>}
    {(list.items.length > 3 || list.next || list.state.page > 0) && <button className="text-button" aria-expanded={expanded} onClick={() => { setExpanded(!expanded); if (expanded) list.refresh(); }}>{expanded ? "Show less" : "Show all datasets →"}</button>}
    <nav hidden={!expanded} className="list-pagination" aria-label="Dataset pages"><span>Dataset page {list.state.page + 1} · newest first</span>
      <button className="secondary-button" disabled={list.loading || list.state.page === 0} onClick={list.previous}>Previous datasets</button>
      <button className="secondary-button" disabled={list.loading || !list.next} onClick={list.advance}>Next datasets</button>
    </nav>
    {managed && <DatasetManager key={managed.id} target={managed} onClose={() => setManaged(null)} onParent={setManaged} onReviewed={list.reload}
      onChanged={(dataset) => { onChanged(dataset); list.refresh(); }}
      onDependencies={(id) => { setSearchOpen(true); setExpanded(true); setDraft(""); list.filter({parent_id:id,scope:"ALL",q:"",status:""}); setManaged(null); }} />}

  </section>;
}
