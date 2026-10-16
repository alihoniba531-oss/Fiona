# 小说工坊 P0 第 2 轮独立复核

复核日期：2026-10-15。复核对象：工作树 `.worktrees/fiona-novel-p0`，分支 `novel-workshop-p0`，基线 129b32a；所有新增文件均为未跟踪文件，直接读文件核验。依据：`04-review.md`（M1–M6）、`05-fix-r1.md`（R1-1~R1-8、O1/O3/O5–O9）、`06-add-ark-provider.md`（任务 1–8）；`03-report.md` 仅作参考。全程未运行真实提供方、未读取或打印密钥、未联网、未用浏览器；仓库内只写了本文件。所有临时文件都在 scratchpad 的 `review2-*` 目录下。

## 结论：通过

- 第 1 轮 6 条必须修复项全部落实；返修单 R1-1~R1-8 与 O1/O3/O5–O9 全部落实。唯一例外是 R1-3 要求给旧测试 `test_novel_router_repairs_json_once_and_keeps_chinese_errors` 新增的断言 `system, user, assistant, user` 没有加——该旧测试的输入只有一条 user 消息，这条断言在不改输入的前提下不可能成立（实测第二次请求的角色序列是 `user, assistant, user`）。实施方没有偷改输入，而是新增独立测试并在报告里上报等待拍板，处理方式正确。行为本身已由新测试覆盖并经变异验证。记为「部分修复（待验收方拍板测试文本）」，不阻断。
- 豆包（火山方舟）接入 8 项任务全部核实，我用自己写的 MockTransport 脚本独立截获了真实 SDK 发出的请求体：URL、`thinking`、`response_format`、`max_tokens`、无 `frequency_penalty`/`presence_penalty`、客户端 `timeout=300`/`max_retries=0` 均符合。
- 测试纪律：既有测试只改了返修单允许的四处；第 1 轮新增的 r1 测试在豆包轮没有再动。
- 24 个关键变异全部让对应测试变红；全量回归 3987 通过，等于第 1 轮基线 3692 + 本轮新增 200 + 95，无新增失败。
- 没有发现会让真跑白花钱或让结论不可信的新问题。

## 复核方法

- 读完三份需求文件与全部 `backend/novel/**`、`backend/tests/test_novel_*.py`（12 个源文件、13 个测试文件，5298 行）。
- 与两份快照逐文件 `diff`：`snap-r0`（返修前）→ 当前，`snap-r1`（接豆包前）→ 当前，确认每处改动都对应返修单或豆包单的条款。
- `PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_novel_*.py` → `518 passed in 2.79s`（223 + 200 + 95）。
- 全量回归（排除本就因沙箱禁止绑定 127.0.0.1 端口而失败的 `test_exchange_isolation.py`、`test_safe_http_deadline.py`，密钥环境变量全部覆盖为占位值）：`3987 passed, 3 skipped, 15 deselected, 0 failed`，日志 `scratchpad/review2-full/full.log`。第 1 轮同口径为 3692，差值 295 正好等于两轮新增用例数。
- 三个 dry-run 由我复跑到 `scratchpad/review2-dry/{A,B,C}`：退出码均为 0；A 两组各 5 章、`blind/` 四个文件齐全；B 报告 `完结章号：9`；C 报告两个审校模型各抓到 3/3、原稿误报 0。`git status --porcelain` 无 `M` 状态文件；`grep -n between_tools novel/llm_router.py` 命中第 29 行。
- **独立截获真实请求体**（`scratchpad/review2-sdk/capture.py`，日志 `capture.log`）：整体替换 `os.environ` 为占位映射、封死 socket，然后 monkeypatch `openai.AsyncOpenAI` / `anthropic.AsyncAnthropic` 的构造函数记录构造参数并注入 `httpx.MockTransport` / `httpx2.MockTransport`，再走路由自己的 `_single_real_call`。这样同时验证了客户端构造参数和线上序列化的 JSON 体。
- **变异测试**（`scratchpad/review2-mut/mutate.py`，结果 `report.json`）：把 `novel/` 和测试复制到 scratchpad，先跑正控（518 通过），再逐个改坏 24 处关键修复，记录变红的用例。每个变异都先断言目标字符串在副本中恰好出现一次，防止「没改到」。
- 最新 dry-run 产物 `scratchpad/novel-p0-ark/{A,B,C}` 逐章读取步骤文件，核对两组写手载荷键集合、推演会载荷、`stop_reason` 字段、报告表格。

