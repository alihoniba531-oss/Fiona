# 独立复核（第 2 轮）：多智能体讨论群第一期

复核对象：基线 `859e2c5` + 全部待审改动（含 `08-fix-review-r1.md` 返修与 `09-fix-review-r1b.md` 补单）。依据：`02-spec.md` v1.2、第 1 轮复核 `04-review.md`、本轮差异文件。实现方的两份报告只当线索用。

所有改坏代码、加探针的实验都在系统临时目录下的 APFS 克隆里做，做完已删。复核副本里除本文件外没有任何改动（开始和结束时对 `git diff 859e2c5` 与全部未跟踪文件做了哈希比对，一致）。

---

## 1. 结论

**不通过。** M1–M4 四条都已修好；本轮新代码里查出 1 条必须修复：

| 编号 | 一句话 |
|---|---|
| M5 | M1 的修法把分身两次读库包进了 `NovelBilling._drain`，而 `_drain` 在「调用方已被取消、内层又抛了普通异常」时会把取消吞掉、只抛内层异常；`engine._avatar_try` 又会吞掉普通异常。两者叠加后，作者点暂停可能被无视：暂停接口一直等到群把后面的步骤跑完，返回 200 但状态是 `done` 或 `awaiting_start`，暂停之后的付费步骤照样扣费。注入故障后可以稳定复现；把本轮的 `_drain` 去掉，同一探针下暂停正常。 |

M5 的触发需要「分身读库报错」和「暂停」恰好同时发生。典型情形是写锁被别处占住超过 5 秒、`BEGIN IMMEDIATE` 超时报 `database is locked`，正常运行时概率很低。但它是本轮改动引入的新路径，后果是错误扣费和状态错乱，所以按规矩算必须修复。改法很小（见第 5 节），我在克隆里验证过：改后探针通过，讨论群 191 条用例全过。

其余方面：

- **认领补偿、残留预扣退款、删群退款**：查了多退、重复退、退错人，以及与并发任务、`cancel_group` 的冲突，没有发现问题（第 3 节、第 6 节 P3–P5、P8）。
- **`resume` 的新判据**：在各种停下的时机下都对（第 2 节 M2）。
- **名字清除、建群重名、详情只取一次分身名、隐私说明**：都与 v1.2 一致。缺口只在测试上（第 4 节）。

## 2. M1–M4 逐条核验

### M1 分身路径的取消保护：已修好

- **代码**：`avatar.py:25-26` 与 `:75` 的三处调用都改成了 `await NovelBilling._drain(...)`。`service.detail` 一次请求最多调一次 `avatar.display_name`（`service.py:527-530`），`_avatar_member` 复用这个结果。全 `discuss/` 里调用其他模块写事务函数的地方只有这三处：`ByokBridge.describe` 只读，`database._apply_daily_refill` 在计费事务内部。
- **用户路径上的复现（P1）**：
  - 设置：带分身建群，钩住 `aiosqlite.Connection._execute`，让后台 brief 步骤里 `FROM agents WHERE owner_username` 那条查询执行完、游标没取走时停住；这时调用 `service.pause`，0.1 秒后放行。
  - 当前代码：暂停 0.112 秒返回，状态 `('paused','user', run_token=None)`，之后新连接 0.2 秒内拿得到写锁。
  - 对照：只把 `avatar.py` 的 `_drain` 去掉，同一探针下 `sqlite3.OperationalError: database is locked`。日志里任务收尾的退款和清令牌都失败了（`refund_failed`、`token_clear_failed`），耗时 17 秒。这正是第 1 轮描述的现象。
- **新用例的证明力**：派单方变异脚本的 V1、V2、V3 我复跑了，都靠断言失败杀死。`zombie_probe.py` 复跑输出 `write_interrupted_by_cancel=False lock_in_cleanup=free`。
- **遗留**：这个修法本身引出 M5。

### M2 「继续」不能跳过开工：已修好

