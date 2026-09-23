"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setAuth } from "@/lib/auth";
import Signal from "@/components/Signal";

import { API_BASE as API } from "@/lib/config";

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

  // 开发测试入口：不走短信 OTP，直接以指定 username 建立会话。
  // 仅 NODE_ENV=development 时渲染按钮；后端也需 DEV_MODE=1，否则返回 404。
  async function handleTestLogin() {
    setErr("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/test-login`, {
        method:  "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ username: testUser.trim() || "tester" }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.detail || "测试登录失败（后端是否 DEV_MODE=1？）");
        return;
      }
      setAuth(data.username, data.balance ?? 200);
      router.replace("/");
    } catch {
      setErr("网络错误");
    } finally {
      setLoading(false);
    }
  }

  async function handleRedeem() {
    if (loading) return;
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
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ code: inviteCode }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.detail || "邀请码无效");
        return;
      }
      setAuth(data.username, data.balance ?? 200);
      router.replace("/");
    } catch {
      setErr("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendOtp() {
    if (loading) return;
    setErr("");
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setErr("请输入正确的手机号");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/send-otp`, {
        method:  "POST",
        credentials: "include",
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
    if (loading) return;
    setErr("");
    if (code.length !== 6) {
      setErr("验证码是 6 位数字");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/verify-otp`, {
        method:  "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ phone, code }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.detail || "验证失败");
        return;
      }
      setAuth(data.username, data.balance ?? 200);
      router.replace("/");
    } catch {
      setErr("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6 max-md:min-h-dvh max-md:px-4 max-md:py-6 max-md:pb-[calc(24px+env(safe-area-inset-bottom))]">
      <div className="flex w-[360px] flex-col gap-8 max-md:w-full max-md:min-w-0 max-md:gap-6">
        <div className="flex flex-col gap-3">
          <svg className="text-[color:var(--amber-ink)]" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="9" cy="12" r="5.5" />
            <circle cx="15" cy="12" r="5.5" />
          </svg>
          <div className="echo text-[44px]" data-text="Chloe">Chloe</div>
          <p className="text-[15px] text-muted-foreground">每个人自己的分身。</p>
          <Signal mode="idle" className="mt-2" />
        </div>

        <div className="glass rounded-[10px] border p-[22px]" style={{ borderColor: "var(--glass-border)" }}>
          <div className="flex flex-col gap-3.5">
            {step === "invite" ? (
              <>
                <label className="flex flex-col gap-1.5 text-xs font-medium">邀请码
                  <input
                    type="text"
                    placeholder="输入邀请码"
                    value={invite}
                    disabled={loading}
                    onChange={e => setInvite(e.target.value.toUpperCase().replace(/\s/g, ""))}
                    onKeyDown={e => e.key === "Enter" && handleRedeem()}
                    className="w-full rounded-[6px] border bg-card px-3 py-[9px] text-sm font-mono tracking-[0.2em] outline-none placeholder:font-sans placeholder:tracking-normal placeholder:text-muted-foreground focus:border-[color:var(--amber-ink)] disabled:opacity-50"
                    autoFocus
                  />
                </label>

                {err && <p className="text-xs text-[color:var(--rec)]">{err}</p>}

                <button
                  onClick={handleRedeem}
                  disabled={loading || !invite.trim()}
                  className="btn btn-primary w-full h-10"
                >
                  {loading ? "进入中…" : "进入"}
                </button>
              </>
            ) : step === "phone" ? (
              <>
                <label className="flex flex-col gap-1.5 text-xs font-medium">手机号
                  <div className="flex w-full items-center gap-2 rounded-[6px] border bg-card px-3 py-[9px] focus-within:border-[color:var(--amber-ink)]">
                    <span className="text-sm text-muted-foreground shrink-0">+86</span>
                    <input
                      type="tel"
                      inputMode="numeric"
                      placeholder="请输入手机号"
                      value={phone}
                      disabled={loading}
                      onChange={e => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
                      onKeyDown={e => e.key === "Enter" && handleSendOtp()}
                      className="min-w-0 flex-1 bg-transparent text-sm font-normal outline-none placeholder:text-muted-foreground disabled:opacity-50"
                      autoFocus
                    />
                  </div>
                </label>

                {err && <p className="text-xs text-[color:var(--rec)]">{err}</p>}

                <button
                  onClick={handleSendOtp}
                  disabled={loading || phone.length < 11}
                  className="btn btn-primary w-full h-10"
                >
                  {loading ? "发送中…" : "获取验证码"}
                </button>
              </>
            ) : (
              <>
                <label className="flex flex-col gap-1.5 text-xs font-medium">
                  <div className="flex items-center justify-between">
                    <span>验证码</span>
                    <span className="font-normal text-muted-foreground">{phone}</span>
                  </div>
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder="6 位验证码"
                    maxLength={6}
                    value={code}
                    disabled={loading}
                    onChange={e => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    onKeyDown={e => e.key === "Enter" && handleVerify()}
                    className="w-full rounded-[6px] border bg-card px-3 py-[9px] text-sm font-mono tracking-[0.3em] outline-none placeholder:font-sans placeholder:tracking-normal placeholder:text-muted-foreground focus:border-[color:var(--amber-ink)] disabled:opacity-50"
                    autoFocus
                  />
                </label>

                {err && <p className="text-xs text-[color:var(--rec)]">{err}</p>}

                <button
                  onClick={handleVerify}
                  disabled={loading || code.length < 6}
                  className="btn btn-primary w-full h-10"
                >
                  {loading ? "验证中…" : "登录 / 注册"}
                </button>

                <button
                  onClick={() => { setStep("phone"); setCode(""); setErr(""); }}
                  className="btn btn-quiet w-full"
                >
                  换个手机号
                </button>
              </>
            )}

            <p className="text-xs leading-relaxed text-muted-foreground">内测阶段凭邀请码进入。登录即同意用户协议，新用户赠送 <b className="readout">200</b> 颗草莓。</p>
          </div>
        </div>

        {/* 开发测试入口（仅本地 dev 构建可见，生产 build 时自动消失） */}
        {process.env.NODE_ENV !== "production" && (
          <div className="pt-3 border-t border-border/30 space-y-2">
            {!showTest ? (
              <button
                onClick={() => setShowTest(true)}
                className="btn btn-quiet w-full"
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
                  className="w-full rounded-[6px] border bg-card px-3 py-[9px] text-sm outline-none placeholder:text-muted-foreground focus:border-[color:var(--amber-ink)] disabled:opacity-50"
                />
                <button
                  onClick={handleTestLogin}
                  disabled={loading}
                  className="btn btn-quiet w-full"
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
