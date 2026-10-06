# 实现报告：重新上线前加固（2026-10-05）

实现基于 `main` 的 `9061a52`，按规格第 2 节六块并行处理，文档由同一个代理统一修改。六块功能已落地，但**尚未全部满足规格或验收**：聊天图片在线程等待期间被调用者取消后的清理与「只改调用一行」要求存在冲突，当前只落实指定的 `await asyncio.to_thread` 调用；B1 有 6 个既有网络夹具用例因绑定本地端口被拒失败，B4 默认 Turbopack 构建因同类权限限制失败。未改既有测试、未加跳过，也未绕过权限限制。新增的 147 个测试全部通过、零 skip；辅助 Webpack 构建通过。

## 1. 按规格逐项对应的实现

### 2.1 上传照片和视频去元数据（S8）

| 文件与行号 | 对应要求与做法 |
|---|---|
| `backend/utils/media.py:54` | 保留原魔数、大小、4000 万像素限制和损坏文案；JPEG 校验接受 MPO，输出只取主帧。 |
| `backend/utils/media.py:72` | `ImageOps.exif_transpose` 后逐帧新建图像并 paste，按 PNG/JPEG/WebP/GIF 原格式保存；JPEG/WebP 显式 `quality=90`，仅显式保留 ICC 与必要动画播放参数，不传 EXIF/XMP/IPTC、PNG 文本或 GIF comment。LA PNG 保留 PNG。GIF/WebP 保留帧数、时长和循环，限制 300 帧、2 亿总像素；GIF 合成全画面帧以 disposal=2 擦除旧画面，保留透明帧显示结果。进程级 `BoundedSemaphore(2)` 控制图像及视频处理并发。 |
| `backend/utils/media.py:134` | 调用时 `shutil.which("ffmpeg")`，无工具返回指定 503，其他错误/超时/空输出返回指定 400。无损 `-c copy`，指定 `0:V:0` 和可选首音轨、去 metadata/chapters/data/subtitles、bitexact；MP4 加 faststart。输出 MP4/MOV/WebM 容器，30 秒超时，无原样保存兜底。额外去除流级 metadata。 |
| `backend/utils/media.py:158` | 临时文件使用调用时的 `media.UPLOADS_DIR`，点前缀随机文件名；输出通过 `os.replace` 原子改名，失败清理输入、输出临时文件及半成品。 |
| `backend/utils/media.py:181` | 广场处理移到线程，取消时等待受保护的在途 worker 结束，再由上传路径清理文件；重复取消也保持清理。 |
| `backend/utils/media.py:239` | 广场两类媒体复用清理函数，流读、校验、写盘、替换任一阶段失败或取消均清理。 |
| `backend/utils/media.py:295` | 聊天同步函数保存清理后的文件，data URI 使用清理后的字节；同步处理失败，包括其自身收到 `CancelledError` 时，清理临时/输出文件。调用者取消等待线程的情形尚未覆盖，见未决问题。 |
| `backend/services/chat_service.py:460` | 严格只把原同步调用改为 `await asyncio.to_thread(_save_uploaded_image, req.image_base64)`，保持函数名和第 49 行按名导入。 |
| `backend/scripts/strip_upload_metadata.py:17` | 按 admin_env 同样的配置选择和环境优先级定位上传目录，支持 `--env-file`。 |
| `backend/scripts/strip_upload_metadata.py:26` | 仅匹配 `plaza_*` 和 32 位十六进制聊天文件名，跳过生成图、参考图、点文件和符号链接。 |
| `backend/scripts/strip_upload_metadata.py:35` | 默认 dry-run，仅输出数量和类型；显式 apply 复用同一套图片/视频处理函数，原子改写；单文件失败跳过计数不中断，保留失败原文件。 |
| `backend/tests/test_upload_metadata.py:107` | 47 个新用例：两条上传路径的 JPEG/GPS/XMP/Artist/拍摄时间/Orientation、PNG 文本与 ICC、多帧 GIF/WebP、MPO、LA PNG、动画超帧/总像素、原子失败、线程/并发、取消清理、存量脚本范围与失败；透明 GIF 的三组混合 disposal 在两条路径共 6 例逐帧 RGBA 一致性检查。 |
| `backend/tests/test_upload_metadata.py:218` | 视频 argv、容器、超时、缺工具 503、其他失败 400 与临时文件清理。 |
| `backend/tests/test_upload_metadata.py:378` | 真实 ffmpeg 生成带定位、时间和流标签及旋转矩阵的短 MP4，上传后 ffprobe 验证私密标签消失、90 度旋转保留、视频流仍在；本次通过，未跳过。 |

**正控**：样本构造首先证明原始字节中确实存在注入的私密标记，视频也先检查处理前有 location 和旋转。HEAD 的原实现把原始图片字节直接保存并返回 data URI，因此图片输出中字节标记消失、EXIF/info 清空和方向转正断言会失败；HEAD 对视频直接写原字节，去标签、调用 remux 和 fail-closed 断言也会失败。未在本 worktree 回退 HEAD 运行这些测试。

### 2.2 下线旧语音合成长连接（B1，用户决定 D2）

| 文件与行号 | 对应要求与做法 |
|---|---|
| `backend/routers/voice.py:17` | 删除旧长连接路由及变成死代码的 WebSocket、ws_authenticate import；保留另外三个 TTS 路由原内容。 |
| `backend/tts_ws.py` | 整文件删除。 |
| `backend/tests/test_tts_ws_limits.py` | 按第 4 节唯一允许的例外整文件删除，移除 2 个旧测试；其他既有测试输入和断言未改。 |
| `backend/tests/test_tts_ws_removed.py:6` | 2 个新测试：路由不存在、Peer 与流式路由仍在；开发态回环 WebSocket 实际连接失败且关闭码不是 4401。 |

`auth_dep.ws_authenticate` 和 `tts.dashscope_timeout_millis` 保留。第 6 节 B5 零命中，以及后端 ws_authenticate 正控，见验收输出。

### 2.3 每日上限（B7，用户决定 D1）

| 文件与行号 | 对应要求与做法 |
|---|---|
| `backend/rate_limit.py:63` | 四项配置在每次调用读取，默认官方 3、热点 30、卡片 30、ASR 300；不为正整数时回落，每个环境变量仅警告一次。 |
| `backend/rate_limit.py:72` | 每次调用检查 `limiter.enabled` 且 `DEV_MODE != "1"`，否则跳过每日上限。 |
| `backend/rate_limit.py:93` | 四类 429 统一返回中文 `detail/error` 与 `retry_after`，头 `Retry-After` 为距离北京次日零点向上取整、最少 1 秒；官方文案带当前 N。 |
| `backend/rate_limit.py:114` | 每日内存计数仍复用 `check_and_hit`，账号和 `database._today_shanghai()` 的日期进入键；让额度调整不改变同日累计键，立即改成 1 不会清空已用计数。原字符串限流解析路径保持兼容。 |
| `backend/exchange_store.py:44` | 新异常 `OfficialDailyCapExceeded` 独立于 `ExchangeConflict`。 |
| `backend/exchange_store.py:464` | 官方 ID 404 保持最前；在已有 `BEGIN IMMEDIATE` 事务中按指定 SQL 统计官方创建记录，超限不 INSERT，包括停止/失败记录，支持并发抢最后一个名额。无新表、无新迁移版本。检查相对旧冲突的顺序见未决问题。 |
| `backend/routers/agent_exchanges.py:78` | 在既有冲突捕获之前捕获每日上限异常并返回统一 429。 |
| `backend/routers/hot.py:20` | 保留 IP 每分钟限流，空标题和缺密钥提前返回之后、模型调用之前按账号计数。 |
| `backend/routers/cards.py:34` | 本地参数校验后、详情工具前按账号计数，保留原 IP 限流。 |
| `backend/routers/voice.py:499` | 仅 ASR 路由添加当前用户依赖；base64、空音频、大小、时长、ffmpeg 转码通过后，在识别模型前计数。已有语音 ffmpeg 参数和另外三个 TTS 路由未改。 |
| `frontend/app/page.tsx:713` | 输入框旁语音识别 429 用现有 micNotice 显示后端 error，其他失败行为保持原样。 |
| `frontend/app/page.tsx:806` | 免提识别 429 显示同文案，关闭免提并追加「，免提已关闭」。 |
| `frontend/components/AgentExchangeWorkspace.tsx:206` | 替换官方体验说明为每个账号每天可体验次数有限，仍说明不扣草莓。 |
| `backend/tests/test_daily_caps.py:114` | 65 个新用例，生产态鉴权与重置 limiter，覆盖 N/N+1、完整 429、账号隔离、换日、开发/关限流不计、运行时配置改变、非法配置、本地失败不计、上游失败仍计、官方并发最后名额、404 顺序、已停止/失败统计、UTC 转北京日期、草莓未扣与 Retry-After 边界。 |

