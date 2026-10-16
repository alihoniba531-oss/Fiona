# 小说工坊 P1 第 2 轮独立复核（返修 F1–F7 / O1 / O2 核验）

复核日期：2026-10-15。复核对象：工作树 `.worktrees/fiona-novel-p0`，基线 `820fff1`，未跟踪新增文件直接读；返修前快照为 scratchpad `snap-p1r1/`。本轮**只核验第 1 轮返修单（05-fix-r1.md）的必须修复项是否真正修好**，不新增主观问题。全部核验离线：fake 提供方 + 临时库；未运行真实提供方、未读密钥、未联网、未改仓库任何文件（本文除外）。探针与变异副本都在 scratchpad `review-p1c/`（复用并改写了 `review-p1a/` 的探针），不入库。

## 结论：通过

- F1–F7、O1、O2 全部确认修复；第 1 轮的三个丢账窗口与混沌守恒探针在新代码上全部关闭，两种资金变异（预扣拆回两个事务、结算与 ok 写入拆开）都会让新增正式测试变红。
- `tests/test_novel_p1_*.py` 133 条通过（返修前 95 条，净增 38 条，与返修单要求一一对应）；全量 `python -m pytest -q`：**4893 passed, 3 skipped**（基线 4855 + 38，跳过数不变；本机沙箱可绑定回环端口，报告里提到的 6 项全部通过）。
- 测试纪律：P1 既有测试只增不删（billing/api/byok/runner 的 diff 全是追加），只有 `test_novel_p1_context.py` 按 F5 新规则改写了 3 条断言（删掉「locked 原样不裁」与「knows 全量下发」两条，均为返修单明确允许），没有无关断言被删弱；非 P1 测试、`database.py`/`main.py`/`rate_limit.py` 与六份文档均只有新增行。
- 没有新发现的阻断问题。

## 一、F1 / F2（资金）

### 1.1 第 1 轮探针重跑（当前代码）

| 探针 | 第 1 轮结果（返修前） | 本轮结果（返修后） |
|---|---|---|
| `review-p1a/probe_conservation.py`（critique 三顾问并行 + 随机网络失败/坏 JSON/缺 usage + 随机外部暂停/续跑，每次停下核对 `初始余额−余额 == spent == Σcharged`、`reserved==0`） | SEED 7 → `FAIL violations=19`；SEED 11 → `violations=20`（用户多付 85 颗） | SEED 7/11/23 全部 `RESULT: PASS`；三种子的 `settled-but-not-ok steps = 0`（付了钱的结果不再被丢弃） |
| `probe_cancel_window2.py`（三丢账窗口改写为适配单事务的 5 个窗口：A 外部取消落在 commit 进行中；B 事务协程内 commit 后抛 CancelledError；C commit 后进程被杀；C2 扣余额后、commit 前被杀；D 外部取消落在 INSERT 执行中） | 旧 A/B/C 各丢 8 颗 | `SUMMARY: {'A_loss': 0, 'A_second_refund': 0, 'B_gain': 0, 'B_second_refund': 0, 'C_loss': 0, 'C2_loss': 0, 'D_loss': 0, 'D_second_refund': 0}`；A/D 的 `drained=True`（取消被推迟到事务完成后再响应），每个窗口 `refund_reserved()` 第二次调用都返回 0，无双退 |
| `probe_double_pay2.py`（第 1 轮 P2-3 探针，适配 `settle(step_record=)` 签名，另加「步骤到 ok 后 fake 是否被再次调用」计数） | SEED 5 双付 2 步 12 颗；SEED 9 双付 4 步 36 颗 | SEED 5/9/17：`steps paid more than once: 0`、`fake re-called after step ok: 0`、`settled-but-not-ok: 0`，三者均守恒 |

正控：同一 `probe_double_pay2.py` 跑在变异 mutSD（见下）上 SEED 5 立即出现 `double-paid step … settles=[4, 5, 4]`，`extra strawberries: 8`，说明探针仍然敏感。

