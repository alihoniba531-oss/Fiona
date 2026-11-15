# 独立复核（第 3 轮）：多智能体讨论群第一期

## 复核对象与做法

**对象**：第 2 轮复核之后的状态，加上 `10-fix-review-r2.md` 的返修（A–D）。

**依据**：
- `02-spec.md` v1.2，重点是改过的第 1、2、4 条和新增的第 11、12 条；
- 我上一轮的报告 `04-review-r2.md`；
- 本轮的差异文件。

实现方报告 `impl/report-review-r2.md` 只当线索。

**改动范围**：我把这份副本与上一轮的复核副本逐文件比对过。
- 产品代码只有 `backend/discuss/engine.py` 和 `service.py` 有变化。`avatar.py`、`runner.py`、`store.py`、`billing.py`、`routers/discuss.py`、`agent_store.py`、`database.py`、`main.py`、`conftest.py`、`backend/novel/` 和三份文档都没变。
- 四个测试文件只有追加，没有删除或修改原有的行。

**实验环境**：所有改坏代码、加探针的实验都在系统临时目录下的 APFS 克隆里做，做完已删。复核副本里除本文件外没有任何改动：开始和结束时都对 `git diff 859e2c5` 和全部未跟踪文件做了哈希，两次一致。

---

## 1. 结论

**通过。** M5 已经修好。本轮的新代码里没有查出必须修复的缺陷。

本轮新代码有两处。

**分身步骤的取消判断**（`engine._avatar_try`）：
- 只在任务确实收到过取消时，才把普通异常转成取消；没有取消时，分身出错仍然照原样跳过、继续流程。
- `_AVATAR_RAISE` 里那四类异常排在新判断之前，处理方式和原来一样。

**`accept` 和 `close` 新加的退残留预扣**：
- 没有多退或重复退：和其他退款路径一样，只退仍处于 reserved 的行，而且在写锁下串行。
- 退给的是本人。
- 对已经是 closed 的群重复调用 `close`，只退一次。

另外有一处并发窗口和几处小缺口，列在第 4 节，都不阻断。

## 2. M5 的核验

### 第 2 轮的现象已经消失

探针写法与第 2 轮的 P9、P10 相同：
- 把 `agent_store.get_memory_snapshot` 换成「第一次调用时阻塞到放行，然后抛 `sqlite3.OperationalError`」的版本；
- 阻塞期间调用 `service.pause`；
- 50 毫秒后放行。

| 场景 | 当前代码 | 去掉本轮的取消判断（即 V11） |
|---|---|---|
| P9 立项阶段（brief） | 暂停返回 `('paused','user')`；消息只有 `plan`；任务退出后令牌为空，`reserved == 0`，写锁空闲 | 返回 `('awaiting_start', None)`，多了一条跳过通知 |
| P9 开工后（第 1 轮的 view） | 返回 `('paused','user', round=1)`；没有 `verdict`；令牌为空，`reserved == 0` | 返回 `('done','accepted')`，后面整轮都跑完了 |
| P10 付费，第 1 轮的 view | 阻塞时 spent 31，暂停后仍是 31；`reserved == 0`；暂停之后没有任何新结算的步骤；余额 = 10000 − 31 | 暂停后 spent 31 → 34，`r01/50-accept-acceptor` 在暂停之后才结算 |

右栏与第 2 轮记录的现象逐项相同。所以这一处判断就是修好 M5 的那一处改动。

### 新用例确实能发现改坏

我用自己的变异脚本，不带 `-x` 跑了全部讨论群用例：

| 改坏方式 | 结果 |
|---|---|
| V11：取消判断改成 `if False:` | 3 条失败：`test_pause_during_avatar_memory_error_keeps_cancellation[planning]`、`[running]`、`test_pause_during_paid_avatar_memory_error_keeps_spent` |
| Z1：去掉 `cancelling()` 条件，所有分身错误都转成取消 | 2 条失败：`test_avatar_failure_becomes_notice_and_flow_continues`、付费 M5 用例 |

Z1 被杀死，说明「没有取消时仍然跳过」这条行为本来就有用例守着。

### 判断本身有没有副作用

逐项核对：

1. **`_AVATAR_RAISE` 的四类异常不受影响。** `except _AVATAR_RAISE: raise` 排在新判断之前。
   - 有取消在等、读库抛 `InsufficientStrawberries` 时（Q2），走的仍是原来的路径：暂停接口返回 `('paused','insufficient_strawberries')`，消息只有 `plan`。这与本轮改动之前完全一样。
