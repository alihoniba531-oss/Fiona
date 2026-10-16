# 小说工坊 P0 独立复核

复核日期：2026-10-15。复核对象：工作树 `.worktrees/fiona-novel-p0`，分支 `novel-workshop-p0`，基线 129b32a，实施方新增的 `backend/novel/**`、`backend/tests/test_novel_*.py`。需求依据只有 `02-spec.md`；`03-report.md` 仅作参考。全程未运行真实提供方、未读取密钥、未联网；所有临时文件都在 scratchpad 的 `review-*` 目录下。

## 结论：不通过

离线部分做得扎实：223 个新用例全绿，三条关键测试经变异验证确实会变红，全量回归无新增失败，白名单、密钥、环境守卫、输出目录越界都符合规格。**不通过的原因全部集中在「dry-run 全绿但真跑会出问题」**，其中三条会直接让真跑白花钱或让实验 A 的结论不可信：

1. **anthropic 调用没有关闭 thinking。** `claude-sonnet-5-5` 与 `claude-haiku-5-5` 在省略 `thinking` 参数时默认开启 adaptive thinking，思考 token 计入 `max_tokens`。主编裁决只有 4000、反转设计师只有 2000，JSON 极可能被截断；截断后修正重试仍会截断，最终以 `step_failed`/`decision_invalid` 退出。规格 §2 明确要求「anthropic 不开启 thinking」，实际没有落实。
2. **每次调用把圣经和罗盘发两遍，写手还收到了两组不同的 `decision`。** 推演会的每条消息同时带 `bible`、`compass` 和已经包含它们的 `brief`；写手收到 `beat_sheet` 三份外加整个 `decision`（panel 组多出三条反对意见回应，solo 组没有），违反 §4.4 的上下文包定义和 §6.3「两组条件完全相同」。前者让最大的那块输入翻倍，后者给实验 A 开了一条不对称的信息通道。
3. **实验 C 的 corrupter 校验超出规格且过严。** 规格只要求锚点唯一，实施方额外要求 `contradicts` 逐字包含圣经里某条完整事实的原文（整句 location/condition/timeline）。用真实模型常见的部分引用实测会被拒绝，一次修正后仍失败就 `step_failed`，整个实验 C 白跑。

下文附逐条核验、证据、修法和可直接转交的清单。

## 复核方法

- 读完规格与全部新文件（含 6 份测试）；对照 dry-run 产物 `scratchpad/novel-p0/{A,B,C}` 里的步骤文件分析真实发出的消息体。
- `PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_novel_*.py` → `223 passed`。
- 全量回归（排除本就因沙箱禁止绑定 127.0.0.1 端口而失败的 `test_exchange_isolation.py`、`test_safe_http_deadline.py` 两个文件，共 15 条）：`3692 passed, 3 skipped, 15 deselected`，无新增失败。这两个文件的基线由验收方另测。
- **变异测试**（把 `backend/novel` 复制到 scratchpad 改坏后跑同一套测试，仓库文件未动）：
  - m1 去掉 `validate_decision` 里「end 须 n≥m」守卫 → `test_early_end_retries_and_reports_exit_code[True/False]` 2 条变红。注意 `test_novel_schemas.py::test_decision_end_guards_and_fields[early_end]` 没有变红（它同时触发了 major 伏笔守卫，不能单独隔离这条规则）。
  - m2 让 `_reserve` 永不抛 `BudgetExhausted` → `test_budget_stops_before_call_then_relaxes_without_config_change[0/1]`、`test_novel_router_budget_prevents_call_and_can_resume` 3 条变红；另外 `test_novel_router_parallel_budget_reservations_are_atomic` 在该变异下**挂起而不是失败**（第二次调用不再被拒，进入 fake 后永远等 `release`）。
  - m3 让步骤缓存永不命中 → 续跑/缓存相关 5 条变红（`test_interrupted_resume_preserves_completed_calls_and_final_artifacts`、`test_novel_router_cache_avoids_calls_and_duplicate_usage`、`test_novel_router_resume_after_failure_reuses_completed_steps` 及两条预算用例）。
