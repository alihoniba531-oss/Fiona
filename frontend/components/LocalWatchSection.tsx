"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/auth";
import { API_BASE as API } from "@/lib/config";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { CHAT_MODEL_REV_KEY, getChatModel } from "@/lib/chatModel";
import { formatBeijingDateTime } from "@/lib/beijingTime";
import {
  LocalWatchError, localWatchErrorMessage, localWatchRequest, localWatchNotificationsEnabled,
  setLocalWatchNotifications, localWatchDraft, localWatchRulePayload, localWatchCaptureMessage, type LocalWatchDevice, type LocalWatchWindow,
  type LocalWatchRule, type LocalWatchRuleDraft, type LocalWatchKind,
} from "@/lib/localWatch";

const inputClass = "h-[42px] w-full rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 text-base shadow-[inset_0_1px_2px_var(--pool)] outline-none placeholder:text-[color:var(--ink2)] focus:border-[color:var(--ink)] disabled:opacity-50";
const noteClass = "text-[13px] leading-[1.85] text-[color:var(--ink2)]";
const buttonClass = "btn min-h-10 px-3 text-[13px] disabled:opacity-50";
const typeLabels: Record<LocalWatchKind, string> = { keyword: "关键词", number: "数值", ai: "AI" };
const emptyRule = () => localWatchDraft();
const tokenCommand = "mkdir -p ~/.fiona && umask 077 && pbpaste > ~/.fiona/watcher.token";