2. **没有取消时，行为与原来一致。** 读库直接抛错、不调用暂停（Q1，立项和开工后两种阶段）：都照常留下分身的跳过通知，流程继续（分别停在 `awaiting_start`、跑到 `done`）。
3. **`cancelling()` 只会因为有人真要停这个任务才大于 0。**
   - 两处 `_avatar_try` 都在后台任务的主协程里顺序执行，不在 `gather` 的子任务里，所以 `current_task()` 就是那个后台任务。
   - 后台任务调用链上没有吞掉取消后继续跑的代码：`_drain`、计费、调用器的 `except BaseException` 都会重新抛出。
   - `novel/llm_router.py` 里没有 `asyncio.timeout` 或 `wait_for`，所以不会出现「超时临时把计数加 1」的情况。
   - 能给后台任务发取消的只有 `cancel_group`：它被暂停、删群、删号、关停和重启恢复调用。这些场合把普通异常转成取消，正是想要的结果。
4. **收尾正常。** 转成的 `CancelledError` 在 `_run` 里原样上抛，`finally` 照常退款、清令牌、清 `WORKING`。`_call` 的 `finally` 也会清掉「正在发言」的标记。用 `from error` 串上原异常，不会把异常文字写进日志或库。
5. **Python 版本没问题。** `Task.cancelling()` 需要 3.11 及以上。仓库里 `services/exchange_service.py` 已经在用它，开发环境是 3.14。

## 3. 必须修复项

没有。

## 4. 可优化项（不阻断）

1. **`accept` 晚到的无令牌退款，可能退掉新一轮的在途预扣（Q3）。**
   - **构造**：
     1. 群跑到 `awaiting_user`；
     2. `accept` 的状态事务提交（改成 `done`）后，在它的退款之前停住；
     3. 这时插话，调用 `continue`，新任务在返工步骤上预扣了 9 颗并阻塞；
     4. 放行 `accept` 的退款。
   - **结果**：
     - 那 9 颗被退回；
     - 返工步骤结算时发现该行已是 refunded，没有扣费，也没有写步骤缓存（行停在 `interrupted/refunded`），而这一轮已经用了它的结果，接着跑到了第 2 轮；
     - 最终余额 9955 = 10000 − spent 45，守恒，没有多退。
   - **影响**：用户少付了一次调用的钱，平台承担。这一步没有缓存，以后重放会重跑它，重跑结果可能与当初用过的不同。
   - **触发难度**：`accept` 的退款要在「提交完 → 退款」这几毫秒里被挡住，同时同一用户还要插话并点继续。界面上基本到不了。
   - **相关但不同**：`close` 之后群是终态，不会再起任务，所以没有这个窗口。
   - **建议**：把退残留预扣的三条 SQL 并进各自的状态事务。`start`、`resume`、`continue` 也一样，第 2 轮我提过同样的建议。这样窗口就没有了，还能消除下一条的问题。
2. **状态先改、退款后做，退款失败后不好恢复。**
   - `accept` 的退款如果失败（例如 5 秒写锁超时），接口返回 500，但状态已经是 `done`；再点一次会因为状态不对而返回 409，残留预扣要等追加轮数或删群时才退。
   - `close` 有「已是 closed 时也退一次」的分支，重复调用就能补上，没有这个问题。
   - 并进同一事务即可解决。
3. **「已是 closed 时也退」这条分支没有用例。** 把它去掉（Z2），200 条用例照样全过。
   - 我的探针 Q4 能发现它：已经 closed、留有 8 颗残留预扣的群，第一次 `close` 后余额从 9987 回到 9995，第二次 `close` 仍是 9995。
   - 建议照 Q4 补一条用例。
4. **规格 v1.2 第 2 条「必须把取消交还」，只在分身步骤做到了。**
   - 有取消在等时，分身步骤以外的受保护写库如果以普通异常结束（Q5：让写方案消息的那次写库阻塞后报错，期间暂停），任务会落到 runner 的 `except Exception`，记成 `failed/error`。暂停接口随后返回 `('failed','error')`，而不是 `paused/user`。
   - 同样，有取消在等、分身读库抛余额不足时，记成 `paused/insufficient_strawberries`（Q2）。
   - 这两种情况任务都会停下，不会接着跑、也不会多扣费，只是停下的原因与作者的操作不符。
   - 建议：runner 的 `except` 各分支先判断 `current_task().cancelling()`，有取消就原样上抛，交给 `pause` 的事务写 `paused/user`。或者规格作者把第 2 条明确限定在「不得继续往下跑」。
5. **规格 v1.2 第 4 条「保证群停下来之后 `reserved == 0`」说得过满。**
   - 进程在 `_pause` 提交和收尾退款之间被杀，群停在 `paused`，残留预扣要等作者下一次继续、接受、结束或删群时才退。重启恢复只处理 `planning` 和 `running` 的群。
   - 改状态和退款分两步做，中间崩溃也会留下残留。
   - 建议改成「作者对这个群做下一次操作时退回」，或者在启动时对所有不在跑、但 `reserved_strawberries > 0` 的群退一次。
