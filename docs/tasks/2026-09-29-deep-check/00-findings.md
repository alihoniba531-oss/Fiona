# Fiona 深度检查（2026-09-29）

- **检查对象**：当前工作区，即 `ae026c9` 加上尚未提交的 09-25 内测加固。
- **参与代理**：28 个。其中 9 个按模块读代码，3 个实际运行（门禁、生产态冒烟、真 Key 端到端）；每批发现都由独立复核员尝试推翻，P0/P1 另请第二位复核员复现；最后由批评代理找漏查的地方。
- **原始发现**：109 条，另有批评代理补报 4 条。
- **复核结果**：确认 80 条，代码层面成立但无法完全证实的 23 条，被推翻 6 条。批评代理补报的两条 P1 由我亲自复现确认。
- **P0**：没有。越权、计费错乱、数据丢失、密钥泄露都没有发现。
- **复现脚本**：存在 `~/.claude/projects/-Users-yangjing-Desktop-ai-workspace/baselines/2026-09-29-fiona-bughunt/`。

## 门禁与实跑结果（全绿部分）

- **后端 pytest**：1169 通过。以下几种跑法结果都一样：逐文件跑、倒序跑、`DEV_MODE=0`、按 CI 条件新建 venv；出网拦截下 0 次出网；asyncio 调试模式下没有超过 100ms 的慢回调，也没有未 await 的协程。
- **前端**：tsc 0 错误；eslint 0 error、28 warning；next build 成功；npm audit 0 漏洞。
- **桌面资源守卫**：通过。
- **长命库升级实测**：用 HEAD 版本建的旧库，在新代码下 `init_db` 连跑两次，结果幂等。旧用户的 `session_version` 保持不变，库切换到 WAL，退役名表生效。
- **生产态冒烟**：
  - 18 个受保护端点在未登录时返回 401。
  - 两个用户交叉调用对方资源 ID，所有接口都拒绝。
  - 退款逻辑正确：断开、上游 500、空回复、欠费四种情况都退款；并发扣费精确。
  - 删号后旧 Cookie 返回 401。
  - 生产态下 `/docs`、`test-login` 均返回 404。
- **真 Key 端到端**（真实调用，在换 DeepSeek Key 之后跑）：
  - 普通聊天、天气、危机（high 首事件和热线都有）、「我困得要死」（没有误报）、朗读、图片生成、各个抽屉、官方分身交流（DeepSeek 审稿），全部正常。
  - 390 宽手机布局下可以正常发送和阅读。

## P1：5 条（内测前应修）

| # | 问题 | 位置 | 怎么触发 | 来源 |
|---|---|---|---|---|
| 1 | 生图正则抢在所有判断之前，把评论和提问当成付费生图命令 | `backend/intent_router.py:153`，`services/chat_service.py:1016/1032` | 刚生成完图说「画得真好看」，或问「做个头像要多少钱」「画一只猫难吗？」，都会直接调用生图模型，回「图片已生成。」并扣 10 颗，用户的话没有得到回应。14 句都复现了。 | 09-21 fab579c 起就有 |
| 2 | 抓网页只限制单次读超时，没有总时限；慢速滴流网址能无限期占住线程，耗尽默认线程池后全站聊天卡死 | `backend/utils/safe_http.py:211/280` | 恶意内测用户在聊天里反复发「读一下 http://他的慢速服务器/」。每个请求占住一个线程，可长达数十天；客户端断开后草莓还会退回，攻击成本为零。实测 timeout=2s 的请求占住了线程 14.4s。 | 早已存在 |
| 3 | 官方分身交流用阻塞调用，每次最长占线程 120 秒；点「停止」不会取消正在进行的调用。一个用户反复点「开始→停止」就能占满线程池，其他所有人的私聊都得排队 | `backend/services/exchange_service.py:119`，`exchange_store.py:528` | 在 2 vCPU 主机上（默认线程池 6 个线程）复现：6 个在途调用就能让其他用户的聊天首字节等到调用结束。 | 早已存在 |
| 4 | 危机判级不做繁简转换，繁体写的明确危机句全部判为「无关」 | `backend/safety.py:78` | 「我想自殺」「吃了一整瓶安眠藥」「我想了解怎麼自殺最快」都判为 None：不出热线、不注入危机指引，还会进入联网搜索等工具。对应的简体句都判为 high。我已亲自复现。 | 旧版也漏；属于已知召回问题 K1 的新触发方式，但漏掉的是一整类输入 |
| 5 | 「可能相关（possible）」级别的危机句，在草莓用完或模型报错时拿不到任何热线 | `backend/routers/chat.py:113`，`services/chat_service.py` 的 except 分支 | 余额为 0 时，发「晚安，永别了」「刚吞了好多药」「活着没意思」，只收到「草莓不足」。「活着没意思」在旧版会免费给热线，**这是第 3 步加固造成的回归**。原因是我写的规格只给 high 级兜底，这是规格本身的漏洞。 | 09-25 加固引入 |

