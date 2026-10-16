"use client";

import { ContentSection, ContentValue, record, records, text } from "./NovelContent";
import { EmptyState } from "./NovelStates";

const decisionLabels: Record<string, string> = { adopt: "采纳", partial: "部分采纳", reject: "不采纳" };

function BeatSheet({ value }: { value: unknown }) {
  const beat = record(value);
  return <dl className="space-y-3">{[["title", "章名"], ["chapter_goal", "本章目标"], ["scenes", "场景"], ["beats", "节拍"], ["opening_hook", "开头钩子"], ["ending_hook", "结尾钩子"]].map(([key, label]) => <div key={key}><dt className="text-xs text-[var(--ink2)]">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words"><ContentValue value={beat[key]} /></dd></div>)}</dl>;
}

export function beatChanges(initial: Record<string, unknown>, final: Record<string, unknown>) {
  const fields = ["title", "chapter_goal", "opening_hook", "ending_hook"];
  const changed = fields.filter(field => text(initial[field]) !== text(final[field]));
  const before = Array.isArray(initial.beats) ? initial.beats.map(text) : [];
  const after = Array.isArray(final.beats) ? final.beats.map(text) : [];
  // Multisets preserve duplicate beats rather than undercounting their changes.
  const remaining = [...before];
  let added = 0;
  for (const beat of after) { const index = remaining.indexOf(beat); if (index < 0) added++; else remaining.splice(index, 1); }
  return { changed, added, removed: remaining.length };
}

export default function DeliberationTimeline({ meeting, panelMode }: { meeting: Record<string, unknown> | null; panelMode?: string }) {
  if (!meeting || !Object.keys(meeting).length) return <EmptyState>这一章的推演记录还未生成。</EmptyState>;
  const decision = record(meeting.decision);
  const initial = record(record(meeting.plan).beat_sheet);
  const final = record(decision.beat_sheet);
  const objections = records(meeting.objections);
  const responses = records(decision.objection_responses);
  const alternatives = objections.filter(item => /^A\d+$/.test(text(item.id)) || !!item.alternative);
  const alternativeResponses = records(decision.alternative_responses);
  const critiques = records(meeting.critiques);
  const noteReplies = records(decision.user_note_responses);
  const notes = records(record(meeting.brief).user_notes);
  const hasPanelRecord = meeting.mode === "critique" || !!meeting.plan || critiques.length > 0 || records(meeting.proposals).length > 0;
  const solo = !hasPanelRecord && (panelMode === "solo" || !objections.length);
  const labels: Record<string, string> = { title: "章名", chapter_goal: "目标", opening_hook: "开头钩子", ending_hook: "结尾钩子" };
  const changes = beatChanges(initial, final);
  return <div className="min-w-0 space-y-6 break-words text-sm leading-[1.9]">
    {solo ? <ContentSection title="主编裁决"><BeatSheet value={final} /><p className="mt-3 whitespace-pre-wrap">裁决理由：{text(decision.rationale)}</p></ContentSection> : <>
      <ContentSection title="主编初案"><BeatSheet value={initial} /></ContentSection>
      <ContentSection title="顾问意见">{critiques.length ? critiques.map((critique, index) => {
        const advisorObjections = objections.filter(item => item.author === critique.author && /^O\d+$/.test(text(item.id)));
        const items = advisorObjections.length ? advisorObjections : records(critique.objections);
        return <section key={text(critique.author) || index} className="space-y-3 border-l border-[var(--carve)] pl-3"><h4 className="font-medium">{text(critique.author_name) || text(critique.author)}</h4>
          {items.map((item, n) => <div key={text(item.id) || n} className="space-y-1"><p><span className="tag">{item.severity === "major" ? "重" : "轻"}</span> <span className="readout">{text(item.id)}</span> {text(item.target)}</p><p className="whitespace-pre-wrap">问题：{text(item.problem)}</p><p className="whitespace-pre-wrap text-[var(--ink2)]">改法：{text(item.suggestion)}</p></div>)}
          <p className="whitespace-pre-wrap">值得保留：{text(critique.keep)}</p></section>;
      }) : <p className="text-[var(--ink2)]">本章没有顾问意见。</p>}</ContentSection>
      <ContentSection title="替代走向">{alternatives.length ? alternatives.map((alternative, index) => {
        const id = text(alternative.id);
        const modern = alternativeResponses.find(response => response.alternative_id === id);
        const legacy = responses.find(response => response.objection_id === id);
        const response = modern ?? legacy;
        const responseText = text(response?.response);
        // Historic A replies contain only prose. Show an explicit decision when
        // present; never invent a rejected/adopted result from ambiguous wording.
        const legacyLabel = /部分采纳/.test(responseText) ? "部分采纳" : /不采纳|未采纳|拒绝/.test(responseText) ? "不采纳" : /采纳|采用/.test(responseText) ? "采纳" : "旧版文字回应";
        const label = modern ? decisionLabels[text(modern.decision)] ?? "待回应" : legacy ? legacyLabel : "待回应";
        return <div key={id || index} className="space-y-2"><p className="text-xs text-[var(--ink2)]">{id} {text(alternative.author_name)}</p><p className="whitespace-pre-wrap">{text(alternative.alternative)}</p><p><span className="tag">{label}</span></p><p className="whitespace-pre-wrap">{responseText || "主编尚未回应。"}</p></div>;
      }) : <p className="text-[var(--ink2)]">本章没有提出替代走向。</p>}</ContentSection>
      <ContentSection title="主编逐条回应">{responses.filter(response => /^O\d+$/.test(text(response.objection_id))).sort((a, b) => Number(text(a.objection_id).slice(1)) - Number(text(b.objection_id).slice(1))).map((response, index) => {
        const objection = objections.find(item => item.id === response.objection_id);
        return <div key={text(response.objection_id) || index} className="space-y-1"><p className="readout">{text(response.objection_id)}</p>{objection && <p className="text-[var(--ink2)]">{text(objection.problem)}</p>}<p className="whitespace-pre-wrap">{text(response.response)}</p></div>;
      })}<p className="whitespace-pre-wrap text-[var(--ink2)]">裁决理由：{text(decision.rationale)}</p></ContentSection>
      <ContentSection title="定稿相对初案的改动">{changes.changed.map(field => <div key={field} className="space-y-1"><p className="text-xs text-[var(--ink2)]">{labels[field]}</p><p className="whitespace-pre-wrap">{text(initial[field]) || "（空）"} → {text(final[field]) || "（空）"}</p></div>)}
        <p>节拍：新增 <span className="readout">{changes.added}</span> 条，删除 <span className="readout">{changes.removed}</span> 条。</p>{!changes.changed.length && !changes.added && !changes.removed && <p className="text-[var(--ink2)]">章名、目标、钩子与节拍均沿用初案。</p>}</ContentSection>
    </>}
    {!solo && noteReplies.length > 0 && <ContentSection title="用户留言回应">{noteReplies.map((response, index) => {
      const note = notes.find(item => item.id === response.note_id);
      return <div key={text(response.note_id) || index} className="space-y-2"><p className="whitespace-pre-wrap text-[var(--ink2)]">{text(note?.text) || text(response.note_id)}</p><span className="tag">{response.adopted ? "采纳" : "不采纳"}</span><p className="whitespace-pre-wrap">{text(response.response)}</p></div>;
    })}</ContentSection>}
  </div>;
}
