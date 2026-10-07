"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setAuth } from "@/lib/auth";
import Signal from "@/components/Signal";
import Glaze from "@/components/Glaze";
import InkLandscape from "@/components/InkLandscape";
import Seal from "@/components/Seal";

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
    <main className="relative flex min-h-dvh items-center overflow-x-hidden max-md:py-10 max-md:pb-[calc(40px+env(safe-area-inset-bottom))]">
      <InkLandscape variant="login" />
      <section className="relative z-[1] box-border w-[560px] max-w-full pb-[72px] pl-[168px] pr-8 max-md:w-full max-md:min-w-0 max-md:px-8 max-md:pb-0">
        <div>
          <Seal variant="brand" size={56} />
          <h1 className="mt-11 text-[76px] font-light leading-none tracking-[0.01em] max-md:mt-7 max-md:text-[64px]">Chloe</h1>
          <p className="mt-[22px] text-[20px] leading-[1.6] tracking-[0.16em] text-[color:var(--ink2)] max-md:text-[18px]">每个人自己的分身。</p>
          <Signal mode="idle" className="mt-3 h-[22px]" />
        </div>

        <Glaze variant="panel" fur className="relative z-[2] -ml-9 mt-[18px] w-[calc(100%+72px)] max-w-[452px] rounded-[18px] px-9 py-[30px] max-md:-ml-4 max-md:w-[calc(100%+32px)] max-md:px-5 max-md:py-6">
          <div className="flex flex-col gap-8">
            {step === "invite" ? (
              <>
                <label className="flex flex-col gap-1 text-[13px] font-normal tracking-[0.14em] text-[color:var(--ink2)]">邀请码
                  <input
                    type="text"
                    placeholder="输入邀请码"
                    value={invite}
                    disabled={loading}
                    onChange={e => setInvite(e.target.value.toUpperCase().replace(/\s/g, ""))}
                    onKeyDown={e => e.key === "Enter" && handleRedeem()}
                    className="readout h-[52px] w-full rounded-none border-0 border-b border-[color:var(--rule2)] bg-transparent p-0 text-[20px] shadow-[0_1px_0_var(--etch)] tracking-[0.12em] text-[color:var(--ink)] outline-none placeholder:tracking-normal placeholder:text-[color:var(--ink2)] focus:border-[color:var(--ink)] disabled:opacity-50"
                    autoFocus
                  />
                </label>

                {err && <p role="alert" className="text-xs text-[color:var(--seal)]">{err}</p>}

                <button
                  onClick={handleRedeem}
                  disabled={loading || !invite.trim()}
                  className="btn btn-primary h-[46px] self-start px-10 text-[15px] tracking-[0.36em]"
                >
                  {loading ? "进入中…" : "进入"}
                </button>
              </>
            ) : step === "phone" ? (
              <>
                <label className="flex flex-col gap-1 text-[13px] font-normal tracking-[0.14em] text-[color:var(--ink2)]">手机号
                  <div className="flex h-[52px] w-full items-center gap-2 border-b border-[color:var(--rule2)] focus-within:border-[color:var(--ink)]">
                    <span className="text-sm text-muted-foreground shrink-0">+86</span>
                    <input
                      type="tel"
                      inputMode="numeric"
                      placeholder="请输入手机号"
                      value={phone}
                      disabled={loading}
                      onChange={e => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
                      onKeyDown={e => e.key === "Enter" && handleSendOtp()}
                      className="min-w-0 flex-1 bg-transparent text-[20px] font-normal text-[color:var(--ink)] outline-none placeholder:text-[color:var(--ink2)] disabled:opacity-50"
                      autoFocus
                    />
                  </div>
                </label>

                {err && <p role="alert" className="text-xs text-[color:var(--seal)]">{err}</p>}

                <button
                  onClick={handleSendOtp}
                  disabled={loading || phone.length < 11}
                  className="btn btn-primary h-[46px] self-start px-10 text-[15px] tracking-[0.36em]"
                >
                  {loading ? "发送中…" : "获取验证码"}
                </button>
              </>
            ) : (
              <>
                <label className="flex flex-col gap-1 text-[13px] font-normal tracking-[0.14em] text-[color:var(--ink2)]">
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
                    className="readout h-[52px] w-full rounded-none border-0 border-b border-[color:var(--rule2)] bg-transparent p-0 text-[20px] shadow-[0_1px_0_var(--etch)] tracking-[0.3em] text-[color:var(--ink)] outline-none placeholder:tracking-normal placeholder:text-[color:var(--ink2)] focus:border-[color:var(--ink)] disabled:opacity-50"
                    autoFocus
                  />
                </label>

                {err && <p role="alert" className="text-xs text-[color:var(--seal)]">{err}</p>}

                <button
                  onClick={handleVerify}
                  disabled={loading || code.length < 6}
                  className="btn btn-primary h-[46px] self-start px-10 text-[15px] tracking-[0.36em]"
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

            <p className="-mt-1 text-[13px] leading-[1.9] tracking-normal text-[color:var(--ink2)]">内测阶段凭邀请码进入。登录即同意用户协议，新用户赠送 <b className="readout">200</b> 颗草莓。</p>
          </div>
        </Glaze>

        {/* 开发测试入口（仅本地 dev 构建可见，生产 build 时自动消失） */}
        {process.env.NODE_ENV !== "production" && (
          <div className="mt-6 space-y-2 border-t border-[color:var(--carve)] pt-3">
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
                  className="h-[44px] w-full rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 text-base outline-none placeholder:text-[color:var(--ink2)] focus:border-[color:var(--ink)] disabled:opacity-50"
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
      </section>
    </main>
  );
}
