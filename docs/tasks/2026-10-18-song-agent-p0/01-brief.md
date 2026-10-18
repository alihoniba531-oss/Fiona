# 01-brief · Fiona 写歌智能体（P0）

日期：2026-10-18　分支：`song-agent-p0`（从 Fiona main `4b45346` 切出）　分级：L3 + 高风险（新表、计费、密钥）

## 1. 用户原始需求

> 我想创造一个写歌功能，有后台大接入相应的可以推演的大语言模型的智能体。你先帮我调研下目前市场上音乐创造的Agent

调研后用户拍板（2026-10-15）：放进 Fiona 做成聊天工具；首版自用或小范围内测；音乐引擎用云 API 双供应商（腾讯云 MPS→MiniMax 3.0 + 火山豆包音乐）；智能体用 Claude。P0 只接火山。2026-10-18 批准方案，复核方指定用 Qwen 3.8 Max。

## 2. 市场调研结论（2026-10-15，三路调研汇总）

- **海外**：最接近「音乐 Agent」的是 Google Flow Music（原 ProducerAI，Lyria 3 Pro 驱动，多轮对话改段落），中国大陆不可用。Suno v6（2026-09-09，授权数据训练）、ElevenLabs Music v2.5 是「生成 + 自然语言局部改」；Suno 无官方 API，第三方逆向接口违约且有封号风险；Udio 和解后禁下载。
- **国内**：只有 Mureka 做了对话式多轮创作（Agent Studio）；网易天音能逐句改词；海绵音乐/豆包写歌用户主要抱怨「改一处词就整首重来、结尾截断、风格少」。
- **引擎**：MiniMax 音乐 API 2026-08-20 起不接受新用户（新用户只能经腾讯云 MPS `CreateAigcAudioTask` 调，约 1 元/首）；火山豆包音乐后付费 0.002 元/秒；Mureka 编辑接口最全；开源兜底 ACE-Step 1.5（MIT）；腾讯 SongGeneration、YuE2 禁商用。
- **市场空位（本产品的差异点）**：可逐步确认的创作流程（不是一句话直出）；段落级修改（只改那一段词）；中文韵脚/字数的确定性检查；偏好记忆；授权干净可商用。
- **合规**：《人工智能生成合成内容标识办法》（2025-09-01）要求音频隐式标识（文件元数据写内容属性、服务提供者、内容编号）与显式提示（交互界面显著提示或音频提示）；对公众上线须地方网信办登记并公示所用模型备案号。自用/内测不触发登记，但标识照做。

## 3. 火山「豆包音乐模型」接口实测事实（官方文档，2026-10-18 读取）

来源：火山引擎文档库 `Audiovideounderstandingandprocessing`：生成人声歌曲（更新 2026-07-24）、查询任务（2026-01-16）、公共字段（2025-12-01）、可选参数（2026-08-25）、产品计费（2026-07-24）；签名方法 `docs/6369/67269`（2025-09-15）。

