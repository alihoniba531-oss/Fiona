# 规格：聊天建书（Claude 智能体把聊天里定下的小说设定送进书斋）

- 规格版本：v1.2（2026-11-03；R2 决裁：T5.1 把 iframe `src` 状态化必然打破既有锁 `backend/tests/test_novel_p2_frontend.py:40`（`assert 'src="/novels?embed=1"' in drawer`），v1.1 没查到，执行者用注释字面量绕过，独立复核判为锁已恒真。v1.2 把该文件加入白名单，**只许改这一处**：把那一行换成三行——`assert "src={novelFrameSrc}" in drawer`、`assert 'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")' in source`、`assert 'src="/novels?embed=1"' not in drawer`；`page.tsx` 删掉那行注释。）
- v1.1（2026-11-03；R1 决裁：`novel_drafts` 建表保持 T1.1 的「无条件」，为此把 `backend/tests/test_studio_sources_readonly_integration.py` 加入白名单、只许改两处（§3.1 末尾与 §4.1）；v1.0 只在派单前补了白名单一行 `backend/studio/sources.py`）。事实来源：派单方亲自读落点 + DeepSeek Flash 只读调查事实表 `01-investigation.md`（乙档；调查方在 read-only 沙箱里跑不了 pytest，测试类结论以源码为准）。
- 任务级别：**L3**（新增一张表与一个可空列，属数据模型变更）。规格须经用户确认后才派单；复核用 dsh 上的 Opus 5.5 `xhigh`。
- 基线：Fiona `main` = `0ca95af`（后端全量 `7863 passed / 0 skipped`，由 11-02 第五批门禁在 `9b02ff0` 实测，`0ca95af` 只加了文档）。
- 执行者：dsh / DeepSeek Flash / max，经 codex MCP，在专用 worktree。

## 1. 产品目标与场景

用户在聊天里用自带的 Claude 和分身一起把一本长篇的题材、时代、主角成长线、主要人物聊定，然后说「帮我去我的书斋里建」。现在模型只能在聊天里搭框架（截图 2026-11-02 12:35），书斋对它不可见、也没有任何建书入口。

本批之后：Claude 调用一个免费的 `draft_novel` 工具，把聊定的设定写成一份**书斋草稿**；聊天里出现一张「书斋草稿」卡片，点「去书斋建书」打开书斋抽屉，建书向导第一步已经填好故事思路；**选智能体与模型、定预算、点「建书」仍由主人在向导里完成**——建书会立刻发起付费推演（`service.create` 插入 `setup_running` 并 `start_novel`），这一步不能由模型代做。建书成功后卡片变成「已建书，打开《书名》」。

用户已接受的方案原文：「给聊天加一个「建书」工具，模型把聊天里定下的题材、背景、人物写成简报，调用书斋的建书接口，回你一张卡片，点开就是那本书的工作台；是否开始写、用哪种推演方式仍在书斋里确认，因为写作是按章扣费的，不能让模型代扣。」本规格把「调用书斋的建书接口」落实为「写草稿 + 向导预填」，原因见 §2.1。

## 2. 现状事实（派单方亲自核实，行号以 `0ca95af` 为准）

### 2.1 建书即扣费，没有「只建不写」的路径

- `backend/novel/service.py:207-229` `create()`：`estimate` → 预算校验 → `INSERT INTO novels(... status='setup_running' ...)` → `start_novel(novel_id, username)` → 立即返回 `detail`。
- `backend/novel/runner.py:95-131` `start_novel` / `_start_novel_locked`：状态为 `setup_running` / `running` 且无 `run_token` 时领 token 并 `create_background_task(_run(...))`；`_run` 用 `NovelBilling` 预留草莓（`runner.py:63`）。
- `novels.status` 的非运行态（`paused` / `awaiting_*` / `completed` / `failed`）都只由 runner 或 `transition()` 写入；没有任何代码路径能插入一本「待主人确认才开始」的书（`rg -n "INSERT INTO novels" backend` → 仅 `service.py:225` 一处）。
- 结论：聊天工具**不得**调用 `service.create`；草稿另存一张表，由向导预填后、主人在向导里提交 `create`。

### 2.2 Claude 智能体的工具按轮追加