- **离线捕获真实请求体**：用 `httpx2.MockTransport`（anthropic 1.12.1 基于 httpx2）/`httpx.MockTransport`（openai 2.37.0）替换客户端传输层，跑 `_single_real_call`，看它实际发出的 JSON：anthropic 请求体只有 `model/max_tokens/system/messages`，没有 `thinking`，也没有 `output_config`；dashscope 带 `response_format={"type":"json_object"}` 和 `enable_thinking=false`；deepseek 带 `thinking={"type":"disabled"}`，markdown 输出时不带 `response_format`；`timeout=300`、`max_retries=0`、显式 `base_url` 均生效；usage 归一化对真实 SDK 响应对象正确（含 `cache_read_input_tokens`、`prompt_tokens_details.cached_tokens`、`prompt_cache_hit_tokens`）。
- 用真实 SDK 异常类逐个过 `is_retryable`：超时类、429、5xx（含 529）重试；`openai/anthropic.APIConnectionError`、`httpx.ConnectError`、`RemoteProtocolError` **不重试**；401/400 不重试。
- 环境守卫与缺密钥信息实跑（在构造任何客户端之前即退出，无网络）：`ANTHROPIC_BASE_URL=http://x … run` → `配置或环境错误：请先 unset 这些变量：ANTHROPIC_BASE_URL`，退出码 2，未创建输出目录；全部密钥 unset → `缺少环境变量：ANTHROPIC_API_KEY、DASHSCOPE_API_KEY、DEEPSEEK_API_KEY`，退出码 2，不含任何值。
- 模型事实依据：Anthropic 官方型号表（claude-api 参考）确认 `claude-sonnet-5-5`、`claude-haiku-5-5` 为真实型号；两者省略 `thinking` 即运行 adaptive thinking；Sonnet 5.5 关闭思考须发 `thinking={"type":"between_tools"}`（`disabled` 返回 400），Haiku 5.5 在 effort≤high 时接受 `thinking={"type":"disabled"}`；连续两条 user 消息会被合并为一轮，不报错；非默认 temperature 在 Sonnet 5.5 上返回 400（实施方未传，正确）。

## 规格逐条核验

证据栏的「文件:行号」以本次读取的行号为准。

