# 小说工坊 P0 第 2 轮返修单（真跑首轮暴露的问题）

> 来源：2026-10-15 作者批准后首次用真实模型运行，实验 B 在第 1 章以 step_failed 停下，实验 A 已被验收方中止。首轮产物归档在 `/Users/yangjing/Desktop/ai-workspace/outputs/novel-p0-2026-10-15/aborted-run1/`，**可以只读查看，不要修改**。
> 红线与 05-fix-r1 相同：
> - 只改 `backend/novel/**`、`backend/tests/test_novel_*.py`、`03-report.md`。
> - 不改任何既有文件。
> - 不联网，不读密钥，不运行真实提供方，不提交 commit。
> - 既有测试的输入和断言不改，本单明确允许的除外。

## 真跑中观察到的现象（证据都在 aborted-run1 的步骤文件里）

1. **JSON 字符串被英文双引号提前截断**。见 `expB/arm-panel/ch001/05-review-reviewer-r2.json`：qwen3.8-max 在 json_object 模式下，想在 `problem` 字段里引用带英文双引号的原文，结果字符串在引号处被截断，后面只剩空白和 `}]}`，留下一个只有 category 和 problem 的残缺 issue。修正重试时它犯了同样的错误，于是整个实验以 step_failed 退出。
2. **审校的阻断误报很多，造成空转**。同一章三轮审校给出的阻断问题包括：
   - 「正文写林夏二十四岁，与圣经 age 冲突」，但圣经里写的就是 24；
   - 「小痣」与「小泪痣」这样的措辞差异；
   - 「沈栀不该知道周铭远」，这是对 knows 字段的过度解读。

   结果写手每章都被迫修订 2 轮。
3. **写手长度一贯超标**。实验 B 目标 1500 字（允许 900–2400 字），DeepSeek 五次输出分别是 2251、2509、2554、2555、2382 字，几乎每一轮都触发一次长度重写。原因是写手只拿到「target_words 的 0.6–1.6 倍」这种相对描述，没有具体数字。

## 必须修复

### R2-1 禁止在 JSON 字符串里使用英文双引号（agent_pool.py、llm_router.py）

- 在所有 JSON 输出角色的 schema 提示末尾统一加一句：「JSON 字符串值内部不得出现英文双引号 "；需要引用原文、人物台词或圣经内容时，一律使用中文直角引号「」。」覆盖 setup、提案/互评、裁决、审校、档案员、corrupter，写成一个常量在各处复用。
- 校验失败时，修正消息里追加同一条提醒。

### R2-2 审校中残缺的 issue 只丢弃，不让整步失败（schemas.py）

- `validate_review` 的处理规则：
  - 顶层结构不合法时仍按失败处理，包括 `issues` 不是列表、不是对象等情况。
  - 单条 issue 缺字段或字段类型不对时，把它放进 `dropped_issues`，`drop_reason` 写「字段不完整或类型错误」，**不抛错**。
- 这与「证据对不上就丢弃」采用同一口径：无法核实的问题不能拿来阻断章节。
- 同一条规则只用于审校，不扩展到其他角色。
- 补测试：输入 aborted-run1 中那种残缺 issue（只有 category 和 problem），结果应为不抛错、被丢弃、该轮通过。

### R2-3 收紧审校的阻断标准，复审只盯上一轮的问题（agent_pool.py、writing.py）

审校提示词新增以下规则：

- 只有三类问题可以判为阻断（blocking=true）：
  1. 读者会明显察觉的前后矛盾，例如人物在两处同时出现，或已经死去的人又出现；
  2. 与锁定设定直接冲突，例如外形或身份被写成另一个样子；
  3. 漏掉了细纲中 `foreshadowing_plant`、`foreshadowing_resolve` 所要求的伏笔，或者漏掉了细纲的核心节拍。
- 同义表述、数字的中文写法与阿拉伯数字写法、措辞的详略差异，**都不算矛盾**。
- 对 knows 等动态状态，只有正文明确写出某人知道了他不可能知道的事，才算矛盾。
- 拿不准时一律 blocking=false。
- 每轮最多 3 条阻断问题，按严重程度排序。

writing.py 的复审流程：

- 第 1 轮及以后（`review_round >= 1`），审校的 payload 增加 `previous_blocking_issues`，内容是上一轮保留下来的阻断问题。
- 提示词写明：复审时先逐条判断上一轮的阻断问题是否已经解决；新发现的问题只有属于上面三类中的严重情况，才可以判为阻断，否则 blocking=false。
- 实验 C 的审校调用不传 `previous_blocking_issues`，保持单轮审校。

补测试：

- 复审 payload 中含有上一轮的阻断问题；首轮 payload 中没有。
- 实验 C 的审校 payload 中没有这个字段。

### R2-4 写手拿到具体的字数范围（writing.py、agent_pool.py）

- 写手 payload 增加 `length_range: {"min": ceil(0.6×W), "max": floor(1.6×W), "target": W}`，W 为本章目标字数。
- 提示词改成具体数字：「正文（不计空白）目标 {target} 字，必须在 {min}–{max} 字之间；宁可略短，不要超过上限。」
- 长度重写时的提示 `length_instruction` 也要带上「上一稿 X 字，超出（或不足）范围 {min}–{max}」，其中 X 由代码计算。
- 对应更新 `test_writer_receives_scoped_complete_context_without_full_bible` 和 R1 中写手 payload 键集合的那条测试：只允许在期望的键集合里**新增 `length_range`**，其他断言不变。

## 验收（全部由验收方复跑）

1. `tests/test_novel_*.py` 全部通过，测试数不少于 518 条加上本单新增的测试数。
2. 全量测试不出现新增失败。
3. 三个 dry-run 都以退出码 0 结束；`git status --porcelain` 中没有 `M` 状态的文件。
4. 在 03-report.md 末尾追加「第 2 轮返修（真跑问题）」一节。