- `backend/services/claude_agent.py:48-54` `CLAUDE_CLIENT_TOOLS` 固定 5 个；`:70-92` `client_tools_for_turn`：`novel_intents_enabled(user, crisis)` 为真时追加 `list_novels` / `read_novel`（`allow_studio` 再加 `start_film`），写歌开启再追加 `SONG_TOOLS`；全关时**返回同一个对象** `CLAUDE_CLIENT_TOOLS`。
- `backend/intent_router.py:155-159` `novel_intents_enabled`：`FIONA_NOVEL_CHAT == "1"` 且 `novel_access(username)`（`studio/sources.py:31-34`：`FIONA_NOVEL == "1"` 且用户名在 `FIONA_NOVEL_USERS`）。
- 工具执行：`claude_agent.py:678-700`，`name in _NOVEL_CLIENT_INTENTS` → `_novel_tool_params` → `chat.run_slow(chat.execute_intent, ...)`；结果是 `{"type":"card",...}` 时拼进 `state.full_response`（`［卡片：…］`）、`delivered = True`、`yield chat._sse({"card": result, "append": True})`；否则当文本回灌。
- 写歌工具的卡片落库：`claude_agent.py:470-486` 把 `card["project_id"]` 写进 `state.song_project_id`；`chat_service.py:774` `ChatState.song_project_id`、`:977` 传给 `save_message`；`database.py:145` 用 `_safe_migrate` 给 `messages` 加 `song_project_id` 列，`:550-561` 存前核对项目属于本人本会话。
- 前端重建：`frontend/lib/useConversations.ts:67-69` 按 `message.song_project_id` 生成 `{subtype:"song_project", project_id}` 卡片；`frontend/components/ChatBubble.tsx:90-123` `ChatCard` 按 `subtype` 分支渲染（`song_project` → `SongProjectCard`；`studio_project` → 瓷片卡 + `url` 以 `/studio/` 开头且只含 `[A-Za-z0-9/_-]` 才渲染「打开工作室」）。
- `start_film` 的卡片形状（`backend/studio/novel_chat.py:116-135`）：`{"type":"card","subtype":"studio_project","source":"短片工作室","points":[...],"url":"/studio/<id>"}`，出错时 `{**card,"error":"..."}`。

### 2.3 既有测试锁（一字不改，新工具必须绕开）

- `backend/tests/test_novel_chat.py:179-188` `test_claude_dynamic_tools_keep_original_constant`：`FIONA_NOVEL_CHAT=1` 时 `client_tools_for_turn` 追加的集合**恰为** `{"list_novels","read_novel"}`（jwt 再加 `start_film`；危机轮为空集且 `tools is CLAUDE_CLIENT_TOOLS`）；`CLAUDE_CLIENT_TOOLS` 的名字集合恰为五个。
- `:27-33` 夹具 `enabled` 只设 `FIONA_NOVEL_CHAT` / `FIONA_NOVEL` / `FIONA_NOVEL_USERS` / `FIONA_STUDIO*`，**不设**本规格的新开关 → 新开关默认 0 时既有测试看到的工具集合不变。
- `:270-283`：开关 0 与 1 两次请求 `kwargs["tools"] is h.agent.CLAUDE_CLIENT_TOOLS` 且请求体逐字节相同（那条用例的 `FIONA_NOVEL_USERS` 不含该用户）。
- `backend/tests/test_studio_sources_readonly_integration.py:21-30` `novel_table_bytes()` 断言库里名为 `novels` 或 `novel_*` 的表集合**恰为** P1 五张；`:177-199` 的 AST 锁只允许聊天侧五个文件 `from novel import service` / `from novel.service import <六个只读函数>` / `from novel.runner import is_editing`，其他 `novel.*` 导入一律断言失败。v1.0 没查到这两条，执行者首轮因此把建表改成「开关开启才建」并用 `importlib` 绕过 AST 锁（都不接受，见 R1）。**v1.1 授权**：该测试文件只许改两处——(a) `:28-29` 的集合加入 `"novel_drafts"`；(b) `:193-195` 的 `elif node.module and node.module.startswith("novel.")` 分支改为：`novel.runner` 只许 `is_editing`，`novel.drafts` 只许 `{"validate_draft_args", "create_draft", "count_open_drafts"}`，其余 `novel.*` 仍断言失败。此外一个字节不动。
- `backend/tests/test_claude_agent_runtime.py:118-123` 锁 `CLAUDE_CLIENT_TOOLS` 名字集合恰为五个；`test_song_agent_tools.py:689-696, 750-755` 锁「全关 5 个、写歌开 9 个」且 `is CLAUDE_CLIENT_TOOLS`。新工具只在独立开关下动态追加，这些都不动。
- `backend/tests/test_claude_agent_docs.py:12-48` 要求 `README.md` / `CLAUDE.md` / `PLAN.md` / `docs/ARCHITECTURE.md` / `docs/DEPLOYMENT.md` / `backend/.env.example` 六份文档逐字含「Claude 智能体模式」「4 次」「240 秒」「8000 字」「**卡片不落库**」「历史图片」等短语。新文档句子只能追加，且必须保留「卡片不落库」这个子串（写成「其余卡片不落库；写歌卡与书斋草稿卡例外」，不能改成「卡片一般不落库」）。
- `backend/tests/test_novel_v2_compat.py:113-122` 只断言 `volume_gate` 不在 `CreateNovel.model_fields`，加 `draft_id` 不冲突；`test_novel_p21_frontend.py:32-48` 锁 `NovelWizard.tsx` 的既有文案行，只能加行不能改行。

