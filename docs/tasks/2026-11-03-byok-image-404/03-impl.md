# 03 · 实施报告 — BYOK Claude 智能体生图先登记归属，修「图片加载失败，请重试。」

日期：2026-11-03 · 基线提交 `0ca95af` · 分支 `fix/byok-image-404` · 分级 L2

## 代理拆分表（本任务全部派出记录）

| 代理 | 任务范围 | 文件 | 结果 |
| --- | --- | --- | --- |
| Agent A | §4.1–§4.3 生产代码 | `backend/services/chat_service.py`、`backend/services/claude_agent.py`、`backend/main.py` | 完成；`py_compile` 退出码 0；未越界 |
| Agent B | §4.4 新回归测试 | `backend/tests/test_byok_pending_image_access.py` | 完成；`py_compile` 退出码 0；未越界 |

两个代理在同一个 workflow 的 `parallel()` 中并发执行，均不带 schema、直接返回文本；每个任务说明均自包含并明确禁止调用 `subagent` / `subagent_fork` / `workflow`。没有代理失败，没有重派，没有额外派出其他代理。

## 1. 修改了哪些文件

| 状态 | 文件 | 说明 |
| --- | --- | --- |
| 修改 | `backend/main.py` | 引入 pending 查询；`_can_view_generated_image` 先查登记表，未命中再查库 |
| 修改 | `backend/services/chat_service.py` | 新增进程内待入库生成图登记表及 3 个模块级函数 |
| 修改 | `backend/services/claude_agent.py` | 生成图事件 yield 前登记；`finally` 中先注销再决定删图 |
| 新增 | `backend/tests/test_byok_pending_image_access.py` | 4 个 pytest 回归测试 |
| 新增 | `docs/tasks/2026-11-03-byok-image-404/03-impl.md` | 本报告 |

未修改任何既有测试、`frontend/`、`.env*`、依赖、数据表/迁移、持久化与计费顺序；未 commit。`git diff --stat`：3 个生产文件，`28 insertions(+), 2 deletions(-)`。

## 2. 实现了什么

1. **进程内登记表**：`chat_service._PENDING_GENERATED_IMAGES: set[tuple[str, str]]`，键为 `(username, image_path)`。提供 `claim_pending_generated_image`、`release_pending_generated_image`、`is_pending_generated_image` 三个模块级函数，语义分别是加入、幂等移除、成员判断。
2. **交付前登记**：Claude 智能体收到执行核心的 `generated_image` 事件后，在把该事件 `yield` 给客户端之前，立即用 `ctx.user` 和事件里的 `image_path` 登记。登记早于 `delivered=True` / `billable_pending=True`，更早于整轮结束时的 `save_delivered()`。
3. **本轮结束无条件注销**：`finally` 中先调用 `release_pending_generated_image`，再按原逻辑判断 `image_path != persisted_image_path` 时删除未入库图片。入库成功、入库失败并删图、客户端断开、预算耗尽、异常路径都会经过这里；即使图片在执行核心完成但事件尚未被读取，`owned_image_result` 的兜底路径也会先注销（未登记时为空操作）。
4. **私有图放行**：`main._can_view_generated_image` 先判断登记表命中，命中直接返回 `True`，不打开数据库连接；未命中时完全沿用原有的 `database.message_references_image` 归属校验。没有放宽为「所有 generated_ 图」或「文件存在即放行」。
5. **回归测试**：T1 覆盖「事件到达时已登记、入库时仍未注销、入库后注销且不删图」；T2 覆盖入库失败注销并删图、不计费；T3 覆盖客户端在图片事件后断开时注销并删图；T4 覆盖 `/uploads` 路由只向登记用户放行、其他用户 404、未登记文件名 404、release 后 404，并断言登记表最终为空。

## 3. 与 §4 任务清单逐项对应

