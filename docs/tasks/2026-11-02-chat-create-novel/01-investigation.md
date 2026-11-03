以下事实以当前工作区 HEAD `0ca95af` 的源码为准；调查期间没有修改文件。当前 DSH 沙箱是 read-only，pytest 无法启动（详见 Q8），所以测试相关结论分「源码已核实」与「未实测」两类。工作区在 2026-11-02 23:51 新增了 `docs/tasks/2026-11-02-chat-create-novel/02-spec.md`；本事实表没有把它当代码证据，只把它当待核对的规格草稿。

## Q1 需求定位与调用链

F1.1 [已核实] Claude 客户端工具统一由 `_tool(name, description, properties, required)` 生成 `input_schema`；`CLAUDE_CLIENT_TOOLS` 固定为 5 个：`get_weather/plan_travel/plan_route/get_hot_topics/generate_image`。
  证据:`backend/services/claude_agent.py`:43-54

F1.2 [已核实] `client_tools_for_turn(ctx,state)` 先判断小说工具和写歌工具；两者都关闭时返回**同一个对象** `CLAUDE_CLIENT_TOOLS`，写歌开、小说关时返回「常量 + 4 个写歌工具」的新列表。
  证据:`backend/services/claude_agent.py`:70-92
```
if not novel_intents_enabled(...):
    if not song_enabled:
        return CLAUDE_CLIENT_TOOLS
    return _append_song_tools(CLAUDE_CLIENT_TOOLS)
```

F1.3 [已核实] 写歌工具开关是 `FIONA_SONG_AGENT` 只有字面 `1` 开启，并且用户名精确命中 `FIONA_SONG_USERS`；危机轮（`state.crisis` 或 `crisis_level`）不追加。四个工具是 `song_save_brief/song_save_lyrics/song_revise_section/song_get_status`。
  证据:`backend/song/config.py`:68-87，`backend/services/claude_agent.py`:57-67，`backend/song/tools.py`:133-204

F1.4 [已核实] 小说工具要求 `novel_intents_enabled(user, crisis)`：`FIONA_NOVEL_CHAT == "1"`、`FIONA_NOVEL == "1"`、用户名在 `FIONA_NOVEL_USERS`、非危机轮。基础工具是 `list_novels/read_novel`；只有 `gate.allow_studio(user, auth_method)` 为真才追加 `start_film`。三个工具都计入每轮上限。
  证据:`backend/intent_router.py`:157-162，`backend/studio/sources.py`:31-37，`backend/studio/gate.py`:15-22，`backend/services/claude_agent.py`:78-92

F1.5 [已核实] 工具执行循环按 `client_names` 找本轮第一个匹配的 `tool_use`；小说工具走 `_NOVEL_CLIENT_INTENTS`，先经 `_novel_tool_params` 校验，再用 `chat.run_slow(chat.execute_intent, ...)` 执行。未知工具不会进入通用分支。
  证据:`backend/services/claude_agent.py`:637-704
```
tool = next((item for item in content if item.get("type") == "tool_use" and item.get("name") in client_names), None)
...
elif name in _NOVEL_CLIENT_INTENTS:
    params, error = _novel_tool_params(name, args)
```

F1.6 [已核实] 小说工具返回 `{"type":"card"}` 时，卡片通过 `{"card": result, "append": True}` 立即追加；正文追加 `［卡片：…］` 摘要，`delivered=True`，不设置 `billable_pending`；否则把 `model_text/text` 作为工具结果回灌。
  证据:`backend/services/claude_agent.py`:696-704

F1.7 [已核实] 通用平台工具（天气/热榜/旅行/路线）走 `_tool_result_text`；工具结果以 `{"role":"user","content":[{"type":"tool_result","tool_use_id":...,"content":result_text}]}` 加入下一轮请求。
  证据:`backend/services/claude_agent.py`:247-273，`:820-821`

F1.8 [已核实] 每轮最多执行 4 次客户端工具（写歌、小说、生图、平台工具共用）；第 5 次不执行，只回 `本轮工具调用次数已用完，请直接回答主人`，并允许一次最终回答。
  证据:`backend/services/claude_agent.py`:644-647，`:817-821`；`backend/tests/test_claude_agent_runtime.py`:240-247；`backend/tests/test_novel_chat.py`:241-257

F1.9 [已核实] Claude 智能体入口条件：`FIONA_CLAUDE_AGENT` 非 `0`、`request_mode == "chat"`、无危机、BYOK 已启用且 `provider == "anthropic"`、无 `byok_error`、未触发 `byok_unreserved`。
  证据:`backend/services/chat_service.py`:281-295

F1.10 [已核实] 书斋建书 HTTP 门控：`FIONA_NOVEL` 不是字面 `1` 时 `workshop_user` 返回 404；用户名不在 `FIONA_NOVEL_USERS` 时返回 403。`POST /novels` 与 `POST /novels/estimate` 都是 `20/minute` 限流。
  证据:`backend/routers/novel.py`:12-18，`:29-38`

F1.11 [已核实] `service.create` 顺序是：`estimate`（内部 `validate_selection`）→ 预算下限校验 → 生成 config → `BEGIN IMMEDIATE` → `check_active` → 用户存在检查 → `INSERT ... status='setup_running'` → commit → `start_novel` → `detail`。HTTP 返回 201。
  证据:`backend/novel/service.py`:207-229

F1.12 [已核实] `start_novel` 在状态为 `setup_running`/`running` 且没有 `run_token` 时领 token，并 `create_background_task(_run(...))`；已有未完成任务时直接复用或等待，不重复起任务。`_run` 先等 `FIONA_NOVEL_MAX_RUNNING` 信号量，再 `_advance`。
  证据:`backend/novel/runner.py`:95-136，`:209-220`

