# 验收后小单：三条收紧

讨论群第一期已通过三轮独立复核并合入 main（提交 `1b7e226`、`19e4bd1`）。作者验收时同意把第 3 轮复核 `docs/tasks/2026-11-14-agent-group/04-review-r3.md` 第 4 节的三条不阻断建议做掉。依据：`02-spec.md`「v1.2 修订」新增的第 13、14 条，请先读这两条和 `04-review-r3.md` 第 4、6 节。

工作区现在是干净的（全部已提交），本单的改动就是 `git diff` 能看到的全部内容。

## 一、规矩

1. 只允许改：
   - `backend/discuss/store.py`、`billing.py`、`service.py`（A 条）、`backend/discuss/runner.py`（B 条）；
   - `backend/tests/test_discuss_*.py`；
   - 新报告 `docs/tasks/2026-11-14-agent-group/impl/report-followup.md`。
2. 不许动：其他实现文件（`engine.py`、`avatar.py`、`roles.py`、`research.py`、`schemas.py`、`config.py`、`backend/novel/`、`backend/agent_store.py` 等）、`conftest.py`、任务目录下的规格、复核、返修单与 `verify/`。
3. 已有用例的断言不许放宽或删除。如果某条已有用例因为「退款并进了状态事务」而需要调整造数或观察点（不是放宽断言），可以改，但要在报告里逐条列出改了什么、为什么。其余只追加。
4. 不装依赖，不读 `.env`，不 commit / stash / checkout / reset，不访问外网，不调用真实模型。
5. 本单改动不大，可以由你直接完成；要拆分的话按文件不重叠，用工作流（workflow 工具）并行，任务说明自包含并写明不得再派生。
6. 你实测到的事实优先于本单的说法；不符就停下来在报告里说明。只有影响「实现什么」的矛盾才停；怎么实现、怎么验证自己定并写明理由。任何情况不回滚已完成的工作。

## 二、要做的事

### A. 退残留预扣并进状态事务（规格 v1.2 第 13 条）

- 现状：`service.start`、`resume`、`continue_group`、`accept`、`close` 先提交改状态的事务，再单独调用一次 `DiscussBilling(...).refund_reserved()`。两步之间有窗口：退款失败时状态已经改了；`accept` 之后几毫秒内如果作者插话并继续，退款会把新一轮在途的预扣也退掉。
- 改法：
  - 抽出一个「在给定连接上退还某个群全部 reserved 预扣」的函数（余额加回、群的 `reserved_strawberries` 归零、步骤标成已退），放在 `store.py` 或 `billing.py` 由你定；`DiscussBilling._refund_reserved_transaction` 与 `store.delete_group` 里的退款改成复用它，行为不变。
  - 上述五个接口在各自改状态的那个 `run_write` 事务里调用它，去掉事务之后那次单独的 `refund_reserved()`。
  - 已经是 `closed` 的群再次 `close`：在一个受保护的写事务里只做退款。
  - `runner.cancel_group`、`_cleanup`、恢复流程里的 `refund_reserved()` 不动。
- 新用例（付费模式）：
  - 原子性：让那个退款函数抛异常，调用 `start`（或 `resume`）：接口报错，群的状态、令牌、预扣和余额都与调用前相同，没有起后台任务。至少覆盖 `start` 和 `accept` 两个接口。
  - 已是 `closed` 且留有残留预扣的群：`close` 一次退回，再 `close` 一次余额不再变（第 3 轮复核的 Q4、Z2）。
- 自检：把退款挪回事务之外，原子性用例必须失败；去掉「已是 closed 时也退」，对应用例必须失败。已有的五条 `*_refunds_stale_reservation*` 用例必须仍然通过。

### B. 取消优先于同时发生的失败（规格 v1.2 第 14 条）

- 现状：`runner._run` 里，任务已经收到取消、却以别的异常结束时，会按那个异常写停止原因（比如 `failed/error`、`paused/insufficient_strawberries`），与作者点的「暂停」不符。
- 改法：`_run` 在处理 `CancelledError`、`RunNoLongerActive` 以外的任何异常之前，先看当前任务是否已收到取消（`asyncio.current_task().cancelling()` 大于 0）；是则不写停止原因，改为抛出 `CancelledError`（`from` 原异常）。`finally` 里的收尾不变。
- 新用例（复现法见 `04-review-r3.md` 第 6 节 Q2、Q5）：
  - 让一次受保护的写库（例如写方案消息）阻塞后抛 `sqlite3.OperationalError`，期间调用暂停：最终 `paused/user`（现在是 `failed/error`）。
  - 让分身读库阻塞后抛余额不足，期间调用暂停：最终 `paused/user`（现在是 `paused/insufficient_strawberries`）。
  - 对照：没有取消时，同样的异常仍然写原来的停止原因（已有用例覆盖的就不用重复）。
- 自检：去掉这处判断，两条新用例必须失败。

### C. 一条用例（第 3 轮复核第 4 节第 6 点）

目录接口 `GET /discuss/catalog` 返回的 `notice` 以「联网搜索按次另扣草莓，与成员用哪个模型无关。」结尾。放 `tests/test_discuss_api.py`。

## 三、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过。
2. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 讨论群用例总数，0 失败、0 跳过。
3. 自检表：A、B 各条「改坏后由哪条用例靠断言失败发现」，一行一条（必须是 `failed`，不能是 `error` 或超时）。
4. `git status --porcelain --untracked-files=all`：只有第一节第 1 条允许的文件有变动，另加规格作者已放好的 `02-spec.md`（第 13、14 条）和本单。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-followup.md`，不写本机绝对路径：A–C 逐条做了什么、改了哪些函数、调整过哪些已有用例及理由、新用例的函数名、自检表、验收四条的命令与输出摘要、没做完或需要人工确认的地方。
