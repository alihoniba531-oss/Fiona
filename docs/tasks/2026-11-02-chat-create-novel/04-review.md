# 04 复核：聊天建书（Claude 智能体把聊天里定下的小说设定送进书斋）

- 复核方：独立复核，与实现方、规格作者没有任何对话上下文。
- 依据：`docs/tasks/2026-11-02-chat-create-novel/02-spec.md` v1.1（唯一依据）。`01-investigation.md` 只当线索用。`03-report.md`、`impl/*.md`、`05-fix-r1.md` 只当线索看，下面每个结论都由本轮亲自重跑得到。
- 对象：基线 `0ca95af` + 工作区改动。
- 开工核对：`git diff` 与 `.review/diff.patch` 逐字节相同（`cmp` 无输出，打印 `DIFF_SAME`）。按「`git diff` + `.review/untracked.txt` 各文件内容」计算的 sha256 为 `8afb5e7e…0d46b`，与 `.review/snapshot.sha256` 一致。未跟踪文件共 31 个：清单里的 16 个，加上派单方事后放入的 `verify/claude/` 下 15 个（README、4 个脚本、`results/` 下 10 个文件）。后者不属于执行方交付。
- 收尾核对：做完全部变异并逐一还原后，再算一次快照哈希，仍为 `8afb5e7e…0d46b`；`git diff` 仍与 `.review/diff.patch` 逐字节相同。

## 1. 结论：**不通过**

后端主体（不扣费、不建书、开关与锁、归属与隔离、四个清理钩子、`create` 兼容）全部实测正确，§5 第 1–7 条全过。下面两项必须修复：

1. **`frontend/app/page.tsx:2971` 用一行 JSX 注释保住了既有测试锁 `backend/tests/test_novel_p2_frontend.py:40`，让这条既有断言变成恒真**。规格 T5.1 要求 iframe 的 `src` 改用状态，这与既有锁 `'src="/novels?embed=1"' in drawer` 冲突，规格 §2.3 没有列出这条锁。按规格 §6，这属于「规格与源码事实矛盾」，应停下来上报。执行方没有上报（`03-report.md` §5「冲突」和 §7「需人工确认」都没写，只在 `impl/C.md` 里提了一句），而是把字面量塞进注释，绕过了这条锁。这和 R1 已经否决的「用 `importlib` 绕 AST 锁」是同一类做法。实测：删掉注释后既有用例变红（C1）；保留注释、把 iframe 初值改成别的路径，既有用例照样全绿（C2）。
2. **§4.5 点名的「`onOpenNovel` 透传」只测了一半**：`ChatBubble → ChatCard` 这一段没有任何断言。去掉 `ChatBubble.tsx:404-405` 两处 `onOpenNovel={onOpenNovel}` 后，「去书斋建书」「打开」按钮从卡片上消失，主流程断掉。但 8 条新前端用例加上所有引用 `ChatBubble` / 书斋前端的既有用例（共 216 条）**全部仍绿**（F5、F5all）。

其余发现都不阻断，见 §5。

## 2. 验收标准逐条核验（规格 §5）

### 2.1 第 1 条：`npx tsc --noEmit`

```text
$ cd frontend && export npm_config_cache=/tmp/fiona-npm-cache && npx tsc --noEmit; echo "TSC_EXIT=$?"
TSC_EXIT=0
```

✅

### 2.2 第 2 条：`npm run lint`

```text
$ npm run lint
✖ 25 problems (0 errors, 25 warnings)
LINT_EXIT=0
```

25 条 warning 中，24 条在 `frontend/app/page.tsx`，都是旧的未使用变量、`handleSend` 依赖和 `<img>`；1 条在 `frontend/app/plaza/page.tsx:603`。新代码没有 warning。在 HEAD 副本上跑同一命令，同样是 `✖ 25 problems (0 errors, 25 warnings)`。✅

### 2.3 第 3 条：`npm run build`

```text
✓ Compiled successfully in 1404ms
✓ Generating static pages using 17 workers (18/18) in 221ms
ƒ  (Dynamic)  server-rendered on demand
BUILD_EXIT=0
```

✅

### 2.4 第 4 条：后端全量 pytest

```text
$ cd backend && env -u HTTP_PROXY … -u no_proxy .venv/bin/python -m pytest -p no:cacheprovider --collect-only -q | tail -1
7903 tests collected in 7.35s
$ … --collect-only -q tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py | tail -1
40 tests collected in 0.78s
$ … .venv/bin/python -m pytest -q -p no:cacheprovider -rs     # 后台任务
7903 passed, 35 warnings in 321.50s (0:05:21)
EXIT=0
```

0 failed，0 skipped（`-rs` 没有列出任何 skip）；7903 = 7863 + 40。✅

### 2.5 第 5 条：HEAD 对照

做法：`git archive HEAD | tar -x -C <mktemp 目录>`；只拷入两个新测试；`frontend/node_modules` 用 `cp -cR` 克隆；用工作区的 `backend/.venv/bin/python` 在 HEAD 副本的 `backend/` 下运行。

```text
$ … -m pytest -q -p no:cacheprovider -rfEs --tb=line tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py
40 failed, 33 warnings in 2.23s
FAILED lines: 40   ERROR lines: 0
$ … --junitxml=… ；逐条解析 <failure> 的首个 "E " 行
cases 40 skipped 0 errors 0
Counter({('assert', ()): 40})      # 40 条都是断言失败，没有其他异常类型
```

