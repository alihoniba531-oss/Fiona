# 独立复核报告：讨论群第三期（分身聊天互通）

复核对象：基线 `eb9ec55` + 全部未提交改动（与 `.cache/review/r0.patch` 的 sha256 一致，开工时与收尾时都核对过）。规格 `docs/tasks/2026-11-15-agent-group-chat/02-spec.md` v1.1。
复核方式：通读规格、调查摘要、返修单与两份实现报告（只当线索），逐文件读实现，复跑第 8 节全部验收，另写差分探针、独立核验脚本和 100 处变异。没有使用浏览器、子代理、外网、真实模型，也没有读 `.env`、数据库文件。

临时脚本都在副本之外的 `review-wo3-tmp/` 目录里（与本副本同在 scratchpad 下）：`diff_probe.py`（基线与被审差分）、`indep_check.py`（并发、隔离、平台续读真实往返）、`mutate.py` 加 `muts_backend.py` / `muts_frontend.py` / `muts_docs.py` / `muts_gate.py`（变异），结果在同目录的 `*.json`、`*.log`。补充用例的草稿放在 `.cache/review/proposed_test_claude_off_turn.py`。

---

## 1. 结论：不通过

实现本身没有发现违反规格的行为：开关关着时与基线逐字节相同（我的差分探针 24 组全部一致），权限、事务、幂等、v1.1 两处、数据包装都核实通过，验收命令全部达标。

不通过的原因有两条，都不需要改实现代码：

1. **测试缺口（中）**：规格 6.1 第 4 条要求的「讨论群关或白名单外时，智能体一轮的请求、事件、落库与开关不存在时相同」，Claude 路径没有对应用例。我实测了两处门控回归（Claude 工具表不看白名单、出卡工具只看卡片开关），269 条新用例和全量测试都没拦住。
2. **文档缺句（低）**：规格 4.11.1 的隐私要点，`docs/ARCHITECTURE.md` 和 `docs/DEPLOYMENT.md` 各缺一两句。

---

## 2. 规格第 8 节验收逐条核验

命令都加了 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

| # | 内容 | 我跑的命令与结果 | 判定 |
|---|---|---|---|
| 1 | 前端 lint / tsc / build | `npm run lint -- --max-warnings=25`：退出 0，`0 errors, 25 warnings`，告警只在 `app/page.tsx`、`app/plaza/page.tsx` 的既有行上，新文件没有告警；`npx tsc --noEmit`：退出 0、无输出；`npm run build`：退出 0 | 通过 |
| 2 | 新用例 | `pytest -q -p no:cacheprovider -rs tests/test_discuss_chat_*.py`：`269 passed`，没有 skip | 通过 |
| 3 | 全量 | `pytest -q -p no:cacheprovider`：`8965 passed, 48 warnings in 519.35s`，退出 0；8965 = 8696 + 269 | 通过 |
| 4 | 既有测试 diff | `git diff -- backend/tests` 只改了 `test_empty_states_settings_privacy.py` 的两行：`assert fold.count("<p>") == 7` 改成 `== 8`，`assert fold.count("</p>") == 7` 改成 `== 8`。324 个已跟踪测试文件里只有这一个变了；`git diff eb9ec55 --name-only -- backend/tests` 也只列出这一个文件 | 通过 |
| 5 | 白名单 | 46 个改动或新增文件逐个对照 4.1 两张表、第 6 节新测试、两份报告与规格作者的四份任务文档。唯一不在 4.1 表里的是 `frontend/lib/discussLogic.ts`，但规格 6.9 明文要求「写成 `frontend/lib/discussLogic.ts` 里的纯函数」，属于规格内部的不一致，不算实现方越界 | 通过 |
| 6 | `CLAUDE.md` | `wc -c` 为 69219（≤ 69,300），新一节 193 字节（≤ 260），位于文件末尾，只写了两个开关名、两个入口文件和「细节见 docs/ARCHITECTURE.md」 | 通过 |
| 7 | 两个开关都不设 | `test_discuss_chat_claude.py::test_all_switches_off_return_the_constant_object` 与 `test_discuss_chat_platform.py::test_intent_system_content_matches_switches` 都在全量里通过。我自己的差分探针（见 3.1）也证实返回值是 `CLAUDE_CLIENT_TOOLS` 对象本身，意图识别的 system 内容与基线相同 | 通过 |