三个内存计数接口会在重启时清零，按规格作为单进程取舍记录在部署、架构、README 和 CLAUDE 文档中；原每分钟 IP 限流叠加保留。

### 2.4 可信代理 IP（O3）

| 文件与行号 | 对应要求与做法 |
|---|---|
| `backend/rate_limit.py:22` | 保持函数名、签名和 limiter 导入期绑定；每次调用解析 `FIONA_TRUSTED_PROXIES`，默认回环、支持 IP/CIDR。仅可信对端采信 X-Real-IP 或 XFF 最后一段；非合法 IP 如 testclient 原样返回，None 对端沿用回环。IPv4 映射 IPv6 展开比较，docstring 解释 uvicorn 已可能改写对端。 |
| `backend/main.py:114` | 更新过时的 IP 信任限流注释，说明由 rate_limit 校验可信代理、uvicorn 可能已改写 client.host。 |
| `frontend/lib/config.ts:4` | 删除过时的独立 API 域名注释，运行逻辑不变。 |
| `backend/tests/test_client_ip_trust.py:23` | 9 个新用例覆盖远端伪造头、可信回环、XFF 兜底、CIDR 调用时变化、testclient、None、IPv4 映射对端与配置。 |

`auth_dep.is_loopback_client` 未改，uvicorn proxy_headers 设置未改。每个入口必须覆盖 X-Real-IP 并追加 XFF；只设置第一个头时，uvicorn 仍可能采信客户端自带 XFF 的局限写入部署与架构文档。

### 2.5 健康检查、启动退出码、清理循环（O4）

| 文件与行号 | 对应要求与做法 |
|---|---|
| `backend/main.py:149` | `/health` 加入公开端点，不需登录、不清 Cookie。原根响应保持不变。 |
| `backend/main.py:237` | `aiosqlite` 以 `mode=rw` URI 打开现有库，1 秒 timeout，核对五个迁移常量及 users 表，调用时检查上传目录存在且可写。200 返回 status ok，失败 503 仅包含检查项名称，无路径、异常、版本或提交，不调用外部服务。 |
| `backend/main.py:81` | 每轮上传清理捕获 Exception，只记录异常类型后继续下一轮；CancelledError 保持传播。 |
| `backend/run.py:13` | `server.serve()` 返回后，若从未成功启动则 `sys.exit(3)`；监听地址和端口不变。 |
| `backend/tests/test_health_and_startup.py:8` | 10 个新用例覆盖公开 200、缺库 503 且不建文件、缺迁移/users、不可写目录、调用时目录变更、URI 与 timeout、started 的退出码以及单次清理失败后继续和取消传播。 |

### 2.6 迁移工具、定时备份、文档（O1、O2、O4、O11）

| 文件与行号 | 对应要求与做法 |
|---|---|
| `backend/migrate.py:21` | 只读盘点迁移前后版本、各表行数和列名，不打印消息内容；预查没有归属用户的消息并明确提示第①道迁移风险。 |
| `backend/migrate.py:52` | 只运行 `database.init_db()`，不恢复交流、不清上传；同进程完成后恢复原 database.DB_PATH。 |
| `backend/migrate.py:72` | 复用 configure_database，支持 env-file，db 优先级最高。默认复制库及存在的 WAL/SHM 到临时目录后迁移副本，明确 in-place 才操作指定库。缺库/配置不可用退出 2，其他失败退出 1，只输出异常类型和中文提示。 |
| `deploy/fiona-backup.sh:3` | POSIX sh、全程 umask 077；路径与保留天数环境变量覆盖。要求运行 UID 与数据库属主一致。在线 `.backup`，独立快照 integrity_check 必须 ok，再 tar 上传。UTC 时间戳加 PID 两份同名配对，成品 chmod 0600，默认 14 天只删除本脚本命名的旧备份，错误非零并清理未完成配对。 |
| `deploy/fiona-backup.service:1` | oneshot、User/Group=fiona、受控环境文件、UMask=0077、明确状态与备份可写目录。 |
| `deploy/fiona-backup.timer:1` | `OnCalendar=*-*-* 04:00:00 Asia/Shanghai`，`Persistent=true`。 |
| `backend/tests/test_migrate_and_backup.py:64` | 14 个新用例覆盖 WAL 源库副本演练原字节不变、in-place 五版本、配置与 db 优先、缺库、孤立消息、只 init、私密内容不打印；真实 sqlite 在线备份、完整性和行数、tar、同戳、0600、过期删除、原侧文件属主、失败非零/清理、timer/service。测试路径含空格和单引号。本次真实备份集成通过，未跳过。 |
| `docs/DEPLOYMENT.md:42` | 补第 5 道迁移。 |
| `docs/DEPLOYMENT.md:62` | ffmpeg 前置条件补广场视频去元数据及建议 ≥6。 |
| `docs/DEPLOYMENT.md:113` | 配置表补可信代理、四个每日上限和备份参数，解释触发条件、账号自然日、内存重启清零。 |
| `docs/DEPLOYMENT.md:236` | Nginx 每个入口双代理头、后端可信代理机制与 uvicorn 局限；首次验证改为 health，保留根为进程级检查。 |
| `docs/DEPLOYMENT.md:420` | 定时备份安装命令、服务账号/0700目录/0600文件、非默认路径 drop-in、异地加密拷贝做法。 |
| `docs/DEPLOYMENT.md:453` | 旧备份副本的只读 schema 盘点、默认迁移演练、孤立消息处理、仅副本 in-place、带 uploads 前缀的媒体恢复、旧元数据清理命令；禁止启动唯一备份，提示启动副作用及 JWT Secret/旧匿名归属限制。 |
| `docs/DEPLOYMENT.md:505` | 外部 api/health 拨测、journalctl、OnFailure 说明，DashScope/DeepSeek 消费告警列为作者发布前手工检查。 |
| `docs/DEPLOYMENT.md:554` | 发布前检查所有反代入口与备份/监控/消费告警；下线历史更新为 2026-10-04 公共 DNS 无解析，桌面卸载和旧密钥删除保持待作者确认。 |
| `README.md:15`、`README.md:118` | 语音能力同步为 HTTP/流式，官方每日上限与其他三项默认额度、内存取舍。 |
| `docs/ARCHITECTURE.md:61`、`:92`、`:106`、`:155`、`:157`、`:184`、`:211` | 同步语音、媒体、每日上限、可信代理、health、迁移/备份/清理与当前局限；精确注明聊天调用者取消尚未落实。 |
| `PLAN.md:120` | 新增 2026-10-05 上线前加固日期节，逐块记录；同步语音、媒体和已完成/仍待完成的运维边界。 |
| `CLAUDE.md:56`、`:67`、`:79` | 仅更新本单相关的额度、可信代理、health、备份/演练、媒体/语音事实句，并记录聊天取消缺口。 |
| `docs/tasks/2026-10-05-prelaunch-hardening/03-report.md:1` | 按第 5 节新增本报告。 |

