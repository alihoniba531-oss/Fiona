# 02 · 规格 — 自带模型（BYOK Claude 智能体）生图：图片交给客户端前先登记归属，修「图片加载失败，请重试。」

- 日期 2026-11-03 · 基线提交 `0ca95af`（main）· 分级 **L2**（涉及 `/uploads` 私有图的放行校验，按风险至少 L2）
- 工作目录：本仓库检出（一个 git worktree，分支 `fix/byok-image-404`）。后端在 `backend/`，虚拟环境 `backend/.venv` 已就绪。
- 复现与归因见同目录 `01-repro.md`；复现脚本 `verify/repro_byok_image_race.py`（修复前输出 `verify/01-repro-before-fix.txt`，最后一行 `VERDICT: RACE_REPRODUCED`）。

## 给执行者的硬规矩（先读）

1. **白名单**（只允许改动 / 新增这些文件，其余任何文件不得改动）：
   - `backend/services/chat_service.py`（修改）
   - `backend/services/claude_agent.py`（修改）
   - `backend/main.py`（修改）
   - `backend/tests/test_byok_pending_image_access.py`（新增）
   - `docs/tasks/2026-11-03-byok-image-404/03-impl.md`（新增，变更总结）
2. **既有测试一字不许改**：不得修改 `backend/tests/` 下任何既有文件的输入、断言、夹具；新测试只放新文件。
3. 不改 `frontend/`，不改 `.env*`，不加依赖，不加数据表 / 迁移，不动持久化与计费语义（仍是「整轮结束一次最终保存、保存成功才计费」）。
4. **不要 commit**，不要 `git checkout` / `git stash` / 改分支；改动留在工作区由 Claude 门禁。
5. **用工作流（workflow 工具）并行**：在脚本里用 `parallel()` 同时运行 2 个 agent，按文件不重叠拆分：
   - agent A：§4.1–§4.3（`chat_service.py`、`claude_agent.py`、`main.py`）；
   - agent B：§4.4（新测试文件 `backend/tests/test_byok_pending_image_access.py`）。
   每个 agent 的任务说明必须自包含（把本规格对应章节原文贴给它，它看不到你的对话），并写明**不得调用 subagent / subagent_fork / workflow**。agent 不带 schema，直接返回文本。
   主代理只做拆分、派发、汇总、白名单检查、跑 §5 验收、写 `03-impl.md`；报告开头列拆分表，如实列出全部派出过的代理。agent 失败先读它的结果再决定，不许盲目重派。
6. **何时停下来问**：只有「规格自相矛盾」或「按规格无法实现」才停下并说明；只影响「怎么实现 / 怎么验证」的事自己定并在 `03-impl.md` 写明理由。你实测到的事实优先于本规格的断言，不符就停下来说明。任何情况下不回滚已完成的工作。
7. `03-impl.md` 必须含五项：修改了哪些文件 / 实现了什么 / 与 §4 任务清单逐项对应 / §5 每条验收的实际输出 / 未完成或需人工确认的地方。

## 1. 产品目标

自带 Claude 的智能体模式里，模型调用 `generate_image` 工具生成的图片，前端收到生图卡片的那一刻就能加载显示，和平台生图一样；不再出现「图片加载失败，请重试。」。

## 2. 现状事实（Claude 已核实，行号按基线 0ca95af）

- `backend/services/claude_agent.py`
  - 736–740 行：`if "generated_image" in payload:` 块，记录 `image_path = payload["generated_image"]["image_path"]`、`delivered = True`、`billable_pending = True`，随后该事件在 752 行 `yield event` 发给客户端。
  - 487–510 行 `save_delivered()`：调用 `chat._save_response(ctx, state, image_path=...)` 入库，成功后 `persisted_image_path = saved_image_path`。它只在整轮结束时被调用（834、842、865 行）。
  - 867–872 行 `finally:`：`image_path = image_path or (owned_image_result or {}).get("image_path")`，未入库的图 `chat.delete_uploaded_files([image_path])`。