F1.13 [已核实] 第一次付费步骤是 setup 的主编调用 `setup/steps/00-setup-editor.json`；`LLMRouter._attempt` 在请求厂商前调用 `NovelBilling.reserve` 预扣，成功后 `settle`，失败由 `_run` 的 `finally` 调 `refund_reserved()`。`DEV_MODE=1`、`byok:self`、`fake:` 免费。
  证据:`backend/novel/runner.py`:259-281，`:244-246`；`backend/novel/llm_router.py`:270-287`；`backend/novel/billing.py`:150-153，`:187-228`，`:275-296`

F1.14 [已核实] setup 完成后 `commit_setup` 把状态改为 `awaiting_setup`、写入 `title/compass/bible_version` 并清 `run_token`；用户 `setup/approve` 后 `_activate` 设为 `running` 并再次 `start_novel`，之后才进入逐章推演。
  证据:`backend/novel/store_db.py`:252-264；`backend/novel/service.py`:371-411，`:315-322`

F1.15 [已核实] 真实冒烟记录显示建书后 setup 预扣 68、实扣 9，说明「建书」本身就会触发付费 setup，而不是等到第一章。
  证据:`docs/tasks/2026-10-15-novel-workshop-p1/06-smoke.md`:18

F1.16 [已核实] 平台（非 Claude）小说意图由 `NOVEL_INTENTS = {"novel_list","novel_read","novel_to_film"}` 定义；`recognize_intent` 只在 `novel_intents_enabled` 为真时把 `NOVEL_INTENT_PROMPT` 拼进 system，`normalize_intent_result` 才把小说意图加入白名单。
  证据:`backend/intent_router.py`:142-162，`:445-472`，`:490-500`

F1.17 [已核实] 平台分发在 `execute_intent`：`novel_list`→`list_novels`，`novel_read`→`read_novel`（先查每日读额度，成功才 `hit=True`），`novel_to_film`→`start_film(..., auth_method)`；`_stream_novel_intent` 负责把结果写成 SSE 卡片或文本并保存。
  证据:`backend/services/chat_service.py`:569-618，`:1452-1496`

F1.18 [已核实] 平台「继续读」有独立短路：非危机、无本轮图片、消息匹配 `继续读|接着念` 时，从 `chat_slot_state` 取 30 分钟内本会话的续读位置，直接调 `stream_intent(novel_read)`。
  证据:`backend/services/chat_service.py`:1836-1841；`backend/intent_router.py`:164-197

## Q2 输入输出与分支

F2.1 [已核实] `CreateNovel` 全部字段：`seed_idea: str`（1–2000，去空白）、`agents: dict[str,str]`（3–9 个键）、`panel_mode: critique|solo`（默认 `critique`）、`automation: per_batch|per_chapter|full_auto`（默认 `per_batch`）、`batch_size: int`（默认 5，1–10）、`target: Target`、`adaptation: Adaptation`、`drama_adaptation: bool`（默认 false）、`structure: v1|v2`（默认 `v1`）、`budget_strawberries: int`（1–10,000,000）。`Input` 是 `extra='forbid'` 且 `str_strip_whitespace=True`。
  证据:`backend/novel/service.py`:39-41，`:60-70`

F2.2 [已核实] `Target` 默认 `min_chapters=50`、`max_chapters=70`、`chapter_words=2000`，范围分别是 1–200、1–200、1000–4000，并校验 `min <= max`；`Adaptation` 默认 `max_main_characters=6`（1–12）、`max_scenes_per_chapter=3`（1–10）。
  证据:`backend/novel/service.py`:43-58

F2.3 [已核实] `validate_selection` 要求 `editor/writer/archivist` 三个角色；拒绝未知角色；推演顾问最多 5 位；编辑/档案员/审校只允许 `JSON_MODELS`，写手只允许 `WRITER_MODELS`，顾问允许三种平台模型或 `byok:self`；出现 `byok:self` 时调用 `ByokBridge.describe()` 校验。
  证据:`backend/novel/service.py`:165-182

F2.4 [已核实] `estimate` 先 `validate_selection`，再读该用户最近 20 条 `status='ok' AND billing_status='settled'` 的步骤，交给 `estimate_cost`；返回 `per_chapter/chapter_range/book_range/total/method`。estimate 不检查余额，也不使用 `budget_strawberries`。
  证据:`backend/novel/service.py`:185-189；`backend/novel/billing.py`:89-140

F2.5 [已核实] `create` 的预算分支只有「`budget_strawberries < estimate.per_chapter.min` → 422」；它**不检查**用户余额、不检查每日建书次数、不查同名书。实际余额检查发生在 setup 的 `NovelBilling.reserve`。
  证据:`backend/novel/service.py`:208-210，`:220-228`；`backend/novel/billing.py`:199-213

F2.6 [已核实] 并发限制只在同一用户内：`check_active` 在 `BEGIN IMMEDIATE` 中查该用户是否已有 `running` 或 `setup_running` 的书，有则 409「每个用户同时只能运行一本小说」。两个并发 create 会被 SQLite 写锁串行化，第二个在第一个提交后看到 `setup_running` 而失败。
  证据:`backend/novel/service.py`:159-162，`:220-225`

F2.7 [已核实] `create` 没有每日上限；`FIONA_DAILY_NOVEL_CHAPTERS`（`novel_chapter`）只在 runner 的 `_advance` 中、setup 完成后检查，且 `DEV_MODE=1` 或关闭限流时跳过。
  证据:`backend/novel/runner.py`:305-307，`:358-367`；`backend/rate_limit.py`:79，`:155-165`

F2.8 [已核实] reserve 的实际预检是 `spent + reserved + amount >= budget * .8` 时抛 `NovelBudgetExceeded`；余额不足时 `UPDATE users ... WHERE strawberry_balance >= amount` 无返回行，抛 `InsufficientStrawberries`。因此预算刚好等于 `per_chapter.min` 时，第一笔 setup 仍可能因 80% 上限直接暂停。
  证据:`backend/novel/billing.py`:199-213

F2.9 [已核实] `create` 立即进入 `setup_running`，`start_novel` 是异步任务；HTTP 在模型调用前返回。若 setup 失败/预算不足/余额不足，`_run` 把书改为 `paused`（或 `failed`），`finally` 退还未结算的 reserved；已结算步骤不退。`create` 本身没有 try/except 退款。
  证据:`backend/novel/service.py`:220-229；`backend/novel/runner.py`:221-256；`backend/novel/billing.py`:275-296

F2.10 [已核实] `detail` = `summary` 字段（id/title/status/pause_reason/bible_version/chapters_done/words_done/budget/spent/reserved/created/updated/completed/max_chapters）+ `config` + `compass` + `bible`（经 `trim_bible` 裁剪）+ `chapters`（chapter/title/status/words/flags/edited_by_user）+ `pending_gate` + `pending_notes` + `last_error`。建书刚返回时 `title/compass/bible` 可能为 null，`chapters=[]`。
  证据:`backend/novel/service.py`:192-256

F2.11 [已核实] 前端 `NovelCreateInput` 有 `seed_idea/agents/panel_mode/automation/batch_size/target/adaptation/drama_adaptation?/budget_strawberries`，**没有** `structure`、`draft_id`、`title`；`createNovel` 就是 `POST /novels`。
  证据:`frontend/lib/novels.ts`:9-15，`:112-113`

F2.12 [已核实] 向导三步：①思路与篇幅（seed、最少/最多章、每章字数、改编短剧及参数）②智能体与模型（panel_mode、角色模型）③节奏与预算（automation、batch、budget、估算、余额、汇总）。默认 seed 空，50/70/2000，6/3，`critique`，`per_batch`，batch 5，budget 10000；`defaultNovelAgents` 默认 editor=qwen3.8-max、writer=deepseek-flash、archivist=qwen3.8-max、reviewer=qwen3.8-max，顾问 plot_architect/character_advocate/twist_designer。
  证据:`frontend/components/novel/NovelWizard.tsx`:20-38，`:56-69`

F2.13 [已核实] 必填与校验：step0 seed 1–2000、章数/字数/人物/场景整数范围、min≤max；step1 必须三基础角色、顾问≤5、模型在 catalog 可选项中；step2 budget 1–10,000,000 且不低于 `estimate.per_chapter.min`、batch 1–10。提交前会重跑三步校验，成功后 `router.push(novelHref('/novels/<id>', embedded))`。
  证据:`frontend/components/novel/NovelWizard.tsx`:119-161

## Q3 既有测试怎样搭环境

F3.1 [已核实] `backend/tests/conftest.py` 在收集阶段设 `FIONA_DB_PATH/FIONA_UPLOADS_DIR/FIONA_STUDIO_DIR` 到 `tempfile.TemporaryDirectory`，设占位 `JWT_SECRET`、`DASHSCOPE_API_KEY`，默认 `FIONA_CLAUDE_AGENT=0`、`FIONA_NOVEL_CHAT=0`，并把 `FIONA_CHAT_IMAGE_TOOL=0`；`client` fixture 再用 `tmp_path/test.db` 和 `DEV_MODE=1`，进入 `TestClient` 触发 `init_db()`。
  证据:`backend/tests/conftest.py`:18-41，`:91-140`

F3.2 [已核实] `test_novel_chat.py` 的 `offline` 阻断 IPv4/IPv6 连接和 DNS；`enabled` 设 `FIONA_NOVEL_CHAT=1/FIONA_NOVEL=1/FIONA_NOVEL_USERS="author, agent-user"/FIONA_STUDIO=1/FIONA_STUDIO_OWNERS=.../FIONA_STUDIO_REQUIRE_JWT=1`；`catalog` 用 monkeypatch 替换 `sources.list_candidates/find_candidates/_novel_call`，不碰真实小说库。
  证据:`backend/tests/test_novel_chat.py`:15-58

F3.3 [已核实] `test_claude_agent_runtime.py` 提供 `message(stop="end_turn", *, content=None, text="", usage=None)`、`call(name, arguments=None, identity="tool-1")`、`FakeStream(final, text="", failure=None)`、`harness(monkeypatch)`、`run(h)`。`harness` 替换 `agent.open_agent_stream`、`chat.execute_intent`、`chat._save_response`、`chat.detect_mode`、`get_pending` 等，记录 `requests/executions/caps/saves`，并把 `_BYOK_USERS` 清空。
  证据:`backend/tests/test_claude_agent_runtime.py`:32-116

F3.4 [已核实] 模拟 tool_use 的方式是：`h.streams.extend([FakeStream(message("tool_use", content=[call("read_novel", {...})])), FakeStream(message(text="..."), "...")])`；第二轮请求的 `h.requests[1][0][-1]["content"][0]` 就是 `tool_result`，断言 `type/content`。
  证据:`backend/tests/test_novel_chat.py`:192-221，`:241-257`

F3.5 [已核实] `test_novel_p1_api.py` 用 `client` fixture（DEV_MODE=1）搭 HTTP 环境，`workshop` 设 `FIONA_NOVEL/FIONA_NOVEL_USERS`、关 limiter，并把 `runner.router_factory` 换成 `LLMRouter(store, dry_run=True, fake=FakeLLM())`；`wait()` 每 10ms 轮询 detail 直到目标状态，`create()` 断言 201 并等到 `awaiting_setup`。
  证据:`backend/tests/test_novel_p1_api.py`:23-56

F3.6 [已核实] `test_novel_p1_billing.py` 不用 TestClient：`_book()` 把 `database.DB_PATH` 指到 `tmp_path`，`init_db` 后建用户和一本 `running` 书，返回 `DbStepStore/NovelBilling`；`_call()` 构造步骤；`_snapshot()` 读 `novels/users/novel_steps`。模块 autouse 设 `DEV_MODE=0`、`STRAWBERRY_DAILY_REFILL=0`、清价格覆盖并封 TCP。
  证据:`backend/tests/test_novel_p1_billing.py`:21-58

F3.7 [已核实] 断言请求体工具表：runtime 直接断言 `CLAUDE_CLIENT_TOOLS` 名字集合为 5 个；novel chat 断言 `client_tools_for_turn` 与常量的差集**恰为** `{list_novels,read_novel[,start_film]}` 且全关时 `tools is CLAUDE_CLIENT_TOOLS`；SKD 测试在 `open_agent_stream` 的 `calls[0]["tools"]` 中断言客户端工具 + 服务端 `web_search/web_fetch`。
  证据:`backend/tests/test_claude_agent_runtime.py`:118-123`；`backend/tests/test_novel_chat.py`:180-190，`:259-287`；`backend/tests/test_claude_agent_client.py`:139-172

