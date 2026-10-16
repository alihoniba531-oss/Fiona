# WO1 短片工作室：后端地基（单镜「首帧 + 提示词 → 报价 → 确认 → 成片」）

> 所属项目：Fiona「短片工作室」，这是 12 期中的第 1 期。这一期只做后端，不改前端。
> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。
> 上一期（WO0）的真实接口实测见 `docs/tasks/2026-10-16-studio-wo0-probe/06-probe-results.md`，**必读**。
> WO0 的探针实现 `backend/scripts/_studio_probe_*.py` 里，请求写法已经过真实接口验证，可作为参考，但不要从业务代码 import 它们。

## 1. 产品目标与使用场景

「短片工作室」是 Fiona 里**只开放给作者本人**的功能，用于把小说一步步做成 AI 短剧。本期只搭地基，做完后作者能用 curl 完成下面这条流程：

1. 建一个项目。
2. 上传一张首帧图。
3. 对「首帧 + 提示词」请求报价。可选万相 3.0 或 Seedance 2.5，默认万相 480P、5 秒、带原生音频。
4. 确认报价。确认后任务进入后台队列。
5. 后台调度器负责提交（付费 POST 只发一次）、轮询、下载、校验、结算。
6. 作者查询任务状态，拿到成片文件（支持 Range，可在浏览器里拖动播放）。

需要同时做到：重启后不重复提交；花钱上限写进数据库，任何开关都绕不过去；非作者完全看不到这个功能。

## 2. 技术约束

- 沿用现有技术栈：FastAPI、aiosqlite（SQLite）、httpx、Pillow；外部命令只用 ffprobe。**不新增任何依赖。**
- **数据库只做新增**：只新建表和索引，不修改、不删除已有表和列。建表语句放在 `backend/studio/store.py` 的 `STUDIO_TABLES_DDL` 里，由 `database.py` 的 `init_db()` 统一执行，写法参照 `database.py:311-318` 小说工坊和本机监控的做法。
- **开关和配置在调用时读取**：环境变量每次调用时读。非法值回落默认，并且只告警一次，参照 `rate_limit.py` 中 `_DAILY_SETTINGS` 的写法。`FIONA_STUDIO` 只有字面 `0` 表示关闭。
- **不改动无关模块**：不重构现有代码；修改集中在第 5 节列出的文件。
- **隐私**：日志里只记录 id、状态和错误码，不记录提示词原文、图片和密钥。
- 用户可见的文案用中文，代码注释风格与仓库保持一致。

## 3. 必须遵守的硬规则（验收重点）

1. **付费提交在每个任务的整个生命周期里，最多发出 1 次 POST。** 遇到超时、连接重置、响应读到一半中断、**5xx**、2xx 但没有 task_id 或 JSON 无效，都**不重试**，任务记为 `uncertain`，错误信息里写「可能已扣费，请勿直接重试，去控制台核对」。注意：WO0 探针把 5xx 标成了 rejected，本期按计划**从严**处理，5xx 一律算 uncertain。
2. **上游明确拒绝**：HTTP 4xx 或 429 且响应体完整，记为 `rejected`，释放预留额度，不重试。错误码和错误信息要保留，例如 Seedance 肖像闸拒绝时的错误码。
3. **只读请求可以重试**：查询状态、下载结果失败时，由调度器在之后的 tick 里再试。下载在单次 tick 内最多重试 3 次。
4. **防重复提交**：
   - 每张报价只能确认 1 次，确认第二次返回 409。
   - 报价在 15 分钟后过期，过期只限制「确认」这个动作。确认时锁定价格并预留额度，预留一直保留到任务进入终态。
   - `studio_jobs` 上建一个部分唯一索引：`fingerprint` 在在途状态（queued / submitting / submitted / running / uncertain）范围内唯一。指纹由「参数 + quote_item_id」算出，所以有意让同一提示词多出几版时不会被拦。
5. **重启恢复**，在启动时、调度器启动之前执行：
   - `submitting` → `uncertain`，错误信息写明「服务重启时请求可能已发出」。
   - `submitted` / `running` 保留，立即恢复轮询。
   - 已经 `succeeded` 但还没下载的，保留，交给调度器下载。
   - `queued` 保留。
   - **恢复过程中 POST 次数为 0。**
