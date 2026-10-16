# 小说工坊 P1 独立复核 A：计费 / 运行器 / 上下文压缩

复核日期：2026-10-15。复核对象：工作树 `.worktrees/fiona-novel-p0`，基线 `820fff1`，未跟踪新增文件直接读。全部核验离线：fake 提供方 + 临时库；未运行真实提供方、未读密钥、未改仓库任何文件（本文除外）。探针脚本与变异副本都在 scratchpad `review-p1a/`，不入库。

## 结论：不通过（1 项必须修复的守恒缺陷 + 4 项 P2）

计费主路径（价目、上界预扣、按真实 usage 结算、差额退、重试计费、失败全退、免费口径、缓存续跑、余额不足不发调用）在顺序执行下全部正确，95 条新增测试通过。但 **`NovelBilling.reserve()` 由三段独立事务拼成**，用户暂停/删书/关机触发的取消，或两段之间进程被杀，会让「用户余额变化 ≠ 本书 spent」。混沌探针（critique 三路并行 + 随机网络失败/坏 JSON/缺 usage + 随机外部暂停/续跑）两个种子分别出现 19、20 次守恒违反，方向两边都有（用户少付 1～15 颗，也有用户多付 29～85 颗）。把余额扣减并入同一个 `BEGIN IMMEDIATE` 后（补丁只改 `reserve()`，在 scratchpad 副本验证），同一探针三个种子全部守恒，三个取消/崩溃窗口全部归零，59 条计费/运行器/接口测试照旧通过。修法明确、改动局部，修完可通过。

## 一、逐项核验

### 1. 计费正确性（`novel/billing.py`、`llm_router.py` 钩子、`store_db.py`）

| 项 | 结论 | 证据 |
|---|---|---|
| 价目按 §13 D1 折算 | ✅ | `billing.py:20-24`：qwen 1.80/5.40、deepseek-flash 0.33/1.30、豆包 0.90/4.50。手算：¥12/M→0.012/千→×100×1.5=1.8；$0.30×7.2=¥2.16/M→0.216×1.5=0.324→向上取 0.01=0.33；$1.20×7.2=8.64→0.864×1.5=1.296→1.30；¥6→0.9；¥30→4.5。`test_author_prices_and_decimal_rounding` 固定了这些值 |
| 单次 `ceil(...)`、最少 1 | ✅ | `calculate_cost` 用 Decimal + `ROUND_CEILING`，`max(1, …)`（`billing.py:84-86`） |
| 预扣上界 = 输入字符数 + 角色 max_tokens | ✅ | `billing.py:167` `calculate_cost(model, input_characters(messages), max_tokens)` |
| 结算 ≤ 预扣、差额退还、spent/reserved 更新 | ✅ | `_finish`（`billing.py:212-236`）：`charged=min(reserved, charge)`，users +(reserved−charged)、novels reserved−=reserved、spent+=charged，三张表同一事务。变异 D（去掉 `min`）→ `test_charge_never_exceeds_reservation…` 失败，测试有效 |
| 校验重试照常计费 | ✅ | 每次 `_attempt` 独立 reserve/settle（`llm_router.py:285-303`）；`test_validation_retry_charges_each_attempt…` 断言 charged=2 |
| 网络失败 / 未拿到 usage 全额退 | ✅ | `llm_router.py:297-302`（usage 缺项 → refund）、`:307-313`（异常 → finally refund）。变异 A（去掉 finally 退款）→ `test_failed_or_unknown_call_refunds_everything` 2/3 参数失败，测试有效 |
| 自带 Key / fake / DEV_MODE=1 不扣 | ✅ | `is_free`（`billing.py:149-151`），`_attempt` 对 fake 不进计费（`:285`） |
| 续跑命中缓存不重复扣 | ✅（有一处例外，见 P2-3） | `call()` 读到 `status=='ok'` 直接返回（`llm_router.py:342-344`）。变异 B（禁用缓存）→ 恢复类 3 条测试全部失败，测试有效 |
| 余额不足不发调用，抛 `InsufficientStrawberries` | ✅ | reserve 在 `invoked=True` 之前（`:286-287`）；`test_failed_precheck_never_sends_call` 用 `pytest.fail` 守住 `_single_real_call` |
| **并发 + 异常 + 取消下的守恒** | ❌ | 见 P1-1。探针 `probe_conservation.py`（原代码）：SEED 7 → `RESULT: FAIL violations=19`，末态 `spent=815 balance_delta=816`；SEED 11 → `violations=20`，末态 `spent=899 balance_delta=984`（用户多付 85 颗）。同探针跑在补丁副本：SEED 7/11/23 全部 `RESULT: PASS`，`spent==balance_delta==sum(charged)`，`reserved=0` |

