"use client";

import { cn } from "@/lib/utils";
import { Volume2, VolumeX, Trash2, Globe, LoaderCircle, RotateCcw } from "lucide-react";
import { memo, useState, useEffect, useRef, useMemo } from "react";
import GeneratedImage from "@/components/GeneratedImage";
import { generatedImagePath, referenceImagePath, storedReferenceImagePaths, isLocalReferenceDataUrl, type ReferenceImageInput } from "@/lib/generatedImages";
import { API_BASE as API } from "@/lib/config";

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
        // 前缀失配（外部突然换了内容）时直接同步
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
  items?: { title: string; url?: string }[];
  sources?: { title: string; url: string }[];
}

export type ImageAspectRatio = "1:1" | "16:9" | "9:16";

export interface ImageGenerationRetry {
  prompt: string;
  aspectRatio?: ImageAspectRatio;
  referenceImages?: ReferenceImageInput[];
  conversationId: string;
  owner: string;
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
  referenceImageUrls?: string[];
  localReferenceImageUrls?: string[];
  generatedImage?: { width: number; height: number; model: string };
  generationStatus?: string;
  imageGenerationRetry?: ImageGenerationRetry;
  cardData?: CardData;  // 网页卡片(fetch_card 意图)——非空时整条消息渲染为卡片
  pendingTtsText?: string;  // 搜索类回复待询问播报的文本；非空时气泡下方出现 [帮我读]/[不用] 按钮
}

interface ChatBubbleProps {
  message: Message;
  agentName?: string;
  agentAvatar?: string;
  onDelete?: (id: string, dbId?: number) => void;
  onConfirmTts?: (id: string, text: string) => void;
  onDeclineTts?: (id: string) => void;
  onRetryImage?: (request: ImageGenerationRetry) => void;
  imageRetryDisabled?: boolean;
  onEditImage?: (imageUrl: string) => void;
  selectedReferenceImagePaths?: string[];
}