### 3.1 鉴权（不是方舟 API Key，不能复用 `ARK_API_KEY`）
- Host `open.volcengineapi.com`，路径 `/`，查询串 `Action=<...>&Version=2024-08-12`，方法 POST，`Content-Type: application/json`。
- Header：`Host`、`X-Date`（UTC，`YYYYMMDD'T'HHMMSS'Z'`）、`Authorization: HMAC-SHA256 Credential={AK}/{YYYYMMDD}/cn-beijing/imagination/request, SignedHeaders=host;x-date, Signature={sig}`；`X-Content-Sha256` 可选。
- 签名：`CanonicalRequest = Method\n/\nCanonicalQuery\nhost:{host}\nx-date:{xdate}\n\nhost;x-date\nhex(sha256(body))`；`StringToSign = "HMAC-SHA256\n" + xdate + "\n" + "{YYYYMMDD}/cn-beijing/imagination/request\n" + hex(sha256(CanonicalRequest))`；`kSigning = HMAC(HMAC(HMAC(HMAC(SK, YYYYMMDD), region), service), "request")`；`Signature = hex(HMAC(kSigning, StringToSign))`。查询串参数按名 ASCII 升序、RFC3986 编码。
- **官方固定向量（Claude 已用独立脚本复现，改一字节即不同）**：文档示例 AK `AKEXAMPLEPLACEHOLDER`（文档原示例 AK 会被 GitHub 推送保护误判为密钥，此处换成占位值；签名只依赖 SK，不影响下面的固定向量）、SK `WkRZeE1EQmxPVGhsWWpWak5HVmtNbUUxTXpZeU9UVXlOMlE1TmpZeVlqTQ==`、Host `billing.volcengineapi.com`、region `cn-beijing`、service `billing`、X-Date `20250329T180937Z`：
  - POST `Action=ListBill&Version=2022-01-01`，body `{"Limit":10,"BillPeriod":"2023-08"}` → CanonicalRequest 哈希 `27383e3b56d03850f5634483527fbddcbf06cf98de1bc8a6679ef2300bff3b15`，Signature `5e8480ceea12d0000a23c054151c50dd02c1a7dec835004057d19f13d53a7658`。
  - GET `Action=QueryBalanceAcct&Version=2022-01-01`，空 body → 哈希 `43171c1658c64b5db55c58d54988a4598d2d09a5613136beaa5eef40eae6e2c1`，Signature `1eda9e7e6b1728151a8e8791fdaf67cfbd28bd5c80d0fce2eb208746cf483105`。
  - 以上是文档公开的示例值，不是真实密钥。

### 3.2 提交：`Action=GenSongForTime`（后付费；`GenSongV4` 是预付费包，不用）
- Body（本项目用到的）：`Lyrics`（中文 5–700 字符、英文 5–2000；v4.x 与 `Prompt` 二选一，本项目只传 Lyrics）、`ModelVersion`（`v4.0`/`v4.3`/`v5.0`，默认 v4.0；本项目用 **`v4.3`**）、`Genre`（v4.3 最多 3 个，逗号分隔）、`GenreExtra`（最多 2 个）、`Mood`（v4.3 最多 2 个）、`Gender`（`Female`/`Male`）、`Timbre`（v4.3 最多 3 个）、`Duration`（Int 秒，[30, 240]）、`Key`（`A A# B C C# Cb D D# E F F# G Ab`）、`Kmode`（`Major`/`Minor`）、`Tempo`（`Grave Largo Adagio Andante Moderato Allegro Vivace Presto`，**不收 BPM 数字**）、`Instrument`（最多 5 个）、`Scene`（最多 3 个）、`Lang`（`Chinese`/`English`/`Cantonese`，默认 Chinese）、`VodFormat`（`wav`/`mp3`，默认 wav）、`SkipCopyCheck`（false=开启歌词版权检测）、`ImplicitWaterMark`（map：`ContentProducer`、`ProduceId`、`ContentPropagator`、`PropagateId`、`Enable`）、`AigcWatermark`（bool，显式水印，默认 false）、`CallbackURL`（不用）。
- 歌词结构标签（小写，独占一行）：`[intro] [verse] [pre-chorus] [chorus] [bridge] [inst] [outro] [hook] [build-up] [drop] [solo]`。
- 返回：`{"Code":0,"Message":"success","Result":{"TaskID":"2024...","PredictedWaitTime":0},"ResponseMetadata":{...,"Error":null}}`。
- v4.3 各枚举全表见 `refs/volc-v43-options.md`（从官方「可选参数」页整理，只含取值与中文说明）。