## M1–M6 与 R1 逐条核验

证据栏行号以本次读取的当前文件为准。

| 条款 | 判定 | 证据 |
|---|---|---|
| **M1 / R1-1** 按型号关闭 Claude 思考 | 已修复 | `llm_router.py:28-32` `CLAUDE_THINKING` 表（sonnet→between_tools，haiku→disabled，opus→None）；`:168-170` 按表写入 `thinking`，不传 `output_config`。独立截获：sonnet 请求体 `{"max_tokens":4242,"messages":[…],"model":"claude-sonnet-5-5","system":"…","thinking":{"type":"between_tools"}}`，haiku 为 `{"type":"disabled"}`，opus 无 `thinking` 键，三者均无 `output_config`、`temperature`；客户端构造参数 `base_url=https://api.anthropic.com, timeout=300, max_retries=0`。未知型号：`:84-85` 报「未知的 Claude 型号，无法确定如何关闭思考」退出 2，我的脚本实测 `anthropic:claude-9` 在构造任何客户端之前即被拒；`:86-87` opus 启动一行提示。`validate_model_settings` 在 `pilot.py:219` 先于 `validate_environment` 调用。测试：`test_novel_r1_router.py:74-97`（anthropic 1.12.1 + `DefaultAsyncHttpxClient(transport=httpx2.MockTransport)`，断言 `thinking` 与无 `output_config`）、`:100-105`、`:109-115`、`:118-120`、`test_novel_r1_pilot_report.py:139-147`。变异 mA（去掉 thinking）→ 2 条变红；mP（放过未知型号）→ 3 条变红。 |
| **M4 / R1-2** 识别截断与拒答 | 已修复 | `_single_real_call` 返回三元组：anthropic 取 `response.stop_reason`（`:173`），openai 兼容把 `length→max_tokens`、`content_filter→refusal`（`:181-183`）；fake 三元组经 `_response_parts`（`:191-211`）同样归一。`stop_reason` 写入 usage 行（`:234`）和步骤文件（`:348`）；最新产物 `usage.jsonl` 71 行均含 `stop_reason` 字段。截断：`:297-308`，修正文案「上一次输出因长度上限被截断。请压缩各字段文字，重新输出完整、合法的结果。」，与 JSON 修正共用 `validation_retries` 这 1 次机会；拒答：`:292-296` 不重试、`errors=["refusal"]`、状态固定 `step_failed`。测试：`test_novel_r1_router.py:125-138`（anthropic 空 content 仍读到 stop_reason）、`:144-167`、`:172-182`（修正消息含「截断」）、`:187-195`（共用一次）、`:200-212`（拒答 1 次调用、errors 只有枚举）。变异 mE（不识别截断）→ 4 条变红；mD（拒答也重试）→ 3 条变红；mQ（不记 stop_reason）→ 7 条变红。 |
| **M5 / R1-3** 修正前回放上一轮输出 | **部分修复**（实现已到位；旧测试断言未加，已上报） | `llm_router.py:337-341` `_append_repair` 先追加 `{"role":"assistant","content": raw or "（上一轮输出为空）"}` 再追加修正 user 消息；三条修正路径（截断 `:302`、JSON/校验 `:330`）都走它。新测试 `test_novel_r1_router.py:217-222` 断言 `["system","user","assistant","user"]` 与占位文本；变异 mC（去掉 assistant 回放）→ 6 条变红。**旧测试**：`tests/test_novel_router.py:48-58` 与 r0 快照逐字节相同，没有新增返修单指定的断言。原因属实：该测试的 `options()`（`:23-27`）只有一条 user 消息，我用同一输入实测第二次请求的角色序列为 `['user','assistant','user']`（`scratchpad/review2-r13/prove.py`），返修单写的 `system, user, assistant, user` 在「不得改输入」的前提下不可能通过。实施方在 03-report「本轮状态与红线」一节如实上报并等待拍板，没有偷改输入或在路由里造 system 消息。 |
| **M2 / R1-4** 去重输入、两组写手信息一致 | 已修复 | 推演会 `deliberation.py:60` `base = {"chapter","brief","mode"}`，顶层无 `bible`/`compass`/`arm`；互评只加 `proposals, proposal_ids`（`:93-95`）；裁决只加 `proposals, scores, objections, proposal_ids, objection_ids, user_notes, note_ids, solo`（`:121-125`）。写手 `writing.py:77-85` 精确 10 键，无 `decision` 与外层 `beat_sheet`；审校 `:90-93` 为 `task, chapter, body, beat_sheet, bible, review_round`；档案员 `:107-110` 为 `task, chapter, body, beat_sheet, bible`。fake 从 `brief.locked/dynamic` 取数（`fake_llm.py:118-121`）。最新产物实测：A 第 1–5 章 solo/panel 写手载荷键集合完全相同（且 `context` 子键也相同），都不含 `decision`；panel 第 3 章 7 个推演步骤文件顶层键均只有 `brief/chapter/mode/task` + 阶段字段。测试：`test_novel_r1_workflow.py:77-87`、`:90-108`、`:117-134`；`test_novel_r1_pilot_report.py:54-65`、`:68-89`。变异 mF（写手塞回 decision）→ 3 条变红；mG（推演会塞回 bible/compass）→ 4 条变红。设计取舍见可优化项 O-D。 |
| **M3 / R1-5** corrupter 只硬校验锚点 | 已修复 | `schemas.py:425-464`：硬校验只剩恰好 3 条（`:429`）、锚点在正文恰好出现一次（`:449-451`）、三个锚点互不相同（`:452-455`）；`contradicts` 允许为空（`:447`）。`citation_check` 用归一后 ≥8 字公共连续子串按三类记录（`:456-463`），事实集合已剔除 `name/age/personality`（`:434-435` 只取 appearance、motivation + world_rules）。写进 `control/insertions.json`（`pilot.py:199`，结果来自校验返回的规范化副本，含 `citation_check`）；报告列表 `report.py:172-173`。最新 C 产物：三条插入分别命中「锁定外形或设定 / 当前位置或伤病 / 时间线或伏笔」，报告有「插入引文核对记录」表。测试：`test_novel_r1_schemas.py:177-198`、`:208-252`；`test_novel_r1_pilot_report.py:91-114`（引文全是「待人工核对」仍退出 0 并记录）。变异 mH（未命中即拒绝）→ 32 条变红；mY（去掉锚点互异）→ 1 条变红。 |
| **M6 / R1-6** 无害偏差规范化 | 已修复 | `schemas.py:36-50` `_normalized_copy`：`age` 整数转字符串；`_OPTIONAL_TEXT_FIELDS`（`:29-33`）中的 `null` 转空串；各 validator 开头都先取副本（`:197,233,250,290,349,378,426`），原输入不改。`closing_chapters_left` 非 closing 时缺失/`null` 按 0（`:291-293`）。`knows` 允许字符串列表（`:396-397`），`bible.py:65` 逐条 `extend`。写手：`writing.py:28-44` `normalize_manuscript` 去 ```markdown/``` 围栏、首个非空行匹配 `^#{1,3}\s*第\s*{n}\s*章[\s:：]*(.*)$` 则替换为规范首行、否则插入规范首行，只有空正文失败；流水线 `:85` 使用它。参数化用例：`test_novel_r1_schemas.py:34-51`（age 0/25/120 × setup/new_character）、`:67-116`（15 个 null 字段）、`:121-132`（缺失/null × continue/end）、`:150-158`（knows 单条/列表/空）；`test_novel_r1_workflow.py:165-186`（10 种标题/围栏变体 + 5 种空输入）、`:190-209`（流水线）。变异 mK/mL/mV/mW 各自变红（6/6/2/4 条）。 |
| **R1-7** 提示词 | 已修复 | ① `bible.py:25` `compass["seed_idea"]` 原样写入；最新产物中写手 `context.compass.seed_idea`、推演 `brief.compass.seed_idea`、审校 `bible.compass.seed_idea` 都能看到原文。② 主编按 task 拆两张：setup 卡在 `agent_pool.py:144-146` 单独构造（保留「不写死大纲」，`:24`），decision 卡 `:84-85`；decision 提示新增五维度、`used_beats` 不重复、每章一个新发现（`:45-46`）。solo/panel 用同一张：`deliberation.py:30-35,121` 只按 `task="decision"` 取卡，最新产物 solo 与 panel 第 3 章裁决的 system 消息逐字相同；没有让主编扮演多角色的指令。③ `PROPOSAL_SCHEMA :29-30` direction 80–200 字四要素、conflict 对立双方与争点。④ 六个推演角色各 4 行清单（`:86-121`），情节架构师/人物代言人/反转设计师/节奏顾问四条内容与返修单逐条对应。⑤ 写手四条 `:126-129`。⑥ 审校核对顺序与引用圣经原文 `:56-57`。⑦ 档案员 `timeline_add` 「第n章：」前缀、`knows` 写成「谁知道了什么」`:67-68`。**只改提示词、未加硬校验**：`schemas.py` 从 r0 到现在的 diff 没有任何关于 direction 字数、conflict 内容、timeline 前缀的新检查，唯一新增硬校验是 R1-5 要求的锚点互异。测试：`test_novel_r1_workflow.py:212-225`、`:228-243`、`:246-255`；`test_novel_r1_schemas.py:275-281`。变异 mX（solo 裁决提示追加一句）→ 1 条变红；mM（去掉 seed_idea）→ 9 条变红。 |
| **R1-8** max_tokens 余量 | 已修复 | setup 12000（`agent_pool.py:146`）、decision 6000（`:85`）、六个推演角色 2500（`:91-121`）、审校/档案员 4000（`:131-132`）、写手 `max(4000, ceil(words×2.5))`（`:143`）。旧测试期望值按返修单更新；新测试 `test_novel_r1_workflow.py:258-269`。变异 mN（decision 改回 4000）→ 2 条变红。 |
| **O1** 连接类异常重试 | 已修复 | `llm_router.py:110-123` 纳入两家 SDK `APIConnectionError`（含子类）与 httpx/httpx2 的 `ConnectError`、`RemoteProtocolError`，`retry_delay=5`（`:142`）。测试 `test_novel_r1_router.py:249-260` 覆盖 8 类。变异 mS → 8 条变红。 |
| **O3** 失败诊断与 failed_step | 已修复 | `_exception_metadata :126-134` 只记类名与 `HTTP <code>`；`_save_step :350-353` 写 manifest `failed_step` 并在续跑成功后清空；`run_store.py:52` 初始化；`pilot.py:244-247` stdout 打印；`report.py:138-139` 报告列出。测试 `test_novel_r1_router.py:265-302`、`test_novel_r1_pilot_report.py:127-136`。变异 mT（把异常文本也写进去）→ 4 条变红。 |
| **O5** 并发预算测试 `wait_for` | 已修复 | `tests/test_novel_router.py:150` 第二次调用外包 `asyncio.wait_for(..., 5)`，其余不变。 |
| **O6** early_end 用例隔离 | 已修复 | `tests/test_novel_schemas.py:160` 仅补 `foreshadowing_resolve=["F001"]`。 |
| **O7** `compact` 归一引号与省略号 | 已修复 | `schemas.py:23-26`：去空白与 “”‘’「」『』"'，…… / … / ... 统一为「…」；审校证据（`:353,363`）、C 抓到匹配（`pilot.py:150-153`）、citation_check 共用同一函数。测试 `test_novel_r1_schemas.py:257-271`、`test_novel_r1_pilot_report.py:175-177`。变异 mU → 28 条变红。 |
| **O8** 盲读文件名固定 | 已修复 | `report.py:122-128` 只循环「版本甲/版本乙」两个常量，映射值只允许 solo/panel。测试 `test_novel_r1_pilot_report.py:151-172`。 |
| **O9** 估算口径提醒 | 已修复 | `report.py:106` 加入「Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低」；三份 estimate.md 与 stdout 已核对。 |