### 1.2 变异验证（scratchpad 副本，只跑 `test_novel_p1_billing.py` + `test_novel_p1_chaos.py`）

| 变异 | 结果 | 被哪些正式测试杀死 |
|---|---|---|
| **mutR**：`_reserve_transaction` 扣完余额后 `commit()` 再 `BEGIN IMMEDIATE`（预扣拆回两个事务） | 1 failed / 48 passed | `test_reserve_statement_failure_rolls_back_refill_balance_and_book`（第二段写步骤行失败时余额与补给日期都应回滚） |
| **mutS**：`atomic_step_settlement = False`（结算与 ok 写入拆成两个事务，仍在 `_drain` 保护内） | 3 failed / 46 passed | `test_cancel_between_settlement_and_step_ok_never_recharges[*-after_settle]` ×2、`test_step_ok_statement_failure_rolls_back_settlement_before_refund` |
| **mutSD**：mutS + 去掉 `_with_retries` 里对 `_complete_response` 的 `_drain`（回到返修前形态） | 5 failed / 44 passed | 上述 3 条 + `…never_recharges[*-before_ok]` ×2 |
| **mutO1**：`budget * .8` → `* 1.0` | 1 failed / 45 passed | `test_budget_exact_79_and_80_percent_boundary[80]`（79 例照常通过） |

说明一点：mutR 下混沌守恒测试与第 1 轮守恒探针都仍然 PASS——因为 `_drain` 已让外部取消无法落在两次 commit 之间，拆事务只剩「进程在两次 commit 之间被杀」这一种丢账方式，这正是触发器注入失败那条测试建模的场景。判定「新的正式测试会变红」成立，但杀手只有一条，见可优化 1。

### 1.3 代码核对

- `billing.py::_reserve_transaction`：同一连接、同一 `BEGIN IMMEDIATE` 内依次 `_active`（run_token + users JOIN）→ 80% 预算检查 → `database._apply_daily_refill(db, username, database.strawberry_daily_refill())` → 条件扣余额（`RETURNING`，不足则抛） → `INSERT novel_steps … ON CONFLICT`（保留 `strawberries_charged` 累计值）→ `UPDATE novels.reserved` → `commit`。任何一步抛异常即连接关闭回滚。
- 每日补给：调用与 `database.reserve_strawberries` 的 `_apply_daily_refill(db, username, strawberry_daily_refill())` 完全相同；`test_novel_reservation_reuses_existing_daily_refill_semantics` 用三组（余额 0 无日期 / 300 昨日 / 300 今日）与 `database.reserve_strawberries` 并排比对余额与补给日期。`git diff 820fff1 -- backend/database.py` 只有 `init_db` 建表循环与 `delete_account_data` 删表两处新增，`reserve_strawberries` / `refund_strawberries` / `_apply_daily_refill` 原文未动。
- `_drain`：把事务包成子任务 + `asyncio.shield`，外部取消时循环等子任务完成后再抛 `CancelledError`；`reserve()` 捕获后按持久 reserved 行走 `refund()`，不做无凭据的余额补偿。退款、结算、`refund_reserved` 同样走 `_drain` 与单事务（用户余额、`novels` 两个计数、`novel_steps.billing_status` 同时改）。
- F2 采用「结算与成功缓存同事务」：`_save_step(status='ok', bill=True)` → `settle(step_record=record)` → `_finish_transaction` 内 `DbStepStore.write_step_on_connection(db, …)`，一起 `commit`。`_finish_transaction` 对 `billing_status != 'reserved'` 的行直接返回 0，重复结算幂等。`_complete_response`（解析/校验/落盘，不含网络等待）整体被 `_drain`。

## 二、F3–F7 逐条

