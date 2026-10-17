"use client";

import { useState } from "react";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { archiveCastingAsset, auditionCastingVoices, approveCastingVoice, castingAuditionCostLabel, castingDefaultAuditionText, castingFxLabel, castingItemStatusLabel, castingVoiceEngineLabel, castingVoiceRoleLabel, castingVoiceSpecLabel, formatCastingTime, type CastingAuditionRequest, type CastingAuditionVariant, type CastingItem, type CastingLanguage, type CastingMutate, type CastingPrices, type CastingVoiceCatalog, type CastingVoiceEngine, type CastingVoiceRole } from "@/lib/studio-casting";
import { breakdownFieldClass } from "./BreakdownDialog";
import StudioAssetAudio from "./StudioAssetAudio";

const engines: CastingVoiceEngine[] = ["cosyvoice", "edge-tts"];
const roles: CastingVoiceRole[] = ["dialogue", "narration"];

interface VariantDraft { engine: CastingVoiceEngine; voice: string; rate: string; pitch: string; fx: string; role: CastingVoiceRole }

function ratePitchDefaults(engine: CastingVoiceEngine): { rate: string; pitch: string } {
  return engine === "cosyvoice" ? { rate: "1", pitch: "1" } : { rate: "+0%", pitch: "+0Hz" };
}
function firstVoice(catalog: CastingVoiceCatalog, engine: CastingVoiceEngine): string {
  return catalog.voices.find(voice => voice.engine === engine)?.voice ?? "";
}
function newRow(catalog: CastingVoiceCatalog, language: CastingLanguage): VariantDraft {
  const engine: CastingVoiceEngine = language === "zh" ? "cosyvoice" : "edge-tts";
  return { engine, voice: firstVoice(catalog, engine), ...ratePitchDefaults(engine), fx: "", role: "dialogue" };
}
function fxOptions(catalog: CastingVoiceCatalog): string[] {
  return Object.entries(catalog.fx).flatMap(([type, levels]) => levels.map(level => `${type}:${level}`));
}
function validateRow(row: VariantDraft): string {
  if (!row.voice.trim()) return "每个方案都需要选择音色。";
  if (row.engine === "cosyvoice") {
    const rate = Number(row.rate);
    const pitch = Number(row.pitch);
    if (!Number.isFinite(rate) || rate < 0.5 || rate > 2.0 || !Number.isFinite(pitch) || pitch < 0.5 || pitch > 2.0) return "CosyVoice 的语速与音高需要在 0.5–2.0 之间。";
  } else {
    const rateMatch = /^[+-]\d+%$/.exec(row.rate.trim());
    const pitchMatch = /^[+-]\d+Hz$/.exec(row.pitch.trim());
    if (!rateMatch || Math.abs(Number(rateMatch[0].slice(0, -1))) > 50) return "edge-tts 的语速需要形如 +5% 或 -8%（-50% 到 +50%）。";
    if (!pitchMatch || Math.abs(Number(pitchMatch[0].slice(0, -2))) > 50) return "edge-tts 的音高需要形如 +0Hz 或 -3Hz（-50Hz 到 +50Hz）。";
  }
  return "";
}

export default function VoicePanel({ projectId, items, language, prices, catalog, catalogError, busy, mutate, onChanged }: {
  projectId: string;
  items: CastingItem[];
  language: CastingLanguage;
  prices: CastingPrices;
  catalog: CastingVoiceCatalog | null;
  catalogError?: string;
  busy: boolean;
  mutate: CastingMutate;
  onChanged: () => Promise<void>;
}) {
  const characters = items.filter(item => item.kind === "character");
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5">
    <h2 className="mb-2 text-xl tracking-[.2em]">声线</h2>
    <p className="mb-4 text-[13px] leading-relaxed text-[color:var(--ink2)]">中文用 CosyVoice（付费），英文用 edge-tts（免费）。</p>
    {catalogError ? <ErrorNotice message={catalogError} /> : !catalog ? <LoadingState>正在读取音色…</LoadingState> : !characters.length ? <EmptyState>暂无可配置声线的人物。</EmptyState> : <div className="min-w-0 space-y-4">
      {characters.map(item => <VoiceCard key={item.id} projectId={projectId} item={item} language={language} prices={prices} catalog={catalog} busy={busy} mutate={mutate} onChanged={onChanged} />)}
    </div>}
  </Glaze>;
}

