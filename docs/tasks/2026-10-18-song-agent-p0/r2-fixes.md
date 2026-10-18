# R2 返修单（写歌 P0，复核可优化项中由用户决定修复的 3 项）

独立复核已通过、无必修项。作者决定再修下面 3 项后合并。`02-spec.md` 已同步修订：§7.2 两条「R2 修订」、§8.2 一处「R2 修订」、§15 R2 条目——**先读这几处**。

工作方式不变（`02-spec.md` §0）：可用工作流并发，但本轮改动集中在两个源文件，按下表拆即可；不得改任何既有测试（`4b45346` 时已存在的文件）；新测试只加在 `backend/tests/test_song_jobs.py` 与 `backend/tests/test_song_agent_tools.py`；不提交、不 stash、不切分支；不要修改 `02-spec.md`、`01-brief.md`、`r1-gate-fixes.md`、本文件、`04-review.md`。

**本轮白名单（只许改这些）**：`backend/song/jobs.py`、`backend/main.py`（仅 lifespan 里加一行调用）、`backend/services/claude_agent.py`、`backend/tests/test_song_jobs.py`、`backend/tests/test_song_agent_tools.py`、`CLAUDE.md` 与 `docs/ARCHITECTURE.md`（只补与这 3 项相关的句子）、`docs/tasks/2026-10-18-song-agent-p0/03-report.md`（追加「R2 返修」一节）。

| agent | 文件 |
|---|---|
| J 计费兜底 | `song/jobs.py`、`main.py`、`tests/test_song_jobs.py` |
| K 镜子轮 | `services/claude_agent.py`、`tests/test_song_agent_tools.py` |
| L 文档 | `CLAUDE.md`、`docs/ARCHITECTURE.md` |

## 1. 退款对账（`song/jobs.py` + `main.py`）

- 新增 `async def reconcile_refunds() -> int`：查出 `status IN ('failed','rejected','uncertain','expired') AND billing_state = 'reserved'` 且 `EXISTS(SELECT 1 FROM users WHERE username = owner_username)` 的版本 id，逐个调用现有 `refund_version`（它本身同事务、只退一次），返回实际退回的个数。`succeeded`、`queued/submitting/submitted/running/downloading` 一律不碰。单个版本退款抛异常时打印固定错误码（如 `[song] code=reconcile_failed`）并继续下一个。
- `main.py` lifespan 里，在 `await song_jobs.recover_on_startup()` 之后加 `await song_jobs.reconcile_refunds()`（仍在 `song_agent_enabled()` 分支内）。
- `run_poller` 每 60 秒那次在 `drain_cleanup_queue` 之后也调用 `reconcile_refunds`（各自 try/except，互不影响）。
- 新测试（`test_song_jobs.py`）：
  - 造 4 条版本，状态分别为 `failed/rejected/uncertain/expired`，均 `billing_state='reserved'`、`strawberries=30`，用户初始余额 0 → 调 `reconcile_refunds()` 返回 4、余额 120、四条都变 `refunded`；**再调一次**返回 0、余额仍 120。
  - 同一用户再造 `succeeded`+`reserved`（人为异常数据）、`running`+`reserved`、`downloading`+`reserved` 各一条 → `reconcile_refunds()` 不动它们（`billing_state` 仍 `reserved`，余额不变）。
  - 用户已删除（`users` 里无此行）的 `failed`+`reserved` 版本 → 不退款、不报错。
  - 模拟「标终态成功、退款失败」：让一次提交被拒后 `refund_version` 抛异常（monkeypatch 只在第一次调用时抛），断言版本是 `rejected`+`reserved`；随后 `reconcile_refunds()` 把它退回。
  - lifespan：开关打开、轮询器换成空转时，启动应用（与现有开关开启测试相同的夹具写法）后，预先放好的 `uncertain`+`reserved` 版本已被退回。

## 2. 镜子轮不加写歌提示（`services/claude_agent.py`）

- 现状：R1 把 `SONG_MODE_PROMPT` 拼进 `base_prompt` 的时机在 `if mode == "mirror":` 分流之前，镜子轮的 `state.sys_prompt_final` 也带上了写歌提示（镜子轮不带任何工具）。
- 改法：只在 `_song_turn_enabled(ctx, state) and mode != "mirror"` 时拼接；镜子轮的 `state.sys_prompt_final` 必须与写歌关闭时逐字节相同。
- 新测试（`test_song_agent_tools.py`，参照 `tests/test_claude_agent_runtime.py:190` `test_mirror_uses_existing_branch_and_never_opens_agent` 的写法：把 `detect_mode` 换成返回 `"mirror"`、把 `stream_mirror` 换成记录 `state.sys_prompt_final` 的假实现）：
  - 写歌开启（用户在白名单）+ 镜子模式：记录到的 system 文本不含「【写歌模式】」，且与同一输入在写歌关闭时记录到的文本逐字节相等。
  - 正控：同样开启写歌但 `detect_mode` 返回 `"friend"` 时，发给模型的 system 文本含 `SONG_MODE_PROMPT` 恰好一次（证明上一条断言能区分）。

## 3. 轮询单版本兜底（`song/jobs.py`）

- `poll_once`：对每个版本的处理加兜底。`provider.query` 抛出 `volc.PollError` 以外的任何异常 → 打印固定错误码（如 `[song] code=poll_unexpected`，不打印异常正文）→ `_postpone_version(version_id, current + 10)` → 继续处理下一个版本；整个 `poll_once` 不向外抛。
- `_handle_succeeded`：`media.download_and_store` 抛出 `MediaError` 以外的异常 → 按 `failure_code='download_unexpected'`、文案 `GENERIC_FAILURE_MESSAGE` 把 `downloading` 标为 `failed` → `refund_version`。
- 新测试（`test_song_jobs.py`）：
  - 两个到期版本 A、B；假供应商对 A 的 `query` 抛 `RuntimeError("boom")`、对 B 正常返回 running → `poll_once(now)` 不抛；A 的 `next_poll_at == now + 10` 且状态不变；B 的 `progress` 被更新。捕获 stdout，断言不含 `boom`。
  - 假供应商返回 succeeded，`download_and_store` 被 monkeypatch 成抛 `RuntimeError` → 版本 `failed`、`failure_code == 'download_unexpected'`、余额退回 N、`billing_state='refunded'`；再调一次 `refund_version` 返回 False。

## 完成后

- `backend/` 下跑 `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py` 与全量 `-rs`，都要 0 failed、0 skipped（本机若报 `Invalid port: ':1]'`，命令前加 `env -u NO_PROXY -u no_proxy`）。本轮不改前端，不需要跑前端构建。
- 在 `03-report.md` 末尾追加「R2 返修」一节：三项各改了什么、新增测试名、正控说明、上面命令末尾计数行原文。