---

## 3. 九个重点逐条

### 3.1 开关关着时与基线逐字节相同

- **差分探针** `diff_probe.py`：同一份脚本分别在基线副本（`git archive eb9ec55` 解出，`.venv` 用 `cp -cR` 克隆）与被审副本里运行。覆盖 6 种「讨论群应为关」的组合：都不设；只开 FIONA_DISCUSS；CHAT=0 而 CARDS=1；白名单外（还用了一个前缀相近的名字 `authorx`）；FIONA_DISCUSS=0；CHAT=`true`。再乘以 4 种小说/写歌组合：无；小说；写歌；小说 + 写歌 + 建书 + 修改意见 + 工作室。每组记录以下内容：
  - `client_tools_for_turn` 在非危机与 `possible` 时是否为常量对象本身，以及工具表 JSON；
  - `recognize_intent` 发给模型的完整请求（3 种 username/crisis 组合，假客户端返回讨论群意图）与归一后的结果；
  - `normalize_intent_result` 对 6 种原始结果的输出；
  - `_recognize_turn_intent` 的调用形状。

  结果：24 组 × 11 个字段里，只有一个字段不同，就是下面这条观察；其余全部相同，包括工具表的对象身份与 JSON、意图请求、归一结果。
- **唯一差异（不违反规格）**：小说开着时，`recognize_intent_with_fallback` 调 `recognize_intent` 多传了一个默认值参数 `crisis=False`（基线是 `{username}`，现在是 `{username, crisis: False}`）。发给模型的请求逐字节相同；规格 4.5.2 只要求「两者都关时调用形状与今天完全相同」，两者都关时形状确实相同。
- 代码层面：`claude_agent.py:145-183` 四个开关都关时 `return CLAUDE_CLIENT_TOOLS`（156 行）。小说开着时先 `tools = CLAUDE_CLIENT_TOOLS + [...]` 生成新列表再追加，没有改动常量。`chat_service.py:1931` 快捷续读先判 `_discuss_chat_enabled` 再读库（短路求值）；`stream_intent` 里的讨论群分支只有讨论群意图才走得到，而开关关着时 `normalize_intent_result` 不会放行讨论群意图。
- 平台整轮由 `test_platform_discuss_off_request_events_history_refund_unchanged` 覆盖。**Claude 整轮没有用例覆盖**，见必须修复项 1。

### 3.2 权限与归属

- 只读服务全部经 `discuss_store.list_groups(username)` / `service.detail(username, …)` / `service.output(username, …)`，按账号过滤。`indep_check.py` 证实：bob 用 alice 的群 id 找群、读进展都失败，返回「你还没有讨论群。」。
- 三条卡片接口都是 `Depends(discuss_user)`（`routers/discuss.py`）。读卡、送卡都用 `_fetch_task` / `_fetch_note` 按 `owner_username` 过滤。独立核验里 bob 调 `task_card_view`、`note_card_view`、`send_note_card` 都得到 404。变异 R1、R2、K2、K3 都被 `failed` 拦住。
- `save_message` 的两段附加校验在 `database.py:657` 起，位于「# 写歌归属只做附加校验」（683 行）之前，不在既有标记之间。查询条件是 id、owner、conversation 三项都要对上，出任何异常都存 NULL。变异 D1、D2（不核对会话）被拦，门禁的 D4、D5（不核对归属）也有用例。
- 模型不能建群、插话、扣费：`draft_discuss_task` 只调 `cards.create_task_card`，`draft_discuss_note` 只调 `cards.create_note_card`。建群只在 `service.create_group` 收到 `task_id` 时发生，送进群只在 `POST /note-cards/{id}/send`。Claude 只读工具与平台意图都只走 `chat.py` 的只读函数。`execute_intent` 自己也会再查一次 `chat_enabled`（`chat_service.py:624-626`，变异 G4 被拦）。
- 缺口：`client_tools_for_turn` 的白名单与主开关判断没有用例钉住（变异 G1、G2 存活），见必须修复项 1。

### 3.3 事务与幂等

