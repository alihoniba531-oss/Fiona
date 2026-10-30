"use client";

import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import Glaze from "@/components/Glaze";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { quoteStudioClip, studioErrorMessage, uploadStudioAsset, type StudioClipParams, type StudioQuote } from "@/lib/studio";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import StudioAssetImage from "./StudioAssetImage";

export interface ClipComposerProps {
  projectId: string;
  owner: string;
  busy?: boolean;
  refill?: { token: number; params: StudioClipParams };
  onQuote: (quote: StudioQuote) => void;
  onBusyChange?: (busy: boolean) => void;
  onChanged?: () => Promise<void>;
}

export function validateStudioFirstFrame(file: Pick<File, "type" | "size">): string {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) return "首帧仅支持 PNG、JPEG、WebP 图片。";
  if (file.size > 20 * 1024 * 1024) return "首帧不能超过 20MB。";
  return "";
}

export default function ClipComposer(props: ClipComposerProps) {
  return <Composer key={`${props.owner}:${props.projectId}:${props.refill?.token ?? 0}`} {...props} />;
}

function Composer({ projectId, owner, busy = false, refill, onQuote, onBusyChange, onChanged }: ClipComposerProps) {
  const initial = refill?.params;
  const [assetId, setAssetId] = useState(initial?.first_frame_asset_id ?? "");
  const [prompt, setPrompt] = useState(initial?.prompt ?? "");
  const [provider, setProvider] = useState<StudioClipParams["provider"]>(initial?.provider ?? "wan");
  const [model, setModel] = useState(initial?.model);
  const [resolution, setResolution] = useState((initial?.resolution ?? "480P").toUpperCase());
  const [duration, setDuration] = useState(String(initial?.duration ?? 5));
  const [audio, setAudio] = useState(initial?.audio ?? true);
  const [durationRange, setDurationRange] = useState<{ min: number; max: number } | null>(initial?.duration_min_s != null && initial.duration_max_s != null ? { min: initial.duration_min_s, max: initial.duration_max_s } : null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState<"upload" | "quote" | "">("");
  const input = useRef<HTMLInputElement>(null);
  const locked = useRef(false);
  const { beginRequest } = useAccountRequest(owner);
  const disabled = busy || !!working;
  const promptLength = Array.from(prompt).length;

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || locked.current || busy) return;
    const validation = validateStudioFirstFrame(file);
    setError(validation);
    if (validation) return;
    const request = beginRequest();
    if (!request) return;
    locked.current = true;
    setWorking("upload");
    onBusyChange?.(true);
    try {
      const asset = await uploadStudioAsset(projectId, file, request.signal);
      if (!request.isCurrent()) return;
      setAssetId(asset.id);
      await onChanged?.();
    } catch (cause) {
      if (request.isCurrent()) setError(studioErrorMessage(cause));
    } finally {
      locked.current = false;
      if (request.isCurrent()) setWorking("");
      onBusyChange?.(false);
    }
  };

  const quote = async (event: FormEvent) => {
    event.preventDefault();
    if (locked.current || busy) return;
    setError("");
    if (!assetId) { setError("请先上传首帧。"); return; }
    if (!prompt.trim() || promptLength > 2000) { setError("提示词须为 1–2000 字。"); return; }
    const seconds = Number(duration);
    if (!duration.trim() || !Number.isInteger(seconds)) { setError("时长须为整数秒，具体范围以报价校验为准。"); return; }
    const request = beginRequest();
    if (!request) return;
    locked.current = true;
    setWorking("quote");
    onBusyChange?.(true);
    try {
      const next = await quoteStudioClip(projectId, { first_frame_asset_id: assetId, prompt, provider, ...(model ? { model } : {}), resolution, duration: seconds, audio }, request.signal);
      if (!request.isCurrent()) return;
      const params = next.items[0]?.params;
      if (params?.duration_min_s != null && params.duration_max_s != null) setDurationRange({ min: params.duration_min_s, max: params.duration_max_s });
      onQuote(next);
      await onChanged?.();
    } catch (cause) {
      // Preserve the server's Chinese 422 detail verbatim.
      if (request.isCurrent()) setError(studioErrorMessage(cause));
    } finally {
      locked.current = false;
      if (request.isCurrent()) setWorking("");
      onBusyChange?.(false);
    }
  };

  return <Glaze as="section" variant="panel" lens={false} className="@container min-w-0 rounded-[18px] p-5 mobile:p-4" aria-labelledby="studio-composer-title">
    <h2 id="studio-composer-title" className="mb-4 text-fs-22 tracking-[.24em]">单镜试拍</h2>
    {refill && <p role="status" className="mb-4 text-fs-13 leading-relaxed text-[color:var(--ink2)]">已回填同样参数，检查后可重新报价。</p>}
    <form onSubmit={event => void quote(event)} className="min-w-0 space-y-5">
      <div className="grid min-w-0 gap-5 @[620px]:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="min-w-0 space-y-3">
          <span className="block text-fs-16.5">首帧</span>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" aria-label="选择首帧图片" disabled={disabled} onChange={event => void upload(event)} />
          {assetId && <div className="mount-frame overflow-hidden rounded-[10px] p-2"><StudioAssetImage assetId={assetId} alt="试拍首帧" className="max-h-56" /></div>}
          <button type="button" disabled={disabled} className="btn btn-quiet min-h-10" onClick={() => input.current?.click()}>{working === "upload" ? "上传中…" : assetId ? "更换首帧" : "上传首帧"}</button>
          <p className="text-fs-13 leading-relaxed text-[color:var(--ink2)]">PNG、JPEG、WebP，不超过 20MB。</p>
        </div>
        <div className="min-w-0"><label htmlFor="studio-prompt" className="mb-2 block text-fs-16.5">提示词</label><textarea id="studio-prompt" rows={6} maxLength={2000} value={prompt} disabled={disabled} onChange={event => setPrompt(event.target.value)} className={`${novelFieldClass} resize-y`} aria-describedby="studio-prompt-count" placeholder="描述这一镜的主体、动作与画面。" /><p id="studio-prompt-count" className="readout mt-1 text-right">{promptLength} / 2000 字</p></div>
      </div>
      <fieldset disabled={disabled} className="min-w-0"><legend className="mb-2 text-fs-16.5">模型</legend><div className="flex flex-wrap gap-2" role="group" aria-label="视频模型">{([{ value: "wan", label: "万相 3.0" }, { value: "seedance", label: "Seedance 2.5" }] as const).map(option => <button key={option.value} type="button" aria-pressed={provider === option.value} className={`chip min-h-10 px-3 ${provider === option.value ? "chip-on" : ""}`} onClick={() => { setProvider(option.value); setModel(undefined); setDurationRange(null); }}>{option.label}</button>)}</div></fieldset>
      <div className="grid min-w-0 gap-5 @[620px]:grid-cols-2">
        <fieldset disabled={disabled} className="min-w-0"><legend className="mb-2 text-fs-16.5">分辨率</legend><div className="flex flex-wrap gap-2" role="group" aria-label="分辨率">{["480P", "720P", "1080P"].map(value => <button key={value} type="button" aria-pressed={resolution === value} className={`chip min-h-10 px-3 ${resolution === value ? "chip-on" : ""}`} onClick={() => setResolution(value)}>{value}</button>)}</div></fieldset>
        <div className="min-w-0"><label htmlFor="studio-duration" className="mb-2 block text-fs-16.5">时长（秒）</label><input id="studio-duration" type="number" step={1} value={duration} disabled={disabled} className={novelFieldClass} onChange={event => setDuration(event.target.value)} aria-describedby="studio-duration-hint" /><p id="studio-duration-hint" className="mt-2 text-fs-13 leading-relaxed text-[color:var(--ink2)]">{durationRange ? <>本次报价时长范围 <span className="readout">{durationRange.min}–{durationRange.max}</span> 秒。</> : "输入整数秒；报价后显示后端校验的时长范围。"}</p></div>
      </div>
      <label className="flex min-h-10 w-fit items-center gap-3 text-fs-16.5"><input type="checkbox" role="switch" checked={audio} disabled={disabled} onChange={event => setAudio(event.target.checked)} className="h-5 w-5 accent-[color:var(--ink)]" />生成音频</label>
      {error && <ErrorNotice message={error} />}
      {working === "upload" && <LoadingState>正在上传首帧…</LoadingState>}
      <button type="submit" className="btn btn-primary min-h-10" disabled={disabled || !assetId || !prompt.trim() || promptLength > 2000}>{working === "quote" ? "报价中…" : "报价"}</button>
    </form>
  </Glaze>;
}
