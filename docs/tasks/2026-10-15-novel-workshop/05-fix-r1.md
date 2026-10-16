# 小说工坊 P0 第 1 轮返修单

> 依据：`04-review.md`（独立复核，结论为不通过），以及验收方核实过的事实。
> 本单是对 `02-spec.md` 的增量。两者冲突时以本单为准，没有提到的条款继续按 `02-spec.md` 执行。
> 红线不变：
> - 只能新增或修改 `backend/novel/**`、`backend/tests/test_novel_*.py` 和 `docs/tasks/2026-10-15-novel-workshop/03-report.md`，不得修改任何既有文件。
> - 不运行真实提供方，不读取密钥，不联网，不提交 commit。
> - 不得修改已有测试的输入和断言来让测试通过。只有本单明确要求更新的测试才能改，并且只能按本单写明的方向改。

## 已核实的事实（验收方查自 Anthropic 官方 API 参考）

- `claude-sonnet-5-5`：
  - 不传 `thinking` 时默认运行 adaptive thinking，思考消耗的 token 计入 `max_tokens`。
  - `thinking={"type":"disabled"}` 会返回 400。
  - 关闭思考的唯一写法是 `thinking={"type":"between_tools"}`。该字段不能再带任何其他字段，并且只在 effort 为 high 或更低时合法（默认 effort 是 high，因此**不要传 `output_config`**）。
- `claude-haiku-5-5`：
  - 默认同样开启 adaptive thinking。
  - `thinking={"type":"disabled"}` 在 effort 为 high 或更低时合法（默认 effort 是 medium，不要传 `output_config`）。
- 两个模型都可能返回 HTTP 200，但 `stop_reason="refusal"`，此时 `content` 可能为空。超出长度时 `stop_reason="max_tokens"`。
- 连续两条 user 消息会被 API 合并成一轮，不会报错。

## 必须修复

### R1-1 关闭 Claude 思考（llm_router.py）

- 增加型号到 thinking 参数的映射表：`claude-sonnet-5-5` → `{"type": "between_tools"}`，`claude-haiku-5-5` → `{"type": "disabled"}`，`claude-opus-5-5` → 不传（这个型号无法关闭思考；启动时打印一行提示「opus-5-5 无法关闭思考，输出 token 会显著增加」）。
- 型号不在表中时报 ConfigurationError，退出码 2，提示「未知的 Claude 型号，无法确定如何关闭思考」。不要静默照常发出请求。
- 新增离线测试：给 anthropic 1.12.1 的 AsyncAnthropic 传 `http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))`；如果 1.12.1 的写法不同，以实测为准，但只能用 MockTransport，不得联网。然后断言：sonnet 的请求体里 `thinking == {"type":"between_tools"}`，且没有 `output_config`；haiku 的请求体里是 `{"type":"disabled"}`。

### R1-2 识别截断和拒答（llm_router.py）

- `_single_real_call` 额外返回 `stop_reason`：
  - anthropic 取 `response.stop_reason`。
  - openai 兼容提供方取 `choices[0].finish_reason`，其中 `length` 视为 `max_tokens`，`content_filter` 视为 `refusal`。
- fake 提供方可以返回三元组来模拟这两种情况。
- 把 `stop_reason` 写进 usage 行和步骤文件。
- 处理规则：
  - 截断（`max_tokens`）：修正消息改为「上一次输出因长度上限被截断。请压缩各字段文字，重新输出完整、合法的结果。」截断占用的是修正重试的那 1 次机会。
  - 拒答（`refusal`）：不重试，直接以 step_failed 结束。步骤文件的 errors 只写 `refusal`，不写响应文本。
- 测试覆盖：截断时修正消息包含「截断」；拒答时 fake 调用次数为 1 并且 step_failed。

### R1-3 修正重试时回放上一轮输出（llm_router.py）

- 追加修正用的 user 消息之前，先追加 `{"role":"assistant","content": raw}`。如果 raw 为空（拒答已在 R1-2 处理掉，这里只剩空输出这一种情况），追加占位文本「（上一轮输出为空）」。
- 更新 `test_novel_router_repairs_json_once_and_keeps_chinese_errors`：断言第二次请求的消息角色序列是 `system, user, assistant, user`。这是本单唯一允许修改断言的既有测试，并且只能新增这一条断言，原有断言保留。

