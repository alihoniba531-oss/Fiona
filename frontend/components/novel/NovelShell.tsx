"use client";

import { useEffect } from "react";

export function canCloseNovelDrawer(event: Pick<KeyboardEvent, "key" | "defaultPrevented" | "isComposing">, focused: Element | null, dialogOpen: boolean): boolean {
  return event.key === "Escape" && !event.defaultPrevented && !event.isComposing && !dialogOpen
    && !focused?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])');
}

/** Let the host drawer handle Escape without interrupting a native dialog. */
export function useNovelEmbedClose(embedded: boolean) {
  useEffect(() => {
    if (!embedded || window.parent === window) return;
    const close = (event: KeyboardEvent) => {
      if (!canCloseNovelDrawer(event, document.activeElement, !!document.querySelector("dialog[open]"))) return;
      window.parent.postMessage({ type: "fiona-novel-close" }, window.location.origin);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [embedded]);
}
