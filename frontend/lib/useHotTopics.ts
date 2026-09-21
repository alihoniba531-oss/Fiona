"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";

const REFRESH_INTERVAL = 5 * 60_000;
const REQUEST_TIMEOUT = 45_000;
const MAX_STALE = 60 * 60_000;

export type HotCategories = Record<string, string[]>;
type HotResponse = Record<string, unknown>;

export interface HotFeedState<T> {
  data: T;
  loading: boolean;
  loaded: boolean;
  error: string | null;
  stale: boolean;
  partial: boolean;
  updatedAt: string | null;
}

function cleanItems(value: unknown): string[] {
  if (!Array.isArray(value)) throw new Error("热点数据格式有误");
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    // Older servers put their error message in points. It is never a topic.
    .filter((item) => item && !/^获取失败[：:]/.test(item));
}

function parseTopics(response: HotResponse): string[] {
  if (Array.isArray(response.items)) {
    return cleanItems(response.items.map((item: unknown) => (
      item && typeof item === "object" && "title" in item ? item.title : null
    ))).slice(0, 5);
  }
  // Only the legacy points contract includes rank and heat suffixes.
  return cleanItems(response.points)
    .map((item) => item.replace(/^\d{1,2}\.\s+/, "").replace(/\s*·\s*[\d.]+[万亿千]?$/, "").trim())
    .filter((item) => item && !/^获取失败[：:]/.test(item))
    .slice(0, 5);
}

function emptyTopics(): string[] { return []; }

function emptyCategories(): HotCategories {
  return { 娱乐: [], 经济: [], 生活: [], 科技: [], 文化: [] };
}

function parseCategories(response: HotResponse): HotCategories {
  if (!response.categories || typeof response.categories !== "object" || Array.isArray(response.categories)) {
    throw new Error("热点分类数据格式有误");
  }
  const categories = emptyCategories();
  const aliases: Record<string, string> = { 历史: "文化", 哲学: "文化", 时事: "生活" };
  for (const [name, items] of Object.entries(response.categories)) {
    const category = aliases[name] || name;
    if (!(category in categories)) continue;
    categories[category] = [...new Set([...categories[category], ...cleanItems(items)])].slice(0, 5);
  }
  return categories;
}

function useHotFeed<T>(path: string, parse: (response: HotResponse) => T, initialData: () => T) {
  const [state, setState] = useState<HotFeedState<T>>(() => ({
    data: initialData(), loading: true, loaded: false, error: null,
    stale: false, partial: false, updatedAt: null,
  }));
  const request = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT);
    setState((previous) => ({ ...previous, loading: true }));
    try {
      const response = await apiFetch(`${API_BASE}${path}`, {
        signal: controller.signal, cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(response.status === 429 ? "请求较频繁，请稍后重试" : "热点暂时拉取失败");
      }
      const payload: unknown = await response.json();
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        throw new Error("热点数据格式有误");
      }
      const data = payload as HotResponse;
      if (data.error) {
        throw new Error(typeof data.message === "string" && data.message ? data.message : "热点暂时拉取失败");
      }
      const parsed = parse(data);
      if (request.current !== controller || controller.signal.aborted) return;
      setState({
        data: parsed, loading: false, loaded: true, error: null,
        stale: data.stale === true,
        partial: Array.isArray(data.source_errors) && data.source_errors.length > 0,
        updatedAt: typeof data.updated_at === "string" ? data.updated_at : null,
      });
    } catch (error) {
      if (request.current !== controller || (controller.signal.aborted && !timedOut)) return;
      // Keep the last successful result visible when a later refresh fails.
      setState((previous) => {
        const fetchedAt = previous.updatedAt ? new Date(previous.updatedAt).getTime() : NaN;
        const expired = Number.isFinite(fetchedAt) && Date.now() - fetchedAt >= MAX_STALE;
        return {
          ...previous, loading: false, loaded: true,
          data: expired ? initialData() : previous.data,
          updatedAt: expired ? null : previous.updatedAt,
          error: timedOut ? "热点请求超时，请重试" : error instanceof Error && !(error instanceof TypeError) ? error.message : "热点暂时拉取失败，请重试",
        };
      });
    } finally {
      window.clearTimeout(timeout);
    }
  }, [path, parse, initialData]);

  useEffect(() => {
    // The request owns the loading state, including automatic revalidation.
    void refresh();
    const interval = window.setInterval(() => void refresh(), REFRESH_INTERVAL);
    return () => {
      window.clearInterval(interval);
      request.current?.abort();
      request.current = null;
    };
  }, [refresh]);

  return { ...state, refresh };
}

export function useHotTopics(source: string) {
  return useHotFeed(`/hot/${encodeURIComponent(source)}`, parseTopics, emptyTopics);
}

export function useCategorizedHotTopics() {
  return useHotFeed("/hot/categorized/all", parseCategories, emptyCategories);
}
