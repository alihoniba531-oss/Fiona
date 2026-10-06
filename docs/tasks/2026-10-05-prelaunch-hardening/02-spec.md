# 规格：重新上线前加固（2026-10-05）

- **基线**：`main` HEAD `9061a52`（2026-10-05 实测）：
  - `backend/tests` 全量 **1546 passed**；
  - 前端 `npx tsc --noEmit` 通过；
  - `npm run lint` 共 **25 条警告**、0 错误（CI 门禁是 `--max-warnings=38`）。
- 下文行号都指这个版本。
- **依据**：2026-10-04 全项目待修清单中「重新上线前必须完成」的几条：
  - S8：上传照片带 GPS；
  - B1：`/tts/ws` 无限流；
  - B7：付费接口无每日上限；
  - O3：X-Real-IP 可伪造；
  - O1：旧备份恢复与迁移未演练；
  - O2：没有定时备份；
  - O4：没有健康检查与告警。
- 用户拍板见第 1 节。危机识别不在本单，另有一单。

## 0. 硬规则（违反任一条即返工）

- **已有测试的输入和断言一律不得修改。** 唯一的例外是第 4 节第 1 条：整文件删除 `backend/tests/test_tts_ws_limits.py`。
- 如果某条已有测试和本规格冲突，**不要改测试**。调整实现，并在报告的「未决问题」里写清冲突。
- 不引入任何新依赖（Python 和 npm 都不行），不改 `requirements.txt`、`package.json` 和 lockfile。ffmpeg 是系统命令行工具，项目已在用（语音转码），不算新依赖。
- 不改 `.github/workflows/`。
- 不做真实网络调用，不调用真实模型，不下载。
- 不启动服务，不运行浏览器。
- 不写 git 状态（不 commit、不 stash、不切分支），不读 `.env*`。
- 派生子代理时，不要传 model 或 reasoning_effort 参数。
- 同一个文件不要让多个子代理并行改。建议按第 2 节的六块分给不同子代理；`docs/`、`README.md`、`PLAN.md`、`CLAUDE.md` 由同一个子代理最后统一改。
- **凡偏离本规格原文，或者本规格没写、由你自行决定的行为，都必须写进报告的「未决问题」**，不能只写在正文里。
- 只有影响「实现什么」的事才停下来；只影响「怎么验证」的事自己定。不回滚已完成的工作。
- 公开仓库里不得出现本机绝对路径（如 `/Users/...`）。
- **白名单**：只允许改动或新建第 2 节各条列出的文件，加上本目录的 `03-report.md`（新建）。

## 1. 用户拍板（2026-10-05）与本单默认决定

| # | 问题 | 决定 |
|---|---|---|
| D1 | 官方分身交流怎么封顶 | **每账号每天限次**：官方交流每天 3 次；热点展开、卡片详情、语音识别也按账号设每日上限；都不扣草莓；数字可配置 |
| D2 | `/tts/ws` | **直接下线**：删掉接口、处理代码和对应测试 |

下面这些是 Claude 定的默认做法，用户没有逐条拍板；报告里要单独列出来，便于用户复核。
- 广场视频去元数据用 ffmpeg 无损 remux。服务器没有 ffmpeg 或处理失败时**拒绝上传**（fail-closed），不退回原样保存。
- 图片按原格式重编码；保留 ICC 色彩配置；动图保留动画，但限制帧数。
- 每日上限只在限流器开启、并且不是开发模式时生效（与草莓预扣、换票限流的现有做法一致）。
- 健康检查新开 `/health`，原来的 `/` 不变。

## 2. 改动

### 2.1 上传照片和视频去元数据（S8）

**现状**：
- `utils/media.py` 的 `_save_plaza_upload`（广场，`:96-155`）和 `_save_uploaded_image`（聊天看图，`:158-197`）都把原始字节写盘（`:125`、`:133`、`:190`），只校验、不重编码。
- 手机照片里的 GPS、拍摄时间、机型都原样保存。任何登录用户都能下载广场和聊天图片（`main.py:174` 只把 `generated_`、`reference_` 当私有图）。
- `_save_uploaded_image` 返回的 data URI 也是原始字节（`:195-197`），会原样发给视觉模型。

