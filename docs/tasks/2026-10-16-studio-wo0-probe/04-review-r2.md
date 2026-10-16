# WO0 复核记录（第 2 轮，只核 R1-1～R1-8）

- 复核方式：全新上下文的独立代理（Fable）。
- 机械验证（主控在沙箱外执行）：
  - 定向测试：201 passed。
  - 全量测试：5278 passed、17 skipped、0 failed。17 个跳过都是 worktree 缺前端 `node_modules`，与基线相同，属于环境原因。

## 结论：通过

| 项 | 结论 | 证据 |
|---|---|---|
| R1-1 工作空间 ID 脱敏 | 通过 | `_studio_probe_common.py:154-161,83-93`；`test_video_success_contract[wan]` 内的 `assert_all_secrets_absent` 检查 6 个变量 × 5 个输出面（夹具、report.jsonl、report.md、stdout、stderr）。复核另用脚本独立跑了一遍 wan 成功流程，无泄漏 |
| R1-2 Claude schema 兼容 | 通过 | `_studio_probe_brain.py:76-101,441,511`；发出去的 schema 在任意深度都没有残留不兼容的关键字，本地校验仍用完整 schema |
| R1-3 effort=low 与截断 | 通过 | `:441,453-454,497,505,515-516`；截断时只发 1 次请求，并记为 `succeeded_truncated` |
| R1-4 2xx 异常判 uncertain | 通过 | `_studio_probe_common.py:204-208` |
| R1-5 脱敏不误伤 | 通过 | `:76-82` |
| R1-6 夹具只在有上游响应时写 | 通过 | `persist :404`；夹具目录只剩 `.gitkeep` |
| R1-7 breakdown 花费硬闸 | 通过 | `_studio_probe_brain.py:557-607,647`；最多 3 路并发，超预算后停止派发，并跳过 reduce |
| R1-8 万相首帧预检 | 通过 | `_studio_probe_media.py:278-331`；9 个不合格用例都是 0 请求 |

## 新发现（留待以后，本期不修）

- `_api_schema` 按关键字名删除。以后 schema 的 `properties` 里如果出现叫 `format`、`pattern`、`minimum` 的业务字段，会被误删。第 1 期写正式的 `brain.py` 时，改成只删除约束位置上的关键字。
- 完整 JSON 响应的 5xx，在探针里标为 rejected（与规格 §5.1 一致）。正式任务表里一律改判 uncertain，从严处理。
