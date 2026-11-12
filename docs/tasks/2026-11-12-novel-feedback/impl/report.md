# 实现报告：修改意见卡（规格 v1.3）

分支 `feat/novel-feedback`，基线 `7a17f64`。本报告由主代理汇总；验收命令均在当前 worktree 实跑。

## 拆分与执行

### 第一轮：实现与文档（10 个 agent，`parallel()` 并行）

| agent | 负责文件 | 规格 | 结果 |
|---|---|---|---|
| db | `backend/database.py`、`backend/agent_store.py` | §4.2 T1 | 完成：建表/补列、消息归属与 INSERT、清理、会话 SELECT。针对性 70 + 70 + 38 条既有测试通过。 |
| feedback | `backend/novel/feedback.py`（新） | §4.2 T2 | 完成：三段校验、`create_feedback`、`awaiting_is_final`。临时自测通过；并行中间态下曾看到测试锁未更新导致的失败，最终不在改动归属内。 |
| service-router | `backend/novel/service.py`、`backend/routers/novel.py` | §4.2 T3 | 完成：`_insert_pending_note`、`_begin_redo`、`feedback_view`、交留言、重新定稿、删书置 NULL、三个路由。报告 199 + 1727 + 142 条针对性测试通过。 |
| chat | `backend/studio/sources.py`、`backend/services/claude_agent.py`、`backend/services/chat_service.py` | §4.2 T4 | 完成：独立开关、工具常量、按请求追加、每轮标志、执行分支、回灌文案、状态透传。报告 127/177/327/242 条针对性测试通过。 |
| frontend-lib | `frontend/lib/novelFeedback.ts`（新） | §4.3 T5 | 完成：三个请求函数、视图类型、路径编码、signal 透传。临时 Node 桩验证三条 URL/method 正确。 |
| frontend-card | `frontend/components/NovelFeedbackCard.tsx`（新） | §4.3 T6 | 完成：取数、三节、十/七种状态、确认框、busy/abort/失败重拉、底部入口。`tsc` 0、lint 25 既有 warning、build 0；相关测试 225 + 33 条通过。 |
| frontend-wiring | `frontend/components/ChatBubble.tsx`、`frontend/lib/useConversations.ts`、`frontend/app/page.tsx` | §4.3 T7 | 完成：分支分发、历史重建、两处流式 card 透传；BOM 保留为 `efbbbf`。改后 `tsc` 0。 |
| desk | 三份 desk 文件、`backend/tests/test_desk_polish_frontend.py`（新） | §8 | 完成 O1/O2/O3；新测试 9 条、案头相关 109 + 42 条通过。 |
| docs-a | `CLAUDE.md`、`README.md` | §4.4 | 完成例外清单、CLAUDE 技术段、README 作者段；文档/语言测试 36 条通过。 |
| docs-b | `PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example` | §4.4 | 完成五处例外清单、ARCHITECTURE 多处陈述、DEPLOYMENT 三开关、PLAN 新节、env.example 配置；47 条文档测试通过。 |

### 第二轮：测试编写（2 个 agent，`parallel()` 并行）

| agent | 负责文件 | 规格 | 结果 |
|---|---|---|---|
| test-backend | `backend/tests/test_novel_chat_feedback.py`（新）、`backend/tests/test_studio_sources_readonly_integration.py`（仅两处） | §4.5 后端 1–12 | 完成：110 条用例；授权文件 diff 恰 2 hunk；新测试 + 该既有文件共 115 条通过。 |
| test-frontend | `backend/tests/test_novel_chat_feedback_frontend.py`（新） | §4.5 前端 1–8 | 完成：84 条用例；包含 SSR、交互、源码约束、路由 AST、请求路径及 15 条坏副本自检；84 条通过。 |

### 返修轮

无。第一轮/第二轮完成后主代理验收全绿，未再派返修 agent。

## 1. 修改了哪些文件

