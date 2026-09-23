# 复核报告：内测阻断修复（后端）

复核人：独立复核总结人（未参与规格与实现）。基线 `54a9b57`，复核对象为工作区 `backend/**`、`README.md`、`PLAN.md`、`CLAUDE.md`、`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`docs/CYBER_AVATAR_PLATFORM.md` 的差异及四个未跟踪新文件；`frontend/**` 与 `docs/tasks/2026-09-23-mobile-layout/` 属并行任务，已忽略。

三个独立视角（T1/T2 计费并发、T4 安全与回归、T3/T5/T6 脚本与隔离）的每条 must_fix 我都亲自复现过：探针、pytest、脚本命令均在 `backend/` 下用 `.venv` 重跑，临时文件只写在 scratchpad。全程未修改任何受版本控制文件（本文件除外），未读 `.env*`、未开 `*.db`、未读 `uploads/`。

## 结论：不通过

4 条必须修复项（R1 计费漏退、R2 危机误报、R3 危机漏报、R4 TTS 提示词位置回归）。其余工作质量扎实：原子预扣/退款、补给、管理脚本连库与不撞号、测试隔离、文档同步全部实测成立。

## 验收标准逐条核验（规格第 5 节）

| # | 标准 | 结果 | 证据（本人亲自执行） |
|---|---|---|---|
| 1 | 全量 pytest 0 failed，通过数 ≥ 829 + 新增 | pass | `.venv/bin/python -m pytest -q -p no:cacheprovider` → **920 passed, 0 failed**（26s）。新增 4 个测试文件 91 用例，829 + 91 = 920 |
| 2 | 全量 + 逐文件运行都不碰 `uploads/` 与 `*.db` | pass | 我的全量跑后：`ls uploads \| sort \| shasum` = `ccf9c152…7eac`，476 个文件，`find uploads -mmin -40` 为 0，`fiona.db`(Sep 10) / `local-avatar.db`(Sep 21) mtime 未变。视角三的三次快照（跑前/全量后/逐文件 42/42 后）逐字一致，同一 shasum |
| 3 | `compileall` 退出 0 | pass | `compileall rc=0` |
| 4 | `grep "请充值"` 无命中 | pass | grep rc=1 |
| 5 | 并发预扣/被拒/复原/提前关流/补给测试存在且通过 | **fail（部分）** | `tests/test_beta_billing.py` 所列用例全部存在并通过；但「提前关闭流」只覆盖 `aclose()`（:154-167），生产 uvicorn 的 `http.disconnect` 取消路径实测**漏退**（见 R1），T1.5「客户端中途断开必须退还」未达成 |
| 6 | 脚本：缺库退出 2 不建文件 / `--init-db` 发 2 码 / 删 tester01 后发 `tester03` / grant 50 / grant nobody 退出 1 | pass | 在 scratchpad 临时目录重跑：rc=2 且目录内仅有 `env`；`--init-db` 发出 `tester01/02`，stderr 含 `数据库：<绝对路径>`；`delete_account_data("tester01")` 后 `seed_invites.py 1` → `tester03`；`grant tester02 50` → `tester02  250`；`grant nobody 1` → rc=1 |
| 7 | T4.5 所列测试全部存在且通过 | pass | `tests/test_beta_safety.py` 60 用例通过（夹具 22 条、危机轮 system 以 `CRISIS_GUIDANCE` 结尾、模型抛错仍发资源文案、镜子模式不用附录、余额 0 不调模型、五个非危机分支底线唯一且最后、交流 9 条 system 路径含底线）。注意：测试通过 ≠ 词表合格，见 R2/R3 |
| 8 | `git status` 每个路径在白名单内 | pass | 排除并行任务后，改动路径仅为 `backend/**`（含 `.env.example`）、6 个白名单文档、`docs/tasks/2026-09-23-beta-blockers-backend/{02-spec,03-report}.md`；`02-spec.md` 是规格本身，非实现方写入 |

## 必须修复项

### R1 生产路径客户端中途断开时退款被级联取消吞掉，用户为未交付的回复付费

- **问题**：`run_chat` 的 `finally` 用 `asyncio.shield(refund_task)` + 裸 `await refund_task` 兜底（`backend/services/chat_service.py:1072-1078`）。生产 uvicorn 0.47 对 HTTP 请求声明 ASGI `spec_version="2.3"`（`.venv/.../uvicorn/protocols/http/h11_impl.py:206`、`httptools_impl.py:227`），Starlette 1.3.1 对 `< 2.4` 走 task group，收到 `http.disconnect` 后 `task_group.cancel_scope.cancel()`（`.venv/.../starlette/responses.py:265-281`）。anyio 4.14 的取消是 level-triggered：`CancelScope._deliver_cancellation`（`_backends/_asyncio.py:581-626`）每个事件循环周期对仍在等待的任务重复 `task.cancel()`。第一次取消打断 `asyncio.shield`，代码回退到裸 `await refund_task`，第二次取消落在这条 await 上，asyncio 顺带取消被等待的 `refund_task` → `refund_strawberries` 协程在 `UPDATE` 前后被 `CancelledError` 打断，连接关闭即回滚。
- **证据（亲自复现）**：用真实 `_ReservedChatResponse` + 真实 `run_chat` + 真实 aiosqlite 退款、模型流打桩为发出一块后阻塞、`receive` 在首块后返回 `http.disconnect`：
  - `spec_version=2.3`（生产）→ `balance=0`，退款 trace `['refund-start', 'refund-CANCELLED']`
  - `spec_version=2.4`（正控）→ `balance=10`，`['refund-start', 'refund-done:10']`
  - 三种 finally 写法在 anyio task-group 取消下对比：当前写法 → `['await-task-cancelled']`；`with anyio.CancelScope(shield=True): await …` → `['refund-done']`；`create_task` 后在 anyio 屏蔽作用域内 `await task` → `['refund-done']`
  - 现有 `test_early_stream_aclose_refunds_reservation`（`tests/test_beta_billing.py:154`）只覆盖 `aclose()`/`GeneratorExit`，不经过 task-group 取消，故全绿仍漏此路径。
- **失败场景**：`DEV_MODE=0`，余额 10，发普通消息 → 预扣至 0 → 模型流式中用户关页/断网 → uvicorn 发 `http.disconnect` → 流任务被取消 → 退款协程被打断 → 余额停在 0；`_ReservedChatResponse.__call__`（`routers/chat.py:86`）因 `tracker.started=True` 也不再补退。用户没收到回复却被扣 10 颗，且没有任何日志。
- **修复要求**：`chat_service.py:1072-1078` 改用文件内已有的 `with anyio.CancelScope(shield=True):`（`:447`、`:581`、`:597` 已在用，`import anyio` 在 `:21`）包住退款 await；`routers/chat.py:50-56 _refund_before_stream` 与 `:77-86 _ReservedChatResponse.__call__` 的同款 `asyncio.shield` + 裸 await 一并改为 anyio 屏蔽作用域（服务停机取消时同样会丢）。补一条测试：scope 带 `{"asgi": {"spec_version": "2.3"}}` 直接调用 `_ReservedChatResponse`，模型流打桩为一块后阻塞、`receive` 首块后返回 `http.disconnect`，断言余额复原；先确认该测试在修复前失败。

### R2 危机识别对陪聊高频亲昵/夸张表达误报，普通轮次被改写为危机脚本且免费

- **问题**：`backend/safety.py:28` `(?:我|自己|本人).{0,8}(?:想死|要死|去死|不想活|活不下去)` 与 `:39` `suicidal|suicide` 无任何排除。
- **证据（亲自执行 `detect_crisis`）**，全部返回 `True`：「我想死你了」「宝贝我想死你了」「我要死了，笑死」「累得我要死」「笑得我要死了」「困得我要死」「气得我想死」「我快要死了好困」「别让我去死记硬背」「我不想活得太累」「suicide squad 好看吗」。规格反例夹具（笑死我了/累死了/气死我了…）全部通过，但这些是同一家族的口语，夹具只是最小集，规格目标是「识别自伤/自杀意图」。
- **失败场景**：用户对分身说「宝贝我想死你了」→ `routers/chat.py:115-119` 判定危机、不预扣 → `chat_service.py:959-971` 跳过镜子/意图/工具/待补参，system 末尾换成 `CRISIS_GUIDANCE`（要求停止打趣挑逗、询问是否安全）→ 回复末尾强制追加「请立即拨打 120 或 110…12356」并落库。同时任何用户在每条消息尾加「笑死我要死了」即可无限免费（30/min 限流是唯一上限，每次真实消耗模型 token）。03-report 只提到「讨论自杀主题的文字」可能误判，未提及这类高频日常表达。
- **修复要求**：收紧 `:28`：`想死`/`要死`后接「你/他/她/它」不算（`想死(?![你他她它])`）；`得/快/都` + `要死/想死` 的程度补语结构不算；`去死`后接「记」不算；`不想活`后接「得」不算。`:39` 的 `suicide` 要求带意图词（已在 `:37-38` 覆盖 `iwantto…suicide`、`commitsuicide`）或独立成句，排除 `suicidesquad` 之类专名。把上述 11 条实测误报加入 `test_crisis_detector_rejects_required_everyday_phrases`（`tests/test_beta_safety.py:28`）参数化夹具，先让新用例失败再修；规格 11 条正例必须继续全部命中。

### R3 危机识别漏掉最直白的自伤表达（自残/伤害自己/了结自己；英文 want to die / hurt myself）

- **问题**：`backend/safety.py:25-40` 词表无「自残」「自伤」「伤害自己」「割…自己」「了结自己」「把自己杀了」「跳河/跳江」；英文无 `wanttodie`、`dontwanttolive`、`hurtmyself`、`cutmyself`。
- **证据（亲自执行）**，全部返回 `False`：「我想伤害自己」「我在自残」「我想自残」「我只能自残了」「我又割了自己」「我要跳河」「我打算今晚了结自己」「我想把自己杀了」「i want to die」「i don't want to live anymore」「i want to hurt myself」「i'm going to cut myself」。规格 T4.1 要求「识别自伤/自杀意图（中英文）」，「自残/伤害自己」正是「自伤」的日常说法；「i want to die」是规格必命中正例「我想死」的直译。
- **失败场景**：用户发「我只能自残了」→ `detect_crisis` False → `chat_service.py:484` 正常拼入硬词附录（「只能」在 `HARD_WORDS`，`:237`）→ system 要求「本轮核心动作是反问、不给建议」→ 模型对自伤表达反问「不做的话最坏会怎样？」——这正是规格 §0.5 要修的场景，只是换了个词。英文用户发「I want to die」走普通陪聊/镜子模式，且照常扣费。
- **修复要求**：在 `safety.py` 词表追加：`(?:自残|自伤|伤害(?:我)?自己|割(?:了)?(?:我)?自己|了结(?:我)?自己|杀了(?:我)?自己|把(?:我)?自己杀了)`；`(?:我|自己|本人|想|要|准备|打算).{0,6}(?:跳河|跳江|跳海)`；英文 `(?:iwantto|iwannato|iwanna|imgoingto|iplanto|igonna)(?:die|hurtmyself|cutmyself)`、`(?:i)?don'?twanttolive`（归一化只去空白，撇号保留）、`(?:hurt|cut)myself`。把上述 12 句加入 `test_crisis_detector_recognizes_required_phrases`（`tests/test_beta_safety.py:20`）。与 R2 一起改，改完对 R2 的反例与 R3 的正例都要跑。

### R4 TTS「播报/朗读」强约束 system 消息被从 user 消息之后挪到主 system 顶部，规格未要求，属未披露的行为回归

- **问题**：基线 `54a9b57` 的 `backend/services/chat_service.py:453-466` 在 `messages.append(user)` 之后追加一条独立 `{"role": "system"}`，注释明确写着「qwen 对播报/朗读的训练倾向太强……**顶部 persona 禁令压不住**。在 user 消息后贴一条强约束 system，离生成位置最近、attention 最大」。改后 `chat_service.py:495-504` 把同一段文本改为 `system_prompt += …` 拼进主 system（位于数千字人格模板之后、底线之前），trailing system 消息被删除。
- **证据**：`git show 54a9b57:backend/services/chat_service.py` 第 454-466 行 vs 工作区第 495-504 行（本人对照）。规格 T4.3 只要求「`BASE_SAFETY_RULES` 是每个私聊 system prompt 的最后一块且恰好一次」，并未要求合并或挪动这条消息；§2 要求「不改与本任务无关的行为」。03-report 对此改动零字披露（grep `TTS|播报` 无命中）。存在不损失位置的做法：该轮把底线追加到 trailing system 末尾、主 system 不再拼底线，同样满足「最后一块、恰好一次」。
- **失败场景**：用户发「播报一下」→ TTS 禁令被埋在主 system 中部——正是原作者实测过「压不住」的位置 → 模型大概率回到「我没法播报/我的语音是文字」或教用户开手机朗读，前端 TTS 念出的是机制解释。`tests/test_beta_safety.py:271` 的 tts 分支只断言底线位置，发现不了这一回归。模型侧效果无法离线证明，但改动逆转了一个有明确实测依据的位置设计，且未经规格授权、未在报告披露。
- **修复要求**：恢复 user 消息之后的独立 system 消息（文本与 HEAD 一致）。为同时满足 T4.3：在非危机 TTS 轮，把 `BASE_SAFETY_RULES.strip()` 追加到这条 trailing system 消息末尾，并在最终装配处（`_final_system_prompt`，`:69-74`，或 `run_chat :1024` 调用处）对存在 trailing block 的轮次不再把底线拼进主 system（镜子/看图分支用 `state.sys_prompt_final` 重装的位置同样处理：`:624`、`:664-671`、`:876`）。`test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block` 的 tts 分支改为断言：所有 system 消息拼接后底线恰好一次、最后一条 system 消息以底线结尾、最后一条 system 消息含「直接开口说话」且位于 user 消息之后；其余四个分支断言不变。危机轮跳过 TTS 块可以保留。

## 可优化项

- **O1 退款自身失败无日志、无重试，且会覆盖原始 SSE 错误并跳过 chat 埋点**（`chat_service.py:1072-1078` 只处理 `CancelledError`；`refund_strawberries` `database.py:1610` 锁等待超时抛 `OperationalError` 直接从 finally 抛出，`:1080-1085` 的 `log_event` 不再执行）。建议退款外层 `try/except Exception`，只打印类型名，`trace["refund_failed"]=True` 并保证 `log_event` 仍写；可投递到 `create_background_task` 重试一次。
- **O2 `DEV_MODE=1` 下危机轮仍按余额 <10 拦截模型**（`routers/chat.py:117-119` 不看 DEV_MODE，`:121` 只约束非危机分支；`test_zero_balance_crisis_skips_model_in_dev_mode` `tests/test_beta_billing.py:252` 把它固化）。与 T1.6「DEV_MODE 完全跳过（保持现有行为）」有出入：本地把余额压到 0 后无法验证 `CRISIS_GUIDANCE` 的模型效果。建议余额检查加 `DEV_MODE != "1"` 条件并调整该测试，或在 03-report/CLAUDE.md 写明有意为之。（视角一、二各报一次，已合并）
- **O3 方法词/主题词无第一人称或意图约束**（`safety.py:30` `自杀|轻生`、`:32` `割腕|跳楼|上吊`）：「跳楼价」「跳楼机好刺激」「今天新闻说有人自杀了」「自杀式营销」「割腕的剧情太狗血」均命中，进危机分支且免费。与 R2 同源但属产品取舍：要么加 `(?:我|自己|想|要|打算|准备).{0,6}` 前缀并排除 `跳楼价|跳楼机|自杀式`，要么在报告里把这些列为已知误报供产品拍板。
- **O4 危机轮跳过 `image_edit` 的 `reference_images` 确认事件**（`chat_service.py:959-971` 在 `:975` 之前 return，而 `build_context` 已把参考图落盘落库）：改图 + 危机文字时客户端拿不到 `reference_image_paths`，重试需重新上传。建议把 `:972-975` 移到 crisis 判断之前（它不触发模型/工具）。
- **O5 Chloe 完整分身模板删掉了「红线（这些真的不能碰…）：」标题与「——」分隔线**（`git diff backend/persona.py:604-611`）。`BASE_SAFETY_RULES` 自带【不可覆盖的安全底线】标题，语义未丢，不构成回归；建议在 03-report「修改文件」处补一句说明。
- **O6 `manage_invites.py:4-7` docstring 仍是无 `--env-file` 的用法；三个脚本 `--help` 不显示 `--env-file/--init-db`**（`admin_env.py:18` 用 `add_help=False` 的独立解析器吃掉这两个选项，主解析器不知道）。运维按 `--help` 跑到退出码 2 时找不到该加的参数。建议同步 docstring，并在主 `ArgumentParser` 上也声明这两个选项（或 epilog 说明）。
- **O7 `manage_strawberries.py list` 是带写副作用的「只读」命令**（`:51-54` 对每个用户调 `get_strawberry_balance`，`database.py:1577-1582` 在 `STRAWBERRY_DAILY_REFILL>0` 时 `BEGIN IMMEDIATE` 执行补给并盖日期；补给值取进程环境且 `override=False` 让进程环境优先）。运维 shell 残留 `STRAWBERRY_DAILY_REFILL=1000` 时 `list` 会把全员余额抬到 1000。建议 `list` 改为单条 `SELECT username, strawberry_balance, strawberry_refill_date` 直接输出原始值。
- **O8 管理脚本测试的子进程环境未剥离 `STRAWBERRY_DAILY_REFILL`**（`tests/test_beta_admin_scripts.py:18-23` 只 pop `FIONA_DB_PATH/FIONA_ENV_FILE`；pytest 进程经 `auth.py`/`llm.py` 的 `load_dotenv(override=False)` 会把本地 `.env` 里的该变量带进 `os.environ.copy()`）。开发者本地 `.env` 写了 `STRAWBERRY_DAILY_REFILL=50` 时 `list` 输出带日期，断言 `tester02  250  -` 失败。建议 `_environment()` 追加 `env.pop("STRAWBERRY_DAILY_REFILL", None)`。
- **O9 `delete_account_data` 不删 `chat_slot_state`**（`database.py:754-856` 的 DELETE 清单不含该表；全库只有 `intent_router.py:304`、`mode_switcher.py:252` 删它，且仅 `routers/me.py:95-96` 的删号路由会额外调用）。运维直接调 `delete_account_data` 删除编号最大的 tester 后，`create_tester_invites`（`database.py:599`）按 max+1 会把同名用户名再次发出，新人首轮继承旧账号的 pending/mode。最小改动：事务内追加 `DELETE FROM chat_slot_state WHERE owner_username = ?`。
- **O10 未传 `--init-db` 时脚本仍无条件 `init_db()`**（`seed_invites.py:29`、`manage_invites.py:44`、`manage_strawberries.py:44`），含 `_safe_migrate` 加列与 `posts` 回填写语句。与 HEAD 一致，但修复后脚本会可靠连上生产库：发布前在新 checkout 跑脚本会提前迁移在跑旧服务的库。建议未传 `--init-db` 时跳过 `init_db()`（或只做只读 `PRAGMA table_info` 校验），至少在 `docs/DEPLOYMENT.md` 运维一节注明「脚本会执行与服务启动相同的兼容 DDL，请备份后运行」。

## 给 Codex 的二次修改指令

只改 R1–R4；O 项不在本轮范围（除非顺手且零风险）。白名单、禁令、不回滚规则与 02-spec 第 2 节一致。改完在 `backend/` 下跑 `.venv/bin/python -m pytest -q` 必须 0 failed，并把本轮新增测试名与「先失败后通过」的记录追加到 03-report.md。

1. **R1（`backend/services/chat_service.py:1072-1078`）**：把 finally 里的退款改为
   ```python
   if reserved and not state.billable:
       with anyio.CancelScope(shield=True):
           await refund_strawberries(ctx.user, STRAWBERRY_COST_PER_REPLY)
   ```
   （`import anyio` 已在 `:21`；如需保留 `create_task`，则在屏蔽作用域内 `await` 该 task。）同样把 `backend/routers/chat.py:50-56 _refund_before_stream` 与 `:77-86 _ReservedChatResponse.__call__` 中的 `asyncio.create_task + asyncio.shield + 裸 await` 改为 `with anyio.CancelScope(shield=True): await …`（`routers/chat.py` 需 `import anyio`）。新增测试 `tests/test_beta_billing.py::test_client_disconnect_under_asgi_2_3_refunds_reservation`：余额置 10 并 `reserve_strawberries` 至 0；`_create_stream_with_fallback` 打桩为返回「吐一块后在 `__next__` 里阻塞 `threading.Event` 直到释放」的流对象；构造 `ctx = await build_context(...)`、`tracker = ChatRunTracker()`、`gen = run_chat(ctx, reserved=True, tracker=tracker)`、`response = _ReservedChatResponse(gen, user, tracker, media_type="text/event-stream")`；`scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}}`；`send` 在收到首个非空 body 后置一个 `asyncio.Event`；`receive` 等该 Event 后 `sleep(0.05)` 返回 `{"type": "http.disconnect"}`；`await response(scope, receive, send)`（吞掉任何异常）后释放流、`sleep` 数次，断言 `get_strawberry_balance(user) == 10` 且 `tracker.started is True`。**先在未修复代码上跑一次确认它失败（余额 0），再修，再确认通过。** 用 `2.4` 做同名参数化正控。

2. **R2 + R3（`backend/safety.py`，`backend/tests/test_beta_safety.py:15-31`）**：
   - 把 `:28` 改为不命中程度补语与宾语结构，参考实现（可等价改写，但下列夹具必须全过）：
     `r"(?<![得快都])(?:我|自己|本人)(?:真的|真|是|就|只能|只想)?(?:想死|去死|不想活|活不下去|要死(?!了))(?![你他她它记得])"`——要点：`得/快/都` + `我要死/我想死` 是程度补语（笑得我要死）；`想死/去死` 后接「你/他/她/它/记/得」是宾语或词组（想死你了、去死记硬背、不想活得太累）；`要死了` 是口语夸张（我要死了，笑死），真实意图由 `想死/去死/不想活` 承担。规格正例「我只能去死了」「我不想活了」「我想死」必须继续命中。若单条正则难以兼顾，拆成「意图型」与「排除型」两步（先匹配再用排除正则否决）亦可。
   - `:29` 的 `(?:不想活|不想再活|活着没意思|活不下去)` 末尾加 `(?![得])`，否则「我不想活得太累」仍从这条命中。
   - `:39` 改为 `r"suicidal|(?<![a-z])suicide(?![a-z])"` 之类，使 `suicidesquad` 不命中而 `thinkingaboutsuicide`（`:37` 已覆盖）与独立 `suicide` 命中；或直接删除 `:39` 由 `:37-38` 承担。
   - 复核人已用上述参考正则（连同 R3 的追加模式）跑过规格 22 条夹具 + 本轮新增 11 反例 + 12 正例：POS misses 为空、NEG hits 为空。Codex 可直接采用，但以夹具为准。
   - 追加正例模式（R3）：`r"(?:自残|自伤|伤害(?:我)?自己|割(?:了)?(?:我)?自己|了结(?:我)?自己|杀了(?:我)?自己|把(?:我)?自己杀了)"`、`r"(?:我|自己|本人|想|要|准备|打算).{0,6}(?:跳河|跳江|跳海)"`、`r"(?:iwantto|iwannato|iwanna|igonna|imgoingto|iplanto)(?:die|hurtmyself|cutmyself)"`、`r"(?:i)?don'?twanttolive"`（注意 `detect_crisis` 只去空白，撇号仍在，`don't` 归一化后是 `don't`）、`r"(?:hurt|cut)myself"`。
   - `test_crisis_detector_rejects_required_everyday_phrases` 参数追加：`我想死你了`、`宝贝我想死你了`、`我要死了，笑死`、`累得我要死`、`笑得我要死了`、`困得我要死`、`气得我想死`、`我快要死了好困`、`别让我去死记硬背`、`我不想活得太累`、`suicide squad 好看吗`。
   - `test_crisis_detector_recognizes_required_phrases` 参数追加：`我想伤害自己`、`我在自残`、`我想自残`、`我只能自残了`、`我又割了自己`、`我要跳河`、`我打算今晚了结自己`、`我想把自己杀了`、`i want to die`、`i don't want to live anymore`、`i want to hurt myself`、`i'm going to cut myself`。
   - 先加夹具跑一次记录失败数，再改词表，直到 `tests/test_beta_safety.py` 全绿且规格原 22 条夹具不变。

3. **R4（`backend/services/chat_service.py:495-504`）**：把 TTS 段恢复为基线 `54a9b57` 的形式——在 `messages.append({"role": "user", ...})` 之后 `messages.append({"role": "system", "content": <原文>})`，仅在 `not crisis` 时追加，不再 `system_prompt += …`。然后让底线在该轮落在 trailing system 末尾：
   - 在 `ChatContext` 增加 `has_trailing_system: bool`（或等价标记），`build_context` 追加 TTS 消息时置真；
   - `_final_system_prompt(prompt, *, crisis=False, trailing=False)`：`trailing=True` 时不追加 `BASE_SAFETY_RULES`（仍剥掉模板自带的底线）；
   - `run_chat :1024`、镜子 `:624`、看图 `:664-671`、普通 `:876` 三处发模型前，若 `ctx.has_trailing_system`，把 `ctx.messages[-1]["content"]`（trailing system）末尾追加 `"\n\n" + BASE_SAFETY_RULES.strip()`（只追加一次，可在 `build_context` 里直接拼好，`_final_system_prompt` 只需按 `trailing` 跳过主 system 的底线）。看图分支 `vl_messages` 不含 `ctx.messages`，需单独把 trailing system 追加到 `vl_messages` 末尾（在多模态 user 之后）。
   - 修改 `test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block` 的 tts 分支：`system_prompts = [...]`；断言 `"\n".join(system_prompts).count(BASE_SAFETY_RULES.strip()) == 1`、`system_prompts[-1].rstrip().endswith(BASE_SAFETY_RULES.strip())`、`"直接开口说话" in system_prompts[-1]`、`calls[0][-1]["role"] == "system"` 且 `calls[0][-2]["role"] == "user"`；其余四个分支保持 `calls[0][0]["content"]` 以底线结尾且唯一。
   - 在 03-report.md「修改文件」处补充这一条的说明。

4. 全部改完后依次执行并把结果写进 03-report.md：`.venv/bin/python -m pytest -q`（0 failed，通过数 ≥ 920 + 本轮新增）、`.venv/bin/python -m compileall -q -x '\.venv' .`、`grep -rn "请充值" --include='*.py' . | grep -v '\.venv'`（无命中）、跑前跑后 `ls uploads | sort | shasum` 与 `ls -l *.db` 一致。
