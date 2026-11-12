# R2 返修报告：修改意见卡（规格 v1.5 §4.7，只补测试）

分支 `feat/novel-feedback`，基线 `7a17f64`。R2 只改两个新测试文件，新增本报告；产品代码、文档、规格、返修单、复核文件、`impl/report.md`、`impl/report-r1.md` 与既有测试均未动。

## 拆分与执行

`parallel()` 同时运行 2 个 agent，文件不重叠：

| agent | 负责文件 | 规格 | 结果 |
|---|---|---|---|
| r2-frontend-tests | `backend/tests/test_novel_chat_feedback_frontend.py` | §4.7 G1–G5 | 完成：113 passed；G1 调整 F7(c) 夹具与说明断言，G2 四条提前结束复位路径与四份坏副本，G3 re-read abort 卸载，G4 TypeError 固定文案，G5 F1 的 onOpenNovel 自证。 |
| r2-backend-tests | `backend/tests/test_novel_chat_feedback.py` | §4.7 G6–G7 | 完成：131 passed；G6 B1 增加 stale 反例与 `status<>'done'` 坏副本，G7 B6 增加 running / 删书两态与判断顺序坏副本。 |

无返修派发。主代理只做了拆分、派发、汇总、白名单检查、§5/R2 验收与本报告。

## 1. 修改了哪些文件

R2 实际变更只有：

- `backend/tests/test_novel_chat_feedback.py`（G6、G7）
- `backend/tests/test_novel_chat_feedback_frontend.py`（G1–G5）
- `docs/tasks/2026-11-12-novel-feedback/impl/report-r2.md`（本文件）

与 R1 工作副本逐文件比较，R2 只差这两个测试文件；另出现的 `02-spec.md`（v1.5）、`06-fix-r2.md`、`impl/report-r1.md` 是派单方在本轮前后放入的任务文件，不是本代理改动。保护文件哈希：`impl/report.md` = `3db982ec…`（未变）、`test_desk_polish_frontend.py` = `47e529fd…`（未变）；`impl/report-r1.md` 修改时间为 R1 的 05:21，早于本轮开始。

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
?? docs/tasks/2026-11-12-novel-feedback/06-fix-r2.md
?? docs/tasks/2026-11-12-novel-feedback/impl/report-r1.md
?? docs/tasks/2026-11-12-novel-feedback/impl/report-r2.md
?? docs/tasks/2026-11-12-novel-feedback/impl/report.md
?? frontend/components/NovelFeedbackCard.tsx
?? frontend/lib/novelFeedback.ts
```

`backend/tests` 专项仍只有三个 `??` 与授权文件的 ` M`：

```
 M backend/tests/test_studio_sources_readonly_integration.py
?? backend/tests/test_desk_polish_frontend.py
?? backend/tests/test_novel_chat_feedback.py
?? backend/tests/test_novel_chat_feedback_frontend.py
```

授权文件 diff 仍恰 2 个 hunk，本轮未改。

## 2. 实现了哪些功能（测试）

- **G1**：把 F7(c) 的重新读取夹具改成「只比卡片原视图多 `redo_started_at`」：`book=make_book(redo_pending=False, awaiting_chapter=PLAN_CHAPTER)`。断言标签「已发起重新定稿」、说明逐字包含「已经带着这些要求重新定稿过第 2 章细纲。新细纲在书斋里等你确认。」，确认框与 POST 均不调用；原等第 3 章夹具删掉。新增删 `!view.redo_started_at` 的坏副本自检。
- **G2**：F7(b) 的重新读取视图保留卡上 `next_chapters`；F7(b)/(c) 提前结束后再点「交给编辑部」，按钮可用且 `sendNovelFeedbackNote` 恰 1 次；F7(d) 后再点重定稿使 GET 累计 2 次；取消确认框后再点使 GET 与 confirm 各累计 2 次。四份坏副本分别删除不可用分支的两句、只删 `busyRef`、删失败分支 `busyRef`、删取消分支 `busyRef`。
- **G3**：新增 `deferred-abort` GET 桩，在重新读取途中卸载后 GET signal 被 abort、无 confirm/POST、卸载后 state setter 为 0；自检删除 re-read catch 的 abort 判断。
- **G4**：F7(d) 加 `TypeError("Failed to fetch")`，断言 alert 逐字「请求未完成，请稍后重试。」；自检把失败文案改成 `error.message`。
- **G5**：F1 (a)(b) 两条 HTML 断言含「在书斋打开」，证明 `onOpenNovel` 确实传入。
- **G6**：B1 在「done 不算」旁加 `stale` 段；stale 章 meeting 含 N1 与回应时 `planned_*` 全 None。坏副本把进行中状态查询改成 `status<>'done'` 时必须变红。
- **G7**：B6 增加书 `running` 与卡片 `novel_id=NULL` 两态，均 409「这张卡没有重新定稿的要求」，`redo_started_at` 仍 NULL、`start_novel` 桩未调用、章节行不变。坏副本把 `plan_chapter is None` 从第一条判断删掉并在 `_begin_redo` 前单独判断时，running 报「第 None 章…」、删书报「这本书已经删除」，自检变红。

## 3. 与 G1–G7 逐条对应

| 条目 | 实现 | 自检 |
|---|---|---|
| G1 | `redo_started_view()` 用卡上同一章（PLAN_CHAPTER）；F7(c) 说明与标签逐字断言；旧第 3 章数据删除。 | 删 `redoAvailable` 的 `!view.redo_started_at` → G1 红；既有 F7 自检复用新夹具仍红。 |
| G2 | F7(b) 保留 `next_chapters` 并断言两视图文字一致；提前结束后再点 note；失败后再点 redo；取消后再点 redo。 | 四份坏副本分别红：按钮 disabled、note 调用数、GET 累计数、confirm 累计数。 |
| G3 | `deferred-abort` 桩 + 卸载途中 re-read；断言 signal.aborted、无 confirm/POST、setter 0。 | 删 re-read catch 的 `if (signal?.aborted) return;` → setter >0 红。 |
| G4 | `new TypeError("Failed to fetch")`；alert 逐字固定句。 | 坏副本显示 `Failed to fetch` → 断言红。 |
| G5 | F1 (a)(b) 传 `__withOpenNovel` 且断言「在书斋打开」。 | 参数化与 F1 自检均覆盖。 |
| G6 | stale 反例与原本 done 反例并列；三种进行中状态正样本保留。 | `status<>'done'` 坏副本使 stale 的 `planned_chapter` 从 None 变 2 → 红。 |
| G7 | running 书、`novel_id=NULL` 卡各返回同一 409；无副作用。 | 把 `plan_chapter` 判断挪后，running / 删书两种坏副本都红。 |

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

退出码 `0`；25 条与基线一致，新增测试不产生 warning。

### §5.3 `npm run build`

```text
✓ Generating static pages using 17 workers (18/18) in 179ms
✓ Finalizing page optimization
```

退出码 `0`。

### §5.4 后端全量

```bash
cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local \
  .venv/bin/python -m pytest -q -p no:cacheprovider
