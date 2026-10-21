import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import LoomPreview from "./LoomPreview";
import { ActionSpark, motionScrollBehavior } from "./motion";
import type { DatasetPage } from "./api";
import { api, submissionError } from "./api";
import type { Dataset, Job, RegexRule } from "./api";
import { sameColumns, toggleColumn } from "./ruleSelection";
import "./transformWorkflow.css";

type Props = { dataset: Dataset; busy: boolean; job: Job | null; onJob: (job: Job) => void; rows?: DatasetPage["rows"]; active?: boolean };

export default function RulePanel({ dataset, busy, job, onJob, rows = [], active = true }: Props) {
  const [columns, setColumns] = useState<string[]>([]);
  const [instruction, setInstruction] = useState("");
  const [replacement, setReplacement] = useState("[REDACTED]");
  const [rule, setRule] = useState<RegexRule | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [previewColumn, setPreviewColumn] = useState("");
  const panel = useRef<HTMLElement>(null);
  const version = useRef(0);
  const draftEdited = useRef(false);

  useEffect(() => {
    const generation = ++version.current;
    draftEdited.current = false;
    setRule(null);
    setError("");
    setColumns([]);
    setInstruction("");
    setReplacement("[REDACTED]");
    setPreviewColumn("");
    api<{ rules: RegexRule[] }>(`/datasets/${dataset.id}/rules/`)
      .then(({ rules }) => {
        if (generation !== version.current || draftEdited.current) return;
        const previous = rules.find((entry) => entry.status === "READY");
        if (previous) {
          setRule(previous);
          setColumns(previous.columns || [previous.column]);
          setInstruction(previous.instruction);
          setReplacement(previous.replacement);
        }
      }).catch((err) => {
        if (generation === version.current) setError(err instanceof Error ? err.message : "Could not load rules.");
      });
    return () => { version.current += 1; };
  }, [dataset.id]);

  useEffect(() => {
    if (job?.kind !== "GENERATE_RULE" || !job.rule_id) return;
    const generation = version.current;
    if (job.status === "SUCCESS") {
      api<RegexRule>(`/rules/${job.rule_id}/`).then((record) => {
        if (generation !== version.current || record.dataset_id !== dataset.id) return;
        setRule(record);
        setColumns(record.columns || [record.column]);
        setInstruction(record.instruction);
        setReplacement(record.replacement);
        setError("");
        if (panel.current?.getClientRects().length) panel.current.scrollIntoView({ behavior: motionScrollBehavior(), block: "start" });
      }).catch((err) => {
        if (generation === version.current) setError(err instanceof Error ? err.message : "Could not load the generated rule.");
      });
    } else if (job.status === "FAILED") {
      setError(job.error_message);
    }
  }, [job?.id, job?.status, dataset.id]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (busy || submitting || columns.length === 0) return;
    version.current += 1;
    setSubmitting(true);
    setRule(null);
    setError("");
    try {
      onJob(await api<Job>(`/datasets/${dataset.id}/rules/`, { columns, instruction, replacement }));
    } catch (err) {
      setError(submissionError(err, onJob));
    } finally {
      setSubmitting(false);
    }
  }

  async function apply() {
    if (!rule || rule.status !== "READY" || busy || submitting || edited || !rule.preview.full_values) return;
    setSubmitting(true);
    setError("");
    try {
      onJob(await api<Job>(`/rules/${rule.id}/apply/`, {}));
    } catch (err) {
      setError(submissionError(err, onJob));
    } finally {
      setSubmitting(false);
    }
  }

  const edited = rule && (!sameColumns(rule.columns || [rule.column], columns) || rule.instruction !== instruction || rule.replacement !== replacement);
  const previews = rule?.preview.column_previews || (rule ? [{ column: rule.column,
    name: dataset.columns.find((entry) => entry.key === rule.column)?.name || rule.column,
    sampled_rows: rule.preview.sampled_rows, matched_rows: rule.preview.matched_rows,
    match_count: 0, changed_rows: 0, examples: rule.preview.examples }] : []);
  const generating = busy && job?.kind === "GENERATE_RULE";
  const applying = busy && job?.kind === "APPLY_RULE";
  const ready = rule?.status === "READY";
  const current = ready && !edited && Boolean(rule.preview.full_values);
  const previewKey = columns.includes(previewColumn) ? previewColumn : columns[0];
  const selectedPreview = previews.find(entry => entry.column === previewKey);
  const sampleRows = ready && !edited
    ? (selectedPreview?.examples || []).slice(0, 5).map(r => ({ id: String(r.row_number), label: `Row ${r.row_number}`, before: r.before, after: r.after, status: r.matched ? "matched" : "no match" }))
    : previewKey ? rows.slice(0, 5).map(r => ({ id: String(r.row_number), label: `Row ${r.row_number}`, before: r.cells[dataset.columns.findIndex(c => c.key === previewKey)] })) : [];
  return (
    <section className="rule-panel transform-workflow" ref={panel} aria-label="Natural-language regex">
      <div className="transform-composition">
      <form className="workflow-editor" onSubmit={generate}>
        <div className="workflow-heading"><h3>Match and replace</h3><p>Choose columns and describe what to replace</p></div>
        <fieldset className="column-selection" disabled={busy || submitting}>
          <legend>Columns</legend>
          <div className="column-selection-actions">
            <button className="text-button" type="button" onClick={() => { draftEdited.current = true; setColumns(dataset.columns.map((entry) => entry.key)); }}>Select all</button>
            <button className="text-button" type="button" onClick={() => { draftEdited.current = true; setColumns([]); }}>Clear</button>
          </div>
          <div className="column-options">{dataset.columns.map((entry) => <label key={entry.key}>
            <input type="checkbox" checked={columns.includes(entry.key)} aria-label={`Regex target: ${entry.name}`}
              onChange={(event) => { draftEdited.current = true; setColumns((current) => toggleColumn(dataset.columns.map((col) => col.key), current, entry.key, event.target.checked)); }} />
            <span>{entry.name}</span>
          </label>)}</div>
        </fieldset>

        <label>What to match<textarea value={instruction} required maxLength={2000} rows={3}
          disabled={busy || submitting} onChange={(event) => { draftEdited.current = true; setInstruction(event.target.value); }}
          placeholder="For example, email addresses or 邮件" /></label>
        <label>Replacement text<input value={replacement} maxLength={256} aria-describedby="regex-replacement-help"
          disabled={busy || submitting} onChange={(event) => { draftEdited.current = true; setReplacement(event.target.value); }}
          placeholder="Leave blank to delete matches" /></label>
        <p className="workflow-field-help" id="regex-replacement-help">Use any text, with or without brackets. Leave blank to delete matches.</p>

        <div className="workflow-editor-actions">
        <ActionSpark disabled={busy || submitting}><button className={current ? "secondary-button" : "primary-button"} disabled={busy || submitting || columns.length === 0}>
          {generating ? "Generating" : submitting ? "Submitting" : ready ? "Update preview" : "Generate"}
        </button></ActionSpark>
        </div>
        <details className="workflow-help"><summary>Regex details</summary><p>The regex is generated from your description. Replacement text is used as written. Capture substitutions and lookarounds are not supported.</p><p>Only your instruction is sent to OpenAI. Replacement text, table values and AWS credentials stay private.</p></details>
        {error && <p className="dataset-error" role="alert">{error}</p>}
      </form>
      <div className="workflow-preview">
      <div className="workflow-preview-heading"><h3>Preview</h3>
        {ready && <ActionSpark disabled={busy || submitting}><button className={current ? "primary-button" : "secondary-button"} type="button" disabled={busy || submitting || !current} onClick={() => void apply()}>{applying ? "Applying" : "Apply"}</button></ActionSpark>}
      </div>
      {ready && <div className="workflow-preview-status">
          {edited ? <p className="workflow-warning" role="status">Your changes need a new preview before applying</p>
            : !rule.preview.full_values ? <p className="workflow-warning" role="status">Update this older preview before applying</p>
            : <p className="workflow-result-summary"><strong>{rule.preview.matched_rows}</strong> of {rule.preview.sampled_rows} sample rows match</p>}
          {!edited && rule.preview.matched_rows === 0 && <p className="workflow-warning">No sample matches. Check your rule before applying.</p>}
          {!edited && selectedPreview?.examples.some(example => example.before_truncated || example.after_truncated) &&
            <p className="workflow-warning">Long values are shortened here. Matching uses complete values.</p>}
          <p className="workflow-save-note">Saves a new version across {columns.length === 1 ? "the selected column" : `all ${columns.length} selected columns`}</p>
      </div>}
      {(generating || applying) && <p role="status" className="workflow-progress">{applying ? "Applying changes" : "Preparing preview"} {job?.progress}%</p>}
      {columns.length > 1 && <label className="workflow-column-switch">Column<select aria-label="Preview column" value={previewKey} onChange={event => setPreviewColumn(event.target.value)}>{columns.map(key => <option key={key} value={key}>{dataset.columns.find(c => c.key === key)?.name || key}</option>)}</select></label>}
      <div className="workflow-sample" role="region" aria-label="Regex sample preview" tabIndex={0}>
      <LoomPreview active={active} ready={ready} stale={Boolean(edited)} title={dataset.columns.find(c => c.key === previewKey)?.name || "Your sample"}
        job={job && ["GENERATE_RULE", "APPLY_RULE"].includes(job.kind) ? job : null}
        rows={sampleRows} />
      </div>
      {ready && (
        <div className="workflow-result">
          <details className="preview-evidence workflow-evidence"><summary>Compare sample values</summary>
          <p>Representative rows from each selected column. Sample results are not a full-dataset count. Long values are shortened for display.</p>
          {previews.map((preview, index) => <details className="column-preview" key={preview.column} open={index === 0}>
            <summary>{preview.name} {preview.matched_rows} matching sample rows</summary>
            <div className="rule-examples">{preview.examples.map((example) => (
            <div className="rule-example" key={example.row_number}>
              <strong>Row {example.row_number} {example.matched ? `${example.match_count} match${example.match_count === 1 ? "" : "es"}` : "No match"}</strong>
              <span>Before{example.before_truncated ? " (shortened)" : ""}</span><code>{example.before ?? "null"}</code>
              <span>After{example.after_truncated ? " (shortened)" : ""}</span><code>{example.after ?? "null"}</code>
            </div>
          ))}</div></details>)}
          </details>
          <details className="workflow-evidence"><summary>Rule details</summary>
            <pre className="regex-code"><code>{rule.pattern}</code></pre>
            <p>{rule.explanation}</p>
            <p>Replacement: <code>{rule.replacement === "" ? "(delete matches)" : rule.replacement}</code>. {rule.ignore_case ? "Ignores case." : "Case sensitive."}</p>
            <p>Syntax and safety checks passed. {rule.cache_hit ? "Reused a cached rule without a model call." : `Generated by ${rule.model}.`}</p>
            <p>{rule.preview.full_values ? "Matching uses complete cell values." : "This older preview needs to be updated."} Display limit: {rule.preview.cell_character_limit.toLocaleString()} characters.</p>
            {rule.preview.validation_examples && <><p>Generated examples checked locally</p><p>Should match: {rule.preview.validation_examples.matching.map((value, index) => <code key={index}>{value}{" "}</code>)}</p><p>Should not match: {rule.preview.validation_examples.non_matching.map((value, index) => <code key={index}>{value}{" "}</code>)}</p></>}
          </details>
        </div>
      )}
      </div>
      </div>
    </section>
  );
}
