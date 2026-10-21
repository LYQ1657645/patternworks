import type { Dataset, Job } from "./api";

/** Presentation only: no elapsed-time estimate can advance a server task. */
export function taskPresentation(job: Job | null) {
  if (!job) return { state: "idle", running: false, progress: 0, label: "Ready when you are" };
  const progress = Number.isFinite(job.progress) ? Math.min(100, Math.max(0, job.progress)) : 0;
  return {
    state: job.status.toLowerCase(),
    running: job.status === "RUNNING",
    progress,
    label: job.status === "SUCCESS" ? "Complete" : job.status === "FAILED" ? "Failed"
      : job.status === "CANCELLED" ? "Cancelled" : job.status === "QUEUED" ? "Queued" : job.stage || "Processing",
  };
}

export function isNewDatasetResult(job: Job | null, dataset: Dataset) {
  return Boolean(job?.status === "SUCCESS" && job.dataset_id === dataset.id
    && job.dataset_available !== false && dataset.status === "READY" && dataset.lifecycle === "ACTIVE"
    && ["IMPORT_DATASET", "REPLACE_TEXT", "APPLY_RULE", "APPLY_TRANSFORM"].includes(job.kind));
}

export type MotionRow = { id: string; label: string; before: string | null; after?: string | null; status?: string; shortened?: boolean };
export function isFlagged(status?: string) {
  return Boolean(status && !["normalized", "classified", "updated", "unchanged", "matched", "no match"].includes(status.toLowerCase()));
}

/** Limit the visual sample, never the full preview. Group only returned category values. */
export function layoutRows(rows: MotionRow[], ready: boolean, categories: boolean) {
  const sample = rows.slice(0, 5);
  const groups = categories && ready ? [...new Set(sample.map(row => row.after ?? "No result"))] : [];
  const ordered = groups.flatMap(group => sample.filter(row => (row.after ?? "No result") === group));
  let previous = "", top = 0;
  return (groups.length ? ordered : sample).map((row, index) => {
    const group = row.after ?? "No result";
    const groupStart = groups.length > 0 && (index === 0 || group !== previous);
    if (groupStart) top += 28;
    const result = { ...row, top, groupStart, group, count: sample.filter(r => (r.after ?? "No result") === group).length };
    // Result cards show both the original and result; leave room for that pair
    // and a possible review status without letting adjacent rows overlap.
    previous = group; top += ready ? 94 : 76;
    return result;
  });
}
