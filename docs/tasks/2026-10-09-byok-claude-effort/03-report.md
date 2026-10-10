# Claude 思考强度实现报告

日期：2026-10-09。依据 [02-spec.md](02-spec.md)，基线 `main @ 7163acd`。三个子代理分别独占后端存储/接口/新测试、`client.py`、前端三个文件；主代理负责文档、交叉审查及统一验收。派发未指定模型或推理参数。

R1-1 至 R1-3 已实现，依据 [05-fix-r1.md](05-fix-r1.md)，本轮未派子代理。最新后端全量为 **2924 passed / 1 failed / 5 errors / 6 skipped**，退出 **1**；累计新增 118 项通过，其中本轮新增 16 项。非通过项均为既有回环测试受断网保护影响，沙箱内尚未达到返修单要求的 **2936 passed**。前端 tsc 退出 **0**，ESLint **0 errors / 25 warnings**、退出 **0**。浏览器验收脚本已准备，需主控在沙箱外执行；不宣称浏览器或全量验收已通过。

第 1–7 节保留初次交付的历史记录；最新变更、R1 对受保护文件的明确例外、调整后的验收输出与待验证事项以第 8 节「R1 返修」为准。

## 1. 新增与修改的文件

新增：

- `backend/tests/test_byok_effort.py`：102 个参数化用例。
- `docs/tasks/2026-10-09-byok-claude-effort/03-report.md`：本报告。

修改：

- 后端：`backend/byok/store.py`、`backend/byok/providers.py`、`backend/byok/client.py`、`backend/routers/chat_model.py`、`backend/database.py`。
- 前端：`frontend/lib/chatModel.ts`、`frontend/app/page.tsx`、`frontend/components/ChatModelSection.tsx`。
- 两个既有 BYOK 测试文件：`backend/tests/test_byok_api.py`、`backend/tests/test_byok_store.py`；仅修改下文列明的两处字段集合。
- 文档：`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`。

任务目录及 `02-spec.md` 在开始时已是未跟踪文件；规格原文未修改。第 3 节受保护文件及全部其他既有测试均未修改。

## 2. 实现的功能

Claude 配置增加跟随账号保存的低 / 中 / 高思考强度，默认低。聊天底栏及设置页均可立即 PATCH 保存，无需点击保存；两处使用现有版本号跨文档刷新。设置页调档保留模型与 Key 草稿，不计入未保存修改；操作错误由操作清除，后台刷新成功或先失败后恢复均不能清除该错误。

后端提供元数据、公开与内部配置字段、原子选项更新及老库自动补列。普通和镜子 Claude 请求随档位增加 token 预算，高档放大总时限并封顶 240 秒。测试连接、OpenAI 兼容厂商参数、正文上限、气泡标注及 R2/R3 的生命周期逻辑保持原行为。未安装包、未启动前后端服务，未执行 build/dev，未发起真实网络请求。

## 3. 与规格 4.1–4.6 的逐项对应

| 规格 | 实现与验证 |
| --- | --- |
| 4.1 数据库 | DDL 增加 `effort TEXT NOT NULL DEFAULT 'low'`，无 CHECK；`init_db` 紧跟 DDL 执行 `_safe_migrate(ALTER TABLE …)`。旧行默认 low，重复初始化幂等；不新增迁移版本，`/health` 不变。 |
| 4.2 存储与接口 | 新常量与 `validate_effort` 固定文案；仅 Anthropic 元数据有三档与默认值，其余为 null。公开/内部 effort 非法时回落 low。PUT 继续拒绝 effort，INSERT 用默认值，冲突更新保留档位，包括更换型号、Key 与厂商。PATCH 至少一个字段、严格 enabled 校验、effort 固定校验、仅 Claude 可调、needs_reentry 可调；同事务验证后单条 UPDATE，失败不写入。保留 `set_enabled` 兼容包装，限流与 no-store 不变。 |
| 4.3 Claude 参数 | 低、中、高 `max_tokens` 普通/镜子为 4096/2048、8192/4096、16384/8192；低/中使用原总时限，高使用 `min(240, total_seconds()*1.5)`。`_Resources` 接受时限且保留原默认；非法/缺失 effort 用 low。连接测试固定 low/1024/原时限；OpenAI 请求抓包逐字节一致。betas/fallbacks、无 thinking/采样参数、正文 4000/600 及中断关闭分离/发送前 closed 检查保留。 |
| 4.4 前端 | 类型、响应解析、中文标签/title 与 `setChatModelOptions`；原 enabled helper 委托新 helper。底栏严格四项显示条件，设置区需已保存且选中 Claude，否则提示保存后可选。radio/aria-checked、roving tabindex、左右键循环切换与焦点、整组忙碌禁用、底栏 loading 禁用、flex-wrap 和现有 btn-quiet。即时 PATCH 更新本地与版本号；不将 effort 写 localStorage。草稿及错误归属有离线交互验证。 |
| 4.5 文档 | 五份指定文档补三档/默认低、各档 token 与总时限公式、Nginx 300 秒约束、额度消耗、其他厂商不受影响与老库自动补列；架构及部署的表结构清单同步更新。新增内容没有本机绝对路径。 |
| 4.6 测试 | 新文件独占新增 102 项：61 项真实 SDK + MockTransport/看门狗，41 项迁移/元数据/默认/合法非法 PATCH/原子更新/needs_reentry/PUT 保留与拒绝/非法存储降级/删号。全部沿用断网夹具。前端使用临时离线 harness 与指定 tsc/eslint，不引入测试框架。 |