## 豆包（火山方舟）接入逐条核验

| 任务 | 判定 | 证据 |
|---|---|---|
| 1 新增提供方 `ark` | 符合 | `llm_router.py:20` `PROVIDERS["ark"] = ("https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY")`。走 openai 兼容分支（`:157-160` 构造 `AsyncOpenAI(base_url, api_key, timeout=300, max_retries=0)`；`:174-178` `extra_body={"thinking":{"type":"disabled"}}`，json 时 `response_format={"type":"json_object"}`，显式 `max_tokens`）。**独立截获**（`review2-sdk/capture.log`）：`POST https://ark.cn-beijing.volces.com/api/v3/chat/completions`，json 角色请求体 `{"messages":[…],"model":"doubao-seed-2-1-pro-260915","max_tokens":4242,"response_format":{"type":"json_object"},"thinking":{"type":"disabled"}}`；markdown 角色同体但无 `response_format`；260628 同样；两者都不含 `frequency_penalty`、`presence_penalty`、`enable_thinking`、`temperature`；`Authorization` 头存在；构造参数 `base_url=https://ark.cn-beijing.volces.com/api/v3, timeout=300, max_retries=0`。`finish_reason` 归一复用 `:181-182`，截断/拒答/修正与其他提供方共用一条路径。实施方测试 `test_novel_ark_router.py:126-163`（2 型号 × json/markdown × stop/length/content_filter）、`:168-180`（空 content 仍读 finish_reason）、`:189-226`（length→一次修正且回放 assistant；content_filter→1 次即 step_failed）。变异 mB（去掉 thinking）→ 12 条变红；mO（markdown 也带 response_format）→ 6 条变红。 |
| 2 全库更新「提供方:型号」校验 | 符合 | `grep -rn` 全库：`llm_router.parse_model :53-56`、`agent_pool._validate_model :190-193`、`pilot._model_spec :69-72` 三处均加 `ark`，后两处改为同一正则并追加调用 `parse_model` 复用白名单；三处中文文案都已含 `ark`（`:54`、`agent_pool.py:192`、`pilot.py:71`）。除此之外 `novel/` 内没有其他提供方枚举（`grep "dashscope|deepseek|anthropic"` 仅命中这三处）。测试 `test_novel_ark_validation.py:64-68`（两型号 × 11 个角色）、`:72-77`（reviewers_to_compare）、`:81-83`、`:88-90`（`volc:xxx` 等报错含 ark）。 |
| 3 环境守卫 | 符合 | `validate_environment :60-74` 只按本次用到的提供方查 `PROVIDERS[provider][1]`，ark → `ARK_API_KEY`，缺失只报变量名；污染变量清单 `:26-27` 未变（4 个）。测试 `test_novel_ark_router.py:230-240`（缺 key 在构造 SDK 之前退出 2，文案恰为「缺少环境变量：ARK_API_KEY」）、`:243-254`（不读其他提供方的 key）、`:258-264`（污染变量报错不含值）、`:267-272`（dry-run 不读环境）；`test_novel_ark_security.py:179-186`（CLI 退出 2、不建目录、stderr 为空）、`:189-200`。变异 mJ（ark 的 key 名写错）→ 24 条变红。 |
| 4 型号白名单 | 符合 | `MODEL_ALLOWLISTS :22-24` 只有 `ark`，内容恰为 260915/260628；`parse_model :55-56` 白名单外报「火山方舟型号未在白名单内」退出 2。因 `parse_model` 在 `validate_model_settings` 的 `dry_run` 早退之前执行（`:79-82`），dry-run 同样拒绝；我的脚本实测 `ark:doubao-seed-2-1-pro` 在构造任何客户端前被拒。其他提供方不加白名单（`test_novel_ark_validation.py:95-96`）。测试 `test_novel_ark_router.py:106-110`、`:277-288`（未知型号不进入 call/fake、usage 为空）、`test_novel_ark_validation.py:105-124`（CLI 两种槽位 × dry-run/真实 → 退出 2、不建目录、不读环境）。变异 mI（去掉白名单）→ 14 条变红。 |
| 5 估算表计入 ark | 符合 | `report.py:98-109` 按 usage 汇总，不按提供方过滤；`test_novel_ark_security.py:84-129` 用仅测试内的 A 配置（plot_architect→ark）跑完整 dry-run，逐字段核对 estimate/cost 行，无价格时无金额列，外部价格按给定值计算，`load_prices(None) == {}` 证明无内置价格。 |
| 6 README | 符合 | `novel/README.md:28` 提供方清单含 `ark` 与 `ARK_API_KEY`；`:30-32` 写明推荐型号 260915、往期 260628、URL、`thinking` 关闭、`max_tokens`、`response_format`、不传惩罚项、白名单与退出码。 |
| 7 离线测试 | 符合 | 三个新文件共 95 项：`test_novel_ark_router.py`（`httpx.MockTransport` 截获真实 SDK 请求体，断言 URL 结尾、`thinking`、json/markdown 的 `response_format`、`max_tokens` 存在、无两项惩罚）、`test_novel_ark_validation.py`（`ark:doubao-seed-2-1-pro-260915` 通过；`ark:unknown-model`、`volc:xxx` 退出 2）、`test_novel_ark_security.py:132-158`（哨兵 `ARK_API_KEY`，单次调用函数替换成本地桩，递归扫描输出目录文件名与内容、stdout/stderr 均无哨兵）、`:84-129`（测试内配置把 plot_architect 换成 ark，dry-run 退出 0，两组各 5 章；未新增 pilot_configs 文件）。全部封死 socket、禁构造真实客户端、整体替换 `os.environ`。 |
| 8 默认配置不改 | 符合 | `expA/B/C.json` 与 r0、r1 快照逐字节相同（`diff -q` SAME）。 |
| 验收 1–6 | 符合 | 518 passed；全量 3987 passed 无新增失败；三个 dry-run 退出 0；`grep -rn '"ark"' novel/` 命中提供方表（:20）、白名单（:23）、校验（:55）；`git status --porcelain` 无 `M`；03-report 末尾有「接入火山方舟」一节。 |

