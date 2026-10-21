import { useEffect, useState } from "react";
import { api, ApiError, submissionError } from "./api";
import type { Job } from "./api";

type Props = { connection: string; sourceKey: string; value: string; disabled: boolean;
  onChange: (name: string) => void; onExpired: (id: string) => void; onJob: (job: Job) => void };

export default function WorksheetPicker({ connection, sourceKey, value, disabled, onChange, onExpired, onJob }: Props) {
  const [names, setNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [task, setTask] = useState<Job | null>(null);
  const [notice, setNotice] = useState("");
  const [cancelling, setCancelling] = useState(false);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    setLoading(true); setNames([]); setTask(null); setError(""); setNotice(""); onChange("");
    const accept = (next: Job) => {
      if (!alive) return;
      setTask(next); setNotice("");
      if (next.status === "SUCCESS") {
        const tabs = next.result.sheet_names;
        if (next.result.source_key !== sourceKey || !Array.isArray(tabs) || !tabs.length || !tabs.every(x => typeof x === "string")) {
          setError("Could not read worksheet names. Reload worksheets to try again.");
        } else { setNames(tabs as string[]); onChange(tabs[0]); }
        setLoading(false);
      } else if (["FAILED", "CANCELLED"].includes(next.status)) {
        setLoading(false);
        setError(next.status === "CANCELLED" ? "Worksheet reading was cancelled." : next.error_message);
        if (next.error_code === "CONNECTION_EXPIRED") onExpired(connection);
      } else timer = setTimeout(() => void poll(next.id), 1000);
    };
    const poll = async (id: string) => {
      try { accept(await api<Job>(`/jobs/${id}/`, undefined, controller.signal)); }
      catch (err) {
        if (!alive) return;
        if (err instanceof ApiError && [403, 404].includes(err.status)) {
          setLoading(false); setError("This task is no longer available in this session. Reconnect or reload worksheets."); return;
        }
        setNotice("Connection interrupted. Rechecking the same task…");
        timer = setTimeout(() => void poll(id), 3000);
      }
    };
    api<Job>(`/connections/${connection}/worksheets/`, { key: sourceKey })
      .then((next) => { if (alive) { onJob(next); accept(next); } })
      .catch((err) => {
        if (!alive) return;
        setLoading(false); setError(submissionError(err, onJob));
        if (err instanceof ApiError && err.status === 410) onExpired(connection);
      });
    return () => { alive = false; clearTimeout(timer); controller.abort(); };
  }, [connection, sourceKey, attempt]);
  async function cancel() {
    if (!task) return;
    setCancelling(true);
    try { onJob(await api<Job>(`/jobs/${task.id}/cancel/`, {})); }
    catch (err) { setNotice(err instanceof Error ? err.message : "Could not cancel. Try again."); }
    finally { setCancelling(false); }
  }
  return <div>
    <label>Worksheet<select aria-label="Worksheet" value={value} disabled={disabled || loading || !!error}
      onChange={(event) => onChange(event.target.value)}>
      {!value && <option value="">{loading ? "Reading worksheets…" : "Choose a worksheet"}</option>}
      {names.map((name) => <option key={name} value={name}>{name}</option>)}
    </select></label>
    {loading && <p role="status">{task ? `${task.stage} · ${task.progress}%` : "Submitting worksheet task…"}</p>}
    {loading && task && <button type="button" className="secondary-button" disabled={cancelling} onClick={() => void cancel()}>Cancel worksheet reading</button>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error} <button type="button" disabled={disabled} onClick={() => setAttempt(attempt + 1)}>Reload worksheets</button></p>}
  </div>;
}