## P2：修一下更稳（去重后 32 条）

**隐私与安全**
- `frontend/app/page.tsx:726`：朗读时把回复原文放进 `GET /tts/stream?text=...` 的网址里，uvicorn 和 nginx 的访问日志会明文记下私聊内容，危机轮也不例外。
- `.gitignore:27`：**第 3 步开启 WAL 以后，`*.db-wal`、`*.db-shm` 不在忽略范围内。** 后端崩溃或运行中提交时，里面的明文私聊和手机号会被 `git add -A` 带进公开仓库。已实测：`backend/local-avatar.db-wal` 没被忽略。
- `frontend/app/settings/page.tsx:60`：退出请求失败（断网、后端重启时 nginx 返回 502）时，前端照样当作已经退出，但服务端会话其实还有效，访问 /login 会被弹回首页。在共用电脑上，下一个人会直接看到上一个人的私聊。
- `frontend/next.config.ts:40`：按 README 配置的开发环境（`DEV_MODE=1` 加 `next dev`，监听 `*:3000`），局域网里的人可以用 `X-Dev-User` 读任何人的历史，也能用 test-login 拿到任意用户的 Cookie。只影响开发环境。

**数据与配置**
- `backend/main.py:16`、`database.py:8`：`FIONA_DB_PATH` 如果写在 `backend/.env` 里，服务进程不会采用（database 在加载 dotenv 之前就被导入了），上传目录却采用了。结果数据库、上传目录和管理脚本各用各的库，管理脚本发出的邀请码在服务端返回 401。
- `backend/utils/media.py:68`：HEIC、AVIF 格式的照片会被识别成 mp4 视频入库，广场上出现黑色、无法播放的「视频帖」。
- `backend/routers/voice.py:49`、`docs/DEPLOYMENT.md`：部署文档没有列 ffmpeg，而浏览器录的 webm 语音必须先用 ffmpeg 转码。照文档新部署的环境，语音识别会全部失败。文档也漏了 sqlite3 命令行（备份依赖它）和「SQLite ≥ 3.35」的版本要求。
- `backend/tools/system_tools.py:16`：本机时区是 America/New_York。问「现在几点」比北京时间差 12 小时，照样扣 10 颗；北京时间上午，搜索、行程、热点提示里的「今天」会早一天。

