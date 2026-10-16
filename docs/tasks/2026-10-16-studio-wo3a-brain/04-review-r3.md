# WO3a 第 3 轮核验（R2 视觉模型可配置 + R3 CI 兼容）

- R3 改动：`test_studio_frontend_shell.py` 的 `probe()` 在 Node 启动前检查 `frontend/node_modules/typescript/lib/typescript.js` 和 `node` 命令；components / navigation 入口此前已有同类守卫，由 `test_studio_frontend_dependencies.py` 覆盖。原有断言未改。
- R2 抽查：`config._vision_model()` 每次调用读取，空值走默认、非法值回落默认并告警一次；`brain.py:396-402` 在创建 SDK、发出付费请求之前查价，缺价返回 409；DeepSeek 看图一律转交千问视觉。

## 机械验证（主控在沙箱外执行）
| 环境 | 结果 |
|---|---|
| 工作室 worktree，有 `frontend/node_modules` | 后端全量 6220 passed，0 failed，0 skipped |
| 临时合并副本（WO3a 快照合入 origin/main 57cf1c8，无 `frontend/node_modules`，等同 CI） | 6386 passed，65 skipped，0 failed；skip 全部是「frontend dependencies unavailable」 |
| 前端 | lint 0 个错误（25 条警告，与基线相同）；tsc 通过；build 通过 |

## 合并 main 的冲突
- 只有 `backend/tests/test_studio_frontend_shell.py` 冲突，两边都给 `probe()` 加了守卫。解决方式：保留 WO3a 的较严守卫，同时保留 main 的元测试 `test_probe_skips_when_frontend_dependencies_are_missing`。
- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md` 自动合并，已逐处核对：小说工坊结构 v2 的新增段落和工作室 `qwen3-vl-plus` 的改动都在。

## 结论：通过，可交作者决定是否合并推送。