**白名单**：
- `backend/utils/media.py`；
- `backend/services/chat_service.py`（只改调用 `_save_uploaded_image` 那一行，见下）；
- 新建 `backend/scripts/strip_upload_metadata.py`；
- 新建测试 `backend/tests/test_upload_metadata.py`。

**要求**：

1. **图片**（广场和聊天两条路径都要做）：
   - 先 `ImageOps.exif_transpose` 把方向转正。
   - 再像 `utils/reference_images.py:87-93` 那样**新建图像再 paste**，不得依赖原图的 `info`。注意 Pillow 12.3：`exif_transpose` 只删 Orientation，PNG 保存会隐式带出 `info` 里的 ICC，GIF 保存会带出 comment。
   - 按**原格式**重编码：png→png，jpg→jpg，webp→webp，gif→gif。
     - JPEG 显式指定 `quality=90`；
     - WebP 显式指定 `quality=90`；
     - 保存时只显式传入 `icc_profile`（如果源图有）；EXIF、XMP、IPTC、PNG 文本块、GIF comment 一律不带。
   - **MPO**（多图 JPEG，部分手机直接拍出来就是这种）：现在被 `_validate_decodable_image` 当成「损坏」拒绝。改为接受，**只输出主帧**，存成 JPEG。附属帧和它们的 EXIF 不得写出。
   - **动图**（GIF/WebP 多帧）：保留动画，逐帧重建，保留每帧时长和循环次数。上限：帧数 ≤ 300，并且「帧数 × 宽 × 高」≤ 2 亿像素。超出返回 400「动图帧数过多，请压缩后再发」。
   - 现有的像素上限（4000 万）、文件大小上限、魔数判断、错误文案保持不变。重编码后输出可以比输入大，不另设输出大小上限。
   - **重编码不得在事件循环上跑**：
     - 广场路径用 `asyncio.to_thread`；
     - 聊天路径把 `chat_service.py:460` 的同步调用改为 `await asyncio.to_thread(_save_uploaded_image, req.image_base64)`。函数名 `_save_uploaded_image` 和 `chat_service.py:49` 的按名导入**保持不变**（有测试按这个名字打桩）。
     - 用一个进程级的有界信号量（同时最多 2 个重编码），防止并发上传占满内存。
   - 聊天路径返回的 data URI 改用**去元数据后的字节**。
   - 为了让 `test_chat_image_branch` 继续通过：1×1 的 LA 模式 PNG 仍然输出为 PNG，data URI 仍以 `data:image/png;base64,` 开头。
2. **视频**（广场）：
   - 用 ffmpeg 无损 remux（`-c copy`），并清掉元数据。参数至少包括：
     - `-nostdin`；
     - `-map 0:V:0 -map 0:a:0?`（大写 V 排除封面图，不要用 `-map 0`）；
     - `-map_metadata -1 -map_chapters -1`；
     - `-dn -sn`（GoPro、大疆的数据轨或字幕轨里有逐帧 GPS）；
     - `-fflags +bitexact`；
     - mp4 输出加 `-movflags +faststart`；
     - 设置超时（≤ 30 秒）。
   - 输出容器与扩展名：mp4/3gp 输入 → `.mp4`（`-f mp4`）；mov → `.mov`（`-f mov`）；webm → `.webm`（`-f webm`）。
   - remux 失败（例如 mkv 里装的是 H.264，被当成 webm）、超时、或服务器上找不到 ffmpeg 时：**拒绝上传**，删掉所有临时文件，不得退回原样保存。
     - ffmpeg 缺失返回 503「服务器暂时无法处理视频，请改发图片」；
     - 其他失败返回 400「视频处理失败，请转成 MP4 后再发」。
   - 用 `shutil.which("ffmpeg")` 在调用时探测。**不要**照抄 `voice.py:356` 那个写死的 Windows 兜底路径。
   - **不要动** `voice.py` 里现有的 ffmpeg 调用和参数（`test_qwen_asr.py` 依赖 `-f` 的位置）。
