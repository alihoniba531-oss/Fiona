"use client";

import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import { type Message } from "@/components/ChatBubble";
import { API_BASE as API } from "@/lib/config";
import { apiJson, errorMessage, type Agent, type Conversation } from "@/lib/agents";
import { getUsername } from "@/lib/auth";
import { storedReferenceImagePaths } from "@/lib/generatedImages";

interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  image_path: string | null;
  reference_image_paths?: string[];
  created_at: string;
}

interface ConversationDetail {
  conversation: Conversation;
  messages: StoredMessage[];
  agent: Agent;
  has_more?: boolean;
  limit?: number;
}

interface State {
  owner: string;
  agent: Agent | null;
  conversations: Conversation[];
  current: Conversation | null;
  messages: Message[];
  loading: boolean;
  error: string;
  hasMoreMessages: boolean;
}

const EMPTY: State = {
  owner: "", agent: null, conversations: [], current: null,
  messages: [], loading: true, error: "", hasMoreMessages: false,
};

function selectionKey(owner: string) {
  return `fiona_conversation:${encodeURIComponent(owner)}`;
}

function remember(owner: string, id: string | null) {
  try {
    if (id) localStorage.setItem(selectionKey(owner), id);
    else localStorage.removeItem(selectionKey(owner));
  } catch { /* 会话仍可使用；浏览器可能禁用了本地存储。 */ }
}

function toMessages(messages: StoredMessage[]): Message[] {
  return messages.map(message => ({
    id: `db-${message.id}`,
    dbId: message.id,
    role: message.role,
    content: message.content,
    timestamp: new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(message.created_at)
      ? message.created_at : `${message.created_at.replace(" ", "T")}Z`),
    imageUrl: message.image_path ? `${API}${message.image_path}` : undefined,
    referenceImageUrls: message.role === "user"
      ? storedReferenceImagePaths(message.reference_image_paths, message.image_path).map(path => `${API}${path}`)
      : undefined,
  }));
}

