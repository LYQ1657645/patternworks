import { useEffect, useRef } from "react";
import { useAppearance } from "./motion";

/**
 * One sky across the workspace. The library supplies its own depth-aware stars;
 * this lightweight layer keeps the atmosphere and occasional meteor continuous.
 */
export function WorkspaceSky({ active, library = false }: { active: boolean; library?: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const { reduced } = useAppearance();

  useEffect(() => {
    if (!active || !canvas.current) return;
    const element = canvas.current;
    const context = element.getContext("2d", { alpha: true });
    if (!context) return;

    // A fixed seed keeps the sky in place when moving between workspace pages.
    let seed = 1927;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    const stars = Array.from({ length: 330 }, () => ({
      x: random(),
      y: random(),
      depth: random(),
      phase: random() * Math.PI * 2,
      warm: random() > 0.88,
    }));
    let width = 1;
    let height = 1;
    let frame = 0;
    let previousTime = 0;
    let elapsed = 0;
    let paintedAt = 0;
    let nextMeteor = 6;
    let meteor: { start: number; x: number; y: number; distance: number; duration: number } | null = null;
    // Cache the bright star glow; no shadowBlur or new gradients per star/frame.
    const glow = document.createElement("canvas");
    glow.width = glow.height = 32;
    const glowContext = glow.getContext("2d");
    if (glowContext) {
      const light = glowContext.createRadialGradient(16, 16, 0, 16, 16, 16);
      light.addColorStop(0, "rgba(214,232,255,.65)");
      light.addColorStop(.18, "rgba(165,200,250,.23)");
      light.addColorStop(1, "rgba(135,176,239,0)");
      glowContext.fillStyle = light; glowContext.fillRect(0, 0, 32, 32);
    }

    function draw() {
      if (!context) return;
      context.clearRect(0, 0, width, height);
      for (const star of library ? [] : stars) {
        const drift = reduced ? 0 : elapsed * (0.25 + star.depth * 0.35);
        const x = ((star.x * width + drift) % (width + 24)) - 12;
        const y = star.y * height + (reduced ? 0 : Math.sin(elapsed * 0.018 + star.phase) * (1 + star.depth * 3));
        const radius = 0.45 + star.depth * star.depth * 1.05;
        const pulse = reduced ? 1 : 0.86 + Math.sin(elapsed * 0.2 + star.phase) * 0.14;
        const alpha = (0.23 + star.depth * 0.48) * pulse;
        context.fillStyle = star.warm ? `rgba(238,216,185,${alpha})` : `rgba(194,212,241,${alpha})`;
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.fill();
        if (star.depth > 0.96) {
          context.globalAlpha = alpha * .7;
          context.drawImage(glow, x - 7, y - 7, 14, 14);
          context.globalAlpha = 1;
        }
      }
      if (!reduced && elapsed >= nextMeteor && !meteor) {
        meteor = { start: elapsed, x: .12 + random() * .68, y: .06 + random() * .32,
          distance: 180 + random() * 160, duration: 1.25 + random() * .4 };
        nextMeteor = elapsed + 17 + random() * 11;
      }
      if (meteor && !reduced) {
        const progress = (elapsed - meteor.start) / meteor.duration;
        if (progress >= 1) meteor = null;
        else {
          const x = meteor.x * width + progress * meteor.distance;
          const y = meteor.y * height + progress * meteor.distance * .48;
          const length = Math.min(115, width * .13);
          const fade = Math.sin(progress * Math.PI) * .58;
          const trail = context.createLinearGradient(x - length, y - length * .48, x, y);
          trail.addColorStop(0, "rgba(145,186,237,0)");
          trail.addColorStop(.75, `rgba(176,209,248,${fade * .35})`);
          trail.addColorStop(1, `rgba(231,242,255,${fade})`);
          context.strokeStyle = trail; context.lineWidth = 1.2; context.lineCap = "round";
          context.beginPath(); context.moveTo(x - length, y - length * .48); context.lineTo(x, y); context.stroke();
          context.globalAlpha = fade; context.drawImage(glow, x - 6, y - 6, 12, 12); context.globalAlpha = 1;
        }
      }
    }

    function animate(time: number) {
      if (document.hidden) return;
      // A 24 fps ceiling is enough for sub-pixel drift behind a working form.
      if (time - paintedAt >= 1000 / 24) {
        if (previousTime) elapsed += Math.min(time - previousTime, 100) / 1000;
        previousTime = time;
        paintedAt = time;
        draw();
      }
      frame = window.requestAnimationFrame(animate);
    }

    function visibility() {
      window.cancelAnimationFrame(frame);
      previousTime = 0;
      if (document.hidden) return;
      draw();
      if (!reduced) frame = window.requestAnimationFrame(animate);
    }

    function resize() {
      width = window.innerWidth;
      height = window.innerHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
      context?.setTransform(ratio, 0, 0, ratio, 0, 0);
      if (!document.hidden) draw();
    }

    resize();
    visibility();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [active, reduced, library]);

  return <div className="workspace-sky" hidden={!active} aria-hidden="true"><canvas ref={canvas} /></div>;
}