| 项 | 复现方式 | 结果 |
|---|---|---|
| **F3** 改最新章竞态 | `probe_edit_race2.py`：per_batch(2) 写完 1–2 章后 continue，fake 卡在第 3 章 archive；此时 PUT 第 2 章，替身 `cancel_novel` 先放行并等第 3 章提交（模拟排空中的 worker），再真取消 | `edit result: rearchiving=False`，圣经版本 `(5,'archive:3'),(6,'archive:4')`、无 `rearchive:*`，`chapter_summaries=[1,2,3,4]`（第 3 章归档未丢），第 3 章 `stale`、第 2 章 `edited_by_user=1`，`_rearchive` 未写入。代码：`edit_chapter` 在 `editing_novel` 锁内先 `cancel_novel` 排空，再在 `BEGIN IMMEDIATE` 内重读 `chapters_done` 判最新；`start_novel`/`_start_novel_locked` 双重 `is_editing` 检查且 claim 与 TASKS 登记共用同一把 `_operation_lock`；`_activate`/`transition` 经 `_check_not_editing` 返回 409。正式测试 3 条（`test_edit_rechecks_latest…`、`test_edit_waits_for_claimed_worker…`、`test_edit_blocks_activation…[resume/continue]`）通过 |
| **F4** 改早章导致待批细纲 500 | 第 1 轮 `probe_stale_plan.py` 原样重跑 + redo 变体 | 改第 1 章后 `[(1,'done'),(2,'stale'),(3,'awaiting_plan_approval')]`，`approve_plan: OK`；redo 变体 `redo_plan: OK` 且重做后仍为 `awaiting_plan`。（原探针在 approve 成功后紧接着 redo 得到 409「当前状态不能执行此操作」是因为关卡已被 approve 消费，属正确行为，不是 500。）stale 语句改为 `status NOT IN ('planning','awaiting_plan_approval') AND body IS NOT NULL`；approve/redo 查不到待批行 → 409「当前没有可批准/重做的待批细纲」。正式测试 `test_early_edit_keeps_pending_plan_usable_and_missing_plan_is_409[approve/redo]` 通过 |
| **F5** 配角卡片与 knows 裁剪 | 第 1 轮 `probe_context_growth.py` MODE=realistic 原样重跑（每章加 1 条 knows、植/收伏笔、每 4 章新增 1 配角，open 伏笔固定 5） | ch30→ch60：editor +1.7%、twist_designer +2.2%、writer +1.4%、reviewer +1.3%、archivist +1.3%（第 1 轮为 +20.6% / +25.3% / +20.8%）。组件分解 ch31 vs ch61：`locked.characters` +1（原 +1199）、`C1.knows` +18（原 +1080）、`arc_summaries` +345 不变（fake 卷摘要 58 字）。MODE=plain 仍 +5.6～9.2%。四类输入：简报在 critique 初案后按 `plan.beat_sheet.characters` 重建（`deliberation.py`），写手包/审校/档案员输入都经 `trim_bible(…, beat_sheet["characters"])`，卷摘要输入也裁卡；`validate_archive(data, bible)` 与 `apply_archive` 仍传完整圣经（`schemas.py` 用 `bible["locked"]["characters"]` 校验人物 ID）。正式测试 `test_sixty_chapter_context_views…`（真实引擎 60 章，四类调用的 `locked.characters` 与 `knows≤30` 逐一断言，30/60 ≤10%）、`test_supporting_cards_and_states…`、`test_plan_named_card_reaches_all_inputs_and_archive_validation_uses_full_bible`（C2 不在卡片里仍可被档案员改状态且不触发重试）通过 |
| **F6** 自带模型运行中失效 | `probe_byok_realseam.py`：**不替换 `_single_real_call`**，走真实 `ByokBridge.resolve()`，只把 `_provider_call` 换成 fake；三角色全 byok:self，第一次 write 前把配置置为 `enabled=False` | `paused / byok_unavailable`，`last_error='请先启用可用的自带模型'`，`reserved=0`；禁用状态下 resume 再次进入同一暂停且 provider 调用增量 0；重新启用后 resume → `awaiting_end`、2 章、`last_error=None`，setup 与 ch1 decision 各只调用 1 次、spent=0。代码：`ByokUnavailable(ConfigurationError)` 在 `_with_retries` 里原样上抛，`_run` 单独捕获写 `_last_error`；`_activate` 清除旧 `_last_error`；`PATCH agents` 只在 paused/awaiting_* 允许并复用 `validate_selection`。正式测试 `test_byok_disabled_mid_run_pauses_and_reenabled_resume_reuses_steps[reenable/platform]`、`test_patch_agents_requires_pause_or_gate_and_validates_selection`、`test_internal_byok_store_failures_become_fixed_recoverable_messages[needs_reentry/unavailable]`（内部异常文案固定、不回显 Key）通过 |
| **F7** 不支持的自带模型文案 | 正式测试 `test_byok_create_preserves_the_specific_unavailability_reason` 三例 | 未启用 →「请先启用可用的自带模型」；moonshot →「小说工坊仅支持自带 Anthropic、千问或 DeepSeek」；dashscope 未知型号 →「该模型暂不支持用于小说工坊」，均 422，catalog 仍 200。`describe()` 不再吞异常，`catalog` 单独 `except ValueError` 置 `byok=None` |