### 3.3 查询：`Action=QuerySong`，Body `{"TaskID": "..."}`
- `Result.Status`：0 等待中、1 处理中、2 成功、3 失败；`Progress` 0–100；`FailureReason`：成功时 null，失败示例 `{"Code":300061,"Msg":"InputLyricsPlagiarized"}`。
- `SongDetail`：`AudioUrl`（域名规则 `v{1-50}-default.douyinvod.com`）、`Captions`（**字符串**，示例 `"{}"`，格式未写进文档）、`Lyrics`、`Duration`（浮点秒，后付费按此计费）、`Genre`/`Mood`/`Gender`/`Timbre`/`Key`/`Kmode`/`Tempo`/`Instrument`/`Scene`/`Lang`/`GenreExtra`/`Prompt`/`TosPath`/`CallbackURL`，v5.0 才有 `StyleInfo`。
- 文档原话要点：默认 wav，「因视频云链路有默认转码逻辑，可能出现 mp4 等格式」；URL「仅供参考您转存使用、请勿直接用在应用中」，有效期 1 年。
- 计费与限额：人声歌曲 standard 0.002 元/秒（200 秒 = 0.4 元），公共资源池 QPS ≤ 2；standard 支持 30–240 秒；企业用户首次可 0 元购 200 首试用包（1 个月）。需在控制台 `console.volcengine.com/ai-music/product` 手动开通。

## 4. Fiona 现状事实（HEAD 4b45346，Claude 逐条核对）