### 2.4 书斋抽屉与向导

- `frontend/app/page.tsx:2934-2962`：书斋抽屉 `#novel-drawer` 内是固定 `src="/novels?embed=1"` 的 iframe（`novelFrameRef`）；`:531-545` 只处理 iframe → 父页的 `fiona-novel-open-settings` / `fiona-novel-close` 两种消息；**父页没有任何向 iframe 导航的代码**（`grep -c 'contentWindow?.postMessage\|novelFrameRef.current.src' page.tsx` → 0）。
- `frontend/app/novels/new/page.tsx` 只包了 `<Suspense><NovelWizard/></Suspense>`；`NovelWizard.tsx:41` 读 `embed` 查询参数；`:56-69` 各字段 `useState`，默认 50–70 章、2000 字/章、6 人物、3 场景、`critique`、`per_batch`、每批 5、预算 10000；`:150-160` `submit` → `createNovel(input)` → `router.push(novelHref('/novels/<id>', embedded))`。
- `frontend/lib/novels.ts:9-15` `NovelCreateInput`；后端 `CreateNovel`（`novel/service.py:60-70`）`extra='forbid'`，所以请求体多一个字段会 422——加 `draft_id` 必须同时改模型。
- `novels.title` 由推演阶段写入，向导没有书名输入框；草稿的 `title` 只用于卡片与草稿列表，不进 `CreateNovel`。

### 2.5 不存在的东西（派单方 grep）

- 仓库里没有 `novel_draft` / `novelDraft` / `draft_novel`（`rg` → 0）。
- 父页没有向书斋 iframe 导航的机制（见 2.4）。
- `service.create` 没有同名去重、没有「一轮多本」保护（它靠 `check_active` 限制每用户同时只能运行一本）。

## 3. 设计决策

1. **独立开关** `FIONA_NOVEL_CHAT_CREATE`：默认 `0`，只有字面 `1` 开启，调用时读取；必须同时满足 `novel_chat_enabled(user)` 与非危机轮才追加 `draft_novel`。目的：既有 `test_novel_chat.py` 的集合锁一字不改；试用脚本和 `.env.example` 加这一项。
2. **只写草稿，不建书**：新表 `novel_drafts`；向导通过 `?draft=<id>` 预填；真正的 `create` 仍由主人在向导里发起，并带 `draft_id` 让服务端在同一事务里把草稿标为已消费。
3. **只做 Claude 智能体路径**：平台（千问）意图识别要从对话里抽出一份 2000 字简报不可靠，P0 不加 `novel_draft` 平台意图；文档写明。
4. **卡片落库**：`messages` 加可空列 `novel_draft_id`，与 `song_project_id` 同模式；刷新后按它重建卡片。
5. **抽屉导航**：父页加一个 `openNovelAt(path)`：打开书斋抽屉并把 iframe 的 `src` 设为 `path`（含 `embed=1`）；iframe 重载、丢失原页面状态是可接受的。只允许 `/novels/new?...&draft=<uuid>` 与 `/novels/<uuid>?embed=1` 两种形状，其他一律忽略。

