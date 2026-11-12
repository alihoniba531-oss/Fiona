# R1 返修报告：修改意见卡（规格 v1.4 §4.6）

分支 `feat/novel-feedback`，基线 `7a17f64`。本报告只记录 R1；R0 报告仍为 `impl/report.md`，本轮未改。

## 拆分与执行

### 第一轮：产品与文档（`parallel()`，3 个 agent）

| agent | 负责文件 | 规格 | 结果 |
|---|---|---|---|
| card-p1 | `frontend/components/NovelFeedbackCard.tsx` | §4.6 P1、§4.3 T6.3 第 3 支/T6.6 | 完成模块级 `redoCostSentence`、`redoAvailable`，渲染第 3 支改用这两个函数；`sendRedo` 先重读，失败/不可用只更新卡片或报错，不再弹旧费用确认框。`tsc` 0、lint 25 既有 warnings、build 0。 |
| service-p2 | `backend/novel/service.py` | §4.6 P2、§4.2 T3 | 仅把条件改为 `current_plan 去空白为空 or plan_chapter is None`，其余不动。针对性既有测试 93 条通过。 |
| docs-d1-d4 | `PLAN.md`、`docs/DEPLOYMENT.md`、`README.md`、`CLAUDE.md` | §4.6 D1–D4 | 四份文档按给定句逐字替换/插入；每处新句恰好 1 次，旧句不再出现；相关文档测试 36 条通过。 |

### 第二轮：测试补齐（`parallel()`，2 个 agent）

| agent | 负责文件 | 规格 | 结果 |
|---|---|---|---|
| tests-backend-r1 | `backend/tests/test_novel_chat_feedback.py` | §4.6 B1–B6 | 完成：129 passed；B1 三种状态参数化、B2 四边界、B3 pending 计数、B4 章号上限、B5 K≥max 分支、B6 plan_chapter NULL；13 个坏副本用例全部变红通过。 |
| tests-frontend-r1 | `backend/tests/test_novel_chat_feedback_frontend.py` | §4.6 F1–F8 | 完成：107 passed；F1 两条断言、F2 守卫、F3 K≥max、F4 同步连点、F5/F6 卸载 setter 计数、F7 重读五态、F8 既有交互适配；13 个 self_check 用例通过。 |

无第三次派发；主代理未发现需要返修的产品实现。

## 1. 修改了哪些文件

### R1 实际变更（相对 R0）

- `frontend/components/NovelFeedbackCard.tsx`（P1）
- `backend/novel/service.py`（P2，一处条件）
- `PLAN.md`、`docs/DEPLOYMENT.md`、`README.md`、`CLAUDE.md`（D1–D4）
- `backend/tests/test_novel_chat_feedback.py`、`backend/tests/test_novel_chat_feedback_frontend.py`（B1–B6/F1–F8）
- `docs/tasks/2026-11-12-novel-feedback/impl/report-r1.md`（本文件）

未动 `backend/tests/test_desk_polish_frontend.py`、`impl/report.md`、`02-spec.md`、`03-dispatch.md`、`04-review.md`、`05-fix-r1.md`、`frontend/app/page.tsx` 或任何既有测试文件。保护文件哈希在 R1 前后一致：`impl/report.md` = `3db982ec…`，`test_desk_polish_frontend.py` = `47e529fd…`，`02-spec.md` = `d07051c2…`，`04-review.md` = `356a03a1…`。

### `git status --porcelain --untracked-files=all` 原文

```
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/agent_store.py
 M backend/database.py
 M backend/novel/service.py
 M backend/routers/novel.py
 M backend/services/chat_service.py
 M backend/services/claude_agent.py
 M backend/studio/sources.py
 M backend/tests/test_studio_sources_readonly_integration.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/components/desk/DeskChaptersView.tsx
 M frontend/components/desk/DeskDialogs.tsx
 M frontend/components/desk/DeskEpisodesView.tsx
 M frontend/lib/useConversations.ts
?? backend/novel/feedback.py
?? backend/tests/test_desk_polish_frontend.py
?? backend/tests/test_novel_chat_feedback.py
?? backend/tests/test_novel_chat_feedback_frontend.py
?? docs/tasks/2026-11-12-novel-feedback/01-brief.md
?? docs/tasks/2026-11-12-novel-feedback/02-spec.md
?? docs/tasks/2026-11-12-novel-feedback/03-dispatch.md
?? docs/tasks/2026-11-12-novel-feedback/04-review.md
?? docs/tasks/2026-11-12-novel-feedback/05-fix-r1.md
?? docs/tasks/2026-11-12-novel-feedback/impl/report-r1.md
?? docs/tasks/2026-11-12-novel-feedback/impl/report.md
?? frontend/components/NovelFeedbackCard.tsx
?? frontend/lib/novelFeedback.ts
```

