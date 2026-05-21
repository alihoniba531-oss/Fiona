"use client";

import { Wifi, Battery, Signal, Bell, Search, ChevronDown, User } from "lucide-react";
import { useState, useEffect } from "react";
import { getUsername, updateBalance } from "@/lib/auth";

const API = "/api";

export default function TopBar() {
  const [time,    setTime]    = useState("");
  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    const update = () => {
      setTime(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }));
    };
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    // 每次拉余额都重读 username —— 切换身份后能看到新账号的余额
    // 监听两个事件:跨 tab 的 storage 变化 + 同 tab 的自定义 fiona-user-changed
    const fetchBalance = () => {
      const username = getUsername();
      if (!username) { setBalance(null); return; }
      fetch(`${API}/strawberry/${encodeURIComponent(username)}`)
        .then(r => r.json())
        .then(data => {
          if (typeof data?.balance === "number") {
            setBalance(data.balance);
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
    <div className="shrink-0 z-10">
      {/* iOS 状态栏 */}
      <div className="glass border-b border-border/40 h-11 flex items-center px-5 justify-between">
        {/* 左：时间 */}
        <span className="text-[13px] font-semibold w-16">{time}</span>

        {/* 中：App 名称 */}
        <span className="text-[13px] font-semibold tracking-tight">菲欧娜</span>

        {/* 右：状态图标 */}
        <div className="flex items-center gap-1.5 w-16 justify-end">
          <Signal size={13} className="text-foreground" strokeWidth={2} />
          <Wifi size={13} className="text-foreground" strokeWidth={2} />
          <Battery size={15} className="text-foreground" strokeWidth={2} />
        </div>
      </div>

      {/* iOS 导航栏 */}
      <div className="glass border-b border-border h-12 flex items-center px-4 gap-3">
        {/* 搜索框 */}
        <div className="flex items-center gap-2 w-80 bg-secondary rounded-[10px] px-3 py-1.5 shrink-0">
          <Search size={13} className="text-muted-foreground shrink-0" />
          <input
            placeholder="搜索…"
            className="flex-1 bg-transparent text-[13px] text-foreground placeholder:text-muted-foreground outline-none min-w-0"
          />
        </div>

        <div className="flex-1" />

        {/* 草莓余额 */}
        <div
          className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-secondary transition-all cursor-default"
          title="草莓余额（每条消息消耗 10 颗）"
        >
          <span className="text-[16px] leading-none">🍓</span>
          <span className={`text-[11px] tabular-nums font-medium ${
            balance === null ? "text-muted-foreground" :
            balance < 30    ? "text-red-400" :
            balance < 100   ? "text-yellow-400" :
                              "text-foreground"
          }`}>
            {balance === null ? "…" : balance}
          </span>
        </div>

        {/* 通知 */}
        <button className="relative w-8 h-8 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-secondary transition-all">
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />
        </button>

        {/* 用户 */}
        <button className="flex items-center gap-1.5 px-2 py-1 rounded-[10px] hover:bg-secondary transition-all">
          <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center">
            <User size={13} className="text-primary" />
          </div>
          <ChevronDown size={11} className="text-muted-foreground" />
        </button>
      </div>
    </div>
  );
}