### 2. 运行器状态机（`novel/runner.py`）

| 项 | 结论 | 证据 |
|---|---|---|
| 状态与 pause_reason 枚举、四类关卡 | ✅ | setup→`awaiting_setup`（`store_db.commit_setup`）；per_chapter→`save_plan`→`awaiting_plan`；per_batch `chapter % batch_size==0`→`awaiting_review`；裁决 `end` 且归档完成→`awaiting_end`（`runner.py:284-296`）；完结守卫 `validate_decision` final 必须 end（`schemas.py:361`） |
| 每章流程同一事务 | ✅ | `commit_chapter` 一个 `BEGIN IMMEDIATE` 内写章节、圣经版本、计数、留言回应（`store_db.py:279-325`） |
| 80% 预算暂停口径 | ✅（口径比规格略严，应写进报告） | `spent + reserved(在途) + 本次预扣上界 > 0.8×budget`（`billing.py:171,179`），规格原文只写「已花费 + 本次预扣」。因为用的是上界而非期望值，实际会在真实花费约 70–78% 时就停；resume 判据 `spent×5 ≥ budget×4` 与之一致（`service.py:342-344`）。但测试无法区分 80% 与 100%，见 P2-4 |
| 每日上限 | ✅ | 章前 `check_chat_daily_cap(hit=False)` 预检（`runner.py:254`），写完一章 `check_daily_cap` 计数并在 commit 后暂停（`:282-290`），不自动续跑（resume 由用户发起） |
| 每用户 1 本 / 全局槽排队 | ✅ | `check_active` 在 `BEGIN IMMEDIATE` 内（`service.py:125-128`）；`_slots()` 按事件循环建 `Semaphore(FIONA_NOVEL_MAX_RUNNING)`，排队书保持 `running`（`runner.py:58-68,167`）；`test_global_slot_queue…` 覆盖第 4 本排队 |
| run_token 防双跑 | ✅ | `start_novel` 在 `BEGIN IMMEDIATE` 内只对 `run_token IS NULL` 的书发令牌（`:85-93`）；`DbStepStore.transaction()` 每次写库校验 token+users 存在（`store_db.py:134-149`）；`NovelBilling._active` 同样校验（`billing.py:153-161`） |
| 暂停/删书取消时进行中调用退款 | ✅ | `_attempt` finally 退本次（`llm_router.py:307-313`）+ `_run` finally `refund_reserved()`（`runner.py:197`）+ `cancel_novel` 再退一次（幂等，按 `billing_status='reserved'` 行） |
| 重启恢复：reserved 退款、标 interrupted、断点续跑 | ✅ | `recover_interrupted_novels`→`cancel_novel`→`refund_reserved`（`billing.py:238-257`）→`start_novel(recovering=True)`；`test_runner_restart_refunds_reserved_and_reuses_completed_step` 证明 fake 调用数不增、spent 不变 |
| 条件写入防删号后重建 | ✅ | 所有后台写走 `transaction()`，`is_current` JOIN users（`store_db.py:123-132`）；`_run` 末尾清令牌也带 `EXISTS(users)`（`runner.py:205-207`） |
| 任务泄漏 | ✅ | `TASKS/_owners` 由 done callback 清理（`runner.py:98-102`）；关机 `shutdown_novel_tasks` 先于 `shutdown_background_tasks` |
| 改稿最新章的竞态 | ❌ | 见 P2-2 |
| 恢复后错误原因语义 | ⚠️ | 见可优化 1 |

