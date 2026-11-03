# 04 · 独立复核 — BYOK Claude 智能体生图「图片加载失败」修复

- 复核方：独立副本（`review-byok-image-404`），基线 `0ca95af`，待审 diff 未提交
- diff 一致性：`.review/diff.patch` sha256 = `22303f67…`，与 `diff.sha256` 一致；`git diff`（3 个已跟踪文件）与 patch 前 76 行逐字相同，新测试文件与 patch 中的内容逐字相同。变异测试做完后已还原，还原后 `git diff | shasum` = `943e99c8…`，与还原前相同。
- 运行环境：所有 pytest 和脚本都加了 `env -u NO_PROXY -u no_proxy`；D 额外设了 `DASHSCOPE_API_KEY=placeholder JWT_SECRET=placeholder`。`frontend/node_modules` 是指向主检出的软链（已确认存在）。
- 复核用的辅助文件都在 `.review/` 下（git 已忽略，没有删除）：`rv_probe_test.py`（退出路径与 HTTP 实测）、`rv_leak_plugin.py`（登记残留检查插件）、`rv_mutate.py` / `rv_mutate2.py`（变异脚本）、`rv_backup/`（变异前的源码备份）、`rv_full_C.txt`（全量输出）。

## 1. 结论：**通过**

没有必须修复项。改动只碰白名单里的文件，与规格 §4 逐字一致。规格 §5 的 A–G 我都自己跑了一遍，全部满足。
- 安全：登记表只在 `(username, normpath 后的路径)` 完全相同时放行。实测换用户、换用户名大小写、换文件名、`reference_` 文件、`.generated_` 隐藏文件都返回 404。
- 生命周期：所有退出路径都会注销，没有发现残留。
- 契约：一次最终保存、保存成功才计费，这条不变；平台生图路径没有受影响。
- 测试证明力：四条指定变异都能让新测试变红，另外补做的两条（登记晚于 `yield`、注销早于入库）也被抓住。

另外发现一个**和本 diff 无关的既有问题**：在大小写不敏感的文件系统上，可以用大写文件名绕过 `/uploads` 中间件的私有图校验。我建议另开任务处理，这次不阻塞，详见 §3.5。

## 2. 验收 A–G 逐条核验

| 项 | 命令（在 `backend/` 下执行） | 实际输出摘要 | 结论 |
|---|---|---|---|
| A | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_byok_pending_image_access.py` | `4 passed, 33 warnings in 2.81s`，退出码 0 | 通过 |
| B | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_claude_agent_runtime.py tests/test_claude_agent_r1_runtime.py tests/test_image_generation.py tests/test_crisis_resource_paths.py tests/test_chat_multi_image_editing.py tests/test_health_and_startup.py` | `322 passed, 33 warnings in 12.45s`，退出码 0。基线 `verify/00-baseline-subset-0ca95af.txt` 也是 `322 passed`，两边都是 0 skipped | 通过 |
| C | `.venv/bin/python -m pytest -q -p no:cacheprovider`（全量） | `7867 passed, 35 warnings in 339.64s (0:05:39)`，退出码 0，输出里没有 FAILED、ERROR 或 skipped。基线 7863 + 4 = 7867（输出存 `.review/rv_full_C.txt`） | 通过 |
| D | `DASHSCOPE_API_KEY=placeholder JWT_SECRET=placeholder .venv/bin/python ../docs/tasks/2026-11-03-byok-image-404/verify/repro_byok_image_race.py "$PWD"` | 时间线：`(0.042,'sse',['generated_image'])` → `(0.048,'client_fetch_at_event',True,(200,'image/png',139))` → `(0.048,'save_response_begin',…)` → `(0.051,'save_response_done',…)`。结果：`http_at_event: (200, 'image/png', 139)`、`http_after_stream: (200, 'image/png', 139)`、`file_exists_after: True`、`billable: True`、`response_saved: True`，最后一行 `VERDICT: FIXED` | 通过（入库开始前 GET 已经是 200） |
| E | 仓库根执行 `git status --porcelain` | 恰好 5 行：` M backend/main.py`、` M backend/services/chat_service.py`、` M backend/services/claude_agent.py`、`?? backend/tests/test_byok_pending_image_access.py`、`?? docs/tasks/2026-11-03-byok-image-404/` | 通过 |
| F | `git diff --stat -- backend/tests` | 无输出，退出码 0 | 通过 |
| G | `git diff -- backend/main.py backend/services/chat_service.py backend/services/claude_agent.py \| grep -c '^[-+][^-+]'` | `21`（≤ 40） | 通过 |