### R1-4 去掉重复输入，两组写手拿到的信息必须一致（deliberation.py、writing.py、fake_llm.py）

- **推演会**：每次调用的 payload 只保留 `task, chapter, mode, brief` 和该阶段特有的字段（互评用 `proposals` 和 `proposal_ids`；裁决用 `proposals, scores, objections, proposal_ids, objection_ids, user_notes, note_ids, solo`）。删除顶层的 `bible`、`compass`、`arm`，`arm` 只保留在步骤键里。
- **写手**：payload 只包含 `task, chapter, title, target_words, context, previous_draft, blocking_issues, revision, write_attempt, length_instruction`。删除外层的 `beat_sheet` 和 `decision`，细纲已经在 `context.beat_sheet` 里。
- **审校**：payload 只包含 `task, chapter, body, beat_sheet, bible, review_round`，与实验 C 的审校输入保持一致。删除 `context` 和 `compass`。
- **档案员**：payload 只包含 `task, chapter, body, beat_sheet, bible`。删除 `decision`。
- fake_llm 取数时改从新的位置读取，例如推演会从 `brief.locked` 和 `brief.dynamic` 取。
- 新增测试：
  - 实验 A 的 dry-run 结束后，读取 solo 组和 panel 组各自第 1–5 章的写手步骤文件。两组 user 消息 JSON 的**键集合**完全相同，并且都不含 `decision`。
  - 推演会各阶段的 payload 都不含顶层的 `bible` 和 `compass`。

### R1-5 实验 C 的 corrupter 只对锚点做硬校验（schemas.py、pilot.py、report.py）

- `validate_insertions` 只硬性检查两点：插入恰好 3 条；每个锚点在正文中恰好出现一次，且三个锚点互不相同。
- 原来对引文和三类覆盖的检查改成**只记录、不拒绝**：
  - 每条插入计算 `citation_check`，记录它与哪一类事实（锁定外形或设定、当前位置或伤病、时间线或伏笔）有至少 8 个字的公共连续子串。事实集合中去掉 `name`、`age`、`personality`。
  - 结果写进 `control/insertions.json`，并在报告里列一张表。
- 更新 `test_insertions_quote_real_bible_facts_and_cover_three_categories`：只能改成「不合格的引文不抛错，但会被记录」，其余用例不变。

### R1-6 真实模型的常见无害偏差不判为失败（schemas.py、writing.py）

各 validator 先生成一份**规范化副本**，再做校验；校验通过后返回这份规范化副本，原始输入不改：

- 人物的 `age` 是整数时转成字符串。
- 示例里值为 `""` 的可选字符串字段（`merge_note, risks, closing_reason, comment, fix, note, deviation_from_beat_sheet.note` 等）如果是 `null`，按空串处理。
- `ending_status != "closing"` 时，`closing_chapters_left` 允许缺失或为 `null`，按 0 处理。
- 档案员 `knows` 的 `value` 允许是字符串列表，逐条追加（`bible.apply_archive` 同步支持）。
- 写手正文：
  1. 先去掉外层的 ```markdown 或 ``` 代码围栏。
  2. 再看第一个非空行：如果匹配 `^#{1,3}\s*第\s*{n}\s*章[\s:：]*(.*)$`，由代码把它替换成规范首行 `# 第{n}章 {title}`。标题以细纲为准。
  3. 第一个非空行不是章节标题时，在正文前插入规范首行。
  4. 只有正文为空时才算校验失败。

每一条都要有参数化用例。

### R1-7 加强角色提示词（agent_pool.py、bible.py；只改提示词，不新增任何硬校验）

1. **思路原文**：`build_setup` 把 `config["seed_idea"]` 原样写入 `compass["seed_idea"]`。之后所有推演、写手、审校调用都能通过罗盘看到用户的原始思路。
2. **主编提示词按 task 拆成两张**（setup 一张，decision 一张），由 `get_agent(role, task=...)` 返回对应那张。setup 提示保留「不写死大纲」。decision 提示加入下面三点，**solo 和 panel 两组用同一张 decision 提示**，不要给主编扮演多个角色的指令：
   - 判断本章走向时，要考虑逻辑、人物、吸引力、与罗盘的契合度、可拍性这五个维度。
   - 不重复 `used_beats` 里已经用过的桥段。
   - 每章必须有一个读者能说得出来的新发现。