| 条款 | 判定 | 证据 |
|---|---|---|
| §1 白名单，不改已有文件 | 符合 | `git status --porcelain` 只有 `??` 新文件，无 `M`；新增文件全在白名单内，未扩展白名单 |
| §2 Python 3.14 / `$PY` / 不新增依赖 / JSON 配置 | 符合 | 只用标准库 + openai/anthropic；配置为 JSON |
| §2 asyncio + 同阶段 `Semaphore(3)` | 符合 | deliberation.py:63,68；`test_concurrency_is_limited_to_three` |
| §2 测试不联网；有把两个构造函数换成抛异常再跑 dry-run 的测试 | 符合 | test_novel_pilot.py:19-31 autouse 禁网+禁构造；:56-83 三实验 dry-run；test_novel_router.py:173-186 |
| §2 密钥只从三个变量读、只查用到的提供方、不打印不落盘 | 符合 | llm_router.py:16-20,47-61,109,113；`_save_step` 不写异常文案（:224,251）；test_novel_pilot.py:180-195 哨兵测试；实跑缺密钥只报变量名 |
| §2 环境污染守卫（4 个变量，退出 2，dry-run 不受限） | 符合 | llm_router.py:21-22,52-57；pilot.py:215；实跑退出 2；test_novel_pilot.py:198-202 |
| §2 客户端显式 base_url/api_key，dashscope `enable_thinking:false`，deepseek `thinking disabled`，timeout=300，max_retries=0 | 符合 | llm_router.py:107-114,124-126；MockTransport 捕获的请求体证实 |
| §2 anthropic「不开启 thinking」 | **不符合** | llm_router.py:120-121 未传 `thinking`/`output_config`；Sonnet 5.5、Haiku 5.5 默认 adaptive thinking，思考 token 计入 `max_tokens`。见必须修复 M1 |
| §2 openai 兼容传 `response_format json_object`；anthropic 靠提示词，解析去围栏取最外层 `{}`；写手输出 Markdown | 符合 | llm_router.py:127-128；schemas.py:44-68；test_novel_schemas.py:63-75 |
| §2 统一重试函数：超时/429/5xx 等 5 秒重试 1 次；解析/校验失败追加中文错误清单修正 1 次；仍失败 step_failed 并保留已完成步骤 | 部分符合 | llm_router.py:200-251 结构正确、`retry_delay=5`、错误清单不含原始响应（:243-248）；但修正消息前没有把模型上一轮输出作为 assistant 消息放回（:247），模型是「盲改」；连接类异常不重试（见可优化 O1）；截断（`finish_reason=length`/`stop_reason=max_tokens`）未识别，修正提示会误导（M4） |
| §2 每个系统提示末尾加防注入句 | 符合 | agent_pool.py:10,68-71；`test_every_role_has_complete_guarded_card` |
| §2 标准输出只打印进度行 | 符合 | `grep -rn "print("`：llm_router.py:177 进度行；pilot.py:229,235,241,246,271,276 为估算表/状态/错误，不含提示词、正文 |
| §3 ID 一律代码分配 | 符合 | bible.py:22-33,44-46,71-87；deliberation.py:84,107；pilot.py:92 |
| §3.1 setup 校验（结局 2–3、主线 1–4、main≤上限、总数≤12、appearance≥20、禁用词≥5） | 符合 | schemas.py:182-201；test_novel_schemas.py:91-103。注意 `age` 必须是字符串（:155-156），真实模型常给整数（见 M6） |
| §3.1 compass / bible v1 结构 | 符合 | bible.py:17-52；test_novel_state.py:38-53 |
| §3.2 提案校验 | 符合 | schemas.py:207-220 |
| §3.3 互评只发他人提案；恰好评分一次；1–5 整数；objection 引用有效 | 符合 | deliberation.py:87-96；schemas.py:223-243；均值汇总 :110-117 |
| §3.4 裁决校验全部条款；失败回交 1 次，再失败 `decision_invalid` | 符合 | schemas.py:260-314；deliberation.py:122-130 `failure_status="decision_invalid"`；test_novel_pilot.py:86-136 |
| §3.5 审校：证据去空白子串且≥6 字，否则 `dropped_issues`；style/adaptation 非阻断；结论由代码算 | 符合 | schemas.py:317-342；test_novel_schemas.py:212-228 |
| §3.6 档案员校验 + bible 增量 + 标记 | 符合 | schemas.py:345-387；bible.py:55-91；writing.py:96-99；test_novel_state.py:56-101 |
| §4.1 模式与阶段纯函数 + 单测 | 符合 | context.py:16-40（整数算 ceil(0.85M)）；test_novel_state.py:12-35 |
| §4.2 简报内容；closing/final 写明回收指令 | 符合 | context.py:43-64；test_novel_state.py:104-121 |
| §4.3 推演会模式 / 独自构思模式，同一输出结构 | 符合 | deliberation.py:38-132；`test_solo_skips_proposals_and_reviews` |
| §4.4 写手上下文包 | **部分符合** | context.py:67-87 的包本身正确；但 writing.py:62-70 另外塞入了 `beat_sheet`（重复）和整个 `decision`（超出规格、两组不对称）。见 M2 |
| §4.4 首行格式、长度 0.6–1.6 倍、重写 1 次后接受并打 `length_out_of_range` | 符合 | writing.py:18-25,60-72,90-91；test_novel_workflow.py:273-287,344-353。首行要求逐字相等（:23-24），真实模型多一个空格/全角冒号/代码围栏都会被判失败（M6） |
| §4.4 写手系统提示要点（8 条） | 符合 | agent_pool.py:89-93 |
| §4.5 审校循环最多修订 2 轮；仍阻断打 `review_unresolved`；无审校则跳过 | 符合 | writing.py:73-86；test_novel_workflow.py:263-305 |
| §4.6 档案员输入与完结记录 | 符合 | writing.py:92-100；pilot.py:143-145 完结指标写入 manifest |
| §4.7 用户留言只下发一次、编号 N*、主编必须回应 | 符合 | pilot.py:91-92；schemas.py:246-257,271；B 的 manifest 显示第 4 章 N1 已回应 |
| §5 智能体卡片字段、11 个角色、max_tokens 表 | 符合 | agent_pool.py:68-109；`test_role_token_limits_do_not_mutate_registry` |
| §5 提示词三点说明 + 互评对重复桥段扣 appeal | 符合 | agent_pool.py:24-33 |
| §5 必选角色缺失退出 2 | 符合 | agent_pool.py:119-121；pilot.py:243-247；test_novel_pilot.py:206-210 |
| §6.1 三份配置内容 | 符合 | 逐字段核对 expA/B/C.json 与规格一致 |
| §6.2 CLI 参数、`--dry-run` 估算表（含调用次数与口径）、`--max-total-tokens` 预判不发出超限调用、`--prices` 无内置价格、退出码 0/2/3/4 | 符合 | pilot.py:250-278；report.py:32-48,98-109；llm_router.py:132-136,154-157；变异 m2 证明预算测试有效 |
| §6.3 实验 A（一次 setup 共用、两组各 5 章、盲读文件只含正文、SystemRandom key、阅读说明四维度） | **部分符合** | pilot.py:120-129；report.py:112-125；A 产物甲乙各 5 章、不含「推演会」字样、key 为 SystemRandom。但「除推演会的组成外两组条件完全相同」被写手收到的 `decision` 打破（M2） |
| §6.3 实验 B（全部推演智能体、end 或 final 强制完结、报告指标） | 符合 | pilot.py:132-145；report.py:157-162；B 报告 `完结章号：9` |
| §6.3 实验 C 第 1–2 步（读 panel 第 4 章最终稿与章前圣经；corrupter 恰好 3 条；锚点恰好出现一次否则重试 1 次；插入生成污染稿） | **部分符合** | pilot.py:162-195；schemas.py:393,412-415 锚点校验正确；但 :416-426 额外要求 `contradicts` 逐字包含整条圣经事实并覆盖三类，规格未要求且真实模型容易失败（M3） |
| §6.3 实验 C 第 3–5 步（两次审校、8 字公共连续子串判定、单测三种情况、报告抓到数与误报数） | 符合 | pilot.py:148-151,197-204；report.py:163-165；test_novel_pilot.py:213-220 |
| §7 目录结构、步骤文件字段、临时文件改名原子写 | 符合 | run_store.py:66-84；步骤文件含 step_key/model/messages/raw_response/result/usage/attempts/duration_ms/status |
| §7 续跑：ok 步骤直接读；从第一个未完成步骤接着跑；usage 不重复 | 符合 | llm_router.py:186-192；变异 m3 证明测试有效；test_novel_pilot.py:160-177 逐字节比对 |
| §7 配置哈希不一致退出 2；只改预算不算变化 | 符合 | run_store.py:22-27,41-47；test_novel_store.py:32-47 |
| §7 usage.jsonl 字段；openai/anthropic 缓存 token 读取 | 符合 | llm_router.py:68-81,162-176；test_novel_router.py:212-218 |
| §7 cost.md 两张表、有价格加金额列；report.md 内容 | 符合 | report.py:63-95,128-171；A/B/C 的 report.md、cost.md 已核对 |
| §8.1 实验 A dry-run | 符合 | test_novel_pilot.py:56-70 |
| §8.2 实验 B 第 9 章 end | 符合 | :71-75 |
| §8.3 完结守卫（第 5 章 end 被拒、重裁合法继续、两次非法退出 4） | 符合，且变异验证有效 | :86-104；m1 变红 |
| §8.4 final 模式 | 符合 | :107-123 |
| §8.5 open major 伏笔守卫 | 符合 | :126-136；test_novel_schemas.py:186-194 |
| §8.6 模式/阶段表 | 符合 | test_novel_state.py:12-29 |
| §8.7 互评隔离/漏评/重复/越界 | 符合 | test_novel_workflow.py:145-152；test_novel_schemas.py:125-141 |
| §8.8 反对意见/留言漏回应 | 符合 | test_novel_schemas.py:197-201 |
| §8.9 审校四条 | 符合 | test_novel_schemas.py:212-228；test_novel_workflow.py:290-305 |
| §8.10 档案员四条 | 符合 | test_novel_state.py:56-87；test_novel_schemas.py:231-257 |
| §8.11 写手长度与首行 | 符合 | test_novel_workflow.py:273-287,344-347 |
| §8.12 JSON 提取与两次失败 | 符合 | test_novel_schemas.py:63-75；test_novel_router.py:47-69 |
| §8.13 中断续跑逐字节相同 | 符合，变异验证有效 | test_novel_pilot.py:160-177；m3 变红 |
| §8.14 哈希变化拒绝、只改预算允许 | 符合 | :152-157,139-149 |
| §8.15 预算不发出超限调用（fake 计数为 0）、放宽后续跑 | 符合，变异验证有效 | :139-149；m2 变红 |
| §8.16 实验 C 四条 | 符合 | :76-80,213-226；test_novel_schemas.py:260-272 |
| §8.17 环境守卫 / 缺密钥只报变量名 | 符合 | :198-202；test_novel_router.py:189-201 |
| §8.18 不联网三实验 | 符合 | :19-31,56-83 |
| §8.19 哨兵密钥不落盘 | 符合 | :180-195 |
| §8.20 必选缺失退出 2 | 符合 | :206-210 |
| §8 禁改已有测试与夹具 | 符合 | `git status` 无 `M` |
| §9.1 新测试全过且≥40 | 符合 | 223 passed |
| §9.2 全量通过且不超基线 | 符合（有条件） | 排除两个沙箱绑端口文件后 3692 passed、0 failed；这两个文件的基线由验收方核对 |
| §9.3 A dry-run 退出 0、产物齐全、各 5 章、打印估算表 | 符合 | 验收方产物核对：甲乙各 5 章；estimate.md 存在 |
| §9.4 B 完结章号 8–12 | 符合 | `完结章号：9` |
| §9.5 C 两个审校模型抓到数/误报数 | 符合 | C report.md 表格 |
| §9.6 守卫退出 2 无网络 | 符合 | 实跑退出 2，在构造客户端之前 |
| §9.7 git status 只有白名单新文件 | 符合 | 已核 |
| §9.8 print 只打印进度/估算/错误 | 符合 | 已人工核对 7 处 |

