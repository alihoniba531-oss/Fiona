# R1 返修单：修改意见卡（规格 v1.4 §4.6）

你是上一轮的实施方，本轮在同一个工作区继续。独立复核 `docs/tasks/2026-11-12-novel-feedback/04-review.md` 判了不通过，作者另外确认了一处产品改动。

**本轮只做 `02-spec.md` §4.6 列出的内容。** 先完整读 §4.6，再读它引用的几处：§4.3 T6.3 第 3 支与 T6.6、§4.2 T3 的 `redo_feedback_plan`、§4.5 后端第 3 条与第 12 条。`04-review.md` 可以当背景看，但两者不一致时按 §4.6 做。

## 规矩（与上一轮相同）

- 只改 §4.6「R1 白名单」里的文件。不改 `02-spec.md`、`03-dispatch.md`、`04-review.md`、本文件、`impl/report.md`，也不改任何既有测试文件。
- 不执行 `git commit` / `git stash` / `git checkout` / `git reset`；不安装或升级依赖；不读 `.env` / `.env.local`。
- 改前端之前先读 `frontend/AGENTS.md`。`frontend/app/page.tsx` 本轮不动。
- 跑 Python 一律用 `backend/.venv/bin/python -m pytest ...`，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。
- 何时停下来问：只有 §4.6 自相矛盾，或照做会违反 §4.6 之外的规格条款时，才停下来说明。测试怎么写、锚点怎么选，自己决定，并在报告里写明理由。你实测到的事实优先于规格里的断言，两者不符就停下来说明。任何情况下都不回滚已完成的工作。
- 坏副本锚点提示：
  - `novel/service.py` 里 `SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=? AND status='pending'` 一共出现 4 次，B3 的锚点要带上 `(card['novel_id'],)`。
  - `novel/feedback.py` 里有两处 `> TEXT_MAX`，用 `len(next_text)` 和 `len(current_text)` 区分。
  - P1 之后，F1 (a) 的锚点在 `redoAvailable` 里。

## 并行方式

用工作流（workflow 工具）并行：在脚本里用 parallel() 同时运行多个 agent，按文件拆分，文件不重叠。每个 agent 的任务说明要自包含，把 §4.6 里与它相关的条目原文贴进去，并写明不得调用 subagent / subagent_fork / workflow。

建议分两轮：

- **第一轮**，并行 3 个 agent：
  1. `frontend/components/NovelFeedbackCard.tsx`，做 P1；
  2. `backend/novel/service.py`，做 P2；
  3. 四份文档，做 D1–D4。逐字替换，改完逐条 grep，确认每个新句子都恰好出现 1 次。
- **第二轮**，等第一轮落盘后并行 2 个 agent：
  1. `backend/tests/test_novel_chat_feedback.py`，做 B1–B6；
  2. `backend/tests/test_novel_chat_feedback_frontend.py`，做 F1–F8。

分工：
- 主代理只做拆分、派发、汇总、白名单检查、§5 验收和写报告。
- 代理失败时，先读它的结果再决定怎么办，不要盲目重派。
- 报告开头列拆分表，如实列出所有派出过的代理。

## 完成后

按 §4.6「R1 验收」重跑，并写 `impl/report-r1.md`。变更总结写五项：
1. 修改了哪些文件；
2. 实现了哪些功能；
3. 与 §4.6 各条逐项对应；
4. 测试结果；
5. 未完成或需要人工确认的地方。
