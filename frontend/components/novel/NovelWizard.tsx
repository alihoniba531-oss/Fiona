"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Loader2 } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import InkLandscape from "@/components/InkLandscape";
import Glaze from "@/components/Glaze";
import NovelModelFields, { novelFieldClass } from "@/components/novel/NovelModelFields";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useNovelEmbedClose } from "@/components/novel/NovelShell";
import { createNovel, estimateNovel, getNovelBalance, getNovelCatalog, novelErrorMessage, novelHref, novelModelLabel, novelModelOptions, type NovelAutomation, type NovelCatalog, type NovelCreateInput, type NovelEstimate, type NovelPanelMode } from "@/lib/novels";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

type FieldErrors = Record<string, string>;
const steps = ["思路与篇幅", "智能体与模型", "节奏与预算"];
const rangeError = (value: number, min: number, max: number) => !Number.isInteger(value) || value < min || value > max;

export function defaultNovelAgents(catalog: NovelCatalog): Record<string, string> {
  const preferredModels: Record<string, string> = {
    editor: "dashscope:qwen3.8-max",
    writer: "deepseek:deepseek-flash",
    archivist: "dashscope:qwen3.8-max",
    reviewer: "dashscope:qwen3.8-max",
    plot_architect: "dashscope:qwen3.8-max",
    character_advocate: "ark:doubao-seed-2-1-pro-260915",
    twist_designer: "deepseek:deepseek-flash",
  };
  const defaultAdvisors = ["plot_architect", "character_advocate", "twist_designer"];
  return Object.fromEntries(catalog.agents
    .filter(agent => agent.required || agent.id === "reviewer" || defaultAdvisors.includes(agent.id))
    .map(agent => {
      const options = novelModelOptions(catalog, agent.id);
      const preferred = preferredModels[agent.id];
      return [agent.id, options.some(option => option.value === preferred) ? preferred : options[0]?.value ?? ""];
    }));
}

