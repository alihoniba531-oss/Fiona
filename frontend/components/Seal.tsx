import { useId } from "react";
import { avatarGlyph } from "@/lib/avatarGlyph";

export default function Seal({variant="agent", avatar, size=36, className=""}: {variant?:"brand"|"agent";avatar?:string;size?:number;className?:string}) {
  const id=useId().replace(/:/g,"");
  const glyph=avatarGlyph(avatar);
  return <svg width={size} height={size} viewBox="0 0 56 56" aria-hidden="true" className={className} style={{flexShrink:0,transform:"rotate(2deg)",overflow:"visible"}}>
    <defs><filter id={`${id}-seal`} x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".12" numOctaves="3" seed="7" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="1.3" xChannelSelector="R" yChannelSelector="G"/></filter></defs>
    <g filter={`url(#${id}-seal)`}>
      <rect x="2" y="2" width="52" height="52" rx="1" fill="var(--seal)"/>
      {variant === "brand" ? <g fill="none" stroke="var(--glyph)" strokeWidth="1.8"><circle cx="22" cy="28" r="13"/><circle cx="34" cy="28" r="13"/></g>
        : glyph ? <text x="28" y="30" dominantBaseline="middle" textAnchor="middle" fill="var(--glyph)" fontSize="30">{glyph}</text>
          : <path d="M28 9 C30 24 32 26 47 28 C32 30 30 32 28 47 C26 32 24 30 9 28 C24 26 26 24 28 9 Z" fill="var(--glyph)"/>}
    </g>
  </svg>;
}
