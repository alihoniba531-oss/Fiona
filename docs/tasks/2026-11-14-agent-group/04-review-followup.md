# 独立复核：验收后小单「三条收紧」

**复核对象**：基线 `19e4bd1`，加上副本里 `git diff` 能看到的全部改动。

**依据**：
- 小单 `11-followup-tighten.md`；
- `02-spec.md`「v1.2 修订」新增的第 13、14 条；
- 我第 3 轮报告 `04-review-r3.md` 第 4、6 节。

实现方报告 `impl/report-followup.md` 只当线索。

**做法**：
- 所有改坏代码、加探针的实验都在系统临时目录下的 APFS 克隆里做，做完已删。
- 复核副本里除本文件外没有任何改动：开始和结束时都对 `git diff` 和全部未跟踪文件做了哈希，两次一致。

---

## 1. 结论

**通过。** 没有必须修复项。

**A：退残留预扣并进状态事务**
- 新函数 `refund_reserved_on_connection` 与原来的 `refund_reserved` 行为等价。
- 五个接口都在各自的状态事务里退款；事务失败时，状态和预扣一起回滚。
- 没有多退或重复退，也不会与在跑的任务或 `cancel_group` 冲突。
- 第 3 轮 Q3 的那个窗口已经消除，实测确认。

**B：取消优先于同时发生的失败**
- 没有取消时，各类异常的停止原因与原来一一相同，恢复模式的映射也不变。
- 有取消时，一律把取消交还给发起方。`RunNoLongerActive` 和 `finally` 收尾都没变。
- 第 3 轮 Q2、Q5 的现象都变成了 `paused/user`。
- 服务关停时，群保持原状态等重启恢复，与规格第 14 条一致。

**用例缺口（不阻断）**：有两处已经写进规格或小单的行为，把实现改坏后用例照样全过，见第 4 节第 1、2 条。

## 2. 逐条核验

### A. 退残留预扣并进状态事务

1. **与原来等价**：`store.refund_reserved_on_connection` 和原来的 `DiscussBilling._refund_reserved_transaction` 做的是同一件事：
   - 只合计本群、本人、`billing_status='reserved'` 的行；
   - 把这个金额加回本人余额；
   - 群的 `reserved_strawberries` 归零；
   - 这些行标成 `refunded/interrupted`；
   - 返回金额（整数）。

   唯一的差别：金额为 0 时不再执行那条 `+0` 的余额更新，没有可观察的影响。
   - 计数用 `row[0]`，带不带 `Row` 工厂的连接都能用。
   - 原函数里那行 `row_factory = aiosqlite.Row` 只给被替换掉的那条查询用，删掉没有影响。
2. **两个复用点行为不变**：
   - `DiscussBilling._refund_reserved_transaction` 仍在自己的锁和 `BEGIN IMMEDIATE` 下调用这个函数，再提交。
   - `delete_group` 改成调用它之后，除了退余额，还会先把群和步骤行改一下，紧接着这些行就在同一事务里删掉，所以结果不变。
   - V8、V16 以及我加的 F11（不把群的预扣归零）、F12（合计时不限 reserved）都被杀死。
3. **五个接口都在状态事务里退款**：
   - `start`、`resume`、`continue_group`、`accept`、`close`（未结束的分支），都在 `update_group_on_connection` 之后、同一个 `run_write` 里调用它。
   - 已经 closed 的分支单独开一个 `run_write` 只做退款。
   - 事务之后那次单独的 `refund_reserved()` 全部去掉了。`service.py` 里已经没有别的退款调用，`runner` 里两处（`cancel_group`、`_cleanup`）没动。
4. **事务失败时状态与预扣都不变**：
   - 退款函数抛错，或者后面的检查失败（例如 `start` 的「已有别的群在跑」检查排在退款之后），都会让 `run_write` 整体回滚，`start_group` 也不会被调用。
   - 有专门用例的是 `start` 和 `accept`：把这两处的退款挪回事务之外（V14、F5），会被 `test_start_refund_failure_rolls_back_state_and_tasks` 和 `test_accept_refund_failure_rolls_back_state` 杀死。
   - `resume`、`continue`、`close` 的代码结构相同，我读过，也是对的；但没有用例守着，见第 4 节第 1 条。
5. **不会多退或重复退，不会与在跑的任务冲突**：
   - 所有退款路径（状态事务、`cancel_group`、任务收尾、结算或退单步、删群）都在 `BEGIN IMMEDIATE` 下串行执行，而且都只处理仍是 reserved 的行，所以同一笔钱只会退一次。
   - 能在状态事务里退款的时刻，这个群不会有持有有效令牌的任务：
     - 改成非 `planning`/`running` 的状态会自动清令牌；
     - `resume` 和 `continue` 的事务还会显式清令牌；
     - 新任务要等这个事务提交后才认领令牌。
   - 旧任务即使还在收尾，新任务的 `start_group` 也会先等它结束。