### 3. 上下文压缩（`novel/context.py`、`writing.py`）

| 项 | 结论 | 证据 |
|---|---|---|
| 章节摘要只留最近 10 章 | ✅ | `trim_bible` `chapter >= current-10` 再 `[-10:]`（`context.py:27`） |
| 卷摘要每 10 章由档案员 `arc_summary` 生成、≤600 字、计费 | ✅ | `apply_archived_chapter`（`writing.py:98-124`）走 `router.call`；探针 60 章：`arc_summary calls at chapters: [10, 20, 30, 40, 50, 60]`，`arc_summaries stored` 6 条；`test_runner_arc_10_and_20…` 证明两条步骤 `settled` 且 charged>0 |
| 卷摘要进入视图的时机 | ✅ | 只保留 `start_chapter < current-10` 的卷（与逐章窗口不重叠） |
| 伏笔：open 全留、resolved 留最近 5 | ✅ | `context.py:31-36`；探针 60 章 open 5 条全部在视图中；测试 `{OPEN0..3}` 断言 |
| 时间线 10 / 桥段 30 | ✅ | `:29-30`；brief 在压缩开启时 `timeline_limit=10`（`deliberation.py:61`） |
| 人物：主角状态全留；配角只留最近 3 章出场 + 细纲点名 | ✅（状态层面） | `:41-51`；但**配角卡片**在 `locked` 里从不裁剪，见下 |
| 锁定区与罗盘不裁剪 | ✅ | `locked`、`compass` 原样 deepcopy |
| 稳定块/变化块两条 user、Anthropic `cache_control` | ✅ | `context_messages`（`:77-80`）、`_provider_call`（`llm_router.py:205-217`）；`test_anthropic_system_and_stable_user_ephemeral_cache` 用 MockTransport 截请求体验证 |
| 「30 vs 60 章增长 14–21% 无法 ≤10%」归因是否成立 | **部分成立，归因不完整** | 探针 `probe_context_growth.py`（真实引擎 60 章，档案员每章给主角加 1 条 knows、植/收伏笔、每 4 章新增 1 配角）：ch30→ch60 editor +20.6%、writer +25.3%、archivist +20.8%。按组件拆分（ch31 vs ch61 的裁剪后圣经，字符）：`locked.characters` **+1199**、`character_states.C1.knows` +1080、`arc_summaries` +345（fake 卷摘要只有 58 字；真实 600 字/卷会是约 +1800），其余组件 +0～+9。实施方只提到卷摘要和主角知识，**漏掉了新增配角卡片**：§4.6「人物」条写的是「配角只保留最近 3 章出场过的」，实现只对 `character_states` 做了，`locked.characters` 里的配角卡片一条不减（档案员每章最多新增 2 个）。同一探针在不增长的 fixture（MODE=plain）下增长仅 +5.6～9.2%，说明 ≤10% 只在圣经不增长时成立 |

### 4. 测试是否真能失败（变异验证，scratchpad 副本）

| 变异 | 目标测试 | 结果 |
|---|---|---|
| A `llm_router.py:307` `if billed and not billing_done` → `if False and …` | `test_failed_or_unknown_call_refunds_everything` | **杀死**（2 failed, 1 passed） |
| B `llm_router.py:343` 缓存命中判断 → `if False:` | `test_runner_restart_refunds_reserved_and_reuses_completed_step`、`test_resume_reuses_completed_steps…`、`test_validation_retry_charges…` | **杀死**（3 failed） |
| C1 `billing.py` `*.8` → `*1.0`（80%→100%） | `test_runner_precheck_pause_and_resume_after_fix`、`test_failed_precheck_never_sends_call` | **存活**（4 passed）→ 测试守不住 80% 这个数，见 P2-4 |
| C2 `*.8` → `*1000`（阈值失效） | 同上 | 杀死（2 failed） |
| D `_finish` 去掉 `min(reserved, charge)` | `test_charge_never_exceeds_reservation…` | 杀死 |

