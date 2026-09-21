import { type AgentCard } from "@/lib/agents";

export default function AgentIdentityCard({ agent, preview = false }: { agent: AgentCard; preview?: boolean }) {
  const name = agent.display_name || "我的分身";
  return (
    <section className="glass-card flex flex-col gap-[18px] p-[22px] pb-[18px]" aria-label={preview ? "分身名片预览" : "AI 分身名片"}>
      <div className="flex items-center justify-between">
        <span className="tag tag-amber">AI 分身</span>
        <span className="readout">{preview ? "名片预览" : "分身名片"}</span>
      </div>
      <div className="py-1 text-[40px]">
        {name.length <= 12
          ? <span className="echo" data-text={name}>{name}</span>
          : <span className="break-words text-[28px] font-medium">{name}</span>}
      </div>
      <p className="whitespace-pre-wrap break-words text-[13px] leading-[1.7]">{agent.bio || "这个分身还没有填写介绍。"}</p>
      <div className="flex items-center gap-2.5 border-t pt-3.5 text-xs text-muted-foreground" style={{ borderColor: "var(--glass-border)" }}>
        <span className="grid h-8 w-8 place-items-center rounded-[6px] bg-secondary text-base" aria-hidden="true">{agent.avatar_emoji || "✨"}</span>
        <span>由用户创建的人工智能分身</span>
      </div>
      {preview && <p className="text-xs text-muted-foreground">{agent.is_public ? "保存后，其他已登录用户可查看这张名片。" : "保存后，这张名片将仅自己可见。"}</p>}
    </section>
  );
}