- **Claude 智能体循环**：`backend/services/claude_agent.py`。`CLAUDE_CLIENT_TOOLS` 在 48–54 行（5 个工具）；`client_tools_for_turn(ctx, state)` 在 57–74 行，小说/工作室工具就是在这里按开关**追加**的，开关关闭时原样返回 `CLAUDE_CLIENT_TOOLS` 对象（注释写明保持请求形状）。工具分派在 548 行起：`tool = next(... name in client_names)`；563 行小说分支、590 行生图分支、657 行通用平台工具分支（只认 `CLAUDE_CLIENT_TOOLS` 里的工具）。每轮最多 4 次工具（555 行），可见文字累计 8000 字，整轮预算默认 240 秒。联网来源卡在循环结束后追加（707–714 行）：`state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"`，`yield chat._sse({"card": card, "append": True})`。`_agent_messages`（147–161 行）把北京时间文本块放在本轮 user 消息里。
- **基线测试约束**：`tests/test_claude_agent_runtime.py:117` 断言 `CLAUDE_CLIENT_TOOLS` 名字集合恰好 5 个；`tests/test_novel_chat.py:182` 测 `client_tools_for_turn`。`tests/conftest.py` 在收集阶段把库、上传目录指到临时路径，逐用例阻断真实网络与 DNS，并把工作室调度器换成空转（104–109 行）。
- **落库**：`chat_service._save_response`（972 行）调用 `database.save_message(user, "assistant", full_response, image_path=..., conversation_id=...)`；`save_message` 在 `database.py:488`，`BEGIN IMMEDIATE` 内校验会话归属。`ChatState` 在 `chat_service.py:764`（dataclass，字段 trace/full_response/sys_prompt_final/response_saved/billable/crisis…）。
- **消息表**：`database.py:129` 建表，之后用 `_safe_migrate`（71 行，吞「列已存在」）补过 `image_path`、`reference_image_paths`、`image_summary` 三列。会话消息查询在 `agent_store.py:338`（显式列名 SELECT），前端 `lib/useConversations.ts:10` 的 `StoredMessage` 与 `toMessages`（54 行）只映射正文和图片——**卡片不落库**，刷新后只剩正文里的「［卡片：…］」摘要。
- **建表惯例**：小说五表、工作室多表、本机监控三表都在 `init_db` 里 `CREATE TABLE IF NOT EXISTS`（`database.py:310–320` 一带），**不新增迁移版本号**；`/health`（`main.py:336–383`）只校验五道迁移版本 + 上传目录 +（工作室开启时）工作室目录。
- **草莓**：`reserve_strawberries`（`database.py:1667`，原子扣减，余额不足返回 None）、`refund_strawberries`（1685）。聊天每轮预扣 10 颗在 `routers/chat.py:164`；`DEV_MODE=1` 跳过预扣。
- **上传与鉴权**：`main.py` 的 `require_auth` 中间件里，`/uploads/` 下非 `generated_`/`reference_` 前缀的文件在 `DEV_MODE=1` 且回环访问时**不鉴权**直接放行（256–258 行）。所以写歌音频**不放进 uploads**，另存独立目录，经带归属校验的路由用 `FileResponse` 返回（工作室 `studio/storage.py:72` 就是这样，Starlette 1.3.1 的 FileResponse 支持 Range）。
- **删除路径**：删号 `database.delete_account_data`（791 行，单事务）；删会话 `agent_store.delete_conversation`（354 行，单事务）；清空历史 `routers/me.py` → `database.clear_message_history`。上传文件清理靠 `upload_cleanup_queue`，只清登记过的路径，没有扫描未引用文件的清扫器。
- **可借鉴的工作室写法（只借鉴，不 import `studio.*`——工作室正在另一工作树频繁改动）**：`studio/providers/base.py:85–130` 付费 POST 只发一次、超时/5xx/坏 JSON 记 uncertain、不复制异常正文；`studio/storage.py:220–270` 独立 httpx 客户端下载（`follow_redirects=False`、`trust_env=False`、大小上限、`.part` 临时文件 fsync 后原子替换）；`studio/audio.py` 用 ffmpeg 子进程、超时 kill、没有 ffmpeg 时抛 `RuntimeError("ffmpeg unavailable")`。后台任务用 `utils/background_tasks.create_background_task`，在 `main.py` lifespan（117–150 行）启动。
- **前端卡片**：`components/ChatBubble.tsx:86` `CardData`；`ChatCard`（101 行起）按 `subtype` 分支渲染，`studio_project` 卡用 `ceramic-card`、`btn btn-primary`、CSS 变量 `--carve` `--seal`；消息的 `cards` 在 346 行渲染。`app/page.tsx:2059–2072` 把 SSE 的 `data.card`（`append: true`）**逐字段拷贝**成 `CardData`，新字段必须在这里加。`ChatBubble` 由 `page.tsx:2551` 渲染，输入框状态 `const [input, setInput]`（432 行）。
- **前端约束**：`frontend/AGENTS.md` 要求改前读 `node_modules/next/dist/docs/` 对应文档；Fiona 前端**没有 vitest**，前端测试是 pytest 里用 `node -e` 检查源码（如 `tests/test_claude_agent_frontend.py`）；`ChatModelSection.tsx` 的隐私说明有基线测试逐字比对（不要改它）。
- **环境**：系统有 ffmpeg 8.1.2 / ffprobe；ffmpeg 用 `-id3v2_version 4 -metadata AIGC=<json>` 可写入 ID3v2.4 `TXXX:AIGC`，`ffprobe -show_entries format_tags` 能读回（Claude 已实测）。pypinyin 0.55.0（MIT，2025-07-20 发布，月下载约 160 万）未安装，需新增；不引入 mutagen（GPL）。
- **pypinyin 实测**（`Style.FINALS, strict=True`）：花 ua、家 ia、歌 e、多 uo、姐 ie、雪 ve、一/时/日/子 i、去 v、儿 er、苦 u、来 ai、快 uai、飞 ei、回 uei、好 ao、桥 iao、走 ou、秋 iou、天/前 ian、关 uan、元 van、人 en、心 in、春 uen、军 vn、光 uang、香 iang、风 eng、情 ing、东 ong、穷 iong、翁 ueng。`heteronym=True` 会带出生僻读音（家→ia/ie/u，波→o/ei/i），不能用来判押韵。
- **工作树环境**：`backend/.venv` 是本工作树独立的新建 venv（按 requirements.txt + pytest + pypinyin==0.55.0 安装，被 gitignore）；`frontend/node_modules` 已 `npm ci`。

## 5. 风险与未知

- `Captions` 格式未文档化，只能按「可能是 JSON 字符串、可能是空对象」容错保存原文，P0 不解析。
- 火山没有局部编辑：改一段词只能整首重新生成，旋律不保证延续（P1 再做「同参数重生成」与对比）。
- 公共资源池 QPS ≤ 2；实际生成耗时文档没写（计费页例子按 20 秒估）。
- 显式水印 `AigcWatermark=true` 的听感未知，需真实冒烟后由用户定。
- Claude 智能体模式只对启用了 Anthropic BYOK 的用户开放；P0 只给白名单用户。
