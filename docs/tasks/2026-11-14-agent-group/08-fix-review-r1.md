# 复核返修单 第 1 轮：多智能体讨论群第一期

依据：`docs/tasks/2026-11-14-agent-group/02-spec.md` **v1.2**（开头新增了「v1.2 修订」一节，共 10 条，覆盖正文对应句子）和独立复核 `docs/tasks/2026-11-14-agent-group/04-review.md`。复核结论是不通过，4 条必须修复（M1–M4）规格作者都已独立复现，属实。本单把 4 条必须修复、v1.2 修订里需要改代码的条目、以及复核列出的测试缺口一次做完。

先读：`02-spec.md` 的「v1.2 修订」、`04-review.md` 第 3、4、5、6 节、`verify/lock-root-cause.md`。复核里的行号是它当时看到的，动手前自己核对。

## 一、规矩

1. 只允许改这些文件：
   - `backend/discuss/avatar.py`、`engine.py`、`service.py`、`runner.py`、`store.py`、`billing.py`、`roles.py`；
   - `backend/tests/test_discuss_*.py`；
   - 文档里引用隐私说明那段话的地方（只为第二节 H 条同步一句话）；
   - 新报告 `docs/tasks/2026-11-14-agent-group/impl/report-review-r1.md`。
2. 不许动：`backend/agent_store.py`、`backend/novel/`、`backend/tests/conftest.py`、其他任何模块；任务目录下的 `02-spec.md`、`04-review.md`、各返修单、`verify/` 整个目录；`tests/test_discuss_runner.py` 末尾「R3 门禁后由规格作者补充」那一段的两条用例（可以在它后面追加，不能改它）。
3. 已有用例的断言不许放宽或删除。只有三处例外，因为规格变了：
   - 第二节 C 条点名的两条用例，把子串断言改成更严格的整段比较；
   - 断言隐私说明原文的用例，改成新原文（H 条）；
   - 如果有用例断言「固定席位名字传空字符串返回 422」，改成 v1.2 第 6 条的新行为。
4. 不装依赖，不读 `.env`，不 commit / stash / checkout / reset，不访问外网，不调用真实模型。
5. 用工作流（workflow 工具）并行：在脚本里用 parallel() 同时运行多个 agent，按文件不重叠拆分，拆得越细越好；每个 agent 的任务说明自包含，并写明不得调用 subagent / subagent_fork / workflow。先并行改实现文件（一个文件只归一个 agent），实现改完再并行写测试（一个测试文件只归一个 agent）。agent 失败先读结果再决定，不盲目重派。报告开头列拆分表。
6. 你实测到的事实优先于本单的说法；不符就停下来在报告里说明，不要硬凑。只有影响「实现什么」的矛盾才停；怎么实现、怎么验证自己定并写明理由。任何情况不回滚已完成的工作。

## 二、要做的事

### A. 分身路径的取消保护（复核 M1，v1.2 第 2 条）

- `avatar.py` 里对 `agent_store.get_my_agent` 与 `agent_store.get_memory_snapshot` 的全部调用，改成在受保护任务里执行（`NovelBilling._drain(...)`，与 `store.run_write` 同一套保护）。
- `service.detail` 一次请求最多取一次分身名字，`_avatar_member` 复用这个结果。
- 全库搜索 `backend/discuss/` 里还有没有别的地方调用了「其他模块里会开写事务的函数」而没有保护，有就一并处理，并在报告里列出你查过的调用。
- 新用例两条（放 `tests/test_discuss_runner.py`，写法见复核第 6 节 B）：让 `FROM agents WHERE owner_username` 那条查询执行完、游标未取走时停住，取消调用方，在它的 `finally` 里用忙等待 0.2 秒的新连接执行 `BEGIN IMMEDIATE`，必须立刻成功。分别覆盖 `avatar.system_for` 与 `avatar.display_name`。
- 自检：去掉保护后两条都必须失败，贴输出。

### B. 「继续」不能跳过开工（复核 M2，v1.2 第 1 条）

- `service.resume`：这个群从未开工（`round == 0`）时回 `planning`，否则 `running`。
- 新用例：
  - 免费模式：带分身建群，brief 阻塞时暂停，再继续。断言最终停在 `awaiting_start`，库里没有任何 `r01/` 及以后的步骤和消息，brief 被重新调用（或留下跳过通知）；之后作者正常开工能跑完。
  - 付费模式（`DEV_MODE=0`，替换 `LLMRouter._single_real_call`）：brief 因余额不足停下，加余额后继续，停在 `awaiting_start`，余额减少量等于 `spent`。
- 自检：把判据改回 `plan_revision == 0`，新用例必须失败。

### C. 身份设定独占一行（复核 M3，v1.2 第 5 条）

- `engine._system`：提示词 + `"\n"` + 身份设定行 + 公共规则（JSON 步骤再接 JSON 规则）；没有身份设定时输出与现在逐字相同。
- 把 `test_host_identity_line_and_plan_edits` 与 `test_empty_persona_removes_identity_line` 里的子串断言改成对整段 system 的精确比较，至少覆盖一个 JSON 步骤（decide）和撰稿步骤。
- 自检：把换行去掉，用例必须失败。

### D. 付费路径的用例（复核 M4）

在 `tests/test_discuss_billing.py` 加四条（写法见复核第 6 节 D）：

