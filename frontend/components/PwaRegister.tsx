"use client";

import { useEffect } from "react";

export default function PwaRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // dev 模式：主动卸载所有已注册的 service worker，避免 F5 时从 sw 缓存拿到旧 bundle
    // (Next.js 16 Turbopack HMR + sw 缓存会让代码不一致，F5 后 React state 异常)
    if (process.env.NODE_ENV !== "production") {
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        registrations.forEach((reg) => reg.unregister());
      }).catch(() => {});
      return;
    }

    // production：正常注册 sw 用于 PWA 离线能力
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);

  return null;
}