3. **写盘方式**：
   - 临时文件放在 `media.UPLOADS_DIR` 里（不要放系统 `/tmp`，生产 systemd 开了 PrivateTmp，`os.replace` 会跨文件系统失败）。临时文件名用点开头加随机串，处理完用 `os.replace` 原子改名为最终文件名。
   - 任何失败（包括 `asyncio.CancelledError`，它不是 `Exception` 的子类）都要删掉临时文件和半成品。
   - 新代码要在调用时读 `media.UPLOADS_DIR`（测试会打桩它），不要在别的模块里 `from utils.media import UPLOADS_DIR`。
4. **存量文件**：新建 `backend/scripts/strip_upload_metadata.py`，用于恢复旧备份后清理已经落盘的旧图。
   - 默认只读：`--dry-run` 是默认行为，列出将处理的文件数和类型；只有加 `--apply` 才改写。
   - 上传目录按 `admin_env` 的现有方式定位：支持 `--env-file`，读 `FIONA_UPLOADS_DIR`。
   - 处理范围：只处理 `plaza_*` 和聊天图片（32 位十六进制文件名）。跳过 `generated_*`、`reference_*`，以及点开头的文件。
   - 复用第 1、2 点的同一套去元数据函数，原子改写。单个文件失败时跳过并计数，不中断。
   - 输出只打印计数和类型，不打印文件名以外的内容。
5. **测试**（`test_upload_metadata.py`）：
   - 用 Pillow 在内存里造带 GPS、XMP、Artist、拍摄时间、Orientation=6 的 JPEG；造带 tEXt 块和 ICC 的 PNG；造多帧 GIF 和 WebP（有 comment / EXIF）；造 MPO。
   - 广场和聊天两条路径都要断言：
     - 输出文件和返回的 data URI 字节里搜不到注入的私密字符串；
     - `getexif()` 为空；
     - `info` 里没有 exif、xmp、comment；
     - Orientation=6 的图输出后宽高已对调；
     - ICC 仍在；
     - 动图帧数和时长不变；
     - 超帧数的动图被拒；
     - MPO 只剩主帧。
   - **正控**：在报告里说明这些断言在改动前（HEAD）的实现上会失败。可以在测试里直接对原始字节断言「注入的字符串存在」来证明样本有效。
   - **视频**：
     - 打桩 `subprocess.run` / `shutil.which`，断言 argv 含上面列出的参数；ffmpeg 缺失返回 503；失败返回 400；临时文件被清理。
     - 另写一条**真 ffmpeg 集成测试**：用 ffmpeg 本身生成带 `location` 等元数据标签和旋转矩阵的短 mp4，上传后用 ffprobe 断言元数据标签消失、旋转保留、视频流仍在。机器上没有 ffmpeg 时用 `pytest.mark.skipif` 跳过，并且 skip 原因要写清楚。

### 2.2 下线 `/tts/ws`（B1，用户决定 D2）

**白名单**：
- `backend/routers/voice.py`：删 `:489-501` 的路由，删 `:17` 的 `WebSocket` 和 `:22` 的 `ws_authenticate` 这两个因此变成死代码的 import；
- 删除 `backend/tts_ws.py`；
- 删除 `backend/tests/test_tts_ws_limits.py`；
- 新建测试 `backend/tests/test_tts_ws_removed.py`。

**要求**：
- `auth_dep.ws_authenticate`、`tts.dashscope_timeout_millis` **保留**（peer WebSocket 和其余 TTS 路由还在用）。
- 其余三个 TTS 路由（`/tts/ticket`、`/tts/synthesize`、`/tts/stream`）一行不动。
- 新测试：
  - 断言 `main.app.routes` 里没有 `/tts/ws`；
  - 正控：`/ws/peer/{room_id}` 和 `/tts/stream` 仍在；
  - 再用 conftest 的 `client`（回环、`DEV_MODE=1`）`websocket_connect('/tts/ws?dev_user=...')`，断言连不上，并且原因不是鉴权失败的 4401。
- **零命中证明**：`git grep -n -e 'tts/ws' -e 'tts_ws' -e 'handle_tts_ws' -e 'TTS_WS' -- . ':!docs/tasks'` 输出为空。同时 `git grep -c ws_authenticate -- backend` 仍有命中（正控）。

### 2.3 每日上限（B7，用户决定 D1）

**现状**：
- 官方分身交流（`POST /agent-exchanges/official`）不扣草莓，没有次数上限，单次预算 1400 万 token。
- `/hot/expand`、`/cards/detail`、`/asr/recognize` 都调付费模型，只有按 IP 的每分钟限流。