R0 已有的 20 个 `M` + 10 个 `??` 仍存在；R1 新增的差异是上述 8 个实现/测试/文档文件与本报告。`01-brief.md`、`02-spec.md`、`03-dispatch.md`、`04-review.md`、`05-fix-r1.md` 为派单方任务文件，非本轮修改。

`backend/tests` 专项：

```
 M backend/tests/test_studio_sources_readonly_integration.py
?? backend/tests/test_desk_polish_frontend.py
?? backend/tests/test_novel_chat_feedback.py
?? backend/tests/test_novel_chat_feedback_frontend.py
```

授权既有测试 diff 仍恰 2 个 hunk（`@@ -29 +29 @@` 与 `@@ -199,0 +200,3 @@`），未增加。

## 2. 实现了哪些功能

- **P1**：点击「带着这些要求重新定稿」时先 `GET /novels/feedback/{id}` 重新读一次；重读失败只在第一节末尾报错、不弹框；重读成功先用新视图替换卡片，再按新视图判断是否仍可重定稿，并按新视图的 `redo_cost` 弹确认框。新增组件外纯函数 `redoCostSentence(cost)` 与 `redoAvailable(view)`；渲染第 3 支与费用句也统一走这两个函数。
- **P2**：`redo_feedback_plan` 对 `current_plan` 去空白为空或 `plan_chapter` 为 NULL 的卡片一律返回 409「这张卡没有重新定稿的要求」，防止直接改库造出的卡跳过章号核对。
- **D1–D4**：更新重新定稿流程说明、部署兼容 DDL 清单、README 作者说明和 CLAUDE 技术说明。
- **B1–B6/F1–F8**：补齐复核指出的分支、边界、守卫、连点、卸载、重读、HEAD 对照相关测试，并保留原有交互意图。

## 3. 与 §4.6 各条逐项对应

### P1

- `redoCostSentence` 为模块级函数，`own_model` / `free` 外一律返回 `strawberries` 句。
- `redoAvailable(view)` 的条件与 §4.6 完全一致：`current_plan.trim()` 非空、`plan_chapter !== null`、`redo_started_at` 空、`book !== null`、`awaiting_plan`、`awaiting_chapter === plan_chapter`、`automation === "per_chapter"`。
- 渲染第 3 支由 `redoAvailable(view)` 判断，费用句由 `redoCostSentence(view.book?.redo_cost)` 生成；其余 9 支顺序与文案未动，T6.4/T6.5/底部提示未动。
- `sendRedo`：`busyRef` 防重入 → `busy = "confirm"` → 重读 → 失败报错并复位 / 成功替换视图 → `redoAvailable` 为假复位 / 为真按新 `plan_chapter` 与新 `redo_cost` 拼 title/body → `confirm` → 返回 true 才 POST。重读期间按钮文字不变且两个动作均禁用。
- 每次 `await` 后均检查 `signal.aborted`；仍是单函数组件，无新增 hooks/子组件，lint 0 新增 warning。

### P2

- 只改 `redo_feedback_plan` 的判空条件为 `not (card['current_plan'] or '').strip() or card['plan_chapter'] is None`，错误文案与判断顺序不变。

### D1–D4

- D1 `PLAN.md:519` 两处均按指定新句替换；新句各 1 次，旧句 0 次。
- D2 `docs/DEPLOYMENT.md:584` 在指定锚点后插入「书斋草稿与修改意见卡同样…」；锚点保留，新句 1 次。
- D3 `README.md:369` 改为「点按钮时卡片会先重新读一次…」；旧句 0 次。
- D4 `CLAUDE.md:198` 两处改为「点击后卡片先重新读取一次…」与「…或没有记下章号时拒绝」；旧句 0 次。