- 建群消费任务卡：`service.py:507-511` 在 `run_write` 的同一个 `BEGIN IMMEDIATE` 事务里，先插入群，再 `consume_task_card`（条件 `owner_username=? AND group_id IS NULL`），失败时抛 422，`run_write` 回滚。独立核验结果：
  - 用别人的卡建群得到 422「任务卡不存在或已使用」，alice 名下一个群也没有，bob 的卡仍未使用；
  - 三个并发请求用同一张卡建群，只成功一个（另两个是 409「已有群在跑」），卡上记的正是新群 id。
- 送出意见卡：`cards.py:277-337` 把「插入插话」与「`UPDATE … WHERE message_id IS NULL`」放在同一个写事务里，已送出的卡直接返回视图。独立核验：三个 `asyncio.gather` 并发送出只插入 1 条，三份视图的 `message` 相同，插话的 `round` 等于群当前轮次（2）；满 5 条未读时 409、文案与 `add_note` 一致，卡片的 `message_id` 仍为空。
- `post_user_note` 拆出 `post_user_note_in_txn`，原函数行为不变（全量里既有插话用例都通过）。

### 3.4 v1.1 两处

- 找群（`chat.py:132-167`）：先去空白；被一对书名号包着时去掉再去空白；为空时按空查询规则；然后依次 id 精确、显示名 `casefold` 后精确相等（多于 1 个时只列同名的群）、包含。变异 C1、C13 被拦。
- `read_output` 成功时带 `group_id`；平台文本的续读提示是「还有后文，说『继续读』接着念。」，`model_text` 的提示仍是「…请从 N 开始。」（`chat.py:363-372`）。
- 续读位置：`intent_router.py:226-299` 存在 `chat_slot_state`，`kind='discuss_read'`，30 分钟（主键是 `(state_key, kind)`，与小说位置、pending 并存）。`_stream_discuss_intent`（`chat_service.py:1555`）只在 `discuss_read`、`part=output`、成功时存或删位置。Claude 路径的 `execute_intent` 不存位置。
- 快捷续读（`chat_service.py:1931-1946`）放在小说那段之前。我把基线与被审的小说那段逐字符比较（从 `if (_novel_chat_enabled…` 到 `if _claude_agent_enabled`）：**完全相同**；`_stream_novel_intent` 也完全相同。
- 平台真实往返（`indep_check.py` 的 `platform_roundtrip`）：用真实的 `run_chat`、真实的 `execute_intent` 和 `chat.read_output`、临时库里 22,690 字的成果，依次发「把泰国短剧的成果念给我听」→「继续读」→「接着读」→「接着念。」。结果：四段拼起来等于原文；只做了一次意图识别；平台提示里没有数字；读完后位置被删除；四轮都退回了预扣；落库正文就是回复文字。
- 提示词：删掉了 `offset=6000` 的示例，`offset` 的说明补了「一般省略，『继续读』由系统接着上次的位置读」，示例有 5 个。

### 3.5 数据当数据

- `chat.py:177-183` 的 JSON 版与标签版都和 4.3.7 逐字一致，`DATA_NOTICE` 与规格原文逐字一致。用例里有正文含引号、换行、`</discuss_data>` 时 JSON 仍合法、能还原原文的断言（我的变异 C10 被拦）。
- Claude 路径（`claude_agent.py:819-835`）把 `model_text` 回灌，不往 `state.full_response` 里写，也不发 SSE 文字。变异 CA1（改成回灌标签版）、CA10（往正文里写东西）都被多条用例以 `failed` 拦住。

### 3.6 既有测试一字不改

见第 2 节第 4 条，只有授权的两处数字。

### 3.7 新用例的证明力（我自己的 100 处变异）

做法：每处改坏后跑 `tests/test_discuss_chat_*.py`，按 `failed` / `error` 分类，随即用读到的原文写回并核对 sha256。收尾时 46 个文件的哈希与 `git diff` 的哈希都和开工时一致。

| 组 | 数量 | 被 failed 拦住 | 只靠 error 拦住 | 存活 |
|---|---|---|---|---|
| 后端（chat / cards / service / store / database / agent_store / intent_router / chat_service / claude_agent / router） | 62 | 56 | 0 | 6 |
| 前端（两个卡片组件、page、useConversations、新建页、discussLogic、ChatBubble、discuss.ts） | 27 | 27 | 0 | 0 |
| 文档 | 7 | 4 | 0 | 3 |
| 门控补充 | 4 | 2 | 0 | 2 |
| 合计 | 100 | 89 | 0 | 11 |