- **代码**：`service.py:829` 改为 `status = "planning" if round == 0 else "running"`。
- **第 1 轮探针 C 的复现（P6）**：带分身，brief 阻塞时暂停，再继续。
  - 状态轨迹：`while_brief=('planning', plan_revision=1, round=0)` → `paused=('paused','user',1,0)` → `after_resume=('awaiting_start', round=0, output_version=0)`。
  - brief 被重新调用（2 次），没有任何 r01 及以后的调用。
  - 修之前第 1 轮记录的是 `('done','accepted',1,1)`。
- **其他停下时机，逐一核对**：
  - 方案写入之前停下：`round=0` → `planning`，对。
  - brief 期间停下：见上，对。
  - `awaiting_start`：不能暂停，不涉及。
  - 已开工但第 1 轮还没开始就停下（P2）：用全站并发上限把任务卡在等槽位，此时状态 `running`、`round=0`；暂停后继续，回到 `awaiting_start`；brief 已有缓存，不再调用；没有 r01 调用；作者再点开工后正常跑完。这正是 v1.2 第 1 条明说可以接受的副作用。
  - 跑到 `round >= 1` 之后停下：回 `running`，对。
  - `failed` 的两种情形：`round=0` 回 `planning`，`round>=1` 回 `running`，对。
  - 重启恢复不经过 `resume`，不受影响。
  - `continue` 只能从 `awaiting_user` 或 `done` 进入，这时 `round` 一定 `>= 1`，不受影响。
- **新用例的证明力**：
  - V4（判据改回 `plan_revision`）由免费和付费两条用例靠断言失败杀死。
  - 我另加的 Y7（判据改成 `round <= 1`）被 3 条已有的续跑用例杀死。

### M3 身份设定独占一行：已修好

- **代码**：`engine.py:92` 改为 `text += "\n" + line`。
- **实测（P7）**：decide 的系统提示在身份设定附近是 `…"}\n主人给你的身份设定：谨慎追问。…格式。\n\n【讨论群公共规则】\n`。没有身份设定时，整段等于 `prompt + RULES + JSON_RULE`，与原来逐字相同。
- **新用例的证明力**：两条用例都改成了整段精确比较，覆盖 plan、decide、rework、draft 四种步骤。V5 被杀死。

### M4 付费路径用例：已修好

我用自己的变异脚本，不带 `-x` 跑全部讨论群用例，看是哪条用例杀死的：

| 变异 | 杀死它的用例 |
|---|---|
| X1 原子结算不写步骤缓存 | `test_paid_continue_reuses_ok_steps_and_charges_only_new_spend` |
| X4 计费不核对令牌 | `test_stale_token_cannot_reserve_or_reserve_fixed` |
| X25 暂停不取消任务 | `test_pause_while_paid_call_blocked_refunds_reservation` |
| X26 删群不取消任务 | `test_delete_while_paid_call_blocked_refunds_reservation`、`test_delete_refunds_stale_reservation_when_cancel_is_noop` |

四条都是被对应的新用例按设计意图杀死的，而且都在 `DEV_MODE=0` 下运行，不是免费模式里的恒真断言。

注意：删群事务自己也退预扣之后，X26 在余额上已经看不出差别，现在只靠「接口返回时任务已结束」这条断言发现。这条断言在，所以够用。

## 3. 必须修复项

### M5 分身读库与暂停同时发生、读库又报错时，取消被吞掉，暂停被无视

- **哪里错**
  - `NovelBilling._drain`（`novel/billing.py:166-185`）：外层被取消时，先记下 `cancelled=True`，再等内层；如果内层抛的是普通异常，第二次 `await asyncio.shield(task)` 直接把这个异常抛出去，`cancelled` 被丢掉。
  - 本轮 `avatar.py:25-26` 把 `get_my_agent`、`get_memory_snapshot` 包进了 `_drain`。这两个调用在 `engine._avatar_try`（`engine.py:302-323`）里，而它的 `except Exception:` 会把普通异常变成一条「分身这次没能发言」通知，然后继续流程。
  - 结果：取消丢了；任务接着跑后面的步骤；`cancel_group` 一直等到任务自然结束；`pause` 的事务看到状态已经不是 `planning` 或 `running`，什么都不改，返回 200。
  - 修之前没有这个问题：取消直接以 `CancelledError` 抛进读库调用，`_avatar_try` 会原样上抛（代价是 M1 的写锁泄漏）。
