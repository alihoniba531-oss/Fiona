# 复核返修第 2 轮实施报告

依据 `02-spec.md` v1.2（第 1、2、4 条及新增第 11、12 条）与 `04-review-r2.md` 第 3–6 节。只改 `engine.py`、`service.py` 与四个测试文件，追加测试，不改已有用例；没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`，没有访问真实模型/搜索。

## 拆分表

本单改动小，按返修单允许由主代理直接完成，没有派子代理。

| 执行者 | 文件 | 内容 | 结果 |
|---|---|---|---|
| 主代理 | `backend/discuss/engine.py` | A：`_avatar_try` 在取消已被请求时交还 `CancelledError` | ok |
| 主代理 | `backend/discuss/service.py` | B：accept/close 后 `refund_reserved`；C：名字超长文案 | ok |
| 主代理 | `backend/tests/test_discuss_runner.py` | A 的 M5 两阶段、Y1 | ok |
| 主代理 | `backend/tests/test_discuss_billing.py` | A 的付费 M5、B 的 accept/close | ok |
| 主代理 | `backend/tests/test_discuss_api.py` | Y3、Y6 | ok |
| 主代理 | `backend/tests/test_discuss_docs.py` | Y5 | ok |
| 主代理 | `impl/report-review-r2.md` | 本报告 | ok |

`avatar.py`、`runner.py`、`store.py`、`billing.py`、`backend/novel/`、`agent_store.py`、`conftest.py`、`verify/` 均未改。

## A–D 逐条

### A. 分身步骤不得吞掉取消（M5）

`engine._avatar_try` 的 `except Exception as error` 分支开头新增：

- 当 `asyncio.current_task()` 非空且 `.cancelling() > 0` 时，`raise asyncio.CancelledError() from error`；
- 不发「分身这次没能发言」的跳过通知，也不继续后续步骤；
- 其余普通异常仍按原逻辑发 notice 并继续。

新用例：

- `test_pause_during_avatar_memory_error_keeps_cancellation`（参数化 `planning`、`running`）
  - 把 `agent_store.get_memory_snapshot` 换成「第一次调用阻塞到放行，然后抛 `sqlite3.OperationalError`；之后调用原函数」。
  - 立项阶段：直接 `runner.start_group`，等 brief 的 memory 查询阻塞后发起暂停，放行后断言 `paused/user`、没有 skip notice。
  - 开工后阶段：先跑到 `awaiting_start` 再 `service.start`，让第 1 轮 view 的 memory 查询阻塞；暂停后断言 `paused/user`，没有 `verdict` 消息。
- `test_pause_during_paid_avatar_memory_error_keeps_spent`（付费）
  - `paid_planning(avatar=True)` 后启动第 1 轮，view 读记忆阻塞时暂停；断言暂停返回 `paused/user`，暂停后的 `spent` 等于阻塞时的 `spent`，`reserved == 0`，余额等于 `10000 - spent`。

自检：去掉 `engine.py` 这段取消判断后，上述 3 条（runner 两个参数 + billing 一条）全部 `failed`。

### B. accept 与 close 也退残留预扣

`service.accept` 在状态事务提交后调用 `billing.DiscussBilling(username, group_id).refund_reserved()`；`service.close` 同样在正常关闭事务后调用，已 `closed` 的早返回分支也补了一次退款。

新用例：

- `test_accept_refunds_stale_reservation`
- `test_close_refunds_stale_reservation`

两条都用付费模式造出「群停在可接受/可结束状态、残留一条 reserved 步骤、余额已被预扣」的状态；调用后断言旧步骤 `interrupted/refunded`、`reserved == 0`、余额恢复到 `10000 - spent`。

自检：分别去掉 accept、close 的退款调用后，对应用例各自 `1 failed`。

### C. 文案

`service._parse_identities` 的超长名字文案从「固定席位的名字需要 1–12 字」改为「固定席位的名字最多 12 字」。全库搜索旧文案，只有实现这一处；测试里没有断言旧文案。

### D. 四条缺口

- **Y1**：`test_cancelled_start_group_does_not_clear_other_token`。群上已有 `other-token`，在认领事务提交处设闸门并取消 `start_group`；断言调用方收到 `CancelledError`，`other-token` 原样保留，`TASKS` 没有该群。
- **Y3**：`test_detail_calls_avatar_display_name_only_once`。带分身群取一次详情，monkeypatch `avatar.display_name` 计数，断言恰好 1 次；实现已由 `detail` 单次取名字并传给 `_avatar_member`。
- **Y5**：`test_privacy_notice_and_docs_include_search_fee_sentence`。断言 `roles.PRIVACY_NOTICE` 以「联网搜索按次另扣草莓，与成员用哪个模型无关。」结尾，且 README、ARCHITECTURE、CLAUDE 三份文档都含这句。
- **Y6**：`test_create_group_rejects_duplicate_names_with_role_override`。两个 `role` 成员改名成同一个名字，建群 422。

自检四条各自 `1 failed`。

## 自检表

在系统临时目录的克隆里逐条改坏、运行、还原并删除克隆；失败均为 `failed`，不是 `error`/超时。

| 项 | 改坏方式 | 由哪条用例发现 | 失败摘要 |
|---|---|---|---|
| A/M5 | 去掉 `_avatar_try` 的取消判断 | `test_pause_during_avatar_memory_error_keeps_cancellation`（2 参数）、`test_pause_during_paid_avatar_memory_error_keeps_spent` | `3 failed in 3.46s` |
| B/accept | 去掉 accept 后的 `refund_reserved` | `test_accept_refunds_stale_reservation` | `1 failed in 0.89s` |
| B/close | 去掉 close 后的 `refund_reserved` | `test_close_refunds_stale_reservation` | `1 failed in 0.90s` |
| D/Y1 | `release_claim` 去掉 `AND run_token=?` | `test_cancelled_start_group_does_not_clear_other_token` | `1 failed in 0.86s` |
| D/Y3 | `detail` 不把 `name=avatar_name` 传给 `_avatar_member` | `test_detail_calls_avatar_display_name_only_once` | `1 failed, 45 warnings in 2.09s` |
| D/Y5 | 隐私说明删掉新句 | `test_privacy_notice_and_docs_include_search_fee_sentence` | `1 failed in 0.03s` |
| D/Y6 | 重名检查只对 custom 成员生效 | `test_create_group_rejects_duplicate_names_with_role_override` | `1 failed, 45 warnings in 1.22s` |

## 验收

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

结果：`200 passed, 45 warnings in 15.17s`，退出码 0，0 跳过。

各文件收集数：api 38、billing 30、docs 20、engine 49、runner 26、schemas 33、structure 4，合计 200。

### 2. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8552 passed, 47 warnings in 405.65s (0:06:45)`，退出码 0，0 失败、0 跳过。基线 8352 + 200 = 8552；全量收集数 8552。