## 2. 用户决定与第 1 节默认做法

- **D1**：官方交流每天默认 3 次，另外三个付费接口按账号每日封顶，数字可配置，不扣草莓；已实现。
- **D2**：旧语音合成长连接接口、实现和旧测试删除；其他三个 TTS 路由及 Peer 保留，已实现。
- **默认：视频无损 remux、失败拒绝**：已实现，缺 ffmpeg 为指定 503，其他错误/超时为指定 400，无原样保存回退。
- **默认：图片原格式、保留 ICC、动画有限帧**：已实现；MPO 输出 JPEG 主帧，LA PNG 保持 PNG。
- **默认：每日上限仅限流器开启且非开发模式**：调用时判断，已实现。
- **默认：新开 health、根不变**：已实现，无外部依赖探测。

## 3. 第 6 节验收命令、原样输出尾部与退出码

下列保留相应实际运行的输出尾部，未替换或重写输出内容；命令按规格公共写法列出。无输出的命令明确标记无输出。验证使用隔离临时目录，具体本机路径不写入仓库。标准验收失败与辅助验证分开记录。

### B1：后端全量

在 `backend/` 运行 `python -m pytest -q -p no:cacheprovider`。退出码 **1**。原样尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 1685 passed, 5 errors in 49.21s
```

以上 6 个既有用例均因本地 socket bind 的 PermissionError 失败，未修改输入/断言或加 skip。新增 147 用例由媒体 47、语音下线 2、每日额度 65、可信代理 9、健康启动 10、迁移备份 14 组成；总用例应为 `1546 - 2 + 147 = 1691`，本次收集/执行合计 `1685 + 1 + 5 = 1691`，数量吻合，但未达全部通过。

### B2：六份新增测试

在 `backend/` 运行：

```bash
python -m pytest -q -p no:cacheprovider -rs tests/test_upload_metadata.py tests/test_tts_ws_removed.py tests/test_daily_caps.py tests/test_client_ip_trust.py tests/test_health_and_startup.py tests/test_migrate_and_backup.py
```

退出码 **0**，**零 skip**。原样尾部：

```text
...                                                                      [100%]
147 passed in 3.75s
```

### B3：Python 编译

在 `backend/` 运行 `python -m compileall -q .`：**无输出，退出码 0**。

### B4：前端

在 `frontend/` 运行 `npx tsc --noEmit`：**无输出，退出码 0**。

运行 `npm run lint`，退出码 **0**。原样尾部：

```text
✖ 25 problems (0 errors, 25 warnings)
```

运行标准 `npm run build`，退出码 **1**。原样尾部：

```text
- Operation not permitted (os error 1)
    at <unknown> (TurbopackInternalError: [project]/app/globals.css [app-client] (css)) {
  type: 'TurbopackInternalError',
  location: undefined
}
```

Turbopack 创建 worker 需要绑定端口，被运行权限阻止，标准命令未通过。辅助运行 `npm run build -- --webpack`，退出码 **0**，编译及 14 个静态页面生成成功。原样尾部：

```text
ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

### B5：旧语音实现零命中与正控

```bash
git grep -n -e 'tts/ws' -e 'tts_ws' -e 'handle_tts_ws' -e 'TTS_WS' -- . ':!docs/tasks'
```

**无输出，退出码 1**（git grep 无命中）。

```bash
git grep -c ws_authenticate -- backend
```

退出码 **0**。原样输出：

```text
backend/auth_dep.py:1
backend/main.py:1
backend/routers/peer.py:3
```

### B6：已有测试仅允许的删除

运行 `git diff --stat -- backend/tests`，退出码 **0**。原样输出：

```text
 backend/tests/test_tts_ws_limits.py | 46 -------------------------------------
 1 file changed, 46 deletions(-)
```

运行 `git status --porcelain backend/tests`，退出码 **0**。原样输出：

```text
 D backend/tests/test_tts_ws_limits.py
?? backend/tests/test_client_ip_trust.py
?? backend/tests/test_daily_caps.py
?? backend/tests/test_health_and_startup.py
?? backend/tests/test_migrate_and_backup.py
?? backend/tests/test_tts_ws_removed.py
?? backend/tests/test_upload_metadata.py
```

### B7：仓库本机路径检查

运行 `git grep -n -E '/Users/' -- . ':!docs/tasks'`：**无输出，退出码 1**。

### B8：真实用户样本

按规格交由 Claude 主会话/作者用真实手机照片及 GPS 视频独立复核，本次未执行；本单已有真实 ffmpeg/ffprobe 与真实 sqlite3 的离线集成测试通过。

### 补充静态检查

`git diff --check` 与 `sh -n deploy/fiona-backup.sh`：均**无输出，退出码 0**。

## 4. Git 状态与白名单

创建本报告后运行 `git status --porcelain`，退出码 **0**，原样输出（含未跟踪目录）：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/exchange_store.py
 M backend/main.py
 M backend/rate_limit.py
 M backend/routers/agent_exchanges.py
 M backend/routers/cards.py
 M backend/routers/hot.py
 M backend/routers/voice.py
 M backend/run.py
 M backend/services/chat_service.py
 D backend/tests/test_tts_ws_limits.py
 D backend/tts_ws.py
 M backend/utils/media.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/AgentExchangeWorkspace.tsx
 M frontend/lib/config.ts