- **复现（P9、P10，探针代码见第 6 节）**：把 `agent_store.get_memory_snapshot` 换成「阻塞直到放行，然后抛 `sqlite3.OperationalError`」的版本（它只在引擎的分身步骤里被调用）。阻塞期间调用 `service.pause`，50 毫秒后放行。
  - 立项阶段（brief）：暂停返回 `('awaiting_start', None)`，群没停，消息多了一条跳过通知。
  - 开工后（第 1 轮的 view）：暂停返回 `('done','accepted', round=1)`，群跑完了整轮。
  - 付费模式（P10）：阻塞时已花 31 颗；暂停返回后已花 34 颗，`r01/50-accept-acceptor` 是在作者点了暂停之后结算的。
  - 对照：只把 `get_memory_snapshot` 那处 `_drain` 去掉，同一探针下两种阶段的暂停都返回 `('paused','user')`，之后没有任何新步骤。
- **为什么算必须修复**
  - 这是本轮新代码引入的路径，后果是暂停失效、暂停后照样扣费，状态与作者的操作不符。
  - 触发条件是「读库抛异常时恰好有一个取消在等」。最可能的真实情形是写锁被别处占住超过 `SQLITE_BUSY_TIMEOUT`（5 秒），`BEGIN IMMEDIATE` 报 `database is locked`，而作者正是在这几秒里点了暂停。正常运行时概率很低。
  - 第 1 轮可优化项 7 已经点到过这个机制，当时只是潜在风险；本轮的修法把它直接放进了分身路径。
- **期望改法（不需要动 `novel/`）**
  - 在 `_avatar_try` 的 `except Exception` 分支开头加一个判断：如果当前任务已经收到过取消请求，就上抛 `CancelledError`，并带上原异常：

    ```python
    except Exception as error:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise asyncio.CancelledError() from error
        await store.post_message(...)
    ```

    `_drain` 吞下 `CancelledError` 时不会调用 `uncancel()`，所以 `cancelling()` 仍大于 0。这样改还能顺带兜住调用器内部（`billing.reserve`、`finish_usage` 等）在分身步骤里同类的取消丢失。
  - 我在克隆里按这个写法改过：P9 两种阶段都变成 `('paused','user')`，讨论群 191 条用例全过。
  - 另一种做法：在 `avatar.py` 里用一个 discuss 自己的 `_drain` 变体，只要曾被取消，内层结束后一律抛 `CancelledError`（从内层异常 `from`）。两种可以都做。

## 4. 可优化项（不阻断）

### 新代码的测试缺口

我加的变异里，下面这些在现有 191 条用例下全部存活。代码现在是对的，缺的是用例：

| 编号 | 变异 | 说明 |
|---|---|---|
| Y1 | `release_claim` 清令牌时去掉 `AND run_token=?` | 返修单 E 明说「只清自己认领的那个值」，但没有用例。我的探针 P3 能发现它：群上已有别人的令牌，认领被拒，同时调用方被取消，期望别人的令牌保留。当前代码通过，Y1 下失败。 |
| Y3 | `detail` 不传 `name=avatar_name`，退回到在 `_avatar_member` 里再取一次 | 返修单 A 要求「最多取一次」，没有计数用例 |
| Y4 | `run_rounds` 的 `draft` 初值改回库里最新一版（v1.2 第 9 条） | 返修单说不要求用例；目前确实观察不到差别 |
| Y5 | 隐私说明删掉 v1.2 第 10 条新加的那句 | `test_discuss_docs` 只查「阿里云百炼」；目录接口的 `notice` 和三份文档里的这句都没人断言 |
| Y6 | 建群重名检查只对自定义成员生效 | 现有用例只用了两个同名的自定义成员；带 `role` 又改了名字的成员与别人重名的情形没测 |
| Y8 | `release_claim` 不再吸收第二次取消 | 两种写法外部可见的行为相同（都抛 `CancelledError`，令牌都已清掉），属等价变异，可以不管 |