## 必须修复项

### M1 anthropic 没有关闭 thinking，`max_tokens` 会被思考吃掉

- 位置：`backend/novel/llm_router.py:117-123`。
- 问题：请求体只有 `model/max_tokens/system/messages`。`claude-sonnet-5-5`（主编）和 `claude-haiku-5-5`（反转设计师）省略 `thinking` 时默认 adaptive thinking，思考 token 计费并占用 `max_tokens`。裁决上限 4000、提案 2000、setup 8000 都是按「不思考」定的；真实裁决 JSON（细纲 + 3 条反对意见回应 + 理由）本身就要 1500–3000 token，再加思考几乎必然截断。截断的 JSON 解析失败 → 修正重试同样截断 → `decision_invalid` 退出 4。实验 A/B 每章都要过主编，等于每章都可能在这里停。
- 为什么重要：直接让真跑白花钱；且规格 §2 明文「不开启 thinking」。
- 修法（二选一，推荐 a）：
  a. 按型号关思考：`claude-sonnet-5-5` 传 `thinking={"type": "between_tools"}`；`claude-haiku-5-5` 传 `thinking={"type": "disabled"}`（两者都只在 effort ≤ high 下合法，默认即可）。在 llm_router 里加一张型号→thinking 参数的小表，未知型号默认不传并在日志里记一行。
  b. 若不想按型号分支：对所有 anthropic 调用传 `output_config={"effort": "low"}` 把思考压到最少，并把 anthropic 角色的 `max_tokens` 再留 1500 的余量。
  无论哪种，都要配合 M4 的截断识别。真跑前先用 haiku 发一次最小请求（几分钱）确认参数被接受，再开整轮。

