# WO3c 返修单 R2（三处小修）

工作区：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`。WO3c 的改动尚未提交，在当前工作区上继续修改。
背景见同目录的 `02-spec.md`（规格）、`04-review-r2.md` 第 4 节，以及 `06-verify.md` 末尾的「留给作者定的可优化项」(a)(b) 和 N3。

## 约束
- 只改下面点名的文件及其对应测试。改动尽量小，不做无关重构。
- 不新增依赖，不改 `package.json`、lockfile、`requirements.txt`、`globals.css`。
- 不联网，不提交，不改非工作室的测试。
- 所有由 node 驱动的新测试，必须沿用 `backend/tests/test_studio_breakdown_frontend.py` 里的 `probe()`：缺少依赖时 skip。

## 1. 分集表「操作」列被挤出可视区（`frontend/components/studio/EpisodePlan.tsx`）
现状：桌面表格是 `min-w-[1180px]`，操作列是 `w-20`。容器宽约 1100px 时（视口 1280 加侧栏），操作列整列落在横向滚动区外，看不到「更多」。

修法：
- 把操作列的 `th` 和每行 `td` 固定在右侧：加 `sticky right-0 z-10`，背景用不透明的 `bg-[color:var(--paper)]`，左侧加一条 `border-l border-[color:var(--carve)]` 作为分隔。表格横向滚动时，「更多」始终可见。
- 把 `min-w-[1180px]` 降到 `min-w-[1040px]`；必要时给「这集发生的变化」「终点 / 钩子」两列设合理宽度，确保不挤。
- 测试：在 `backend/tests/test_studio_breakdown_frontend.py` 现有分集表 SSR 测试里，断言操作列的 th 和 td 都带 `sticky`、`right-0`、`bg-[color:var(--paper)]`，表格的最小宽度类为 `min-w-[1040px]`。

## 2. 「大约几集（可不填）」标签折行（`frontend/components/studio/BreakdownPanel.tsx`）
- 标签改为「大约几集」，输入框加 `placeholder="可不填"`。
- 三个标签的文字都加 `whitespace-nowrap`，保证三个输入框上沿对齐。
- 相应更新已有测试里对标签文字的断言（如有）。

## 3. 已完成的旧拆解被标成 cancelled（`backend/studio/breakdown.py` 的 `start()`，约 200–215 行）
现状：重新拆解时，`start()` 会把旧拆解的状态一律写成 `cancelled`，包括状态本来是 `done` 的旧拆解。之后的工单如果直接读这一列，会误判。

修法：
- 只有旧拆解里确实有被取消的 `queued / blocked` 批，也就是之前是 `running` 或 `partial`，才写 `cancelled`。
- 旧拆解原来是 `done` 时，保持 `done`。
- 新增一列 `superseded_by`（TEXT NULL，指向新拆解的 id），所有被新拆解替代的旧拆解都写这一列，不论之前是什么状态。建表 DDL 和 `migrate_schema` 的补列字典要同时加，做法同现有的 `studio_*` 补列。
- 检查本文件里所有用 `status == 'cancelled'` 判断「旧拆解不再物化、不再调度」的地方（约 470、499、557、627、655 行一带）。凡是本意是「这次拆解已被替代」的，改为同时识别 `superseded_by IS NOT NULL`，确保 `done` 状态的旧拆解不会被重新物化，也不会重新发布方案。
- `_published` 的现有行为（重新拆解进行中继续显示旧方案）必须保持不变。
- 测试（放在 `backend/tests/test_studio_breakdown_r1_pipeline.py` 或新建 `test_studio_breakdown_r2.py`）：
  - (a) 旧拆解 `done` → 再报价并开始：旧拆解状态仍为 `done`、`superseded_by` 等于新拆解 id；接下来对项目的 GET 都不会改写旧拆解的单元和总表；在新拆解发布之前，分集表仍显示旧方案。
  - (b) 旧拆解 `partial`（有 blocked 批）→ 再开始：旧拆解为 `cancelled`、`superseded_by` 已写入，未执行批的预留已释放。这条是现有测试的行为，补上 `superseded_by` 的断言即可。

## 完成后
- 用仓库虚拟环境跑：`cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_breakdown_*.py tests/test_studio_brain_frontend.py`
- 跑：`cd frontend && npm run lint && npx tsc --noEmit`
- 在 `03-report.md` 末尾追加「R2 小修」一节，逐条写明改了哪些文件、增减了哪些测试、两条命令的结果。