export default function NovelWizard() {
  const embedded = useSearchParams().get("embed") === "1";
  const owner = useAccountIdentity();
  return <Wizard key={owner} owner={owner} embedded={embedded} />;
}
function Wizard({ owner, embedded }: { owner: string; embedded: boolean }) {
  useNovelEmbedClose(embedded);
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [catalog, setCatalog] = useState<NovelCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [balance, setBalance] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState("");
  const [minChapters, setMinChapters] = useState("50");
  const [maxChapters, setMaxChapters] = useState("70");
  const [chapterWords, setChapterWords] = useState("2000");
  const [mainCharacters, setMainCharacters] = useState("6");
  const [scenes, setScenes] = useState("3");
  const [dramaAdaptation, setDramaAdaptation] = useState(false);
  const [adaptationOpen, setAdaptationOpen] = useState(false);
  const [adaptationAdvisorError, setAdaptationAdvisorError] = useState("");
  const [agents, setAgents] = useState<Record<string, string>>({});
  const [panelMode, setPanelMode] = useState<NovelPanelMode>("critique");
  const [automation, setAutomation] = useState<NovelAutomation>("per_batch");
  const [batch, setBatch] = useState("5");
  const [budget, setBudget] = useState("10000");
  const [estimate, setEstimate] = useState<NovelEstimate | null>(null);
  const [estimateError, setEstimateError] = useState("");
  const [estimating, setEstimating] = useState(false);
  const dataRequest = useAccountRequest(owner);
  const costRequest = useAccountRequest(owner);
  const mutationRequest = useAccountRequest(owner);
  const beginData = dataRequest.beginRequest;
  const beginCost = costRequest.beginRequest;
  const estimateInput = useMemo<Omit<NovelCreateInput, "budget_strawberries">>(() => ({
    seed_idea: seed.trim(), agents: Object.fromEntries(Object.entries(agents).filter(([role]) => panelMode === "critique" || ["editor", "writer", "archivist", "reviewer"].includes(role))),
    panel_mode: panelMode, automation, batch_size: Number(batch),
    target: { min_chapters: Number(minChapters), max_chapters: Number(maxChapters), chapter_words: Number(chapterWords) },
    adaptation: { max_main_characters: Number(mainCharacters), max_scenes_per_chapter: Number(scenes) },
    drama_adaptation: dramaAdaptation,
  }), [seed, agents, panelMode, automation, batch, minChapters, maxChapters, chapterWords, mainCharacters, scenes, dramaAdaptation]);
  const input = useMemo<NovelCreateInput>(() => ({ ...estimateInput, budget_strawberries: Number(budget) }), [estimateInput, budget]);
  const load = useCallback(async () => {
    const request = beginData();
    if (!request) return;
    try {
      const [nextCatalog, account] = await Promise.all([getNovelCatalog(request.signal), getNovelBalance(request.signal)]);
      if (!request.isCurrent()) return;
      if (account.username !== owner) throw new Error("账号已变化，请重新打开建书向导。");
      setCatalog(nextCatalog); setBalance(account.balance); setError("");
      setAgents(current => Object.keys(current).length ? current : defaultNovelAgents(nextCatalog));
    } catch (cause) {
      if (request.isCurrent()) setError(novelErrorMessage(cause, true));
    } finally { if (request.isCurrent()) setLoading(false); }
  }, [beginData, owner]);
  useEffect(() => {
    const timer = setTimeout(() => { void load(); }, 0);
    return () => clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    if (step !== 2 || !catalog) return;
    let current = true;
    const timer = setTimeout(async () => {
      const request = beginCost();
      if (!request) return;
      setEstimating(true); setEstimateError("");
      try {
        // The estimate endpoint requires a budget field but pricing never uses it.
        const cost = await estimateNovel({ ...estimateInput, budget_strawberries: 1 }, request.signal);
        if (current && request.isCurrent()) setEstimate(cost);
      } catch (cause) { if (current && request.isCurrent()) { setEstimate(null); setEstimateError(novelErrorMessage(cause)); } }
      finally { if (current && request.isCurrent()) setEstimating(false); }
    }, 600);
    return () => { current = false; clearTimeout(timer); };
  }, [step, catalog, estimateInput, beginCost]);
  const validate = (at: number): FieldErrors => {
    const next: FieldErrors = {};
    if (at === 0) {
      if (!seed.trim() || seed.length > 2000) next.seed = "请填写 1–2000 字的故事思路。";
      if (rangeError(Number(minChapters), 1, 200)) next.minChapters = "最少章数须为 1–200 的整数。";
      if (rangeError(Number(maxChapters), 1, 200)) next.maxChapters = "最多章数须为 1–200 的整数。";
      else if (Number(minChapters) > Number(maxChapters)) next.maxChapters = "最少章数不得大于最多章数。";
      if (rangeError(Number(chapterWords), 1000, 4000)) next.chapterWords = "每章字数须为 1000–4000 的整数。";
      if (rangeError(Number(mainCharacters), 1, 12)) next.mainCharacters = "主要人物上限须为 1–12 的整数。";
      if (rangeError(Number(scenes), 1, 10)) next.scenes = "每章场景上限须为 1–10 的整数。";
    } else if (at === 1) {
      if (!catalog) next.agents = "请等待模型目录加载完成。";
      else {
        for (const role of ["editor", "writer", "archivist"]) if (!input.agents[role]) next.agents = "必须选择主编、写手和档案员。";
        const advisorCount = Object.keys(input.agents).filter(role => !["editor", "writer", "archivist", "reviewer"].includes(role)).length;
        if (advisorCount > 5) next.agents = "推演顾问最多选择 5 位。";
        for (const [role, model] of Object.entries(input.agents)) if (!novelModelOptions(catalog, role).some(option => option.value === model)) next.agents = "有模型已不可用，请重新选择。";
      }
    } else {
      if (rangeError(Number(budget), 1, 10000000)) next.budget = "预算须为 1–10000000 的整数。";
      else if (estimate && Number(budget) < estimate.per_chapter.min) next.budget = "预算低于估算下限的一章份额，请调高预算。";
      if (rangeError(Number(batch), 1, 10)) next.batch = "每批章数须为 1–10 的整数。";
    }
    return next;
  };
  const nextStep = () => {
    const next = validate(step); setErrors(next); setError("");
    if (!Object.keys(next).length) {
      if (step === 1) { setEstimate(null); setEstimateError(""); setEstimating(false); }
      setStep(current => current + 1);
    }
  };
  const submit = async () => {
    if (busy) return;
    for (let at = 0; at < 3; at += 1) { const next = validate(at); if (Object.keys(next).length) { setErrors(next); setStep(at); return; } }
    const request = mutationRequest.beginRequest();
    if (!request) return;
    setBusy(true); setError("");
    try {
      const book = await createNovel(input, request.signal);
      if (request.isCurrent()) router.push(novelHref(`/novels/${book.id}`, embedded));
    } catch (cause) { if (request.isCurrent()) setError(novelErrorMessage(cause)); }
    finally { if (request.isCurrent()) setBusy(false); }
  };
  const toggleDramaAdaptation = (enabled: boolean) => {
    setDramaAdaptation(enabled); setAdaptationAdvisorError("");
    if (!enabled) return;
    setAdaptationOpen(true);
    if (!catalog || agents.adaptation_advisor) return;
    const advisors = Object.keys(agents).filter(role => !["editor", "writer", "archivist", "reviewer"].includes(role) && agents[role]);
    if (advisors.length >= 5) {
      setAdaptationAdvisorError("顾问已满 5 位，先取消一位才能加入短剧改编顾问");
      return;
    }
    setAgents(current => ({ ...current, adaptation_advisor: novelModelOptions(catalog, "adaptation_advisor")[0]?.value ?? "" }));
  };
  const fieldError = (field: string) => errors[field] ? <p id={`novel-error-${field}`} role="alert" className="mt-1 text-[13px] leading-[1.8] text-[color:var(--ink)]">{errors[field]}</p> : null;
  const numeric = (id: string, label: string, value: string, change: (value: string) => void, min: number, max: number) => <div className="min-w-0"><label htmlFor={`novel-${id}`} className="mb-2 block text-[14px]">{label}</label><input id={`novel-${id}`} type="number" inputMode="numeric" min={min} max={max} step="1" value={value} onChange={event => { change(event.target.value); setErrors(current => ({ ...current, [id]: "" })); }} aria-invalid={!!errors[id]} aria-describedby={errors[id] ? `novel-error-${id}` : undefined} className={novelFieldClass} />{fieldError(id)}</div>;
  return <div className={`relative flex min-w-0 ${embedded ? "min-h-full" : "h-dvh"} overflow-hidden`}>
    {!embedded && <><InkLandscape variant="page" /><Sidebar /></>}
    <main className={`relative z-[1] min-w-0 flex-1 overflow-y-auto text-[color:var(--ink)] ${embedded ? "" : "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]"}`}>
      <div className="mx-auto max-w-[900px] px-9 pb-12 pt-6 mobile:px-4 mobile:pt-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><Link href={novelHref("/novels", embedded)} className="inline-flex min-h-10 items-center gap-1 text-[13px] text-[color:var(--ink2)]"><ArrowLeft size={14} />回到书架</Link>{embedded && <a href="/novels/new" target="_blank" rel="noopener noreferrer" className="btn btn-quiet min-h-10 mobile:hidden">在新页面打开</a>}</div>
        <h1 className="text-[28px] tracking-[.24em]">新建一本</h1>
        <ol aria-label="建书步骤" className="my-6 grid grid-cols-3 gap-2 border-b border-[color:var(--carve)] pb-5 mobile:gap-1">{steps.map((label, index) => <li key={label} aria-current={index === step ? "step" : undefined} className={`flex min-w-0 flex-wrap items-center gap-2 text-[14px] mobile:gap-1 mobile:text-[12px] ${index === step ? "text-[color:var(--ink)]" : "text-[color:var(--ink2)]"}`}><span className={`chip readout ${index === step ? "chip-on" : ""}`}>{index < step ? <Check size={12} /> : index + 1}</span><span>{label}</span></li>)}</ol>
        {!owner ? <EmptyState>请登录后新建小说。</EmptyState> : loading ? <LoadingState>正在加载智能体、模型和草莓余额…</LoadingState> : !catalog ? <ErrorNotice message={error || "模型目录暂不可用。"} retry={() => void load()} /> : <>
          {error && <div className="mb-4"><ErrorNotice message={error} /></div>}
          <Glaze variant="panel" lens={false} backdrop={!embedded} className="rounded-[18px] p-7 mobile:p-4">
            <form onSubmit={event => { event.preventDefault(); if (step < 2) nextStep(); else void submit(); }}>
              <fieldset disabled={busy} className="min-w-0">
                {step === 0 && <div className="space-y-6">
                  <div><label htmlFor="novel-seed" className="mb-2 block text-[16px]">故事思路</label><textarea id="novel-seed" rows={6} maxLength={2000} value={seed} onChange={event => { setSeed(event.target.value); setErrors(current => ({ ...current, seed: "" })); }} aria-invalid={!!errors.seed} aria-describedby="novel-seed-count novel-error-seed" placeholder="一位替亡人修补家书的年轻匠人，在一封没有署名的信里，发现了自己尚未经历的明天。" className={`${novelFieldClass} resize-y`} /><p id="novel-seed-count" className="readout mt-1 text-right text-[12px] text-[color:var(--ink2)]">{seed.length} / 2000 字</p>{fieldError("seed")}</div>
                  <div className="grid grid-cols-3 gap-4 mobile:grid-cols-1">{numeric("minChapters", "最少章数", minChapters, setMinChapters, 1, 200)}{numeric("maxChapters", "最多章数", maxChapters, setMaxChapters, 1, 200)}{numeric("chapterWords", "每章字数", chapterWords, setChapterWords, 1000, 4000)}</div>
                  <div className="min-w-0 space-y-2"><label className="flex min-h-10 items-center gap-2 text-[16px]"><input type="checkbox" checked={dramaAdaptation} onChange={event => toggleDramaAdaptation(event.target.checked)} aria-describedby="novel-drama-help" className="h-5 w-5 shrink-0 accent-[color:var(--ink)]" />这本书要改编成短剧</label><p id="novel-drama-help" className="text-[13px] leading-[1.85] text-[color:var(--ink2)]">{panelMode === "solo" ? "主编独自构思时不请顾问参会；审校仍会按「场景太多、主要人物太多」这类硬伤要求重写。" : "勾选后会请短剧改编顾问参会；审校发现「场景太多、主要人物太多」这类不好拍的硬伤时，会要求重写。每章可能多花一些草莓。"}</p>{adaptationAdvisorError && <ErrorNotice message={adaptationAdvisorError} />}</div>
                  <details open={adaptationOpen} onToggle={event => setAdaptationOpen(event.currentTarget.open)}><summary className="flex min-h-10 cursor-pointer items-center text-[14px] text-[color:var(--ink2)]">改编参数（可选，展开调整）</summary><div className="mt-3 grid grid-cols-2 gap-4 mobile:grid-cols-1">{numeric("mainCharacters", "主要人物上限", mainCharacters, setMainCharacters, 1, 12)}{numeric("scenes", "每章场景上限", scenes, setScenes, 1, 10)}</div></details>
                </div>}
                {step === 1 && <>
                  <fieldset className="min-w-0"><legend className="mb-2 text-[16px]">推演方式</legend><div className="space-y-2">{([{ value: "critique", label: "主编出方案、顾问挑错" }, { value: "solo", label: "主编独自构思" }] as const).map(option => <label key={option.value} className="flex min-h-10 items-center gap-2 text-[14px]"><input type="radio" name="panel-mode" value={option.value} checked={panelMode === option.value} onChange={() => setPanelMode(option.value)} className="h-5 w-5 accent-[color:var(--ink)]" />{option.label}</label>)}</div></fieldset>
                  {fieldError("agents")}<NovelModelFields catalog={catalog} agents={agents} panelMode={panelMode} allowRoleChanges onChange={next => { setAgents(next); setAdaptationAdvisorError(""); setErrors(current => ({ ...current, agents: "" })); }} disabled={busy} />
                </>}
                {step === 2 && <div className="space-y-6">
                  <fieldset><legend className="mb-2 text-[16px]">自动化方式</legend><div className="space-y-2">{([{ value: "per_batch", label: "每写 N 章停下来给我看" }, { value: "per_chapter", label: "每章先给我看细纲" }, { value: "full_auto", label: "全自动写到完结" }] as const).map(option => <label key={option.value} className="flex min-h-10 items-center gap-2 text-[14px]"><input type="radio" name="automation" checked={automation === option.value} onChange={() => setAutomation(option.value)} className="h-5 w-5 accent-[color:var(--ink)]" />{option.label}</label>)}</div></fieldset>
                  {automation === "per_batch" && numeric("batch", "每批章数 N", batch, setBatch, 1, 10)}
                  <div className="grid grid-cols-2 items-start gap-5 mobile:grid-cols-1">{numeric("budget", "本书预算（草莓）", budget, setBudget, 1, 10000000)}<div className="pt-1 text-[14px] leading-[1.95]"><p>当前余额 <span className="readout">{balance ?? "—"}</span> 草莓</p><div aria-live="polite">{estimating && <LoadingState>正在估算…</LoadingState>}{estimate && <><p>每章约 <span className="readout">{estimate.per_chapter.min}–{estimate.per_chapter.max}</span> 草莓</p><p>整本约 <span className="readout">{estimate.total.min}–{estimate.total.max}</span> 草莓</p></>}{!estimate && !estimating && !estimateError && <p className="text-[color:var(--ink2)]">等待估算…</p>}{estimateError && <ErrorNotice message={estimateError} />}</div><p className="mt-2 text-[12px] text-[color:var(--ink2)]">估算口径：近 20 次调用均值或基线，±20%</p></div></div>
                  <section className="border-t border-[color:var(--carve)] pt-5" aria-label="提交前汇总确认"><h2 className="mb-3 text-[18px] tracking-[.12em]">确认这本书</h2><dl className="space-y-3 text-[14px] leading-[1.9]"><div><dt className="text-[color:var(--ink2)]">思路摘要</dt><dd className="whitespace-pre-wrap break-words">{seed.length > 180 ? `${seed.slice(0, 180)}…` : seed}</dd></div><div><dt className="text-[color:var(--ink2)]">智能体和模型</dt><dd><ul className="space-y-1">{Object.entries(input.agents).map(([role, model]) => <li key={role} className="break-words">{catalog.agents.find(agent => agent.id === role)?.name ?? role} · {model === "byok:self" && catalog.byok ? `我的模型（${catalog.byok.provider}·${catalog.byok.model}）· 不扣草莓` : novelModelLabel(model)}</li>)}</ul></dd></div><div><dt className="text-[color:var(--ink2)]">改编短剧</dt><dd>{dramaAdaptation ? "是" : "否"}</dd></div><div><dt className="text-[color:var(--ink2)]">篇幅</dt><dd className="readout">{minChapters}–{maxChapters} 章 · 每章 {chapterWords} 字</dd></div><div><dt className="text-[color:var(--ink2)]">节奏与预算</dt><dd>{automation === "per_batch" ? `每 ${batch} 章审阅` : automation === "per_chapter" ? "每章先确认细纲" : "全自动写到完结"} · <span className="readout">{budget}</span> 草莓</dd></div></dl></section>
                </div>}
                <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--carve)] pt-5"><div>{step > 0 && <button type="button" className="btn min-h-10" onClick={() => { setStep(current => current - 1); setErrors({}); setError(""); }}>上一步</button>}</div><button type="submit" disabled={busy} className="btn btn-primary min-h-10">{busy && <Loader2 size={14} className="animate-spin" />}{busy ? "正在立项…" : step < 2 ? "下一步" : "开始立项"}</button></div>
              </fieldset>
            </form>
          </Glaze>
        </>}
      </div>
    </main>
  </div>;
}
