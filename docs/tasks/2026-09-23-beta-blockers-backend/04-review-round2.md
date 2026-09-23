# 第二轮复核：内测阻断修复（后端）

复核人：第二轮独立复核总结人（未参与规格、实现与第一轮复核）。基线 `54a9b57`，复核对象为工作区 `backend/**`、`README.md`、`PLAN.md`、`CLAUDE.md`、`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`docs/CYBER_AVATAR_PLATFORM.md` 的差异及未跟踪的 `backend/admin_env.py`、`backend/manage_strawberries.py`、`backend/safety.py`、`backend/tests/test_beta_*.py`；`frontend/**` 与 `docs/tasks/2026-09-23-mobile-layout/` 属并行任务，已忽略。

第二轮规则：只核验 `04-review.md` 列出的必须修复项 R1–R4 是否真正修好、有没有因修复引入新的回归；同轮顺带项 O1/O2/O6–O10 简要核验；新发现一律列为 optional，不构成不通过理由。

两位独立核验员（A：R1+O1；B：R2/R3/R4+O2）的结论全部为「已修好、无回归」，没有任何 fixed=false 项需要我推翻。我仍在 `backend/` 下用 `.venv` 亲自重跑了关键证据（全量 pytest 两次并做前后快照、R1 正控、R2/R3 夹具探针、R4 与 HEAD 原文对照、三个管理脚本的临时库实操），临时文件只写在 scratchpad `reviewA2/`。全程未修改任何受版本控制文件（本文件除外），未读 `.env*`、未开 `*.db`、未读 `uploads/`。

## 结论：通过

R1–R4 四条必须修复项全部修好，且均有「先失败后通过」或等价的正控证据；未发现因修复引入的回归。全量 `pytest` 960 passed / 0 failed（第一轮 920 + 本轮新增 40），`uploads/` 与 `*.db` 快照跑前跑后逐字一致，`compileall` rc=0，`grep 请充值` 无命中，改动路径全部在规格白名单内。

## 通用证据（本人亲自执行）

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider`（不接管道，取真实退出码） | **rc=0，960 passed, 13 warnings in 26.12s**；日志中 `^(FAILED\|ERROR)` 计数 0 |
| 逐文件：`test_beta_billing.py` / `test_beta_safety.py` / `test_beta_admin_scripts.py` / `test_account_deletion.py` / `test_beta_test_isolation.py` | 28 / 74 / 26 / 3 / 2 passed，各 rc=0 |
| 跑前 vs 两次全量跑后 `ls uploads \| sort \| shasum` + `ls -l *.db` | 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`fiona.db` 192512 Sep 10 09:44、`local-avatar.db` 1507328 Sep 21 12:57，`diff` 为空 |
| `.venv/bin/python -m compileall -q -x '\.venv' .` | rc=0 |
| `grep -rn "请充值" --include='*.py' . \| grep -v '\.venv'` | rc=1（无命中） |
| `git status --porcelain --untracked-files=all` 过滤并行任务后与白名单比对 | 无白名单外路径；无 `backend/.env`、`*.db`、`uploads/` 改动；任务目录内仅 `02-spec/03-report/04-review/05-fix-round1` 四个未跟踪文档 |

## R1–R4 逐条核验

### R1 客户端中途断开时退款被级联取消吞掉 —— 已修好，无回归

**代码**（三处都进了 anyio 屏蔽作用域，与返修单要求一致）：
- `backend/routers/chat.py:50-52` `_refund_before_stream`：`with anyio.CancelScope(shield=True): await refund_strawberries(...)`。
- `backend/routers/chat.py:71-80` `_ReservedChatResponse.__call__`：`finally` 整体在 `anyio.CancelScope(shield=True)` 内，先 `aclose()`，再按 `tracker.started` 决定是否补退。
- `backend/services/chat_service.py:1088-1102` `run_chat` 的 `finally` 整体在 `anyio.CancelScope(shield=True)` 内（退款 + `log_event`）；`tracker.started = True` 在 `:971-972`，是生成器 `try` 块第一条语句。
- `grep -n "asyncio.shield\|CancelScope(shield"`：工作区 `routers/chat.py` 与 `chat_service.py` 已无第一轮指出的「`asyncio.shield` + 裸 await」写法用于退款（剩余的 `asyncio.shield` 在 `:457`、`:595` 是 HEAD 原有的落盘保护，且都套在屏蔽作用域内）。

**仓库测试与正控**（本人重跑）：
- `tests/test_beta_billing.py:206-272` `test_asgi_disconnect_after_first_chunk_refunds_reservation[2.3|2.4]`：直接以 `scope={"asgi": {"spec_version": ...}}` 调用真实 `_ReservedChatResponse` + 真实 `run_chat`，模型流打桩为首块后阻塞，`receive` 首块后返回 `http.disconnect`，断言余额复原为 10 且 `tracker.started is True`。当前代码 → `2 passed`，rc=0。
- 用 scratchpad `reviewA2/noshield_plugin.py`（pytest 插件，把 `anyio.CancelScope` 的 `shield=True` 剥掉以模拟未修复代码）重跑同一测试 → `[2.3]` 失败 `assert 0 == 10`（`tests/test_beta_billing.py:272`），`[2.4]` 通过。证明该测试真的覆盖 task-group 取消路径、不是恒真。
- 03-report「R1 先失败后通过」自述（1 failed 1 passed → 2 passed）与上述正控结果一致。

**核验员 A 的探针**（scratchpad `reviewA2/probe_r1.py`、`probe_uvicorn.py`）：
- 真实 `_ReservedChatResponse` + `run_chat` + aiosqlite，六个场景：spec 2.3 断线 → balance=10、trace `['svc:refund-start','svc:refund-done:10']`、0.058s；2.4 正控 → 10；生成器挂在 `yield` 走 `aclose` 路径 → 10；去掉 shield → balance=0、`refund-CANCELLED`（探针能抓到原缺陷）；断线发生在生成器启动前 → `started=False`，仅 router 退款一次、svc 零次，且验证了未启动的 async generator `aclose()` 不执行 `finally`，不存在双退；原生 `task.cancel()` → 退款仍完成。
- 端到端：真实 uvicorn 0.47 + httptools（声明 spec 2.3），经 `RequestBodyLimit`/CORS/`require_auth` 全栈，裸 socket 收到首块后 `SO_LINGER=0` RST 断开：修复版 balance=10，退款在断线后 1ms 完成，`events` 表落 chat 事件；`--noshield` 版 balance=0、`refund-CANCELLED`、无 chat 事件。

**回归**：未发现。全量 960 passed；屏蔽作用域内无阻塞导致挂起（三个断线场景 0.001–0.058s 结束）；生产调用方只有 `routers/chat.py:116-146` 一处 `reserve` / `run_chat(reserved=True)`，无漏改路径。

### R2 危机识别误报（亲昵/夸张口语） —— 已修好，无回归

**代码**：`backend/safety.py:28` `(?<![得快都])(?:我|自己|本人).{0,8}(?:想死(?![你他她它])|要死(?!了|[你他她它])|去死(?![记你他她它])|不想活(?!得)|活不下去)`；`:29` `(?:不想活|不想再活|活着没意思|活不下去)(?!得)`；`:33-34` `跳楼(?![价机])`；`:43` `suicidal|(?<![a-z])suicide(?![a-z])`。

**夹具**：`tests/test_beta_safety.py:27-35` `test_crisis_detector_rejects_required_everyday_phrases` 参数 24 条 = 规格 11 条 + 返修单 13 条（含「跳楼价甩卖」「跳楼机好刺激」），逐条与 `05-fix-round1.md` 一致。

**本人探针**（scratchpad `reviewA2/final/probe_crisis_final.py`，直接调 `detect_crisis`）：规格 11 反例 + 返修单 13 反例 = 24 条 **0 命中**；规格 11 正例 + 返修单 12 正例 + 2 条无撇号变体 = 25 条 **0 漏报**。输出：`POS total=25 miss=[]` / `NEG total=24 hit=[]` / `OK`。

**核验员 B 抽检**：另构造 20 条同族口语（想死你了宝贝 / 笑死我要死了哈哈哈 / 作业多得我想死 / 我要去死记硬背单词了 / 想死的心都有了 / 去死吧你 等），15 条正确不命中；5 条命中里 3 条属返修单已明确留给产品的 O3 家族，2 条为新发现（见「新发现」）。

**回归**：无。规格原 22 条夹具结果不变；`tests/test_beta_safety.py` 74 passed。

### R3 危机识别漏报（直白自伤表达） —— 已修好，无回归

**代码**：`backend/safety.py:31` `(?:自残|自伤|伤害(?:我)?自己|割(?:了)?(?:我)?自己|了结(?:我)?自己|杀了(?:我)?自己|把(?:我)?自己杀了)`；`:32` `(?:我|自己|本人|想|要|准备|打算).{0,6}(?:跳河|跳江|跳海)`；`:41` `(?:iwantto|iwannato|iwanna|i'?mgoingto|iplanto|igonna)(?:die|hurtmyself|cutmyself)`；`:42` `(?:i)?don'?twanttolive|(?:hurt|cut)myself`（撇号可选，兼容 `dont` / `im`）。

**夹具**：`tests/test_beta_safety.py:15-24` `test_crisis_detector_recognizes_required_phrases` 参数 23 条 = 规格 11 条 + 返修单 12 条，逐条一致；`:38-42` `test_crisis_detector_normalizes_case_and_whitespace` 已加 `i dont want to live anymore` / `im going to cut myself` 断言。

**本人探针**：返修单 12 条正例 12/12 命中；无撇号变体 2/2 命中；规格 11 条正例 11/11（同上 `POS total=25 miss=[]`）。

**HTTP 层**（核验员 B）：`我只能自残了` 这类硬词 + 自伤组合，`chat_service.py:490-492` 先 `detect_crisis` 再决定是否拼硬词附录，探针 `hardword_in_main=false`，第一轮 R3 的失败场景（硬词附录压过自伤表达、要求「反问」）已消除。抽检 32 条直白自伤表达 28 条命中，4 条漏报见「新发现」。

**回归**：无。规格 11 条反例仍 0 命中；全量 960 passed。

### R4 TTS「播报/朗读」强约束 system 消息位置回归 —— 已修好，无回归

**文本与位置逐字一致**（本人 `git show 54a9b57:backend/services/chat_service.py` 452-467 行对照工作区 503-516 行）：
- 触发正则 `(播报|朗读|口播|念出来|读出来|念一[下遍]|读一[下遍]|大声[念读])` HEAD `:455` == 工作区 `:505`。
- 强约束正文（「对方刚才请求你**直接开口说话**……跟机制无关，不用解释。」）HEAD `:459-463` == 工作区 `:509-513`；工作区仅在末尾多出 `"\n\n" + BASE_SAFETY_RULES.strip()`（`:514`），即「原文 + 底线在末尾」，正是返修单 R4.2 要求的形态。核验员 B 用 AST 抽取字符串常量比对得到同一结论（HEAD 原文 194 字 == 工作区常量前 194 字）。
- 位置：`:501` `messages.append({"role":"user",...})` 之后 `:506` 追加独立 `{"role":"system"}`，不再 `system_prompt +=`；守卫 `:505` `not crisis and re.search(...)` 保证仅非危机轮追加。

**底线唯一性机制**：`_final_system_prompt(prompt, *, crisis, trailing_system)` `:69-78` 在 `trailing_system=True` 时不给主 system 拼底线；`_has_trailing_system` `:81-82`；`run_chat :1038-1041`（普通/镜子共用）、`stream_image :676-683` 与 `:696-697`（trailing 追加到多模态 user 之后）都传入该标记；`stream_normal :890`、`stream_mirror :636` 发 `[system] + ctx.messages`；危机轮 `:978` 走 `_final_system_prompt(ctx.system_prompt, crisis=True)`，无 trailing。

**测试**：`tests/test_beta_safety.py:274-316` `test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block` 七分支（normal / mirror / hard_word / image / tts / tts_mirror / tts_image）：所有 system 拼接后底线计数恰好 1（`:306`）、最后一条 system 以底线结尾（`:307`）；tts 三分支另断言含「直接开口说话」、倒数第一条 role=system、倒数第二条 role=user（`:308-311`）；其余分支主 system 以底线结尾且唯一（`:313-314`），与返修单 R4.3 逐条一致。

**核验员 B 的 HTTP 探针**（scratchpad `reviewA2/test_probe_r4.py`，21 passed）：枚举 普通/镜子/看图/硬词 × 朗读词 × 危机 × DEV/生产：非危机 + 朗读四分支 roles 均为 `system/user/system`，trailing 去底线后 == HEAD 原文，底线计数恰好 1，主 system 不含底线；非危机无朗读四分支主 system 以底线结尾且计数 1（镜子分支含镜子附录、硬词分支含「【⚠️ 即时引导」）；危机 + 朗读四分支无 trailing、最后一条 system 以 `CRISIS_GUIDANCE` 结尾、`detect_mode` 未调用；生产路径普通 + 朗读余额 200→190、危机 200→200。

**文档**：`CLAUDE.md:76`、`docs/ARCHITECTURE.md:84` 已写明「朗读强约束仍作为当前 user 消息后的独立 system 消息」。

**回归**：未发现。工具/追问分支（`stream_intent` / `stream_pending`）不发 system prompt，与 HEAD 相同；危机轮不追加 TTS 消息是规格与返修单明确要求（非回归）。

## 同轮顺带项核验（O1/O2/O6–O10，简要）

| 项 | 结论 | 证据 |
|---|---|---|
| O1 退款失败不覆盖 SSE、记 trace、仍写 `log_event` | 成立 | `chat_service.py:1090-1095` `try/except Exception` → `trace["refund_failed"]=True`，只 `print` 类型名；`:1097-1102` 之后仍 `log_event`（自身 try/except）。`tests/test_beta_billing.py:118` `test_refund_failure_keeps_sse_error_and_records_trace` 通过。核验员 A 探针 G（2.3 断线 + 退款抛 `OperationalError('… (private detail)')`）：events 表 payload 含 `"refund_failed": true`，stdout 仅 `[chat] refund failed type=OperationalError`，私有字符串未泄露 |
| O2 `DEV_MODE=1` 危机轮不做余额拦截 | 成立 | `routers/chat.py:110` `dev_mode = os.getenv("DEV_MODE","0")=="1"`，`:111-114` 仅 `not dev_mode and balance < 10` 时直接回资源；`:115` `elif not dev_mode` 才预扣。`tests/test_beta_billing.py:354` `test_zero_balance_crisis_reaches_model_in_dev_mode` 通过；生产门槛 `tests/test_beta_safety.py:221` `test_zero_balance_crisis_returns_resources_without_model` 仍通过。核验员 B 探针 7 passed（DEV 余额 0/5/200 均调模型、余额不变；生产 0/5/9 不调模型、事件恰为资源 + done；生产 10 调模型且不扣）。`docs/ARCHITECTURE.md:84` 已同步 |
| O6 docstring 与 `--help` | 成立 | `manage_invites.py:4-8` docstring 已带 `--env-file` 与 `--init-db` 示例。本人跑 `seed_invites.py --help` / `manage_invites.py --help` / `manage_strawberries.py --help` / `manage_strawberries.py list --help`：usage 行与选项表均显示 `--env-file PATH`、`--init-db`（`admin_env.py:16-21` `admin_options_parser` 作为 `parents` 挂到主解析器与各子命令）。`tests/test_beta_admin_scripts.py:56` `test_admin_scripts_help_shows_shared_options` 通过 |
| O7 `list` 只读 | 成立 | `manage_strawberries.py:44-68`：默认 `list` 不 `init_db`，以 `?mode=ro` 的 URI 只读连接 `SELECT username, strawberry_balance, strawberry_refill_date`，旧库缺日期列显示 `-`、缺余额列退出 2。本人在临时库复现第一轮 O7 失败场景：建 `tester01/02`（余额 200、日期 NULL）→ shell 里 `STRAWBERRY_DAILY_REFILL=1000` 跑 `list` → 输出 `tester01  200  -` / `tester02  200  -`，跑后 sqlite 原始行仍 `(200, None)`，未被抬到 1000；`grant tester02 50` → `tester02  250`。四个相关测试（`:204/:244/:267/:283`）通过 |
| O8 子进程环境剥离 `STRAWBERRY_DAILY_REFILL` | 成立 | `tests/test_beta_admin_scripts.py:23` `env.pop("STRAWBERRY_DAILY_REFILL", None)`；`:64` `test_admin_script_subprocess_environment_ignores_parent_refill` 通过 |
| O9 删号同事务删 `chat_slot_state` | 成立 | `database.py:851` `DELETE FROM chat_slot_state WHERE owner_username = ?` 位于 `:769 BEGIN IMMEDIATE` … `:861 commit` 之间。`tests/test_account_deletion.py:135` `test_direct_account_deletion_clears_chat_slots_before_username_reuse`（4 槽位 → 0，他人 2 槽位保留，重建同名后 pending 为空、mode 回 friend）通过。本人临时库：`delete_account_data("tester01")` 后 `seed_invites.py 1` → `tester03` |
| O10 部署文档注明兼容 DDL 需备份 | 成立 | `docs/DEPLOYMENT.md:338`：「三个脚本进入初始化路径时会执行与服务启动相同的兼容 DDL（只加列/索引），并可能执行旧帖 owner 回填及版本化迁移……请先备份数据库再运行」，并说明 `list` 默认只读例外 |

另核规格第 5.6 条脚本验收（临时目录）：缺库不带 `--init-db` → rc=2 且目录内无 `none.db`；`--init-db` 发 2 码、stderr 含 `数据库：` 1 行；`grant nobody 1` → rc=1。

## 新发现（仅 optional，留给产品负责人）

以下均为本轮两位核验员在抽检中的新观察，不在返修单范围、不影响通过结论。词表类问题与已留给产品的 O3 同属「词表边界取舍」。

**危机词表·误报**
1. `我要死啦` / `我快要死`（无「了」）命中：`safety.py:28` `要死(?!了|[你他她它])` 只排除「了」，未排除语气词「啦/啊/呀」。建议排除集扩为 `(?!了|啦|啊|呀|[你他她它])`。
2. `让我去死吧哈哈哈哈` 命中（`:28` `去死` 仅排除 记/你/他/她/它）；「让我去死吧」是常见网络口头禅，是否算危机属产品取舍，建议至少排除紧随「哈哈/hhh/笑」的情形。
3. `跳楼大甩卖` 命中：`:33-34` `跳楼(?![价机])` 不排除「大甩卖/甩卖」。
4. 英文习语 `kill myself laughing`、`i want to die laughing` 命中（`:40-41` 无后缀排除）。

**危机词表·漏报**
5. `我把安眠药都攒好了` 不命中：`:36` 只覆盖「攒/准备/买…安眠药」语序，`:37` `安眠药.{0,8}(?:一瓶|一把|吞|吃|服)` 不含「攒/备好」。
6. `dont wanna live` 不命中：`:42` 只认 `want to`，不认 `wanna`（`:41` 的 die/hurt 分支已兼容 wanna）。
7. `i'm going to jump off the bridge` 不命中：英文词表无 jump off / jump from。
8. 无主语的「想死」（如 `生无可恋想死`）、`我想自我了断`、`我想结束这一切` 不命中：`:28` 要求「我/自己/本人」前缀；「了断」不在词表；含蓄表达超出词表能力。规格正例都带「我」，可接受但需知晓。

**提醒·非新问题**
9. O3 家族（`自杀式营销真恶心`、`今天新闻说有人自杀了`、`割腕的剧情太狗血`、`他跳楼了`）仍命中，返修单已明确留给产品负责人拍板，此处仅记录实测。

**R1 修复的边角**
10. `routers/chat.py:74-80` 的屏蔽作用域把 `aclose()` 也包进去（返修单明确要求）。副作用：`aclose()` 触发 `chat_service.py:120-124` `_iter_sync_stream` finally 里的 `await asyncio.to_thread(close)`，若供应商流的 `close()` 因网络长时间阻塞，该请求任务在此期间无法被取消（HEAD 时可被取消但线程同样残留）。本轮探针中 close 都是即时返回，未观察到挂起；如需保险可给 close 加超时。
11. 退款被原生 `task.cancel()`（非 anyio 作用域）打断时不会进入 `except Exception`，trace 不会记 `refund_failed` 且 `log_event` 被跳过。探针 F 显示原生单次取消下退款仍完整完成（原生取消不是 level-triggered），目前无实际漏退；若日后引入重复原生取消的调用方需重新评估。
12. 极端路径：`_ReservedChatResponse` 已构造但 ASGI 从未调用其 `__call__`（路由返回后、被调用前中间件抛错）时无人退款。检查了 slowapi `limiter.limit` 与 `require_auth` 中间件，返回后到调用前没有会抛错的代码，属理论缺口。

**测试覆盖建议**
13. `tests/test_beta_safety.py:274-282` 朗读分支只覆盖 tts / tts_mirror / tts_image，未覆盖「硬词 + 朗读」组合（硬词附录在主 system、底线在 trailing）。核验员 B 的探针已验证该组合正确，建议补一条参数 `("tts_hard_word", "我只能周末去，播报一下")` 固化。

## 复核方法与临时文件

- 核验员 A：scratchpad `reviewA2/probe_r1.py`（六场景）、`probe_uvicorn.py`（真实 uvicorn 端到端）、`noshield_plugin.py`（正控）。
- 核验员 B：`reviewA2/probe_crisis.py` / `probe_crisis2.py`（词表探针与抽检）、`probe_tts_ast.py`（HEAD vs 工作区 AST 比对）、`test_probe_r4.py`（21 例 HTTP 探针）、`test_probe_o2.py`（7 例）。
- 总结人：`reviewA2/final/probe_crisis_final.py`（49 条夹具复跑）、`final/full_pytest.log`、`final/snap_before.txt` / `snap_after.txt` / `snap_after2.txt`、`final/o7-*/`（临时库脚本实操）；R1 正控用 A 的 `noshield_plugin.py` 重跑。
