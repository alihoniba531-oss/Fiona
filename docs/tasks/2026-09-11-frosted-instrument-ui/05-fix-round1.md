# 返修指令（第 1 轮独立复核后）

复核结论：视觉与结构按规格落地，门禁通过，行为红线无违反；但有 2 处必须修复，外加 1 处规格自身遗漏的一致性问题。**只改下面三处，其余任何文件、任何行都不动。**

1. `frontend/app/globals.css`，`.typing-cursor::after` 规则里 `color: var(--hud-cyan);` 改为 `color: var(--amber-ink);`（`--hud-cyan` 已被删除，光标现在没有颜色）。
2. `frontend/components/ConversationPicker.tsx`，`formatRelative` 里 `const date = new Date(iso);` 改为：
   `const date = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");`
   原因：后端 `updated_at` 形如 `2026-09-11 12:41:09`，是 UTC 且无时区标记，直接 `new Date` 会按本地时区解析，列表时间比消息时间偏一个时区。与 `app/history/page.tsx` 的 `parseUtcTimestamp` 做法一致。
3. `frontend/app/page.tsx` 四个右侧抽屉的宽度表达式仍按旧侧栏 64px 计算，侧栏已改 56px。把所有 `100vw - 64px` 改成 `100vw - 56px`（含 `min(960px, calc(100vw - 64px))` 与 `calc((100vw - 64px) * 2 / 3)` 两种写法）。

## 验收（在 frontend/ 目录执行，先跑对照再判定）

```bash
grep -c "hud-cyan" app/globals.css                                  # 改前 1 → 期望 0
grep -c 'replace(" ", "T") + "Z"' components/ConversationPicker.tsx  # 改前 0 → 期望 1
grep -c "100vw - 64px" app/page.tsx                                 # 改前 4 → 期望 0
grep -c "100vw - 56px" app/page.tsx                                 # 期望 4
npm run lint            # 0 errors
npx tsc --noEmit        # 无输出
```

把上述命令的原始输出追加到 `03-report.md` 末尾，标题「返修 1」。不要运行 build、dev、start。
