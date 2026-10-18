# 第 2 轮独立复核报告（R2 三项 · 写歌 P0）

复核日期：2026-10-18 · 复核对象：R2 完整工作区（基线 `0d6560e` + R1 + R2 增量）
验收依据：`r2-fixes.md`、`02-spec.md` §7.2 两处「R2 修订」、§8.2「R2 修订」、§15 R2 条目
方式：只读代码核对 + 运行测试 + 6 个变异实验 + 1 个临时并发探针（已删除）。`03-report.md`「R2 返修」一节只当线索，所有结论均以本轮实测为准。

## 1. 结论

**通过。** 三项返修均按 `r2-fixes.md` 与规格 R2 条文实现并有测试证明力（6 个变异全部被杀）；未发现三项范围内必须修复的错误，未破坏 R1 不变量；全量测试 0 failed。

## 2. 三项逐条核验

### 2.1 退款对账 `reconcile_refunds` —— ✅ 符合要求

**实现**（`backend/song/jobs.py`）：

- `:48` `REFUNDABLE_TERMINAL_STATUSES = ("failed", "rejected", "uncertain", "expired")`，注释明确 `succeeded` 与在途状态不碰。
- `:454–486` `reconcile_refunds()`：SELECT 条件为 `status IN (四终态) AND billing_state = 'reserved' AND EXISTS(SELECT 1 FROM users WHERE username = song_versions.owner_username)`（`:468–473`），逐行调用既有 `refund_version` 并计数返回；查询异常打印固定 `[song] code=reconcile_failed` 后返回（`:476–478`），单版本退款异常打印同一固定码后继续下一个（`:484–485`）；两处均不打印异常正文、不外抛。
- **只退一次 / 并发安全**：`refund_version`（`:415–451`）在 `BEGIN IMMEDIATE` 事务内先 `UPDATE … SET billing_state='refunded' WHERE id=? AND billing_state='reserved'`，`rowcount != 1` 即返回 False，只有改到 1 行才加回草莓。对账与轮询器错误路径退款并发时，写事务串行化 + 条件更新保证同一版本只退一次；对账的 SELECT 读到过期快照也无害（refund_version 在自己事务内重查）。实测：既有 `test_refund_is_idempotent_under_concurrency`（两个并发 `refund_version` → `[False, True]`、余额恰 100）通过；本轮另写临时探针（30 个 `failed+reserved` 版本，每版 `refund_version` 与 `reconcile_refunds` 并发）→ 余额恰为 30×30、全部 `refunded`、再对账返回 0（探针文件已删除，见 §5 说明）。
- **启动调用位置**：`backend/main.py:126–133`，`reconcile_refunds()` 位于 `if song_agent_enabled():` 分支内、`recover_on_startup()` 之后，仅新增这一行（diff-of-diffs 证实 main.py 相对 R1 只有 `+        await song_jobs.reconcile_refunds()` 一行）。开关关闭时不调用：`test_lifespan_song_wiring_only_when_enabled` 断言关闭时 `calls == []`、开启时 `calls == ["drain", "orphans", "recover", "reconcile"]`。
- **轮询器 60 秒一次**：`jobs.py:804–822` `run_poller` 在 `time.monotonic() - last_cleanup >= 60` 分支里、`drain_cleanup_queue` 之后调用，两项各自 try/except 互不影响，失败也推进 `last_cleanup` 避免热循环。

**测试**（`backend/tests/test_song_jobs.py`，与 r2-fixes §1 五条一一对应）：

- `:858` `test_reconcile_refunds_terminal_reserved_once`：4 条终态+reserved、余额 0 → 返回 4、余额 120、全部 `refunded`；再调返回 0、余额不变。
- `:887` `test_reconcile_refunds_ignores_non_terminal_and_succeeded`：`succeeded/running/downloading`+reserved 不动，仅 `failed` 退回。
- `:920` `test_reconcile_refunds_skips_missing_user`：删用户后返回 0、不退款、不报错。
- `:940` `test_reconcile_refunds_after_rejected_refund_failure`：monkeypatch 首次 `refund_version` 抛异常 → `submit_version` 抛出后版本 `rejected+reserved`、余额 70；`reconcile_refunds()` 补退 → `refunded`、余额 100。
- `:1181` `test_lifespan_reconcile_refunds_after_recover`：真实 `main.lifespan` + 真实 `init_db`，预置 `uncertain+reserved` 启动后即 `refunded`。

**证据**：`cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py -rs` → `301 passed, 35 warnings in 4.72s`（0 failed、0 skipped）。

### 2.2 镜子轮不加写歌提示 —— ✅ 符合要求