40 条全部 FAIL，都是 `AssertionError`（pytest 断言重写输出的 `assert …`）。没有 ImportError、ModuleNotFoundError、OperationalError、CalledProcessError，也没有 skip。前端渲染用例在 HEAD 上同样是断言失败，不是 skip。✅

### 2.6 第 6 条：计数

```text
$ grep -c "draft_novel" backend/services/claude_agent.py
3
$ grep -c 'ALTER TABLE messages ADD COLUMN novel_draft_id' backend/database.py
1
$ grep -c "FIONA_NOVEL_CHAT_CREATE" backend/studio/sources.py backend/.env.example CLAUDE.md
backend/studio/sources.py:1
backend/.env.example:1
CLAUDE.md:1
$ head -c 3 frontend/app/page.tsx | xxd
00000000: efbb bf
```

✅

### 2.7 第 7 条：既有测试零 diff 与定向回归

```text
$ git diff HEAD --stat -- backend/tests ':!backend/tests/test_novel_chat_create*' ':!backend/tests/test_studio_sources_readonly_integration.py'
（空）
$ git diff -U0 HEAD -- backend/tests/test_studio_sources_readonly_integration.py | grep -c '^@@'
2
@@ -29 +29 @@          集合加 "novel_drafts"（只加这一项）
@@ -195,2 +195,7 @@    novel.runner 只许 {"is_editing"}；novel.drafts 只许三个名字；其余 assert False
$ … tests/test_studio_sources_readonly_integration.py
5 passed, 33 warnings in 1.89s
$ … tests/test_novel_chat.py tests/test_song_agent_tools.py tests/test_claude_agent_runtime.py tests/test_claude_agent_docs.py tests/test_novel_p1_api.py tests/test_novel_v2_compat.py tests/test_novel_p21_frontend.py
184 passed, 35 warnings in 6.52s
$ … tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py
40 passed, 33 warnings in 3.40s
```

两个 hunk 与规格 §2.3 (a)(b) 逐字对应，原有的 `novel.runner` 只许 `is_editing` 语义保留。✅

（注：既有测试文件虽然零 diff，但 `test_novel_p2_frontend.py:40` 这条锁被源码里的注释变成了恒真，见 §4.1。）

### 2.8 第 8 条：走查脚本能否证明规格 §1 的流程（不由本方执行，只审脚本与结果）

`verify/claude/seed_ccn.py` + `walk_ccn.py`，结果 `results/walk.txt`：`== FAIL 0 / 20`。

**能证明的部分**：
- 刷新重建出来的草稿卡（标题、思路摘录、恰好 1 个「去书斋建书」按钮）。
- 点击后抽屉从 `aria-hidden=true` 变成 `false`，iframe 的 `src` 恰为 `/novels/new?embed=1&draft=<id>`。
- 向导第一步预填了思路，以及 40 / 60 / 2500 三个篇幅值。
- 三步提交前草稿未消费；提交后库里草稿的 `novel_id` 已填、`novels` 多 1 行，iframe 内跳到 `/novels/<id>?embed=1`。
- 刷新后卡片变「已建书《…》」并带「打开」，点「打开」后 iframe 的 `src` 恰为 `/novels/<id>?embed=1`。
- 390 宽手机视口没有横向溢出。

**证明不了的部分**：
1. **「聊天出草稿卡」没有走聊天流程**。卡片是 `seed_ccn.py` 直接调用 `create_draft` + `save_message(novel_draft_id=…)` 写进库里的，页面看到的是 `useConversations` 刷新重建出来的卡。规格 §5.8 允许的「假传输回放 `tool_use`」没有做，所以流式到达的卡片在浏览器里从没被验证过：`page.tsx:2159/2175` 两处 SSE 复制的 `draft_id`、实时渲染出来的按钮都没走到。这条链路目前只有一个字符串计数断言（`count == 2`）。
2. **「建书成功后卡片变成已建书」被刷新混在了一起**。脚本先 `page.reload()` 再检查。而实现里 `NovelDraftCard` 只在挂载时拉一次（这符合 T4.3 的写法），不刷新时聊天里的卡片仍是「去书斋建书」。规格 §1 说「建书成功后卡片变成「已建书…」」，§5.8 的顺序是「卡片变已建书 → 刷新页面卡片仍在」。这两种读法，走查都区分不了，见 §5.4。
3. **「开关为 0 时请求体与 HEAD 逐字节相同」不在走查脚本里**。本方用两种方法补做了，结果都相同，见 §2.10 (b)。
4. 没覆盖「在 iframe 里导航后再点同一张卡」的场景，见 §5.5。

### 2.9 规格对照（T1–T6、§4.4、白名单）