## 4. 先红后绿的实际证据

| 范围 | 实现前 | 实现后 |
| --- | --- | --- |
| 客户端 61 个新用例 | `.venv/bin/python -m pytest -q tests/test_byok_effort.py`：`16 failed, 45 passed in 1.46s`，退出 1；失败为中/高档 SDK 参数及高档看门狗时限。 | `.venv/bin/python -m pytest -q tests/test_byok_effort.py -k 'claude_sdk or connection_always or openai_body or watchdog'`：`61 passed, 41 deselected in 1.06s`，退出 0。 |
| 完整 102 个新用例 | `.venv/bin/python -m pytest -q tests/test_byok_effort.py --tb=short`：`52 failed, 50 passed, 14 warnings in 2.36s`，退出 1。此次在原 client 与未实现后端上直接跑红；跨组临时依赖协调未作为证据。 | `.venv/bin/python -m pytest -q tests/test_byok_effort.py tests/test_byok_api.py tests/test_byok_store.py --tb=short`：`181 passed, 14 warnings in 3.70s`，退出 0；其中 102 项为新增用例。 |
| 后端存储/API 41 项 | 上述完整红测涵盖新增后端行为；原行为对照保持通过。 | 后端独立筛选：`41 passed, 61 deselected, 14 warnings in 2.04s`，退出 0。 |
| 既有两处字段集合 | 实现后、修改断言前，两个原测试为 `2 failed, 14 warnings in 1.22s`，退出 1；均只因公开集合新增 effort。 | 仅按第 3 节更新集合后，包含在 181 项绿色回归中。 |
| 前端交互与接口 27 项 | 临时 Node harness 转译真实 TS/TSX、mock API 与 React hooks：`27 tests, 27 failures`，退出 1。 | `27 tests, 0 failures`，退出 0。涵盖即时 PATCH、显示条件、键盘/忙碌、错误归属、草稿及版本号刷新；不代替真实浏览器验证。 |
| 文档 25 项 | 临时离线检查：`25 documentation checks, 25 failed`，退出 1。 | `25 documentation checks, 0 failed`，退出 0。 |
| 既有客户端离线回归 | 原测试未修改。 | `.venv/bin/python -m pytest -q tests/test_byok_client.py -k 'not real_loopback and not loopback_interrupt_race'`：`124 passed, 6 deselected in 1.13s`，退出 0；6 个真实回环用例留待外部复跑。 |

不改变行为的连接测试、OpenAI 参数等用例作为通过的对照；新增行为先观察目标断言失败后才实现。所有辅助 harness/断网保护均在仓库外临时目录，未新增仓库依赖。

## 5. 既有 BYOK 断言的逐条修改及依据

1. `backend/tests/test_byok_api.py::test_get_public_metadata_and_no_key` 的 `expected`：
   - 原：`{"provider", "model", "base_url", "key_last4", "enabled", "status", "updated_at"}`。
   - 新：`{"provider", "model", "base_url", "key_last4", "enabled", "effort", "status", "updated_at"}`。
   - 依据：规格第 3 节允许修改精确公开字段集合，4.2.3 要求 `_PUBLIC_FIELDS` 加 effort。后续 `set(config) == expected`、enabled/status、Key 末四位及 GET 等断言原样保留。