**白名单**：
- `backend/rate_limit.py`；
- `backend/exchange_store.py`；
- `backend/routers/agent_exchanges.py`；
- `backend/routers/hot.py`；
- `backend/routers/cards.py`；
- `backend/routers/voice.py`（只改 `/asr/recognize`）；
- `frontend/app/page.tsx`（只改语音识别的两处失败处理，见第 5 点）；
- `frontend/components/AgentExchangeWorkspace.tsx`（只改 `:206` 的说明文案）；
- 新建测试 `backend/tests/test_daily_caps.py`。

**要求**：

1. **上限与配置**：四个环境变量，**每次调用时读取**；不是正整数时回落默认值，并且只打印一次告警（写法参考 `database.strawberry_daily_refill()`）：

   | 变量 | 默认 | 对象 |
   |---|---|---|
   | `FIONA_DAILY_OFFICIAL_EXCHANGES` | 3 | 每账号每天创建官方交流的次数 |
   | `FIONA_DAILY_HOT_EXPANDS` | 30 | 每账号每天 `/hot/expand` 的次数 |
   | `FIONA_DAILY_CARD_DETAILS` | 30 | 每账号每天 `/cards/detail` 的次数 |
   | `FIONA_DAILY_ASR` | 300 | 每账号每天 `/asr/recognize` 的次数 |

2. **「一天」**：北京时间自然日，取日期一律用 `database._today_shanghai()`。调用时按模块属性 `database._today_shanghai()` 调用，不要 `from database import _today_shanghai`（测试会打桩它）。
3. **什么时候生效**：只在「限流器开启（`limiter.enabled` 为真）并且 `DEV_MODE` 不等于 `1`」时生效。这两个条件也在调用时判断。这样现有那些在开发模式下、或关掉限流器后连续创建几十次官方交流的测试（`test_exchange_isolation.py`、`test_official_agent_exchanges.py`）可以原样通过。
4. **计数方式**：
   - **官方交流**：在 `exchange_store.create_official_exchange` 现有的 `BEGIN IMMEDIATE` 事务里、INSERT 之前（`:472` 与 `:473` 之间）计数：
     ```sql
     SELECT COUNT(*) FROM agent_exchanges
     WHERE kind = 'official' AND initiator_username = ? AND date(created_at, '+8 hours') = ?
     ```
     注意 `created_at` 是 SQLite 的 UTC 时间。所有创建过的官方交流都算，包括很快就被停止或失败的。
     - 超限时抛出一个**新的、不继承 `ExchangeConflict` 的异常**。路由在现有 `except ExchangeConflict`（`agent_exchanges.py:78`）之前捕获它，返回 429。
     - 官方 ID 不存在时的 404 检查顺序保持在最前面。
     - 不新增数据库表，不新增 `schema_migrations` 版本（`test_agent_conversations.py` 断言版本恰好 5 个）。
   - **其余三个接口**：复用 `rate_limit.check_and_hit`（它已经尊重 `limiter.enabled`）。计数键里带上北京日期和账号，例如 `("daily", "hot_expand", user, day)`；窗口用「每天 N 次」。因为键里带日期，到北京零点自然换新键。
     - 这样计数存在限流器的内存存储里，服务重启会清零。这是已知取舍，单进程部署下可以接受，写进文档。
     - 计数点必须放在**所有本地校验之后、调用模型之前**：
       - `/asr/recognize` 在 base64、空音频、大小、时长、ffmpeg 转码都通过之后才计数；
       - `/hot/expand` 在空标题和缺密钥的提前返回之后才计数。
       - 已经计数的请求，上游失败也不退还。
     - `/asr/recognize` 现在没有用户依赖，加 `user: str = Depends(get_current_user)`。
     - `/hot/expand` 的 `_user` 参数可以直接使用（改名随意）。
   - 现有的按 IP 每分钟限流全部保留。每日上限是叠加上去的。