?? backend/migrate.py
?? backend/scripts/strip_upload_metadata.py
?? backend/tests/test_client_ip_trust.py
?? backend/tests/test_daily_caps.py
?? backend/tests/test_health_and_startup.py
?? backend/tests/test_migrate_and_backup.py
?? backend/tests/test_tts_ws_removed.py
?? backend/tests/test_upload_metadata.py
?? deploy/
?? docs/tasks/2026-10-05-prelaunch-hardening/
```

该目录中 `02-spec.md` 在任务开始时就已未跟踪，本次未修改；默认 status 把规格与新报告合并显示为目录。运行 `git status --porcelain --untracked-files=all docs/tasks/2026-10-05-prelaunch-hardening`，退出码 **0**，原样输出：

```text
?? docs/tasks/2026-10-05-prelaunch-hardening/02-spec.md
?? docs/tasks/2026-10-05-prelaunch-hardening/03-report.md
```

`deploy/` 仅含本报告列出的备份脚本、service 和 timer。所有本次改动/新增均在第 2 节白名单与本报告之内，无其他既有测试改动。未使用 Git 写命令；临时测试、缓存和编译产物已清理。

## 5. 未决问题、偏离与自主判断

1. **聊天线程等待取消的规格冲突尚未解决**：第 2.1 节要求调用行只能改为指定 to_thread，另外又要求任何 CancelledError 清理全部文件。调用者取消 to_thread 的 await 不会停止工作线程，也不会把异常注入同步函数；严格只改调用一行时，无法可靠获知线程最终输出并清理。当前保留一行要求，没有扩展调用端保护代码；广场取消与同步处理自身的失败已覆盖。需要作者确认允许最小增加调用端保护逻辑后补齐，并增加针对调用者取消的测试。未把当前实现称为完整满足取消要求。
2. **B1/B4 标准验收未通过**：6 个既有本地网络用例因端口权限失败，默认 Turbopack 构建因创建 worker 的端口权限失败。需要在允许这些本地端口操作的环境独立重跑原命令；没有改旧测试、跳过失败或改默认 build 配置。辅助 Webpack 成功不能替代默认 build 验收。
3. **输出记录方式与临时目录**：按用户要求保留原样输出尾部，避免将包含本机路径的完整错误堆栈或 lint 文件列表写入公开仓库；未把替换后的日志冒充原样输出。测试临时根选工作树根目录，以满足既有隔离测试不落在 backend 真数据区的断言。默认 Turbopack 首次失败时工具自行把 panic 诊断写入系统临时目录，该文件未读取；后续验证的临时/缓存输出约束在工作树内，验收后清理。
4. **每日官方检查顺序有明确偏离**：官方 404 与用户存在检查仍在最前；每日计数放在事务中、旧活动冲突检查之前，而规格指定旧冲突之后紧邻 INSERT 的位置。这样已用完每日额度的账号优先得到 429；配额仍在原写事务内、INSERT 前，活动冲突请求不增加创建计数。此优先级由实现自行判断，应由作者复核。
5. **每日内存键与输入细节**：为使运行时额度降低立即生效且不清空已用次数，新增只覆盖 key_for 的 `_DailyLimitItem`，不修改全局 limits parser；四项配置接受 ASCII 数字组成的正整数，不接受符号/空格，逐环境变量警告一次。Retry-After 使用实时 UTC+8 时钟计算，计数日期仍经指定模块属性函数；第三方上游失败不退还，三个接口重启清零是规格明确取舍。热点路由额外复用工具本地校验和同形响应，确保空标题/缺密钥不计数。
6. **可信代理解析细节**：忽略非法 IP/CIDR 项；显式空配置表示不信任任何代理；CIDR 用 strict=False 接受带主机位的写法。除规格要求的 mapped 对端外，额外支持 mapped 单 IP/CIDR 配置并展开比较。uvicorn 已改写 ASGI 对端时的行为按规格背景保留，不改变回环鉴权。
7. **图片与视频实现细节**：调色板图转 RGB/RGBA 以保留像素/透明度；JPEG 不支持的模式转 RGB，LA PNG 原模式保留；APNG 只输出主帧，因为规格只要求 GIF/WebP 动画。Pillow 解码后的 GIF 已是合成全画面帧，因此保存时显式 disposal=2，每帧显示后清空旧画面，防止透明部分残留上一帧像素；三组源 disposal 策略逐帧 RGBA 正控/输出一致性已加入两路径测试。临时文件 mkstemp 权限为 0600；同一个 2 槽信号量同时约束图像和视频。额外 `-map_metadata:s -1` 清流标签，空视频输出视为失败，超时取允许上限 30 秒。未验证旧 ffmpeg 的旋转兼容，文档保留 ≥6 建议。
8. **存量媒体脚本细节**：跳过符号链接以避免清理上传目录以外的目标；旧 3GP 内容 remux 为 MP4 后仍保留旧文件名，避免打断已有数据库引用。单文件失败统计后整批退出 0；目录缺失退出 2，其他整体异常退出 1。调用者必须检查失败计数，不能仅看退出码判断每个文件成功。
9. **迁移工具判断**：隐藏 configure_database 原有路径诊断，缺库与配置不可用统一退出 2，其他失败退出 1；每次迁移后恢复原模块 DB_PATH，便于同进程使用。旧主库/WAL/SHM 逐文件复制只适用于稳定的离线副本，不能替代在线 `.backup`；报告与文档已明确。孤立消息只提示、不猜归属、不补虚构用户、不写成功标记。
10. **备份命名、权限与失败策略**：自行选 `FIONA_BACKUP_DIR`、`FIONA_BACKUP_RETENTION_DAYS`，默认路径与服务账号沿用部署基线；属主 UID 不匹配时拒绝运行。UTC 时间戳加 PID 避免同秒并行覆盖，数据库快照转 DELETE journal 以获得独立可恢复文件并消除临时侧文件。目标固定安全文件名配合 cd，支持目录空格/引号。保留期按完整 24 小时达到 N 天删除，只清理本脚本命名；失败清理不完整配对，完整配对在保留清理失败时保留。
11. **媒体 tar 与一致性边界**：为任意源目录固定归档 `uploads/` 前缀，创建受控临时 symlink 并用 tar -h；它也会跟随源树内符号链接，上传目录应由服务账号受控。数据库 `.backup` 是在线一致快照，之后 tar 并不是跨文件系统同一时点事务；要求严格一致恢复点时需停写。service 使用 ProtectSystem 与默认 ReadWritePaths，非默认状态/备份路径需作者配置 drop-in 扩充。
12. **health 失败归类判断**：数据库无法打开只列 database，不再连带列 schema；users 表或迁移结构缺失列 schema。URI 使用 Path.as_uri 转义，核对五个已知迁移版本集合均存在，不要求版本表恰好只有 5 条，以便以后追加迁移。没有在健康检查写测试文件来验证目录权限，只用目录存在与 os.access。
13. **测试正控与下线检查判断**：下线路径在新测试里使用字符串拼接，以使全仓库 B5 零命中仍覆盖实际路由；保留了独立 Peer/TTS 流式正控。媒体正控以原始样本包含私密信息证明有效，未回退 worktree 重跑 HEAD。新测试只在缺 ffmpeg 或缺 sqlite3 时允许跳过；有 ffmpeg 但缺 ffprobe 会明确失败，不新增规格之外的 skip 类别。本次均零 skip。
14. **文档中的恢复处置建议**：给出孤立消息先只读计数、从可信记录恢复 owner、无法确认先保全另一副本；只有作者明确可删时才在演练副本执行删除。已有 owner 字段不因 JWT Secret 变化消失，旧 MD5 仅匹配时兼容；建议先在受控副本用匹配旧 Secret 核对回填，再决定换密钥方案。DNS 下线事实按规格给定的 2026-10-04 历史记录更新，未联网复查。
15. **仍需作者/独立验收执行**：真实手机照片与 GPS 视频复核、实际旧备份迁移与媒体恢复演练、Linux systemd 安装与 timer/失败通知、异地备份传输、所有反代入口检查、DashScope/DeepSeek 控制台消费告警、桌面卸载和旧 API Key 删除。没有启动服务、浏览器或接入第三方监控，也没有操作真实备份、密钥或线上数据。

第 0、3、4 节边界：未新增依赖、未改 requirements/package/lock/CI，未改危机识别、费用持久化或独立 API 域名拓扑；既有测试仅删除指定整文件。临时验收产物清理后，改动仅限白名单。尚未解决的取消与验收限制如上，没有回滚已经完成的实现。

## 第 1 轮返修

依据 `05-fix-round1.md` 完成 F1 和第 2 节 1–13。以下是相对第 0 轮工作区的返修记录；前文保留为历史，涉及取消、GIF disposal、清理脚本退出码和迁移提示的旧结论以本节为准。实现项已完成，但 B1/B4 标准验收未全绿：有两项旧断言与新要求冲突，另有六项旧 HTTP 用例和标准构建受到本地端口权限限制，详见验收与未决问题。

### 1. 逐项对应、文件与行号

| 项目 | 本轮改法与定位 | 验证定位 |
|---|---|---|
| F1 | `backend/utils/media.py:99`、`:128`、`:142`：仅透明源或解码帧实际含透明像素时设置 `disposal=2`；不透明 GIF 不传 disposal，保留 Pillow 帧间差分。 | `backend/tests/test_upload_metadata.py:484` 两路径 100 帧复杂静态背景加小块运动，输出 ≤ 输入 2 倍，逐帧像素和时长一致；`:191` 三组透明混合 disposal 保持逐帧 RGBA 一致，并新增 ≤3 倍体积断言。 |
| 1 | `backend/main.py:84`、`:117`：启动在线程中清扫超过 1 小时的 `.upload_*` 普通文件；`:202` 在鉴权之前对规范化上传路径的点开头组件返回 404，原私有图片判定保留；`deploy/fiona-backup.sh:66` 排除点文件。 | `test_health_and_startup.py:122`、`:165`；`test_migrate_and_backup.py:235` 覆盖点文件、隐藏目录与嵌套点文件不入包。 |
| 2 | `media.py:206` 先在事件循环等待 `asyncio.Semaphore(2)`，获得槽位再 `to_thread`；`:78`、`:348` 聊天线程信号量等待最多 10 秒，超时返回 503「服务器繁忙，请稍后再发图片」；取消最多额外等一次 shield，重复取消交由完成回调清理，去掉忙等。 | `test_upload_metadata.py:538` 默认线程池不被排队请求占满；`:570` 503 与清盘；`:586` anyio 取消仅两次 shield、无残留。 |
| 3 | `media.py:112` 无有效方向标签不复制；`:122` 相同模式不 convert，转换后及时关闭旧中间图；`:130` paste 后释放中间图；`:153` 保存完成关闭重建帧。列表只持有重建帧，所有既定上限保持不变。 | 下节给出五组样本、优化前后峰值内存与测量边界。 |
| 4 | `backend/services/chat_service.py:460` 上传任务外套 shield；调用方取消后注册完成回调，线程最终成功则删除返回的文件。改动仅在调用附近，13 行新增、1 行删除。 | `test_upload_metadata.py:615` 在线程等待期间取消，线程完成后目录为空。 |
| 5 | `backend/routers/cards.py:38`、`backend/routers/voice.py:536` 按原工具语义先检查 `DASHSCOPE_API_KEY`，再计每日额度；保留 ASR 原 ffmpeg 调用和参数。 | `backend/tests/test_daily_caps.py:256`、`:279` 共五个缺失、空或空白密钥用例，恢复密钥后首次额度仍可用，下一次才 429。 |
| 6 | `frontend/app/page.tsx:713`、`:806` 只有 429 正文含 `retry_after` 才提示后端每日文案，免提也仅此时关闭；`:808` 拼接前删除末尾中文句号。IP 每分钟限流仍按原分支处理。 | TypeScript、lint、webpack 构建通过；两处分支只读复核通过。 |
| 7 | `media.py:118` RGB/L PNG 有 tRNS 色键时先转 RGBA/LA，再重建，保留透明像素。 | `test_upload_metadata.py:509` RGB/L × 广场/聊天四个用例，断言透明及不透明像素。 |
| 8 | `backend/scripts/strip_upload_metadata.py:167` 已清理图片直接跳过；`:170`、`:173` 原子替换前恢复原权限位；`:186` apply 有失败返回 1。`:38`、`:78`、`:105` 同时检查 GIF 全部扩展、PNG/WebP chunks 与 JPEG application，防止 Pillow info 未暴露的元数据被误判为干净。 | `test_upload_metadata.py:662` 四格式字节/mtime 不变；`:682` 权限保持；`:696` GIF XMP 在循环扩展前后两种排列；`:720` PNG/WebP/JPEG 隐藏私有块；`:745` CLI 实际退出码 1，失败原件不变。 |
| 9 | `deploy/fiona-backup.sh:74` tar 返回 1 时保留已通过 integrity_check 的数据库，若媒体包存在也保留并告警可能不完整，脚本最终仍返回 1；`:93` 保留清理加 `-maxdepth 1`。 | `test_migrate_and_backup.py:235` 子目录同名旧备份保留；`:297` tar=1 有/无媒体临时包均保留完整数据库并非零退出。 |
| 10 | `main.py:283` 数据库文件 `os.access(..., os.W_OK)` 失败归 database；`:305`、`:306` 独立 GET/HEAD 路由，避免多方法路由产生重复 OpenAPI ID；`:310` 整体 `wait_for` 3 秒。 | `test_health_and_startup.py:75` 不可写数据库；`:86` HEAD 无需鉴权且不清 Cookie；`:96` 整体超时及取消；原 `test_public_surface.py` 全文件通过。 |
| 11 | `backend/migrate.py:104` 原库写入前打印目标绝对路径；`:74` 检查模型/JWT 配置；`:118` 配置提示带 `--env-file`；`:81`、`:125` 分开 OS/SQLite IO 和迁移失败提示，不打印异常正文。 | `test_migrate_and_backup.py:83` 路径先于迁移盘点输出；`:170` 两项缺密钥；`:187` OS/SQLite IO 提示；原坏库/孤立消息失败测试继续通过。 |
| 12 | `docs/DEPLOYMENT.md:557`、`:565` 新备份名与媒体恢复；`:343` 发布前备份 14 天到期需另存；`:572` 服务账号对生产目录停服清理、先 dry-run 后 apply 并核对失败数；`:515` GET 拨测；`:161`、`:200`、`:524` systemd <254 的启动限额配置；`:71` 0600、后端静态访问、GIF 合帧总时长及 3GP/AMR 可能失败。`docs/ARCHITECTURE.md:3` 日期句恢复 HEAD 原样；`:92`、`:155` 更新相关媒体与 health 说明；`CLAUDE.md:68`、`:79`、`PLAN.md:122`、`:126` 同步本轮行为。 | 文档及命令只读复核通过；没有操作真实生产数据或安装 unit。 |
| 13 | `backend/tests/test_client_ip_trust.py:60` 不可信 IPv4 映射地址严格断言原字符串；`test_upload_metadata.py:132` MPO 主帧红色/附帧蓝色并断言保留主帧；`:524` JPEG/WebP 两路径显式 `quality=90`。 | B2 全部通过。 |

本轮实际修改 19 个文件：上述 8 个后端/脚本实现文件、5 个新测试文件、`frontend/app/page.tsx`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` 和本报告。`README.md` 等第 0 轮其他改动保留，本轮未再修改；没有新建实现或测试文件，也没有改用户提供的规格/评审/返修单。

