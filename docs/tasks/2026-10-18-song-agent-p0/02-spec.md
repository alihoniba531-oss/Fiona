# 02-spec · Fiona 写歌智能体 P0

> 执行方：你在 `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-song-p0`（git 工作树，分支 `song-agent-p0`，基线提交 `4b45346`）里工作。你看不到任何对话，本规格与同目录 `01-brief.md`、`refs/volc-v43-options.md` 就是全部需求。**先通读这三个文件再动手。**

## 0. 工作方式（必读）

1. **用工作流并行**：用 workflow 工具，在脚本里用 `parallel()` 同时运行多个 agent，按 §14 的拆分表**按文件不重叠**拆分，拆得越细越好；同一文件及其测试只归一个 agent。每个 agent 的任务说明必须自包含（它看不到你的对话，把本规格相关章节原文贴进去），并写明「不得调用 subagent / subagent_fork / workflow」。agent 失败先读它的结果再决定，不许盲目重派。主代理只做拆分、派发、汇总、白名单检查、跑门禁、写报告。
2. **白名单**：只许改动 / 新增 §9 列出的文件。发现必须改白名单外的文件才能完成，停下来说明原因，不要改。
3. **基线测试一字不许改**：不得修改任何既有测试文件（`backend/tests/` 下已存在的文件，含 `conftest.py`）的输入、断言与夹具。新测试一律放 §9 列出的新文件。
4. **何时停下来问**：只有影响「实现什么」的问题才停（规格自相矛盾、规格要求的行为无法实现、必须改白名单外文件）。只影响「怎么实现 / 怎么测」的自己定，并在报告里写明理由。任何情况下不回滚已完成的工作。**你实测到的事实优先于规格的断言**——若代码现状与本规格「现状事实」不符，停下来说明不符之处。
5. **不要提交 git commit**，不要 `git stash`，不要切分支。改动留在工作区。
6. **不得访问真实网络调用火山接口**；所有供应商交互用 `httpx.MockTransport` 或假供应商。测试不得读仓库外文件、不得依赖 git 历史。
7. 后端测试命令一律在 `backend/` 下用 `.venv/bin/python -m pytest`（该 venv 已装好依赖和 pypinyin 0.55.0）；前端在 `frontend/` 下 `npm run lint`、`npx tsc --noEmit`、`npm run build`（node_modules 已装好）。改前端前先读 `frontend/AGENTS.md` 和 `frontend/node_modules/next/dist/docs/` 里与你改动相关的文档。
8. 结束时输出报告，开头是拆分表（如实列出全部派出过的 agent：名字、负责文件、结果），然后是变更总结五项：① 修改了哪些文件（含新增）② 实现了哪些功能 ③ 与 §13 验收标准逐项对应 ④ 测试结果（命令 + 原样输出末尾的计数行）⑤ 未完成或需人工确认的地方。

## 1. 产品目标与使用场景

Fiona 里启用了 Claude 智能体模式（Anthropic BYOK）的白名单用户，在聊天里说「帮我写首歌」后，由 Claude 主导一个**可逐步确认**的写歌流程：

1. 简短访谈（场景、送给谁、情绪、曲风参考）→ 2. 保存**创作简报**与**结构蓝图**（段落、每段行数与字数、押韵格式）→ 3. Claude 写歌词，服务端用**纯代码自检**（字数、押韵、结构）→ 4. 主人在卡片上看到简报、按段歌词与自检结果，可点某段「改这一段」让 Claude 只改那一段 → 5. 主人点卡片按钮「生成试听」（扣草莓、确认弹窗）→ 6. 火山豆包音乐异步生成，卡片显示进度，完成后可播放 → 7. 音频带 AI 隐式标识，界面常驻「AI 生成」标识。

差异点（不可丢）：流程每步可确认；改一段词只改那一段（其余段落原样保留）；押韵与字数由代码判定，不靠模型自评；扣费只能由主人点按钮触发，模型无法花用户的钱。

## 2. 范围

**P0 做**：上面 1–7；火山单供应商；每次生成 1 版；历史刷新后卡片可重建；删号 / 删会话 / 清空历史时清理写歌数据与音频。

**P0 不做**（不要实现，也不要留半成品入口）：腾讯 MPS / MiniMax；一次出两版与版本对比；偏好记忆；LRC 导出；歌词时间轴解析；音频显式提示的自制拼接；纯音乐 BGM；平台模型（非 Claude）路径的写歌；判断器 / 意图识别路径。

## 3. 现状事实（HEAD 4b45346，规格作者已逐条核对）

见 `01-brief.md` §4，以下是必须依赖的要点，行号以 HEAD 为准，动手前请自行复核：