6. **花钱上限写进数据库**，`DEV_MODE=1` 时照样生效。上限按 Asia/Shanghai 的自然日计算，日期以确认时间为准。当日已占用金额 = 已结算的实际金额 + 在途和 uncertain 任务的预留金额；rejected、cancelled，以及经作者确认未扣费而释放的任务，都按 0 计。
7. **准入**：
   - 所有 `/studio/*` 路由（包括文件下载）必须同时满足：`FIONA_STUDIO != "0"`；当前用户在 `FIONA_STUDIO_OWNERS` 里（逗号分隔，去掉空白后精确匹配）；鉴权方式是 JWT（Bearer 或 Cookie）。
   - 不满足任何一条，一律返回 `404 {"detail":"Not Found"}`，响应头带 `Cache-Control: private, no-store`。
   - 只有当 `FIONA_STUDIO_REQUIRE_JWT == "0"` 时，才允许 `X-Dev-User` 开发通道访问。
   - 为此，`main.py` 的鉴权中间件（`:244-273`）要在 `request.state.auth_method` 里写入 `"jwt"` 或 `"dev"`，不改变其他任何行为。
8. **文件**：
   - 只存在 `FIONA_STUDIO_DIR` 下，默认 `backend/studio_data/`，**不挂到 `/uploads` 静态目录**。
   - 前端只能按 asset_id 获取文件。服务端要校验归属，并确认解析后的真实路径在工作室目录之内。
   - 用 `FileResponse` 返回，支持 Range，响应头带 `Cache-Control: private, no-store`。
9. **结果下载**：
   - host 必须匹配白名单 `FIONA_STUDIO_VIDEO_HOSTS`，逗号分隔、支持 `*` 通配。默认值 `*.oss-accelerate.aliyuncs.com,*.oss-cn-beijing.aliyuncs.com,*.tos-cn-beijing.volces.com`（来自 WO0 实测）。
   - 不跟随重定向；大小不超过 300MB；先写临时文件，完整后再改名；不向结果 host 转发任何鉴权头。
   - 下载后用 ffprobe 校验，**按时长判断，不按帧数**：时长不小于请求时长减 0.2 秒，否则判 `failed`，错误码 `short_output`。因为万相是 30fps、Seedance 是 24fps。
10. **首帧**：
    - 万相首帧必须没有透明通道，边长在 240–8000 之间，文件不超过 20MB。不合格时，在报价阶段就返回 422。
    - **Seedance 提交前，先把首帧等比缩到不大于输出分辨率**（480p 的长边 ≤ 854、短边 ≤ 480；720p 为 1280×720；1080p 为 1920×1080），再编码成 data URI。只有在提交时内存里做，原始素材不变。
    - 万相不缩放。

## 4. 数据表（`backend/studio/store.py`）

| 表 | 字段（可按需补充，但不能少于这些） |
|---|---|
| `studio_projects` | id（uuid 文本主键）、owner、title、aspect（`16:9` / `9:16`）、created_at、updated_at、archived |
| `studio_assets` | id、project_id、owner、kind（image / video / audio）、source（upload / generated）、rel_path、sha256、bytes、width、height、duration_s、fps、has_audio、meta_json、archived、created_at |
| `studio_quotes` | id、project_id、owner、items_json、total_min_cny、total_max_cny、params_hash、status（open / confirmed）、created_at、expires_at、confirmed_at |
| `studio_jobs` | id、project_id、owner、kind（`i2v`）、provider（`wan` / `seedance`）、model、params_json（**不存 base64**，首帧只存 asset_id）、fingerprint、quote_id、quote_item_id、status、task_id、run_token、est_min_cny、est_max_cny、reserved_cny、actual_cny、usage_json、result_host、result_asset_id、error_code、error_message、needs_recheck、next_poll_at、submitted_at、finished_at、created_at、updated_at |

任务状态机：
```
queued → submitting → submitted → running → succeeded → downloaded
```
旁支状态：

| 状态 | 含义 | 预留额度 |
|---|---|---|
| `rejected` | 上游明确拒绝 | 释放 |
| `uncertain` | 结果不确定，可能已扣费 | 保留 |
| `failed` | 上游任务失败，或下载后校验不通过 | 有 usage 就按 usage 结算，没有记 0 |
| `filtered` | 版权或内容过滤拦截 | 记 0 |
| `expired` | 结果地址已过期 | 按 usage 结算 |
| `cancelled` | 在 queued 阶段取消 | 释放 |
| `released` | 作者确认未扣费后释放 | 记 0 |

