"use client";

import { useEffect, useState } from "react";
import { brainProviderName, breakdownTaskLabel, formatBreakdownMoney, type BreakdownQuote, type BreakdownTask } from "@/lib/studio-breakdown";
import BreakdownDialog from "./BreakdownDialog";
import { quoteRemainingSeconds } from "./QuoteDialog";

export default function BreakdownQuoteDialog({ quote, retry = false, targetMin, targetMax, affectsApproved = false, replacesPartial = false, busy, onConfirm, onClose }: { quote: BreakdownQuote; retry?: boolean; targetMin?: number; targetMax?: number; affectsApproved?: boolean; replacesPartial?: boolean; busy: boolean; onConfirm: () => Promise<void>; onClose: () => void }) {
  const [remaining, setRemaining] = useState(() => quoteRemainingSeconds(quote.expires_at));
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const update = () => { const seconds = quoteRemainingSeconds(quote.expires_at); setRemaining(seconds); if (seconds > 0) timer = setTimeout(update, 1000); };
    timer = setTimeout(update, 1000);
    return () => clearTimeout(timer);
  }, [quote.expires_at]);
  return <BreakdownDialog title={retry ? "确认单批重跑报价" : "确认拆解报价"} confirmLabel={retry ? "确认重跑" : "确认开始"} busy={busy} disabled={remaining <= 0} onClose={onClose} onConfirm={async () => { if (quoteRemainingSeconds(quote.expires_at) <= 0) throw new Error("报价已过期，请重新报价。"); await onConfirm(); }}>
    {!retry && targetMin != null && targetMax != null && <p>每集目标时长将保存为 {targetMin}–{targetMax} 秒（确认开始时保存）。</p>}
    {!retry && affectsApproved && <p role="status">当前已批准方案的目标时长将发生变化。旧方案与 G0 状态保留至新方案发布；新方案发布后会退回待批准，需要重新批准。</p>}
    {!retry && replacesPartial && <p>上一次拆解未执行的批次将取消并释放预留。</p>}
    <p>导演模型：{brainProviderName(quote.provider)}</p><p>共 <span className="readout">{quote.total_chunks}</span> 批</p>
    <ul className="flex flex-wrap gap-2">{(["novel_complete", "text_map", "episode_plan", "synopsis"] as BreakdownTask[]).map(task => <li key={task} className="chip">{breakdownTaskLabel(task)} {quote.task_counts[task] ?? 0} 批</li>)}</ul>
    <p>预估费用 <span className="readout">{formatBreakdownMoney(quote.total_min, quote.currency)}–{formatBreakdownMoney(quote.total_max, quote.currency)}</span></p>
    <p role="status">{remaining > 0 ? `报价剩余有效时间 ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "报价已过期，请取消后重新报价"}</p>
  </BreakdownDialog>;
}
