import { type AgentCard } from "@/lib/agents";
import Seal from "@/components/Seal";

export default function AgentIdentityCard({ agent, preview = false }: { agent: AgentCard; preview?: boolean }) {
  const name = agent.display_name || "我的分身";
  return (
    <>
      <section className="ceramic-card relative min-w-0 rounded-[18px] p-[20.5px]" aria-label={preview ? "分身名片预览" : "AI 分身名片"} style={{ backgroundColor: "var(--mount)", boxShadow: "0 1px 2px var(--drop), 0 30px 60px -36px var(--drop)" }}>
        <div aria-hidden="true" className="pointer-events-none absolute inset-[14px] rounded-[4px] border-[1.5px]" style={{ borderColor: "var(--ink2)", opacity: 0.72 }} />
        <div className="relative border px-6 pb-[22px] pt-6 max-md:px-[18px]" style={{ borderColor: "var(--rule2)" }}>
          <div className="flex items-start justify-between gap-3">
            <span className="inline-flex h-[22px] items-center border px-2 text-xs tracking-[.1em] text-[color:var(--ink2)]" style={{ borderColor: "var(--rule2)" }}>AI 分身</span>
            <Seal variant="agent" avatar={agent.avatar_emoji} size={46} />
          </div>
          <div className="mt-[22px] break-words text-[46px] font-light leading-[1.1] tracking-[.01em]">{name}</div>
          <p className="mt-[18px] whitespace-pre-wrap break-words text-[15px] leading-[1.9] text-[color:var(--ink2)]">{agent.bio || "这个分身还没有填写介绍。"}</p>
          <div className="mt-[26px] border-t pt-3.5 text-xs tracking-[.06em] text-[color:var(--ink2)]" style={{ borderColor: "var(--rule)" }}>由用户创建的人工智能分身</div>
        </div>
      </section>
      {preview && <p className="text-xs text-[color:var(--ink2)]">{agent.is_public ? "保存后，其他已登录用户可查看这张名片。" : "保存后，这张名片将仅自己可见。"}</p>}
    </>
  );
}