function VoiceCard({ projectId, item, language, prices, catalog, busy, mutate, onChanged }: {
  projectId: string;
  item: CastingItem;
  language: CastingLanguage;
  prices: CastingPrices;
  catalog: CastingVoiceCatalog;
  busy: boolean;
  mutate: CastingMutate;
  onChanged: () => Promise<void>;
}) {
  const [text, setText] = useState(() => castingDefaultAuditionText(item));
  const [rows, setRows] = useState<VariantDraft[]>(() => [newRow(catalog, language)]);
  const [localError, setLocalError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const blocked = busy || submitting || item.orphaned;
  const options = fxOptions(catalog);
  const approvedId = item.voice?.approved_asset_id ?? null;
  const auditions = (item.voice?.auditions ?? []).filter(audition => !audition.archived);

  const updateRow = (index: number, patch: Partial<VariantDraft>) => {
    setRows(current => current.map((row, position) => position === index ? { ...row, ...patch } : row));
    setLocalError("");
  };
  const changeEngine = (index: number, engine: CastingVoiceEngine) => {
    setRows(current => current.map((row, position) => position === index ? { ...row, engine, voice: firstVoice(catalog, engine), ...ratePitchDefaults(engine) } : row));
    setLocalError("");
  };
  const addRow = () => {
    setRows(current => current.length >= 3 ? current : [...current, newRow(catalog, language)]);
    setLocalError("");
  };
  const removeRow = (index: number) => {
    setRows(current => current.length <= 1 ? current : current.filter((_, position) => position !== index));
    setLocalError("");
  };
  const generate = async () => {
    if (blocked) return;
    const trimmed = text.trim();
    if (!trimmed || trimmed.length > 120) { setLocalError("试听台词需要 1–120 字。"); return; }
    for (const row of rows) { const message = validateRow(row); if (message) { setLocalError(message); return; } }
    setLocalError("");
    const variants: CastingAuditionVariant[] = rows.map(row => ({
      engine: row.engine, voice: row.voice,
      rate: row.engine === "cosyvoice" ? Number(row.rate) : row.rate.trim(),
      pitch: row.engine === "cosyvoice" ? Number(row.pitch) : row.pitch.trim(),
      fx: row.fx || null, role: row.role,
    }));
    const input: CastingAuditionRequest = { item_id: item.id, text: trimmed, variants };
    setSubmitting(true);
    try { await mutate(signal => auditionCastingVoices(projectId, input, signal), "试听已生成。"); }
    finally { setSubmitting(false); }
  };
  const approve = async (assetId: string) => {
    if (blocked) return;
    setSubmitting(true);
    try {
      await mutate(signal => approveCastingVoice(item.id, assetId, signal), "声线已定档。");
      await onChanged();
    } finally { setSubmitting(false); }
  };
  const archive = async (assetId: string) => {
    if (blocked) return;
    setSubmitting(true);
    try {
      await mutate(signal => archiveCastingAsset(assetId, signal), "试听已归档。");
      await onChanged();
    } finally { setSubmitting(false); }
  };

  return <div className="ceramic-card min-w-0 space-y-3 p-4">
    <div className="min-w-0 space-y-1">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h3 className="min-w-0 break-words text-lg tracking-[.12em]">{item.name}</h3>
        <span className="tag">{castingItemStatusLabel(item.status)}</span>
        {item.orphaned && <span className="tag">已不在当前总表</span>}
        {approvedId && <span className="tag">已定档</span>}
      </div>
      {approvedId && item.voice?.spec && <p className="readout break-words">{castingVoiceSpecLabel(item.voice.spec)}</p>}
    </div>
    <label htmlFor={`voice-text-${item.id}`} className="block min-w-0 space-y-1 text-sm">
      <span>试听台词</span>
      <textarea id={`voice-text-${item.id}`} rows={2} maxLength={120} value={text} disabled={blocked} className={breakdownFieldClass} onChange={event => { setText(event.target.value); setLocalError(""); }} />
    </label>
    <div className="min-w-0 space-y-3">
      {rows.map((row, index) => <div key={index} className="min-w-0 space-y-2 rounded-lg border border-[color:var(--carve)] p-3">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <p className="readout">方案 {index + 1}</p>
          {rows.length > 1 && <button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => removeRow(index)}>移除</button>}
        </div>
        <div className="grid min-w-0 gap-2 @[640px]:grid-cols-2">
          <label htmlFor={`voice-engine-${item.id}-${index}`} className="block min-w-0 space-y-1 text-sm">
            <span>引擎</span>
            <select id={`voice-engine-${item.id}-${index}`} value={row.engine} disabled={blocked} className={breakdownFieldClass} onChange={event => changeEngine(index, event.target.value as CastingVoiceEngine)}>
              {engines.map(engine => <option key={engine} value={engine}>{castingVoiceEngineLabel(engine)}</option>)}
            </select>
          </label>
          <label htmlFor={`voice-name-${item.id}-${index}`} className="block min-w-0 space-y-1 text-sm">
            <span>音色</span>
            <select id={`voice-name-${item.id}-${index}`} value={row.voice} disabled={blocked} className={breakdownFieldClass} onChange={event => updateRow(index, { voice: event.target.value })}>
              {row.voice === "" && <option value="">请选择音色</option>}
              {catalog.voices.filter(voice => voice.engine === row.engine).map(voice => <option key={voice.voice} value={voice.voice}>{voice.label}</option>)}
            </select>
          </label>
          <label htmlFor={`voice-rate-${item.id}-${index}`} className="block min-w-0 space-y-1 text-sm">
            <span>语速（{row.engine === "cosyvoice" ? "0.5–2.0" : "-50% 到 +50%"}）</span>
            <input id={`voice-rate-${item.id}-${index}`} value={row.rate} disabled={blocked} className={breakdownFieldClass} onChange={event => updateRow(index, { rate: event.target.value })} />
          </label>
          <label htmlFor={`voice-pitch-${item.id}-${index}`} className="block min-w-0 space-y-1 text-sm">
            <span>音高（{row.engine === "cosyvoice" ? "0.5–2.0" : "-50Hz 到 +50Hz"}）</span>
            <input id={`voice-pitch-${item.id}-${index}`} value={row.pitch} disabled={blocked} className={breakdownFieldClass} onChange={event => updateRow(index, { pitch: event.target.value })} />
          </label>
          <label htmlFor={`voice-fx-${item.id}-${index}`} className="block min-w-0 space-y-1 text-sm">
            <span>声线特效</span>
            <select id={`voice-fx-${item.id}-${index}`} value={row.fx} disabled={blocked} className={breakdownFieldClass} onChange={event => updateRow(index, { fx: event.target.value })}>
              <option value="">无特效</option>
              {options.map(fx => <option key={fx} value={fx}>{castingFxLabel(fx)}</option>)}
            </select>
          </label>
          <label htmlFor={`voice-role-${item.id}-${index}`} className="block min-w-0 space-y-1 text-sm">
            <span>角色类型</span>
            <select id={`voice-role-${item.id}-${index}`} value={row.role} disabled={blocked} className={breakdownFieldClass} onChange={event => updateRow(index, { role: event.target.value as CastingVoiceRole })}>
              {roles.map(role => <option key={role} value={role}>{castingVoiceRoleLabel(role)}</option>)}
            </select>
          </label>
        </div>
      </div>)}
      <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || rows.length >= 3} onClick={addRow}>再加一个方案</button>
    </div>
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <button type="button" className="btn btn-primary min-h-10" disabled={blocked} onClick={() => void generate()}>生成试听</button>
      <span className="readout">{castingAuditionCostLabel(text, language, prices)}</span>
    </div>
    {localError && <p role="status" className="break-words text-sm text-[color:var(--seal)]">{localError}</p>}
    {item.voice && <div className="min-w-0 space-y-3">
      {auditions.map((audition, index) => {
        const approved = approvedId === audition.asset_id;
        return <div key={audition.asset_id} className="min-w-0 space-y-2 rounded-lg border border-[color:var(--carve)] p-3">
          <StudioAssetAudio assetId={audition.asset_id} label={`第 ${index + 1} 条试听`} />
          <p className="readout break-words">{castingVoiceSpecLabel(audition.spec)} · 实测响度 {audition.measured_lufs} LUFS</p>
          <time dateTime={audition.created_at} className="readout block break-words">创建于 {formatCastingTime(audition.created_at)}</time>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || approved} onClick={() => void approve(audition.asset_id)}>选定这条</button>
            <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || approved} title={approved ? "先换选定" : undefined} onClick={() => void archive(audition.asset_id)}>归档</button>
            {approved && <span className="tag">已定档</span>}
          </div>
        </div>;
      })}
      {!auditions.length && <p className="text-[13px] leading-relaxed text-[color:var(--ink2)]">还没有试听，先生成一条方案。</p>}
    </div>}
  </div>;
}