**聊天逻辑**
- `services/chat_service.py:1069`：镜子模式下发图，图片不会送给任何模型，只按「[发了一张图片]」盲回，照样扣费。
- `services/chat_service.py:816`：搜索正则会把「我查了」「我搜了」这类叙述改写成联网搜索，并计费。
- `mode_switcher.py:288`：镜子模式的触发词用子串匹配。「让我说实话」「别问我…帮我查下机票」会被误切到镜子模式，还会清掉待补参数。
- `services/chat_service.py:1081`：待补参数（生图除外）没有退出口，10 分钟内下一句不管说什么都会被当作参数执行。
- `extractor.py:82`：私有记忆只保留最早的 12 条，而且从不删除。存满以后，新信息永远写不进去。
- `tools/visual_search.py:173`：查天气不带城市时一律返回宁波的天气（真 Key 实测）；含「天气」但不是问天气的句子也会被硬解析成某地天气；两种情况都照常扣费。
- `routers/chat.py:134`：high 级危机遇到图片校验失败、会话失效、数据库锁这类异常时，直接返回 HTTP 错误，不给求助资源（只有 ResourceNotFound 这一种兜住了）。
- `llm.py:99`：上游挂起时，要等大约 4 倍超时时间（生产约 240 秒）才报错，这期间一个 SSE 字节都没有。
- `database.py:1228`：已经互相接受、超过 30 天的真人房间，会被同一对用户的新推荐撤销。

**外部工具**
- `tools/fetch_card.py:84`：不跟随任何重定向。裸域名、http 链接、微博链接、短链一律「读不到这个网页」。
- `utils/safe_http.py:66`：网页编码只看响应头。只在 meta 里声明 GBK 的中文网站会被解成乱码，再交给模型。
- `utils/reference_images.py:87`：参考图会被完整解码，上限 4000 万像素，还要复制好几份。一张 166KB 的 PNG 就能让峰值内存增加约 700MB。（未完全证实）
- `frontend/app/page.tsx:1374`：工具失败的卡片被前端吞掉。例如热榜全部失败时，气泡里写着「搜到了，详情在下面的卡片里」，下面却什么都没有。

**前端**
- `page.tsx:1721`：关掉「朗读」停不下正在播放和排队中的语音；气泡上的「静音」按钮点了没有效果。
- `page.tsx:973`：本次打开页面后新发的消息，点「删除」只从界面上移除，数据库里还在。刷新后又出现，并且继续进入模型上下文。
- `proxy.ts:28`、`lib/useAccountIdentity.ts:21`：Cookie 有效但 localStorage 里的身份丢了（Safari 7 天会清脚本存储；上面那条退出失败也会造成这种状态），用户就卡住了：面板显示「请登录」，点了又被弹回首页；设置页要求输入「默认用户」才能删号，而后端返回 400。
- `plaza/page.tsx:342`：广场发帖不检查响应。超过 5MB 的图片被拒（413）后静默丢弃，弹窗关闭、文案丢失，没有任何提示。
- `plaza/page.tsx:413`：常见桌面宽度下，「世界」抽屉里的热点详情面板被压成 42–124px 的窄条，分类卡片还会遮住帖子。
- `match/page.tsx:51`：匹配卡 27 秒后自动过期，用户正在写招呼语也不暂停。写到一半卡片消失，并被标记为已读，这次匹配就丢了。
- `match/page.tsx:301`：真人私聊发超长消息（超过 4000 字）或发得太频繁时，前端先清空输入框；服务器随后关闭连接，没有任何提示，之后的消息全部静默发不出去。
- `settings/page.tsx:45`：「清空聊天记录」不检查响应，后端失败也提示「已清空」。
- `login/page.tsx:67`：邀请码登录被限流（429）时，提示「邀请码无效」，正确的码也被说成无效。
- `page.tsx:1442`：Safari（macOS 或 iOS 主屏 PWA）上用中文输入法按回车确认拼音时，消息会被提前发出。（未完全证实，需要真机确认）

**桌面**
- `desktop/src-tauri/tauri.conf.json:9`：`dev.ps1` / `tauri dev` 会自己等自己：CLI 先等 localhost:3000 就绪，而隧道要等 App 起来才建立。

## P3：小问题 59 条（见附录 A）