| 规格项 | 实现位置 | 对应情况 |
| --- | --- | --- |
| §4.1 `chat_service.py` 新增登记表与 3 个函数 | `backend/services/chat_service.py` 95–107 行 | 名字、签名、实现与规格一致；位于模块级常量区末尾、首个函数之前；未改其他行 |
| §4.2a 事件 yield 前登记 | `backend/services/claude_agent.py` 739 行 | 紧跟 `image_path = ...`，在 `delivered`/`billable_pending` 与该事件 `yield` 之前；通过模块属性 `chat.claim_pending_generated_image(...)` 调用 |
| §4.2b `finally` 先注销再删图 | `backend/services/claude_agent.py` 869–874 行 | 先 `release_pending_generated_image`，再按原条件 `delete_uploaded_files`；两处均在 `finally` 内 |
| §4.3a `main.py` import | `backend/main.py` 49 行 | 改为 `from services.chat_service import is_pending_generated_image, shutdown_byok_pool` |
| §4.3b 登记命中直接放行 | `backend/main.py` 238–251 行 | 命中时返回 `True` 且不建数据库连接；未命中路径与原文逐字一致 |
| §4.4 T1 | 测试文件 40 行 `test_generated_image_is_viewable_from_the_event_until_persisted` | 事件时登记为 True 且 `saves == []`；入库时仍为 True 且 `not billable`；结束后 saves 长度 1、第二项为 PATH、登记 False、未删图、已计费 |
| §4.4 T2 | 测试文件 64 行 `test_failed_persistence_releases_claim_and_deletes_image` | `pytest.raises(RuntimeError)`；之后登记 False、`deleted == [PATH]`、不计费 |
| §4.4 T3 | 测试文件 77 行 `test_client_disconnect_after_image_event_releases_claim` | 用 `anext` 消费到图片事件后 `aclose()`；登记 False、`deleted == [PATH]`、无 save、不计费 |
| §4.4 T4 | 测试文件 92 行 `test_uploads_route_serves_pending_image_only_to_its_owner` | 未登记 404；登记后同用户 200/`image/png`/`no-store`/字节等于写入 PNG；他人 404；未登记文件名 404；release 后 404；登记表为空 |

## 4. §5 验收的实际输出

### 验收环境说明（只影响怎么跑，不改变代码）

- 本机 shell 注入了 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY=...,[::1]`。当前 `httpx 0.28.1` 解析该 `NO_PROXY` 条目时会在 OpenAI 客户端构造阶段抛出 `InvalidURL: Invalid port: ':1]'`；即使是改动前的既有 `tests/test_health_and_startup.py` 也会因此失败。因此 A–C 实际执行时在命令前清除了代理变量（`env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY -u http_proxy -u https_proxy -u all_proxy -u no_proxy`），清除后命令与 §5 等价。
- 本 worktree 没有 `frontend/node_modules`；不补依赖时全量套件有 235 个前端依赖测试 skipped。为满足 §5-C「skipped 不多于基线 0」，C 运行期间临时把已有主检出的 `/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/node_modules` 软链到本 worktree 的 `frontend/node_modules`，跑完立即删除；未修改任何前端源文件，最终 `git status` 也没有该路径。若只按本 worktree 现状运行，235 个 skipped 全部来自「前端依赖不可用」，不是本次改动引入。
- `verify/repro_byok_image_race.py` 是独立脚本，不走 pytest 的 conftest 占位环境；本 worktree 又没有 `backend/.env`，所以 D 运行时显式设置了占位 `DASHSCOPE_API_KEY` 与 `JWT_SECRET`。脚本使用临时库/临时上传目录和假传输，不调真实模型。

### A. 新增测试

```text
$ .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_byok_pending_image_access.py
....                                                                     [100%]
4 passed, 33 warnings in 1.24s
```

0 failed、0 skipped。

### B. 指定子集（6 个既有测试文件）

```text
$ .venv/bin/python -m pytest -q -p no:cacheprovider \
    tests/test_claude_agent_runtime.py tests/test_claude_agent_r1_runtime.py \
    tests/test_image_generation.py tests/test_crisis_resource_paths.py \
    tests/test_chat_multi_image_editing.py tests/test_health_and_startup.py