### 计费与并发（新代码，没发现错，但值得收紧）

1. **残留预扣只在开工、继续、追加轮数和删群时退。**
   - 进程如果在 `_pause` 提交之后、`_cleanup` 退款之前被杀，群停在 `paused`，留着 reserved 行。
   - 之后作者如果点「接受」（`paused` 状态允许）或「结束」，这笔钱要等删群或返工时才回来，违背 4.11「群停下来之后 reserved == 0」。
   - 建议 `accept` 和 `close` 的事务里也退一次，或者启动时对所有不在跑、但 `reserved_strawberries > 0` 的群退款。属规格范围问题，请规格作者定。
2. **退款在状态改成 `running` 之后单独做。**
   - `start`、`resume`、`continue` 先提交「状态 = running」，再单独做一次 `refund_reserved`，然后才 `start_group`。
   - 如果这次退款失败（比如 5 秒写锁超时），接口返回 500，群停在「running、没令牌、没任务」，作者要先暂停再继续才能恢复。
   - 建议把退预扣的三条 SQL 并进同一个状态事务。这样还少一次写事务，也去掉了中间窗口。
3. **认领补偿之后，群可能停在「running 或 planning、没令牌、没任务」。**
   - 这符合 v1.2 第 3 条的字面，但第 1 轮说的「一直显示进行中、挡住新建或开工别的群」仍然存在，要作者手动暂停一次才恢复。
   - 实际只有 HTTP 处理被取消时才会发生，概率很低。
4. **预扣行覆盖（第 1 轮可优化项 2 的剩余部分）。**
   - 跨运行的残留预扣，现在由启动前退款兜住了。
   - 同一次运行内，如果退款本身失败（不是令牌失效），同一步骤键的重试 `reserve` 仍会用 `ON CONFLICT … DO UPDATE` 覆盖仍处于 reserved 的旧金额。
   - 建议冲突且旧行仍是 reserved 时累加，或直接拒绝。

### 我核对过、确认没问题的并发情形（供参考）

- **删群时任务还在跑（P4）**：把 `cancel_group` 换成空操作，模拟第 1 轮可优化项 1 的竞态。
  - 删群前 spent=5、在途预扣 2、余额 9993；删群事务退回 2 颗，余额 9995。
  - 放行后，在途任务结算时因群不存在得到 `RunNoLongerActive`，安静结束；余额仍是 9995，五张表都为空。
  - 没有多退，也没有重复退。
- **无令牌退款撞上有效令牌的在途调用（P5）**：直接调用一次 `refund_reserved()`。
  - 在途的 2 颗被退回；之后这一步结算得到 0，不扣费，也不写缓存。
  - 最终余额 = 10000 − spent（9968 = 10000 − 32），守恒。
  - 代码上，`start`、`resume`、`continue` 退款时这种情形不可达：`_group_update` 在状态改成非 `planning`/`running` 时会自动清令牌，`resume` 和 `continue` 的事务也显式清令牌。所以退款时不存在持有有效令牌的旧任务。
- **暂停与并发开工交错（P8）**：用钩子强制「暂停的 `cancel_group` 先跑完 → 开工认领并起任务 → 任务读到 running → 暂停事务提交」。
  - 结果：暂停事务因 `_group_update` 自动清令牌，旧任务下一次写库得到 `RunNoLongerActive` 退出。
  - 最终 `('paused','user', round=0, run_token=None)`，状态没有错乱。
- **`delete_group` 退款的范围**：只合计本群、本人、`billing_status='reserved'` 的行，退给本人。它与 `refund_reserved`、`_finish_transaction` 都在 `BEGIN IMMEDIATE` 下串行，都先检查 reserved 状态，所以只会退一次。Y2（合计时去掉 reserved 条件）被 `test_delete_while_paid_call_blocked_refunds_reservation` 杀死。
- **认领补偿被第二次取消（P3b）**：在认领提交处取消一次，在补偿提交处再取消一次。令牌最终为空，`TASKS` 里没有这个群，写锁空闲，调用方收到 `CancelledError`。

