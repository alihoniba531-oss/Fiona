# verify/claude/：Claude 的门禁与实测（聊天建书）

执行者交付后由 Claude 在沙箱外跑，结果在 `results/`。路径占位：`<工作树>` = 候选 worktree，`<HEAD 副本>` = `git archive 0ca95af` 加克隆依赖的目录，`<基线目录>` = 临时库与密钥文件所在目录。

| 文件 | 用途 |
|---|---|
| `gate_ccn.py` | 机械门禁：`python3 -I gate_ccn.py <工作树> <HEAD 副本> [--skip-build] [--skip-pytest]`。核对改动集合与白名单（含 v1.1 对 `test_studio_sources_readonly_integration.py` 的两处授权 hunk）、`CLAUDE_CLIENT_TOOLS` 常量块与 HEAD 逐字节相同、BOM、规格 §5.6 计数与「卡片不落库」子串、tsc / lint / build、新测试 + 9 个相关既有测试、全量 pytest（`7863 + 实收集数`）、新测试在 HEAD 副本上的对照（必须失败且全是 AssertionError）。先在空实现的 HEAD worktree 上做过失败正控（23/36 红）。`results/gate-r0.txt` 是首轮交付的一次（含 build）：实质项全过，3 个 FAIL 是脚本自身 bug（中文路径引号、`--collect-only` 重复 `-q`），已修；`results/gate-r1.txt` 是 R1 后 `--skip-build` 的一次：`== FAIL 0 / 46`；`results/gate-r2.txt` 是 R2 后（规格 v1.2：授权 `test_novel_p2_frontend.py:40` 一处、删 `page.tsx` 注释行）含 build 的一次。 |
| `mut_ccn.py` | 12 项变异：开关条件、每轮一份、50 上限边界、落库归属、config 排除 `draft_id`、建书不消费草稿、草稿可重复消费、路由不隔离本人、刷新不重建卡、`ChatCard` 分支、`openNovelAt` 白名单、向导不带 `draft_id`；每项要求有非 selfcheck 的真实用例变红，按字节还原。`results/mutations.txt`：R1 后 `== FAIL 0 / 12`；R2 后加两项（`ChatBubble` 两处不透传 `onOpenNovel`、iframe 初值改掉）共 14 项，`results/mutations-r2.txt`：`== FAIL 0 / 14`。 |
| `seed_ccn.py` | 走查造数：在隔离临时库里用后端自己的代码路径（`resolve_chat_conversation` → `novel.drafts.create_draft` → `database.save_message(novel_draft_id=…)`）为 tester 造一份草稿和一条带卡片的 assistant 消息。 |
| `walk_ccn.py` | 真实走查（Playwright 1.63 无头 Chromium，隔离实例：候选 worktree 的 8098 后端 + 3099 dev 前端 + 临时库，开发模式、占位 Key）：登录 → 聊天出草稿卡 → 「去书斋建书」→ 抽屉打开且 iframe 路径为 `/novels/new?embed=1&draft=<id>` → 向导预填思路与篇幅 → 三步提交建书 → 库里草稿 `novel_id` 已填、`novels` 多一行 → iframe 跳到工作台 → 刷新后卡片变「已建书」带「打开」→ 「打开」后 iframe 路径为 `/novels/<id>?embed=1` → 390 宽无横向溢出。`results/walk.txt` / `walk.json`：`== FAIL 0 / 20`；截图在 `results/screenshots/`。占位 Key 下建书后的 setup 必然失败（工作台显示「某一步失败，可以重试」），这是环境所致，不在本批范围。 |

Claude 智能体真实调用 `draft_novel` 的路径没有真实 Anthropic Key，由 `test_novel_chat_create.py` 用假传输回放 `tool_use` 覆盖（工具追加矩阵、参数校验、成功落库、每轮一份、50 上限、不建书不扣费）。

## R3（CI 无 node_modules）

- `gate_ccn_r3.py <worktree> <无 node_modules 副本>`：副本用 rsync 排除 node_modules/.venv/.git 得到。先用 HEAD 版本的测试文件在副本里复现 CI 的 3 failed（正控），再检查守卫位置、既有 9 条用例逐字节未动、自检存在、有依赖 12 passed / 0 skipped、无依赖 0 failed / 4 skipped（3 条约定文案），并在副本里做两处变异（去掉一条用例的守卫；守卫不再 skip）。结果在 `results/gate-r3.txt`。