- `backend/main.py`
  - 49 行：`from services.chat_service import shutdown_byok_pool`
  - 238–244 行 `_can_view_generated_image(username, image_path)`：只查 `messages` 表（`database.message_references_image`）。
  - 317–318 行：`generated_` / `reference_` 开头的 `/uploads/...` 校验不过 → `404 {"detail": "图片不存在或无权访问"}`，`Cache-Control: private, no-store`。
  - 中间件传入的 `image_path` 是 `posixpath.normpath` 后的 `/uploads/generated_<32 hex>.png`，与 SSE 事件里的 `image_path` 字符串完全相同（都来自 `tools/image_generation.py` 454 行 `f"/uploads/{filename}"`）。
- `backend/services/chat_service.py`
  - 71–73 行：`_IMAGE_GENERATION_USERS: set[str]`、`_BYOK_USERS: set[str]`、`_BYOK_ACTIVE` 都是进程内状态，现有限流 / 占位逻辑已经依赖「单进程 uvicorn」这一部署事实。
  - 1105–1121 行：平台生图（`agent_result is None`）先 `await _save_response(...)` 再 `yield _sse({"generated_image": generated})`；智能体路径（`agent_result is not None`）只 `agent_result.update(success=True, image_path=..., model=..., aspect_ratio=...)` 后就 `yield`，入库交给智能体最后统一做。
- 前端 `frontend/components/GeneratedImage.tsx` 60–75 行：收到 `imageUrl` 立即 `apiFetch`，`!response.ok` 即显示「图片加载失败，请重试。」。前端不需要改。
- 测试基线（Claude 在基线 0ca95af、本 worktree 的 `backend/.venv` 实测）：
  - 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：`7863 passed, 35 warnings in 355.92s`（0 failed、0 skipped；输出存 `verify/00-baseline-full-0ca95af.txt`）
  - 子集（§5-B 那 6 个文件）：`322 passed, 33 warnings in 11.81s`（0 failed、0 skipped；输出存 `verify/00-baseline-subset-0ca95af.txt`）
- 测试夹具（`backend/tests/conftest.py`）：收集阶段已把 `FIONA_DB_PATH` / `FIONA_UPLOADS_DIR` 指到会话临时目录（27 行）；`client` fixture 设 `DEV_MODE=1`、临时库、`TestClient(main.app, client=("127.0.0.1", 50000))`（91–142 行）；`dev_headers` = `{"X-Dev-User": "smoke_tester"}`（145–147 行）。
- 智能体测试夹具（`backend/tests/test_claude_agent_runtime.py` 59–115 行）：`harness` 返回 `NS(agent, chat, ctx, state, streams, saves, deleted, monkeypatch, …)`，已把 `chat._save_response`（记录到 `h.saves` 并置 `response_saved=True`）、`chat.delete_uploaded_files`（记录到 `h.deleted`）、`agent.open_agent_stream`（按 `h.streams` 顺序回放 `FakeStream`）等打桩；`run(h)` 同步收集全部事件。`tests/test_claude_agent_r1_runtime.py` 13 行 `from test_claude_agent_runtime import FakeStream, call, harness, message, run` 就是复用方式，其 16–27 行是模块级封网 fixture，83–96 行是「假 `_stream_image_execution`」写法，70–79 行是手动 `anext` 消费流的写法。

## 3. 方案（已定，不改方向）

进程内「待入库生成图」登记表：智能体把 `generated_image` 事件交给客户端之前，先登记 `(username, image_path)`；`/uploads` 中间件对登记中的图放行给该用户；智能体本轮在 `finally` 里无条件注销（入库成功、入库失败并删图、客户端断开、预算耗尽、异常都走这里）。

不改前端；不改持久化与计费顺序；不加表。登记表与 `_IMAGE_GENERATION_USERS` 同为进程内状态（单进程部署）。

## 4. 执行者任务清单

### 4.1 `backend/services/chat_service.py`（agent A）

在 71 行 `_IMAGE_GENERATION_USERS: set[str] = set()` 所在的模块级常量区之后、第一个函数定义之前，新增（名字、签名一字不差，三个函数都是模块级函数）：

