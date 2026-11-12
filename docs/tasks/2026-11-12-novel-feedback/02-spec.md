# 规格：修改意见卡（Claude 智能体把聊天里的修改意见交给书斋）

- 规格版本：v1.6（2026-11-12）。v1.3 经作者确认（§8 案头三处小修已获批准并入任务清单）；v1.4 依据独立复核 `04-review.md` 与作者确认，加了「点重新定稿先重新读取」，R1 返修内容写在 §4.6；v1.5 只补测试（R2，§4.7）；v1.6 在第 2 轮复核通过后，按作者决定把两条可优化项写进已知局限（R3，§4.8）。v1.0 经五路对抗式审查（测试锁与可行性、后端、前端、执行者能否照做、产品），每路问题再由独立核实者尝试推翻：66 条里 48 条 must/should 全部成立（27 条原样成立，21 条修正了改法），据此出 v1.1；v1.1 再经三路只读核对（引用事实、问题落实、内部一致性，在副本里照字面实现了一遍），据此出 v1.2。修订内容见 §9。
- 任务级别：**L3**（新增一张表与 `messages` 一个可空列，属数据模型变更）。规格经作者确认后才派单；复核用 dsh 上的 Opus 5.5 `xhigh`。
- 基线：Fiona `main` = `7a17f64`。有 `frontend/node_modules` 时后端全量 `8011 passed / 0 skipped`；前端 `tsc` 退出 0，`npm run lint` 为 `0 errors, 25 warnings`，`npm run build` 退出 0；全仓 JSX `<dialog` 恰 14 个（`backend/tests/test_ui_closeout_dialog_scrim.py:117`）。派单前派单方会在 HEAD 上重测这几个数，以重测结果为准。
- 执行者：dsh / DeepSeek Flash / max，经 codex MCP，在专用 worktree。
- 本规格自包含。执行者看不到任何对话，规格没写的不要自行扩展。

## 1. 产品目标与场景

作者在主聊天里用自带的 Claude（智能体模式）和分身讨论自己在书斋里写的长篇。分身读完原文能写出具体的修改意见，但现在没有任何办法把意见交给书斋：分身只能请作者「在确认细纲那一步自己贴给写手」。

本批之后：分身调用一个免费工具 `draft_novel_feedback`，把意见按用途分三类写成一张「修改意见卡」，作者在卡片上逐项决定怎么用：

1. **以后的章节**：点「交给编辑部」，在书斋里成为一条待下发留言（免费）。
2. **第 N 章细纲**（只在这本书正等作者确认第 N 章细纲时才有）：点「带着这些要求重新定稿」，确认框说明费用，作者确认后才发起既有的重新定稿流程（书斋里同一个操作叫「附一句话重新定稿」）。
3. **已写好的章节**：只列出问题，提示作者去书斋「改稿」，书斋不会自动修改。

**模型不能代作者做任何决定**：工具只写卡片记录；交留言、发起重新定稿都必须由作者在卡片上点按钮。卡片要如实写出每个按钮的作用范围、费用与当前进展（见 §2.1、§2.2），不能让作者以为意见已经生效、会长期生效，或把会错的章号写给作者。

## 2. 现状事实（行号以 `7a17f64` 为准）

### 2.1 留言：一次性、只影响下一次规划细纲

- `backend/novel/service.py:82-83` `Note`：`text` 1–500 字（`Input` 基类去首尾空白、禁止多余字段，`:40-41`）。
- `:642-649` `note()`：`BEGIN IMMEDIATE` → `owned()`（只验归属，不看书的状态）→ 该书 `status='pending'` 的留言已有 5 条则 `fail('待处理留言最多五条')`（409）→ `INSERT ... 'pending'` → 返回 `{'status':'pending'}`。**不返回留言 id、不幂等**；没有撤回或编辑留言的接口（`routers/novel.py` 只有 `:64` 的 GET 与 `:139-142` 的 POST）。
- `backend/novel/runner.py:314` 每章开头取出全部 pending 留言，但只有**这一章还没有细纲**时才交给主编规划（`:347-350`），写进 `brief.user_notes`，每项形如 `{"id": "N{留言id}", "text": ...}`（`:350`）；已经出了细纲的章（等确认、重新定稿、批准后写正文）都不读新留言。
- 主编的裁决 `decision.user_note_responses` 每项形如 `{"note_id": "N1", "adopted": true, "response": "回应"}`（`novel/agent_pool.py:45`），必须回应本次全部 N 留言、不增不漏（`:95`）。
- `backend/novel/store_db.py:320-329`：只有某章写完归档的同一事务里，才按 `response.get("note_id", response.get("id"))`（去掉开头的 `N`）把留言改成 `delivered`，写入 `delivered_chapter` 与 `response_json`（整条回应项，含 `note_id`、`adopted`、`response`）。所以 **pending 不等于没被看过**：审查方实测，逐章确认的书在「等确认第 1 章细纲」时交出留言，作者批准第 1 章后，第 2 章细纲的 `brief.user_notes` 里已经有这条留言，而留言仍是 pending，直到第 2 章写完才变 `delivered`。
- 逐章确认（`per_chapter`）的书每章都停在 `awaiting_plan`（`runner.py:351-353`）。**这时第 N 章细纲已出，新留言要到第 N+1 章规划细纲时才被读到。**
- 状态为 `completed` / `failed` 的书，`resume` 只接受 `paused`（`service.py:666`），留言永远不会被读到；`awaiting_end` 只有作者选择续写才会读。写正文或重新归档时出意外异常，书变 `failed`，章节行保持原状（`runner.py:236-243`），所以「某章细纲已读到留言、书却失败了」是可能的。
- 某章细纲的裁决里 `ending_status == "end"` 时，这一章写完后书进入 `awaiting_end`（`runner.py:363-364`），不会再规划下一章；只在章号小于 `min_chapters`（默认 50）时禁止定为最后一章（`schemas.py:492`、`service.py:45-46`）。所以「等确认第 K 章细纲」时第 K 章本身就可能是最后一章，不能只用 `K >= max_chapters` 判断。
- `service.notes()`（`:276-286`）返回留言列表，`adopted` / `response` 只在 `delivered` 后才有值，解析写法见该函数。书斋留言页把两种状态叫「待下发」「已下发到第 N 章」（`frontend/components/novel/NotesPanel.tsx:30`），满 5 条时写「已有 5 条待下发留言」（`:26`）。

### 2.2 重新定稿（代码里叫 redo）：只对正在等确认的那一章、在后台跑、可能计费

- `service.redo_plan()`（`:449-461`）：`BEGIN IMMEDIATE` → `owned(..., ('awaiting_plan',))`（不是 `awaiting_plan` 时 409「当前状态不能执行此操作」）→ 取 `status='awaiting_plan_approval'` 中**章号最大**的一章（没有或没有 `meeting_json` 时 409「当前没有可重做的待批细纲，请刷新后重试」）→ 把附言写进 `meeting['_redo_note']`、`_redo_count+1`、章节改 `planning` → `_activate`（改稿中或作者另一本书在跑时 409）→ `commit`；之后在函数内 `from .runner import start_novel`（所以测试可以 monkeypatch `novel.runner.start_novel`）、`await start_novel(...)`，返回 `detail()`。
- 后台的 `_redo`（`runner.py:458-499`）拿旧 meeting 里的 `brief`（含当初的留言）、主编自己的初稿 `plan`、顾问意见，加上 `author_instruction`（附言）让主编重新定稿；**作者正在看的那一版定稿（`meeting['decision']`）不在载荷里**，交出得晚的新留言也不在。步骤键 `arm-{arm}/ch{NNN}/03-{task}-editor-redo{n}.json`（`:492`）。书斋 UI 把这个操作叫「附一句话重新定稿」，旁边是「批准（原样）」「改完批准」（`frontend/components/novel/PlanEditor.tsx:36-37`）；付费的「附一句话重新定稿」用普通 `btn`，主按钮留给批准。
- 计费：每次重新定稿都是新的付费步骤，按 `billing.py:187-235` 预扣、按实际用量结算。`NovelBilling.is_free(call)`（`billing.py:150-153`，staticmethod）在 `DEV_MODE=1`、`dry_run`、`model == "byok:self"` 或 `model` 以 `fake:` 开头时不扣草莓。主编的模型在 `config_json` 的 `agents.editor`；作者的试用书主编就是 `byok:self`（不扣草莓、用作者自己的模型额度）。
- `automation`（`service.py:65`、`:77`）取 `per_batch`（默认）/ `per_chapter` / `full_auto`，任何状态下作者都可以改（`service.py:624-630` 的 `patch()` 只对 agents 限制状态）；不是逐章确认的书重新定稿后会直接写正文，不再停下来等确认。
- 重新定稿在后台进行：`runner.py:305-307` 在重做之前检查每日上限，满了直接暂停；`:225-243` 把模型失败、余额不足、预算、自带模型不可用都转成 `paused`。这时该章仍是 `planning`、meeting 里仍有 `_redo_note`，恢复写作后用同一个步骤键再跑一次；`failed` 的书不能恢复（`POST /resume` 409）。
- 审查实测：v1.0 把卡片核对、`redo_plan` 与记下 `redo_started_at` 分在三个连接里，记账失败时会出现「付费重做已经发起、卡片却没记下」，作者再点会第二次付费。本版改成一个写事务（见 T3.4）。

### 2.3 已写章节：只能作者自己改

- 书斋 `ChapterReader.tsx:35`「改稿」→ `PUT /novels/{id}/chapters/{n}`（`service.py:743-770`）。改最新一章会重新归档（`service.py:760-764` → `runner.py:537-545` 再调一次档案员，档案员不是自带模型且非 `DEV_MODE` 时计费），已经出来、等确认的下一章细纲不会跟着重做。改较早的章会把其后已写的章标为 `stale`（`service.py:766` 是全仓唯一写 `stale` 的地方，没有任何语句改回），故事圣经与章节摘要不重算；工作室拒收有 `stale` 章的书（`backend/studio/sources.py:65-66`）。没有历史版本或撤回，改稿前也没有提醒（`ChapterReader.tsx:26-35`）。
- 书斋没有直达某一章的 URL 参数（`frontend/app/novels/[id]/page.tsx` 只读 id 与 embed）。

### 2.4 Claude 智能体的小说工具

- `backend/services/claude_agent.py:57-69` `NOVEL_DRAFT_TOOL`；`:85-110` `client_tools_for_turn`：小说开时依次追加 `list_novels`、`read_novel`、（`allow_studio` 时）`start_film`、（`novel_create_enabled` 时）`NOVEL_DRAFT_TOOL`、（写歌开时）写歌工具；小说、写歌全关时返回 `CLAUDE_CLIENT_TOOLS` 对象本身（`:89-91`）。开关在函数体内现读。
- `backend/studio/sources.py:36-41`：`novel_chat_enabled`、`novel_create_enabled`。
- 每轮标志在 `claude_agent.py:466-480`（`draft_written`、`draft_conversation_id` 在 `:476-477`）；工具执行时 `tools_executed` 达 4 次后回「本轮工具调用次数已用完」（`:664-669`，校验失败也计数）。
- `draft_novel` 执行分支 `:725-762`：每轮限 1 份、校验失败 `agent_tool_errors += 1`、成功后 `state.novel_draft_id = ...`、`state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"`、`delivered = True`、`yield chat._sse({"card": card, "append": True})`、异常回「书斋草稿暂时不可用」并计错。其后是 `elif name == "generate_image":`（`:763`），最后兜底 `else` 在 `:831` 起，兜底里 `next(... CLAUDE_CLIENT_TOOLS ...)` 遇到未知工具名会抛 `StopIteration`，所以新工具必须有自己的 `elif` 分支。
- 模型只知道书名：`read_novel` / `start_film` 用 `book` 参数，经 `backend/studio/novel_chat.py:34-45` `_resolve(username, query)`：去掉《》→ `sources.find_candidates` → 恰好一本时返回候选 dict（含 `id`、`title`、`status`、`chapters_done` 等），否则返回报错文本（「没找到《X》…」或「要读哪本书？找到这些候选：…」）。`list_novels` 每本书一行，含状态名（`novel_chat.py:10-17`、`:28`；`awaiting_plan` 显示为「等你确认细纲」）。`read_novel` 只读 `done` / `stale` 且有正文的章（`:79`），读不到细纲。
- `service.detail(username, novel_id)`（`service.py:249-262`）返回 `status`、`chapters_done`、`title`、`max_chapters`（经 `summary()`，`:194-197`）、`config`（解析后的 `config_json`，含 `automation`、`agents`、`target`）、`chapters`（每项含 `chapter`、`title`、`status`，不含正文，也不含 `meeting_json`）、`pending_notes` 等；不属于本人时抛 404。
- 聊天侧的 AST 锁（`backend/tests/test_studio_sources_readonly_integration.py:177-208`）扫描 `services/claude_agent.py`、`intent_router.py`、`services/chat_service.py`、`routers/chat.py`、`studio/novel_chat.py` 五个文件：只许 `from novel import service`（属性限 `list_books`/`find_books`/`detail`/`bible`/`chapter`/`chapters_range`）、`novel.runner` 只许 `is_editing`、`novel.drafts` 只许三个草稿函数，其他 `novel.*` 一律 `assert False`。因此**聊天侧不得调用 `note` / `redo_plan`**；交留言、重新定稿都由作者点卡片后经 `routers/novel.py` 的新接口完成。
- `backend/tests/test_studio_sources.py:493-504` 锁 `backend/studio/**`：只许 `novel.runner.is_editing`，并禁止对 `novels` / `novel_*` 表写 SQL。所以新代码不得放进 `backend/studio/`（`sources.py` 里只加一个读环境变量的开关函数）。
- Claude 思考强度默认低档，低档 `max_tokens` 为 4096（`byok/client.py:463`）。

### 2.5 卡片落库与清理（草稿卡的做法）

- `backend/database.py:70-85` `NOVEL_DRAFTS_DDL` / `NOVEL_DRAFTS_INDEX`；`init_db` 在 `:335-336` 无条件建表；`:163` `_safe_migrate(... ADD COLUMN novel_draft_id ...)`。
- `save_message`（`:522-618`）：关键字参数 `song_project_id`、`novel_draft_id`（`:532-533`）；写歌归属核对 `:572-584`；草稿归属核对 `:585-597`，以注释「# 书斋草稿归属同样只做附加校验：不属于本人本会话就存 NULL。」开头；`INSERT` 在 `:598-602`。
- 清理：清空历史 `database.py:509`、删号 `:988` 都是 `DELETE FROM novel_drafts WHERE owner_username = ?`；删会话 `agent_store.py:374-377`；删书 `novel/service.py:781` 把草稿 `novel_id` 置 NULL（同一事务 `:778-782`）。
- 读消息：`agent_store.py:338` 的 SELECT 列以 `song_project_id, novel_draft_id` 结尾；`routers/conversations.py` 原样返回。
- `backend/services/chat_service.py:780-792` `ChatState` 以 `song_project_id`、`novel_draft_id` 结尾；`:991-998` `_save_response` 把两者传给 `save_message`。

### 2.6 前端

- `frontend/components/ChatBubble.tsx:91-102` `CardData`（含 `draft_id?: string;  // "novel_draft" = 书斋草稿卡片`）；`:104-109` `ChatCardProps`（已有 `onOpenNovel?: (path: string) => void`）；`:111-116` `ChatCard` 的 `novel_draft` 分支：`if (!card.draft_id) return null; return <NovelDraftCard draftId={card.draft_id} onOpenNovel={onOpenNovel} />;`。
- `frontend/components/NovelDraftCard.tsx` 是卡片取数写法的样板（挂载时 `AbortController` 拉取、按 id 记账、加载态用 `result.draftId === draftId ? … : loading` 推导）。**不要照抄它的两处**：标题行带 `font-medium`；正文用 `.slice(0, 80)` 截成摘要（`:60`）。新卡片正文完整显示、不加粗。
- 聊天卡片里的错误提示用 `--seal` 色（`SongProjectCard.tsx:350`、`:434`；`LocalWatchSection.tsx:270` 写作 `text-[color:var(--seal)]`）；`SongProjectCard.tsx:261`、`:287`、`:294-306` 用 `busyRef` 防重复提交。
- `frontend/lib/useConversations.ts:10-19` `StoredMessage`、`:56-79` `toMessages`（写歌卡在前、草稿卡在后）。
- `frontend/app/page.tsx`（**文件以 UTF-8 BOM 开头**）`:2186-2214` 有两处 `const card: CardData = {...}`，各含一行 `draft_id: data.card.draft_id,`；`:529-534` `openNovelAt` 只放行 `^/novels/new\?embed=1&draft=[0-9a-f-]{36}$` 与 `^/novels/[0-9a-f-]{36}\?embed=1$` 两种路径，前者之外打开书斋抽屉用后者。路径与当前相同时 iframe 不重载；抽屉关上后 iframe 保留页面状态（`:2996` 的注释写明这是有意的）；书斋工作台只在 `running` / `setup_running` 时轮询（`NovelWorkbench.tsx:28`、`:118-135`）。所以作者此前在抽屉里开过这本书时，卡片操作后再打开看到的仍是旧页面。书斋的「批准（原样）」不带细纲提交（`PlanEditor.tsx:36` → `NovelWorkbench.tsx:306` 发 `{}`），后端批准当前存档的那一版（`service.py:426`，只有带 `beat_sheet` 时 `:435` 才整块替换）；「改完批准」提交页面上的细纲。所以重新定稿完成后，在旧页面点「批准（原样）」会批准作者还没看过的新细纲并开始写正文，点「改完批准」会用旧页面里的内容覆盖新细纲。
- `frontend/lib/agents.ts:33-45` `apiJson`（不传 `method` 时为 GET；非 2xx 抛 `ApiError(detail, status)`）；`frontend/lib/novels.ts:158-166` `novelErrorMessage`（`AbortError` 会变成「请求未完成，请稍后重试。」，`:164-165`）；`:178-182` `displayNovelChapterTitle`。
- `frontend/components/ConfirmDialog.tsx:13-19` `ConfirmOptions {body; title?; confirmLabel?; cancelLabel?; danger?}`，`:70-72` `useConfirm()` 返回 `(options) => Promise<boolean>`；Provider 已挂在 `app/layout.tsx`。用它**不增加** JSX `<dialog` 计数。仓库惯例写成 `const confirm = useConfirm();` 再 `await confirm({ … })`（如 `NovelWorkbench.tsx:81`、`:246`）。
- 全仓扫描原生对话框：`backend/tests/test_component_language.py:36-38` 的 `NATIVE_DIALOG` 是 `(^|[^.A-Za-z_])(window\.)?(confirm|alert)\(\s*[`"']`，只命中括号后紧跟引号的调用，所以 `await confirm({` 不命中；但组件里自己定义名为 `alert` 的函数再写 `alert("…")` 会被命中。
- lint：`eslint-config-next` 并入了 `eslint-plugin-react-hooks` 7.1.1 的 recommended 规则，`react-hooks/set-state-in-effect`、`react-hooks/refs`、`react-hooks/static-components` 都是 error（审查实测：在 effect 里同步 `setState` 会出 1 个 error、`npm run lint` 退出 1）。HEAD 为 0 errors、25 warnings。