所有状态转换都用 `UPDATE … WHERE id=? AND status=? [AND run_token=?]` 这种带条件的写法，并检查受影响行数。

## 5. 文件清单

**新增**
- `backend/studio/__init__.py`
- `backend/studio/config.py`：所有 `FIONA_STUDIO_*` 配置的读取，默认值与合法范围都在这里。
- `backend/studio/gate.py`：准入判断，供路由依赖使用。
- `backend/studio/store.py`：DDL 与数据库读写。
- `backend/studio/storage.py`：目录、原子写、路径安全、文件响应、ffprobe 封装。
- `backend/studio/pricing.py`：价目与报价。
- `backend/studio/spend.py`：额度预留、结算、当日占用。
- `backend/studio/providers/__init__.py`
- `backend/studio/providers/base.py`
- `backend/studio/providers/video_wan.py`
- `backend/studio/providers/video_seedance.py`
- `backend/studio/scheduler.py`
- `backend/studio/recovery.py`
- `backend/routers/studio.py`
- `backend/tests/test_studio_*.py`：可拆成多个文件。

**修改**
- `backend/main.py`：
  - 注册 `studio.router`。
  - 在 lifespan 里，`recover_interrupted_novels()` 之后执行 `recover_studio_jobs()`，再用 `create_background_task` 启动调度循环。关停时调度循环要能被现有的 `shutdown_background_tasks` 取消。
  - 鉴权中间件写入 `request.state.auth_method`。
  - `/health` 增加一项：`FIONA_STUDIO != "0"` 时检查工作室目录可写，检查项名为 `studio_storage`。
- `backend/database.py`：
  - `init_db()` 执行工作室的 DDL。
  - 删号流程（`database.py:903` 一带）在同一个事务里删除该用户的 `studio_*` 行，并把 `<FIONA_STUDIO_DIR>/<project_id>/` 目录加入清理队列。
- 上传清理器：读 `routers/me.py:54-101` 与 `upload_cleanup_queue` 的处理代码，让它能删除**位于 FIONA_STUDIO_DIR 之内的目录**。目录外的路径一律拒绝，现有的文件删除行为不变。
- `backend/tests/conftest.py`：
  - `FIONA_STUDIO_DIR` 指向会话临时目录。
  - `os.environ.setdefault("FIONA_STUDIO_OWNERS", "")`。