2. `backend/tests/test_byok_store.py::test_public_fields_patch_delete_and_bad_ciphertext`：
   - 原：`assert set(public) == {"provider", "base_url", "model", "key_last4", "enabled", "status", "updated_at"}`。
   - 新：`assert set(public) == {"provider", "base_url", "model", "key_last4", "enabled", "effort", "status", "updated_at"}`。
   - 依据：同为规格第 3 节与 4.2.3 的精确字段集合要求；状态、保密、启停、删除与损坏密文等断言原样保留。

仅以上两处，各为一行集合修改；无其他既有断言修改或放宽，无其他既有测试文件改动。

## 6. 第 5 节验收命令的实际输出与退出码

使用现存 `backend/.venv` 的 Python（环境未提供裸 `python`，因此将该 bin 加入 PATH），没有安装任何包。全量 pytest 的 `PYTEST_ADDOPTS=--tb=short` 仅缩短 traceback；通过仓库外临时 `sitecustomize` 拒绝真实 IP bind/connect/connect_ex/sendto 与 DNS，保证包括回环在内无真实网络 I/O。`PIP_NO_CACHE_DIR=1` 避免不可写缓存警告，npx 设置 `npm_config_offline=true`，只使用现有依赖。

以下保留实际命令、诊断与退出码；为遵守第 3 节，输出中的本机绝对路径改为仓库相对路径，临时目录和标准库安装目录用占位符表示。无输出处明确标注，未把检查失败写成通过。

### 5.1 文件范围

执行目录：`.`（`.` 为仓库根）。

```bash
git status --porcelain
```

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/byok/client.py
 M backend/byok/providers.py
 M backend/byok/store.py
 M backend/database.py
 M backend/routers/chat_model.py
 M backend/tests/test_byok_api.py
 M backend/tests/test_byok_store.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatModelSection.tsx
 M frontend/lib/chatModel.ts
?? backend/tests/test_byok_effort.py
?? docs/tasks/2026-10-09-byok-claude-effort/
```

退出码：**0**。

### 5.2 受保护文件

执行目录：`.`（`.` 为仓库根）。

```bash
git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/persona.py backend/tools backend/utils/safe_http.py backend/byok/url_safety.py backend/byok/crypto.py backend/services/chat_service.py backend/routers/chat.py
```

实际输出：

```text
（无输出）
```

退出码：**0**。

### 5.2 既有测试差异

执行目录：`.`（`.` 为仓库根）。

```bash
git diff --stat -- backend/tests
```

实际输出：

```text
 backend/tests/test_byok_api.py   | 2 +-
 backend/tests/test_byok_store.py | 2 +-
 2 files changed, 2 insertions(+), 2 deletions(-)
```

退出码：**0**。

该命令不展示未跟踪的新测试；已有测试 diff 仅包含上述两个 `test_byok_*.py`。新文件已在 5.1 状态输出中列明。

### 5.3 禁止档位检查

执行目录：`.`（`.` 为仓库根）。

```bash
grep -n 'xhigh\|"max"' backend/byok/providers.py backend/byok/client.py
```

实际输出：

```text
（无输出）
```

退出码：**1**。

`grep` 退出 1 表示没有匹配，符合规格要求；不是执行故障。

### 5.4 依赖一致性

执行目录：`backend`（`.` 为仓库根）。

```bash
python -m pip check
```

实际输出：

```text
No broken requirements found.
```

退出码：**0**。

### 5.4 后端全量测试

执行目录：`backend`（`.` 为仓库根）。

```bash
python -m pytest -q
```

实际输出：

```text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  7%]
........................................................................ [  9%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 17%]
........................................................................ [ 19%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 27%]
...........................ss.................ssss...................... [ 29%]
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 49%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 59%]
.............EF......................................................... [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 81%]
.................................................EEE.E.................. [ 83%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 96%]
........................................................................ [ 98%]
........................................                                 [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________
tests/test_exchange_isolation.py:151: in test_stop_disconnects_async_upstream_and_releases_user_slot
    server, entered, disconnected = client.portal.call(start_server)
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python 标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/asyncio/base_events.py:1637: in create_server
    raise OSError(err.errno, msg) from None
E   PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] offline verification forbids real network i/o
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2908 passed, 6 skipped, 14 warnings, 5 errors in 77.01s (0:01:17)
```

退出码：**1**。

基线 2818 + 新增 102 = 2920；本次通过 2908，其余 12 项是 1 failed + 5 errors + 6 skipped。六个失败/error 的诊断全部是既有回环服务器 bind 被临时断网保护以 EPERM 拒绝；六个 skip 为既有 BYOK 的两项 watchdog 回环和四项中断竞态回环测试。依据规格第 5 节可忽略沙箱端口/回环限制项，但本报告仍保留实际退出 1，2920 全通过须在沙箱外确认。

### 5.5 TypeScript

执行目录：`frontend`（`.` 为仓库根）。

```bash
npx tsc --noEmit
```

实际输出：

```text
（无输出）
```

退出码：**0**。

### 5.5 ESLint

执行目录：`frontend`（`.` 为仓库根）。

```bash
npx eslint .
```

实际输出：

```text