### 其他

5. **X14 的语义需要规格作者定。** 返修单写的是「其余步骤先被取消并收尾，再抛出」；实现和新用例是「等其余步骤自然完成后再抛出」，兄弟步骤会把模型调用跑完。规格正文没有写。实现方在报告里也标了这一点。
6. **文案小错。** 固定席位名字现在允许空字符串，但超长时的报错文案仍是「固定席位的名字需要 1–12 字」（`service.py:189`）。
7. **`detail` 每次轮询仍会开一次写事务。** 带分身的群，每次 GET 详情仍有一次 `get_my_agent`（`BEGIN IMMEDIATE`，因为它可能建行）。比修之前的两次少了，但轮询时仍在争抢全局写锁。以后可以考虑只读取名字、不建行。

## 5. 给实现方的修改指令（只针对 M5，可直接转发）

依据 `02-spec.md` v1.2 与本复核。只改 `backend/discuss/engine.py`（必要时加 `backend/discuss/avatar.py`）和 `backend/tests/test_discuss_runner.py`，其他文件不动。

1. **`engine._avatar_try`**：在 `except Exception` 分支开头，如果 `asyncio.current_task()` 不为空且 `.cancelling()` 大于 0，就 `raise asyncio.CancelledError() from error`，不发跳过通知、不继续流程。其余行为不变。
2. **新用例**（放 `tests/test_discuss_runner.py`，用现有的 `world` 夹具，参数化两种阶段，写法见第 6 节 P9）：
   - 把 `agent_store.get_memory_snapshot` 换成「第一次调用时阻塞到放行，然后抛 `sqlite3.OperationalError`；之后调用原函数」的版本。
   - 立项阶段：带分身建群后 `start_group`。开工后阶段：先跑完立项，再 `service.start`。
   - 等阻塞发生后，创建 `service.pause` 的任务，50 毫秒后放行。
   - 断言：暂停返回 `('paused','user')`；之后没有新的消息和步骤（立项阶段消息只有 `plan`，开工后阶段没有 `verdict`）。
3. **付费版用例**（放 `tests/test_discuss_billing.py`，写法见 P10）：`paid_planning(avatar=True)` 之后，同样阻塞在第 1 轮 view 的读库上，暂停。断言暂停返回 `paused`，且暂停接口返回后的 `spent` 等于阻塞时的 `spent`。
4. **自检**：去掉第 1 条改动，新用例必须靠断言失败变红，贴输出。
5. **验收**：`tests/test_discuss_*.py` 全过、0 跳过；全量 = 8352 + 讨论群用例数，0 失败；`git status` 只多出允许的文件。

可选（不阻断）：第 4 节「新代码的测试缺口」里的 Y1、Y3、Y5 各补一条用例。P3 的写法可以直接用作 Y1 的用例。

## 6. 探针与变异实验

除 6.1 外，都在系统临时目录下的克隆里完成，克隆用完已删。命令都从 `backend/` 执行，前面加 `NO_PROXY=… no_proxy=…`。

### 6.1 门禁复跑

- 复核副本里 `tests/test_discuss_*.py`：`191 passed`，0 跳过，约 16 秒。
- 全量没重跑：没有具体怀疑。8352 + 191 = 8543，与派单方的数字对得上。
- `verify/zombie_probe.py` 复制进克隆运行：`ZOMBIE_PROBE write_interrupted_by_cancel=False lock_in_cleanup=free`，1 passed。

### 6.2 派单方变异脚本复跑（16 条）

`verify/mut_discuss.py <新克隆> <结果> V1 V2 V3 V4 V5 V6 V7a V7b V7c V8 V9 V10 X1 X4 X25 X26`：

- 开头和结尾的正控都是 `191 passed`。
- 16 条全部杀死，都是 `1 failed`，没有一条是靠报错或超时杀死的。

X1、X4、X25、X26、V6 我又不带 `-x` 跑了一遍，确认是哪条用例杀死的（见第 2 节 M4 的表；V6 由 `test_cancelled_start_group_claim_clears_token_and_leaves_no_task` 杀死）。