6. **第 3 轮 Q3 的窗口已经消除（Q3b）**：
   - 我用提交闸门把 `accept` 的事务挡在提交之前，这时它已经拿着写锁，再同时调用 `continue`。
   - `continue` 只能排在后面：等 `accept` 提交后，它看到状态是 `done`，按返工处理。
   - 新一轮在返工步骤上预扣了 9 颗并阻塞，这 9 颗没有被 `accept` 退掉；放行后，返工步骤是 `ok/settled`（有缓存）。
   - 最终余额 9952 = 10000 − spent 48，守恒。
   - 第 3 轮同样的构造下，这一步会被误退，变成 `interrupted/refunded`，也没有缓存。
7. **已 closed 的群再次 `close`**：退一次之后余额不再变化。V13a 被 `test_closed_group_close_refunds_once` 杀死，第 3 轮记录的 Z2 缺口已经补上。

### B. 取消优先于同时发生的失败

1. **没有取消时，停止原因一一相同**：
   - 原来是六个 `except`，现在合成一个 `except Exception`，内部用 `isinstance` 判断，顺序与原来相同：余额不足 → 预算不够 → 自带模型不可用 → 搜索不可用 → 步骤失败 → 其他异常。
   - 我查了这几个异常类的继承关系：`DiscussBudgetExceeded` 继承 `NovelBudgetExceeded`；`ByokUnavailable` 继承 `ConfigurationError` 和 `ValueError`；其余都直接继承 `RuntimeError`。被映射的类之间没有父子关系，所以判断顺序不影响结果。
   - 一个没被映射的 `NovelBudgetExceeded` 仍落到「其他异常」，与原来相同。
   - 恢复模式（`recovering`）的两处映射，以及「其他异常」那条只记类型名的日志，都原样保留。
   - 派单方的 N3、N4、N5、N7、X17、X18、X19 我复跑了，全部杀死。
   - 我的探针 R2 也确认：非恢复模式下意外异常记 `failed/error`，恢复模式下记 `paused/server_restart_failed`。
2. **有取消时，都把取消交还**：
   - 判断放在 `except Exception` 的最前面，只要 `cancelling()` 大于 0 就 `raise CancelledError() from error`，不写任何停止原因。
   - `CancelledError` 不是 `Exception` 的子类，仍由前面的 `except asyncio.CancelledError: raise` 处理。
   - `RunNoLongerActive` 仍由它自己的分支安静吞掉，不走取消判断，与规格第 14 条「照旧安静退出」一致。
   - `finally` 里的 `_cleanup` 和清 `WORKING` 没变。
   - `cancelling()` 只会在 `cancel_group` 或关停时取消任务才大于 0：讨论群和调用器里都没有 `wait_for` 或 `asyncio.timeout` 这类会临时改动取消计数的写法。
3. **第 3 轮的两个现象**：
   - Q2（分身读库阻塞后抛余额不足，期间暂停）：从 `paused/insufficient_strawberries` 变成 `paused/user`，令牌为空。
   - Q5（写方案消息的受保护写库阻塞后报错，期间暂停）：从 `failed/error` 变成 `paused/user`，令牌为空，写锁空闲。
4. **服务关停（R1）**：在 Q5 的同样时机调用 `shutdown_discuss_tasks()`，群保持 `planning`，令牌为空，没有写停止原因，下次启动时会被重启恢复接走。修改之前，这种情况会记成 `failed/error`，重启后不会被恢复。
5. **新用例能发现改坏**：把取消判断改成 `if False:`（V15，我的 F15 同理），`test_pause_during_protected_write_error_keeps_paused` 和 `test_pause_during_avatar_insufficient_keeps_paused` 都会失败。

### C. 目录接口 `notice` 的用例

`test_catalog_notice_ends_with_search_fee_sentence` 通过真实的 `GET /discuss/catalog` 断言 `notice` 的结尾，补上了第 3 轮第 4 节第 6 点。

### 规格第 13、14 条

- **第 13 条**：实现与它一致。
  - 第 13 条明说覆盖第 4 条「改状态之后也退一次」的做法；但第 4 条开头那句「`start`、`resume`、`continue` 在启动后台任务之前先退还……（`DiscussBilling.refund_reserved`）」字面上仍写着单独调用。第 13 条本身已经说清这三个接口也改了，只是覆盖范围的那句话没把这一句点名，读起来有一点歧义。建议改成「覆盖第 4 条的前两句」。