F3.8 [已核实] `test_song_agent_tools.py` 在关开关时断言 `client_tools_for_turn(h.ctx,h.state) is agent.CLAUDE_CLIENT_TOOLS`、请求 `kwargs["tools"] is ...`，开开关且白名单命中时断言工具名集合恰为 5+4=9。
  证据:`backend/tests/test_song_agent_tools.py`:689-696，`:750-755

F3.9 [已核实] 测试环境有 session 级临时目录和 `tmp_path`；当前 read-only 沙箱下 pytest 连收集都失败，见 Q8，未能实测上述用例。
  证据:本回答 Q8 的实测输出

## Q4 现状与需求的差距

F4.1 [已核实] 现有「聊天→书斋」只有侧栏「书斋」入口和常驻 iframe：`Sidebar` 的 `/novels` 映射 `novel-drawer`，主页 iframe 固定 `src="/novels?embed=1"`；聊天正文/卡片没有到 `/novels/[id]` 的入口。
  证据:`frontend/components/Sidebar.tsx`:21，`:118`；`frontend/app/page.tsx`:2467-2468，`:2961`

F4.2 [已核实] 聊天能触达小说工坊的路径只有 Claude 的 `list_novels/read_novel` 和平台的 `novel_list/novel_read`；`start_film/novel_to_film` 是「小说→短片工作室」，不是「聊天→小说」。
  证据:`backend/services/claude_agent.py`:78-92；`backend/intent_router.py`:142-153；`backend/studio/novel_chat.py`:116-134

F4.3 [已核实] 缺口一：没有 `draft_novel`/`create_novel` 工具定义或参数映射；`_novel_tool_params` 只处理 `list_novels/read_novel`，没有对 `title/seed_idea/target` 的清洗与默认值。
  证据:`backend/services/claude_agent.py`:95-110；`rg -n 'draft_novel|novel_create' backend frontend` → 0（代码）

F4.4 [已核实] 缺口二：`CreateNovel` 没有 `title`、人物、brief 字段，只有 `seed_idea`（≤2000）；`novels` 表也没有 brief/人物列。聊天里定下的书名和人物只能压进 `seed_idea`，书名要等 setup/审阅后才由 `compass['title']` 写入。
  证据:`backend/novel/service.py`:60-70，`:211-225`；`backend/novel/store_db.py`:22-33，`:252-264`

F4.5 [已核实] 缺口三：没有服务端默认智能体/预算/目标值。向导的 `defaultNovelAgents` 和默认 50/70/2000、budget 10000 只存在于前端组件；聊天工具若直接调用 `service.create`，必须自己另造一份默认值。
  证据:`frontend/components/novel/NovelWizard.tsx`:20-38，`:56-69`；`rg -n 'defaultNovelAgents' backend` → 0

F4.6 [已核实] 缺口四：没有小说卡片。`ChatCard` 只处理 `song_project/studio_project/weather/web_sources`；`page.tsx` 卡片事件只复制 `source/points/url/error/subtype/project_id/weather/items/sources`，没有 `novel_draft_id/draft_id`。
  证据:`frontend/components/ChatBubble.tsx`:90-127；`frontend/app/page.tsx`:2144-2170

F4.7 [已核实] 缺口五：`messages` 没有小说引用列；`useConversations.toMessages` 只按 `song_project_id` 重建 `song_project` 卡，刷新后小说卡片只剩正文里的 `［卡片：…］` 摘要。
  证据:`backend/database.py`:129-145，`:550-565`；`frontend/lib/useConversations.ts`:10-17，`:60-69`

F4.8 [已核实] 缺口六：没有父页向书斋 iframe 导航的机制。父页只处理 iframe 发来的 `fiona-novel-open-settings`/`fiona-novel-close`，没有 `novelFrameRef.current.src = ...` 或 `contentWindow.postMessage`。
  证据:`frontend/app/page.tsx`:531-545；`rg -n 'novelFrameRef\.current\.src|contentWindow\?\.postMessage' frontend/app/page.tsx` → 0

F4.9 [已核实] 缺口七：文档没有「聊天建书」；`rg -n '聊天建书|建书工具' README.md CLAUDE.md PLAN.md docs backend frontend --glob '!**/__pycache__/**' --glob '!frontend/node_modules/**'` 只命中调查提示和刚出现的规格草稿，没有正式文档。
  证据:上述 `rg` 的命中只有 `docs/tasks/2026-11-02-chat-create-novel/00-investigation-prompt.md:1` 与 `02-spec.md:1`

## Q5 辅助函数与夹具

F5.1 [已核实] `message(stop="end_turn", *, content=None, text="", usage=None)`、`call(name, arguments=None, identity="tool-1")`、`FakeStream(final, text="", failure=None)`、`run(h)` 都在 `test_claude_agent_runtime.py`，是模块级函数/类，可被其他测试 `from test_claude_agent_runtime import ...` 导入；`harness` 是 pytest fixture，只能通过参数注入，不能直接 import 调用。
  证据:`backend/tests/test_claude_agent_runtime.py`:32-116；`backend/tests/test_novel_chat.py`:12

F5.2 [已核实] `test_claude_agent_routing.py` 提供 `context(**kwargs)`（构造 `ChatContext`）、`parse(events)`（解析 SSE）、`isolate(monkeypatch)`（替换保存/日志/退款/模式/意图，返回 `chat,saved,traces,refunded`）、`collect(iterator)`（异步收集）。均为模块级，可导入。
  证据:`backend/tests/test_claude_agent_routing.py`:27-91

F5.3 [已核实] `test_claude_agent_client.py` 提供 `config(model="claude-opus-5-5", effort="low")`、`messages()`、`sse(blocks=None, stop="end_turn", *, server_usage=None)`、`install_sdk(monkeypatch, response=None)`、`consume_agent(monkeypatch, *, settings=None, history=None, response=None, deadline=90)`。
  证据:`backend/tests/test_claude_agent_client.py`:55-135

F5.4 [已核实] `test_song_agent_tools.py` 提供 `song_db` fixture、`_brief(**overrides)`、`_new_conversation(username="owner")`、`_seed_project(username, conversation_id, *, title="夏日信", with_lyrics=True)`、`_save_brief_args(*, project_id=None, **overrides)`、`_run_tool(...)`、`_project_count()`；均是模块级。
  证据:`backend/tests/test_song_agent_tools.py`:89-202

F5.5 [已核实] `test_novel_p1_api.py` 提供 `payload(chapters=3, mode='critique', automation='per_batch', batch=5)`、`workshop(client, monkeypatch)`、`wait(client, book, state, headers=HEADERS)`、`create(client, **kwargs)`、`approve(client, book)`；`test_novel_p1_billing.py` 提供 `_book/_call/_snapshot/_runner_book/_run_to_gate/_drain_runner`。
  证据:`backend/tests/test_novel_p1_api.py`:17-56；`backend/tests/test_novel_p1_billing.py`:32-58，`:279-321

