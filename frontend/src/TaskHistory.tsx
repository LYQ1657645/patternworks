import { useEffect, useRef, useState } from "react";
import TaskMotion from "./TaskMotion";
import { motionScrollBehavior } from "./motion";
import { api, ApiError, submissionError } from "./api";
import type { Job } from "./api";
import { jobDataset, jobLabels, timeLabel } from "./historyLabels";
import { save, savedId } from "./listState";
import { useCursorList } from "./useCursorList";
import "./taskWorkflow.css";

type Props = { job: Job | null; busy: boolean; onChanged: (job: Job) => void;
  onNewJob: (job: Job) => void; onOpenDataset: (id: string) => void; datasetRevision: number };

const actions: Record<Job["kind"], string> = {
  LIST_WORKSHEETS: "Read worksheets", DIAGNOSTIC: "System check", CONNECT_S3: "Connect storage",
  IMPORT_DATASET: "Import file", REPLACE_TEXT: "Replace text", GENERATE_RULE: "Generate regex",
  APPLY_RULE: "Apply regex", PREVIEW_TRANSFORM: "Preview transformation",
  APPLY_TRANSFORM: "Apply transformation", EXPORT_CSV: "Export CSV",
};
const statuses: Record<Job["status"], string> = {
  QUEUED: "Waiting", RUNNING: "In progress", SUCCESS: "Complete", FAILED: "Failed", CANCELLED: "Cancelled",
};
const fileName = (entry: Job) => typeof entry.result?.source_key === "string" ? entry.result.source_key : null;

