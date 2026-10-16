# 小说工坊 P2.1 第 1 轮返修单

> **来源**：
> - 独立复核 `04-review.md`，结论不通过，有 1 条必须修复项（M1，数据风险），另有 7 条可优化项；
> - 验收方的截图验收。
>
> **机械门禁已通过**：
> - lint：0 个错误、25 条警告；tsc 通过；build 通过；
> - 后端全量 5223 passed；
> - 在不含 `node_modules` 的仓库副本中，新增测试 0 failed。
>
> **红线**同规格 §1、§7：
> - 既有测试一律不改，`test_novel_p21_*.py` 已有的断言只能收紧；
> - 工作室依赖的 5 个函数签名、表的列、圣经结构、状态语义都不变；
> - 不加依赖，不联网，不读密钥，不提交 commit。
>
> 本单**额外授权**修改 `backend/novel/runner.py` 中 `_rearchive` 的「圣经重建」一段。状态机、暂停原因和计费仍然不能动。

## F1【必须】立项后补改的人物字段，被「最新章重新归档」静默丢弃（复核 M1）

**问题**：`_rearchive`（`runner.py` 约 371–392 行）以本章原归档之前的版本为底重建圣经。作者在归档之后通过 `PATCH /novels/{id}/characters/{cid}` 写入的 `user_edit` 版本因此被丢弃。复核已用离线真实路径复现：

> service.create → approve_setup → update_character → edit_chapter → _rearchive

**改法**：

1. `_rearchive` 得到重建的 `next_bible` 后、写库前，按版本号升序取出所有满足以下条件的版本：

   ```
   version > original.version AND source = 'user_edit'
   ```

   将每个版本与它的前一版本比对 `locked.characters[]` 中的 `appearance`、`personality`、`motivation` 三个字段，把有变化的值按人物 `id` 依次叠加到 `next_bible`。
   - 重建结果里不存在的人物跳过。
   - 只叠加这三个字段，与 `CharacterEdit` 的白名单一致。
2. 叠加后的结果要满足以下条件：
   - 仍然通过现有校验；
   - 版本号和 `source`（`rearchive:n`）的写法不变。
3. **测试**：新增离线测试，可沿用复核探针 `probe_rearchive.py` 的路径或 `test_rearchive_repairs_short_new_appearance_before_persisting` 的骨架。
   - **主路径**：PATCH 修改人物三个字段后，改最新章正文，排空任务。断言：
     - 三个字段都保留了修改后的值；
     - 版本来源序列以 `…, user_edit, rearchive:n` 结尾；
     - 其他人物、动态区的重建结果与不 PATCH 时一致。
   - **连续修改**：连续两次 PATCH 同一人物的不同字段，两次的改动都保留。
   - **反证**：先写出这条测试，并确认它在修复前的代码上失败（可以用 git stash 之外的方法，例如临时复制旧函数）。在报告里写明失败输出。

## F2【建议，提示词只追加】复审轮的提示词没有指向例外（复核可优化 1）

`agent_pool.py:120`「新发现的问题只有属于上述三类中的严重情况，才可以判为阻断」已被测试冻结。不改原句，在它后面追加：

> 或符合前述唯一例外（payload 含 adaptation_blocking=true 时的硬约束）

如果追加后有冻结期望失败，**停下来报告**。

## F3【建议】小项

1. **PATCH 校验顺序**：先确认人物是否存在（不存在返回 404），再校验字段（不合格返回 422）。
2. **`failed` 状态的文案**：对 `failed` 状态返回「这本书已出错，不能修改人物」，不再用「正在运行」。
3. **solo 模式的说明**：推演方式为 solo 时，「这本书要改编成短剧」下面的说明改为：
   > 主编独自构思时不请顾问参会；审校仍会按「场景太多、主要人物太多」这类硬伤要求重写。
4. **人物卡草稿**：`editable` 变为 false 时，清空人物卡里未保存的草稿。
5. **无变化不保存**：比较草稿与原值时，两边都先 trim。没有实质变化时不发请求，并提示「没有改动」。
6. **导出标注的位置**：stale 章正文首行以 `# ` 开头时，标注插在首行之后；否则插在正文最前面。
7. **圣经里的原始英文键名**（截图发现）：人物当前状态中的 `last_seen_chapter` 等原始键名直接显示在界面上。
   - 已知键用中文显示，例如 `last_seen_chapter` 显示为「最近出场：第 n 章」；
   - 其余未知键不显示原始英文名：统一放进「其他」，或者直接不显示，二选一，在报告中说明选择。
   - 不改数据结构。

## 验收（验收方复跑）

1. lint：0 个错误，警告不超过 25 条；tsc 通过；build 成功。
2. 后端全量通过，基线为 5223 passed。在不含 `node_modules` 的仓库副本中，新增测试 0 failed。
3. 既有测试的 diff 为空；`test_novel_p21_*.py` 原有断言没有放宽。
4. 由验收方复跑复核探针：`/private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/8c7c9461-074c-48c4-aa9b-bbaaef19ee71/scratchpad/p21-review/probe_rearchive.py` 的输出不再出现 `USER EDIT LOST`。
5. 在 `03-report.md` 末尾追加「第 1 轮返修」一节，逐条写明 F1–F3 的改法和证据（文件:行号）。