F5.6 [已核实] `test_claude_agent_frontend.py` 提供 `run_cards(events)`、`require_rendering_dependencies()`、`render_card(card)`；`test_novel_chat_frontend.py` 直接 `from test_claude_agent_frontend import render_card as render_shared_card`。这三个函数在缺 node/依赖时会 `pytest.skip`。
  证据:`backend/tests/test_claude_agent_frontend.py`:54-183；`backend/tests/test_novel_chat_frontend.py`:7-19

F5.7 [已核实] `backend/tests` 没有 `__init__.py`，但这些测试模块没有定义 `__all__`，所以模块级函数/类都可按模块名导入；pytest fixture 不是普通可导入对象，只能注入。
  证据:`ls backend/tests/__init__.py` → 不存在；`grep -n '__all__' backend/tests/test_claude_agent_runtime.py backend/tests/test_song_agent_tools.py` → 0

## Q6 导入、导出、构建与测试收集

F6.1 [已核实] 后端新测试放在 `backend/tests/test_*.py`，从 `backend/` 运行 `python -m pytest` 即自动收集；新业务模块放在 `backend/novel/`、`backend/studio/` 等包内即可导入。只有新增 HTTP 路由才需要在 `backend/main.py` 注册 router（现有 novel router 已注册）。
  证据:`backend/main.py`:201；`backend/tests/conftest.py`:1-41

F6.2 [已核实] 前端没有 test runner，`frontend/package.json` 只有 `dev/dev:lan/build/start/lint`；前端测试实际是 `backend/tests/test_*_frontend.py` 的源码契约或 Node SSR。新组件放 `frontend/components/`，类型/请求放 `frontend/lib/`，`tsc` 的 `include` 覆盖 `**/*.ts`、`**/*.tsx`。
  证据:`frontend/package.json`:6-13；`frontend/tsconfig.json`:24-38

F6.3 [已核实] 后端测试命令：`env -u HTTP_PROXY ... backend/.venv/bin/python -m pytest -q -p no:cacheprovider <文件>`；CI 是 `cd backend && python -m pytest -q`。前端类型检查：`cd frontend && npx tsc --noEmit`；lint：`npm run lint`（CI 用 `npm run lint -- --max-warnings=38`）；build：`npm run build`。
  证据:`.github/workflows/quality.yml`:31-60；本任务给定的运行命令

F6.4 [已核实] `CLAUDE_CLIENT_TOOLS` 恰好 5 个的名字集合被 `test_claude_agent_runtime.py` 锁定：
  证据:`backend/tests/test_claude_agent_runtime.py`:118-123
```
assert {tool["name"] for tool in tools} == {"get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image"}
assert all("eager_input_streaming" not in tool for tool in tools)
```

F6.5 [已核实] 同一 5 个名字集合和「小说工具差集恰为两个/三个」被 `test_novel_chat.py` 锁定；新增 `draft_novel` 若挂在现有小说分支下，会直接打破这个集合断言。
  证据:`backend/tests/test_novel_chat.py`:180-190
```
assert {tool["name"] for tool in tools} - {tool["name"] for tool in CLAUDE_CLIENT_TOOLS} == expected
assert {tool["name"] for tool in CLAUDE_CLIENT_TOOLS} == {"get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image"}
if not expected:
    assert tools is CLAUDE_CLIENT_TOOLS
```

F6.6 [已核实] 写歌测试锁定「全关 5 个」「写歌开 9 个」；新增工具若只在独立开关下追加，现有这两组断言可保持不变。
  证据:`backend/tests/test_song_agent_tools.py`:689-696，`:750-755

F6.7 [已核实] 文档测试 `test_claude_agent_docs.py` 对 `README.md/CLAUDE.md/PLAN.md/docs/ARCHITECTURE.md/docs/DEPLOYMENT.md/backend/.env.example` 逐字要求「Claude 智能体模式」「4 次」「240 秒」「8000 字」「卡片不落库」「历史图片」等短语；它**不**断言 `CLAUDE_CLIENT_TOOLS` 是 5 个，但文档正文目前都写了 5 个。
  证据:`backend/tests/test_claude_agent_docs.py`:12-48；`README.md`:146；`CLAUDE.md`:18，`:168`；`docs/ARCHITECTURE.md`:9；`docs/DEPLOYMENT.md`:245，`:892`；`PLAN.md`:483

F6.8 [已核实] 新增 `draft_id` 到 `CreateNovel` 不会破坏现有「`volume_gate` 不在 model_fields」测试；前端 `NovelCreateInput` 加可选字段也不会破坏现有向导源码断言，但 `NovelWizard.tsx` 的既有文案/行必须逐字保留。
  证据:`backend/tests/test_novel_v2_compat.py`:113-122；`backend/tests/test_novel_p21_frontend.py`:32-48

## Q7 数据与状态

F7.1 [已核实] `messages` 表基础列是 `id/username/role/content/image_path/created_at`；迁移补 `reference_image_paths/image_summary/song_project_id`，`agent_store.init` 再补 `conversation_id/agent_id`。没有 `novel_id` 或 `novel_draft_id`。
  证据:`backend/database.py`:129-145；`backend/agent_store.py`:150-158

F7.2 [已核实] 写歌卡片写入：`deliver_song_card()` 把 `card["project_id"]` 写进 `state.song_project_id`，`_save_response` 透传给 `save_message`；`save_message` 只在 `song_projects` 中该 id 属于本人且 `conversation_id` 匹配时才存，否则存 NULL，且查询异常也存 NULL、不让消息落库失败。
  证据:`backend/services/claude_agent.py`:481-485；`backend/services/chat_service.py`:977；`backend/database.py`:550-563

F7.3 [已核实] 刷新重建：`agent_store.get_conversation_messages` 的 SELECT 带 `song_project_id`；`useConversations.toMessages` 在 `message.role === "assistant" && message.song_project_id` 时生成 `{source:"写歌", subtype:"song_project", project_id}`；`ChatCard` 渲染 `SongProjectCard`。
  证据:`backend/agent_store.py`:338-345；`frontend/lib/useConversations.ts`:60-69；`frontend/components/ChatBubble.tsx`:118-126

F7.4 [已核实] 小说没有对应列时，`novel_read` 只把正文/错误文本写进 `state.full_response`；`novel_list` 也只是文本；`start_film/novel_to_film` 的卡片只把 `_summarize_card_for_history` 的 `[短片工作室] + points` 写进正文，URL 不进数据库，刷新后无法重建卡片。Claude 的 `read_novel` 工具结果只回灌给模型，不落库。
  证据:`backend/services/chat_service.py`:493-527，`:1472-1478`；`backend/services/claude_agent.py`:696-702

F7.5 [已核实] `novels` 表结构：`id TEXT PK, username, title（可空）, seed_idea, status, pause_reason, config_json, compass_json, bible_version, chapters_done, words_done, budget_strawberries, spent_strawberries, reserved_strawberries, run_token, created_at, updated_at, completed_at`；没有 brief、人物、draft 列。
  证据:`backend/novel/store_db.py`:22-33

F7.6 [已核实] 删号：`delete_account_data` 先 `cancel_user_tasks`，在同一事务里删 `novel_*` 和 `novels`、`messages`、会话等；删会话：`agent_store.delete_conversation` 只删该会话 `messages`、会话行和该会话的写歌数据，**不删 novels**；清空历史：`clear_message_history` 删全用户 `messages` 和写歌数据，**不删 novels**。
  证据:`backend/database.py`:826-934，`:470-487`；`backend/agent_store.py`:354-381

F7.7 [已核实] 单本删除 `service.delete` 会 `cancel_novel` 后删 `novel_notes/novel_steps/novel_chapters/novel_bible_versions/novels`；它不会清理任何聊天消息里的引用（因为现在没有引用列）。
  证据:`backend/novel/service.py`:768-778

F7.8 [已核实] 因此，若新增 `messages.novel_draft_id`：删会话/清空历史/删号必须同步删 `novel_drafts`；单本删书时若草稿的 `novel_id` 已指向该书，现有代码不会回写草稿，卡片可能出现「已建书」但链接 404。这是新表需要额外决定的分支。
  证据:`backend/database.py`:470-487，`:931`；`backend/agent_store.py`:354-381；`backend/novel/service.py`:768-778

## Q8 运行环境与沙箱限制

F8.1 [已核实] 当前 read-only 沙箱下，普通 pytest 在启动 capture 时失败：`FileNotFoundError: [Errno 2] No usable temporary directory found in ['/var/folders/.../T/', '/tmp', '/var/tmp', '/usr/tmp', ...]`。加 `-s` 后仍在 `tests/conftest.py:23` 的 `tempfile.TemporaryDirectory` 失败。没有测试真正开始，故没有 skip/fail 统计。
  证据:实测 `backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_chat.py` 与 `-s` 的输出

F8.2 [已核实] 普通 `cd frontend && npx tsc --noEmit` 在 read-only 下报 `error TS5033: Could not write file '.../frontend/tsconfig.tsbuildinfo': EPERM`。加 `--incremental false` 后退出码 0（实测）。`tsconfig.tsbuildinfo` 被 `frontend/.gitignore` 忽略，不属于源码。
  证据:实测输出；`frontend/.gitignore`:40；`frontend/tsconfig.json`:19

F8.3 [已核实] `npx eslint app components lib --max-warnings=0` 可运行，0 errors、25 warnings，退出 1 仅因 `--max-warnings=0`；CI 的阈值是 38，所以现有 CI 不会因这 25 条失败。
  证据:实测输出；`.github/workflows/quality.yml`:55-57

F8.4 [已核实] 前端 SSR/卡片测试的 skip 条件：`render_card` 先 probe `typescript/react/react-dom/server`，缺包或没有 node 就 `pytest.skip("frontend dependencies unavailable: ...")` / `"node is unavailable"`；`test_novel_chat_frontend.py` 也有一层相同的 probe。工作区没有 `node_modules` 时这些用例会 skip 而不是红。
  证据:`backend/tests/test_claude_agent_frontend.py`:140-158；`backend/tests/test_novel_chat_frontend.py`:12-19

F8.5 [已核实] `backend/.venv/`、`frontend/node_modules/`、`frontend/tsconfig.tsbuildinfo` 都被 gitignore；新建 worktree 只 checkout 源码，不会带这些构建产物。worktree 下直接跑 `.venv/bin/python` 会找不到解释器，前端 SSR 测试会 skip，`npx tsc` 因缺 `node_modules` 失败或触发 npx 联网安装。
  证据:`git check-ignore -v backend/.venv frontend/node_modules frontend/tsconfig.tsbuildinfo`；`.gitignore`:17；`frontend/.gitignore`:4，`:40`

F8.6 [推断] 在 workspace-write 下，`tempfile` 与 `tsconfig.tsbuildinfo` 可写，pytest 和 tsc 应能正常启动；但 `-p no:cacheprovider` 仍应保留以避免写 `.pytest_cache`，且全量验收要求 `0 skipped`，必须准备 `frontend/node_modules` 和 `node`，否则前端渲染用例会被 skip。
  证据:上述失败条件与 skip 条件；未在 workspace-write 实测

## Q9 平台行为

F9.1 [已核实] 主页书斋是常驻抽屉 `#novel-drawer`，内部 iframe 固定 `src="/novels?embed=1"`；关闭时保留 iframe 状态。
  证据:`frontend/app/page.tsx`:2934-2962

