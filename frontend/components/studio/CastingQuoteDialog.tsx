"use client";

import { useEffect, useState } from "react";
import { castingLookQuoteLineLabel, castingQuoteKindLabel, formatCastingMoney, type CastingQuote } from "@/lib/studio-casting";
import BreakdownDialog from "./BreakdownDialog";
import { quoteRemainingSeconds } from "./QuoteDialog";

export default function CastingQuoteDialog({ quote, model, busy, onConfirm, onClose }: { quote: CastingQuote; model: string; busy: boolean; onConfirm: () => Promise<void>; onClose: () => void }) {
  const [remaining, setRemaining] = useState(() => quoteRemainingSeconds(quote.expires_at));
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const update = () => { const seconds = quoteRemainingSeconds(quote.expires_at); setRemaining(seconds); if (seconds > 0) timer = setTimeout(update, 1000); };
    timer = setTimeout(update, 1000);
    return () => clearTimeout(timer);
  }, [quote.expires_at]);
  const sheets = quote.kind === "casting_sheets";
  const looks = quote.kind === "casting_looks";
  return <BreakdownDialog title={`确认${castingQuoteKindLabel(quote.kind)}报价`} confirmLabel={sheets ? "确认出图" : looks ? "确认补全" : "确认生成"} busy={busy} disabled={remaining <= 0} onClose={onClose} onConfirm={async () => { if (quoteRemainingSeconds(quote.expires_at) <= 0) throw new Error("报价已过期，请重新报价。"); await onConfirm(); }}>
    <p>报价类型：{castingQuoteKindLabel(quote.kind)}</p>
    <p>模型：{model}</p>
    <ul className="min-w-0 space-y-2">{quote.items.map((line, index) => <li key={line.item_id ?? index} className="ceramic-card flex min-w-0 flex-wrap items-center justify-between gap-2 p-3">
      <span className="min-w-0 break-words">{looks ? castingLookQuoteLineLabel(line, index) : line.name}</span>
      <span className="readout">{looks ? formatCastingMoney(line.unit, quote.currency) : `${line.versions} 版 × ${formatCastingMoney(line.unit, quote.currency)}`} = <b>{formatCastingMoney(line.est, quote.currency)}</b></span>
    </li>)}</ul>
    <p>合计 <span className="readout"><b>{formatCastingMoney(quote.total, quote.currency)}</b></span></p>
    {sheets && <p className="text-fs-13 text-[color:var(--ink2)]">定妆图由 Seedream 5.0 生成，一律 2560×1440，一图两区：三视图 + 细节栏，纯白背景。</p>}
    {looks && <p className="text-fs-13 text-[color:var(--ink2)]">导演模型补全造型说明</p>}
    <p role="status">{remaining > 0 ? `报价剩余有效时间 ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "报价已过期，请取消后重新报价"}</p>
  </BreakdownDialog>;
}