## 测试纪律核对

与 `snap-r0`（返修前）逐文件 diff，既有测试文件的改动**只有**下面四处，且都在返修单允许范围内：

| 文件 | 改动 | 允许依据 |
|---|---|---|
| `tests/test_novel_router.py` | `test_novel_router_parallel_budget_reservations_are_atomic` 第二次调用外包 `asyncio.wait_for(..., 5)`（1 行） | O5 |
| `tests/test_novel_schemas.py` | `test_decision_end_guards_and_fields[early_end]` 补 `foreshadowing_resolve=["F001"]`（1 行） | O6 |
| `tests/test_novel_schemas.py` | `test_insertions_quote_real_bible_facts_and_cover_three_categories` 把 valid/invalid 分支改为「不抛错、记录 citation_check」；parametrize 输入未变 | R1-5 |
| `tests/test_novel_workflow.py` | `test_role_token_limits_do_not_mutate_registry` setup/decision 期望改 12000/6000（2 行） | R1-8 |

- `test_novel_pilot.py`、`test_novel_state.py`、`test_novel_store.py` 与 r0 逐字节相同。
- R1-3 允许加的那条断言没有加（见上表 M5/R1-3），没有借改输入让它通过。
- `snap-r1`（接豆包前）→ 当前：10 个既有测试文件逐字节相同，豆包轮只新增 3 个 `test_novel_ark_*.py`。
- 源码改动面：r0→r1 改了 12 个 `novel/` 文件（全部对应 R1/O 条款）；r1→当前只改了 `llm_router.py`、`agent_pool.py`、`pilot.py`、`README.md`（全部对应豆包任务 1、2、6）。
- 没有改动任何仓库既有文件（`git status` 无 `M`）。