E 的补充：用 `--untracked-files=all` 展开 docs 目录，里面有 `01-repro.md`、`02-spec.md`、`03-impl.md` 和 `verify/` 下 5 个文件。除 `03-impl.md` 外都是 Claude 预先放的输入。`docs/.../03-impl.md` 与 `.review/03-impl.md` 逐字节相同。

## 3. 安全与隐私审查

### 3.1 放行条件：只在完全匹配时生效（实测）

方法：`rv_probe_test.py::test_http_variants` 使用 conftest 的 `client` 夹具（DEV_MODE=1、回环客户端、临时库和临时上传目录）。临时上传目录里写入 4 个真实 PNG：`generated_d…`、`reference_d…`、`.generated_d…`、`generated_e…`。

登记了两条：`("smoke_tester", "/uploads/generated_d….png")`，以及故意多登记的隐藏名 `("smoke_tester", "/uploads/.generated_d….png")`。

请求方式：为了避免 httpx 在客户端先把 `./`、`../` 规范化掉，请求是直接构造 ASGI scope（带原始 path）发给 `main.app` 的。百分号编码那两条用的是 TestClient。

| 状态 | 请求者 | 路径 | 状态码 |
|---|---|---|---|
| 已登记 | 本人 smoke_tester | `/uploads/generated_d….png` | **200** |
| 已登记 | 其他用户 someone_else | 同上 | **404** |
| 已登记 | 用户名大小写变体 SMOKE_TESTER | 同上 | **404** |
| 已登记 | 匿名 | 同上 | 401 |
| 已登记 | 本人 / 其他用户 | `/uploads/./generated_d….png` | 200 / **404** |
| 已登记 | 本人 / 其他用户 | `/uploads/../uploads/generated_d….png` | 200 / **404** |
| 已登记 | 本人 / 其他用户 | `/uploads/x/../generated_d….png` | 200 / **404** |
| 已登记 | 本人 / 其他用户 | `/uploads//generated_d….png` | 200 / **404** |
| 已登记 | 本人 / 其他用户 | `/uploads/generated_%64…（百分号编码）.png` | 200 / **404** |
| 已登记 | 本人 | `/uploads/generated_d….png/`（结尾斜杠） | 200 |
| 已登记（含隐藏名的登记） | 本人 | `/uploads/.generated_d….png`（文件存在） | **404**（隐藏文件检查排在登记检查前面） |
| 已登记 | 本人 | `/uploads/reference_d….png`（同 id，文件存在） | **404** |
| 已登记 | 本人 | `/uploads/generated_e….png`（文件存在，未登记） | **404** |
| 注销后 | 本人 / 其他用户 / 大小写用户名 / 匿名 | `/uploads/generated_d….png` | 404 / 404 / 404 / 401 |

结论：
- 中间件在查登记表之前，先用 `posixpath.normpath` 处理路径（`main.py` 里 `upload_path`）。所以 `./`、`../`、`//`、百分号编码这些写法，最后都还原成同一个文件，而且**只对本人**放行。这和原来按消息归属查库的行为一致，不算误放行。
- 换用户、换用户名大小写、换文件名、`reference_`、`.generated_` 一律 404。
- 代码层面：登记只在 `claude_agent.py:739` 发生，取值是 `ctx.user` 加上执行核心返回的 `image_path`（固定是 `/uploads/generated_<uuid hex>.png`），没有任何用户可控的输入能写进登记表。

### 3.2 注销是否覆盖所有退出路径

代码结构：登记（739 行）只会发生在 `claude_agent.py` 第 512 行的 `try` 里面。这个 `try` 的 `finally`（868–875 行）会无条件执行 `release`。`release` 底层是 `set.discard`，不会抛异常。`release` 和 `delete_uploaded_files` 之间没有 `await`。

每轮最多一张图（有 `image_success` 守卫）。`image_path` 一旦赋值就不会被置回 None；765 行的 `result.get("image_path", image_path)` 拿到的值和事件里的路径是同一个（`chat_service.py:1103/1124/1138` 都来自同一个 `generated["image_path"]`）。

逐条实测（`rv_probe_test.py`，结束时都断言 `_PENDING_GENERATED_IMAGES == set()`，全部通过：`9 passed`）：