## 4. 执行者任务清单

### 4.1 白名单（只许改 / 新增这些）

后端：
- `backend/database.py`（`novel_drafts` 建表 + `messages.novel_draft_id` 列迁移 + `save_message` 的归属核对 + 删号 `delete_account_data`（`:826-934`，`novels` 在 `:931` 删）与清空历史 `clear_message_history`（`:470-487`）的同事务清理）
- `backend/agent_store.py`（`get_conversation_messages` 的 SELECT 带上 `novel_draft_id`，`:338-345`；`delete_conversation`（`:354-381`）同事务删本会话草稿）
- `backend/novel/drafts.py`（新）：草稿的增查改
- `backend/novel/service.py`（`CreateNovel.draft_id`、`create` 内消费草稿；`delete`（`:768-778`）同事务把指向该书的草稿 `novel_id` 置回 NULL）
- `backend/routers/novel.py`（`GET /novels/drafts/{id}`）
- `backend/studio/sources.py`（新增 `novel_create_enabled(username)`，紧挨 `novel_chat_enabled`）
- `backend/services/claude_agent.py`（工具定义、追加条件、执行分支、卡片落库）
- `backend/services/chat_service.py`（`ChatState.novel_draft_id`、`_save_response` 透传）
- 文档六份：`backend/.env.example`、`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`（具体段落见 §4.4）
- 新测试：`backend/tests/test_novel_chat_create.py`、`backend/tests/test_novel_chat_create_frontend.py`
- 既有测试（v1.1 加入，只许 §2.3 说明的两处）：`backend/tests/test_studio_sources_readonly_integration.py`
- 既有测试（v1.2 加入，只许 `:40` 那一处换成三行）：`backend/tests/test_novel_p2_frontend.py`

前端：
- `frontend/components/NovelDraftCard.tsx`（新）
- `frontend/components/ChatBubble.tsx`（`ChatCard` 加 `novel_draft` 分支与 `onOpenNovel` 透传）
- `frontend/lib/useConversations.ts`（按 `novel_draft_id` 重建卡片）
- `frontend/app/page.tsx`（`openNovelAt`、iframe `src` 状态化、把 `onOpenNovel` 传给消息列表；**按字节读写，保留 BOM**）
- `frontend/components/novel/NovelWizard.tsx`（读 `draft` 参数、预填、提交带 `draft_id`）
- `frontend/lib/novels.ts`（`getNovelDraft`、`NovelCreateInput.draft_id?`）

文档：`docs/tasks/2026-11-02-chat-create-novel/03-report.md`、`impl/*.md`。

**不得改**：其他既有测试一字不改；`CLAUDE_CLIENT_TOOLS` 常量不动；`client_tools_for_turn` 在新开关为 0 时的返回值（含对象同一性）逐字节不变；`service.create` 对不带 `draft_id` 的请求行为不变；不新增依赖。

### 4.2 后端

**T1 草稿存储（`database.py` + `novel/drafts.py`）**

1. `init_db` 里 `CREATE TABLE IF NOT EXISTS novel_drafts(id TEXT PRIMARY KEY, owner_username TEXT NOT NULL, conversation_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', seed_idea TEXT NOT NULL, target_json TEXT NOT NULL DEFAULT '{}', novel_id TEXT DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)` 与 `idx_novel_drafts_owner` 索引；紧跟 `song_project_id` 那行加 `await _safe_migrate(db, "ALTER TABLE messages ADD COLUMN novel_draft_id TEXT DEFAULT NULL")`。不新增迁移版本号，`/health` 仍五道迁移。
2. `novel/drafts.py` 提供：`create_draft(username, conversation_id, title, seed_idea, target) -> dict`、`get_draft(username, draft_id) -> dict | None`（只返回本人的）、`count_open_drafts(username) -> int`（`novel_id IS NULL`）、`consume_draft(db, username, draft_id, novel_id) -> bool`（同一连接、同一事务内把 `novel_id` 填上，只在 `novel_id IS NULL` 时成功）。
3. `save_message`：`novel_draft_id` 非空时核对 `novel_drafts` 里该 id 属于本人本会话，不属于则存 NULL（与 `song_project_id` 同写法）。
4. 删号（`database.delete_account_data`）、清空历史（`database.clear_message_history`）：在删 `messages` 的同一事务里 `DELETE FROM novel_drafts WHERE owner_username=?`；删会话（`agent_store.delete_conversation`）：同一事务里 `DELETE FROM novel_drafts WHERE owner_username=? AND conversation_id=?`。都紧挨着现有的写歌清理语句写。草稿没有文件，不进清理队列。
5. 单本删书（`service.delete`）：在删 `novels` 的同一事务里 `UPDATE novel_drafts SET novel_id=NULL, updated_at=CURRENT_TIMESTAMP WHERE owner_username=? AND novel_id=?`，草稿回到可用状态（卡片随之回到「去书斋建书」），不留悬空引用。

