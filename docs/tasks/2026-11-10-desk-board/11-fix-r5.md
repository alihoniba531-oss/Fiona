# 返修单 R5：案头第一期

R4 之后，机械门禁（54 项）、变异、三个宽度的界面走查（113 项）都通过了。第三轮独立复核（报告在同目录 `10-review-r3.md`，请完整读第 5、8 节）确认第二轮 3 条已修好、第 13 节实现符合规格、验收 10 条全部符合、没有新的错误行为；只剩 1 条必须修复：一条容器用例的夹具写错了，断言证明不了「方案已刷新」。

规格已改成 v1.5：**请读 `docs/tasks/2026-11-10-desk-board/02-spec.md` 第 14 节**，它就是这一轮的完整要求。

## 硬规矩

- **只许改两个文件**：`backend/tests/test_desk_dock_races_frontend.py` 和 `docs/tasks/2026-11-10-desk-board/impl/主代理.md`。
- `frontend/**`、其他测试、四份文档（`CLAUDE.md`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`）一个字节都不动。做变异时改了 `DeskDock.tsx`，做完必须按原字节还原并用 `shasum -a 256` 校验。
- 不新增用例（新测试仍是 100 条）；不装依赖；不提交、不 stash、不切分支；任务目录下 `01`–`11` 开头的文件和 `design/` 不要改。
- 由你自己直接改，不要调用 subagent / subagent_fork / workflow。

## 要做的事（规格 14.1）

1. `NODE_FOCUS_DRIVER` 里的 `let locked = LOCK;` 改成 `let locked = false;`。别的初始值不动。
2. `lockScenario` 在 `locked = true; operationConflict = true;` 这一句**之前**记下 `view.plan.active_breakdown_status`，放进最后 `console.log(JSON.stringify({...}))` 的对象里，字段名 `beforeActive`。
3. `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan`：`edit` 和 `approve` 两个结果都加 `assert ...["beforeActive"] == "done"`，原有断言全部保留。

## 先证明、再还原

开工前先记下 `DeskDock.tsx` 的 sha256。然后依次做三个变异，每个只跑 `tests/test_desk_dock_races_frontend.py`，贴出结果，再按原字节还原：

- **改测试之前**先做一次 G9，确认现在是全过（这就是问题本身）。
- 改完测试后：
  - **G9**（规格 14.1 写了具体改法）→ `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan` 必须变红。
  - **G2**（两处 `isRevisionConflict(currentPlan.plan_revision, refreshed)` 换成 `true`）→ 这条用例仍变红。
  - **G3**（两处换成 `false`）→ `test_real_version_conflict_sets_notice_and_resolves` 仍变红。
- 全部还原后 `shasum -a 256 frontend/components/desk/DeskDock.tsx` 与开工前相同。

## 验收

逐条执行规格第 7 节的 10 条命令并给出实际输出（全量仍用 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local` 前缀）。全量要求 `8011 passed`、0 失败、0 跳过。另外：

- `git status --porcelain` 的条目与开工前相同（没有新增或减少文件）。
- `git diff main -- frontend/app/page.tsx | shasum -a 256` 仍是 `825086b000d3d31b0f167e1f2ecc8bb048257715f4d7712a17fc501ee1187d4b`。
- `shasum -a 256 frontend/components/desk/*.tsx frontend/lib/desk.ts` 与开工前逐个相同。

## 报告

在 `impl/主代理.md` 末尾追加「## R5」，然后回复五项：改了哪些文件、哪几行；改测试前后 G9 的结果，以及 G2、G3 的结果；逐项对应规格 14.1 的四条要求；每条命令的实际输出；没做完或需要人工确认的地方。
