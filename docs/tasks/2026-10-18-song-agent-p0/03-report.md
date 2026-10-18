# 03-report · Fiona 写歌智能体 P0

日期：2026-10-18　工作树：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-song-p0`　分支：`song-agent-p0`　代码基线：`4b45346`

## 拆分表（全部实际派出过的 agent）

| 轮次 | agent 名称 | 负责文件 | 结果 |
|---|---|---|---|
| 第一波 | A 配置与火山选项 | `backend/song/__init__.py`、`config.py`、`volc_options.py`、`tests/test_song_config.py` | 完成；13 passed；常量数量与 refs 逐项比对一致 |
| 第一波 | B 歌词结构与自检 | `backend/song/lyrics_check.py`、`tests/test_song_lyrics_check.py` | 完成；111 passed；十三辙与上下文测试通过，记录「长」测试的实测取舍 |
| 第一波 | C 火山客户端 | `backend/song/volc.py`、`tests/test_song_volc.py` | 完成；57 passed；两组官方签名向量逐字通过，含改一字节反例 |
| 第一波 | D 存储与删除 | `backend/song/store.py`、`database.py`、`agent_store.py`、`routers/conversations.py`、`routers/me.py`、`tests/test_song_store.py` | 完成；10 passed；另跑删号/会话等回归 197+374+581 passed |
| 第一波 | E 媒体 | `backend/song/media.py`、`tests/test_song_media.py` | 完成；25 passed、0 skipped；真实 ffmpeg 生成 wav/mp4 并回读 AIGC |
| 第一波 | H 前端 | `frontend/lib/songs.ts`、`components/SongProjectCard.tsx`、`ChatBubble.tsx`、`app/page.tsx`、`lib/useConversations.ts`、`tests/test_song_frontend.py` | 完成；15 passed；lint/tsc/build 通过（lint 仅既有 warning） |
| 第一波 | I 文档与配置 | `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、`docs/DEPLOYMENT.md`、`backend/.env.example`、`backend/requirements.txt`、`.gitignore` | **失败**：返回空字符串，未写入任何文件；读结果后没有盲目原样重派，改为按文件拆成 I1–I3 |
| 第二波 | F 任务、路由与主入口 | `backend/song/jobs.py`、`routers/songs.py`、`main.py`、`tests/test_song_jobs.py`、`tests/test_song_routes.py` | 完成；24 + 12 passed；真实 ffmpeg 的 submit→poll→下载转码手工链路通过 |
| 第二波 | G 工具与 Claude 接入 | `backend/song/tools.py`、`services/claude_agent.py`、`services/chat_service.py`、`tests/test_song_agent_tools.py` | 完成；13 passed；开关关闭零影响、正控、工具流与卡片测试通过 |
| 文档补跑 | I1 CLAUDE 与 README | `CLAUDE.md`、`README.md` | 完成；新增写歌章节并更新工具/消息/删除/数据目录事实 |
| 文档补跑 | I2 ARCHITECTURE 与 PLAN | `docs/ARCHITECTURE.md`、`PLAN.md` | 完成；新增写歌架构、状态机、删除与 P1/P2 界限 |
| 文档补跑 | I3 部署、env、依赖、gitignore | `docs/DEPLOYMENT.md`、`backend/.env.example`、`backend/requirements.txt`、`.gitignore` | 完成；升级六步、生产目录、备份缺口、10 个变量、pypinyin、song_data |
| 集成 | 主代理 | 上述文件的交叉修复与白名单/门禁 | 修复文档精确短语、默认会话项目摘要、`.part.mp3` 清扫；统一跑门禁并写本报告 |

所有 agent 均被明确要求：不得调用 subagent / subagent_fork / workflow、不得修改既有测试、不得访问真实网络、不得 git commit/stash。

## ① 修改了哪些文件（含新增）

### 新增