| 规格 | 落点 | 核验 |
|---|---|---|
| T1.1 表 / 索引 / 列 | `database.py:71-85` DDL 与规格逐列一致；`init_db` 在 `NOVEL_TABLES_DDL` 之后**无条件**建表 + 建索引；`ALTER … novel_draft_id` 紧跟在 `song_project_id` 那行之后；没有新增迁移版本 | ✅（`test_init_db_creates_draft_table_without_switch` 在开关未设时断言表和索引都存在） |
| T1.2 drafts API | `novel/drafts.py` 的 `create_draft / get_draft / count_open_drafts / consume_draft`，签名与规格一致；`consume_draft` 用调用方连接，`WHERE id=? AND owner_username=? AND novel_id IS NULL`，按 `rowcount` 判断 | ✅ |
| T1.3 `save_message` 归属 | `database.py:585-597`，与写歌同写法：按 id + owner + conversation 核对，不属于就存 NULL，异常也存 NULL | ✅（B4 / B4b 变异都红） |
| T1.4 删号 / 清空 / 删会话 | `delete_account_data:988`、`clear_message_history:509`、`agent_store.delete_conversation:374-377`，都在各自的 `BEGIN IMMEDIATE` 连接内、`commit` 之前，紧挨写歌清理 | ✅（B9 / B10 / B11 变异都红；同一事务由读码确认） |
| T1.5 删书复位 | `service.delete:781`，与删 `novels` 在同一个 `BEGIN IMMEDIATE` 里 | ✅（B8 变异红） |
| T2.1 `CreateNovel.draft_id` / 事务内消费 / 422 回滚 / config 排除 | `service.py:72,213,228-230`；先插书再消费，失败时 `rollback` + `fail(…,422)`，不会走到 `start_novel` | ✅（B5 / B6 / B6b / B7 变异都红） |
| T2.2 `GET /novels/drafts/{id}` | `routers/novel.py:46-51`，`workshop_user` 门控；路由排在 `/{novel_id}` 之前，不冲突；非本人 404 | ✅（B15 变异红） |
| T2.3 不带 `draft_id` 与 HEAD 一致 | 见 §2.10 (c)：4 种请求体在 HEAD 与新代码上逐字节相同 | ✅ |
| T3.1 `NOVEL_DRAFT_TOOL` | 名字、描述、5 个属性（含 `maxLength` / `minimum` / `maximum` / `description`）、`required` 与规格逐字一致 | ✅ |
| T3.2 追加条件与位置 | 在小说分支里，`start_film` 之后、写歌之前；`novel_create_enabled` 紧挨 `novel_chat_enabled` | ✅（见 §2.10 (a)） |
| T3.3 执行分支 | 参数非法时返回文本并计 `agent_tool_errors`；每轮第二次在参数校验之前直接回固定文本、不计错误；`>= 50` 拒绝；成功后卡片形状、`［卡片：…］`、`delivered`、`state.novel_draft_id`、回灌两行，都与规格一致；分支不碰 `novels`、`start_novel`、计费或每日上限；只有本轮实际提供的工具才会执行（`claude_agent.py` 的 `client_names` 过滤） | ✅ |
| T3.4 `ChatState.novel_draft_id` → `save_message` | `chat_service.py:775,978` | ✅（B14 变异红） |
| T3.5 镜子 / 危机 | 沿用 `novel_intents_enabled` 的危机早退 | ✅（B17 变异红） |
| T4.1 `toMessages` | 写歌卡与草稿卡同时存在时两张都生成 | ✅（F1 / F1b 变异都红） |
| T4.2 `ChatCard` 分支与透传 | 分支 ✅；`ChatBubble → ChatCard` 透传代码正确，但**没有测试**（§4.2） | ⚠️ |
| T4.3 `NovelDraftCard` | 加载 / 草稿 / 已建书 / 404·403 → 「草稿已不存在」且无按钮；另有「草稿暂时读不到」；样式类与 `studio_project` 卡一致，只用 `font-medium`，没有新令牌 | ✅（状态分支测试覆盖弱，见 §5.2） |
| T5 抽屉导航 | `novelFrameSrc` 初值 `/novels?embed=1`；`openNovelAt` 的两条正则与规格逐字一致，通过时 `setNovelFrameSrc` + `setDrawer("novel")`；两处 SSE 复制都补了 `draft_id`；`onOpenNovel={openNovelAt}` 沿 `onCompose` 那条链传下去（页面上只有这一处 `ChatBubble`）；没动抽屉外壳和 postMessage | ✅，但 `:2971` 加了注释，见 §4.1 |
| T6 向导 | 读取 `draft` 并用 36 位形状校验；`load` 里用 `allSettled` 同时拉草稿；只有 `novel_id` 为空时才预填并记 `draftId`；已消费时显示「这份草稿已建成《…》」+ 链接；404 / 403 显示「草稿不存在」；提交带 `draft_id`；**估算请求不带**（`NovelWizard.tsx:141` 只展开 `estimateInput`）；没加装饰标签 | ✅（预填条件和估算不带都没有测试，见 §5.2） |
| §4.4 文档 | `.env.example:209-210`；`CLAUDE.md:30,196`；`README.md:142,361`；`ARCHITECTURE.md:21,412`；`DEPLOYMENT.md:257`；`PLAN.md:23`；六份文档都保留了「卡片不落库」子串，`test_claude_agent_docs.py` 绿 | ✅（顺带可以更新的几处见 §5.7） |
| 白名单 | 已跟踪的 19 个改动文件都在 §4.1 白名单里；执行方新增的未跟踪文件（`drafts.py`、两个新测试、`NovelDraftCard.tsx`、`03-report.md`、`impl/*.md`）都在白名单里；`package.json` / 依赖未动；`CLAUDE_CLIENT_TOOLS` 常量块未动；`git diff --check` 退出码 0 | ✅ |

### 2.10 重点挑刺的补充实测

