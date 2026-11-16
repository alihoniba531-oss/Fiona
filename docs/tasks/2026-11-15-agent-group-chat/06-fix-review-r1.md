# 复核返修第 1 轮

独立复核（同目录 `04-review.md`）结论「不通过」：实现没有违反规格，两条必须修复都在用例与文档上。规格作者另据复核的可优化项补了 v1.2 的几处细节。先读规格 `02-spec.md` 末尾新增的「v1.2 修订」一节，再读 `04-review.md` 第 4、5 节，然后动手。

这是复核返修第 1 轮（上限 3 轮）。

## 一、复核与规格作者核实过的事实

- 实现与规格 v1.1 一致：全量 8965 条通过、0 失败、0 跳过；开关关着时与基线的差分对照逐字段相同；267 处变异全部被断言杀死。
- 必须修复 1 已由规格作者独立复现：把 `backend/services/claude_agent.py` 里 `client_tools_for_turn` 的两行门控分别改成
  - `discuss_read = os.getenv('FIONA_DISCUSS') == '1' and os.getenv('FIONA_DISCUSS_CHAT') == '1' and not crisis`（工具表不看白名单），
  - `discuss_cards = os.getenv('FIONA_DISCUSS_CHAT_CARDS') == '1' and not crisis`（出卡工具只看卡片开关），
  
  `tests/test_discuss_chat_*.py` 269 条都照样通过。
- 必须修复 2 已核实：`docs/ARCHITECTURE.md` 第三期隐私段没有「群里的发言可能包含分身根据私有记忆补充的主人背景。」；`docs/DEPLOYMENT.md` 第三期隐私段这句和「任务卡与意见卡的文字由作者自带的 Claude 起草」都没有。
- v1.2 里四处读取上的问题已由规格作者在隔离环境里看到：230 条消息的群「最近发言」显示 `custom1 · 调研笔记`、`writer · 成稿`、`policy · 调研笔记`，同一个群消息不到 200 条时显示的是「十年投资人」「撰稿人」「政策与合规」。

## 二、要做的事

1. **实现**（只改 `backend/discuss/chat.py` 与 `backend/services/chat_service.py`）：
   - 规格 v1.2「4.3 第 4 条再修订」：32 位 id 找不到时的说明。
   - 规格 v1.2「4.3 第 5 条修订」：翻页后的发言人名与 `detail` 一致；还没验收的成果。可以改用 `service.detail(username, group_id, after=…)` 翻页，也可以复用 `service` 里给 `sender_name` 取名的那段逻辑，但不要复制一份会和它走样的取名规则。
   - 规格 v1.2「4.3 第 6 条修订」：空成果。
   - 规格 v1.2「4.5 第 4 条修订」：平台读成果失败时也删位置。
2. **文档**：规格 v1.2「4.11 修订」第 1–4 条（`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`）。
3. **用例**：规格 v1.2「6 测试要求（再追加）」第 15–17 条。第 15 条的写法提示：在 `test_claude_agent_runtime.py` 的 `harness` 夹具上，先清掉四个讨论群变量跑一轮作为对照，再按组合设变量跑一轮；每轮的第一次模型返回是调用 `draft_discuss_task`（没下发的工具），第二次正常回答；把 `h.requests` 里每次请求的 `messages` 与去掉 `deadline_seconds`、`control` 之后的参数用 `json.dumps(..., ensure_ascii=False, sort_keys=True, default=str)` 序列化后，连同事件列表与 `h.saves` 一起与对照逐项比较。首轮已有用例里与 v1.2 冲突的断言（例如还没验收时的文字）按 v1.2 更新。

## 三、规矩

1. 允许改动或新增的文件只有：`backend/discuss/chat.py`、`backend/services/chat_service.py`、`backend/tests/test_discuss_chat_*.py`（改本期新建的，或新增）、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`，加上报告 `docs/tasks/2026-11-15-agent-group-chat/impl/report-fix-review-r1.md`。其余文件（含前端全部、`claude_agent.py`、`cards.py`、`intent_router.py`、`database.py`、`README.md`、`CLAUDE.md`、`.env.example`、规格、调查、复核报告）与本单派出时逐字节相同。如果你认为必须改别的文件，停下来说明。
2. 既有测试（基线 `eb9ec55` 里就有的测试文件）一字不改；`chat_service.py` 里小说「继续读」那一段一个字符都不改。
3. 不 commit、不 stash、不 checkout、不 reset；不装依赖；不读 `.env`、`.env.local`、数据库文件；不访问外网；不调用真实模型。临时脚本放仓库外的临时目录，用完删掉；自检改坏的文件用你读到的原文写回。
4. 并行：用工作流（workflow 工具）并行，按文件不重叠拆分（例如「`chat.py` 与它的用例」「`chat_service.py` 续读删位置与它的用例」「Claude 整轮对照用例（新测试文件）」「三份文档与文档用例」）；每个 agent 的任务说明自包含，写明规格路径与条款、可改文件、必须先读的既有用例，并写明不得调用 subagent / subagent_fork / workflow。
5. 你实测到的事实优先于本单的断言，不符就停下来说明。任何情况下不回滚已完成的工作。

## 四、自检

逐一改坏、跑 `tests/test_discuss_chat_*.py`、还原，写明哪条用例 `failed`：

1. 第一节里复核方的两处门控改坏（各自单独改）。
2. v1.2 每一处实现至少一处改坏：翻页后又用内部代号；还没验收写成「没通过」；空成果又落到「续读位置不对。」；32 位 id 又原样写进说明；读成果失败时不删位置。
3. 三份文档各删一句隐私原文。
4. 首轮与返修第 1 轮已经能发现的改坏继续能发现（不放松已有断言）。

## 五、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `frontend/`：`npm run lint -- --max-warnings=25`、`npx tsc --noEmit`、`npm run build` 退出码都是 0（本轮不改前端，用来确认没碰坏）。
2. 在 `backend/`：`tests/test_discuss_chat_*.py` 全部通过、0 跳过。
3. 在 `backend/`：全量 0 失败、0 跳过，通过数 = 8696 + 本期新用例总数。
4. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只在第三节第 1 条的清单里。
5. `git diff -- backend/tests`：既有测试仍只有 `test_empty_states_settings_privacy.py` 那两处数字。

报告不写本机绝对路径：改了什么、新用例各钉住什么、自检表、验收五条的命令与输出摘要、未完成或需人工确认的地方。最后一条回复给出变更总结五项。
