# 返修 R1（机械门禁发现，2026-10-26）

本返修单与 `02-spec.md` 同等效力，冲突时以本单为准。§2 的全部约束（不加粗、不改既有测试、不重排既有代码、不新增依赖、白名单）照旧适用。只做下面三项，其余已完成的工作保持不动，不回滚。

本轮不需要拆子代理，直接由你自己完成；不得调用 subagent / subagent_fork / workflow。

## F1 历史页搜索高亮在 AI 回复里丢失（功能退步，必须修）

**现状**：`frontend/app/history/page.tsx` 原来对用户消息和 AI 消息都调用 `highlight(msg.content)`，把搜索词包进 `<mark className="bg-[color:var(--accent)] text-foreground rounded-[3px] px-0.5">`。改成 `<MessageText text={msg.content} />` 后，AI 消息不再高亮：在历史页搜「简单说：」时，页面上 `<mark>` 数为 0。

**改法**：
- `frontend/components/MessageText.tsx` 新增可选属性 `highlight?: string`。非空（`trim()` 后）时，在所有 `text`、`em`、`code` 行内片段以及代码块 `code` 的文字里，按**不区分大小写**的子串匹配，把命中部分包进与历史页完全相同的 `<mark className="bg-[color:var(--accent)] text-foreground rounded-[3px] px-0.5">`；查询词里的正则元字符必须转义（照抄历史页 `highlight` 的转义写法）。空串或只含空白时行为与现在逐字节相同。
- `frontend/app/history/page.tsx`：AI 消息改为 `<MessageText text={msg.content} highlight={query} />`。用户消息保持原来的 `highlight(msg.content)`。
- 新增测试放进**新文件** `backend/tests/test_ui_polish_fix_r1.py`（不改已有的 5 个新测试文件）：能跑 node 时用 `react-dom/server` 渲染 `MessageText`，断言 ① `highlight="SKILL"` 时 `简单说：**给我装个插件（Skill/Tool）**` 里出现恰好 1 个 `<mark`，且 mark 位于 `<em` 内部；② `highlight="("` 不抛异常；③ `highlight=""` 与不传时输出完全相同；④ 代码块和行内代码里的命中也有 `<mark`。node 不可用时按现有做法 skip，并另写一条源码断言：`history/page.tsx` 含 `highlight={query}`。

## F2 着重号太淡（必须修）

`MessageText.tsx` 里 `em` 的着重号颜色从 `var(--ink3)` 改为 `var(--ink2)`，`-webkit-` 与标准属性两处都改，其他不动。实测：1280 宽、DPR 1 下 ink3 的点几乎看不见。

## F3 手机上模型说明被截成「Claude Haiku 5.5 · …」（必须修）

`frontend/app/page.tsx` 的 `ChatModelFooter`：自带模型启用时，标签改为两段，`<span className="min-w-0 truncate" title={labelTitle}>{modelDisplayName(config.model)}<span className="max-md:hidden"> · 不扣草莓</span></span>`。手机上只显示模型名，桌面仍显示「Claude Haiku 5.5 · 不扣草莓」；未启用时的「平台模型 · 每条 10 颗草莓」不变。`title` 不变。若 `test_ui_polish_page_contracts.py` 里有断言依赖原来的 `label` 变量写法而因此变红，**不要改那个测试文件**，在报告里说明，由 Claude 裁决。

## 验收

- `cd frontend && npx tsc --noEmit` 退出码 0；`npm run lint` 0 errors，warning 仍为 25 个。
- 后端全量 `python -m pytest -q`（解释器见 02-spec §5）0 失败；`test_ui_polish_fix_r1.py` 全部通过。
- 改动集合只多出 `backend/tests/test_ui_polish_fix_r1.py` 这一个新文件，修改只涉及 `MessageText.tsx`、`history/page.tsx`、`page.tsx`。
- 在 `03-report.md` 末尾追加「R1」一节：三项各自改了什么、测试原始摘要行。