5. **超限响应**（四个接口统一）：
   - HTTP 429；
   - 头 `Retry-After` 为距离北京次日零点的秒数（向上取整，最小 1）；
   - JSON 同时带 `detail` 和 `error` 两个字段，内容是同一句中文，另加 `retry_after`。之所以两个字段都要带：前端的热点展开只读 `error`；按住说话只读 `data.error`；交流页的 `apiJson` 先读 `detail`。
   - 文案：
     - 官方交流：「今天的官方体验次数已用完（每天 N 次），明天再来吧。」
     - 热点展开：「今天的热点展开次数已用完，明天再来吧。」
     - 卡片详情：「今天的详情查看次数已用完，明天再来吧。」
     - 语音识别：「今天的语音识别次数已用完，明天再来吧，可以先打字。」
     - 其中 N 是当前配置值。
6. **前端**（最小改动）：
   - `frontend/app/page.tsx` 输入框旁「语音转文字」与免提的识别结果处理，现在失败时完全静默（`:707-714`、`:796-803`）。改为：响应状态是 429 时，用现有的 `micNotice` 显示后端返回的 `error` 文案；免提另外调用 `setHandsFree(false)`，并在文案后加「，免提已关闭」。其他失败维持现状。
   - `AgentExchangeWorkspace.tsx:206` 的说明「记录仅你可见，内测期间不扣草莓。」改为「记录仅你可见，内测期间不扣草莓，每个账号每天可体验的次数有限。」
   - 前端不新增依赖，不改其他文件。lint 警告数不得超过 25。
7. **测试**（`test_daily_caps.py`）：
   - 打开限流器，设 `DEV_MODE=0`，用生产态鉴权（Cookie 或 Bearer，参考 `test_beta_billing.py::_prepare` 和 `test_dev_loopback.py:52-69`），前后各 `limiter.reset()`。
   - 逐个接口验证：
     - 第 N 次成功、第 N+1 次 429，响应头和响应体都符合上面的形状；
     - 换一个账号不受影响；
     - 打桩 `database._today_shanghai` 跨到第二天后恢复；
     - `DEV_MODE=1` 或限流器关闭时不限；
     - 本地校验失败的请求（空音频、空标题）不计数；
     - 环境变量改成 1 后立即生效。
   - 官方交流还要验证：并发两次创建（当天已用 2 次的情况下）恰好一个 201、一个 429；不存在的官方 ID 仍然 404。

### 2.4 按 IP 限流不再无条件相信 X-Real-IP（O3）

**现状**：`rate_limit._client_ip`（`:15-32`）只要请求带 `X-Real-IP` 就原样采信，不看对端是谁。后端被直接暴露，或者某个反代入口没覆盖这个头时，客户端可以伪造 IP，绕过所有按 IP 的限流。

**已知背景**：
- uvicorn 0.47 默认 `proxy_headers=True`、`FORWARDED_ALLOW_IPS=127.0.0.1`。按部署手册经 nginx 进来的请求，`request.client.host` 已经被 uvicorn 按 `X-Forwarded-For` 改写成真实客户端 IP。
- 测试用的 `TestClient` 不经过 uvicorn 中间件，对端固定是 `127.0.0.1`（conftest）或字符串 `"testclient"`（默认）。

**白名单**：
- `backend/rate_limit.py`；
- `backend/main.py`（只改 `:108` 的过时注释）；
- `frontend/lib/config.ts`（只删 `:5` 关于 `api.madchloechat.online` 的过时注释）；
- 新建测试 `backend/tests/test_client_ip_trust.py`。

**要求**：
- 只有当 `request.client.host` 属于受信任代理时，才采信 `X-Real-IP`（以及现有的「取 `X-Forwarded-For` 最后一段」兜底）。否则一律用 `request.client.host`。
- 受信任代理来自环境变量 `FIONA_TRUSTED_PROXIES`：逗号分隔，支持 IP 和 CIDR，默认 `127.0.0.1,::1`，**调用时读取**。IPv4 映射的 IPv6 地址（`::ffff:127.0.0.1`）要按 `auth_dep.py:31-32` 的办法展开后再比较。
- `client.host` 不是合法 IP（如 `"testclient"`）时：不受信，原样作为键，不得抛错。`client` 为 None 时沿用现在的 `"127.0.0.1"`。
- 函数名、签名不变（`limiter = Limiter(key_func=_client_ip)` 在导入时就绑定了这个函数）。
- 更新 `:16-25` 的 docstring，写清 uvicorn 会改写 `client.host`。
- **`auth_dep.is_loopback_client` 一行不改**，仍然只看 ASGI 对端，不看任何代理头。
- 测试覆盖：
  - 远端对端（如 `203.0.113.17`）带伪造的 `X-Real-IP` 时，按对端计数；
  - 对端 `127.0.0.1` 带 `X-Real-IP` 时，采信这个头；
  - CIDR 配置生效；
  - `"testclient"` 不抛错；
  - IPv4 映射地址能正确展开。
  - 可以直接构造 Starlette `Request(scope)` 做单元测试。