**(a) 开关与锁：`client_tools_for_turn` 的全矩阵对比 HEAD。** 在 HEAD 副本和工作区各跑同一个脚本，矩阵为：`FIONA_NOVEL_CHAT` ∈ {0,1} × 用户 ∈ {白名单, 非白名单} × `auth_method` ∈ {None, dev, jwt} × 危机 ∈ {None, possible, high} × 写歌 ∈ {0,1} × `FIONA_NOVEL_CHAT_CREATE` ∈ {0, 未设, "true", 1}。逐例比较 `json.dumps(tools)` 的字节和 `tools is CLAUDE_CLIENT_TOOLS`：

```text
switch 0/unset/true cases identical to HEAD (bytes+identity): 216 differ: 0 []
switch=1 cases correct: 72 (of which expect draft: 6 ) bad: []
nc=1|u=agent-user|m=jwt|c=None|song=1|create=1 [... 'list_novels', 'read_novel', 'start_film', 'draft_novel', 'song_save_brief', ...]
```

开关为 0 / 未设 / `"true"` 时，216 例与 HEAD 逐字节相同，对象同一性也相同。开关为 1 时，只有「小说聊天开 + 白名单 + 非危机」这 6 例多出 `draft_novel`，且只多这一个，位置在 `start_film` 之后、写歌之前，其余 66 例与 HEAD 相同（含危机轮和写歌 9 工具的情形）。`test_novel_chat.py` 的集合锁、`test_song_agent_tools.py` 的 5 / 9 锁、`test_claude_agent_runtime.py` 的 5 工具锁都在 §2.7 的 184 passed 里。

**(b) 开关为 0 时请求体与 HEAD 相同（补走查第 8 条的最后一句）。** 用 `test_claude_agent_runtime.harness` 写了一条临时用例，分别放进 HEAD 副本和工作区运行，跑完立即删除，工作区没有残留。参数为 `FIONA_NOVEL_CHAT` ∈ {0,1} × `FIONA_NOVEL_CHAT_CREATE` ∈ {0, 未设, "true"} × `auth_method` ∈ {None, jwt}，共 12 例。逐例比较 `messages + tools + 对象同一性 + SSE 事件 + 落库调用` 序列化后的结果：`12 12 identical: 12 diff: []`。

**(c) 不扣费、不建书；`create` 不带 `draft_id` 与 HEAD 相同。** 读码确认：`draft_novel` 分支只调用 `validate_draft_args`、`resolve_chat_conversation`（仅当会话为空时）、`count_open_drafts`、`create_draft`（只 `INSERT novel_drafts`）和 `get_draft`，没有任何路径碰 `novels`、`start_novel`、`billable_pending` 或 `check_chat_daily_cap`。

再用脚本在 HEAD 与新代码上各执行 4 种请求体：默认、`structure=v2`、只有三个必选智能体（触发 `panel_mode=solo`）、`drama_adaptation=true`。打桩 `runner.start_novel` 记录调用，每例导出两样东西：

- `create` 返回值（去掉 `id`、`created_at`、`updated_at`）；
- `novels` 行（含 `config_json`）与 `start_novel` 调用。

两边输出文件 `cmp` 相同（`CREATE_IDENTICAL`）。每例 `start_novel` 都恰好调用一次、参数为新书 id，`config` 中没有 `draft_id`。

**(d) 归属与隔离。** `save_message` 遇到别人的草稿、或本人另一会话的草稿时存 NULL（B4、B4b 变异都会被真实用例拦住）。`GET /novels/drafts/{id}` 对他人返回 404（B15）。`consume_draft` 在 `create` 的 `BEGIN IMMEDIATE` 内；已消费的草稿再次使用时返回 422，且 `novels` 行数不变（B6）；别人的草稿返回 422（B6b）。四个清理钩子都在各自的同一事务里（读码确认，每个钩子都有变异会红）。

**(e) AST 锁的放行范围。** `novel.drafts` 只放行 `validate_draft_args`、`create_draft`、`count_open_drafts`。`claude_agent.py:730` 实际只导入这三个；五个聊天侧文件里没有别的 `novel.drafts` / `from novel import drafts` 导入（`from novel import X` 仍只许 `service`）。导入 `novel.drafts` 的另外两个文件是 `routers/novel.py` 和 `novel/service.py`，都不在聊天侧。

**(f) 前端 `openNovelAt`。** 把真实函数从源码里取出来，在 node 里执行，另外测了几种边界输入：

| 输入 | 结果 |
|---|---|
| 两个合法形状 | 放行 |
| 末尾带 `\n` | 拒绝 |
| 带 `#x` | 拒绝 |
| 前导空格 | 拒绝 |
| `draft` 在前、`embed` 在后 | 拒绝 |
| `javascript:…//?embed=1` | 拒绝 |
| `data:` | 拒绝 |
| 多带一个参数 `&x=1` | 拒绝 |
| `/studio/<uuid>?embed=1` | 拒绝 |
| 36 个 `-` | 放行（规格给定的正则允许；同源、无害） |