**T2 建书消费草稿（`novel/service.py` + `routers/novel.py`）**

1. `CreateNovel` 加 `draft_id: str | None = None`（`extra='forbid'` 保持）。`create()` 在 `BEGIN IMMEDIATE` 事务里、插入 `novels` 之后：若 `draft_id` 非空，调用 `consume_draft`；失败（不存在 / 不属于本人 / 已消费）→ `fail('草稿不存在或已使用', 422)`，事务回滚（不插书、不 `start_novel`）。`config_json` 不含 `draft_id`（`config = data.model_dump(exclude={'draft_id'})`）。
2. `GET /novels/drafts/{draft_id}`（`workshop_user` 门控）：返回 `{id, title, seed_idea, target, novel_id, created_at}`；不是本人的 404。不做列表、删除接口（P0）。
3. `create` 不带 `draft_id` 时：请求体、返回结构（去掉时间戳字段后）、`config_json` 内容、`start_novel` 调用与 HEAD 完全一致；`detail().config` 不含 `draft_id`。

**T3 Claude 工具（`services/claude_agent.py` + `chat_service.py`）**

1. 新常量 `NOVEL_DRAFT_TOOL = _tool("draft_novel", "把聊天里定下的小说设定写成书斋草稿；免费，不会开始写作。主人到书斋确认智能体与预算后才建书。", {"title": {"type":"string","maxLength":60}, "seed_idea": {"type":"string","maxLength":2000,"description":"故事思路：题材、时代、主角成长线、主要人物、风格；第一行写书名"}, "min_chapters": {"type":"integer","minimum":1,"maximum":200}, "max_chapters": {"type":"integer","minimum":1,"maximum":200}, "chapter_words": {"type":"integer","minimum":1000,"maximum":4000}}, ["title","seed_idea"])`。
2. `client_tools_for_turn`：在追加 `list_novels` / `read_novel` 的那个分支里，`novel_create_enabled(ctx.user)` 为真时再 `tools.append(NOVEL_DRAFT_TOOL)`（放在 `start_film` 之后、写歌之前）。`novel_create_enabled` 写在 `intent_router.py` 旁边的 `studio/sources.py`：`os.getenv("FIONA_NOVEL_CHAT_CREATE","0") == "1" and novel_chat_enabled(username)`。新开关为 0 时函数的每条返回路径与现在逐字节相同。
3. 执行分支（与 `_NOVEL_CLIENT_INTENTS` 并列的 `elif name == "draft_novel":`）：
   - 参数校验在 `novel/drafts.py:validate_draft_args(args) -> (clean, error)`：`title` 去空白后 1–60 字；`seed_idea` 去空白后 1–2000 字；三个整数可缺省（缺省用 `Target` 默认 50 / 70 / 2000），范围同 `Target`，`min > max` 报错；非法 → 结果文本（如「草稿的故事思路要在 1–2000 字之间」），计入 `agent_tool_errors`，不建草稿。
   - 每轮最多 1 份草稿：第二次调用直接回文本「本轮已写过一份草稿，请直接回答主人」，不计错误。
   - `count_open_drafts >= 50` → 文本「未使用的草稿太多，请先到书斋建书或删除」。
   - 成功：`create_draft(...)`，卡片 `{"type":"card","subtype":"novel_draft","source":"书斋","points":[f"草稿《{title}》已送到书斋", "到书斋确认智能体与预算后开始写作"],"draft_id": id,"url": f"/novels/new?draft={id}","error": False}`；像小说工具一样 `yield chat._sse({"card": card, "append": True})`、拼 `［卡片：…］`、`delivered = True`，并 `state.novel_draft_id = id`；回灌给 Claude 的 `result_text` = points 两行。
   - 草稿不扣草莓、不计 `byok_chat` 之外的任何每日上限；仍占本轮 4 次客户端工具的名额。