## 三、O1 / O2

- **O1**：`test_budget_exact_79_and_80_percent_boundary[79/80]`，budget=10000、价目覆盖使预扣恰为 7900/8000；`>=` 口径下 8000 拒绝、7900 放行并可全退。变异 `*1.0` → `[80]` 失败、`[79]` 通过（见 1.2）。
- **O2**：`test_same_user_running_book_blocks_another_create_and_resume`：一本运行中时再建一本、resume 另一本均 409「每个用户同时只能运行一本小说」；`check_active` 在 `create` 与 `transition(resume/continue)` 的 `BEGIN IMMEDIATE` 内执行。

## 四、测试纪律与范围

- 快照 `snap-p1r1/` 与当前比对：`test_novel_p1_billing.py`（+1 import、+8 组测试）、`test_novel_p1_api.py`（+4 组）、`test_novel_p1_byok.py`（+1 import、+1 组）、`test_novel_p1_runner.py`（+4 组）全部为追加；`test_novel_p1_store.py`、`test_novel_p1_p0.py` 未动；新增 `test_novel_p1_chaos.py`。
- `test_novel_p1_context.py`：① 60 章测试由「合成圣经上的序列化长度」改为「真实引擎连跑 60 章、四类实际调用输入字符」，原有 10 条摘要/10 时间线/30 桥段/5 已回收/open 不丢/<20000/圣经不被改写/≤10% 全部保留并加严；删去 `trimmed["locked"] == bible["locked"]`——与 F5 直接矛盾，属预期。② `test_supporting_states…` 改名为 `test_supporting_cards_and_states…`，去掉 `result["locked"] == bible["locked"]`，加卡片集合与 knows 窗口断言。③ `test_full_length_arcs_and_growing_main_state…` 改名，`knows` 断言由「全量」改为「最近 30 条且原圣经仍为全量」，卷摘要 600 字与 <22000 保留。没有其他断言被删弱。
- 快照内 30 个非 P1 `test_novel_*.py` 与当前逐个 `diff -q` 一致；`git diff 820fff1 --numstat` 中没有任何 `tests/` 文件，有删除行的只有 `novel/{agent_pool,context,deliberation,fake_llm,llm_router,writing}.py`（规格允许的引擎改动）。
- 受保护文件：`backend/database.py 13/0`、`main.py 6/0`、`rate_limit.py 2/0`，六份文档 8/0、6/0、8/0、12/0、12/0、10/0；`git diff 820fff1 -- <九文件> | grep '^-[^-]'` 为空（numstat 删除列 0 作为正控）。本机监控原有行未改。
- P0 冻结：用第 1 轮复核员 B 的 `p0_compare.py` 重跑四份 dry-run（A 71/10/132、A2 61/10/122、B 109/9/161、C 5/0/17），与基线 `p0_baseline.json` 比对 steps / bodies / files 全部 True。
- 复核前后 `git status --porcelain` 一致（本文件除外）。

