# 返修指令（第 1 轮复核后）

只改下列两处，其余一律不动。改完在 `frontend/` 目录跑 `npm run lint`、`npx tsc --noEmit` 和下面的判据命令，把原始输出追加到 `docs/tasks/2026-09-12-frosted-instrument-ui-v2/03-report.md` 末尾「## 返修 1」一节。

## 1. `frontend/components/ChatBubble.tsx`：带卡片的分身回复正文不能被隐藏

现状：第 269 行左右的文字块守卫是 `{!message.cardData && !message.generationStatus && (message.content || message.isTyping) && message.content !== "[发了一张图片]" && (…)}`。`page.tsx` 在收到卡片时会把 `cardData: card` 与 `content: tip` 一起写进同一条分身消息，这个 `!message.cardData` 守卫会把正文（天气建议、「搜到了…」提示句）整段藏掉。

改法：
- 去掉守卫里的 `!message.cardData &&`，其余条件不变。
- 调整顺序为：名字标签 → 文字正文 → 天气卡 / 网页卡 → 「帮我读 / 不用」按钮 → Meta 行。即把文字块整段移到「天气卡片（weather subtype）」块之前。
- 卡片与正文之间用 `gap` 已有的 6px 间距即可，不加额外 margin。

判据：
```bash
grep -c '!message.cardData &&' components/ChatBubble.tsx   # 期望 0（改前 1）
# 文字块必须出现在天气卡块之前：
awk '/message.cardData\?\.subtype === "weather"/{w=NR} /!message.generationStatus && \(message.content \|\| message.isTyping\)/{t=NR} END{print (t<w)?"order ok":"ORDER WRONG"}' components/ChatBubble.tsx   # 期望 order ok
```

## 2. `frontend/components/MyAgentWorkspace.tsx`：恢复「查看已保存的公开名片」链接

现状：基线第 153 行的 `{savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} …><ExternalLink size={13} />查看已保存的公开名片</Link>}` 及 `ExternalLink` 的 lucide import 被删了，这是功能回退。

改法：在右栏 `AgentIdentityCard` 与 `.note` 提示之间恢复这一行，条件、href、文案原样，样式改为 `inline-flex items-center gap-1.5 text-xs text-[color:var(--amber-ink)] hover:underline`；恢复 `ExternalLink` import。

判据：
```bash
grep -c '查看已保存的公开名片' components/MyAgentWorkspace.tsx   # 期望 1（改前 0）
grep -c 'ExternalLink' components/MyAgentWorkspace.tsx   # 期望 2（import + 使用；改前 0）
grep -c 'savedAgent?.is_public && <Link' components/MyAgentWorkspace.tsx   # 期望 1
```

## 通用判据
```bash
npm run lint      # 0 errors，warnings ≤ 28
npx tsc --noEmit  # 无输出
```
不得改其他文件，不得回滚已完成的工作。