1. 付费调用阻塞时 pause：接口一返回，`reserved == 0`，余额 = 初始值 − `spent`，状态 `paused/user`。
2. 付费调用阻塞时 delete：余额 = 初始值 − 删群前的 `spent`。
3. 付费跑到 `awaiting_user` 后 continue：之前 `status=ok` 的模型步骤不再被调用，余额减少量 = `spent`。
4. 旧令牌的 `DiscussBilling` 调用 `reserve` 与 `reserve_fixed`：都抛 `RunNoLongerActive`，余额、`reserved` 与步骤行都不变。

自检：复核第 6 节 A 的 X1、X4、X25、X26 四条变异，逐条确认由这些用例靠断言失败发现。

### E. 认领令牌后被取消（v1.2 第 3 条，复核可优化项 6）

- `runner.start_group`：认领令牌的事务结束之后、后台任务创建之前如果收到取消，先在受保护的事务里把刚认领的那个令牌清掉（只清自己认领的那个值），再把取消交还。
- 新用例（复现法见复核第 6 节 E 的 CLAIM_PROBE）：在认领事务的提交处设闸门，取消 `start_group`；之后库里令牌为空，`TASKS` 里没有这个群，写锁可立即拿到。
- 自检：去掉补偿后用例必须失败。

### F. 残留预扣（v1.2 第 4 条，复核可优化项 1、2）

- `start`、`resume`、`continue`：在 `runner.start_group` 之前先 `DiscussBilling(username, group_id).refund_reserved()`。
- `delete`：在删除各表行的同一个事务里，把这个群 `billing_status='reserved'` 的步骤的 `strawberries_reserved` 合计退回用户余额，再删行。
- 新用例（付费模式）：
  - 造一个「群已暂停、但留有一条 reserved 步骤、余额已被预扣」的状态，调用 resume：余额先恢复、那条步骤变成已退，之后正常运行，最终余额减少量 = `spent`。
  - 同样的状态直接 delete：余额恢复到预扣之前。
- 自检：分别去掉两处改动，对应用例必须失败。

### G. 名字与重名（v1.2 第 6、7 条，复核可优化项 13、14）

- 固定席位的名字传空字符串：清除自定义名字、恢复默认名，返回成功。
- 建群时 `members` 名字重复：`422`。
- 各一条用例。

### H. 两处小改（v1.2 第 9、10 条，复核可优化项 11、5）

- `run_rounds` 开头内存里的 `draft` 初始化为空串。不要求新用例；确认现有重放与续跑用例仍通过。
- 隐私说明末尾加一句「联网搜索按次另扣草莓，与成员用哪个模型无关。」（紧接在「平台模型按用量扣草莓，选「我的模型」不扣。」之后）。全库搜索这段话的所有出现处逐一同步，报告里列出改了哪些位置。

### I. 测试缺口（复核第 4 节「测试缺口」与第 6 节 A）

下面每一条都是「把代码改坏后 156 条用例照样全过」。代码现在是对的，只补用例。每条变异都要有至少一条用例靠断言失败发现它；变异的具体改法看复核第 6 节 A 的表，自己在系统临时目录的克隆里改、跑、还原。

| 编号 | 要守住的行为 |
|---|---|
| X12 | 返工载荷带上引用问题 |
| X15 | 撰稿载荷带上分身提供的背景（`owner_context`） |
| X34 | 事实截到 160 字 |
| X35 | 笔记载荷只带该成员自己的来源，不带全部来源 |
| X14 | 并行步骤里一个失败时，其余步骤先被取消并收尾，之后才抛出 |
| X17 | 恢复模式下步骤失败记 `paused/server_restart_failed` |
| X18 | 恢复模式下意外异常记 `paused/server_restart_failed`，不是 `failed` |
| X19 | 平时步骤失败记 `paused/step_failed`，不是 `failed/error` |
| X20 | 全站并发上限 `FIONA_DISCUSS_MAX_RUNNING` 生效 |
| X22 | 补充材料做危机检查 |
| X30 | 详情的 `after` 参数生效 |
| X31 | 开工时已有别的群在跑则 `409` |
| X32 | 继续时已有别的群在跑则 `409` |
| X33 | 追加轮数时已有别的群在跑则 `409` |
| X27 | 群列表最多 50 个 |
| X28 | 删成员时清掉它的模型设置 |
| X37 | 分身默认模型：启用了自带模型就用自带模型 |
| X39 | 新增自定义成员跳过已用过的代号 |
| X44 | 身份设定超过 300 字被拒 |

X40 由 B 条的用例覆盖。复核表里标成「冗余」或「分支走不到」的 10 条（X3、X5、X6、X8、X13、X16、X21、X36、X41、X42）不用管。

## 三、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过；连跑 5 次都如此，贴 5 次的结尾行。
2. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 讨论群用例总数，0 失败、0 跳过。
3. 自检表：A–G 各条的「去掉改动后新用例失败」，以及 D、I 两条里每个 X 编号「改坏后由哪条用例靠断言失败发现」，一行一条，写明用例名与失败摘要（必须是 `failed`，不能是 `error` 或超时）。
4. `git status --porcelain --untracked-files=all`：相对本单派出时，只多出报告，以及第一节第 1 条允许的文件有变动。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-review-r1.md`，不写本机绝对路径：拆分表；A–I 逐条做了什么、改了哪些函数；自检表；验收四条的命令与输出摘要；没做完或需要人工确认的地方。
