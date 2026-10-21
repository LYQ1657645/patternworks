import { useEffect, useRef, useState } from "react";
import TaskMotion from "./TaskMotion";
import { Reveal } from "./motion";
import { api, submissionError } from "./api";
import type { Dataset, Job } from "./api";
import "./taskWorkflow.css";

type Props = { dataset: Dataset; busy: boolean; job: Job | null; onJob: (job: Job) => void; compact?: boolean };

export default function ExportPanel({ dataset, busy, job, onJob, compact = false }: Props) {
  const [record, setRecord] = useState<Job | null>(null);
  const [available, setAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const currentExportId = job?.kind === "EXPORT_CSV" && job.dataset_id === dataset.id ? job.id : null;

  useEffect(() => {
    const version = ++generation.current;
    setRecord(null); setAvailable(false); setLoading(true); setError("");
    api<{ job: Job | null; download_available: boolean }>(`/datasets/${dataset.id}/export/`)
      .then((result) => {
        if (generation.current !== version) return;
        setRecord(result.job); setAvailable(result.download_available);
      })
      .catch((err) => { if (generation.current === version) setError(err instanceof Error ? err.message : "Could not check CSV export."); })
      .finally(() => { if (generation.current === version) setLoading(false); });
    return () => { generation.current += 1; };
  }, [dataset.id, currentExportId]);

  useEffect(() => {
    if (!record || !["QUEUED", "RUNNING"].includes(record.status)) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const id = record.id;
    const poll = async () => {
      try {
        const updated = await api<Job>(`/jobs/${id}/`);
        if (disposed) return;
        setRecord(updated); setAvailable(updated.status === "SUCCESS"); setError("");
        if (["QUEUED", "RUNNING"].includes(updated.status)) timer = setTimeout(poll, 1000);
      } catch {
        if (disposed) return;
        setError("Could not check CSV progress. Retrying…"); timer = setTimeout(poll, 3000);
      }
    };
    timer = setTimeout(poll, 500);
    return () => { disposed = true; clearTimeout(timer); };
  }, [record?.id, record?.status]);

  async function generate() {
    const version = generation.current;
    setSubmitting(true); setError("");
    try {
      const result = await api<Job>(`/datasets/${dataset.id}/export/`, {});
      if (generation.current !== version) return;
      setRecord(result); setAvailable(result.status === "SUCCESS"); onJob(result);
    } catch (err) {
      if (generation.current === version) setError(submissionError(err, onJob));
    } finally {
      setSubmitting(false);
    }
  }

  const pending = record && ["QUEUED", "RUNNING"].includes(record.status);
  return <section className={`export-panel export-workflow${compact ? " export-compact" : ""}`} aria-label="Export dataset">
    {!compact && <div className="export-summary"><h3>CSV file</h3><p>{pending ? "Preparing your download" : available ? "Ready to download" : `All ${dataset.row_count.toLocaleString()} rows and columns`}</p></div>}
    <div className="export-action-row">
    {pending && <div className="export-progress" role="status">{compact && <span>Preparing CSV</span>}<TaskMotion job={record} label="CSV export progress" /></div>}
    {available && record ? <Reveal identity={record.id}><a className={`${compact ? "secondary-button" : "primary-button"} export-download`} href={`/api/jobs/${record.id}/download/`} download>Download CSV</a></Reveal>
      : !pending && <button className="secondary-button" disabled={loading || busy || submitting} onClick={() => void generate()}>
        {loading ? "Checking" : submitting ? "Preparing" : "Export CSV"}
      </button>}
    <details className="preview-note export-notes"><summary>{compact ? "Excel tips" : "Opening in Excel"}</summary><p>Import columns as Text to preserve leading zeros and prevent formula-like values from running as formulas. Empty and null values both download as blank cells.</p></details>
    </div>
    {pending && !compact && <p className="export-help" role="status">You can cancel from Tasks</p>}
    {error && <p className="export-feedback" role="alert">{error}</p>}
    {record && ["FAILED", "CANCELLED"].includes(record.status) && <p className="export-feedback" role="status">{record.status === "CANCELLED" ? "Export cancelled. Your dataset is unchanged." : record.error_message || "CSV export failed. Try again."}</p>}
  </section>;
}