frontend/app/page.tsx
   146:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   237:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   528:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   581:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   582:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   583:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   593:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   594:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   595:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   596:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   599:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   605:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   606:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   910:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1004:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1428:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1448:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1456:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1477:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1519:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1615:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1956) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  2055:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  2095:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2365:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)

```

退出码：**0**。

## 7. 未完成或需要人工确认的地方

功能实现没有未完成项，未遇到第 6 节的要求无法实现、要求互相矛盾、SDK 档位不接受或必须修改受保护文件等情况。

需按规格在沙箱外完成验证：

- 复跑上述六个既有回环失败/error 和六个既有 BYOK 回环 skip，确认全量至少 2920 passed；本次为遵守禁止真实网络请求要求，没有放开回环。
- 真实浏览器检查底栏与设置区的 radio 焦点、左右键、PATCH 失败文案、忙碌禁用、手机换行无横向溢出；离线 harness 已验证逻辑，未启动浏览器/开发服务进行视觉实测。
- 真实抽屉 iframe 双向同步及有模型/Key 草稿时的刷新保留，由 Claude 在沙箱外复验。没有发起真实 Claude 请求，线上延迟和额度消耗未实测。

`git diff --check` 实际无输出、退出 0。受保护文件 diff 为空；既有测试仅有两处允许的精确字段集合变更。没有安装包、没有运行 `npm run build` / `npm run dev`，没有启动后端服务或执行真实网络请求。

## 8. R1 返修

依据 `04-review.md` 与 `05-fix-r1.md`，实现 R1-1 至 R1-3；本轮直接由主代理完成，没有派发子代理，没有安装包、启动服务、执行 Next build/dev 或发起真实网络请求。

### 8.1 本轮文件与实现

新增 `backend/tests/test_byok_heartbeat.py`，共 16 个参数化用例。

修改文件：

- `backend/services/chat_service.py`：仅新增模块常量 `_BYOK_HEARTBEAT_SECONDS = 10`，以及 `_stream_byok_reply` 内部的建流、读块等待与取消清理；这是 R1-2 明确放开的例外。
- `frontend/app/page.tsx`：底栏 radio 的 ARIA 禁用、焦点归位、强调色及桌面布局。
- `frontend/components/ChatModelSection.tsx`：设置区 radio 的 ARIA 禁用、焦点归位及强调色；将组移出原生 disabled fieldset，避免祖先继续禁用 radio。型号、Key 等其余控件仍保留原生禁用行为。
- `docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`：补充 BYOK 每 10 秒发送 SSE 注释心跳，以及 Next 开发代理 30 秒空闲超时的原因。
- `docs/tasks/2026-10-09-byok-claude-effort/03-report.md`：更新最新状态并追加本节。

返修单与复核原文未修改。仓库外临时验收脚本和日志不属于仓库变更，下文用 `$R1_TMP` 表示本轮临时目录；其实际位置由交付消息中的脚本链接提供。

| 返修项 | 实现 | 对应原规格 |
| --- | --- | --- |
| R1-1 | 底栏 busy/loading/unavailable 和设置区 busy/unavailable 均使用 `aria-disabled`；保留请求守卫、roving tabIndex，补充禁用视觉样式；请求结束且焦点仍在组内时，聚焦当前 checked 项，组外焦点不被抢回。 | 4.4 键盘交互、忙碌与 loading 禁用；以返修单替代原生 disabled。 |
| R1-2 | 建流与每次读块分别启动 `_byok_call` 任务，等待满 10 秒仍无结果时发送 `: thinking\n\n`；取消或关闭时取消并 shield 等待任务结束，沿用 abort → worker 结束 → close → 槽位释放。避免第二次 abort；生成器停在心跳时已完成但未接收的建流结果也会关闭。data 字节与顺序、reply_model、保存与计费/退款和错误映射保持原行为。 | 4.3 原有生命周期与时限；4.5 文档；4.6 测试。受保护文件仅使用 R1-2 授权范围。 |
| R1-3 | 两处 checked 项使用 `var(--btn)` / `var(--btnink)`，含悬停时保持强调色；未选中项保持 btn-quiet 的轻微变化。≥1280 底栏单行，只有聊天模型标签允许收缩、省略，并以 title 给出全文；思考组与平台按钮不收缩，手机仍可换行。 | 4.4 现有按钮体系与响应布局；以返修单补充桌面单行和强调色要求。 |

原规格 4.1 数据库、4.2 存储/接口、4.3 Claude 档位与预算代码未作本轮修改；4.4 按 R1-1/R1-3 收尾，4.5 增补心跳说明，4.6 新增 16 项心跳与取消测试。初次交付的 102 项 effort 用例也在本轮全量中通过。

### 8.2 先红后绿与回归证据

| 范围 | 修改前实际结果 | 修改后实际结果 |
| --- | --- | --- |
| R1-1/R1-3 前端契约 | `node "$R1_TMP/frontend.cjs"`：`14 tests, 12 failures`，退出 1；两个组外焦点对照通过，其余失败涵盖原生禁用/祖先 fieldset、连续方向键、选中配色、桌面收缩规则。 | 同一脚本：`14 tests, 0 failures`，退出 0。涵盖两次 ArrowRight 不重新聚焦、鼠标焦点、失败后归位、忙碌/loading/unavailable 守卫、组外焦点、tabIndex、强调色与布局类。 |
| R1-2 首批 14 项 | 在未改后端实现上执行 `.venv/bin/python -m pytest -q tests/test_byok_heartbeat.py --tb=short`：`12 failed, 2 passed in 5.44s`，退出 1；缺少心跳，取消验收等待心跳超时；立即返回两项为通过对照。 | 新 14 项与既有 `test_byok_chat.py` 一起：`118 passed, 14 warnings in 6.36s`，退出 0。 |
| R1-2 补充竞态 2 项 | 先加入「建流在心跳暂停时完成，随后关闭生成器」用例：`1 failed, 1 passed, 14 deselected in 1.06s`，退出 1；成功返回的流未关闭，异常对照通过。之后才补充未接收结果的关闭逻辑。 | `.venv/bin/python -m pytest -q tests/test_byok_heartbeat.py tests/test_byok_chat.py --tb=short`：`120 passed, 14 warnings in 6.12s`，退出 0，其中本轮新增 16 项，既有聊天回归 104 项。 |
| R1-2 文档 | `backend/.venv/bin/python "$R1_TMP/docs.py"`：`2 documentation checks, 2 failed`，退出 1。 | 同一脚本：`2 documentation checks, 0 failed`，退出 0。 |
| 初次前端行为回归 | 仓库外原 27 项 harness 副本仅按 R1 将禁用检查改为 ARIA；没有修改仓库既有测试。 | `node "$R1_TMP/frontend-regression.cjs"`：`27 tests, 0 failures`，退出 0。 |

新增后端测试使用断网夹具与内存桩流；建流和首块等待各覆盖普通/镜子模式，延迟 0.2 秒、间隔 0.05 秒，至少两条注释心跳，之后 data 事件与立即返回版本逐字相同。取消测试覆盖建流/读块、任务取消/生成器关闭、worker 返回/报错，断言 abort 一次、worker 完成、无剩余任务、无 asyncio ERROR、流已关闭、未保存、活跃槽位与用户占用归零。立即返回不发心跳。既有 104 项聊天回归检查原错误、标签、计费/退款等路径。

前端 Node harness 转译真实 TSX 并模拟 hooks/focus，用于逻辑与结构契约；它不替代浏览器 DOM/CSS 验收。Playwright 脚本仅通过语法检查和离线 fixture 生成，尚未执行浏览器。

### 8.3 受保护范围及既有断言

本轮 **没有修改任何既有测试或断言**。返修前的 79 个测试文件（包含初次新增的 `test_byok_effort.py`）SHA-256 均一致，唯一新增测试文件为 `test_byok_heartbeat.py`。

对 `chat_service.py` 做 AST 范围核对：去掉 `_stream_byok_reply` 整个函数范围及唯一新增常量后，余下文本与返修前逐字相同。具体差异也已逐段检查，限于该函数的等待与相关取消清理。其他受保护文件由调整后的第 5.2 条 diff 确认无修改。

`backend/.venv/bin/python "$R1_TMP/scope-audit.py"` 实际输出：

```text
PASS chat_service.py: all lines outside _stream_byok_reply and new constant unchanged
PASS all 79 pre-R1 existing test files byte-identical; one new BYOK heartbeat file
2 scope checks, 0 failed
```

退出码：**0**。

对初次交付两处既有 BYOK 断言的逐条说明仍见第 5 节：API public expected 集合与 store public 集合分别只加入 `effort`，依据原规格第 3 节与 4.2.3。本轮两处均未再次改动；累计仍只有这两处允许的精确集合修改，未放宽其他断言。

### 8.4 调整后的第 5 节验收：全部实际输出与退出码

执行环境与初次验收相同：现存 venv 加入 PATH，`PYTEST_ADDOPTS=--tb=short`，仓库外断网保护拒绝 IP bind/connect/connect_ex/sendto 和 DNS，npx 使用离线模式；未安装包。输出仅将本机绝对路径替换为仓库相对路径或占位符，保留实际诊断和退出码。

第 5.1 白名单追加 `backend/services/chat_service.py`，新建 `test_byok_heartbeat.py` 使用 R1-2 明确许可；第 5.2 受保护命令去掉该服务文件，另列它的完整 diff。

#### 5.1 文件范围

执行目录：`.`。

```bash
git status --porcelain
```

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/byok/client.py
 M backend/byok/providers.py
 M backend/byok/store.py
 M backend/database.py
 M backend/routers/chat_model.py
 M backend/services/chat_service.py
 M backend/tests/test_byok_api.py
 M backend/tests/test_byok_store.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatModelSection.tsx
 M frontend/lib/chatModel.ts
?? backend/tests/test_byok_effort.py
?? backend/tests/test_byok_heartbeat.py
?? docs/tasks/2026-10-09-byok-claude-effort/
```