新增测试函数列表（仅在第 0 轮新建、HEAD 未跟踪的文件内追加）：

- `test_upload_metadata.py`：`test_opaque_gif_small_motion_keeps_frame_differences_and_size`、`test_png_trns_color_key_keeps_transparency`、`test_jpeg_and_webp_explicit_quality_90`、`test_plaza_queue_does_not_occupy_default_executor`、`test_chat_reencoding_slot_timeout_is_503_and_leaves_no_files`、`test_anyio_cancelled_plaza_upload_waits_once_without_busy_loop`、`test_chat_cancelled_during_worker_removes_final_upload`、`test_cleanup_skips_clean_image_without_reencoding`、`test_cleanup_preserves_original_permission_bits`、`test_cleanup_gif_xmp_application_is_not_hidden_by_loop_extension`、`test_cleanup_hidden_container_metadata_is_not_mistaken_for_clean_image`、`test_cleanup_apply_failure_cli_exit_code_is_nonzero`。
- `test_daily_caps.py`：`test_card_and_asr_missing_key_do_not_consume_daily_quota`、`test_asr_blank_key_is_checked_like_provider_before_daily_quota`。
- `test_health_and_startup.py`：`test_health_detects_unwritable_database_without_opening_it`、`test_health_head_is_public_and_retains_invalid_cookie`、`test_health_total_timeout_cancels_entire_check`、`test_startup_cleans_only_expired_upload_temporaries`、`test_hidden_uploads_are_404_before_authentication`。
- `test_migrate_and_backup.py`：`test_migration_missing_credentials_are_configuration_failures`、`test_migration_io_failures_have_disk_hint`、`test_backup_tar_exit_one_preserves_verified_database`。
- 另加强第 0 轮新测试中透明 GIF 体积、MPO 主帧、清理失败返回值、备份隐藏文件/子目录、原库路径和 IP 映射地址断言；没有修改任何 HEAD 已有测试输入或断言。

