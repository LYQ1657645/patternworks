import { useRef } from "react";
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import type { Job } from "./api";
import { useAppearance } from "./motion";
import { isFlagged, layoutRows, taskPresentation } from "./motionState";
import type { MotionRow } from "./motionState";
import "./loomWorkflow.css";

const displayValue = (value: string | null | undefined) =>
  value === null ? "null" : value === undefined ? "No result" : value === "" ? "(empty)" : value;

export default function LoomPreview({ rows, ready, categories = false, active, job, title, stale = false }: {
  rows: MotionRow[]; ready: boolean; categories?: boolean; active: boolean; job: Job | null; title: string; stale?: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const { reduced } = useAppearance();
  const task = taskPresentation(job);
  const layout = layoutRows(rows, ready && !stale, categories);
  const signature = JSON.stringify({ rows, ready, categories, stale });
  useGSAP(() => {
    if (!active) return;
    const records = root.current!.querySelectorAll<HTMLElement>(".loom-record");
    records.forEach((element) => {
      const row = layout.find(r => r.id === element.dataset.row);
      const index = rows.findIndex(r => r.id === element.dataset.row);
      const sorted = ready && !stale;
      const target = { xPercent: -50, x: sorted ? 0 : [-18, 18, -22, 16, -12][index % 5],
        y: sorted ? row?.top ?? 0 : index * 76, rotation: sorted ? 0 : [-7, 5, -4, 6, -5][index % 5] };
      // Keep semantic content immediate. Only the visual movement is delayed.
      gsap.to(element, { ...target, duration: reduced ? 0 : .65, delay: reduced ? 0 : index * .045, ease: "power3.out" });
    });
  }, { scope: root, dependencies: [signature, active, reduced], revertOnUpdate: true });
  useGSAP(() => {
    if (!active || reduced || !task.running) return;
    const pulse = gsap.fromTo(root.current!.querySelectorAll(".loom-pulse"), { strokeDashoffset: 950 }, { strokeDashoffset: -950, duration: 2.6, repeat: -1, ease: "none", stagger: .18 });
    const visibility = () => document.hidden ? pulse.pause() : pulse.resume();
    document.addEventListener("visibilitychange", visibility); visibility();
    return () => { document.removeEventListener("visibilitychange", visibility); };
  }, { scope: root, dependencies: [active, reduced, task.running], revertOnUpdate: true });
  const height = Math.max(330, (layout.at(-1)?.top ?? 0) + (ready && !stale ? 108 : 94));
  return <div className={`loom-preview ${stale ? "preview-stale" : ""}`} ref={root} aria-label="Animated data preview">
    <div className="loom-preview-heading"><span>{title}</span></div>
    <div className="loom-canvas" style={{ height }}>
      <svg className="loom-threads" viewBox="0 0 500 460" preserveAspectRatio="none" aria-hidden="true">{Array.from({ length: 17 }, (_, i) => <path key={i} d={`M ${-35+i*8} -25 C ${160+i*4} ${70+i*3}, ${-10+i*3} ${150+i*4}, ${225+i*6} 235 S ${530-i*3} ${340+i*2}, ${360+i*7} 490`} />)}{task.running && [3, 8, 13].map(i => <path className="loom-pulse" key={`pulse-${i}`} d={`M ${-35+i*8} -25 C ${160+i*4} ${70+i*3}, ${-10+i*3} ${150+i*4}, ${225+i*6} 235 S ${530-i*3} ${340+i*2}, ${360+i*7} 490`} />)}</svg>
      {layout.filter(row => row.groupStart).map(row => <span className="loom-group" key={row.group} style={{ top: row.top - 23 }}>{row.group} · {row.count}</span>)}
      {rows.slice(0, 5).map((row, index) => {
        const showResult = ready && !stale && !row.shortened;
        const flagged = row.shortened || (showResult && isFlagged(row.status));
        const changed = showResult && row.before !== row.after;
        return <div key={row.id} data-row={row.id} className={`loom-record ${showResult ? "has-comparison" : ""} ${flagged ? "flagged" : changed ? "updated" : ""}`} style={{ transform: `translate(-50%, ${index * 76}px)` }}>
          <span className="loom-row-label">{row.label}</span>
          <div className="loom-values">
            <code className={`${showResult ? "loom-before" : "loom-source"} ${changed ? "value-changed" : ""}`}
              aria-label={`${row.label} original value`} title={displayValue(row.before)}>{displayValue(row.before)}</code>
            {showResult && <code className="loom-after" aria-label={`${row.label} result`} title={displayValue(row.after)}>{displayValue(row.after)}</code>}
          </div>
          {flagged && <small className="loom-review-status">{row.status?.replaceAll("_", " ")}</small>}
        </div>;
      })}
      {!rows.length && <div className="loom-empty">Choose a column</div>}
    </div>
    {(stale || task.running || job?.status === "QUEUED") && <p className="loom-caption" role="status">{stale ? "Options changed. Preview again." : `${task.label} · ${task.progress}%`}</p>}
  </div>;
}