## 变异验证汇总

正控副本 518 通过。24 个变异结果（`scratchpad/review2-mut/report.json`）：

| 变异 | 改坏的点 | 结果 |
|---|---|---|
| mA | anthropic 不传 `thinking` | 2 条红（sonnet/haiku 的 MockTransport 测试） |
| mB | openai 兼容分支不传 `thinking` | 12 条红（ark 序列化测试） |
| mC | 修正前不回放 assistant | 6 条红 |
| mD | 拒答也重试 | 3 条红 |
| mE | 不识别 `max_tokens` | 4 条红（`test_truncation_and_json_errors_share_one_repair` 不红属预期，它只数调用次数） |
| mF | 写手载荷塞回 `decision`/`beat_sheet` | 3 条红 |
| mG | 推演会载荷塞回 `bible`/`compass` | 4 条红 |
| mH | 引文未命中即拒绝 | 32 条红 |
| mI | 去掉 ark 白名单 | 14 条红 |
| mJ | ark 的密钥变量名写错 | 24 条红 |
| mK | 不剥代码围栏 | 6 条红 |
| mL | `age` 整数不转串 | 6 条红 |
| mM | 罗盘不带 `seed_idea` | 9 条红 |
| mN | decision 改回 4000 | 2 条红 |
| mO | markdown 也带 `response_format` | 6 条红 |
| mP | 放过未知 Claude 型号 | 3 条红 |
| mQ | usage 行不记 `stop_reason` | 7 条红 |
| mS | 连接类异常不重试 | 8 条红 |
| mT | 失败 errors 带异常文本 | 4 条红 |
| mU | `compact` 不归一引号/省略号 | 28 条红 |
| mV | `knows` 列表不逐条追加 | 2 条红 |
| mW | 非 closing 时 `closing_chapters_left` 不补 0 | 4 条红 |
| mX | solo 裁决提示多一句（两组不同） | 1 条红 |
| mY | 去掉锚点互异校验 | 1 条红 |