### 2. GIF 体积与峰值内存对照

同一 100 帧、64 色噪点静态背景加小块移动 GIF：输入 **40,579 B**；第 0 轮输出 **1,744,722 B（42.996 倍）**；第 1 轮输出 **40,554 B（0.999 倍）**。广场与聊天两路径的体积、逐帧 RGBA 和时长回归均通过。三组透明 GIF 输出不超过输入 3 倍。

在修改前保存第 0 轮 `media.py`，用它与最终实现分别在隔离子进程处理相同输入，测 `resource.ru_maxrss`。10 个子进程退出码全部 0；单位为 MiB：

| 样本 | 输入字节 | 第 0 轮峰值 | 第 1 轮峰值 |
|---|---:|---:|---:|
| 300 帧、816×816 动画 WebP | 210,088 | 850.03 | 842.84 |
| 300 帧、816×816 GIF | 676,833 | 1037.38 | 1040.31 |
| 8000×5000 PNG | 126,610 | 663.30 | 357.84 |
| 6000×6000 重复噪声无损 WebP | 79,258 | 1768.59 | 1493.67 |
| 同一 GIF 三个并发、重编码槽位 2 | 每份 676,833 | 2023.77 | 2026.03 |

样本按评审尺寸和内容类型合成：GIF 是逐帧改变的纯色调色板画布；动画 WebP 是静态背景上移动 8×8 小块；PNG 是白色 RGB；大 WebP 是固定随机种子生成的 128×128 RGB 噪点平铺，源编码使用 lossless 与 method=0。未拿到复核员的原始字节，因此不把这组数据称为其原文件复测；这里严格比较的是本轮相同样本的前后峰值。大 PNG 降低约 305 MiB，大 WebP 降低约 275 MiB；动画保存器仍占主要峰值，GIF 几 MiB 增加属于运行波动。帧数、像素和上传大小上限没有调整，未新增内存预算或输出体积上限。

### 3. B1–B7 最终验收

所有命令在原规格指定目录执行。只贴原样输出尾部，避免把含本机绝对路径的诊断正文写进公开文件；空输出明确注明。验证临时目录、日志、内存对照副本及编译缓存均位于工作树并已清理，前端原有构建目录与 TypeScript 缓存已恢复。没有联网、重装依赖、启动服务或浏览器，也没有运行 Git 写命令。

#### B1：全部后端测试

`backend/` 下 `python -m pytest -q -p no:cacheprovider`，另指定隔离的 basetemp。退出码 **1**。新测试文件合计 **203** 个用例，收集数量符合 **1546 − 2 + 203 = 1747**。原样尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_chat_external_references.py::test_uncommitted_reference_and_generation_files_cannot_be_read_during_normalization[.reference_]
FAILED tests/test_chat_external_references.py::test_uncommitted_reference_and_generation_files_cannot_be_read_during_normalization[.generated_]
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
3 failed, 1739 passed, 11 warnings, 5 errors in 52.73s
```

其中六个 HTTP 用例因绑定本地端口被拒而失败，异常为 `PermissionError: Operation not permitted`；另两项是旧测试 401 与返修单 404 的冲突，不能归为环境失败。没有改旧测试、添加 skip 或回退点文件保护。需要在沙箱外重跑标准命令，解决旧断言授权问题后才能达到全绿。

#### B2：六个新测试文件

`python -m pytest -q -p no:cacheprovider -rs tests/test_upload_metadata.py tests/test_tts_ws_removed.py tests/test_daily_caps.py tests/test_client_ip_trust.py tests/test_health_and_startup.py tests/test_migrate_and_backup.py`，另指定隔离 basetemp。退出码 **0**，**零 skip**。原样尾部：

```text
203 passed, 11 warnings in 6.75s
```

#### B3：Python 编译

`backend/` 下 `python -m compileall -q .`，编译缓存定向到工作树验证临时目录。**无输出，退出码 0**。

#### B4：前端

`frontend/` 下 `npx tsc --noEmit`：**无输出，退出码 0**。

`npm run lint`：退出码 **0**。原样尾部：

```text
✖ 25 problems (0 errors, 25 warnings)
```

`npm run build`：退出码 **1**。原样尾部：

```text
- Operation not permitted (os error 1)
    at <unknown> (TurbopackInternalError: [project]/app/globals.css [app-client] (css)) {
  type: 'TurbopackInternalError',
  location: undefined
}
```

日志明确指向 `binding to a port`；标准 Turbopack 构建受到权限限制，仍需沙箱外重跑。辅助 `npm run build -- --webpack` 退出码 **0**，原样尾部：

```text
ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

#### B5：旧语音实现零命中与正控

`git grep -n -e 'tts/ws' -e 'tts_ws' -e 'handle_tts_ws' -e 'TTS_WS' -- . ':!docs/tasks'`：**无输出，退出码 1**，表示无命中。

`git grep -c ws_authenticate -- backend`：退出码 **0**，原样输出：

```text
backend/auth_dep.py:1
backend/main.py:1
backend/routers/peer.py:3
```

#### B6：已有测试改动

`git diff --stat -- backend/tests`：退出码 **0**，原样输出：

```text
 backend/tests/test_tts_ws_limits.py | 46 -------------------------------------
 1 file changed, 46 deletions(-)
```

`git status --porcelain backend/tests`：退出码 **0**，原样输出：

```text
 D backend/tests/test_tts_ws_limits.py
?? backend/tests/test_client_ip_trust.py
?? backend/tests/test_daily_caps.py
?? backend/tests/test_health_and_startup.py
?? backend/tests/test_migrate_and_backup.py
?? backend/tests/test_tts_ws_removed.py
?? backend/tests/test_upload_metadata.py
```

#### B7：本机路径与补充检查

`git grep -n -E '/Users/' -- . ':!docs/tasks'`：**无输出，退出码 1**。对未跟踪实现文件也做相同补充扫描，零命中。`git diff --check`、`sh -n deploy/fiona-backup.sh`：均**无输出，退出码 0**。依赖、lockfile、CI 没有改动；所有实现与测试变动保持白名单。`02-spec.md`、`04-review.md`、`05-fix-round1.md` 是输入文件，本轮未改。

### 4. 未决问题、保留现状与自主判断