- `deploy/fiona-backup.sh`：工作室目录存在时增加第三个 tar 包，规则与 uploads 相同（`.part` 文件和隐藏文件不打包，保留天数相同）。
- `backend/.env.example`：补上第 6 节的全部变量，以及 `DASHSCOPE_WORKSPACE_ID`，附中文说明。
- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`：**在全库里搜索相关陈述**（鉴权、/health 检查项、备份内容、删号清理、单进程约束等），逐处更新到与新事实一致，不要只改预先想到的几处。生产环境的 `FIONA_STUDIO_DIR` 写为 `/var/lib/fiona/studio`，理由：systemd 只允许写 `/var/lib/fiona`，见 `docs/DEPLOYMENT.md:274,280`。另外写明「调度器在进程内运行，只支持单 worker」。

## 6. 配置（`backend/studio/config.py`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `FIONA_STUDIO` | 开 | 只有字面 `0` 关闭 |
| `FIONA_STUDIO_OWNERS` | 空 | 逗号分隔的用户名；为空时任何人都不能访问 |
| `FIONA_STUDIO_REQUIRE_JWT` | 开 | 只有字面 `0` 才允许 dev 通道 |
| `FIONA_STUDIO_DIR` | `backend/studio_data` | 工作室文件根目录 |
| `FIONA_STUDIO_DAILY_CNY` | 300 | 正数 |
| `FIONA_STUDIO_MAX_QUOTE_CNY` | 100 | 正数 |
| `FIONA_STUDIO_MAX_INFLIGHT_WAN` | 3 | 1–10 |
| `FIONA_STUDIO_MAX_INFLIGHT_SEEDANCE` | 3 | 1–10 |
| `FIONA_STUDIO_VIDEO_HOSTS` | 见第 3 节第 9 条 | 结果下载的 host 白名单 |
| `FIONA_STUDIO_POLL_TIMEOUT_MIN` | 30 | 超过后设 `needs_recheck=1` 并停止自动轮询 |

## 7. 价目与报价（`backend/studio/pricing.py`）

- **万相 3.0**（`wan3.0-video`、`wan3.0-video-prime`）：480P 0.3、720P 0.6、1080P 1.2 元/秒。报价区间为原价的七折到原价；**实际金额按上游 `usage.duration` × 原价结算**。
- **Seedance 2.5**（模型 id 以 WO0 探针中的默认值为准）：单价 0.07 元/千 token，报价区间下限按 0.05544 元/千 token 算。每秒 token 数**按分辨率分档**：480p 9,700，720p 21,600，1080p 48,938。报价 = 秒数 × 分档速率 × 单价，再乘 0.8–1.2 作为区间。**实际金额按 `usage.completion_tokens` × 0.07/1000 结算。**
- **时长**：取参考实现目录 `~/Desktop/ai-workspace/MCP/seedance-mcp-ts/src/video-catalog.ts` 与 `cost.ts` 中各模型允许的时长，其中整数秒范围以参考实现为准。超出范围时，在报价阶段返回 422。
- **报价时的检查**：总价上限超过 `MAX_QUOTE_CNY` 时返回 422，文案写明上限值。日上限在确认时才检查，但报价响应里要附上当日已占用金额和剩余额度，供界面显示。

## 8. 接口（`backend/routers/studio.py`，全部经过 gate）

| 方法与路径 | 说明 |
|---|---|
| GET `/studio/access` | 返回 `{enabled, caps:{daily_cny, max_quote_cny, inflight:{wan,seedance}}, today:{committed_cny, remaining_cny}}` |
| POST `/studio/projects` | 请求体 `{title, aspect}`，建项目 |
| GET `/studio/projects` | 列出本人项目，按 updated_at 倒序 |
| POST `/studio/projects/{pid}/assets` | multipart 上传图片：PNG / JPEG / WebP，≤20MB；用 Pillow 校验并读取宽高；按 sha256 去重落盘；返回 asset |
| POST `/studio/projects/{pid}/clips/quote` | 请求体 `{first_frame_asset_id, prompt(1–2000字), provider='wan', model?, resolution='480P', duration=5, audio=true}`，返回报价 |
| POST `/studio/quotes/{qid}/confirm` | 在事务里依次检查：未过期、未确认（否则 409）、额度足够（不足返回 409 并说明剩余额度）。通过后建 job（queued）并预留额度。返回 job 列表 |
| GET `/studio/projects/{pid}/jobs` | 列出项目内的任务 |
| GET `/studio/jobs/{jid}` | 单个任务详情 |
| POST `/studio/jobs/{jid}/cancel` | 只能取消 queued 状态的任务，否则 409 |
| POST `/studio/jobs/{jid}/recheck` | 适用于 submitted / running / needs_recheck / 已有 task_id 的 uncertain 任务：立即排一次轮询（只发 GET） |
| POST `/studio/jobs/{jid}/link-task` | 请求体 `{task_id}`，只适用于没有 task_id 的 uncertain 任务。写入 task_id、状态改为 submitted、恢复轮询，**不发 POST** |
| POST `/studio/jobs/{jid}/release` | 请求体 `{not_charged:true, note?}`，只适用于 uncertain 任务。状态改为 released，按 0 计费。`not_charged` 不为 true 时返回 422 |
| GET `/studio/assets/{aid}/file` | 返回文件，见第 3 节第 8 条 |

**项目、素材、报价、任务都按 owner 隔离**：访问别人的资源返回 404。

## 9. 调度器（`backend/studio/scheduler.py`）

- 一个 asyncio 循环，每 2 秒 tick 一次。异常不能让循环退出，捕获后只记录错误码。
- **提交**：
  - 每个 provider 的在途数（submitting / submitted / running）低于上限时，按创建时间先后取 queued 任务。
  - 先抢占：`UPDATE … SET status='submitting', run_token=? WHERE id=? AND status='queued'`，抢到才提交。
  - 提交在线程里执行，或用 httpx 异步执行，不能阻塞事件循环。
- **轮询**：
  - 前 2 分钟每 15 秒一次，之后每 30 秒一次。
  - 超过 `POLL_TIMEOUT_MIN` 后，设 `needs_recheck=1` 并停止自动轮询，只能由作者手动 recheck。
  - 状态映射以 WO0 探针为准：
    - 万相：PENDING / RUNNING → running；SUCCEEDED → succeeded；FAILED / UNKNOWN → failed。
    - Seedance：queued / running → running；succeeded → succeeded；failed → failed；`OutputVideoSensitiveContentDetected` 这类内容过滤 → filtered。
- **下载与结算**：任务成功后下载、用 ffprobe 校验、存为 asset、写入 `result_asset_id`，按第 7 节结算实际金额，状态改为 downloaded。结果地址返回 403 或 404 时，状态改为 expired。

## 10. 离线测试（必须全部用模拟传输，不联网）

WO0 留下的真实响应夹具在 `backend/tests/fixtures/studio/wan-*.json`、`seedance-*.json`，可用来构造模拟响应。

1. **单次 POST**：提交时分别模拟超时、连接重置、响应中断、500、502、2xx 但没有 task_id。断言 POST 只发 1 次，状态为 `uncertain`，额度仍然预留。再分别模拟 400 和 429，断言状态为 `rejected`、额度已释放、POST 只发 1 次。
2. **确认幂等**：同一报价确认两次，第二次返回 409。并发确认（两个协程同时确认）也只会建出 1 批任务。
3. **多版不被误拦**：同一首帧、同一提示词的两张不同报价，都能确认，也都能提交。
4. **过期**：报价过期后确认返回 409 或 410。已经确认的任务排队超过 15 分钟，照样能提交。
5. **恢复**：预置 submitting / submitted / running / succeeded（未下载）/ queued 各种状态，运行恢复后断言 POST 次数为 0，且各状态去向正确。
6. **在途上限**：建 5 个万相任务，同时在途的最多 3 个。万相和 Seedance 的上限各自独立计算。
7. **日上限**：`DEV_MODE=1` 时照样拦。当日已占用 + 本次上限 > 日上限时，确认返回 409。uncertain 任务的预留计入占用，released 计 0。环境变量非法时回落默认值 300，并且只告警一次。
8. **准入**：
   - 非作者访问每一条 `/studio/*`（包括文件）都返回 404。
   - `FIONA_STUDIO=0` 时全部返回 404。
   - 带 X-Dev-User（DEV_MODE=1、回环地址）访问返回 404；设置 `FIONA_STUDIO_REQUIRE_JWT=0` 后才放行。
   - 作者用 JWT（Cookie 或 Bearer）可以正常访问。
9. **文件**：路径穿越被拒（篡改 rel_path 也不行）；Range 请求返回 206；响应头带 no-store；访问别人的 asset 返回 404。
10. **下载**：host 不在白名单时拒绝；遇到 3xx 拒绝；超过 300MB 拒绝；时长不足判 `failed` 且错误码为 `short_output`；结果地址 403 时判 `expired`。
11. **首帧**：万相首帧带透明通道或尺寸越界时，报价返回 422。Seedance 提交的请求体里，首帧已缩到输出分辨率以内（解码 data URI 后断言宽高），并且原始 asset 文件没有变化。
12. **结算**：万相按 `usage.duration` × 原价，例如 480P 5 秒 = 1.50。Seedance 按 `completion_tokens` × 0.07/1000，例如 48,324 → 3.38268。
13. **删号**：删号后 `studio_*` 中该用户的行全部消失，项目目录进入清理队列，清理器能删除这个目录，但拒绝删除工作室目录之外的路径。
14. **/health**：工作室目录不可写时，返回 503 且 failed 里包含 `studio_storage`；`FIONA_STUDIO=0` 时不检查这一项。
15. **既有行为不变**：`/uploads` 的访问规则、聊天鉴权、其他路由的行为都不变。全量测试的失败数与基线一致（基线：5278 passed，0 failed）。

## 11. 验收标准（在 `backend/` 下执行，解释器 `$PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`）

1. `$PY -m pytest -q tests/test_studio_*.py` 全部通过。
2. `$PY -m pytest -q` 全量通过，0 failed。
3. `rg -n "follow_redirects=True|max_retries=[1-9]" backend/studio` 没有任何输出。
4. `rg -n "/uploads" backend/studio` 没有任何输出（工作室不碰 uploads 静态目录）。
5. `git status --porcelain` 只包含第 5 节列出的文件和本规格所在目录。
6. 手工跑一遍「建项目 → 上传首帧 → 报价」（主控用真实服务器和 curl 验收，你不需要联网）。

## 12. 完成后输出的变更总结

必须包含五项：
1. 修改了哪些文件。
2. 实现了哪些功能。
3. 与第 3、8、9、10 节逐条的对应关系。
4. 测试结果。
5. 未完成或需要人工确认的地方，尤其是参考实现与本规格不一致的地方，以及需要真实接口才能核实的点。
