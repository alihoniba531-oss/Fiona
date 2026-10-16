# 小说工坊 P1 第 3 轮返修单（冒烟复测）

> **来源**：第 2 轮返修之后复测冒烟。恢复那本暂停的书后，千问作为主编在 critique 定稿（finalize）阶段再次以 `decision_invalid` 暂停。错误信息已经明确写出「缺少：A1、A2、A3」，但它两次都只回应了 O1–O9，三个替代走向（A*）一条都没回应。
>
> **原因**：替代走向的回应和反对意见混在同一个 `objection_responses` 字段里，这个字段名会让模型以为「只需要回应反对意见」。Claude 在实验 A2 中能理解这个隐含要求，千问理解不了。
>
> **红线**同前：
> - 只改 `backend/novel/**`、`backend/tests/test_novel_*.py`，并在 `03-report.md` 中补记；
> - 既有测试的输入与断言不改，本单明确允许的除外；
> - 测试不读取仓库外的文件；
> - 不联网，不读密钥，不提交 commit。

## H1 替代走向的回应单独成字段（schemas.py、deliberation.py、agent_pool.py、report.py）

1. **新字段**：critique 定稿（finalize）的输出结构新增 `alternative_responses`，格式如下：
   ```json
   [{"alternative_id": "A1", "decision": "adopt|partial|reject", "response": "理由"}]
   ```
   `decision` 必须是这三个枚举值之一，`response` 不能为空。

2. **校验规则**：
   - 每个 A* 必须恰好回应一次。回应可以写在 `alternative_responses` 里，也可以按旧格式写在 `objection_responses` 里，以兼容旧格式和 Claude 的既有行为。
   - 同一个 A* 在两个字段里都出现，按「重复」处理。
   - O* 只能在 `objection_responses` 里回应。
   - 第 2 轮返修中「列出具体缺少、多出、重复的 ID」的报错要覆盖这两个字段。
   - 所有 A* 都没有替代走向时，`alternative_responses` 允许缺失或为空列表。

3. **输入**：
   - finalize 的 payload 改为分别提供 `objection_ids` 和 `alternative_ids`。
   - 第 2 轮新增的 `required_response_ids` 保留，但只放 O* 和 N*。
   - 提示词要写明以下三点：
     - `objection_responses` 回应 O*；
     - `alternative_responses` 逐条回应 A*，并给出采纳、部分采纳或不采纳的决定；
     - `user_note_responses` 回应 N*。

4. **适用范围**：merge 和 solo 模式的 decision 不涉及 A*，结构保持不变。

5. **报告与接口**：`report.md` 和 `GET /novels/{id}/chapters/{n}` 中的推演记录，要展示 `alternative_responses`，包括每条的决定和理由。

6. **测试**：
   - 新格式（A* 写在 `alternative_responses` 里）能通过校验；
   - 旧格式（A* 写在 `objection_responses` 里）也能通过；
   - 同一个 A* 在两个字段都出现时判为重复；
   - 漏掉 A* 时，报错里列出具体是哪些 ID；
   - `decision` 不是三个枚举值之一时判为失败；
   - 反转设计师没有给出替代走向时，`alternative_responses` 为空也能通过；
   - 把冒烟测试中千问的那种输出（只回应 O1–O9，再补上 `alternative_responses`）做成测试数据，构造方式要与真实输出一致，验证能通过校验。

## 验收

1. `tests/test_novel_*.py` 全部通过；全量测试不得新增失败，基线为 4921 passed（不含沙箱内的端口用例）。
2. P0 的四份 dry-run 都以退出码 0 结束。critique 模式的推演记录在 dry-run 产物中包含 `alternative_responses`。
3. 在 03-report.md 末尾追加一节「第 3 轮返修（冒烟复测）」。