1. **旧断言冲突，需要作者确认**：`backend/tests/test_chat_external_references.py:515` 在 `.reference_` 与 `.generated_` 两个参数下要求匿名 GET/HEAD/download 返回 401；返修单第 2 节 1 明确要求点文件不论登录一律 404。实现遵循本轮要求，HEAD 旧测试保持不变；非点 `reference_`、`generated_` 原私有归属判定仍通过。后续若要全绿，需要作者明确授权更新这两个旧断言，不能自行突破「已有测试不得修改」。
2. **环境验收限制**：六个旧 HTTP 用例与默认 Turbopack 构建需在沙箱外重跑；webpack 通过不替代标准构建。B8 真实手机照片/GPS 视频、实际旧备份恢复、Linux systemd timer/失败通知、异地备份和消费告警等仍由作者独立验收，本轮未操作真实数据或外部系统。
3. **取消保证的边界**：本轮修复等待上传线程期间的普通 asyncio/anyio 取消。线程已完成后的 `save_message` 等待窗口，以及广场媒体函数返回后的帖子写库窗口仍是已有行为，超出调用点白名单。事件循环关闭会取消遗留的外层 Task，底层线程或强制终止的进程无法保证执行完成回调；最终孤儿文件仍可能存在。没有把这次局部修复宣称为全流程或强制关停均无孤儿。
4. **清扫与隐藏路径判断**：清扫仅处理第一层 `.upload_*` 普通文件，按 mtime 严格超过 3600 秒，不递归、不跟随 symlink；IO 故障只记录类型并继续启动。404 同时覆盖规范化路径中的隐藏目录组件，判断位于 OPTIONS 和鉴权之前；原私有判定代码保留，隐藏私有文件直接返回 404。
5. **排队与 GIF 判断**：广场 asyncio 信号量按事件循环保存，避免测试使用不同循环时交叉绑定；所有重编码仍共用进程级 2 槽线程信号量。聊天槽位超时取 10 秒。GIF 源带透明或实际帧含透明时整段使用 disposal=2，不透明动画不传；没有设置额外输出上限。相同连续帧可能合并，总时长不变。
6. **幂等与容器判断**：清理脚本仅对无待清理元数据的图片跳过，视频继续无损 remux，避免增加视频探测依赖。保留 ICC、透明及播放字段；GIF 允许图形控制/循环扩展，PNG/WebP 对未知 chunk、JPEG 对非 JFIF/ICC/Adobe application 保守判为需要清理。补充扫描修复了 GIF 后置循环扩展遮住 XMP 的实测问题，也覆盖 Pillow info 不暴露的私有块。原权限保持，apply 单文件失败继续但整批返回 1。
7. **备份判断**：tar=1 已验证数据库始终保留；存在媒体临时包则也发布但标为可能不完整，整批退出 1。tar>1 维持清理未完成配对。`COPYFILE_DISABLE=1` 仅作用于 tar，防止 macOS 自动生成绕过源排除规则的 AppleDouble 点文件。保留期只清理第一层，长期保留的配套备份另存。
8. **health 与迁移判断**：health 总超时归 `database`；GET/HEAD 采用独立路由以保持两个方法与不同 OpenAPI ID。迁移配置前置检查在任何写入前执行，DEV_MODE=1 沿用 JWT 开发默认；配置/缺库退出 2，IO/迁移失败退出 1。只暴露原库目标路径，不输出密钥、行内容或异常正文。
9. **内存对照范围**：复核员原样本未随任务提供，测量使用按其尺寸和类型合成的配对样本；输入字节量不同，不能直接当成原复核文件的精确复测。保留大图与动画规格上限，动画高峰值仍存在；是否降低预算、按像素加权准入或增加广场限流不属于本轮。
10. **文档恢复判断**：生产媒体清理显式指定生产目录，以服务账号读取临时空配置，避免读取 root 私有密钥文件；完成后删除此临时配置。清理脚本保持权限，恢复流程另行统一旧文件到 0600。systemd 版本差异与通知配置需在目标机验证，GET 拨测独立配置。
11. **返修单第 3 节保留项**：视频 SEI user data（含编码器版本串）仍保留，`filter_units` 兼容性以后评估；截断/缺 EOI 的 JPEG 继续拒绝；3GP/AMR 到 MP4 未验证且可能失败，已写部署手册；官方额度仍先于进行中冲突检查，额度用完且存在进行中交流时得到 429，需用户确认；未使用的 `NewsCardContent.tsx` 429 文案未改；热点路由内重复的两道本地校验保留。

没有提交、暂存、切分支或改写 Git 状态；没有改动任何 HEAD 已有测试，唯一允许的整文件删除仍是 `test_tts_ws_limits.py`。本轮实现与报告完成，标准全绿验收及上述人工确认尚未完成。

### 5. 清理后的 Git 状态

`git status --porcelain`，退出码 **0**，原样输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/exchange_store.py
 M backend/main.py
 M backend/rate_limit.py
 M backend/routers/agent_exchanges.py
 M backend/routers/cards.py
 M backend/routers/hot.py
 M backend/routers/voice.py
 M backend/run.py
 M backend/services/chat_service.py
 D backend/tests/test_tts_ws_limits.py
 D backend/tts_ws.py
 M backend/utils/media.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/AgentExchangeWorkspace.tsx
 M frontend/lib/config.ts
?? backend/migrate.py
?? backend/scripts/strip_upload_metadata.py
?? backend/tests/test_client_ip_trust.py
?? backend/tests/test_daily_caps.py
?? backend/tests/test_health_and_startup.py
?? backend/tests/test_migrate_and_backup.py
?? backend/tests/test_tts_ws_removed.py
?? backend/tests/test_upload_metadata.py
?? deploy/
?? docs/tasks/2026-10-05-prelaunch-hardening/
```

没有新增白名单以外路径；第 0 轮已有的改动与删除继续保留。所有本轮验证临时目录均已删除，前端原有验证前构建产物已恢复。

### 6. 点文件鉴权顺序补充修正（2026-10-06）

按本次澄清，`backend/main.py` 将隐藏上传文件的 404 放到鉴权成功之后，并从 DEV 回环静态文件免鉴权分支排除隐藏路径。未登录或无效 Cookie 请求保持原有 401 与 `fiona_token` 清除行为；Bearer、Cookie 或 DEV 回环身份通过后，点文件返回 404，保留 Cookie。规范化路径及编码点号仍受保护。此前第 4 节第 1 点的旧断言冲突已解决，第 4 点中「鉴权之前」的描述由本补充更新。

仅修改 `backend/main.py`、本轮未跟踪新增的 `backend/tests/test_health_and_startup.py` 和本报告。将新增文件中旧的鉴权前 404 用例校正为 `test_hidden_uploads_require_authentication_before_404`，24 个参数组合在同一回归函数中同时覆盖匿名/无效 Cookie 的 401 与鉴权后的 404，验证 Cookie 清除/保留、GET/HEAD/download、生产与 DEV 入口及编码点号。所有 HEAD 已有测试保持不动。定向运行该函数及完整 `test_chat_external_references.py`，退出码 **0**，原样尾部：

```text
72 passed, 11 warnings in 2.59s
```

在 `backend/` 使用指定后端虚拟环境，设置 `PYTHONDONTWRITEBYTECODE=1`，执行 `python -m pytest -q -p no:cacheprovider`；TMPDIR 与 basetemp 均放在 worktree 内的自动清理隔离目录。全量退出码 **1**，原样尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 1749 passed, 11 warnings, 5 errors in 50.46s
```

原先 `.reference_` 与 `.generated_` 的两条既有测试现已通过；剩余六个既有端口用例全部明确报绑定本地端口的 `PermissionError: Operation not permitted`，仍需在沙箱外复跑。此次修正无其他未决问题；`git diff --check` 通过，未运行 Git 写命令，测试临时目录均已清理。

## 第 2 轮返修（2026-10-06）

按 `05-fix-round2.md` 执行，只修改本轮白名单的三个文件。实现仅将 `backend/utils/media.py` 中 `gif_transparency` 的初值改为 `False`；保留重建后 RGBA 帧实际 alpha 最小值小于 255 时置为 `True` 的判断，其余代码不动。这样首帧只声明透明索引、整段没有透明像素的 GIF 可以保留帧间差分，实际含透明像素的 GIF 继续使用 `disposal=2`。本节更新第 1 轮第 4 节第 5 点中「源带透明元数据」也会触发该分支的描述。

`backend/tests/test_upload_metadata.py` 仅新增 `test_opaque_gif_with_unused_transparency_preserves_frame_differences`，参数化覆盖 plaza/chat 两条路径，未修改任何既有测试输入或断言。样本使用固定随机种子的 160×160、32 色噪点静态背景，加 8×8 小块运动，共 12 帧；首帧声明未使用的透明索引 255，逐帧断言实际 RGBA alpha 极值均为 `(255, 255)`。两条路径均断言输出体积不超过输入 2 倍、帧数不变、每帧 RGBA 字节与输入一致；复用的上传辅助函数也验证聊天 data URI 与落盘字节一致。

