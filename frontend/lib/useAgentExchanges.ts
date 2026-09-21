"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiJson, errorMessage, type Agent, type AgentCard } from "@/lib/agents";
import { ExchangeIdentityError, exchangeBelongsTo, type AgentExchange, type OfficialAgentCard } from "@/lib/agentExchanges";
import { API_BASE as API } from "@/lib/config";
import { useAccountRequest } from "@/lib/useAccountIdentity";

// The workspace is keyed by account. Each independent request stream also aborts
// and checks account identity so late responses cannot refill private state.
export function useAgentExchanges(owner: string, onIdentityInvalid: () => void) {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [officialAgents, setOfficialAgents] = useState<OfficialAgentCard[]>([]);
  const [officialLoading, setOfficialLoading] = useState(true);
  const [officialError, setOfficialError] = useState("");
  const [exchanges, setExchanges] = useState<AgentExchange[]>([]);
  const [loading, setLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [error, setError] = useState("");
  const [recordsError, setRecordsError] = useState("");
  const { beginRequest: beginDirectory } = useAccountRequest(owner);
  const { beginRequest: beginOfficial } = useAccountRequest(owner);
  const { beginRequest: beginRecords, isCurrentOwner } = useAccountRequest(owner);
  const verifiedAgentId = useRef<string | null>(null);
  const identityVersion = useRef(0);

  const invalidateIdentity = useCallback(() => {
    identityVersion.current += 1;
    verifiedAgentId.current = null;
    setAgent(null); setExchanges([]); setRecordsError(""); setRecordsLoading(false); setLoading(false);
    setError(new ExchangeIdentityError().message);
    onIdentityInvalid();
  }, [onIdentityInvalid]);

  const refreshDirectory = useCallback(async () => {
    const request = beginDirectory();
    if (!request) return;
    const version = identityVersion.current;
    setLoading(true);
    setError("");
    try {
      const [mine, publicCards] = await Promise.all([
        apiJson<{ agent: Agent }>(`${API}/agents/me`, { signal: request.signal }),
        apiJson<{ agents: AgentCard[] }>(`${API}/agents`, { signal: request.signal }),
      ]);
      if (!request.isCurrent() || version !== identityVersion.current) return;
      if (mine.agent.owner_username !== owner) { invalidateIdentity(); return; }
      verifiedAgentId.current = mine.agent.id;
      setAgent(mine.agent);
      setAgents(publicCards.agents);
    } catch (error) {
      if (request.isCurrent() && version === identityVersion.current) {
        if (error instanceof ApiError && [401, 403].includes(error.status)) invalidateIdentity();
        else setError(errorMessage(error));
      }
    } finally {
      if (request.isCurrent() && version === identityVersion.current) setLoading(false);
    }
  }, [beginDirectory, invalidateIdentity, owner]);

  const refreshOfficial = useCallback(async () => {
    const request = beginOfficial();
    if (!request) return;
    setOfficialLoading(true); setOfficialError("");
    try {
      const result = await apiJson<{ agents: OfficialAgentCard[] }>(`${API}/agent-exchanges/official-agents`, { signal: request.signal });
      if (request.isCurrent()) setOfficialAgents(result.agents.filter(card => card.kind === "official"));
    } catch (error) {
      if (request.isCurrent()) setOfficialError(errorMessage(error));
    } finally {
      if (request.isCurrent()) setOfficialLoading(false);
    }
  }, [beginOfficial]);

  const refreshRecords = useCallback(async () => {
    const agentId = verifiedAgentId.current;
    if (!agentId) return;
    const request = beginRecords();
    if (!request) return;
    try {
      const result = await apiJson<{ exchanges: AgentExchange[] }>(`${API}/agent-exchanges`, { signal: request.signal });
      if (!request.isCurrent() || verifiedAgentId.current !== agentId) return;
      if (!result.exchanges.every(exchange => exchangeBelongsTo(exchange, agentId))) { invalidateIdentity(); return; }
      setExchanges(result.exchanges);
      setRecordsError("");
    } catch (error) {
      if (request.isCurrent() && verifiedAgentId.current === agentId) setRecordsError(errorMessage(error));
    } finally {
      if (request.isCurrent()) setRecordsLoading(false);
    }
  }, [beginRecords, invalidateIdentity]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) { void refreshDirectory(); void refreshOfficial(); }
    });
    return () => { cancelled = true; };
  }, [refreshDirectory, refreshOfficial]);

  useEffect(() => {
    if (!agent) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (cancelled) return;
      await refreshRecords();
      if (!cancelled) timer = setTimeout(poll, 4000);
    };
    void Promise.resolve().then(poll);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [agent, refreshRecords]);

  const onExchangeChanged = useCallback((exchange: AgentExchange) => {
    if (!isCurrentOwner()) return;
    if (!verifiedAgentId.current || !exchangeBelongsTo(exchange, verifiedAgentId.current)) { invalidateIdentity(); return; }
    // Starting a fresh list request invalidates a pre-mutation poll before it
    // can overwrite the newly accepted/stopped exchange with an old snapshot.
    void refreshRecords();
    setExchanges(previous => [exchange, ...previous.filter(item => item.id !== exchange.id)]);
  }, [invalidateIdentity, isCurrentOwner, refreshRecords]);

  return { agent, agents, exchanges, loading, recordsLoading, error, recordsError,
    officialAgents, officialLoading, officialError, refreshOfficial,
    refreshDirectory, refreshRecords, onExchangeChanged, invalidateIdentity };
}
