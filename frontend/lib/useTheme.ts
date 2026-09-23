"use client";

import { useSyncExternalStore } from "react";

// The document class is the theme source of truth for both navigation controls.
function getDark() {
  return typeof document === "undefined" || document.documentElement.classList.contains("dark");
}

function subscribeTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

export function useTheme() {
  const dark = useSyncExternalStore(subscribeTheme, getDark, () => true);
  const toggleTheme = () => document.documentElement.classList.toggle("dark");
  return { dark, toggleTheme };
}
