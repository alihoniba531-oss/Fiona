# 小说工坊 P0 第 3 轮返修单（实验 B 卡在最后一章裁决）

> 来源：真跑实验 B 在第 12 章（也就是 final 模式）以 decision_invalid 退出。证据在 `/Users/yangjing/Desktop/ai-workspace/outputs/novel-p0-2026-10-15/expB/arm-panel/ch012/03-decision-editor.json`（只读，不要修改；作者会用同一目录续跑）。
> 红线与 05-fix-r2 相同：只改 `backend/novel/**`、`backend/tests/test_novel_*.py`、`03-report.md`；不联网、不读密钥、不运行真实提供方、不提交 commit；既有测试的输入和断言不得修改。

## 现象

主编在 `beat_sheet.foreshadowing_resolve` 里写了 `["F005","F006","F008","F011"]`。其中 F011 已在第 6 章回收，状态是 resolved，校验因此判失败。修正重试时，主编又写了一遍 F011，于是整本书停在最后一章。这一章的其余字段都合法：ending_status=end，所有 major 伏笔都已经回收。

## R3-1 回收清单里的失效 ID 只剔除并记录，不再判裁决失败（schemas.py，以及 report.py 的展示）

- `validate_decision` 处理 `beat_sheet.foreshadowing_resolve` 时，按 ID 分三种情况：
  - **已回收**（status=resolved）：从返回的规范化副本里剔除。
  - **不存在**：同样剔除。
  - **仍处于 open 状态**：保留。
- 被剔除的 ID 记进返回结果顶层新增的 `warnings` 列表，格式是 `{"field":"beat_sheet.foreshadowing_resolve","id":"F011","reason":"已回收"或"不存在"}`。`warnings` 由代码生成，不属于模型的输出结构。
- **完结守卫照常执行**：剔除之后，仍然处于 open 状态的 major 伏笔，必须出现在 `foreshadowing_resolve` 里，或者出现在 `unresolved_major_handling` 里；判断以剔除后的清单为准。
- 同一个 ID 写了两次，仍按原规则判失败（这是格式错误，不是状态问题）。
- `unresolved_major_handling` 里的 ID 校验**不放宽**，因为它代表主编对完结的承诺。
- 报告：在 `report.md` 的每章推演摘要里，如果裁决带有 `warnings`，就列出来。
- 测试：
  - 回收清单里有一个已回收的 ID 和一个不存在的 ID：裁决通过，两个 ID 都被剔除，`warnings` 有两条，原因分别为「已回收」和「不存在」。
  - 剔除失效 ID 之后，还有 major 伏笔处于 open 状态，并且没有给出处理方式：仍判失败。这是正控，用来确认守卫没有被削弱。
  - 同一 ID 重复：仍判失败。
  - 用证据文件里的 raw_response 做一次离线回放：新代码下校验通过，`warnings` 记录了 F011。
- 只有在原断言恰好断言「回收已回收 ID 必须失败」时，才允许修改既有测试。修改方向只能是：把它改成断言「剔除并记录警告」。如果确实改了，必须在 03-report 中逐条列出。

## 验收

1. `tests/test_novel_*.py` 全部通过；全量测试没有新增失败；三个默认配置的 dry-run 都以退出码 0 结束；`git status --porcelain` 里没有 `M` 状态的文件。
2. 在 03-report.md 末尾追加「第 3 轮返修」一节。
