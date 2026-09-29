# 2026-09-29 深度检查修复规格（5 条 P1 + 隐私与数据相关 P2）

来源：同目录 `00-findings.md`（28 代理深度检查，已逐条复核）。本规格自包含；以本文为准，`00-findings.md` 只作背景和复现线索。

## 0. 工作区基线（必读）

- 仓库：`/Users/yangjing/Desktop/ai-workspace/Fiona`。工作区里**已有一批未提交的改动**（09-25 内测加固：35 个修改文件、若干未跟踪测试和任务文档，以及 `.gitignore` 新增的 WAL 忽略规则）。这是本任务的**基线**，基线快照为 `git stash create` 生成的提交 `656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f`（引用 `refs/fiona-baselines/2026-09-29-prefix`）。
- **不得回滚、覆盖或重写基线里的任何改动**；本任务的改动都叠加在基线之上。衡量「本任务改了什么」一律用 `git diff 656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f`（已跟踪文件）加未跟踪文件清单的差集。
- 不得运行任何写 git 状态的命令（add/commit/stash/checkout/reset/restore/clean/switch）。
- 当前基线门禁：后端 `pytest` 1169 passed；前端 `tsc` 0 错、`npm run lint -- --max-warnings=38` 通过、`npm run build` 通过。

## 1. 产品目标

Fiona 是陪伴型聊天产品（FastAPI + SQLite 后端，Next.js 16 前端，Tauri 桌面壳），即将恢复小范围内测。本任务修掉内测前的 5 条 P1，以及隐私、数据一致性相关的 P2。目标按优先级排列：

1. 用户在情绪危机中说的话，**任何情况下**都能得到求助资源（热线），无论余额、上游状态、书写方式（简体/繁体）如何。
2. 随口的评论或提问不会被当成付费命令执行。
3. 单个用户（包括恶意内测用户）无法让其他用户的聊天卡住。
4. 私聊内容不出现在 URL 和访问日志里；退出登录失败时不假装已退出；开发环境不向局域网开放冒充身份的通道。
5. 配置、上传与时间相关的明显错误得到纠正，部署文档照做能跑通。

## 2. 技术约束

- 沿用现有技术栈、代码风格与注释密度；**不引入任何新依赖**（`backend/requirements*.txt`、`frontend/package.json` 的 dependencies/devDependencies、各 lock 文件都不得变化；`package.json` 只允许改 `scripts`）。
- **不做数据库 schema 变更**（不加表、不加列）。
- 不做与任务无关的重构；不改动下文白名单以外的文件。
- 测试隔离：绝不读写真实 `backend/*.db`、`backend/uploads/`、`backend/.env`、`backend/.env.local`；测试需要 dotenv 文件时用临时文件。绝不打印任何 KEY/SECRET/TOKEN 的值。
- 不要运行 `next dev`（它会改写 `frontend/AGENTS.md`）；如 `frontend/AGENTS.md` 被任何命令改动，交付前必须恢复为基线内容。
- 需要本地端口的测试只用 127.0.0.1 上由测试自己分配的临时端口（端口 0），不得占用 3000、3001、8000、8001、8010。
- 请使用多个 subagent 并行实施，按下文「分工建议」的文件边界划分，同一文件的所有改动交给同一个 subagent 串行完成。

### 2.1 文件白名单（只允许修改或新建这些）

后端：
- `backend/intent_router.py`、`backend/services/chat_service.py`、`backend/routers/chat.py`、`backend/safety.py`
- `backend/utils/safe_http.py`、`backend/services/exchange_service.py`、`backend/exchange_store.py`、`backend/exchange_models.py`、`backend/routers/agent_exchanges.py`
- `backend/main.py`、`backend/admin_env.py`、`backend/database.py`（仅限 DB 路径解析，见 T9）、`backend/auth.py`、`backend/auth_dep.py`、`backend/routers/auth.py`、`backend/routers/me.py`（仅限 `/users`）、`backend/routers/peer.py`（仅限 WebSocket 的 `dev_user` 通道）——后四者仅限 T8 的回环限制
- `backend/routers/hot.py`、`backend/routers/cards.py`、`backend/routers/voice.py`、`backend/tts.py`、`backend/utils/media.py`
- `backend/tools/system_tools.py`、`backend/tools/web_search.py`、`backend/tools/travel_plan.py`、`backend/tools/topic_expand.py`、`backend/tools/card_detail.py`、`backend/persona.py`（仅限 T9 时区）
- 新建：`backend/utils/` 下的新模块（例如线程池、时间工具、繁简表）
- `backend/tests/` 下新建或修改测试、`backend/tests/conftest.py`
- `backend/.env.example`

