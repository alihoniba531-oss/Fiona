# 小说工坊 P2.1 第 2 轮返修单（作者拍板，一行人名守卫）

**来源**：`04-review-r2.md` 可优化项 1，作者决定先修再提交。

**问题**：新人物的 ID 按位置顺延。场景如下：
1. 某章归档时新增人物 C3（临时证人），作者随后补改了 C3；
2. 作者再改这一章的正文，重新归档时产生了另一位新人物（老张），编号同样是 C3；
3. 重放时，原本改给临时证人的外形和动机，被叠加到了老张身上。

复核探针 `probe_v4_new_character_id_reuse.py` 在当前代码上输出 `GRAFTED ONTO UNRELATED CHARACTER`。

**改法**：只改 `backend/novel/runner.py` 中 `_rearchive` 的重放段（约 409–411 行）。按人物 ID 找到目标之后，再比较 `name`：
- 重建结果中该人物的 `name` 与 `user_edit` 版本中的 `name` 不一致，就跳过这个人物，不叠加。
- 作者不能修改人名（`CharacterEdit` 只开放外形、性格、动机），所以用人名判断可靠。
- 不做按名字回退匹配。

**测试**：在 `backend/tests/test_novel_p21_fix_r1_runner.py` 或新文件 `test_novel_p21_fix_r2_runner.py` 中新增一条用例，走真实路径（FastAPI PATCH → `service.edit_chapter` → runner，使用离线 dry_run 路由）：
1. 构造「新人物编号复用、名字不同」的场景，断言补改**没有**落到新人物身上，新人物保留重建出的原值；
2. 同时断言同名人物的补改仍然保留，避免守卫把正常情况也挡掉；
3. 反证：修复前该用例失败。在报告中写明失败输出。

**红线**：
- 既有测试和 P2.1 测试的已有断言一律不改；
- 除上述重放段外不改其他代码；
- 不使用 git stash，不提交 commit。

**验收**：
- 复核探针 `probe_v4` 不再输出 `GRAFTED`；
- `probe_rearchive.py` 仍然输出 `USER EDIT SURVIVED`；
- P2.1 全部测试和后端全量测试通过。