### M2 输入重复发送；写手收到两组不同的 `decision`

- 位置：`backend/novel/deliberation.py:60-67`；`backend/novel/writing.py:47-58,62-70,75-78,92-95`。
- 问题（以 B 第 9 章步骤文件实测）：
  - 推演会每条消息同时带 `bible`（1601 字）、`compass`（426 字）和 `brief`（2228 字）；`brief.locked == bible.locked`、`brief.compass == compass`，等于圣经和罗盘各发两遍。fake 的圣经只有 1 个人物；真实圣经 6–12 个人物加逐章累积的摘要/时间线/伏笔，到第 9 章约 8–12K 字，重复部分在 B 里每章 9 次调用 × 2 组实验，浪费数十万 token。
  - 写手 payload：`context` 内已有 `beat_sheet` 和 `compass`，外层又放了 `beat_sheet` 和整个 `decision`（含 `rationale`、`merge_note`、`objection_responses`）。`beat_sheet` 发了三份；`decision` 不在 §4.4 的上下文包里。实测 solo 组的 `decision.objection_responses` 为 0 条、panel 组为 3 条——panel 的写手多拿到了推演会的内容，违反 §6.3「除推演会的组成外两组条件完全相同」，盲读结果会把「写手多拿了信息」误读成「推演会更好」。
  - 审校 payload：`context`（含与审校无关的 1500 字 `previous_tail`、重复的 `compass`/`beat_sheet`/`chapter_summaries`）+ `bible` + `compass` + `beat_sheet` + `body`。
  - 档案员 payload：`decision` 里又包了一份 `beat_sheet`，`rationale` 等与归档无关。
- 为什么重要：实验 A 的核心结论不可信；最大的输入块翻倍。
- 修法：
  - 推演会 `base` 只保留 `chapter/arm/task/mode/brief`，去掉顶层 `bible`、`compass`（brief 已含）。fake 的 `default_response` 用 `_find` 取 `bible`，改为从 `brief.locked/dynamic` 取。
  - 写手 payload = `task/chapter/title/target_words/context/previous_draft/blocking_issues/revision/write_attempt/length_instruction`，删除 `decision` 和外层 `beat_sheet`。
  - 审校 payload = `task/chapter/body/beat_sheet/bible/review_round`（与实验 C 的审校输入对齐，可加 `compass`），删除 `context`。
  - 档案员 payload = `task/chapter/body/beat_sheet/bible`，删除 `decision`。
  - 对应更新 `test_writer_receives_scoped_complete_context_without_full_bible`，断言写手 payload **不含** `decision`，并新增一条断言：A 的 solo/panel 两组写手 payload 去掉 `context.beat_sheet` 内容差异后键集合与结构完全相同。

### M3 实验 C 的 corrupter 校验超出规格且过严