| 路径 | 用例 | 实测 |
|---|---|---|
| 入库成功 | 新测试 T1 | 注销，不删图 |
| 入库失败并删图 | T2；P3（模型异常后保存又失败）；P4（`ResourceNotFound`） | 注销，`deleted == [PATH]` |
| 客户端断开（aclose） | T3 | 注销并删图，不保存 |
| 任务被取消（等待下一轮模型时 `CancelledError`） | P8 | 注销并删图 |
| 预算耗尽（图片事件后时钟跳到 241） | P1 | `agent_stop=budget`，图片入库，然后注销 |
| 模型异常（第二轮流抛 RuntimeError） | P2 | 先保存再注销，最后一条事件是 error |
| 平台侧失败（第二次取全局槽抛 OSError） | P5 | `platform_failure` 分支保存后重新抛出，注销 |
| 生图失败、没有 image_path | P6 | 从未登记（claim 打桩计数为 0），不删图 |
| 图已落盘但事件没被读到（`owned_image_result` 兜底） | P7 | 从未登记，按原逻辑删图 |

残留扫描：我用插件 `rv_leak_plugin.py` 在每个测试 teardown 时检查登记表，对 21 个与智能体或生图相关的既有测试文件，加上新测试文件，跑了一遍：`1258 passed`，`RV_LEAK_SWEEP claims=12 leaks=0`。也就是说，既有测试实际触发了 12 次登记，事后都没有残留。

有没有路径会让登记永久残留：
- 只有一种：进程在 finally 执行前就崩溃。但那时内存里的登记表也一起没了，等于没残留。
- 异步生成器被丢弃、没有显式 aclose 的情况：外层 `stream_claude_agent` 用 `aclosing` 包住内层；就算外层被丢弃，asyncio 的 asyncgen finalizer 也会补做 aclose。
- 登记表的规模受每用户锁 `_BYOK_USERS` 限制：同一用户同时最多一轮，每轮最多一条登记。

### 3.3 登记是否早于 `yield`

`claude_agent.py:738` 赋值 `image_path`，739 行 `claim`，740–752 行只有赋值、切片和 `_sse` 拼字符串，**没有 `await`**，然后 753 行 `yield event`。登记和 `yield` 在同一个同步步骤里完成，外层生成器只是转发。所以不存在客户端先拿到事件、登记后发生的情况。

验证：
- T1 在收到事件的那一刻断言已登记。
- 我额外做了变异 m5：把 `claim` 挪到 `yield` 之后。T1 变红。
- 复现脚本 D 在事件时刻发 HTTP GET，结果 200。

### 3.4 `release` 与 `delete_uploaded_files` 先后形成的窗口

**窗口一：已注销，但文件还在**
- 入库成功时：`save_delivered()` 在 `try` 里被 await 完才进 `finally`，消息行已经提交，然后才注销。注销之后按消息归属查库照样能看到，**没有 404 空档**。
- 没入库时：注销后紧接着同步删文件，中间没有 `await`，事件循环上没有可观察的空档。
- 唯一的例外是 `delete_uploaded_files` 本身失败（比如 OSError），文件会留在磁盘上，但对所有人都是 404。这是失败即关闭，属于既有行为，不是本 diff 引入的。

**窗口二：文件已删，但还登记着**
- 按现在的顺序不会出现。
- 就算顺序反过来，后果也只是本人请求会走到 StaticFiles 拿到 404，不会泄露给别人。

**还有两个可接受的边角情况**
- 某个请求刚好在注销前通过了中间件，StaticFiles 还在线程里读文件时文件被删。只影响本人这一次请求，最坏是读失败或拿到旧内容。
- 入库成功后，`finally` 之前还有 `_normal_followups` 和 `yield done`。这段时间登记仍在，但消息行也在，没有额外暴露。只有本人在这几秒内删掉这个会话时，本人能多看见几秒自己的图。只涉及本人，可以忽略。

### 3.5 本 diff 之外的既有问题（不阻塞，建议另开任务）

在大小写不敏感的文件系统上（本机 APFS，已用 `touch /tmp/rvCaseX && ls /tmp/rvcasex` 确认），可以用大写文件名绕过私有图校验。

- 原因：`main.py` 判断私有图用的是 `basename.startswith(("generated_", ...))`，区分大小写，所以 `/uploads/GENERATED_d….png` 不会被识别成私有图。
- 实测：不管登记还是注销，**其他用户、甚至匿名请求**都拿到了 200（DEV_MODE 回环下，非私有的上传文件不需要鉴权；DEV_MODE=0 时匿名会是 401，但其他已登录用户照样能拿到）。
- 和本 diff 的关系：这一段代码本 diff 没碰；而且注销后的几行结果也是 200，说明和登记表无关。
- 影响范围：生产环境（Linux ext4，区分大小写）不受影响；macOS 本机开发实例，或者部署在大小写不敏感的卷上时会受影响。
- 建议修法：判断前缀时先 `.lower()` 再比，或者把不合规范的大小写一律 404。