```python
# Generated images the Claude agent has already shown to the client but not yet persisted.
# Process-local like the limits above; the agent releases every entry in its finally block.
_PENDING_GENERATED_IMAGES: set[tuple[str, str]] = set()


def claim_pending_generated_image(username: str, image_path: str) -> None:
    _PENDING_GENERATED_IMAGES.add((username, image_path))


def release_pending_generated_image(username: str, image_path: str) -> None:
    _PENDING_GENERATED_IMAGES.discard((username, image_path))


def is_pending_generated_image(username: str, image_path: str) -> bool:
    return (username, image_path) in _PENDING_GENERATED_IMAGES
```

不改本文件其他任何行。

### 4.2 `backend/services/claude_agent.py`（agent A）

a) 736–740 行 `if "generated_image" in payload:` 块内，紧跟 `image_path = payload["generated_image"]["image_path"]` 之后加一行：

```python
                                            chat.claim_pending_generated_image(ctx.user, image_path)
```

必须通过模块属性 `chat.claim_pending_generated_image(...)` 调用（测试会对 `chat` 模块打桩），必须在该事件被 `yield` 给客户端之前执行。

b) 867–872 行 `finally:` 块改为：

```python
    finally:
        # An image can finish while the caller is suspended at a heartbeat.
        # The adapter has transferred ownership even before its event is read.
        image_path = image_path or (owned_image_result or {}).get("image_path")
        if image_path:
            chat.release_pending_generated_image(ctx.user, image_path)
        if image_path and image_path != persisted_image_path:
            chat.delete_uploaded_files([image_path])
```

即：先注销登记，再按原逻辑决定是否删图；两者都在 `finally` 内，不受异常影响。不改本文件其他任何行。

### 4.3 `backend/main.py`（agent A）

a) 49 行改为：

```python
from services.chat_service import is_pending_generated_image, shutdown_byok_pool
```

b) 238–244 行 `_can_view_generated_image` 改为（登记命中时不开库连接）：

```python
async def _can_view_generated_image(username: str, image_path: str) -> bool:
    """Generated results and uploaded references inherit message ownership.

    An image the Claude agent has just shown to its owner is viewable before the
    reply is persisted; the agent releases that claim when the turn ends.
    """
    if is_pending_generated_image(username, image_path):
        return True
    import aiosqlite
    import database

    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        return await database.message_references_image(db, image_path, username=username)
```

不改本文件其他任何行。

### 4.4 新测试 `backend/tests/test_byok_pending_image_access.py`（agent B）

文件头照抄 `tests/test_claude_agent_r1_runtime.py` 的导入与模块级封网 fixture（禁止真实 TCP / DNS），并 `from test_claude_agent_runtime import FakeStream, call, harness, message, run`。常量 `PATH = "/uploads/generated_" + "c" * 32 + ".png"`。

假执行核心（T1–T3 共用，照 r1 文件 83–86 行）：

```python
async def image(ctx, state, prompt, *, agent_result, **kwargs):
    agent_result.update(success=True, image_path=PATH, model="model", aspect_ratio="1:1")
    yield h.chat._sse({"generated_image": {"image_path": PATH, "model": "model", "width": 16, "height": 9}})
    yield h.chat._sse({"text": "图片已生成。"})
```

用 `h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)` 打桩；流回放 `h.streams.extend([FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])), FakeStream(message(text="完成"), "完成")])`。

- **T1 `test_generated_image_is_viewable_from_the_event_until_persisted`**
  - `_save_response` 换成自定义 save：断言调用时 `h.chat.is_pending_generated_image(h.ctx.user, PATH)` 为 True（登记必须早于入库）、`not state.billable`，记录 `h.saves.append((state.full_response, image_path))`，置 `state.response_saved = True`。
  - 手动 `async for event in h.agent.stream_claude_agent(h.ctx, h.state)` 消费：收到包含 `"generated_image"` 的事件那一刻，断言 `is_pending(...)` 为 True 且 `h.saves == []`；必须真的收到过这个事件（用标志位断言）。
  - 流结束后：`h.saves == [(任意, PATH)]`（长度 1 且第二项为 PATH）；`is_pending(...)` 为 False；`h.deleted == []`；`h.state.billable` 为 True。