### 本轮 diff

以下 diff 相对于本轮开始时的未提交工作树，保留此前已完成的修改。本报告只在末尾追加本节。

```diff
--- a/backend/utils/media.py
+++ b/backend/utils/media.py
@@ -96,7 +96,7 @@
                     icc = image.info.get("icc_profile")
                     loop = image.info.get("loop")
                     durations = []
-                    gif_transparency = ext == "gif" and "transparency" in image.info
+                    gif_transparency = False
                     canvas_width, canvas_height = image.size
                     for index in range(frame_count):
                         image.seek(index)
--- a/backend/tests/test_upload_metadata.py
+++ b/backend/tests/test_upload_metadata.py
@@ -217,6 +217,47 @@
     assert PRIVATE_COMMENT in source and PRIVATE_COMMENT not in saved
 
 
+@pytest.mark.parametrize("route", ["plaza", "chat"])
+def test_opaque_gif_with_unused_transparency_preserves_frame_differences(uploads, route):
+    size = (160, 160)
+    rng = random.Random(69321)
+    background = Image.frombytes("P", size, bytes(rng.randrange(32) for _ in range(size[0] * size[1])))
+    palette = [channel for red in (0, 85, 170, 255)
+               for green in (0, 85, 170, 255) for blue in (0, 255)
+               for channel in (red, green, blue)]
+    palette.extend([0, 0, 128])
+    palette.extend([0] * (768 - len(palette)))
+    background.putpalette(palette)
+    frames = []
+    for index in range(12):
+        frame = background.copy()
+        left = 8 + index * 10
+        frame.paste(32, (left, 72, left + 8, 80))
+        frames.append(frame)
+    output = io.BytesIO()
+    frames[0].save(output, "GIF", save_all=True, append_images=frames[1:],
+                   duration=100, loop=2, disposal=1, transparency=255, optimize=False)
+    source = output.getvalue()
+    expected_frames = []
+    with Image.open(io.BytesIO(source)) as image:
+        # The declared index is unused: metadata alone must not disable differences.
+        assert image.info["transparency"] == 255
+        assert image.n_frames == 12
+        for index in range(image.n_frames):
+            image.seek(index)
+            rgba = image.convert("RGBA")
+            assert rgba.getextrema()[3] == (255, 255)
+            expected_frames.append(rgba.tobytes())
+
+    saved, _, _ = _upload(source, route)
+    assert len(saved) <= 2 * len(source), (len(source), len(saved))
+    with Image.open(io.BytesIO(saved)) as image:
+        assert image.n_frames == len(expected_frames)
+        for index, expected in enumerate(expected_frames):
+            image.seek(index)
+            assert image.convert("RGBA").tobytes() == expected
+
+
 def _video_stub(ext):
     if ext == "webm":
         return b"\x1a\x45\xdf\xa3private-video"
```

### 测试结果（原样尾部与退出码）

测试均在 `backend/` 下使用用户指定的后端虚拟环境解释器，设置 `PYTHONDONTWRITEBYTECODE=1`，禁用 pytest 缓存插件，并通过 `--basetemp` 指定隔离目录；`TMPDIR` 同样指向 worktree 内隔离目录。以下命令中的 `python` 指该解释器，`test_temp` 指各次运行独立创建、结束后清理的验证目录。

**1. 旧实现正控。** 新增测试完成后、尚未修改实现时运行：

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$test_temp" python -m pytest tests/test_upload_metadata.py -k opaque_gif_with_unused_transparency -p no:cacheprovider --basetemp "$test_temp/pytest"
```

两条路径输入均为 **31,144 B**，输出均为 **248,247 B**，约 **7.97 倍**，均在体积断言处失败，证明新增测试能捕获此次缺陷。退出码 **1**，原样尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_upload_metadata.py::test_opaque_gif_with_unused_transparency_preserves_frame_differences[plaza]
FAILED tests/test_upload_metadata.py::test_opaque_gif_with_unused_transparency_preserves_frame_differences[chat]
======================= 2 failed, 72 deselected in 0.19s =======================
```

**2. 修复后定向回归。** 新增 2 个用例和既有透明 GIF 混合 disposal 的 6 个用例：

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$test_temp" python -m pytest -q -p no:cacheprovider --basetemp "$test_temp/pytest" tests/test_upload_metadata.py -k 'opaque_gif_with_unused_transparency or transparent_gif_preserves_composed_frames_with_mixed_disposal'
```

退出码 **0**，原样尾部：

```text
8 passed, 66 deselected in 0.15s
```

**3. 完整媒体测试。**

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$test_temp" python -m pytest -q -p no:cacheprovider -rs --basetemp "$test_temp/pytest" tests/test_upload_metadata.py
```

退出码 **0**，零 skip；逐帧 RGBA 一致、体积回归、既有真实透明像素 GIF 与离线 ffmpeg 集成测试均通过。原样尾部：

```text
74 passed in 1.34s
```

**4. 全量后端测试首次运行与验证目录修正。**

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$test_temp" python -m pytest -q -p no:cacheprovider --basetemp "$test_temp/pytest" tests
```

首次把隔离目录建在 `backend/` 内，导致既有 `test_import_time_paths_use_session_temporary_directory` 的「临时数据库不在 backend 内」断言失败。这是本轮验证目录选择错误，不是实现回归。退出码 **1**，原样尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_beta_test_isolation.py::test_import_time_paths_use_session_temporary_directory
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
2 failed, 1750 passed, 11 warnings, 5 errors in 50.07s
```

不修改测试或实现，将 `TMPDIR` 与 basetemp 的共同父目录移到 **worktree 根目录、backend 外**，仍保持所有验证文件在当前 worktree 内，再按同一命令完整复跑。退出码 **1**，原样尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 1751 passed, 11 warnings, 5 errors in 49.91s
```

复跑只剩此前报告中已知的六个端口用例；六项 traceback 均明确为本地端口绑定时的 `PermissionError: [Errno 1] Operation not permitted`。既有临时库隔离测试恢复通过，没有新增失败，也未修改、跳过或放宽任何既有测试。

**5. 范围与清理检查。** 本轮起始文件快照比对确认：`media.py` 只有上述一行替换；测试文件只有 41 行插入，移除该新增块后与本轮起始内容完全一致；报告此前内容保持原样。`git diff --check` 无输出、退出码 **0**。运行结束后所有本轮隔离验证目录均已删除，无临时文件残留；无依赖、CI 或白名单以外文件修改。没有运行 git 写命令，没有读取项目环境密钥，没有真实网络或模型调用，没有手动启动服务或浏览器。

### 未决问题与自主验证选择

1. **本轮无新增实现未决问题，也没有偏离返修单的实现行为。** 为证明回归测试有效，先在本轮改动前的实现上执行正控；除要求的定向回归外，自主增加完整媒体测试和全量后端回归。隔离目录最初置于 backend 内的验证错误已修正并完整复跑，不保留为待修代码问题。
2. **沙箱限制仍待外部验收。** 六个既有端口用例需要在允许绑定本地端口的环境复跑；没有把全量结果宣称为全绿，也没有修改它们的输入或断言。
3. **复核员原样本与本机真实 GIF 的独立验收尚未进行。** 当前 worktree 未包含这些 GIF，本轮遵守工作树访问范围，仅使用新增的确定性合成样本；不将其称为复核员原文件的精确复测。`04-review-round2.md` 末尾约定的真实样本核验仍由主会话在可访问样本的环境执行。