- 已知局限（写进文档，不用修）：如果某个入口只设 `X-Real-IP`、不追加 `X-Forwarded-For`，客户端自带的 XFF 会被 uvicorn 采信。所以手册要求每个入口两个头都设。

### 2.5 健康检查、启动失败退出码、后台清理不再静默停止（O4）

**白名单**：
- `backend/main.py`；
- `backend/run.py`；
- 新建测试 `backend/tests/test_health_and_startup.py`。

**要求**：
1. **新增 `GET /health`**：
   - 加进 `main.py` 的 `_AUTH_PUBLIC_PATHS`，否则未登录会被 401 并删 Cookie。
   - 不挂限流。原来的 `GET /` 保持不变。
   - 检查项：
     - 数据库能以**不创建文件**的方式打开：用 `file:<路径>?mode=rw` URI，不能用普通 `connect`，否则路径配错时会建出空库；
     - `schema_migrations` 里 5 道已知版本齐全，并且 `users` 表存在；
     - `media.UPLOADS_DIR` 存在且可写（`os.access`，不写文件）。
   - 打开数据库的超时 ≤ 1 秒。路径在调用时读 `database.DB_PATH`、`media.UPLOADS_DIR`。
   - 全部通过返回 200 `{"status": "ok"}`；任一失败返回 503 `{"status": "error", "failed": [...]}`，`failed` 只放检查项名称（如 `"database"`、`"schema"`、`"uploads"`）。**响应里不得出现路径、异常正文、版本号或提交号。**
   - 不探测 DashScope、DeepSeek 等外部服务。
2. **`run.py`**：现在用 `server.serve()`，启动失败（包括迁移失败）时进程以退出码 0 结束，systemd 的 `Restart=on-failure` 不会重启，也不会报 failed。改为：`serve()` 返回后，如果服务从未成功启动（`server.started` 为假），就 `sys.exit(3)`。监听地址和端口保持不变。
3. **`main.py:78-81` 的定期上传清理循环**：现在出一次异常任务就永久结束。改为每轮捕获 `Exception`，只打印异常类型（沿用 `[cleanup] ... failed type=...` 的风格，不打印正文），然后继续下一轮。`CancelledError` 照常传播（关停时要能退出）。
4. **测试**：
   - `/health` 的正常 200；
   - 数据库文件不存在时返回 503，并且**没有创建文件**；
   - 缺少某道迁移版本时返回 503；
   - 上传目录不可写时返回 503；
   - 未登录可访问，且不删 Cookie；
   - 响应体里没有路径；
   - `run.py` 的退出码逻辑（打桩 `uvicorn.Server`）；
   - 清理循环遇到一次异常后仍然继续（可以打桩 `asyncio.sleep` 和 `_run_upload_cleanup_once`）。

### 2.6 迁移演练工具、定时备份、文档（O1、O2、O4 告警、O11）