export function useConversations(owner: string, enabled: boolean) {
  const [state, setState] = useState<State>(EMPTY);
  const revision = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const operationPending = useRef(false);

  const begin = useCallback(() => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    return { request, version: ++revision.current };
  }, []);

  const reload = useCallback(async () => {
    if (!enabled) return;
    const { request, version } = begin();
    operationPending.current = true;
    setState({ ...EMPTY, owner });
    try {
      const [agentResult, listResult] = await Promise.all([
        apiJson<{ agent: Agent }>(`${API}/agents/me`, { signal: request.signal }),
        apiJson<{ conversations: Conversation[] }>(`${API}/conversations`, { signal: request.signal }),
      ]);
      let saved: string | null = null;
      try { saved = localStorage.getItem(selectionKey(owner)); } catch {}
      const selected = listResult.conversations.find(item => item.id === saved) ?? listResult.conversations[0];
      const detail = selected ? await apiJson<ConversationDetail>(
        `${API}/conversations/${encodeURIComponent(selected.id)}/messages?limit=500`, { signal: request.signal },
      ) : null;
      if (version !== revision.current) return;
      setState({
        owner, agent: detail?.agent ?? agentResult.agent,
        conversations: listResult.conversations,
        current: detail?.conversation ?? null,
        messages: detail ? toMessages(detail.messages) : [], loading: false, error: "",
        hasMoreMessages: detail?.has_more ?? false,
      });
      remember(owner, detail?.conversation.id ?? null);
    } catch (error) {
      if (version === revision.current && !request.signal.aborted) {
        setState(previous => ({ ...previous, owner, loading: false, error: errorMessage(error) }));
      }
    } finally {
      if (version === revision.current) operationPending.current = false;
    }
  }, [begin, enabled, owner]);

  useEffect(() => {
    let cancelled = false;
    // Let cleanup cancel the Strict Mode probe before it initiates a request.
    void Promise.resolve().then(() => { if (!cancelled) void reload(); });
    return () => {
      cancelled = true;
      revision.current += 1;
      controller.current?.abort();
      operationPending.current = false;
    };
  }, [reload]);

  const selectConversation = useCallback(async (id: string) => {
    if (operationPending.current || !enabled) return;
    const { request, version } = begin();
    operationPending.current = true;
    setState(previous => ({ ...previous, current: null, messages: [], loading: true, error: "", hasMoreMessages: false }));
    try {
      const detail = await apiJson<ConversationDetail>(
        `${API}/conversations/${encodeURIComponent(id)}/messages?limit=500`, { signal: request.signal },
      );
      if (version !== revision.current) return;
      setState(previous => ({
        ...previous, owner, current: detail.conversation, agent: detail.agent,
        messages: toMessages(detail.messages), loading: false, error: "",
        hasMoreMessages: detail.has_more ?? false,
      }));
      remember(owner, detail.conversation.id);
    } catch (error) {
      if (version === revision.current && !request.signal.aborted) {
        setState(previous => ({ ...previous, loading: false, error: errorMessage(error) }));
      }
    } finally {
      if (version === revision.current) operationPending.current = false;
    }
  }, [begin, enabled, owner]);

  const createConversation = useCallback(async () => {
    if (operationPending.current || !enabled || !state.agent) return;
    const { request, version } = begin();
    operationPending.current = true;
    setState(previous => ({ ...previous, loading: true, error: "" }));
    try {
      const { conversation } = await apiJson<{ conversation: Conversation }>(`${API}/conversations`, {
        method: "POST", signal: request.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: state.agent.id }),
      });
      if (version !== revision.current) return;
      setState(previous => ({
        ...previous, owner, current: conversation, messages: [], loading: false, error: "",
        hasMoreMessages: false,
        conversations: [conversation, ...previous.conversations],
      }));
      remember(owner, conversation.id);
    } catch (error) {
      if (version === revision.current && !request.signal.aborted) {
        setState(previous => ({ ...previous, loading: false, error: errorMessage(error) }));
      }
    } finally {
      if (version === revision.current) operationPending.current = false;
    }
  }, [begin, enabled, owner, state.agent]);

  const deleteConversation = useCallback(async (id: string) => {
    if (operationPending.current || !enabled) return;
    const { request, version } = begin();
    operationPending.current = true;
    setState(previous => ({ ...previous, loading: true, error: "" }));
    try {
      await apiJson(`${API}/conversations/${encodeURIComponent(id)}`, { method: "DELETE", signal: request.signal });
      if (version === revision.current) await reload();
    } catch (error) {
      if (version === revision.current && !request.signal.aborted) {
        setState(previous => ({ ...previous, loading: false, error: errorMessage(error) }));
      }
    } finally {
      if (version === revision.current) operationPending.current = false;
    }
  }, [begin, enabled, reload]);

  const refreshList = useCallback(async () => {
    const version = revision.current;
    try {
      const result = await apiJson<{ conversations: Conversation[] }>(`${API}/conversations`);
      if (version !== revision.current) return;
      setState(previous => ({
        ...previous, conversations: result.conversations,
        current: result.conversations.find(item => item.id === previous.current?.id) ?? previous.current,
      }));
    } catch { /* A completed response stays visible if refreshing its title fails. */ }
  }, []);

  const setMessages = useCallback((update: SetStateAction<Message[]>) => {
    setState(previous => ({
      ...previous, messages: typeof update === "function" ? update(previous.messages) : update,
    }));
  }, []);
  const updateAgent = useCallback((agent: Agent) => {
    if (getUsername() !== owner || agent.owner_username !== owner) return;
    setState(previous => previous.owner === owner && previous.agent?.id === agent.id
      ? { ...previous, agent }
      : previous);
  }, [owner]);
  const getSelectionVersion = useCallback(() => revision.current, []);

  return {
    ...(state.owner === owner && enabled ? state : EMPTY),
    setMessages, updateAgent, reload, selectConversation, createConversation,
    deleteConversation, refreshList, getSelectionVersion,
  };
}
