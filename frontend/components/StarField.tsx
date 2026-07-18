"use client";

import { useEffect, useRef } from "react";

interface Star {
  x: number;
  y: number;
  z: number;
  size: number;
  alpha: number;
  phase: number;
  twinkleFreq: number;
  drift: number;
}

interface ShootingStar {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
}

interface Props {
  count?: number;
  className?: string;
}

export default function StarField({ count = 260, className = "" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf: number | null = null;
    let stars: Star[] = [];
    let shootingStar: ShootingStar | null = null;
    let dpr = 1;
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    let prefersReducedMotion = motionQuery.matches;

    const drawStaticStarfield = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);

      for (const s of stars) {
        const twinkle = (Math.sin(s.phase) + 1) * 0.5;
        const a = s.alpha * (0.35 + twinkle * 0.65);
        const r = Math.floor(180 + s.z * 75);
        const g = Math.floor(215 + s.z * 40);
        ctx.fillStyle = `rgba(${r},${g},255,${a})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size * s.z, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.floor(w * dpr));
      canvas.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      initStars();
      if (prefersReducedMotion) drawStaticStarfield();
    };

    const initStars = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      stars = [];
      for (let i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          z: 0.3 + Math.random() * 0.7,
          size: 0.4 + Math.random() * 1.6,
          alpha: 0.25 + Math.random() * 0.55,
          phase: Math.random() * Math.PI * 2,
          twinkleFreq: 0.4 + Math.random() * 1.6,
          drift: 0.015 + Math.random() * 0.08,
        });
      }
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    let lastT = performance.now();
    const tick = (now: number) => {
      raf = null;
      if (document.hidden || prefersReducedMotion) return;

      const dt = Math.min(3, (now - lastT) / 16.67);
      lastT = now;
      const t = now * 0.001;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);

      for (const s of stars) {
        s.y += s.drift * s.z * dt;
        if (s.y > h + 4) {
          s.y = -4;
          s.x = Math.random() * w;
        }
        const twinkle = (Math.sin(t * s.twinkleFreq + s.phase) + 1) * 0.5;
        const a = s.alpha * (0.35 + twinkle * 0.65);
        const r = Math.floor(180 + s.z * 75);
        const g = Math.floor(215 + s.z * 40);
        ctx.fillStyle = `rgba(${r},${g},255,${a})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size * s.z, 0, Math.PI * 2);
        ctx.fill();
      }

      if (!shootingStar && Math.random() < 0.0012) {
        shootingStar = {
          x: Math.random() * w * 0.7,
          y: Math.random() * h * 0.5,
          vx: 4 + Math.random() * 4,
          vy: 1.5 + Math.random() * 2.5,
          life: 1.0,
        };
      }
      if (shootingStar) {
        const s = shootingStar;
        const grad = ctx.createLinearGradient(
          s.x - s.vx * 8, s.y - s.vy * 8,
          s.x, s.y
        );
        grad.addColorStop(0, "rgba(242,168,60,0)");
        grad.addColorStop(1, `rgba(242,168,60,${s.life * 0.9})`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(s.x - s.vx * 8, s.y - s.vy * 8);
        ctx.lineTo(s.x, s.y);
        ctx.stroke();
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        s.life -= 0.018 * dt;
        if (s.life <= 0 || s.x > w + 20 || s.y > h + 20) shootingStar = null;
      }

      raf = requestAnimationFrame(tick);
    };

    const stopAnimation = () => {
      if (raf === null) return;
      cancelAnimationFrame(raf);
      raf = null;
    };

    const startAnimation = () => {
      if (document.hidden || prefersReducedMotion || raf !== null) return;
      lastT = performance.now();
      raf = requestAnimationFrame(tick);
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopAnimation();
      } else {
        startAnimation();
      }
    };

    const handleMotionPreferenceChange = (event: MediaQueryListEvent) => {
      prefersReducedMotion = event.matches;
      shootingStar = null;

      if (prefersReducedMotion) {
        stopAnimation();
        drawStaticStarfield();
      } else {
        startAnimation();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    motionQuery.addEventListener("change", handleMotionPreferenceChange);
    startAnimation();

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      motionQuery.removeEventListener("change", handleMotionPreferenceChange);
      stopAnimation();
      ro.disconnect();
    };
  }, [count]);

  return (
    <canvas
      ref={canvasRef}
      className={"absolute inset-0 w-full h-full pointer-events-none " + className}
    />
  );
}