**白名单**：
- 新建 `backend/migrate.py`；
- 新建 `deploy/fiona-backup.sh`、`deploy/fiona-backup.service`、`deploy/fiona-backup.timer`（`Fiona/deploy/` 是新目录）；
- 新建测试 `backend/tests/test_migrate_and_backup.py`；
- 文档：`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`README.md`、`PLAN.md`、`CLAUDE.md`（只改与本单各条直接相关的句子）。

**要求**：

1. **`backend/migrate.py`（只跑迁移、不启动服务）**：
   - 复用 `admin_env.configure_database`，支持 `--env-file`。另支持 `--db <路径>` 直接指定数据库，优先级最高。
   - **默认不碰原库**：先把数据库（连同 `-wal`、`-shm`，如果存在）复制到临时目录，在副本上执行 `database.init_db()`。只有显式加 `--in-place` 才在原库上执行。
   - 只执行 `init_db`，**不执行** `recover_interrupted_exchanges`，也不执行上传清理。
   - 输出：迁移前、后的 `schema_migrations` 版本列表，以及各表行数和列名的摘要。只输出结构和计数，不输出任何行内容。另外检查迁移前是否存在「没有归属用户的消息」（第 ① 道迁移会因此失败），存在时给出明确提示。
   - 退出码：成功 0，失败非 0。失败时只打印异常类型和一句中文提示。
   - 数据库不存在时返回 2，不建库（与现有管理脚本一致，参考 `test_beta_admin_scripts.py`）。
2. **定时备份 `deploy/`**：
   - `fiona-backup.sh`：
     - **在线**一致性备份：`sqlite3 <库> ".backup '<目标>'"`，不停服；
     - 对备份文件跑 `PRAGMA integrity_check`，结果必须是 `ok`；
     - 再把上传目录打成 tar.gz；数据库和上传目录的备份用同一个时间戳命名；
     - 全程 `umask 077`，备份文件权限 0600；
     - 按保留天数删除旧备份，默认 14 天；
     - 所有路径和保留天数都能用环境变量覆盖（便于测试和不同服务器）；
     - **不得**在线上库旁边留下 root 属主的 `-wal`、`-shm` 文件：说明里写清楚用哪个账号运行，以及备份目录的属主和权限；
     - 只用 POSIX 和常见 GNU/BSD 兼容的命令写法，macOS 和 Linux 都能跑；
     - 任一步失败时以非 0 退出。
   - `fiona-backup.service`（oneshot）和 `fiona-backup.timer`：每天北京时间 04:00 运行，`Persistent=true`。
   - 测试：
     - 在临时目录造一个 WAL 模式的 SQLite 库（写入几行）和上传目录，用环境变量把脚本指向它们，运行脚本；
     - 断言备份库 `integrity_check` 为 ok 且行数一致、tar 里有上传文件、文件权限 0600、超过保留期的旧文件被删、原库旁没有新增的属主异常文件；
     - 机器上没有 `sqlite3` 命令时用 skipif 跳过，并写清原因。
3. **文档**（`docs/DEPLOYMENT.md` 为主）：
   - 启动迁移一节补上漏写的第 5 道 `20260905_official_exchange_workflow_v4`。
   - 新增「旧备份恢复演练」小节，步骤要写成可直接执行的命令：
     - 只读盘点备份副本的 schema；
     - 用 `backend/migrate.py` 在副本上演练；
     - 处理没有归属用户的消息；
     - 媒体恢复命令（tar 包带 `uploads/` 前缀，要和 `FIONA_UPLOADS_DIR` 对齐）；
     - 演练全程只用副本，绝不拿唯一一份备份直接起服务（启动会改写进行中的交流，并按清理队列删文件）；
     - 换新 `JWT_SECRET` 后，旧广场帖子的匿名 ID 与归属回填会失效（匿名 ID 由它派生），恢复前要知道这一点；
     - 用 `backend/scripts/strip_upload_metadata.py` 清理旧图的元数据。
   - 新增「定时备份」小节：怎么安装 `deploy/` 下的三个文件，备份目录属主与权限，如何把备份拷到服务器以外（只写做法，不写具体地址）。
   - 新增「监控与告警」小节：
     - 外部拨测 `https://<域名>/api/health`（任何外部拨测服务或另一台机器上的 cron + curl 都行；不在代码里接入第三方服务）；
     - 用 `journalctl` 看日志；
     - systemd `OnFailure=` 的用法提示；
     - **在 DashScope 和 DeepSeek 控制台设置消费告警**（列为发布前检查项，由作者手动完成）。
   - 首次验证一节的 curl 检查改用 `/api/health`（本机 `http://127.0.0.1:8000/health`）。说明 `/` 仍只是进程级检查。
   - Nginx 一节写明：每个反代入口都必须 `proxy_set_header X-Real-IP $remote_addr` 并追加 `X-Forwarded-For`；后端只在对端属于 `FIONA_TRUSTED_PROXIES` 时才采信这两个头。环境变量表加上 `FIONA_TRUSTED_PROXIES` 和四个每日上限变量。「发布前安全检查」加一条检查所有入口的这两个头。
   - ffmpeg 前置条件补一句：广场视频去元数据也依赖它（建议 ≥ 6，旧版 remux 可能丢旋转信息）。
   - 下线记录一节：域名 DNS「仍指向原服务器」改为「2026-10-04 公共 DNS 已查不到解析记录」；桌面端卸载、密钥删除两项保留为「待作者确认」。
   - `docs/ARCHITECTURE.md`、`README.md`、`PLAN.md`、`CLAUDE.md`：
     - 同步改掉「TTS WebSocket」的说法（`README.md:15`、`ARCHITECTURE.md:61`、`PLAN.md:136`）；
     - 补上每日上限（`README.md:118` 官方体验说明、`ARCHITECTURE.md:96/100/108` 一带）、上传去元数据（`ARCHITECTURE.md:90/203`、`PLAN.md:244`）、`/health`（`ARCHITECTURE.md:149`）；
     - `PLAN.md` 在 `:115` 之后新增一个「2026-10-05：上线前加固」日期节，逐条记录；
     - `CLAUDE.md` 只改与本单相关的事实句。