- 位置：`backend/novel/schemas.py:396-406,416-426`；调用处 `pilot.py:191`。
- 问题：规格 §6.3 对代码只要求「每个 after_anchor 在正文中恰好出现一次」。实施方另加：`contradicts` 必须**逐字包含**圣经中某条完整事实（整条 `appearance`/`location`/`condition`/`timeline` 条目/伏笔描述），且三条分别落在三组。用 A 第 4 章章前圣经实测：逐字整句引用才通过；「圣经写明林澈右手完好，没有外伤」这种把事实嵌进句子的写法通过，但「时间线记录第3章核对并保存了记录」（少一个「。」）就被拒；「林澈的外形是黑色短发」只命中人名而不命中外形。真实圣经的 timeline 条目是长句，qwen 作为 corrupter 很难整句照抄；一次修正后仍失败即 `step_failed`，实验 C 整体退出 4。另外 `name`、`age`、`personality` 也算「锁定事实」，使第一组几乎总能命中，三类覆盖检查并不真的在检查三类。
- 为什么重要：会让实验 C 白跑；且这是规格外的硬失败。
- 修法：锚点唯一性保留为硬校验；引文与三类覆盖改为**记录而非拒绝**——把匹配结果写进 `control/insertions.json` 的 `citation_check` 字段并在报告里列出，由人工抽查。若坚持要自动核验，改用与 `evidence_matches` 同口径的「≥8 字公共连续子串」，并把 `name/age/personality` 从事实集合中去掉。

### M4 不识别截断与拒答，修正提示会误导模型

- 位置：`backend/novel/llm_router.py:120-130,226-251`。
- 问题：anthropic 的 `stop_reason`（`max_tokens`/`refusal`）、openai 兼容的 `finish_reason`（`length`/`content_filter`）都没有读取。被截断的 JSON 只会得到「JSON 解析或字段校验失败」的修正消息，模型会再次输出同样长度再次截断；Sonnet 5.5 的安全分类器拒答时 HTTP 200 但正文为空，同样被当成 JSON 错误重试。这与 M1 叠加时每一步都可能多烧一次满额调用。
- 修法：`_single_real_call` 返回第三项 `stop_reason`；`_attempt` 把它写进 usage 行和步骤文件；`_with_retries` 在 `stop_reason in ("max_tokens","length")` 时把修正消息改成「输出被截断，请压缩各字段文字长度后重新完整输出」；在 `refusal`/`content_filter` 时直接以 `step_failed` 结束并把原因写入步骤文件的 `errors`（只写枚举值，不写响应文本）。

### M5 修正重试没有把上一轮输出放回对话

- 位置：`backend/novel/llm_router.py:247-248`。
- 问题：校验失败后只追加一条 user 消息「校验错误 + 请重新输出」，消息序列是 `system, user, user`。模型看不到自己上一轮写了什么，只能凭错误清单重做一遍，「修正」退化成「重来」；对「恰好回应 O1、O2、O3」「P2 评了两次」这类错误，看不到原稿的模型未必能改对。规格说错误清单不含原始响应全文，并没有禁止把原始响应作为 assistant 轮放回。
- 修法：追加前先 `request["messages"].append({"role": "assistant", "content": raw})`，再追加修正 user 消息。三家 API 都接受这个结构。更新 `test_novel_router_repairs_json_once_and_keeps_chinese_errors` 断言 `messages[-2]["role"] == "assistant"`。

### M6 对真实模型常见的无害偏差判失败

- 位置：`schemas.py:155-156`（age）、`:268`（merge_note）、`:213-214`（risks/closing_reason）、`:235`（comment）、`:288-289`（closing_chapters_left）、`:364`（knows 的 value）、`writing.py:22-24`（首行）。
- 问题：`"age": 26`（整数）、可选字符串为 `null`、`continue` 时 `closing_chapters_left` 为 `null`、`knows` 给成字符串列表、写手首行多一个空格 / 用全角冒号 / 外层套了 ```markdown 围栏，都会触发一次修正重试（一次满额调用），重复出现就 `step_failed`。这些都不是规格要约束的语义错误。
- 修法：在各 validator 开头做一次只读的规范化副本：`age` 整数转字符串；规格示例里为 `""` 的可选字段 `null` 视为空串；`closing_chapters_left` 在 `ending_status != "closing"` 时允许缺失/`null`，按 0 处理；`knows` 的 `value` 允许字符串列表，按多条追加。写手输出先剥掉外层代码围栏，取第一个非空行，若匹配 `^#+\s*第\s*{n}\s*章[\s:：]*{title}\s*$` 就由代码替换成规范首行，否则才算校验失败（标题和章号本来就是代码已知的）。补对应单测。

## 可优化项