- 后端模块：`backend/song/__init__.py`、`config.py`、`store.py`、`lyrics_check.py`、`volc_options.py`、`volc.py`、`media.py`、`jobs.py`、`tools.py`
- 路由：`backend/routers/songs.py`
- 新测试：`backend/tests/test_song_config.py`、`test_song_lyrics_check.py`、`test_song_volc.py`、`test_song_store.py`、`test_song_media.py`、`test_song_jobs.py`、`test_song_agent_tools.py`、`test_song_routes.py`、`test_song_frontend.py`
- 前端：`frontend/lib/songs.ts`、`frontend/components/SongProjectCard.tsx`
- 本报告：`docs/tasks/2026-10-18-song-agent-p0/03-report.md`

### 修改

- 后端：`backend/services/claude_agent.py`、`backend/services/chat_service.py`、`backend/database.py`、`backend/agent_store.py`、`backend/main.py`、`backend/routers/conversations.py`、`backend/routers/me.py`、`backend/requirements.txt`、`backend/.env.example`
- 前端：`frontend/components/ChatBubble.tsx`、`frontend/app/page.tsx`、`frontend/lib/useConversations.ts`
- 配置与文档：`.gitignore`、`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、`docs/DEPLOYMENT.md`

未修改任何既有测试文件；`git diff --name-only 4b45346 -- backend/tests` 为空。未提交 git commit，未 stash，未切分支。

## ② 实现了哪些功能

- **配置与准入**：`song/config.py` 全部调用时读取；开关只有字面 `1` 开启；用户名精确白名单；价格、每日、在途、目录、显式水印、AIGC 提供者、火山 AK/SK 全部按 §4 校验；非法值只告警一次且不打印值。
- **数据**：`song_projects`、`song_lyrics`、`song_versions`、`song_cleanup_queue` 四表及索引由 `init_db` 幂等创建；`messages` 补 `song_project_id`；`save_message` 在同一事务校验项目归属，失败仍照常落消息；删号、删会话、清空历史同事务删 `song_*` 行并把音频登记队列。
- **歌词自检**：结构蓝图校验、11 种段落类型、中英文/粤语计字、十三辙押韵判定（整句 `lazy_pinyin(..., Style.FINALS, strict=True)`，不用 heteronym）、AABB/ABAB/XAXA/AAAA/free、provider_text 拼装与长度限制、逐行字数/押韵结果、错误与提醒中文文案。
- **火山客户端**：官方 HMAC-SHA256 签名、`GenSongForTime`/`QuerySong`、1 MiB 上限、付费 POST 只发一次、rejected/uncertain/PollError 分类、`build_params` 冻结参数与 v4.3 枚举。
- **生成与计费**：`queued → submitting → submitted → running → downloading → succeeded` 状态机；非 DEV 预扣、幂等键、每日/在途上限、失败/不确定/超时/rejected 只退一次、DEV 不扣不退；重启恢复与 5 秒轮询、60 秒队列清理。
- **媒体与标识**：只接受火山视频域名的 https 结果；50 MB 限制；`.part` fsync；ffmpeg 一步转 mp3 并写 `TXXX:AIGC`；ffprobe 回读音频流、ProduceID、时长 > 5 秒；缺 ffmpeg 报 `ffmpeg_unavailable`；清理队列只删根内普通文件，启动孤儿清扫。
- **Claude 工具**：四个工具保存/更新简报、保存整首歌词、只改一段、只读状态；项目 owner+会话隔离；`execute` 通过 `context["project_id"]` 回报本轮触达项目；写歌工具不改变计费。
- **智能体接入**：白名单非危机轮追加四个工具；工具分派在小说分支之前；默认会话解析；写歌提示词拼进 `_final_system_prompt` 的入参（R1 修正，安全规则仍在最后一条 system 末尾）；user 消息追加 ≤300 字项目摘要；循环结束/异常补发一张 `song_project` 卡；`ChatState.song_project_id` 落库；关闭时请求、提示词、消息逐字节不变。
- **HTTP API**：`GET /songs/projects/{id}` 快照、`POST /songs/projects/{id}/generate`（202/402/409/429）、`GET /songs/versions/{id}/audio`（FileResponse + Range + 下载头）；全部白名单外 404、owner 隔离、`private, no-store`、10 次/分钟限流。
- **前端**：`songs.ts` 类型、4 秒轮询/隐藏暂停/15 分钟停止/AbortController、幂等键、音频地址校验、中文标签映射；`SongProjectCard` 页眉常驻「AI 生成」、简报 tag、分段歌词/字数/押韵、本稿修改、自检、原生 dialog 确认、版本进度/播放/下载、加载/错误/404/空歌词态；`ChatBubble`、`page.tsx`、`useConversations` 接入与同项目紧凑提示。
- **文档与配置**：`CLAUDE.md`、`README.md`、`ARCHITECTURE`、`PLAN`、`DEPLOYMENT` 更新工具/消息/删除/环境变量/数据位置/备份事实；`.env.example` 全部 10 个变量；`requirements.txt` 加 `pypinyin==0.55.0`；`.gitignore` 加 `backend/song_data/`。

## ③ 与 §13 验收标准逐项对应

| # | 验收项 | 结果与证据 |
|---|---|---|
| 1 | 白名单 | `git status --porcelain -uall` 仅出现 §9 允许路径；`git diff --name-only 4b45346 -- backend/tests` 为空；`conftest.py`、`_fakes.py` 对基线 `git diff --quiet` 均退出 0 |
| 2 | 后端全量 | `env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider -rs`：`7510 passed, 35 warnings in 284.84s`，0 failed、0 skipped；基线 7230 + 新增 280 |
| 3 | 新测试单跑 | `tests/test_song_*.py`：`280 passed, 35 warnings in 5.09s`，无 skipped |
| 4 | 签名固定向量 | `test_song_volc.py` 断言 `5e8480ce...`、`1eda9e7e...`，并有 body 改一字节签名不同的反例 |
| 5 | 开关关闭零影响 | `test_song_agent_tools.py` 断言 `is CLAUDE_CLIENT_TOOLS`、请求 tools 与常量一致、system 无「【写歌模式】」、user 块仅时间+原文、`/songs/*` 404、lifespan 无 `song-poller`；正控断言三处变化 |
| 6 | 完整流程 | 单测覆盖假流工具→一张卡→`song_project_id`→快照→202→poll→succeeded→audio 200/206；主代理另用真实 ffmpeg 手工跑通并 ffprobe 回读 `ProduceID` 匹配 |
| 7 | 计费 | `test_song_jobs.py` 覆盖扣 N、rejected/failed/uncertain/expired 退款、并发只退一次、幂等只扣一次、余额不足 402 不建版本、DEV 不扣不退 |
| 8 | 权限 | 路由与 `safe_audio_path` 测试覆盖他人项目/版本 404、白名单外 404、`../` 与符号链接逃逸拒绝 |
| 9 | 删除 | `test_song_store.py` 与 `test_song_jobs.py` 覆盖删号/删会话/清空历史后行数 0、音频删除、删号后写库影响 0 且新文件被删 |
| 10 | 前端 | `npm run lint` 退出 0（0 errors，25 个既有 warnings）、`npx tsc --noEmit` 退出 0、`npm run build` 退出 0；`test_song_frontend.py` 检查无加粗 token、AI 生成公共页眉、两处 `project_id`、`song_project_id` 映射 |
| 11 | 版式 | 卡片 `w-full max-w-[600px] min-w-0`、`flex-wrap`、`break-words`、正文最小 `text-xs`；浏览器实测由门禁方执行 |
| 12 | 长命库升级 | `test_song_store.py` 用旧 messages 表验证补列、四表/索引创建、旧消息可读；`/health` 未改，仍五道迁移 |
| 13 | 浅克隆 | 新测试只读仓库内路径、不依赖 git 历史；未使用仓库外夹具 |
| 14 | 报告 | 本文件按 §0 第 8 条格式编写 |

## ④ 测试结果（命令 + 原样输出末尾计数行）

> 本机环境变量 `NO_PROXY`/`no_proxy` 含 `[::1]`，httpx 0.28 在测试收集期会把它误解析为非法端口并报 `Invalid port: ':1]'`；这是本机环境问题，不是代码问题。因此本机所有 pytest 命令都加了 `env -u NO_PROXY -u no_proxy`；门禁环境若无该变量可直接用规格里的原命令。

### 基线（改动前）

```bash
cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider -rs
```

```text
7230 passed, 32 warnings in 271.71s (0:04:31)
```

### 全量（改动后）

```bash
cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider -rs
```

```text
7510 passed, 35 warnings in 284.84s (0:04:44)
```

### 新测试单跑

```bash
cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py -rs
```

```text
280 passed, 35 warnings in 5.09s
```

### 分模块计数

```text
tests/test_song_config.py          13 passed
tests/test_song_lyrics_check.py   111 passed, 2 warnings
tests/test_song_volc.py            57 passed
tests/test_song_store.py           10 passed
tests/test_song_media.py           25 passed
tests/test_song_jobs.py            24 passed
tests/test_song_routes.py          12 passed
tests/test_song_agent_tools.py     13 passed
tests/test_song_frontend.py        15 passed
tests/test_claude_agent_docs.py    13 passed
```

### 前端

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

```text
✖ 25 problems (0 errors, 25 warnings)
（tsc 无输出，退出码 0）
（next build 退出码 0，✓ Compiled successfully / Finished TypeScript / Generating static pages 17/17）
```

### 手工端到端复核（假供应商 + 本地 ffmpeg + MockTransport）

```text
snapshot 200 True
generate 202 queued
after submit submitted task-e2e
after poll succeeded <32hex>.mp3 6.0
audio 206 audio/mpeg b'ID'
probe duration 6.000000 produce id <32hex> match True
```

## ⑤ 未完成或需人工确认的地方

1. **「长」多音字测试的规格取舍**：实测 pypinyin 0.55.0 `Style.FINALS, strict=True` 下「长江」为 `['ang','iang']`、「长大」为 `['ang','a']`；「长」字本身两处韵母都是 `ang`，因此无法写出「同一个字得到不同韵母」的必然断言。测试改为断言两行整句 pinyin 结果不同、并按整行上下文取最后一个汉字的韵脚分组；另用「快乐 / 音乐」（乐 `e` vs `ve`）证明整句上下文确实改变韵母判定。详见 `tests/test_song_lyrics_check.py`。
2. **镜子模式**：写歌提示词和工具只在进入 Claude 智能体循环后追加；镜子模式在循环前分流，不追加写歌提示词、不下发写歌工具。若产品要求镜子轮也带写歌提示词，需要再确认。
3. **`failure_code` 内部码**：`recover_on_startup` 把 `submitting → uncertain` 记为 `recovered_submitting`；前端按 `uncertain` 状态显示「结果不确定，已退回草莓」，不直接展示内部码。
4. **清理队列的根外/符号链接条目**：`drain_cleanup_queue` 拒绝删除并保留队列条目待人工检查，不会自动丢弃；这是按「拒绝越界」的保守处理。
5. **`cleanup_orphans` 数据库不可用时**：保守地不删任何 mp3，只清理超过 1 小时的 `.part` / `.part.mp3` 临时文件，避免误删。
6. **Captions**：按 P0 原样存 `captions_raw`，未解析；备份脚本尚未包含 `FIONA_SONG_DIR`（P2），部署手册已明确。
7. **白名单外文档**：`docs/CYBER_AVATAR_PLATFORM.md` 仍写旧的「八项每日上限」、`messages` 字段和工具概览；`docs/tasks/2026-10-10-claude-agent/*`、`2026-10-16-studio-wo3b-sources/*` 等历史任务记录仍写「五种客户端工具」。这些不在 §9 白名单内，未改，建议人工确认是否作为历史快照保留。
8. **前端 lint 既有 warning**：25 条均为改动前既有问题（未使用变量、`<img>` 等），本次未新增 error；未做无关清理。
9. **本机代理环境**：pytest 需去掉 `NO_PROXY`/`no_proxy` 才能收集；这是本机环境变量与 httpx 的兼容问题，不影响门禁环境，也未改代码规避。

## R1 返修

R1 派出 5 个 agent，按文件不重叠并行；第一波 A/C/D/E，第二波 B 依赖 A 已修改 `test_song_agent_tools.py` 后再执行。

| R1 agent | 负责文件 | 结果 |
|---|---|---|
| A 安全规则末尾修复 | `backend/services/claude_agent.py`、`backend/tests/test_song_agent_tools.py` | 完成；3 个新增布局测试 + 更新旧断言；A 完成时 `test_song_agent_tools.py` 16 passed（B 完成后 20 passed） |
| C 媒体回读证明测试 | `backend/tests/test_song_media.py` | 完成；3 个新增 `_probe_output` 测试；28 passed |
| D rejected 文案 | `frontend/components/SongProjectCard.tsx`、`backend/tests/test_song_frontend.py` | 完成；rejected 独立文案；16 passed，lint/tsc 通过 |
| E 文档提示位置修正 | `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、`docs/DEPLOYMENT.md` | 完成；旧「system 末尾追加」短语 0 处 |
| B 简报重检与只改一段证明测试 | `backend/song/tools.py`、`backend/tests/test_song_agent_tools.py`、`backend/tests/test_song_routes.py` | 完成；2 个简报重检测试 + 2 个 `song_revise_section` 参数化测试 + 1 个路由测试；变异验证通过 |

### 1. 安全规则必须仍在末尾

- `claude_agent.py` 不再在 `_final_system_prompt` 返回值后追加写歌提示；改为先算 `base_prompt`，写歌开启时把 `"\n\n" + SONG_MODE_PROMPT` 拼进 `_final_system_prompt` 的第一个入参，再赋值 `state.sys_prompt_final`。删除原来的末尾追加代码块。
- 写歌关闭时 `base_prompt` 表达式与原先一致，system 文本逐字节不变；镜子模式也按规格统一走该行。
- 新增测试：
  - `test_song_mode_prompt_stays_before_trailing_safety_rules`：无 trailing system，断言写歌提示 1 次、安全规则 1 次且在最后一条 system 末尾、写歌提示在安全规则前。
  - `test_song_mode_prompt_stays_before_trailing_system_safety`：`ctx.messages` 末尾带 trailing system 时同样断言。
  - `test_layout_check_rejects_song_prompt_appended_after_safety`：正控，先构造「最终提示 + 写歌提示」的旧错误拼法，`pytest.raises(AssertionError)` 确认布局 helper 会失败；再跑真实实现确认通过。
  - 更新原有 `test_switch_on_changes_tools_prompt_and_user_message` 中「system 以写歌提示结尾」的旧断言。
- 运行：`tests/test_song_agent_tools.py` 最终 20 passed；`tests/test_beta_safety.py` 259 passed；两者合并 279 passed。

### 2. 更新简报时对已有歌词重检

- `song/tools.py` 新增 `_recheck_lyrics_after_brief`：`song_save_brief` 更新项目成功后，若 `lyrics_revision > 0`，取最新稿 sections，按更新后的 structure 与 language 调 `check_lyrics`，以最新稿 revision 为 base、`changed_section_ids=[]` 调 `store.save_lyrics` 另存新稿；返回文本附「已按新结构重检第 N 稿」和自检摘要。无歌词项目不进入该分支，行为不变。
- 旧 sections 原样传入，不按新结构裁剪；结构 id 对不上时由 `check_lyrics` 产出 `structure_mismatch`，新稿 `ok=false`。
- 新增测试：
  - `test_save_brief_rechecks_existing_lyrics_on_structure_change`：删除 s1 只留 chorus，断言第 2 稿、`ok=false`、含 `structure_mismatch`、第 1 稿深比较不变。
  - `test_save_brief_language_change_rechecks_lyrics`：English 2 段 × 12 行 × 30 字母，初始 `ok=true` 且 `provider_chars < 2000`；仅改语言为 Chinese 后新稿 `ok=false`、含 `too_long`（provider_text > 700）。
  - `test_brief_update_rechecks_lyrics_and_blocks_generation`（`test_song_routes.py`）：快照 `lyrics_revision=2`、`check.ok=false`、`can_generate=false`，`POST /generate` 带 `lyrics_revision=2` 返回 409「歌词有未解决的问题」且不建版本。
- 变异验证：临时禁用重检分支时上述两个工具测试失败；恢复后确认源码无残留。

### 3. 「只改这一段」证明力测试

- 新增参数化 `test_revise_section_preserves_every_other_section[s2]` 与 `[s4]`：结构 4 段（s1 verse、s2 chorus、s3 inst、s4 verse），分别修改中间唱段 s2 和最后唱段 s4；断言新稿稿号 2、`changed_section_ids == [目标段]`、目标段 lines 等于新行且 type 保留、除目标段外每一段 `lines` 完整列表与基础稿逐项相等（含器乐段空列表）、基础稿第 1 稿回读深比较不变。
- 变异验证：临时在 `_revise_section` 注入 `sections[0]["lines"] = list(lines)`，两个参数用例均失败（s1 被顺带改掉），证明测试能杀死门禁变异；恢复后与备份逐字节一致。

### 4. 回读标识核对证明力测试

- `test_song_media.py` 新增 `_write_sine_mp3` helper 与三个用例：
  - `test_probe_output_rejects_foreign_produce_id`：AIGC 存在但 ProduceID 是 `other-id`，先证明标签可回读，再断言 `_probe_output(path, 期望id)` 抛 `MediaError(code="invalid_audio")`。
  - `test_probe_output_rejects_missing_aigc_tag`：无 AIGC 标签，断言 `invalid_audio`。
  - `test_probe_output_accepts_matching_produce_id`：正确 id 返回 float 且 > 5。
- 变异验证：删除 `or aigc.get("ProduceID") != version_id` 后，第一个用例会正常返回时长、`pytest.raises` 失败；保留时 28 个媒体测试全过、0 skipped。

### 5. rejected 文案

- `SongProjectCard.tsx` 的 `versionStatusText` 将 `rejected` 拆为独立 case，返回「提交被拒，已退回草莓」；`failed` 仍返回「失败」。`SongVersionRow` 的 `failed` 布尔改为只判断 `version.status === "failed"`，rejected 不再显示 failure_message。
- `test_song_frontend.py` 新增 `test_rejected_version_copy_is_separate_from_failed`，检查独立 case、旧共用 case 不存在、failure_message 仍只随 failed 展示。前端 `test_song_frontend.py` 16 passed。

### 文档修正

- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、`docs/DEPLOYMENT.md` 中「在 system 末尾追加写歌模式提示词」全部改为「拼进 `_final_system_prompt` 的入参；基础安全规则仍在最后一条 system 消息末尾且恰好出现一次」。旧短语 grep 命中 0 处。

### R1 测试结果

```bash
cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py -rs
# 292 passed, 35 warnings in 4.63s

cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider -rs
# 7522 passed, 35 warnings in 281.42s (0:04:41)

cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_safety.py tests/test_song_agent_tools.py
# 279 passed, 35 warnings in 2.74s

cd frontend && npm run lint && npx tsc --noEmit && npm run build
# lint: ✖ 25 problems (0 errors, 25 warnings)，退出码 0
# tsc: 无输出，退出码 0
# build: 退出码 0
```

全量 7522 = 基线 7230 + 新增 292，0 failed、0 skipped。既有测试仍零改动；未提交、未 stash、未切分支。

## R2 返修

R2 派出 3 个 agent，按文件不重叠并行：J（`song/jobs.py`、`main.py`、`test_song_jobs.py`）、K（`services/claude_agent.py`、`test_song_agent_tools.py`）、L（`CLAUDE.md`、`docs/ARCHITECTURE.md`）。

### 1. 退款对账

- `song/jobs.py` 新增 `reconcile_refunds() -> int`：只查 `status IN ('failed','rejected','uncertain','expired')`、`billing_state='reserved'`、且 `users` 中仍存在的版本，逐个调用现有 `refund_version()`，返回实际退回数。`succeeded` 与 queued/submitting/submitted/running/downloading 不碰。单版本退款异常打印固定 `[song] code=reconcile_failed` 后继续；查询异常也不外抛。
- `main.py` lifespan 在 `recover_on_startup()` 之后调用一次 `reconcile_refunds()`；`run_poller` 每 60 秒在 `drain_cleanup_queue()` 之后调用，两项各自 try/except，互不影响。
- 新增测试：`test_reconcile_refunds_terminal_reserved_once`（4 条终态各退 30，余额 0→120，再调 0）、`test_reconcile_refunds_ignores_non_terminal_and_succeeded`（succeeded/running/downloading 保持 reserved）、`test_reconcile_refunds_skips_missing_user`、`test_reconcile_refunds_after_rejected_refund_failure`（模拟提交被拒后首次退款抛异常，对账补退）、`test_lifespan_reconcile_refunds_after_recover`（真实 lifespan，预置 uncertain+reserved 已被退回）。现有 `test_lifespan_song_wiring_only_when_enabled` 的调用顺序同步为 drain→orphans→recover→reconcile。

### 2. 镜子轮不加写歌提示

- `claude_agent.py` 的拼接条件改为 `_song_turn_enabled(ctx, state) and mode != "mirror"`。镜子轮 `state.sys_prompt_final` 与写歌关闭时逐字节相同，且不打开 agent、不带工具。
- 新增测试：`test_mirror_turn_does_not_add_song_mode_prompt`（同一 harness 开/关写歌，镜子 system 逐字节相等且不含【写歌模式】）、`test_friend_turn_with_song_on_contains_mode_prompt_once`（正控，friend 轮 system 恰好一次 SONG_MODE_PROMPT）。

### 3. 轮询单版本兜底

- `poll_once` 对每个版本外层兜底：`provider.query` 的非 `PollError` 异常、`get_provider()` 异常、其他单版本非预期异常都打印固定 `[song] code=poll_unexpected`、尝试 `next_poll_at=now+10` 并继续；`_due_versions` 查询本身也加了兜底，整轮不向外抛；不打印异常正文。
- `_handle_succeeded` 对 `media.download_and_store` 的非 `MediaError` 异常标 `failed`、`failure_code='download_unexpected'`、使用 `GENERIC_FAILURE_MESSAGE` 并退款；`MediaError` 原行为不变。
- 新增测试：`test_poll_unexpected_query_error_postpones_and_continues`（A 抛 RuntimeError、B 正常 running；A 状态不变且 next_poll_at=now+10，B progress 更新，stdout 不含 boom）、`test_poll_download_unexpected_marks_failed_and_refunds`（版本 failed、failure_code=download_unexpected、余额退回、billing_state=refunded，二次退款 False）。

### R2 文档

- `CLAUDE.md`、`docs/ARCHITECTURE.md` 补充退款对账、轮询单版本兜底、镜子轮不拼写歌提示、`download_unexpected` 与 60 秒调用点。

### R2 测试结果

```bash
cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py -rs
# 301 passed, 35 warnings in 4.79s

cd backend && env -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider -rs
# 7531 passed, 35 warnings in 279.82s (0:04:39)
```

分文件：`test_song_jobs.py` 31 passed，`test_song_agent_tools.py` 22 passed。全量 7531 = 基线 7230 + 新增 301，0 failed、0 skipped；既有测试仍零改动；未提交、未 stash、未切分支。按 R2 要求本轮未跑前端构建。