### B1–B6

- B1：`test_feedback_view_planned_read_from_in_progress_meeting` 参数化为三种状态；坏副本去掉 `writing` / 去掉 `planning+writing` 时对应组均变红。
- B2：四个上限正样本均 `error is None` 并核对清洗值；四处 `>` 改 `>=` 时分别变红。
- B3：本书 2 pending + 1 delivered + 另一本书 1 pending，断言 `pending_notes == 2`；写死 0、去 `status='pending'`、去按书过滤三种坏副本都变红。
- B4：`chapters_done=2`、第 3 章行 `done` 时拒绝；去掉 `or number > chapters_done` 变红。
- B5：`K == max_chapters` 且 `ending_status="continue"` 时回灌第二句走「最后一章」支，全文无 `K+1`；去掉 `K >= M` 变红。
- B6：`plan_chapter=NULL` 卡片返回 409 且无副作用；去掉新条件变红（坏副本会直接启动第 3 章重定稿）。

### F1–F8

- F1：新增「书在等第 3 章、卡是第 2 章」的不可用分支和「已发起重定稿但书在等第 3 章」分支；自检分别删 `redoAvailable` 章号比较与第 1 支追加条件。
- F2：12 个指定用例（参数化 14 条）均在依赖守卫后、读组件/请求模块前 `_require_feedback()`；R1 新 node 用例同样遵守。HEAD 导出上跑该前端测试：`103 failed, 4 passed`，`FileNotFoundError=0`。
- F3：`awaiting_chapter=50、max_chapters=50、awaiting_is_final=False` 的 note=None 与 pending 两态，说明含第 50 章句、无第 51 章；删 `K >= max` 变红。
- F4：同步连点两次，交留言只 1 次；重定稿重读只 1 次、confirm 1 次、POST 1 次；分别删 busyRef 守卫变红。
- F5/F6：重读未返回时卸载、确认框打开时卸载都不调用后续动作；迷你运行时记录卸载后 setter 次数并断言 0，删 abort 判断后变红。
- F7：重读最新费用、已不可用、已在别处发起、ApiError/TypeError 失败、顺序与忙碌态；跳过重读、旧费用、跳过 availability 三种坏副本变红。
- F8：既有重定稿交互按多一次重读调整 `calls.get`，保留确认框 1 次、POST 1 次、失败后额外拉取 1 次、三种费用逐字。

### §4.4 第 2 条：六份文档全部改动位置

含 R0 已改与 R1 D1–D4：

| 文件 | 位置 | 内容 |
|---|---|---|
| `CLAUDE.md` | 30 | R0 例外清单加入修改意见卡与三列 |
| `CLAUDE.md` | 198 | R0 新增整段；R1 D4 改流程与拒绝条件 |
| `README.md` | 142 | R0 例外清单 |
| `README.md` | 369 | R0 新增作者段；R1 D3 改重读费用说明 |
| `PLAN.md` | 23 | R0 例外清单 |
| `PLAN.md` | 515–523 | R0 新增「2026-11-12：修改意见卡」；R1 D1 改第 519 行两处 |
| `docs/ARCHITECTURE.md` | 21、54、137、141、324、328、418 | R0 更新例外清单、消息列、历史重建、工具卡、DDL、数据流、小说聊天段 |
| `docs/DEPLOYMENT.md` | 257、584、866–870 | R0 例外清单与三开关；R1 D2 在 584 插兼容 DDL 句 |
| `backend/.env.example` | 47、211–212 | R0 例外清单与 `FIONA_NOVEL_CHAT_FEEDBACK` 注释/开关 |

## 4. 测试结果

### §5.1 `npx tsc --noEmit`

```bash
cd frontend && npx tsc --noEmit
```

无输出，退出码 `0`。

### §5.2 `npm run lint`

```text
✖ 25 problems (0 errors, 25 warnings)
```

退出码 `0`；25 条均在既有 `app/page.tsx` / `app/plaza/page.tsx`，新文件 0 warning。

### §5.3 `npm run build`

```text
✓ Compiled successfully in 432ms
✓ Generating static pages using 17 workers (18/18) in ...
```

退出码 `0`。

### §5.4 后端全量