说明：第一次全量出现一次既有 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]` 的时序失败（`8551 passed, 1 failed`）；单跑通过，第二次全量 8552 全过。该测试不属于讨论群，未改动。

### 3. 自检

见上表：A、B、D 共 7 个改坏点，全部由断言失败发现，无 `error`/超时。

### 4. 改动范围

`git status --porcelain --untracked-files=all` 当前共 61 条。

- 与本次派单时相比，只多出本报告；`04-review-r2.md`、`10-fix-review-r2.md` 是规格作者在返修单派出前提供的材料。
- 内容变动只在允许的 `backend/discuss/engine.py`、`service.py`、`backend/tests/test_discuss_runner.py`、`test_discuss_billing.py`、`test_discuss_api.py`、`test_discuss_docs.py`。
- `avatar.py`、`runner.py`、`store.py`、`billing.py`、`backend/novel/`、`agent_store.py`、`conftest.py`、`verify/` 未改。
- `CLAUDE.md` 仍为 68,497 字节；已跟踪文件的 `git diff --stat` 未变。

## 未完成或需要人工确认

1. M5 的取消判断放在 `engine._avatar_try`，可兜住分身步骤里 `_drain` 吞取消后再抛普通异常的情况；未改 `NovelBilling._drain` 本身（在 `backend/novel/`，本单禁止改）。
2. B 的 accept/close 退款在状态事务提交之后单独执行，沿用已有 start/resume/continue 的同一模式；没有把退款并进状态事务。复核把它列为不阻断的建议，本单未扩大改动范围。
3. C 的文案没有专门用例；现有用例没有任何位置断言旧文案，变更不影响其他测试。
4. Y5 检查的是三份文档和 `roles.PRIVACY_NOTICE`；目录接口直接使用同一个 `PRIVACY_NOTICE`，没有另写路由级断言。