## 3. 不做的事

- 不做持久化的费用上限和真实 usage 记账（PLAN 已暂缓）。
- 不接入任何第三方监控或错误追踪 SaaS。
- 不改 `is_loopback_client`，不改 uvicorn 的 `proxy_headers` 设置。
- 不改危机识别（另一单）。
- 不做 `api.*` 独立域名的反代配置（代码的 CORS 和 Cookie 本来就不支持这种拓扑）。

## 4. 允许修改的已有测试

1. 整文件删除 `backend/tests/test_tts_ws_limits.py`（只测被下线的 `tts_ws.handle_tts_ws`，删掉 `tts_ws.py` 后会在收集阶段报 ImportError）。**这是唯一的例外**，其他已有测试一个字都不能改。

## 5. 报告（新建 `03-report.md`）

- 按第 2 节六块，逐条写出改动的文件、行号和做法。
- 第 1 节「Claude 定的默认做法」逐条说明实现情况。
- 第 6 节验收命令的原样输出与退出码。
- `git status --porcelain` 的原样输出（含未跟踪文件），确认只有白名单文件。
- **未决问题**：包括任何偏离本规格原文之处，以及你自己做的判断。

## 6. 验收（Claude 主会话会独立重跑）

| # | 命令 | 期望 |
|---|---|---|
| B1 | `backend/` 下 `python -m pytest -q -p no:cacheprovider` | 全部通过。数量 = 1546 − 2（删掉的 tts_ws 测试）+ 新增用例数，报告里写明 |
| B2 | `backend/` 下 `python -m pytest -q -p no:cacheprovider -rs tests/test_upload_metadata.py tests/test_tts_ws_removed.py tests/test_daily_caps.py tests/test_client_ip_trust.py tests/test_health_and_startup.py tests/test_migrate_and_backup.py` | 全部通过；`-rs` 列出的 skip 只能是「没有 ffmpeg」「没有 sqlite3」两类，本机两者都有，所以应该**零 skip** |
| B3 | `backend/` 下 `python -m compileall -q .` | 退出码 0 |
| B4 | `frontend/` 下 `npx tsc --noEmit`、`npm run lint`、`npm run build` | tsc 和 build 退出码 0；lint 0 错误、警告 ≤ 25 |
| B5 | `git grep -n -e 'tts/ws' -e 'tts_ws' -e 'handle_tts_ws' -e 'TTS_WS' -- . ':!docs/tasks'` | 无输出 |
| B6 | `git diff --stat -- backend/tests` 与 `git status --porcelain backend/tests` | 已有测试文件只有 `test_tts_ws_limits.py` 被删除；其余都是新建文件 |
| B7 | `git grep -n -E '/Users/' -- . ':!docs/tasks'` | 无新增命中 |
| B8 | 真实样本 | Claude 会用真手机照片和 ffmpeg 生成的带 GPS 视频，跑过两条上传路径后用 exiftool/ffprobe 检查。你不需要做这一步 |