4. `ChatState.novel_draft_id: str | None = None`；`_save_response` 把它传给 `save_message(novel_draft_id=...)`。
5. 镜子轮不带工具、危机轮不追加——沿用现有条件，不另写。

### 4.3 前端

**T4 卡片（`NovelDraftCard.tsx` + `ChatBubble.tsx` + `useConversations.ts`）**

1. `useConversations.ts` 的 `toMessages`：`message.novel_draft_id` 存在时生成 `{source:"书斋", points:[], subtype:"novel_draft", draft_id}`（与写歌并列；两者同时存在时两张都要）。`StoredMessage` 加 `novel_draft_id?: string | null`；`CardData` 加 `draft_id?: string`。
2. `ChatCard`：`subtype === "novel_draft"` → `<NovelDraftCard draftId onOpenNovel />`。`ChatCardProps` 加 `onOpenNovel?: (path: string) => void`，由 `ChatBubble` → 页面透传（和 `onCompose` 同路径）。
3. `NovelDraftCard`：挂载时 `getNovelDraft(id)`；三态——加载中（「正在读取草稿…」）、草稿态（瓷片卡：`书斋草稿 · 《title》`、思路前 80 字、按钮「去书斋建书」→ `onOpenNovel("/novels/new?embed=1&draft=<id>")`）、已建书态（`novel_id` 非空：「已建书《title》」、按钮「打开」→ `onOpenNovel("/novels/<novel_id>?embed=1")`）；404 / 403 → 「草稿已不存在」，无按钮。样式沿用 `studio_project` 卡：`ceramic-card w-[340px] max-w-full`，按钮 `btn btn-primary min-h-10`；**不加粗**（`font-medium` 以内）；不新增颜色与字号令牌。
4. 同一草稿出现在多条消息里时，每张卡都独立拉取（P0 不做「只最后一张完整显示」）。

**T5 抽屉导航（`page.tsx`）**

1. iframe `src` 改为状态 `novelFrameSrc`（初值 `"/novels?embed=1"`）。
2. `openNovelAt(path: string)`：只接受正则 `^/novels/new\?embed=1&draft=[0-9a-f-]{36}$` 或 `^/novels/[0-9a-f-]{36}\?embed=1$`，其他直接返回；通过时 `setNovelFrameSrc(path)` 并 `setDrawer("novel")`。
3. 把 `onOpenNovel={openNovelAt}` 传到渲染 `ChatCard` 的地方（现有 `onCompose` 走哪条链就跟哪条）。
4. `page.tsx:2144-2170` 有两处手工复制卡片字段的 `const card: CardData = {...}`（SSE 卡片事件进状态时只拷 `source/points/url/error/subtype/project_id/weather/items/sources`），两处都要加 `draft_id`，否则流式到达的草稿卡没有 id、渲染不出按钮。
5. 不改抽屉外壳、关闭逻辑、postMessage 处理。

**T6 向导预填（`NovelWizard.tsx` + `novels.ts`）**

1. `novels.ts`：`getNovelDraft(id, signal)` → `GET /novels/drafts/{id}`；`NovelCreateInput` 加 `draft_id?: string`。
2. `NovelWizard`：读 `useSearchParams().get("draft")`；形状合法（36 位 uuid）时在 `load` 里一并 `getNovelDraft`，成功则 `setSeed(draft.seed_idea)`、`setMinChapters/MaxChapters/ChapterWords`（有值才覆盖），并记 `draftId`；草稿已消费（`novel_id` 非空）→ 页面顶部一行提示「这份草稿已建成《…》」并提供链接，不预填；404 → 提示「草稿不存在」，向导照常可用。
3. `submit` 时 `createNovel({...input, draft_id: draftId ?? undefined})`；422「草稿不存在或已使用」按现有 `novelErrorMessage` 显示。
4. 主人改动预填内容不受限制；不加「来自聊天」之类的装饰标签。