- **实现**：`backend/services/claude_agent.py:415–418` 拼接条件改为 `if _song_turn_enabled(ctx, state) and mode != "mirror":`。全仓 `SONG_MODE_PROMPT` 只有这一个拼接点（grep 证实，另两处引用都在测试）；`_song_turn_enabled` 是纯读取（无副作用），其余引用点（`client_tools_for_turn`、`_song_project_block`、`:439` 工具名集合）镜子轮均不可达——镜子分支在 `:421–427` 提前 return。因此镜子轮从提示词、工具到消息与写歌关闭时完全一致。
- **逐字节相同的传导**：真实镜子流 `chat_service.py:1187` 直接以 `state.sys_prompt_final` 作 system 消息，所以测试对 `sys_prompt_final` 的逐字节断言即等价于对镜子模型请求的断言。
- **测试**：`backend/tests/test_song_agent_tools.py:964` `test_mirror_turn_does_not_add_song_mode_prompt`——同一 harness、假 `stream_mirror` 记录 `state.sys_prompt_final`：写歌开启时不含「【写歌模式】」与 `SONG_MODE_PROMPT`、`not h.requests`（不开 agent 流）；随后仅把 `FIONA_SONG_AGENT` 置 `0` 再跑一遍，断言两次记录文本 `==`（逐字节）。配置为调用时读取（`song/config.py:_flag`），中途改开关立即生效，对比有效。`:998` `test_friend_turn_with_song_on_contains_mode_prompt_once` 为正控：friend 轮 system 文本含 `SONG_MODE_PROMPT` 恰好一次——变异 2b 证实该正控能区分（见 §5）。
- **R1 不变量未破坏**：非镜子轮拼接仍在 `_final_system_prompt` 的入参里（`claude_agent.py:419–420`），基础安全规则仍在最后一条 system 消息末尾且只出现一次；R1 四个不变量测试 `test_switch_on_changes_tools_prompt_and_user_message`（`:762–766` 断言 endswith safety、count==1、写歌提示在 safety 之前）、`test_song_mode_prompt_stays_before_trailing_safety_rules`、`test_song_mode_prompt_stays_before_trailing_system_safety`、`test_layout_check_rejects_song_prompt_appended_after_safety` 全部通过；`tests/test_beta_safety.py`、`tests/test_claude_agent_runtime.py`、`tests/test_novel_chat.py` 回归 → `354 passed`（0 failed）。

### 2.3 轮询单版本兜底 —— ✅ 符合要求

- **`provider.query` 非 `PollError` 异常**：`jobs.py:697–748`，每版本处理体包在 `try/except Exception` 里；异常时打印固定 `[song] code=poll_unexpected`（不含异常正文），`_postpone_version(version_id, current + 10)`（推迟自身再套 try/except，二次失败也不打断整轮），`continue` 处理下一版本；整个 `poll_once` 不外抛（`_due_versions` 查询失败也有兜底 `:690–695`）。`except Exception` 不拦 `CancelledError` 等 `BaseException`，任务取消语义未被吞。
- **`PollError` 原行为不变**：`:717–722` 内层 `except volc.PollError` 先于外层兜底命中，只推迟 10 秒、不打印、不改状态、不退款。`test_poll_error_only_postpones` 通过；本轮以 `-s` 运行该测试，stdout/stderr 中 `[song]` 行数为 0，证实 PollError 不打印错误码。
- **下载转码非 `MediaError` 异常**：`jobs.py:644–654`，`_fail_version(version_id, 'download_unexpected', GENERIC_FAILURE_MESSAGE, ('downloading',))` 后 `refund_version`（守卫保证只退一次）；`MediaError` 原分支（`:638–643`）不变；异常正文不进日志、不进 `failure_message`（固定文案）。
- **测试**：`:767` `test_poll_unexpected_query_error_postpones_and_continues`——A 抛 `RuntimeError("boom")`、B 正常 running：`poll_once(now)` 不抛，A 状态仍 `submitted` 且 `next_poll_at == now+10`，B `progress=42`，`provider.queried == ["task-a", "task-b"]`（证明继续处理），stdout 无 `boom`、含 `code=poll_unexpected`。`:657` `test_poll_download_unexpected_marks_failed_and_refunds`——版本 `failed`、`failure_code='download_unexpected'`、固定文案、`billing_state='refunded'`、余额退回（70→100），二次 `refund_version` 返回 False，stdout/stderr 不含 `download boom`。
- **非阻断观察**（不构成必修项）：双重故障窗口——若兜底里的 `_fail_version` 写库本身再失败（如 DB 锁超时），版本停在 `downloading+reserved`，既不会被再次轮询（`_due_versions` 只取 submitted/running）也不属于对账范围（非终态），要等进程重启 `recover_on_startup` 把 `downloading` 翻回 `running` 重查自愈。该窗口与 R2 之前完全一致（R2 只把它收窄），钱处于 reserved 非损失，且重启恢复已有测试覆盖（`test_recover_on_startup_handles_each_status`）。

## 3. 必须修复项

无。

