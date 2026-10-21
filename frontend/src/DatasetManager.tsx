import { useEffect, useState } from "react";
import { api } from "./api";
import type { Dataset } from "./api";
import { timeLabel } from "./historyLabels";
import "./taskWorkflow.css";

type Identity = { id: string; source_key: string };
type Review = { id: string; is_original: boolean; lifecycle: Dataset["lifecycle"]; retention_days: number;
  expires_at: string | null; purge_after: string | null; trash_reason: string; parent: (Identity & { lifecycle: string }) | null;
  children_count: number; active_children_count: number; active_jobs_count: number; export_count: number;
  children: (Identity & { lifecycle: string })[]; blockers: string[]; can_trash: boolean; can_restore: boolean; review_token: string };

export default function DatasetManager({ target, onClose, onChanged, onDependencies, onParent, onReviewed }: {
  target: Identity; onClose: () => void; onChanged: (dataset: Dataset) => void;
  onDependencies: (id: string) => void; onParent: (target: Identity) => void;
  onReviewed: () => void;
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [original, setOriginal] = useState(false);
  const [days, setDays] = useState(0);
  const [expiryConsent, setExpiryConsent] = useState(false);
  const [revision, refresh] = useState(0);
  useEffect(() => {
    let alive = true; setLoading(true); setReview(null); setConfirmation(""); setOriginal(false); setExpiryConsent(false);
    api<Review>(`/datasets/${target.id}/lifecycle/`).then((result) => {
      if (alive) { setReview(result); setDays(result.retention_days); onReviewed(); }
    }).catch((err) => { if (alive) setError(err instanceof Error ? err.message : "Could not review dataset dependencies."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [target.id, revision]);

  async function act(action: "trash" | "restore" | "retention") {
    if (!review || acting) return;
    if (action === "trash" && (!review.can_trash || confirmation !== target.source_key || (review.is_original && !original))) return;
    setActing(true); setError("");
    const body = action === "trash" ? { confirm_id: target.id, confirm_original: original, review_token: review.review_token }
      : action === "retention" ? { days, confirm_expiry: expiryConsent } : {};
    try {
      const result = await api<Dataset>(`/datasets/${target.id}/${action}/`, body);
      onChanged(result); refresh((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update this dataset."); refresh((v) => v + 1);
    } finally { setActing(false); }
  }
  return <section className="dataset-manager version-management" aria-label="Dataset deletion and retention">
    <div className="list-heading"><h3>Manage version</h3><button className="text-button" disabled={acting} onClick={onClose}>Close</button></div>
    <strong>{target.source_key}</strong>
    {error && <p role="alert">{error}</p>}
    {loading && <p role="status">Checking this version</p>}
    {review && <>
      {review.is_original && review.lifecycle === "ACTIVE" && <p className="management-summary">Original import</p>}
      {review.parent && <button className="text-button" disabled={acting} onClick={() => onParent(review.parent!)}>Source version</button>}
      {review.active_children_count > 0 && <p className="lifecycle-warning">{review.active_children_count} later version{review.active_children_count === 1 ? " depends" : "s depend"} on this one. Move {review.active_children_count === 1 ? "it" : "them"} to Trash first.</p>}
      {review.active_jobs_count > 0 && <p className="lifecycle-warning">Tasks are still using this version. Wait until they finish or complete cancellation.</p>}
      {review.blockers.filter(message => !message.includes("dependent dataset(s)") && !message.includes("task(s)")).map(message => <p key={message} className="lifecycle-warning">{message}</p>)}
      {review.children_count > 0 && <button className="secondary-button" disabled={acting} onClick={() => onDependencies(target.id)}>Related versions</button>}
      {review.lifecycle === "ACTIVE" && <>
        {!review.is_original && <details className="retention-controls"><summary>Automatic cleanup</summary>
          <label>Keep this version<select value={days} disabled={acting || review.is_original} onChange={(event) => { setDays(Number(event.target.value)); setExpiryConsent(false); }}>
            <option value={0}>Keep until I delete it</option><option value={7}>Move to Trash in 7 days</option>
            <option value={30}>Move to Trash in 30 days</option><option value={90}>Move to Trash in 90 days</option>
          </select></label>
          {days > 0 && <label className="consent"><input type="checkbox" checked={expiryConsent} disabled={acting} onChange={(event) => setExpiryConsent(event.target.checked)} />Move this version to Trash automatically, then permanently remove its data and exports after 7 days. Dependent versions and unfinished tasks delay cleanup.</label>}
          <button className="secondary-button" disabled={acting || review.is_original || (days > 0 && !expiryConsent)} onClick={() => void act("retention")}>Save</button>
        </details>}
        {review.expires_at && <p className="management-schedule">Moves to Trash {timeLabel(review.expires_at)} unless another version or task still needs it.</p>}
        <details className="trash-confirmation"><summary>Delete version</summary>
          <p>Recoverable from Trash for 7 days. After that, its data and exports are permanently removed when no version or task still needs them. Your S3 file stays unchanged.</p>
          {review.is_original && <label className="consent"><input type="checkbox" checked={original} disabled={acting} onChange={(event) => setOriginal(event.target.checked)} />I also want to remove this original imported copy.</label>}
          <label>Type the file name to confirm<input placeholder={target.source_key} value={confirmation} disabled={acting || !review.can_trash} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label>
          <button className="danger-button" disabled={acting || !review.can_trash || confirmation !== target.source_key || (review.is_original && !original)} onClick={() => void act("trash")}>Move to Trash</button>
        </details>
      </>}
      {review.lifecycle === "TRASH" && <>
        <p>Restore before {review.purge_after ? timeLabel(review.purge_after) : "the recovery period ends"}</p>
        {review.parent?.lifecycle !== "ACTIVE" && review.parent && <p className="lifecycle-warning">Restore the source version first.</p>}
        <button className="primary-button" disabled={acting || !review.can_restore} onClick={() => void act("restore")}>Restore</button>
        <p className="management-summary">Restored versions stay until you delete them</p>
      </>}
      {review.lifecycle === "PURGING" && <p>Permanent deletion is underway. This version can no longer be restored.</p>}
      {review.lifecycle === "PURGED" && <p>This version has been permanently deleted.</p>}
      <details className="management-details"><summary>Details</summary>
        <p>Version ID <code className="managed-id">{target.id}</code></p>
        <p>{review.lifecycle} · {review.children_count} related versions · {review.export_count} exports</p>
        {review.is_original && <p>Original imports are never deleted automatically.</p>}
        {review.trash_reason && <p>{review.trash_reason}</p>}
        <ul>{review.children.map(child => <li key={child.id}>{child.source_key} ({child.lifecycle})<code className="managed-id">{child.id}</code></li>)}</ul>
      </details>
    </>}
    <button className="text-button" disabled={acting || loading} onClick={() => { setError(""); refresh((v) => v + 1); }}>Refresh</button>
  </section>;
}
