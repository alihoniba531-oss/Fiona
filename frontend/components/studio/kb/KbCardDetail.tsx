"use client";

import type { ReactNode } from "react";
import { kbCardTypeLabel, kbPaceLabel, kbRange, kbSceneTypeLabel, type KbCard, type KbLintRule } from "@/lib/studio-kb";

function text(value: string | number | null | undefined): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}
function empty<T>(value: T[] | undefined): value is T[] {
  return Array.isArray(value) && value.length > 0;
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0"><dt className="text-xs text-[color:var(--ink2)]">{label}</dt><dd className="mt-1 min-w-0 whitespace-pre-wrap break-words text-sm leading-relaxed">{children}</dd></div>;
}
function Tags({ values, label }: { values: string[] | undefined; label: string }) {
  if (!empty(values)) return null;
  return <Field label={label}><span className="flex flex-wrap gap-1">{values.map(value => <span key={value} className="tag whitespace-normal break-words">{value}</span>)}</span></Field>;
}
function List({ values, label }: { values: string[] | undefined; label: string }) {
  if (!empty(values)) return null;
  return <Field label={label}><ul className="space-y-1">{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul></Field>;
}
function SourceList({ card }: { card: KbCard }) {
  if (!empty(card.sources)) return null;
  return <Field label="来源"><ul className="space-y-1">{card.sources.map((source, index) => <li key={`${source.name}-${index}`}>{source.name} · {source.license}{source.ref ? ` · ${source.ref}` : ""}</li>)}</ul></Field>;
}
function RuleCondition({ rule }: { rule: KbLintRule }) {
  if (rule.pattern) return <span>正则 {rule.pattern}</span>;
  if (!rule.when) return <span>—</span>;
  return <span>{Object.entries(rule.when).map(([key, value]) => `${key}=${Array.isArray(value) ? value.join("/") : String(value)}`).join("，")}</span>;
}

export default function KbCardDetail({ card }: { card: KbCard }) {
  return <article className="ceramic-card min-w-0 space-y-5 rounded-2xl p-4 @[640px]:p-5" aria-label={`卡片详情：${card.title}`}>
    <header className="min-w-0 space-y-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="tag">{kbCardTypeLabel(card.type)}</span>
        {card.scene_type && <span className="tag">{kbSceneTypeLabel(card.scene_type)}</span>}
        {card.position && <span className="tag">{card.position === "opening" ? "开场钩子" : "结尾悬念"}</span>}
      </div>
      <h2 className="break-words text-xl tracking-[.16em]">{card.title}</h2>
      <p className="readout break-words">{card.id}{card.version != null ? ` · 第 ${card.version} 版` : ""}</p>
      <p className="break-words text-sm leading-relaxed text-[color:var(--ink2)]">{card.summary}</p>
    </header>

    <dl className="grid min-w-0 grid-cols-1 gap-4 @[720px]:grid-cols-2">
      <Tags values={card.tags} label="标签" />

      {card.type === "grammar" && <>
        <Field label="定义">{text(card.definition)}</Field>
        <Field label="叙事作用">{text(card.narrative_use)}</Field>
        <Field label="提示词安全写法">{text(card.safe_prompt)}</Field>
        <List values={card.avoid} label="不要这样写" />
        {empty(card.entries) && <Field label="子条目"><ul className="space-y-3">{card.entries.map(entry => <li key={entry.name} className="min-w-0 border-l border-[color:var(--carve)] pl-3"><p className="break-words">{entry.name}</p>{entry.definition && <p className="break-words text-[color:var(--ink2)]">{entry.definition}</p>}{entry.safe_prompt && <p className="break-words">写法：{entry.safe_prompt}</p>}</li>)}</ul></Field>}
        <Tags values={card.related} label="相关卡片" />
      </>}

      {card.type === "scene" && <>
        <List values={card.signals} label="识别信号" />
        <List values={card.beats} label="节拍" />
        <List values={card.coverage} label="覆盖拍法" />
        <Field label="节奏分档"><div className="grid min-w-0 grid-cols-1 gap-2 @[720px]:grid-cols-3">{(["fast", "mid", "slow"] as const).map(key => <div key={key} className="min-w-0 rounded-lg border border-[color:var(--carve)] p-2"><p className="text-[color:var(--ink2)]">{kbPaceLabel(key)}</p><p className="readout break-words">每分钟 {kbRange(card.pacing?.[key]?.shots_per_min, "镜")}</p><p className="readout break-words">每镜 {kbRange(card.pacing?.[key]?.shot_seconds, "秒")}</p></div>)}</div></Field>
        <List values={card.camera} label="运镜建议" />
        <List values={card.sound} label="声音设计" />
        {empty(card.ai_risks) && <Field label="AI 风险与降级"><ul className="space-y-2">{card.ai_risks.map((item, index) => <li key={`${item.risk}-${index}`} className="min-w-0"><p className="break-words">风险：{item.risk}</p><p className="break-words text-[color:var(--ink2)]">降级：{item.fallback}</p></li>)}</ul></Field>}
        <Field label="示例拆法">{text(card.example)}</Field>
        <Tags values={card.related_grammar} label="相关语法" />
        <Tags values={card.related_negative} label="相关反例" />
      </>}

      {card.type === "model" && <>
        <Field label="模型">{text(card.model)}</Field>
        <Field label="风格">{text(card.style)}</Field>
        <List values={card.facts} label="能力事实" />
        <Field label="肖像闸">{text(card.portrait_gate)}</Field>
        <Field label="版权拦截">{text(card.copyright)}</Field>
        <List values={card.motion_risks} label="运镜风险" />
        <List values={card.prompt_syntax} label="提示词写法" />
        <Field label="同框人数上限">{text(card.max_characters)}</Field>
        {empty(card.lint_rules) && <Field label="检查规则"><ul className="space-y-2">{card.lint_rules.map((rule, index) => <li key={`${rule.id ?? rule.pattern ?? "rule"}-${index}`} className="min-w-0"><div className="flex flex-wrap items-center gap-1"><span className="tag">{rule.level ?? "info"}</span>{rule.id && <span className="readout break-words">{rule.id}</span>}</div><p className="break-words">{text(rule.message)}</p><p className="readout break-words"><RuleCondition rule={rule} /></p></li>)}</ul></Field>}
      </>}

      {card.type === "negative" && <>
        <Field label="错误写法">{text(card.wrong)}</Field>
        <Field label="正确写法">{text(card.right)}</Field>
        <Field label="原因">{text(card.why)}</Field>
        <Field label="出处">{text(card.evidence)}</Field>
        <Tags values={card.applies_to?.scene_type?.map(kbSceneTypeLabel)} label="适用场景" />
        <Tags values={card.applies_to?.model} label="适用模型" />
        {card.lint_pattern && <Field label="检查正则">{card.lint_pattern}</Field>}
      </>}

      <SourceList card={card} />
    </dl>
  </article>;
}