前端：
- `frontend/app/page.tsx`、`frontend/app/settings/page.tsx`、`frontend/app/plaza/page.tsx`、`frontend/app/login/page.tsx`（仅当 T7 需要）
- `frontend/lib/auth.ts`、`frontend/lib/useAccountIdentity.ts`、`frontend/lib/` 下新建模块
- `frontend/next.config.ts`、`frontend/package.json`（仅 `scripts`）

文档：
- `README.md`、`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`CLAUDE.md`、`PLAN.md`（仅限与本任务行为变化直接相关的段落；`CLAUDE.md` 要求改动环境变量、端口、部署方式时同步这些文档，例如其中「可能相关的轮次……文字回复末尾附资源」一句须随 T5 更新）
- 本目录下新建 `03-report.md`

## 3. 任务清单

### T1 生图命令只认「明确命令」（P1）

**现状**：`backend/intent_router.py` 的 `explicit_image_intent` 只要消息以「画/生成/绘制/做/创作/制作」开头（可带礼貌前缀）就可能判为生图；`services/chat_service.py` 的 `run_chat` 在镜子模式、待补参数、大模型意图识别之前就执行它。于是「画得真好看」「做个头像要多少钱」会直接调用付费生图、扣 10 颗草莓，而用户的话得不到回应。

**要求**：
- `explicit_image_intent` 改成**高精度**判定：只有**正向证据**齐全的祈使命令才抢先生图。证据包括：可选的礼貌或祈使前缀，加动词，再加量词（一张/一幅/一个/一只/张/幅/个/只 等），或者「帮我/给我/请/麻烦」这类祈使前缀加明确的图片名词。拿不准的一律返回 `None`，交给后面的大模型意图识别（它仍然可以判出 `generate_image`）。**不要靠不断追加黑名单词来修**。
- 关于价格、时长、难度、方法、评价、感想的**提问或评论**，不属于命令，即使句中出现了动词和量词。像「能帮我画一只柯基吗」这种**礼貌请求**，仍然算命令。
- 新增参数化测试 `backend/tests/test_image_intent_precision.py`，至少包含下面两组语料，全部通过：
  - **必须识别为生图命令**（`intent == "generate_image"`）：画一只猫；画只橘猫在窗台上晒太阳；帮我画一只在月球上的猫；给我画个头像，要二次元风格；请画一幅水墨山水；画张海报：周末市集，暖色调；生成一张赛博朋克风格的城市夜景图片；帮我生成一张海报，主题是读书会；做一张生日贺卡的图片；帮我做个头像；能帮我画一只柯基吗；可以给我生成一张壁纸吗；画一幅竖版的星空。
  - **必须不识别**（返回 `None`）：画得真好看；画的这是啥；画画是我的爱好；画展门票多少钱；画一只猫难吗？；画面感太强了，我脑子里一直是他离开的样子；画风好喜欢；画完了；画了一下午；做个头像要多少钱；做一张海报一般要多久？；做海报好累啊；制作照片墙需要什么材料；做头像好难；你刚才画的不好；生成图片要花多少草莓；画一个圆要用什么软件；做一个网站多少钱。
- 端到端测试：「画得真好看」这一轮不调用生图函数，会走到大模型意图识别（可以打桩）；「画一只猫」仍然直接生图。
- 基线里已有的生图相关测试全部保持通过（例如 README 中的示例「帮我生成一张薄雾古庙图片」仍然直接生图）。

### T2 外部抓取必须有总时限（P1）

**现状**：`backend/utils/safe_http.py` 把 `timeout` 交给 `urllib3.Timeout(connect, read)`，这只限制单次 socket 读；`raw.read(max_bytes+1)` 会一直读到读满或 EOF。一个每隔几秒吐 1 字节的网址，就能把线程占住几天。

**要求**：
- `request_public_url` 的 `timeout` 改为**整个调用的墙钟总时限**，覆盖所有重定向、连接、响应头和响应体。超时后立即中止连接、释放线程，抛出明确的超时异常。调用方（fetch_card、topic_expand 等）把它当作普通抓取失败处理，行为与现在一样：提示读取失败，不崩溃。
- 读取响应体改为分块读取：每块检查剩余时间，并把 socket 读超时设为「剩余时间」和「原单次读超时」中较小的那个。
- 测试：在 127.0.0.1 临时端口起一个滴流服务器，声明 `Content-Length` 很大、每 0.5 秒吐 1 字节。用 `request_public_url(..., timeout=2)` 去读，必须在 **3 秒内**以超时失败返回；正常的快速响应（含重定向）不受影响。测试可以桩掉 `resolve_public_url` 的公网校验，但连接、超时、读取逻辑必须走生产代码。

### T3 慢外部调用不得饿死其他用户的聊天（P1）

**现状**：
- 官方分身交流（`services/exchange_service.py:119`）用 `asyncio.to_thread` 做非流式整稿调用，每次最长 120 秒，占用的是**默认线程池**。
- 聊天里的工具（`execute_intent`）、`routers/hot.py`、`routers/cards.py` 等慢外部调用也都在默认线程池里。
- 默认线程池大小是 `min(32, CPU+4)`，2 vCPU 主机上只有 6 个线程；而聊天主链路的槽位读写、流式逐块读取也在这个池里。
- 「停止交流」只改数据库状态，不取消在途调用；每人 1 个运行中交流的上限只统计 `status='running'`，于是反复点「开始→停止」就能叠出多个在途调用。

**要求（以可观测结果为准，实现方式由你选择并在报告中说明）**：
- 官方/分身交流的上游模型调用**不再占用默认线程池**。推荐改用 openai 包自带的异步客户端（`AsyncOpenAI`），取消时能真正断开连接；也可以用专用的有界线程池。
- 停止或撤销交流时，**取消在途的上游调用**：上游在 **2 秒内**观察到连接断开。被取消的调用按现有语义记为 discarded。
- 同一用户任何时刻最多 `MAX_RUNNING_PER_USER` 个在途交流上游调用；「开始→停止」快速循环不能突破这个上限（在假上游处计数验证）。
- 聊天工具执行（`execute_intent`）以及 `hot.py`、`cards.py` 里的慢外部调用，改到**专用的有界线程池**。池大小用环境变量配置，默认值写进 `backend/.env.example`，并在报告中给出取值理由。
- 应用启动时显式设置默认线程池大小（环境变量可配，默认不低于 32），避免小主机上默认池只有 6 个线程。
- **验收测试**（新增，全部走进程内 TestClient 或临时端口，不用真实 Key）：
  1. 把默认线程池强制设为 4 个线程，模拟小主机。
  2. 同时让 8 个官方交流上游调用各挂起 5 秒，再发起 8 个滴流 fetch_card 工具调用。
  3. 这时另一位用户发一条普通聊天（假模型秒回）：首个 SSE 事件在 **1.5 秒内**到达，**3 秒内**完成。
  4. 在基线代码上，同一测试应当失败；请在报告里写明你如何确认这一点。

### T4 危机判级支持繁体（P1）

**现状**：`backend/safety.py` 的 `assess_crisis` 只做去空白和 `lower()`，规则全是简体字面，所以繁体书写的明确危机句一律判为 `None`。例如「我想自殺」「吃了一整瓶安眠藥」「我想了解怎麼自殺最快」都会进入意图识别和工具，没有热线；对应的简体句都能判为 high。

**要求**：
- 在 `assess_crisis` 做匹配前，先把文本做**繁转简归一**。只用于分类，**不得改动**存库、送模型、显示的原文。
- 用内置映射表实现，**不引入依赖**。表至少覆盖 `safety.py` 所有规则和本节语料里出现的汉字的常见繁体与异体写法（如 殺→杀、輕→轻、樓→楼、結→结、遺→遗、書→书、藥→药、別→别、麼/么→么、這→这、會→会、經→经、剛→刚、睏→困、著→着、撐→撑、說→说、該→该、勸→劝、幫→帮、種→种、從→从、嗎→吗、媽→妈、還→还、準→准、備→备、覺→觉、慮→虑、劃→划、後→后、裡/裏→里、為/爲→为 等）。
- 新增测试「覆盖性检查」：`safety.py` 规则里出现的每个汉字，只要映射表的反查里有对应繁体，就必须能归一回该汉字。
- 新增参数化测试，下列繁体句的判级必须与标注一致：
  - **high**：我想自殺；我想了解怎麼自殺最快；吃了一整瓶安眠藥；剛吞了半瓶安眠藥；我想跳樓；我想結束這一切；我想結束自己的生命；我已經寫好遺書了；我想寫遺書然後自殺；哪種安眠藥吃了不會醒；我想從樓上跳下去；我媽媽走了我也不想活了；活著沒意思，不如死了；我在考慮結束生命；我打算結束這一切了。
  - **possible**：晚安，永別了；活著沒意思；剛吞了好多藥；我真的撐不下去了；他說他不想活了，我該怎麼勸；幫我查下割腕的急救方法。
  - **None**：我睏得要死；我要死磕這個bug；《自殺小隊》好看嗎；笑死我了；會議結束一切按計劃推進；疫情現在結束一切恢復正常；我想跳槽到大廠。
- `backend/tests/test_beta_safety.py` 中基线的全部夹具，以及日常/危机两组语料护栏，必须继续通过。

### T5 「可能相关」和明确危机，每一种结束路径都要给资源（P1 + P2）

**现状**：
- 余额不足时，只有 high 级免费拿到资源；possible 级只收到「草莓不足」。例如「晚安，永别了」「刚吞了好多药」「活着没意思」都是这样，其中「活着没意思」在旧版能拿到热线，属于回归。
- 上游报错、空回复、生图或改图这几种情况下，possible 级都拿不到资源。
- high 级在 `routers/chat.py` 预检阶段遇到 ResourceNotFound 以外的异常，或者遇到请求级校验错误时，直接返回 HTTP 错误，没有资源。

**要求（不变量）**：
- 对 `assess_crisis` 判为 **high 或 possible** 的消息，在**每一种**服务端能控制的结束路径上，用户都**恰好收到一次** `CRISIS_RESOURCE_NOTE`（客户端主动断开的除外）。需要覆盖的路径：
  - 正常文字回复；
  - 上游异常；
  - 空回复；
  - 余额不足；
  - 会话不存在（ResourceNotFound）；
  - 预检阶段的其他异常和 HTTPException；
  - `routers/chat.py` 里能在判级之后执行的请求级校验失败（请把 `assess_crisis` 移到这些校验之前）；
  - 生图或改图的成功与失败；
  - 工具结果、待补参数追问、镜子模式。
- high 级的现有行为不变：首事件 `{"crisis": true}`，照常计费但不拦截。**possible 级不发** `{"crisis": true}`。
- 余额不足时：
  - high 级保持现状；
  - possible 级返回 SSE：先发 `{"text": CRISIS_RESOURCE_NOTE}`，再发原有的余额不足 `{"error": ...}`。不调用模型，不扣费。
  - 前端现有逻辑会把「已收到的文字 + 错误：…」合并显示，所以不需要改前端。
- 错误路径同理：先发资源文本，再发 `{"error": ...}`。退款语义保持不变。
- FastAPI 在进入路由之前就返回的 422（比如消息超过 8000 字）不在本任务范围内；请在报告中注明。
- 新增参数化测试，覆盖上面每一条路径，分别对 high 和 possible 断言资源文本恰好出现一次、`{"crisis": true}` 只在 high 出现、计费或退款正确。「活着没意思」和「晚安，永别了」在零余额下必须收到资源。
- 同步更新 `docs/ARCHITECTURE.md` 中关于 possible 级行为的描述。

### T6 朗读不把私聊原文放进 URL（P2，隐私）

**现状**：`frontend/app/page.tsx` 的 `mkTtsAudio` 用 `GET /tts/stream?text=...` 播放，回复原文（包括危机轮）会被 uvicorn 和 nginx 的访问日志明文记下来。

**要求**：
- **任何 URL 或查询串里都不得出现私聊文本**，包括 `/tts/stream`、`/tts/synthesize`，以及前端发起的其他请求。
- 推荐做法：
  1. 前端先 `POST` 文本（请求体）到新接口，换取一张**一次性、短时有效（≤60 秒）、绑定当前用户**的票据；
  2. 再用 `GET /tts/stream?ticket=<不透明随机串>` 播放。
- 票据存在进程内存里即可。后端按单进程部署，请核实 `docs/DEPLOYMENT.md` 并在报告中说明；票据丢失或过期时，前端跳过这一句，不中断队列。
- 首音延迟不能明显变差：`<audio>` 仍然流式播放，预取下一句的逻辑保留。
- 同样数量的句子，限流不能比现在更严。换票和播放合起来算一次配额，或者分别设置不低于现有值的额度。
- 仍然只有已登录用户能用；开发构建里的 `dev_user` 兜底如果还需要，也不得携带文本。
- 测试：后端新接口的鉴权、一次性、过期、跨用户不可用；并断言 `/tts/stream` 不再接受 `text` 查询参数，或者对它一律拒绝。

### T7 退出登录与身份不同步（P2，隐私）

**现状**：
- `frontend/app/settings/page.tsx` 的 `logout()` 不管 `/auth/logout` 成功还是失败，都清掉本地身份、跳去登录页。失败时服务端会话其实仍然有效，`proxy.ts` 看到 Cookie 还在，又把用户弹回首页，于是上一位用户的私聊会继续显示在共用设备上。
- 前端的身份只从 `localStorage.fiona_user` 读。Cookie 有效但 localStorage 被清空时（Safari 会清脚本存储，上面的退出失败也会造成这个状态），用户就卡住了：各个面板显示「请登录」，点了又被弹回首页；设置页显示「默认用户」，删号要求输入「默认用户」，后端则返回 400。

**要求**：
- 退出：只有 `/auth/logout` 返回 2xx 时，才清本地身份并跳转。失败时（网络错误或非 2xx）留在原页，给出明确错误提示和重试入口，不清本地状态。
- 身份回填：已登录（Cookie 有效）但本地没有用户名时，前端向后端现有的 `GET /profile`（返回 `{"username": ...}`）取回用户名并写回本地，所有用 `useAccountIdentity` / `getUsername` 的地方随之恢复。返回 401 则按现有逻辑去登录页。回填只做一次，失败不死循环。
- 生产构建里，账号类操作（删号确认、清空记录确认文案、发图归属判断等）**不得**把「默认用户」当成身份。删号确认必须拿真实用户名比对；还拿不到真实用户名时，禁用删号按钮并提示正在加载。
- 在 `03-report.md` 中说明手工验证步骤；前端没有测试框架，**不要新增测试依赖**。

### T8 开发环境不向局域网开放冒充通道（P2，安全）

**现状**：
- `frontend/package.json` 的 `dev` 是 `next dev`，默认监听所有网卡。
- `next.config.ts` 设置了 `allowedDevOrigins: ["*"]`。
- 后端 `DEV_MODE=1` 时接受 `X-Dev-User` 头、`dev_user` 参数和 `/auth/test-login`。
- 结果是：按 README 启动开发环境后，同一局域网里的任何人都能读到任意用户的历史。

**要求**：
- 前端：`dev` 默认只绑定 `127.0.0.1`。如果确实需要局域网真机调试，另设显式脚本（例如 `dev:lan`），并在 README 写明风险。`allowedDevOrigins` 不再是 `"*"`：默认只允许本机，需要额外来源时由环境变量显式配置。
- 后端纵深防御：`DEV_MODE=1` 时，开发专用的鉴权通道（`auth_dep.py` 与 `main.py` 中间件里的 `X-Dev-User`/`dev_user`、`routers/peer.py` 的 WebSocket `dev_user`、`/auth/test-login`、`/auth/send-otp`、`/auth/verify-otp`、`routers/me.py` 的 `/users`，以及其他 DEV 专用入口，请用 `rg -n 'DEV_MODE|dev_user|X-Dev-User'` 找全）只接受 socket 对端地址为回环的请求。判断依据是 ASGI 的 `request.client.host`，**不得**信任 `X-Forwarded-For` 或 `X-Real-IP`。非回环请求按未登录处理（401/404）。
- 测试：模拟非回环对端（TestClient 可以设 client 地址），断言这些 DEV 通道被拒绝；回环对端仍然可用。生产态（`DEV_MODE=0`）行为不变。

### T9 配置、上传与时间（P2）

1. **FIONA_DB_PATH 写在 `backend/.env` 里不生效**
   - 现状：`main.py` 先 import `database`，这时 `DB_PATH` 已经从环境变量读定；`.env` 要到 `auth.py`、`llm.py` 被导入时才加载。结果服务进程用的库，和上传目录、管理脚本用的不是同一个。
   - 要求：在导入任何读取环境变量的模块之前加载 dotenv（`override=False`，显式环境变量优先）。为了测试，允许用环境变量 `FIONA_ENV_FILE` 指定另一份 dotenv 文件，默认仍是 `backend/.env`。
   - 测试：在子进程里用一份临时 dotenv 设置 `FIONA_DB_PATH` 和 `FIONA_UPLOADS_DIR`，断言 `database.DB_PATH` 和上传目录都采用了该文件里的值。**不得读写真实 `backend/.env`**。
   - `admin_env.py` 与服务进程要用同一套解析规则。
2. **HEIC/AVIF 被当成 mp4**
   - 现状：`backend/utils/media.py` 的 `_sniff_video_ext` 把所有 `ftyp` 盒子都当成 mp4，HEIC/AVIF 照片因此以视频入库。
   - 要求：
     - 按 brand 区分：`heic/heix/hevc/hevx/mif1/msf1/avif/avis` 等图像 brand 不能被当成视频，以 400 拒绝，并给出清楚的中文提示（例如「暂不支持 HEIC/AVIF，请转成 JPG 或 PNG 后再发」）。
     - 只有已知的视频 brand 才算视频，比如 `isom/iso2/iso4/iso5/iso6/mp41/mp42/avc1/dash/M4V /qt  ` 和 3gp 系列。
     - 未知 brand 一律拒绝。
     - 补测试。
3. **广场发帖失败被静默吞掉**：`frontend/app/plaza/page.tsx` 的 `handleSubmit` 要检查响应。非 2xx（413 文件太大、400 格式不支持等）时，把后端的 `detail` 显示在发布弹窗里，保留文案和已选标签，不关闭弹窗。
4. **时区**
   - 现状：面向用户的「现在几点、今天几号」用的是进程本地时区，本机是纽约时区。
   - 要求：新增一个统一的北京时间工具函数（`Asia/Shanghai`），并替换 `tools/system_tools.py`、`tools/web_search.py`、`tools/travel_plan.py`、`tools/topic_expand.py`、`tools/card_detail.py`，以及 `persona.py` 里面向用户的「当前时间/日期」。
   - 模式切换、过期判断等**内部计时**不要改。
   - 测试：把进程时区设成 `America/New_York`（例如 `TZ` 加 `time.tzset`），断言工具输出的是北京时间。

### T10 文档（P2）

- `docs/DEPLOYMENT.md` 的前置条件补全：
  - ffmpeg：浏览器录的 webm/opus 语音必须经它转码，给出安装命令和自检命令；
  - `sqlite3` 命令行：备份依赖它；
  - SQLite ≥ 3.35：后端用到 `RETURNING`，给出 `python -c "import sqlite3; print(sqlite3.sqlite_version)"` 这条自检命令。
- 备份步骤要让产物权限为 600 或 640（例如先设 umask 077），避免邀请码与私聊备份全机可读。
- `README.md`：开发环境默认只监听本机；局域网调试怎么显式开启，以及它的风险。
- `backend/.env.example`：补上本任务新增的环境变量及默认值说明。
- 其他文档只改与本任务行为变化直接相关的句子。

## 4. 什么时候停下来问

- 只有当两条要求确实无法同时满足，且会影响「实现什么」时，才停下：在报告中列出冲突和你的建议，其余任务照常完成。
- 只影响「怎么实现、怎么验证」的问题，自行决定并在报告中说明理由。
- 任何情况下都不回滚已完成的工作，也不回滚基线。

## 5. 分工建议（按文件互不重叠）

- A：`safety.py` 及其繁简表模块、`tests/test_beta_safety.py` 和新增的繁体测试（T4）
- B：`intent_router.py`、`tests/test_image_intent_precision.py`（T1）
- C：`utils/safe_http.py`、新增的线程池模块、`services/exchange_service.py`、`exchange_store.py`、`exchange_models.py`、`routers/agent_exchanges.py`、`routers/hot.py`、`routers/cards.py`、`main.py`（线程池与 dotenv 提前加载）、`admin_env.py`、`database.py`（T2、T3、T9.1）
- D：`routers/chat.py`、`services/chat_service.py`（T5，以及 T1/T3 在 `run_chat` 里需要的接线）
- E：`routers/voice.py`、`tts.py`、`frontend/app/page.tsx`（T6）；`frontend/app/settings/page.tsx`、`lib/auth.ts`、`lib/useAccountIdentity.ts`、`login/page.tsx`（T7）；`next.config.ts`、`package.json` scripts，以及 `auth.py`、`auth_dep.py`、`routers/auth.py`、`routers/me.py`、`routers/peer.py` 的回环限制（T8；E 在 `auth_dep.py` 提供回环判断函数，`main.py` 中间件里的 DEV 通道由 C 接入该函数）
- F：`utils/media.py`、`plaza/page.tsx`（T9.2、T9.3）；时间工具与 tools/persona（T9.4）；全部文档（T10）

## 6. 验收标准（逐条可执行）

在仓库根目录 `/Users/yangjing/Desktop/ai-workspace/Fiona` 下执行：

1. `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider`：全部通过，数量 > 1169；0 failed、0 error。
2. 逐文件执行 `for f in tests/test_*.py; do .venv/bin/python -m pytest -q -p no:cacheprovider "$f" || echo FAIL $f; done`：没有 FAIL。
3. `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .`：退出码 0。
4. `cd frontend && npx tsc --noEmit` 退出码 0；`npm run lint -- --max-warnings=38` 退出码 0；`npm run build` 成功。
5. 测试前后执行 `ls backend/uploads | sort | shasum` 和 `shasum backend/*.db`，结果一致。
6. `git diff --stat 656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f` 列出的文件，以及新增的未跟踪文件，全部在 §2.1 白名单内；`git diff 656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f -- backend/requirements*.txt frontend/package-lock.json desktop` 为空；`frontend/package.json` 的差异只在 `scripts`。
7. 在 `frontend/` 和 `backend/` 源码里 `rg -n "tts/stream\?\$\{|text=\$\{|params\.set\(\"text\"|text: text" ` 找不到把回复文本放进 URL 的写法。请在报告中给出你实际用来证明这一点的命令与输出。
8. T1–T9 列出的新增测试名称和语料都存在并通过。报告里逐条给出测试函数名。
9. `frontend/AGENTS.md` 与基线一致。

## 7. 交付

完成后写 `docs/tasks/2026-09-29-deep-check/03-report.md`，包含以下内容：

1. 修改和新建的文件清单；
2. T1–T10 与实现的逐项对应，重点写清设计选择和取值理由；
3. 验收命令的真实输出摘要，包括测试数量；
4. 未完成、有意保留或需要人工确认的地方（例如 FastAPI 422、线程池默认值、单进程假设）。

最后输出同样内容的变更总结。
