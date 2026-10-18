"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "@/components/novel/NovelStates";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { studioErrorMessage } from "@/lib/studio";
import { getKbReviewProvider, kbReviewProviderLabel, kbReviewProviderOptions, setKbReviewProvider, type KbReviewProvider } from "@/lib/studio-kb";

const allowed: KbReviewProvider[] = ["claude", "qwen", "deepseek", "off"];

export default function ReviewProviderPicker({ projectId, owner, brainProvider, busy = false }: {
  projectId: string; owner: string; brainProvider: string; busy?: boolean;
}) {
  const [provider, setProvider] = useState<KbReviewProvider | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const load = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setLoading(true);
    try {
      const value = await getKbReviewProvider(projectId, request.signal);
      if (!request.isCurrent()) return;
      if (!allowed.includes(value.review_provider)) throw new Error("审核模型配置无法识别，请重新加载。");
      setProvider(value.review_provider); setError("");
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead, projectId]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const change = async (next: KbReviewProvider) => {
    if (busy || saving || !provider || provider === next) return;
    const request = beginMutation();
    if (!request) return;
    setSaving(true); setError("");
    try {
      const value = await setKbReviewProvider(projectId, next, request.signal);
      if (request.isCurrent()) setProvider(value.review_provider);
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setSaving(false); }
  };

  const same = provider != null && provider !== "off" && provider === brainProvider;
  const blocked = busy || saving;
  return <fieldset disabled={blocked} className="mt-4 min-w-0">
    <legend className="mb-2 text-sm">审核模型</legend>
    <p className="mb-2 max-w-[520px] text-xs leading-relaxed text-[color:var(--ink2)]">审核会把原文发给所选厂商。</p>
    {loading && provider == null ? <p role="status" className="text-sm text-[color:var(--ink2)]">正在读取审核模型…</p> : null}
    {provider != null && <label className="block max-w-[320px] min-w-0"><span className="sr-only">审核模型</span><select value={provider} disabled={blocked} onChange={event => { void change(event.target.value as KbReviewProvider); }} className={`${novelFieldClass} min-h-10 py-2`}>{kbReviewProviderOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>}
    {provider != null && <p className="mt-2 text-sm text-[color:var(--ink2)]">当前：{kbReviewProviderLabel(provider)}</p>}
    {same && <p className="mt-1 text-sm text-[color:var(--seal)]">同一模型自审，效果有限</p>}
    {error && <div className="mt-2"><ErrorNotice message={error} retry={() => { void load(); }} /></div>}
  </fieldset>;
}
