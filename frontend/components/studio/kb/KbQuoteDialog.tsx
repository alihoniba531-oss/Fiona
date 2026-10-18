"use client";

import { useEffect, useState } from "react";
import { formatCastingMoney } from "@/lib/studio-casting";
import type { KbQuote } from "@/lib/studio-kb";
import BreakdownDialog from "../BreakdownDialog";
import { quoteRemainingSeconds } from "../QuoteDialog";

function quoteTotalText(quote: KbQuote): string {
  if (quote.currency === "mixed") {
    const parts = (["CNY", "USD"] as const)
      .filter(currency => quote.totals[currency] > 0)
      .map(currency => formatCastingMoney(quote.totals[currency], currency));
    return parts.length > 0 ? parts.join(" + ") : formatCastingMoney(0, "CNY");
  }
  return formatCastingMoney(quote.total ?? quote.totals[quote.currency], quote.currency);
}

export default function KbQuoteDialog({ quote, busy, onConfirm, onClose }: {
  quote: KbQuote; busy: boolean; onConfirm: () => Promise<void>; onClose: () => void;
}) {
  const [remaining, setRemaining] = useState(() => quoteRemainingSeconds(quote.expires_at));
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
  return <BreakdownDialog title="确认试拆报价" confirmLabel="确认开始试拆" busy={busy} disabled={remaining <= 0} onClose={onClose} onConfirm={async () => { if (quoteRemainingSeconds(quote.expires_at) <= 0) throw new Error("报价已过期，请重新报价。"); await onConfirm(); }}>
    <p>报价类型：试拆对比</p>
    <p>同一场戏拆两次：带知识库、不带知识库。审核费用按项目当前的审核模型一并计入。</p>
    <ul className="min-w-0 space-y-2">{quote.items.map((line, index) => <li key={line.item_id ?? index} className="ceramic-card flex min-w-0 flex-wrap items-center justify-between gap-2 p-3">
      <span className="min-w-0 break-words">{line.name}</span>
      <span className="readout">{typeof line.versions === "number" ? `${line.versions} 版 × ${formatCastingMoney(line.unit ?? 0, line.currency)} = ` : ""}{formatCastingMoney(line.est, line.currency)}</span>
    </li>)}</ul>
    <p>合计 <span className="readout">{quoteTotalText(quote)}</span></p>
    <p role="status">{remaining > 0 ? `报价剩余有效时间 ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "报价已过期，请取消后重新报价"}</p>
  </BreakdownDialog>;
}
