# 独立复核：多智能体讨论群第一期（后端引擎）

复核对象：基线 `859e2c5` + 待审改动（R1–R3 返修 + 派单方门禁后补的两条用例）。唯一依据：`02-spec.md` v1.1。实现方报告和三张返修单只当线索用。

所有改坏代码、加探针的实验都在系统临时目录下的 APFS 克隆里做，做完就删。复核副本里我只临时放过一次 `verify/zombie_probe.py` 的副本（跑完已删）。工作区与开始时相比只多出本文件。

---

## 1. 结论

**不通过。** 有 4 条必须修复：

| 编号 | 一句话 |
|---|---|
| M1 | 分身路径（后台 brief/view 步骤，以及 GET 详情）里有两个写事务没做取消保护：`agent_store.get_my_agent` 和 `get_memory_snapshot` 都是 `BEGIN IMMEDIATE`。用 R3 那套机制可以稳定复现 `database is locked`。 |
| M2 | 立项阶段在方案已写入（`plan_revision=1`）、还没到 `awaiting_start` 时停下的群，点「继续」后会直接进入 `running`。结果是跳过作者开工，在作者没确认方案、预算和模型的情况下跑付费轮次。 |
| M3 | 固定席位的身份设定没有单独成一行，而是直接粘在 JSON 输出示例的右花括号后面，违反规格 4.4 和附录 A 第 9 条。 |
| M4 | 付费路径的关键性质没有测试。暂停、续跑、删群里的 `reserved == 0` 等断言只在免费模式下跑，所以恒真。原子结算写缓存、计费令牌守卫、暂停或删群时取消任务这四处改坏后，156 条用例全部照样通过。 |

其余方面基本符合规格：

- **账号隔离**：没发现越权。所有 SQL 都带 `username`，17 条路由都挂了 `discuss_user`。
- **计费守恒**：主路径没发现错扣、重扣或扣成负数。
- **令牌守卫**：后台写库都经过令牌守卫。
- **提示词**：除 M3 外，与 `pilot.py` 逐字一致，改动恰为附录 A 列出的几处。
- **日志**：没有写入诉求、发言、提示词、搜索问题或模型响应。

## 2. 规格第 8 节验收标准的核验

命令都从 `backend/` 执行，前面加 `NO_PROXY=… no_proxy=…`。