## 4. 其他发现

无（本轮未发现三项之外会造成资损或越权的新问题）。

白名单合规性顺带核实：以 `.review/r1-tracked.diff` 与当前 `git diff 0d6560e` 做 diff-of-diffs，R1→R2 跟踪文件改动仅限 `CLAUDE.md`、`docs/ARCHITECTURE.md`、`backend/main.py`（+1 行）、`backend/services/claude_agent.py`（条件行+注释）及作者自改的 `02-spec.md`（三处「R2 修订」与 §15 R2 条目，内容与实现一致）；跟踪文件集合无增减，`4b45346` 时已存在的测试文件零改动（`test_song_jobs.py`/`test_song_agent_tools.py` 经 `git ls-tree 4b45346` 证实当时不存在，属白名单内新增）。`03-report.md` 所报计数与实测一致：song 301（其中 jobs 31 + agent_tools 22 = 53 实测吻合）、全量总数 7531（复核环境 7373 passed + 158 skipped，跳过全部为前端依赖缺失的 studio/novel/claude 前端测试，属复核副本环境问题，与 R2 无关）。

## 5. 变异实验表

规则执行：每个变异先备份原文件并记录 md5，改坏后运行测试（除 2b 外均跑满全部 9 个 `tests/test_song_*.py`，301 个用例），随后从备份恢复并以 md5 核对与变异前一致。无任何变异存活。

| # | 位置 | 改法 | 结果（被哪个测试杀死） |
|---|---|---|---|
| 1a | `song/jobs.py:48` | `REFUNDABLE_TERMINAL_STATUSES` 去掉 `"uncertain"` | 变红：`test_reconcile_refunds_terminal_reserved_once`（返回 3≠4）、`test_lifespan_reconcile_refunds_after_recover`；2 failed / 299 passed。已杀死 |
| 1b | `song/jobs.py:468–473` | 对账 SELECT 去掉 `AND EXISTS(users…)` 子句 | 变红：`test_reconcile_refunds_skips_missing_user`（对已删用户退款）；1 failed / 300 passed。已杀死 |
| 2 | `services/claude_agent.py:415` | 条件改回 R1 的 `if _song_turn_enabled(ctx, state):`（镜子轮也拼提示） | 变红：`test_mirror_turn_does_not_add_song_mode_prompt`；1 failed / 300 passed。已杀死 |
| 2b | `services/claude_agent.py:415` | 条件前加 `False and`（任何轮都不拼，验证正控区分力） | 变红 5 个：`test_friend_turn_with_song_on_contains_mode_prompt_once`（正控）+ R1 不变量测试 `test_switch_on_changes_tools_prompt_and_user_message`、`test_song_mode_prompt_stays_before_trailing_safety_rules`、`test_song_mode_prompt_stays_before_trailing_system_safety`、`test_layout_check_rejects_song_prompt_appended_after_safety`（test_song_agent_tools.py：5 failed / 17 passed）。已杀死 |
| 3a | `song/jobs.py:741–748` | `poll_once` 单版本兜底改为 `print` 后 `raise`（整轮外抛） | 变红：`test_poll_unexpected_query_error_postpones_and_continues`（RuntimeError 逃出 `poll_once`）；1 failed / 300 passed。已杀死 |
| 3b | `song/jobs.py:644` | `_handle_succeeded` 的兜底 `except Exception:` 改成 `except volc.PollError:`（RuntimeError 永不命中） | 变红：`test_poll_download_unexpected_marks_failed_and_refunds`（版本停在 downloading、未退款）；1 failed / 300 passed。已杀死 |

**并发探针**（非变异）：临时文件 `tests/test_r2_probe_tmp.py`（复核后已删除，最终 `git status --porcelain` 与会话开始时逐行一致）——30 个 `failed+reserved` 版本，每版并发执行 `refund_version` 与 `reconcile_refunds`：终态余额恰 900（不多退不少退）、全部 `refunded`、再次对账返回 0。1 passed。

## 6. 回归记录

| 命令（均在 `backend/` 下，`env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider …`） | 结果 |
|---|---|
| 9 个 `tests/test_song_*.py` | `301 passed, 35 warnings in 4.72s` |
| `tests/test_beta_safety.py tests/test_claude_agent_runtime.py tests/test_novel_chat.py` | `354 passed, 33 warnings in 2.55s` |
| 全量（两次，均 `-rs`） | `7373 passed, 158 skipped, 35 warnings in 243.89s / 257.13s`，0 failed；158 个跳过全部为「frontend dependencies unavailable: typescript/react…」类模块级跳过（复核副本无完整前端依赖，环境性，与 R2 无关；7373+158=7531 与实现方全量总数一致） |

工作区自查：结束时 `git status --porcelain` 与 `git diff 0d6560e --stat` 均与会话开始时完全一致，除本报告外无任何新增/修改文件。