## 新发现的阻断问题

无。没有发现会让真跑白花钱或让实验结论不可信的新问题。

## 可优化项

- **O-A** 截断修正文案「请压缩各字段文字」对 Markdown 写手不贴切（`llm_router.py:303`）；可按 `request["output"]` 分两套措辞。不影响正确性。
- **O-B** `normalize_manuscript` 只剥 ```markdown / ``` 两种围栏（`writing.py:33-35`），模型写 ```md 时不剥，会多一次修正；可放宽为 ```[A-Za-z]*。
- **O-C** `_OPTIONAL_TEXT_FIELDS`（`schemas.py:29-33`）比返修单列举的更宽（含 `problem`、`appearance`、`location`、`condition`、`personality`、`motivation`）。目前无害（后续类型/长度检查仍在），建议在 README 的规范化说明里列出完整清单，避免以后误以为这些字段必填。
- **O-D** R1-4 要求审校载荷删除 `compass`，实施方改为放进 `bible.compass`（`context.py:90-98` `build_review_bible`，章节审校与实验 C 共用），顶层键与规格一致，且满足 R1-7 第 1 点「审校能通过罗盘看到原始思路」。两条返修要求本身有张力，实施方的取舍合理，建议验收方确认并沿用。
- **O-E** 旧测试 `test_insertions_quote_real_bible_facts_and_cover_three_categories` 改后 `valid` 参数不再参与断言（三组都断言 `matched_categories == []`，因夹具里的事实不足 8 字）；正向命中只由 `test_novel_r1_schemas.py:208-228` 覆盖。覆盖面够，只是这条旧测试名字与内容已不对应，后续可改名。
- **O-F** 真跑前最小验证清单（04-review 第 10 条）建议补一条 ark：方舟 `response_format=json_object` 要求输入含 json 字样，现有提示词写的是大写「JSON」，首次真实 ark 调用应确认被接受。
- **O-G** `_single_real_call` 每次调用都重跑 `validate_model_settings` 与 `validate_environment`（`llm_router.py:149-150`），功能无害，只是重复读环境；可在构造客户端时做一次。

## 给实施方的修改指令

本轮没有必须修复项。只有一条待验收方拍板的测试文本事项：

1. **R1-3 旧测试断言**：`tests/test_novel_router.py::test_novel_router_repairs_json_once_and_keeps_chinese_errors` 的输入只有一条 user 消息，返修单写的 `system, user, assistant, user` 无法在不改输入的前提下成立。请验收方二选一：
   - a. 接受现状：行为由 `tests/test_novel_r1_router.py::test_repair_replays_assistant_before_correction` 覆盖（已变异验证），旧测试不动；或
   - b. 授权在旧测试末尾只新增一条断言 `assert [m["role"] for m in fake.calls[1]["messages"]] == ["user", "assistant", "user"]`（输入与原有断言不变）。
   两者都不影响通过结论。

可优化项 O-A~O-G 是否处理由验收方决定，不作为本轮通过条件。
