import { WorkspaceSky } from "./WorkspaceSky";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, submissionError, ApiError } from "./api";
import type { FilePage, Job, S3File } from "./api";
import { AppearanceControls, ActionSpark } from "./motion";
import TaskMotion from "./TaskMotion";
import WorksheetPicker from "./WorksheetPicker";
import DatasetPanel from "./DatasetPanel";
import TaskHistory from "./TaskHistory";
import { readSaved, save, savedId } from "./listState";
import { jobLabels } from "./historyLabels";
import WorkspaceIcon from "./WorkspaceIcon";
import { pageFromHash, pages } from "./navigation";

const terminal = (job: Job) =>
  ["SUCCESS", "FAILED", "CANCELLED"].includes(job.status);
const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please retry.";
export default function App() {
  const [disconnecting, setDisconnecting] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [bucket, setBucket] = useState("");
  const [region, setRegion] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [connection, setConnection] = useState<string | null>(null);
  const [files, setFiles] = useState<S3File[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [sheetName, setSheetName] = useState("");
  const [datasetId, setDatasetId] = useState<string | null>(() => savedId("patternworks-selected-dataset"));
  const [prefix, setPrefix] = useState("");
  const [appliedPrefix, setAppliedPrefix] = useState("");
  const [loading, setLoading] = useState(false);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesLoaded, setFilesLoaded] = useState(false);
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [datasetRevision, setDatasetRevision] = useState(0);
  const [view, setView] = useState(() => pageFromHash(window.location.hash));
  const [openDatasetRequest, setOpenDatasetRequest] = useState<{ id: string; nonce: number } | null>(null);
  const [importSource, setImportSource] = useState<{ key: string; sheet: string } | null>(null);
  const [connectionState, setConnectionState] = useState({ expiresAt: "", issue: "", expired: false, attempt: 0 });
  const pageTitle = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const sync = () => setView(pageFromHash(window.location.hash));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => {
    document.title = `${pages[view].title} · Patternworks`;
    pageTitle.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [view]);
  const activeConnection = useRef(connection);
  activeConnection.current = connection;
  const generation = useRef(0);
  const finishedJob = useRef("");
  const filesSection = useRef<HTMLElement>(null);
  const datasetSection = useRef<HTMLDivElement>(null);
  const active = Boolean(job && !terminal(job));
  const restoreSelection = useRef(Boolean(datasetId));
  useEffect(() => { save("patternworks-selected-dataset", datasetId || ""); }, [datasetId]);

  function expireConnection(id: string) {
    if (activeConnection.current !== id) return;
    generation.current += 1; // Discard file responses started with the expired connection.
    activeConnection.current = null;
    setConnection(null); setFiles([]); setFilesLoaded(false); setFilesLoading(false);
    setSelected(""); setSheetName(""); setNextCursor(null); setPrefix(""); setAppliedPrefix("");
    setConnectionState((state) => ({ ...state, expiresAt: "", expired: true }));
  }

  useEffect(() => {
    if (!datasetRevision || !job || !terminal(job)) return;
    let alive = true;
    const id = job.id;
    api<Job>(`/jobs/${id}/`).then((updated) => {
      if (alive) setJob((current) => current?.id === id ? updated : current);
    }).catch(() => { /* History refresh can retry without interrupting the workspace. */ });
    return () => { alive = false; };
  }, [datasetRevision]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const version = generation.current;
    setRestoring(true);
    setConnectionState((state) => ({ ...state, issue: "" }));
    async function restore(attempt = 0) {
      try {
        const { connections } = await api<{ connections: { id: string; bucket: string; region: string; expires_at: string }[] }>("/connections/");
        if (!alive || generation.current !== version) return;
        const record = connections[0];
        if (record) {
          activeConnection.current = record.id;
          setConnection(record.id); setBucket(record.bucket); setRegion(record.region);
          setConnectionState((state) => ({ ...state, expiresAt: record.expires_at || "", expired: false, issue: "" }));
          save("patternworks-s3-expires", record.expires_at || "");
          void loadFiles(record.id);
        } else {
          if (activeConnection.current) expireConnection(activeConnection.current);
          const expired = Date.parse(readSaved("patternworks-s3-expires") || "") <= Date.now();
          setConnectionState((state) => ({ ...state, expiresAt: "", expired, issue: "" }));
          save("patternworks-s3-expires", "");
        }
        setRestoring(false);
      } catch {
        if (!alive || generation.current !== version) return;
        if (attempt < 2) {
          timer = setTimeout(() => void restore(attempt + 1), 1000 * (attempt + 1));
          return;
        }
        setConnectionState((state) => ({ ...state, issue: "Could not check your S3 connection. Try again." }));
        setRestoring(false);
      }
    }
    void restore();
    return () => { alive = false; clearTimeout(timer); };
  }, [connectionState.attempt]);

  useEffect(() => {
    if (!connection || !connectionState.expiresAt) return;
    const remaining = Date.parse(connectionState.expiresAt) - Date.now();
    if (!Number.isFinite(remaining)) return;
    const check = () => { if (Date.now() >= Date.parse(connectionState.expiresAt)) expireConnection(connection); };
    const timer = setTimeout(check, Math.max(0, remaining));
    window.addEventListener("focus", check);
    return () => { clearTimeout(timer); window.removeEventListener("focus", check); };
  }, [connection, connectionState.expiresAt]);

  useEffect(() => {
    if (!job || terminal(job)) return;
    const controller = new AbortController();
    const id = job.id;
    let timer: ReturnType<typeof setTimeout>;
    let disposed = false;
    const poll = async () => {
      try {
        const updated = await api<Job>(
          `/jobs/${id}/`,
          undefined,
          controller.signal,
        );
        if (disposed) return;
        setJob((current) => (current?.id === id ? updated : current));
        setPollError("");
        if (!terminal(updated)) timer = setTimeout(poll, 1000);
      } catch (err) {
        if (disposed) return;
        setPollError(`${message(err)} Retrying status check…`);
        timer = setTimeout(poll, 3000);
      }
    };
    timer = setTimeout(poll, 500);
    return () => {
      disposed = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [job?.id, job?.status]);

  useEffect(() => {
    let alive = true;
    api<{ jobs: Job[] }>("/jobs/?limit=1").then(({ jobs }) => {
      if (alive && jobs.length) setJob((current) => {
        if (current) return current;
        if (terminal(jobs[0])) finishedJob.current = jobs[0].id;
        return jobs[0];
      });
    }).catch(() => { /* A new task can still be submitted if history is unavailable. */ });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (job && !terminal(job)) restoreSelection.current = false;
    if (!job || !terminal(job) || finishedJob.current === job.id) return;
    finishedJob.current = job.id;
    if (job.status === "FAILED") {
      setError(job.error_message);
      if (job.error_code === "CONNECTION_EXPIRED" && job.connection_id
          && ["IMPORT_DATASET", "CONNECT_S3", "LIST_WORKSHEETS"].includes(job.kind)) expireConnection(job.connection_id);
    }
    if (
      job.status === "SUCCESS" &&
      job.kind === "CONNECT_S3" &&
      job.connection_id
    ) {
      setRestoring(true);
      setConnectionState((state) => ({ ...state, attempt: state.attempt + 1 }));
    }
    // A saved library selection wins over the restored latest completed job.
    // Newly submitted/running tasks still open their output on completion.
    const keepSelection = restoreSelection.current;
    restoreSelection.current = false;
    if (job.status === "SUCCESS" && job.dataset_id && !keepSelection) {
      setDatasetId(job.dataset_id);
      if (job.kind === "IMPORT_DATASET") {
        setOpenDatasetRequest((previous) => ({ id: job.dataset_id!, nonce: (previous?.nonce || 0) + 1 }));
        window.location.hash = "/datasets"; window.scrollTo({ top: 0 });
      }

    }
    if (!keepSelection && job.status === "SUCCESS" && ["GENERATE_RULE", "PREVIEW_TRANSFORM"].includes(job.kind) && typeof job.result.source_dataset_id === "string") {
      setDatasetId(job.result.source_dataset_id);
    }
  }, [job]);

  async function loadFiles(
    id: string,
    cursor = "",
    append = false,
    requestedPrefix = "",
  ) {
    const version = generation.current;
    setFilesLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({ prefix: requestedPrefix, cursor });
      const page = await api<FilePage>(`/connections/${id}/files/?${query}`);
      if (generation.current !== version) return;
      setFiles((current) =>
        append ? [...current, ...page.files] : page.files,
      );
      setAppliedPrefix(requestedPrefix);
      setNextCursor(page.next_cursor);
      setFilesLoaded(true);
    } catch (err) {
      if (generation.current === version) {
        setError(message(err));
        if (err instanceof ApiError && err.status === 410) {
          expireConnection(id);
        }
      }
    } finally {
      if (generation.current === version) setFilesLoading(false);
    }
  }

  async function connect(event: FormEvent) {
    event.preventDefault();
    generation.current += 1;
    setLoading(true);
    setError("");
    setPollError("");
    setConnection(null);
    setFiles([]);
    setFilesLoaded(false);
    setSelected("");
    setNextCursor(null);
    setPrefix("");
    setAppliedPrefix("");
    try {
      const next = await api<Job>("/connections/", {
        access_key_id: accessKey,
        secret_access_key: secretKey,
        session_token: sessionToken,
        bucket,
        region,
      });
      setJob(next);
      // Credentials remain in the form only until accepted; never persist them in browser storage.
      setAccessKey("");
      setSecretKey("");
      setSessionToken("");
    } catch (err) {
      setError(submissionError(err, setJob));
    } finally {
      setLoading(false);
    }
  }

  async function disconnect() {
    if (active || loading) return;
    setDisconnecting(true); setError("");
    try {
      await api("/connections/disconnect/", {});
      if (connection) expireConnection(connection);
      save("patternworks-s3-expires", "");
      setConnectionState((state) => ({ ...state, expiresAt: "", expired: false, issue: "" }));
      setAccessKey(""); setSecretKey(""); setSessionToken("");
      setJob(null); setPollError("");
    } catch (err) { setError(message(err)); }
    finally { setDisconnecting(false); }
  }

  async function cancel() {
    if (!job) return;
    try {
      setJob(await api<Job>(`/jobs/${job.id}/cancel/`, {}));
    } catch (err) {
      setError(message(err));
    }
  }

  async function retryJob() {
    if (!job) return;
    setLoading(true); setError(""); setPollError("");
    try { setJob(await api<Job>(`/jobs/${job.id}/retry/`, {})); }
    catch (err) { setError(submissionError(err, setJob)); }
    finally { setLoading(false); }
  }

  async function importFile() {
    if (!connection || !selected || (!selected.toLowerCase().endsWith(".csv") && !sheetName)) return;
    const version = generation.current;
    setLoading(true);
    setError("");
    setPollError("");
    try {
      const next = await api<Job>("/datasets/", {
        connection_id: connection, key: selected, sheet_name: sheetName,
      });
      if (generation.current === version) setJob(next);
      if (generation.current === version) setImportSource({ key: selected, sheet: sheetName });
    } catch (err) {
      if (generation.current !== version) return;
      setError(submissionError(err, setJob));
      if (err instanceof ApiError && err.status === 410) expireConnection(connection);
    } finally {
      setLoading(false);
    }
  }

  const [activityOpen, setActivityOpen] = useState(false);
  function openDataset(id: string) {
    setDatasetId(id);
    setOpenDatasetRequest((previous) => ({ id, nonce: (previous?.nonce || 0) + 1 }));
    setActivityOpen(false);
    window.location.hash = "/datasets";
  }
  const activityPanel = useRef<HTMLDivElement>(null);
  const previousView = useRef<"sources" | "datasets" | "transform">("datasets");
  useEffect(() => {
    if (view === "history") { setActivityOpen(true); window.location.hash = `/${previousView.current}`; }
    else previousView.current = view;
  }, [view]);
  useEffect(() => {
    if (!activityOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    activityPanel.current?.querySelector<HTMLButtonElement>(".drawer-heading button")?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActivityOpen(false);
      if (event.key === "Tab") {
        const controls = Array.from(activityPanel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, select, [tabindex="0"]') || []).filter(el => el.getClientRects().length);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener("keydown", escape);
    return () => { window.removeEventListener("keydown", escape); previousFocus?.focus(); };
  }, [activityOpen]);

  return (
    <div className={`shell cosmic-shell ${view === "datasets" ? "universe-shell" : ""}`}>
      <WorkspaceSky active library={view === "datasets"} />
      <a className="skip-link" href="#workspace" onClick={(event) => { event.preventDefault(); pageTitle.current?.focus(); }}>Skip to workspace</a>
      <header className="shell-header">
        <a className="brand" href="#/sources" aria-label="Patternworks home"><span className="brand-symbol" aria-hidden="true" />Patternworks</a>
        <nav className="workspace-nav" aria-label="Workspace pages">
          {Object.entries(pages).filter(([key]) => key !== "history").map(([key, page]) => <a key={key} href={`#/${key}`} aria-current={view === key ? "page" : undefined}>{page.title}</a>)}
          <button type="button" className="nav-activity" aria-expanded={activityOpen} aria-controls="workspace-activity" onClick={() => setActivityOpen(true)}>Tasks{active && <span className="task-running-dot" aria-label="Task in progress" />}</button>
        </nav>
        <AppearanceControls />
      </header>
      <main id="workspace">
        <div className="content">
          <div className={`route-heading route-${view}`}>
            <h1 ref={pageTitle} tabIndex={-1}>{view === "sources" ? restoring || connectionState.issue ? "Sources" : connection ? "Import a file" : "Connect your data" : view === "transform" ? "Transform" : pages[view].title}</h1>
          </div>
          {error && !(view === "transform" && job?.kind === "GENERATE_RULE" && job.status === "FAILED"
            && job.dataset_id === datasetId && error === job.error_message) && (
            <div className="alert" role="alert">
              <strong>We couldn’t complete that request.</strong>
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                ×
              </button>
            </div>
          )}
          <div hidden={view !== "sources"}>
          <div className={`source-flow ${connection ? "source-connected" : "source-login"}`} aria-busy={restoring || disconnecting}>
            {restoring && <p className="guidance" role="status">Checking your connection</p>}
            {!restoring && !connection && connectionState.issue && <section className="card connection-card">
              <p className="guidance" role="alert">{connectionState.issue}</p>
              <button className="primary-button" onClick={() => setConnectionState((state) => ({ ...state, attempt: state.attempt + 1 }))}>Retry connection</button>
            </section>}
            {!restoring && !connection && !connectionState.issue && (
            <section className="card connection-card">
              <div className="card-heading">
                <span className="section-icon"><WorkspaceIcon name="source" /></span>
                <div>
                  <h2>Amazon S3</h2>
                  <p className="guidance">{connectionState.expired ? "Your S3 connection expired. Reconnect to browse your bucket. Your imported files are still available in Datasets." : "Use read-only credentials to connect your bucket."}</p>
                </div>
                {connection && (
                  <span className="connected-label">Connected</span>
                )}
              </div>
              <form className="connection-form" onSubmit={connect} autoComplete="off">
                <div className="connection-fields">
                <div className="connection-field">
                <label htmlFor="bucket">Bucket name</label>
                <input
                  id="bucket"
                  placeholder="e.g. my-data-bucket"
                  value={bucket}
                  onChange={(e) => setBucket(e.target.value)}
                  required
                  maxLength={63}
                  disabled={active || loading}
                />
                </div>
                <div className="connection-field">
                  <label htmlFor="region">AWS region <span className="field-optional">optional</span></label>
                  <input id="region" placeholder="e.g. ap-southeast-2" value={region}
                    onChange={(e) => setRegion(e.target.value)} maxLength={63} disabled={active || loading} />
                </div>
                <div className="connection-field">
                <label htmlFor="access">AWS Access Key ID</label>
                <input
                  id="access"
                  type="password"
                  autoComplete="off"
                  placeholder="Enter your access key"
                  value={accessKey}
                  onChange={(e) => setAccessKey(e.target.value)}
                  required
                  maxLength={128}
                  disabled={active || loading}
                />
                </div>
                <div className="connection-field">
                <label htmlFor="secret">AWS Secret Access Key</label>
                <input
                  id="secret"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter your secret key"
                  value={secretKey}
                  onChange={(e) => setSecretKey(e.target.value)}
                  required
                  maxLength={256}
                  disabled={active || loading}
                />
                </div>
                </div>
                <details>
                  <summary>Session token</summary>
                  <label htmlFor="token">Session token</label>
                  <input
                    id="token"
                    type="password"
                    value={sessionToken}
                    onChange={(e) => setSessionToken(e.target.value)}
                    autoComplete="off"
                    maxLength={8192}
                    disabled={active || loading}
                  />
                </details>
                <ActionSpark disabled={loading || active}><button
                  className="primary-button"
                  type="submit"
                  disabled={loading || active}
                >
                  {loading
                    ? "Submitting…"
                    : active
                      ? "Task in progress…"
                      : "Connect bucket"}
                </button></ActionSpark>
                {active && job?.kind === "CONNECT_S3" && <div className="connection-feedback" role="status"><TaskMotion job={job} /><span>Checking access…</span><button type="button" className="text-button" onClick={() => void cancel()}>Cancel</button></div>}
              </form>
            </section>)}
            {!restoring && connection && <div className="right-column">
              <section className="card files-card" ref={filesSection}>
                <div className="card-heading">
                  <span className="section-icon"><WorkspaceIcon name="table" /></span>
                  <div>
                    <h2>{bucket}</h2>
                    <p className="guidance">Select a CSV or Excel file to preview.</p>
                  </div>
                  <button className="secondary-button disconnect-button" disabled={disconnecting || active || loading} onClick={() => void disconnect()}>{disconnecting ? "Disconnecting…" : "Disconnect S3"}</button>
                </div>
                {connection && (
                  <form
                    className="prefix-search"
                    onSubmit={(e) => {
                      e.preventDefault();
                      setSelected("");
                      void loadFiles(connection, "", false, prefix);
                    }}
                  >
                    <input
                      aria-label="S3 folder or prefix"
                      placeholder="Folder or file prefix"
                      value={prefix}
                      onChange={(e) => setPrefix(e.target.value)}
                    />
                    <button
                      className="secondary-button"
                      disabled={filesLoading}
                    >
                      Find files
                    </button>
                  </form>
                )}
                {files.length > 0 ? (
                  <div className="file-list" aria-label="S3 files">
                    {files.map((file) => (
                      <button
                        className={`file-row ${selected === file.key ? "selected" : ""}`}
                        key={file.key}
                        onClick={() => { if (selected !== file.key) { setSelected(file.key); setSheetName(""); } }}
                        disabled={active || loading}
                        aria-pressed={selected === file.key}
                      >
                        <span className="file-icon">
                          {file.format.toUpperCase()}
                        </span>
                        <span className="file-description">
                          <strong>{file.key}</strong>

                        </span>
                        <span className="radio-indicator">
                          {selected === file.key ? "●" : "○"}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-illustration">
                      <span className="empty-file empty-file-back" aria-hidden="true">XLSX</span>
                      <span className="empty-file empty-file-front" aria-hidden="true"><WorkspaceIcon name="table" /><small>CSV</small></span>
                      <span className="empty-file-plus" aria-hidden="true">+</span>
                    </div>
                    <h3>
                      {filesLoading
                        ? "Looking for your files…"
                        : connection && filesLoaded
                          ? "No supported files on this page"
                          : "A fresh start for your data"}
                    </h3>
                    {!filesLoading && connection && filesLoaded && <p>
                      Try another prefix, or continue to the next page if available.
                    </p>}
                  </div>
                )}
                {nextCursor && <div className="files-footer">
                  {connection && nextCursor && (
                    <button
                      className="text-button"
                      disabled={filesLoading}
                      onClick={() =>
                        void loadFiles(
                          connection,
                          nextCursor,
                          true,
                          appliedPrefix,
                        )
                      }
                    >
                      {filesLoading ? "Loading…" : "Load next page"}
                    </button>
                  )}
                </div>}
                {selected && (
                  <div className="import-actions">
                    <strong>{selected}</strong>
                    {!selected.toLowerCase().endsWith(".csv") && connection && (
                      <WorksheetPicker key={`${connection}:${selected}`} connection={connection} sourceKey={selected}
                        value={sheetName} disabled={loading || active} onChange={setSheetName} onExpired={expireConnection} onJob={setJob} />
                    )}
                    <div className="import-command">
                    <ActionSpark disabled={loading || active}><button className="primary-button" disabled={loading || active || (!selected.toLowerCase().endsWith(".csv") && !sheetName)} onClick={() => void importFile()}>
                      {loading ? "Submitting" : active ? job?.kind === "IMPORT_DATASET" ? "Importing" : "Task in progress" : "Import file"}
                    </button></ActionSpark>
                    {job?.kind === "IMPORT_DATASET" && job.connection_id === connection && importSource?.key === selected && importSource.sheet === sheetName && <div className="import-status" role="status">
                      <TaskMotion job={job} label="File import progress" />
                      {pollError && <span role="alert">{pollError}</span>}
                      <span>{active ? job.stage : job.status === "SUCCESS" ? "Import complete" : job.status.toLowerCase()}</span>
                      {active && <button className="text-button" onClick={() => void cancel()}>Cancel import</button>}
                      {job.status === "SUCCESS" && job.dataset_id && job.dataset_available !== false
                        ? <button className="text-button" onClick={() => openDataset(job.dataset_id!)}>View result</button>
                        : <a href="#/history">View task</a>}
                    </div>}
                    </div>
                  </div>
                )}
              </section>

            </div>}
          </div>
          </div>
          {activityOpen && <button className="activity-backdrop" aria-label="Close tasks" onClick={() => setActivityOpen(false)} />}
          <div ref={activityPanel} id="workspace-activity" className="activity-drawer" hidden={!activityOpen} role="dialog" aria-modal="true" aria-label="Workspace activity">
            <div className="drawer-heading"><h2>Tasks</h2><button className="secondary-button" onClick={() => setActivityOpen(false)}>Close</button></div>
              {job && job.status !== "SUCCESS" && <section className="card activity-card" aria-live="polite">
                <div className="activity-heading">
                  <h2>{job ? jobLabels[job.kind] : "No tasks yet"}</h2>
                  {job && (
                    <span
                      className={`status-pill status-${job.status.toLowerCase()}`}
                    >
                      {job.status === "RUNNING" ? "In progress" : job.status === "QUEUED" ? "Queued" : job.status === "CANCELLED" ? "Cancelled" : "Failed"}
                    </span>
                  )}
                </div>
                {job ? (
                  <>
                    {active && <><p className="task-stage">{job.stage}</p><TaskMotion job={job} /></>}
                    <div className="task-meta">
                      {active && (
                        <button className="text-button" onClick={cancel}>
                          Cancel task
                        </button>
                      )}
                    </div>
                    {job.retry_allowed && <button className="secondary-button" disabled={loading} onClick={() => void retryJob()}>Retry</button>}
                    {job.status === "FAILED" && <p className="dataset-error">{job.error_message}</p>}
                    {!job.retry_allowed && job.retry_unavailable_reason && <p className="preview-note">{job.retry_unavailable_reason}</p>}
                    {pollError && <p className="poll-error">{pollError}</p>}
                  </>
                ) : (
                  <p className="activity-empty">
                    Import a file to get started.
                  </p>
                )}
              </section>}
          <TaskHistory job={job} busy={loading || active} datasetRevision={datasetRevision}
            onChanged={(next) => setJob((current) => current?.id === next.id ? next : current)}
            onNewJob={(next) => { setJob(next); setError(""); setPollError(""); }}
            onOpenDataset={openDataset} />
          </div>
          <div ref={datasetSection} hidden={view !== "datasets" && view !== "transform"}>
            <DatasetPanel openRequest={openDatasetRequest} visible={view === "datasets" || view === "transform"} onActivity={() => setActivityOpen(true)} view={view === "transform" ? "transform" : "datasets"} datasetId={datasetId} datasetRevision={datasetRevision} onDatasetChanged={() => setDatasetRevision((value) => value + 1)} onSelect={setDatasetId} onJob={(next) => { setJob(next); setError(""); setPollError(""); }} busy={loading || active} job={job} />
          </div>
        </div>
      </main>
    </div>
  );
}