**(g) 测试本身。**
- §4.5 后端 1–9 项每项都有实际断言。「不扣费 / 不建书」用 `novels` 行数为 0 和 `runner.TASKS` 不变来判断，没有用 `state.billable`。这个判据确实能区分：B12 让分支偷插一行 `novels`，用例就红。
- 「刷新后仍在」恢复了真实的 `_save_response`，经 `get_conversation_messages` 读回 `novel_draft_id`。
- 前端渲染用例在缺依赖时会 skip（经共享 `render_card` 的 `require_rendering_dependencies`），本环境 0 skipped。其余前端用例直接 `node … check=True`，缺依赖会报错，不会误绿。
- 没有发现「目标不存在也通过」的空集。
- 问题：`onOpenNovel` 透传缺一段（§4.2）；两条后端自检缺少正样本对照（§5.1）。

## 3. 变异实验记录

做法：用脚本按字节读出文件，断言替换目标出现的次数恰好符合预期，替换后写回，只跑对应测试，用 junit XML 记下每条失败用例的首个 `E` 行，再把原字节写回并核对 sha256。`page.tsx` 全程按字节处理，BOM 保留。共 38 项不同的变异（另有 F5all、F7all 两次扩大测试范围的重跑），**每项都已还原，逐文件 sha256 核对一致**，收尾时整体快照也一致。「真实」指名字不以 `test_bad_` 开头、且失败原因不是自检那部分的用例。

### 3.1 后端（跑 `tests/test_novel_chat_create.py`，B1 另加 `test_novel_chat.py`、`test_song_agent_tools.py`）

| # | 改了什么 | 结果（真实用例红在哪） | 还原 |
|---|---|---|---|
| B1 | `if novel_create_enabled(ctx.user):` → `if True:` | 7 failed：`test_switch_matrix…[None/dev/jwt-None]` ×3、既有 `test_novel_chat.py::test_claude_dynamic_tools_keep_original_constant` ×3（另 1 条是自检，因标记消失而红） | ✅ |
| B2 | `if draft_written:` → `if False:` | `test_one_draft_per_turn_then_text_reply`：`assert 2 == 1` | ✅ |
| B3 | `>= 50` → `> 50` | `test_fifty_open_drafts…`：`assert 51 == 50` | ✅ |
| B4 | `save_message` 草稿归属 SQL 放宽为只按 `id` | `test_save_message_checks_draft_owner_and_conversation`：`'…' is None` | ✅ |
| B4b | 只核对本人，不核对会话 | 同上（本人另一会话的草稿没存成 NULL） | ✅ |
| B5 | `create` 删掉消费草稿三行 | `test_create_with_draft_consumes_and_delete_resets`：`assert None == '<book>'` | ✅ |
| B6 | `consume_draft` 去掉 `novel_id IS NULL` | 同上：二次使用 `assert 201 == 422` | ✅ |
| B6b | `consume_draft` 去掉 `owner_username` 条件 | 同上：别人的草稿 `assert 201 == 422` | ✅ |
| B7 | `model_dump(exclude={'draft_id'})` → `model_dump()` | `test_create_with_draft…` 与 `test_create_without_draft_keeps_head_config_shape` 都红 | ✅ |
| B8 | 删书时不把草稿的 `novel_id` 置回 NULL | `test_create_with_draft…`：`'<book>' is None` | ✅ |
| B9 | 删会话不删草稿 | `test_delete_conversation_removes_only_that_conversations_drafts` | ✅ |
| B10 | 清空历史不删草稿 | `test_account_and_history_cleanup…[history]` | ✅ |
| B11 | 删号不删草稿 | `test_account_and_history_cleanup…[account]` | ✅ |
| B12 | `draft_novel` 分支偷插一行 `novels` | `test_success_path…`：`assert 1 == 0`（证明「不建书」判据能区分） | ✅ |
| B13 | 开关判定 `== '1'` → `!= '0'` | `test_switch_matrix…` ×3（`"true"` 那一组） | ✅ |
| B14 | `_save_response` 不透传 `novel_draft_id` | `test_success_path…`：落库消息 `None == '<id>'` | ✅ |
| B15 | `get_draft` 不按本人过滤 | `test_get_draft_route_is_owner_only`：`assert 200 == 404` | ✅ |
| B16 | 参数非法时不计 `agent_tool_errors` | `test_invalid_arguments…` 10 组：`assert 0 == 1` | ✅ |
| B17 | 在危机早退分支里也追加 `draft_novel` | `test_switch_matrix…[jwt-possible/high]` | ✅ |

### 3.2 前端（跑 `tests/test_novel_chat_create_frontend.py`）

