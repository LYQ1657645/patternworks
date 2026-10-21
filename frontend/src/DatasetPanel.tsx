import { useEffect, useRef, useState } from "react";
import { datasetLabel, timeLabel } from "./historyLabels";
import { ActionSpark, Reveal, motionScrollBehavior } from "./motion";
import { isNewDatasetResult } from "./motionState";
import LoomPreview from "./LoomPreview";
import type { FormEvent } from "react";
import { api, ApiError, submissionError } from "./api";
import type { Dataset, DatasetPage, Job } from "./api";
import RulePanel from "./RulePanel";
import TransformPanel from "./TransformPanel";
import ExportPanel from "./ExportPanel";
import GalaxyExplorer from "./GalaxyExplorer";
import FloatingPanel from "./FloatingPanel";

type Props = {
  view: "datasets" | "transform";
  visible?: boolean;
  datasetId: string | null;
  onSelect: (id: string | null) => void;
  onJob: (job: Job) => void;
  busy: boolean;
  job: Job | null;
  datasetRevision: number;
  onDatasetChanged: () => void;
  onActivity?: () => void;
  openRequest?: { id: string; nonce: number } | null;
};

export default function DatasetPanel({ view, visible = true, datasetId, onSelect, onJob, busy, job, datasetRevision, onDatasetChanged, openRequest, onActivity = () => {} }: Props) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [page, setPage] = useState<DatasetPage | null>(null);
  const [cursors, setCursors] = useState([0]);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [column, setColumn] = useState("");
  const [find, setFind] = useState("");
  const [replacement, setReplacement] = useState("");
  const [tool, setTool] = useState("regex");
  const version = useRef(0);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewRequest, setPreviewRequest] = useState<string | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const [manageRequest,setManageRequest]=useState<{id:string;source_key:string}|null>(null);
  const openedRequest = useRef(0);
  useEffect(() => {
    if (!visible || view !== "datasets" || !openRequest || openedRequest.current === openRequest.nonce) return;
    openedRequest.current = openRequest.nonce;
    setPreviewOpen(true);
    setPreviewRequest(openRequest.id);
  }, [openRequest, visible, view]);
  useEffect(() => {
    if (previewRequest && dataset?.id === previewRequest && !loading) {
      if(view === "transform") previewRef.current?.scrollIntoView({ behavior: motionScrollBehavior(), block: "start" });
      setPreviewRequest(null);
    }
  }, [dataset?.id, loading, previewRequest]);

  useEffect(() => {
    if (datasetId) return;
    let alive = true;
    api<{ datasets: Dataset[] }>("/datasets/?status=READY&limit=1")
      .then((result) => {
        if (!alive) return;
        if (result.datasets[0]) onSelect(result.datasets[0].id);
      })
      .catch(() => { if (alive) setError("Could not load recent datasets."); });
    return () => { alive = false; };
  }, [datasetId, onSelect]);

  useEffect(() => {
    const generation = ++version.current;
    setDataset(null);
    setPage(null);
    setCursors([0]);
    setPageIndex(0);
    setError("");
    if (!datasetId) return;
    setLoading(true);
    Promise.all([
      api<Dataset>(`/datasets/${datasetId}/`),
      api<DatasetPage>(`/datasets/${datasetId}/rows/?limit=25&after=0`),
    ]).then(([record, rows]) => {
      if (version.current !== generation) return;
      setDataset(record);
      setPage(rows);
      setColumn("");
    }).catch((err) => {
      if (version.current === generation) {
        if (err instanceof ApiError && [404,409].includes(err.status)) onSelect(null);
        else setError(err instanceof Error ? err.message : "Could not load dataset.");
      }
    }).finally(() => {
      if (version.current === generation) setLoading(false);
    });
    return () => { version.current += 1; };
  }, [datasetId, datasetRevision]);

  async function turnPage(after: number, nextIndex: number) {
    const generation = version.current;
    setLoading(true);
    setError("");
    try {
      const result = await api<DatasetPage>(`/datasets/${datasetId}/rows/?limit=25&after=${after}`);
      if (generation !== version.current) return;
      setPage(result);
      setCursors((values) => [...values.slice(0, nextIndex), after]);
      setPageIndex(nextIndex);
    } catch (err) {
      if (generation === version.current) setError(err instanceof Error ? err.message : "Could not load page.");
    } finally {
      if (generation === version.current) setLoading(false);
    }
  }

  async function replaceText(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const job = await api<Job>(`/datasets/${datasetId}/replace/`, { column, find, replacement });
      onJob(job);
    } catch (err) {
      setError(submissionError(err, onJob));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card dataset-card" aria-label={view === "datasets" ? "Dataset workspace" : "Transformation workspace"}>
      <div className="dataset-content">
        <div hidden={view !== "datasets"}><GalaxyExplorer datasetId={datasetId} active={visible && view === "datasets"} job={job}
          previewId={visible && view === "datasets" && previewOpen ? datasetId : null} revision={`${job?.id}:${job?.status}:${datasetRevision}`} onActivity={onActivity} manageRequest={manageRequest}
          onOpen={(id) => { setPreviewOpen(true); onSelect(id); setPreviewRequest(id); }}
          onTransform={(id) => { onSelect(id); window.location.hash = "/transform"; }}
          onChanged={(record) => { onDatasetChanged(); if (record.id === datasetId && record.lifecycle !== "ACTIVE") {setPreviewOpen(false);onSelect(null);} }} /></div>
        <FloatingPanel open={visible && previewOpen} inline={view === "transform"} onClose={()=>setPreviewOpen(false)} label={dataset?.source_key || "File data"} className="data-overlay">
        <div ref={previewRef} id="dataset-preview" hidden={view === "datasets" && !previewOpen}>
        {view === "datasets" && <div className="preview-heading">
          <div><h2>{dataset?.source_key || "Loading data"}</h2>{dataset && <span>{datasetLabel(dataset)} · {timeLabel(dataset.created_at)}<br />{dataset.row_count.toLocaleString()} rows · {dataset.columns.length} columns{dataset.sheet_name ? ` · ${dataset.sheet_name}` : ""}</span>}</div>
          <div className="preview-actions">{dataset && <><ExportPanel compact key={dataset.id} dataset={dataset} busy={busy} job={job} onJob={onJob} /><a className="primary-button" href="#/transform" onClick={()=>setPreviewOpen(false)}>Transform</a><button className="text-button" onClick={()=>{setPreviewOpen(false);setManageRequest({id:dataset.id,source_key:dataset.source_key});}}>Manage</button></>}
          <button className="text-button" onClick={()=>setPreviewOpen(false)}>Close</button></div>
        </div>}

        {error && <p className="dataset-error" role="alert">{error}</p>}
        {loading && <p role="status">Loading dataset preview…</p>}
        {!datasetId && <p className="dataset-empty">No dataset selected. <a href="#/sources">Import a file</a></p>}
        {dataset && page && (
          <>
            {view === "transform" && isNewDatasetResult(job, dataset) && <Reveal identity={dataset.id} className="dataset-arrival" active={view === "transform"}>
              <strong>{dataset.parent_id ? "New version saved" : "File imported"}</strong>
              <a className="text-button" href="#/datasets" onClick={() => setPreviewOpen(true)}>View result</a>
            </Reveal>}
            <div className="editor-filebar" hidden={view === "datasets"}>
            <div className="dataset-summary">
              <strong>{dataset.source_key}</strong>
              <span>{dataset.row_count.toLocaleString()} rows · {dataset.columns.length} columns</span>
              {dataset.sheet_name && <span>{dataset.sheet_name}</span>}
            </div>
            <a className="text-button" href="#/datasets">Change file</a>
            </div>
            <div hidden={view !== "datasets"}>
            {dataset.metadata.status_counts && <div className="result-summary" role="status">
              <strong>{datasetLabel(dataset)}: {Object.entries(dataset.metadata.status_counts).map(([status, count]) => `${count} ${status}`).join(" · ")}</strong>
              <p>Results are in {dataset.columns.slice(-2).map((entry) => entry.name).join(" and ")}.</p>
              {Object.entries(dataset.metadata.status_counts).some(([status, count]) => count > 0 && !["normalized", "classified"].includes(status)) &&
                <p>Some values need review. Check the result status column before downloading.</p>}
              <button type="button" className="secondary-button" onClick={() => {
                const table = document.querySelector<HTMLElement>('[aria-label="Scrollable dataset rows"]');
                table?.scrollTo({ left: table.scrollWidth, behavior: motionScrollBehavior() });
              }}>Show result columns</button>
            </div>}
            {dataset.metadata.column_stats && <details className="column-results"><summary>Results by column</summary>
              <table className="preview-table" aria-label="Regex results by column">
                <thead><tr><th>Column</th><th>Matched rows</th><th>Matches</th><th>Changed rows</th></tr></thead>
                <tbody>{Object.entries(dataset.metadata.column_stats).map(([key, stats]) => <tr key={key}>
                  <th scope="row">{dataset.columns.find((entry) => entry.key === key)?.name || key}</th>
                  <td>{stats.matched_rows}</td><td>{stats.match_count}</td><td>{stats.changed_rows}</td>
                </tr>)}</tbody>
              </table>
              <p className="preview-note">Overall row counts include each row once, even when several selected columns match.</p>
            </details>}
            <div className="table-scroll" tabIndex={0} aria-label="Scrollable dataset rows">
              <table className="preview-table">
                <thead><tr><th scope="col">Row</th>{dataset.columns.map((entry) => (
                  <th scope="col" key={entry.key}>{entry.name}</th>
                ))}</tr></thead>
                <tbody>{page.rows.map((row) => (
                  <tr key={row.row_number}><th scope="row">{row.row_number}</th>{row.cells.map((cell, index) => (
                    <td key={index}>{cell === null ? <span className="null-cell">null</span> : cell}</td>
                  ))}</tr>
                ))}</tbody>
              </table>
              {page.rows.length === 0 && <p className="dataset-empty">This dataset has a header but no data rows.</p>}
            </div>
            {(pageIndex > 0 || page.next_cursor !== null) && <div className="dataset-pagination">
              <span>Page {pageIndex + 1}</span>
              <button className="secondary-button" disabled={loading || pageIndex === 0}
                onClick={() => void turnPage(cursors[pageIndex - 1], pageIndex - 1)}>Previous</button>
              <button className="secondary-button" disabled={loading || page.next_cursor === null}
                onClick={() => page.next_cursor !== null && void turnPage(page.next_cursor, pageIndex + 1)}>Next</button>
            </div>}

            </div>
            <div hidden={view !== "transform"}>
              <div className="tool-switcher" role="group" aria-label="Choose a transformation">
                {[ ["regex", "Regex"], ["ai", "Dates and categories"], ["text", "Replace text"]].map(([key, label]) => <button key={key} aria-pressed={tool === key} onClick={() => setTool(key)}>{label}</button>)}
              </div>
            <div hidden={tool !== "regex"}><RulePanel rows={page.rows} active={view === "transform" && tool === "regex"} dataset={dataset} busy={busy} job={job} onJob={onJob} />
            </div><div hidden={tool !== "ai"}><TransformPanel rows={page.rows} active={view === "transform" && tool === "ai"} dataset={dataset} busy={busy} job={job} onJob={onJob} />
            </div><div hidden={tool !== "text"}><div className="text-workspace transform-workflow"><form id="replace-text-form" className="replace-form" onSubmit={replaceText}>
              <div className="workflow-heading"><h3>Exact match</h3><p>Replace text in one column</p></div>
              <label>Column<select value={column} disabled={busy || submitting}
                onChange={(event) => setColumn(event.target.value)}>
                <option value="" disabled>Choose a column to replace</option>
                {dataset.columns.map((entry) => <option key={entry.key} value={entry.key}>{entry.name}</option>)}
              </select></label>
              <label>Find text<input value={find} required maxLength={256} disabled={busy || submitting}
                onChange={(event) => setFind(event.target.value)} placeholder="Exact text to find" /></label>
              <label>Replace with<input value={replacement} maxLength={256} disabled={busy || submitting}
                onChange={(event) => setReplacement(event.target.value)} placeholder="Leave blank to remove" /></label>
            </form><div className="workflow-preview text-preview">
              <div className="workflow-preview-heading"><h3>Preview</h3>
              <ActionSpark disabled={busy || submitting}><button form="replace-text-form" type="submit" className="primary-button" disabled={busy || submitting || !column || !find}>
                {busy || submitting ? "Applying" : "Apply replacement"}
              </button></ActionSpark>
              </div>
              {column && find && <p className="workflow-save-note">Sample preview shown below. Apply saves a new version of all {dataset.row_count.toLocaleString()} rows.</p>}
              {column && page.rows.slice(0, 5).some(row => (row.cells[dataset.columns.findIndex(c => c.key === column)]?.length || 0) >= page.preview_cell_limit) &&
                <p className="workflow-warning">Some values are shortened. Their replacement preview is unavailable here; Apply uses the complete value.</p>}
              <div className="workflow-sample" role="region" aria-label="Text replacement sample preview" tabIndex={0}>
              <LoomPreview active={view === "transform" && tool === "text"} ready={Boolean(column && find)} job={job?.kind === "REPLACE_TEXT" ? job : null} title={dataset.columns.find(c => c.key === column)?.name || "Your sample"} rows={column ? page.rows.slice(0, 5).map(row => {
              const before = row.cells[dataset.columns.findIndex(c => c.key === column)];
              const shortened = before !== null && before.length >= page.preview_cell_limit;
              return { id: String(row.row_number), label: `Row ${row.row_number}`, before, shortened,
                status: shortened ? "Shortened source" : undefined,
                after: shortened ? undefined : before === null || !find ? before : before.split(find).join(replacement) };
            }) : []} /></div></div></div></div></div>
          </>
        )}
        </div>
        </FloatingPanel>
      </div>
    </section>
  );
}