- `backend/services/claude_agent.py`：`CLAUDE_CLIENT_TOOLS`（48–54）；`client_tools_for_turn`（57–74），开关关闭时**原样返回 `CLAUDE_CLIENT_TOOLS` 对象**；工具分派 548 起（563 小说分支、590 生图分支、657 通用分支，通用分支用 `CLAUDE_CLIENT_TOOLS` 查 required，会对未知工具名抛 StopIteration——所以写歌分支必须排在通用分支之前）；每轮最多 4 次工具（555）；联网来源卡在循环结束后追加（707–714）；`_agent_messages`（147–161）在本轮 user 消息里放北京时间文本块；`state.sys_prompt_final` 在 359 行赋值。
- `backend/services/chat_service.py`：`ChatState` dataclass（764）；`_save_response`（972）调 `save_message`；`_summarize_card_for_history`（493）对未知 subtype 输出 `[{source}]` + 要点行。
- `backend/database.py`：`_safe_migrate`（71）；`messages` 建表（129）及三条补列；`init_db` 里小说/工作室表 `CREATE TABLE IF NOT EXISTS`（约 310–320），不加迁移版本；`clear_message_history`（465）；`save_message`（488，`BEGIN IMMEDIATE` 内校验会话归属）；`delete_account_data`（791，单事务）；`reserve_strawberries`（1667）/ `refund_strawberries`（1685）。
- `backend/agent_store.py`：`get_conversation_messages`（330，338 行显式列 SELECT）；`delete_conversation`（354，单事务）。`resolve_chat_conversation`（283）在 `conversation_id is None` 时解析默认会话。
- `backend/main.py`：lifespan（117–150）启动工作室调度器等后台任务；路由 include（175–191）；`/health`（336–393）校验五道迁移版本（**本任务不改 `/health`，仍是五道**）。`require_auth` 中间件对 `/uploads/` 非私有前缀文件在开发回环下不鉴权——**写歌音频不得放进 uploads**。
- `backend/routers/conversations.py:62–71` 删会话后删文件；`backend/routers/me.py` 的 `clear_history` / `delete_account` 在事务提交后删文件。
- `backend/tests/conftest.py`：收集阶段把 `FIONA_DB_PATH`、`FIONA_UPLOADS_DIR` 指到临时目录；`client` 夹具设 `DEV_MODE=1`、把 `database.DB_PATH` 指到 `tmp_path`、触发 lifespan、阻断外网（只放行回环）、把工作室调度器换成空转。**它不会替你空转写歌轮询器**——所以写歌轮询器只在 `FIONA_SONG_AGENT=1` 时由 lifespan 启动，开关默认关；你的新测试若打开开关，要在自己的夹具里把轮询器换成空转并直接调用单步函数。
- 前端：`components/ChatBubble.tsx`（`CardData` 86、`ChatCard` 101、`cards` 渲染 346、`ChatBubbleProps` 240）；`app/page.tsx:2059–2072` 把 SSE `data.card`（`append: true`）**逐字段拷贝**成 `CardData`；`ChatBubble` 在 `page.tsx:2551` 渲染；输入框 `const [input, setInput]`（432）；`lib/useConversations.ts` 的 `StoredMessage`（10）与 `toMessages`（54）。样式类：`ceramic-card`、`tag`、`tag-rec`、`chip`、`btn`、`btn-primary`（`app/globals.css:339–363`）；工作室试听组件 `components/studio/StudioAssetAudio.tsx`、报价弹窗 `components/studio/QuoteDialog.tsx` 可参考写法（**不要 import `components/studio/*` 或后端 `studio.*`**，工作室正在另一分支频繁改动）。
- 前端没有 vitest；前端测试 = pytest 里读源码/用 `node -e` 做检查（参照 `backend/tests/test_claude_agent_frontend.py` 的写法）。`components/ChatModelSection.tsx` 的隐私说明有基线测试逐字比对，**不要改它**。
- 系统有 ffmpeg / ffprobe（`/opt/homebrew/bin`）。`ffmpeg -i in -map_metadata -1 -c:a libmp3lame -b:a 192k -id3v2_version 4 -metadata AIGC=<json> -metadata title=<标题> out.mp3` 写出的 `TXXX:AIGC` 可被 `ffprobe -v error -show_entries format_tags -of json` 读回为 `format.tags.AIGC`（规格作者已实测）。
- pypinyin 0.55.0 已在工作树 venv 里。实测见 brief §4（`Style.FINALS, strict=True`）。

## 4. 开关、准入与配置（新文件 `backend/song/config.py`）

所有配置**调用时读取**；非法值回落默认并只告警一次（`print("[song] code=config_invalid name=<变量名>")`，不打印值）。

| 变量 | 默认 | 规则 |
|---|---|---|
| `FIONA_SONG_AGENT` | `0` | 只有字面 `1` 开启 |
| `FIONA_SONG_USERS` | 空 | 逗号分隔的精确用户名；空 = 没有人可用 |
| `FIONA_SONG_STRAWBERRIES` | `30` | 每次生成预扣草莓，整数 1–500 |
| `FIONA_DAILY_SONGS` | `10` | 每用户每个上海自然日最多「提交成功或在途」的生成次数，整数 1–100；按数据库计数，`DEV_MODE` 不豁免 |
| `FIONA_SONG_MAX_INFLIGHT` | `2` | 每用户同时在途（queued/submitted/running/downloading）上限，整数 1–5 |
| `FIONA_SONG_DIR` | `backend/song_data` | 音频存放目录（相对路径按 backend 目录解析）；生产应设到 `/var/lib/fiona/songs` |
| `FIONA_SONG_EXPLICIT_WATERMARK` | `1` | 只有字面 `0` 关闭；开启时提交带 `AigcWatermark: true`（火山显式水印） |
| `FIONA_AIGC_PRODUCER` | `Fiona` | 隐式标识里的服务提供者名称，1–40 个可见字符 |
| `VOLC_MUSIC_ACCESS_KEY` / `VOLC_MUSIC_SECRET_KEY` | 无 | 火山子账号 AK/SK；缺任一则生成按钮返回 409「写歌服务未配置」，**不发请求** |

- `song_enabled_for(user) -> bool` = 开关开 且 用户名精确在白名单里。
- 密钥只从环境变量读，**不得**写入数据库、日志、trace、异常文案或响应；日志只写 ID / 状态 / 错误码。

## 5. 数据（新文件 `backend/song/store.py`）

### 5.1 建表

