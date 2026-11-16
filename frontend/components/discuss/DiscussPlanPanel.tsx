"use client";

import { useCallback, useRef, useState, type JSX } from "react";
import { Loader2, Plus } from "lucide-react";
import DiscussTeamEditor, { type DiscussTeamMember } from "@/components/discuss/DiscussTeamEditor";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import {
  getDiscussGroup,
  updateDiscussPlan,
  type DiscussCatalog,
  type DiscussCoreRole,
  type DiscussDetail,
  type DiscussMember,
  type DiscussPlanDraft,
  type DiscussPlanIdentityDraft,
  type DiscussPickDraft,
} from "@/lib/discuss";
import {
  buildDiscussPlanPatch,
  discussErrorMessage,
  discussIsActive,
  discussMemberShowsFocus,
  discussModelLabel,
  discussPlanPatchIsEmpty,
} from "@/lib/discussLogic";
import { useAccountRequest } from "@/lib/useAccountIdentity";

const CORE_ROLES: DiscussCoreRole[] = ["host", "critic", "writer", "acceptor"];
const CRITERIA_MIN = 3;
const CRITERIA_MAX = 6;
const ANSWERS_MAX = 1000;
const CRITERION_MAX = 120;
const TITLE_MAX = 40;
const FOCUS_MAX = 300;
const FIELD_CLASS = "ceramic-card min-h-10 w-full min-w-0 rounded-[10px] px-3 py-2 text-fs-15 text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";

const KIND_LABELS: Record<string, string> = {
  core: "固定席位",
  lens: "调研",
  custom: "自定义",
  avatar: "分身",
};

const DELIVERABLE_LABELS: Record<string, string> = {
  report: "调研报告",
  plan: "行动方案",
  comparison: "对比分析",
};

type ModelOption = { value: string; label: string };
type ModelRow = { key: string; label: string; role: string; value: string };

function errorStatus(error: unknown): number | undefined {
  return error !== null && typeof error === "object"
    ? (error as { status?: number }).status
    : undefined;
}

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

function deliverableLabel(kind: string): string {
  return DELIVERABLE_LABELS[kind] ?? kind;
}

function initialDraft(detail: DiscussDetail): DiscussPlanDraft {
  const plan = detail.plan;
  const core = new Map(
    detail.members
      .filter(member => member.kind === "core")
      .map(member => [member.role, member] as const),
  );
  return {
    title: detail.title,
    criteria: plan?.criteria?.map(item => item.text) ?? [],
    picks: plan?.picks?.map(item => ({
      role: item.role,
      name: item.name,
      does: item.does,
      focus: item.focus,
    })) ?? [],
    identities: CORE_ROLES.map((role): DiscussPlanIdentityDraft => {
      const member = core.get(role);
      return {
        role,
        name: member?.name ?? "",
        persona: member?.does ?? "",
        default_name: member?.name ?? "",
        default_persona: member?.does ?? "",
      };
    }),
    budget_strawberries: detail.budget_strawberries,
    max_rounds: detail.max_rounds,
    avatar: detail.members.some(member => member.kind === "avatar"),
    models: Object.fromEntries(detail.members.map(member => [member.role, member.model])),
    answers: detail.answers ?? "",
  };
}

function modelOptions(catalog: DiscussCatalog): ModelOption[] {
  const options: ModelOption[] = catalog.models.map(model => ({
    value: model.id,
    label: discussModelLabel(model.id),
  }));
  if (catalog.byok) options.push({ value: "byok:self", label: "我的模型" });
  return options;
}

function withCurrentModel(options: ModelOption[], value: string): ModelOption[] {
  if (!value || options.some(option => option.value === value)) return options;
  return [...options, { value, label: discussModelLabel(value) }];
}

function answerLength(value: string): number {
  return Array.from(value).length;
}