- O1 `is_retryable`（llm_router.py:84-89）不重试 `openai/anthropic.APIConnectionError`、`httpx.ConnectError`、`RemoteProtocolError`。本机走代理访问 DashScope 的 p90 延迟 5–6 秒、Anthropic 需要代理，连接层抖动很可能出现。建议把 SDK 的 `APIConnectionError` 纳入「网络超时」同一类重试一次。
- O2 主编系统提示同时含 setup 与裁决两套 schema（agent_pool.py:75-76），每次裁决多发约 900 字且在裁决时混入「不写死大纲」等 setup 指令；按 task 拆成两张提示。
- O3 步骤失败只记「模型调用失败」（llm_router.py:224），manifest 不记失败的 step_key，stdout 只打印状态。建议记录异常类名与 HTTP 状态码（不含消息文本），manifest 增加 `failed_step`，stdout 打印它，方便真跑排障。
- O4 并行阶段一个调用失败时兄弟任务被取消（deliberation.py:17-27），取消的调用也会在 `usage.jsonl` 记一行 `attempts=1`，成本表的「调用次数」会把它算进去；真实提供方对已取消的请求也可能照常计费。建议 usage 行加 `cancelled` 标记并在 cost.md 单列。
- O5 `test_novel_router_parallel_budget_reservations_are_atomic` 在预算逻辑回归时会挂起而不是失败；第二次 `router.call` 外包一层 `asyncio.wait_for(..., 5)`。
- O6 `test_decision_end_guards_and_fields[early_end]` 同时触发 major 伏笔守卫，不能单独证明「n<m 不得 end」；该用例补 `foreshadowing_resolve=["F001"]`。
- O7 审校证据匹配只去空白（schemas.py:24-26），真实模型常把 “ ” 写成 " "、…… 写成 ...，证据会被整条丢弃，实验 C 的「抓到数」因此偏低。若作者同意微调规格，可在 `compact` 里同时归一全半角引号、省略号、逗号句号后再比对（证据与正文同一函数）。
- O8 `generate_blind` 用 key.json 里的标签拼文件名（report.py:122-124），标签不经过 `RunStore._path` 的越界检查；改为固定「版本甲/版本乙」两个常量，只从 key.json 读映射值。
- O9 估算表按「1 字符 = 1 token」是规格口径，但 Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界会偏低；在估算口径说明里加一句提醒。
- O10 `FakeLLM` 的 B 实验「第 9 章 end」硬编码在 `default_response`（fake_llm.py:157），改用脚本注入更清楚；不影响结论。

## 对角色系统提示词的评估（针对 P0 目的）

P0 要回答的是「多智能体推演是否明显好于主编独自构思」。两组共用同一个主编（Sonnet 5.5）和同一个写手（DeepSeek），这一点设计正确。但现有提示词会让两组差异被其他因素淹没：

1. **用户的基调要求在 setup 之后就丢了。** `seed_idea` 只在 setup 的 payload 里出现一次（pilot.py:96），「节奏快，每章都有新发现」能否进入罗盘完全取决于主编是否把它写进 `style_guide.voice`。之后所有推演、写手调用都看不到原始思路。建议 `build_setup` 把 `config["seed_idea"]` 原样放进 `compass["seed_idea"]`（约 150 字，每次调用成本可忽略），写手提示加一句「每章必须有一个读者能说出来的新发现」。
2. **solo 组的主编是一个弱基线。** 推演智能体的提示里有「不重复 used_beats」「推进主线」「收尾服务回收」三条，主编提示里只有后两条的变体，没有「不重复 used_beats」，也没有任何构思章节的判断标准；panel 组的主编却能从均分和反对意见里间接得到五个维度。这样比出来的差异一部分来自「主编独自构思时没有被告知怎么评价一个章节」。建议把五个维度（logic/character/appeal/compass_fit/filmability）和 used_beats 禁重复写进主编的裁决提示，两组同一张提示；不要给主编扮演多角色的指令，那会把 panel 的机制偷运进 solo。
3. **提案缺乏具体性要求。** 角色提示每个只有一句话（agent_pool.py:77-88），`direction` 没有字数和内容要求。真实模型给薄提示通常产出「主角继续调查并发现新线索」这类抽象走向，主编最终还是自己填细纲——推演会的影响被稀释。建议 PROPOSAL_SCHEMA 要求 `direction` 80–200 字、必须写明本章新发现是什么、谁做了什么选择、与上一章的因果连接、章末钩子具体是什么；`conflict` 要写明对立双方和争的是什么。
4. **各角色提示可以展开成 3–5 行的检查清单，否则视角差异不显著：** 情节架构师（因果链、信息差、每个伏笔的回收时点）；人物代言人（逐个出场人物核对动机与已知信息，拒绝为剧情让人物降智）；反转设计师（先写出读者最可能预期的走向，再提反向走向并说明为何仍合理）；节奏与完结顾问（按 n/M 和主线完成度明确给出该收该放，并说明 `suggest_closing` 的触发条件）；短剧改编顾问（场景数、每场人数、对白比例、是否有可拍的动作）。
5. **写手提示缺三条会直接影响盲读质量的指引：** 从 `previous_tail` 自然接续、不复述前情；按 `beat_sheet.scenes` 顺序写、每个 beat 都要在正文里可见；不在正文里解释设定（圣经是给写手看的，不是给读者看的）。
6. **审校（尤其实验 C）：** 提示里应给出核对顺序——锁定人物外形与设定 → 人物当前位置/伤病 → 时间线与伏笔——并要求 `problem` 里引用圣经原文，这样正控才能检验它是否真的对照了圣经。
7. **档案员：** 要求 `timeline_add` 每条以「第 n 章」开头，`knows` 记成「谁知道了什么」，否则时间线很快不可追溯。
8. **无法在 P0 消除但要在报告里写明的混杂因素：** 三个推演角色分别用 qwen/deepseek/haiku，panel 的表现同时是模型组合的函数；panel 模式下主编被迫至少选一条提案，不能完全按自己的想法来。