export default function TaskHistory({ job, busy, onChanged, onNewJob, onOpenDataset, datasetRevision }: Props) {
  const list = useCursorList<Job>("jobs", { status: "", kind: "" }, `${job?.id}:${job?.status}:${datasetRevision}`);
  const [selectedId, setSelectedId] = useState<string | null>(() => savedId("patternworks-history-job"));
  const [detail, setDetail] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [acting, setActing] = useState(false);
  const [detailRevision, setDetailRevision] = useState(0);
  const detailPanel = useRef<HTMLElement>(null);
  const scrollRequest = useRef<string | null>(null);
  useEffect(() => { save("patternworks-history-job", selectedId || ""); }, [selectedId]);
  useEffect(() => {
    setDetail(null);
    if (!selectedId) return;
    setError("");
    let alive = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api<Job>(`/jobs/${selectedId}/`, undefined, controller.signal);
        if (!alive) return;
        setDetail(result); setError("");
        if (["QUEUED", "RUNNING"].includes(result.status)) timer = setTimeout(poll, 1000);
      } catch (err) {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 404) { setSelectedId(null); setError("This task is no longer available."); }
        else { setError("Could not load task details. Retrying…"); timer = setTimeout(poll, 3000); }
      }
    };
    void poll();
    return () => { alive = false; clearTimeout(timer); controller.abort(); };
  }, [selectedId, job?.id, job?.status, datasetRevision, detailRevision]);
  useEffect(() => {
    if (detail?.id !== selectedId || scrollRequest.current !== detail?.id || !detailPanel.current?.getClientRects().length) return;
    detailPanel.current.scrollIntoView({ behavior: motionScrollBehavior(), block: "nearest" });
    scrollRequest.current = null;
  }, [detail?.id, selectedId]);

  function selectTask(id: string) {
    scrollRequest.current = id;
    setSelectedId(id);
    // Selecting the already-open row should bring its detail back into view too.
    if (detail?.id === id && detailPanel.current?.getClientRects().length) {
      detailPanel.current.scrollIntoView({ behavior: motionScrollBehavior(), block: "nearest" });
      scrollRequest.current = null;
    }
  }

  function refreshHistory() {
    list.refresh(); setDetailRevision((value) => value + 1);
  }

  async function act(action: "cancel" | "retry") {
    if (!detail) return;
    const id = detail.id;
    setActing(true); setError("");
    try {
      const result = await api<Job>(`/jobs/${id}/${action}/`, {});
      if (action === "retry") { selectTask(result.id); onNewJob(result); }
      else { setDetail(result); onChanged(result); }
      list.refresh();
    } catch (err) {
      setError(submissionError(err, (next) => { selectTask(next.id); onNewJob(next); }));
    } finally { setActing(false); }
  }
  const resultId = detail ? jobDataset(detail) : null;
  const filtered = Boolean(list.state.filters.status || list.state.filters.kind);
  const inProgress = detail && ["QUEUED", "RUNNING"].includes(detail.status);
  return <section className="card history-card task-history" aria-label="Task history">
    <div className="list-heading"><h2>Recent tasks</h2>
      <button className="text-button" disabled={list.loading} onClick={refreshHistory}>Refresh</button></div>
    <details className="task-filters" open={filtered || undefined}><summary>{filtered ? "Filters applied" : "Filter tasks"}</summary><div className="list-filters">
      <label>Status<select value={list.state.filters.status} onChange={(event) => list.filter({ status: event.target.value })}>
        <option value="">All statuses</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Action<select value={list.state.filters.kind} onChange={(event) => list.filter({ kind: event.target.value })}>
        <option value="">All actions</option>{Object.entries(actions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      {filtered && <button className="text-button" onClick={() => list.filter({ status: "", kind: "" })}>Clear</button>}
    </div></details>
    {list.error && <p role="alert">{list.error} Select Refresh to try again.</p>}
    {list.notice && <p role="status">{list.notice}</p>}
    {list.loading ? <p role="status">Loading tasks</p> : <>
      <ul className="record-list" aria-label="Historical tasks">{list.items.map((entry) => <li key={entry.id} className={entry.id === selectedId ? "selected-record" : ""}>
        <button className="task-record" disabled={acting} aria-pressed={entry.id === selectedId} onClick={() => selectTask(entry.id)}>
          <span className="task-record-name"><strong>{actions[entry.kind] || jobLabels[entry.kind]}</strong>{fileName(entry) && <span>{fileName(entry)}</span>}<time>{timeLabel(entry.created_at)}</time></span>
          <span className={`task-record-status status-${entry.status.toLowerCase()}`}>{statuses[entry.status]}</span>
        </button>
      </li>)}</ul>
      {!list.items.length && <p>{filtered ? "No matching tasks" : "Your tasks will appear here"}</p>}
    </>}
    {(list.next || list.state.page > 0) && <nav className="list-pagination" aria-label="Task history pages"><span>Page {list.state.page + 1}</span>
      <button className="secondary-button" disabled={list.loading || list.state.page === 0} onClick={list.previous}>Previous</button>
      <button className="secondary-button" disabled={list.loading || !list.next} onClick={list.advance}>Next</button>
    </nav>}
    {error && <p role="alert">{error}</p>}
    {selectedId && !detail && !error && <p role="status">Loading task</p>}
    {detail && <section ref={detailPanel} className="history-detail" aria-label="Historical task details">
      <div className="list-heading"><h3>{actions[detail.kind] || jobLabels[detail.kind]}</h3><button className="text-button" disabled={acting} onClick={() => setSelectedId(null)}>Close</button></div>
      {fileName(detail) && <p className="task-file-name">{fileName(detail)}</p>}
      <p className={`task-detail-status status-${detail.status.toLowerCase()}`}>{statuses[detail.status]}</p>
      {inProgress && <><TaskMotion job={detail} label="Historical task progress" />{/cancel/i.test(detail.stage) && <p>Cancellation requested</p>}</>}
      {detail.error_message && <p role="alert">{detail.error_message}</p>}
      <div className="history-actions">
        {resultId && <button className="secondary-button" onClick={() => onOpenDataset(resultId)}>View data</button>}
        {detail.kind === "EXPORT_CSV" && detail.status === "SUCCESS" && detail.dataset_available !== false && <a className="primary-button export-download" href={`/api/jobs/${detail.id}/download/`} download>Download CSV</a>}
        {detail.dataset_available === false && detail.dataset_id && <p>This version is unavailable. Check Trash in the Library to restore it.</p>}
        {inProgress && <button className="secondary-button" disabled={acting} onClick={() => void act("cancel")}>Cancel</button>}
        {detail.retry_allowed && <button className="secondary-button" disabled={busy || acting} onClick={() => void act("retry")}>Retry</button>}
        {!detail.retry_allowed && detail.retry_unavailable_reason && <p>{detail.retry_unavailable_reason}</p>}
      </div>
      <details className="task-details"><summary>Details</summary>
        <p>Created {timeLabel(detail.created_at)}{detail.finished_at && <><br />Finished {timeLabel(detail.finished_at)}</>}</p>
        <p>Task ID <code>{detail.id}</code></p>
      </details>
    </section>}

  </section>;
}