### 4.4 文档与配置

- `backend/.env.example:205-214` 小说段：加 `FIONA_NOVEL_CHAT_CREATE=0` 与一句说明（默认关闭、只有字面 1 开启、须同时开 `FIONA_NOVEL_CHAT`）。
- `CLAUDE.md`「聊天读小说」段（`:194` 附近）末尾追加一段：开关、`draft_novel` 工具、草稿免费且不开始写作、建书仍在向导里由主人确认、`novel_drafts` 表与 `messages.novel_draft_id` 列（`init_db` 幂等、`/health` 仍五道迁移）、删号 / 删会话 / 清空历史 / 删书的清理、平台路径不支持；「已知局限」里把「卡片一般不落库，写歌卡例外」改成「其余卡片不落库；写歌卡与书斋草稿卡例外」（必须保留子串「卡片不落库」）。`CLAUDE.md:18`「5 个客户端工具」照旧，常量没变。
- `README.md:333-357` 小说工坊段加一小段「聊天建书」；`docs/ARCHITECTURE.md:412` 小说聊天处加一句；`docs/DEPLOYMENT.md` 与 `PLAN.md` 只在提到「卡片不落库」的句子处同步例外（`DEPLOYMENT.md:245/251/892`、`PLAN.md:483` 按实际内容判断是否需要改，改则保留子串）。
- 所有文档改动跑 `tests/test_claude_agent_docs.py` 必须仍绿。

### 4.5 测试（新文件，规格列的每一项都要有断言）

`test_novel_chat_create.py`：`message` / `call` / `FakeStream` / `run` 可 `from test_claude_agent_runtime import ...`（模块级，`backend/tests` 无 `__init__.py` 但按模块名可导）；`harness` 是 fixture 只能注入；`enabled` / `offline` / `catalog` 是 `test_novel_chat.py` 的模块内 fixture，新文件自己定义同样的（再多设 `FIONA_NOVEL_CHAT_CREATE=1`）。判据必须用能区分的 oracle：「不扣费 / 不建书」用 `novels` 行数为 0 且 `runner.TASKS` 为空来断，**不能用** `state.billable`（小说分支本来就不设它）也**不能只用**余额（`DEV_MODE=1` 下恒不变）；「刷新后仍在」要真走 `_save_response` → `agent_store.get_conversation_messages`，断言 `novel_draft_id`。清单：
1. 开关矩阵：`FIONA_NOVEL_CHAT_CREATE` 为 `0` / 未设 / `true` 时，`client_tools_for_turn` 返回集合与对象同一性和现在完全一致（直接复用 `test_claude_dynamic_tools_keep_original_constant` 的四组参数逐组断言）；为 `1` 且 `novel_chat_enabled` 时多且只多 `draft_novel`；危机轮不追加。
2. 参数校验：标题空 / 超 60、思路空 / 超 2000、章数越界、`min > max` 各一条，全部返回文本、不建草稿、`agent_tool_errors` +1。
3. 成功路径：一次 `tool_use` → `novel_drafts` 多 1 行（owner / conversation 正确）、SSE 里有 `subtype == "novel_draft"` 的卡片、`state.novel_draft_id` 等于该 id、落库的 assistant 消息 `novel_draft_id` 等于该 id、`full_response` 含 `［卡片：`、草莓余额不变。
4. 一轮两次调用：第二次为文本、只有 1 行草稿。
5. 50 份未消费草稿时拒绝。
6. `save_message` 传入别人的 / 别的会话的草稿 id → 存 NULL。
7. `create` 带 `draft_id`：成功后草稿 `novel_id` = 新书 id；再次带同一 `draft_id` → 422 且 `novels` 行数不变；别人的 id → 422。不带 `draft_id` 的请求行为与 HEAD 相同（请求体与返回逐字段比对）。
8. 删号（`delete_account_data`）、清空历史（`clear_message_history`）、删会话（`agent_store.delete_conversation`）后 `novel_drafts` 对应行消失，其他账号 / 其他会话的草稿不受影响；删书（`service.delete`）后草稿 `novel_id` 回到 NULL。
9. 自检：至少三条「坏实现」（去掉开关判断、去掉每轮限 1、`save_message` 不核对归属）用 monkeypatch 或源码副本证明相应断言会红。