改动集合与 §4.1 白名单逐条一致：后端 8 个源文件、6 份文档、3 个新测试与 1 个既有测试的两处；前端 2 个新文件和 6 个既有文件（其中 3 个 desk 文件）；三个新测试中包含 §8 的案头测试。`docs/tasks/.../impl/report.md` 是规格授权的新增任务文档。

`git status --porcelain --untracked-files=all` 原文：

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
?? docs/tasks/2026-11-12-novel-feedback/impl/report.md
?? frontend/components/NovelFeedbackCard.tsx
?? frontend/lib/novelFeedback.ts
```

逐条对应：

| 路径 | 状态 | 白名单/规格 |
|---|---|---|
| `backend/database.py` | M | §4.1；T1 |
| `backend/agent_store.py` | M | §4.1；T1 |
| `backend/novel/feedback.py` | ?? | §4.1 新文件；T2 |
| `backend/novel/service.py` | M | §4.1；T3 |
| `backend/routers/novel.py` | M | §4.1；T3 |
| `backend/studio/sources.py` | M | §4.1；T4 |
| `backend/services/claude_agent.py` | M | §4.1；T4 |
| `backend/services/chat_service.py` | M | §4.1；T4 |
| `CLAUDE.md` | M | §4.1/§4.4 |
| `README.md` | M | §4.1/§4.4 |
| `PLAN.md` | M | §4.1/§4.4 |
| `docs/ARCHITECTURE.md` | M | §4.1/§4.4 |
| `docs/DEPLOYMENT.md` | M | §4.1/§4.4 |
| `backend/.env.example` | M | §4.1/§4.4 |
| `backend/tests/test_novel_chat_feedback.py` | ?? | §4.1/§4.5 新测试 |
| `backend/tests/test_novel_chat_feedback_frontend.py` | ?? | §4.1/§4.5 新测试 |
| `backend/tests/test_desk_polish_frontend.py` | ?? | §4.1/§4.5/§8 新测试 |
| `backend/tests/test_studio_sources_readonly_integration.py` | M | §4.5 仅授权两处 |
| `frontend/lib/novelFeedback.ts` | ?? | §4.1/§4.3 T5 |
| `frontend/components/NovelFeedbackCard.tsx` | ?? | §4.1/§4.3 T6 |
| `frontend/components/ChatBubble.tsx` | M | §4.1/§4.3 T7 |
| `frontend/lib/useConversations.ts` | M | §4.1/§4.3 T7 |
| `frontend/app/page.tsx` | M | §4.1/§4.3 T7；BOM 保留 |
| `frontend/components/desk/DeskDialogs.tsx` | M | §4.1/§8 O1 |
| `frontend/components/desk/DeskChaptersView.tsx` | M | §4.1/§8 O2 |
| `frontend/components/desk/DeskEpisodesView.tsx` | M | §4.1/§8 O3 |
| `docs/tasks/2026-11-12-novel-feedback/impl/report.md` | ?? | §4.1 任务文档 |
| `docs/tasks/2026-11-12-novel-feedback/01-brief.md` | ?? | 派单前已存在，非本次修改 |
| `docs/tasks/2026-11-12-novel-feedback/02-spec.md` | ?? | 派单前已存在，非本次修改 |
| `docs/tasks/2026-11-12-novel-feedback/03-dispatch.md` | ?? | 派单前已存在，非本次修改 |

测试目录专项：

```
$ git status --porcelain --untracked-files=all -- backend/tests
 M backend/tests/test_studio_sources_readonly_integration.py
