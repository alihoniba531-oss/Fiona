"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setAuth } from "@/lib/auth";

const API = "/api";

type Step = "invite" | "phone" | "otp";

export default function LoginPage() {
  const router = useRouter();
  const [step,    setStep]    = useState<Step>("invite");
  const [invite,  setInvite]  = useState("");
  const [phone,   setPhone]   = useState("");
  const [code,    setCode]    = useState("");
  const [loading, setLoading] = useState(false);
  const [err,     setErr]     = useState("");
  const [showTest, setShowTest] = useState(false);
  const [testUser, setTestUser] = useState("tester");

  // 开发测试入口：不走短信 OTP，直接以指定 username 拿 token。
  // 仅 NODE_ENV=development 时渲染按钮；后端也需 DEV_MODE=1，否则返回 404。
  async function handleTestLogin() {
    setErr("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/test-login`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ username: testUser.trim() || "tester" }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.detail || "测试登录失败（后端是否 DEV_MODE=1？）");
        return;
      }
      setAuth(data.token, data.username, data.balance ?? 200);
      router.replace("/");
    } catch {
      setErr("网络错误");
    } finally {
      setLoading(false);
    }
  }

  async function handleRedeem() {
    setErr("");
    const inviteCode = invite.trim().toUpperCase();
    if (!inviteCode) {
      setErr("请输入邀请码");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/redeem-invite`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ code: inviteCode }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.detail || "邀请码无效");
        return;
      }
      setAuth(data.token, data.username, data.balance ?? 200);
      router.replace("/");
    } catch {
      setErr("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendOtp() {
    setErr("");
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setErr("请输入正确的手机号");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/send-otp`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ phone }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setErr(d.detail || "发送失败，请稍后重试");
        return;
      }
      setStep("otp");
    } catch {
      setErr("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify() {
    setErr("");
    if (code.length !== 6) {
      setErr("验证码是 6 位数字");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/verify-otp`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ phone, code }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.detail || "验证失败");
        return;
      }
      setAuth(data.token, data.username, data.balance ?? 200);
      router.replace("/");
    } catch {
      setErr("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-6">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="text-5xl">🍓</div>
          <h1 className="text-2xl font-bold tracking-tight">Chloe</h1>
          <p className="text-sm text-muted-foreground">你的私人 AI 助理</p>
        </div>

        {/* Form */}
        <div className="space-y-4">
          {step === "invite" ? (
            <>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">邀请码</label>
                <input
                  type="text"
                  placeholder="输入邀请码"
                  value={invite}
                  onChange={e => setInvite(e.target.value.toUpperCase().replace(/\s/g, ""))}
                  onKeyDown={e => e.key === "Enter" && handleRedeem()}
                  className="w-full bg-secondary rounded-xl px-4 py-3 text-sm outline-none
                             placeholder:text-muted-foreground tracking-[0.2em] font-mono"
                  autoFocus
                />
              </div>

              {err && <p className="text-xs text-red-400">{err}</p>}

              <button
                onClick={handleRedeem}
                disabled={loading || !invite.trim()}
                className="w-full py-3 rounded-xl bg-primary text-primary-foreground text-sm font-semibold
                           disabled:opacity-40 hover:opacity-90 transition-opacity"
              >
                {loading ? "进入中…" : "进入"}
              </button>
            </>
          ) : step === "phone" ? (
            <>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">手机号</label>
                <div className="flex items-center gap-2 bg-secondary rounded-xl px-4 py-3">
                  <span className="text-sm text-muted-foreground shrink-0">+86</span>
                  <input
                    type="tel"
                    inputMode="numeric"
                    placeholder="请输入手机号"
                    value={phone}
                    onChange={e => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
                    onKeyDown={e => e.key === "Enter" && handleSendOtp()}
                    className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                    autoFocus
                  />
                </div>
              </div>

              {err && <p className="text-xs text-red-400">{err}</p>}

              <button
                onClick={handleSendOtp}
                disabled={loading || phone.length < 11}
                className="w-full py-3 rounded-xl bg-primary text-primary-foreground text-sm font-semibold
                           disabled:opacity-40 hover:opacity-90 transition-opacity"
              >
                {loading ? "发送中…" : "获取验证码"}
              </button>
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">验证码</label>
                  <span className="text-xs text-muted-foreground">{phone}</span>
                </div>
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="6 位验证码"
                  maxLength={6}
                  value={code}
                  onChange={e => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  onKeyDown={e => e.key === "Enter" && handleVerify()}
                  className="w-full bg-secondary rounded-xl px-4 py-3 text-sm outline-none
                             placeholder:text-muted-foreground tracking-[0.3em] font-mono"
                  autoFocus
                />
              </div>

              {err && <p className="text-xs text-red-400">{err}</p>}

              <button
                onClick={handleVerify}
                disabled={loading || code.length < 6}
                className="w-full py-3 rounded-xl bg-primary text-primary-foreground text-sm font-semibold
                           disabled:opacity-40 hover:opacity-90 transition-opacity"
              >
                {loading ? "验证中…" : "登录 / 注册"}
              </button>

              <button
                onClick={() => { setStep("phone"); setCode(""); setErr(""); }}
                className="w-full py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                换个手机号
              </button>
            </>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground">
          登录即同意用户协议 · 新用户赠送 200 🍓 草莓
        </p>

        {/* 开发测试入口（仅本地 dev 构建可见，生产 build 时自动消失） */}
        {process.env.NODE_ENV !== "production" && (
          <div className="pt-3 border-t border-border/30 space-y-2">
            {!showTest ? (
              <button
                onClick={() => setShowTest(true)}
                className="w-full py-2 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
              >
                开发测试入口（跳过登录）
              </button>
            ) : (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="测试用户名（默认 tester）"
                  value={testUser}
                  onChange={e => setTestUser(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleTestLogin()}
                  className="w-full bg-secondary rounded-xl px-4 py-2 text-sm outline-none placeholder:text-muted-foreground"
                />
                <button
                  onClick={handleTestLogin}
                  disabled={loading}
                  className="w-full py-2 rounded-xl bg-secondary text-sm font-medium disabled:opacity-40 hover:bg-secondary/80 transition-colors"
                >
                  {loading ? "进入中…" : "以测试身份进入"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