## 五、新发现的阻断问题

无。本轮未发现会导致用户多扣钱、丢钱或数据损坏的新问题。

## 六、可优化项（不阻断）

1. **mutR 只被一条测试杀死。** 预扣拆成两次 commit 时，混沌守恒与所有取消类测试都仍通过（`_drain` 使取消无法插入两次 commit 之间），只有 `test_reserve_statement_failure_rolls_back_refill_balance_and_book` 变红。可再加一条「`reserve()` 全程只发生一次 `commit`」的计数断言，让「单事务」这个不变量有直接的守卫。
2. `_drain` 让所有计费/落盘事务不可取消；`SQLITE_BUSY_TIMEOUT=5.0` 下极端情况关机或暂停最多多等几秒。可接受，建议写进报告的已知边界。
3. `PATCH /novels/{id}` 改 `agents`：去掉全部顾问会把 `panel_mode` 改成 `solo`，但再加回顾问不会恢复 `critique`（`PatchNovel` 没有 `panel_mode`）。P2 做前端时可一并暴露。
4. `reserve()` 的 `except CancelledError` 分支里 `self.refund(call)` 若抛 `RunNoLongerActive`，会替换掉 `CancelledError` 向上传播；资金无影响（`_run` finally 仍会 `refund_reserved`），但语义上可 `try/except` 后再 `raise` 原 `CancelledError`。
5. `transition('pause')` 不检查 `is_editing`，改稿中暂停会把书置为 paused，随后 `_rearchive` 留在 config 里等 resume 时执行；行为正确但用户看到的 `message`「最新章节正在重新归档」会与实际 paused 状态不一致。
6. 上下文增长的剩余来源只剩卷摘要（realistic 探针 +345 字符，600 字上限时 11.6–17.4%），返修报告已如实写明并交作者拍板，本轮不计。
7. 第 1 轮「可优化」里的 `recovering` 语义范围、缓存命中按全价计费、`awaiting_review` 续跑跳过审阅等均未在本轮处理，维持原建议。

## 七、复现命令

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
export BACKEND=<工作树>/backend PYTHONDONTWRITEBYTECODE=1 DASHSCOPE_API_KEY=placeholder
cd <工作树>/backend && $PY -m pytest -q -p no:cacheprovider tests/test_novel_p1_*.py   # 133 passed
cd <工作树>/backend && $PY -m pytest -q -p no:cacheprovider                            # 4893 passed, 3 skipped

cd <scratchpad>/review-p1a
for s in 7 11 23; do SEED=$s $PY probe_conservation.py | grep RESULT; done              # 3× PASS
MODE=realistic $PY probe_context_growth.py                                             # ch30->ch60 +1.3~2.2%
$PY probe_stale_plan.py                                                                # approve_plan: OK

cd <scratchpad>/review-p1c
$PY probe_cancel_window2.py                                                            # RESULT: PASS（5 窗口全 0）
for s in 5 9 17; do SEED=$s $PY probe_double_pay2.py | grep RESULT; done                # 3× PASS
$PY probe_edit_race2.py                                                                # RESULT: PASS
$PY probe_stale_plan_redo.py                                                           # redo_plan: OK
$PY probe_byok_realseam.py                                                             # RESULT: PASS
# 变异（副本 mutR / mutS / mutSD / mutO1，各自 backend/ 下）
$PY -m pytest -q -p no:cacheprovider tests/test_novel_p1_billing.py tests/test_novel_p1_chaos.py   # 1 / 3 / 5 failed
(cd mutO1 && $PY -m pytest -q -p no:cacheprovider tests/test_novel_p1_billing.py)                   # 1 failed（[80]）
# 正控
BACKEND=<scratchpad>/review-p1c/mutSD SEED=5 $PY probe_double_pay2.py                 # double-paid step 出现
# P0 独立比对
(cd <工作树>/backend && PYTHONPATH=. $PY <scratchpad>/review-p1b/p0_compare.py <scratchpad>/review-p1c/p0_current_r2.json)
```
