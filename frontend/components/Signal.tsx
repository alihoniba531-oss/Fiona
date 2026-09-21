"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

export type SignalMode = "idle" | "listening" | "speaking";

export default function Signal({
  mode,
  className,
}: {
  mode: SignalMode;
  className?: string;
}) {
  const pathRef = useRef<SVGPathElement>(null);
  const dotRef = useRef<SVGCircleElement>(null);
  const modeRef = useRef(mode);
  // eslint-disable-next-line react-hooks/purity -- The signal specification requires a stable random phase per mount.
  const phaseRef = useRef(Math.random() * 20);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    const currentPath = pathRef.current;
    const currentDot = dotRef.current;
    if (!currentPath || !currentDot) return;
    const path: SVGPathElement = currentPath;
    const dot: SVGCircleElement = currentDot;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    );
    if (reduceMotion.matches) {
      path.setAttribute("d", "M0 20 L1000 20");
      dot.setAttribute("opacity", "0");
      return;
    }

    let level = 0;
    let t = 0;
    let last = performance.now();
    let animationFrame = 0;

    function draw(dt: number) {
      const currentMode = modeRef.current;
      const target =
        currentMode === "idle" ? 0 : currentMode === "listening" ? 0.5 : 0.9;
      level += (target - level) * Math.min(1, dt * 6);
      t += dt;

      let d = "";
      for (let i = 0; i < 140; i += 1) {
        const x = (i / 139) * 1000;
        const env = Math.sin((Math.PI * i) / 139);
        const w =
          8 * Math.sin(x * 0.045 + t * 9 + phaseRef.current) +
          5 * Math.sin(x * 0.012 - t * 5.5) +
          3 * Math.sin(x * 0.09 + t * 14);
        const y = 20 + env * level * w;
        d += `${i ? " L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
      }
      path.setAttribute("d", d);

      if (currentMode === "idle" && level < 0.02) {
        const cx = ((t * 140 + phaseRef.current * 100) % 1300) - 150;
        dot.setAttribute("cx", String(cx));
        dot.setAttribute("opacity", cx < 0 || cx > 1000 ? "0" : "1");
      } else {
        dot.setAttribute("opacity", "0");
      }
    }

    function loop(now: number) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      draw(dt);
      animationFrame = requestAnimationFrame(loop);
    }

    animationFrame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animationFrame);
  }, []);

  return (
    <svg
      className={cn("signal", className)}
      viewBox="0 0 1000 40"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path ref={pathRef} d="M0 20 L1000 20" />
      <circle ref={dotRef} cx="-10" cy="20" r="3" />
    </svg>
  );
}
