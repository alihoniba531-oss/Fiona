"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { getUsername } from "@/lib/auth";

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