F9.2 [已核实] 父页对书斋 iframe 只处理两种消息：`fiona-novel-open-settings`（切到设置抽屉）和 `fiona-novel-close`（关书斋并回焦触发按钮）；没有「打开某本书」的消息。
  证据:`frontend/app/page.tsx`:531-545

F9.3 [已核实] `novelHref(path, embedded)` 只负责在路径后追加 `?embed=1` 或 `&embed=1`；它被书架、工作台、向导使用，聊天页和 `ChatBubble/useConversations` 没有使用。
  证据:`frontend/lib/novels.ts`:161；`rg -n 'novelHref' frontend/app/page.tsx frontend/components/ChatBubble.tsx frontend/lib/useConversations.ts` → 0

F9.4 [已核实] 聊天里的 `studio_project` 卡是普通 `<a href="/studio/...">打开工作室</a>`，不是抽屉；URL 只接受 `/studio/` 开头且字符集 `[A-Za-z0-9/_-]`。
  证据:`frontend/components/ChatBubble.tsx`:108-126

F9.5 [已核实] `NovelFilmDialog`（小说工作台内）用 `router.push(studioHref('/studio/<id>', embedded))` 跳转；它是在书斋 iframe 内导航到工作室路径，不打开工作室抽屉。
  证据:`frontend/components/novel/NovelFilmDialog.tsx`:32-34；`frontend/lib/studio.ts`:114

F9.6 [已核实] 工作室提醒 chip 只调用 `handleSelectConversation(notice.conversation_id)` 切会话，不打开书斋/工作室抽屉。
  证据:`frontend/app/page.tsx`:2626-2632

F9.7 [已核实] `data-shell` 只在嵌入页（`embed=1` 且 `window.parent !== window`）由父窗口 `matchMedia("(min-width: 768px)")` 设置/移除；CSS 用 `:root:not([data-shell="desktop"])` 切移动布局。新建/工作台的 `embed` 参数必须保留。
  证据:`frontend/app/layout.tsx`:70-77；`frontend/app/globals.css`:10`；`frontend/app/novels/page.tsx`:8-10

## Q10 恒真风险

F10.1 [推断] 只测「开关打开时 `draft_novel` 在工具表里」会漏掉无条件追加：若工具被加到 `CLAUDE_CLIENT_TOOLS`，打开时也在、关闭时也在，正向断言仍绿。必须同时测 `FIONA_NOVEL_CHAT_CREATE=0/未设/true`、`FIONA_NOVEL_CHAT`、白名单、危机四组，并断言关闭时 `is CLAUDE_CLIENT_TOOLS`。
  证据:`backend/services/claude_agent.py`:70-92；`backend/tests/test_novel_chat.py`:180-190

F10.2 [推断] `assert h.state.billable is False` 对「不扣费」是**恒真假阳性**：`billable` 只由 `_tool_billable` 和图片成功设置，小说/写歌分支本来就不设；即使实现偷偷调 `service.create` 触发 setup reserve，这个值仍是 False。必须查 `users.strawberry_balance`、`novels` 行、`novel_steps` 或 runner 任务。
  证据:`backend/services/claude_agent.py`:696-704，`:812-816`；`backend/services/chat_service.py`:113-118

F10.3 [推断] 在 `DEV_MODE=1` 或全 `byok:self`/`fake:` 下断言余额不变也是恒真：`NovelBilling.is_free` 直接返回 0；只测余额会放过「调了 service.create 但免费」的实现。必须同时用平台模型、`DEV_MODE=0`、`STRAWBERRY_DAILY_REFILL=0`，并断言没有新书/没有 setup 请求。
  证据:`backend/novel/billing.py`:150-153；`backend/tests/conftest.py`:95

F10.4 [推断] `service.create` 先插行、再异步 `start_novel`；工具调用返回后立即查余额，可能还没 reserve。只测「调用后余额不变」会因竞态假绿。要等 `runner.TASKS` 完成或查 `novels.status/novel_steps`。
  证据:`backend/novel/service.py`:220-229；`backend/novel/runner.py`:95-136

F10.5 [推断] 只断言 SSE 里有一张 `novel_draft` 卡、或只断言正文含 `［卡片：`，不能证明刷新后仍在；`state.full_response += ［卡片：…］` 与 `messages.novel_draft_id` 是两件事。要跑真实 `_save_response` → `agent_store.get_conversation_messages` → 断言 `novel_draft_id`，再断言前端 `toMessages` 能重建。
  证据:`backend/services/claude_agent.py`:696-700；`backend/database.py`:550-565；`frontend/lib/useConversations.ts`:60-69

F10.6 [推断] 只断言工具 schema 的 `maxLength/minimum` 不代表服务端校验：Anthropic 可能给出字符串、`True`、越界整数。必须用 `True`/`"50"`/`1.5`/空串/超 60 字/超 2000 字/`min>max` 做实际 `execute`，断言返回文本、`agent_tool_errors` +1、`novel_drafts` 行数不变。
  证据:`backend/services/claude_agent.py`:95-110，`:773-790`（现有 read 的 `type(...) is int` 校验是正确样例）

F10.7 [推断] 前端只做源码正则（例如 `assert "novel_draft" in source`）会放过死代码/不可达分支；而 `render_card` 缺 `node_modules` 会 skip，不是绿。必须让 `render_card` 真正渲染 `novel_draft` 卡，并让 `toMessages` 的映射可执行（当前它是未导出的内部函数，需决定是否导出或用等价运行时断言）。
  证据:`backend/tests/test_claude_agent_frontend.py`:140-183；`frontend/lib/useConversations.ts`:60-69

F10.8 [推断] 只断言 `len(CLAUDE_CLIENT_TOOLS)==5` 不能证明「新工具按轮追加」：新工具加在动态列表里时仍是 5；反过来，加进常量时变 6，能抓住一种坏实现，抓不住另一种。必须同时断言常量名字集合不变、请求 `tools` 名字集合恰好多 `draft_novel`。
  证据:`backend/tests/test_claude_agent_runtime.py`:119-123；`backend/tests/test_novel_chat.py`:185-188

## Q11 区分力怎么证明

以下变异都以「正确实现应绿、变异后对应断言应红」为目标；标 [推断] 因为新测试尚未写。

F11.1 [推断] 变异：在 `client_tools_for_turn` 的新增 `tools.append(NOVEL_DRAFT_TOOL)` 处去掉 `novel_create_enabled`/`novel_intents_enabled` 条件。期望红：开关 0/未设/白名单外/危机轮的 `client_tools_for_turn` 集合与对象同一性测试。
  目标:`backend/services/claude_agent.py`:70-92

F11.2 [推断] 变异：把 `novel_create_enabled` 写成只看 `FIONA_NOVEL_CHAT_CREATE`，漏掉 `novel_chat_enabled(user)` 或漏掉 `crisis`。期望红：`FIONA_NOVEL=0`、用户不在白名单、`crisis_level="possible"` 三组。
  目标:`backend/studio/sources.py`:31-37` 附近新增函数；`backend/intent_router.py`:157-162

