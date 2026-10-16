"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ErrorNotice } from "@/components/novel/NovelStates";
import { studioErrorMessage, studioModelLabel, type StudioQuote } from "@/lib/studio";

export function quoteRemainingSeconds(expiresAt: string, now = Date.now()): number {
  const expires = new Date(expiresAt).getTime();
  return Number.isFinite(expires) ? Math.max(0, Math.ceil((expires - now) / 1000)) : 0;
}

export default function QuoteDialog({ quote, busy = false, onConfirm, onClose }: { quote: StudioQuote; busy?: boolean; onConfirm: () => Promise<void>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const locked = useRef(false);
  const titleId = useId();
  const [remaining, setRemaining] = useState(() => quoteRemainingSeconds(quote.expires_at));
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const disabled = busy || confirming;
  const expired = remaining <= 0;
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => { dialog?.close(); }; }, []);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const update = () => {
      if (cancelled) return;
      const seconds = quoteRemainingSeconds(quote.expires_at);
      setRemaining(seconds);
      if (seconds > 0) timer = setTimeout(update, 1000);
    };
    timer = setTimeout(update, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [quote.expires_at]);

  const confirm = async () => {
    if (locked.current || disabled || quoteRemainingSeconds(quote.expires_at) <= 0) return;
    locked.current = true;
    setConfirming(true);
    setError("");
    try { await onConfirm(); }
    catch (cause) { setError(studioErrorMessage(cause)); }
    finally { locked.current = false; setConfirming(false); }
  };

  return <dialog ref={ref} aria-labelledby={titleId} onCancel={event => { if (disabled) event.preventDefault(); else onClose(); }} className="m-auto max-h-[85dvh] w-[min(620px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] p-6 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)] mobile:p-4">
    <h2 id={titleId} className="mb-5 text-xl tracking-[.24em]">确认试拍报价</h2>
    <div className="space-y-4 text-[14px] leading-[1.9]">
      {quote.items.map((item, index) => <div key={item.id ?? index} className="ceramic-card flex min-w-0 flex-wrap gap-2 p-3"><span className="chip">{studioModelLabel(item.params.model ?? item.params.provider)}</span><span className="chip">{item.params.resolution.toUpperCase()}</span><span className="chip">{item.params.duration === -1 ? `${item.params.duration_min_s}–${item.params.duration_max_s}` : item.params.duration} 秒</span><span className="chip">音频{item.params.audio ? "开" : "关"}</span></div>)}
      <p>预估区间 <span className="readout">¥{quote.total_min_cny.toFixed(2)}–¥{quote.total_max_cny.toFixed(2)}</span></p>
      <p>今日剩余额度 <span className="readout">¥{quote.today.remaining_cny.toFixed(2)}</span></p>
      {!expired && <p>报价剩余有效时间 <span className="readout">{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}</span></p>}
      <p role="status" aria-live="polite">{expired ? "报价已过期，请重新报价" : ""}</p>
      {error && <ErrorNotice message={error} />}
    </div>
    <div className="mt-6 flex min-w-0 flex-wrap justify-end gap-3"><button type="button" className="btn btn-quiet min-h-10" disabled={disabled} onClick={onClose}>取消</button><button type="button" className="btn btn-primary min-h-10 max-w-full whitespace-normal" disabled={disabled || expired} onClick={() => void confirm()}>{expired ? "报价已过期，请重新报价" : confirming ? "确认中…" : `确认生成（最多 ¥${quote.total_max_cny.toFixed(2)}）`}</button></div>
  </dialog>;
}