?? backend/tests/test_desk_polish_frontend.py
?? backend/tests/test_novel_chat_feedback.py
?? backend/tests/test_novel_chat_feedback_frontend.py
```

授权既有测试 diff 原文（恰 2 个 hunk）：

```diff
@@ -29 +29 @@ def novel_table_bytes():
-                               "novel_drafts", "novel_notes", "novel_steps"}
+                               "novel_drafts", "novel_feedback", "novel_notes", "novel_steps"}
@@ -199,0 +200,3 @@ def test_chat_novel_access_cannot_import_or_call_writer_functions():
+                    elif node.module == "novel.feedback":
+                        assert {alias.name for alias in node.names} <= {
+                            "validate_feedback_args", "create_feedback"}, path
```

`git diff -U0 HEAD -- backend/tests/test_studio_sources_readonly_integration.py | grep -c '^@@'` = `2`。

## 2. 实现了哪些功能

- 新增 `novel_feedback` 表与 `messages.novel_feedback_id` 可空列；`save_message` 校验卡片归属后落库；清空历史、删号、删会话、删书均按规格处理。
- Claude 智能体新增免费工具 `draft_novel_feedback`，由独立开关 `FIONA_NOVEL_CHAT_FEEDBACK` 控制；三类意见有长度/类型/书状态校验，格式错误一次报全；每轮最多一张，成功后写入卡片行、SSE 卡片、assistant 消息和本轮回灌文本。
- 新增只读书斋视图和两个作者动作接口：`GET /novels/feedback/{id}`、`POST /novels/feedback/{id}/note`、`POST /novels/feedback/{id}/redo`；交留言与重新定稿分别原子、幂等，重新定稿在一个写事务里核对章号和逐章确认。
- 新前端卡完整显示三类意见，按书的当前状态给出进展/费用/失败/暂停/最后一章等文案；确认框说明费用后才发起重新定稿；支持重试、abort、busy 防重入、刷新后按 `novel_feedback_id` 重建。
- 同步六份文档；完成 §8 案头 O1/O2/O3 三处小修。

## 3. 与规格任务清单的逐项对应

### T1 表与落库

- `NOVEL_FEEDBACK_DDL` / `NOVEL_FEEDBACK_INDEX` 位于 `NOVEL_DRAFTS_INDEX` 后；`init_db` 无条件执行，`messages.novel_feedback_id` 用 `_safe_migrate` 补列。
- `save_message` 新参数在写歌核对之后、书斋草稿注释之前，按 owner + conversation 校验，异常/不命中存 NULL；INSERT 三处同步。
- 清空历史、删号同事务 `DELETE FROM novel_feedback`；`agent_store` 读取列与删会话清理同步。
- 覆盖测试：T1 + 清理 + 老库补列 + 归属坏副本。

### T2 `novel/feedback.py`

- 常量、三段校验顺序、去重、字数、bool 排除、`written` 顺序和章名、`awaiting_chapter`/`plan_chapter`、`automation`、`max_chapters` 均按规格。
- `create_feedback` 同连接插入并计算 `awaiting_is_final`；模块顶层不 import `novel.service`。
- 覆盖测试：T2.2 每行、错误组合、通过返回值、建卡往返。

### T3 书斋侧

- `note()` 改用 `_insert_pending_note`，对外行为未变；`redo_plan()` 改用 `_begin_redo`，对外行为未变。
- `feedback_view` 键集合、`note` 的 delivered/pending/planned 计算、`redo_cost` 三态、`awaiting_is_final`、`plan_row_status`、`redo_pending` 按规格。
- `send_feedback_note` 与 `redo_feedback_plan` 原子、幂等、拒绝条件、提交后启动；`delete()` 置 NULL。
- 三个路由使用 `workshop_user`，不读新开关；新路由位于动态 `/{novel_id}` 前。
- 覆盖测试：视图全部键、三种 redo_cost、planned_* 与损坏 meeting、HTTP 交留言幂等/并发/上限/拒绝、重新定稿成功/二次/并发/五种拒绝/HTTP 后台失败、redo_plan 回归。

### T4 Claude 工具

- `NOVEL_FEEDBACK_TOOL` 紧跟 `NOVEL_DRAFT_TOOL`；`client_tools_for_turn` 独立 import/条件，保持 `novel_create_enabled` 锚点行。
- 每轮标志、执行分支、每轮一张限制、`_resolve`/`detail`/校验/建卡/卡片 dict/SSE/状态/回灌六段均按规格。
- `ChatState.novel_feedback_id` 与 `_save_response` 透传。
- 覆盖测试：开关矩阵有序名字与对象同一性、五个 `(method,crisis)` 组、成功路径七个书状态分支、每轮两次、找书失败、落库与归属。

### T5/T6/T7 前端

- T5 三个请求函数与类型已实现。
- T6 单组件，取数三态、三节、十种细纲状态、七种留言状态、已写章节、底部提示、确认框、错误处理、busy/abort 全部实现；源码约束与交互测试覆盖。
- T7 ChatCard 分支、`toMessages` 顺序、两处流式 card 透传、BOM 与哈希锁保持。

### §4.4 文档

- 六份文档：例外清单加入修改意见卡与三列；CLAUDE 技术段与 README 作者段补齐开关、工具、接口、费用、局限；PLAN 新节、ARCHITECTURE 数据流与多处历史陈述、DEPLOYMENT 三开关、`.env.example` 开关。
- `test_claude_agent_docs.py`、`test_component_language.py` 通过。

### §4.5 测试与 §8

- 后端新测试 110 条、前端新测试 84 条、案头新测试 9 条，合计 203 条；HEAD 可收集、新功能类 `_require_feedback()` 守卫、七条后端坏副本与十五条前端坏副本自检。
- 既有测试仅改授权文件两处，恰 2 hunk。
- §8 O1/O2/O3 与坏副本自检完成。

## 4. 测试结果（§5 逐条）

### 4.1 `npx tsc --noEmit`

命令：

```bash
cd frontend && npx tsc --noEmit
```

结果：无输出，退出码 `0`。

### 4.2 `npm run lint`

命令：

```bash
cd frontend && npm run lint
```

原始尾部：

```text
✖ 25 problems (0 errors, 25 warnings)
```

退出码 `0`；25 条与基线一致，均为既有 `app/page.tsx`、`app/plaza/page.tsx` warning，新文件 0 warning。

### 4.3 `npm run build`

命令：

```bash
cd frontend && npm run build
```

原始尾部：

```text
✓ Compiled successfully in 303ms
✓ Generating static pages using 17 workers (18/18) in 176ms
...
ƒ Proxy (Middleware)
```

退出码 `0`。

### 4.4 后端全量

命令：

```bash
cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local \
  .venv/bin/python -m pytest -q -p no:cacheprovider
