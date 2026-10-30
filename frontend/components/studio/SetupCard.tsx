"use client";

import { useState } from "react";
import Glaze from "@/components/Glaze";
import { castingLanguageLabel, castingResolutionOptions, castingResolutionPriceNote, castingSheetSize, castingVideoModelLabel, formatCastingTime, type CastingLanguage, type CastingResolution, type CastingSetup, type CastingSetupInput, type CastingVideoModel } from "@/lib/studio-casting";

const sheetSizeLabel = castingSheetSize.replace("x", "×");

export default function SetupCard({ aspect, setup, busy, onSave }: { aspect: "16:9" | "9:16"; setup: CastingSetup | null; busy: boolean; onSave: (input: CastingSetupInput) => Promise<void> }) {
  const [editing, setEditing] = useState(!setup);
  const [resolution, setResolution] = useState<CastingResolution>(setup?.resolution ?? "480P");
  const [videoModel, setVideoModel] = useState<CastingVideoModel>(setup?.video_model ?? "wan");
  const [language, setLanguage] = useState<CastingLanguage>(setup?.language ?? "zh");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const blocked = busy || saving;
  const save = async () => {
    if (blocked) return;
    setSaving(true); setError("");
    try { await onSave({ resolution, video_model: videoModel, language }); setEditing(false); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "开工设置未保存，请重试。"); }
    finally { setSaving(false); }
  };
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5">
    <h2 className="mb-4 text-fs-22 tracking-[.2em]">开工确认</h2>
    {setup && !editing ? <div className="min-w-0 space-y-3">
      <div className="flex min-w-0 flex-wrap gap-2">
        <span className="chip">画幅 {aspect}</span>
        <span className="chip">分辨率 {setup.resolution}</span>
        <span className="chip">默认模型 {castingVideoModelLabel(setup.video_model)}</span>
        <span className="chip">语言 {castingLanguageLabel(setup.language)}</span>
        <span className="chip">定妆图 {sheetSizeLabel}</span>
      </div>
      <p className="readout text-fs-13">开工已确认：<b><time dateTime={setup.confirmed_at}>{formatCastingTime(setup.confirmed_at)}</time></b></p>
      <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => { setResolution(setup.resolution); setVideoModel(setup.video_model); setLanguage(setup.language); setEditing(true); }}>修改</button>
    </div> : <fieldset disabled={blocked} className="min-w-0 space-y-4">
      <div className="min-w-0 space-y-1 text-fs-13">
        <p className="text-[color:var(--ink2)]">画幅（沿用项目设置，只读）</p>
        <p className="readout">{aspect}</p>
      </div>
      <div className="min-w-0 space-y-2 text-fs-13">
        <p className="text-[color:var(--ink2)]">视频分辨率</p>
        <div className="flex min-w-0 flex-wrap gap-2">{castingResolutionOptions.map(value => <button key={value} type="button" className={`chip min-h-10 ${resolution === value ? "chip-on" : ""}`} aria-pressed={resolution === value} disabled={blocked} onClick={() => setResolution(value)}>{value}</button>)}</div>
        <p className="readout">{castingResolutionPriceNote}</p>
      </div>
      <div className="min-w-0 space-y-2 text-fs-13">
        <p className="text-[color:var(--ink2)]">默认视频模型</p>
        <div className="flex min-w-0 flex-wrap gap-2">{(["wan", "seedance"] as CastingVideoModel[]).map(value => <button key={value} type="button" className={`chip min-h-10 ${videoModel === value ? "chip-on" : ""}`} aria-pressed={videoModel === value} disabled={blocked} onClick={() => setVideoModel(value)}>{castingVideoModelLabel(value)}</button>)}</div>
      </div>
      <div className="min-w-0 space-y-2 text-fs-13">
        <p className="text-[color:var(--ink2)]">语言</p>
        <div className="flex min-w-0 flex-wrap gap-2">{(["zh", "en"] as CastingLanguage[]).map(value => <button key={value} type="button" className={`chip min-h-10 ${language === value ? "chip-on" : ""}`} aria-pressed={language === value} disabled={blocked} onClick={() => setLanguage(value)}>{castingLanguageLabel(value)}</button>)}</div>
        <p className="text-[color:var(--ink2)]">中文声线用 CosyVoice（付费），英文声线用 edge-tts（免费）。</p>
      </div>
      <div className="min-w-0 space-y-1 text-fs-13">
        <p className="text-[color:var(--ink2)]">定妆图尺寸（只读）</p>
        <p className="readout">{sheetSizeLabel}（一图两区：三视图 + 细节栏）</p>
      </div>
      {error && <p role="alert" className="text-fs-13">{error}</p>}
      <div className="flex min-w-0 flex-wrap gap-2">
        <button type="button" className="btn btn-primary min-h-10" disabled={blocked} onClick={() => void save()}>{saving ? "保存中…" : "确认开工设置"}</button>
        {setup && <button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => { setEditing(false); setError(""); }}>取消</button>}
      </div>
    </fieldset>}
  </Glaze>;
}