存活项逐一分析：

- **G1**：`client_tools_for_turn` 的 `discuss_read` 改成只看 `FIONA_DISCUSS_CHAT=="1"`，不看主开关和白名单。**真缺口**，白名单外的账号会拿到讨论群工具，违反第 3 节第 1 条。
- **G2**：`discuss_cards` 改成只看 `FIONA_DISCUSS_CHAT_CARDS=="1"`。**真缺口**，CHAT=0 而 CARDS=1 时会下发出卡工具，违反 4.2.3 与第 3 节第 1 条。
  - 我确认过，整个测试目录里只有新用例引用这两个变量，所以全量测试同样拦不住 G1、G2。
- **S1**：`if body.task_id is not None` 改成 `if body.task_id:`。实现正确，只是没有用例覆盖空串 `task_id`，记为可优化。
- **I3**：`normalize_intent_result` 不再把 `crisis` 传给 `chat_enabled`。从 `run_chat` 走不到这种情况（危机轮不会把 username 交给意图识别），属于纵深防御，记为可优化。
- **I4**：`>` 改成 `>=`，只在两个位置的微秒时间戳完全相同时才有区别，实际上等价。
- **CS4**：去掉 `not novel_position`，与原条件等价，因为 `discuss_read_position_is_newer` 在没有小说位置时本来就返回真。
- **K9**：送卡时去掉对 `failed` 的显式判断，与原代码等价，因为 `post_user_note_in_txn` 会再查一次，抛出的 409 文案相同。
- **C14**：「没找到」时列出群的个数，规格没有规定，不算缺口。
- **X1 / X2 / X6**：文档里的隐私句与清理说明没有用例钉住。规格 6.11 只要求查标题、本机路径、`.env.example` 和 `CLAUDE.md` 的大小，记为可优化。

其余 89 处全部以 `failed` 拦住，没有一处只靠 `error`。各条命中的用例名见 `mut-*.json`。抽查断言写法：工具定义与规格原文抄录比较，没有拿实现跟自己比；`page.tsx` 先断言恰好两个 `const card` 块再查字段；`openDiscussAt` 在 Node 里执行真实源码，并带坏副本自检；没有发现恒真的断言或扫描到空集的断言。

### 3.8 界面

- 两个卡片组件和前端改动的新增行里，扫描 `font-medium|font-semibold|font-bold|fontWeight|<b |<strong|font-weight|confirm(|alert(|dangerouslySetInnerHTML` 都没有命中。颜色令牌 `--ink2`、`--carve`、`--seal` 都是 `globals.css` 里已有的，`--seal` 在 `NovelFeedbackCard` 里也用过。
- 文案与 4.10 第 5、6 条逐条对照一致，涵盖读取中、不存在、读不到、重新读取、讨论群任务、前 80 字加「……」、建议行三种写法、去讨论群建群、扣草莓提示、已建群、打开、给《…》的意见、已删除、已结束、满 5 条、送进群、返工提示、已送进群加读没读到、打开讨论群。意见卡没有确认框，用 ref 加状态防重复点击，失败时显示后端文案并重读一次卡。新建页预填、403/404 提示、「已建成」与「已用过」两种提示都与 4.10.7 一致，变异 F17–F22 都被拦。

### 3.9 文档与隐私、大小

- 六份文档都有「讨论群聊天互通（第三期）」；README、ARCHITECTURE、PLAN 的 v1.1 补句都在；DEPLOYMENT 三个变量各一条；`.env.example` 三行上方各有中文注释。
- 扫描 46 个改动或新增文件，查 `/Users/`、`/private/tmp`、`/home/x/`、账号名、`sk-…`、`AKIA…`、`PRIVATE KEY`：只命中测试里定义正则的那一行。正控 `printf '/Users/x' | grep -c` 得到 1，证明扫描确实生效。
- **缺句**：4.11.1 第一条隐私要点里的「群里的发言可能包含分身根据私有记忆补充的主人背景。」只在 README 里有，`docs/ARCHITECTURE.md:584`、`docs/DEPLOYMENT.md:976` 的隐私段都没有；DEPLOYMENT 那段还缺第三条里的「文字由作者自带的 Claude 起草」。见必须修复项 2。

---