| # | 改了什么 | 结果 | 还原 |
|---|---|---|---|
| F1 | `useConversations` 草稿分支条件改恒假 | `test_use_conversations_rebuilds…` 在执行结果上红（`both` 少了草稿卡） | ✅ |
| F1b | 写歌与草稿同时存在时只建写歌卡 | 同上，在执行结果上红 | ✅ |
| F2 | 删掉 `ChatCard` 的 `novel_draft` 分支 | `test_chat_card_renders…`：源码契约断言红 | ✅ |
| F2b | 分支字面保留，但传错 id（`card.project_id`） | 同上：**真实渲染**断言红（`data-novel-draft=""`） | ✅ |
| F3 | 删掉 `openNovelAt` 的两条正则守卫 | `test_page_open_novel_at…`：源码契约断言红 | ✅ |
| F3b | 正则字面保留，把 `setDrawer("novel")` 提到守卫之前 | 同上：**node 执行**断言红（非法路径也打开了抽屉） | ✅ |
| F3c | 第二条正则去掉 `$` | 同上：正则字面断言红 | ✅ |
| F4 | 两处 SSE 复制都去掉 `draft_id` | `test_page_stream_cards…`：`assert 0 == 2` | ✅ |
| **F5** | **`ChatBubble` 两处 `<ChatCard>` 都不传 `onOpenNovel`** | **8 passed，全绿**；F5all 把所有引用 `ChatBubble` 与书斋前端的测试都跑了一遍：**216 passed**。去掉后卡片按钮不渲染，主流程断掉 → §4.2 | ✅ |
| F6 | 页面不把 `onOpenNovel` 传给 `ChatBubble` | `test_page_stream_cards…`：源码契约断言红 | ✅ |
| F7 | 向导对已消费草稿也照样预填（`if (nextDraft.novel_id)` → `if (false)`） | **全绿**（F7all 加跑 p2 / p21 前端，77 passed）→ §5.2 | ✅ |
| F8 | 估算请求也带 `draft_id` | 只有自检那部分红（`DID NOT RAISE`：坏副本替换落到了估算那一行），没有真实断言拦住 → §5.2 | ✅ |
| F9 | 向导提交不带 `draft_id` | `test_wizard_reads_draft…`：源码契约断言红 | ✅ |
| F10 | `NovelDraftCard` 标题加 `font-semibold` | `test_novel_draft_component_states…` 红 | ✅ |
| F11 | 「去书斋建书」路径缺 `embed=1` | 同上，字面断言红 | ✅ |
| F12 | `NovelDraftCard` 已建书态与草稿态对调（`!draft.novel_id`） | **全绿** → §5.2 | ✅ |
| F13 | 404 也显示「草稿暂时读不到」 | **全绿** → §5.2 | ✅ |

### 3.3 既有锁与注释（跑 `tests/test_novel_p2_frontend.py`）

| # | 改了什么 | 结果 | 还原 |
|---|---|---|---|
| C1 | 只删 `page.tsx:2971` 那行 JSX 注释 | 既有用例 `test_home_keeps_novel_iframe_mounted_when_drawer_closes` 红：`assert 'src="/novels?embed=1"' in drawer` | ✅ |
| C2 | 保留注释，把 `useState("/novels?embed=1")` 改成 `useState("/novels/new?embed=1")` | 既有文件 **48 passed**：这条既有锁只靠注释通过，已经恒真 → §4.1 | ✅ |

## 4. 必须修复项

### 4.1 注释字面量绕过既有测试锁（规格与源码矛盾未上报；既有断言恒真）

- 文件 / 行：`frontend/app/page.tsx:2971`，`{/* 初始 src="/novels?embed=1"；打开草稿或已建书时由 novelFrameSrc 切换。 */}`；被绕过的锁是 `backend/tests/test_novel_p2_frontend.py:40`，`assert 'src="/novels?embed=1"' in drawer`。
- 现象：
  - T5.1 必然会打破这条既有锁，规格 §2.3 没有列出它。执行方没有按 §6 停下来上报，`03-report.md` §5 / §7 都没写，只在 `impl/C.md:13` 写了一句「保留注释字面量以兼容既有 test_novel_p2_frontend」。
  - 执行方把字面量放进 `#novel-drawer` 范围内的注释，让锁继续通过。C1 证明这条锁现在完全靠注释通过；C2 证明 iframe 初值改成别的路径，它也照样绿，即这条既有断言已经恒真。
  - 规格 §4.1 / 派单要求「既有测试一字不改」，R1 又否决过 `importlib` 绕 AST 锁。这里是同一类问题：测试文件一字没改，测试却失去了作用。
  - 实际功能目前没有错：新用例 `test_page_stream_cards_copy_draft_id_and_iframe_uses_state` 断言了 `useState("/novels?embed=1")` 和 `src={novelFrameSrc}`，原锁的意图有人接管。
- 期望：由派单方裁决（建议规格升 v1.2），授权把 `test_novel_p2_frontend.py:40` 改成断言状态化后的写法，同时删掉 `page.tsx` 里这行注释。另一种做法是派单方书面接受保留注释，但至少要写进 `03-report.md` 的「规格与源码事实的冲突」。具体步骤见 §6 A。

### 4.2 `ChatBubble → ChatCard` 的 `onOpenNovel` 透传没有断言（§4.5 点名项缺一段）

- 文件 / 行：`frontend/components/ChatBubble.tsx:285`（解构 `onOpenNovel`）、`:404-405`（两处 `<ChatCard … onOpenNovel={onOpenNovel} …/>`）；测试 `backend/tests/test_novel_chat_create_frontend.py:95-113`。
- 现象：
  - 现有用例只覆盖了两段：渲染测试验证 `ChatCard → NovelDraftCard` 这段（桩上的 `data-has-open`）；`page.tsx` 的 `onOpenNovel={openNovelAt}` 有字符串断言。
  - 第 99 行的 `"onOpenNovel={onOpenNovel} />"` 匹配到的是 `<NovelDraftCard …/>` 那一行，不是 `ChatBubble` 里的两个 `<ChatCard>`。
  - F5 去掉这两处透传后，8 条新前端用例全绿；F5all 把所有引用 `ChatBubble` 与书斋前端的测试一起跑（共 216 条，含这 8 条），也全绿。但 `NovelDraftCard` 在 `onOpenNovel` 缺失时不渲染按钮，「去书斋建书」和「打开」会从卡片上消失，规格 §1 的主流程断掉。
  - 规格 §4.5 前端清单写的是「`ChatCard` 的 `novel_draft` 分支与 `onOpenNovel` 透传」；T4.2 明确透传指「由 `ChatBubble` → 页面」。
