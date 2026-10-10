"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import {
  CHAT_MODEL_REV_KEY, CLAUDE_EFFORTS, CHAT_MODEL_EFFORT_LABELS, CHAT_MODEL_EFFORT_TITLES, chatModelErrorMessage, deleteChatModel, getChatModel, publishChatModelRevision, saveChatModel, setChatModelEnabled, setChatModelOptions, testChatModel,
  type ChatModelDraft, type ChatModelEffort, type ChatModelProvider, type ChatModelSettings,
} from "@/lib/chatModel";

const inputClass = "h-[42px] w-full rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 text-base shadow-[inset_0_1px_2px_var(--pool)] outline-none placeholder:text-[color:var(--ink2)] focus:border-[color:var(--ink)] disabled:opacity-50";
const noteClass = "text-[13px] leading-[1.85] text-[color:var(--ink2)]";

function providerModel(provider: ChatModelProvider): string {
  return provider.default_model ?? provider.recommended_models[0] ?? "";
}

function ChatModelForm({ initial, username }: { initial: ChatModelSettings; username: string }) {
  const [settings, setSettings] = useState(initial);
  const [providerId, setProviderId] = useState(initial.config?.provider ?? initial.providers[0].id);
  const [model, setModel] = useState(initial.config?.model ?? providerModel(initial.providers[0]));
  const [baseUrl, setBaseUrl] = useState(initial.config?.base_url ?? "");
  const [keyEditing, setKeyEditing] = useState(!initial.config || initial.config.status === "needs_reentry");
  const [keyEntered, setKeyEntered] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | "toggle" | "effort" | "delete" | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const keyInput = useRef<HTMLInputElement>(null);
  const { beginRequest } = useAccountRequest(username);
  const { beginRequest: beginRead } = useAccountRequest(username);
  const config = settings.config;
  const provider = settings.providers.find(item => item.id === providerId) ?? settings.providers[0];
  const custom = provider.id === "custom";
  const disabled = !settings.available || busy !== null;
  const needsKey = !config || config.provider !== provider.id || (custom && config.base_url !== baseUrl)
    || config.status === "needs_reentry";
  const dirty = keyEntered || (config
    ? config.provider !== provider.id || config.model !== model || (custom && config.base_url !== baseUrl)
    : provider.id !== settings.providers[0].id || model !== providerModel(settings.providers[0]) || baseUrl.length > 0);
  const switchDisabled = disabled || !config || config.status !== "ok";
  const draftProtection = useRef({ dirty, busy });
  const serverRevision = useRef(0);
  const errorOwner = useRef<"refresh" | "operation" | null>(null);
  const effortGroup = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const group = effortGroup.current;
    if (!busy && group?.contains(document.activeElement)) {
      group.querySelector<HTMLButtonElement>('button[role="radio"][aria-checked="true"]')?.focus();
    }
  }, [busy, config?.effort]);

  useEffect(() => { draftProtection.current = { dirty, busy }; }, [dirty, busy]);

  useEffect(() => {
    const refresh = () => {
      // Reads have their own account-scoped lane: a refresh invalidates an old
      // read without aborting a save, test, toggle or delete that is in progress.
      const request = beginRead();
      if (!request) return;
      const readRevision = serverRevision.current;
      getChatModel(request.signal).then(value => {
        if (!request.isCurrent() || readRevision !== serverRevision.current) return;
        setSettings(value);
        if (!draftProtection.current.dirty && !draftProtection.current.busy) {
          setProviderId(value.config?.provider ?? value.providers[0].id);
          setModel(value.config?.model ?? providerModel(value.providers[0]));
          setBaseUrl(value.config?.base_url ?? "");
          setKeyEditing(!value.config || value.config.status === "needs_reentry");
        }
        if (errorOwner.current === "refresh") {
          errorOwner.current = null;
          setError("");
        }
      }).catch(cause => {
        if (request.isCurrent() && readRevision === serverRevision.current && errorOwner.current !== "operation") {
          errorOwner.current = "refresh";
          setError(chatModelErrorMessage(cause));
        }
      });
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === CHAT_MODEL_REV_KEY) refresh();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [beginRead]);

  useEffect(() => {
    const input = keyInput.current;
    return () => { if (input) input.value = ""; };
  }, []);

  const clearKey = () => {
    if (keyInput.current) keyInput.current.value = "";
    setKeyEntered(false);
  };

  const draft = (): ChatModelDraft => {
    const apiKey = keyInput.current?.value ?? "";
    return {
      provider: provider.id, model, ...(custom ? { base_url: baseUrl } : {}),
      ...(apiKey ? { api_key: apiKey } : {}),
    };
  };

  const selectProvider = (next: ChatModelProvider) => {
    if (provider.id === next.id) return;
    clearKey();
    setProviderId(next.id);
    setModel(providerModel(next));
    setBaseUrl("");
    setKeyEditing(true);
    errorOwner.current = null;
    setError("");
    setSuccess("");
  };

  const save = async () => {
    if (disabled) return;
    const request = beginRequest();
    if (!request) return;
    errorOwner.current = null;
    serverRevision.current += 1;
    draftProtection.current = { dirty, busy: "save" };
    setBusy("save"); setError(""); setSuccess("");
    try {
      const saved = await saveChatModel(draft(), request.signal);
      if (!request.isCurrent()) return;
      serverRevision.current += 1;
      setSettings(previous => ({ ...previous, config: saved }));
      setProviderId(saved.provider); setModel(saved.model); setBaseUrl(saved.base_url ?? "");
      clearKey(); setKeyEditing(false);
      publishChatModelRevision();
      setSuccess("聊天模型已保存");
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  const test = async () => {
    if (disabled) return;
    const request = beginRequest();
    if (!request) return;
    errorOwner.current = null;
    draftProtection.current = { dirty, busy: "test" };
    setBusy("test"); setError(""); setSuccess("");
    try {
      const result = await testChatModel(draft(), request.signal);
      if (!request.isCurrent()) return;
      if (result.ok) setSuccess(`${result.message}（测试不会保存配置）`);
      else {
        errorOwner.current = "operation";
        setError(result.message);
      }
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  const toggle = async () => {
    if (switchDisabled || !config) return;
    const request = beginRequest();
    if (!request) return;
    errorOwner.current = null;
    serverRevision.current += 1;
    draftProtection.current = { dirty, busy: "toggle" };
    setBusy("toggle"); setError(""); setSuccess("");
    try {
      const saved = await setChatModelEnabled(!config.enabled, request.signal);
      if (!request.isCurrent()) return;
      serverRevision.current += 1;
      setSettings(previous => ({ ...previous, config: saved }));
      publishChatModelRevision();
      setSuccess(saved.enabled ? "已启用自带模型" : "已改用平台模型");
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  const changeEffort = async (effort: ChatModelEffort) => {
    if (disabled || !config || config.provider !== "anthropic" || provider.id !== "anthropic" || config.effort === effort) return;
    const request = beginRequest();
    if (!request) return;
    errorOwner.current = null;
    serverRevision.current += 1;
    draftProtection.current = { dirty, busy: "effort" };
    setBusy("effort"); setError(""); setSuccess("");
    try {
      const saved = await setChatModelOptions({ effort }, request.signal);
      if (!request.isCurrent()) return;
      serverRevision.current += 1;
      setSettings(previous => ({ ...previous, config: saved }));
      publishChatModelRevision();
      setSuccess("思考强度已保存");
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  const remove = async () => {
    if (disabled || !config || !confirm("确定删除自带模型配置与 Key？之后聊天将使用平台模型。")) return;
    const request = beginRequest();
    if (!request) return;
    errorOwner.current = null;
    serverRevision.current += 1;
    draftProtection.current = { dirty, busy: "delete" };
    setBusy("delete"); setError(""); setSuccess("");
    try {
      await deleteChatModel(request.signal);
      if (!request.isCurrent()) return;
      serverRevision.current += 1;
      setSettings(previous => ({ ...previous, config: null }));
      setProviderId(settings.providers[0].id);
      setModel(providerModel(settings.providers[0]));
      setBaseUrl("");
      clearKey(); setKeyEditing(true);
      publishChatModelRevision();
      setSuccess("自带模型配置与 Key 已删除");
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  return <div className="min-w-0 space-y-3">
    {!settings.available && <p role="alert" className="text-xs text-[color:var(--seal)]">{settings.unavailable_reason}</p>}
    <fieldset disabled={disabled} className="min-w-0 space-y-3 disabled:opacity-60">
      <legend className="sr-only">聊天模型接入配置</legend>
      <div role="radiogroup" aria-label="模型厂商" className="flex flex-wrap gap-2"
        onKeyDown={event => {
          if (disabled) return;
          const index = settings.providers.findIndex(item => item.id === provider.id);
          const count = settings.providers.length;
          const nextIndex = event.key === "ArrowRight" || event.key === "ArrowDown" ? (index + 1) % count
            : event.key === "ArrowLeft" || event.key === "ArrowUp" ? (index + count - 1) % count
            : event.key === "Home" ? 0 : event.key === "End" ? count - 1 : -1;
          if (nextIndex < 0) return;
          event.preventDefault(); selectProvider(settings.providers[nextIndex]);
          event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role="radio"]')[nextIndex]?.focus();
        }}>
        {settings.providers.map(item => <button key={item.id} type="button" role="radio" aria-checked={provider.id === item.id}
          tabIndex={provider.id === item.id ? 0 : -1} onClick={() => selectProvider(item)}
          className={cn("chip h-auto min-h-10 max-w-full whitespace-normal text-left", provider.id === item.id && "chip-on")}>
          {item.name}
        </button>)}
      </div>
      <div className="space-y-2">
        <label htmlFor="chat-model-name" className="block text-sm">模型名</label>
        <input id="chat-model-name" value={model} onChange={event => { setModel(event.target.value); setSuccess(""); }}
          readOnly={provider.allowed_models !== null} autoComplete="off" spellCheck={false} autoCapitalize="none"
          aria-describedby={provider.allowed_models ? "chat-model-whitelist-note" : undefined} maxLength={100} className={inputClass} />
        {provider.allowed_models && <p id="chat-model-whitelist-note" className={noteClass}>此厂商只能选择下面的支持型号。</p>}
        {(provider.allowed_models ?? provider.recommended_models).length > 0 && <div role="group" aria-label="推荐模型" className="flex flex-wrap gap-2">
          {(provider.allowed_models ?? provider.recommended_models).map(name => <button key={name} type="button" aria-pressed={model === name}
            onClick={() => { setModel(name); setSuccess(""); }} className={cn("chip h-auto min-h-8 max-w-full break-all whitespace-normal mobile:min-h-10", model === name && "chip-on")}>
            {name}
          </button>)}
        </div>}
      </div>
    </fieldset>
    {provider.id === "anthropic" && (config?.provider === "anthropic" ? <div className="space-y-2">
      <span className="block text-sm">思考强度</span>
      <div ref={effortGroup} role="radiogroup" aria-label="思考强度" className="flex max-w-full flex-wrap items-center gap-2"
        onKeyDown={event => {
          if (disabled) return;
          const index = CLAUDE_EFFORTS.indexOf(config.effort);
          const nextIndex = event.key === "ArrowRight" ? (index + 1) % CLAUDE_EFFORTS.length
            : event.key === "ArrowLeft" ? (index + CLAUDE_EFFORTS.length - 1) % CLAUDE_EFFORTS.length : -1;
          if (nextIndex < 0) return;
          event.preventDefault();
          void changeEffort(CLAUDE_EFFORTS[nextIndex]);
          event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role="radio"]')[nextIndex]?.focus();
        }}>
        {CLAUDE_EFFORTS.map(effort => <button key={effort} type="button" role="radio" aria-checked={config.effort === effort}
          tabIndex={config.effort === effort ? 0 : -1} title={CHAT_MODEL_EFFORT_TITLES[effort]} aria-disabled={disabled}
          onClick={() => void changeEffort(effort)}
          className="btn btn-quiet min-h-10 px-3 text-sm aria-checked:bg-[color:var(--btn)] aria-checked:text-[color:var(--btnink)] aria-checked:hover:bg-[color:var(--btn)] aria-checked:hover:text-[color:var(--btnink)] aria-disabled:opacity-50 aria-disabled:cursor-default">
          {CHAT_MODEL_EFFORT_LABELS[effort]}
        </button>)}
      </div>
      <p className={noteClass}>调高后 Claude 会先思考再回答：更周全，但更慢、更费你自己的额度；高档单条最长约 3 分钟。只对 Claude 生效。</p>
    </div> : <p className={noteClass}>保存后可选择思考强度</p>)}
    <fieldset disabled={disabled} className="min-w-0 space-y-3 disabled:opacity-60">
      <legend className="sr-only">聊天模型密钥与启用选项</legend>
      {custom && <div className="space-y-2">
        <label htmlFor="chat-model-url" className="block text-sm">API 地址</label>
        <input id="chat-model-url" type="url" inputMode="url" placeholder="https://…/v1" autoComplete="off" spellCheck={false}
          autoCapitalize="none" value={baseUrl} onChange={event => { setBaseUrl(event.target.value); setSuccess(""); }} maxLength={512} className={inputClass} />
        <p className={noteClass}>仅支持可公网访问的 HTTPS 地址；更换地址需要重新填写 Key。</p>
      </div>}
      <div className="space-y-2">
        <label htmlFor="chat-model-key" className="block text-sm">API Key</label>
        {config && <div className="flex flex-wrap items-center gap-3">
          <span className="readout text-sm">已保存：••••{config.key_last4}</span>
          <button type="button" className="btn h-8 px-2 text-xs mobile:min-h-10" onClick={() => { setKeyEditing(true); requestAnimationFrame(() => keyInput.current?.focus()); }}>更换 Key</button>
          <button type="button" className="btn btn-danger h-8 px-2 text-xs mobile:min-h-10" onClick={() => void remove()}>{busy === "delete" ? "正在删除…" : "删除"}</button>
        </div>}
        <input ref={keyInput} id="chat-model-key" type="password" autoComplete="off" spellCheck={false} autoCapitalize="none"
          aria-label="API Key" placeholder={needsKey ? "填写 API Key" : "留空保留已保存的 Key"} maxLength={512}
          onChange={event => { setKeyEntered(event.target.value.length > 0); setSuccess(""); }}
          className={cn(inputClass, !keyEditing && !needsKey && "hidden")} />
        {needsKey && <p className={noteClass}>{config?.status === "needs_reentry" ? "配置需要重新填写 Key，保存后才能启用。" : "首次配置或更换厂商、地址时，需要填写 Key。"}</p>}
      </div>
      <div className="border-t border-[color:var(--carve)] pt-3 shadow-[inset_0_1px_0_var(--etch)]">
        <div className="flex items-center justify-between gap-4">
          <span id="chat-model-enabled-name" className="text-sm tracking-[0.06em]">启用我的聊天模型</span>
          <button type="button" role="switch" aria-checked={config?.enabled ?? false} aria-labelledby="chat-model-enabled-name"
            aria-describedby="chat-model-enabled-note" disabled={switchDisabled} onClick={() => void toggle()}
            className="relative flex h-10 w-11 shrink-0 items-center justify-center rounded-[12px] disabled:cursor-default disabled:opacity-50">
            <span aria-hidden="true" className="relative block h-6 w-11 rounded-full border border-[color:var(--rule2)] shadow-[inset_0_1px_2px_var(--pool)]"
              style={{ background: config?.enabled ? "var(--btn)" : "transparent" }}>
              <span className="absolute left-[3px] top-[3px] h-4 w-4 rounded-full transition-transform"
                style={{ transform: config?.enabled ? "translateX(20px)" : "translateX(0)", background: config?.enabled ? "var(--btnink)" : "var(--ink2)" }} />
            </span>
          </button>
        </div>
        <p id="chat-model-enabled-note" className={noteClass}>{!config ? "先保存配置，才能启用。" : config.status === "needs_reentry" ? "请重新填写并保存 Key。" : "开关使用已保存的配置；关闭后使用平台模型。"}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={!model || (needsKey && !keyEntered)} className="btn min-h-10 px-4" onClick={() => void test()}>{busy === "test" ? "正在测试…" : "测试连接"}</button>
        <button type="button" disabled={!model || (needsKey && !keyEntered)} className="btn btn-primary min-h-10 px-4" onClick={() => void save()}>{busy === "save" ? "正在保存…" : "保存"}</button>
      </div>
    </fieldset>
    {dirty && <p role="status" className={noteClass}>有未保存的修改。</p>}
    {error && <p role="alert" className="text-xs text-[color:var(--seal)]">{error}</p>}
    {success && <p role="status" className="text-xs text-[color:var(--ink)]">{success}</p>}
    <div className={`${noteClass} space-y-2 border-t border-[color:var(--carve)] pt-3 shadow-[inset_0_1px_0_var(--etch)]`}>
      <p>启用后，聊天回复会把分身设定、你的私有长期记忆、本会话最近 60 条消息（含平台看图生成的图片描述）和本条消息发送给你选择的厂商，账号名替换为「（账号已隐藏）」。</p>
      <p>危机复核、意图识别、模式判定、看图、其他工具执行、朗读和画像提取仍由平台处理并读取对话；画像提取会读到你的模型回复，明确危机轮也由平台回复。</p>
      <p>生图：选 Claude 或 DeepSeek（deepseek-v4-pro、deepseek-flash）时，由你的模型决定何时生图并撰写画面描述；选其他厂商时，在你的消息或上一条回复涉及画图时，平台的生图判断器（阿里云 DashScope 千问 qwen3.8-flash）会读取最近 6 条对话来决定是否生图、撰写画面描述。生图由平台执行并扣草莓，默认使用 Seedream 5.0 Flash，画面描述会发送给字节跳动火山引擎（点名千问时发送给阿里云），可能包含对话中出现过的内容。</p>
      <p>自带模型文字聊天不扣草莓，零余额也可聊天；平台模型回复、工具、看图和生图照常扣费，自带模型失败时不会改用平台模型，聊天和连接测试均有每日上限。</p>
      <p>Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天，无服务端密钥无法解密。</p>
      <p>Claude 的接口不对中国大陆提供服务。</p>
    </div>
  </div>;
}

export default function ChatModelSection({ username, sectionClass, headingClass }: {
  username: string;
  sectionClass: string;
  headingClass: string;
}) {
  const [settings, setSettings] = useState<ChatModelSettings | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const { beginRequest } = useAccountRequest(username);
  const load = useCallback(() => {
    const request = beginRequest();
    if (!request) return;
    getChatModel(request.signal).then(value => {
      if (request.isCurrent()) setSettings(value);
    }).catch(cause => {
      if (request.isCurrent()) setError(chatModelErrorMessage(cause));
    }).finally(() => {
      if (request.isCurrent()) setLoading(false);
    });
  }, [beginRequest]);
  useEffect(() => {
    if (settings) return;
    load();
    const onStorage = (event: StorageEvent) => {
      if (event.key === CHAT_MODEL_REV_KEY) load();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, settings]);

  return <section className={sectionClass}>
    <h2 className={headingClass}>聊天模型</h2>
    {settings ? <ChatModelForm initial={settings} username={username} />
      : <div className="space-y-2">
        <p role={error ? "alert" : "status"} className={error ? "text-xs text-[color:var(--seal)]" : noteClass}>{error || "正在加载聊天模型…"}</p>
        {error && <button type="button" disabled={loading} className="btn min-h-10 px-4"
          onClick={() => { setError(""); setLoading(true); load(); }}>重试</button>}
      </div>}
  </section>;
}