退出码：**0**。

#### 5.2 其他受保护文件

执行目录：`.`。

```bash
git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/persona.py backend/tools backend/utils/safe_http.py backend/byok/url_safety.py backend/byok/crypto.py backend/routers/chat.py
```

实际输出：

```text
（无输出）
```

退出码：**0**。

#### 5.2 既有测试差异

执行目录：`.`。

```bash
git diff --stat -- backend/tests
```

实际输出：

```text
 backend/tests/test_byok_api.py   | 2 +-
 backend/tests/test_byok_store.py | 2 +-
 2 files changed, 2 insertions(+), 2 deletions(-)
```

退出码：**0**。

#### R1-2 服务文件范围

执行目录：`.`。

```bash
git diff -- backend/services/chat_service.py
```

实际输出：

```text
diff --git a/backend/services/chat_service.py b/backend/services/chat_service.py
index 3c22340..e72f33b 100644
--- a/backend/services/chat_service.py
+++ b/backend/services/chat_service.py
@@ -72,6 +72,7 @@ _BYOK_POOL: ThreadPoolExecutor | None = None
 _BYOK_POOL_SIZE = 0
 _BYOK_POOL_LOCK = threading.Lock()
 _IMAGE_HEARTBEAT_SECONDS = 10
+_BYOK_HEARTBEAT_SECONDS = 10
 # 视觉分支拼进 VL 请求的历史条数上限（T2a）。
 _VL_HISTORY_TURNS = 10
 _BILLABLE_TOOLS = frozenset({
@@ -245,6 +246,19 @@ async def _unreserved_error(ctx: "ChatContext", state: "ChatState"):
 
 async def _stream_byok_reply(ctx: "ChatContext", state: "ChatState", *, mirror: bool):
     """Both reply branches use this isolated consumer; errors never fall back."""
+    async def wait_with_heartbeats(task):
+        try:
+            while not task.done():
+                done, _ = await asyncio.wait({task}, timeout=_BYOK_HEARTBEAT_SECONDS)
+                if not done:
+                    yield ": thinking\n\n"
+        finally:
+            if not task.done():
+                task.cancel()
+            # Join _byok_call so its existing abort/worker cleanup owns cancellation.
+            with anyio.CancelScope(shield=True):
+                await asyncio.gather(task, return_exceptions=True)
+
     stream = None
     state.trace["model"] = "byok"
     if ctx.byok_config and ctx.byok_config.get("provider"):
@@ -272,17 +286,35 @@ async def _stream_byok_reply(ctx: "ChatContext", state: "ChatState", *, mirror:
                 raise _ByokBusyError(message)
             from functools import partial
             control = ReplyStreamControl()
-            stream = await _byok_call(pool, partial(
+            task = asyncio.create_task(_byok_call(pool, partial(
                 open_reply_stream, config,
                 [{"role": "system", "content": state.sys_prompt_final}] + ctx.messages,
                 mirror=mirror, username=ctx.user, control=control,
-            ), control=control)
+            ), control=control))
+            try:
+                async with aclosing(wait_with_heartbeats(task)) as waiting:
+                    async for event in waiting:
+                        yield event
+                stream = task.result()
+            finally:
+                # A heartbeat can suspend the owner after opening already finishes.
+                if stream is None and task.done() and not task.cancelled() and task.exception() is None:
+                    control.abort()
+                    with anyio.CancelScope(shield=True):
+                        try:
+                            await _byok_call(pool, task.result().close)
+                        except Exception as exc:
+                            print(f"[byok] close failed type={type(exc).__name__}", flush=True)
             labelled = False
             exhausted = False
             try:
                 iterator = iter(stream)
                 while True:
-                    chunk = await _byok_call(pool, next, iterator, _STREAM_END, control=control)
+                    task = asyncio.create_task(_byok_call(pool, next, iterator, _STREAM_END, control=control))
+                    async with aclosing(wait_with_heartbeats(task)) as waiting:
+                        async for event in waiting:
+                            yield event
+                    chunk = task.result()
                     if chunk is _STREAM_END:
                         exhausted = True
                         break
@@ -296,7 +328,7 @@ async def _stream_byok_reply(ctx: "ChatContext", state: "ChatState", *, mirror:
                         state.full_response += text
                         yield _sse({"text": text})
             finally:
-                if not exhausted:
+                if not exhausted and not control.aborted:
                     control.abort()
                 with anyio.CancelScope(shield=True):
                     try:
```