F11.3 [推断] 变异：在 `claude_agent.py:644` 把 `tools_executed >= 4` 改成 `>= 5`。期望红：`test_novel_tools_retain_four_call_budget` 的 4 次执行、第 5 次 `_TOOL_LIMIT_RESULT`。
  目标:`backend/services/claude_agent.py`:644-647

F11.4 [推断] 变异：把小说工具分支的 `yield chat._sse({"card": result, "append": True})` 改成 `append=False` 或不发。期望红：事件序列测试（append 卡不覆盖文字、卡片只追加一次）。
  目标:`backend/services/claude_agent.py`:696-700

F11.5 [推断] 变异：在 `save_message` 中删掉 `novel_drafts` 的 owner/conversation 核对，直接写入。期望红：别人的草稿、别的会话的草稿存成 NULL 的测试。
  目标:`backend/database.py`:550-563` 的同类校验位置

F11.6 [推断] 变异：`create` 的 `config = data.model_dump(exclude={'draft_id'})` 改成 `data.model_dump()`。期望红：`detail.config` 不含 `draft_id` 的向后兼容断言。
  目标:`backend/novel/service.py`:211

F11.7 [推断] 变异：`create` 中插入 novels 后不调用 `consume_draft`，或先 commit 再消费。期望红：同一 `draft_id` 第二次 422、`novels` 行数不变的测试；事务回滚测试。
  目标:`backend/novel/service.py`:220-228

F11.8 [推断] 变异：`useConversations.toMessages` 删除 `message.novel_draft_id` 分支。期望红：刷新重建测试（DB 消息 → cards 含 `novel_draft`）。
  目标:`frontend/lib/useConversations.ts`:60-69

F11.9 [推断] 变异：`ChatCard` 删除 `subtype === "novel_draft"` 分支。期望红：`render_card` 渲染出 `NovelDraftCard`/按钮的测试。
  目标:`frontend/components/ChatBubble.tsx`:90-127

F11.10 [推断] 变异：`page.tsx` 的 `openNovelAt` 只 `setDrawer("novel")` 不设 iframe `src`，或去掉正则白名单。期望红：打开后 `novelFrameSrc` 不等于目标路径；`javascript:`/外部 URL 不改变 src 的测试。
  目标:`frontend/app/page.tsx`:2934-2962` 与新函数

F11.11 [推断] 变异：`NovelWizard` 不读 `draft` 参数或不把 `draft_id` 传给 `createNovel`。期望红：预填 seed/target 的测试；提交请求含 `draft_id` 的测试。
  目标:`frontend/components/novel/NovelWizard.tsx`:41，`:56-69`，`:151-161

F11.12 [推断] 变异：`count_open_drafts` 的阈值写成 `> 50` 而不是 `>= 50`。期望红：50 份未消费草稿时拒绝的边界测试。
  目标:新 `backend/novel/drafts.py`（尚不存在）

## Q12 其他规格作者需要知道

F12.1 [已核实] 每轮 4 次客户端工具是硬编码；整轮预算默认 240 秒，`FIONA_CLAUDE_AGENT_TOTAL_SECONDS` 合法 60–290，非法回落 240；每次请求取剩余预算与 BYOK 时限较小值；可见文字累计 8000、单次 4000。
  证据:`backend/services/claude_agent.py`:113-118，`:644-647`；`backend/byok/client.py`:474；`CLAUDE.md`:18

F12.2 [已核实] 工具结果没有统一的字符截断：`result_text` 直接作为 `tool_result.content`；相关上限只有 `read_novel` 的 6000 字正文、`_tool_result_text` 的 points 最多 15 条、以及模型输出的 `character_limit=4000`。新工具回灌标题/两行 points 不会触及上限。
  证据:`backend/services/claude_agent.py`:247-273，`:820-821`；`backend/studio/novel_chat.py`:76；`backend/byok/client.py`:474

F12.3 [已核实] 提示前缀缓存：`_prepare_agent_messages` 把 system 重排为「前缀 + `CLAUDE_TOOL_INSTRUCTIONS` + 安全规则」，给 system 和最后一条 user 内容块加 `cache_control: {"type":"ephemeral"}`。新增固定提示词会改变 system 前缀，新增工具会改变 `tools` 数组；两者都会让该轮缓存失效。
  证据:`backend/byok/client.py`:415-428；`backend/tests/test_claude_agent_client.py`:139-158

F12.4 [已核实] 既有逐字节断言：`test_novel_chat.py` 比较小说开关 0 与 1 两次请求的 `{"messages", "tools"}` 序列化字节、SSE、保存内容和退款；`test_song_agent_tools.py` 比较写歌关闭时 system 与请求。新开关默认 0、且不改关闭路径，才能保住这些断言。
  证据:`backend/tests/test_novel_chat.py`:259-287；`backend/tests/test_song_agent_tools.py`:680-707

F12.5 [已核实] 隐私：建书参数（书名、seed、人物）作为 Claude 的 `tool_use.input` 属于本轮发给 Anthropic 的内容；如果只写草稿，不会调用平台小说模型；如果误调 `service.create`，`seed_idea` 会写入 `novels.seed_idea` 并作为 setup 提示发给主编模型（阿里云百炼/DeepSeek/火山方舟/用户 BYOK Anthropic）。`novel_steps` 只存请求摘要，不存提示词。
  证据:`backend/novel/billing.py`:215-224；`backend/novel/service.py`:225`；`README.md`:347；`CLAUDE.md`:164

F12.6 [已核实] 六份文档的同步点：`CLAUDE.md` 的 Claude 智能体段（15-18）、小说工坊段（164）、聊天读小说段（194）；`README.md` 的 Claude 段（130）、写歌段（146）、小说工坊段（333-357）；`docs/ARCHITECTURE.md` 的总览（9）、小说聊天（412）、隐私（398）；`docs/DEPLOYMENT.md` 的 Claude 段（245、251、892）；`PLAN.md` 的写歌段（483）；`backend/.env.example` 的 Claude/写歌/小说段（27-30、54、205-214）。
  证据:上列各文件行号

