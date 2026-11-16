"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Loader2, Plus } from "lucide-react";
import DiscussTeamEditor, { type DiscussTeamMember } from "@/components/discuss/DiscussTeamEditor";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import {
  createDiscussGroup,
  getDiscussCatalog,
  getDiscussTaskCard,
  type DiscussCatalog,
  type DiscussCoreRole,
  type DiscussCreateForm as DiscussCreateFormState,
  type DiscussIdentityDraft,
  type DiscussLensDraft,
  type DiscussTaskCardView,
} from "@/lib/discuss";
import {
  applyDiscussTaskPrefill,
  buildDiscussCreateBody,
  defaultDiscussCustomMemberModel,
  discussErrorMessage,
  discussHref,
  discussModelLabel,
  validateDiscussCreate,
} from "@/lib/discussLogic";
import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } from "@/lib/useAccountIdentity";

const coreRoles: DiscussCoreRole[] = ["host", "critic", "writer", "acceptor"];
const fieldClass = "ceramic-card min-h-10 w-full min-w-0 rounded-[10px] px-4 py-3 text-fs-16.5 text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";

type ModelRow = { key: string; label: string; value: string; change: (value: string) => void };

function taskCardMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 403);
}

function modelOptions(catalog: DiscussCatalog) {
  const options = catalog.models.map(model => ({ value: model.id, label: discussModelLabel(model.id) }));
  if (catalog.byok) options.push({ value: "byok:self", label: "我的模型" });
  return options;
}

function withCurrentModel(options: { value: string; label: string }[], value: string) {
  if (!value || options.some(option => option.value === value)) return options;
  return [...options, { value, label: discussModelLabel(value) }];
}

function initialForm(catalog: DiscussCatalog): DiscussCreateFormState {
  const fallbackModel = catalog.models[0]?.id ?? "";
  const defaultModel = (role: string) => catalog.defaults[role] ?? fallbackModel;
  return {
    request: "",
    materials: "",
    team: "host",
    lenses: catalog.roles.filter(role => role.kind === "lens").map(role => ({
      role: role.id,
      selected: false,
      name: role.name,
      does: role.does,
      default_name: role.name,
      default_does: role.does,
      model: defaultModel(role.id),
      default_model: defaultModel(role.id),
    })),
    custom_members: [],
    avatar: true,
    avatar_model: defaultModel("avatar"),
    default_avatar_model: defaultModel("avatar"),
    budget_strawberries: catalog.limits.budget_default,
    max_rounds: catalog.limits.rounds_default,
    identities: coreRoles.map(role => ({
      role,
      name: "",
      persona: "",
      model: defaultModel(role),
      default_model: defaultModel(role),
    })),
  };
}

export default function DiscussCreateForm({ embedded, taskId }: { embedded: boolean; taskId?: string }) {
  const owner = useAccountIdentity();
  const identityPending = useAccountIdentityPending();
  return <CreateForm key={owner} owner={owner} identityPending={identityPending} embedded={embedded} taskId={taskId} />;
}

