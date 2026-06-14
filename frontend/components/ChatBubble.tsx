"use client";

import { cn } from "@/lib/utils";
import { Volume2, VolumeX, Trash2, Globe } from "lucide-react";
import { useState, useEffect, useRef, useMemo } from "react";

// 打字机：把 target 按固定字符速率 (cps) 显示出来。
// 历史消息首次渲染时 initial 即 target，不会重放；只有当 target 在生命周期内"增长"才动画。
function useTypewriter(target: string, enabled: boolean, cps = 45) {
  const [shown, setShown] = useState(target);
  const targetRef = useRef(target);
  const cpsRef = useRef(cps);

  useEffect(() => {
    targetRef.current = target;
    cpsRef.current = cps;
  }, [target, cps]);

  useEffect(() => {
    if (!enabled) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      setShown((cur) => {
        const tgt = targetRef.current;
        if (cur === tgt) return cur;
        // 前缀失配（外部突然换了内容）→ 直接同步
        if (!tgt.startsWith(cur)) return tgt;
        const add = Math.max(1, Math.floor((dt / 1000) * cpsRef.current));
        // 防止落后过多（网络突然吐一大段时加速追赶，但不秒到）
        const lag = tgt.length - cur.length;
        const step = lag > 60 ? add + Math.floor(lag / 20) : add;
        const next = Math.min(tgt.length, cur.length + step);
        return tgt.slice(0, next);
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [enabled]);

  return enabled ? shown : target;
}

export interface WeatherForecastDay {
  day: string;        // "周三"
  date: string;       // "2026-05-16"
  high: string;       // "26"
  low: string;        // "17"
  condition: string;  // "晴"
  icon: string;       // weather icon URL
}

export interface WeatherData {
  location: string;
  currentTemp: string;
  feelsLike: string;
  condition: string;
  conditionIcon: string;
  humidity: string;
  windSpeed: string;
  visibility: string;
  forecast: WeatherForecastDay[];
}

export interface CardData {
  source: string;
  points: string[];
  url?: string;
  error?: boolean;
  subtype?: string;  // "weather" = 天气卡片专用渲染
  weather?: WeatherData;
}

export interface Message {
  id: string;
  dbId?: number;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  isTyping?: boolean;
  isDivider?: boolean;
  imageUrl?: string;
  cardData?: CardData;  // 网页卡片(fetch_card 意图)——非空时整条消息渲染为卡片
  pendingTtsText?: string;  // 搜索类回复待询问播报的文本；非空时气泡下方出现 [帮我读]/[不用] 按钮
}

interface ChatBubbleProps {
  message: Message;
  onDelete?: (id: string, dbId?: number) => void;
  onConfirmTts?: (id: string, text: string) => void;
  onDeclineTts?: (id: string) => void;
}

export default function ChatBubble({ message, onDelete, onConfirmTts, onDeclineTts }: ChatBubbleProps) {
  const isUser = message.role === "user";
  const [muted, setMuted] = useState(false);
  const [hovered, setHovered] = useState(false);

  // AI 消息走打字机，用户消息和分隔线直出
  const shownContent = useTypewriter(message.content, !message.isDivider && !isUser);
  const stillTyping = !isUser && shownContent !== message.content;
  const timeStr = useMemo(
    () => message.timestamp.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    }),
    [message.timestamp],
  );

  // 分隔线渲染
  if (message.isDivider) {
    return (
      <div className="flex items-center gap-3 py-2">
        <div className="flex-1 h-px bg-border" />
        <span className="text-[10px] text-muted-foreground/50 shrink-0">{message.content}</span>
        <div className="flex-1 h-px bg-border" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-start gap-2 max-w-[80%] group",
        isUser ? "ml-auto flex-row-reverse msg-in-right" : "msg-in-left"
      )}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="hud-avatar-ring shrink-0 mt-0.5">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center"
            style={{
              background: "radial-gradient(circle at 30% 30%, rgba(0,212,255,0.55), rgba(0,90,140,0.85))",
              boxShadow: "inset 0 0 8px rgba(0,212,255,0.5), 0 0 10px rgba(0,212,255,0.35)",
            }}
          >
            <span className="text-[#e0f6ff] text-xs font-semibold tracking-wider">C</span>
          </div>
        </div>
      )}

      <div className={cn("flex flex-col gap-1", isUser && "items-end")}>
        {/* 图片（如果有） */}
        {message.imageUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={message.imageUrl}
            alt="图片"
            className="rounded-2xl max-w-[260px] max-h-[260px] object-cover cursor-pointer hover:opacity-95 transition"
            onClick={() => window.open(message.imageUrl, "_blank", "noopener,noreferrer")}
          />
        )}

        {/* 天气卡片（weather subtype） */}
        {message.cardData?.subtype === "weather" && message.cardData.weather && (() => {
          const w = message.cardData.weather;
          return (
            <div className="w-[340px] max-w-full rounded-2xl overflow-hidden shadow-sm"
              style={{
                background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
                color: "#e0e0e0",
              }}
            >
              {/* 城市 + 当前状况 */}
              <div className="px-4 pt-4 pb-2 flex items-center justify-between">
                <div>
                  <div className="text-xs text-white/60">{w.location}</div>
                  <div className="text-3xl font-light text-white mt-1">{w.currentTemp}°</div>
                  <div className="text-xs text-white/50 mt-0.5">体感 {w.feelsLike}°</div>
                </div>
                <div className="text-right">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {w.conditionIcon && <img src={w.conditionIcon} alt={w.condition} className="w-12 h-12 -my-1 opacity-80" />}
                  <div className="text-sm text-white/70">{w.condition}</div>
                </div>
              </div>

              {/* 湿度/风速/能见度 */}
              <div className="px-4 pb-3 flex gap-3 text-[11px] text-white/40">
                <span>💧 {w.humidity}%</span>
                <span>🌬 {w.windSpeed}km/h</span>
                <span>👁 {w.visibility}km</span>
              </div>

              {/* 分割线 */}
              <div className="mx-4 h-px bg-white/10" />

              {/* 多日预报 */}
              <div className="px-2 py-2">
                {w.forecast.map((f, i) => (
                  <div key={i} className="flex items-center px-2 py-1.5">
                    <span className="text-xs text-white/60 w-10 shrink-0">{f.day}</span>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {f.icon && <img src={f.icon} alt={f.condition} className="w-5 h-5 mx-1 opacity-70" />}
                    <span className="text-xs text-white/40 flex-1 ml-1">{f.condition}</span>
                    <span className="text-xs text-white/70 tabular-nums">
                      <span className="text-white/40">{f.low}°</span>
                      {" "}
                      <span>{f.high}°</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

        {/* 网页卡片（fetch_card / web_search 通用） */}
        {message.cardData && message.cardData.subtype !== "weather" && message.cardData.points && message.cardData.points.length > 0 && (
          <div
            className={cn(
              "w-[340px] max-w-full rounded-2xl border border-border/60 bg-card/80 backdrop-blur-sm",
              "shadow-sm overflow-hidden"
            )}
          >
            <div className="flex items-center gap-1.5 px-4 pt-3 pb-2 border-b border-border/40">
              <Globe size={12} className={cn(
                message.cardData.error ? "text-orange-400" : "text-primary"
              )} />
              <span className="text-[11px] font-medium text-muted-foreground tracking-wide">
                {message.cardData.source || "网页"}
              </span>
              {message.cardData.url && (
                <span className="text-[10px] text-muted-foreground/50 truncate flex-1 ml-1">
                  {message.cardData.url.replace(/^https?:\/\//, "").slice(0, 40)}
                </span>
              )}
            </div>
            <ul className="px-4 py-3 space-y-1.5">
              {message.cardData.points.map((point, i) => (
                <li key={i} className="text-sm text-foreground/90 leading-relaxed flex gap-2">
                  <span className="text-primary/60 shrink-0 mt-1">•</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 文字气泡（如果有内容或正在打字，且不是卡片） */}
        {!message.cardData && (message.content || message.isTyping) && message.content !== "[发了一张图片]" && (
          <div
            className={cn(
              "px-4 py-2.5 text-sm leading-relaxed max-w-prose",
              isUser ? "bubble-user" : "bubble-ai",
              (message.isTyping || stillTyping) && "typing-cursor"
            )}
          >
            {isUser ? message.content : (shownContent || (message.isTyping ? "" : "…"))}
          </div>
        )}

        {/* 搜索类回复：询问是否播报 */}
        {!isUser && message.pendingTtsText && (
          <div className="flex gap-2 mt-1">
            <button
              onClick={() => onConfirmTts?.(message.id, message.pendingTtsText!)}
              className="hud-btn flex items-center gap-1.5 px-3 py-1 text-[11px]"
              style={{ clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))" }}
            >
              <Volume2 size={11} />
              <span className="hud-label">帮我读</span>
            </button>
            <button
              onClick={() => onDeclineTts?.(message.id)}
              className="text-[11px] px-3 py-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              不用
            </button>
          </div>
        )}

        {/* Meta row */}
        <div
          className={cn(
            "flex items-center gap-1.5 px-1",
            isUser ? "flex-row-reverse" : "flex-row"
          )}
        >
          <span className="hud-label text-[9px] opacity-70">{timeStr}</span>
          {!isUser && (
            <button
              onClick={() => setMuted(!muted)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={muted ? "播放语音" : "静音"}
            >
              {muted ? <VolumeX size={12} /> : <Volume2 size={12} />}
            </button>
          )}
          {/* 逐条删除按钮 hover 显示 */}
          {hovered && onDelete && !message.isTyping && (
            <button
              onClick={() => onDelete(message.id, message.dbId)}
              className="text-muted-foreground/50 hover:text-destructive transition-colors"
              title="删除这条消息"
            >
              <Trash2 size={11} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