`SONG_TABLES_DDL`（列表），在 `database.init_db` 里紧跟小说表之后逐条执行 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`（与小说、工作室同一惯例），**不新增迁移版本号，不改 `/health`**。

```
song_projects(
  id TEXT PRIMARY KEY,                 -- uuid4().hex
  owner_username TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  brief_json TEXT NOT NULL DEFAULT '{}',
  structure_json TEXT NOT NULL DEFAULT '[]',
  lyrics_revision INTEGER NOT NULL DEFAULT 0,   -- 最新歌词稿号，0 = 还没有歌词
  revision INTEGER NOT NULL DEFAULT 0,          -- 乐观锁，每次写项目 +1
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
  索引：(owner_username, conversation_id)

song_lyrics(
  project_id TEXT NOT NULL, revision INTEGER NOT NULL,
  sections_json TEXT NOT NULL,          -- [{"id","type","lines":[...]}]
  check_json TEXT NOT NULL,             -- §6 自检结果
  changed_section_ids TEXT NOT NULL DEFAULT '[]',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (project_id, revision))

song_versions(
  id TEXT PRIMARY KEY,                  -- uuid4().hex，也作内容编号 produce_id 的来源
  project_id TEXT NOT NULL, owner_username TEXT NOT NULL,
  lyrics_revision INTEGER NOT NULL,
  provider TEXT NOT NULL,               -- P0 固定 'volc'
  params_json TEXT NOT NULL,            -- 冻结的提交参数（不含密钥）
  status TEXT NOT NULL,                 -- §7.2 状态机
  provider_task_id TEXT,
  progress INTEGER NOT NULL DEFAULT 0,
  strawberries INTEGER NOT NULL DEFAULT 0,
  billing_state TEXT NOT NULL,          -- none / reserved / settled / refunded
  idempotency_key TEXT NOT NULL,
  audio_rel_path TEXT,                  -- 相对 FIONA_SONG_DIR
  duration_s REAL, captions_raw TEXT,
  failure_code TEXT, failure_message TEXT,
  next_poll_at REAL, deadline_at REAL, -- time.time() 秒
  created_day TEXT NOT NULL,            -- Asia/Shanghai 的 YYYY-MM-DD，算每日上限
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (owner_username, idempotency_key))
  索引：(owner_username, status)、(project_id)
```

### 5.2 给既有 `messages` 表加列（长命库升级）

- `database.init_db` 里在现有三条 messages 补列之后加：`await _safe_migrate(db, "ALTER TABLE messages ADD COLUMN song_project_id TEXT DEFAULT NULL")`。旧代码的查询都写了列名，新列对旧代码无影响。
- **老库升级步骤**（写进 `docs/DEPLOYMENT.md` 新小节）：① 停后端 ② `sqlite3 <库> ".backup <库>.bak-song-<日期>"` ③ `python migrate.py`（默认在临时副本上演练，核对无报错）④ 正常启动服务（`init_db` 自动建表补列）⑤ `sqlite3 <库> "PRAGMA table_info(messages)"` 确认有 `song_project_id`，`/health` 仍为 ok ⑥ 回滚 = 停服恢复备份。
- `save_message` 新增仅限关键字参数 `song_project_id: str | None = None`：非空时，在同一 `BEGIN IMMEDIATE` 事务内校验 `song_projects` 里存在 `id=? AND owner_username=? AND conversation_id=<本次写入的会话 id>` 的行，校验失败则**照常保存消息但该列写 NULL**（不让写歌问题影响聊天落库）。
- `agent_store.get_conversation_messages` 的 SELECT 加上 `song_project_id`，返回给前端。

### 5.3 删除（三条路径，同事务删行，提交后删文件）

- `delete_account_data`、`agent_store.delete_conversation`、`clear_message_history` 各自在**原有事务内**删除该用户（或该会话）的 `song_versions` / `song_lyrics` / `song_projects` 行，并把这些版本的 `audio_rel_path` 收集起来。
- 返回值：`delete_account_data` 与 `delete_conversation` 的返回 dict 增加键 `song_audio_paths: list[str]`；`clear_message_history` 原返回 `list[str]` 不变（不改签名），改为把音频路径登记到新表 `song_cleanup_queue(path TEXT PRIMARY KEY, created_at ...)`（同属 `SONG_TABLES_DDL`）。前两条也同样登记进 `song_cleanup_queue`。
- 文件删除由 `song.media.drain_cleanup_queue()` 执行：只删 `FIONA_SONG_DIR` 之内的普通文件（`resolve()` 后必须在根下，拒绝符号链接与 `..`），删完或文件已不存在则出队，其他错误保留待下次。三个路由（`routers/conversations.py` 删会话、`routers/me.py` 清空历史与删号）在提交后各调用一次；lifespan 启动时调用一次；轮询器每 60 秒调用一次。
- 启动时另做一次**孤儿清扫**：`FIONA_SONG_DIR` 下文件名形如 `<32位hex>.mp3` 且数据库里没有任何 `song_versions.audio_rel_path` 指向它的，删除；`.part` 临时文件超过 1 小时的删除。目录不存在则跳过。

## 6. 歌词结构与纯代码自检（新文件 `backend/song/lyrics_check.py`，纯函数，无 I/O）

### 6.1 段落类型（= 火山歌词标签，小写）

`intro verse pre-chorus chorus bridge inst outro hook build-up drop solo`。其中 `intro inst outro solo` 是**器乐段**，`lines` 必须为空；其余为**唱段**，至少 1 行。

### 6.2 结构蓝图（`structure`）

`[{"id": "s1", "type": "verse", "lines": 4, "chars": [7, 9], "rhyme": "AABB"}, ...]`
- `id`：`^s[0-9]{1,2}$`，项目内唯一；1–16 段；必须至少有一个 `chorus` 或 `hook`。
- `lines`：唱段 1–12，器乐段 0；`chars`：`[min, max]`，1 ≤ min ≤ max ≤ 30（器乐段可省略）；`rhyme`：`AABB` / `ABAB` / `XAXA` / `AAAA` / `free`（器乐段可省略）。

### 6.3 歌词（`sections`）

`[{"id": "s1", "lines": ["……", "……"]}, ...]`，段落 id 与顺序必须和结构蓝图完全一致；`type` 从蓝图取。

### 6.4 自检结果 `check_lyrics(structure, sections, lang) -> {"ok": bool, "errors": [...], "warnings": [...], "lines": [...], "provider_text": str, "provider_chars": int}`

- **计字规则**：中文/粤语按「汉字 + 数字 + 拉丁字母组成的单词各计 1」，标点与空白不计；英文按空白分隔的单词计。
- **errors（任一存在则 `ok=false`，生成按钮不可用）**：
  - `structure_mismatch`：段落 id/顺序与蓝图不一致；
  - `empty_section`：唱段没有行，或某行去空白后为空；
  - `instrumental_has_lines`：器乐段有行；
  - `bracket_in_line`：行内含 `[` `]` `【` `】`（会破坏结构标签）；
  - `line_too_long`：某行计字超过 30；
  - `too_long`：拼出的 `provider_text` 字符数超过上限（`Chinese` / `Cantonese` 700，`English` 2000），或少于 5。
- **warnings（不阻断，显示给主人和 Claude）**：
  - `line_count`：唱段行数 ≠ 蓝图 `lines`；
  - `char_count`：某行计字超出 `[min-1, max+1]`；
  - `rhyme`：押韵格式不满足（见 6.5）；
  - `chorus_variant`：多个 `chorus` 段的歌词不完全相同（只提醒）。
- 每条 error/warning：`{"code", "section_id", "line_index"(可空), "message"}`，`message` 是给人看的中文短句，如「副歌第 2 行 11 字，蓝图要求 7–9 字」。
- `lines`：逐行 `{"section_id","line_index","chars","rhyme_group"(十三辙名或 null),"rhyme_ok"(bool 或 null)}`，供前端显示字数与 ✓/✗。
- `provider_text`：按段拼成 `"[verse]\n行1\n行2\n[chorus]\n……"`（标签独占一行，段与段之间不空行，器乐段只有标签），这就是提交给火山的 `Lyrics`。

### 6.5 押韵判定（十三辙）

- 每行取**最后一个汉字**；没有汉字（纯英文行）则该行不参与押韵（`rhyme_group=null`）。
- 读音：对**整行文本**调用 `pypinyin.lazy_pinyin(行, style=Style.FINALS, strict=True)`，取最后一个汉字对应位置的韵母（利用整句上下文判多音字）。**不要用 `heteronym=True`**（会带出生僻读音，brief §4 有实测）。
- 韵母 → 十三辙（以 strict=True 的实际输出为准）：
  - 发花：a ia ua　梭波：o uo e　乜斜：ie ve　一七：i v er　姑苏：u　怀来：ai uai　灰堆：ei uei　遥条：ao iao　油求：ou iou　言前：an ian uan van　人辰：en in uen vn　江阳：ang iang uang　中东：eng ing ong iong ueng
  - 不在表里的韵母 → `rhyme_group=null`，该行不参与判定。
- 格式（行号从 1 起，只看参与判定的行）：`AABB` = 第 1、2 行同辙，第 3、4 行同辙……（奇数行数时最后一行不判）；`ABAB` = 1 与 3 同辙，2 与 4 同辙，依次类推；`XAXA` = 所有偶数行同辙；`AAAA` = 所有行同辙；`free` = 不判。不满足的行 `rhyme_ok=false` 并产生 `rhyme` 警告；满足的 `true`；不参与的 `null`。
- 必须有单测覆盖：每一辙至少 1 对押韵字；「花/家」同辙、「天/心」不同辙、「春/军」同为人辰、「回/飞」同为灰堆、「秋/走」同为油求、「雪/姐」同为乜斜；「长」在「长江」与「长大」两种语境下的判定结果不同（证明用了整句上下文）。

## 7. 生成、轮询与音频

### 7.1 火山客户端（新文件 `backend/song/volc.py`）

- `sign_request(method, query: dict, body: bytes, *, ak, sk, xdate, host, region, service) -> dict(headers)`：实现 brief §3.1 的签名，签名头固定 `host;x-date`。**单测必须用 brief §3.1 的两组官方固定向量**断言 CanonicalRequest 哈希与 Signature 逐字相等，并加一条反例（body 改一个字节签名必须不同）。
- `VolcMusicClient(transport=None)`：`submit(params) -> task_id`、`query(task_id) -> dict`。端点 `https://open.volcengineapi.com/?Action=GenSongForTime&Version=2024-08-12` 与 `...Action=QuerySong...`；`httpx.AsyncClient(transport=..., trust_env=False, follow_redirects=False, timeout=httpx.Timeout(60 if submit else 20, connect=10))`；响应体读取上限 1 MiB。
- 提交结果分类（**付费 POST 只发一次，绝不自动重试**）：
  - `Code == 0` 且 `Result.TaskID` 是非空字符串 → 成功；
  - 读到完整的 HTTP 4xx，或 HTTP 200 但 `Code != 0` → `rejected`（确定没建任务）；
  - 超时、断连、5xx、坏 JSON、HTTP 200 却没有 TaskID → `uncertain`；
  - 异常文案不得包含响应正文、请求体或密钥，只带错误码（如 `HTTP_429`、`code_<Code>`、`transport_error`、`invalid_json`）。
- 查询结果：返回 `{"state": "waiting"|"running"|"succeeded"|"failed", "progress": int, "audio_url", "duration", "captions_raw", "failure_code", "failure_msg"}`，`Status` 0/1/2/3 依次对应；查询的网络错误、5xx、坏 JSON → 抛 `PollError`（下次再查）。
- 必须按 brief §3.3 的真实返回形状写测试样例：`Captions` 是**字符串**（可能是 `"{}"`、可能是一段 JSON 文本、可能缺失），原样存 `captions_raw`，P0 不解析；`FailureReason` 成功时为 `null`；`Duration` 是浮点数。
- 提交参数（`build_params(project, lyrics_check, version_id)`，结果冻结进 `params_json`，不含密钥）：
  - `Lyrics` = `provider_text`；`ModelVersion` = `"v4.3"`；`Duration` = 简报时长（整数 30–240）；`Lang` = 简报语言（`Chinese`/`English`/`Cantonese`）；`VodFormat` = `"mp3"`；`SkipCopyCheck` = `false`；`AigcWatermark` = 开关值；
  - `ImplicitWaterMark` = `{"ContentProducer": FIONA_AIGC_PRODUCER, "ProduceId": <version_id>, "Enable": true}`；
  - 简报里给了才传：`Genre`（≤3）、`GenreExtra`（≤2）、`Mood`（≤2）、`Gender`、`Timbre`（≤3）、`Key`、`Kmode`、`Tempo`、`Instrument`（≤5）、`Scene`（≤3），多值用英文逗号连接；
  - **所有枚举值必须在 `refs/volc-v43-options.md` 的表里**（把表整理成 `backend/song/volc_options.py` 里的常量集合，单测断言常量数与表一致：Genre/GenreExtra 119、Mood 26、Timbre 27、Kmode 2、Tempo 8、Instrument 22、Scene 108、Lang 3、Key 13）。不在表里的值在保存简报时就拒绝（见 §8）。

### 7.2 版本状态机（新文件 `backend/song/jobs.py`）

`queued → submitted → running → downloading → succeeded`；终态还有 `failed`、`rejected`、`uncertain`、`expired`。

- **创建**（`create_generation(user, project_id, lyrics_revision, idempotency_key)`，由路由调用）：一个 `BEGIN IMMEDIATE` 事务内依次检查——项目属于该用户；`lyrics_revision` 等于项目最新稿号且该稿自检 `ok=true`（否则 409「歌词有未解决的问题」或「歌词已更新，请刷新」）；同用户同幂等键已存在则直接返回那条版本（不重复扣费）；在途数 < `FIONA_SONG_MAX_INFLIGHT`（否则 429）；当日（上海自然日）非 `rejected` 的版本数 < `FIONA_DAILY_SONGS`（否则 429）；非 `DEV_MODE` 时原子扣草莓（同一事务内 `UPDATE users SET strawberry_balance = strawberry_balance - ? WHERE username=? AND strawberry_balance >= ?`，失败则 402 并沿用 `strawberry_insufficient_message()`），`billing_state='reserved'`；`DEV_MODE=1` 时不扣，`billing_state='none'`。插入版本行 `status='queued'`，提交事务后立即后台执行提交（`create_background_task`）。
- **提交**：从 `queued` 原子改成 `submitting`（用 `UPDATE … WHERE status='queued'`，影响 0 行就放弃，防重复提交）→ 调 `submit` →
  - 成功：`status='submitted'`、记 `provider_task_id`、`next_poll_at=now+5`、`deadline_at=now+900`；
  - `rejected`：`status='rejected'`、退款；
  - `uncertain`：`status='uncertain'`、**退款**（平台承担可能的上游计费，P0 自用可接受）、不重试；
  - 缺 AK/SK：在创建阶段就拒绝，不会走到这里。
- **轮询**（`poll_once(now)`，轮询器每 5 秒调用一次）：取 `status IN ('submitted','running') AND next_poll_at <= now` 的版本逐个 `query`：
  - waiting/running：更新 `progress`、`status='running'`；距创建不足 60 秒时 `next_poll_at=now+5`，之后 `now+10`；
  - succeeded：`status='downloading'` → 下载与转码（§7.3）→ 成功则 `status='succeeded'`、`billing_state='settled'`（若原为 reserved）、写 `audio_rel_path`/`duration_s`/`captions_raw`；下载或转码失败 → `status='failed'`、`failure_code` 记原因、退款；
  - failed：`status='failed'`、记 `failure_code`/`failure_msg`、退款；`FailureReason.Code == 300061` 或 `Msg == "InputLyricsPlagiarized"` 时给主人的文案为「歌词疑似与已有作品重复，请改写后再试」，其他为「生成失败，请稍后再试」；
  - `PollError`：只推迟 `next_poll_at=now+10`；
  - `now > deadline_at`：`status='expired'`、退款。
- **退款只退一次，且与标记同事务**：一个 `BEGIN IMMEDIATE` 事务内先 `UPDATE song_versions SET billing_state='refunded' WHERE id=? AND billing_state='reserved'`，影响 1 行才 `UPDATE users SET strawberry_balance = strawberry_balance + ? WHERE username=?`，再提交；`billing_state='none'` 不退。扣费同理：与插入版本行同一事务，并先调用 `database._apply_daily_refill(db, user, strawberry_daily_refill())`（与 `reserve_strawberries` 的顺序一致）。
- **删号后不复活**：轮询与下载写库时用 `WHERE id=? AND EXISTS(SELECT 1 FROM users WHERE username=owner_username)`；写库影响 0 行则删除刚下载的文件。
- **重启恢复**（lifespan，**仅开关开启时**；§5.3 的启动清理与孤儿清扫也只在开关开启时执行——测试用临时库启动时若清扫真实目录，会把开发目录里的歌全部当孤儿删掉）：`submitting` → `uncertain` 并退款（不知道是否已建任务）；`queued` → 重新调度提交；`downloading` → 改回 `running` 且 `next_poll_at=now`（URL 一年有效，可再下）；`submitted`/`running` 照常轮询。
- **测试隔离**：所有新测试必须用 `monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / ...))` 把音频目录指到临时目录，不得在仓库目录下产生任何文件；打开 `FIONA_SONG_AGENT` 的测试要把 `run_poller` 换成空转，直接调用 `poll_once` / 提交函数推进状态。
- **轮询器**：`run_poller()` 无限循环，每轮 `poll_once` + 每 60 秒 `drain_cleanup_queue`，单轮异常打印错误码后继续；lifespan 仅在 `FIONA_SONG_AGENT=1` 时 `create_background_task(run_poller(), label="song-poller")`。供应商用模块级工厂 `get_provider()`，测试可 monkeypatch 成假供应商。

### 7.3 下载、转码与隐式标识（新文件 `backend/song/media.py`）

- 只接受 `https` 且主机名匹配 `^v([1-9]|[1-4][0-9]|50)-default\.douyinvod\.com$` 的 `AudioUrl`，否则 `failure_code='result_host'`。独立 `httpx.AsyncClient(trust_env=False, follow_redirects=False)`，不带任何凭据；3xx 视为失败；`content-length` 超过 50 MB 或实际超过 50 MB 失败；写到 `FIONA_SONG_DIR` 内的 `.part` 临时文件并 fsync。
- 转码与写标识一步完成（ffmpeg 子进程，单次超时 120 秒，超时 kill）：`ffmpeg -nostdin -hide_banner -v error -y -i <part> -map_metadata -1 -vn -c:a libmp3lame -b:a 192k -id3v2_version 4 -metadata AIGC=<json> -metadata title=<项目标题> -metadata comment=本音频由人工智能生成 <out.part.mp3>`。不论上游给的是 wav、mp3 还是 mp4，一律转成 mp3。
  - `AIGC` 的 JSON（键顺序固定、无空格分隔符 `separators=(",",":")`）：`{"Label":"1","ContentProducer":<FIONA_AIGC_PRODUCER>,"ProduceID":<version_id>,"ReservedCode1":"","ContentPropagator":"","PropagateID":"","ReservedCode2":""}`。
- 写完用 `ffprobe -v error -show_entries format=duration:format_tags -of json` 回读：必须有音频流、`format.tags.AIGC` 解析后 `ProduceID` 等于版本 id、时长 > 5 秒；任何一项不满足 → 删文件、`failure_code='invalid_audio'`。通过后原子 `replace` 成 `FIONA_SONG_DIR/<version_id>.mp3`，`audio_rel_path` = `<version_id>.mp3`。
- 系统没有 ffmpeg/ffprobe → `failure_code='ffmpeg_unavailable'`，退款，不静默降级。
- 测试里用 ffmpeg 本地生成一段 6 秒正弦波 wav 作为「下载内容」（经 MockTransport 返回），跑完整转码并回读标识；同时测 mp4 容器输入（ffmpeg 生成带音轨的 mp4）。没有 ffmpeg 的环境这些测试 `skip`（但门禁环境有，必须 0 跳过）。

## 8. 给 Claude 的工具（新文件 `backend/song/tools.py`）与智能体接入

### 8.1 工具定义（Anthropic tool schema，用与 `claude_agent._tool` 相同的形状）

1. `song_save_brief`：保存或更新创作简报与结构蓝图；没有 `project_id` 时新建项目（绑定本轮会话）。
   - 入参：`project_id`（可选）；`title`（1–20 字）；`brief`：`theme`（≤200 字，必填）、`occasion`（≤60）、`recipient`（≤60）、`language`（`Chinese`/`English`/`Cantonese`，必填）、`duration_seconds`（30–240 整数，必填）、`gender`（`Female`/`Male`，可选）、`genre`（数组 ≤3）、`genre_extra`（≤2）、`mood`（≤2）、`timbre`（≤3）、`key`、`kmode`、`tempo`、`instrument`（≤5）、`scene`（≤3）、`style_notes`（≤200，只给人看，不传火山）；`structure`（§6.2）。枚举类字段的 schema 直接写 `enum`（取自 `volc_options.py`），服务端再校验一遍。
   - 返回给 Claude 的文本：项目 id、标题、结构摘要（如「s1 主歌 4 行 7–9 字 AABB；s2 副歌 4 行…」）；校验失败返回逐条错误，不建项目。
2. `song_save_lyrics`：保存整首歌词。入参 `project_id`、`base_revision`（当前最新稿号，新项目为 0）、`sections`（§6.3）。`base_revision` 不等于项目最新稿号 → 不保存，返回「歌词已被更新，请先调用 song_get_status」。成功则稿号 +1、存自检结果，返回新稿号 + 自检摘要（errors/warnings 逐条）。
3. `song_revise_section`：只改一段。入参 `project_id`、`base_revision`、`section_id`、`lines`、`reason`（≤60 字）。以 `base_revision` 那一稿为底，**只替换该段**，其余段落逐字保留，存为新稿（`changed_section_ids=[section_id]`），返回新稿号 + 该段新旧对照 + 自检摘要。
4. `song_get_status`：只读。入参 `project_id`。返回简报摘要、结构、最新稿号与歌词全文、自检摘要、最近 3 个版本的状态（不含音频地址）。
- 所有工具：项目必须属于 `ctx.user` 且属于本轮会话，否则返回「找不到这个写歌项目」；不扣草莓、不调用火山；执行只读写本地 SQLite，必须远小于 1 秒。
- 工具结果文本不得包含用户名、会话 id 以外的内部路径、密钥。

### 8.2 接入 `services/claude_agent.py`（尽量少改）

- `client_tools_for_turn`：在现有小说逻辑之外，若 `song_enabled_for(ctx.user)` 且非危机轮（`state.crisis or state.crisis_level is not None` 时不加），返回一个**新列表** = 原本要返回的列表 + 4 个写歌工具；写歌关闭时返回值与现在完全一致（包括「小说也关闭时返回 `CLAUDE_CLIENT_TOOLS` 原对象」）。
- 分派：在 563 行小说分支之前加 `if name in SONG_TOOL_NAMES:` 分支，调用 `song.tools.execute(name, args, ctx=ctx, conversation_id=<本轮实际会话 id>)`（在 `asyncio` 中直接 await，异常时返回「写歌工具暂时不可用」并 `agent_tool_errors += 1`）。记下本轮触达的项目 id（取最后一个成功写入或读取的项目）。
- 循环结束、联网来源卡之前：若本轮触达过项目，追加**一张**卡：`{"type":"card","subtype":"song_project","source":"写歌","points":["《<标题>》第 <稿号> 稿"],"project_id":<id>,"error":False}`，按现有方式 `state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"` 并 `yield chat._sse({"card": card, "append": True})`，`delivered=True`。异常分支同样补发（参照 738–744 行来源卡的处理）。
- `ChatState` 增加字段 `song_project_id: str | None = None`；追加卡片时赋值；`_save_response` 把它传给 `save_message(..., song_project_id=state.song_project_id)`。
- 写歌工具**不改变计费**：不设置 `billable_pending`。
- 本轮会话 id：`ctx.conversation_id` 为 None 时，用 `agent_store.resolve_chat_conversation(ctx.user, None)` 得到默认会话 id（与 `save_message` 写入的是同一个）。
- 写歌开启的轮次，在 `state.sys_prompt_final` **末尾**追加 §8.3 的固定文本（静态，利于缓存）；并在 `_agent_messages` 构造的本轮 user 消息里、北京时间块之后，若本会话存在写歌项目，加一个文本块（≤300 字）：「（本会话的写歌项目：《标题》id=…，最新第 N 稿，自检 X 个问题 / Y 条提醒，最近一次生成：状态。需要歌词全文请调用 song_get_status。）」，只取最近更新的一个项目。写歌关闭时这两处输出与现在逐字节一致。

### 8.3 写歌模式提示词（逐字使用，放在 `song/tools.py` 常量 `SONG_MODE_PROMPT`）

```
【写歌模式】主人明确想写歌、改歌时才进入，否则照常聊天。
1. 先简短了解：写给谁、什么场合、想要的情绪和曲风、大约多长；一次最多问三个问题，主人说「你定」就由你决定。
2. 想清楚后调用 song_save_brief 保存创作简报和结构蓝图（段落、每段行数、每行字数范围、押韵格式），再调用 song_save_lyrics 提交整首歌词。歌词只通过工具提交，回复正文里不要重复贴整首歌词，用一两句话说明你的构思和需要主人确认的地方。
3. 工具会返回字数和押韵的自检结果。有「问题」时先自己修改再提交一次；只有「提醒」时可以在回复里说明取舍。
4. 主人要改某一段时，只用 song_revise_section 改那一段，其他段落一个字也不要动。
5. 不模仿任何真实歌手的嗓音或唱腔；不照抄已有歌曲的歌词，连续 8 个字以上相同就算照抄。
6. 生成试听由主人在卡片上点按钮确认，你不能替主人生成，也不要说「已经开始生成」。
```

## 9. 白名单（只许改动 / 新增这些文件）

新增：
- `backend/song/__init__.py`、`backend/song/config.py`、`backend/song/store.py`、`backend/song/lyrics_check.py`、`backend/song/volc_options.py`、`backend/song/volc.py`、`backend/song/media.py`、`backend/song/jobs.py`、`backend/song/tools.py`
- `backend/routers/songs.py`
- `backend/tests/test_song_config.py`、`test_song_lyrics_check.py`、`test_song_volc.py`、`test_song_store.py`、`test_song_media.py`、`test_song_jobs.py`、`test_song_agent_tools.py`、`test_song_routes.py`、`test_song_frontend.py`（均在 `backend/tests/` 下）
- `frontend/lib/songs.ts`、`frontend/components/SongProjectCard.tsx`
- `docs/tasks/2026-10-18-song-agent-p0/03-report.md`（你的报告）

修改：
- `backend/services/claude_agent.py`、`backend/services/chat_service.py`、`backend/database.py`、`backend/agent_store.py`、`backend/main.py`、`backend/routers/conversations.py`、`backend/routers/me.py`、`backend/requirements.txt`（加一行 `pypinyin==0.55.0`）、`backend/.env.example`
- `frontend/components/ChatBubble.tsx`、`frontend/app/page.tsx`、`frontend/lib/useConversations.ts`
- `.gitignore`（加 `backend/song_data/`）
- 文档：`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、`docs/DEPLOYMENT.md`
- **事实变更要全库搜索**：本任务改变了「工具清单」「消息表字段」「删号/删会话会清理哪些数据」「环境变量」「数据位置」等事实。用 grep 在上面这些文档里找到所有陈述点逐处更新；若发现白名单外的文档也陈述了这些事实，列进报告「需人工确认」，不要改。

## 10. 路由（新文件 `backend/routers/songs.py`，前缀 `/songs`）

- 全部路由：`song_enabled_for(user)` 为假一律 404；响应头 `Cache-Control: private, no-store`；项目/版本不属于当前用户一律 404（不区分「不存在」与「无权」）。
- `GET /songs/projects/{project_id}` → 项目快照：`{id, title, brief, structure, lyrics_revision, lyrics: {revision, sections:[{id,type,lines}], check}, versions: [{id, lyrics_revision, status, progress, failure_message, duration_s, created_at}]（最新在前，最多 10 个）, price_strawberries, can_generate: bool, generate_blocked_reason: str|null, configured: bool}`。`can_generate` = 有歌词 且 自检 ok 且 已配置 AK/SK 且 未达在途/每日上限。
- `POST /songs/projects/{project_id}/generate`，body `{"lyrics_revision": int, "idempotency_key": "<8–64 位 [A-Za-z0-9_-]>"}` → 202 + 版本对象；错误码见 §7.2（402/409/429，`detail` 为中文短句）。按 IP 限流沿用 slowapi 写法：10 次/分钟。
- `GET /songs/versions/{version_id}/audio` → `FileResponse(media_type="audio/mpeg")`，支持 Range（Starlette 自带）；文件路径 = `FIONA_SONG_DIR / audio_rel_path` 经 `resolve()` 后必须在根目录下；`?download=1` 时加 `Content-Disposition: attachment; filename*=UTF-8''<标题>.mp3`（标题经 `quote`）。状态不是 `succeeded` → 404。
- `main.py`：`app.include_router(songs.router)`；lifespan 按 §5.3 / §7.2 启动清理、恢复与轮询器。

## 11. 前端

### 11.1 数据与轮询（`frontend/lib/songs.ts`）

- 类型：`SongProject`、`SongVersion`、`SongCheck` 等，与 §10 快照一致。
- `useSongProject(projectId)`：首次加载拉快照；有版本处于 `queued/submitting/submitted/running/downloading` 时每 4 秒拉一次；页面 `document.hidden` 时暂停；在途超过 15 分钟停止轮询；组件卸载或账号切换时 `AbortController` 取消请求。返回 `{project, loading, error, refresh}`。
- `generateSong(projectId, lyricsRevision)`：生成 `idempotency_key`（`crypto.randomUUID()` 去掉横线），失败时把后端 `detail` 原样作为错误文字。
- 音频地址：`${API}/songs/versions/${id}/audio`（`import { API_BASE as API } from "@/lib/config"`，与 `ChatBubble.tsx`、`useConversations.ts` 相同），版本 id 必须匹配 `^[0-9a-f]{32}$` 才拼地址。

### 11.2 卡片（`frontend/components/SongProjectCard.tsx`）

视觉沿用现有 `ceramic-card` 卡片语言，与工作室卡同一家族；宽度 `w-full max-w-[600px]`；**所有文字不加粗**（不用 `font-semibold`/`font-bold`，不用 `font-weight ≥ 600`；层次只靠字号与 `--ink`/`--ink2` 灰度；现有 `font-medium` 也不要新增）；不新增颜色、字体或依赖；不用渐变、大圆角或装饰图形。自上而下：

1. **页眉**一行：左「写歌 ·《标题》」，右侧常驻 `tag`「AI 生成」（任何状态都显示，含加载与错误态）。
2. **简报**一行 `tag` 组：语言、时长（如「2 分钟」）、曲风、情绪、调式（如「A# 小调」）、速度（中文名）、人声（女声/男声）；值为空的不显示。中文名取自 `refs/volc-v43-options.md` 的说明列（在 `songs.ts` 里放一份取值 → 中文名的映射，只放 Mood、Genre、Tempo、Kmode、Timbre、Lang 用到的）。
3. **歌词**按段：段标题行「主歌 · s1」（段类型中文名：intro 前奏、verse 主歌、pre-chorus 导歌、chorus 副歌、bridge 桥段、inst 间奏、outro 尾奏、hook 记忆点、build-up 铺垫、drop 高潮段、solo 独奏）+ 右侧按钮 `chip`「改这一段」（器乐段不显示）；每行：歌词文字 + 右侧小字「8 字」+ 押韵标记（`rhyme_ok` 为 true 显示「押」、false 显示「不押」并用 `--seal` 色、null 不显示）。器乐段只显示「（器乐）」。本稿新改过的段（`changed_section_ids`）段标题右侧加 `tag`「本稿修改」。
4. **自检**：errors 逐条列出（`--seal` 色），warnings 逐条列出（`--ink2`）；都为空显示「字数与押韵检查通过」。
5. **操作行**：主按钮 `btn btn-primary`「生成试听（N 草莓）」——`can_generate=false` 时禁用并在按钮下方显示 `generate_blocked_reason`；点击打开原生 `<dialog>` 确认框，正文三行：「将用第 X 稿歌词生成一首约 Y 秒的试听，预扣 N 颗草莓，失败自动退回。」「歌词与曲风参数会发送给字节跳动火山引擎生成音乐。」「生成的音频带有 AI 生成标识。」，按钮「确认生成」/「取消」；确认后按钮转为禁用直到请求返回。
6. **版本列表**（最新在前）：每个版本一行「第 X 稿 · 状态文字」+ 进度或结果——排队中 / 生成中 N%（显示已用时长「已用 1 分 20 秒」）/ 正在保存 / 已完成（原生 `<audio controls preload="none">` + 「下载」文字链接）/ 失败：`failure_message` / 结果不确定，已退回草莓 / 超时，已退回草莓。
7. **状态**：加载态（骨架或「正在读取写歌项目…」）、错误态（「写歌项目读取失败」+「重试」按钮）、404 态（「这个写歌项目已删除」）、空歌词态（只有简报时：「歌词还在写，Claude 提交后会显示在这里」）。

「改这一段」：调用父组件传入的 `onCompose(text)`，把「把【副歌 s2】改成：」填进聊天输入框并聚焦（不自动发送）。

### 11.3 接入现有组件

- `ChatBubble.tsx`：`CardData` 增加 `project_id?: string`；`ChatCard` 增加 `subtype === "song_project"` 分支渲染 `SongProjectCard`；`ChatBubbleProps` 增加可选 `onCompose?: (text: string) => void` 与 `songCardCompact?: (projectId: string) => boolean`，透传给卡片。**同一项目在消息列表里出现多次时，只有最后一条消息显示完整卡片**，更早的显示一行紧凑提示「写歌《标题》已更新，见下方最新卡片」（`songCardCompact` 返回 true 时）。
- `page.tsx`：2059–2072 两处 `CardData` 拷贝都加上 `project_id: data.card.project_id`；给 `ChatBubble` 传 `onCompose`（`setInput(text)` 并聚焦输入框）与 `songCardCompact`（根据当前消息列表计算每个项目最后出现的消息 id）。
- `useConversations.ts`：`StoredMessage` 增加 `song_project_id?: string | null`；`toMessages` 对有值的 assistant 消息设 `cards: [{source: "写歌", points: [], subtype: "song_project", project_id}]`（刷新后卡片重建）。

## 12. 文档与配置

- `backend/.env.example`：§4 全部变量，带中文注释；AK/SK 只写变量名和获取方式（火山控制台右上角账号 →「密钥管理」新建子账号密钥，最小权限；在 `console.volcengine.com/ai-music/product` 开通「生成人声歌曲」后付费），值留空。
- `CLAUDE.md` 新增一节「写歌智能体（P0）」：开关与白名单、四个工具、计费（每次生成预扣 N 颗、失败/不确定/超时退回、`DEV_MODE` 不扣）、隐私（歌词与曲风参数发送给字节跳动火山引擎；Claude 侧仍是用户自带 Key）、标识（隐式 ID3 `TXXX:AIGC` + 界面「AI 生成」+ 可选火山显式水印）、数据位置 `FIONA_SONG_DIR`、删除行为、已知局限（无局部编辑、改词需整首重生成；Captions 未解析；只对 Claude 智能体模式开放）。README、ARCHITECTURE、PLAN、DEPLOYMENT 按 §9 的「全库搜索」更新；DEPLOYMENT 写明生产 `FIONA_SONG_DIR=/var/lib/fiona/songs` 并注明「备份脚本尚未包含写歌目录（P2）」。

## 13. 验收标准（门禁会逐条执行）

命令均在工作树根目录 `W=/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-song-p0` 下执行。

1. **白名单**：`git status --porcelain` 列出的每个路径（含未跟踪）都在 §9 内；`git diff --stat 4b45346 -- backend/tests` 只出现新文件（既有测试文件零改动，逐文件 `git diff --quiet 4b45346 -- <file>` 退出码 0）。
2. **后端全量**：`cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider -rs` 退出码 0，0 failed、0 skipped；passed 数 = **基线 7230**（规格作者 2026-10-18 在本工作树 venv 实测：`7230 passed, 32 warnings in 265.04s`，0 skipped）+ 新增测试数。`/health` 仍只校验五道迁移（不改 `main.py` 的 `_check_health`）。
3. **新测试单跑**：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py` 退出码 0，且输出含 `passed` 且不含 `skipped`。
4. **签名固定向量**：`test_song_volc.py` 里存在断言 `5e8480ceea12d0000a23c054151c50dd02c1a7dec835004057d19f13d53a7658` 与 `1eda9e7e6b1728151a8e8791fdaf67cfbd28bd5c80d0fce2eb208746cf483105` 的用例，以及一个 body 改一字节签名不同的反例。
5. **开关关闭零影响**：`test_song_agent_tools.py` 断言 `FIONA_SONG_AGENT` 未设置时：`client_tools_for_turn` 返回的对象 `is CLAUDE_CLIENT_TOOLS`（小说也关闭时）；用假流跑一轮，发给模型的请求里 `tools` 名字集合与 `CLAUDE_CLIENT_TOOLS` 相同、system 文本不含「【写歌模式】」、本轮 user 消息的内容块只有北京时间块与原文块（无写歌项目块）；`/songs/*` 返回 404；lifespan 不启动 `song-poller`。再用同一假流把开关打开（用户在白名单）跑一轮，断言上述三处**确实变化**（正控：证明这些断言能区分开关状态）。
6. **开关开启的完整流程**（假供应商 + 本地 ffmpeg，全离线）：Claude 假流（参照 `tests/test_claude_agent_runtime.py` 构造 FakeStream 的方式）依次调用 `song_save_brief`、`song_save_lyrics` → SSE 里恰好一张 `subtype=song_project` 卡 → 落库消息 `song_project_id` 有值 → `GET /songs/projects/{id}` 快照含歌词与自检 → `POST generate` 202 → 调 `poll_once` 若干次 → 版本 `succeeded` → `GET audio` 返回 200、`audio/mpeg`、带 `Range: bytes=0-1` 时 206 → 用 ffprobe 读回 `AIGC` 标签且 `ProduceID` = 版本 id。
7. **计费**：非 DEV_MODE 下生成扣 N 颗；`rejected` / `failed` / `uncertain` / `expired` 各退回且只退一次（并发调用两次退款函数，余额只回 N）；同幂等键重复 POST 只扣一次；余额不足 402 且不建版本；DEV_MODE 不扣不退。
8. **权限**：别人的项目/版本 → 404；白名单外用户 → 404；`../` 或符号链接逃逸 → 拒绝。
9. **删除**：删号、删会话、清空历史后，对应 `song_*` 行为 0，音频文件被删除；删号后轮询器写库影响 0 行且新下载文件被删。
10. **前端**：`cd frontend && npm run lint && npx tsc --noEmit && npm run build` 全部退出码 0；`test_song_frontend.py` 检查：`SongProjectCard.tsx` 与 `songs.ts` 中不出现 `font-semibold`、`font-bold`、`fontWeight`；卡片源码在加载/错误/404/空歌词各分支都包含「AI 生成」标识（或该标识在所有分支之外的公共页眉里，测试需证明这一点）；`page.tsx` 两处卡片拷贝都含 `project_id`；`useConversations.ts` 映射了 `song_project_id`。
11. **版式**（门禁方用浏览器实测，你只需保证实现合理）：聊天区宽 1280 与 1263（1280−17，模拟 Windows 经典滚动条）、手机 375 与 358 下，写歌卡片容器 `scrollWidth <= clientWidth`（不产生横向滚动），歌词长行自动换行；卡片内正文字号不小于 12px。
12. **长命库升级**（门禁方执行，你不要读任何真实数据库）：门禁方会把一份长期使用的库拷贝到临时目录，用新代码启动，检查 `messages` 多出 `song_project_id`、三张 `song_*` 表与 `song_cleanup_queue` 已建、`/health` 为 ok、旧消息可正常读取。
13. **浅克隆**：新测试不依赖 git 历史、不读仓库外文件（门禁会在浅克隆副本里跑 `tests/test_song_*.py`）。
14. **报告**：`docs/tasks/2026-10-18-song-agent-p0/03-report.md` 按 §0 第 8 条格式写好。

## 14. 并行拆分建议（按文件不重叠，可再细分）

| agent | 负责文件 |
|---|---|
| A 配置与选项 | `song/__init__.py`、`song/config.py`、`song/volc_options.py`、`tests/test_song_config.py` |
| B 自检 | `song/lyrics_check.py`、`tests/test_song_lyrics_check.py` |
| C 火山客户端 | `song/volc.py`、`tests/test_song_volc.py` |
| D 存储与删除 | `song/store.py`、`database.py`、`agent_store.py`、`routers/conversations.py`、`routers/me.py`、`tests/test_song_store.py` |
| E 媒体 | `song/media.py`、`tests/test_song_media.py` |
| F 任务与路由 | `song/jobs.py`、`routers/songs.py`、`main.py`、`tests/test_song_jobs.py`、`tests/test_song_routes.py` |
| G 智能体接入 | `song/tools.py`、`services/claude_agent.py`、`services/chat_service.py`、`tests/test_song_agent_tools.py` |
| H 前端 | `frontend/lib/songs.ts`、`frontend/components/SongProjectCard.tsx`、`ChatBubble.tsx`、`page.tsx`、`useConversations.ts`、`tests/test_song_frontend.py` |
| I 文档 | `CLAUDE.md`、`README.md`、`docs/*.md`、`PLAN.md`、`.env.example`、`.gitignore`、`requirements.txt` |

模块之间的接口以本规格为准（函数名、参数、返回形状）；先由主代理把 §5–§8 的函数签名写成各 agent 共享的接口说明，再并行。全部完成后由主代理统一跑 §13 的 1–3、10，修好再写报告。