### 6.3 我加的变异（脚本没覆盖的点）

| 编号 | 改法 | 结果 |
|---|---|---|
| Y1 | `release_claim` 不带令牌条件清令牌 | 存活（测试缺口；P3 可发现） |
| Y2 | `delete_group` 合计时去掉 `billing_status='reserved'` | 杀死：`test_delete_while_paid_call_blocked_refunds_reservation` |
| Y3 | `detail` 不复用分身名字 | 存活（测试缺口） |
| Y4 | `draft` 初值改回最新成果 | 存活（无需用例，观察不到） |
| Y5 | 隐私说明删掉新句 | 存活（测试缺口） |
| Y6 | 建群重名只查自定义成员 | 存活（测试缺口，轻） |
| Y7 | `resume` 判据改成 `round <= 1` | 杀死：3 条续跑用例 |
| Y8 | `release_claim` 不吸收第二次取消 | 存活（等价变异） |

### 6.4 探针（都在克隆的 `tests/test_discuss_zz_probe.py` 里，复用 `test_discuss_runner` 与 `test_discuss_billing` 的夹具）

| 编号 | 做法 | 当前代码 | 对照 |
|---|---|---|---|
| P1 | 后台 brief 停在 agents 查询未取走游标时暂停 | 0.112 秒返回 `paused/user`，写锁空闲 | 去掉 avatar 的 `_drain`：`database is locked`，17 秒 |
| P2 | 已开工、卡在等槽位（`round=0`）时暂停再继续 | 回到 `awaiting_start`，brief 不重调，无 r01 调用，再开工能跑完 | 判据改回 `plan_revision`：直接跑到 `done`，r01 有 9 次调用 |
| P3 | 认领被拒（已有别人的令牌）同时取消 | 别人的令牌保留 | Y1：别人的令牌被清掉 |
| P3b | 认领提交、补偿提交各取消一次 | 令牌为空、无任务、写锁空闲 | — |
| P4 | 删群时绕过 `cancel_group`，在途预扣 2 颗 | 余额 9993 → 9995，任务安静结束，五表清空 | V8：余额不恢复 |
| P5 | 有效令牌在途时做一次无令牌退款 | 退 2 颗，该步不扣不缓存，最终守恒 | — |
| P6 | 第 1 轮探针 C（brief 阻塞时暂停再继续） | `awaiting_start`、round 0，brief 调 2 次，无轮次调用 | — |
| P7 | 身份设定行的前后字符 | `"}\n主人给你…格式。\n\n【讨论群公共规则】` | — |
| P8 | 暂停与并发开工的最坏交错 | 最终 `paused/user`，令牌为空 | — |
| P9 | 分身读库阻塞→暂停→读库报错（M5） | 立项阶段返回 `awaiting_start`，开工后阶段返回 `done/accepted` | 去掉该处 `_drain`：两种阶段都是 `paused/user`；按第 5 节改法改后也是 `paused/user`，191 条全过 |
| P10 | P9 的付费版 | 暂停后 spent 31 → 34，accept 在暂停之后结算 | — |

P9 的核心写法（P10 同理，换成 `test_discuss_billing` 的 `paid_planning(avatar=True)`）：

```python
@pytest.mark.parametrize("stage", ["planning", "running"])
def test_p9_pause_during_avatar_read_that_errors(world, monkeypatch, stage):
    # 准备：带分身建群；stage=running 时先跑完立项，等到 awaiting_start 且任务已退出
    original = agent_store.get_memory_snapshot
    fired = [False]

    async def failing(username, conversation_id=None):
        if not fired[0]:
            fired[0] = True
            entered.set()
            await release.wait()
            raise sqlite3.OperationalError("simulated")
        return await original(username)

    monkeypatch.setattr(agent_store, "get_memory_snapshot", failing)
    # planning：runner.start_group；running：service.start(expected_revision=…)
    # 等 entered → pause_call = create_task(service.pause(...)) → sleep(0.05) → release.set()
    # 期望 pause 返回 ('paused','user')；当前代码返回 awaiting_start 或 done
```

