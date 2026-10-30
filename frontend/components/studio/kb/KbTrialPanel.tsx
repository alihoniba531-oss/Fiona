"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { listStudioProjects, studioErrorMessage, type StudioProject } from "@/lib/studio";
import {
  getKbTrial, kbInjectedChars, kbLintWarnings, kbModeLabel, kbPaceOptions, kbPositionOptions,
  kbRealismOptions, kbReviewProviderLabel, kbReviewStatusLabel, kbSceneTypeOptions, kbSettingOptions,
  kbSensitiveOptions, kbShotBasis, kbTrialInFlight, kbTrialMode, kbTrialStatusLabel, kbVideoModelOptions,
  quoteKbTrial, startKbTrial, type KbLint, type KbMode, type KbPace, type KbPosition, type KbQuote,
  type KbRealism, type KbReview, type KbSceneTags, type KbSceneType, type KbSensitive, type KbSetting,
  type KbShot, type KbTrial, type KbTrialMode, type KbVideoModel,
} from "@/lib/studio-kb";
import KbQuoteDialog from "./KbQuoteDialog";

function reviewDone(review: KbReview | null | undefined): boolean {
  if (!review) return false;
  if (review.status && review.status !== "succeeded") return false;
  return typeof review.verdict === "string" || typeof review.summary === "string" || Array.isArray(review.issues);
}
function severityLabel(value: string | undefined): string {
  return value === "must" ? "must" : value === "should" ? "should" : value ?? "issue";
}
function ShotTable({ shots }: { shots: KbShot[] }) {
  return <div className="hidden min-w-0 @[560px]:block">
    <table className="w-full min-w-0 table-fixed border-collapse text-left text-fs-12 leading-relaxed">
      <thead><tr>
        <th className="w-[8%] border-b border-[color:var(--carve)] px-1 py-2 font-normal">镜号</th>
        <th className="w-[13%] border-b border-[color:var(--carve)] px-1 py-2 font-normal">景别</th>
        <th className="w-[19%] border-b border-[color:var(--carve)] px-1 py-2 font-normal">机位</th>
        <th className="border-b border-[color:var(--carve)] px-1 py-2 font-normal">动作</th>
        <th className="w-[10%] border-b border-[color:var(--carve)] px-1 py-2 font-normal">时长</th>
        <th className="w-[15%] border-b border-[color:var(--carve)] px-1 py-2 font-normal">依据</th>
      </tr></thead>
      <tbody>{shots.map((shot, index) => <tr key={shot.no ?? index}>
        <td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{shot.no ?? index + 1}</td>
        <td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{shot.shot_size || "—"}</td>
        <td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{[shot.angle, shot.camera].filter(Boolean).join(" · ") || "—"}</td>
        <td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{shot.action || "—"}</td>
        <td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{typeof shot.duration_s === "number" ? `${shot.duration_s} 秒` : "—"}</td>
        <td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{kbShotBasis(shot).join("、") || "—"}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}
function ShotCards({ shots }: { shots: KbShot[] }) {
  return <div className="min-w-0 space-y-2 @[560px]:hidden">{shots.map((shot, index) => <article key={shot.no ?? index} className="min-w-0 border-t border-[color:var(--carve)] pt-2 text-fs-15 leading-relaxed">
    <div className="flex min-w-0 flex-wrap items-center gap-2"><span className="tag">第 {shot.no ?? index + 1} 镜</span><span className="readout">时长 {typeof shot.duration_s === "number" ? `${shot.duration_s} 秒` : "未填"}</span></div>
    <dl className="mt-1 grid min-w-0 grid-cols-1 gap-x-3 gap-y-1">
      <div className="min-w-0"><dt className="text-fs-12 text-[color:var(--ink2)]">景别</dt><dd className="break-words">{shot.shot_size || "—"}</dd></div>
      <div className="min-w-0"><dt className="text-fs-12 text-[color:var(--ink2)]">机位</dt><dd className="break-words">{[shot.angle, shot.camera].filter(Boolean).join(" · ") || "—"}</dd></div>
      <div className="min-w-0"><dt className="text-fs-12 text-[color:var(--ink2)]">动作</dt><dd className="break-words">{shot.action || "—"}</dd></div>
      <div className="min-w-0"><dt className="text-fs-12 text-[color:var(--ink2)]">依据</dt><dd className="break-words">{kbShotBasis(shot).join("、") || "—"}</dd></div>
    </dl>
  </article>)}</div>;
}
function LintTags({ warnings }: { warnings: KbLint[] }) {
  if (warnings.length === 0) return null;
  return <div className="min-w-0 space-y-2">
    <h3 className="text-fs-16.5">知识库检查</h3>
    <div className="flex min-w-0 flex-wrap gap-1">{warnings.map((warning, index) => <span key={`${warning.rule_id ?? "lint"}-${index}`} className={`tag whitespace-normal break-words ${warning.level === "warn" ? "tag-rec" : ""}`}>{warning.shot_no != null ? `第 ${warning.shot_no} 镜 · ` : ""}{warning.message || warning.rule_id || "检查提示"}</span>)}</div>
  </div>;
}
function ReviewBlock({ review }: { review: KbReview | null | undefined }) {
  if (!review) return <p className="text-fs-15 leading-relaxed text-[color:var(--ink2)]">本次未开启交叉审核。</p>;
  if (!reviewDone(review)) {
    const pending = ["queued", "running", "submitting"].includes(review.status ?? "");
    return <div className="min-w-0 space-y-1"><p className="text-fs-15 leading-relaxed">{kbReviewStatusLabel(review.status)}</p>{!pending && review.summary && <p className="break-words text-fs-15 leading-relaxed text-[color:var(--ink2)]">{review.summary}</p>}{review.provider && <p className="readout break-words">{kbReviewProviderLabel(review.provider)}{review.model ? ` · ${review.model}` : ""}</p>}</div>;
  }
  const issues = Array.isArray(review.issues) ? review.issues : [];
  return <div className="min-w-0 space-y-3">
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      {review.provider && <span className="tag">{kbReviewProviderLabel(review.provider)}</span>}
      {review.model && <span className="readout break-words">{review.model}</span>}
      <span className={`tag ${review.verdict === "issues" ? "tag-rec" : ""}`}>{review.verdict === "ok" ? "通过" : review.verdict === "issues" ? "有问题" : review.verdict || "—"}</span>
    </div>
    {review.summary && <p className="break-words text-fs-15 leading-relaxed">{review.summary}</p>}
    {issues.length > 0 && <ul className="min-w-0 space-y-3">{issues.map((issue, index) => <li key={index} className="min-w-0 border-t border-[color:var(--carve)] pt-2 text-fs-15 leading-relaxed">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className={`tag ${issue.severity === "must" ? "tag-rec" : ""}`}>{severityLabel(issue.severity)}</span>
        {issue.kind && <span className="tag">{issue.kind}</span>}
        {issue.where && <span className="readout break-words">{issue.where}</span>}
      </div>
      {issue.problem && <p className="mt-1 break-words">{issue.problem}</p>}
      {issue.suggestion && <p className="mt-1 break-words text-[color:var(--ink2)]">建议：{issue.suggestion}</p>}
      {issue.source_ref && <p className="mt-1 break-words text-fs-12 text-[color:var(--ink2)]">原文：{issue.source_ref}</p>}
    </li>)}</ul>}
  </div>;
}

export function KbTrialModeColumn({ mode, data, inFlight = false }: { mode: KbMode; data: KbTrialMode | null; inFlight?: boolean }) {
  const chars = kbInjectedChars(data);
  const shots = Array.isArray(data?.shots) ? data.shots : [];
  const warnings = kbLintWarnings(data);
  const cardIds = Array.isArray(data?.card_ids) ? data.card_ids : [];
  return <section className="@container min-w-0 space-y-3 ceramic-card rounded-2xl p-4" aria-label={kbModeLabel(mode)}>
    <header className="min-w-0 space-y-1">
      <h2 className="text-fs-18 tracking-[.16em]">{kbModeLabel(mode)}</h2>
      <p className="readout break-words">状态：{kbTrialStatusLabel(data?.status)}</p>
      <p className="readout break-words">模板 id：{data?.template_id || "无"}{chars != null ? ` · 注入字数：${chars}` : ""}</p>
      {data?.model_card_missing === true && <p className="break-words text-fs-15 leading-relaxed text-[color:var(--ink2)]">该写实度没有对应的模型卡，未注入模型能力与其检查规则</p>}
      {data?.deviations && <p className="break-words text-fs-15 leading-relaxed text-[color:var(--ink2)]">偏离模板：{data.deviations}</p>}
    </header>
    {cardIds.length > 0 && <div className="flex min-w-0 flex-wrap gap-1">{cardIds.map(id => <span key={id} className="tag whitespace-normal break-words">{id}</span>)}</div>}
    {!data ? (inFlight ? <LoadingState>正在拆这一模式…</LoadingState> : <EmptyState>这一模式还没有结果。</EmptyState>)
      : data.error_message ? <ErrorNotice message={data.error_message} />
      : shots.length === 0 ? (inFlight ? <LoadingState>正在拆镜…</LoadingState> : <EmptyState>没有返回镜头。</EmptyState>)
      : <><ShotTable shots={shots} /><ShotCards shots={shots} /></>}
    <LintTags warnings={warnings} />
    <div className="min-w-0 space-y-2 border-t border-[color:var(--carve)] pt-3">
      <h3 className="text-fs-16.5">交叉审核</h3>
      <ReviewBlock review={data?.review} />
    </div>
  </section>;
}

export default function KbTrialPanel({ owner }: { owner: string }) {
  const [projects, setProjects] = useState<StudioProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");
  const [projectId, setProjectId] = useState("");
  const [sceneText, setSceneText] = useState("");
  const [sceneType, setSceneType] = useState<KbSceneType>("dialogue");
  const [position, setPosition] = useState<KbPosition>("body");
  const [pace, setPace] = useState<KbPace>("mid");
  const [emotion, setEmotion] = useState("");
  const [castCount, setCastCount] = useState(2);
  const [realism, setRealism] = useState<KbRealism>("photoreal");
  const [setting, setSetting] = useState<KbSetting>("interior");
  const [sensitive, setSensitive] = useState<KbSensitive[]>([]);
  const [targetSeconds, setTargetSeconds] = useState(30);
  const [videoModel, setVideoModel] = useState<KbVideoModel>("wan");
  const [quote, setQuote] = useState<KbQuote | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [trial, setTrial] = useState<KbTrial | null>(null);
  const [trialId, setTrialId] = useState("");
  const [trialProjectId, setTrialProjectId] = useState("");
  const [trialError, setTrialError] = useState("");
  const refreshing = useRef(false);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);

  const loadProjects = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setProjectsLoading(true);
    try {
      const next = await listStudioProjects(request.signal);
      if (!request.isCurrent()) return;
      const list = Array.isArray(next) ? next : [];
      setProjects(list);
      setProjectId(previous => list.some(project => project.id === previous) ? previous : list[0]?.id ?? "");
      setProjectsError("");
    } catch (cause) { if (request.isCurrent()) setProjectsError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setProjectsLoading(false); }
  }, [beginRead]);
  useEffect(() => { void Promise.resolve().then(loadProjects); }, [loadProjects]);

  const target = Math.max(1, Math.round(targetSeconds));
  const tags = (): KbSceneTags => ({
    scene_type: sceneType, position, pace, emotion: Array.from(emotion).slice(0, 20).join("").trim(),
    cast_count: Math.max(1, Math.min(6, Math.round(castCount))), realism, setting, sensitive: [...sensitive],
  });
  const validate = (): string => {
    if (!projectId) return "请选择项目。";
    const length = Array.from(sceneText).length;
    if (length === 0 || !sceneText.trim()) return "请粘贴一场戏。";
    if (length > 3000) return "一场戏最多 3000 字。";
    if (Array.from(emotion).length > 20) return "情绪标签最多 20 字。";
    if (!Number.isFinite(castCount) || castCount < 1 || castCount > 6) return "同框人数为 1–6。";
    if (!Number.isFinite(targetSeconds) || targetSeconds < 10 || targetSeconds > 120) return "目标时长为 10–120 秒。";
    return "";
  };

  const getQuote = async () => {
    if (quoting || starting) return;
    const problem = validate();
    if (problem) { setError(problem); return; }
    const request = beginMutation();
    if (!request) return;
    setQuoting(true); setError("");
    try {
      const value = await quoteKbTrial(projectId, {
        scene_text: sceneText, tags: tags(), target_seconds: target,
        video_model: videoModel, modes: ["with_kb", "without_kb"],
      }, request.signal);
      if (request.isCurrent()) setQuote(value);
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setQuoting(false); }
  };

  const start = async () => {
    if (!quote || starting) return;
    const request = beginMutation();
    if (!request) return;
    setStarting(true); setError("");
    try {
      const next = await startKbTrial(projectId, quote.id, request.signal);
      if (!request.isCurrent()) return;
      const id = next.id || next.trial_id || "";
      if (!id) throw new Error("试拆已提交，但没有返回试拆编号，请稍后重试。");
      setTrial(next); setTrialId(id); setTrialProjectId(projectId); setTrialError(""); setQuote(null);
    } catch (cause) {
      if (request.isCurrent()) setError(studioErrorMessage(cause));
      throw cause;
    } finally { if (request.isCurrent()) setStarting(false); }
  };

  const refreshTrial = useCallback(async () => {
    if (!trialId || !trialProjectId || refreshing.current) return;
    const request = beginRead();
    if (!request) return;
    refreshing.current = true;
    try {
      const next = await getKbTrial(trialProjectId, trialId, request.signal);
      if (request.isCurrent()) { setTrial(next); setTrialError(""); }
    } catch (cause) { if (request.isCurrent()) setTrialError(studioErrorMessage(cause)); }
    finally { refreshing.current = false; }
  }, [beginRead, trialId, trialProjectId]);

  useEffect(() => {
    if (!trialId || !trial || !kbTrialInFlight(trial)) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      clearTimeout(timer);
      if (!stopped && !document.hidden && trial && kbTrialInFlight(trial)) timer = setTimeout(tick, 3000);
    };
    const tick = async () => {
      if (stopped || document.hidden) return;
      await refreshTrial();
      schedule();
    };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void tick(); };
    schedule();
    document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [refreshTrial, trial, trialId]);

  const changeProject = (value: string) => {
    setProjectId(value);
    setQuote(null); setTrial(null); setTrialId(""); setTrialProjectId(""); setError(""); setTrialError("");
  };
  const busy = quoting || starting;

  if (projectsLoading) return <LoadingState>正在读取项目…</LoadingState>;
  if (projectsError) return <ErrorNotice message={projectsError} retry={() => { void loadProjects(); }} />;
  if (projects.length === 0) return <EmptyState>还没有工作室项目，请先在短片工作室新建项目，再来试拆。</EmptyState>;

  return <div className="min-w-0 space-y-5">
    <section className="ceramic-card min-w-0 space-y-4 rounded-2xl p-4 @[640px]:p-5" aria-label="试拆设置">
      <h2 className="text-fs-18 tracking-[.16em]">1 选项目</h2>
      <label className="block min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">项目</span><select value={projectId} onChange={event => changeProject(event.target.value)} className={`${novelFieldClass} min-h-10 py-2`}>{projects.map(project => <option key={project.id} value={project.id}>{project.title}</option>)}</select></label>

      <h2 className="text-fs-18 tracking-[.16em]">2 粘贴一场戏</h2>
      <label className="block min-w-0"><span className="sr-only">一场戏原文</span><textarea value={sceneText} rows={8} onChange={event => setSceneText(Array.from(event.target.value).slice(0, 3000).join(""))} placeholder="粘贴 3000 字以内的一场戏" className={`${novelFieldClass} min-h-40 resize-y`} /></label>
      <p className="readout text-right">{Array.from(sceneText).length} / 3000 字</p>

      <h2 className="text-fs-18 tracking-[.16em]">3 填标签</h2>
      <div className="grid min-w-0 grid-cols-1 gap-3 @[720px]:grid-cols-2">
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">场景类型</span><select value={sceneType} onChange={event => setSceneType(event.target.value as KbSceneType)} className={`${novelFieldClass} min-h-10 py-2`}>{kbSceneTypeOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">位置</span><select value={position} onChange={event => setPosition(event.target.value as KbPosition)} className={`${novelFieldClass} min-h-10 py-2`}>{kbPositionOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">节奏</span><select value={pace} onChange={event => setPace(event.target.value as KbPace)} className={`${novelFieldClass} min-h-10 py-2`}>{kbPaceOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">情绪（最多 20 字）</span><input value={emotion} onChange={event => setEmotion(Array.from(event.target.value).slice(0, 20).join(""))} className={`${novelFieldClass} min-h-10 py-2`} /></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">同框人数（1–6）</span><input type="number" min={1} max={6} value={castCount} onChange={event => setCastCount(Number(event.target.value))} className={`${novelFieldClass} min-h-10 py-2`} /></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">写实度</span><select value={realism} onChange={event => setRealism(event.target.value as KbRealism)} className={`${novelFieldClass} min-h-10 py-2`}>{kbRealismOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">空间</span><select value={setting} onChange={event => setSetting(event.target.value as KbSetting)} className={`${novelFieldClass} min-h-10 py-2`}>{kbSettingOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">目标时长（10–120 秒）</span><input type="number" min={10} max={120} value={targetSeconds} onChange={event => setTargetSeconds(Number(event.target.value))} className={`${novelFieldClass} min-h-10 py-2`} /></label>
        <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">视频模型</span><select value={videoModel} onChange={event => setVideoModel(event.target.value as KbVideoModel)} className={`${novelFieldClass} min-h-10 py-2`}>{kbVideoModelOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
      </div>
      <fieldset className="min-w-0"><legend className="mb-2 text-fs-13 text-[color:var(--ink2)]">敏感镜头</legend><div className="flex min-w-0 flex-wrap gap-x-4 gap-y-2">{kbSensitiveOptions.map(option => <label key={option.id} className="inline-flex min-h-10 items-center gap-2 text-fs-13"><input type="checkbox" checked={sensitive.includes(option.id)} onChange={event => setSensitive(previous => event.target.checked ? [...previous, option.id] : previous.filter(value => value !== option.id))} className="h-5 w-5 accent-[color:var(--ink)]" />{option.label}</label>)}</div></fieldset>

      <h2 className="text-fs-18 tracking-[.16em]">4 报价并开始</h2>
      <p className="text-fs-15 leading-relaxed text-[color:var(--ink2)]">两种模式都会拆：{kbModeLabel("with_kb")} / {kbModeLabel("without_kb")}，结果左右并排展示。</p>
      {error && <p role="alert" className="break-words text-fs-13 text-[color:var(--seal)]">{error}</p>}
      <div className="flex min-w-0 flex-wrap gap-2"><button type="button" className="btn btn-primary min-h-10 max-w-full whitespace-normal" disabled={busy} onClick={() => { void getQuote(); }}>{quoting ? "报价中…" : "试拆报价"}</button>{trial && <button type="button" className="btn btn-quiet min-h-10" disabled={quoting || starting} onClick={() => { void refreshTrial(); }}>刷新结果</button>}</div>
      <p className="text-fs-12 leading-relaxed text-[color:var(--ink2)]">报价 15 分钟内有效，确认一次后不能重复使用。费用按导演模型与审核模型一并预留。</p>
    </section>

    {quote && <KbQuoteDialog quote={quote} busy={busy} onClose={() => setQuote(null)} onConfirm={start} />}

    <section className="min-w-0 space-y-3" aria-label="试拆对比结果">
      {trial ? <>
        <div className="flex min-w-0 flex-wrap items-center gap-2"><h2 className="text-fs-18 tracking-[.16em]">试拆对比</h2><span className="tag">{kbTrialStatusLabel(trial.status)}</span></div>
        {trialError && <ErrorNotice message={trialError} retry={() => { void refreshTrial(); }} />}
        {trial.status === "failed" && trial.error_message && <ErrorNotice message={trial.error_message} />}
        <div className="grid min-w-0 grid-cols-1 items-start gap-4 @[1000px]:grid-cols-2">
          {(["with_kb", "without_kb"] as KbMode[]).map(mode => <KbTrialModeColumn key={mode} mode={mode} data={kbTrialMode(trial, mode)} inFlight={kbTrialInFlight(trial)} />)}
        </div>
      </> : <EmptyState>选好项目、贴一场戏并报价后，结果会在这里左右并排显示。</EmptyState>}
    </section>
  </div>;
}
