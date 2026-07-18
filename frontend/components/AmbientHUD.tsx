"use client";

import { useEffect, useState } from "react";

interface Props {
  username: string;
  messageCount: number;
}

/** 右板块环境 HUD — 空状态时显示动态系统读数，不显示"卡片放这里"占位文字 */
export default function AmbientHUD({ username, messageCount }: Props) {
  const sessionId = hash(username).toString(16).padStart(6, "0").toUpperCase().slice(0, 6);

  return (
    <div className="absolute inset-0 p-4 flex flex-col gap-4 pointer-events-none select-none">
      <HudClock />

      {/* 心电图条 */}
      <div className="mt-3 flex flex-col items-center gap-1.5">
        <div className="hud-label opacity-60">SIGNAL · STABLE</div>
        <svg className="hud-ekg" width="220" height="32" viewBox="0 0 220 32">
          <path d="M0,16 L30,16 L34,8 L38,24 L42,4 L46,28 L50,16 L90,16 L95,12 L100,20 L105,16 L160,16 L165,10 L170,22 L175,16 L220,16" />
        </svg>
      </div>

      {/* 数据栅格 */}
      <div className="mt-4 grid grid-cols-2 gap-3 px-2">
        <HudStat label="SESSION" value={sessionId} />
        <HudStat label="USER" value={(username || "ANON").slice(0, 8).toUpperCase()} />
        <HudStat label="MSGS" value={messageCount.toString().padStart(4, "0")} />
        <HudStat label="MODE" value="LIVE" pulse />
      </div>

      {/* 底部环境频谱（伪静态） */}
      <div className="mt-auto pb-2">
        <div className="hud-label opacity-60 mb-1.5 px-2">AMBIENT SPECTRUM</div>
        <AmbientSpectrum />
      </div>
    </div>
  );
}

function HudClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const time = now ? now.toLocaleTimeString("zh-CN", { hour12: false }) : "--:--:--";
  const date = now ? now.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }) : "----/--/--";
  const ms = now ? now.getMilliseconds().toString().padStart(3, "0") : "000";

  return (
    /* 大时钟 */
    <div className="flex flex-col items-center mt-6">
      <div className="hud-label opacity-60 mb-1">SYS · CLOCK</div>
      <div
        className="tabular-nums"
        style={{
          fontFamily: "var(--font-mono), 'SF Mono', Menlo, monospace",
          fontSize: 42,
          fontWeight: 300,
          letterSpacing: "0.08em",
          color: "var(--foreground)",
          textShadow: "0 0 10px color-mix(in srgb, var(--primary) 18%, transparent)",
          lineHeight: 1,
        }}
      >
        {time}
      </div>
      <div className="hud-label mt-2 opacity-60 tabular-nums">
        {date} · {ms}MS
      </div>
    </div>
  );
}

function AmbientSpectrum() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const seconds = now ? now.getSeconds() : 0;

  return (
    <div className="flex items-end gap-[3px] h-12 px-2">
      {Array.from({ length: 36 }).map((_, i) => {
        const h = 8 + Math.abs(Math.sin(i * 0.7 + seconds * 0.3)) * 28;
        return (
          <div
            key={i}
            className="flex-1 rounded-sm"
            style={{
              height: `${h}px`,
              background: "linear-gradient(180deg, color-mix(in srgb, var(--primary) 70%, transparent), color-mix(in srgb, var(--primary) 10%, transparent))",
              boxShadow: "0 0 2px color-mix(in srgb, var(--primary) 18%, transparent)",
              opacity: 0.4 + (i % 6) * 0.08,
            }}
          />
        );
      })}
    </div>
  );
}

function HudStat({ label, value }: { label: string; value: string; pulse?: boolean }) {
  return (
    <div
      className="px-2 py-1.5"
      style={{
        border: "1px solid var(--border)",
        background: "color-mix(in srgb, var(--primary) 3%, transparent)",
        clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))",
      }}
    >
      <div className="hud-label opacity-50 text-[8px]">{label}</div>
      <div
        style={{
          fontFamily: "var(--font-mono), 'SF Mono', Menlo, monospace",
          fontSize: 13,
          color: "var(--primary)",
          textShadow: "0 0 4px color-mix(in srgb, var(--primary) 24%, transparent)",
          letterSpacing: "0.05em",
        }}
      >
        {value}
      </div>
    </div>
  );
}

function hash(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i);
  return h >>> 0;
}