注意：`get_memory_snapshot` 只在引擎的分身步骤里被调用。如果换成 `get_my_agent`，开工那次请求的 `detail` 会先触发钩子，造成死锁。

## 7. 附：规格 v1.2 十条修订的核对

| 条 | 实现是否一致 | 修订本身 |
|---|---|---|
| 1 继续判据 | 一致（`service.py:829`） | 「`round == 0` 等价于没开工过」说得过头：后文自己承认「开工后、第 1 轮前停下」的群也是 `round == 0`。行为描述清楚，只是用词矛盾，建议改成「`round == 0` 时一律视为未开工」 |
| 2 写事务保护 | 一致：三处分身读库都受保护，store 的形式与修订一致 | 只要求「受保护」，没要求「保护后仍要把取消交还调用方」，M5 就出在这里。建议补一句：受保护的调用不得吞掉调用方的取消 |
| 3 认领令牌 | 一致：只清自己认领的值，在受保护事务里清，之后上抛取消 | 无问题；遗留见可优化项 3 |
| 4 残留预扣 | 一致：开工、继续、追加轮数在 `start_group` 前退；删群在同一事务里先退再删 | 标题引了 4.14（删号），正文却没有对应要求（删号时用户行一起删掉，退款无意义），建议删掉这个引用；没覆盖 `accept`、`close`，见可优化项 1 |
| 5 身份设定独占一行 | 一致 | 无问题 |
| 6 清除名字 | 一致 | 报错文案没跟着改，见可优化项 6 |
| 7 建群重名 | 一致，与改方案时的检查相同 | 无问题 |
| 8 分身提示顺序 | 一致（`avatar.py` 四段 + 任务提示 + JSON 规则） | 第 1 轮提过的「只输出一个 JSON 对象」在 `AVATAR_IDENTITY` 和 `JSON_RULE` 里重复，仍在，无害 |
| 9 draft 初值 | 一致（`engine.py:437`） | 无问题 |
| 10 隐私说明 | 一致：`roles.PRIVACY_NOTICE`（目录的 `notice`）、README、ARCHITECTURE、CLAUDE.md 四处文字相同。三份文档本来就是转述，没有逐字引用原句，实现方把新句接在各自隐私段末尾，读起来通顺 | 附录 A 正文没改，由修订覆盖，符合修订开头的约定；CLAUDE.md 仍在大小上限内（68,497 字节，相关测试通过） |

## 8. 附：新用例的证明力抽查

- **数量**：本轮新增 35 条（156 → 191）。
- **既有用例的改动**：与派单方说的一致，只有三类：
  - 两条身份设定用例收紧成整段比较；
  - `test_resume_and_continue_reject_exhausted_budget_until_added` 的造数补了 `round=1`。判据变了之后，这个群应被视为已开工，这样补是对的；
  - `prepare` 加了 `max_rounds` 参数，默认值不变。

  没有放宽或删除断言。
- **计费断言是否只在免费模式下成立**：
  - 本轮付费用例全部 `DEV_MODE=0`，并替换了 `_single_real_call`。
  - 免费模式的 M2 用例里那句 `reserved == 0` 是恒真的，但同一路径另有付费用例（`test_paid_resume_after_brief_insufficient_funds_waits_for_start`），所以不算缺口。
- **扫描空集**：
  - 抽查的 `all(...)` 断言多数前面检查过非空，或另有断言证明集合非空（例如续跑用例先断言 `ok_keys` 非空、`r02/` 步骤存在）。
  - `test_avatar_brief_pause_then_resume_waits_for_start` 里对消息步骤键的 `all(...)` 前面没有检查非空，但同一用例前面已经断言有 plan 和 brief 两条消息，不构成空集。
- **断言是否命中目标**：
  - V3 用例的标记查询只出现在 `get_memory_snapshot` 里，确实停在了记忆查询上（V3 被杀死）。
  - M1 两条用例里 `assert not task.done()` 和写锁检查都能发现去掉 `_drain`。
  - E 用例的闸门装在认领事务的提交上。
- **测试缺口**：见第 4 节 Y1、Y3、Y5、Y6。