```bash
cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local \
  .venv/bin/python -m pytest -q -p no:cacheprovider
```

原始尾行：

```text
8256 passed, 37 warnings in 375.23s (0:06:15)
```

退出码 `0`；0 failed、0 skipped。`8256 = 8011 + 245`，245 为三个新文件收集数。

### §5.5 三个新文件与无 node_modules 副本

三个新文件（有 node_modules）：

```text
245 passed, 35 warnings in 29.06s
```

收集数：`129 + 107 + 9 = 245`。

无 node_modules 副本按规格 rsync 后：

```text
SKIPPED [87] tests/test_novel_chat_feedback_frontend.py:63: frontend dependencies unavailable: typescript, react, react-dom/server
SKIPPED [9] tests/test_desk_views_frontend.py:36: frontend dependencies unavailable: typescript, react, react-dom/server
149 passed, 96 skipped, 35 warnings in 6.26s
```

退出码 `0`。`87 + 9 = 96`：前端新文件 107 条中 20 条源码断言、87 条起 node；案头 9 条全部起 node。副本内确认无 `frontend/node_modules`，`backend/.venv` 保留。

### §5.6 改动集合

见 §1 的完整 `git status`；`backend/tests` 只有三个 `??` 与授权文件的 ` M`，授权 diff 恰 2 hunk。`git diff --check` 退出码 `0`。

### §5.7 既有文件列表

规格列出的 23 个文件加上授权文件合跑：

```text
573 passed, 37 warnings in 64.31s (0:01:04)
```

退出码 `0`。授权文件单独跑：`5 passed`。

### §5.8 计数

```text
ALTER TABLE messages ADD COLUMN novel_feedback_id = 1
FIONA_NOVEL_CHAT_FEEDBACK: sources.py=1, .env.example=1, CLAUDE.md=1
draft_novel_feedback in claude_agent.py = 2
page.tsx BOM = efbbbf
desk stat = DeskChaptersView.tsx, DeskDialogs.tsx, DeskEpisodesView.tsx
forbidden frontend stat = 空
```

### §5.9 开关为 0

```text
30 passed, 99 deselected in 0.81s
```

覆盖开关矩阵的 30 条写死期望，退出码 `0`。

### R1 坏副本自检

- 后端 `-k bad_`：`16 passed, 113 deselected in 2.38s`；各用例打印的变红摘要已随测试执行打印（B1 三态缺失、B2 四边界、B3 三种计数、B4 章号上限、B5 最后一章、B6 无章号等）。
- 前端 `-k self_check`：`13 passed, 94 deselected in 6.21s`；输出包含 F1(a)/(b)、F3 两态、F4 两处、F5/F6、F7 三组、HEAD 相关等的实际断言失败摘要，例如：
  - `F1(a) bad copy: 第 2 章细纲已经不在等你确认了，这一项不能再用。`
  - `F4 note bad copy: {'note': 2} != {'note': 1}`
  - `F6 note-resolve bad copy: 卸载后仍调用了 3 次 state setter`
  - `F7 old-fee bad copy: ...own_model... != ...strawberries...`
- HEAD 导出（`7a17f64`）前端新测试：`103 failed, 4 passed`，`FileNotFoundError` 计数 `0`，失败均为 `AssertionError`；符合 F2 守卫目标。

## 5. 未完成或需要人工确认

- 未发现 §4.6 自相矛盾，也未发现照做会违反 §4.6 之外条款的情况。
- `redoCostSentence` 的入参类型按 `NovelFeedbackView["book"]["redo_cost"] | undefined` 收窄；实际运行中 `own_model`/`free` 之外都走 strawberries 分支，符合 §4.6。若以后新增第四种 `redo_cost`，会默认按扣草莓说明，这是刻意的安全回退。
- 本轮未改 `frontend/app/page.tsx`；BOM 仍为 `efbbbf`。
- `frontend/tsconfig.tsbuildinfo` 是 `tsc` 的既有被忽略缓存，未进入改动集合。
- HEAD 对照由主代理额外跑了前端新文件（F2）；后端 HEAD 对照未在本轮重复，R1 未改后端产品行为，除 P2 一条 409 条件外均由现有全量/既有测试覆盖。
- 无依赖安装、无 `.env` 读取、无 Git commit/stash/checkout/reset。