6. **Y5 的用例查的是 `roles.PRIVACY_NOTICE`，不是目录接口返回的 `notice`。** 目录接口直接用这个常量，目前等价；但如果以后接口改用别的字符串，这条用例发现不了。可以在 `test_discuss_api` 里补一行断言。
7. **文案（C 条）没有对应用例。** 全库（实现、用例、三份文档）已经没有旧文案「固定席位的名字需要 1–12 字」，新文案只在 `service.py:189` 出现一次。不重要。

## 5. 给实现方的修改指令

没有必须修复项，本轮不需要返修。

如果规格作者决定采纳第 4 节的建议，按优先级：
1. 第 1、2 条：把退残留预扣并进状态事务；
2. 第 3 条：补「已是 closed 时也退」的用例；
3. 第 4 条：runner 遇到已有取消时原样上抛。

可以合成一张小单。

## 6. 探针与变异实验

命令都从 `backend/` 执行，前面加 `NO_PROXY=… no_proxy=…`。

### 6.1 门禁复跑

- 复核副本里 `tests/test_discuss_*.py`：`200 passed`，0 跳过，约 18 秒。
- 全量没重跑：本轮只改了两个讨论群文件，没有具体怀疑。8352 + 200 = 8552，与派单方的数字对得上。

### 6.2 派单方变异脚本复跑（14 条）

命令：`verify/mut_discuss.py <新克隆> <结果> V11 V12 V13 Y1 Y3 Y5 Y6 E9 E10 V1 V2 V3 V6 V8`

- 开头和结尾的正控都是 `200 passed`。
- 14 条全部杀死，都是 `1 failed`，没有一条是靠报错或超时杀死的。
- V1–V3、V6、V8 是前几轮修好的点，这次一起复跑，确认没有被本轮改动带坏。

### 6.3 我加的变异（不带 `-x`，跑全部讨论群用例）

| 编号 | 改法 | 结果 |
|---|---|---|
| V11 | 取消判断改成 `if False:` | 杀死：M5 的三条新用例 |
| Z1 | 去掉 `cancelling()` 条件 | 杀死：`test_avatar_failure_becomes_notice_and_flow_continues` 和付费 M5 用例 |
| Z2 | 去掉 `close` 在已是 closed 时的退款 | **存活**（第 4 节第 3 条） |
| V12 | `accept` 不退 | 杀死：`test_accept_refunds_stale_reservation` |
| V13 | `close` 不退 | 杀死：`test_close_refunds_stale_reservation` |

### 6.4 探针

都放在克隆里的 `tests/test_discuss_zz_probe3.py`，复用 `test_discuss_runner` 与 `test_discuss_billing` 的夹具。

| 编号 | 做法 | 当前代码 | 对照 |
|---|---|---|---|
| P9 | 分身读记忆阻塞 → 暂停 → 放行后报错，分立项和开工后两种阶段 | 两种阶段都是 `paused/user`，没有跳过通知或 `verdict`，令牌为空，`reserved == 0`，写锁空闲 | V11 下：`awaiting_start` / `done accepted` |
| P10 | P9 的付费版（第 1 轮的 view） | spent 31 → 31，暂停后没有新结算的步骤 | V11 下：31 → 34，accept 在暂停后结算 |
| Q1 | 读记忆报错，不暂停 | 两种阶段都留下跳过通知，流程继续 | — |
| Q2 | 读记忆阻塞后抛余额不足，期间暂停 | `paused/insufficient_strawberries`，与改动之前同一路径 | — |
| Q3 | `accept` 的退款挡在提交之后，期间插话并继续，新任务预扣 9 颗并阻塞 | 9 颗被退回，那一步不扣费、不缓存，最终守恒（9955 = 10000 − 45） | — |
| Q4 | 已 closed 且留有 8 颗残留预扣的群，连续 `close` 两次 | 9987 → 9995 → 9995，只退一次 | Z2 下第一次 `close` 不退 |
| Q5 | 写方案消息的受保护写库阻塞后报错，期间暂停 | `failed/error`（第 4 节第 4 条） | — |

P9 的写法与第 2 轮报告第 6 节相同。Q3 的关键：
- 把 `DiscussBilling.refund_reserved` 换成「第一次调用先等一个事件，再调原函数」，这第一次就是 `accept` 发起的；
- 等它停住后，调用 `discuss_store.post_user_note` 和 `service.continue_group`；
- `continue_group` 里替换后的 `_single_real_call` 阻塞住，形成在途预扣；
- 再放行 `accept`。