```

原始尾行：

```text
8264 passed, 37 warnings in 372.16s (0:06:12)
```

退出码 `0`；0 failed、0 skipped。`8264 = 8011 + 253`。

### §5.5 三个新文件与无 node_modules 副本

有 node_modules：

```text
253 passed, 35 warnings in 32.37s
```

收集数：`131 + 113 + 9 = 253`。

无 node_modules 副本按规格 rsync 后：

```text
SKIPPED [93] tests/test_novel_chat_feedback_frontend.py:63: frontend dependencies unavailable: typescript, react, react-dom/server
SKIPPED [9] tests/test_desk_views_frontend.py:36: frontend dependencies unavailable: typescript, react, react-dom/server
151 passed, 102 skipped, 35 warnings in 6.15s
```

退出码 `0`；`93 + 9 = 102`。前端 113 条中 20 条源码断言、93 条起 node；案头 9 条全部起 node。副本确认无 `frontend/node_modules`，`backend/.venv` 保留。

### §5.6 改动集合

见 §1 的完整 `git status`；`backend/tests` 只有三个 `??` 与授权文件 ` M`，授权 diff 仍 2 hunk；`git diff --check` 退出码 `0`。

### §5.7 既有文件列表

规格列出的 23 个文件加授权文件合跑：

```text
573 passed, 37 warnings in 63.96s (0:01:03)
```

退出码 `0`；授权文件单独跑 `5 passed`。

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
30 passed, 101 deselected in 0.78s
```

退出码 `0`。

### R2 自检摘要

- 后端 G6/G7 自检：`2 passed, 129 deselected in 0.99s`。
  - G6 坏副本视图实际 `planned_chapter=2, planned_adopted=True, planned_response="已采纳"`，真实实现全 None，自检红。
  - G7 坏副本 running 实际 `(409, '第 None 章细纲已经不在等你确认了')`；删书实际 `(409, '这本书已经删除')`，自检红；原 awaiting_plan 场景仍被最后一道判断拦住。
- 前端 self_check 子集：`17 passed, 96 deselected in 9.04s`。实际变红摘要包括：
  - `G1 missing redo_started guard bad copy: assert [{'title': ...}] == []`
  - `G2 unavailable both-reset bad copy: assert True is False`
  - `G2 unavailable busyRef-only bad copy: {'note': 0} != {'note': 1}`
  - `G2 reread-failure busyRef-only bad copy: {'get': 1} != {'get': 2}`
  - `G2 confirm-cancel busyRef-only bad copy: {'get': 1} != {'get': 2}`
  - `G3 reread abort guard bad copy: 卸载后仍调用了 2 次 state setter`
  - `G4 reread error message bad copy: ['Failed to fetch'] != ['请求未完成，请稍后重试。']`

## 5. 未完成或需要人工确认

- 未发现 §4.7 自相矛盾或照做会违反其他规格条款的情况。
- 本轮只改测试，没有产品代码、文档或规格改动；无依赖安装、无 `.env` 读取、无 Git 写操作。
- `impl/report.md` 与 `impl/report-r1.md` 未改；`test_desk_polish_frontend.py` 哈希未变。
- R2 测试总数从 245 增至 253（`+8`：后端 `+2`、前端 `+6`）；完整全量因此从 8256 到 8264。
- 无未解决的测试失败。