有代表性的几条：
- 0°C 时天气口播说成「现在20°」。
- 删除任何一个对话都会清空当前草稿。
- 每条 AI 气泡的打字机动画循环一直不停，持续耗 CPU。
- 主题切换不保存。
- 聊天后草莓余额最长 60 秒才刷新。
- 本地 `.venv` 里有 4 个带已知漏洞的包，但 CI 按 requirements.txt 审计，查不到它们。
- `analyze.py` 把数据库路径写死成 `fiona.db`。
- `/tts/ws` 没有限流。
- 私有图片的归属校验区分大小写，在 macOS/Windows 上改大小写就能绕过。

## 附录 A：P3 小问题全表（各维度原始条目，含少量跨维度重复）

- [账号会话·CONFIRMED] 邀请码登录被限流（429）时，前端提示「邀请码无效」 — `frontend/app/login/page.tsx:67`
- [账号会话·CONFIRMED] 邀请码字段不是字符串时，/auth/redeem-invite 返回 500 — `backend/routers/auth.py:88`
- [计费·CONFIRMED] 退款是相对 +10，与每日补给下限/管理员 set 这类绝对调整交错时余额被多加 10 — `backend/database.py:1582`
- [计费·CONFIRMED] 聊天结算后前端余额不刷新，最长滞后 60 秒 — `frontend/components/Sidebar.tsx:71`
- [对话智能·PLAUSIBLE] possible 级求助资源只在「成功的文字回复」里附带：余额为 0、上游报错、镜子模式空回复时全部丢失 — `backend/routers/chat.py:113`
- [对话智能·PLAUSIBLE] 私聊上下文没有长度预算：60 条历史、每条最多 8000 字全部送给模型 — `backend/services/chat_service.py:444`
- [对话智能·PLAUSIBLE] 意图分类器的输出没有做白名单和结构校验：params 为 null 时会话连续 10 分钟每句都报错；未知 intent 直接回复「不知道怎么执行这个」 — `backend/intent_router.py:335`
- [对话智能·CONFIRMED] 修图引用正则把聊自己修图的话误判为「修改参考图」请求，返回固定引导语并清除 pending — `backend/intent_router.py:171`
- [外部工具·CONFIRMED] topic_expand 的链接存活检测把大量真实来源误判为「链接失效」：HEAD 带空 Range 头触发 416，反爬站 HEAD 返回 403/404 时不再尝试 GET — `backend/tools/topic_expand.py:210`
- [外部工具·CONFIRMED] 本机（本地后端）的代理假 IP DNS 下，所有服务端抓取都被 SSRF 校验拒绝：fetch_card 永远失败，热点展开的所有来源都显示失效 — `backend/utils/safe_http.py:104`
- [外部工具·PLAUSIBLE] topic_expand 不校验模型 JSON 字段类型，广场页没有错误边界：字段类型漂移会把整页渲染崩成空白 — `backend/tools/topic_expand.py:165`
- [外部工具·PLAUSIBLE] 「现在几点」工具使用进程本地时区，服务器时区不是上海时会报错时间，并且照常计费 — `backend/tools/system_tools.py:16`
- [分身平台·CONFIRMED] 上游超时被报成通用错误，「生成超时」分支实际上走不到 — `backend/services/exchange_service.py:145`
- [分身平台·CONFIRMED] 会话被撤销后，已打开的真人聊天 WebSocket 仍能持续收到对方消息 — `backend/routers/peer.py:123`
- [分身平台·CONFIRMED] analyze.py 写死 backend/fiona.db，忽略 FIONA_DB_PATH — `backend/analyze.py:22`
- [分身平台·CONFIRMED] 分身交流（双方可见）结束后显示「记录仅你可见」，与同页说明相矛盾 — `frontend/components/AgentExchangeWorkspace.tsx:340`
- [分身平台·CONFIRMED] 广场点赞状态不回显：刷新后已赞过的帖子仍显示未赞，再点只在本地 +1 — `frontend/app/plaza/page.tsx:40`
- [语音媒体数据·CONFIRMED] /tts/ws WebSocket 没有任何限流或并发限制，可以绕过 /tts/* 的 20 次/分钟限流，无上限消耗 DashScope TTS 费用 — `backend/routers/voice.py:154`
- [语音媒体数据·PLAUSIBLE] 删号、删会话、清历史时逐张图全表扫描 messages，长时间持有写锁，其他用户的写入超过 5 秒 busy timeout 后报 database is locked — `backend/database.py:401`
- [语音媒体数据·PLAUSIBLE] 上传文件清理的周期任务遇到一次数据库异常就永久退出，之后待删文件再也不会重试 — `backend/main.py:52`
- [语音媒体数据·PLAUSIBLE] 聊天图片、广场媒体先落盘后写库，写库抛异常时文件成为孤儿，删号也清不掉 — `backend/services/chat_service.py:454`
- [语音媒体数据·CONFIRMED] 私有生成图/参考图的权限判断区分大小写，在大小写不敏感的文件系统（macOS/Windows）上改大小写就能绕过归属校验 — `backend/main.py:143`
- [语音媒体数据·CONFIRMED] analyze.py 写死 backend/fiona.db，忽略 FIONA_DB_PATH，统计的是错误的库 — `backend/analyze.py:22`
- [前端聊天·PLAUSIBLE] 朗读逐句请求 /tts/stream，后端按 IP 每分钟只放 20 次；长回复或免提模式从第 21 句起全部 429，前端把它当作「播完」静默跳过 — `frontend/app/page.tsx:1152`
- [前端聊天·CONFIRMED] 天气口播在 0°C 时说成「现在20°」（体感 0°C 同理），冷天提醒也随之错乱 — `frontend/app/page.tsx:1347`
- [前端聊天·CONFIRMED] 工具卡片失败时（天气查询失败、搜索失败、没搜到、旅行规划缺目的地），气泡仍写「搜到了，详情在下面的卡片里」 — `frontend/app/page.tsx:1374`
- [前端聊天·PLAUSIBLE] 「语音转文字」按钮识别后直接发送并扣 10 颗草莓，不会把文字放进输入框让用户确认 — `frontend/app/page.tsx:639`
- [前端聊天·CONFIRMED] 删除任意一个对话（包括非当前对话）会清空当前草稿、已选参考图和待发图片，并整页重载当前对话 — `frontend/app/page.tsx:1043`
- [前端聊天·CONFIRMED] 超过 8000 字的消息被后端 422 拒绝，前端只提示笼统的「请求参数校验失败」，此时输入框已被清空 — `frontend/app/page.tsx:1224`
- [前端聊天·CONFIRMED] 每条 AI 气泡的打字机 requestAnimationFrame 循环常驻不停，历史越长越费 CPU 和电量 — `components/ChatBubble.tsx:41`
- [前端聊天·CONFIRMED] 发送消息后草莓余额最长 60 秒不刷新，余额显示与实际不一致 — `components/Sidebar.tsx:72`
- [前端聊天·PLAUSIBLE] Cookie 仍有效但 localStorage 被清空时（Safari ITP 7 天清脚本存储，而 Cookie 有效期 30 天），聊天页多处静默失效 — `frontend/app/page.tsx:1475`
- [前端聊天·CONFIRMED] 非安全上下文（开发时手机通过局域网 http://IP:3000 访问）下，聊天主页挂载时同步抛 TypeError，整页崩溃 — `frontend/app/page.tsx:513`
- [前端聊天·CONFIRMED] 主题切换不保存，也不同步到常驻 iframe 抽屉：切成浅色后打开「设置」「世界」仍是深色，刷新后又变回深色 — `lib/useTheme.ts:18`
- [前端聊天·PLAUSIBLE] MediaRecorder 按 webm/opus 构造失败时，已打开的麦克风流不会释放，并误报「麦克风未授权」 — `frontend/app/page.tsx:546`
- [前端页面·CONFIRMED] 历史页请求失败时显示“还没有聊天记录” — `frontend/app/history/page.tsx:58`
- [前端页面·CONFIRMED] 历史页不显示用户自己发送的照片 — `frontend/app/history/page.tsx:318`
- [前端页面·CONFIRMED] 在设置抽屉清空聊天记录后，主对话区仍显示已被删除的消息 — `frontend/app/settings/page.tsx:46`
- [前端页面·CONFIRMED] 深浅色切换只作用于顶层文档且不持久：世界/设置抽屉仍为深色，刷新后恢复深色 — `frontend/lib/useTheme.ts:18`
- [前端页面·CONFIRMED] 主页常驻隐藏的世界 iframe：抽屉关闭时 WebGL 太阳系仍满帧渲染，且每次打开主页都消耗 /hot 限流额度 — `frontend/app/page.tsx:1969`
- [前端页面·PLAUSIBLE] 删号/退出后 localStorage 仍保留含用户名的 fiona_conversation:<用户名> 键 — `frontend/lib/auth.ts:31`
- [桌面/CI/部署·PLAUSIBLE] 启用 WAL 后 .gitignore 没覆盖 -wal/-shm，私聊数据可能被提交到公开仓库 — `.gitignore:27`
- [桌面/CI/部署·PLAUSIBLE] 后端依赖 SQLite≥3.35（RETURNING），部署手册没写版本要求，启动时也不检查 — `docs/DEPLOYMENT.md:58`
- [桌面/CI/部署·CONFIRMED] 部署前置条件漏了 ffmpeg 和 sqlite3 CLI：语音输入全坏，发布备份会静默跳过 — `docs/DEPLOYMENT.md:54`
- [桌面/CI/部署·CONFIRMED] 按手册做出的数据库和媒体备份是 0644，全机可读（含可重复登录的邀请码） — `docs/DEPLOYMENT.md:76`
- [桌面/CI/部署·CONFIRMED] 开发者模式 SSH 隧道断了不会重建，「重试」按钮救不回来 — `desktop/src-tauri/src/lib.rs:455`
- [桌面/CI/部署·PLAUSIBLE] 桌面端 window.open 新窗口请求被静默吞掉：点图片看大图、「完整历史」都没反应 — `frontend/components/ChatBubble.tsx:202`
- [桌面/CI/部署·PLAUSIBLE] setup.ps1 在 Windows PowerShell 5.1 下写出带 BOM 的 fiona.config.json，Rust 端解析失败 — `desktop/setup.ps1:98`
- [桌面/CI/部署·PLAUSIBLE] setup.ps1 的 SSH 免密自检在 PS 5.1 下遇到 ssh 的 stderr 输出就中断，指引根本打不出来 — `desktop/setup.ps1:114`
- [桌面/CI/部署·PLAUSIBLE] 已提交的「启动Chloe」脚本会强杀本机所有 python/node 进程，然后跑向不存在的旧路径 — `启动Chloe.ps1:1`
- [门禁·CONFIRMED] 本地后端 .venv 装着 4 个带已知漏洞的包，CI 的漏洞审计门禁查不到 — `.github/workflows/quality.yml:52`
- [生产态冒烟·CONFIRMED] /auth/redeem-invite 收到非字符串的 code 时返回 500 — `backend/routers/auth.py:88`
- [生产态冒烟·CONFIRMED] 超出 SQLite 整数范围的路径 ID 触发 OverflowError，返回 500 — `backend/routers/me.py:53`
- [生产态冒烟·CONFIRMED] 聊天上传的原图没有归属校验和 no-store；私有图的前缀判断区分大小写，在大小写不敏感的文件系统上可绕过 — `backend/main.py:143`
- [真Key实测·CONFIRMED] 热点分类 LLM 的 8 秒超时每次都失败，却在每个打开的聊天页上每 5 分钟重复发起付费调用 — `backend/routers/hot.py:121`
- [真Key实测·CONFIRMED] 朗读归一化会剩下孤立的 U+FE0F，回复以 ❤️/❄️ 这类 emoji 结尾时多发一次无效 TTS — `frontend/app/page.tsx:822`
- [真Key实测·CONFIRMED] 天气卡和历史记录显示英文天气状况，刷新后卡片消失、只剩英文文本 — `backend/services/chat_service.py:157`
- [真Key实测·PLAUSIBLE] 逐句 TTS 与 /tts/stream 按 IP 每分钟 20 次的限流冲突，长回复或免提连聊时后面的句子会被静默跳过 — `backend/routers/voice.py:136`
- [真Key实测·CONFIRMED] 「语音转文字」识别失败或录音失败时完全没有提示 — `frontend/app/page.tsx:637`

## 附录 B：被复核推翻的 6 条

- [计费·REFUTED] possible 级危机在余额不足、上游报错、会话不存在、生图模式下拿不到任何求助资源 — `backend/routers/chat.py:113`
  - 推翻理由：行为能复现，但完全符合规格，不算实现缺陷。docs/tasks/2026-09-25-beta-hardening/02-spec.md:72 写的是：「possible 轮行为：按普通轮完整处理（镜子、意图、工具、待补参、图片模式、计费全部照常）……若本轮是文字回复（非图片生成/修改），回复结束后追加」资源文案。AR…
- [计费·REFUTED] STRAWBERRY_DAILY_REFILL 可设为 1–9（小于单条 10 颗），补给形同虚设且提示语误导 — `backend/database.py:14`
  - 推翻理由：这是运维配置问题，不是代码缺陷。strawberry_daily_refill 按规格（2026-09-23 02-spec.md:59「非负整数，缺省 0」）接受任意非负整数。DEPLOYMENT.md:105 明确写着「补到至少该数量」，每条 10 颗在 README、CLAUDE.md 和前端 title「每条消…
- [分身平台·REFUTED] 他人发来的待处理邀请占用受邀人的「待处理上限」且永不过期，受邀人会被锁在官方体验和邀请功能之外 — `backend/exchange_store.py:466`
  - 推翻理由：现象能复现：3 个待处理的收到邀请会让受邀人发起官方体验得到 409，第 4 个人再邀请也得到 409。但这是有文档写明的设计，不是缺陷。docs/ARCHITECTURE.md:96 明确写「每账号最多 3 个待处理/运行交流、同时最多运行 1 个」；ARCHITECTURE.md:104 写官方体验「复用有限轮数、…
- [分身平台·REFUTED] 官方交流遇上游 402 时能正常失败，但每次重试都先花一次主模型整稿调用，失败调用还按满额记为估算用量 — `backend/services/exchange_service.py:142`
  - 推翻理由：引用的代码属实：select_exchange_slot 只在奇数轮（审稿）走 official 槽（exchange_models.py:44-47）；error 路径传 result=None，于是 estimated=True，按 input_limit/output_limit 记账（exchange_stor…
- [语音媒体数据·REFUTED] scripts/fix_matches.py 无任何确认就清空全体用户的待弹匹配卡，并写入指向不存在用户的演示数据 — `backend/scripts/fix_matches.py:9`
  - 推翻理由：代码引用属实：fix_matches.py 确实执行无条件的 DELETE FROM pending_matches，并插入「默认用户 → test_friend」的演示数据。但它不是产品缺陷。commit 78476bb 的说明明确写着「一次性维护脚本移入 backend/scripts/：fix_matches.p…
- [桌面/CI/部署·REFUTED] 桌面端 Rust 代码在 PR 阶段完全没有 CI：编译和测试只在合入 main 之后才跑 — `.github/workflows/build-windows-desktop.yml:3`
  - 推翻理由：事实描述准确。build-windows-desktop.yml:3-9 只由 push 到 main（带 paths 过滤）和 workflow_dispatch 触发；quality.yml 虽然跑 PR，但只有 desktop-assets、backend、frontend 三个 job，没有 cargo che…
