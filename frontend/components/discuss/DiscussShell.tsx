"use client";

import { useEffect, type ReactNode } from "react";
import InkLandscape from "@/components/InkLandscape";
import Sidebar from "@/components/Sidebar";
import { canCloseNovelDrawer } from "@/components/novel/NovelShell";

export default function DiscussShell({ embedded, children }: { embedded: boolean; children: ReactNode }) {
  useEffect(() => {
    if (!embedded || window.parent === window) return;
    const close = (event: KeyboardEvent) => {
      if (canCloseNovelDrawer(event, document.activeElement, !!document.querySelector("dialog[open]"))) {
        window.parent.postMessage({ type: "fiona-discuss-close" }, window.location.origin);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [embedded]);
  return <div className="relative flex h-dvh min-w-0 overflow-hidden">
    {!embedded && <><InkLandscape variant="page" /><Sidebar discussAccessAllowed /></>}
    <main className={`relative z-[1] flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto text-[color:var(--ink)] ${embedded ? "" : "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]"}`}>
      <div className="@container mx-auto flex w-full min-w-0 max-w-[1440px] flex-[1_0_auto] flex-col px-4 py-5 [overflow-wrap:anywhere] [&_.tag]:h-auto [&_.tag]:min-h-[22px] [&_.tag]:whitespace-normal [&_.tag]:py-1 [&_.tag]:leading-relaxed @[640px]:px-8">{children}</div>
    </main>
  </div>;
}
