"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageCircle, Sparkles, User, Settings, Moon, Sun, UsersRound, LayoutGrid, History } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", icon: MessageCircle, label: "聊天" },
  { href: "/match", icon: Sparkles, label: "匹配" },
  { href: "/plaza", icon: LayoutGrid, label: "我的世界" },
  { href: "/community", icon: UsersRound, label: "社群" },
  { href: "/profile", icon: User, label: "我的" },
  { href: "/settings", icon: Settings, label: "设置" },
];

export default function Sidebar({
  onHistoryClick,
  onPlazaClick,
  plazaActive,
  onMatchClick,
  matchActive,
}: {
  onHistoryClick?: () => void;
  onPlazaClick?: () => void;
  plazaActive?: boolean;
  onMatchClick?: () => void;
  matchActive?: boolean;
}) {
  const pathname = usePathname();
  const [dark, setDark] = useState(true);

  const toggleTheme = () => {
    setDark(!dark);
    document.documentElement.classList.toggle("dark");
  };

  return (
    <aside className="glass flex flex-col items-center w-16 border-r border-border bg-sidebar py-4 gap-1 shrink-0">
      {/* Logo */}
      <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center mb-4 shadow-sm">
        <span className="text-white text-sm font-semibold">菲</span>
      </div>

      {/* Nav */}
      <nav className="flex flex-col items-center gap-1 flex-1">
        {navItems.map(({ href, icon: Icon, label }) => {
          const active =
            pathname === href ||
            (href === "/plaza" && plazaActive) ||
            (href === "/match" && matchActive);
          // 抽屉模式：父组件传了对应 callback 时走按钮 + 不路由跳转
          const drawerCallback =
            href === "/plaza" ? onPlazaClick :
            href === "/match" ? onMatchClick :
            undefined;
          if (drawerCallback) {
            return (
              <button
                key={href}
                onClick={drawerCallback}
                className={cn(
                  "flex flex-col items-center justify-center w-12 h-12 rounded-xl gap-0.5 transition-all duration-150",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
                title={label}
              >
                <Icon size={20} strokeWidth={active ? 2.2 : 1.8} />
                <span className="text-[9px] font-medium">{label}</span>
              </button>
            );
          }
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex flex-col items-center justify-center w-12 h-12 rounded-xl gap-0.5 transition-all duration-150",
                active
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              )}
              title={label}
            >
              <Icon size={20} strokeWidth={active ? 2.2 : 1.8} />
              <span className="text-[9px] font-medium">{label}</span>
            </Link>
          );
        })}

        {/* 历史聊天记录按钮 */}
        {onHistoryClick && (
          <button
            onClick={onHistoryClick}
            className="flex flex-col items-center justify-center w-12 h-12 rounded-xl gap-0.5 transition-all duration-150 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="历史聊天记录"
          >
            <History size={20} strokeWidth={1.8} />
            <span className="text-[9px] font-medium">历史</span>
          </button>
        )}
      </nav>

      {/* 底部：深浅色切换 */}
      <button
        onClick={toggleTheme}
        className="flex items-center justify-center w-10 h-10 rounded-xl text-muted-foreground hover:bg-secondary hover:text-foreground transition-all"
        title={dark ? "切换浅色" : "切换深色"}
      >
        {dark ? <Sun size={18} /> : <Moon size={18} />}
      </button>
    </aside>
  );
}