function lastSeen(value: string | null): string {
  if (!value) return "尚未上线";
  const date = new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value.replace(" ", "T")}Z`);
  return Number.isNaN(date.getTime()) ? "时间未知" : formatBeijingDateTime(date, true);
}

export default function LocalWatchSection({ username, sectionClass, headingClass }: {
  username: string; sectionClass: string; headingClass: string;
}) {
  const [devices, setDevices] = useState<LocalWatchDevice[]>([]);
  const [rules, setRules] = useState<LocalWatchRule[]>([]);
  const [windows, setWindows] = useState<LocalWatchWindow[]>([]);
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>([]);
  const [claudeAvailable, setClaudeAvailable] = useState(false);
  const [available, setAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [deviceName, setDeviceName] = useState("我的 Mac");
  const [token, setToken] = useState("");
  const [notifications, setNotifications] = useState(false);
  const [draft, setDraft] = useState<LocalWatchRuleDraft>(emptyRule);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [label, setLabel] = useState("价格");
  const [op, setOp] = useState<">" | ">=" | "<" | "<=">(">=");
  const [threshold, setThreshold] = useState("100");
  const [condition, setCondition] = useState("");
  const [model, setModel] = useState<"platform" | "claude">("platform");
  const { beginRequest } = useAccountRequest(username);
  const { beginRequest: beginRead } = useAccountRequest(username);
  const { beginRequest: beginRulesRead } = useAccountRequest(username);
  const disabled = loading || busy || !username || !available;

  const refresh = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    try {
      const [nextDevices, nextRules, nextWindows, chatModel, conversationResponse] = await Promise.all([
        localWatchRequest<LocalWatchDevice[]>("/devices", { signal: request.signal }),
        localWatchRequest<LocalWatchRule[]>("/rules", { signal: request.signal }),
        localWatchRequest<LocalWatchWindow[]>("/windows", { signal: request.signal }),
        getChatModel(request.signal).catch(() => null),
        apiFetch(`${API}/conversations`, { signal: request.signal, cache: "no-store" })
          .then(response => response.ok ? response.json() : null).catch(() => null),
      ]);
      if (!request.isCurrent()) return;
      setDevices(nextDevices); setRules(nextRules); setWindows(nextWindows); setAvailable(true);
      setClaudeAvailable(!!(chatModel?.available && chatModel.config?.enabled
        && chatModel.config.provider === "anthropic" && chatModel.config.status === "ok"));
      setConversations(conversationResponse?.conversations ?? []);
      setNotifications(localWatchNotificationsEnabled(username));
    } catch (cause) {
      if (!request.isCurrent()) return;
      if (cause instanceof LocalWatchError && cause.status === 404) setAvailable(false);
      setError(localWatchErrorMessage(cause));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRead, username]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setDevices([]); setRules([]); setWindows([]); setConversations([]);
      setToken(""); setFormOpen(false); setEditingId(null); setDraft(emptyRule());
      setNotifications(false); setClaudeAvailable(false); setAvailable(true);
      setLoading(true); setBusy(false); setError(""); setSuccess("");
      void refresh();
    });
    const onStorage = (event: StorageEvent) => { if (event.key === CHAT_MODEL_REV_KEY) void refresh(); };
    window.addEventListener("storage", onStorage);
    return () => {
      cancelled = true;
      window.removeEventListener("storage", onStorage);
    };
  }, [refresh]);

  useEffect(() => {
    if (!username || !available) return;
    let stopped = false;
    let pending = false;
    let active: AbortController | null = null;
    const tick = async () => {
      if (stopped || pending || document.visibilityState !== "visible") return;
      // A separate account lane keeps status polling from cancelling a slow
      // initial load of devices, windows, conversations and model settings.
      const request = beginRulesRead();
      if (!request) return;
      const controller = new AbortController();
      const abort = () => controller.abort();
      active = controller;
      pending = true;
      request.signal.addEventListener("abort", abort, { once: true });
      try {
        const nextRules = await localWatchRequest<LocalWatchRule[]>("/rules", { signal: controller.signal });
        if (stopped || controller.signal.aborted || document.visibilityState !== "visible" || !request.isCurrent()) return;
        setRules(nextRules);
      } catch (cause) {
        if (stopped || controller.signal.aborted || !request.isCurrent()) return;
        if (cause instanceof LocalWatchError && cause.status === 404) {
          stopped = true;
          window.clearInterval(timer);
          setAvailable(false);
        }
      } finally {
        request.signal.removeEventListener("abort", abort);
        if (active === controller) active = null;
        pending = false;
      }
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
      else active?.abort();
    };
    const timer = window.setInterval(onVisible, 10_000);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      active?.abort();
    };
  }, [available, beginRulesRead, username]);

  const operate = async (action: (signal: AbortSignal) => Promise<void>, message: string) => {
    if (disabled) return;
    const request = beginRequest();
    if (!request) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await action(request.signal);
      if (!request.isCurrent()) return;
      setSuccess(message);
      await refresh();
    } catch (cause) {
      if (request.isCurrent()) setError(localWatchErrorMessage(cause));
    } finally {
      if (request.isCurrent()) setBusy(false);
    }
  };

  const createDevice = () => {
    setToken("");
    void operate(async signal => {
      const device = await localWatchRequest<LocalWatchDevice & { token: string }>("/devices", {
        method: "POST", signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: deviceName.trim() || "我的 Mac" }),
      });
      if (!signal.aborted) setToken(device.token);
    }, "设备令牌已生成，请立即复制并保存");
  };

  const copyToken = async () => {
    try { await navigator.clipboard.writeText(token); setSuccess("令牌已复制，粘贴到下方命令写入文件"); }
    catch { setError("无法访问剪贴板，请手动复制令牌"); }
  };

  const editRule = (rule?: LocalWatchRule) => {
    // The model section can change BYOK in this same document; storage events
    // are only emitted in other documents, so reread eligibility when editing.
    void refresh();
    setDraft(localWatchDraft(rule));
    setEditingId(rule?.id ?? null);
    setKeywords(rule?.params.keywords?.join("\n") ?? "");
    setLabel(rule?.params.label ?? "价格"); setOp(rule?.params.op ?? ">=");
    setThreshold(String(rule?.params.threshold ?? 100));
    setCondition(rule?.params.condition ?? ""); setModel(rule?.params.model ?? "platform");
    setError(""); setFormOpen(true);
  };

  const saveRule = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const words = keywords.split(/[\n,，]/).map(word => word.trim()).filter(Boolean);
    if (!draft.name.trim() || (!draft.app_match.trim() && !draft.title_match.trim())) {
      setError("请填写规则名称，以及应用名或窗口标题"); return;
    }
    if (draft.kind === "keyword" && (!words.length || words.length > 10 || words.some(word => Array.from(word).length > 20))) {
      setError("请填写 1–10 个关键词，每个不超过 20 字"); return;
    }
    if (draft.kind === "number" && (!label.trim() || !threshold.trim() || !Number.isFinite(Number(threshold)))) {
      setError("请填写标签和有效的数值阈值"); return;
    }
    if (draft.kind === "ai" && (Array.from(condition.trim()).length < 2 || (model === "claude" && !claudeAvailable))) {
      setError(model === "claude" && !claudeAvailable ? "请先启用 Anthropic 自带模型" : "提醒条件至少需要 2 字"); return;
    }
    const params = draft.kind === "keyword" ? { keywords: words }
      : draft.kind === "number" ? { label: label.trim(), op, threshold: Number(threshold) }
      : { condition: condition.trim(), model };
    void operate(async signal => {
      await localWatchRequest(editingId === null ? "/rules" : `/rules/${editingId}`, {
        method: editingId === null ? "POST" : "PATCH", signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(localWatchRulePayload({ ...draft, params })),
      });
      if (!signal.aborted) { setFormOpen(false); setEditingId(null); }
    }, editingId === null ? "规则已创建" : "规则已保存");
  };

  const allowNotifications = async () => {
    if (!("Notification" in window)) { setError("此浏览器不支持通知"); return; }
    const request = beginRequest();
    if (!request) return;
    try {
      const permission = await Notification.requestPermission();
      if (!request.isCurrent()) return;
      setLocalWatchNotifications(username, permission === "granted");
      setNotifications(permission === "granted");
      setSuccess(permission === "granted" ? "已允许本机提醒的浏览器通知" : "尚未允许通知，可在浏览器设置中调整权限");
    } catch { if (request.isCurrent()) setError("无法启用通知，请检查浏览器权限和本地存储设置"); }
  };

  return <section className={sectionClass}>
    <h2 className={headingClass}>本机监控</h2>
    <div className="min-w-0 space-y-5">
      <p className={noteClass}>在自己的 Mac 上监控指定程序窗口，符合规则时由分身在聊天里提醒你。只支持 macOS 14 及以上；不会点击、操作或自动回复其他程序。</p>
      <p className={noteClass}>屏幕锁定或显示器休眠时 macOS 不允许截取窗口，期间无法监控。如果需要离开电脑时也能监控，可以在 系统设置 → 锁定屏幕 中延长自动锁定时间，但要自行权衡安全。</p>
      {loading && <p className={noteClass}>正在加载本机监控…</p>}
      {!available && <p className={noteClass}>本机监控暂未开启，请联系管理员。</p>}
      {error && <p role="alert" className="text-[13px] text-[color:var(--seal)]">{error}</p>}
      {success && <p role="status" className={noteClass}>{success}</p>}

      <div className="space-y-2">
        <h3 className="text-sm font-medium">设备</h3>
        <label className="block text-[13px]" htmlFor="local-watch-device-name">设备名称</label>
        <input id="local-watch-device-name" className={inputClass} value={deviceName} maxLength={60} disabled={disabled} onChange={event => setDeviceName(event.target.value)} />
        <button className={buttonClass} disabled={disabled || devices.filter(device => !device.revoked).length >= 3} onClick={createDevice}>生成设备令牌</button>
        <p className={noteClass}>每个账号最多 3 台有效设备。令牌只显示一次，请立即复制；不要发给他人或保存到公开仓库。</p>
        {token && <div className="space-y-2 rounded-[8px] border border-[color:var(--rule2)] p-3">
          <label htmlFor="local-watch-token" className="block text-[13px]">一次性显示的设备令牌</label>
          <textarea id="local-watch-token" className={`${inputClass} h-auto break-all py-2`} readOnly rows={3} value={token} />
          <div className="flex flex-wrap gap-2"><button className={buttonClass} onClick={() => void copyToken()}>复制令牌</button>
            <button className={buttonClass} onClick={() => setToken("")}>我已保存，隐藏令牌</button></div>
        </div>}
        <p className={noteClass}>复制后在 Mac 终端运行以下命令。令牌文件必须保持 600 权限：</p>
        <code className="block break-all rounded-[8px] bg-[color:var(--mount)] p-3 text-xs leading-6">{tokenCommand}</code>
        <ul className="space-y-2" aria-label="监控设备">
          {devices.filter(device => !device.revoked).map(device => <li key={device.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-[color:var(--carve)] pt-2">
            <div className="min-w-0"><p className="break-all text-sm">{device.name || "未命名设备"}</p><p className={noteClass}>最后在线：{lastSeen(device.last_seen_at)}</p></div>
            <button className={buttonClass} disabled={disabled} onClick={() => {
              if (confirm(`吊销「${device.name || "未命名设备"}」的令牌？监控程序将停止。`)) {
                setToken(""); void operate(async signal => { await localWatchRequest(`/devices/${device.id}`, { method: "DELETE", signal }); }, "设备已吊销");
              }
            }}>吊销</button>
          </li>)}
        </ul>
      </div>

      <div className="space-y-2 border-t border-[color:var(--carve)] pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-medium">最近发现的窗口</h3><button className={buttonClass} disabled={disabled} onClick={() => void refresh()}>刷新</button></div>
        {windows.length ? <ul className="space-y-2">{windows.map((window, index) => <li key={`${window.bundle_id}-${index}`}>
          <button className="w-full rounded-[8px] border border-[color:var(--rule2)] p-3 text-left disabled:opacity-50" disabled={disabled || rules.length >= 20} onClick={() => {
            editRule(); setDraft({ ...emptyRule(),
              app_match: window.app_name && Array.from(window.app_name).slice(0, 60).join(""),
              title_match: Array.from(window.title).slice(0, 60).join(""),
            });
          }}><span className="block break-all text-sm">{window.app_name}</span><span className={`${noteClass} block break-all`}>{window.title || "无标题窗口"}</span></button>
        </li>)}</ul> : <p className={noteClass}>尚未发现窗口，请先启动 Mac 监控程序。窗口清单保留 5 分钟。</p>}
      </div>

      <div className="space-y-3 border-t border-[color:var(--carve)] pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-medium">规则（{rules.length}/20）</h3><button className={buttonClass} disabled={disabled || rules.length >= 20} onClick={() => editRule()}>新建规则</button></div>
        <ul className="space-y-3" aria-label="本机监控规则">{rules.map(rule => <li key={rule.id} className="space-y-2 rounded-[8px] border border-[color:var(--rule2)] p-3">
          <p className="break-all text-sm font-medium">{rule.name} <span className={noteClass}>· {typeLabels[rule.kind]} · {rule.enabled ? "已启用" : "已停用"}</span></p>
          <p className={`${noteClass} break-all`}>应用：{rule.app_match || "任意"}；标题：{rule.title_match || "任意"}</p>
          <p role="status" className={`break-all ${rule.capture?.ok || rule.capture?.neutral ? noteClass : "text-[13px] leading-[1.85] text-[color:var(--seal)]"}`}>{localWatchCaptureMessage(rule)}</p>
          <div className="flex flex-wrap gap-2">
            <button className={buttonClass} disabled={disabled} onClick={() => void operate(async signal => {
              await localWatchRequest(`/rules/${rule.id}`, { method: "PATCH", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !rule.enabled }) });
            }, rule.enabled ? "规则已停用" : "规则已启用")}>{rule.enabled ? "停用" : "启用"}</button>
            <button className={buttonClass} disabled={disabled} onClick={() => editRule(rule)}>编辑</button>
            <button className={buttonClass} disabled={disabled} onClick={() => {
              if (confirm(`删除规则「${rule.name}」？`)) void operate(async signal => { await localWatchRequest(`/rules/${rule.id}`, { method: "DELETE", signal }); }, "规则已删除");
            }}>删除</button>
          </div>
        </li>)}</ul>
        {formOpen && <form onSubmit={saveRule} className="space-y-3 rounded-[8px] border border-[color:var(--rule2)] p-3">
          <h4 className="text-sm font-medium">{editingId === null ? "新建规则" : "编辑规则"}</h4>
          <label className="block space-y-1 text-[13px]">名称（1–30 字）<input className={inputClass} value={draft.name} required maxLength={30} disabled={disabled} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label>
          <label className="block space-y-1 text-[13px]">应用名包含<input className={inputClass} value={draft.app_match} maxLength={60} placeholder="例如：微信" disabled={disabled} onChange={event => setDraft({ ...draft, app_match: event.target.value })} /></label>
          <label className="block space-y-1 text-[13px]">窗口标题包含<input className={inputClass} value={draft.title_match} maxLength={60} placeholder="例如：工作群（应用名和标题至少填一项）" disabled={disabled} onChange={event => setDraft({ ...draft, title_match: event.target.value })} /></label>
          <label className="block space-y-1 text-[13px]">类型<select className={inputClass} value={draft.kind} disabled={disabled} onChange={event => setDraft({ ...draft, kind: event.target.value as LocalWatchKind })}>{Object.entries(typeLabels).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
          {draft.kind === "keyword" && <label className="block space-y-1 text-[13px]">关键词（每行一个，也可用逗号分隔）<textarea className={`${inputClass} h-24 py-2`} value={keywords} required placeholder={"@我\n老板的名字"} disabled={disabled} onChange={event => setKeywords(event.target.value)} /><span className={noteClass}>例如：「@我」「老板的名字」。任一关键词出现即提醒。</span></label>}
          {draft.kind === "number" && <div className="space-y-2">
            <label className="block space-y-1 text-[13px]">数值标签<input className={inputClass} value={label} required maxLength={20} disabled={disabled} onChange={event => setLabel(event.target.value)} /></label>
            <label className="block space-y-1 text-[13px]">比较<select className={inputClass} value={op} disabled={disabled} onChange={event => setOp(event.target.value as typeof op)}>{[">", ">=", "<", "<="].map(value => <option key={value}>{value}</option>)}</select></label>
            <label className="block space-y-1 text-[13px]">阈值<input className={inputClass} type="number" step="any" value={threshold} required disabled={disabled} onChange={event => setThreshold(event.target.value)} /></label>
            <p className={noteClass}>例如：标签「价格」 &gt;= 100。</p>
          </div>}
          {draft.kind === "ai" && <div className="space-y-2">
            <label className="block space-y-1 text-[13px]">提醒条件（2–200 字）<textarea className={`${inputClass} h-24 py-2`} value={condition} required minLength={2} maxLength={200} placeholder="下载完成或出现报错时提醒我" disabled={disabled} onChange={event => setCondition(event.target.value)} /></label>
            <label className="block space-y-1 text-[13px]">判断模型<select className={inputClass} value={model} disabled={disabled} onChange={event => setModel(event.target.value as typeof model)}><option value="platform">平台模型（阿里云千问）</option><option value="claude" disabled={!claudeAvailable}>Claude（Anthropic）</option></select></label>
            {!claudeAvailable && <p className={noteClass}>请在「聊天模型」中保存并启用 Anthropic 自带模型后再选 Claude。</p>}
            <p className={noteClass}>例如：「下载完成或出现报错时提醒我」。不扣草莓。</p>
          </div>}
          <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
            <label className="block space-y-1 text-[13px]">截图间隔（2–60 秒）<input className={inputClass} type="number" value={draft.interval_seconds} min={2} max={60} required disabled={disabled} onChange={event => setDraft({ ...draft, interval_seconds: Number(event.target.value) })} /></label>
            <label className="block space-y-1 text-[13px]">提醒冷却（10–3600 秒）<input className={inputClass} type="number" value={draft.cooldown_seconds} min={10} max={3600} required disabled={disabled} onChange={event => setDraft({ ...draft, cooldown_seconds: Number(event.target.value) })} /></label>
          </div>
          <label className="block space-y-1 text-[13px]">提醒发送到<select className={inputClass} value={draft.conversation_id ?? ""} disabled={disabled} onChange={event => setDraft({ ...draft, conversation_id: event.target.value || null })}><option value="">默认会话</option>{conversations.map(conversation => <option key={conversation.id} value={conversation.id}>{conversation.title || "未命名会话"}</option>)}</select></label>
          <div className="flex flex-wrap gap-2"><button className={buttonClass} type="submit" disabled={disabled}>保存规则</button><button className={buttonClass} type="button" disabled={busy} onClick={() => setFormOpen(false)}>取消</button></div>
        </form>}
      </div>

      <div className="space-y-2 border-t border-[color:var(--carve)] pt-4">
        <button className={buttonClass} disabled={disabled} onClick={() => {
          if (!notifications) { void allowNotifications(); return; }
          try { setLocalWatchNotifications(username, false); setNotifications(false); setSuccess("已关闭本机提醒的浏览器通知"); }
          catch { setError("无法保存通知设置，请检查浏览器本地存储"); }
        }}>{notifications ? "关闭浏览器通知" : "允许浏览器通知"}</button>
        <p className={noteClass}>默认不弹浏览器通知。页面关闭时不会实时弹出，提醒仍会保存到聊天。</p>
        <p className={noteClass}>监控程序只在你的 Mac 上截图并识别文字，截图和整页文字不会上传；只有窗口里新出现的文字会发给 Fiona 用于判断，不落日志。AI 判断规则会把新出现的文字发给阿里云千问（选 Claude 时发给 Anthropic）。只会保存提醒摘要。</p>
      </div>
    </div>
  </section>;
}