### 2.7 测试夹具的真实形状（审查方在副本里实测）

- `backend/tests/test_claude_agent_runtime.py`：`harness` 夹具定义在 `:60`，`conftest.py` 里没有，**必须 import 进新测试文件才能注入**（只 import 别的名字、参数里写 `harness` 会报 `fixture 'harness' not found`）；`run(h)`（`:111`）驱动 `services.claude_agent.stream_claude_agent(ctx, state)`（`claude_agent.py:358`）。仓库里**没有** `run_agent_turn`。harness 用假会话 `conversation_id="conversation"`（`:65`），并在 `:84`、`:96` 把 `chat._save_response` 换成只记账、不写库的假函数。
- `backend/tests/test_novel_chat_create.py`：`offline` 夹具 `:34-52`；`enabled` `:56`、`create_enabled` `:67`；`draft_db` `:71` 起；顶层导入真实 `_save_response` 在 `:18-19`，用例里换回真实函数见 `:285`，用 `agent_store.create_conversation` 建真实会话见 `:83-85`；HEAD 对照时让新功能用例以 `AssertionError` 而不是 `ImportError` 失败的守卫先例是 `_require_drafts()`（`:144-146`）；`_load_module`（`:137-141`）直接 exec 源码，对使用相对导入的 `novel/service.py` 会报 `ImportError: attempted relative import with no known parent package`（exec 前设 `module.__package__ = "novel"` 即可，先例 `test_byok_image_tool.py:53-57`）；开关矩阵的 `(method, crisis)` 参数是 **五组**（`:160-166`）。
- `backend/tests/test_novel_chat.py:36-57` 的 `catalog` 桩掉 `sources.find_candidates`，返回假书 `book-1`；新分支随后真调 `service.detail` 会 404。**本功能的测试不要用它**，改为真实插库：照 `test_studio_sources_readonly_integration.py:44-71` 的 INSERT 写法（`novels` 的 `seed_idea`、`config_json`、`budget_strawberries` 必填）。
- `backend/tests/test_novel_p1_api.py`：`workshop` 夹具用 `FakeLLM`（`:27-28`），`wait(client, book, state)`（`:32`）；HTTP 重新定稿返回后约 1–15 ms 内章节还是 `planning`，之后变回 `awaiting_plan_approval`、`_redo_note` 被弹出——**中间态不能在 HTTP 用例里断言**。`backend/tests/test_novel_p1_runner.py:41-44` 的 `drain(novel_id)` 等后台任务结束。`FakeLLM` 定义在产品代码 `backend/novel/fake_llm.py:34`：`payload(request)` 是 staticmethod（`:57-58`），用法见 `test_novel_p1_runner.py:271`；`fake.calls` 的每项是请求 dict，带 `"step_key"` 键；`script` 可以是 `callable(request, index)`，返回异常对象就抛出、返回 None 走默认回答（`:35-40`、`:80-105`）。第一次重新定稿之前 meeting 里没有 `_redo_count` 键（`service.py:456` 用 `.get('_redo_count', 0)`）。在 `asyncio.run` 里调用会启动 runner 的服务函数后直接离开，会把书卡在 `running`；把 `start_novel` 桩掉后书也一直停在 `running`，同一用户的另一本书再发起会被 `_activate` → `check_active` 拦成 409「每个用户同时只能运行一本小说」（`service.py:166-169`、`:318-320`）。
- `backend/tests/test_desk_views_frontend.py`：`NODE_RENDERER` 与 `STUBS`（`:92`）、`resolveFile`（`:110`）、`requireFrom`（`:127`）；没列进 `STUBS` 的 `@/` 模块直接加载仓库里的真实文件；渲染脚本的 props 只来自 `JSON.parse(process.argv[2])`（`:162-167`，唯一特例是 `__childrenText`），**函数型 prop（如 `onOpenNovel`）传不进去**。`backend/tests/test_desk_dock_races_frontend.py:57-60` 的 `flush()` 只调用 `Component(props)`，`:147-151` 的 `find` 只沿 `props.children` 往下找，**不会展开嵌套的函数组件**；这个迷你运行时（`:55-80`）只在依赖变化时调用 effect 的清理函数，**没有卸载入口**。
- `backend/tests/test_novel_p2_frontend.py:75-82` 的 `backend_paths` 用 AST 取 `router.get/post/...` 的路径并把 `{…}` 归一成 `{}`，**只返回路径字符串的集合，不含 HTTP 方法**；模块顶层只有常量和函数，可以直接导入。`routers/novel.py:86` 已有 `/{novel_id}/plan/redo`、`:139` 已有 `/{novel_id}/notes`，所以「路径里含 `/redo`、`/note`」在 HEAD 上就成立，不能当证据。

### 2.8 不存在的东西

- 仓库里没有 `novel_feedback` / `draft_novel_feedback` / `NovelFeedbackCard` / `FIONA_NOVEL_CHAT_FEEDBACK`。
- 没有撤回或编辑留言的接口；没有重做报价接口；书斋没有按章深链。

## 3. 设计决策

1. **独立开关** `FIONA_NOVEL_CHAT_FEEDBACK`：默认 `0`，只有字面 `1` 开启，调用时读取；还须 `novel_chat_enabled(user)` 为真，且只在小说分支（非危机轮）追加。理由：`backend/tests/test_novel_chat.py:179-188`、`test_novel_chat_create.py:160-211`、`:595-601` 锁住了现有开关下的工具集合，新工具必须在新开关为 0 时完全不出现。
2. **工具只写卡片记录**：新表 `novel_feedback`，新模块 `backend/novel/feedback.py`（参数校验与建卡）；工具不碰 `novel_*` 业务表、不调用编辑部、不扣草莓。
3. **意见分三类字段**：`next_chapters`（以后章节的要求，≤500 字）、`current_plan`（这一章细纲的修改要求，≤500 字，只在 `awaiting_plan` 时可填）、`written_chapters`（已写章节问题，≤10 条、每条 ≤200 字）。超长一律报错让分身精简，**不静默截断**；格式错误一次报全、带实际字数（分身每轮只有 4 次工具名额）。不是逐章确认的书不收 `current_plan`（卡片上不能对它重新定稿）。
4. **交给编辑部：原子、幂等**。新接口 `POST /novels/feedback/{id}/note` 在一个 `BEGIN IMMEDIATE` 事务里插入留言并记下留言 id；已交过就直接返回卡片现状，重复点击不重复交。抽出 `service._insert_pending_note`，`note()` 改为调用它，对外行为不变。
5. **重新定稿从卡片发起，核对与改库在同一个写事务**：卡片用 `useConfirm()` 弹确认框，按这本书主编的模型说明费用（扣草莓 / 用你自己的模型额度 / 不扣）。新接口 `POST /novels/feedback/{id}/redo` 在一个 `BEGIN IMMEDIATE` 里核对「这本书仍在 `awaiting_plan`、逐章确认、等确认的就是卡片记下的 `plan_chapter`」、把细纲改为重做中、记下 `redo_started_at`，提交后才启动后台。抽出 `service._begin_redo` 给 `redo_plan()` 复用，`redo_plan()` 对外行为不变。章号对不上就拒绝，绝不把第 N 章的意见用到第 N+1 章；同一张卡只会发起一次。
6. **卡片如实显示进展，不推算会错的章号**：后端视图带出「这条留言是否已被某章细纲读到、编辑部怎么回应」（从进行中章节的 meeting 里按留言 id 查）、「重新定稿是否还在进行、暂停或失败」、费用类型、是否逐章确认、计划章数、等确认的那一章是不是最后一章；前端按固定顺序挑文案，失败的书优先说「不能再继续写」。
7. **已写章节只展示**，加「在书斋打开」按钮（经 `openNovelAt` 打开书斋抽屉到这本书）；等确认细纲一节另有「去书斋改细纲」。作者在卡片上操作后，卡片提示「书斋若已开着这本书，要回到书架重新打开」。本批不改 `page.tsx` 的抽屉重载逻辑。
8. **卡片落库**：`messages` 加可空列 `novel_feedback_id`，与 `novel_draft_id` 同模式；刷新后按它重建卡片。卡片挂载时经 `GET /novels/feedback/{id}` 读取卡片与书的**当前**状态，按钮可用与否以此为准。
9. **新路由只用 `workshop_user` 门控**，不读 `FIONA_NOVEL_CHAT_FEEDBACK`：关掉开关后，历史里已有的卡片仍能读取和操作，和草稿卡一致。
10. **不接案头**：修改意见卡流式到达时不触发案头定位；`frontend/lib/desk.ts` 一个字节都不改；`frontend/components/desk/*` 除 §8 的三处小修外一个字节都不改。
11. **只做 Claude 智能体路径**：平台（千问）路径不加意图。
12. **不另加孤儿卡片清理**：建卡成功但本轮消息没落库、或单条消息被删时，卡片行保留到清空历史、删会话或删号（与草稿卡相同）。

## 4. 执行者任务清单

### 4.1 白名单（只许改 / 新增这些）