### 5. 其他核验

- 新增 95 条测试在工作树通过：`95 passed, 28 warnings in 5.58s`。
- `git status --porcelain` 在复核前后一致（本文件除外）。
- `FakeLLM.payload` 对拆分后的两条 user 做深合并（`fake_llm.py:58-78`），P0 单条 user 路径不受影响；P0 冻结测试通过。

## 二、必须修复

### P1-1 `NovelBilling.reserve()` 不是一个事务：取消或崩溃会让账目不守恒

- 位置：`backend/novel/billing.py:163-198`。
- 问题：先 `database.reserve_strawberries()`（独立事务扣余额）→ 再开第二个 `BEGIN IMMEDIATE` 写步骤行 + `novels.reserved`。aiosqlite 的 commit 在工作线程执行，等待它的协程被取消时 commit 照样完成。于是有三个窗口（探针 `probe_cancel_window.py`，每次预扣 8 颗）：
  - A 取消落在第一段 commit 之后：余额已扣、没有 reserved 行，`refund_reserved()` 退 0 → `LOST=8`（用户丢钱，永不找回）。
  - B 取消落在第二段 commit 之后：`except BaseException` 走 `refund_strawberries`，随后 `_run` finally 的 `refund_reserved()` 按行再退一次 → `GAIN=8`（平台丢钱）。
  - C 两段之间进程被杀：同 A，`LOST=8`。
- 影响：用户暂停、删书、删号、关机、`_gather_phase` 取消兄弟调用、`InsufficientStrawberries/BudgetExceeded` 取消在途调用，都会落进这些窗口。因为整条预扣路径只有 DB I/O，窗口占比不小：混沌探针 22 次暂停里 19 次核对失败。
- 修法：把余额扣减放进同一个事务，不再经 `database.reserve_strawberries/refund_strawberries`：

  ```python
  async with aiosqlite.connect(...) as db:
      await db.execute("BEGIN IMMEDIATE")
      book = await self._active(db)
      if 预算检查失败: raise NovelBudgetExceeded()
      await database._apply_daily_refill(db, self.username, database.strawberry_daily_refill())
      cursor = await db.execute("UPDATE users SET strawberry_balance=strawberry_balance-? "
                                "WHERE username=? AND strawberry_balance>=? RETURNING strawberry_balance",
                                (amount, self.username, amount))
      if await cursor.fetchone() is None: raise InsufficientStrawberries()
      INSERT novel_steps … ON CONFLICT …; UPDATE novels SET reserved_strawberries+=amount
      await db.commit()
  ```

  这样 commit 之前取消 → 整体回滚；commit 之后取消 → `_run` finally 的 `refund_reserved()` 按行退一次，恰好守恒。补丁已在 scratchpad 副本验证（`patch_reserve.py`）：守恒探针 3 种子 PASS、三窗口 0、`test_novel_p1_billing/runner/api` 59 条通过。规格 §6「先调用 reserve_strawberries」的字面要求与守恒冲突时，以守恒为准，报告里写明即可。
- 同时补一条测试：在 `reserve()` 的 commit 后注入 `CancelledError`，断言 `refund_reserved()` 之后余额恢复到起点（可直接改造 `probe_cancel_window.py` 的 B 场景）。

## 三、P2（应修，不阻断合并但要排期）

### P2-2 `edit_chapter` 的「最新章」判定与取消之间有竞态，会丢掉正典圣经里下一章的归档