退出码：**0**。

#### 5.3 禁止档位

执行目录：`.`。

```bash
grep -n 'xhigh\|"max"' backend/byok/providers.py backend/byok/client.py
```

实际输出：

```text
（无输出）
```

退出码：**1**。

退出 1 表示没有匹配，符合不得开放额外档位的要求。

#### 5.4 依赖一致性

执行目录：`backend`。

```bash
python -m pip check
```

实际输出：

```text
No broken requirements found.
```

退出码：**0**。

#### 5.4 后端全量

执行目录：`backend`。

```bash
python -m pytest -q
```

实际输出：

```text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  7%]
........................................................................ [  9%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 17%]
........................................................................ [ 19%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
...........................ss.................ssss...................... [ 29%]
........................................................................ [ 31%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 49%]
........................................................................ [ 51%]
........................................................................ [ 53%]
........................................................................ [ 56%]
........................................................................ [ 58%]
.............................EF......................................... [ 61%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
.................................................................EEE.E.. [ 83%]
........................................................................ [ 85%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 98%]
........................................................                 [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___
tests/test_safe_http_deadline.py:51: in local_fetch_server
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python 标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python 标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
<临时断网保护>/sitecustomize.py:15: in _guard_bind
    return _deny()
           ^^^^^^^
<临时断网保护>/sitecustomize.py:11: in _deny
    raise PermissionError(errno.EPERM, 'offline verification forbids real network I/O')
E   PermissionError: [Errno 1] offline verification forbids real network I/O
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________
tests/test_exchange_isolation.py:151: in test_stop_disconnects_async_upstream_and_releases_user_slot
    server, entered, disconnected = client.portal.call(start_server)
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python 标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python 标准库>/asyncio/base_events.py:1637: in create_server
    raise OSError(err.errno, msg) from None
E   PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] offline verification forbids real network i/o
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2924 passed, 6 skipped, 14 warnings, 5 errors in 77.16s (0:01:17)
```