## 4. 必须修复项

### 必须修复 1（中）：规格 6.1 第 4 条的 Claude 路径用例缺失，门控回归测不出来

- **现象**：没有任何新用例在「讨论群应为关」的组合下（白名单外、CHAT=0 而 CARDS=1、FIONA_DISCUSS=0）跑一整轮 Claude 智能体，并和「开关不存在」比较请求（messages 与 tools 的 JSON）、事件、落库。`test_all_switches_off_return_the_constant_object` 只测了全部不设的情况。
- **复现**：对 `backend/services/claude_agent.py` 做下面任一处改动后，`tests/test_discuss_chat_*.py` 仍然 269 条全部通过，全量也通过（整个测试目录只有新用例引用这两个变量）：
  - 第 152 行 `discuss_read = discuss_config.chat_enabled(ctx.user, crisis)` 改成 `discuss_read = os.getenv("FIONA_DISCUSS_CHAT") == "1" and not crisis`。后果：白名单外的账号拿到 `list_discuss_groups` / `read_discuss_group`。
  - 第 153 行 `discuss_cards = discuss_config.chat_cards_enabled(ctx.user) and not crisis` 改成 `discuss_cards = os.getenv("FIONA_DISCUSS_CHAT_CARDS") == "1" and not crisis`。后果：CHAT=0 而 CARDS=1 时下发出卡工具，白名单外的账号也能建任务卡。
- **为什么违反规格**：第 6 节第 1 组第 4 条明文要求这条用例；第 6 节末尾要求每条用例都能区分对错。这两处正是第 3 节第 1 条（关着时逐字节相同）与 4.2.3（`chat_cards_enabled` 必须以 `chat_enabled` 为前提）的守门点，属于本次风险排序第一、二位。实现本身目前是对的（我的差分探针证实了），缺的是用例。
- **可直接采用的用例草稿**：`.cache/review/proposed_test_claude_off_turn.py`。它参数化三种组合，第一轮模型乱调一个没下发的 `draft_discuss_task`，第二轮正常作答；屏蔽 `deadline_seconds` 与 `control` 对象之后，逐字节比较请求、事件、落库。我在被审实现上跑了一遍：`3 passed`。用 G1 改坏：`2 failed, 1 passed`（CHAT=0 那组本来就该通过）；用 G2 改坏：`3 failed`，都是断言失败。

### 必须修复 2（低）：ARCHITECTURE 与 DEPLOYMENT 的隐私段缺 4.11.1 的句子

- **现象**：`docs/ARCHITECTURE.md:584` 和 `docs/DEPLOYMENT.md:976` 的隐私段都缺「群里的发言可能包含分身根据私有记忆补充的主人背景。」；`docs/DEPLOYMENT.md:976` 还缺「任务卡与意见卡的文字由作者自带的 Claude 起草」。
- **复现**：`grep -n "私有记忆补充的主人背景" README.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md` 只命中 `README.md:440`。
- **为什么违反规格**：4.11.1 要求三条隐私要点写进 README、ARCHITECTURE、CLAUDE、DEPLOYMENT 的相应位置。CLAUDE 受 4.11.3 的 260 字节限制可以不写，另外两份应写全。这句话说明了一项具体的隐私风险：分身的私有记忆会经由群发言流向聊天模型的厂商。

---

## 5. 可优化项（不违反规格）

1. **超过 200 条消息时的发言人名**：`chat._recent_messages` 翻页取到的后续消息是 `discuss_store.list_messages` 的原始行，没有 `sender_name`，「最近发言」会显示内部角色 id（如 `host`）而不是成员名。只影响超过 200 条消息的群。
2. **还没验收的成果**：`_verdict_line` 把还没验收的成果（`verdict` 为空，比如验收步还没跑或跑失败了）写成「最新成果验收：没通过。」，容易误导。规格只说「通过或没通过」，可以考虑区分出「还没验收」。
3. **找群范围**：`resolve_group` 只在 `list_groups` 默认返回的最近 50 个群里找，更早的群按 id 或名字都找不到。
4. **续读的群已被删除**：之后 30 分钟内每次说「继续读」都会得到「没找到「<32 位 id>」…」，把内部 id 暴露给作者。规格要求失败时不动位置，所以不算违规；可以考虑在「群已不存在」时顺手删掉位置，或换一句话说明。
5. **空成果**：成果正文为空串时，`offset=0` 会得到「续读位置不对。」，可以改成「还没有成果」。
6. **用例补强**：
   - 空串 `task_id` 建群应得 422（变异 S1 存活）；
   - `normalize_intent_result(…, crisis=True)` 不放行讨论群意图（变异 I3 存活）；
   - 文档隐私句与清理说明的原文断言（X1、X2、X6 存活），可以和必须修复项 2 一起补。