export default function DiscussPlanPanel(props: {
  owner: string;
  detail: DiscussDetail;
  catalog: DiscussCatalog | null;
  catalogError: string;
  busy: boolean;
  onReloadCatalog: () => void;
  onUpdated: (detail: DiscussDetail) => void;
  onDirtyChange: (dirty: boolean) => void;
}): JSX.Element {
  const {
    owner,
    detail,
    catalog,
    catalogError,
    busy,
    onReloadCatalog,
    onUpdated,
    onDirtyChange,
  } = props;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DiscussPlanDraft | null>(null);
  const [customKeys, setCustomKeys] = useState<string[]>([]);
  const [budgetText, setBudgetText] = useState("");
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const savingRef = useRef(false);
  const reloadingRef = useRef(false);
  const { beginRequest } = useAccountRequest(owner);

  const exitEdit = useCallback(() => {
    setEditing(false);
    setDraft(null);
    setCustomKeys([]);
    setError("");
    setConflict(false);
    onDirtyChange(false);
  }, [onDirtyChange]);

  if (!detail.plan) {
    return discussIsActive(detail.status)
      ? <LoadingState>主持人正在立项…</LoadingState>
      : <EmptyState>还没有方案。</EmptyState>;
  }
  const plan = detail.plan;
  const questions = plan.questions ?? [];
  const answers = detail.answers ?? "";
  const waitingStart = detail.status === "awaiting_start";
  const canEdit = !!catalog && !catalogError;
  const seatName = (role: string) =>
    catalog?.roles.find(item => item.id === role)?.name ?? role;
  const rolePool = (catalog?.roles ?? [])
    .filter(role => role.kind === "lens")
    .map(role => ({ id: role.id, name: role.name, does: role.does }));
  const currentMemberModel = (role: string) =>
    detail.members.find(member => member.role === role)?.model ?? "";

  const enterEdit = () => {
    if (!catalog || catalogError || busy || !detail.plan) return;
    const next = initialDraft(detail);
    setDraft(next);
    setCustomKeys(next.picks.filter(pick => !pick.role).map((_, index) => `custom-${index}`));
    setBudgetText(String(next.budget_strawberries));
    setError("");
    setConflict(false);
    setEditing(true);
    onDirtyChange(false);
  };

  const markDirty = () => {
    onDirtyChange(true);
    // 409 需要重新加载方案才能继续，改草稿时不把这条提示和按钮一起清掉。
    if (!conflict) setError("");
  };

  const updateDraft = (updater: (current: DiscussPlanDraft) => DiscussPlanDraft) => {
    setDraft(current => (current ? updater(current) : current));
    markDirty();
  };

  const updateCriterion = (index: number, value: string) => {
    updateDraft(current => ({
      ...current,
      criteria: current.criteria.map((text, at) => (at === index ? value : text)),
    }));
  };

  const addCriterion = () => {
    updateDraft(current => current.criteria.length >= CRITERIA_MAX
      ? current
      : { ...current, criteria: [...current.criteria, ""] });
  };

  const removeCriterion = (index: number) => {
    updateDraft(current => current.criteria.length <= CRITERIA_MIN
      ? current
      : { ...current, criteria: current.criteria.filter((_, at) => at !== index) });
  };

  const updateSeat = (role: DiscussCoreRole, patch: Partial<DiscussPlanIdentityDraft>) => {
    updateDraft(current => ({
      ...current,
      identities: current.identities.map(seat => (seat.role === role ? { ...seat, ...patch } : seat)),
    }));
  };

  const updateBudget = (value: string) => {
    setBudgetText(value);
    updateDraft(current => ({ ...current, budget_strawberries: Number(value) }));
  };

  const updateModel = (role: string, value: string) => {
    updateDraft(current => ({ ...current, models: { ...current.models, [role]: value } }));
  };

  const handleTeamChange = (members: DiscussTeamMember[]) => {
    const nextCustomKeys = members.filter(member => !member.role).map(member => member.key);
    setCustomKeys(nextCustomKeys);
    setDraft(current => {
      if (!current) return current;
      const picks: DiscussPickDraft[] = members.map(member => ({
        role: member.role,
        name: member.name,
        does: member.does,
        focus: member.focus ?? "",
      }));
      const keep = new Set<string>([
        ...CORE_ROLES,
        ...picks.flatMap(pick => (pick.role ? [pick.role] : [])),
        ...(current.avatar ? ["avatar"] : []),
      ]);
      return {
        ...current,
        picks,
        models: Object.fromEntries(
          Object.entries(current.models).filter(([role]) => keep.has(role)),
        ),
      };
    });
    markDirty();
  };

  const save = async () => {
    if (!draft || savingRef.current || reloadingRef.current || busy) return;
    const patch = buildDiscussPlanPatch(detail, draft);
    if (discussPlanPatchIsEmpty(patch)) {
      exitEdit();
      return;
    }
    const request = beginRequest();
    if (!request) return;
    savingRef.current = true;
    setSaving(true);
    setError("");
    setConflict(false);
    try {
      const next = await updateDiscussPlan(detail.id, patch, request.signal);
      if (!request.isCurrent()) return;
      onUpdated(next);
      exitEdit();
    } catch (cause) {
      if (!request.isCurrent()) return;
      setError(discussErrorMessage(cause));
      setConflict(errorStatus(cause) === 409);
    } finally {
      savingRef.current = false;
      if (request.isCurrent()) setSaving(false);
    }
  };

  const reloadPlan = async () => {
    if (savingRef.current || reloadingRef.current) return;
    const request = beginRequest();
    if (!request) return;
    reloadingRef.current = true;
    setReloading(true);
    try {
      const next = await getDiscussGroup(detail.id, 0, request.signal);
      if (!request.isCurrent()) return;
      onUpdated(next);
      exitEdit();
    } catch (cause) {
      if (request.isCurrent()) {
        setError(discussErrorMessage(cause));
        setConflict(true);
      }
    } finally {
      reloadingRef.current = false;
      if (request.isCurrent()) setReloading(false);
    }
  };

  const options = catalog ? modelOptions(catalog) : [];
  const modelRows: ModelRow[] = draft ? [
    ...CORE_ROLES.map(role => ({
      key: `core-${role}`,
      label: seatName(role),
      role,
      value: draft.models[role] || currentMemberModel(role) || catalog?.defaults[role] || "",
    })),
    ...draft.picks
      .filter((pick): pick is DiscussPickDraft & { role: string } => !!pick.role)
      .map(pick => ({
        key: `pick-${pick.role}`,
        label: pick.name.trim() || seatName(pick.role),
        role: pick.role,
        value: draft.models[pick.role]
          || currentMemberModel(pick.role)
          || catalog?.defaults[pick.role]
          || "",
      })),
    ...(draft.avatar ? [{
      key: "avatar",
      label: "分身",
      role: "avatar",
      value: draft.models.avatar || currentMemberModel("avatar") || catalog?.defaults.avatar || "",
    }] : []),
  ] : [];

  const teamMembers: DiscussTeamMember[] = draft ? (() => {
    let customIndex = 0;
    return draft.picks.map(pick => {
      if (pick.role) {
        return {
          key: pick.role,
          role: pick.role,
          name: pick.name,
          does: pick.does,
          focus: pick.focus,
        };
      }
      const key = customKeys[customIndex] ?? `custom-${customIndex}`;
      customIndex += 1;
      return {
        key,
        name: pick.name,
        does: pick.does,
        focus: pick.focus,
      };
    });
  })() : [];

  const renderMember = (member: DiscussMember) => (
    <li key={`${member.role}-${member.name}`} className="min-w-0 border-t border-[color:var(--carve)] py-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-fs-15">
        <span className="min-w-0 break-words text-[color:var(--ink)]">{member.name}</span>
        <span className="tag">{kindLabel(member.kind)}</span>
      </div>
      {!!member.does && (
        <p className="mt-1 whitespace-pre-wrap break-words text-fs-13 leading-[1.8] text-[color:var(--ink2)]">{member.does}</p>
      )}
      {discussMemberShowsFocus(member) && (
        <p className="mt-1 whitespace-pre-wrap break-words text-fs-13 leading-[1.8] text-[color:var(--ink2)]">分工：{member.focus}</p>
      )}
      <p className="readout mt-1 break-words text-fs-12">模型：{discussModelLabel(member.model)}</p>
    </li>
  );

  return (
    <div className="min-w-0 space-y-5">
      {waitingStart && !editing && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn min-h-10"
            disabled={busy || !canEdit}
            onClick={enterEdit}
          >
            修改方案
          </button>
        </div>
      )}
      {waitingStart && catalogError && (
        <ErrorNotice message={catalogError} retry={() => onReloadCatalog()} />
      )}

      {editing && draft && catalog ? (
        <div className="min-w-0 space-y-6">
          {error && (
            <div role="alert" className="ceramic-card flex flex-col gap-2 p-3 text-fs-13">
              <p className="whitespace-pre-wrap break-words text-[color:var(--ink)]">{error}</p>
              {conflict && (
                <button
                  type="button"
                  className="btn btn-quiet min-h-10 self-start"
                  disabled={reloading}
                  onClick={() => void reloadPlan()}
                >
                  {reloading && <Loader2 size={14} className="animate-spin" />}重新加载方案
                </button>
              )}
            </div>
          )}

          <fieldset disabled={busy || saving || reloading} className="min-w-0 space-y-6">
            <label className="block min-w-0 space-y-1">
              <span className="text-fs-13 text-[color:var(--ink2)]">标题</span>
              <input
                type="text"
                value={draft.title}
                maxLength={TITLE_MAX}
                onChange={event => updateDraft(current => ({ ...current, title: event.target.value }))}
                className={FIELD_CLASS}
              />
            </label>

            <section className="min-w-0">
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">完成标准</h3>
              <div className="space-y-2">
                {draft.criteria.map((text, index) => (
                  <div key={index} className="flex min-w-0 items-center gap-2">
                    <span className="readout w-6 shrink-0 text-fs-12">C{index + 1}</span>
                    <input
                      type="text"
                      value={text}
                      maxLength={CRITERION_MAX}
                      onChange={event => updateCriterion(index, event.target.value)}
                      className={FIELD_CLASS}
                    />
                    <button
                      type="button"
                      className="btn btn-quiet min-h-10 shrink-0"
                      disabled={draft.criteria.length <= CRITERIA_MIN}
                      onClick={() => removeCriterion(index)}
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="btn min-h-10 mt-2"
                disabled={draft.criteria.length >= CRITERIA_MAX}
                onClick={addCriterion}
              >
                <Plus size={14} />添加一条标准
              </button>
            </section>

            <section className="min-w-0">
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">调研成员</h3>
              <DiscussTeamEditor
                members={teamMembers}
                rolePool={rolePool}
                maxMembers={catalog.limits.members_max}
                nameMax={catalog.limits.name_max}
                doesMax={catalog.limits.custom_does_max}
                focusMax={FOCUS_MAX}
                mode="plan"
                disabled={busy || saving || reloading}
                onChange={handleTeamChange}
              />
            </section>

            <section className="min-w-0">
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">固定席位</h3>
              <div className="space-y-4">
                {draft.identities.map(seat => (
                  <div key={seat.role} className="min-w-0 border-t border-[color:var(--carve)] pt-4">
                    <p className="mb-2 text-fs-13">{seatName(seat.role)}</p>
                    <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
                      <label className="block min-w-0 space-y-1">
                        <span className="text-fs-12 text-[color:var(--ink2)]">名字</span>
                        <input
                          type="text"
                          value={seat.name}
                          maxLength={catalog.limits.name_max}
                          onChange={event => updateSeat(seat.role, { name: event.target.value })}
                          className={FIELD_CLASS}
                        />
                      </label>
                      <label className="block min-w-0 space-y-1">
                        <span className="text-fs-12 text-[color:var(--ink2)]">身份设定</span>
                        <textarea
                          rows={2}
                          value={seat.persona}
                          maxLength={catalog.limits.persona_max}
                          onChange={event => updateSeat(seat.role, { persona: event.target.value })}
                          className={`${FIELD_CLASS} resize-y`}
                        />
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="min-w-0">
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">预算与轮数</h3>
              <div className="grid grid-cols-2 items-start gap-4 mobile:grid-cols-1">
                <label className="block min-w-0">
                  <span className="mb-2 block text-fs-12 text-[color:var(--ink2)]">预算</span>
                  <span className="flex items-center gap-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      min={catalog.limits.budget_min}
                      max={catalog.limits.budget_max}
                      step={1}
                      value={budgetText}
                      onChange={event => updateBudget(event.target.value)}
                      className={FIELD_CLASS}
                    />
                    <span className="shrink-0 text-fs-12 text-[color:var(--ink2)]">颗草莓</span>
                  </span>
                </label>
                <label className="block min-w-0">
                  <span className="mb-2 block text-fs-12 text-[color:var(--ink2)]">轮数</span>
                  <select
                    value={draft.max_rounds}
                    onChange={event => updateDraft(current => ({
                      ...current,
                      max_rounds: Number(event.target.value),
                    }))}
                    className={FIELD_CLASS}
                  >
                    {Array.from(
                      { length: catalog.limits.rounds_max - catalog.limits.rounds_min + 1 },
                      (_, index) => catalog.limits.rounds_min + index,
                    ).map(round => <option key={round} value={round}>{round}</option>)}
                  </select>
                </label>
              </div>
            </section>

            <div>
              <label className="flex min-h-10 items-center gap-2 text-fs-15">
                <input
                  type="checkbox"
                  checked={draft.avatar}
                  onChange={event => {
                    const checked = event.target.checked;
                    updateDraft(current => {
                      const models = { ...current.models };
                      if (!checked) delete models.avatar;
                      return { ...current, avatar: checked, models };
                    });
                  }}
                  className="h-5 w-5 shrink-0 accent-[color:var(--ink)]"
                />
                分身参与
              </label>
            </div>

            <section className="min-w-0">
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">各成员的模型</h3>
              <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
                {modelRows.map(row => (
                  <label key={row.key} className="block min-w-0 space-y-1">
                    <span className="text-fs-12 text-[color:var(--ink2)]">{row.label}</span>
                    <select
                      value={row.value}
                      onChange={event => updateModel(row.role, event.target.value)}
                      className={FIELD_CLASS}
                    >
                      {withCurrentModel(options, row.value).map(option => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </section>

            <section className="min-w-0">
              {questions.length > 0 && (
                <div className="mb-3">
                  <p className="text-fs-12 text-[color:var(--ink2)]">主持人想问你</p>
                  <ul className="mt-1 list-none space-y-1 p-0">
                    {questions.map((question, index) => (
                      <li key={index} className="whitespace-pre-wrap break-words text-fs-13 leading-[1.8]">
                        {question}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">你的回答</h3>
              <textarea
                rows={4}
                value={draft.answers}
                maxLength={ANSWERS_MAX}
                onChange={event => updateDraft(current => ({ ...current, answers: event.target.value }))}
                className={`${FIELD_CLASS} resize-y`}
              />
              <p className="readout mt-1 text-right text-fs-12">{answerLength(draft.answers)} / {ANSWERS_MAX}</p>
            </section>
          </fieldset>

          <div className="flex flex-wrap items-center gap-3 border-t border-[color:var(--carve)] pt-4">
            <button
              type="button"
              className="btn btn-primary min-h-10"
              disabled={busy || saving || reloading}
              onClick={() => void save()}
            >
              {saving && <Loader2 size={14} className="animate-spin" />}保存修改
            </button>
            <button
              type="button"
              className="btn btn-quiet min-h-10"
              disabled={saving || reloading}
              onClick={exitEdit}
            >
              放弃修改
            </button>
          </div>
        </div>
      ) : (
        <div className="min-w-0 space-y-5">
          <section className="min-w-0">
            <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">目标</h3>
            <p className="whitespace-pre-wrap break-words text-fs-15 leading-[1.9] text-[color:var(--ink)]">{plan.goal}</p>
          </section>

          <section className="min-w-0">
            <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">成果形式</h3>
            <p className="text-fs-15 text-[color:var(--ink)]">{deliverableLabel(plan.deliverable.kind)}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-fs-13 leading-[1.8] text-[color:var(--ink2)]">
              {plan.deliverable.outline.map((item, index) => (
                <li key={index} className="break-words">{item}</li>
              ))}
            </ul>
          </section>

          <section className="min-w-0">
            <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">完成标准</h3>
            <ul className="list-none space-y-1 p-0">
              {plan.criteria.map((criterion, index) => (
                <li key={criterion.id || index} className="flex min-w-0 items-start gap-2 text-fs-13 leading-[1.8]">
                  <span className="readout shrink-0">C{index + 1}</span>
                  <span className="min-w-0 break-words text-[color:var(--ink)]">{criterion.text}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="min-w-0">
            <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">成员与分工</h3>
            <ul className="list-none p-0">
              {detail.members.map(renderMember)}
            </ul>
          </section>

          {questions.length > 0 && (
            <section className="min-w-0">
              <h3 className="mb-2 text-fs-13 text-[color:var(--ink2)]">主持人想问你</h3>
              <ul className="list-none space-y-1 p-0">
                {questions.map((question, index) => (
                  <li key={index} className="whitespace-pre-wrap break-words text-fs-13 leading-[1.8] text-[color:var(--ink)]">
                    {question}
                  </li>
                ))}
              </ul>
              <h4 className="mt-3 mb-1 text-fs-12 text-[color:var(--ink2)]">你的回答</h4>
              <p className="whitespace-pre-wrap break-words text-fs-13 leading-[1.8] text-[color:var(--ink)]">
                {answers.trim() ? answers : "还没有回答。"}
              </p>
            </section>
          )}

          <details className="min-w-0 border-t border-[color:var(--carve)] pt-3">
            <summary className="flex min-h-10 cursor-pointer items-center text-fs-13 text-[color:var(--ink2)]">原始诉求</summary>
            <p className="mt-2 whitespace-pre-wrap break-words text-fs-13 leading-[1.8] text-[color:var(--ink)]">{detail.request}</p>
          </details>
        </div>
      )}
    </div>
  );
}