322 passed, 33 warnings in 12.27s
```

passed 数与 §2 基线 `322` 一致；0 failed、0 skipped，skipped 不多于基线 0。

### C. 全量套件

```text
$ .venv/bin/python -m pytest -q -p no:cacheprovider
7867 passed, 35 warnings in 347.69s (0:05:47)
```

`7867 = 基线 7863 + 新增 4`；0 failed、0 skipped，skipped 不多于基线 0。（见上方环境说明：临时链接前端依赖仅用于让既有前端依赖测试实际运行，跑完已删除。）

### D. 机械复现脚本

```text
$ .venv/bin/python ../docs/tasks/2026-11-03-byok-image-404/verify/repro_byok_image_race.py "$PWD"
=== timeline ===
(0.034, 'sse', ['reply_model'])
(0.034, 'sse', ['text'])
(0.034, 'sse', ['message', 'source', 'status'])
(0.035, 'file_persisted', '/uploads/generated_43f9cd2bb6864203b6d4239ba14db52a.png')
(0.035, 'sse', ['generated_image'])
(0.041, 'client_fetch_at_event', True, (200, 'image/png', 139))
(0.041, 'sse', ['text'])
(0.041, 'sse', ['speak', 'text'])
(0.041, 'sse', ['text'])
(0.041, 'sse', ['text'])
(0.041, 'save_response_begin', '/uploads/generated_43f9cd2bb6864203b6d4239ba14db52a.png')
(0.043, 'save_response_done', '/uploads/generated_43f9cd2bb6864203b6d4239ba14db52a.png')
(0.043, 'sse', ['done'])
(0.048, 'client_fetch_after_stream', True, (200, 'image/png', 139))
=== results ===
helper_at_event: True
http_at_event: (200, 'image/png', 139)
helper_after_stream: True
http_after_stream: (200, 'image/png', 139)
file_exists_after: True
billable: True
response_saved: True
VERDICT: FIXED
```

满足 `http_at_event: (200, 'image/png', …)`、`http_after_stream: (200, 'image/png', …)`、`file_exists_after: True`、`response_saved: True`，最后一行 `VERDICT: FIXED`。时间线显示图片事件在 `save_response_begin` 之前，而事件时刻的 GET 已经 200。

### E. 工作区状态

```text
$ git status --porcelain
 M backend/main.py
 M backend/services/chat_service.py
 M backend/services/claude_agent.py
?? backend/tests/test_byok_pending_image_access.py
?? docs/tasks/2026-11-03-byok-image-404/
```

与 §5-E 要求的五行完全一致，无其他改动。

### F. 既有测试零改动

```text
$ git diff --stat -- backend/tests
（无输出，退出码 0）
```

### G. 生产代码改动行数

```text
$ git diff -- backend/main.py backend/services/chat_service.py backend/services/claude_agent.py | grep -c '^[-+][^-+]'
21
```

`21 <= 40`，只包含 §4 列出的插入/替换。

## 5. 未完成或需人工确认的地方

- 没有做真实浏览器/真实 Anthropic Key 的端到端手测；本次以机械复现脚本 D 覆盖「图片事件到达即 GET 成功」的核心时序。前端按规格不需要改。
- 登记表是进程内状态，成立前提与现有 `_IMAGE_GENERATION_USERS` / `_BYOK_USERS` 相同：单进程 uvicorn。若未来改多 worker，需要改为共享存储；本期按规格不做表、不做清理任务。
- 验收环境的两点操作（清除代理变量、为 C 临时链接前端依赖、为 D 设置占位凭据）都是本机 shell/worktree 现状的适配，不是代码改动；C 的前端依赖软链已在运行后删除，最终工作区没有该路径。
- `03-impl.md` 是本任务唯一新增的文档；`01-repro.md`、`02-spec.md`、`verify/` 下既有文件均未修改。
- 未 commit，改动留在工作区等待门禁。