## 安全核验

- 密钥：只从三个环境变量读（llm_router.py:109,113），不打印、不写文件；异常文案统一为固定中文（:224,251）；哨兵测试覆盖 stdout 与输出目录全文件。
- 环境守卫：4 个变量在构造客户端之前检查，实跑退出 2；dry-run 与 fake 完全不读环境（test_novel_router.py:204-209）。
- 输出目录：`RunStore._path` 拒绝绝对路径、`..`、以及通过已存在符号链接逃逸（run_store.py:56-64；test_novel_store.py:17-29）。`report.py` 直接用 `Path(out)` 写固定文件名，路径不受模型输出影响（O8 的标签除外）。
- 步骤文件记录完整提示与模型输出，不含密钥；`seed_idea` 与正文落盘属预期。

## 给实施方的修改指令

按顺序做，每项都要有对应测试，仍然不得改任何已有文件（新增测试放 `tests/test_novel_*.py`）：

1. **M1** `llm_router.py`：按型号加 thinking 参数表（`claude-sonnet-5-5`→`{"type":"between_tools"}`，`claude-haiku-5-5`→`{"type":"disabled"}`）；用 MockTransport（anthropic 用 `httpx2.MockTransport`）写一条离线测试断言请求体里有 `thinking` 字段。
2. **M4** 读取并记录 `stop_reason`/`finish_reason` 到 usage 行与步骤文件；截断时修正提示改为「输出被截断…」；`refusal`/`content_filter` 直接 step_failed 并记录枚举值。测试：fake 返回 `(raw, usage, "max_tokens")` 三元组时修正消息含「截断」。
3. **M5** 修正重试前把 `raw` 作为 assistant 消息放回；更新 router 测试断言消息角色序列为 `system,user,assistant,user`。
4. **M2** 去重：推演会 payload 只带 `brief`；写手只带 §4.4 的包（删 `decision` 与外层 `beat_sheet`）；审校删 `context`；档案员删 `decision`。更新 fake 的取数路径。新增测试：A 的 solo/panel 写手 payload 结构相同且都不含 `decision`；推演会 payload 不含顶层 `bible`。
5. **M3** `validate_insertions` 只硬校验锚点唯一与 3 条；引文/三类覆盖改为写入 `control/insertions.json` 的 `citation_check` 与报告，不再抛错；若保留自动核验，改用 ≥8 字公共子串并剔除 name/age/personality。更新 `test_insertions_quote_real_bible_facts_and_cover_three_categories` 为「记录而非拒绝」。
6. **M6** 规范化：age 整数转串、可选字段 null→""、非 closing 时 `closing_chapters_left` 可缺省、knows 允许列表、写手首行由代码按正则归一并剥代码围栏。每条一个参数化用例。
7. **O1** 把 `APIConnectionError` 纳入重试；**O3** 记录异常类名与状态码、manifest 写 `failed_step`；**O5** 并发预算测试加 `wait_for`；**O6** 隔离 early_end 用例。
8. **提示词**：把 `seed_idea` 放进 compass；主编裁决提示加入五维度与 used_beats 禁重复（两组同一张）；PROPOSAL_SCHEMA 加 direction 具体性要求；各角色展开为检查清单；写手加接续/按场景写/不解释设定三条；审校加核对顺序；档案员加 timeline 前缀。提示词改动不需要新测试，但 `test_every_role_has_complete_guarded_card` 必须仍然通过。
9. 全部改完后重跑：`tests/test_novel_*.py` 全绿；三个 dry-run 退出 0；用 `grep -rn "thinking" novel/llm_router.py` 能看到型号表；把新的估算表贴进 03-report.md。
10. 真跑前的最小验证（由作者授权后执行，不在本单内）：用 `anthropic:claude-haiku-5-5` 发一次 `max_tokens=200` 的 setup 请求，确认 `thinking` 参数被接受且 `stop_reason` 能读到，再开实验 A。
