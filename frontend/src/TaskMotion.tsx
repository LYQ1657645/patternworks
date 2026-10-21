import { useRef } from "react";
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import type { Job } from "./api";
import { taskPresentation } from "./motionState";
import { useAppearance } from "./motion";

export default function TaskMotion({ job, label = "Task progress" }: { job: Job; label?: string }) {
  const root = useRef<HTMLDivElement>(null);
  const { reduced } = useAppearance();
  const state = taskPresentation(job);
  const previous = useRef({ id: job.id, progress: state.progress });
  useGSAP(() => {
    const from = previous.current.id === job.id ? previous.current.progress : state.progress;
    gsap.fromTo(root.current!.querySelector(".task-motion-fill"), { scaleX: from / 100 }, { scaleX: state.progress / 100, duration: reduced ? 0 : .5, ease: "power2.out" });
    previous.current = { id: job.id, progress: state.progress };
  }, { scope: root, dependencies: [job.id, state.progress, reduced], revertOnUpdate: true });
  return <div className={`task-motion state-${state.state}`} ref={root}>
    <span className="task-state-mark" aria-hidden="true">{job.status === "SUCCESS" ? "✓" : job.status === "FAILED" ? "!" : job.status === "CANCELLED" ? "−" : "·"}</span>
    <div className="task-motion-track" role="progressbar" aria-label={label} aria-valuenow={state.progress} aria-valuemin={0} aria-valuemax={100} aria-valuetext={`${state.label}, ${state.progress}%`}><div className="task-motion-fill" style={{ transform: `scaleX(${state.progress / 100})` }} /></div>
    <span className="task-percent">{state.progress}%</span>
  </div>;
}
