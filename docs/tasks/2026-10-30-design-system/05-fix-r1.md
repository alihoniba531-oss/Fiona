# 05 返修单 R1：遮罩兜底色 + 新测试收紧

- 日期：2026-10-30。基于你上一轮的交付（工作树当前状态），规格仍是 `02-spec.md`。
- 来源：独立复核 `04-review.md` 的可优化项 2、3、5，用户决定在合并前补上。复核结论为通过，没有必须修复项；本单只做下面三件事。

## 1. 要做的事

**R1-1 对话框遮罩加兜底色**（`frontend/app/globals.css`）
- 原因：Safari 17.4 之前，`::backdrop` 取不到 `:root` 上的变量，`var(--scrim)` 失效后遮罩变透明。
- 做法：按 `verify/r1_edits.json` 逐条套用，共 2 条，字段同 `t2_edits.json`（`n` / `file` / `count` / `old` / `new`）。
  - 每条先断言 `old` 恰好出现 `count` 次，对不上就停下来说明；
  - 按字节读写，不碰别的字符。
- 结果：两个对话框各有昼、夜两条 `::backdrop` 规则，值为 `var(--scrim, 原来的颜色)`；上方加一行注释说明原因。

**R1-2 源码门禁补 T8**（`backend/tests/test_design_system_gate.py`）
- 在 `test_token_layer` 里加 T8，逻辑照 `verify/ref/gate_rules.py` 里新加的 T8：
  - 遍历全部块，凡选择器以 `::backdrop` 结尾的，收集它们的 `background`；
  - 必须恰好是这 4 条，且每条只有一个值：
    - `.image-preview-dialog::backdrop` 与 `.confirm-dialog::backdrop`：`var(--scrim, rgba(31,41,38,.18))`；
    - `.dark .image-preview-dialog::backdrop` 与 `.dark .confirm-dialog::backdrop`：`var(--scrim, rgba(0,0,0,.45))`。
- `test_selfcheck_token_layer` 补一个坏样本：把兜底值去掉（写回 `var(--scrim)`）后，T8 必须判失败。
- HEAD 上 T8 失败（HEAD 写的是字面颜色），`test_token_layer` 在 HEAD 上照旧失败。

**R1-3 cn 与生成 CSS 两个测试：源文件缺失要失败，不能 skip**
- `test_design_system_cn.py`：`frontend/lib/utils.ts` 不存在时用断言失败，不再 `pytest.skip`。这个断言要放在 node 探测之前，没有 node 时也能报出来。
- `test_design_system_css.py`：`frontend/app/globals.css` 不存在时同样改成断言失败；`REQUIRED_PACKAGES` 去掉用不到的 `typescript`。
- 改后只在「没有 node」或「这个测试真正用到的前端包缺失」时才 skip。

## 2. 白名单

只许改动：
- `frontend/app/globals.css`：只做 R1-1 的 2 条；
- `backend/tests/test_design_system_gate.py`、`test_design_system_cn.py`、`test_design_system_css.py`；
- `docs/tasks/2026-10-30-design-system/03-report.md`：末尾追加一节「返修 R1」；
- `docs/tasks/2026-10-30-design-system/impl/R1.md`：本轮记录。

`02-spec.md`、`04-review.md`、`05-fix-r1.md`、`verify/**` 只读。其余规矩照规格 §3.5、§5 执行：git 只读，不要用编辑工具碰 `app/page.tsx`。

## 3. 验收（你自己先跑一遍，结果写进报告；Claude 会在沙箱外复跑）

1. `python3 -I docs/tasks/2026-10-30-design-system/verify/ref/gate_rules.py .` → `== FAIL 0`（扫描面 1 项、源码规则 19 条、令牌层 T1–T8，共 28 项）。
2. `contrast_check.py`、`gate_twcss.mjs` 仍为 0。
3. 4 个新测试全部通过，0 skipped。
4. 变异自检，每项改完都按字节还原：
   - 把任一条 `::backdrop` 的兜底值去掉 → `test_token_layer` 变红；
   - 在临时副本里把 `frontend/lib/utils.ts` 改名 → `test_cn_keeps_size_and_color` **失败**（不是 skip）；
   - 在临时副本里把 `frontend/app/globals.css` 改名 → `test_generated_css_font_sizes` **失败**（不是 skip）。
   - 改名只能在系统临时目录的副本里做，不要在工作树里改名。
5. HEAD 副本上（跑法同规格 §T3）：除 `test_selfcheck_*` 外仍全部失败，失败类型是 AssertionError，各规则命中数与规格表一致；T8 失败。
6. 全量 pytest（按 §3.5 清代理变量，后台跑完再写结果）：0 failed、0 skipped，passed 仍为 7836。
7. `cd frontend && npm run build` 退出码 0。

## 4. 执行方式

改动很小。用工作流（`workflow` 工具）拆两个 agent 并行，文件不重叠：
- agent 1：R1-1 加 R1-2（`globals.css`、`test_design_system_gate.py`）；
- agent 2：R1-3（`test_design_system_cn.py`、`test_design_system_css.py`）。

每个 agent 的任务说明自包含，写明「不得调用 subagent / subagent_fork / workflow」，并让它自己去读本单和 `verify/` 附件，不要把原文转抄进脚本。两个 agent 都结束后，主代理跑第 3 节，写 `impl/R1.md` 和报告的「返修 R1」一节。

何时停下来问同规格 §8：只有影响「实现什么」的问题才停，实测与本单不符就停下来说明，不回滚已完成的工作。
