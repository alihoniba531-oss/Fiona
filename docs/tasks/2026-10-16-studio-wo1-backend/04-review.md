# WO1 复核记录（第 1 轮）

- 复核方式：全新上下文的独立代理（Fable），逐行审读代码，并用本地脚本做了实测。
- 机械验证：主控在沙箱外跑全量测试，**没有排除任何用例**。结果是 5764 passed、**7 failed、5 errors**。基线（合并 main 之后）为 5436 passed、0 failed。
- 工作室专项测试：541 passed。

## 结论：不通过（只有 1 项必须修复）

经核验成立的部分：
- 付费提交只发一次（`providers/base.py:84-131`）。
- 调度抢占是原子的：用 BEGIN IMMEDIATE 加带条件的 UPDATE，并检查受影响行数（`store.py:442-468`）；两个调度器并发时一共只发了 5 次 POST。
- 没有任何路径会让任务自动重新提交（`store.py:83-90` 的状态转换表；recovery 和 link_task 都不发 POST）。
- 额度与结算正确（`spend.py:20-44`；实测 1.50 和 3.38268）。
- 准入：`main.py:237-307` 加 `gate.py`；非工作室路由的行为不变。
- 下载 host 白名单：`evil.com?x=…`、`…@evil.com`、后缀伪装、`%2E`、`#@` 这几类伪造全部被拒。
- 删除目录：根目录、`..`、根外路径、符号链接都被拒，旧的上传文件清理分支不受影响。
- Seedance 首帧在内存里缩放，原始文件不变。
- 调度器吞掉异常不退出，慢 POST 不阻塞 tick。

## 必须修复
1. **conftest 加了一个全局 autouse 的断网钩子**（`tests/conftest.py:48-73`），连回环地址 127.0.0.1 也一并拦截，导致既有的回环测试 7 failed、5 errors，涉及 `test_byok_client.py`、`test_exchange_isolation.py`、`test_safe_http_deadline.py`。复核把这个钩子恢复成原 socket 函数后重跑这三个文件，145 passed。**失败的原因是这个钩子，不是沙箱。** 另外，`docs/ARCHITECTURE.md:381` 把这些失败解释成沙箱环境受限，这个说法不实。

## 可优化（主控决定本轮一并修 6 条）
2. `pricing.actual_cost` 遇到浮点形式的 `completion_tokens`（例如 48324.0）会记成 0，少算当日占用（`pricing.py:102`）。
3. `_guard` 的日志只记了 id，没有记异常类型（`scheduler.py:74`）。
4. 下载成功但没有 `result_url` 时，每 30 秒无限重查（`scheduler.py:219-223`）。
5. 422 文案出现 `¥100.00000000`（`store.py:304`）。
6. `media.py:383-395` 的 `/uploads/` 特判写得太绕，改为删号入队时用显式前缀区分工作室目录。
7. `routers/me.py:100` 删号时在事件循环里同步执行 rmtree，大目录会卡住。
8. 备份时工作室这个包失败，会连带数据库快照也不发布（`fiona-backup.sh:105-108`）。

## 本轮不修（记录在案）
- `/studio/*` 的 OPTIONS 预检请求会被 404。WO2 的前端经 Next rewrite 走同源，不会触发预检，所以暂不处理。如果以后改成跨源，再放行。