F12.7 [已核实] `test_claude_agent_docs.py` 要求每份文档都含字面「卡片不落库」。若新草稿卡要落库，文档必须保留这个子串，例如写成「其余卡片不落库；写歌卡和书斋草稿卡例外」，不能改成「卡片一般不落库」（会拆断子串）。
  证据:`backend/tests/test_claude_agent_docs.py`:37-48

F12.8 [已核实] 新开关若要加环境变量，`backend/.env.example` 目前没有 `FIONA_NOVEL_CHAT_CREATE`；`FIONA_NOVEL_CHAT` 已有，默认 0。文档测试不检查新变量，但配置模板应同步。
  证据:`backend/.env.example`:205-214；`rg -n 'FIONA_NOVEL_CHAT_CREATE' backend frontend` → 0

## Q13 规格会依赖的「不存在」

F13.1 [已核实] 代码里没有 `novel_drafts`、`draft_novel`、`novel_draft_id`、`FIONA_NOVEL_CHAT_CREATE`：`rg -n 'novel_drafts|draft_novel|novel_draft_id|FIONA_NOVEL_CHAT_CREATE' backend frontend --glob '!**/__pycache__/**' --glob '!frontend/node_modules/**'` → 0 条（只在 `docs/tasks/2026-11-02-chat-create-novel/02-spec.md` 有 24 条）。
  证据:上述命令

F13.2 [已核实] 没有 `novel_project_id` 列/字段：`rg -n 'novel_project_id' backend frontend --glob '!**/__pycache__/**' --glob '!frontend/node_modules/**'` → 0 条。
  证据:上述命令

F13.3 [已核实] `messages` 没有小说引用列：`rg -n 'novel_id' backend/database.py frontend/lib/useConversations.ts frontend/components/ChatBubble.tsx` → 1 条，且只是删号 SQL 里的 `novel_id IN (...)`，不是消息列。
  证据:上述命令；`backend/database.py`:931

F13.4 [已核实] 没有 `getNovelDraft/NovelDraftCard/openNovelAt/novelFrameSrc`：`rg -n 'getNovelDraft|NovelDraftCard|openNovelAt|novelFrameSrc' frontend backend` → 0 条。
  证据:上述命令

F13.5 [已核实] 聊天页没有 `novelHref`：`rg -n 'novelHref' frontend/app/page.tsx frontend/components/ChatBubble.tsx frontend/lib/useConversations.ts` → 0 条；`ChatBubble.tsx` 里 `novel` 也是 0 条。
  证据:上述命令

F13.6 [已核实] 没有聊天侧建书调用者：`rg -n 'service\.create\(' backend` → 7 条，全部是 `routers/novel.py:38` 和 6 个测试；`claude_agent.py` 里没有 `service.create` 或 `create_novel`。
  证据:上述命令；`backend/services/claude_agent.py`:33，`:78-110`

F13.7 [已核实] 建书接口有「每用户同时只能一本 running/setup_running」的写事务保护（`BEGIN IMMEDIATE` + `check_active`），但没有幂等键、没有同名去重、没有每日建书上限、没有 create 时余额预检。`rg -n 'UNIQUE.*title|title.*UNIQUE' backend` → 0；`rg -n 'idempoten|request_id' backend/novel/service.py backend/routers/novel.py` → 0。
  证据:`backend/novel/service.py`:159-162，`:220-225`；上述 `rg` 命令

F13.8 [已核实] 聊天侧没有「一轮只建一本」的专用计数器；只有全局 4 次工具上限。若新工具只写草稿而不进入 `setup_running`，模型可以在一轮内连续写多份草稿；若新工具调用 `service.create`，第二本会被 `check_active` 409。
  证据:`backend/services/claude_agent.py`:644-647；`backend/novel/service.py`:159-162

F13.9 [已核实] `novel_to_film` 确实有「优先复用未归档项目」逻辑：`sources._candidate` 按 `owner + source_kind='novel' + source_ref=book.id + archived=0` 查 `studio_projects`，`start_film` 直接取 `projects[0]`，有则不建快照。这个去重键是来源书 id，不是标题，不能直接照搬到「新建小说草稿」。
  证据:`backend/studio/sources.py`:88-93；`backend/studio/novel_chat.py`:127

F13.10 [已核实] 没有平台侧 `novel_draft` 意图：`NOVEL_INTENTS` 只有 `novel_list/novel_read/novel_to_film`；`normalize_intent_result` 的小说白名单也只加这三个。
  证据:`backend/intent_router.py`:142-153，`:445-446`

F13.11 [已核实] 没有 `page.tsx` 向 iframe 导航的代码：`rg -n 'novelFrameRef\.current\.src|contentWindow\?\.postMessage' frontend/app/page.tsx` → 0 条；父页消息处理只有 settings/close。
  证据:`frontend/app/page.tsx`:531-545

F13.12 [已核实] 没有「草稿消费」事务钩子；`service.create` 当前在插入 novels 后直接 commit，没有第二张表可消费。新表必须在同一个 `BEGIN IMMEDIATE` 内消费，否则同一草稿可被并发/重复使用。
  证据:`backend/novel/service.py`:220-228

## Q14 每条断言的取值

F14.1 [已核实] `h.state.billable`：正确实现（草稿工具）为 False；错误实现若直接调 `service.create` 但没触发通用工具计费，**仍为 False**。因此这个断言在「不扣费」需求上无区分力；它只能区分「通用工具卡计费分支」是否误入。
  证据:`backend/services/chat_service.py`:113-118；`backend/services/claude_agent.py`:696-704

F14.2 [已核实] `users.strawberry_balance`：在 `DEV_MODE=1` 或全 `byok:self`/`fake:` 下，正确与「调了 service.create」都可能不变；只有在 `DEV_MODE=0`、平台模型、非 fake 且等待 setup 真正 reserve 时，错误实现才会下降。环境变量直接决定这个断言是否有效。
  证据:`backend/novel/billing.py`:150-153，`:199-213`

F14.3 [已核实] `novels` 行数/状态：正确草稿实现为 0 行；错误实现调 `service.create` 会多一行 `setup_running`。这个取值不依赖计费开关，是比 `billable` 更好的 oracle；但要注意 `service.create` 可能在断言前已异步改状态。
  证据:`backend/novel/service.py`:225；`backend/novel/runner.py`:95-136

F14.4 [已核实] `messages.novel_draft_id`：正确落库为 uuid；错误/未加列为 None。这个取值只取决于 `save_message` 和 `_save_response`，与 `DEV_MODE` 无关；但若测试直接调 `save_message` 而不是走工具，仍可能测不到工具接线。
  证据:`backend/database.py`:550-565；`backend/services/chat_service.py`:977

F14.5 [已核实] `CLAUDE_CLIENT_TOOLS` 名字集合：正确为 5；错误「把 draft 加进常量」为 6；错误「动态追加」仍为 5。所以它只能抓一种坏实现；必须再断言请求 `kwargs["tools"]` 的差集。
  证据:`backend/services/claude_agent.py`:48-54，`:70-92`；`backend/tests/test_novel_chat.py`:185-188

F14.6 [已核实] `tools is CLAUDE_CLIENT_TOOLS`：关闭时正确为 True；错误「返回新列表但内容相同」为 False；错误「工具加进常量」时集合变 6。这个断言严格但只覆盖「全关」路径。
  证据:`backend/services/claude_agent.py`:73-77；`backend/tests/test_novel_chat.py`:188

F14.7 [推断] 时间戳（`novels.created_at/updated_at`）由 SQLite `CURRENT_TIMESTAMP` 生成，每次不同；如果向后兼容测试用「返回 JSON 逐字节相同」，会因时间戳天然变红。应比较去掉时间字段后的结构，或固定时钟/直接比较请求体和状态。
  证据:`backend/novel/store_db.py`:31-32；`backend/novel/service.py`:225

F14.8 [已核实] `render_card` 的取值还受环境控制：有 `node` 且 `typescript/react/react-dom/server` 可解析才渲染；缺一个就 skip。skip 不是绿，验收要求 `0 skipped` 时必须先补齐依赖。
  证据:`backend/tests/test_claude_agent_frontend.py`:140-158