- 期望：新增一条用例，断言 `ChatBubble` 函数解构了 `onOpenNovel`，且函数体内恰好 2 个 `<ChatCard … />` 标签都带 `onOpenNovel={onOpenNovel}`。用例里先断言原文通过，再断言坏副本抛 `AssertionError`。本方已验证 §6 B 给出的检查函数：原文通过，删一处、删两处（F5）、删解构这三种坏副本都会抛 `AssertionError`。

## 5. 可优化项（不阻断）

1. **两条后端自检缺正样本，且 `pytest.raises` 只是摆设**：`test_bad_one_per_turn_copy_is_caught`（`test_novel_chat_create.py:601-622`）和 `test_bad_save_message_copy_is_caught`（`:625-646`）。两条都没有在同一用例里先断言原实现通过；坏副本跑完后先断言 `len == 2` / `stored == foreign_id`，再写 `with pytest.raises(AssertionError): assert len == 1`，后者已被前一句决定，必然成立。真正起作用的是前一句，结论成立（B2 / B4 的真实用例确实红），但不符合「先断言原文通过，再断言坏副本抛错」的写法。建议抽出共享检查函数，先对原实现跑一次，再对坏副本 `pytest.raises`；`test_bad_switch_copy_is_caught` 已经这样写了。
2. **前端测试的几个覆盖缺口**：下面四项 §4.5 没有点名，但 T4.3 / T6.2 有要求：
   - F7：已消费的草稿也被预填，没有用例拦住；
   - F8：估算请求带上 `draft_id`，只有自检那部分会红，没有真实断言；
   - F12：卡片三态对调，没有用例拦住；
   - F13：404 显示错文案，没有用例拦住。

   建议仿照 `toMessages` 的做法，把 `Wizard.load` 的预填分支和 `NovelDraftCard` 的分支放进 node 里执行，或把状态分支抽成纯函数再测。
3. **`test_create_without_draft_keeps_head_config_shape`（`:548-572`）只比了 `config`**，期望值是照着 service 的后处理逻辑重写一遍得到的。返回结构的其余字段和 `start_novel` 调用没有直接断言。本方已用 HEAD 对照证明行为逐字节相同（§2.10 (c)）。建议把期望值改成固定快照，并比较返回值的全部字段（去掉 id 和时间戳）。
4. **建书后聊天里的卡片不会自己更新**：`NovelDraftCard.tsx:26-39` 只在挂载时拉一次，建书成功后要刷新或切换会话才变「已建书」。这符合 T4.3 的字面要求，但与 §1 / §5.8 的叙述有出入。建议派单方定夺；需要时可以在抽屉关闭、页面重新可见或收到 iframe 的建书消息时重新拉取。
5. **`openNovelAt` 重复点击同一路径不会导航**（`page.tsx:525-530`）：用户在 iframe 里导航过之后（例如点了「回到书架」），再点同一张卡，`setNovelFrameSrc(same)` 不会改变 `src`，抽屉只打开、不回到向导。建议每次通过校验时附带一个 nonce，或直接替换 iframe 的 location。这是规格 T5.2 的设计留下的问题，不算偏离规格。
6. **孤儿草稿与上限竞态**：草稿在本轮落库之前就已提交。如果这轮没落库（客户端断开、会话被删、保存失败），草稿仍然留在库里并占用 50 份的名额。如果会话在 `create_draft` 之前就被删了，草稿会带着失效的 `conversation_id` 残留下来，只能等删号或清空历史时清掉。另外是先 `count` 再 `create`，两步不在同一事务（执行方报告里已经自述）。P0 可以接受，可列入 PLAN。
7. **文档顺带同步**（规格 §4.4 限定了范围，所以不阻断）：
   - `backend/.env.example:47` 的「卡片不落库（写歌卡例外…）」没有加上草稿卡；
   - `docs/ARCHITECTURE.md:137`（`toMessages` 只写了按 `song_project_id` 重建）和 `:141`（「写歌是例外」）没有同步；
   - `docs/DEPLOYMENT.md` 没有出现 `FIONA_NOVEL_CHAT_CREATE`，老库升级一节也没有提 `novel_drafts` / `messages.novel_draft_id`。
8. **测试里残留 v1.0 的注释**：`workshop` 夹具（`:475`）写着「client fixture 已按开关 0 初始化；这里按开关 1 幂等补建草稿表」，`draft_db` 也设置了开关。v1.1 改为无条件建表后，这些已经没有必要，注释会误导读者。
9. `test_page_stream_cards_copy_draft_id_and_iframe_uses_state` 用全文计数 `count == 2`，没有绑定到两个 `const card: CardData = {…}` 块内部。另外 `'src="/novels?embed=1"' not in …split('title="书斋工作区"')…` 依赖 `title` 写在 `src` 前面，属性顺序一变就会恒真。
10. `novel/drafts.py` 在模块顶层 `import database`，`novel/service.py` 又在顶层 `from .drafts import consume_draft`，所以导入 `novel.service` 时会顺带导入 `database`。`novel/store_db.py` 的做法是在函数内延迟导入。可以统一成延迟导入。
11. 走查脚本（派单方）可以补两步：一是用假传输回放 `tool_use`，让聊天流式出卡，验证 SSE 那两处复制和实时渲染出来的按钮；二是先在**不刷新**的情况下断言卡片状态，再刷新（见 §2.8）。