退出码：**1**。

#### 5.5 TypeScript

执行目录：`frontend`。

```bash
npx tsc --noEmit
```

实际输出：

```text
（无输出）
```

退出码：**0**。

#### 5.5 ESLint

执行目录：`frontend`。

```bash
npx eslint .
```

实际输出：

```text

frontend/app/page.tsx
   146:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   237:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   536:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   589:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   590:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   591:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   601:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   602:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   603:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   604:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   607:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   613:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   614:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   918:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1012:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1436:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1456:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1464:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1485:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1527:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1623:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1964) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  2063:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  2103:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2373:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)

```

退出码：**0**。

`git diff --check` 实际无输出、退出 0。

全量新增数为本轮 16，返修单要求 `2920 + 16 = 2936 passed`。实际 **2924 passed / 1 failed / 5 errors / 6 skipped**，与初次受相同保护影响的 2908 个通过相比增加 16；不足的 12 项就是六个端口失败/error 和六个真实回环 skip。本轮新增与原 102 项 effort 用例均通过，但当前环境下全量阈值 **未达成**，不能称验收全绿。按原规格第 5.4 的沙箱例外，需由主控在沙箱外复跑既有回环测试并确认最终通过数，未为凑数新增无关测试或放开断网保护。

### 8.5 主控在沙箱外执行的浏览器验收与待确认事项