## Q15 结构与落点

F15.1 [已核实] 写歌的分层是：`song/config.py`（开关/白名单/参数）、`song/tools.py`（4 个 schema、`execute`、`card_for_project`、`SONG_MODE_PROMPT`）、`song/store.py`（项目/歌词/版本 SQLite）、`song/jobs.py`（真正调火山与轮询）、`routers/songs.py`（HTTP 门控）、`frontend/lib/songs.ts` + `SongProjectCard.tsx` + `ChatBubble` + `useConversations` + `page.tsx`。
  证据:`backend/song/tools.py`:133-204，`:684-724`；`backend/routers/songs.py`:16-36；`frontend/lib/songs.ts`:246-340

F15.2 [已核实] 聊天读小说没有独立 `novel/tools.py`：schema 和 `_novel_tool_params` 内联在 `claude_agent.py`；实际读逻辑在 `studio/novel_chat.py`；`studio/sources.py` 底部又用三个懒加载包装函数转发，属于为兼容旧导入保留的重复层。
  证据:`backend/services/claude_agent.py`:78-110；`backend/studio/novel_chat.py`:22-134；`backend/studio/sources.py`:645-657

F15.3 [已核实] 新「建书」工具最自然的落点：`backend/novel/drafts.py`（新，草稿读写/校验/消费）、`backend/database.py`（建表 + `messages` 列 + `save_message` 校验 + 删除清理）、`backend/novel/service.py`（`CreateNovel.draft_id` 与 `create` 消费）、`backend/routers/novel.py`（`GET /novels/drafts/{id}`）、`backend/services/claude_agent.py`（schema/追加/执行/卡片）、`backend/services/chat_service.py`（`ChatState.novel_draft_id` 透传）。
  证据:上述文件现有职责与签名；`backend/novel/drafts.py` 尚不存在

F15.4 [已核实] 前端落点：`frontend/components/NovelDraftCard.tsx`（新）、`ChatBubble.tsx`（`ChatCard` 分支 + `onOpenNovel`）、`useConversations.ts`（`novel_draft_id` → card）、`page.tsx`（`openNovelAt` + iframe src 状态 + 两处 card 复制）、`NovelWizard.tsx`（读 `draft` 参数、预填、带 `draft_id` 提交）、`lib/novels.ts`（`getNovelDraft`、`NovelCreateInput.draft_id`）。
  证据:`frontend/components/ChatBubble.tsx`:90-127；`frontend/lib/useConversations.ts`:60-69；`frontend/app/page.tsx`:2144-2170，`:2934-2962`；`frontend/components/novel/NovelWizard.tsx`:41，`:151-161`；`frontend/lib/novels.ts`:9-15

F15.5 [已核实] 落点文件骨架（只列导出/签名，不贴实现）：
```
# backend/novel/service.py
class Target(Input)
class Adaptation(Input)
class CreateNovel(Input)
async def validate_selection(username, data) -> None
async def estimate(username, data) -> dict
async def create(username, data) -> dict
async def detail(username, novel_id) -> dict
```
```
# backend/services/claude_agent.py
CLAUDE_CLIENT_TOOLS = [...]
def _tool(name, description, properties, required) -> dict
def client_tools_for_turn(ctx, state) -> list[dict]
def _novel_tool_params(name, args) -> tuple[dict | None, str | None]
async def stream_claude_agent(ctx, state)
```
```
# backend/studio/novel_chat.py
async def list_novels(username)
def validate_read_range(start, end=None, offset=0)
async def read_novel(username, book, start_chapter, end_chapter=None, offset=0)
async def start_film(username, book, auth_method=None)
```
  证据:`backend/novel/service.py`:43-70，`:165-256`；`backend/services/claude_agent.py`:43-110，`:340`；`backend/studio/novel_chat.py`:22-134

F15.6 [已核实] 前端骨架：
```
# frontend/lib/novels.ts
export interface NovelCreateInput { ... }
export const createNovel = (input: NovelCreateInput, signal?: AbortSignal) => ...
export const novelHref = (path: string, embedded: boolean) => ...
```
```
# frontend/components/ChatBubble.tsx
export interface CardData { ... }
export function ChatCard(props: ChatCardProps)
```
```
# frontend/lib/useConversations.ts
interface StoredMessage { ... }
function toMessages(messages: StoredMessage[]): Message[]   // 当前未导出
```
  证据:`frontend/lib/novels.ts`:9-15，`:113`，`:161`；`frontend/components/ChatBubble.tsx`:89-127`；`frontend/lib/useConversations.ts`:10-17，`:60-69`

F15.7 [已核实] 已有重复/别扭点：①`studio/sources.py:645-657` 的三个包装只是懒加载转发 `studio/novel_chat.py`；②`claude_agent._NOVEL_CLIENT_INTENTS` 与 `intent_router.NOVEL_INTENTS` 各维护一份映射，书名去空白/缺参逻辑也各写一遍；③`song/tools.py:72` 的 `_tool` 与 `claude_agent._tool` 形状重复；④`NovelWizard.tsx` 把 `defaultNovelAgents` 这种领域默认值放在组件里，后端没有对应实现；⑤`NovelCreateInput` 没有 `structure` 而后端支持 `structure`；⑥`page.tsx` 两处 `const card: CardData` 手工复制字段，新增字段必须两处都改。
  证据:`backend/studio/sources.py`:645-657；`backend/services/claude_agent.py`:33，`:95-110`；`backend/intent_router.py`:465-472；`backend/song/tools.py`:72-83；`frontend/components/novel/NovelWizard.tsx`:20-38；`frontend/lib/novels.ts`:9-15；`frontend/app/page.tsx`:2144-2170

F15.8 [已核实] `frontend/app/page.tsx` 文件开头有 UTF-8 BOM（`efbb bf`），规格要求按字节编辑并保留；用会重写文件的工具时容易丢掉。
  证据:`head -c 3 frontend/app/page.tsx | xxd` → `00000000: efbb bf`

## 未核实清单

- 全量 pytest 的真实 `passed/skipped/failed` 数和「7863 passed / 0 skipped」基线未核实：当前 read-only 沙箱连 `conftest.py` 的临时目录都创建不了，pytest 未进入收集。需要 workspace-write 或沙箱外复跑。
- `npx tsc --noEmit` 的原始退出码未取得：普通命令在 read-only 下打印 TS5033；`--incremental false` 实测 0。
- `npm run lint` 的完整 CI 等价结果未跑；只跑了 `npx eslint app components lib --max-warnings=0`，0 errors/25 warnings。
- `npm run build` 未跑（会写 `.next`，read-only 不允许）。
- Claude/Anthropic 真实服务端行为未核实：工具 schema 的 `maxLength/minimum` 是否由服务端严格拒绝、`tool_use` 的 `input` 在下一轮如何回放、`tools` 变化是否一定使 prompt cache 失效，均只有代码和既有 MockTransport 测试，没有真实 Key 实测。
- setup 预扣 68/实扣 9 来自 `docs/tasks/2026-10-15-novel-workshop-p1/06-smoke.md` 的历史冒烟记录，不是本次当前环境实测。
- 新 `novel_drafts` 表、`messages.novel_draft_id`、`CreateNovel.draft_id`、`GET /novels/drafts/{id}`、`NovelDraftCard`、`openNovelAt` 都尚不存在；它们的删除钩子、事务回滚和前端行为没有可运行实现可测。
- 单本删书后草稿 `novel_id` 的悬空引用、删会话/清空历史的具体清理顺序，需要实现后在临时库验证；现有代码没有可参照的 novel draft 清理。
- 工作区 2026-11-02 23:51 出现的 `docs/tasks/2026-11-02-chat-create-novel/02-spec.md` 是调查期间新增的规格草稿，不是 HEAD 内容；其中的 7863 基线、行号、`0 skipped` 等我没有逐条复跑。
- 未创建 git worktree 实测；Q8 的 worktree 结论来自 `.gitignore`、`git check-ignore` 和测试 skip 条件，属于推断。
- `page.tsx` 的 BOM 已确认，但「按字节编辑后 BOM 是否保留」没有实际改写验证（只读约束下不能写）。
- 未核实 `FIONA_NOVEL_CHAT_CREATE` 的真实产品命名/默认值是否就是规格草稿所写；代码中不存在该变量。