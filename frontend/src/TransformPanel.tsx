import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import LoomPreview from "./LoomPreview";
import { ActionSpark, motionScrollBehavior } from "./motion";
import type { DatasetPage } from "./api";
import { api, submissionError } from "./api";
import type { Dataset, Job, LLMTransformation } from "./api";
import "./transformWorkflow.css";

type Props = { dataset: Dataset; busy: boolean; job: Job | null; onJob: (job: Job) => void; rows?: DatasetPage["rows"]; active?: boolean };

export default function TransformPanel({ dataset, busy, job, onJob, rows = [], active = true }: Props) {
  const [kind, setKind] = useState<"DATE" | "CATEGORY">("DATE");
  const [column, setColumn] = useState("");
  const [dateOrder, setDateOrder] = useState("REJECT");
  const [labelsText, setLabelsText] = useState("");
  const [fallback, setFallback] = useState("");
  const [instruction, setInstruction] = useState("");
  const [consent, setConsent] = useState(false);
  const [record, setRecord] = useState<LLMTransformation | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const version = useRef(0);
  const panel = useRef<HTMLElement>(null);
  const draftEdited = useRef(false);
  const [requestBudget, setRequestBudget] = useState(100);
  const labels = labelsText.split("\n").map((label) => label.trim()).filter(Boolean);
  const labelsValid = labels.length >= 2 && labels.length <= 12 && new Set(labels).size === labels.length && labels.includes(fallback);
  const options = kind === "DATE" ? { date_order: dateOrder } : { labels, fallback };
  const signature = JSON.stringify({ kind, column, instruction, options });
  const recordSignature = record ? JSON.stringify({ kind: record.kind, column: record.column,
    instruction: record.instruction, options: record.kind === "DATE" ? { date_order: record.options.date_order }
      : { labels: record.options.labels, fallback: record.options.fallback } }) : "";
  const edited = Boolean(record && signature !== recordSignature);

  function restore(previous: LLMTransformation) {
    setRecord(previous); setKind(previous.kind); setColumn(previous.column); setInstruction(previous.instruction);
    setDateOrder(previous.options.date_order || "REJECT");
    setLabelsText((previous.options.labels || []).join("\n"));
    setFallback(previous.options.fallback || "");
    setRequestBudget(previous.request_budget ?? 100);
  }

  useEffect(() => {
    const generation = ++version.current;
    draftEdited.current = false;
    setRecord(null); setConsent(false); setError(""); setColumn("");
    setInstruction("");
    api<{ transformations: LLMTransformation[] }>(`/datasets/${dataset.id}/transformations/`).then(({ transformations }) => {
      if (generation !== version.current || draftEdited.current) return;
      const previous = transformations.find((entry) => entry.status === "READY");
      if (previous) restore(previous);
    }).catch((err) => {
      if (generation === version.current) setError(err instanceof Error ? err.message : "Could not load transformations.");
    });
    return () => { version.current += 1; };
  }, [dataset.id]);

  useEffect(() => {
    if (job?.kind !== "PREVIEW_TRANSFORM" || !job.transformation_id) return;
    const generation = version.current;
    if (job.status === "SUCCESS") {
      api<LLMTransformation>(`/transformations/${job.transformation_id}/`).then((previous) => {
        if (generation !== version.current || previous.dataset_id !== dataset.id) return;
        restore(previous); setError("");
        if (panel.current?.getClientRects().length) panel.current.scrollIntoView({ behavior: motionScrollBehavior(), block: "start" });
      }).catch((err) => {
        if (generation === version.current) setError(err instanceof Error ? err.message : "Could not load preview.");
      });
    } else if (job.status === "FAILED") setError(job.error_message);
  }, [job?.id, job?.status, dataset.id]);

  useEffect(() => {
    if (job?.kind !== "APPLY_TRANSFORM" || !job.transformation_id || !["SUCCESS", "FAILED", "CANCELLED"].includes(job.status)) return;
    let alive = true;
    api<LLMTransformation>(`/transformations/${job.transformation_id}/`).then(updated => {
      if (alive && updated.dataset_id === dataset.id) setRecord(previous => previous?.id === updated.id ? updated : previous);
    }).catch(() => {});
    return () => { alive = false; };
  }, [job?.id, job?.status, dataset.id]);

  async function preview(event: FormEvent) {
    event.preventDefault();
    if (busy || submitting || !consent || !column || !Number.isInteger(requestBudget) || requestBudget < 1 || requestBudget > 1000000 || (kind === "CATEGORY" && !labelsValid)) return;
    version.current += 1; setSubmitting(true); setRecord(null); setError("");
    try {
      onJob(await api<Job>(`/datasets/${dataset.id}/transformations/`,
        { kind, column, instruction, options, allow_send_values: consent, request_budget: requestBudget }));
    } catch (err) { setError(submissionError(err, onJob)); }
    finally { setSubmitting(false); }
  }

  async function apply() {
    if (!record || record.status !== "READY" || busy || submitting || edited || !consent || !budgetValid || overBudget) return;
    setSubmitting(true); setError("");
    try {
      onJob(await api<Job>(`/transformations/${record.id}/apply/`, { allow_send_values: consent, request_budget: requestBudget }));
    } catch (err) { setError(submissionError(err, onJob)); }
    finally { setSubmitting(false); }
  }

  const ready = record?.status === "READY";
  const current = ready && !edited;
  const budgetValid = Number.isInteger(requestBudget) && requestBudget >= 1 && requestBudget <= 1000000;
  const requestsRemaining = Math.max(0, requestBudget - (record?.requests_used ?? 0));
  const plan = record?.plan && typeof record.plan.distinct_values === "number" && typeof record.plan.estimated_new_requests === "number" ? record.plan : null;
  const overBudget = Boolean(plan && plan.estimated_new_requests > requestsRemaining);
  const previewing = busy && job?.kind === "PREVIEW_TRANSFORM";
  const applying = busy && job?.kind === "APPLY_TRANSFORM";
  const flaggedCount = record ? Object.entries(record.preview.counts)
    .reduce((count, [status, total]) => count + (["normalized", "classified"].includes(status) ? 0 : total), 0) : 0;

  return <section className="rule-panel transform-panel transform-workflow" ref={panel} aria-label="LLM date normalization and classification">
    <div className="transform-composition">
    <form className="workflow-editor" onSubmit={preview}>
      <div className="workflow-heading"><h3>{kind === "DATE" ? "Standardize dates" : "Categorize values"}</h3><p>Choose a column and check a sample before applying</p></div>
      <label>Transformation<select aria-label="Transformation" value={kind} disabled={busy || submitting}
        onChange={(event) => { draftEdited.current = true; version.current += 1; setKind(event.target.value as "DATE" | "CATEGORY"); setColumn(""); setRecord(null); setError(""); }}>
        <option value="DATE">Normalize dates</option><option value="CATEGORY">Classify values</option>
      </select></label>
      <label>Column<select aria-label="Values column" value={column} disabled={busy || submitting}
        onChange={(event) => { draftEdited.current = true; version.current += 1; setColumn(event.target.value); }}>
        <option value="" disabled>Choose a column to transform</option>
        {dataset.columns.map((entry) => <option key={entry.key} value={entry.key}>{entry.name}</option>)}
      </select></label>

      {column && /(^id$|[_ ]id$|^uuid$)/i.test(dataset.columns.find((entry) => entry.key === column)?.name || "") &&
        <p role="status" className="dataset-error">This looks like an identifier column. Check that it contains the dates or values you intend to transform.</p>}
      {kind === "DATE" ? <>
        <label>Ambiguous dates<select aria-label="Ambiguous dates" value={dateOrder} disabled={busy || submitting}
          onChange={(event) => { draftEdited.current = true; setDateOrder(event.target.value); }}>
          <option value="REJECT">Leave uncertain dates blank</option>
          <option value="DAY_FIRST">Day first</option>
          <option value="MONTH_FIRST">Month first</option>
        </select></label>
        <details className="workflow-help"><summary>Date help</summary><p>Dates use YYYY-MM-DD. For 03/04/2026, day first means 3 April and month first means March 4.</p><p>Numeric dates, English months and Chinese dates need a four-digit year. Invalid or unsupported dates produce an empty result and a status explaining why. Source values are kept.</p></details>
      </> : <>
        <label>Categories<textarea aria-label="Category labels" placeholder={"United States\nAustralia\nOther"} value={labelsText} rows={3} maxLength={500}
          disabled={busy || submitting} onChange={(event) => { draftEdited.current = true; setLabelsText(event.target.value); if (!event.target.value.split("\n").map((value) => value.trim()).includes(fallback)) setFallback(""); }} /></label>
        <p className="workflow-field-help">Enter 2 to 12 unique categories, one per line</p>
        <label>When unsure<select aria-label="Fallback label" value={fallback} disabled={busy || submitting}
          onChange={(event) => { draftEdited.current = true; setFallback(event.target.value); }}>
          <option value="" disabled>Choose a category</option>
          {labels.map((label, index) => <option key={`${label}-${index}`} value={label}>{label}</option>)}
        </select></label>
        <details className="workflow-help" open={instruction ? true : undefined}><summary>Additional instructions</summary><label>Instructions<textarea aria-label="Classification guidance" value={instruction} maxLength={1000} rows={3}
          disabled={busy || submitting} onChange={(event) => { draftEdited.current = true; setInstruction(event.target.value); }}
          placeholder="Optional instructions for choosing a category" /></label></details>
      </>}
      <label>Maximum model requests<input type="number" aria-label="Maximum model requests" min={1} max={1000000} step={1}
        value={requestBudget || ""} disabled={busy || submitting} onChange={event => { draftEdited.current = true; setRequestBudget(Number(event.target.value)); }} /></label>
      <p className="workflow-field-help">Includes preview, Apply and retries for this plan. Billing is by tokens; this is a request limit.</p>
      <details className="workflow-help"><summary>Data and limits</summary><p>OpenAI receives selected values, instructions and options. Preview checks the full column and shows up to 20 sample rows. Apply processes distinct values in small batches and saves progress on disk. Long text uses smaller batches, up to the same 65,536-character cell limit as import. No values are silently truncated.</p></details>
      <label className="value-consent"><input type="checkbox" checked={consent} disabled={busy || submitting}
        onChange={(event) => setConsent(event.target.checked)} />Allow OpenAI to process the selected values for preview and Apply</label>
      <div className="workflow-editor-actions">
      <ActionSpark disabled={busy || submitting}><button className={current ? "secondary-button" : "primary-button"} disabled={busy || submitting || !consent || !column || !budgetValid || (kind === "CATEGORY" && !labelsValid)}>
        {previewing ? "Preparing preview" : submitting ? "Submitting" : ready ? "Update preview" : "Preview"}
      </button></ActionSpark>
      </div>
      {error && <p role="alert" className="dataset-error">{error}</p>}
    </form>
    <div className="workflow-preview">
      <div className="workflow-preview-heading"><h3>Preview</h3>
        {ready && <ActionSpark disabled={busy || submitting}><button type="button" className={current ? "primary-button" : "secondary-button"} disabled={busy || submitting || !current || !consent || !budgetValid || overBudget} onClick={() => void apply()}>{applying ? "Applying" : "Apply"}</button></ActionSpark>}
      </div>
    {ready && <div className="workflow-preview-status">
      {edited ? <p className="workflow-warning" role="status">Your changes need a new preview before applying</p>
        : <p className="workflow-result-summary"><strong>{record.preview.sampled_rows}</strong> sample rows checked</p>}
      {!edited && flaggedCount > 0 && <p className="workflow-warning">{flaggedCount} sample {flaggedCount === 1 ? "value needs" : "values need"} review. Check the flagged rows before applying.</p>}
      {!consent && <p className="workflow-warning">Allow OpenAI to process the selected values before applying</p>}
      <p className="workflow-save-note">Saves a new version with result and status columns</p>
      {plan && <p className="workflow-result-summary"><strong>{plan.distinct_values.toLocaleString()}</strong> distinct values in the full column. Up to <strong>{plan.estimated_new_requests.toLocaleString()}</strong> additional requests; {requestsRemaining.toLocaleString()} remaining.</p>}
      {overBudget && <p role="status" className="workflow-warning">Increase Maximum model requests before applying. Completed values are kept when resuming.</p>}
    </div>}
    {(previewing || applying) && <p role="status" className="workflow-progress">{applying ? "Applying changes" : "Preparing preview"} {job?.progress}%</p>}
    <div className="workflow-sample" role="region" aria-label="Transformation sample preview" tabIndex={0}>
      <LoomPreview active={active} ready={ready} stale={edited} categories={kind === "CATEGORY"} title={dataset.columns.find(c => c.key === column)?.name || "Your sample"}
        job={job && ["PREVIEW_TRANSFORM", "APPLY_TRANSFORM"].includes(job.kind) ? job : null}
        rows={ready && !edited ? record.preview.examples.slice(0, 5).map(r => ({ id: String(r.row_number), label: `Row ${r.row_number}`, before: r.before, after: r.after, status: r.status }))
          : column ? rows.slice(0, 5).map(r => ({ id: String(r.row_number), label: `Row ${r.row_number}`, before: r.cells[dataset.columns.findIndex(c => c.key === column)] })) : []} />
    </div>
    {ready && <div className="workflow-result">
      <details className="preview-evidence workflow-evidence"><summary>Compare sample values</summary>
      <p>{Object.entries(record.preview.counts).map(([status, count]) => `${count} ${status.replaceAll("_", " ")}`).join(", ")}</p>
      <div className="rule-examples">{record.preview.examples.map((example) => <div className="rule-example" key={example.row_number}>
        <strong>Row {example.row_number} {example.status.replaceAll("_", " ")}</strong><span>Before</span><code>{example.before ?? "null"}</code>
        <span>Result</span><code>{example.after ?? "null"}</code>
      </div>)}</div>
      </details>
      <details className="workflow-evidence"><summary>Processing details</summary>
        <p>{record.kind === "DATE" ? "Date and calendar validation" : "Category validation"} completed. Full-column counts appear after applying.</p>
        <p>{record.usage.cached_values} of {record.usage.unique_values} distinct values used cached results.</p>
        <p>{record.usage.model_calls === 0 ? "No model call was needed." : `${record.usage.model_calls} model calls using ${record.model}.`}</p>
        {record.requests_used !== undefined && <p>Plan total: {record.requests_used} requests reserved, {record.input_tokens?.toLocaleString()} confirmed input tokens and {record.output_tokens?.toLocaleString()} confirmed output tokens. Interrupted or rejected responses may also be billed; their request reservations remain counted.</p>}
      </details>
    </div>}
    </div>
    </div>
  </section>;
}
