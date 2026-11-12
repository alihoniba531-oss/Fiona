# 07 独立复核（第 2 轮，窄范围）：修改意见卡 R1 + R2 返修（规格 v1.5）

- 复核对象：复核副本，即基线 `7a17f64` 加上未提交改动。
  - 未提交改动包括 20 个 `M` 和 15 个 `??`。
  - 快照为 `.review/diff-r2.patch` 与 `.review/untracked-r2.txt`。
  - 开工时核对过：`git diff HEAD --binary` 与快照逐字节相同；15 个未跟踪文件的 sha256 也已记录。
- 依据：`02-spec.md` v1.5，重点是 §4.3 T6.3 第 3 支、T6.6、§4.2 T3 `redo_feedback_plan`、§4.6 与 §4.7。
  - 实施方报告 `impl/report-r1.md`、`impl/report-r2.md` 只当线索。
  - 派单方的 `.review/gate-r2-summary.txt`、`.review/mutations-r2-summary.txt` 也只当线索。
  - 下文结论都来自本人在副本里重新跑的命令和自己写的变异或对照实验。
- 范围：按循环规则，本轮只看两件事：上一轮必须修复项是否修好，以及 R1、R2 新增的内容。范围外的发现一律放进可优化项。
- 环境：
  - pytest 一律用 `backend/.venv/bin/python -m pytest -p no:cacheprovider`，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`，下文省略。
  - 没有联网，没有读 `.env` / `.env.local`，没有执行 commit、stash、checkout、reset，也没有调用子代理。
  - 实验脚本和临时副本都放在仓库外的 `/tmp/r2rev/`，结束前已删除（见 §9）。

## 1. 结论：通过

- **上一轮的必须修复项都已修好**。MF-1、MF-2、MF-3，以及扩大范围的 B19、B33，逐条核验都成立，证据见 §2。
- **上一轮记录为存活的 14 个变异，现在全部被杀**：M1、M2、M3、M3b、M4、M5、M6、M7、M14、M15、B19a、B19b、B19c、B33b。
  - 杀死它们的都是行为类用例，不是读源码的 `self_check` 或 `test_bad_` 自检。
- **R1 的两处产品改动符合规格，没有引入错误**：
  - P1 是 `NovelFeedbackCard.tsx`。服务端渲染时，在 221,328 种视图组合下，改动前后的输出逐字节相同；点击流程与 T6.6 逐句一致。
  - P2 是 `service.py:631`。只改了这一处条件，判断顺序没变。
- **§4.6 B1–B6、F1–F8 与 §4.7 G1–G7 都按规格完成，且有证明力**：
  - 我另外写的 28 个针对 P1、P2 和 R2 条目的变异（X1–X17、X20–X23、Y1–Y7）里，27 个被杀。
  - 唯一存活的那个不违反规格，记作可优化项 1。
  - F8 和 R2 改动过的既有用例，没有一处放宽原来锁住的意图，都是保持或收紧。
- **D1–D4 四处文档改动**：都是逐字替换，每处只动规格写明的那一句。
- **门禁抽查**：全量后端 8264 passed、0 skipped；三个新文件 253 passed；无 `node_modules` 副本 skip 数 93 + 9 = 102；tsc 0；lint 0 errors / 25 warnings。

**必须修复项：无。**

## 2. 上一轮必须修复项逐条核验

### 2.1 MF-1「已被细纲读到」覆盖三种进行中状态：已修好

- **用例**：`backend/tests/test_novel_chat_feedback.py:1049-1093` 的 `test_feedback_view_planned_read_from_in_progress_meeting`。
  - 按 `PROGRESS_STATUSES = ("awaiting_plan_approval", "planning", "writing")`（`:33`）参数化。
  - 每种状态都断言 `planned_chapter == 2`、`planned_adopted is False`、`planned_response == "编辑部回应原文"`。
  - 「meeting 损坏」「`done` 不算」两段保留，R2 又加了 `stale` 段（G6）。
- **自检**：`test_bad_planned_read_statuses_are_caught`（`:1989-2043`）。
  - 少 `writing` 的坏副本：`writing` 一组必须变红。
  - 只留 `awaiting_plan_approval` 的坏副本：`planning`、`writing` 两组必须变红。
  - 已通过，即两个 `pytest.raises` 都成立。
- **我的变异**（锚点是 `service.py:540`，与上轮相同）：

  | 变异 | 改动 | 结果 |
  |---|---|---|
  | M4 | IN 列表改成 `('awaiting_plan_approval','planning')` | **KILLED**，由 `test_feedback_view_planned_read_from_in_progress_meeting[writing]` 杀死 |
  | M5 | IN 列表改成 `('awaiting_plan_approval')` | **KILLED**，由同一用例的 `[planning]` 杀死 |
  | X22 | 改成 `status<>'done'` | **KILLED**，由 `[awaiting_plan_approval]` 里的 stale 段杀死 |
  | X23 | IN 列表加入 `'stale'` | **KILLED**，同上 |

### 2.2 MF-2「等确认的不是卡上这一章」：已修好

- **两条用例**：`backend/tests/test_novel_chat_feedback_frontend.py:756-768`、`:852-855`。
  - (a) `not-awaiting-other-chapter`：`OTHER_CHAPTER_VIEW = make_book(awaiting_chapter=3, plan_row_status="done")`，卡上 `plan_chapter=2`。期望：
    - 说明逐字为 `PLAN_NOT_AWAITING`；
    - 没有「带着这些要求重新定稿」和「去书斋改细纲」按钮。
  - (b) `redo-done-awaiting-other-chapter`：`redo_started_at` 有值，`make_book(redo_pending=False, awaiting_chapter=3)`。期望：
    - 标签为「已发起重新定稿」；
    - 说明只有 `PLAN_DONE`；
    - 由 `assert_only_description` 保证全文不含 `PLAN_DONE_AWAITING`。
  - 两条都传 `__withOpenNovel`，并断言 HTML 含「在书斋打开」（`:884-885`，G5），证明按钮缺失不是因为没传 `onOpenNovel`。
- **两条自检**：`test_feedback_card_other_awaiting_chapter_self_check`（`:889-928`）。
  - (a) 删掉 `redoAvailable` 里的 `&& book.awaiting_chapter === view.plan_chapter`，用例变红。
  - (b) 把第 1 支追加句的条件改成只看 `awaiting_plan`，用例变红。
- **我的变异**：

  | 变异 | 改动 | 结果 |
  |---|---|---|
  | M15 | 删 `NovelFeedbackCard.tsx:52` 的章号比较。P1 之后这一判断在 `redoAvailable` 里 | **KILLED**，由 `test_feedback_card_plan_section_states[not-awaiting-other-chapter]` 杀死 |
  | M14 | 把 `:229` 改成 `if (book.status === "awaiting_plan") {` | **KILLED**，由 `[redo-done-awaiting-other-chapter]` 杀死 |

### 2.3 MF-3 在 HEAD 上不再出现 `FileNotFoundError`：已修好

- **做法**：
  - 用 `git archive 7a17f64 | tar -x -C /tmp/r2rev/head` 导出基线。
  - `.venv` 与 `node_modules` 用软链接接入。
  - 拷入 R2 版的三个新测试文件，拷入后与工作区逐字节比较一致。
  - 加 `--junitxml` 运行。
- **结果**：`212 failed, 41 passed`。
  - 212 条失败的全文里，`FileNotFoundError` 出现 0 次，全部是断言失败。
  - 上一轮点名的 14 条，failure message 逐条都是 `AssertionError: feedback.py 尚未实现`：
    - `note_click_disables…`
    - `redo_confirmation_costs[strawberries|own_model|free]`
    - `redo_confirmed…`
    - `note_success_then_redo…`
    - `action_error…`
    - `read_states…`
    - `note_error_then_success…`
    - `redo_error…`
    - `unmount_aborts…`
    - `own_model_fee…`
    - `request_paths…`
    - `request_path_self_check…`
  - 41 条通过的构成：开关矩阵 30 条、`note` / `redo_plan` 路由行为不变 2 条、skip 守卫自检 4 条、案头 O3 参数用例 5 条。这些都是回归类或本来就成立的用例，与派单方的结果一致。
- **守卫顺序**：
  - 用 AST 检查了前端新文件中所有直接调用 `read(COMPONENT|FEEDBACK_LIB)` 的用例：`_require_feedback()` 都在第一次 `read` 之前，而且都在 `require_node_dependencies()` 之后。
  - 唯一的例外是 `test_feedback_card_shows_full_plan_and_chapter_texts:1214`。它先调用的 `render_view` 内部已经调用了 `_require_feedback()`，所以执行顺序同样正确。
- **无 `node_modules` 副本**：
  - 做法：`rsync -a --exclude frontend/node_modules --exclude frontend/.next --exclude .review` 到 `/tmp/r2rev/nonode`，保留 `backend/.venv`，再跑三个新文件。
  - 结果：
    - `SKIPPED [93] tests/test_novel_chat_feedback_frontend.py:63: frontend dependencies unavailable: typescript, react, react-dom/server`
    - `SKIPPED [9] tests/test_desk_views_frontend.py:36: frontend dependencies unavailable: typescript, react, react-dom/server`
    - `151 passed, 102 skipped`
  - 前端新文件中不起 node 的 20 条，按 `-rA` 逐条列出后，构成与上一轮相同：skip 守卫自检 4 条、源码约束 1 条、坏副本 11 条、page 2 条、路由 2 条。
  - 113 − 20 = 93，所以 R1、R2 新增的起 node 用例全部过了依赖守卫。

### 2.4 B19 扩大：四个边界都已补上

- **正样本**：`test_validate_feedback_args_accepts_each_upper_boundary[next|current|issue|written]`（`:537-586`）。四个上限都断言 `error is None`，并核对返回的清洗值：
  - `next_chapters` 是前后加空白的 500 字；
  - `current_plan` 恰 500 字，且断言 `plan_chapter == 3`；
  - `issue` 恰 200 字；
  - `written_chapters` 恰 10 条，`chapters_done=10`。
- **自检**：`test_bad_upper_boundary_comparison_is_caught`（`:2088-2111`），四个锚点都断言只出现 1 次。
- **我的变异**：

  | 变异 | 位置 | 结果 |
  |---|---|---|
  | B19 | `feedback.py:51` `len(next_text) >= TEXT_MAX` | **KILLED**，由 `[next]` 杀死 |
  | B19a | `:55` `len(current_text) >= TEXT_MAX` | **KILLED**，由 `[current]` 杀死 |
  | B19b | `:89` `len(issue_text) >= ISSUE_MAX` | **KILLED**，由 `[issue]` 杀死 |
  | B19c | `:72` `len(written_raw) >= WRITTEN_MAX` | **KILLED**，由 `[written]` 杀死 |

### 2.5 B33 扩大：已改为只数本书的 pending

- **用例**：`test_feedback_view_pending_notes_counts_this_book_only`（`:1031-1046`）。
  - 库里放：本书 2 条 pending、1 条 delivered，另一本书 1 条 pending。
  - 断言 `pending_notes == 2`。
- **自检**：`test_bad_feedback_view_pending_note_count_is_caught`（`:2139-2185`），三种坏副本都要变红：写死 0、去掉 `status`、去掉按书过滤。
- **我的变异**：

  | 变异 | 改动 | 结果 |
  |---|---|---|
  | B33 | `service.py:527` 写死 `pending_notes=0` | **KILLED** |
  | B33b | `:526` 去掉 ` AND status='pending'` | **KILLED** |
  | B33c | `:526` 去掉按书过滤 | **KILLED** |

  三个都由 `test_feedback_view_pending_notes_counts_this_book_only` 杀死。

### 2.6 上一轮存活变异的现状（锚点按语义重新定位）

- **做法**：变异脚本 `/tmp/r2rev/mutate.py`。
  - 每个变异先断言锚点在原文中恰好出现 1 次，然后改文件。
  - 再跑对应的新测试文件，加 `-x`，并用 `-k "not self_check and not test_bad_"` 排除读源码的自检。
  - 跑完从备份拷回原文件，并核对 sha256。
- **未变异时的正控**：两个文件 `209 passed, 35 deselected`。

| 上轮编号 | 上轮锚点 | 本轮锚点 | 结果 | 杀死它的用例 |
|---|---|---|---|---|
| M1 | `NovelFeedbackCard.tsx:228` 的 `\|\| (maxChapters …)` | `:259` | KILLED | `test_feedback_card_last_chapter_uses_max_chapters_branch` |
| M2 | `claude_agent.py:833` 的 `(F or (M … K >= M))` 改成 `F` | `:833` | KILLED | `test_success_path_…[awaiting-plan-last-chapter-at-max]` |
| M3 | `sendNote` 的 busyRef 守卫（`:109`） | `:128` | KILLED | `test_feedback_card_double_click_note_sends_once` |
| M3b | `sendRedo` 的 busyRef 守卫（`:138`） | `:157` | KILLED | `test_feedback_card_double_click_redo_reads_confirms_and_posts_once` |
| M4 / M5 | `service.py:540` | `:540` | KILLED | 见 §2.1 |
| M6 | `feedback.py:67` 的 `or number > chapters_done` | `:67` | KILLED | `test_validate_feedback_args_rejects_done_chapter_past_chapters_done` |
| M7 | 确认框之后的 abort 判断（`:144`） | `:181` | KILLED | `test_feedback_card_unmount_during_confirm_skips_post` |
| M14 / M15 | `:193`、`:201` | `:229`，以及 `redoAvailable :52` | KILLED | 见 §2.2 |
| B19a–c、B33b | 见 §2.4、§2.5 | — | KILLED | 见 §2.4、§2.5 |

## 3. R1 产品改动审查结论

### 3.1 P1 `frontend/components/NovelFeedbackCard.tsx`：符合规格，没有引入错误

逐项核对：

1. **点击流程与 §4.3 T6.3 第 3 支、T6.6 一致**（`sendRedo`，`:156-209`）：
   - 先防重入：`if (busyRef.current) return;`；
   - 置 `busyRef = true`、清空旧错误、`setBusy("confirm")`；
   - 用 `getNovelFeedback(feedbackId, signal)` 重新读取。
   - 读取失败：
     - 已卸载就直接返回；
     - 否则在第一节显示 `novelErrorMessage(error)`，保留旧视图，复位 `busy` 与 `busyRef`，不弹确认框、不发请求。
   - 读取成功：
     - 已卸载就返回；
     - 先用新视图替换当前视图（`:173`，不回到加载态），再对新视图判断 `redoAvailable`；
     - 不可用就复位并结束；
     - 可用才 `await confirm({…})`。确认后先看是否已卸载；取消就复位；确认才 `setBusy("redo")` 并发 POST。
   - POST 之后的成功和失败分支与 R0 相同，只把局部变量改名为 `after`。
2. **`redoCostSentence`**（`:34-42`）：
   - `own_model`、`free` 两种返回各自的句子，其余（包括 `undefined` 和未知值）一律返回扣草莓那句。
   - 三句与 T6.3 逐字相同。
3. **`redoAvailable`**（`:44-55`）：七个条件与 §4.6 P1 列出的逐一对应：
   - `current_plan.trim()` 非空；
   - `plan_chapter !== null`；
   - `!redo_started_at`；
   - `book !== null`；
   - `status === "awaiting_plan"`；
   - `awaiting_chapter === plan_chapter`；
   - `automation === "per_chapter"`。
   - 两个函数都是组件外的模块级纯函数，仍然只有一个函数组件。
4. **所有路径都复位 `busy` 与 `busyRef`**。逐条列出 `sendRedo` 的出口：
   - 读取失败、不可用、确认框取消、POST 成功、POST 失败后再拉取：五个出口都把两者同时复位。
   - 只有「已卸载」的三个出口不复位，也不 setState，这正是规格要求的。
   - `sendNote` 没有变化。
   - 变异证据见下表的 Y1–Y5、Y7、X4、X12。
5. **卸载后不再 setState**：每个 `await` 之后都先判断 `signal?.aborted`。
   - 位置：重读的 catch `:166`、重读成功 `:172`、确认框之后 `:181`、POST 之后 `:190` 与 `:196`、再拉取之后 `:200` 与 `:204`。
   - X13、X14、M7 三个变异都被「卸载后 setter 调用次数为 0」的断言杀死。
6. **确认框的章号与费用句取自新视图**：
   - 章号：`chapter = refreshed.plan_chapter`（`:174`）。
   - 费用句：`redoCostSentence(refreshed.book?.redo_cost)`（`:180`）。
   - 卡片的 `plan_chapter` 不会变，所以章号取新视图还是旧视图在行为上等价，测试无法也不必区分。
   - 费用句取旧视图的变异 X3 被 F7(a) 杀死。
7. **渲染结果与改动前等价**：
   - 做法：
     - 把 `delta-r0-to-r1.patch` 中这个文件的 hunk 反向应用到仓库外的副本，得到 R0 版组件。
     - 写了一个 node 脚本 `/tmp/r2rev/equiv.js`，用仓库内的 typescript、react 和 `react-dom/server`，对 R0 与当前两版组件 `renderToStaticMarkup`，逐字节比较。
   - 视图组合的维度：
     - `current_plan` 3 种 × `plan_chapter` 2 种 × `redo_started_at` 2 种；
     - `book`：null，或者 8 种 status × 3 种 `awaiting_chapter` × 2 种 automation × 4 种 `redo_cost`（含未知值）× 4 种 `plan_row_status` × 2 种 `redo_pending`；
     - 第二节 3 种 × `novel_id` 2 种 × 是否传 `onOpenNovel` 2 种。
   - 结果：`{"renders":221328,"differences":0}`。
   - 灵敏度对照：把当前版 `free` 的费用句改成 `"X"` 再比，得到 `differences: 96`。
8. **lint**：`npx eslint components/NovelFeedbackCard.tsx lib/novelFeedback.ts` 无输出，退出 0。

**针对 P1 的补充变异**（本人设计；都排除了自检用例，全部已还原）：

| 编号 | 改动 | 结果 / 杀死它的用例 |
|---|---|---|
| X1 | 重读成功后不先替换视图，只在不可用时替换 | KILLED，由 `…redo_reread_uses_latest_cost_and_updates_card` 杀死 |
| X2 | 重读成功后完全不替换视图 | KILLED，同上 |
| X3 | 确认框费用句取渲染闭包里的旧 `book` | KILLED，同上 |
| X4 | 重读失败时只复位 busyRef、不 `setBusy(null)` | KILLED，由 `…redo_reread_failure_keeps_view_and_alerts[api500-None]` 杀死 |
| X5 | 不可用分支额外显示一条错误 | **SURVIVED**，不违反规格，见可优化项 1 |
| X6 | 重读不传 `signal` | KILLED，由 `…redo_confirmation_costs[strawberries]` 杀死 |
| X7 | 重读失败时，非 `ApiError` 显示固定文案 | KILLED，由 `…failure…[type-网络错误]` 杀死 |
| X8 | `redoAvailable` 不看逐章确认 | KILLED，由 `…plan_section_states[not-per-chapter]` 杀死 |
| X9 | `redoAvailable` 不看 `redo_started_at` | KILLED，由 `…redo_reread_already_started_updates_card_without_dialog` 杀死 |
| X10 | 重读期间 busy 先置成 `redo` | KILLED，由 `…redo_confirmation_costs[strawberries]` 杀死 |
| X11 | 对旧视图判断能否重新定稿 | KILLED，由 `…redo_reread_unavailable_updates_card_without_dialog` 杀死 |
| X12 | 确认框取消时只复位 busyRef | KILLED，由 `…redo_confirmation_costs[strawberries]` 杀死 |
| X13 | 重读的 catch 不看是否已卸载 | KILLED，由 `…unmount_during_reread_aborts_and_skips_setters` 杀死 |
| X14 | 重读成功后不看是否已卸载 | KILLED，由 `…unmount_before_reread_resolves_skips_confirm_and_redo` 杀死 |
| X15 | 重读失败的提示写到第二节 | KILLED，由 `…failure…[api500-None]` 杀死 |
| X16 | `free` 落到扣草莓那句 | KILLED，由 `…plan_section_states[actionable-free]` 杀死 |
| X17 | 重读失败后又多拉一次 | KILLED，由 `…failure…[api500-None]` 杀死 |
| Y1 | 不可用分支只删 `busyRef` 复位 | KILLED，由 `…redo_reread_unavailable…` 杀死 |
| Y2 | 不可用分支两句复位都删 | KILLED，同上 |
| Y3 | 重读失败只删 `busyRef` 复位 | KILLED，由 `…failure…[api500-None]` 杀死 |
| Y4 | 确认框取消只删 `busyRef` 复位 | KILLED，由 `…redo_confirmation_costs[strawberries]` 杀死 |
| Y5 | 重读失败两句复位都删 | KILLED，由 `…failure…[api500-None]` 杀死 |
| Y7 | 交留言成功后不复位 busyRef（对照） | KILLED，由 `…note_success_then_redo_click_confirms_once` 杀死 |

### 3.2 P2 `backend/novel/service.py:631`：符合规格

- **改动**：只有一处，`if not (card['current_plan'] or '').strip() or card['plan_chapter'] is None:` 时 `fail('这张卡没有重新定稿的要求')`。
  - `delta-r0-to-r1.patch` 中 `service.py` 只有这 1 个 hunk、1 行。
  - 判断仍在 `redo_started_at is None` 分支里，所以已发起过的卡照旧幂等返回视图。
  - 顺序与 §4.2 T3 一致：卡片不存在、已发起、没有要求或章号、书已删、状态、逐章确认、`_begin_redo`。
- **正常建卡路径不受影响**：
  - `validate_feedback_args` 只在书为 `awaiting_plan`、且有 `awaiting_plan_approval` 章时才收 `current_plan`。
  - 这时 `plan_chapter = awaiting_chapter`，不会是 None。
  - 所以 P2 只拦直接改库造出的卡，不会误拒正常的卡。
- **变异**：

  | 编号 | 改动 | 结果 |
  |---|---|---|
  | X20 | 去掉条件 | KILLED，由 `test_redo_feedback_plan_rejects_card_without_plan_chapter` 杀死 |
  | X21 | `or` 改成 `and` | KILLED，由 `test_redo_feedback_plan_service_rejections` 杀死 |
  | Y6 | 把判断挪到 `_begin_redo` 之前，即 G7 的坏副本 | KILLED，由 `test_redo_feedback_plan_rejects_card_without_plan_chapter` 杀死 |

### 3.3 D1–D4 文档：逐字符合

- **做法**：脚本 `/tmp/r2rev/docs_check.py`。
  - 从 `delta-r0-to-r1.patch` 取出四份文档各自唯一的 `-` / `+` 行。
  - 对 `-` 行依次套用规格 D1–D4 写明的替换，结果与 `+` 行逐字相同。
  - 当前文件里新句各出现 1 次，旧句为 0 次。D2 是插入，旧锚点句保留 1 次。
- **结果**：`PLAN.md exact`、`docs/DEPLOYMENT.md exact`、`README.md exact`、`CLAUDE.md exact`。

### 3.4 改动集合完整性

- **R0→R2 跟踪文件的改动恰为 delta 列出的五个文件**：
  - 做法：用 delta 中跟踪文件的部分反向还原 R0 版本，再与 `.review/diff-r2.patch` 中其余 15 个文件拼回 R0 全量 diff。
  - 结果：sha256 为 `77d66fad5fa94bcbf9f13b05defe9881a7bc48f9e35f0270d6961e92f813f230`，与 `04-review.md` 记录的 R0 快照完全相同。
  - 结论：R1、R2 对跟踪文件只改了 CLAUDE、PLAN、README、DEPLOYMENT、`service.py` 这五个文件。
- **R2 只改了两个新测试文件**：`delta-r1-to-r2.patch` 只含这两个文件。新增的 `report-r1.md`、`report-r2.md` 都在白名单内。
- **白名单外没有新动作**：`backend/tests` 下仍只有三个 `??` 和授权文件的 ` M`。

## 4. §4.6 / §4.7 测试条目核对

| 条目 | 位置 | 核对与证明力 |
|---|---|---|
| B1 | `test_novel_chat_feedback.py:1049-1093`、`:1989-2043` | 见 §2.1；M4、M5 被杀 |
| B2 | `:537-586`、`:2088-2111` | 见 §2.4；四个边界变异都被杀 |
| B3 | `:1031-1046`、`:2139-2185` | 见 §2.5；三种坏副本都被杀 |
| B4 | `:589-611`、`:2114-2136` | 用 SQL 造第 3 章 `done`、`chapters_done=2`，断言报错文本逐字相同；M6 被杀 |
| B5 | `SUCCESS_CASES[awaiting-plan-last-chapter-at-max]`（`:728-740`、`:793-802`）、`:2209-2238` | 断言回灌全文等于期望、第 2 句逐字相同、不含「第 3 章」；M2 被杀 |
| B6 | `:1431-1478`、`:2241-2285` | 409 文案逐字相同；`redo_started_at` 仍为 NULL；章节行不变；`start_novel` 桩未被调用；X20 被杀 |
| F1 | 前端 `:756-768`、`:852-855`、`:889-928` | 见 §2.2 |
| F2 | 14 条加了守卫 | 见 §2.3。HEAD 上没有 `FileNotFoundError`，skip 数仍正确 |
| F3 | `:1069-1122` | (i) 包含该句，(ii) 逐字相同，两条都断言不含「第 51 章」；M1 被杀 |
| F4 | `:1972-2061` | 同步连点两次，`note == 1`；`get`、`confirm`、`redo` 各 1 次；M3、M3b 被杀 |
| F5 | `:2064-2146` | 重读之后卸载、确认框打开期间卸载，两种都断言 setter 次数为 0；M7、X14 被杀 |
| F6 | 迷你运行时 `:1284`、`:1298`；`:1912-1925`、`:2149-2181` | 卸载之后的 setter 调用计数可以证伪；坏副本断言计数大于 0 |
| F7 | `:2184-2443` | 覆盖 (a)–(e)：(d) 同时有 `ApiError` 与非 `ApiError` 两组，(e) 断言调用顺序与忙碌文字；X1–X3、X7、X9–X11、X15、X17 都被杀 |
| F8 | 见下 | 没有放宽 |
| G1 | `:2208-2213`、`:2264-2277`、`:2449-2466` | 重读视图恰好只比原视图多一个 `redo_started_at`（`:2271` 用 `==` 断言）；说明逐字是 `PLAN_DONE_AWAITING`；X9 被杀；复用这个夹具的 F7 自检仍然变红（测试通过即证明） |
| G2 | `:2216-2245`、`:2280-2319`、`:1748-1782`、`:2477-2593` | 不可用、已发起两种情况之后再点交留言，`note == 1`；重读失败后再点，`get == 2`；取消之后再点，`get == 2`、`confirm == 2`；四份坏副本自检；Y1–Y5 被杀 |
| G3 | `:2596-2647` | 桩在 abort 时 reject；断言 signal 已 aborted、setter 次数为 0、没有 confirm 和 POST；X13 被杀 |
| G4 | `:2296-2319`、`:2650-2687` | `TypeError("Failed to fetch")` 显示的提示逐字为「请求未完成，请稍后重试。」；X7 被杀 |
| G5 | `:884-885`、`:894`、`:908` | 断言含「在书斋打开」 |
| G6 | `:1088-1093`、`:2046-2085` | `stale` 段断言三项都是 None；`status<>'done'` 坏副本变红；X22、X23 被杀 |
| G7 | `:1456-1478`、`:2288-2374` | `running` 与 `novel_id` 为 NULL 两种情况都报 409「这张卡没有重新定稿的要求」，且无副作用；坏副本分别报「第 None 章…」「这本书已经删除」；Y6 被杀 |

**F8 以及 R2 改过的既有用例：没有放宽。** 依据是逐条比对两份 delta 中被删掉的 `-…assert` 行：

- `redo_confirmation_costs`：
  - R0 断言 `get == 0`，R1 改成 `get == 1`，R2 改成「取消后再点一次」，`get == 2`。
  - 三种费用的确认框正文仍然逐字比较；`redo == 0` 保持。
  - R2 改成断言 `confirmCalls == [expected, expected]`，每次点击仍只弹一次确认框。
- `redo_confirmed`、`note_success_then_redo`：只把 `get` 照实加 1，并新增 `len(confirmCalls) == 1`。
- `redo_error`：从 `get 1 / redo 1` 改成 `get 2 / redo 1`，并新增断言 signals 顺序为 `["get","redo","get"]`。这正好锁住「点击时重读 1 次、失败后再拉 1 次」。
- `unmount_aborts_pending_post`：删掉的两句读的是卸载前冻结的树，本来恒真（F6 的目标），改成了 setter 计数；`get == 0`（不再重新拉取）保留。
- R2 把 `assert marker in source` 统一改成 `source.count(marker) == 1`，更严。
- R2 把 `PLAN_NOT_AWAITING in text` 改成 `in paragraphs`，要求整段逐字相同，也更严。
- 被删掉的旧 F7(c) 夹具（等确认第 3 章），按 G1「删掉或并入 (b)」处理。
- 没有删掉任何 `def test_`。两份 delta 里出现的 `-def test_…`，同名函数都在 `+` 侧重写，并且只增不减断言。

## 5. §5 验收抽查

| # | 命令 | 结果 |
|---|---|---|
| 1 | `cd frontend && npx tsc --noEmit` | 无输出，`tsc_exit=0` |
| 2 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`。对新文件单独跑 eslint，无输出，退出 0 |
| 3 | build | 未重跑，采用派单方门禁的 `build_exit=0`。本轮前端产品代码只改了 `NovelFeedbackCard.tsx`，tsc 与 lint 都已通过 |
| 4 | `cd backend && … -m pytest -q -p no:cacheprovider -rs` | `8264 passed, 37 warnings in 376.82s`，0 skipped。8011 + 253 = 8264 |
| 5a | 三个新文件 | `253 passed`。`--collect-only` 计数为 131 + 113 + 9 |
| 5b | 无 `node_modules` 副本 | `SKIPPED [93]` + `SKIPPED [9]` = 102，`151 passed`。见 §2.3 |
| 6 | `git status --porcelain --untracked-files=all` | 20 个 `M`、15 个 `??`，都在白名单内或是派单方的文件。见 §3.4 |
| HEAD 对照 | 见 §2.3 | `212 failed, 41 passed`，失败全部是断言，没有 `FileNotFoundError` |

## 6. 必须修复项

无。

逐项排查过的三种情况：

- **上一轮的项没修好**：没有，见 §2。
- **R1、R2 的新代码违反规格**：没有，见 §3、§4。
- **R1、R2 的新代码导致错误行为、测试假绿或计费风险**：没有发现。
  - 确认框的费用句改为点击时重新读取的结果，比 R0 更准确。
  - 后端仍会核对章号与逐章确认。
  - P2 只会多拒绝，不会多扣费。

## 7. 可优化项（不阻塞合入）

1. **「重读后不可用 / 已发起」两条用例没有断言「没有错误提示」**。
   - 证据：变异 X5 在不可用分支额外执行 `setActionError({ section: "plan", … })`，前端新测试文件全绿，结果为 `96 passed, 17 deselected`，变异存活。
   - 规格只写了「卡片按新视图显示新状态，不弹确认框、不发请求」，所以这不算违反规格。
   - 建议在 `assert_redo_reread_unavailable` 与 `assert_redo_reread_started` 里各加一句 `assert reread["alerts"] == []`。
2. **可访问性**。派单方在 §9 v1.5 已经记下，留给作者裁定，这里只确认现象存在：
   - 重读后发现不可用时，被点击的按钮会从 DOM 中消失，焦点丢失，读屏也不会播报新的说明。
   - 可选修法：给第一节说明加 `aria-live="polite"`，或者在不可用时把焦点移到说明段。
3. **费用仍有很小的竞态窗口**。
   - 从重读完成到作者点「重新定稿」之间，如果作者在别处又改了主编模型，确认框里写的费用就会过时。
   - 后端的 `redo_feedback_plan` 不核对作者确认时看到的是哪一类费用。
   - 这个窗口已经从「卡片挂载以来」缩短到「确认框打开期间」，实际风险很低。
   - 如果要彻底消除，可以让前端把 `redo_cost` 一并 POST，后端不一致时返回 409。这需要改规格，由派单方决定。

## 8. 给实施方的返修指令

本轮判为通过，不需要返修。上面三条可优化项由派单方或作者决定是否另行安排。

## 9. 实验与还原记录

- **实验目录**：全部在仓库外的 `/tmp/r2rev/`。
  - `mutate.py`、`mutate2.py`：变异脚本，共 45 个变异。其中 17 个对应上轮的 14 个存活变异和 B19 / B33 / B33c，另 28 个是本人设计的 X / Y 系列；44 个被杀，只有 X5 存活。
  - `equiv.js`：服务端渲染等价性对照。
  - `docs_check.py`：D1–D4 逐字核对。
  - `head/`：HEAD 导出。
  - `nonode/`：无 `node_modules` 副本。
  - `r0comp/`：R0 版组件与灵敏度对照用的变异副本。
  - `r0rebuild/`：R0 全量 diff 重建。
- **变异的还原方式**：每次变异前用 `shutil.copy2` 备份四个产品文件，变异后拷回，并逐个核对 sha256，两批都输出了 `ALL RESTORED`。
- **门禁产物**：tsc 生成的、被 Git 忽略的 `frontend/tsconfig.tsbuildinfo` 已删除；没有跑 build，所以没有 `.next/` 和 `next-env.d.ts`。
- **结束时的核对**：见下。

---

**复核副本还原核对**（写完本文件后执行）：

- **跟踪文件改动**：`git diff HEAD --binary | cmp - .review/diff-r2.patch` 结果一致，两者 sha256 都是 `dacdb28c8dc9aeda81977160c387bc741c3d713ce925f775feefe854d7a7e569`。
- **未跟踪文件**：`.review/untracked-r2.txt` 列出的 15 个文件，sha256 与开工时记录的逐一相同。
  - 其中 `NovelFeedbackCard.tsx` 为 `ab1df49d…`，`feedback.py` 为 `5259707f…`，`test_novel_chat_feedback.py` 为 `cd83bfec…`，`test_novel_chat_feedback_frontend.py` 为 `7e41c5f3…`。
- **改动集合**：`git status --porcelain --untracked-files=all` 共 36 行，即原来的 35 行加上本文件 `?? docs/tasks/2026-11-12-novel-feedback/07-review-r2.md`。
- **被忽略的文件**：`git status --ignored` 只剩开工时的 `.review/`、`backend/.venv/`、`frontend/node_modules/` 三项。tsc 生成的 `tsconfig.tsbuildinfo` 已删除。
- **仓库外临时目录**：`/tmp/r2rev/` 已整体删除，删除前核对过它的实际路径是 `/private/tmp/r2rev`。
  - 目录里指向 `.venv`、`node_modules` 的两个软链接只删了链接本身，工作区里的 `backend/.venv/bin/python` 和 `frontend/node_modules/typescript/package.json` 仍在。