function ChatBubble({ message, agentName = "Chloe", agentAvatar = "✨", onDelete, onConfirmTts, onDeclineTts, onRetryImage, imageRetryDisabled, onEditImage, selectedReferenceImagePaths = [] }: ChatBubbleProps) {
  const isUser = message.role === "user";
  const referenceUrls = useMemo(() => {
    if (!isUser) return [];
    if (message.referenceImageUrls?.length) return message.referenceImageUrls.flatMap(url => {
      const path = referenceImagePath(url);
      if (path) return [`${API}${path}`];
      return message.localReferenceImageUrls?.includes(url) && isLocalReferenceDataUrl(url) ? [url] : [];
    }).slice(0, 3);
    return storedReferenceImagePaths(undefined, message.imageUrl).map(path => `${API}${path}`);
  }, [isUser, message.referenceImageUrls, message.localReferenceImageUrls, message.imageUrl]);
  const imagePath = generatedImagePath(message.imageUrl);
  const selectedReferenceIndex = imagePath ? selectedReferenceImagePaths.indexOf(imagePath) + 1 : 0;
  const referenceLimitReached = selectedReferenceImagePaths.length >= 3;
  const editDisabled = imageRetryDisabled || selectedReferenceIndex > 0 || referenceLimitReached;
  const editLabel = selectedReferenceIndex ? `已选为图${selectedReferenceIndex}` : selectedReferenceImagePaths.length ? "加入参考" : "以此图修改";
  const editDisabledReason = selectedReferenceIndex ? `已选为图${selectedReferenceIndex}，可在输入区移除或调整顺序`
    : referenceLimitReached ? "最多选择3张参考图，请先在输入区移除一张" : undefined;
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
        "group flex items-start gap-2",
        isUser ? "ml-auto max-w-[520px] flex-row-reverse msg-in-right max-md:max-w-full" : "max-w-[640px] msg-in-left max-md:w-full max-md:max-w-full"
      )}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-[6px] bg-secondary text-sm" title={`${agentName} · AI 分身`}>
          {agentAvatar}
        </div>
      )}

      <div className={cn("flex min-w-0 flex-col gap-1.5", isUser ? "items-end" : "max-md:flex-1")}>
        {!isUser && <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-block h-1.5 w-1.5" style={{ background: "var(--amber-ink)" }} />
          {agentName}
        </div>}

        {/* 图片（如果有） */}
        {message.imageUrl && !isUser && <GeneratedImage key={message.imageUrl} imageUrl={message.imageUrl} width={message.generatedImage?.width} height={message.generatedImage?.height}
          onEdit={onEditImage && imagePath ? () => onEditImage(message.imageUrl!) : undefined} editDisabled={editDisabled}
          editLabel={editLabel} editDisabledReason={editDisabledReason} editSelected={selectedReferenceIndex > 0} />}
        {referenceUrls.length > 0 && <div className="flex max-w-full flex-wrap justify-end gap-2" aria-label="本次修改的参考图片">
          {referenceUrls.map((url, index) => <GeneratedImage key={`${index}:${referenceImagePath(url) || "local"}`} imageUrl={url} variant="reference" referenceIndex={index + 1}
            localPreview={message.localReferenceImageUrls?.includes(url)} />)}
        </div>}
        {message.imageUrl && isUser && referenceUrls.length === 0 && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={message.imageUrl}
            alt="图片"
            className="max-h-[260px] max-w-[260px] cursor-pointer rounded-[10px] object-cover transition hover:opacity-95 max-md:max-w-full"
            onClick={() => window.open(message.imageUrl, "_blank", "noopener,noreferrer")}
          />
        )}

        {message.generationStatus && <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle size={16} className="shrink-0 animate-spin" />{message.generationStatus}
        </div>}

        {/* 文字气泡（如果有内容或正在打字，且不是卡片） */}
        {!message.generationStatus && (message.content || message.isTyping) && message.content !== "[发了一张图片]" && (
          <div
            className={cn(
              "break-words whitespace-pre-wrap text-sm",
              isUser ? "bubble-user max-w-[520px] max-md:max-w-full" : "bubble-ai max-w-[640px] max-md:w-full max-md:max-w-full",
              (message.isTyping || stillTyping) && "typing-cursor"
            )}
          >
            {isUser ? message.content : (shownContent || (message.isTyping ? "" : "…"))}
          </div>
        )}

        {/* 天气卡片（weather subtype） */}
        {message.cardData?.subtype === "weather" && message.cardData.weather && (() => {
          const w = message.cardData.weather;
          return (
            <div className="glass-card w-[320px] max-w-full overflow-hidden">
              <div className="flex items-center justify-between border-b px-3.5 py-2 text-xs" style={{ borderColor: "var(--glass-border)" }}>
                <b className="font-medium">天气</b>
                <span className="text-muted-foreground">{w.location}</span>
              </div>
              <div className="flex items-center gap-3.5 px-3.5 py-3">
                <span className="readout" style={{ fontSize: 32, color: "var(--foreground)" }}>{w.currentTemp}°</span>
                <div>
                  <div>{w.condition}</div>
                  <div className="text-xs text-muted-foreground">体感 <span className="readout">{w.feelsLike}°</span>　湿度 <span className="readout">{w.humidity}%</span></div>
                </div>
              </div>
              <div className="grid grid-cols-3 border-t" style={{ borderColor: "var(--glass-border)" }}>
                {w.forecast.slice(0, 3).map((f, i) => (
                  <div key={i} className="flex flex-col gap-0.5 px-3.5 py-2 text-xs text-muted-foreground" style={{ borderLeft: i > 0 ? "1px solid var(--glass-border)" : undefined }}>
                    <span>{f.day}</span>
                    <span className="readout" style={{ color: "var(--foreground)" }}>{f.low}° {f.high}°</span>
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
              "glass-card w-[340px] max-w-full",
              "overflow-hidden"
            )}
          >
            <div className="flex items-center gap-1.5 border-b px-4 pb-2 pt-3" style={{ borderColor: "var(--glass-border)" }}>
              <Globe size={12} style={{ color: "var(--amber-ink)" }} />
              <span className="text-[11px] font-medium text-muted-foreground">
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
                  <span className="mt-1 shrink-0" style={{ color: "var(--amber-ink)" }}>•</span>
                  <span className="max-md:min-w-0 max-md:break-words">{point}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {message.imageGenerationRetry && onRetryImage && <button type="button"
          disabled={imageRetryDisabled}
          title={imageRetryDisabled ? "请等待当前操作完成，并移除待发送的图片后重试" : message.imageGenerationRetry.referenceImages?.length ? "使用原参考图顺序和修改要求重试" : "使用相同的描述和比例重新生成"}
          onClick={() => onRetryImage(message.imageGenerationRetry!)}
          className="btn h-7 self-start px-2.5 text-xs">
          <RotateCcw size={12} />{message.imageGenerationRetry.referenceImages?.length ? "重新修改" : "重新生成"}
        </button>}

        {/* 搜索类回复：询问是否播报 */}
        {!isUser && message.pendingTtsText && (
          <div className="flex gap-2 mt-1">
            <button
              onClick={() => onConfirmTts?.(message.id, message.pendingTtsText!)}
              className="btn btn-quiet h-7 px-2.5 text-xs"
            >
              <Volume2 size={11} />
              <span>帮我读</span>
            </button>
            <button
              onClick={() => onDeclineTts?.(message.id)}
              className="btn btn-quiet h-7 px-2.5 text-xs"
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
          <span className="readout text-[11px]">{timeStr}</span>
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

export default memo(ChatBubble);
