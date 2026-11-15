# 复核返修单 第 2 轮：多智能体讨论群第一期

依据：`docs/tasks/2026-11-14-agent-group/02-spec.md` v1.2（开头「v1.2 修订」的第 1、2、4 条措辞有调整，新增第 11、12 条，请重读这一节）和第 2 轮复核 `docs/tasks/2026-11-14-agent-group/04-review-r2.md`。

第 2 轮复核的结论：M1–M4 都已修好；本轮新代码里有 1 条必须修复（M5），规格作者已独立复现属实。本单处理 M5，并把复核列出的几处小缺口一并补上。先读 `04-review-r2.md` 第 3、4、5、6 节。

## 一、规矩

1. 只允许改：
   - `backend/discuss/engine.py`（A 条）、`backend/discuss/service.py`（B、C 条）；
   - `backend/tests/test_discuss_runner.py`、`test_discuss_billing.py`、`test_discuss_api.py`、`test_discuss_docs.py`（只追加，不改已有用例）；
   - 新报告 `docs/tasks/2026-11-14-agent-group/impl/report-review-r2.md`。
2. 不许动：其他实现文件（包括 `avatar.py`、`runner.py`、`store.py`、`billing.py`、`backend/novel/`、`backend/agent_store.py`）、`conftest.py`、任务目录下的规格、复核、返修单与 `verify/`。
3. 其余规矩同 `08-fix-review-r1.md` 第一节第 3–6 条。本单改动不大，可以由你直接完成；要拆分的话仍按文件不重叠。

## 二、要做的事

### A. 分身步骤不得吞掉取消（复核 M5，v1.2 第 2 条）

- 现象：`avatar.py` 里受保护的读库调用如果在「任务已被取消」的同时以普通异常结束，`engine._avatar_try` 的 `except Exception` 会把它当成「分身这次没能发言」跳过，任务接着往下跑。结果是暂停被无视，暂停之后还在扣费。规格作者的复现：立项阶段让读私有记忆阻塞后抛 `sqlite3.OperationalError`，期间调用暂停，接口返回 200 但状态是 `awaiting_start`，消息里多了一条跳过通知。
- 改法：`engine._avatar_try` 的 `except Exception` 分支开头，如果当前任务已经收到取消请求（`asyncio.current_task()` 不为空且 `.cancelling()` 大于 0），就 `raise asyncio.CancelledError() from error`：不发跳过通知，不继续流程。其余行为不变。
- 新用例（写法见复核第 5 节与第 6 节 P9、P10）：
  - `tests/test_discuss_runner.py`，参数化两个阶段（立项时的 brief、开工后第 1 轮的 view）：把 `agent_store.get_memory_snapshot` 换成「第一次调用阻塞到放行，然后抛 `sqlite3.OperationalError`；之后调用原函数」；阻塞期间发起暂停，随后放行。断言暂停后状态是 `paused/user`，之后没有新的消息和步骤（立项阶段没有跳过通知；开工后阶段没有 `verdict`）。
  - `tests/test_discuss_billing.py`，付费模式：同样阻塞在第 1 轮 view 的读库上再暂停。断言状态 `paused`，且暂停返回之后的 `spent` 等于阻塞那一刻的 `spent`，`reserved == 0`。
- 自检：去掉这处改动，新用例必须靠断言失败变红，贴输出。

### B. `accept` 与 `close` 也退残留预扣（v1.2 第 4 条，复核第 4 节「计费与并发」第 1 点）

- `service.accept` 与 `service.close`：状态事务提交之后调用一次 `DiscussBilling(username, group_id).refund_reserved()`。
- 新用例（付费模式，各一条，写法参照已有的 `test_resume_refunds_stale_reservation_before_replanning`）：造一个「群已停下、留有一条 `billing_status='reserved'` 的步骤、余额已被预扣」的状态，调用 `accept`（`close` 同理）之后，那条步骤变成已退，余额恢复到预扣之前，`reserved == 0`。
- 自检：分别去掉两处调用，对应用例必须失败。

### C. 一处文案

固定席位的名字现在允许空字符串，超长时的报错文案改成「固定席位的名字最多 12 字」。全库搜索这句旧文案的所有出现处（包括用例里的断言）同步。

### D. 补四条用例（复核第 4 节「新代码的测试缺口」）

代码不用改，只补用例；每条都要能发现表里的改坏方式。

| 编号 | 改坏方式 | 要补的用例 |
|---|---|---|
| Y1 | `runner.start_group` 里补偿清令牌时去掉 `AND run_token=?` | 群上已经有别人的令牌，本次认领被拒，同时调用方被取消：别人的令牌必须原样保留（复核第 6 节 P3） |
| Y3 | `service.detail` 不把分身名字传给 `_avatar_member`，退回到再取一次 | 带分身的群取一次详情，`avatar.display_name` 恰好被调用一次 |
| Y5 | 隐私说明删掉「联网搜索按次另扣草莓，与成员用哪个模型无关。」 | 目录接口返回的 `notice` 以这句话结尾；引用这段话的三份文档里都有这句话（放 `tests/test_discuss_docs.py`） |
| Y6 | 建群重名检查只对自定义成员生效 | 一个带 `role` 的成员改了名字、与另一位成员重名时，建群返回 `422` |

自检：四条改坏方式各自由对应用例靠断言失败发现。

## 三、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过。
2. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 讨论群用例总数，0 失败、0 跳过。
3. 自检表：A、B、D 各条「改坏后由哪条用例靠断言失败发现」，一行一条（必须是 `failed`，不能是 `error` 或超时）。
4. `git status --porcelain --untracked-files=all`：相对本单派出时只多出报告，变动只在第一节第 1 条允许的文件里。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-review-r2.md`，不写本机绝对路径：A–D 逐条做了什么、新用例的函数名、自检表、验收四条的命令与输出摘要、没做完或需要人工确认的地方。