```

原始尾行：

```text
8214 passed, 37 warnings in 386.27s (0:06:26)
```

退出码 `0`；0 failed、0 skipped。`8214 = 8011 + 203`，与三个新文件实收集数一致。

### 4.5 三个新文件与无 node_modules 副本

三个新文件（有 node_modules）：

```text
203 passed, 35 warnings in 20.60s
```

无 node_modules 副本用规格命令：

```bash
rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' <worktree>/ <副本>/
cd <副本>/backend && .venv/bin/python -m pytest -q -p no:cacheprovider -rsf \
  tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py tests/test_desk_polish_frontend.py
```

实跑输出：

```text
SKIPPED [64] tests/test_novel_chat_feedback_frontend.py:63: frontend dependencies unavailable: typescript, react, react-dom/server
SKIPPED [9] tests/test_desk_views_frontend.py:36: frontend dependencies unavailable: typescript, react, react-dom/server
130 passed, 73 skipped, 35 warnings in 6.20s
```

退出码 `0`。`64 + 9 = 73`，等于起 node 的用例数：前端新测试 84 条中 64 条起 node、20 条源码断言；案头新测试 9 条均起 node。无 node 副本内确认 `frontend/node_modules` 不存在，`backend/.venv` 保留。

### 4.6 改动集合与测试 diff

见 §1 的 `git status` 原文；`git status -- backend/tests` 仅三新文件 + 一个 M，授权 diff 恰 2 个 hunk。`git diff --check` 退出码 `0`。

### 4.7 §5 第 7 条既有文件列表

命令为规格列出的 24 个文件，结果：

```text
573 passed, 37 warnings in 66.07s (0:01:06)
```

退出码 `0`。

### 4.8 §5 第 8 条计数

```text
grep -c "ALTER TABLE messages ADD COLUMN novel_feedback_id" backend/database.py
1
grep -c "FIONA_NOVEL_CHAT_FEEDBACK" backend/studio/sources.py backend/.env.example CLAUDE.md
backend/studio/sources.py:1
backend/.env.example:1
CLAUDE.md:1
grep -c "draft_novel_feedback" backend/services/claude_agent.py
2
head -c 3 frontend/app/page.tsx | xxd -p
efbbbf
```

`git diff HEAD --stat -- frontend/components/desk` 只列 `DeskDialogs.tsx`、`DeskChaptersView.tsx`、`DeskEpisodesView.tsx` 三份；`git diff HEAD --stat -- frontend/lib/desk.ts frontend/components/novel frontend/lib/novels.ts frontend/components/NovelDraftCard.tsx` 为空。

### 4.9 开关为 0 时请求不变

```text
30 passed, 80 deselected in 1.14s
```

覆盖 `FIONA_NOVEL_CHAT_CREATE ∈ {未设, "1"}` × `FIONA_NOVEL_CHAT_FEEDBACK ∈ {未设, "0", "true"}` 与五组 `(method, crisis)`，以及 `FIONA_NOVEL_CHAT=0` / 白名单外。写死期望见测试文件；退出码 `0`。

## 5. 未完成或需人工确认

- **规格与源码矛盾：无。** 实施中唯一看到的临时失败来自并行中间态（授权测试锁尚未更新、`NovelFeedbackCard` 尚未落盘导致 `tsc` 缺模块），最终状态均复跑通过。
- **`max_chapters` 缺 `target` 的取舍**：T3.2 同时要求“照 `summary()`”和“解析失败为 None”。实现为：`config_json` 非 dict / 整体解析失败 → `None`；config 是 dict 但缺 `target` → 按 `summary()` 回落 `Target().max_chapters`（70）。这是对两条要求的兼容解释。
- **`written_json` 容错**：按规格只把 JSON 解析失败（或不是 list）当 `[]`；没有对列表内每个对象再做一次数据库层 schema 清洗，因为创建接口已保证形状。若人工改库，前端按“损坏记录”处理，不在本批增加新约束。
- **`03-dispatch.md`**：派单前已存在且未修改；§5.6 文案只点名 01/02 为例外，故在本报告中单独说明，不以删除或改写处理。
- **白名单外同类陈述**：`docs/tasks/2026-11-02-chat-create-novel/` 下的旧任务文档仍保留“写歌卡与书斋草稿卡例外”等历史句子；`docs/tasks/2026-11-12-novel-feedback/02-spec.md` 也有规格示例原文。按 §4.4.2 只搜索六份白名单文档、白名单外只列不改，故均未动。
- **六份文档内未改的局部写歌/健康检查陈述**：`CLAUDE.md:114`、`README.md:160-162`、`PLAN.md:491`、`docs/ARCHITECTURE.md:303`、`docs/DEPLOYMENT.md:60-98/528/584/905/926` 仍只提写歌表与 `song_project_id`；它们是写歌专属或 `/health` 检查范围的局部陈述，不是“哪些卡片落库 / 刷新重建”的例外清单，未在本批扩展。`PLAN.md:23` 的“写歌细节见文末”同样保留原措辞。
- **未做的人工验证**（派单方保留）：无 node_modules 副本已在本机实跑；派单方仍可复跑自己的 HEAD 对照、变异测试和真实界面走查。本次未启动 8010/3000，也未读 `.env` 或真实库。
