import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import ClickSpark from "./vendor/react-bits/ClickSpark/ClickSpark";
gsap.registerPlugin(useGSAP);

function stored(key: string) { try { return localStorage.getItem(key); } catch { return null; } }
export function useAppearance() {
  const [night, setNight] = useState(() => stored("patternworks-theme") === "night");
  const [reduced, setReduced] = useState(() => stored("patternworks-reduce-motion") === "true" || window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => { setNight(stored("patternworks-theme") === "night"); setReduced(media.matches || stored("patternworks-reduce-motion") === "true"); };
    media.addEventListener("change", sync); window.addEventListener("patternworks-appearance", sync); window.addEventListener("storage", sync);
    return () => { media.removeEventListener("change", sync); window.removeEventListener("patternworks-appearance", sync); window.removeEventListener("storage", sync); };
  }, []);
  return { night, reduced };
}

export function AppearanceControls() {
  const { night, reduced } = useAppearance();
  useEffect(() => { document.documentElement.dataset.theme = night ? "night" : "paper"; document.documentElement.dataset.motion = reduced ? "reduced" : "full"; }, [night, reduced]);
  function change(key: string, value: string) { try { localStorage.setItem(key, value); } catch { /* Settings may be unavailable in private browsing. */ } window.dispatchEvent(new Event("patternworks-appearance")); }
  return <div className="appearance-controls">

    <details><summary aria-label="Animation preferences">Animations</summary><label><input type="checkbox" checked={reduced} aria-label="Reduce animations" disabled={window.matchMedia("(prefers-reduced-motion: reduce)").matches} onChange={e => change("patternworks-reduce-motion", String(e.target.checked))} /><span>Reduce animations<small>{window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "Following your device setting." : "Stops automatic movement and uses instant transitions."}</small></span></label></details>
  </div>;
}

export function ActionSpark({ children, disabled = false }: { children: ReactNode; disabled?: boolean }) {
  const { reduced } = useAppearance();
  return <ClickSpark className="action-spark" sparkColor="#c6d8ff" sparkCount={7} sparkRadius={30} sparkSize={7} duration={420} shape="streak" disabled={disabled || reduced} style={{ width: "fit-content", height: "auto", maxWidth: "100%" }}>{children}</ClickSpark>;
}

export function Reveal({ children, identity, active = true, className = "" }: { children: ReactNode; identity: string; active?: boolean; className?: string }) {
  const root = useRef<HTMLDivElement>(null);
  const { reduced } = useAppearance();
  useGSAP(() => {
    if (active && !reduced) gsap.fromTo(root.current, { y: 18, opacity: .3 }, { y: 0, opacity: 1, duration: .45, ease: "power3.out", clearProps: "transform,opacity" });
  }, { scope: root, dependencies: [identity, active, reduced], revertOnUpdate: true });
  return <div ref={root} className={className}>{children}</div>;
}

export function motionScrollBehavior(): ScrollBehavior {
  return document.documentElement.dataset.motion === "reduced" || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}