`test_novel_chat_create_frontend.py`（参照 `test_novel_chat_frontend.py`：用 `test_claude_agent_frontend.render_card` 真渲染一张 `novel_draft` 卡，缺 node / 依赖时它会 skip，所以验收环境必须有 `frontend/node_modules`；其余为源码契约）：`useConversations.ts` 的 `novel_draft_id` 分支、`ChatCard` 的 `novel_draft` 分支与 `onOpenNovel` 透传、`page.tsx` 的 `openNovelAt` 正则与 `setDrawer("novel")`、`NovelWizard.tsx` 的 `draft` 参数读取与 `draft_id` 提交、`NovelDraftCard.tsx` 不含 `font-semibold|font-bold`；每条带一条坏副本自检。

## 5. 验收标准（执行者自跑；Claude 在沙箱外复跑并以自己的为准）

前提：worktree 里没有 `backend/.venv` 与 `frontend/node_modules`（都被 gitignore），派单前由派单方从主检出 `cp -cR` 进去；缺了前端渲染用例会 skip，而验收要求 `0 skipped`。pytest 一律加 `-p no:cacheprovider`。

1. `cd frontend && npx tsc --noEmit` 退出码 0。
2. `cd frontend && npm run lint` 0 errors（warnings ≤ 25）。
3. `cd frontend && npm run build` 退出码 0。
4. `cd backend && <pytest 全量>`：`0 failed`、`0 skipped`，`passed = 7863 + 新增用例数`（用 `--collect-only -q` 实数）。
5. HEAD 对照：`git archive HEAD` 到临时目录，只拷两个新测试文件进去跑：契约类用例在 HEAD 上必须 FAIL 且都是 `AssertionError`（不是 ImportError）。
6. 计数：`grep -c "draft_novel" backend/services/claude_agent.py` ≥ 3；`grep -c 'ALTER TABLE messages ADD COLUMN novel_draft_id' backend/database.py` = 1；`grep -c "FIONA_NOVEL_CHAT_CREATE" backend/studio/sources.py backend/.env.example CLAUDE.md` 各 ≥ 1；`head -c 3 frontend/app/page.tsx | xxd` = `efbb bf`。
7. 既有测试零 diff：`git diff HEAD --stat -- backend/tests ':!backend/tests/test_novel_chat_create*' ':!backend/tests/test_studio_sources_readonly_integration.py' ':!backend/tests/test_novel_p2_frontend.py'` 为空；`git diff -U0 HEAD -- backend/tests/test_novel_p2_frontend.py` 恰一个 hunk（`:40` 一行换三行）且该文件单独跑全绿（v1.2）；`grep -c 'src="/novels?embed=1"' frontend/app/page.tsx` = 0；`git diff -U0 HEAD -- backend/tests/test_studio_sources_readonly_integration.py` 恰两个 hunk（集合加一项；`novel.` 分支放行 `novel.drafts` 三个名字），且该文件单独跑全绿（v1.1）；`tests/test_novel_chat.py tests/test_song_agent_tools.py tests/test_claude_agent_runtime.py tests/test_claude_agent_docs.py tests/test_novel_p1_api.py tests/test_novel_v2_compat.py tests/test_novel_p21_frontend.py` 单独跑全绿。
8. 真实走查（Claude 在隔离环境做，不用 8010 / 3000）：开关全开、白名单账号、BYOK Claude 配好（没有真实 Key 时用假传输回放 `tool_use`）：聊天出草稿卡 → 点「去书斋建书」抽屉打开且向导第一步已填 → 向导建书成功 → 卡片变「已建书」→ 刷新页面卡片仍在；开关为 0 时请求体与 HEAD 逐字节相同。

## 6. 何时停下来问

只有「规格与源码事实矛盾」（行号对不上、`extra='forbid'` 之外还有阻止加字段的校验、删号钩子找不到）才停下来说明；只影响「怎么实现」的自行决定并在报告写明理由。任何情况不回滚已完成的工作。你实测到的事实优先于规格的断言，不符就停下来说明。
