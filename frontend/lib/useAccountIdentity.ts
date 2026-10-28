"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { ensureAccountIdentity, getUsername } from "@/lib/auth";

function subscribeAccount(onChange: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (!event.key || event.key === "fiona_user") onChange();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener("fiona-user-changed", onChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("fiona-user-changed", onChange);
  };
}

const serverIdentity = () => "";

export function useAccountIdentity() {
  useEffect(() => { void ensureAccountIdentity(); }, []);
  return useSyncExternalStore(subscribeAccount, getUsername, serverIdentity);
}

// Account-scoped reads and mutations share cancellation and a request version.
// Checking the storage snapshot also covers the interval before React rerenders.
export function useAccountRequest(owner: string) {
  const active = useRef<AbortController | null>(null);
  const version = useRef(0);
  const cancel = useCallback(() => {
    version.current += 1;
    active.current?.abort();
    active.current = null;
  }, []);

  useEffect(() => {
    const onChange = () => { if (getUsername() !== owner) cancel(); };
    const unsubscribe = subscribeAccount(onChange);
    onChange();
    return () => { unsubscribe(); cancel(); };
  }, [cancel, owner]);

  const isCurrentOwner = useCallback(() => !!owner && getUsername() === owner, [owner]);
  const beginRequest = useCallback(() => {
    if (!isCurrentOwner()) return null;
    cancel();
    const controller = new AbortController();
    const requestVersion = version.current;
    active.current = controller;
    return {
      signal: controller.signal,
      isCurrent: () => !controller.signal.aborted
        && version.current === requestVersion && isCurrentOwner(),
    };
  }, [cancel, isCurrentOwner]);

  return { beginRequest, isCurrentOwner };
}

// 身份是否还没确认：服务端渲染与水合首帧为 true；本地没有用户名、且本页第一次身份检查（ensureAccountIdentity）还没结束时也为 true。
// 第一次检查结束后不再回到确认中：另一个标签清掉本地用户名、而 Cookie 仍有效时，会先显示登录提示，等 auth.ts 用 Cookie 找回后再恢复。
// 测试替身只提供 useEffect / useSyncExternalStore 与 getUsername / ensureAccountIdentity，这里不能用别的。
let identityRecoverySettled = false;
const identityPendingListeners = new Set<() => void>();

function subscribeIdentityPending(onChange: () => void) {
  identityPendingListeners.add(onChange);
  const unsubscribeAccount = subscribeAccount(onChange);
  return () => {
    identityPendingListeners.delete(onChange);
    unsubscribeAccount();
  };
}

const clientIdentityPending = () => !getUsername() && !identityRecoverySettled;
const serverIdentityPending = () => true;

export function useAccountIdentityPending(): boolean {
  useEffect(() => {
    if (identityRecoverySettled) return;
    void ensureAccountIdentity().finally(() => {
      identityRecoverySettled = true;
      identityPendingListeners.forEach(listener => listener());
    });
  }, []);
  return useSyncExternalStore(subscribeIdentityPending, clientIdentityPending, serverIdentityPending);
}
