"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
export type SignalMode="idle"|"listening"|"speaking";
const FAR="M0 30 C60 29.5 110 28.5 160 27.5 C190 27 205 22 222 21 C234 20.3 240 15 250 13.5 C258 12.4 263 16 270 16.8 C280 18 287 10 298 7.5 C307 5.5 313 8 320 11 C330 15 342 17.5 360 20 C384 23 404 24.5 430 24 C452 23.6 466 20.5 484 20.5 C504 20.5 530 25 600 27";
const NEAR="M120 34 C200 33 250 31.5 290 30 C312 29.2 322 25.5 338 24.6 C352 24 360 27.5 374 28.6 C400 30.5 450 31.6 600 32.5";
export default function Signal({mode,className}:{mode:SignalMode;className?:string}) {
  const farRef=useRef<SVGPathElement>(null);
  const nearRef=useRef<SVGPathElement>(null);
  const svgRef=useRef<SVGSVGElement>(null);
  useEffect(() => {
    const far=farRef.current,near=nearRef.current,svg=svgRef.current;
    if (!far || !near || !svg) return;
    const media=window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame=0;
    const reset=() => { cancelAnimationFrame(frame); far.setAttribute("d",FAR);near.setAttribute("d",NEAR); };
    function start() {
      reset();
      const effective=media.matches ? "idle":mode;
      svg!.dataset.mode=effective;
      if (effective === "idle") return;
      const sample=(path:SVGPathElement) => { const length=path.getTotalLength();return Array.from({length:120},(_,i) => path.getPointAtLength(length*i/119)); };
      const farPoints=sample(far!),nearPoints=sample(near!);
      const began=performance.now();
      function draw(now:number) {
        const t=(now-began)/1000;
        const line=(points:DOMPoint[],nearLine:boolean) => points.map((p,i) => {
          const envelope=Math.sin(Math.PI*i/119);
          const amount=effective === "speaking" ? (nearLine ? 2.8:5.5) : (nearLine ? .9:0);
          const y=p.y+amount*envelope*(Math.sin(p.x*.025+t*(effective === "listening" ? 11:2.2))+.35*Math.sin(p.x*.048-t*1.5));
          return `${i ? "L":"M"}${p.x.toFixed(2)} ${y.toFixed(2)}`;
        }).join(" ");
        far!.setAttribute("d",line(farPoints,false));near!.setAttribute("d",line(nearPoints,true));
        frame=requestAnimationFrame(draw);
      }
      frame=requestAnimationFrame(draw);
    }
    start();media.addEventListener("change",start);
    return () => {reset();media.removeEventListener("change",start);};
  },[mode]);
  return <svg ref={svgRef} className={cn("signal",className)} viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden="true" data-mode="idle">
    <g transform="scale(1.6666667 1)"><path ref={farRef} d={FAR} className="signal-far" vectorEffect="non-scaling-stroke"/><path ref={nearRef} d={NEAR} className="signal-near" opacity=".6" vectorEffect="non-scaling-stroke"/></g>
  </svg>;
}