3. **PROPOSAL_SCHEMA 的具体性要求**（只写在提示词里，不加校验）：
   - `direction` 写 80–200 字，必须写明：本章新发现是什么、谁做了什么选择、与上一章的因果关系、章末钩子具体是什么。
   - `conflict` 要写明对立双方，以及他们争的是什么。
4. **五个推演角色各展开成 3–5 行检查清单**：
   - 情节架构师：因果链、信息差、每个伏笔预计在什么时候回收。
   - 人物代言人：逐个核对出场人物的动机和已知信息，拒绝为了推动剧情让人物降智。
   - 反转设计师：先写出读者最可能预期的走向，再提出反向走向，并说明为什么仍然合理。
   - 节奏与完结顾问：按 n/M 和主线完成度明确说该收还是该放，并说明 `suggest_closing` 的触发条件。
   - 读者代表、短剧改编顾问：按 `02-spec.md` §5 的视角展开。
5. **写手提示新增四条**：
   - 从 `previous_tail` 自然接续，不复述前情。
   - 按 `beat_sheet.scenes` 的顺序写，每个节拍都要在正文里看得见。
   - 不在正文里解释设定（圣经是写给写手看的，不是给读者看的）。
   - 写出具体的感官细节和动作，避免空泛的抒情和总结句。
6. **审校提示**：
   - 给出核对顺序：锁定的人物外形和设定 → 人物当前位置和伤病 → 时间线与伏笔 → 细纲是否完成。
   - `problem` 里要引用圣经原文。
7. **档案员提示**：
   - `timeline_add` 每条以「第n章：」开头。
   - `knows` 写成「谁知道了什么」的形式。

### R1-8 max_tokens 留出余量（agent_pool.py）

- 主编 setup 改为 12000，decision 改为 6000。
- 推演角色改为 2500。
- 审校和档案员改为 4000。
- 写手保持 `max(4000, chapter_words × 2.5)`。
- 同步更新与之对应的 `test_role_token_limits_do_not_mutate_registry` 期望值，这属于本单要求的方向。

## 同时修复（可优化项中验收方决定一并处理的）

- **O1**：`is_retryable` 把 `openai.APIConnectionError`、`anthropic.APIConnectionError`（包括它们的子类）和 `httpx2/httpx` 的 `ConnectError`、`RemoteProtocolError` 纳入可重试范围，等 5 秒后重试 1 次。补测试。
- **O3**：步骤失败时，步骤文件的 errors 记录异常类名和 HTTP 状态码（不含消息文本）。manifest 增加 `failed_step`（即失败的 step_key），标准输出打印这一项。
- **O5**：`test_novel_router_parallel_budget_reservations_are_atomic` 里第二次调用外面包一层 `asyncio.wait_for(..., 5)`，让回归时测试失败，而不是挂起。这一条属于本单允许修改的测试。
- **O6**：给 `test_decision_end_guards_and_fields[early_end]` 补上 `foreshadowing_resolve=["F001"]`，让它只验证「n<m 时不得 end」这一条规则。这一条属于本单允许修改的测试。
- **O7（规格 §3.5 微调）**：`compact()` 除了去掉空白，还要把全角和半角引号（“”‘’「」『』"'）统一去掉，并把省略号（…… … ...）统一成同一个形式。证据和正文都走同一个函数。补测试。
- **O8**：`generate_blind` 的文件名固定为「版本甲.md」和「版本乙.md」，只从 key.json 里读映射值。
- **O9**：在估算表的口径说明里加一句：「Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低」。

## 验收（全部由验收方复跑）

1. `$PY -m pytest -q -p no:cacheprovider tests/test_novel_*.py` 全部通过，用例数不少于 223 加本单新增的用例数。
2. 全量 `$PY -m pytest -q -p no:cacheprovider` 不出现新增失败（基线是 3484 通过加上全部小说测试）。
3. 三个 dry-run 都以退出码 0 结束；`git status --porcelain` 中没有 `M` 状态的文件。
4. `grep -n "between_tools" backend/novel/llm_router.py` 有结果。
5. 在 03-report.md 末尾追加「第 1 轮返修」一节，逐条写出 R1-1~R1-8 和 O1/O3/O5–O9 是如何改的、对应的测试，并贴上新的估算表。