- **第 14 条**：实现与它一致，包括「关停时保持原状态」和 `RunNoLongerActive` 照旧安静退出。第 2 条末尾的「已知局限」已经由第 14 条明说补上，不矛盾。

## 3. 必须修复项

没有。

## 4. 可优化项（不阻断）

1. **`resume`、`continue_group`、`close` 的原子性没有用例。** 规格第 13 条对五个接口都要求「事务失败时状态与预扣都不变」，小单只要求至少覆盖 `start` 和 `accept`。
   - 我把这三处的退款分别挪回事务之外（F1、F2、F3），206 条用例照样全过：已有的 `*_refunds_stale_reservation*` 用例只观察到「启动后台任务前已退」或「最终已退」，看不出退款是不是和状态在同一个事务里。
   - 建议照 `test_start_refund_failure_rolls_back_state_and_tasks` 的写法补三条，或者把它参数化成五个接口。
2. **非恢复模式下「其他异常」记 `failed/error` 这条映射没有用例。**
   - 把它改成 `paused/step_failed`（F8），206 条照样全过。这是早就存在的缺口：前几轮只测了恢复模式（X18）和步骤失败（X19）。
   - 本轮 B 正好重写了这一段，建议补一条：让 `engine.run_planning` 抛一个普通异常，断言 `failed/error`（写法见我的探针 R2）。
3. **规格第 13 条覆盖范围的措辞**：见第 2 节最后一部分，只是文字问题。
4. **已 closed 的群每次再点 `close` 都会刷新 `updated_at`。** 退款那条 SQL 会写群行的 `updated_at`，即使没有可退的钱，所以重复点 `close` 会让这个群在列表里排到前面。原来单独调用退款时也这样，不是本轮引入的，只顺带记一下。可以改成金额为 0 时不写群行。

## 5. 探针与变异实验

命令都从 `backend/` 执行，前面加 `NO_PROXY=… no_proxy=…`。

### 5.1 门禁复跑

- 克隆里 `tests/test_discuss_*.py`：`206 passed`，0 跳过。
- 全量没重跑，派单方已说明会在机器空闲时重跑；那条书斋的失败用例所在文件自基线以来没有改动。
- 四个测试文件的 diff 只有新增行，没有删除行。

### 5.2 派单方变异脚本复跑（17 条）

命令：`verify/mut_discuss.py <新克隆> <结果> V7a V7b V7c V8 V12 V13 V13a V14 V15 V16 N3 N4 N5 N7 X17 X18 X19`

- 开头和结尾的正控都是 `206 passed`。
- 17 条全部杀死，都是 `1 failed`，没有一条是靠报错或超时杀死的。

### 5.3 我加的变异（不带 `-x`，跑全部讨论群用例）

| 编号 | 改法 | 结果 |
|---|---|---|
| F1 | `resume` 的退款挪回事务之外 | **存活**（第 4 节第 1 条） |
| F2 | `continue_group` 同上 | **存活** |
| F3 | `close`（未结束的分支）同上 | **存活** |
| F5 | `accept` 同上 | 杀死：`test_accept_refund_failure_rolls_back_state` |
| F8 | 非恢复模式下「其他异常」记成 `step_failed` | **存活**（第 4 节第 2 条） |
| F11 | 退款时不把群的 `reserved_strawberries` 归零 | 杀死：7 条，包括五条 `*_refunds_stale_reservation*` 和 `test_refund_reserved_returns_all_open_reservations` |
| F12 | 退款合计时不限 `billing_status='reserved'` | 杀死：18 条，包括付费续跑、暂停、删群等 |
| F15 | 取消判断改成 `if False:` | 杀死：B 的两条新用例 |

### 5.4 探针

都放在克隆里的 `tests/test_discuss_zz_probefu.py`，复用 `test_discuss_runner` 与 `test_discuss_billing` 的夹具。

| 编号 | 做法 | 结果 |
|---|---|---|
| Q2 | 分身读私有记忆阻塞后抛余额不足，期间暂停 | `paused/user`，消息只有 `plan`，令牌为空 |
| Q5 | 写方案消息的受保护写库阻塞后抛 `sqlite3.OperationalError`，期间暂停 | `paused/user`，令牌为空，写锁空闲 |
| R1 | 同 Q5 的时机，改为调用 `shutdown_discuss_tasks()` | 群保持 `planning`，没有写停止原因，令牌为空 |
| R2 | 没有取消，`engine.run_planning` 直接抛普通异常；分非恢复和恢复两种模式 | `failed/error`；`paused/server_restart_failed` |
| Q3b | 用提交闸门挡住 `accept` 的事务，同时调用 `continue`；新一轮在返工步骤上预扣并阻塞 | 在途预扣 9 颗没有被误退；返工步骤 `ok/settled`；余额 9952 = 10000 − 48 |
