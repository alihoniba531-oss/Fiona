"use client";

import { useCallback, type KeyboardEvent } from "react";

/** One tab stop, with automatic activation and focus on arrow/Home/End keys. */
export function useRovingTabs(count: number, selected: number, onSelect: (index: number) => void) {
  return useCallback((index: number) => ({
    tabIndex: selected === index ? 0 : -1,
    onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
      const next = event.key === "ArrowRight" ? (index + 1) % count
        : event.key === "ArrowLeft" ? (index + count - 1) % count
        : event.key === "Home" ? 0 : event.key === "End" ? count - 1 : null;
      if (next === null) return;
      event.preventDefault();
      onSelect(next);
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
    },
  }), [count, onSelect, selected]);
}
