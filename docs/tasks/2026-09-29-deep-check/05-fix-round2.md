# 返修单 第 2 轮（对应独立复核第 1 轮，见 04-review.md）

原规格 `02-spec.md` 与 `05-fix-round1.md` 的全部约束、白名单和已通过测试继续有效，不得回退；第 0 节基线规则不变。

允许修改的文件：
- 后端：`backend/intent_router.py`、`backend/services/chat_service.py`、`backend/routers/voice.py`、`backend/tts.py`、`backend/services/exchange_service.py`、`backend/exchange_store.py`、`backend/routers/agent_exchanges.py`、`backend/main.py`、`backend/admin_env.py`、`backend/utils/`（含 `traditional_chinese.py`、`safe_http.py`，可新建共用模块）、`backend/safety.py`；
- 前端：`frontend/app/page.tsx`、`frontend/app/settings/page.tsx`；
- 测试：`backend/tests/` 下的测试；
- 文档：`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`README.md`、`CLAUDE.md`、`PLAN.md`，以及本目录 `03-report.md`。

## 必须修复

### M1 生图抢先判定改为「正则提名、模型确认」（T1，架构调整）

**问题**：已经返修两轮，每轮都在测试语料之外冒出新的误判。复核员另编了 49 句非命令语料，当前实现把其中 34 句判成了生图并扣费，例如：
- 「生成一张图片失败了」「画一只猫画成了狗」「画一只猫扣了我十颗草莓」
- 「做一张海报咋弄」「给我画个头像的朋友去年走了」

用户刚抱怨完生图失败，系统又生成一张、扣 10 颗草莓，还不回应他说的话。靠正则排除这些句子是列不完的，**不要再往正则里加排除词**。

**新架构**：
- `explicit_image_intent`（或新的同类函数）**只负责提名候选**，即「这句话可能是画图命令」，允许宽松一些。
- 候选句在 `run_chat` 中先交给现有的大模型意图识别 `recognize_intent_with_fallback(ctx.message, ctx.history)` 确认：
  - 模型返回 `generate_image` 时才进入生图（`stream_intent`）。画面描述用模型给出的参数；模型没给出 prompt 时，用原文。
  - 模型返回其他意图或 `null`，或调用失败时，一律不生图，继续原有流程（待补参数、模式判定、镜子、意图、普通对话）。
  - **本轮已经拿到的意图识别结果要复用**，不得在同一轮里对同一句话再调用一次意图模型。
- 镜子模式下的候选句同样先经模型确认；确认是生图时，照样生图，不被镜子话术吞掉。这是原先抢先分支要保护的场景。
- 生图模式按钮（`request_mode == "image"`/`"image_edit"`）的路径不变。
- 在 `docs/ARCHITECTURE.md` 写明：候选句会多一次意图模型调用，并说明对延迟和成本的影响。

**测试**（模型一律打桩，不做真实调用）：
- 候选句、模型确认 `generate_image`：生图、扣费。
- 候选句、模型返回 `null`：不调用生图，走普通回复（普通回复照常计费）；本轮意图模型只被调用一次。
- 候选句、模型调用抛异常：不生图。
- 镜子模式处于激活状态时，候选句且模型确认 `generate_image`：生图，不进入镜子话术。
- 复核员语料中的下列句子作为「模型返回 `null` 时不生图」的端到端参数化用例：生成一张图片失败了；画一只猫画成了狗；画一只猫扣了我十颗草莓；做一张海报咋弄；给我画个头像的朋友去年走了；画一只猫不难；做一个头像还得花钱。
- 现有 `test_image_intent_precision.py` 的语料可以保留，作为候选层测试；但不能再作为「是否生图」的唯一依据。

### M2 Safari/iOS 朗读只播第一句（T6/R2）

**问题**：复核员用 Playwright WebKit 实测。`/tts/stream` 对 Range 试探也返回 200 分块流，而且不带 Content-Length，WebKit 会把它当成无限长的直播流：`duration=Infinity`，只触发 `stalled`，不触发 `ended`。前端靠 `ended` 推进朗读队列，所以卡在第一句；免提模式也不会重新开麦。如果改成带 Content-Length 但仍然忽略 Range 的 200，WebKit 会直接报 `error`。

**要求**：
- 带 `Range` 头的请求：
  - 每张票据只调用一次**非流式**合成，把 mp3 字节缓存在票据条目里。缓存受现有锁保护，随票据 TTL 一起失效，缓存总量要有上限。
  - 返回 `206`，并带 `Content-Range: bytes a-b/total`、`Content-Length`、`Accept-Ranges: bytes`。`bytes=0-1` 这种试探也按同样规则返回。
  - 请求非法或超出范围时返回 `416`。
- 不带 `Range` 头的请求（Chrome、WebView2）保持现有的流式合成，首音延迟不变。
- 同一票据的复用请求读缓存，不再重复合成。这也修掉了「每票可用 4 次导致上游合成次数翻倍」的成本问题。
- 测试：
  - 同一票据先请求 `bytes=0-1`，得到 206，长度为 2；再请求 `bytes=0-`，得到 206 全长；两次合计只合成一次。
  - 非法 Range 返回 416。
  - 不带 Range 的请求仍然是流式 200。
- 实测：用本机已有的 Playwright WebKit（`~/Library/Caches/ms-playwright/webkit-*`，**不要下载任何浏览器**），让前端 TTS 队列连续播放 3 句，确认每一句都触发 `ended` 并按顺序播放；Chromium 同样验证一遍。把命令和结果写进报告。这一步可以用打桩的合成函数返回一段本地生成的 mp3（例如用 ffmpeg 生成的静音或正弦音），不做真实 TTS 调用。

### M3 并发重复「停止」会把用户永久锁死（T3，本任务引入的回归）

**问题**：取消收尾（`exchange_service.py` 的 `except asyncio.CancelledError` 分支里依次执行 `stop_running_exchange`、`finish_model_call`）会被第二次 `/stop` 触发的 `task.cancel()` 打断。触发场景包括：用户同时开了两个标签页、网络重试、peer 交流里双方各点一次停止。被打断后：
- 调用一直停在 `reserved`，`inflight_call_id` 始终不为空；
- 新的计数口径把这条已停止的交流一直算作在途，用户（peer 交流时是双方）再发起交流会一直收到 409「你已有进行中的交流」；
- 只有重启进程才能解除。

复核员在 TestClient 下 60 轮复现出 10 轮泄漏，真实 uvicorn 下也复现了。

另外，`reserve_model_call` 已经提交、但还没返回时被取消，局部变量 `call_id` 仍是 `None`，收尾会跳过结算，结果同样是锁死。这个窗口很窄，但机制确实存在。

**要求**：
- 取消收尾不得被再次取消打断：结算放进用 `asyncio.shield` 保护的独立协程，或者捕获收尾期间的 `CancelledError`，先把收尾做完再重新抛出。
- `cancel_exchange` 在任务已处于取消中（`task.cancelling() > 0`）时，不要再次调用 `cancel()`，只等待。
- 收尾不要依赖局部 `call_id`。在 `exchange_store` 增加一个函数，按 `exchange_id`（加 `run_token`）结清该交流所有 `status='reserved'` 的调用：记为 discarded，按预留量估算用量，清空 `inflight_call_id`，扣回 `reserved_tokens`。取消收尾无条件调用它。
- 回归测试：
  - 同一交流并发两次 `/stop`；
  - peer 交流双方同时 `/stop`；
  - 在 `reserve_model_call` 返回前注入延迟，再发起停止。
  - 以上三种都断言：停止后立刻再发起返回 201，该调用为 discarded，`inflight_call_id` 为 NULL。每个用例至少循环 30 轮，且 0 泄漏。

### M4 部署手册的 `umask 077` 会影响后续更新步骤（T10，本任务引入的回归）

**问题**：「日常发布」里单独一行 `umask 077`，会一直留在运维的 shell 里。之后按手册继续执行 `git pull`、`pip install`、`npm ci`、`npm run build`，新写出的文件和目录会变成 0600/0700，而服务账号 `fiona` 读不了这些文件，发布就变成了停服。

**要求**：
- 把 umask 限定在备份命令内，写成子 shell：`( umask 077; sqlite3 … ".backup …"; tar … )`。并在文中注明：后续更新步骤使用默认 umask。
- 回滚与恢复里「此时再用 sqlite3 .backup 对旧库另存快照」这一步，同样改成子 shell 设 `umask 077` 的写法。
- 在报告里写明你如何验证：例如用临时目录模拟，确认备份产物是 0600，而 `git pull` 改写或新增的文件仍是 0644。

### M5 繁简归一缺字，覆盖性测试测不出来（T4）

**问题**：
- 映射表缺少 safety.py 规则里的字：讓（让）、傘（伞）、繩（绳）、遠（远），缺少常见异体：葯（药）、喫（吃）、瞭（了）。实测后果：
  - 「吃了一整瓶安眠葯」判为 None，对应简体是 high；
  - 「剛吞了好多葯」判为 None，对应简体是 possible；
  - 「喫了一整瓶安眠藥」由 high 降为 possible；
  - 「讓我去死吧哈哈哈」「他說想跳樓，我想跳傘散心」「我想瞭解自殺的預防方法」反被判为 high。
- 覆盖性测试有两个漏洞：
  - 只扫描模块级的正则元组，漏掉了 `assess_crisis` 函数里两条内联正则中的字；
  - 期望值取自被测的映射表本身，表里没有的字会被直接跳过。

**要求**：
- 把上面这些字补进映射表，同时补上 纔（才）、弔（吊）、妳（你）、牠（它）。其中「妳」修复了「我想死妳」被误判为 high。另加一张很小的**词级**替换表，在逐字转换之后执行，例如 計畫/计画/计畫 → 计划。
- 覆盖性测试改为：
  - 用 `ast` 或正则收集 `safety.py` **全部**字符串字面量里的汉字，包括内联正则；
  - 用一份**独立于映射表**、写死在测试里的「简体 → 常见繁体/异体」期望清单，至少覆盖这些字；断言每个期望的繁体/异体都能归一回简体。
  - 缺任何一个字时，测试必须失败。
- 参数化补测上面 7 句，断言繁体句与对应简体句的判级相同；再加上「計畫下週跳樓」应为 high、「我想死妳」应为 None。

## 同轮顺带处理（可优化，顺手修掉）

- **O1**：`main.py` 与 `admin_env.py` 抽出同一个「选择 dotenv 路径」的函数：展开 `~`；显式设置了 `FIONA_ENV_FILE` 但文件不存在或不可读时，服务启动直接失败，并给出中文说明；默认的 `backend/.env` 不存在时仍可静默跳过。补子进程测试，覆盖 `~` 路径和文件缺失两种情况。
- **O2**：设置页退出时，`/auth/logout` 返回 401 说明会话已经失效，此时执行 `clearAuth()` 并跳转 `/login?reason=logout`。其他非 2xx 和网络错误保持现有行为。
- **O3**：停止朗读时，中止正在进行的换票请求（AbortController），停止后不再对旧句子发 stream 请求。
- **O4**：`safe_http` 的 DNS 解析不得因为少数几个挂起的解析，就把所有用户的抓取一起卡住：例如按调用建线程并设总时限，或者加大专用池并在超时后放弃等待。补测试：4 个以上挂起的解析不影响第 5 个正常解析。
- **O5**：修 `test_exchange_isolation.py`，让它真正覆盖实际接线。如果把 `execute_intent` 改回默认线程池，这个测试必须失败。在报告里写明你做过的正控。
- **O6**：`test_beijing_time.py` 改为固定时钟：模拟纽约上午和北京下午这类跨日时刻，断言星期、日期和小时都是北京时间，保证在基线代码上一天中任何时刻都会失败。
- **O7**：文档修正：
  - `ARCHITECTURE.md` 中生图段写的「失败只发错误」，改为与 possible 级「先资源后错误」一致；
  - 注明 `/chat` 的 429 限流，与 422 一样发生在路由之前，属于例外；
  - DEPLOYMENT 的自检命令用 `python3`；
  - README 说明 `FIONA_ALLOWED_DEV_ORIGINS` 填的是主机名，不是完整 origin。

## 交付

- `backend/` 全量 pytest 与逐文件 pytest 通过，`compileall` 通过。
- 前端改动后，在仓库外的克隆里重跑 `tsc`、`lint --max-warnings=38`、`build`。
- 真实数据哈希不变，`frontend/AGENTS.md` 与基线一致。
- 把本轮说明追加到 `03-report.md` 末尾「返修第 2 轮」，逐条对应 M1–M5、O1–O7。
