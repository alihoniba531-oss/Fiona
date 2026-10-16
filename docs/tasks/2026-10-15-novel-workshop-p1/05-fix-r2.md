# 小说工坊 P1 第 2 轮返修单（真实冒烟测试暴露）

> 来源：2026-10-16 作者批准做真实冒烟测试。在隔离临时库上启动后端，主编用平台的 `dashscope:qwen3.8-max`，以 critique 模式跑一本 2 章的小书。结果在第 1 章的 `03-finalize-editor` 以 `decision_invalid` 暂停。
>
> 两次尝试的错误都是：`decision.objection_responses：本次下发的每条意见或留言必须恰好回应一次，不得出现其他 ID`。
>
> 计费、暂停和账目都正确：用户余额减少 = spent = 各步骤实扣之和 = 114，reserved 归零。
>
> 红线与前几轮相同：
> - 只改 `backend/novel/**` 和 `backend/tests/test_novel_*.py`，并在 `03-report.md` 中补记；
> - 既有测试的输入和断言不得修改；
> - 测试不得读取仓库以外的文件；
> - 不联网，不读密钥，不提交 commit。

## G1 回应校验的报错必须指出具体是哪些 ID（schemas.py `_responses`）

**问题**：现在的报错只有一句笼统的话。模型拿到之后修正重试，并不知道漏了哪条、多了哪条，所以第二次大概率还是错。

**修法**：错误清单要分别列出下面三类，**只列 ID，不带任何内容文本**：
- 缺少回应的 ID，例如「缺少：O3、O7、A2」；
- 多出或不存在的 ID，例如「多出：O10」；
- 重复回应的 ID，例如「重复：O1」。

原来那句总述保留，放在最前面。

**测试**：构造缺失、多出和重复三种情况，分别断言错误文本中包含对应的 ID。

## G2 主编定稿和裁决时，给出按顺序排好的待回应清单（deliberation.py、agent_pool.py）

- finalize 的 payload，以及 merge、solo 模式下 decision 的 payload，都新增字段 `required_response_ids`。它按顺序列出全部 O*、A* 和 N* 的 ID：先 O，再 A，最后 N，与代码分配时的顺序一致。
- 提示词同步加上一句：「`objection_responses` 必须按 `required_response_ids` 中 O 与 A 的顺序逐条回应，条数与清单一致；`user_note_responses` 按其中 N 的顺序回应。」
- 只改提示词和 payload，**校验规则不变**。
- **P0 兼容**：P0 离线脚本的步骤键和流程不变。payload 新增字段属于允许的提示词变化；如果有冻结的 P0 期望值因此受影响，只允许为这个新字段做相应调整，并在报告中列出。
- **测试**：
  - finalize、merge 的 decision 和 solo 的 decision 三种 payload 中，`required_response_ids` 的内容和顺序都正确；
  - 三张主编卡片的提示中都包含新加的那句话。

## 验收

1. `tests/test_novel_*.py` 全部通过，全量测试没有新增失败（基线是 4893 passed、3 skipped）。
2. P0 的四份 dry-run 都以退出码 0 结束。
3. 在 03-report.md 末尾追加「第 2 轮返修（冒烟）」一节。