7. **两处冗余**：`cards.TASK_OPEN_LIMIT = 50` 定义了但没用到，`claude_agent.py` 里写的是字面量 50；`send_note_card` 在 `post_user_note_in_txn` 返回非 dict 时用 `MAX(id)` 兜底，这段是走不到的代码，可以删掉。
8. **新建页的补充材料**：新建页每次加载都会 `setMaterialsOpen(Boolean(materials))`，不带任务卡重新加载时会把已展开的补充材料收起来。与基线有细微差别，影响很小。
9. **规格自身**：4.1 的文件表没列 `frontend/lib/discussLogic.ts`，但 6.9 要求改它，建议规格作者在表里补上。
10. **意图识别调用形状**：小说开着时，意图识别的内部调用多了一个 `crisis=False` 参数。发给模型的请求不变，只记录在这里。

---

## 6. 给实现方的二次修改指令

只改下面这些地方，其余文件（含全部实现代码、前端、`CLAUDE.md`、既有测试）与当前状态逐字节相同。

1. **补用例（必须修复 1）**：新建 `backend/tests/test_discuss_chat_off_turn.py`，或并入 `test_discuss_chat_claude.py`，内容以 `.cache/review/proposed_test_claude_off_turn.py` 为底稿，要求如下：
   - 至少覆盖三种组合：`FIONA_DISCUSS=1`、命中白名单、`CHAT=0`、`CARDS=1`；`CHAT=1`、`CARDS=1` 但白名单外；`FIONA_DISCUSS=0` 且 `CHAT=1`、`CARDS=1`。每种都和「四个讨论群变量都不存在」比较一整轮 Claude 智能体的请求（messages 与去掉 `deadline_seconds`、`control` 后的参数 JSON）、SSE 事件、落库。
   - 模型调用一个没下发的讨论群工具时，以上三项也相同。
   - 另加一条直接断言：上述三种组合下 `client_tools_for_turn(...) is CLAUDE_CLIENT_TOOLS`（小说、写歌都关时）。
   - 自检：把 `claude_agent.py` 第 152、153 行分别改成本报告 4-1 里的两种写法，确认新用例 `failed`，然后用原文还原。
2. **补文档（必须修复 2）**：
   - 在 `docs/ARCHITECTURE.md` 第三期一节的隐私段补「群里的发言可能包含分身根据私有记忆补充的主人背景。」；
   - 在 `docs/DEPLOYMENT.md` 第三期一节的隐私段补这句，以及「任务卡与意见卡的文字由作者自带的 Claude 起草」；
   - 在 `test_discuss_chat_docs.py` 里为这两份文档加上这几句原文的断言，先断言找到了第三期那一节，再断言内容。
3. **可选**：顺手补第 5 节第 6 条的两条单元用例（空串 `task_id` 得 422；`crisis=True` 时 normalize 不放行讨论群意图）。不要求改实现。
4. **验收**：
   - `tests/test_discuss_chat_*.py` 全部通过、0 跳过；
   - 全量 0 失败、0 跳过，通过数 = 8696 + 新用例总数；
   - `git diff -- backend/tests` 中既有测试仍只有那两处数字；
   - `git status` 里新增的改动只在本节列出的文件里。

---

## 7. 复核方自己的还原声明

变异期间被审文件每次都是先读出原始字节、改坏、跑测、立即写回，再核对 sha256；没有用 `git stash`、`checkout` 或 `reset`。收尾核对结果：

- 46 个改动或新增文件的 sha256 与开工时的清单完全一致；
- `git diff` 整体的 sha256 与开工时相同，也与 `r0.patch` 相同；
- 工作树里新增的只有 `.cache/review/04-review.md` 与 `.cache/review/proposed_test_claude_off_turn.py`；
- `frontend/.next` 是构建产物，已被 git 忽略。
