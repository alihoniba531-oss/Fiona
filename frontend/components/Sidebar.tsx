"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageCircle, Settings, Moon, Sun, Bot, Orbit, Globe } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { getUsername, updateBalance, apiFetch } from "@/lib/auth";
import { useTheme } from "@/lib/useTheme";

import { API_BASE as API } from "@/lib/config";

const navItems = [
  { href: "/", icon: MessageCircle, label: "对话" },
  { href: "/agents/me", icon: Bot, label: "分身" },
  { href: "/agents", icon: Orbit, label: "广场" },
  { href: "/plaza", icon: Globe, label: "世界" },
  { href: "/settings", icon: Settings, label: "设置" },
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

  return (
    <>
    <aside className="glass flex min-h-0 w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar py-3 max-md:hidden">
      {/* Logo */}
      <div className="mb-3 grid h-8 w-8 shrink-0 place-items-center text-[color:var(--amber-ink)]" title="Chloe">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="9" cy="12" r="5.5" />
          <circle cx="15" cy="12" r="5.5" />
        </svg>
      </div>

      {/* Nav */}
      <nav className="flex min-h-0 w-full flex-col items-center gap-1 flex-1 overflow-y-auto">
        {navItems.map(({ href, icon: Icon, label }) => {
          // active 优先看抽屉状态，没传 active prop 时回退到 pathname
          const drawerActive =
            (href === "/agents/me" && agentActive) ||
            (href === "/agents" && exchangeActive) ||
            (href === "/plaza" && plazaActive) ||
            (href === "/settings" && settingsActive);
          const anyDrawerOpen = !!(agentActive || exchangeActive || plazaActive || settingsActive);
          // "聊天"在主页且没抽屉开时高亮；任一抽屉开时不高亮
          const chatActive = href === "/" && pathname === "/" && !anyDrawerOpen;
          const active = drawerActive || chatActive || (href !== "/" && pathname === href);
          // 抽屉模式：父组件传了对应 callback 时走按钮 + 不路由跳转
          const drawerCallback =
            href === "/" ? onChatClick :
            href === "/agents/me" ? onAgentClick :
            href === "/agents" ? onExchangeClick :
            href === "/plaza" ? onPlazaClick :
            href === "/settings" ? onSettingsClick :
            undefined;
          if (drawerCallback) {
            return (
              <button
                key={href}
                type="button"
                onClick={drawerCallback}
                aria-expanded={href === "/agents/me" ? !!agentActive : href === "/agents" ? !!exchangeActive : undefined}
                aria-controls={href === "/agents/me" ? "agent-drawer" : href === "/agents" ? "exchange-drawer" : undefined}
                className={cn(
                  "flex h-12 w-12 shrink-0 flex-col items-center justify-center gap-0.5 rounded-[6px] transition-colors duration-150",
                  active
                    ? "text-[color:var(--amber-ink)]"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
                title={label}
              >
                <Icon size={20} strokeWidth={active ? 2.2 : 1.8} />
                <span className="text-[10px] font-medium">{label}</span>
              </button>
            );
          }
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex h-12 w-12 shrink-0 flex-col items-center justify-center gap-0.5 rounded-[6px] transition-colors duration-150",
                active
                  ? "text-[color:var(--amber-ink)]"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              )}
              title={label}
            >
              <Icon size={20} strokeWidth={active ? 2.2 : 1.8} />
              <span className="text-[10px] font-medium">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="flex shrink-0 flex-col items-center gap-2.5">
        <div className="flex flex-col items-center gap-0.5 text-[11px] text-muted-foreground" title="草莓余额，每条消息消耗 10 颗">
          <span aria-hidden="true">🍓</span>
          <b
            className="readout"
            style={{
              color: balance !== null && balance < 30
                ? "var(--rec)"
                : balance !== null && balance < 100
                  ? "var(--amber-ink)"
                  : "var(--foreground)",
            }}
          >
            {balance === null ? "…" : balance}
          </b>
        </div>

        {/* 底部：深浅色切换 */}
        <button
          onClick={toggleTheme}
          className="flex h-10 w-12 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          title={dark ? "切换浅色" : "切换深色"}
        >
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
    </aside>
    <nav
      aria-label="主导航"
      className="glass fixed inset-x-0 bottom-0 z-[70] flex h-[calc(56px+env(safe-area-inset-bottom))] items-start border-t pb-[env(safe-area-inset-bottom)] md:hidden"
      style={{ borderColor: "var(--glass-border)" }}
    >
      {navItems.map(({ href, icon: Icon, label }) => {
        const drawerActive =
          (href === "/agents/me" && agentActive) ||
          (href === "/agents" && exchangeActive) ||
          (href === "/plaza" && plazaActive) ||
          (href === "/settings" && settingsActive);
        const anyDrawerOpen = !!(agentActive || exchangeActive || plazaActive || settingsActive);
        const chatActive = href === "/" && pathname === "/" && !anyDrawerOpen;
        const active = drawerActive || chatActive || (href !== "/" && pathname === href);
        const drawerCallback =
          href === "/" ? onChatClick :
          href === "/agents/me" ? onAgentClick :
          href === "/agents" ? onExchangeClick :
          href === "/plaza" ? onPlazaClick :
          href === "/settings" ? onSettingsClick :
          undefined;
        const drawerId =
          href === "/agents/me" ? "agent-drawer" :
          href === "/agents" ? "exchange-drawer" :
          href === "/plaza" ? "plaza-drawer" :
          href === "/settings" ? "settings-drawer" : undefined;
        const itemClassName = cn(
          "flex h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 whitespace-nowrap transition-colors duration-150",
          active
            ? "text-[color:var(--amber-ink)]"
            : "text-muted-foreground hover:bg-secondary hover:text-foreground"
        );
        const content = <><Icon size={20} strokeWidth={active ? 2.2 : 1.8} /><span className="text-[10px] font-medium">{label}</span></>;
        if (drawerCallback) {
          return <button key={href} type="button" onClick={drawerCallback}
            aria-expanded={drawerId ? !!drawerActive : undefined} aria-controls={drawerId}
            className={itemClassName} title={label}>{content}</button>;
        }
        return <Link key={href} href={href} className={itemClassName} title={label}>{content}</Link>;
      })}
    </nav>
    </>
  );
}