脚本：仓库外 `$R1_TMP/browser.cjs`；截图和生成的离线页面：`$R1_TMP/browser-output/`。本轮已执行以下命令：

```bash
node --check "$R1_TMP/browser.cjs"
node "$R1_TMP/browser.cjs" --prepare
```

语法检查无输出，退出 0；页面准备实际输出：

```text
(node:65258) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
Prepared two offline fixtures from real components, actual footer parent row and current project CSS.
```

退出码：**0**。该命令仅生成离线 HTML/CSS，没有运行 Next 构建或浏览器。

主控在仓库根、沙箱外使用现成 Playwright 与已安装浏览器执行：

```bash
BROWSERS=chromium,webkit node "$R1_TMP/browser.cjs"
```

若现有 Playwright 位于其他目录，可用 `PLAYWRIGHT_MODULE` 指向该既有安装；不得为验收安装包。脚本从实际 TSX 提取底栏组件及其父行，使用真实设置区组件、项目 CSS/字体，所有页面与 API 请求由 route.fulfill 本地响应，未识别请求直接 abort，没有真实 API、HTTP 服务或 route.continue。浏览器缺失时退出 2，不记为通过。

需主控执行并核对的项目：

1. 底栏、设置区各在日/夜主题下：仅聚焦一次「低」，不重新聚焦，按 ArrowRight，等 PATCH 完成，再按 ArrowRight；模拟服务端为 high，activeElement 为 checked「高」。请求中焦点仍在组内，radio 无原生禁用；鼠标点「中」后焦点仍在组内。
2. 1440×900：底栏 Enter 提示、模型说明、思考组、改用平台在同一行；标签可省略且 title 完整。
3. 日/夜主题：选中「高」、悬停「中」，仅「高」使用强调色，截图确认可辨。
4. 390×844 夜间：底栏和设置区均无横向溢出，保存截图。
5. 在实际完整页面及抽屉 iframe 再核对上述焦点/版面，以及原先待验收的双向刷新与草稿保留；脚本离线 fixture 不代替完整应用的浏览器集成检查。

以上浏览器场景 **尚未执行，不宣称通过**。沙箱外全量后端复跑及最终 2936 个通过数也尚待主控确认。无功能实现遗留，未遇到影响「做出什么」的第 6 节矛盾；剩余事项属于规格指定的外部验证。本轮未发起真实 Claude 请求，因此线上长思考代理表现仍未实测。