后端：
- `backend/database.py`（建表常量与 `init_db`、`messages.novel_feedback_id` 补列、`save_message` 参数与归属核对与 INSERT、清空历史与删号的清理）
- `backend/agent_store.py`（读消息的 SELECT、删会话的清理）
- `backend/novel/feedback.py`（新）
- `backend/novel/service.py`（`_insert_pending_note`、`note()` 改用它、`_begin_redo`、`redo_plan()` 改用它、`feedback_view`、`send_feedback_note`、`redo_feedback_plan`、`delete()` 置 NULL）
- `backend/routers/novel.py`（三个新路由）
- `backend/studio/sources.py`（只加 `novel_feedback_enabled`）
- `backend/services/claude_agent.py`（工具常量、追加条件、每轮标志、执行分支）
- `backend/services/chat_service.py`（`ChatState.novel_feedback_id`、`_save_response` 透传）
- 文档六份：`CLAUDE.md`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example`
- 新测试：`backend/tests/test_novel_chat_feedback.py`、`backend/tests/test_novel_chat_feedback_frontend.py`、`backend/tests/test_desk_polish_frontend.py`（§8）
- 既有测试（**只许 §4.5 写明的两处**）：`backend/tests/test_studio_sources_readonly_integration.py`

前端：
- `frontend/lib/novelFeedback.ts`（新）
- `frontend/components/NovelFeedbackCard.tsx`（新）
- `frontend/components/ChatBubble.tsx`（`CardData.feedback_id`、`ChatCard` 新分支、import）
- `frontend/lib/useConversations.ts`（`StoredMessage.novel_feedback_id`、`toMessages` 新分支）
- `frontend/app/page.tsx`（两处 `const card: CardData` 各加一行；**按字节读写，保留 BOM**）
- `frontend/components/desk/DeskDialogs.tsx`、`frontend/components/desk/DeskChaptersView.tsx`、`frontend/components/desk/DeskEpisodesView.tsx`（只做 §8 的三处小修）

任务文档：`docs/tasks/2026-11-12-novel-feedback/impl/*.md`，总报告写进 `docs/tasks/2026-11-12-novel-feedback/impl/report.md`。

**不得改**：其他既有测试一字不改；`CLAUDE_CLIENT_TOOLS` 常量不动；新开关为 0 时 `client_tools_for_turn` 的每条返回路径（含对象同一性与列表内容）与 HEAD 逐字节相同；`note()`、`redo_plan()` 的对外行为（状态码、报错文案、返回值）不变；`lib/novels.ts`、`lib/desk.ts`、`components/novel/*`、`NovelDraftCard.tsx` 不动；`components/desk/*` 除上述三份外不动；不新增依赖；不新增 JSX `<dialog`。

### 4.2 后端

**T1 表与落库（`database.py`、`agent_store.py`）**

1. 在 `NOVEL_DRAFTS_INDEX`（`:85`）之后加：

   ```python
   # 聊天修改意见卡：作者在卡片上点按钮才会交给编辑部或重新定稿细纲。
   NOVEL_FEEDBACK_DDL = """
       CREATE TABLE IF NOT EXISTS novel_feedback (
           id TEXT PRIMARY KEY,
           owner_username TEXT NOT NULL,
           conversation_id TEXT NOT NULL,
           novel_id TEXT DEFAULT NULL,
           book_title TEXT NOT NULL DEFAULT '',
           next_chapters TEXT NOT NULL DEFAULT '',
           current_plan TEXT NOT NULL DEFAULT '',
           plan_chapter INTEGER DEFAULT NULL,
           written_json TEXT NOT NULL DEFAULT '[]',
           note_id INTEGER DEFAULT NULL,
           note_sent_at TIMESTAMP DEFAULT NULL,
           redo_started_at TIMESTAMP DEFAULT NULL,
           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
           updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
       )
   """
   NOVEL_FEEDBACK_INDEX = "CREATE INDEX IF NOT EXISTS idx_novel_feedback_owner ON novel_feedback(owner_username)"
   ```

   `init_db` 里紧跟 `await db.execute(NOVEL_DRAFTS_INDEX)` 无条件执行这两句（**不随任何环境变量变化**）；紧跟 `:163` 的 `novel_draft_id` 那行加 `await _safe_migrate(db, "ALTER TABLE messages ADD COLUMN novel_feedback_id TEXT DEFAULT NULL")`。不新增迁移版本号，`/health` 仍五道迁移。

2. `save_message`：在 `novel_draft_id: str | None = None,` 之后加 `novel_feedback_id: str | None = None,`。归属核对块照写歌 / 草稿的写法（`SELECT 1 FROM novel_feedback WHERE id = ? AND owner_username = ? AND conversation_id = ?`，命中才存，否则或出异常存 NULL，变量名 `stored_novel_feedback_id`），**必须放在写歌核对块之后、`# 书斋草稿归属同样只做附加校验` 那行注释之前**（原因：`test_novel_chat_create.py:654-659` 的坏副本会把从这行注释到 `INSERT` 之间的内容整段替换）。`INSERT` 的列清单、`VALUES` 占位符（多一个 `?`）、参数元组三处各加一项（`novel_feedback_id` / `stored_novel_feedback_id`）。

3. 清空历史（`:509` 之后）、删号（`:988` 之后）各加 `await db.execute("DELETE FROM novel_feedback WHERE owner_username = ?", (username,))`，在同一事务里。

4. `agent_store.get_conversation_messages` 的 SELECT 在 `novel_draft_id` 之后加 `, novel_feedback_id`；`delete_conversation` 在删草稿的语句之后加 `DELETE FROM novel_feedback WHERE owner_username = ? AND conversation_id = ?`，同一事务。

**T2 `backend/novel/feedback.py`（新；不得在模块顶层导入 `novel.service`，避免与 service 形成环）**

1. 常量：`TEXT_MAX = 500`，`ISSUE_MAX = 200`，`WRITTEN_MAX = 10`。

2. `def validate_feedback_args(args, book) -> tuple[dict | None, str | None]`（普通函数）。`args` 是 Claude 的工具参数（不是 dict 按空 dict 处理），`book` 是 `service.detail()` 的返回值。`title = (book.get("title") or "").strip() or "未命名小说"`；`{n}` 一律是去首尾空白后的 `len()`。分三段检查：

   **第一段：格式错误，全部收集**。按下表顺序逐项检查，命中就记下一句（同一句只记一次），这一段查完后有任何错误就用「；」连接全部句子返回，不再做第二、三段：

   | 检查 | 报错文本 |
   |---|---|
   | `next_chapters` 出现且不是 None、不是 str | `next_chapters 要是文字` |
   | `next_chapters` 去首尾空白后超过 500 字 | `交给编辑部的要求现在 {n} 字，最多 500 字，请精简后再写` |
   | `current_plan` 出现且不是 None、不是 str | `current_plan 要是文字` |
   | `current_plan` 去首尾空白后超过 500 字 | `重新定稿的要求现在 {n} 字，最多 500 字，请精简后再写` |
   | `written_chapters` 出现且不是 None、不是 list | `written_chapters 要是列表` |
   | 列表超过 10 项（此时不再逐项检查） | `已写章节现在 {n} 条，最多 10 条`（`{n}` 为项数） |
   | 按列表顺序逐项：不是 dict，或 `chapter` 不是 int（`bool` 不算 int），或 `issue` 不是 str（命中后跳过这一项的后两条检查） | `已写章节的每一项要有 chapter（整数）和 issue（文字）` |
   | `chapter` 不在本书「`chapter <= chapters_done` 且状态为 `done` 或 `stale`」的章里（命中后跳过这一项的下一条检查） | `第 {chapter} 章还没写好，不能放进已写章节` |
   | `issue` 去首尾空白后为空或超过 200 字 | `第 {chapter} 章的问题现在 {n} 字，要在 1–200 字之间` |

   **第二段**：三类都为空（字符串去空白后为空、列表为空或缺省）→ 返回 `修改意见卡至少要写一项：以后章节的要求、这一章细纲的要求或已写章节的问题`。

   **第三段：状态错误，全部收集**，有任何一句就用「；」连接返回：

   | 检查 | 报错文本 |
   |---|---|
   | `next_chapters` 非空且书的 `status` 为 `completed` | `《{title}》已经完结，编辑部不会再读留言；已写章节的问题可以放进 written_chapters` |
   | `next_chapters` 非空且书的 `status` 为 `failed` | `《{title}》处于失败状态，编辑部不会再读留言；已写章节的问题可以放进 written_chapters` |
   | `current_plan` 非空，但书的 `status` 不是 `awaiting_plan` 或找不到 `awaiting_plan_approval` 的章 | `《{title}》现在没有等作者确认的细纲，current_plan 只能在等确认细纲时填写` |
   | `current_plan` 非空、书为 `awaiting_plan` 且有 `awaiting_plan_approval` 的章，但 `automation` 不是 `per_chapter` | `《{title}》现在不是逐章确认，卡片上不能重新定稿这一章细纲；这一项请在回复里请作者到书斋处理` |

   其中 `automation`：`book.get("config")` 是 dict 时取其 `"automation"`，缺省或不是 str 时为 `"per_batch"`。通过时返回：

   ```python
   {
       "title": title,
       "status": <book["status"]>,
       "automation": <同上>,
       "max_chapters": <book.get("max_chapters") 为 int（不是 bool）时取它，否则 None>,
       "next_chapters": <去首尾空白后的文本，可能为 "">,
       "current_plan": <去首尾空白后的文本，可能为 "">,
       "awaiting_chapter": <书为 awaiting_plan 时，status 为 awaiting_plan_approval 的最大章号；否则 None>,
       "plan_chapter": <current_plan 非空时等于 awaiting_chapter；否则 None>,
       "written": [{"chapter": n, "title": <该章 detail 里的 title 原文，None 时为 "">, "issue": <去首尾空白>}, ...],  # 保持入参顺序
   }
   ```

3. `async def create_feedback(username, conversation_id, book, clean) -> dict`：照 `novel/drafts.py:create_draft` 的写法（`aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT)`），插入一行：`id=str(uuid4())`、`novel_id=book["id"]`、`book_title=clean["title"]`、`next_chapters`、`current_plan`、`plan_chapter`、`written_json=json.dumps(clean["written"], ensure_ascii=False)`。同一个连接里再算 `awaiting_is_final`：`clean["awaiting_chapter"]` 不为 None 时读 `SELECT meeting_json FROM novel_chapters WHERE novel_id=? AND chapter=?`，解析成 dict、其 `decision` 是 dict 且 `decision.get("ending_status") == "end"` 为 True，其余（含解析失败、没有这一行、`awaiting_chapter` 为 None）为 False。返回 `{"id": <id>, "awaiting_is_final": <bool>}`。

**T3 书斋侧（`novel/service.py`、`routers/novel.py`）**

1. `async def _insert_pending_note(db, username, novel_id, text) -> int`：在调用方事务里数该书 `status='pending'` 的留言，≥5 则 `fail('待处理留言最多五条')`；否则 `INSERT INTO novel_notes(novel_id,username,text,status) VALUES(?,?,?,'pending')`，返回 `cursor.lastrowid`。`note()` 改为 `BEGIN IMMEDIATE` → `owned()` → `await _insert_pending_note(...)` → `commit` → `return {'status':'pending'}`，对外行为不变。`reject_end`（`:733-736`）不动。

2. `async def feedback_view(username, feedback_id) -> dict`：读 `novel_feedback` 中 `id=? AND owner_username=?` 的行，不存在 `fail('修改意见不存在', 404)`。返回（键名与类型逐一如下，不多不少）：

   ```python
   {
       "id": str,
       "novel_id": str | None,
       "book_title": str,
       "next_chapters": str,
       "current_plan": str,
       "plan_chapter": int | None,
       "written": [{"chapter": int, "title": str, "issue": str}],   # written_json 解析失败按 []
       "note": None | {                       # note_id 为 NULL 时为 None
           "sent_at": str,                     # note_sent_at
           "status": "pending" | "delivered" | None,   # 按 note_id 且 novel_id 查 novel_notes；查不到为 None
           "delivered_chapter": int | None,
           "adopted": bool | None,             # 解析方式同 service.notes()：只有 delivered 才取 response_json
           "response": str | None,
           "planned_chapter": int | None,      # 见下方「已被细纲读到」
           "planned_adopted": bool | None,
           "planned_response": str | None,
       },
       "redo_started_at": str | None,
       "book": None | {                       # novel_id 为 NULL，或 novels 里查不到「id=novel_id 且 username=本人」时为 None
           "status": str,
           "chapters_done": int,
           "max_chapters": int | None,         # 照 summary()（:196）从 config_json 取；解析失败为 None
           "awaiting_chapter": int | None,     # status 为 awaiting_plan 时取 awaiting_plan_approval 的最大章号，否则 None
           "awaiting_is_final": bool,          # awaiting_chapter 那一行 meeting_json 的 decision.ending_status == "end"；算法同 T2.3
           "pending_notes": int,               # 该书 status='pending' 的留言数
           "automation": str,                  # config_json 的 automation；缺省或不是 str 时 "per_batch"
           "redo_cost": "strawberries" | "own_model" | "free",
           "plan_row_status": str | None,      # plan_chapter 那一章的 novel_chapters.status；plan_chapter 为 None 或无此行时 None
           "redo_pending": bool,               # plan_row_status == "planning" 且该行 meeting_json 解析成 dict、其 "_redo_note" 不为 None
       },
       "created_at": str,
   }
   ```

   - `config_json` 用 `json.loads` 解析，失败或不是 dict 时按 `{}` 处理。
   - **`redo_cost`**：`editor = config.get("agents", {}).get("editor")`（`agents` 不是 dict 时视为 `{}`）。`editor == "byok:self"` → `"own_model"`；否则 `NovelBilling.is_free({"model": editor if isinstance(editor, str) else ""})` 为真 → `"free"`；其余 → `"strawberries"`。`NovelBilling` 在函数内 `from .billing import NovelBilling` 导入。
   - **已被细纲读到**：只在 `note.status == "pending"` 且 `book` 不为 None 时计算，否则三个 `planned_*` 都是 None。按 `SELECT chapter, meeting_json FROM novel_chapters WHERE novel_id=? AND status IN ('awaiting_plan_approval','planning','writing') ORDER BY chapter DESC` 逐行看：`meeting_json` 解析失败或不是 dict 就跳过这一行；`brief = meeting.get("brief")`，是 dict 且 `brief.get("user_notes")` 是 list，并且其中有 dict 项的 `id` 规范化后等于 `str(note_id)`（规范化：转成 str，以 `N` 开头就去掉这个 `N`），就取这一行：`planned_chapter = chapter`；再在 `meeting.get("decision")`（是 dict 时）的 `user_note_responses`（是 list 时）里找第一项 dict，其 `note_id`（没有就用 `id`）规范化后等于 `str(note_id)`：`planned_adopted` 取它的 `adopted`（是 bool 才取，否则 None），`planned_response` 取它的 `response`（是 str 才取，否则 None）；找不到这一项两者都是 None。取到第一行就停。

3. `async def send_feedback_note(username, feedback_id) -> dict`，一个 `BEGIN IMMEDIATE` 事务里按顺序：
   - 卡片行不存在 → `fail('修改意见不存在', 404)`；
   - `note_id` 已有值 → 不再检查任何条件，提交（无改动）后返回 `feedback_view`（**幂等**）；
   - `next_chapters` 去空白后为空 → `fail('这张卡没有要交给编辑部的内容')`；
   - `novel_id` 为 NULL，或 `SELECT status FROM novels WHERE id=? AND username=?` 查不到 → `fail('这本书已经删除')`；
   - 书 `status` 为 `completed` → `fail('这本书已经完结，编辑部不会再读留言')`；为 `failed` → `fail('这本书处于失败状态，编辑部不会再读留言')`；
   - `note_id = await _insert_pending_note(db, username, novel_id, next_chapters)`（满 5 条时 409「待处理留言最多五条」，卡片不变）；
   - `UPDATE novel_feedback SET note_id=?, note_sent_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_username=? AND note_id IS NULL`；`commit`；返回 `feedback_view`。

4. 重新定稿（**核对、改库、记账在同一个写事务**）：

   - 从 `redo_plan` 抽出 `async def _begin_redo(db, username, novel_id, text, expected_chapter=None) -> int`，在调用方已经 `BEGIN IMMEDIATE` 的连接上依次：`book = await owned(db, username, novel_id, ('awaiting_plan',))`；取 `status='awaiting_plan_approval'` 中章号最大的一行，没有或没有 `meeting_json` 时 `fail('当前没有可重做的待批细纲，请刷新后重试')`；`expected_chapter` 不为 None 且与该章号不等时 `fail(f'第 {expected_chapter} 章细纲已经不在等你确认了')`；写 `_redo_note`、`_redo_count+1`、章节改 `planning`（语句与现有 `redo_plan` 相同）；`await _activate(db, book, username)`；返回章号。
   - `redo_plan()` 改为：`BEGIN IMMEDIATE` → `await _begin_redo(db, username, novel_id, data.text)` → `commit`；之后照旧 `from .runner import start_novel`、`await start_novel(novel_id, username)`、`return await detail(username, novel_id)`。对外行为不变。
   - `async def redo_feedback_plan(username, feedback_id) -> dict`，在一个 `BEGIN IMMEDIATE` 里按顺序：
     - 卡片行不存在 → 404 `修改意见不存在`；
     - `redo_started_at` 已有值 → 提交（无改动），不启动后台，返回 `feedback_view`（幂等）；
     - `current_plan` 去空白后为空，或 `plan_chapter` 为 NULL → `fail('这张卡没有重新定稿的要求')`（v1.4：正常建卡路径下 `current_plan` 非空时一定有 `plan_chapter`，这一条只防直接改库造出的卡跳过章号核对）；
     - `novel_id` 为 NULL 或书查不到 → `fail('这本书已经删除')`；
     - 书 `status` 不是 `awaiting_plan` → `fail(f'第 {plan_chapter} 章细纲已经不在等你确认了')`；
     - 书的 `automation`（解析同 T3.2）不是 `per_chapter` → `fail('这本书现在不是逐章确认，重新定稿后会直接写正文；请到书斋里操作')`；
     - `await _begin_redo(db, username, novel_id, Note(text=current_plan).text, expected_chapter=plan_chapter)`（它抛出的 HTTPException 原样向上抛）；
     - 同一事务 `UPDATE novel_feedback SET redo_started_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_username=? AND redo_started_at IS NULL`；`commit`。
     - 提交之后（连接已关闭）才 `from .runner import start_novel`、`await start_novel(novel_id, username)`；最后返回 `feedback_view`。提交前任何异常都回滚，卡片和书都不变。两个并发请求时，后到的一个等前一个提交后看到 `redo_started_at` 已有值，直接返回视图。

5. `delete()`（`:773-783`）：在 `UPDATE novel_drafts ... :781` 之后、同一事务里加 `UPDATE novel_feedback SET novel_id=NULL, updated_at=CURRENT_TIMESTAMP WHERE owner_username=? AND novel_id=?`。

6. `routers/novel.py`：在 `@router.get('/drafts/{draft_id}')` 之后、`@router.get('/{novel_id}')` 之前加三个路由，都只用 `workshop_user` 门控（**不读** `FIONA_NOVEL_CHAT_FEEDBACK`）：
   - `GET /feedback/{feedback_id}` → `service.feedback_view`；签名照 `:46-51` 的草稿路由写。
   - `POST /feedback/{feedback_id}/note`，`@limiter.limit('20/minute')`，无请求体，签名 `async def send_feedback_note(request: Request, feedback_id: str, user: str = Depends(workshop_user))` → `service.send_feedback_note`；
   - `POST /feedback/{feedback_id}/redo`，`@limiter.limit('20/minute')`，无请求体，签名同上（函数名 `redo_feedback_plan`）→ `service.redo_feedback_plan`。

**T4 Claude 工具（`studio/sources.py`、`services/claude_agent.py`、`services/chat_service.py`）**

1. `studio/sources.py`：紧跟 `novel_create_enabled` 加
   `def novel_feedback_enabled(username: str) -> bool: return os.getenv('FIONA_NOVEL_CHAT_FEEDBACK', '0') == '1' and novel_chat_enabled(username)`。

2. `claude_agent.py`：紧跟 `NOVEL_DRAFT_TOOL` 定义新常量（描述逐字如下）：

   ```python
   NOVEL_FEEDBACK_TOOL = _tool(
       "draft_novel_feedback",
       "把你对作者某本书的修改意见做成聊天里的「修改意见卡」；免费，不会改动书斋里的任何内容，交给编辑部、重新定稿都要作者在卡片上点按钮。意见按用途分三类写：以后章节的要求、正等作者确认的这一章细纲的修改要求、已写章节的问题；同一条要求只写进一栏。前面对话里已经写过的意见直接整理，不必重读原文。不确定这本书现在的状态时先调用 list_novels，状态是「等你确认细纲」才填 current_plan。要改人物的外形、性格或动机（锁定设定），不要写进卡片的任何一栏，在回复里请作者到书斋的人物页修改：用留言或重新定稿去改，会被审校当成与锁定设定冲突；情节上的约束（例如某人物不能提前退场）照常写进 next_chapters。整张卡合计尽量不超过 1500 字。",
       {
           "book": {"type": "string", "description": "书名，和 read_novel 用的一样"},
           "next_chapters": {"type": "string", "maxLength": 500,
                             "description": "对还没写的章节的要求，最多 500 字。作者点「交给编辑部」后成为一条留言，编辑部只在下一次为新的一章规划细纲时参考一次，不会长期生效。只写以后要怎样写，不要写章号，也不要写「重写第几章」；多件事分点写，编辑部只能整条采纳或不采纳。"},
           "current_plan": {"type": "string", "maxLength": 500,
                            "description": "只在这本书正等作者确认细纲时填写，最多 500 字。你看不到这一版细纲（read_novel 只读已写好的章节），编辑部重新定稿时也看不到它，只会拿原来的讨论材料加上这段要求重新写一版。所以不要描述或引用细纲里的内容（例如「保留第二场」），只分点写这一章必须做到和必须避免的事，每条单独读得懂。"},
           "written_chapters": {"type": "array", "maxItems": 10,
                                "description": "已经写好的章节里的问题，最多 10 条，只给作者看；书斋不会自动修改，要作者自己去书斋改稿。需要在后面的章节里补救的，把补救要求另写进 next_chapters。",
                                "items": {"type": "object",
                                          "properties": {"chapter": {"type": "integer", "minimum": 1, "maximum": 300},
                                                         "issue": {"type": "string", "maxLength": 200,
                                                                   "description": "这一章的问题和建议，最多 200 字"}},
                                          "required": ["chapter", "issue"]}},
       },
       ["book"],
   )
   ```

3. `client_tools_for_turn`：在 `if novel_create_enabled(ctx.user): tools.append(NOVEL_DRAFT_TOOL)` 之后、写歌追加之前，另起一行 `from studio.sources import novel_feedback_enabled`，再 `if novel_feedback_enabled(ctx.user): tools.append(NOVEL_FEEDBACK_TOOL)`。**不要**改动或合并已有的 `from studio.sources import novel_create_enabled` 与 `if novel_create_enabled(ctx.user):` 两行（`test_novel_chat_create.py:586` 用其中的 `if novel_create_enabled(ctx.user):` 做坏副本锚点，只替换第一处出现）。

4. 每轮标志：紧跟 `draft_conversation_id = ctx.conversation_id`（`:477`）加 `feedback_written = False` 与 `feedback_conversation_id = ctx.conversation_id`。

5. 执行分支：紧跟 `draft_novel` 分支、在 `elif name == "generate_image":` 之前加 `elif name == "draft_novel_feedback":`：
   - `feedback_written` 为真 → `result_text = "本轮已写过一张修改意见卡，请直接回答主人"`（不计错）。
   - 否则在 `try` 里：`from studio import novel_chat`、`from novel import service`、`from novel.feedback import create_feedback, validate_feedback_args`；`book, error = await novel_chat._resolve(ctx.user, args.get("book"))`，有 `error` → `result_text = error`、`agent_tool_errors += 1`；否则 `detail = await service.detail(ctx.user, book["id"])`，`clean, error = validate_feedback_args(args, detail)`，有 `error` 同上；否则（会话为 None 时照草稿分支 `:737-740` 解析默认会话）`created = await create_feedback(ctx.user, feedback_conversation_id, detail, clean)`，组卡片并下发：

     ```python
     card = {"type": "card", "subtype": "novel_feedback", "source": "书斋",
             "points": [f"修改意见《{clean['title']}》", "交给编辑部、重新定稿都要作者在卡片上点按钮"],
             "feedback_id": created["id"], "error": False}
     ```

     `feedback_written = True`、`state.novel_feedback_id = created["id"]`、`state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"`、`delivered = True`、`yield chat._sse({"card": card, "append": True})`。
   - `except Exception` → `result_text = "修改意见卡暂时不可用"`、`agent_tool_errors += 1`。
   - 成功时回灌给 Claude 的 `result_text` 由下面几句**按顺序**直接拼接（无分隔符、无空格），`K = clean["awaiting_chapter"]`，`S = clean["status"]`，`M = clean["max_chapters"]`，`A = clean["automation"]`，`F = created["awaiting_is_final"]`：
     1. `修改意见卡已放进聊天：《{title}》。卡片上的内容还没有生效，要等作者自己点按钮。`
     2. `next_chapters` 非空时，按顺序取第一条命中的一句，再接 `留言只用一次，不会长期生效，交出后不能撤回。`：
        - `S == "awaiting_end"`：`「以后的章节」要作者点「交给编辑部」才会交出；这本书正等作者确认完结，只有作者选择再写几章，编辑部才会看到。`
        - `K` 不为 None 且（`F` 为真，或 `M` 不为 None 且 `K >= M`）：`「以后的章节」要作者点「交给编辑部」才会交出；第 {K} 章会是这本书的最后一章，只有作者选择再写几章，编辑部才会看到。`
        - `K` 不为 None：`「以后的章节」要作者点「交给编辑部」才会交出；这本书正等作者确认第 {K} 章细纲，交出后要到第 {K+1} 章规划细纲时编辑部才会看到。`
        - 其余：`「以后的章节」要作者点「交给编辑部」才会交出，编辑部只在下一次为新的一章规划细纲时参考一次。`
     3. `current_plan` 非空：`「第 {K} 章细纲」要作者点「带着这些要求重新定稿」并在确认框里确认后才会重新定稿；编辑部看不到现在这一版细纲。`
     4. `K` 不为 None、`current_plan` 为空且 `A == "per_chapter"`：`如果有只针对第 {K} 章的要求，请告诉作者可以在书斋里直接改第 {K} 章细纲，或者下一轮再出一张带 current_plan 的卡。`
     5. `written` 非空：`已写章节的问题只给作者看，书斋不会自动修改，要作者自己去书斋改稿：改最新写好的一章会重新归档（可能扣草莓）；改较早的章会让后面已写的章永久待复核、不能做成片，故事圣经与章节摘要也不会重算。`
     6. `请如实告诉作者，不要说已经交给编辑部或已经改好。`

6. `chat_service.py`：`ChatState` 在 `novel_draft_id` 之后加 `novel_feedback_id: str | None = None`；`_save_response` 的 `save_message(...)` 加 `novel_feedback_id=state.novel_feedback_id`。

7. 镜子轮不带工具、危机轮不追加——沿用现有条件，不另写。

### 4.3 前端

**T5 `frontend/lib/novelFeedback.ts`（新）**

导出类型 `NovelFeedbackNote`、`NovelFeedbackBook`、`NovelFeedbackView`（字段与 §4.2 T3.2 一一对应，`redo_cost` 写成 `"strawberries" | "own_model" | "free"` 联合类型）与三个函数：

```ts
const feedbackPath = (id: string) => API_BASE + "/novels/feedback/" + encodeURIComponent(id);
export const getNovelFeedback = (id: string, signal?: AbortSignal) => apiJson<NovelFeedbackView>(feedbackPath(id), { signal });
export const sendNovelFeedbackNote = (id: string, signal?: AbortSignal) => apiJson<NovelFeedbackView>(feedbackPath(id) + "/note", { method: "POST", signal });
export const redoNovelFeedbackPlan = (id: string, signal?: AbortSignal) => apiJson<NovelFeedbackView>(feedbackPath(id) + "/redo", { method: "POST", signal });
```

（`apiJson` 来自 `@/lib/agents`，`API_BASE` 来自 `@/lib/config`。）

**T6 `frontend/components/NovelFeedbackCard.tsx`（新）**

Props：`feedbackId: string`、`onOpenNovel?: (path: string) => void`、`initialView?: NovelFeedbackView`（**只给测试用**：提供时初始即为就绪态、挂载时不请求；`ChatCard` 不传）。

0. **写法约束**（违反任何一条，lint 或交互测试会失败）：
   - 文件首行 `"use client";`。import 只用：`react` 的 `useEffect`、`useId`、`useRef`、`useState`；`@/lib/agents` 的 `ApiError`；`@/components/ConfirmDialog` 的 `useConfirm`；`@/lib/novels` 的 `displayNovelChapterTitle`、`novelErrorMessage`；`@/lib/novelFeedback` 的三个请求函数与 `NovelFeedbackView` 类型。
   - 整个卡片写成**一个**函数组件，不要定义子组件再用 `<Xxx />` 渲染（交互测试的迷你运行时不展开嵌套组件，组件内定义组件还会触发 `react-hooks/static-components`）。可以写在组件内直接调用、返回 JSX、内部不调用 hooks 的普通函数。
   - 所有 hooks 写在任何 `return` 之前。`const confirm = useConfirm();`，调用一律写成 `await confirm({ … })`（括号后紧跟 `{`，写在同一行）；组件里不得定义名为 `alert` 的函数或变量。
   - effect 体内不得同步 `setState`；渲染期间不读 `ref.current`。初始状态用 `useState` 的初始化函数（有 `initialView` 时直接是就绪态），加载态照 `NovelDraftCard` 由「结果记账的 key 是否等于当前 key」推导；取数 effect 开头写 `if (initialView) return;`，依赖数组写全（含 `initialView`）。
   - 新增和改动的文件不得产生任何 lint warning（基线 25，上限 25）。

1. **取数**：挂载时 `getNovelFeedback(feedbackId, controller.signal)`，按 `feedbackId` 与「第几次读取」记账；卸载或 key 变化时 abort。不轮询。
   - 加载中：`<p role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">正在读取修改意见…</p>`。
   - `ApiError` 且 status 为 404、`message === "修改意见不存在"`：同样的 `<p role="status" …>`，文字「修改意见已不存在」，没有重试。
   - 其他 `ApiError`：显示 `novelErrorMessage(error)`；非 `ApiError`：显示「修改意见暂时读不到」。这两种用 `<div role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">` 包住文字 `<p>` 和一个「重新读取」按钮（`btn btn-quiet mt-2 min-h-10`），点击把读取次数加 1，重新触发取数 effect（加载态仍靠推导，不在 effect 里同步 setState）。

2. **就绪态结构**：外框 `ceramic-card w-[420px] max-w-full overflow-hidden`。
   - 标题行：`<div className="px-4 py-3 text-fs-15">`，文字 `修改意见 · 《{book_title.trim() || "未命名小说"}》`。
   - 依次最多三节（某类为空就整节不渲染）。每节外层 `<section className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>`；节头 `<div className="flex flex-wrap items-center gap-2">`，里面节标题 `<span className="text-fs-12 text-[color:var(--ink2)]">`，有状态标签时紧跟 `<span className="tag">`；正文 `<p className="mt-1 whitespace-pre-wrap break-words text-fs-13">`，**完整显示，不截断，不要照抄 NovelDraftCard 的 80 字摘要**；说明 `<p className="mt-2 break-words text-fs-12 text-[color:var(--ink2)]">`，说明里的多句直接拼接（无空格）；回应行 `<p className="mt-1 break-words text-fs-12 text-[color:var(--ink2)]">`；按钮行 `<div className="mt-3 flex flex-wrap gap-2">`；错误提示 `<p role="alert" className="mt-2 break-words text-fs-13 text-[color:var(--seal)]">`，放在该节末尾。
   - 卡片底部：`view.novel_id` 与 `view.book` 都有值且传了 `onOpenNovel` 时，渲染 `<div className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>`：若 `note !== null`、`redo_started_at` 有值，或第一节处于第 3 种状态（渲染了「去书斋改细纲」），先放一句说明 `<p className="mb-2 break-words text-fs-12 text-[color:var(--ink2)]">`，文字为「书斋如果之前已经开着这本书，要回到书架重新打开它，才会看到最新的细纲和留言。」；`redo_started_at` 有值时再直接接「在旧页面上点「批准（原样）」会直接批准你还没看过的新细纲，点「改完批准」会用旧页面里的内容覆盖新细纲。」；再放「在书斋打开」按钮（`btn btn-quiet min-h-10`），点击 `onOpenNovel("/novels/" + view.novel_id + "?embed=1")`。
   - **全卡不得出现** `font-medium`、`font-semibold`、`font-bold`、`fontWeight` / `font-weight`、`<b>` / `<strong>` 标签；只用 `text-fs-12/13/15` 字号令牌；颜色只用 `text-[color:var(--ink2)]`，错误提示另用 `text-[color:var(--seal)]`；不新增颜色、字号令牌，不写十六进制色。

3. **第一节「第 {N} 章细纲」**（`current_plan.trim()` 非空且 `plan_chapter !== null` 才有；`N = plan_chapter`），正文为 `current_plan`。下文「费用句」按 `book.redo_cost` 取：`strawberries` →「重新定稿会再调用一次编辑部，按实际用量扣草莓。」；`own_model` →「这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。」；`free` →「这次重新定稿不扣草莓。」。状态按顺序取第一条命中的：
   1. `redo_started_at` 有值：标签「已发起重新定稿」，说明再按顺序取第一条：
      - `book` 为 null →「这本书已经删除。」
      - `book.redo_pending` 且 `status` 为 `running` 或 `setup_running` →「编辑部正在带着这些要求重新定稿第 {N} 章细纲，完成后会停下来等你确认。卡片不会自动更新，刷新页面可以看到最新进展。」
      - `book.redo_pending` 且 `status === "paused"` →「重新定稿还没有完成：这本书暂停了，请到书斋查看原因；恢复写作后会接着重新定稿。」
      - `book.redo_pending` 且 `status === "failed"` →「重新定稿没有完成：这本书处于失败状态，不能再继续写。」
      - 其余 →「已经带着这些要求重新定稿过第 {N} 章细纲。」；若 `status === "awaiting_plan"` 且 `awaiting_chapter === N`，再接「新细纲在书斋里等你确认。」
   2. `book` 为 null：说明「这本书已经删除。」
   3. `status === "awaiting_plan"`、`awaiting_chapter === N` 且 `automation === "per_chapter"`：说明 =「重新定稿会让编辑部拿原来的讨论材料加上这些要求，重新写一版第 {N} 章细纲；它看不到你现在看到的这一版，是否照改由编辑部判断。」+ 费用句 +「只想改几处的话，也可以在书斋里直接改细纲，再点「改完批准」（批准后照常开始写这一章）。」按钮：「带着这些要求重新定稿」（`btn min-h-10`）；传了 `onOpenNovel` 时再放「去书斋改细纲」（`btn btn-quiet min-h-10`，点击 `onOpenNovel("/novels/" + novel_id + "?embed=1")`）。点「带着这些要求重新定稿」先按第 6 条重新读取一次最新状态（v1.4），新视图仍处于本支状态才 `await confirm({ title: \`重新定稿第 ${N} 章细纲\`, body: <见下>, confirmLabel: "重新定稿" })`，返回 false 就什么都不做；返回 true 才调 `redoNovelFeedbackPlan`。确认框 body =「编辑部会拿原来的讨论材料加上这张卡上的要求，重新写一版第 {N} 章细纲（看不到现在这一版，是否照改由编辑部判断）。」+ 费用句（按重新读到的新视图的 `book.redo_cost` 取）+「完成后新细纲仍会停下来等你确认。」
   4. `status === "awaiting_plan"` 且 `awaiting_chapter === N`（不是逐章确认）：说明「这本书现在不是逐章确认，重新定稿后会直接开始写正文、不会停下来等你确认；这一项请到书斋里处理。」
   5. `status === "failed"`：说明「这本书处于失败状态，不能再继续写，这一项不能再用。」
   6. `plan_row_status === "awaiting_plan_approval"` 且 `status === "paused"`：说明「第 {N} 章细纲还在等你确认，但这本书暂停了；恢复写作、回到等你确认后可以再用这一项。」
   7. `plan_row_status === "awaiting_plan_approval"` 且 `status` 为 `running` 或 `setup_running`：说明「第 {N} 章细纲还在等你确认，但书斋正在处理这本书；处理完、回到等你确认后可以再用这一项。」
   8. `plan_row_status === "planning"` 且 `status` 为 `running` 或 `setup_running`：说明「书斋正在重新定稿第 {N} 章细纲；完成后如果仍在等你确认这一章，可以再用这一项。」
   9. `plan_row_status === "planning"` 且 `status === "paused"`：说明「书斋重新定稿第 {N} 章细纲时暂停了；恢复写作、回到等你确认后可以再用这一项。」
   10. 其余：说明「第 {N} 章细纲已经不在等你确认了，这一项不能再用。」

4. **第二节「以后的章节」**（`next_chapters.trim()` 非空才有），正文为 `next_chapters`。下文 `K = book.awaiting_chapter`、`M = book.max_chapters`，`r(x) = x || "（没有写回应）"`。状态按顺序取第一条命中的：
   1. `note` 不为 null 且 `note.status === "delivered"`：标签 `delivered_chapter` 不为 null 时「已下发到第 {delivered_chapter} 章」，否则「编辑部已回应」；回应行：`adopted === true` →「编辑部采纳：{r(response)}」，`adopted === false` →「编辑部没有采纳：{r(response)}」，否则「编辑部的回应：{r(response)}」。
   2. `note` 不为 null、`note.status === "pending"`、`note.planned_chapter` 不为 null 且 `book` 不为 null：标签「待下发」；说明在 `book.status === "failed"` 时为「编辑部已经在第 {planned_chapter} 章细纲里读到这条要求，但这本书处于失败状态，不能再继续写，这条留言不会被下发。」，否则为「编辑部已经在第 {planned_chapter} 章细纲里读到这条要求；这一章写完后，这里会记为已下发。」；`planned_adopted` 不为 null 或 `planned_response` 非空时加回应行：`planned_adopted === true` →「编辑部采纳：{r(planned_response)}」，`false` →「编辑部没有采纳：{r(planned_response)}」，否则「编辑部的回应：{planned_response}」。
   3. `note` 不为 null（其余情况）：标签「待下发」；说明按顺序取第一条：`book` 为 null →「这本书已经删除。」；`completed` →「这本书已经完结，这条留言不会再被读到。」；`failed` →「这本书处于失败状态，这条留言不会再被读到。」；`awaiting_end` →「这本书在等你确认完结；只有选择再写几章，编辑部才会读到这条要求。」；`awaiting_plan`、`K` 不为 null 且（`book.awaiting_is_final` 为真，或 `M` 不为 null 且 `K >= M`）→「第 {K} 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。」；`awaiting_plan` 且 `K` 不为 null →「第 {K+1} 章规划细纲时，编辑部会读到这条要求。」；其余 →「编辑部会在下一次为新的一章规划细纲时读到这条要求；那一章写完后，这里会显示编辑部的回应。」**不得用其他方式推算章号。**
   4. `book` 为 null：说明「这本书已经删除。」，无按钮。
   5. `book.status === "completed"`：「这本书已经完结，编辑部不会再读留言。」，无按钮；`"failed"`：「这本书处于失败状态，编辑部不会再读留言。」，无按钮。
   6. `book.pending_notes >= 5`：按钮「交给编辑部」**禁用**，说明「这本书的待下发留言已满 5 条，等编辑部用掉一些再交。」；这段说明的 `<p>` 用 `useId()` 生成的 id，禁用的按钮加 `aria-describedby` 指向它。
   7. 其余：按钮「交给编辑部」（`btn btn-primary min-h-10`），点击直接调 `sendNovelFeedbackNote`（不弹确认框）。说明依次拼接：`pending_notes > 0` 时「这本书现在有 {pending_notes} 条待下发留言（最多 5 条，包括书斋里留的和别的卡片交出的）。」；再按顺序取一句：`awaiting_end` →「这本书在等你确认完结；只有选择再写几章，编辑部才会读到这条要求。」；`awaiting_plan`、`K` 不为 null 且（`book.awaiting_is_final` 为真，或 `M` 不为 null 且 `K >= M`）→「第 {K} 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。」；`awaiting_plan` 且 `K` 不为 null →「第 {K} 章细纲已经出来了，这条要求要到第 {K+1} 章规划细纲时编辑部才会读到；想让第 {K} 章就照做，可以在书斋里直接改第 {K} 章细纲。」；其余 →「编辑部只在下一次为新的一章规划细纲时参考一次（正在规划、正在重新定稿或已经出了细纲的那一章读不到），不会长期生效。」；最后接「交出后不能撤回。」

5. **第三节「已写好的章节」**（`written` 非空才有）：`<ol className="mt-1 space-y-1 text-fs-13">`，每项 `<li key={index} className="break-words">第 {chapter} 章 {displayNovelChapterTitle(title) || "待定章名"}：{issue}</li>`；说明「这些章节不会自动修改，要改就在书斋里打开这一章，点「改稿」自己改。改最新写好的一章会重新归档（再调用一次档案员，可能扣草莓），完成前不会开始下一章，已经出来、等你确认的下一章细纲也不会跟着重做。改较早的章节会把它后面已写好的章永久标成「待复核」，有待复核章节的书不能做成片；故事圣经和章节摘要也不会重算，编辑部之后仍按旧记录规划。可以再交一条留言说明改了什么，但留言只在下一次规划细纲时参考一次。」

6. **操作与错误**：
   - `busy` 状态（`"note" | "confirm" | "redo" | null`）加 `const busyRef = useRef(false)` 防重入（同 `SongProjectCard` 的做法，但不要照搬它在 `finally` 里复位，见下）；`busyRef` 只在事件处理函数里读写，渲染里的 `disabled` 只看 `busy`。`busy` 不为 null 时「交给编辑部」「带着这些要求重新定稿」都禁用；`busy === "note"` 时「交给编辑部」的文字改成「正在交给编辑部…」，`busy === "redo"` 时「带着这些要求重新定稿」的文字改成「正在发起重新定稿…」（确认框还在询问时 `busy === "confirm"`，文字不变）；「去书斋改细纲」「在书斋打开」不受影响。
   - 两个处理函数开头 `if (busyRef.current) return;`，然后置 `busyRef.current = true`、清空旧错误。交留言：`setBusy("note")` 后发请求。重新定稿（v1.4 改写）：`setBusy("confirm")` 后先 `await getNovelFeedback(feedbackId, signal)` 重新读取一次。读取失败：在第一节末尾显示 `novelErrorMessage(error)`，保留旧视图，复位 `busy` 与 `busyRef`，不弹确认框、不发请求。读取成功：先用新视图替换当前视图（不回到加载态），再对**新视图**调用 `redoAvailable`（见 §4.6 P1）——为假就复位并结束，卡片按新视图显示新状态，不弹确认框、不发请求；为真才用 `redoCostSentence(新视图.book.redo_cost)` 拼确认框 body、`await confirm(...)`，返回 false 时复位（`busyRef.current = false`、`setBusy(null)`）并结束；返回 true 才 `setBusy("redo")` 并发请求。重新读取期间与确认框询问期间一样是 `busy === "confirm"`，按钮文字不变。
   - 动作请求用的 `AbortController` 在 `useEffect(() => { const c = new AbortController(); actionRef.current = c; return () => c.abort(); }, [])` 里创建，不要在渲染期或 `useRef` 初值里 new。每次 `await` 之后先判断 `signal.aborted`，已中止就直接 return：不 setState、不显示错误、不重新拉取。
   - 成功：用返回值替换当前视图，`busy` 与 `busyRef` 都复位。失败：先在出错那一节末尾显示 `novelErrorMessage(error)`，再 `await getNovelFeedback(id, signal)` 一次——成功只替换视图（不回到加载态），失败保留旧视图；拉取结束后才复位 `busy` 与 `busyRef`。新视图里该操作已经生效（交留言：`note !== null`；重新定稿：`redo_started_at` 有值）时清掉这条错误。错误提示保留到下一次点击任一动作按钮。

**T7 接入（`ChatBubble.tsx`、`useConversations.ts`、`page.tsx`）**

1. `ChatBubble.tsx`：`import NovelFeedbackCard from "@/components/NovelFeedbackCard";`；`CardData` 在 `draft_id` 之后加 `feedback_id?: string;  // "novel_feedback" = 修改意见卡`；`ChatCard` 紧跟 `novel_draft` 分支加：

   ```tsx
   if (card.subtype === "novel_feedback") {
     if (!card.feedback_id) return null;
     return <NovelFeedbackCard feedbackId={card.feedback_id} onOpenNovel={onOpenNovel} />;
   }
   ```

   不改 `ChatBubble` 的 props、解构与两个 `<ChatCard ... />`。

2. `useConversations.ts`：`StoredMessage` 在 `novel_draft_id` 之后加 `novel_feedback_id?: string | null;`；`toMessages` 在草稿分支之后加：

   ```ts
   if (message.role === "assistant" && message.novel_feedback_id) {
     cards.push({ source: "书斋", points: [], subtype: "novel_feedback", feedback_id: message.novel_feedback_id });
   }
   ```

   （新分支只能引用 `message` 与 `cards`。）

3. `page.tsx`：两处 `const card: CardData = {...}` 各在 `draft_id: data.card.draft_id,` 之后加一行 `feedback_id: data.card.feedback_id,`（不加 `??` 默认值）。不得改动 `// 旅行规划卡：` 到 `if (data.done)` 之间的任何字节（`test_claude_agent_frontend.py:117-123` 哈希锁），不新增第三个 `const card: CardData` 块。用按字节的方式编辑，改完 `head -c 3 frontend/app/page.tsx | xxd -p` 仍为 `efbbbf`。

### 4.4 文档与配置（只追加或替换下面写明的句子，其余字节不动）

`backend/tests/test_claude_agent_docs.py:35-43` 要求六份文档各自含有一批短语（如「卡片不落库」「历史图片」「镜子模式不带工具」「危机轮不进入智能体模式」）。改写「哪些卡片落库」那一句时**只改例外清单**，保留子串「卡片不落库」与这一行的其余内容。

1. 例外清单改为把修改意见卡并进去，例如 `CLAUDE.md:30` 改成「其余卡片不落库；写歌卡、书斋草稿卡与修改意见卡例外：`messages` 新增可空 `song_project_id`、`novel_draft_id` 与 `novel_feedback_id`，刷新后按它们重建，其余卡片刷新后仅保留正文摘要和生成图。」`README.md:142`、`PLAN.md:23`、`docs/ARCHITECTURE.md:21`、`docs/DEPLOYMENT.md:257` 同样处理；`backend/.env.example:47` 写的是「卡片不落库（写歌卡例外：…）」，把括号里改为同时列出写歌卡、书斋草稿卡与修改意见卡及三列。
2. **只在 §4.1 白名单的六份文档内**搜索「哪些卡片落库 / `messages` 有哪些卡片 id 列 / 刷新后重建哪些卡片」这一事实的所有陈述点，逐处改对（已知 `docs/ARCHITECTURE.md:54`、`:137`、`:141` 仍只写了写歌），在报告里列出改过的每一处。白名单外（`docs/tasks/**`、代码注释、`frontend/AGENTS.md` 等）发现的同类陈述只列进报告，不改。
3. `CLAUDE.md`：在「聊天建书」段（`:196`）之后另起一段，至少写明：开关与三个前提（`FIONA_NOVEL_CHAT_FEEDBACK` 默认 `0`、只有字面 `1` 开启、调用时读取、须 `FIONA_NOVEL_CHAT=1` 与小说工坊白名单、非危机轮；三个接口只用 `workshop_user` 门控，关开关后已有卡片仍可用）；工具名与三类字段及长度上限、一次报全格式错误；工具免费、只写卡片记录、不碰书斋业务表、不扣草莓、每轮最多一张、占 4 次名额；「交给编辑部」的接口、原子幂等、拒绝条件（删除、完结、失败、满 5 条），以及留言只在下一次规划细纲时被读一次、等确认第 N 章细纲时交出的要到第 N+1 章、卡片从进行中章节的 meeting 里查留言是否已被读到；「带着这些要求重新定稿」先确认费用（按主编模型区分扣草莓 / 用自己的模型额度 / 不扣）、后端在一个写事务里核对章号与逐章确认再改库并记账（`_begin_redo` 与 `redo_plan` 共用）、编辑部看不到被否的那一版；已写章节只展示；新表 `novel_feedback` 与 `messages.novel_feedback_id`（`init_db` 幂等、不新增迁移版本号、`/health` 仍五道迁移）；删号、删会话、清空历史同事务删卡，删书把 `novel_id` 置 NULL；修改意见卡不触发案头定位；平台路径不支持。
4. `README.md`：在「聊天建书」段（`:367` 附近）之后加一段面向作者的说明：怎么用；四个按钮（「交给编辑部」「带着这些要求重新定稿」「去书斋改细纲」「在书斋打开」）各管什么；费用（交留言免费；重新定稿按主编模型扣草莓或用你自己的模型额度，书斋 `DEV_MODE` 下不扣）；留言只用一次、交出后不能撤回；重新定稿是重写一版、编辑部看不到被否的那一版；手改已写章节的后果（改最新章会重新归档、改较早的章会永久标「待复核」且圣经与摘要不重算）；书斋页面若已开着要回书架重开（旧页面上点「批准（原样）」会批准还没看过的新细纲，点「改完批准」会用旧内容覆盖新细纲）；重新定稿在后台进行，可能因余额、预算、每日上限或自带模型不可用而暂停，卡片会显示，要到书斋恢复；卡上文字不能改、旧卡不会作废，同一本书有多张卡时别重复交；编辑部的「采纳」是它自己报的，不保证细纲真的照做；改人物设定请到书斋人物页；书名只是部分相同时告诉分身完整书名即可，两本完全同名的书分身分不清；思考档位低时整张卡太长可能出不了卡。`docs/ARCHITECTURE.md:418` 段末追加一句数据流说明。`docs/DEPLOYMENT.md` 的「小说工坊 P1 配置」节（`:860-868` 附近）补上 `FIONA_NOVEL_CHAT`、`FIONA_NOVEL_CHAT_CREATE`、`FIONA_NOVEL_CHAT_FEEDBACK` 三个开关各一行。`PLAN.md` 在「2026-11-10 案头」一节之后新开「2026-11-12 修改意见卡」一节（做了什么、§7 的已知局限）。
5. `backend/.env.example`：在 `FIONA_NOVEL_CHAT_CREATE` 那组（`:209-210`）之后加：

   ```
   # 聊天修改意见卡：须同时开启 FIONA_NOVEL_CHAT；默认关闭，只有字面 1 开启。工具只写卡片，作者在卡片上点按钮才交给编辑部或重新定稿细纲。
   FIONA_NOVEL_CHAT_FEEDBACK=0
   ```

6. 文档里不得出现本机绝对路径（`test_claude_agent_docs.py:44`）。

### 4.5 测试

**既有测试只许改这一个文件的两处**：`backend/tests/test_studio_sources_readonly_integration.py`
- (a) `:28-29` 的集合加入 `"novel_feedback"`；
- (b) `:197` 的 `elif node.module == "novel.drafts":` 分支（断言体在 `:198-199`）之后、`:200` 的 `else:` 之前加：

  ```python
  elif node.module == "novel.feedback":
      assert {alias.name for alias in node.names} <= {
          "validate_feedback_args", "create_feedback"}, path
  ```

  其余一个字节不动。`git diff -U0 HEAD -- 该文件` 恰两个 hunk。

**新测试 `backend/tests/test_novel_chat_feedback.py`（后端）**

通用要求：
- 顶部 `from test_claude_agent_runtime import FakeStream, call, harness, message, run`——`harness` 必须一并 import 才能作为夹具注入，不要直接调用它。
- `offline` 照 `test_novel_chat_create.py:34-52` 写；`enabled` / `create_enabled` 照 `:55-68` 写（`FIONA_NOVEL_USERS` 含 `agent-user`），并显式 `setenv` / `delenv` `FIONA_NOVEL_CHAT_FEEDBACK`。**不要定义或使用** `test_novel_chat.py` 的 `catalog`；**不得桩** `sources.find_candidates`、`novel_chat._resolve`、`service.detail`。
- 需要书的用例：照 `draft_db`（`test_novel_chat_create.py:71` 起）建临时库并 `init_db`，再照 `test_studio_sources_readonly_integration.py:44-71` 的 INSERT 写法给 `agent-user` 插 `novels`（`seed_idea`、`config_json`、`budget_strawberries` 必填；`config_json` 按用例需要写 `agents.editor`、`automation`、`target.max_chapters`）与 `novel_chapters`。HTTP 用例照 `test_novel_p1_api.py` 的 `workshop` 夹具写。
- 每条断言都要能区分对错实现；「没有副作用」用 `novel_notes` / `novels` / `novel_chapters` 行内容不变、`runner.TASKS` 里没有该书的未完成任务来断，**不能用**余额（`DEV_MODE=1` 下恒不变）或 `state.billable`。
- 测试不得调用 git、不得读仓库外文件；环境变量一律用 `monkeypatch.setenv` / `delenv`。服务层用例凡是会启动 runner 的，要么先把 `novel.runner.start_novel` monkeypatch 成只记录调用的异步桩，要么照 `test_novel_p1_runner.py:41-44` 在用例结束前 `drain`；不得在 `asyncio.run` 里启动 runner 后直接离开。打了桩的书会一直停在 `running`，每个重新定稿场景用新库或新用户，避免被 `check_active` 拦成别的 409。
- **两个新测试文件在 HEAD 上都必须能被收集**：不在模块顶层导入 `novel.feedback` 或 `service` 的新函数，也不在顶层读新增的前端文件，一律放到用例里导入或读取。新功能类用例开头调用 `_require_feedback()`（照 `test_novel_chat_create.py:144-146` 的 `_require_drafts()`，断言 `backend/novel/feedback.py` 存在，HEAD 上以 `AssertionError` 失败）。回归类用例不得调用它：第 1 条中 `FEEDBACK` 未设 / `"0"` / `"true"` 的组合、第 8 条 `POST /novels/{id}/notes` 行为不变、第 9 条 `redo_plan` 行为不变。

清单：

1. 开关矩阵：对 `test_novel_chat_create.py:160-166` 的五组 `(method, crisis)`，在 `FIONA_NOVEL_CHAT_CREATE ∈ {未设, "1"}` × `FIONA_NOVEL_CHAT_FEEDBACK ∈ {未设, "0", "true", "1"}` 的每种组合下，断言 `client_tools_for_turn` 的名字列表**有序**等于写死的期望：基础 `["get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image", "list_novels", "read_novel"]`；只在 `method == "jwt"` 时追加 `"start_film"`；只在 `CREATE == "1"` 时追加 `"draft_novel"`；只在 `FEEDBACK == "1"` 时最后追加 `"draft_novel_feedback"`——以上只对 `crisis is None` 的三组。`crisis` 为 `possible` / `high` 的两组不论 `CREATE`、`FEEDBACK` 取何值，名字列表都固定为 `["get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image"]`，并断言 `is CLAUDE_CLIENT_TOOLS`；`crisis is None` 的三组断言 `is not`。另对 `FIONA_NOVEL_CHAT=0`、用户不在白名单两组，在 `FEEDBACK="1"` 下断言 `is CLAUDE_CLIENT_TOOLS`。若写死的期望与 `test_novel_chat_create.py` 既有用例对同一组合的断言不一致，以既有用例为准，并在报告里说明。
2. `validate_feedback_args`：§4.2 T2.2 两张表每一行一条用例、第二段一条，断言**逐字**的报错文本（含 `{n}`；含「不是逐章确认的书填了 `current_plan`」那一行，`book["config"]["automation"]` 分别为 `per_batch`、缺省）；空白字符串视为空；`chapter` 为 `True` 被拒；两栏都超长时一次返回两句、以「；」连接、顺序同表；两项都是形状错误时那句只出现一次；超过 10 项时不出现逐项错误；有格式错误时不出现第二、三段的句子；完结的书同时填了 `next_chapters` 与 `current_plan` 时返回两句状态错误。通过时返回值逐字段比对（含 `status`、`automation`、`max_chapters`、`awaiting_chapter`、`plan_chapter`、`written` 的章名与顺序）。
3. 成功路径：真走 `services.claude_agent.stream_claude_agent`，用 `run(h)` 驱动，假传输回放一次 `draft_novel_feedback` 的 tool_use；在模块顶层导入真实的 `services.chat_service._save_response`，用例里 `monkeypatch.setattr(h.chat, "_save_response", 真实函数)`（照 `test_novel_chat_create.py:18-19`、`:285`）；把 `h.ctx.conversation_id` 设为临时库里用 `agent_store.create_conversation` 建的真实会话（照 `:83-85`）。断言：`novel_feedback` 多 1 行且各列正确；SSE 里卡片 dict 与 §4.2 T4.5 逐字相等；落库的 assistant 消息 `novel_feedback_id` 等于该 id（经 `agent_store.get_conversation_messages` 读回）；`full_response` 恰含 1 次「［卡片：」；回灌给 Claude 的 `result_text` 与 §4.2 T4.5 的拼接逐字相等；`novel_*` 业务表内容不变、无后台任务。至少四组：「`awaiting_plan`、`chapters_done=1`、第 1 章 `done`、第 2 章 `awaiting_plan_approval`，三类都有」；「`completed`、只有已写章节」；「`awaiting_end`、只有 `next_chapters`」；「`awaiting_plan`、逐章确认、`current_plan` 为空、有 `next_chapters`」（含第 4 句）；「`awaiting_plan`、`automation` 为 `per_batch`、只有 `next_chapters`」（没有第 4 句）；「`awaiting_plan`、第 K 章 meeting 的 `decision.ending_status == "end"`、`K < max_chapters`、只有 `next_chapters`」（第 2 句走「最后一章」一支，全文不含「第 {K+1} 章」）。
4. 一轮两次调用：第二次回「本轮已写过一张修改意见卡，请直接回答主人」，只有 1 行。
5. 找书失败（没找到、多本候选：插两本书名都含查询词、且没有唯一完全匹配的书）：回灌 `_resolve` 的原文、`agent_tool_errors` +1、不建卡。
6. `save_message` 传入别人的 / 别的会话的卡片 id → 存 NULL；同一条消息同时带草稿 id 与卡片 id 时两列都存。
7. `feedback_view`：未交 / 已交 pending / 已交 delivered（采纳与不采纳各一）/ 书已删（`book` 与 `note.status` 为 None）/ `written_json` 损坏时 `written` 为 `[]`；键集合逐一断言（含 `note` 与 `book` 的子键）。另外：
   - 已被细纲读到：直接造库——pending 留言 `N{id}` 在第 K 章（`awaiting_plan_approval`）meeting 的 `brief.user_notes` 里、`decision.user_note_responses` 有 `{"note_id": "N{id}", "adopted": false, "response": "…"}` → `planned_chapter == K`、`planned_adopted is False`、`planned_response` 逐字；该行 meeting 损坏时三者都为 None；`done` 的章即使含这条留言也不算。
   - 真实流程（HTTP）：逐章确认的书停在等确认第 K 章时交出留言 → 批准第 K 章（`POST /novels/{id}/plan/approve`，载荷照 `test_novel_p1_api.py` 的写法）→ `wait` 到书停在等确认第 K+1 章 → 视图 `note.status == "pending"` 且 `note.planned_chapter == K+1`。
   - `redo_cost` 三种：`agents.editor == "byok:self"` → `own_model`；平台模型且 `DEV_MODE=1` → `free`；平台模型且 `delenv("DEV_MODE")` → `strawberries`。`automation` 缺省为 `per_batch`；`max_chapters` 取自 `target.max_chapters`；`awaiting_is_final`（等确认章 meeting 的 `decision.ending_status` 为 `"end"` 时真，为其他值、meeting 损坏或不在等确认时假）；`plan_row_status` 与 `redo_pending`（`planning` 且含 `_redo_note` 为真；`planning` 无 `_redo_note`、或 `awaiting_plan_approval` 为假）。
8. 交给编辑部（HTTP）：成功后该书恰多 1 条 pending 留言且正文等于 `next_chapters`，返回视图 `note.status == "pending"`；第二次请求不新增留言、`note_id` 不变；用 `asyncio.gather` 并发两次 `send_feedback_note` 只产生 1 条留言；已有 5 条 pending → 409「待处理留言最多五条」且卡片 `note_id` 仍为 NULL；书 `completed` / `failed` / 已删 → 对应 409 文案；别人的卡片 → 404；`next_chapters` 为空 → 409。另加一条：`POST /novels/{id}/notes` 的行为不变（第 6 条 409「待处理留言最多五条」、正常时返回 `{"status": "pending"}`）。
9. 重新定稿：
   - 服务层（把 `novel.runner.start_novel` monkeypatch 成只记录调用的异步桩；`service.py` 在函数内导入它，所以桩会生效）：书 `awaiting_plan`、逐章确认、等确认的是 `plan_chapter` → 该章 `status == "planning"`、`meeting_json._redo_note == current_plan`、`_redo_count` 加 1、`redo_started_at` 有值、桩恰被调用 1 次。第二次调用：返回视图，`_redo_count` 不变，桩不再被调用。等确认的章号与 `plan_chapter` 不同（用 SQL 造）、书不是 `awaiting_plan` → 409「第 {N} 章细纲已经不在等你确认了」；`automation` 为 `per_batch` → 409「这本书现在不是逐章确认，重新定稿后会直接写正文；请到书斋里操作」；`current_plan` 为空 → 409；书已删 → 409；以上每种拒绝后卡片 `redo_started_at` 仍为 NULL、`novel_chapters` 行内容不变、桩未被调用。并发：`asyncio.gather(redo_feedback_plan(...), redo_feedback_plan(...), return_exceptions=True)` 两路都返回视图（dict），`_redo_count` 只加 1，桩只调 1 次。
   - HTTP 真跑 runner（`workshop` 夹具）：先记下 `len(fake.calls)` 与该章 `meeting.get("_redo_count", 0)`（第一次重新定稿前没有这个键），`n` 为它加 1；`POST /novels/feedback/{id}/redo` 返回 200 且 `redo_started_at` 有值；`wait(client, book, "awaiting_plan")` 之后断言 `len(fake.calls) == 前值 + 1`、`fake.calls[-1]` 的步骤键以 `-redo{n}.json` 结尾、`FakeLLM.payload(fake.calls[-1])["author_instruction"] == current_plan`、`_redo_count == 前值 + 1`、meeting 不含 `_redo_note`、该章 `status == "awaiting_plan_approval"`。**HTTP 用例里不要断言 `planning` 或 `_redo_note`**（只存在约 15 ms）。
   - 重新定稿在后台失败（HTTP）：把 `workshop` 的 `fake.script` 设为 `lambda request, index: StepFailed("x", status="decision_invalid") if "-redo" in (request.get("step_key") or "") else None`（`from novel.llm_router import StepFailed`；FakeLLM 返回异常对象就抛出），POST 重新定稿后 `wait` 到书为 `paused`，断言视图 `book.plan_row_status == "planning"`、`book.redo_pending is True`、`redo_started_at` 有值。若实测书没有进入 `paused`，在报告里写明实际状态，改用直接写库构造同样的状态。
   - `redo_plan` 行为不变：`POST /novels/{id}/plan/redo` 在等确认时返回 200 的详情、后台完成后 `_redo_count` 加 1；书不在 `awaiting_plan` 时 409「当前状态不能执行此操作」。
10. 清理：清空历史、删号、删会话后对应卡片行消失，别人的、别的会话的不受影响；删书后卡片 `novel_id` 为 NULL，`feedback_view` 的 `book` 为 None。
11. 表与列随 `init_db` 无条件创建（新开关为 0 时也存在），且对已有 `messages` 表的老库能补上 `novel_feedback_id` 列。
12. 自检（坏实现必须让对应断言变红；写法：共享检查函数，先跑正样本、再跑坏副本，并断言坏副本源码与原文不同；替换锚点先 `assert marker in source`、只替换 1 处）至少六条：去掉新开关判断；去掉 `feedback_written` 每轮限制；`save_message` 不核对归属；`send_feedback_note` 不判 `note_id` 已有值；`redo_feedback_plan` 调 `_begin_redo` 时不传 `expected_chapter`；`feedback_view` 不计算 `planned_chapter`（恒为 None）；`feedback_view` 的 `awaiting_is_final` 恒为 False。`novel/service.py` 的坏副本这样加载：`module = types.ModuleType("novel._bad_service"); module.__package__ = "novel"; module.__file__ = "<novel._bad_service>"; exec(compile(bad_source, module.__file__, "exec"), module.__dict__)`，然后直接调用坏模块的函数，不经 HTTP。

**新测试 `backend/tests/test_novel_chat_feedback_frontend.py`**（照 `test_novel_chat_create_frontend.py` 的结构；起 node 的用例开头先过依赖守卫，缺 node 或缺依赖时 skip，文案沿用 8f1f3f8 的「frontend dependencies unavailable: …」「node is unavailable」；不起 node 的源码断言放在守卫之前，CI 上也要能跑）：

1. `ChatCard` 渲染 `novel_feedback`：注入 `NovelFeedbackCard` 桩，断言桩收到 `feedbackId` 与 `onOpenNovel`；缺 `feedback_id` 时返回 null。
2. `toMessages` 在 node 里执行：只有卡片 id、三列都有（顺序为写歌、草稿、意见）、都没有（无 `cards`）三例结果逐字段相等。
3. `page.tsx`：两个 `const card: CardData = {...}` 块**各自**恰含一行 `feedback_id: data.card.feedback_id,`（断言绑定到块，不用全文计数）；BOM 仍在。
4. `NovelFeedbackCard` 服务端渲染：用 `test_desk_views_frontend.py` 的 `NODE_RENDERER` 写法；`STUBS` 放 `@/lib/novelFeedback`（三个函数一被调用就抛错）、`@/components/ConfirmDialog`（`useConfirm` 返回一个被调用就抛错的函数）、`@/lib/agents`（`ApiError` 类与抛错的 `apiJson`）、`@/lib/auth`、`@/lib/config`；`@/lib/novels` 不桩，用真实模块。渲染脚本另约定：props 里 `__withOpenNovel` 为 true 时注入 `onOpenNovel = () => {}`，并在传给组件前删掉这个键（照 `__childrenText` 的特例写法；JSON 传不了函数）。用 `initialView`：
   - §4.3 T6.3、T6.4、T6.5 列出的每个状态各一条：断言本状态的标签、说明、回应行、按钮有无与 `disabled` 逐字正确，并断言同一节里其他状态**独有**的说明句一句都不出现（与本状态说明逐字相同的句子不算，例如多个状态共用的「这本书已经删除。」，这类状态靠标签、按钮有无区分）；三种 `redo_cost` 各一条（说明里的费用句）。
   - 条件重叠的用例锁住判断顺序：`redo_started_at` 有值且 `book` 为 null → 只出现「这本书已经删除。」；`redo_started_at` 有值、`redo_pending` 为 false、书 `paused`（`failed` 同理）→ 只出现「已经带着这些要求重新定稿过第 {N} 章细纲。」，不出现「还没有完成」「没有完成」；`plan_row_status` 为 `awaiting_plan_approval`、书 `failed` →「这本书处于失败状态，不能再继续写，这一项不能再用。」；`note` 已交且书 `completed` → 标签「待下发」、说明「这本书已经完结，这条留言不会再被读到。」、没有「交给编辑部」按钮；`planned_chapter` 为 K+1 时全文不含「第 {K+2} 章」；`planned_chapter` 为 K、书 `failed` → 出现「…这条留言不会被下发。」、全文不含「这一章写完后」；`K < max_chapters` 且 `awaiting_is_final` 为真 →「第 {K} 章会是这本书的最后一章…」，全文不含「第 {K+1} 章」。
   - 不传 `initialView` 做 SSR：出现 `role="status"` 的「正在读取修改意见…」。
   - 正文完整：`next_chapters`、`current_plan` 各 500 字，末尾各放一个不同的哨兵字；断言全文都出现，且没有「…」。
   - 底部与入口（每条都要有正样本与反样本）：传 `__withOpenNovel` 时，「在书斋打开」在书存在时出现、书已删时不出现；不传时都不出现。提示句只在 `note !== null`、`redo_started_at` 有值或第一节可用时出现，后半句「在旧页面上点「批准（原样）」…」只在 `redo_started_at` 有值时出现。「去书斋改细纲」只在第一节可用且传了 `__withOpenNovel` 时出现。
5. 交互（真执行点击，用 `test_desk_dock_races_frontend.py` 的迷你 hooks 运行时，effect 会执行；给这个运行时加一个 `unmount()`，依次调用所有 effect 的清理函数；按钮按「文字包含『交给编辑部』或『重新定稿』」或按节内顺序查找）：点「交给编辑部」恰调用一次 `sendNovelFeedbackNote`，请求期间两个动作按钮都禁用、被点的按钮文字为「正在交给编辑部…」；`useConfirm` 桩记录收到的 options：对 `strawberries`、`own_model`、`free` 三种视图各点一次「带着这些要求重新定稿」（桩返回 false），断言 `options.title === "重新定稿第 {N} 章细纲"`、`options.confirmLabel === "重新定稿"`、`options.body` 与 T6.3 第 3 条的拼接逐字相等，确认框询问期间按钮文字仍是「带着这些要求重新定稿」；确认框返回 false 时不调用 `redoNovelFeedbackPlan`、按钮恢复可用，返回 true 时恰调用一次；「交给编辑部」成功后再点「带着这些要求重新定稿」，confirm 桩恰被调用 1 次；接口报错时出现 `role="alert"` 且重新拉取恰一次；T6.1 三态：`getNovelFeedback` 桩分别 reject `new ApiError("修改意见不存在", 404)`、`new ApiError("x", 403)`、`new Error("x")`，flush 后依次显示「修改意见已不存在」、`novelErrorMessage(new ApiError("x", 403))` 的结果（在测试里用真实 `@/lib/novels` 算出期望）、「修改意见暂时读不到」，另外两种文案都不出现，后两种有「重新读取」按钮，点击后 `getNovelFeedback` 再被调用一次；卸载后在途的 POST 收到 abort，之后不再调用 `getNovelFeedback`，也不出现 `role="alert"`。
6. 源码约束（不起 node，放守卫之前）：`NovelFeedbackCard.tsx` 不含 `font-medium`、`font-semibold`、`font-bold`、`fontWeight`、`font-weight`、`<dialog`、`alert(`、`window.confirm`、`window.alert`；不匹配正则 `<(b|strong)[\s>]`（不要用子串 `<b`，会误中 `<button`、`<br`）；不匹配 `from test_component_language import NATIVE_DIALOG` 导入的正则；含 `const confirm = useConfirm();`；`source.count("confirm(") == source.count("confirm({") >= 1`。路由对应：照 `test_novel_p2_frontend.py:75-82` 的写法另写一个带方法的 AST 小函数，收集 `routers/novel.py` 里 `router.<方法>(...)` 的 `(方法, 归一后的路径)`，断言以 `/feedback` 开头的恰好是 `("get", "/feedback/{}")`、`("post", "/feedback/{}/note")`、`("post", "/feedback/{}/redo")` 各一次。
7. 请求路径（起 node，放守卫之后）：桩掉 `@/lib/agents` 的 `apiJson` 记录 `(url, init)`、`@/lib/config` 的 `API_BASE = "/api"`，用 id `a/b` 依次调用三个函数：第一次 `init.method === undefined`、url 为 `/api/novels/feedback/a%2Fb`；第二次 `init.method === "POST"`、url 为 `/api/novels/feedback/a%2Fb/note`；第三次 `init.method === "POST"`、url 为 `/api/novels/feedback/a%2Fb/redo`；三次的 `init.signal` 都原样透传。
8. 每条源码约束与第 7 条配坏副本自检（同后端第 12 条写法），至少：把 `await confirm({` 换成 `window.confirm("确定？")`；加一行 `if (!confirm(body)) return;`；加一行 `alert(novelErrorMessage(error));`；加一段 `<strong>交出后不能撤回</strong>`；加一处 `font-medium`；把 `"/redo"` 改成 `"/plan/redo"`；把 `own_model` 的费用句换成 `strawberries` 的（第 5 条的确认框断言必须变红）；把交留言的路由改成 `@router.get`（路由对应断言必须变红）。每条都必须变红。

### 4.6 R1 返修（v1.4，依据独立复核 `04-review.md`；R1 只做这一节）

**R1 白名单**（其余文件一字不动，包括 `02-spec.md`、`03-dispatch.md`、`04-review.md`、`05-fix-r1.md`、`impl/report.md`、任何既有测试文件与 `backend/tests/test_desk_polish_frontend.py`）：

- `frontend/components/NovelFeedbackCard.tsx`（只做 P1）
- `backend/novel/service.py`（只做 P2：`redo_feedback_plan` 里一处条件）
- `backend/tests/test_novel_chat_feedback.py`、`backend/tests/test_novel_chat_feedback_frontend.py`（R1 的全部测试改动只在这两个文件里）
- `PLAN.md`、`docs/DEPLOYMENT.md`、`README.md`、`CLAUDE.md`（只改 D1–D4 写明的句子）
- 新增 `docs/tasks/2026-11-12-novel-feedback/impl/report-r1.md`

**产品改动**

- **P1 点「带着这些要求重新定稿」先重新读取（作者 2026-11-12 确认）**。卡片不轮询，作者可能在书斋里改过主编模型、批准过这一章细纲，或在别处已经发起过重新定稿；确认框里的费用和这一项还能不能用，都以点击时重新读到的状态为准。流程见 §4.3 T6.3 第 3 支与 T6.6（v1.4 已改写）。实现约束：
  - 在组件函数之外新增两个模块级纯函数：`redoCostSentence(cost)` 返回三种费用句（映射与 T6.3 相同，`own_model`、`free` 之外一律按 `strawberries`）；`redoAvailable(view)` 判断第一节是否处于 T6.3 第 3 种状态，条件为 `view.current_plan.trim()` 非空、`view.plan_chapter !== null`、`view.redo_started_at` 为空、`view.book` 不为 null、`book.status === "awaiting_plan"`、`book.awaiting_chapter === view.plan_chapter`、`book.automation === "per_chapter"`。
  - 渲染时第 3 支的判断改为调用 `redoAvailable(view)`，费用句改为调用 `redoCostSentence(view.book?.redo_cost)`；`sendRedo` 对重新读到的新视图调用这两个函数。T6.3 其余分支的顺序、条件与文案不动；T6.4、T6.5 与底部提示不动。
  - 仍是单个函数组件；新增和改动的文件不得产生 lint warning。
- **P2 `redo_feedback_plan` 加固**：`current_plan` 去空白后为空，**或 `plan_chapter` 为 NULL** → `fail('这张卡没有重新定稿的要求')`（§4.2 T3 已改写）。只改这一处条件，判断顺序与其他语句不动。

**文档（逐字替换或插入，其余字节不动）**

- D1 `PLAN.md`「## 2026-11-12：修改意见卡」第二段两处：
  - 「「带着这些要求重新定稿」经 `POST /novels/feedback/{id}/redo` 先弹确认框说明费用（按主编模型区分扣草莓、用自己的模型额度或 `DEV_MODE` 下不扣），」改为「「带着这些要求重新定稿」经 `POST /novels/feedback/{id}/redo`：点击后卡片先重新读取一次最新状态，已经不能重新定稿时只更新卡片、不弹确认框，仍可重新定稿才弹确认框，按读到的主编模型说明费用（扣草莓、用自己的模型额度或 `DEV_MODE` 下不扣）；」
  - 「章号对不上、不是逐章确认或卡片已发起过都拒绝，」改为「章号对不上、不是逐章确认或卡上没有记下章号都拒绝，同一张卡重复点击不会再次发起，」
- D2 `docs/DEPLOYMENT.md`「数据库兼容 DDL 会在后端启动时执行。」那一段：在「`song_cleanup_queue` 四张表，不新增迁移版本号。」之后插入「书斋草稿与修改意见卡同样由 `init_db` 幂等创建 `novel_drafts`、`novel_feedback` 两张表，并补可空列 `messages.novel_draft_id`、`messages.novel_feedback_id`，不新增迁移版本号。」
- D3 `README.md` 修改意见卡一段：「书斋 `DEV_MODE` 下不扣——确认后重新写一版第 N 章细纲，」改为「书斋 `DEV_MODE` 下不扣——点按钮时卡片会先重新读一次这本书的最新状态，按最新的主编模型说明费用，已经不能重新定稿时只更新卡片、不弹确认框；确认后重新写一版第 N 章细纲，」
- D4 `CLAUDE.md` 聊天修改意见卡一段两处：
  - 「先由卡片按这本书的主编模型说明费用：」改为「点击后卡片先重新读取一次最新状态，已经不能重新定稿时只更新卡片、不弹确认框；仍可重新定稿时按读到的主编模型说明费用：」
  - 「不是 `per_chapter` 或卡上没有 `current_plan` 时拒绝」改为「不是 `per_chapter`、卡上没有 `current_plan` 或没有记下章号时拒绝」

**测试**（只在上面两个新测试文件里加或改。自检命名：后端以 `test_bad_` 开头，前端名字含 `self_check`。每条自检都按 §4.5 后端第 12 条的坏副本写法：共享检查函数，先跑正样本再跑坏副本，断言坏副本源码与原文不同；替换锚点先 `assert marker in source`，只替换 1 处）

后端 `test_novel_chat_feedback.py`：

- B1「已被细纲读到」覆盖三种进行中状态：把 `test_feedback_view_planned_read_from_in_progress_meeting` 的章节状态参数化为 `awaiting_plan_approval`、`planning`、`writing`，每种都断言 `planned_chapter == 2`、`planned_adopted is False`、`planned_response == "编辑部回应原文"`；「meeting 损坏」「`done` 不算」两段保留。自检：`novel/service.py` 坏副本把 `('awaiting_plan_approval','planning','writing')` 改成 `('awaiting_plan_approval','planning')` 时，`writing` 一组必须变红；改成 `('awaiting_plan_approval')` 时，`planning` 与 `writing` 两组都必须变红。
- B2 四个上限的边界正样本，各断言 `error is None` 并核对返回的清洗值：`next_chapters` 恰 500 字（前后再加空白，去空白后 500）；`current_plan` 恰 500 字（书 `awaiting_plan`、逐章确认、有等确认章）；某条 `issue` 恰 200 字；`written_chapters` 恰 10 条（书有 10 个已写好的章）。自检：`novel/feedback.py` 坏副本把这四处的 `>` 分别改成 `>=`，对应用例都必须变红。
- B3 `feedback_view` 的 `pending_notes`：本书 2 条 `pending`、1 条 `delivered`，同一用户的另一本书 1 条 `pending`，断言本书 `book["pending_notes"] == 2`。自检：计数写死为 0、去掉 `status='pending'` 条件，两种坏副本都必须变红；计数语句里若有按书过滤的条件，再加一条去掉它的坏副本。
- B4 `validate_feedback_args` 的 `chapter <= chapters_done`：书 `chapters_done=2`，第 3 章行状态为 `done`（用 SQL 造），`written_chapters` 只写第 3 章 → 返回状态错误「第 3 章还没写好，不能放进已写章节」。自检：去掉 `or number > chapters_done` 的坏副本必须变红。
- B5 回灌里「最后一章」走 `K >= max_chapters` 一支：照 §4.5 后端第 3 条的成功路径写法，造「`awaiting_plan`、第 K 章 meeting 的 `decision.ending_status == "continue"`、`K == max_chapters`、只有 `next_chapters`」，断言回灌给 Claude 的 `result_text` 里第 2 句是 §4.2 T4.5 的「`「以后的章节」要作者点「交给编辑部」才会交出；第 {K} 章会是这本书的最后一章，只有作者选择再写几章，编辑部才会看到。`」（K 代入实际章号），全文不含「第 {K+1} 章」。自检：`services/claude_agent.py` 坏副本把 `(F or (M is not None and K >= M))` 改成 `F` 必须变红。
- B6 P2：卡片 `current_plan` 非空、`plan_chapter` 为 NULL（用 SQL 造），书 `awaiting_plan`、逐章确认、等确认第 3 章 → 409「这张卡没有重新定稿的要求」；之后卡片 `redo_started_at` 仍为 NULL，`novel_chapters` 各行内容不变，`novel.runner.start_novel` 桩未被调用。自检：去掉新加的 `plan_chapter` 条件的坏副本必须变红（坏副本会对第 3 章发起重新定稿）。

前端 `test_novel_chat_feedback_frontend.py`：

- F1「书在等确认，但等的不是卡上这一章」：在 `PLAN_CASES` 加两条。(a) `plan_chapter=2`、`redo_started_at=None`、`book=make_book(awaiting_chapter=3, plan_row_status="done")`，逐章确认：说明逐字为「第 2 章细纲已经不在等你确认了，这一项不能再用。」，没有「带着这些要求重新定稿」与「去书斋改细纲」按钮；渲染时传 `onOpenNovel`（照现有 SSR 约定 `__withOpenNovel`），确保按钮缺失不是因为没传它。(b) `redo_started_at` 有值、`book=make_book(redo_pending=False, awaiting_chapter=3)`：标签「已发起重新定稿」，说明只有「已经带着这些要求重新定稿过第 2 章细纲。」，全文不含「新细纲在书斋里等你确认。」。自检：删掉第 3 种状态判断里的章号比较（P1 之后在 `redoAvailable` 里）时 (a) 必须变红；删掉第 1 支「新细纲在书斋里等你确认。」追加条件里的 `&& book.awaiting_chapter === chapter` 时 (b) 必须变红。
- F2 HEAD 守卫：下面 12 个用例（参数化展开后共 14 条）在 `require_node_dependencies()` 之后、第一次 `read(COMPONENT)` 或 `read(FEEDBACK_LIB)` 之前先调用 `_require_feedback()`：`test_feedback_card_note_click_disables_both_actions_while_pending`、`test_feedback_card_redo_confirmation_costs`、`test_feedback_card_redo_confirmed_calls_once_and_updates_view`、`test_feedback_card_note_success_then_redo_click_confirms_once`、`test_feedback_card_action_error_alerts_and_refetches_once`、`test_feedback_card_read_states_and_retry`、`test_feedback_card_note_error_then_success_clears_alert`、`test_feedback_card_redo_error_alerts_and_refetches_once`、`test_feedback_card_unmount_aborts_pending_post_without_refetch_or_alert`、`test_feedback_card_own_model_fee_copy_self_check`、`test_novel_feedback_request_paths_and_signal_passthrough`、`test_novel_feedback_request_path_self_check_catches_plan_redo`。R1 新增的新功能类用例同样在读源码之前先调用 `_require_feedback()`。`_require_feedback()` 一律放在依赖守卫之后，这样无 `node_modules` 副本里这些用例照样 skip。派单方会在 `7a17f64` 的导出上复跑前端新文件：新功能类用例必须以 `AssertionError` 失败，不得出现 `FileNotFoundError`。
- F3「最后一章」走 `K >= max_chapters` 一支（SSR）：书 `awaiting_plan`、`awaiting_chapter=50`、`max_chapters=50`、`awaiting_is_final=False`，卡上只有 `next_chapters`。(i) `note=None`：说明含「第 50 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。」，全文不含「第 51 章」；(ii) `note` 为 `pending`、`planned_chapter=None`：说明逐字为「第 50 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。」，全文不含「第 51 章」。自检：删掉 `|| (maxChapters !== null && awaitingChapter >= maxChapters)` 时两条都必须变红。
- F4 同步连点两次（第二次点击发生在任何重渲染之前）：交留言 → `sendNovelFeedbackNote` 只被调用 1 次；重新定稿（重新读取返回仍可用的视图，确认框返回 true）→ 点击触发的 `getNovelFeedback` 只 1 次、`confirm` 只 1 次、`redoNovelFeedbackPlan` 只 1 次。自检：分别删掉 `sendNote`、`sendRedo` 开头的 `if (busyRef.current) return;`，对应断言都必须变红。
- F5 卸载：(i) 重新读取还没返回时卸载，之后让它成功返回 → `confirm` 与 `redoNovelFeedbackPlan` 都未被调用；(ii) 确认框打开期间卸载，之后确认框返回 true → `redoNovelFeedbackPlan` 未被调用。两条都按 F6 断言卸载之后没有任何 state setter 调用。自检：删掉重新读取之后的 `if (signal?.aborted) return;` 时 (i) 必须变红；删掉 `await confirm(...)` 之后的 `if (signal?.aborted) return;` 时 (ii) 必须变红。
- F6 恒真断言：卸载用例里读冻结的 `lastTree` 得到的「没有 `role="alert"`」断言（迷你运行时 `unmount()` 之后 `flush()` 直接返回，这条不可能失败）改为可证伪的检查：迷你运行时记录 `unmount()` 之后对任何 state setter 的调用次数，断言为 0。自检：删掉交留言请求返回之后的 `if (signal?.aborted) return;`，并让请求在卸载之后成功返回时，计数必须大于 0，断言变红。
- F7 P1 重新读取：
  - (a) 费用变了：卡片初始视图 `redo_cost="own_model"`，点击时重新读取返回 `redo_cost="strawberries"`（其余不变）→ `confirm` 恰 1 次，body 含「重新定稿会再调用一次编辑部，按实际用量扣草莓。」、不含 `own_model` 的费用句；卡片第一节说明里的费用句也变成 `strawberries` 那句；确认后 `redoNovelFeedbackPlan` 恰 1 次。
  - (b) 已经不能用：重新读取返回 `awaiting_chapter=3`、`plan_row_status="done"`（卡上 `plan_chapter=2`）→ `confirm` 与 `redoNovelFeedbackPlan` 都未被调用；卡片说明变为「第 2 章细纲已经不在等你确认了，这一项不能再用。」，没有「带着这些要求重新定稿」按钮。
  - (c) 已在别处发起：重新读取返回 `redo_started_at` 有值 → `confirm` 与 POST 都未被调用，标签为「已发起重新定稿」。
  - (d) 重新读取失败：分别用 `ApiError`（例如 500）和非 `ApiError`（例如 `TypeError`）→ `confirm` 与 POST 都未被调用；第一节末尾 `role="alert"` 的文字等于 `novelErrorMessage(error)`（断言方式与现有「动作失败」用例相同）；卡片其余内容保持点击前的样子；之后「带着这些要求重新定稿」恢复可点（`disabled` 为 false）。
  - (e) 顺序与忙碌态：记录调用顺序，点击触发的 `getNovelFeedback` 在 `confirm` 之前；重新读取还没返回时，「交给编辑部」「带着这些要求重新定稿」都 `disabled`，按钮文字仍是「带着这些要求重新定稿」。
  - 自检（每条都必须变红）：坏副本跳过重新读取、直接用旧视图弹确认框 → (a)(b)(c) 变红；坏副本重新读取了，但费用句仍取点击前的视图 → (a) 变红；坏副本重新读取了，但不对新视图判断能不能用 → (b) 变红。
- F8 既有交互用例的调整：点击重新定稿现在先多一次 `getNovelFeedback`，相关用例的桩与 `calls.get` 期望照实调整（例如「重新定稿失败后只重新拉取一次」变成「点击时重新读取 1 次，失败后再拉取 1 次」）。不得删除用例，也不得放宽它们原本锁住的意图：确认框只弹一次、POST 只发一次、失败后只多拉一次、三种费用句逐字。

**R1 验收**：§5 第 1–9 条全部重跑。后端全量 passed = 8011 + 三个新测试文件的新收集数，0 skipped；无 `node_modules` 副本的 SKIPPED 总数 = 前端新文件里起 node 的用例数 + 9。报告写进 `impl/report-r1.md`，内容：拆分表；P1、P2、D1–D4、B1–B6、F1–F8 逐条对应改了什么；三个新测试文件的收集数；每条自检坏副本变红的输出摘要；§4.4 第 2 条要求的六份文档改动位置逐处列出（含 r0 已改的与本轮 D1–D4）；未完成或需人工确认的地方。

### 4.7 R2 返修（v1.5，只补测试；依据派单方对 R1 的对抗式核查）

**R2 白名单**：只许改 `backend/tests/test_novel_chat_feedback.py`、`backend/tests/test_novel_chat_feedback_frontend.py`，新增 `docs/tasks/2026-11-12-novel-feedback/impl/report-r2.md`。产品代码、文档、规格、返修单、复核文件、`impl/report.md`、`impl/report-r1.md` 与任何既有测试一律不动。自检的命名与写法同 §4.6。

前端 `test_novel_chat_feedback_frontend.py`：

- G1 F7(c)「已在别处发起」的重新读取视图只比卡片原视图多一个 `redo_started_at`：`interaction_view(redo_started_at="2026-11-12 10:01:00", book=make_book(redo_pending=False, awaiting_chapter=PLAN_CHAPTER))`（书仍 `awaiting_plan`、逐章确认、等确认的仍是卡上这一章）→ `confirm` 与 POST 都未被调用；标签「已发起重新定稿」；说明逐字为「已经带着这些要求重新定稿过第 {PLAN_CHAPTER} 章细纲。新细纲在书斋里等你确认。」。原来等确认第 3 章的那组数据与 F7(b) 重复，删掉或并入 (b)。新增自检：删掉 `redoAvailable` 里的 `&& !view.redo_started_at` 时这条必须变红；复用该夹具的既有自检仍须变红。
- G2 提前结束的路径必须真的复位（T6.6「复位 `busy` 与 `busyRef`」不能只看 `disabled`）：
  - F7(b) 的重新读取视图保留卡上的 `next_chapters`（卡上文字不会变，真实接口只会改书的状态）。
  - F7(b)、F7(c) 之后各再点一次「交给编辑部」：按钮 `disabled` 为 false，`sendNovelFeedbackNote` 恰被调用 1 次。
  - F7(d) 之后再点一次「带着这些要求重新定稿」：点击触发的 `getNovelFeedback` 累计 2 次。
  - 确认框取消之后（可在 `test_feedback_card_redo_confirmation_costs` 里或另开一条）再点一次「带着这些要求重新定稿」：`getNovelFeedback` 累计 2 次、`confirm` 累计 2 次。
  - 自检（四份坏副本，各自必须让对应断言变红）：不可用分支删掉 `busyRef.current = false;` 与 `setBusy(null);` 两句；不可用分支只删 `busyRef.current = false;`；重新读取失败分支只删 `busyRef.current = false;`；确认框取消分支只删 `busyRef.current = false;`。
- G3 卸载时重新读取被中止：新增一条，重新读取的桩像现有的 `deferred(signal)` 一样在 abort 时 reject，在重新读取途中卸载 → `confirm` 与 POST 都未被调用；卸载后 state setter 调用次数为 0；这次 GET 收到的 signal `aborted` 为 true。自检：删掉重新读取 `catch` 里的 `if (signal?.aborted) return;` 时必须变红。
- G4 F7(d) 再加一组非 `ApiError`：`new TypeError("Failed to fetch")` → 第一节末尾 alert 逐字为「请求未完成，请稍后重试。」（`frontend/lib/novels.ts` 的 `novelErrorMessage` 对不含汉字的报错返回这句）。自检：重新读取失败分支改为显示 `error instanceof Error ? error.message : "修改意见暂时读不到"` 时必须变红。
- G5 F1 (a)(b) 两条再断言 HTML 含「在书斋打开」，自证确实传了 `onOpenNovel`。

后端 `test_novel_chat_feedback.py`：

- G6 B1 的反例在「`done` 不算」旁边加一段 `stale`：章节状态为 `stale`、meeting 含这条留言 → `planned_chapter`、`planned_adopted`、`planned_response` 都是 None。自检：`novel/service.py` 坏副本把 `status IN ('awaiting_plan_approval','planning','writing')` 改成 `status<>'done'` 时，`stale` 一段必须变红。
- G7 B6 再加两种书态：书为 `running`（不是 `awaiting_plan`）、卡片 `novel_id` 为 NULL（书已删）→ 都是 409「这张卡没有重新定稿的要求」，卡片 `redo_started_at` 仍为 NULL，`novel.runner.start_novel` 桩未被调用。自检：坏副本把 ` or card['plan_chapter'] is None` 从第一条判断里去掉、改在 `await _begin_redo(` 那一行之前单独判断 `card['plan_chapter'] is None` 时必须变红（这时 `running` 会报「第 None 章细纲已经不在等你确认了」，书已删会报「这本书已经删除」）。

**R2 验收**：同 §4.6「R1 验收」：§5 第 1–9 条全部重跑；后端全量 passed = 8011 + 三个新测试文件的新收集数，0 skipped；无 `node_modules` 副本的 SKIPPED 总数 = 前端新文件里起 node 的用例数 + 9。报告写进 `impl/report-r2.md`：拆分表、G1–G7 逐条对应改了什么、三个新测试文件的收集数、每条自检坏副本变红的输出摘要、未完成或需人工确认的地方。

### 4.8 R3 返修（v1.6，只改 PLAN.md 一处）

**R3 白名单**：只许改 `PLAN.md`，新增 `docs/tasks/2026-11-12-novel-feedback/impl/report-r3.md`。

在「## 2026-11-12：修改意见卡」的「已知局限：」段，把「已经发起的重新定稿照常有效；只在 Claude 智能体模式开放。」逐字替换为「已经发起的重新定稿照常有效；点「带着这些要求重新定稿」时卡片先重新读取，发现这一项已经不能用就只更新卡片，被点的按钮随之消失、键盘焦点丢失，读屏软件也不会播报新的说明；确认框打开期间如果在书斋里又改了主编模型，框里写的费用会过时（实际按改后的模型计费，后端不核对作者确认时看到的费用类型）；只在 Claude 智能体模式开放。」。其余字节不动。

**R3 验收**：新句在 `PLAN.md` 中恰出现 1 次，旧句出现 0 次；`backend/tests` 里读 `PLAN.md` 的既有测试（`test_claude_agent_docs.py`、`test_chat_image_tool_docs.py`、`test_local_watch_docs.py`、`test_local_watch_capture_docs_r3.py`、`test_empty_states_match_profile.py`）全绿。

## 5. 验收标准（执行者自跑；派单方在沙箱外复跑并以自己的为准）

前提：worktree 里的 `backend/.venv` 与 `frontend/node_modules` 由派单方从主检出 `cp -cR` 进去。pytest 一律加 `-p no:cacheprovider`；本机 `NO_PROXY` 含 `[::1]` 时，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. `cd frontend && npx tsc --noEmit` 退出码 0。
2. `cd frontend && npm run lint`：0 errors，warnings ≤ 25。
3. `cd frontend && npm run build` 退出码 0。
4. `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider`：0 failed、0 skipped，passed = 8011 + 三个新文件的用例数（用 `--collect-only -q` 实数）。
5. 三个新测试文件单独跑：0 failed、0 skipped。再做一份**不含** `frontend/node_modules` 的副本只跑三个新文件：

   ```
   rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' <worktree>/ <副本>/
   cd <副本>/backend && .venv/bin/python -m pytest -q -p no:cacheprovider -rsf tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py tests/test_desk_polish_frontend.py
   ```

   rsync 时保留 `backend/.venv`。要求 0 failed；按每行 `SKIPPED [n]` 的 n 求和，核对与起 node 的用例数一致，并逐行贴出 skip 原因。
6. 改动集合：`git status --porcelain --untracked-files=all` 逐条贴出，每个路径都必须在 §4.1 白名单内（派单方放进 worktree 的 `docs/tasks/2026-11-12-novel-feedback/01-brief.md`、`02-spec.md` 除外）。`git status --porcelain --untracked-files=all -- backend/tests` 只许出现三个新文件（`??`）和 ` M backend/tests/test_studio_sources_readonly_integration.py`；`git diff -U0 HEAD -- backend/tests/test_studio_sources_readonly_integration.py` 恰两个 hunk，且该文件单独跑全绿。
7. 下列既有文件单独跑全绿：`tests/test_novel_chat.py tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py tests/test_song_agent_tools.py tests/test_song_frontend.py tests/test_claude_agent_runtime.py tests/test_claude_agent_docs.py tests/test_claude_agent_frontend.py tests/test_claude_agent_r1_frontend.py tests/test_novel_p1_api.py tests/test_novel_p1_runner.py tests/test_novel_r2_required_responses.py tests/test_novel_v2_api.py tests/test_novel_v2_compat.py tests/test_novel_p21_service.py tests/test_novel_p2_frontend.py tests/test_ui_closeout_dialog_scrim.py tests/test_design_system_gate.py tests/test_component_language.py tests/test_desk_logic_frontend.py tests/test_desk_views_frontend.py tests/test_desk_contract_frontend.py tests/test_desk_dock_races_frontend.py`。
8. 计数：`grep -c "ALTER TABLE messages ADD COLUMN novel_feedback_id" backend/database.py` = 1；`grep -c "FIONA_NOVEL_CHAT_FEEDBACK" backend/studio/sources.py backend/.env.example CLAUDE.md` 各 ≥ 1；`grep -c "draft_novel_feedback" backend/services/claude_agent.py` ≥ 2；`head -c 3 frontend/app/page.tsx | xxd -p` = `efbbbf`；`git diff HEAD --stat -- frontend/components/desk` 只列出 `DeskDialogs.tsx`、`DeskChaptersView.tsx`、`DeskEpisodesView.tsx` 三份；`git diff HEAD --stat -- frontend/lib/desk.ts frontend/components/novel frontend/lib/novels.ts frontend/components/NovelDraftCard.tsx` 为空。
9. 开关为 0 时请求不变：由 §4.5 后端第 1 条的写死期望覆盖，报告里贴出该用例的结果。

派单方另做（执行者不做）：变异测试；无 node_modules 副本复核；HEAD 对照（回归类用例——`note()` / `redo_plan()` 行为不变、开关未设 / `"0"` / `"true"` 的写死期望——在 HEAD 上必须通过；新功能类用例在 HEAD 上必须以 `AssertionError` 失败，由 `_require_feedback()` 守卫；恒真断言以坏副本自检与变异测试为准）；用作者长期在用的库的备份起一次后端验证老库升级；隔离环境真实界面走查（假传输回放 tool_use，卡片经 SSE 流式到达，再刷新确认仍在；走一遍「交出 → 批准 → 下一章细纲」核对卡片文案；1440 / 1280 / 390 三个宽度；不碰 8010 / 3000）。合入后：先备份作者试用的后端启动脚本，再加 `export FIONA_NOVEL_CHAT_FEEDBACK=1`，重启 8010，把前端改动同步到试用前端副本，用作者的书走一遍「交出 → 批准 → 下一章细纲」确认卡片文案。

## 6. 何时停下来问

- 只有「规格与源码事实矛盾」（行号或代码形状对不上、`_resolve` / `detail()` 的返回与 §2 描述不同、除 §4.5 授权的两处外还有既有测试必须改才能通过）才停下来，在报告里写清矛盾点与证据，不要自行绕开（不得用注释字面量、`importlib` / `getattr`、改名躲开 GLOB、按开关建表之类的办法让锁失效）。
- 只影响「怎么实现 / 怎么验证」的问题自行决定，并在报告里写明理由。
- 你实测到的事实优先于规格的断言，不符就停下来说明。
- 任何情况下不回滚已完成的工作。

## 7. 已知局限（写进文档，不在本批解决）

- 留言是一次性的，只在下一次为新的一章规划细纲时被读一次；「以后每一章都要……」这类长期约束没有通道。
- 重新定稿是让编辑部拿原来的讨论材料加附言重写一版，编辑部和分身都看不到被否的那一版；附言以 `author_instruction` 字段交给主编，主编的提示里没有专门说明这个字段（书斋里手动重新定稿也一样）。编辑部的「采纳」是它自己报的，不保证细纲真的照做。
- 已写章节只能作者手改：改较早的章会把后面已写的章永久标成「待复核」（目前没有办法取消），故事圣经与章节摘要不重算；按意见重写已写章节需要第二步（先给正文加历史版本与撤销）。
- 卡片状态（交没交、重没重）下一轮模型看不到。
- 卡片不轮询，书斋或案头里的变化要刷新页面才更新（v1.4 起，点「带着这些要求重新定稿」时卡片会先重新读取一次，确认框按最新状态说明费用）；作者此前在抽屉里开过这本书时，卡片操作后要回到书架重新打开才看到新细纲（旧页面上点「批准（原样）」会批准还没看过的新细纲，点「改完批准」会用旧内容覆盖新细纲）；修改意见卡不触发案头定位，案头看到的待下发留言数与细纲状态也要点「刷新」才更新。
- 卡上的文字不能改；旧卡不会作废，同一本书有多张卡时要留意别重复交。
- 重新定稿在后台进行，可能因余额、预算、每日上限或自带模型不可用而暂停，卡片会显示暂停，要到书斋恢复。
- 书名只是部分相同时，告诉分身完整书名即可；两本完全同名的书分身分不清（只能按书名找书，书斋也不能改书名）。人物设定要到书斋的人物页改。
- 思考档位低时（`max_tokens` 4096），整张卡太长可能出不了卡。
- 建卡成功但本轮消息没落库、或单条消息被删时，卡片行会保留到清空历史、删会话或删号；刷新后卡片不再显示，但已经交出的留言、已经发起的重新定稿照常有效。
- （v1.6）点「带着这些要求重新定稿」后重新读取，发现这一项已经不能用时只更新卡片：被点的按钮随之消失，键盘焦点丢失，读屏软件也不会播报新的说明。
- （v1.6）确认框打开期间如果在书斋里又改了主编模型，框里写的费用会过时，实际按改后的模型计费；后端不核对作者确认时看到的费用类型。
- 只在 Claude 智能体模式开放。

## 8. 案头三处小修（作者 2026-11-12 已批准，属于本批任务）

作者试用时发现的三处小问题，各自独立、改动很小：

- **O1 读正文多出原始标题行**：`frontend/components/desk/DeskDialogs.tsx:85` 直接渲染 `data.body`，真实正文第一行是「# 第N章 标题」。改为 `import { chapterReadingBody } from "@/components/novel/ChapterReader";`，`const body = data?.body ? chapterReadingBody(data.body) : "";`，`body` 非空时渲染 `<div className="whitespace-pre-wrap break-words text-fs-16.5 leading-[1.9]">{body}</div>`，否则沿用「这一章还没有正文。」空态。
- **O2 章回行展开后摘要仍截两行**：`frontend/components/desk/DeskChaptersView.tsx:112` 的摘要 `<p>` 只在未展开时加 `line-clamp-2`，并加 `break-words`。
- **O3 无项目提示缺句号**：`frontend/components/desk/DeskEpisodesView.tsx:105`，后端给的 `reason` 去空白后非空且不以 `。！？.!?` 结尾时补「。」；没有 `reason` 时文案仍**完整等于**「这本书还没有短片项目。」（`test_desk_views_frontend.py:787-793`）。
- 测试放新文件 `backend/tests/test_desk_polish_frontend.py`（可从 `test_desk_views_frontend` 导入 `render_view`、`make_book` 等辅助函数）：O1 正文以「# 第1章 标题」开头时渲染结果不含该行、正文其余内容都在；O2 展开前后各渲染一次，断言 `line-clamp-2` 只在未展开时出现；O3 原因无句号时补一个、已有句号时不重复、无原因时完整相等；每条配坏副本自检。起 node 的用例同样先过依赖守卫。案头既有测试文件一字不改，且仍须全绿（§5 第 7 条）。

## 9. 修订记录

**v1.1（2026-11-12）**：按五路对抗式审查修订（括号里是审查编号：L 测试锁、B 后端、F 前端、E 执行者、P 产品）。

- 互相矛盾的约束：前端源码约束原写「不含 `confirm(`」，与 `await confirm({…})` 互斥 → 改为禁原生对话框、`confirm(` 只能以 `confirm({` 出现，并补 `<b>` / `<strong>` 禁令（L1、F1、E1、F7）。
- 不存在的引用：`run_agent_turn` → `stream_claude_agent` + `run(h)`；`harness` 必须 import；开关矩阵五组参数并写死期望；`catalog` 不能用，改真实插库；`service.py` 坏副本要设 `__package__`（L2、L4、L5、L7、E3、E4、E9、E13）。
- 卡片会对作者说错话：
  - 交出后作者批准第 N 章，第 N+1 章细纲其实已经读到留言，卡片却说「第 N+2 章才看到」→ 视图从进行中章节的 meeting 里查留言是否已被读到、编辑部怎么回应；完结、失败、等完结、最后一章分别写清（L3、B1、F2、E2、P1、P12）。
  - 重新定稿一律写「扣草莓」，而作者的书主编用自带模型、或 `DEV_MODE` 下不扣 → 按主编模型三种说法（B2、P6）。
  - 「已重做」在后台还没跑完、暂停、失败、删书时都不成立 → 标签改「已发起重新定稿」，按 `redo_pending` 与书状态分别说明；不在等确认时区分暂停、处理中、正在重新定稿（B5、F4、P2）。
  - 不是逐章确认的书重新定稿后直接写正文，确认框说的「会停下来等你确认」不成立 → 后端拒绝、卡片说明（B3）。
  - 分身看不到细纲、编辑部重新定稿也看不到被否的那一版 → 工具描述与卡片文案如实说明，叫法与书斋统一为「重新定稿」（P3、F3）。
  - 手改已写章节的后果补全（改最新章要重新归档、待复核永久、圣经摘要不重算）（F5、P4）。
- 付费安全：卡片核对、改库、记下 `redo_started_at` 合进一个写事务，抽出 `_begin_redo` 与 `redo_plan` 共用（B4、E6）。
- 测试时序：重新定稿的中间态只在服务层打桩断言，HTTP 用例只断稳定事实；并发结果写死（L6、B6、E5）。
- 前端写法：单组件、hooks 规则、lint 零新增、`busyRef` 防重入、动作请求的中止与重新拉取顺序、忙碌文字、`aria-describedby`、读取失败可重试、正文不截断（F8、F9、F10、F12、F13、E7、E15）。
- 分身一次写对：格式错误一次报全并带字数；描述补「先看状态」「同一条只写一栏」「不写章号」「人物设定去人物页」（P8）。
- 卡片显示待下发留言数；用语与书斋留言页统一为「待下发」「已下发到第 N 章」；卡片摘要改成不会过时的说法（P9、P10、P11、F14）。
- 书斋抽屉不会自动刷新 → 操作后提示回书架重开，写进已知局限（P7）。
- 白名单与判据：文档搜索限六份文档；改动集合按白名单逐条核对；无 node_modules 副本的命令写死；§8 批准时的同步修改写全（L8、L9、E10、E11、E12、E14）。
- 细节：`INSERT` 的占位符、POST 路由的 `request` 参数、新路由不受新开关门控、孤儿卡片行、行号（L10、L11、B7、B8、B10、E16）。

**v1.2（2026-11-12）**：按三路只读核对修订。核对方在副本里照 v1.1 字面实现了一遍：只改授权的两处既有测试，后端全量 8011 条全过；`tsc`、`lint`（0 errors、25 warnings）、`build` 都过；单事务在并发与 `_activate` 409 回滚下都成立。修订：

- 卡片仍会说错的两处：底部提示把「批准（原样）」也说成「用旧内容」，实际它会批准作者没看过的新细纲 → 改写提示，并在 §2.6、§7、README 写明；等确认的那一章可能被主编定为最后一章（`ending_status == "end"`，第 50 章起就可能）→ 视图与建卡返回 `awaiting_is_final`，「最后一章」的判断改为「`awaiting_is_final` 或 `K >= max_chapters`」。
- 失败的书：「已被细纲读到」与「细纲仍等确认」两种状态在书 `failed` 时改说「不能再继续写」；T6.3 不在等确认的情形拆成失败、暂停、处理中、正在重新定稿四支。
- 不是逐章确认的书：`validate_feedback_args` 拒收 `current_plan`，回灌第 4 句只在逐章确认时出现。
- 前端：成功分支同时复位 `busyRef`；确认框询问期间按钮文字不变；提示句在「去书斋改细纲」出现时也显示。
- 测试：开关矩阵危机两组固定为 5 个常量工具；新测试文件在 HEAD 上可收集，新功能类用 `_require_feedback()` 守卫；SSR 渲染器约定 `__withOpenNovel`、迷你运行时加 `unmount()`；确认框的标题、正文、按钮名改在交互测试里逐字断言（三种费用）；路由方法用带方法的 AST 小函数断言；互斥只比较其他状态独有的句子；补「重新定稿后台失败」「重新定稿完成后又暂停」「最后一章」「失败的书」等判别用例；重新定稿场景各用新库或新用户。
- 文案与文档：工具描述补「不必重读原文」「整卡不超过 1500 字」「只能整条采纳」与锁定设定的理由；已写章节的回灌句与卡片补全后果；§7 与 README 补「重新定稿可能在后台暂停」、完全同名的书分身分不清、低档长卡；README 列出四个按钮。
- 事实与行号：`response_json` 存整条回应项；`_redo` 到 `:499`；建会话在 `:83-85`；坏副本锚点只用 `if novel_create_enabled(ctx.user):`；第一次重新定稿前没有 `_redo_count` 键；`FakeLLM` 在 `novel/fake_llm.py`；`detail()` 含 `config`、不含 `meeting_json`。

**v1.3（2026-11-12）**：作者确认规格。决定：§8 案头三处小修一起做（已并入 §3 第 10 条、§4.1 白名单与 §5 第 4、5、6、8 条）；书斋抽屉不自动刷新，只在卡片上提示（不改 `page.tsx` 的抽屉逻辑）；同一本书的旧卡不作废，只在说明里提醒。

**v1.4（2026-11-12）**：独立复核（`04-review.md`，Opus 5.5 xhigh）判不通过：产品代码没有必须修复项，有三项测试问题（「已被细纲读到」只测了等确认一种状态、前端没有「等确认的不是卡上这一章」、14 条前端用例在 HEAD 上以 `FileNotFoundError` 失败），另指出确认框里的费用可能已经过时。作者确认：点「带着这些要求重新定稿」时卡片先重新读取最新状态，按最新费用弹确认框，已经不能用就只更新卡片（§4.3 T6.3 第 3 支、T6.6）。同时：`redo_feedback_plan` 对没有 `plan_chapter` 的卡一律拒绝（§4.2 T3）；§7「卡片不轮询」一条补一句；R1 返修内容集中写在 §4.6。复核的可优化项里，「建卡提交后才算 `awaiting_is_final`、查询出错会留下孤儿卡片行」不做：概率极低，与 §7 已列的「消息没落库时卡片行保留」同性质。

**v1.5（2026-11-12）**：派单方对 R1 做了对抗式核查（三路只读审查，每条 must/should 再由独立反驳者复现）。产品代码没有问题：R1 前后的卡片在 23 万多种视图组合下服务端渲染逐字节相同。但测试有几处缺口，§4.7 只补测试：F7(c) 的夹具同时改了等确认章号，`redo_started_at` 这一条件没被单独证明；提前结束路径的复位只看了 `disabled`，或者根本没看；卸载时重新读取被中止而 reject 的分支、非中文报错经 `novelErrorMessage` 的转换、F1 是否真传了 `onOpenNovel`、B1 的 `stale` 反例、B6 的判断顺序，都没被锁住。另有一条可访问性观察不在规格内，留给作者裁定：重新读取后发现不可用时，被点的按钮消失、焦点丢失，读屏没有播报。

**v1.6（2026-11-12）**：独立复核第 2 轮（`07-review-r2.md`）判通过，没有必须修复项，提了 3 条可优化项。作者决定合并；可访问性与「确认框打开期间费用过时」两条先不做，只写进 §7 与 `PLAN.md` 的已知局限（R3，§4.8）；「重读后不可用的用例没断言没有错误提示」不做。