function CreateForm({ owner, embedded, identityPending = false, taskId }: { owner: string; embedded: boolean; identityPending?: boolean; taskId?: string }) {
  const router = useRouter();
  const [catalog, setCatalog] = useState<DiscussCatalog | null>(null);
  const [form, setForm] = useState<DiscussCreateFormState | null>(null);
  const [customKeys, setCustomKeys] = useState<string[]>([]);
  const [budgetText, setBudgetText] = useState("");
  const [taskNotice, setTaskNotice] = useState("");
  const [submitTaskId, setSubmitTaskId] = useState("");
  const [materialsOpen, setMaterialsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const { beginRequest } = useAccountRequest(owner);

  const load = useCallback(async () => {
    if (!owner) return;
    const request = beginRequest();
    if (!request) return;
    setLoading(true);
    setLoadError("");
    setTaskNotice("");
    setSubmitTaskId("");
    try {
      const cardResult: Promise<{ task: DiscussTaskCardView | null; error: unknown }> = taskId
        ? getDiscussTaskCard(taskId, request.signal).then(
            task => ({ task, error: null }),
            error => ({ task: null, error }),
          )
        : Promise.resolve({ task: null, error: null });
      const [next, card] = await Promise.all([getDiscussCatalog(request.signal), cardResult]);
      if (!request.isCurrent()) return;
      let nextForm = initialForm(next);
      if (card.task) {
        if (card.task.group_id) {
          setTaskNotice(card.task.group
            ? `这张任务卡已经建成《${card.task.group.title}》。`
            : "这张任务卡已经用过。");
        } else {
          nextForm = applyDiscussTaskPrefill(nextForm, card.task, next.limits);
          setSubmitTaskId(taskId ?? "");
        }
      } else if (taskCardMissing(card.error)) {
        setTaskNotice("任务卡不存在，可以直接新建。");
      }
      setCatalog(next);
      setForm(nextForm);
      setCustomKeys([]);
      setBudgetText(String(nextForm.budget_strawberries));
      setMaterialsOpen(Boolean(nextForm.materials));
      setError("");
    } catch (cause) {
      if (request.isCurrent()) {
        setCatalog(null);
        setForm(null);
        setLoadError(discussErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRequest, owner, taskId]);

  useEffect(() => {
    if (!owner) return;
    void Promise.resolve().then(() => load());
  }, [load, owner]);

  const teamMembers = useMemo<DiscussTeamMember[]>(() => {
    if (!form) return [];
    const lenses = form.lenses
      .filter(lens => lens.selected)
      .map(lens => ({ key: lens.role, role: lens.role, name: lens.name, does: lens.does }));
    const custom = form.custom_members.map((member, index) => ({
      key: customKeys[index] ?? `custom-${index}`,
      name: member.name,
      does: member.does,
    }));
    return [...lenses, ...custom];
  }, [form, customKeys]);

  if (!owner) {
    return identityPending
      ? <LoadingState>正在加载身份…</LoadingState>
      : <EmptyState>请登录后使用讨论群。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>;
  }
  if (loading) return <LoadingState>正在加载讨论群目录…</LoadingState>;
  if (loadError) return <ErrorNotice message={loadError} retry={() => { void load(); }} />;
  if (!catalog || !form) return <LoadingState>正在加载讨论群目录…</LoadingState>;

  const seatName = (role: DiscussCoreRole) => catalog.roles.find(item => item.id === role)?.name ?? role;
  const updateForm = (patch: Partial<DiscussCreateFormState>) => {
    setForm(current => current ? { ...current, ...patch } : current);
    setError("");
  };
  const updateSeatModel = (role: DiscussCoreRole, model: string) => {
    setForm(current => current ? {
      ...current,
      identities: current.identities.map(seat => seat.role === role ? { ...seat, model } : seat),
    } : current);
    setError("");
  };
  const updateSeat = (role: DiscussCoreRole, patch: Partial<DiscussIdentityDraft>) => {
    setForm(current => current ? {
      ...current,
      identities: current.identities.map(seat => seat.role === role ? { ...seat, ...patch } : seat),
    } : current);
    setError("");
  };
  const updateLensModel = (role: string, model: string) => {
    setForm(current => current ? {
      ...current,
      lenses: current.lenses.map(lens => lens.role === role ? { ...lens, model } : lens),
    } : current);
    setError("");
  };
  const updateCustomModel = (index: number, model: string) => {
    setForm(current => current ? {
      ...current,
      custom_members: current.custom_members.map((member, at) => at === index ? { ...member, model } : member),
    } : current);
    setError("");
  };
  const changeBudget = (value: string) => {
    setBudgetText(value);
    setForm(current => current ? { ...current, budget_strawberries: Number(value) } : current);
    setError("");
  };
  const handleTeamChange = (members: DiscussTeamMember[]) => {
    if (!form) return;
    const customDefault = defaultDiscussCustomMemberModel(catalog) || catalog.models[0]?.id || "";
    const selected = new Map<string, DiscussTeamMember>();
    for (const member of members) if (member.role) selected.set(member.role, member);
    const previousCustom = new Map(customKeys.map((key, index) => [key, form.custom_members[index]]));
    const custom = members.filter(member => !member.role).map(member => {
      const previous = previousCustom.get(member.key);
      return {
        name: member.name,
        does: member.does,
        model: previous?.model ?? customDefault,
        default_model: previous?.default_model ?? customDefault,
      };
    });
    setCustomKeys(members.filter(member => !member.role).map(member => member.key));
    setForm(current => current ? {
      ...current,
      lenses: current.lenses.map((lens: DiscussLensDraft) => {
        const member = selected.get(lens.role);
        return member
          ? { ...lens, selected: true, name: member.name, does: member.does }
          : { ...lens, selected: false };
      }),
      custom_members: custom,
    } : current);
    setError("");
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || submitting.current) return;
    const nextForm = { ...form, budget_strawberries: Number(budgetText) };
    const message = validateDiscussCreate(nextForm, catalog.limits);
    if (message) {
      setError(message);
      return;
    }
    const request = beginRequest();
    if (!request) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const body = buildDiscussCreateBody(nextForm);
      if (submitTaskId) body.task_id = submitTaskId;
      const group = await createDiscussGroup(body, request.signal);
      if (request.isCurrent()) router.push(discussHref(`/discuss/${encodeURIComponent(group.id)}`, embedded));
    } catch (cause) {
      if (request.isCurrent()) setError(discussErrorMessage(cause));
    } finally {
      submitting.current = false;
      if (request.isCurrent()) setBusy(false);
    }
  };

  const rolePool = catalog.roles
    .filter(role => role.kind === "lens")
    .map(role => ({ id: role.id, name: role.name, does: role.does }));
  const options = modelOptions(catalog);
  const modelRows: ModelRow[] = [
    ...form.identities.map(seat => ({
      key: `seat-${seat.role}`,
      label: seatName(seat.role),
      value: seat.model,
      change: (value: string) => updateSeatModel(seat.role, value),
    })),
    ...(form.avatar ? [{
      key: "avatar",
      label: "分身",
      value: form.avatar_model,
      change: (value: string) => updateForm({ avatar_model: value }),
    }] : []),
    ...(form.team === "self" ? [
      ...form.lenses.filter(lens => lens.selected).map(lens => ({
        key: `lens-${lens.role}`,
        label: lens.name || rolePool.find(role => role.id === lens.role)?.name || lens.role,
        value: lens.model,
        change: (value: string) => updateLensModel(lens.role, value),
      })),
      ...form.custom_members.map((member, index) => ({
        key: `custom-${customKeys[index] ?? index}`,
        label: member.name.trim() || "自定义成员",
        value: member.model,
        change: (value: string) => updateCustomModel(index, value),
      })),
    ] : []),
  ];

  return <div className="mx-auto min-w-0 max-w-[900px]">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <Link href={discussHref("/discuss", embedded)} className="inline-flex min-h-10 items-center gap-1 text-fs-13 text-[color:var(--ink2)]"><ArrowLeft size={14} />返回列表</Link>
    </div>
    <h1 className="mb-5 text-fs-30 tracking-[.24em]">新建讨论群</h1>
    <div className="ceramic-card min-w-0 p-7 mobile:p-4">
      {taskNotice && <p role="status" className="ceramic-card mb-4 whitespace-pre-wrap break-words p-3 text-fs-13 text-[color:var(--ink2)]">{taskNotice}</p>}
      {error && <p role="alert" className="ceramic-card mb-4 whitespace-pre-wrap break-words p-3 text-fs-13 text-[color:var(--ink)]">{error}</p>}
      <form onSubmit={event => { void submit(event); }}>
        <fieldset disabled={busy} className="min-w-0 space-y-6">
          <div>
            <label htmlFor="discuss-request" className="mb-2 block text-fs-16.5">诉求</label>
            <textarea
              id="discuss-request"
              rows={6}
              maxLength={catalog.limits.request_max}
              value={form.request}
              onChange={event => updateForm({ request: event.target.value })}
              placeholder="例如：帮我查清楚面向东南亚做 AI 短剧值不值得做，给出结论和起步方案"
              className={`${fieldClass} resize-y`}
            />
            <p className="readout mt-1 text-right text-fs-12">{form.request.length} / {catalog.limits.request_max}</p>
          </div>
          <div>
            <p className="mb-2 text-fs-16.5">补充材料</p>
            {!materialsOpen ? <button type="button" className="btn min-h-10" onClick={() => setMaterialsOpen(true)}><Plus size={14} />添加补充材料</button> : <>
              <textarea
                rows={5}
                maxLength={catalog.limits.materials_max}
                value={form.materials}
                onChange={event => updateForm({ materials: event.target.value })}
                aria-label="补充材料"
                className={`${fieldClass} resize-y`}
              />
              <p className="readout mt-1 text-right text-fs-12">{form.materials.length} / {catalog.limits.materials_max}</p>
            </>}
          </div>
          <fieldset className="min-w-0">
            <legend className="mb-2 text-fs-16.5">队伍</legend>
            <div className="space-y-2">
              <label className="flex min-h-10 items-start gap-2 text-fs-15">
                <input type="radio" name="discuss-team" value="host" checked={form.team === "host"} onChange={() => updateForm({ team: "host" })} className="mt-1 h-4 w-4 shrink-0 accent-[color:var(--ink)]" />
                <span className="min-w-0"><span>主持人点将</span><span className="mt-1 block text-fs-13 leading-[1.8] text-[color:var(--ink2)]">主持人按你的诉求，从角色池里挑 2–4 位调研成员。开工前你还能改。</span></span>
              </label>
              <label className="flex min-h-10 items-start gap-2 text-fs-15">
                <input type="radio" name="discuss-team" value="self" checked={form.team === "self"} onChange={() => updateForm({ team: "self" })} className="mt-1 h-4 w-4 shrink-0 accent-[color:var(--ink)]" />
                <span>我来组队</span>
              </label>
            </div>
            {form.team === "self" && <div className="mt-3">
              <DiscussTeamEditor
                members={teamMembers}
                rolePool={rolePool}
                maxMembers={catalog.limits.members_max}
                nameMax={catalog.limits.name_max}
                doesMax={catalog.limits.custom_does_max}
                mode="create"
                disabled={busy}
                onChange={handleTeamChange}
              />
            </div>}
          </fieldset>
          <div>
            <label className="flex min-h-10 items-center gap-2 text-fs-15">
              <input type="checkbox" checked={form.avatar} onChange={event => updateForm({ avatar: event.target.checked })} className="h-5 w-5 shrink-0 accent-[color:var(--ink)]" />
              分身参与
            </label>
            <p className="text-fs-13 leading-[1.8] text-[color:var(--ink2)]">分身会带着你的背景进群，替你看稿。</p>
          </div>
          <fieldset className="min-w-0">
            <legend className="mb-2 text-fs-16.5">预算与轮数</legend>
            <div className="grid grid-cols-2 items-start gap-4 mobile:grid-cols-1">
              <label className="block min-w-0">
                <span className="mb-2 block text-fs-13">预算</span>
                <span className="flex items-center gap-2">
                  <input
                    type="number"
                    inputMode="numeric"
                    min={catalog.limits.budget_min}
                    max={catalog.limits.budget_max}
                    step={1}
                    value={budgetText}
                    onChange={event => changeBudget(event.target.value)}
                    className={fieldClass}
                  />
                  <span className="shrink-0 text-fs-13 text-[color:var(--ink2)]">颗草莓</span>
                </span>
              </label>
              <label className="block min-w-0">
                <span className="mb-2 block text-fs-13">轮数</span>
                <select
                  value={form.max_rounds}
                  onChange={event => updateForm({ max_rounds: Number(event.target.value) })}
                  className={fieldClass}
                >
                  {Array.from({ length: catalog.limits.rounds_max - catalog.limits.rounds_min + 1 }, (_, index) => catalog.limits.rounds_min + index).map(round => <option key={round} value={round}>{round}</option>)}
                </select>
              </label>
            </div>
            <p className="mt-2 text-fs-12 leading-[1.8] text-[color:var(--ink2)]">联网搜索每次另扣 {catalog.search_price} 颗。</p>
          </fieldset>
          <details className="min-w-0">
            <summary className="flex min-h-10 cursor-pointer items-center text-fs-13 text-[color:var(--ink2)]">更多设置</summary>
            <div className="mt-4 space-y-6">
              <section className="min-w-0">
                <h2 className="mb-2 text-fs-13">固定席位</h2>
                <div className="space-y-4">
                  {form.identities.map(seat => <div key={seat.role} className="min-w-0 border-t border-[color:var(--carve)] pt-4">
                    <p className="mb-2 text-fs-15">{seatName(seat.role)}</p>
                    <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
                      <label className="block min-w-0 space-y-1">
                        <span className="text-fs-12 text-[color:var(--ink2)]">名字</span>
                        <input
                          type="text"
                          value={seat.name}
                          maxLength={catalog.limits.name_max}
                          placeholder={seatName(seat.role)}
                          onChange={event => updateSeat(seat.role, { name: event.target.value })}
                          className={fieldClass}
                        />
                      </label>
                      <label className="block min-w-0 space-y-1">
                        <span className="text-fs-12 text-[color:var(--ink2)]">身份设定</span>
                        <textarea
                          rows={2}
                          value={seat.persona}
                          maxLength={catalog.limits.persona_max}
                          placeholder="不填就用默认"
                          onChange={event => updateSeat(seat.role, { persona: event.target.value })}
                          className={`${fieldClass} resize-y`}
                        />
                      </label>
                    </div>
                  </div>)}
                </div>
              </section>
              <section className="min-w-0 border-t border-[color:var(--carve)] pt-4">
                <h2 className="mb-2 text-fs-13">各成员的模型</h2>
                <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
                  {modelRows.map(row => <label key={row.key} className="block min-w-0 space-y-1">
                    <span className="text-fs-12 text-[color:var(--ink2)]">{row.label}</span>
                    <select value={row.value} onChange={event => row.change(event.target.value)} className={fieldClass}>
                      {withCurrentModel(options, row.value).map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>)}
                </div>
              </section>
            </div>
          </details>
          <p className="whitespace-pre-wrap break-words text-fs-12 leading-[1.8] text-[color:var(--ink2)]">{catalog.notice}</p>
          <div className="flex flex-wrap items-center gap-3 border-t border-[color:var(--carve)] pt-5">
            <button type="submit" disabled={busy} className="btn btn-primary min-h-10">{busy && <Loader2 size={14} className="animate-spin" />}{busy ? "正在建群…" : "建群并立项"}</button>
            <Link href={discussHref("/discuss", embedded)} className="btn btn-quiet min-h-10">取消</Link>
          </div>
        </fieldset>
      </form>
    </div>
  </div>;
}