| # | 标准 | 我实际做了什么 | 结果 |
|---|---|---|---|
| 1 | 新测试全过、0 跳过 | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` | `156 passed, 45 warnings in 13.29s`，0 跳过 |
| 2 | 全量 = 基线 + 新增 | 没有具体怀疑，没重跑。采信派单方的 8508 passed / 0 failed / 0 skipped，8352 + 156 = 8508 算术上对得上 | 采信 |
| 3 | 新测试在基线上全红 | `git archive 859e2c5` 解到系统临时目录（不动仓库元数据），克隆 `.venv`，拷入 7 个新测试文件运行 | 7 个文件都在收集阶段报 `ModuleNotFoundError: No module named 'discuss'`，0 通过 |
| 4 | 白名单 | `git status --porcelain --untracked-files=all` | 53 行：9 个已跟踪文件、`backend/discuss/` 11 个、`routers/discuss.py`、7 个 `test_discuss_*.py`，其余都是任务目录材料。产品代码全在第 9 节内；任务目录里除 `impl/report.md` 外都不在第 9 节，属派单方材料 |
| 5 | 既有测试没改 | `git diff 859e2c5 -- backend/tests` | 只有 `conftest.py` 一处改动 |
| 6 | conftest 恰好一行 | `git diff -U0 859e2c5 -- backend/tests/conftest.py` | `@@ -52 +52 @@`，内容与规格一字不差 |
| 7 | 没加依赖 | diff `requirements*.txt` | 空 |
| 8 | CLAUDE.md 大小 | `wc -c` | 68,431，不超过 69,300 |
| 9 | 没有 node_modules 时也全过 | 本副本本来就没有 `frontend/node_modules` | 第 1 条就是在这个条件下跑的 |
| 10 | 开关关闭时行为不变 | `test_admission_hides_every_route_when_disabled` 在开关未设、`0`、`true` 三种情况下逐条请求 17 条路由，都是 404 和 `Not Found`。`/health` 没单独复跑；结构测试确认迁移仍是 5 道、`init_db` 可重复执行 | 通过 |

另外跑过的核验：

- **提示词逐字比对**：用脚本加载 `verify/pilot.py` 和 `discuss/roles.py`，逐行 diff。
  - `LENSES`、`RULES`、`JSON_RULE`、`critique` 完全相同。
  - `plan`、`queries`、`note`、`decide`、`draft`、`accept`、`rework` 的差异，恰好是附录 A 第 2–7 条要加的行，以及 decide/rework 的输出 JSON 说明。
  - `SEARCH_SYSTEM.format(today=…)` 与 pilot 相同。
  - 分身身份、`brief`、`view` 和隐私说明，与规格原文逐字相同。
  - `solo_*` 没搬，符合要求。
- **`verify/zombie_probe.py`**：复制进 `backend/tests/` 跑，输出 `ZOMBIE_PROBE write_interrupted_by_cancel=False lock_in_cleanup=free`，`1 passed`，副本已删。
- **派单方变异抽查**：用 `verify/mut_discuss.py` 抽了 W1、W3、W5、T1、E23 五条，克隆在系统临时目录，结果全部靠断言失败被杀死。

## 3. 必须修复项

### M1 分身路径的写事务没有取消保护，可以稳定复现 `database is locked`

- **哪里错**
  - `discuss/avatar.py:24-25` 的 `build_avatar_system` 和 `:74` 的 `display_name`，直接 `await agent_store.get_my_agent(...)` 和 `get_memory_snapshot(...)`。这两个函数都开 `BEGIN IMMEDIATE`，里面用 `_one`：先 execute，再 fetchone。
  - 调用方有两处：
    - `engine._avatar_try`（`engine.py:308-309`），后台任务在 brief 和 view 步骤前调用。
    - `service._avatar_member` 和 `service.detail`（`service.py:376`、`556`、`565`），每次 GET 详情最多调两次。
  - R3 要求「engine.py 里直接或间接发起的写入」和「service.py 里的写事务」都要受保护，这两条漏了。而 `verify/lock-root-cause.md` 记录的正是这种机制。
- **复现**：探针代码见第 6 节 B。
  - 做法：给 `aiosqlite.Connection._execute` 装钩子，让 `SELECT * FROM agents WHERE owner_username` 执行完、游标还没取走时停住。这时取消正在执行 `avatar.system_for(USER, "brief")` 或 `avatar.display_name(USER)` 的任务，并在它的 `finally` 里用忙等待 0.2 秒的新连接执行 `BEGIN IMMEDIATE`。
  - 结果：两个调用点都报 `OperationalError: database is locked`（2 failed）。
  - 对照：把 `avatar.py` 里三处调用包进 `NovelBilling._drain(...)` 后，同一探针 2 passed。
- **后果**：和 R3 的起因一样，写锁要等异常对象被回收才释放。在此期间：
  - 任务收尾时的退款、清令牌，以及 `cancel_group` 里的退款，都会等满 5 秒后失败；
  - 暂停接口返回 500，群停在 `running`，令牌没清，预扣没退；
  - 全站其他模块的写入也会被挡住。
- **期望改法**
  - 在 `avatar.py` 里把三处调用改成 `await NovelBilling._drain(agent_store.get_my_agent(username))` 这种形式。规格 3.5 允许用 `_drain`，不需要改 `agent_store.py`。
  - `detail` 在一次请求里只取一次分身名字。
  - 把探针收进正式测试，两个调用点各一条，并做自检：去掉 `_drain` 后必须变红。

### M2 立项阶段在方案写入后停下，「继续」会跳过等开工，直接跑付费轮次

- **哪里错**
  - `engine.run_planning` 的执行顺序是：
    1. 先在一个事务里写入方案，并把 `plan_revision` 置为 1（`engine.py:362-368`）；
    2. 再跑分身 brief，要等一次模型调用；
    3. 最后才把状态改成 `awaiting_start`（`:400-401`）。
  - `service.resume` 按 `plan_revision == 0` 决定回 `planning` 还是进 `running`（`service.py:819`）。
  - 在第 2 步期间停下的群（作者暂停、余额不足、预算不够、意外错误、重启恢复失败），`plan_revision` 已经是 1，继续时就直接进了 `running`。
- **复现**：探针在第 6 节 C。
  - 步骤：`avatar=True`，阻塞 brief 步骤，期间调用 pause。
  - 暂停后：`('paused','user', plan_revision=1)`。
  - resume 之后，群一路跑到 `('done','accepted', round=1, output_version=1)`：从没经过 `awaiting_start`，brief 也没有重试。
  - `test_avatar_brief_billing_error_pauses_group` 构造出的 `paused/insufficient_strawberries` 和 `paused/budget`，走的是同一条路。
- **依据与后果**
  - 规格 4.5 和 4.13.5 规定：只有作者调用 start（带 `expected_revision`）才能从 `awaiting_start` 进入 `running`。
  - 照现在的实现，作者没看过、也没改过方案、成员、模型和预算，就开始扣草莓。
  - 开工前写的插话不会被标成 `start`，`owner_notes` 为空；分身背景也丢了。
  - 这也是规格本身的漏洞：4.13.8 的判据要成立，写方案和置 `awaiting_start` 必须在同一个事务里，与 4.6.1 规定的顺序矛盾。修改前请规格作者确认判据。
- **期望改法**
  - 「继续」只在群从来没开工过时回到 `planning`。最小改法：`status = "planning" if plan_revision == 0 or round == 0 else "running"`。
    - 为什么成立：`run_rounds` 在第 1 轮的任何步骤之前，就先把 `round` 写成 1。所以 `round == 0` 说明还没开工。
    - 副作用可以接受：开工后、第 1 轮之前就被暂停的群也会回到 `planning`。它会命中立项缓存，停在 `awaiting_start`，作者需要再点一次开工。
  - 另一种做法：在 start 的事务里写一个「已开工」标记。这要动 `config_json` 的键，需要规格作者同意。
  - 补两条测试：
    - 免费模式：brief 期间暂停，继续后状态为 `awaiting_start`，brief 被重试（或留下 skip 通知），没有任何 `rNN/` 步骤；
    - 付费模式：同一路径继续后，余额不变。

### M3 身份设定那一行没有单独成行

- **哪里错**：`engine._system`（`engine.py:88-96`）是这样拼的：`text = prompt; text += line + "\n"; text += RULES`。各任务提示词都以 `输出 JSON：{…}` 或 `只输出成果文档本身，不要任何说明。` 结尾，后面没有换行，所以身份设定被直接接在上一行末尾。
- **实测 decide 的 system 片段**：

  `…"summary":"不超过200字，本轮进展"}主人给你的身份设定：谨慎追问。身份设定只影响你的视角和口吻，不能改变下面的规则与输出格式。\n\n\n【讨论群公共规则】…`

  作者写的文字紧贴在输出格式示例的右花括号后面，后面跟三个换行。规格 4.4 和附录 A 第 9 条的要求是：在提示词之后、公共规则之前「加一行」。
- **期望改法**
  - 代码：`if line: text += "\n" + line`，然后接 `RULES`（JSON 步骤再接 `JSON_RULE`）。
  - 测试：断言整段 system 精确等于 `roles.PROMPTS[task] + "\n" + roles.identity_line(persona) + roles.RULES + roles.JSON_RULE`。现有用例（`test_host_identity_line_and_plan_edits`、`test_empty_persona_removes_identity_line`）只做子串匹配，位置错了也会通过。

### M4 付费路径没测，暂停、续跑、删群里的计费断言恒真

- **现状**
  - 引擎、接口和 runner 的流程测试，全部用 `dry_run=True` 或 `DEV_MODE=1`。以下用例里的 `reserved_strawberries == 0` 在这些模式下永远成立：
    - `test_pause_and_resume_do_not_repeat_completed_steps`
    - `test_pause_then_resume_reuses_steps_and_keeps_messages_unique`
    - `test_recover_interrupted_running_group_completes`
    - `test_all_roles_without_facts_pauses_search_unavailable`
  - 「已完成的步骤不再调用模型」只在免费路径上验证过，那条路径用 `store.write_step` 写缓存。付费时真正写缓存的是 `DiscussBilling._finish_transaction` 里的 `write_step_on_connection`（`billing.py:199-204`），没有一条用例覆盖。
  - 付费测试只跑了一轮就通过的单程流程，没有续跑。删群测试只删已经完成的群。
- **存活变异**（第 6 节 A，156 条用例全部照样通过）：

  | 编号 | 改法 | 线上会怎样 |
  |---|---|---|
  | X1 | 原子结算不写步骤记录 | 付费步骤扣了费但不缓存，每次续跑都会重新调用、重新扣费 |
  | X4 | 计费守卫不核对令牌 | 过期任务仍能预扣和结算 |
  | X25 | 暂停不取消后台任务 | 暂停接口返回时预扣还没退，任务还在跑 |
  | X26 | 删群不取消后台任务 | 付费时在途的预扣随着行一起被删掉，用户的草莓丢失 |

- **期望改法**：补 4 条付费模式用例（`DEV_MODE=0`，替换 `LLMRouter._single_real_call`）：
  - (a) 付费模型调用阻塞时调用 pause：接口一返回，`reserved == 0`，余额等于初始值减 spent；
  - (b) 同样情形下调用 delete：余额等于初始值减「删群前的 spent」；
  - (c) 付费跑到 `awaiting_user` 后 continue：之前 `status=ok` 的模型步骤不再被调用，余额减少量等于 spent；
  - (d) 用旧令牌的 `DiscussBilling` 调用 `reserve` 和 `reserve_fixed`：都抛 `RunNoLongerActive`，余额和表行不变。

  我在克隆里写了这 4 条（要点见第 6 节 D）。在当前代码上 4 条都通过；分别对上 X1、X4、X25、X26 时，都由对应用例靠断言失败杀死。

## 4. 可优化项（不阻断）

### 计费与并发

1. **删群与并发「继续」的竞态。** `delete` 先 `cancel_group`，再 `delete_group`。如果两步之间同一用户的 resume 恰好启动了新任务，并在 `delete_group` 之前完成预扣，那么 reserved 行会被一起删掉，预扣不会退回。窗口极小。建议在 `delete_group` 的同一个事务里，先把该群 reserved 行的金额退回用户余额。
2. **预扣行会被覆盖。** `reserve` 和 `reserve_fixed` 遇到冲突时，直接覆盖 `strawberries_reserved`。如果某一步已经留着一条 reserved 行，再次预扣时旧金额就丢了。这种行出现在：进程在 `_pause` 提交之后、`_cleanup` 退款之前被杀，群停在 `paused`。`recover` 只处理 `planning` 和 `running` 的群，不会退这笔钱。建议 resume/continue 启动前先 `refund_reserved()`，或者启动时对所有 `reserved_strawberries > 0` 的群退款。结构与书斋相同，概率很低。
3. **每日上限可以绕过。** 每日上限按库里现存的群数计，删群后名额会回来。`DEV_MODE` 下这部分费用由平台承担。
4. **失败步骤的重复开销。**
   - 失败的搜索和失败的分身步骤，每次重放都会重做；搜索还会再扣一次固定费，即便它下游的步骤早已缓存。规格明文接受「继续时会重查」，但重放更早的轮次时这纯属浪费。
   - 第 1 轮没拿到事实的成员，重放时如果查到了，会在第 1 轮补出一条笔记。
   - 可以考虑：只有下游步骤还没缓存时才重查。
5. **文案与计费不完全一致。** 隐私说明和 README 写「选『我的模型』不扣」，但搜索固定费照扣，实现和测试都是这样理解的。文案是规格原文，建议规格作者补一句。

### 令牌、取消与写锁

6. **令牌认领与创建任务之间被取消。** `start_group` 在认领令牌的事务提交之后、创建任务之前，如果被取消（只可能发生在 `_drain` 里），会留下一个状态是 running 或 planning、令牌非空、却没有任务的群。界面上它一直显示「进行中」，还会挡住新建或开工别的群。
   - 我用提交闸门复现：取消后为 `('running', 令牌非空, TASKS 里没有)`。
   - 可以救回：pause 时 `cancel_group` 没有任务也照样退款、清令牌，结果为 `('paused','user',None)`；重启恢复也能救回。
   - 建议：认领之后捕获 `CancelledError`，要么照样创建任务，要么在受保护的事务里清掉令牌后再抛出。
7. **`_drain` 可能丢掉取消。** `NovelBilling._drain` 在「外层被取消、同时内层抛异常」时，会把内层异常交给调用方，取消就丢了。讨论群里这类异常多是 `RunNoLongerActive` 或 `HTTPException`，影响有限。但 `_avatar_try` 会吞掉 `Exception`，极端情况下（取消恰好碰上数据库错误），任务会把后面的流程跑完，`cancel_group` 要一直等。可以在 discuss 内用一个自己的辅助函数：只要曾被取消，内层结束后一律抛 `CancelledError`（`from` 内层异常）。
8. **只读路径的游标。** 只读路径（`get_group`、`list_messages`、`read_step` 等）同样可能留下没取走的游标。在 WAL 模式下，这只会让僵尸连接在被回收前占着一个读快照，阻止检查点回收 WAL，不会占写锁。可以接受。
9. **R3 改动对调用方的影响。** R3 把 `transaction()` 改成了 `transaction(operation)`，与规格 4.10「yield None」的写法不一致（返修单允许），建议同步改规格。与改之前相比：
   - 过期任务的写入仍然不会落库；
   - `write_step` 和 `append_usage` 遇到过期令牌改为抛 `RunNoLongerActive`，这正是规格 4.10 的要求；
   - 在 `LLMRouter` 里：`append_usage` 在 `_attempt` 的 `finally` 中抛出时，会先尝试退款（因令牌失效被吞掉）再上抛；`_with_retries` 原样上抛，runner 安静结束；预扣由不带令牌的 `refund_reserved` 退回。
   - 返回值没人用。对调用方没有不良影响。
10. 我逐个检查了 `run_write` 和 `transaction` 收到的 operation，只用传入的 `db`；计费里的 `write_step_on_connection` 也用同一连接。没有发现写事务内部另开连接写库。

### 流程与接口

11. **`draft` 的初始值。** `run_rounds` 开头把 `draft` 设成了最新一版成果（`engine.py:437-438`）：首次运行时为空，重放时却是最新版。它只会被已缓存的第 1 轮质疑和撰稿的载荷用到，目前无害；但不符合「重放时内存状态与首次运行一致」，建议初始化为空串。
12. **分身系统提示的顺序。** 现在的顺序是「分身四段 + 任务提示 + JSON 规则」。按规格 4.6 的字面，应该是「任务提示 + 分身系统提示（代替公共规则）+ JSON 规则」。另外，`AVATAR_IDENTITY` 的最后一行与 `JSON_RULE` 都写了「只输出一个 JSON 对象」，重复了。请规格作者确认顺序。
13. **固定席位的名字不能清空。** 名字传空字符串会返回 422（`service.py:183-184`）。规格 4.4 的「空字符串表示清除」是否也适用于名字，说法有歧义。现在作者想改回默认名，只能手动输入默认名。请规格作者确认。
14. **建群时不查成员重名。** 建群时 `members` 不检查名字重复，改方案时会检查。重名会让「名字 → 代号」的归一结果取决于成员顺序。
15. **GET 详情占写锁。** 每次 GET 详情最多调两次 `get_my_agent`，每次都开 `BEGIN IMMEDIATE`，轮询时会一直争抢全局写锁。建议一次请求只取一次，与 M1 一并处理。

### 测试缺口（变异存活，但当前代码是对的）

- **规格写明、但没有断言的载荷与截断**：X12（返工载荷不带引用问题）、X15（撰稿载荷不带分身背景）、X35（笔记载荷带全部来源）、X34（事实不截到 160 字）。
- **状态机映射**：X17、X18、X19 说明 runner 对 `StepFailed` 和恢复模式的映射（`step_failed`、`server_restart_failed`）没有任何用例。把步骤失败改成 `failed/error` 也照样通过。
- **准入与上限**：
  - X20：全站并发上限 `FIONA_DISCUSS_MAX_RUNNING` 没测；
  - X22：补充材料的危机检查没测；
  - X31、X32、X33：开工、继续、追加轮数时「已有别的群在跑」没测，只测了建群；
  - X30：详情的 `after` 参数没测，而轮询依赖它。
- **流程分支**：
  - X40：立项中暂停后继续回到 `planning` 没测，与 M2 相关；
  - X14：把 `_gather_all` 改回普通的 `gather` 也存活。金额有不带令牌的退款兜底，但失败后兄弟任务还在跑，浪费平台调用。
- **零散上限**：X27（群列表最多 50 个）、X28（删成员时清掉它的模型）、X37（分身默认模型取自带模型）、X39（新增自定义成员跳过已用代号）、X44（身份设定 300 字上限）。
- **冗余防护（可接受）**：X3、X8、X16、X21、X36、X5、X6、X13、X41、X42 存活，是因为另有一层兜住或分支走不到。

## 5. 给实现方的修改指令（可直接转发）

依据 `docs/tasks/2026-11-14-agent-group/02-spec.md` v1.1，以下四件事都要做。只改 `backend/discuss/avatar.py`、`engine.py`、`service.py` 和 `backend/tests/test_discuss_*.py`，其他文件不动。M2 的判据会改变规格 4.13.8 的字面，动手前先请规格作者确认。

1. **M1 分身路径的取消保护**
   - `avatar.py` 里对 `agent_store.get_my_agent` 和 `agent_store.get_memory_snapshot` 的三处调用（`build_avatar_system` 两处，`display_name` 一处），全部改成 `await NovelBilling._drain(<原调用>)`。
   - `service.detail` 每次请求最多调一次 `avatar.display_name`，`_avatar_member` 复用这个结果。
   - 在 `tests/test_discuss_runner.py` 加两条用例，写法参照本复核第 6 节 B：钩住 `aiosqlite.Connection._execute`，在 `FROM agents WHERE owner_username` 那条查询执行完后停住，取消调用方任务，在它的 `finally` 里用忙等待 0.2 秒的新连接执行 `BEGIN IMMEDIATE`，必须立刻成功。两条分别覆盖 `avatar.system_for` 和 `avatar.display_name`。
   - 自检：去掉 `_drain` 后两条都要变红，贴出输出。

2. **M2 「继续」不能跳过开工**
   - `service.resume` 的状态判据改成「从来没开工过才回 planning」，建议写成 `"planning" if plan_revision == 0 or round == 0 else "running"`（理由见本复核 M2）。
   - 新增用例：`avatar=True`，阻塞 brief 时暂停，然后继续。断言：群停在 `awaiting_start`；没有任何 `rNN/` 步骤和消息；brief 被重试，或留下 `r00/02-brief-avatar-skip` 通知。
   - 再加一条付费模式的同类用例（brief 抛 `InsufficientStrawberries`，然后加余额继续）：继续后停在 `awaiting_start`，余额减少量等于 spent。

3. **M3 身份设定单独成行**
   - `engine._system` 改成：提示词 + `"\n" + identity_line`（有身份设定时才加）+ `RULES` + （JSON 步骤再加）`JSON_RULE`。
   - 把 `test_host_identity_line_and_plan_edits` 和 `test_empty_persona_removes_identity_line` 的子串断言，改为对整段 system 的精确比较，至少覆盖一个 JSON 步骤（decide）和撰稿步骤。

4. **M4 补付费模式用例**
   - 在 `tests/test_discuss_billing.py` 里增加四条（写法见本复核第 6 节 D）：
     - 付费调用阻塞时 pause：接口返回后 `reserved == 0`，余额等于初始值减 spent；
     - 付费调用阻塞时 delete：余额等于初始值减删群前的 spent；
     - 付费跑到 `awaiting_user` 后续跑：已 ok 的模型步骤不再被调用，余额减少量等于 spent；
     - 旧令牌的 `DiscussBilling` 调用 `reserve` 和 `reserve_fixed`：抛 `RunNoLongerActive`，余额和表行不变。
   - 自检：对 X1、X4、X25、X26 四条变异（第 6 节 A 的表）逐一确认都靠断言失败变红。

验收：

- `tests/test_discuss_*.py` 全部通过、0 跳过；
- 全量通过数等于 8352 加新测试总数，0 失败；
- 上述各项自检贴出输出；
- `git status` 只多出允许的文件。

## 6. 变异实验与探针

### A. 我加的 45 条变异

都没在 `mut_discuss.py` 里出现过。在系统临时目录的克隆里逐条改一处，跑 `tests/test_discuss_*.py`（带 `-x`），然后还原。开头的正控和结尾的复跑都是 `156 passed`。

**被杀死的 11 条**（全部是断言失败）：

| 编号 | 改法 | 杀死它的用例 |
|---|---|---|
| X2 | 搜索结算不写步骤记录 | billing::test_search_charges_fixed_and_refunds_failure |
| X7 | 全额退款不把步骤标成已退 | billing::test_cancel_after_search_reservation_refunds_all_precharges |
| X9 | 发消息去掉 `OR IGNORE` | api::test_rounds_exhausted_then_continue |
| X10 | 存成果不按步骤键去重 | api::test_rounds_exhausted_then_continue |
| X11 | 读取点在步骤已缓存时仍认领新插话 | api::test_done_continue_with_note_reworks_and_adds_second_version |
| X23 | 插话不做危机检查 | engine::test_five_unread_notes_and_crisis_note |
| X24 | 完成后返工不记 revisions | api::test_done_continue_with_note_reworks_and_adds_second_version |
| X29 | 读群不带 username 条件 | api::test_other_user_cannot_touch_group |
| X38 | `owner_notes` 不带作者对提问的回答 | engine::test_pre_start_notes_enter_owner_notes |
| X43 | 分身系统提示去掉基础安全规则 | engine::test_avatar_brief_and_view_prompts |
| X45 | 删群事务不删来源表 | api::test_delete_group_removes_all_five_tables |

**存活的 34 条**（156 条全部照样通过）：

| 编号 | 改法 | 评估 |
|---|---|---|
| X1 | 原子结算不写步骤记录 | **M4**：付费续跑会重复调用、重复扣费 |
| X4 | 计费守卫不核对令牌 | **M4** |
| X25 | 暂停不取消后台任务 | **M4** |
| X26 | 删群不取消后台任务 | **M4**：付费时在途预扣丢失 |
| X40 | 立项中暂停后继续直接进 running | 测试缺口，与 M2 相关 |
| X12 | 返工载荷不带引用问题 | 测试缺口（规格 4.6.2） |
| X15 | 撰稿载荷不带 `owner_context` | 测试缺口（规格 4.6.2） |
| X34 | 事实不截到 160 字 | 测试缺口（规格 4.8） |
| X35 | 笔记载荷带全部来源 | 测试缺口 |
| X14 | `_gather_all` 改回普通 `gather` | 测试缺口 |
| X17 | 恢复时步骤失败不记 `server_restart_failed` | 测试缺口（规格 4.12） |
| X18 | 恢复时意外异常记成 `failed` | 测试缺口（规格 4.12） |
| X19 | 步骤失败记成 `failed/error` | 测试缺口：`step_failed` 从没被断言过 |
| X20 | 全站并发上限不生效 | 测试缺口 |
| X22 | 补充材料不做危机检查 | 测试缺口（规格 4.13.2） |
| X30 | 详情忽略 `after` | 测试缺口 |
| X31 | 开工不查是否有别的群在跑 | 测试缺口 |
| X32 | 继续不查是否有别的群在跑 | 测试缺口 |
| X33 | 追加轮数不查是否有别的群在跑 | 测试缺口 |
| X27 | 群列表不限 50 个 | 测试缺口 |
| X28 | 删成员时不清它的模型 | 测试缺口 |
| X37 | 分身默认模型不看自带模型 | 测试缺口 |
| X39 | 新增自定义成员不跳过已用代号 | 测试缺口 |
| X44 | 身份设定可以超过 300 字 | 测试缺口 |
| X3 | 计费守卫不核对账号 | 冗余：删号时群行在同一事务里删掉 |
| X8 | 写库守卫不核对账号 | 冗余：同上 |
| X16 | 收尾清令牌不核对自己的令牌 | 冗余：新旧任务不会重叠 |
| X21 | 任务自己收尾时不退预扣 | 冗余：`cancel_group` 另有一层 |
| X36 | 终态不自动清令牌 | 冗余：调用方都会显式清 |
| X5 | 模型预扣被取消时不补退 | 冗余：收尾时整笔退还 |
| X6 | 搜索预扣被取消时不补退 | 冗余：同上 |
| X13 | 立项结果总是覆盖已有方案 | 分支走不到 |
| X41 | 接受成果只留事务内检查 | 冗余 |
| X42 | 建群不查账号是否存在 | 冗余：鉴权已经保证 |

### B. 分身路径的写锁探针（M1）

```python
def _hold_after(monkeypatch, marker):          # 让指定查询执行完、游标未取走时停住
    entered, release, fired = asyncio.Event(), asyncio.Event(), [False]
    original = aiosqlite.Connection._execute
    async def hooked(self, fn, *args, **kwargs):
        result = await original(self, fn, *args, **kwargs)
        if not fired[0] and args and isinstance(args[0], str) and marker in args[0]:
            fired[0] = True; entered.set(); await release.wait()
        return result
    monkeypatch.setattr(aiosqlite.Connection, "_execute", hooked)
    return entered, release