- **T2 `test_failed_persistence_releases_claim_and_deletes_image`**
  - `_save_response` 抛 `RuntimeError("conversation no longer available")`。
  - `with pytest.raises(RuntimeError): run(h)`；之后 `is_pending(...)` 为 False、`h.deleted == [PATH]`、`not h.state.billable`。
- **T3 `test_client_disconnect_after_image_event_releases_claim`**
  - 用 `anext` 消费到包含 `"generated_image"` 的事件后立即 `await stream.aclose()`（参照 r1 文件 70–79 行）。
  - 之后 `is_pending(...)` 为 False、`h.deleted == [PATH]`、`h.saves == []`、`not h.state.billable`。
- **T4 `test_uploads_route_serves_pending_image_only_to_its_owner`**（用 conftest 的 `client`、`dev_headers`）
  - `from utils import media`；`name = "generated_" + "d" * 32 + ".png"`；用 PIL 生成一张合法 PNG 写到 `Path(media.UPLOADS_DIR) / name`（临时上传目录）。
  - 未登记：`client.get(f"/uploads/{name}", headers=dev_headers)` → 404。
  - `chat.claim_pending_generated_image("smoke_tester", f"/uploads/{name}")`（放在 `try` 里，`finally` 必须 `release`）：
    - 同用户 GET → 200，`content-type` 以 `image/png` 开头，`cache-control` 含 `no-store`，响应体字节等于写入的 PNG；
    - 另一用户 `headers={"X-Dev-User": "someone_else"}` GET → 404；
    - 另一个未登记的文件名（如 `"generated_" + "e" * 32 + ".png"`，文件不必存在）GET → 404。
  - `release` 后同用户 GET → 404。
  - 测试结束时 `chat._PENDING_GENERATED_IMAGES` 必须为空（断言）。

要求：4 个测试全部通过、0 skipped；不连网；不读仓库外文件；不依赖 git 历史。

## 5. 验收标准（在 `backend/` 目录执行；每条都要把实际输出贴进 `03-impl.md`）

- **A** `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_byok_pending_image_access.py` → 输出含 `4 passed`，无 `failed`、无 `skipped`。
- **B** `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_claude_agent_runtime.py tests/test_claude_agent_r1_runtime.py tests/test_image_generation.py tests/test_crisis_resource_paths.py tests/test_chat_multi_image_editing.py tests/test_health_and_startup.py` → 全过，passed 数与 §2 子集基线一致，skipped 不多于基线。
- **C** `.venv/bin/python -m pytest -q -p no:cacheprovider` → `failed` 为 0，passed = §2 全量基线 passed + 4，skipped 不多于基线。（耗时较长，跑一次即可。）
- **D** `.venv/bin/python ../docs/tasks/2026-11-03-byok-image-404/verify/repro_byok_image_race.py "$PWD"` → 最后一行 `VERDICT: FIXED`，且 `http_at_event: (200, 'image/png', …)`、`http_after_stream: (200, 'image/png', …)`、`file_exists_after: True`、`response_saved: True`。
- **E** 在仓库根 `git status --porcelain` 只有：` M backend/main.py`、` M backend/services/chat_service.py`、` M backend/services/claude_agent.py`、`?? backend/tests/test_byok_pending_image_access.py`、`?? docs/tasks/2026-11-03-byok-image-404/`。
- **F** `git diff --stat -- backend/tests` 为空（既有测试零改动）。
- **G** `git diff -- backend/main.py backend/services/chat_service.py backend/services/claude_agent.py | grep -c '^[-+][^-+]'` 的数字不超过 40（改动只做 §4 列出的那几处）。

## 6. 不接受的设计

- 把入库提前到收到图片时、或拆成两条消息（改变「一次最终保存、保存成功才计费」的既有契约，`tests/test_claude_agent_r1_runtime.py` 整组测试守着它）。
- 前端对 404 自动重试来掩盖顺序问题。
- 放宽中间件：对所有 `generated_` 图跳过归属校验、或按「文件存在」放行。
- 新建数据表、后台清理任务、新依赖。