## 6. 给执行者的二次修改指令

> 工作目录是同一 worktree，基线 `0ca95af`。git 只读；不得调用 subagent / subagent_fork / workflow。只做下面列出的事，其余文件一个字节不动。改 `frontend/app/page.tsx` 必须按字节读写并保留开头 BOM（`efbb bf`）。

### A. 去掉注释绕行（对应 §4.1；**须派单方先在规格 v1.2 授权 `backend/tests/test_novel_p2_frontend.py` 改这一处**，未获授权不要动这个文件）

1. `frontend/app/page.tsx`：按字节删除下面这一整行（含行尾换行），其余不动：
   ```text
           {/* 初始 src="/novels?embed=1"；打开草稿或已建书时由 novelFrameSrc 切换。 */}
   ```
2. `backend/tests/test_novel_p2_frontend.py:40`：把
   ```python
       assert 'src="/novels?embed=1"' in drawer
   ```
   替换为下面三行，缩进相同，其余一字不改：
   ```python
       assert "src={novelFrameSrc}" in drawer
       assert 'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")' in source
       assert 'src="/novels?embed=1"' not in drawer
   ```
3. 自查：
   - `grep -c 'src="/novels?embed=1"' frontend/app/page.tsx` 输出 `0`；
   - `head -c 3 frontend/app/page.tsx | xxd` 为 `efbb bf`；
   - `git diff -U0 HEAD -- backend/tests/test_novel_p2_frontend.py | grep -c '^@@'` 输出 `1`；
   - `tests/test_novel_p2_frontend.py` 全绿；
   - 临时把 `useState("/novels?embed=1")` 改成 `useState("/novels/new?embed=1")`，确认 `test_home_keeps_novel_iframe_mounted_when_drawer_closes` 变红，然后按字节还原。
4. 如果派单方不授权：本项改为在 `03-report.md` 的「规格与源码事实的冲突」里如实写明这处注释的用途和影响，由派单方书面接受。

### B. 补 `ChatBubble → ChatCard` 透传断言（对应 §4.2）

在 `backend/tests/test_novel_chat_create_frontend.py` 的「ChatCard 分发」一节末尾追加以下代码（`re`、`function_block`、`read`、`BUBBLE` 文件里都已存在）：

```python
CHAT_CARD_TAG = re.compile(r"<ChatCard\b[^>]*/>")


def check_bubble_passes_open_novel(source):
    body = function_block(source, "function ChatBubble(")
    assert "onOpenNovel" in body.split(")", 1)[0], "ChatBubble 未解构 onOpenNovel"
    tags = CHAT_CARD_TAG.findall(body)
    assert len(tags) == 2, tags
    for tag in tags:
        assert "onOpenNovel={onOpenNovel}" in tag, tag


def test_chat_bubble_passes_open_novel_to_every_chat_card():
    source = read(BUBBLE)
    check_bubble_passes_open_novel(source)
    for bad in (
        source.replace(" onOpenNovel={onOpenNovel} songCardCompact", " songCardCompact", 1),
        source.replace("onCompose, onOpenNovel, songCardCompact }: ChatBubbleProps",
                       "onCompose, songCardCompact }: ChatBubbleProps", 1),
    ):
        assert bad != source
        with pytest.raises(AssertionError):
            check_bubble_passes_open_novel(bad)
```

自查：
- 新用例在工作区通过；
- 临时把 `ChatBubble.tsx` 里两处 ` onOpenNovel={onOpenNovel} songCardCompact` 都删掉，新用例变红，然后按字节还原；
- HEAD 副本上这条新用例以 `AssertionError` 失败。

### C. 可选，建议同批顺手做（对应 §5.1、§5.8）

1. `test_bad_one_per_turn_copy_is_caught` 与 `test_bad_save_message_copy_is_caught`：各抽一个检查函数，例如 `check_one_draft(rows)`、`check_foreign_draft_stored_null(stored)`。真实用例和自检共用这个函数；自检先用原实现跑一遍并断言通过，再对坏副本 `with pytest.raises(AssertionError): check_…(…)`。删掉现在那种「先 `assert == 2`，再 `pytest.raises` 包 `assert == 1`」的写法。
2. 删掉 `workshop` 夹具里关于「开关 0 初始化 / 按开关 1 补建草稿表」的注释，以及多余的 `init_db` 调用和开关设置。同时确认 `test_init_db_creates_draft_table_without_switch` 仍然覆盖「表的存在与开关无关」。

### D. 重跑与报告

1. 重跑规格 §5 第 1–7 条。新用例数变为 41，全量预期 `7863 + 41 = 7904 passed`，`0 skipped`；HEAD 对照预期 41 条全部是 `AssertionError`。§5.7 的零 diff 命令排除列表里要加上 `':!backend/tests/test_novel_p2_frontend.py'`（仅在 A 获授权时），并贴出该文件 `git diff -U0` 的唯一 hunk。
2. 在 `03-report.md` 末尾追加「R2 记录」：裁决、改了什么、§5 各条末行、上面几项自查的实际输出；在 `impl/主代理.md` 追加本轮记录。报告里不要写本机绝对路径。