## 4. 变异测试结果

方法：每次变异前把源码备份到 `.review/rv_backup/`，用脚本精确替换（替换前断言目标文本恰好出现一次），跑 `tests/test_byok_pending_image_access.py`，然后从备份还原。还原后 diff 哈希不变，4 条新测试回到 `4 passed`。

| 变异 | 内容 | 结果 | 变红的测试 |
|---|---|---|---|
| m1 | 删掉 `chat.claim_pending_generated_image(...)` | 1 failed, 3 passed | T1 `test_generated_image_is_viewable_from_the_event_until_persisted` |
| m2 | 删掉 `finally` 里的 `release` | 4 failed | T1、T2、T3 直接断言没注销；T4 是因为前面测试留下的条目导致结尾的「登记表为空」断言失败（级联） |
| m3 | `is_pending` 只比 image_path，不比 username | 1 failed, 3 passed | T4 `test_uploads_route_serves_pending_image_only_to_its_owner`（someone_else 拿到了 200） |
| m4 | 中间件不查登记表 | 1 failed, 3 passed | T4（本人登记后仍是 404） |
| m5（补充） | 把 `claim` 挪到 `yield event` 之后 | 1 failed | T1 |
| m6（补充） | 在 `save_delivered` 里，入库之前就 `release` | 1 failed | T1（save 内部断言仍在登记，失败；AssertionError 没有被吞掉） |

新测试本身的审查：
- **恒真断言**：没有发现。T1 用 `seen` 标志确保真的收到过 `generated_image` 事件。T3 的 `anext` 循环如果始终没收到事件，会抛 `StopAsyncIteration` 让测试报错，不会静默通过。T2 用 `pytest.raises(match=...)`。T4 的「未登记 404」和「其他用户 404」都是针对**真实存在的文件**，所以 404 确实来自中间件。
- 一个偏弱的断言：T4 的「另一个未登记文件名 404」，那个文件不存在，404 也可能是 StaticFiles 给的。规格允许这样写，我的 §3.1 实测已经用存在的 `generated_e…` 补上了，见 §6-2。
- **连网**：没有。模块级 fixture 封掉了 `connect`、`connect_ex`、`create_connection`、`getaddrinfo`、`gethostbyname(_ex)`。T4 用的 TestClient 走进程内 ASGI，不经过 socket。全量运行时这个模块没有任何封网断言失败。
- **读仓库外文件**：没有。PNG 在内存里生成，写到 conftest 指定的会话临时上传目录 `media.UPLOADS_DIR`，结束时删除；只导入仓库内的 `test_claude_agent_runtime`。不依赖 git 历史。

## 5. 必须修复项

无。

## 6. 可优化项（不阻塞）

1. **把单进程前提写明白**（对应复核问题 6）
   - 现状：`chat_service.py:93-94` 的注释写了 `Process-local like the limits above`，说明登记表是进程内状态，但没有直接写出「多 worker 部署时会失效，图片又会 404」。`main.py` 的 docstring 也没提。
   - 规格已经接受这个前提，所以不阻塞。
   - 建议改成：`Process-local: assumes a single uvicorn worker (same as _IMAGE_GENERATION_USERS); with multiple workers the image may 404 until persisted.`
2. **加强 T4 里「未登记文件名」那条断言**：先把 `generated_e…png` 文件真的写进去，或者断言响应体是 `{"detail": "图片不存在或无权访问"}`，这样能确认 404 来自中间件而不是 StaticFiles。
3. **新测试文件的隔离**：建议加一个 autouse fixture，测试前后清空或断言 `_PENDING_GENERATED_IMAGES` 为空。这样单条失败不会像 m2 那样连带 T4 一起红，定位更直接。
4. **注销路径的加固（可选）**：现在 `finally` 注销用的是 `image_path`。它和登记时用的路径相同，依赖的是执行核心里 `agent_result["image_path"]` 与事件里的 `image_path` 来自同一个值（现有实现确实如此）。如果想彻底去掉这个依赖，可以单独用一个 `claimed_image_path` 记下登记的路径，在 finally 里注销它。
5. **另开任务处理 §3.5**：大小写不敏感文件系统上的 `GENERATED_` 绕过（既有问题，与本 diff 无关）。