- 位置：`backend/novel/service.py:383-405`，`latest` 在第 389 行按取消前读到的 `chapters_done` 决定，取消后 398 行写 `_rearchive=number` 时没有重算。
- 复现：`probe_edit_race.py`（full_auto 中 worker 正在提交第 3 章时用户改第 2 章）→ 圣经版本 `(5,'archive:3'),(6,'rearchive:2'),(7,'archive:4')`，最新圣经 `chapter_summaries=[1,2,4]`，第 3 章的摘要/时间线永久缺失，后续章节都在缺一章的圣经上推演。
- 修法：第二个 `BEGIN IMMEDIATE` 里重读 `chapters_done` 再算 `latest`；若已不是最新，改走 stale 分支并返回对应 message（此时 `cancel_novel` 已停掉 worker，还要把书重新 `start_novel`，或干脆把 cancel 也挪到事务内判定之后）。

### P2-3 settle 与 `write_step(ok)` 分属不同事务：取消落在两者之间，用户会为同一次成功调用付两次

- 位置：`llm_router.py:300`（settle 提交）→ `:322`（append_usage 事务）→ `:412 _save_step`（写 ok）。续跑时该步骤 `billing_status='settled'` 但 `status='interrupted'`，`call()` 不认缓存，重新预扣、调用、结算。
- 证据：补丁副本上 `probe_double_pay.py`（只保留坏 JSON 混沌 + 随机暂停）SEED 5：2 个步骤双付 12 颗；SEED 9：4 个步骤双付 36 颗（总花费 658）。守恒仍成立（用户确实付了两次），但违反 §5「已完成的步骤不重复调用，也不重复计费」。
- 修法（二选一）：
  1. 结算时把 `raw_response/stop_reason/usage` 与 settle 写在同一事务（`_finish` 多接几个字段），`call()` 对「`settled` 且 `raw_response` 非空且 `status!='ok'`」的步骤直接用存好的 raw 走解析/校验，不再预扣不再调用；
  2. 最低限度：恢复/取消时把这类步骤视为平台承担，`refund_reserved` 同时把 `settled AND status!='ok'` 的 `strawberries_charged` 退回（spent 相应减），并在报告里写明平台成本。
  推荐 1，它同时解决了「取消时已拿到的昂贵结果被丢弃」的浪费。

### P2-4 80% 预算暂停的测试守不住 80% 这个数

- 位置：`tests/test_novel_p1_billing.py:320-342`，`budget=1`、预扣 8：阈值改成 100% 甚至 500% 照样暂停（变异 C1 存活）。
- 修法：用 `budget=9`（0.8×9=7.2 < 8 ≤ 9）：80% 口径必须暂停、100% 口径不会；再加一个 `budget=11` 的正例断言第一次调用放行且 spent>0。

### P2-5 改早章把待批细纲行一并标 `stale`，`approve/redo` 变 500

- 位置：`service.py:402` `UPDATE novel_chapters SET status='stale' WHERE chapter>?` 不区分 `done` 与 `awaiting_plan_approval`；`:275/:295` 只查 `awaiting_plan_approval` → `current` 为 None → `TypeError`。
- 复现：`probe_stale_plan.py`（per_chapter，第 3 章待批时改第 1 章）→ `approve_plan raised: TypeError`、`redo_plan raised: TypeError`。用户需先 pause 再 resume 才能解开。
- 修法：stale 只标 `status='done'` 的行；`approve/redo` 查不到待批行时返回 409 而非 500。（接口语义归复核员 B，这里只记录状态机影响。）

## 四、可优化

1. `recovering=True` 会让恢复后的整本书**此后任何** `StepFailed`/异常都标成 `server_restart_failed`（`runner.py:182-190`），例如恢复后几小时才出现的 `decision_invalid` 也被归为重启失败；建议只在恢复后首次成功写库之前用该原因。
2. 上下文增长（给作者拍板）：
   - 视图中的**配角卡片**（`locked.characters`）按与状态相同的「最近 3 章出场 + 本章点名」规则裁剪（只改 `trim_bible` 的视图，正典圣经不动；`validate_*` 都用完整圣经，不受影响）。探针里这一项的增长与主角 knows 相当。
   - 主角 `knows` 在视图中限制为最近 N 条（如 30），或让档案员在 `arc_summary` 时顺带合并旧条目。
   - 以上两项都不动 open 伏笔，可把 30/60 章增长压回 ≤10%；若作者接受增长，`test_sixty_chapter_context_views…` 的 fixture 应改成会增长的，否则 ≤10% 断言只是在不增长的数据上自证。
