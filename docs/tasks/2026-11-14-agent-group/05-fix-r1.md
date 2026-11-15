# 返修单 R1：多智能体讨论群第一期

依据仍是 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1）。首轮交付的门禁结果：改动范围、全量测试（8472 通过、0 跳过）、基线对照都过了；真实模型走查 30 项检查全过。本轮要修的是下面两类问题，其余不要动。

## 一、规矩

1. 只允许改：`backend/discuss/engine.py`、`backend/tests/test_discuss_*.py`（可以往已有的新测试文件里加用例，也可以新建 `test_discuss_` 开头的文件）、新报告 `docs/tasks/2026-11-14-agent-group/impl/report-r1.md`。其他文件一律不动，包括 `verify/` 下的脚本。
2. 已有新测试里的断言不许放宽或删除；只加不减。既有（非讨论群）测试一字不改。
3. 其余规矩同首轮派单（不 commit、不装依赖、Python 用 `backend/.venv/bin/python`、测试离线、不读 `.env`）。
4. 并行方式同首轮：用工作流（workflow 工具）的 `parallel()`，按文件不重叠拆分，agent 的任务说明自包含并写明「不得调用 subagent、subagent_fork、workflow」。建议拆成：engine（改 `engine.py` 并在 `test_discuss_engine.py` 里补 P1–P3 与 T2、T4–T8 的用例）、billing-tests（`test_discuss_billing.py`：T3、T9、T12）、api-tests（`test_discuss_api.py`：T1、T14–T16）、runner-tests（`test_discuss_runner.py`：T10、T11、T13、T17）。

## 二、实现问题（改 `backend/discuss/engine.py`）

**P1 同一位成员被派了多条任务时，后面的任务被丢掉。** 主持人在裁决或返工安排里可能给同一个 `role` 写两条 `assignments`。现在的代码会用同一个步骤键跑两遍 `investigate`，第二条任务的文字没有进入任何载荷（`tasks_by_role.setdefault`），查询和搜索结果还被重复合并。改法：拿到 `assignments` 后先按 `role` 合并，保持首次出现的顺序，同一成员的多条任务用「；」连接成一条；之后每位成员每轮只调研一次，载荷里的 `assignment` 是合并后的文字。合并对裁决（`30-decide-host`）与返工安排（`60-rework-host`）两个来源都生效。

**P2 重放时轮次号会倒退。** `run_rounds` 每次都从第 1 轮重放，循环里无条件 `update_group(round=r)`，会把已经到第 3 轮的群先写回 1、2 再写到 3，界面在继续与恢复时会看到轮次倒退。改法：只在 `r` 大于库里当前的 `round` 时才写。

**P3 返工要求的截断与规格不一致。** 规格 4.7 的硬上限是每条返工要求 300 字，代码里是 `[:160]`。改成 300。

每一项都要有用例：

- P1：返工安排对同一成员给两条任务时，下一轮该成员只有一个 `10-queries` 步骤，它的载荷 `assignment` 同时含两条任务的文字，搜索步骤没有重复；裁决为 `research` 时同理。
- P2：一个已经到第 2 轮的群继续运行时，记录 `update_group` 收到的 `round` 值，不出现小于 2 的写入。
- P3：验收给出一条 250 字的返工要求时，返工安排步骤的载荷里这条要求完整保留；400 字时截到 300。

## 三、测试缺口（变异存活）

规格作者做了变异测试：把实现的关键处逐一改坏，新测试应该变红。63 条里有 17 条改坏之后测试仍然全过，说明这些行为没有被测到。变异脚本是 `docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py`（只读，不要改），每条变异的原文与改法都在里面。

为下面每一条补用例，直到对应的变异被杀死。断言要针对行为本身，不要写成只对这一种改法有效的特例。

| 编号 | 变异 | 没被测到的行为 |
|---|---|---|
| T1 | E3 | 完成后按意见返工：群 `done` 之后插话并 `continue`，重放到上一轮收尾时走 `60-rework-host`（它的 `user_notes` 里有这条插话），再跑出新一版成果 |
| T2 | E7 | 主持人驳回（`reject`）的质疑不再下发；没被驳回的才出现在下一轮调研成员的 `objections_to_address` 里 |
| T3 | E10 | 分身步骤遇到草莓不足或预算超限时照常上抛，群进入对应的暂停原因，不被当成「分身这次没能发言」吞掉 |
| T4 | E11 | 返工轮里撰稿人的载荷 `previous_draft` 是上一版成果全文 |
| T5 | E14 | 第二轮调研时，笔记步骤的载荷 `your_previous_points` 是该成员第一轮的要点 |
| T6 | E17 | 笔记步骤的 `objections_to_address` 包含针对该成员和针对 `overall` 的质疑，不含针对别人的 |
| T7 | E18 | 撰稿人与验收人拿到的 `sources` 只含要点引用过的来源；登记过但没被任何要点引用的来源不在其中 |
| T8 | E24 | 有分身时，验收人与返工安排的载荷 `owner_view` 是分身看稿的结果；没有分身时为 `null` |
| T9 | B5 | 搜索的固定扣费也受预算约束：再扣一次搜索会超过预算时抛预算超限，群进入 `paused` / `budget`，余额不变 |
| T10 | N1 | 群已经有 `run_token` 时，再调 `start_group` 不会起第二个任务 |
| T11 | N2 | 库里有 `users` 表但没有 `discuss_groups` 表时，`recover_interrupted_groups()` 直接返回、不抛错（现在的用例用的是一个连 `users` 都没有的空库，区分不出来） |
| T12 | N6 | 计费打开时（`DEV_MODE=0`、调用器不是 `dry_run`），模型调用进行到一半被暂停或取消，预扣全部退回：群的 `reserved` 为 0，用户余额等于初始余额减去已结算的部分（现在「暂停后预扣清零」的断言是在免费模式下跑的，恒为真） |
| T13 | N7 | 自带模型不可用（调用器抛 `ByokUnavailable`）时群进入 `paused` / `byok_unavailable`，`last_error` 是规格写明的固定文案 |
| T14 | S6 | 群 `done` 且没有未读插话时 `continue` 返回 `409`；有未读插话时成功 |
| T15 | S10 | 还没有任何成果时 `accept` 返回 `409` |
| T16 | S11 | 开工时 `expected_revision` 与库里不符返回 `409`，群仍是 `awaiting_start` |
| T17 | T1 | 旧任务写不进去：令牌已经换掉（或账号已删除）之后，用旧令牌的 `DiscussStepStore` 发消息、改状态、存成果都不生效，库里没有新增或改动 |

自检：补完后运行

```
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> E3 E7 E10 E11 E14 E17 E18 E24 B5 N1 N2 N6 N7 S6 S10 S11 T1
```

脚本会把仓库克隆到那个新目录里改，不碰工作区。要求 17 条全部「杀死」。把脚本输出贴进报告，用完删除克隆目录。如果沙箱不允许克隆，在报告里说明，这一步留给规格作者做，但仍要逐条说明新用例为什么能区分对错。

## 四、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过。
2. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 新测试总数，0 失败、0 跳过。
3. `git status --porcelain --untracked-files=all` 与首轮交付相比，只多出或变动本单第一节第 1 条允许的文件。
4. 第三节的变异自检 17 条全部杀死。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-r1.md`，不写本机绝对路径：开头列拆分表；然后逐条写 P1–P3 改了什么、T1–T17 各自对应的测试函数名、验收四条的命令与输出摘要、未完成或需要人工确认的地方。
