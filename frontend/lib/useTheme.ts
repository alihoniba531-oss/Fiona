"use client";

import { useSyncExternalStore } from "react";

export type Appearance = "system" | "day" | "night";
const solidSystemQueries = ["(prefers-reduced-transparency: reduce)", "(prefers-contrast: more)"];
function snapshot() {
  const root=document.documentElement;
  const systemSolid=solidSystemQueries.some(query => window.matchMedia(query).matches);
  return `${root.dataset.appearance || "system"}|${root.classList.contains("dark")}|${root.dataset.solidManual === "1"}|${root.hasAttribute("data-solid")}|${systemSolid}`;
}
function subscribe(onChange: () => void) {
  const observer=new MutationObserver(onChange);
  observer.observe(document.documentElement,{attributes:true,attributeFilter:["class","data-appearance","data-solid-manual","data-solid"]});
  const queries=solidSystemQueries.map(query => window.matchMedia(query));
  queries.forEach(query => {
    if (query.addEventListener) query.addEventListener("change",onChange);
    else query.addListener(onChange);
  });
  return () => {
    observer.disconnect();
    queries.forEach(query => {
      if (query.removeEventListener) query.removeEventListener("change",onChange);
      else query.removeListener(onChange);
    });
  };
}
function persist(key:string,value:string) {
  try { localStorage.setItem(key,value); } catch { /* The current document still works when storage is unavailable. */ }
  const root=document.documentElement;
  if (key === "chloe-appearance") root.dataset.appearance=value;
  else root.dataset.solidManual=value;
  window.dispatchEvent(new Event("chloe-theme-change"));
}
export function useTheme() {
  const value=useSyncExternalStore(subscribe,snapshot,() => "system|false|false|false|false");
  const [appearance,dark,solid,effectiveSolid,systemSolid]=value.split("|");
  const setAppearance=(next:Appearance) => persist("chloe-appearance",next);
  const setSolid=(next:boolean) => persist("chloe-solid",next ? "1":"0");
  const toggleTheme=() => setAppearance(document.documentElement.classList.contains("dark") ? "day":"night");
  return {appearance:appearance as Appearance,setAppearance,dark:dark === "true",solid:solid === "true",effectiveSolid:effectiveSolid === "true",systemSolid:systemSolid === "true",setSolid,toggleTheme};
}