3. 缓存命中 token 按全价计费（DeepSeek/千问缓存命中有折扣），平台多收；可按 `cached_tokens` 打折，或在价目表里明示。
4. `budget_80` 续跑循环：预算只调高 1 颗即可 resume，但下一次预扣立刻再暂停；建议 resume 判据改为「spent + 一章估算下限 ≤ 0.8×新预算」。
5. 从 `awaiting_review` 暂停再 resume 会跳过审阅关卡直接写下一批（`transition('resume')` 一律 `_activate`）；可在 resume 时若 `per_batch` 且 `chapters_done % batch_size == 0` 回到 `awaiting_review`。
6. `_budget_at_pause/_rearchive/_after_rearchive*` 混在 `config_json` 并经 `detail()` 原样返回，建议单列或在返回时剥掉。
7. `check_daily_cap` 在 `commit_chapter` 之前计数，commit 因令牌失效返回 False 时次数已消耗（极少发生）。
8. 03-report §7 第 1 条的归因应补上配角卡片增长；并写明 80% 判据含在途预扣、按上界计算。

## 五、给实施方的修改指令

1. **（必须）** 重写 `NovelBilling.reserve()` 为单事务（见 P1-1 代码），删除对 `database.reserve_strawberries/refund_strawberries` 的依赖；新增「commit 后取消 → `refund_reserved()` 后余额归零」测试；用与本复核相同的混沌方式（critique 三顾问并行 + 随机暂停/续跑 + 网络/坏 JSON/缺 usage）跑一条守恒测试，断言 `初始余额−余额 == spent == Σ charged`、`reserved==0`。
2. **（P2）** `edit_chapter`：在写 `_rearchive` 的同一 `BEGIN IMMEDIATE` 内重算 `latest`；不是最新则走 stale。补一条把 `cancel_novel` 换成「先提交下一章再返回」的测试。
3. **（P2）** 结算与 ok 落盘同事务，或续跑时用已存 raw 复算（P2-3 方案 1）；补测试：在 settle 后、`_save_step` 前注入取消，续跑后该步骤 fake 调用数不增、charged 不翻倍。
4. **（P2）** 预算暂停测试改 `budget=9/11` 两例（P2-4）。
5. **（P2）** stale 只标 `done` 行；`approve/redo` 无待批行返回 409。
6. 报告补写：80% 判据实际口径；上下文增长三个来源（含配角卡片）与取舍；`recovering` 语义范围。
7. 修完后重跑：`tests/test_novel_p1_*.py` 全绿、全量无新增失败、P0 冻结测试不变。

## 六、复现命令

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
export BACKEND=<工作树>/backend PYTHONDONTWRITEBYTECODE=1
cd <scratchpad>/review-p1a
SEED=7 $PY probe_conservation.py      # 原代码：RESULT: FAIL violations=19
$PY probe_cancel_window.py            # windowA_user_loss=8 windowB_platform_loss=8 windowC_user_loss=8
MODE=realistic $PY probe_context_growth.py   # ch30->ch60 +20~26%，分解表见输出
$PY probe_edit_race.py                # BUG REPRODUCED (chapter 3 archive lost)
$PY probe_stale_plan.py               # approve_plan raised: TypeError
# 修复候选验证（scratchpad 副本 mut/）
$PY patch_reserve.py mut && BACKEND=$PWD/mut SEED=7 $PY probe_conservation.py   # RESULT: PASS
BACKEND=$PWD/mut $PY probe_double_pay.py     # 仍有 2~4 步双付（P2-3）
```