# 准备：init_db、建用户、先调一次 agent_store.get_my_agent(USER) 让 agents 行存在
async def worker():
    try:
        await avatar.system_for(USER, "brief")     # 另一条用例换成 avatar.display_name(USER)
    finally:
        await _assert_write_lock_free()            # 新连接 timeout=0.2，执行 BEGIN IMMEDIATE
# 等 entered → task.cancel() → sleep(0.05) → release.set() → 期望 CancelledError，且收尾时拿得到写锁
```

- 当前代码：`[system_for]`、`[display_name]` 都报 `OperationalError: database is locked`，2 failed。
- 在 `avatar.py` 加上 `_drain` 后：2 passed。

### C. 立项后暂停再继续的探针（M2）

- 设置：`avatar=True`，FakeLLM 让 brief 一直阻塞，直到被取消。
- 结果：`RESUME_PROBE {'while_brief': ('planning', 1), 'paused': ('paused','user',1), 'after_resume': ('done','accepted',1,1), 'brief_retried': False, 'steps': ['r00','r01']}`。

### D. 我写的付费模式用例（M4）

复用 `test_discuss_billing.py` 里的 `prepare`、`snapshot`、`passing_script`、`fake_results`、`search_fake`、`run_group`：

- **pause 和 delete**（参数化）：
  1. 先用不阻塞的付费调用器跑完立项，把群改成 running；
  2. 换成「critique 步骤阻塞」的付费 `_single_real_call`，调用 `start_group`，等阻塞发生；
  3. 断言此时 `reserved > 0`；
  4. pause 分支：断言 `('paused','user')`、`reserved == 0`、余额等于 10000 − spent；
  5. delete 分支：断言余额等于 10000 − 删群前的 spent。
- **付费续跑**：
  1. accept 脚本判不通过，`max_rounds=1`，跑到 `awaiting_user`；
  2. 记下所有 `status=ok` 的模型步骤键；
  3. 把 `max_rounds` 改成 2，置为 running 后再跑；
  4. 断言新调用里没有这些键，余额等于 10000 − spent。
- **过期令牌**：`DiscussBilling(USER, gid, "old-token")` 的 `reserve(call())` 和 `reserve_fixed(...)` 都抛 `RunNoLongerActive`，余额、`reserved` 和步骤行都不变。

在当前代码上 4 passed；分别对 X1、X4、X25、X26 运行，都由对应用例靠断言失败杀死。

### E. 其他探针

- **令牌认领后被取消**（可优化项 6）：在 `run_write` 的提交处设闸门，取消 `start_group`。输出 `CLAIM_PROBE {'cancelled': True, 'after_cancel': ('running', True, False), 'after_pause': ('paused','user',None)}`。
- **R3 四条取消用例的性质**：去掉 `run_write` 的 `_drain` 后，四条只在「取消不应在事务收尾前生效」这条断言上失败，规格作者补的游标用例仍然通过。见第 7 节第 8 条。

## 7. 附：各重点的核对结论

1. **计费守恒与并发**
   - 预扣、结算、退款都在 `BEGIN IMMEDIATE` 内完成，并由 `_drain` 保护。结算最多扣到预扣额，余额扣减带 `>=` 条件，状态从 reserved 变为 settled 或 refunded，保证只退一次。
   - 暂停、删群、删号、关停时，任务被取消后先在自己的收尾里退一次；`cancel_group` 再退一次，第二次是空操作。重启时 `recover` 对在跑的群先退款再重启。
   - `engine` 里另建的 `DiscussBilling` 和调用器里的那个并存没有问题：两者都核对令牌，各自的锁只用来减少等待，真正的串行由 SQLite 的写锁保证，预算判断读的是当前行。
   - 搜索固定费：预扣、成功后结算并写步骤、失败退款，都对。
   - 免费路径：`DEV_MODE`、`byok:self`、`fake:` 不扣费，`dry_run` 不调用计费，都对。
   - 遗留风险见 M4，以及可优化项 1、2。
2. **令牌守卫与续跑**
   - 后台的每次写库都经过令牌守卫：`DiscussStepStore` 的方法、`_pause`，计费靠 `_active`，收尾清令牌也要求令牌和账号匹配。例外是 M1 那两个 `agent_store` 写事务，它们会核对账号存在，不会在删号后重建数据。
   - 重放：要点、缺口、任务、质疑、分身意见都由缓存的结果确定性重建；`draft` 的初值见可优化项 11。
   - 去重：消息和成果都按步骤键去重，已有变异和用例证明。
   - `continue` 两种情形和 `revisions` 的重放逻辑都对上了 4.6.4。
   - 启动恢复和关停没发现问题。
3. **账号隔离**：所有 SQL 都带 `username`；17 条路由都挂了 `discuss_user`；别人的群一律 404，已有用例逐个接口覆盖，X29 被杀死。
4. **私有记忆与提示词**
   - 私有记忆只出现在分身两步的系统提示里。别的成员只看得到分身输出的 `context` 和意见，与隐私说明一致。
   - 系统提示没有拼账号名。
   - 自定义成员的名字和职责代入 `{name}` 和 `{does}`，正确。
   - 身份设定的位置见 M3；提示词逐字比对的结论见第 2 节。
5. **流程**：按 4.6、4.7 逐条对过。以下各项都对：
   - 「再查一轮」的限制同时体现在载荷和校验里；
   - 作者组队和主持人点将两条路径；
   - 角色归一，包括作者改过的名字和自定义成员的名字；
   - 插话的认领与逐条回应；
   - 验收通过条件，丢弃非逐字引用；
   - 截断由校验器返回值生效，落库和下发之前就截了；
   - 来源只登记搜索返回的结果，成果里不允许出现 http(s) 网址。
6. **接口**
   - 17 个接口的前置状态、返回码和文案逐条对过，都与 4.13 一致。
   - 建群时诉求字数校验（422）排在危机检查（400）之前，这与「依次检查」的字面顺序略有出入，但不影响「不落库」。
   - 危机文本不落库、不进日志；每日上限和「同时只能有一个在跑」都在事务里检查。
   - 遗留问题见 M2，以及可优化项 3、13、14。
7. **日志**：逐个看过 `discuss/` 里的 logging 和异常文案，只有 ID、状态和异常类型。`LLMRouter` 那行 `novel_id=` 调用日志按规格接受。
8. **取消与写锁**
   - `verify/lock-root-cause.md` 的机制我认可：语句执行了但游标没取走，连接 `close()` 时走 `sqlite3_close_v2` 变成僵尸，事务要等最后一条语句被销毁时才回滚，这与 SQLite 的关闭语义一致。`07-fix-r3.md` 第一节说「提交、回滚、关闭被跳过」，确实不准确：`close()` 总会被调用，没有残留语句时会正常回滚。
   - 现在的保护在以下各种取消时机下都能收尾：语句执行中、结果没取走、提交中、连续取消两次、事件循环关停（关停时内层任务也会被取消，但 `except BaseException` 里会先回滚；在 `BEGIN` 或 `commit` 处被打断时没有残留语句，`close()` 会回滚或提交完成）。
   - 「操作本身抛异常的同时被取消」：事务能收尾，但取消会丢失，见可优化项 7。
   - 漏掉的写入点见 M1；只读路径见可优化项 8；接口语义的变化见可优化项 9；令牌认领被取消见可优化项 6。
   - R3 新增的四条用例在提交处设闸门，验证的是「取消要等事务提交完才生效」，复现不了写锁泄漏：在提交处被打断时没有残留语句，连接关闭照样释放锁。真正复现机制的是规格作者补的 `test_cancel_with_unconsumed_cursor_leaves_no_write_lock_during_cleanup`，它与 `zombie_probe.py` 等价，已经在正式测试里，不必再收。还需要补 M1 的分身路径用例。
9. **测试的证明力**：见 M4 和第 6 节。主要问题是计费性质只在免费模式下验证。没发现扫描空集的情况：带 `all(...)` 的断言前面都检查过非空或数量。
10. **白名单与文档**
    - 改动集合与 conftest 都合规。
    - 六份文档的新增内容与实现一致，没有本机路径（有用例检查）。
    - ARCHITECTURE 里「后台写库都带 run_token 与账号存在检查」，在 M1 修好之前不完全成立。
    - README 和隐私说明里关于 BYOK 不扣费的说法，见可优化项 5。
