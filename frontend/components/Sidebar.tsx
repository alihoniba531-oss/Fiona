"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Glaze from "@/components/Glaze";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { getUsername, updateBalance, apiFetch } from "@/lib/auth";
import { useTheme } from "@/lib/useTheme";

import { API_BASE as API } from "@/lib/config";

const navItems = [
  { href: "/", label: "对话" },
  { href: "/agents/me", label: "分身" },
  { href: "/agents", label: "广场" },
  { href: "/plaza", label: "世界" },
  { href: "/settings", label: "设置" },
];

export default function Sidebar({
  onChatClick,
  onAgentClick,
  agentActive,
  onExchangeClick,
  exchangeActive,
  onPlazaClick,
  plazaActive,
  onSettingsClick,
  settingsActive,
  onBalanceChange,
}: {
  onHistoryClick?: () => void;
  onChatClick?: () => void;          // 主页传入，点“对话”关闭所有抽屉
  onAgentClick?: () => void;
  agentActive?: boolean;
  onExchangeClick?: () => void;
  exchangeActive?: boolean;
  onPlazaClick?: () => void;
  plazaActive?: boolean;
  onSettingsClick?: () => void;
  settingsActive?: boolean;
  onBalanceChange?: (balance: number | null) => void;
}) {
  const pathname = usePathname();
  const { dark, toggleTheme } = useTheme();
  const [balance, setBalance] = useState<number | null>(null);
  const onBalanceChangeRef = useRef(onBalanceChange);

  useEffect(() => {
    onBalanceChangeRef.current = onBalanceChange;
  }, [onBalanceChange]);

  useEffect(() => {
    // 每次拉余额都重读 username —— 切换身份后能看到新账号的余额
    // 监听两个事件:跨 tab 的 storage 变化 + 同 tab 的自定义 fiona-user-changed
    const fetchBalance = () => {
      const username = getUsername();
      if (!username) { setBalance(null); onBalanceChangeRef.current?.(null); return; }
      apiFetch(`${API}/strawberry`)
        .then(r => r.json())
        .then(data => {
          if (typeof data?.balance === "number") {
            setBalance(data.balance);
            onBalanceChangeRef.current?.(data.balance);
            updateBalance(data.balance);
          }
        })
        .catch(() => {});
    };
    fetchBalance();
    const timer = setInterval(fetchBalance, 60000);
    window.addEventListener("storage", fetchBalance);
    window.addEventListener("fiona-user-changed", fetchBalance);
    return () => {
      clearInterval(timer);
      window.removeEventListener("storage", fetchBalance);
      window.removeEventListener("fiona-user-changed", fetchBalance);
    };
  }, []);

  const shared = !!onChatClick;
  const items = navItems.map(({href,label}) => {
    const drawerActive=(href === "/agents/me" && agentActive) || (href === "/agents" && exchangeActive) || (href === "/plaza" && plazaActive) || (href === "/settings" && settingsActive);
    const anyDrawer=!!(agentActive || exchangeActive || plazaActive || settingsActive);
    const active=!!drawerActive || (href === "/" && pathname === "/" && !anyDrawer) || (href !== "/" && pathname === href);
    const callback=href === "/" ? onChatClick : href === "/agents/me" ? onAgentClick : href === "/agents" ? onExchangeClick : href === "/plaza" ? onPlazaClick : onSettingsClick;
    const drawerId=href === "/agents/me" ? "agent-drawer" : href === "/agents" ? "exchange-drawer" : href === "/plaza" ? "plaza-drawer" : href === "/settings" ? "settings-drawer" : undefined;
    return {href,label,active,callback,drawerActive,drawerId};
  });
  const desktop = <aside className={cn(shared && "relative z-[2] my-3 ml-3", "bookmark-sidebar flex min-h-0 w-[var(--nav-w)] shrink-0 flex-col items-center border-r border-[var(--carve)] py-[22px] max-md:hidden")} aria-label="主导航">
    <svg width="30" height="30" viewBox="0 0 36 36" role="img" aria-label="Chloe"><circle cx="14" cy="18" r="8" fill="none" stroke="var(--ink)" strokeWidth="1.4"/><circle cx="22" cy="18" r="8" fill="none" stroke="var(--ink)" strokeWidth="1.4"/></svg>
    <nav className="mt-10 flex flex-col items-center gap-2.5">
      {items.map(({href,label,active,callback,drawerActive,drawerId}) => {
        const classes=cn("bookmark-nav flex min-h-16 w-10 items-center justify-center border-l-[1.5px] py-2.5 pl-[9px] text-[15px] tracking-[.32em] [writing-mode:vertical-rl]",active ? "border-[var(--ink)] font-medium text-[var(--ink)]":"border-transparent text-[var(--ink2)] hover:text-[var(--ink)]");
        return callback ? <button key={href} type="button" onClick={callback} aria-expanded={drawerId ? !!drawerActive:undefined}
          aria-controls={drawerId} aria-current={active ? "page":undefined} className={classes} title={label}>{label}</button>
          : <Link key={href} href={href} aria-current={active ? "page":undefined} className={classes} title={label}>{label}</Link>;
      })}
    </nav>
    <div className="mt-auto flex flex-col items-center pt-6">
      <button type="button" onClick={toggleTheme} className="grid h-10 w-10 place-items-center rounded-full border border-[var(--rule2)] text-sm text-[var(--ink2)] hover:text-[var(--ink)]" title={dark ? "切换浅色":"切换深色"} aria-label={dark ? "切换浅色":"切换深色"}>
        <span className="theme-day">夜</span><span className="theme-night">昼</span>
      </button>
      <div className="mt-[18px] text-center leading-[1.3]" title="平台模型每条消息消耗 10 颗；自带模型聊天不扣">
        <div className="text-sm tabular-nums" style={{color:balance !== null && balance < 30 ? "var(--seal)":"var(--ink)"}}>{balance === null ? "…":balance}</div>
        <div className="text-[11px] tracking-[.1em] text-[var(--ink2)]">草莓</div>
      </div>
    </div>
  </aside>;
  const mobile = <nav aria-label="主导航" className={cn("mobile-tabbar fixed inset-x-0 bottom-0 z-[70] flex h-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] items-start pb-[env(safe-area-inset-bottom)] md:hidden", shared && "border-t border-[var(--carve)]")}>
    {items.map(({href,label,active,callback,drawerActive,drawerId}) => {
      const classes=cn("flex h-[var(--tabbar-h)] min-w-0 flex-1 flex-col items-center justify-center gap-1.5 whitespace-nowrap text-sm tracking-[.2em]",active ? "font-medium text-[var(--ink)]":"text-[var(--ink2)] hover:text-[var(--ink)]");
      const content=<><span aria-hidden="true" className={cn("h-[1.5px] w-4",active ? "bg-[var(--ink)]":"bg-transparent")}/>{label}</>;
      return callback ? <button key={href} type="button" onClick={callback} aria-expanded={drawerId ? !!drawerActive:undefined}
        aria-controls={drawerId} aria-current={active ? "page":undefined} className={classes} title={label}>{content}</button>
        : <Link key={href} href={href} aria-current={active ? "page":undefined} className={classes} title={label}>{content}</Link>;
    })}
  </nav>;
  return <>
    {shared ? desktop : <Glaze variant="panel" fur className="my-3 ml-3 flex shrink-0 max-md:hidden">{desktop}</Glaze>}
    {shared ? mobile : <Glaze variant="slab" className="fixed inset-x-0 bottom-0 z-[70] h-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] rounded-t-[18px] rounded-b-none md:hidden">{mobile}</Glaze>}
  </>;
}
