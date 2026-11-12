# 04 独立复核：修改意见卡（规格 v1.3）

- 复核对象：复核副本 = 基线 `7a17f64` + 未提交改动（20 个 `M`、10 个 `??`）。快照文件实际名为 `.review/diff-r0.patch`（简报里写的是 `.review/diff.patch`），未跟踪清单为 `.review/untracked-r0.txt`。
- 依据：只按 `docs/tasks/2026-11-12-novel-feedback/02-spec.md`（v1.3）。实施方报告只当线索用，下文结论都来自本人在副本里重新跑的命令和实验。
- 环境：pytest 一律 `backend/.venv/bin/python -m pytest -p no:cacheprovider`，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`（下文省略）。没有联网，没有读 `.env`，没有执行 commit、stash、checkout、reset。

## 1. 结论：不通过（只需返修测试，产品代码没有发现必须改的地方）

- **实现本体**：T1–T7、§4.4 文档、§8 案头三处小修逐条核对，与规格一致。
  - 文案逐字核对过：工具常量与规格代码块 `==` 比较为 True，卡片与回灌文案也逐句比对过。
  - 事务、幂等、回滚、归属、门控、计费都实测过，没有发现会多扣费、越权或留下半截状态的实现缺陷。
  - 门禁全绿，与派单方的结果一致：全量 8214 passed、0 skipped；tsc 0；lint 0 errors / 25 warnings；build 0。
- **不通过的原因**：有 3 项必须修复，都是测试问题。
  - 2 项是关键分支的变异存活：规格要求的行为在错误实现下测试照样全绿，正好是规格最强调的「不对作者说错话」和「章号对不上」两处。
  - 1 项是 14 条前端新功能用例在 HEAD 上以 `FileNotFoundError` 失败，而规格要求以 `AssertionError` 失败。
- **派单方已知的 B19、B33**：按目前描述的修法只补「500 字」和「写死 0」不够，同类的边界变异还有 4 个也会存活，见 §3.4。

## 2. §5 验收标准逐条核验

| # | 标准 | 命令 / 做法 | 结果 |
|---|---|---|---|
| 1 | tsc 退出 0 | `cd frontend && npx tsc --noEmit; echo $?` | 无输出，`tsc_exit=0` ✅ |
| 2 | lint 0 errors、warnings ≤ 25 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`，退出 0。25 条全在 `app/page.tsx` 与 `app/plaza/page.tsx`，与基线相同。另单独对 7 个新增或改动的前端文件跑 `npx eslint …`：无输出，退出 0 ✅ |
| 3 | build 退出 0 | `cd frontend && npm run build` | 路由表正常输出，`build_exit=0`；`tsconfig.json` 构建前后 sha 不变 ✅ |
| 4 | 后端全量 0 failed、0 skipped，passed = 8011 + 新用例数 | `cd backend && … -m pytest -q -p no:cacheprovider -rs` | `8214 passed, 37 warnings in 376.91s`，退出 0。收集数：`--collect-only -q` 三个新文件依次 110 + 84 + 9 = 203；8011 + 203 = 8214 ✅ |
| 5a | 三个新文件 0 failed、0 skipped | `… pytest -q -rsf tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py tests/test_desk_polish_frontend.py` | `203 passed` ✅ |
| 5b | 无 `node_modules` 副本：0 failed，skip 数等于起 node 的用例数 | `rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' ./ /tmp/review-nonode-copy/` 后在副本跑同一命令 | `SKIPPED [64] tests/test_novel_chat_feedback_frontend.py:63: frontend dependencies unavailable: typescript, react, react-dom/server`；`SKIPPED [9] tests/test_desk_views_frontend.py:36: frontend dependencies unavailable: typescript, react, react-dom/server`；`130 passed, 73 skipped`。前端新文件 84 条中 20 条在守卫之前（4 条 skip 守卫自检、1 条源码约束、11 条坏副本、2 条 page、2 条路由），所以起 node 的是 84 − 20 = 64 条；案头 9 条全部起 node。64 + 9 = 73 ✅ |
| 6 | 改动集合都在白名单内；`backend/tests` 只有三个新文件和一个 M；授权文件恰 2 个 hunk 且单独跑全绿 | `git status --porcelain --untracked-files=all`；`… -- backend/tests`；`git diff -U0 HEAD -- backend/tests/test_studio_sources_readonly_integration.py \| grep -c '^@@'` | 20 个 `M`（6 份文档含 `.env.example`、7 个后端源码文件、1 个授权测试、6 个前端文件）、10 个 `??`（`feedback.py`、3 个新测试、2 个前端新文件、`01-brief`、`02-spec`、`03-dispatch`、`impl/report.md`），全部在 §4.1 白名单或派单方文件之内。`03-dispatch.md` 是派单方文件，§5.6 的例外里没点名，报告已说明。`backend/tests` 只有 ` M test_studio_sources_readonly_integration.py` 和三个 `??`；hunk 数 = `2`，内容正是 §4.5 (a)(b)；该文件在第 7 条的合跑中全绿 ✅ |
| 7 | 23 个既有文件单独跑全绿 | 规格列出的 23 个文件加上授权文件，一次合跑 | `578 passed, 37 warnings in 65.97s` ✅ |
| 8 | 计数 | `grep -c …`、`head -c 3 … \| xxd -p`、`git diff HEAD --stat -- …` | `ALTER TABLE messages ADD COLUMN novel_feedback_id` = 1；`FIONA_NOVEL_CHAT_FEEDBACK` 在 sources.py、.env.example、CLAUDE.md 各 1；`draft_novel_feedback` 在 claude_agent.py 中 = 2；BOM = `efbbbf`；desk 目录的 stat 只列 `DeskChaptersView.tsx`、`DeskDialogs.tsx`、`DeskEpisodesView.tsx` 三份；`lib/desk.ts`、`components/novel`、`lib/novels.ts`、`NovelDraftCard.tsx` 的 stat 为空 ✅ |
| 9 | 开关为 0 时工具集合不变 | `test_switch_matrix_off_values_match_head`（5 组 × CREATE{未设,1} × FEEDBACK{未设,0,true}） | 本副本 30 passed。另在 HEAD 副本上（见下）这 30 条同样通过 ✅ |

### 补充核验

- **HEAD 对照**（派单方的工作，这里顺手做了，供参考）：
  - 做法：`git archive HEAD | tar -x -C /tmp/review-head`，`.venv` 与 `node_modules` 用软链接接入，再拷入三个新测试文件后运行。
  - 结果：`162 failed, 41 passed`。
  - 回归类用例在 HEAD 上通过：开关矩阵 30 条、`test_note_route_behavior_unchanged`、`test_redo_plan_route_behavior_unchanged`、skip 守卫自检 4 条，另有 5 条案头 O3 参数用例在 HEAD 上本来就成立。
  - 新功能类用例中，147 条以 `AssertionError` 失败，**另有 14 条以 `FileNotFoundError` 失败**，见 MF-3。
- **老库升级**：
  - 做法：在临时库里先只建最小的 `messages` 表，再连续调用两次 `database.init_db()`。
  - 结果：`messages.novel_feedback_id` 恰好 1 列；`novel_feedback`、`idx_novel_feedback_owner` 存在；`schema_migrations` = 5。
  - 结论：幂等成立，迁移版本没有增加。

## 3. 必须修复

### MF-1 「已被细纲读到」只测了 `awaiting_plan_approval`，`planning` / `writing` 两种状态写错也测不出来

- **位置**
  - 实现：`backend/novel/service.py:540`（`status IN ('awaiting_plan_approval','planning','writing')`）。
  - 测试：`backend/tests/test_novel_chat_feedback.py:931-967`（`test_feedback_view_planned_read_from_in_progress_meeting`，只造了 `awaiting_plan_approval` 一种状态），以及 `:970-1005` 的 HTTP 用例（只观察停在等确认的那一刻）。
- **证据（变异实验，改完都已还原，脚本见 §6）**

  | 变异 | 改动 | 新测试结果 |
  |---|---|---|
  | M4 | `IN ('awaiting_plan_approval','planning','writing')` 改成 `IN ('awaiting_plan_approval','planning')` | `110 passed`，存活 |
  | M5 | 改成 `IN ('awaiting_plan_approval')` | `110 passed`，存活 |

  - 现实现本身是对的：临时实验 E3 造了一行「第 2 章 `writing`、brief 含 `N1`」的库，`feedback_view` 返回 `planned_chapter == 2`、`planned_adopted is True`、`planned_response == '好'`。
- **后果（变异 M4 下）**
  - 场景是 §2.1 的典型流程：作者交出留言，批准第 K 章，第 K+1 章细纲读到了这条留言，作者再批准第 K+1 章，第 K+1 章进入 `writing`。
  - 此时卡片的 `planned_chapter` 会变成 None，走到 T6.4 第 3 支的「其余」，对作者说「编辑部会在下一次为新的一章规划细纲时读到这条要求；那一章写完后，这里会显示编辑部的回应。」
  - 实际上留言已经被第 K+1 章用掉，这正是 v1.1 修订要消除的说错话（§9 中的 L3/B1/F2/E2/P1/P12）。测试目前护不住这个修复。
- **建议改法**
  - 把 `test_feedback_view_planned_read_from_in_progress_meeting` 的章节状态参数化为 `awaiting_plan_approval` / `planning` / `writing` 三种，每种都断言 `planned_chapter == K`、`planned_adopted`、`planned_response` 逐字；`done` 不算的那条反例保留。
  - 可以另加一条坏副本自检：把 `'writing'` 从 IN 列表里删掉后，同一个检查函数必须变红。

### MF-2 前端没有「书在等确认、但等的不是卡上这一章」的用例；按钮与「新细纲在书斋里等你确认」不核对章号也测不出来

- **位置**
  - 实现：`frontend/components/NovelFeedbackCard.tsx:199-203`（T6.3 第 3 支：`status === "awaiting_plan" && awaiting_chapter === N && automation === "per_chapter"`）、`:193`（T6.3 第 1 支「其余」里「新细纲在书斋里等你确认。」的追加条件）、`:207`（第 4 支）。
  - 测试：`backend/tests/test_novel_chat_feedback_frontend.py:732-814` 的 `PLAN_CASES`。所有 `status="awaiting_plan"` 的用例都用 `make_book()` 默认的 `awaiting_chapter=PLAN_CHAPTER`，没有一条 `awaiting_chapter ≠ plan_chapter`。
- **证据（变异实验，已还原）**

  | 变异 | 改动 | 前端测试结果 |
  |---|---|---|
  | M15 | 删掉 `:201` 的 `&& book.awaiting_chapter === chapter`，任何等确认的章都显示按钮 | `84 passed`，存活 |
  | M14 | 删掉 `:193` 的 `&& book.awaiting_chapter === chapter` | `84 passed`，存活 |

- **后果（变异 M15 下）**
  - 场景：作者在书斋批准了第 N 章，书现在停在等确认第 N+1 章。
  - 卡片仍然显示付费按钮「带着这些要求重新定稿」，确认框会告诉作者「重新写一版第 N 章细纲……按实际用量扣草莓」。
  - 后端 `expected_chapter` 会以 409 拒绝，所以不会扣错钱；但卡片把会错的章号写给了作者，并弹出了收费确认，违反 §1、§3.5「绝不把第 N 章的意见用到第 N+1 章」。
  - M14 下，卡片会把第 N+1 章的待确认细纲说成「新细纲在书斋里等你确认」，暗示它是按这张卡重定的第 N 章。
- **建议改法**：在 `PLAN_CASES` 加至少两条，并用已有的互斥句子检查锁住。
  1. 不发起重新定稿：`book=make_book(awaiting_chapter=PLAN_CHAPTER + 1, plan_row_status="done")`，`automation` 保持 `per_chapter`。期望走第 10 支「第 2 章细纲已经不在等你确认了，这一项不能再用。」，既没有「带着这些要求重新定稿」也没有「去书斋改细纲」。
  2. 已发起重新定稿：`redo_started_at` 有值、`redo_pending=False`、`awaiting_chapter=PLAN_CHAPTER + 1`。期望只出现 `PLAN_DONE`，全文不含「新细纲在书斋里等你确认。」。

### MF-3 14 条前端新功能用例在 HEAD 上以 `FileNotFoundError` 失败，不是规格要求的 `AssertionError`

- **规格要求**
  - §4.5：「两个新测试文件在 HEAD 上都必须能被收集……新功能类用例开头调用 `_require_feedback()`」。
  - §5 HEAD 对照：「新功能类用例在 HEAD 上必须以 `AssertionError` 失败，由 `_require_feedback()` 守卫」。
- **位置**：`backend/tests/test_novel_chat_feedback_frontend.py:1453-1731`。这些用例在调用 `_require_feedback()` 之前（守卫在 `run_interaction` / `run_request_paths` 里面），先执行了 `source = read(COMPONENT)` 或 `read(FEEDBACK_LIB)`。
- **证据**
  - 在 HEAD 副本上用 `--junitxml` 跑前端新文件，以下 14 条的 failure message 都是 `FileNotFoundError: … NovelFeedbackCard.tsx`（最后两条是 `lib/novelFeedback.ts`）：
    - `test_feedback_card_note_click_disables_both_actions_while_pending`
    - `test_feedback_card_redo_confirmation_costs[strawberries|own_model|free]`
    - `test_feedback_card_redo_confirmed_calls_once_and_updates_view`
    - `test_feedback_card_note_success_then_redo_click_confirms_once`
    - `test_feedback_card_action_error_alerts_and_refetches_once`
    - `test_feedback_card_read_states_and_retry`
    - `test_feedback_card_note_error_then_success_clears_alert`
    - `test_feedback_card_redo_error_alerts_and_refetches_once`
    - `test_feedback_card_unmount_aborts_pending_post_without_refetch_or_alert`
    - `test_feedback_card_own_model_fee_copy_self_check`
    - `test_novel_feedback_request_paths_and_signal_passthrough`
    - `test_novel_feedback_request_path_self_check_catches_plan_redo`
  - 其余 147 条新功能类失败都是 `AssertionError`。
- **建议改法**：在这 14 条用例里，紧跟 `require_node_dependencies()` 之后、`read(...)` 之前先调用 `_require_feedback()`。也可以把 `read(COMPONENT)` / `read(FEEDBACK_LIB)` 收进一个先调用 `_require_feedback()` 的小函数。注意 `_require_feedback()` 必须放在依赖守卫**之后**，这样无 `node_modules` 副本的 skip 数仍是 64。

### 关于派单方已知的 B19 / B33：按目前的描述修，范围不够

- **B19（只补「恰 500 字通过」）**：同类边界变异还有 3 个也存活（已实测并还原）。

  | 变异 | 位置 | 改动 | 后端新测试结果 |
  |---|---|---|---|
  | B19a | `backend/novel/feedback.py:55` | `current_plan` 的 `> TEXT_MAX` 改 `>=` | `110 passed` |
  | B19b | `:89` | `issue` 的 `> ISSUE_MAX` 改 `>=` | `110 passed` |
  | B19c | `:72` | `written_chapters` 的 `> WRITTEN_MAX` 改 `>=` | `110 passed` |

  返修应补齐四个边界的正样本，每个都断言 `error is None`：`next_chapters` 恰 500 字（含首尾空白，去空白后 500）、`current_plan` 恰 500 字、`issue` 恰 200 字、`written_chapters` 恰 10 条。
- **B33（`pending_notes` 写死 0）**：变异 B33b 把 `service.py:526` 的计数去掉 `status='pending'` 条件后，测试同样 `110 passed`。返修用例除了断言 `pending_notes == 2`（两条 pending）以外，库里还要同时放一条本书的 `delivered` 留言和一条**另一本书**的 pending 留言，确保只数本书的 pending。

## 4. 可优化项

1. **「K ≥ max_chapters 即最后一章」这一支，前后端都没有用例**。
   - 证据：变异 M1 删掉 `NovelFeedbackCard.tsx:228` 的 `|| (maxChapters !== null && awaitingChapter >= maxChapters)`，前端测试 `84 passed`；变异 M2 把 `services/claude_agent.py:833` 的 `(F or (M is not None and K >= M))` 改成 `F`，后端测试 `110 passed`。
   - 影响：在现有状态机里，第 K = max_chapters 章处于 final 模式，`schemas.py:494-495` 强制 `ending_status == "end"`，所以 F 基本覆盖了这种情况，实际影响很小。但这是 v1.2 明确加入的判断。
   - 建议：前端加一条 `awaiting_chapter == max_chapters`、`awaiting_is_final=False` 的 SSR 用例，后端加一条成功路径用例。
2. **`busyRef` 防重入没有被真正测到**。
   - 证据：变异 M3（删 `NovelFeedbackCard.tsx:109`）和 M3b（删 `:138`）均 `84 passed`。现有交互用例只点一次，所以「恰调用一次」对去掉守卫的实现也成立。
   - 影响：后端两个接口都幂等，没有数据或计费风险。
   - 建议：加一个同步连点两次的场景，第二次点击发生在重渲染之前，断言 `calls.note == 1`、`confirmCalls.length == 1`。
3. **确认框返回之后的 abort 判断没有测到**（变异 M7 删 `:144`，`84 passed`）。建议加一个「确认框打开期间卸载」的场景。
4. **卸载用例里的「不出现 `role="alert"`」是恒真断言**。
   - 原因：迷你运行时 `unmount()` 后 `flush()` 直接 return，`lastTree` 冻结在卸载前，所以 `after["alerts"] == []` 不可能失败（`test_novel_chat_feedback_frontend.py:1137-1139`、`:1640`）。
   - 实际起作用的是 `calls.get == 0` 那条。
   - 建议：改成记录卸载后 setState / schedule 的调用次数，或者删掉这条断言并在注释里说明。
5. **`validate_feedback_args` 的 `chapter <= chapters_done` 条件没有测到**（变异 M6 删 `feedback.py:67` 的 `or number > chapters_done`，`110 passed`）。建议造一条「状态为 `done`、章号大于 `chapters_done`」的反例。
6. **纵深防御**：`redo_feedback_plan` 遇到 `plan_chapter IS NULL`、但 `current_plan` 非空的卡，会跳过章号核对。
   - 实验 E4：用 SQL 造了这样一张卡，书正等确认第 3 章，调用后直接对第 3 章发起了重新定稿（`redo_started_at` 有值、桩被调用 1 次、第 3 章 `planning`）。
   - 正常建卡路径到不了这种状态：`validate_feedback_args` 保证 `current_plan` 非空时 `plan_chapter` 一定有值。
   - 按规格字面实现也没有错。可以考虑 `plan_chapter is None` 时直接 409，但这偏离规格字面，由派单方决定。
7. **确认框里的费用可能已经过时**。这是规格层面的问题，供派单方或作者参考。
   - 卡片不轮询，而 `service.patch` 允许在 `awaiting_*` 时修改 agents（`service.py:826-830`）。
   - 作者先在书斋把主编从「我的模型」改成平台模型，再回到旧卡片点重新定稿：确认框仍写「重新定稿不扣草莓，但会用掉你自己的模型额度」，实际会扣草莓。
   - `automation` 的变化后端会拦住，费用的变化不会。
   - 可选修法：点按钮时先 `getNovelFeedback` 拿到新视图，再按新的 `redo_cost` 弹确认框，新视图已不可用就不弹。
8. **建卡后才计算 `awaiting_is_final`**。`novel/feedback.py:168` 先 `commit` 插入，再在同一连接里查 meeting。如果查询抛错，工具会回「修改意见卡暂时不可用」，但卡片行已经留在库里，变成孤儿行。概率极低，建议先算 `awaiting_is_final` 再提交。
9. **文档细节**
   - `PLAN.md:519`「章号对不上、不是逐章确认或卡片已发起过都拒绝」：已发起过的卡实际是 200 幂等返回现状，不是拒绝。建议改为「同一张卡重复点击不会再次发起」。
   - `docs/DEPLOYMENT.md:584` 列举启动时的兼容 DDL，没有列出 `novel_drafts` / `novel_feedback` 两表和 `messages.novel_draft_id` / `novel_feedback_id` 两列。`novel_draft_id` 在基线时就漏了，报告把这处列为「未改」。这一段面向部署者，建议补上。
   - §4.4.2 要求「在报告里列出改过的每一处」。`impl/report.md` 只概括写了「ARCHITECTURE 多处历史陈述」，没有逐处列出。实际改动位置：`ARCHITECTURE.md:21/54/137/141/324/328/418`、`CLAUDE.md:30/198`、`README.md:142/369`、`PLAN.md:23/515-523`、`DEPLOYMENT.md:257/866-870`、`.env.example:47/211-212`。

## 5. 其余核对记录（均已通过）

- **T1 表与落库**
  - DDL 与规格逐字相同；`init_db` 无条件建表、建索引、补列。
  - `save_message` 的归属核对块位于写歌块之后、`# 书斋草稿归属同样只做附加校验` 之前；INSERT 的列、占位符、参数三处同步。
  - 清空历史、删号、删会话都在同一事务内删卡；删书在同一事务内置 NULL。
- **T2 `validate_feedback_args` / `create_feedback`**
  - 三段检查的顺序、去重、`bool` 排除、`written` 保序与章名、`automation` / `max_chapters` 的缺省都符合规格。
  - 模块顶层没有 import `novel.service`。
- **T3 书斋侧**
  - `note()`、`redo_plan()` 只改为调用抽出的函数，对外行为不变；回归用例在 HEAD 与本副本上都通过，既有 p1/v2/r2 测试全绿。
  - `feedback_view` 的键集合、`planned_*` 算法、`redo_cost` 三态都与规格逐项一致。
  - `send_feedback_note` / `redo_feedback_plan` 的判断顺序与规格一致；`start_novel` 只在提交后、只在本次真正发起时调用。
- **回滚实验 E1**
  - 同一用户另一本书在 `running` 时，对等确认的书调用 `redo_feedback_plan`，返回 409「每个用户同时只能运行一本小说」。
  - 这时 `_begin_redo` 里改章节状态的 UPDATE 已经执行，异常在 `_activate` 处抛出。实验后：章节行与 `novels` 行逐字不变，`redo_started_at` 仍为 NULL，桩未被调用。
  - 让另一本书暂停后重试，恰好发起 1 次。
- **并发**：两个并发重新定稿只发起 1 次，两个并发交留言只插 1 条留言，现有用例都覆盖并真实执行。变异 M19（去掉 `redo_started_at` 幂等判断）、M20（已发起时仍启动 runner）都被杀死。
- **归属与门控（实验 E2）**
  - 别人的卡片：GET、POST note、POST redo 三个接口都返回 404「修改意见不存在」。
  - `FIONA_NOVEL_CHAT_FEEDBACK=0` 时卡主仍然 200。
  - 账号不在 `FIONA_NOVEL_USERS` 时三个接口都是 403；`FIONA_NOVEL=0` 时 404。
  - 三个新路由都在 `/{novel_id}` 之前，POST 带 `request: Request` 和 `20/minute`。
- **T4 Claude 工具**
  - `NOVEL_FEEDBACK_TOOL` 与规格代码块 exec 结果 `==` 为 True；`CLAUDE_CLIENT_TOOLS` 仍是 5 个。
  - 追加位置、锚点行未改、每轮标志、执行分支、回灌六句都与规格一致。
  - 修改意见卡的 subtype 不在 `deskSubjectFromCard` 的处理范围内，不触发案头定位。
  - AST 锁和 `studio/**` 写库锁仍然全绿。
- **T5–T7 前端**
  - 卡片是单个函数组件，hooks 都在任何 return 之前，effect 里没有同步 `setState`，渲染时不读 ref。
  - 不加粗；没有 `<dialog`、原生 `confirm(` / `alert(`；只用 `text-fs-12/13/15`、`--ink2`、`--seal`。
  - 状态顺序与 T6.3 / T6.4 / T6.5 / T6.2 逐支对照一致（10 支、7 支、底部提示）。
  - 测试里的文案常量与规格逐句比对过；`page.tsx` 两个块各一行，BOM 保留；`toMessages` 三张卡片的顺序正确。
- **§8 案头小修**：O1、O2、O3 与规格一致，案头既有测试全绿。
- **文档**：六份文档只改了例外清单与规格指定的新增段落，没有本机绝对路径，`test_claude_agent_docs.py` 全绿。

## 6. 实验与还原记录

- **变异脚本**：`/tmp/review-mutate.py`，放在仓库外。
  - 每个变异先断言锚点在原文中恰好出现 1 次，然后改文件、跑相关的新测试文件（`-x`）、再从 `/tmp/review-backup/` 拷回原文件，并比对 sha。
  - 共做了 21 个变异：
    - 存活 14 个：M1、M2、M3、M3b、M4、M5、M6、M7、M14、M15、B19a、B19b、B19c、B33b。
    - 被杀 7 个：M16 不认 own_model、M17 交留言不查完结、M18 重新定稿不查逐章确认、M19 重新定稿不幂等、M20 已发起仍启动 runner、M26 不记 `state.novel_feedback_id`、M29 卸载不 abort。
- **临时实验用例**：E1–E4 写在 `backend/tests/test_zz_review_scratch.py`，跑完已删除。
- **HEAD 对照与无 `node_modules` 副本**：都在仓库外，分别为 `/tmp/review-head`、`/tmp/review-nonode-copy`。
- **结束时的核对**：见文末。

## 7. 给实施方的返修指令（可直接转发）

> 修改意见卡（规格 v1.3）独立复核：产品代码不用改，返修只涉及两个新测试文件 `backend/tests/test_novel_chat_feedback.py` 和 `backend/tests/test_novel_chat_feedback_frontend.py`。不要改任何既有测试，也不要改产品代码。每条新增断言都必须能区分对错实现：写完后请自己把对应的产品代码临时改坏，确认测试变红，再改回来，并在报告里贴出变红的输出。
>
> 1. **「已被细纲读到」覆盖三种进行中状态**（`novel/service.py:540` 的 `status IN ('awaiting_plan_approval','planning','writing')`）。
>    - 把 `test_feedback_view_planned_read_from_in_progress_meeting` 的章节状态参数化为 `awaiting_plan_approval`、`planning`、`writing`。
>    - 每种都断言 `planned_chapter == K`、`planned_adopted is False`、`planned_response` 逐字；原来「meeting 损坏」「done 不算」两条保留。
>    - 自检：把 IN 列表删成只剩 `'awaiting_plan_approval','planning'` 时必须变红；只剩 `'awaiting_plan_approval'` 时也必须变红。
> 2. **前端「等确认的不是卡上这一章」**。在 `PLAN_CASES` 加两条：
>    - (a) `plan_chapter=2`、`redo_started_at=None`、`book=make_book(awaiting_chapter=3, plan_row_status="done")`（逐章确认，书停在等确认第 3 章）：说明逐字为「第 2 章细纲已经不在等你确认了，这一项不能再用。」，没有「带着这些要求重新定稿」和「去书斋改细纲」按钮。用 `open_novel=True` 渲染，确保按钮缺失不是因为没传 onOpenNovel。
>    - (b) `redo_started_at` 有值、`book=make_book(redo_pending=False, awaiting_chapter=3)`：标签「已发起重新定稿」，说明只有「已经带着这些要求重新定稿过第 2 章细纲。」，全文不含「新细纲在书斋里等你确认。」。
>    - 自检：删掉 `NovelFeedbackCard.tsx` 中第 3 支的 `&& book.awaiting_chapter === chapter`，(a) 必须变红；删掉第 1 支「新细纲在书斋里等你确认」追加条件里的 `&& book.awaiting_chapter === chapter`，(b) 必须变红。
> 3. **HEAD 守卫**。以下 14 条用例在 `require_node_dependencies()` 之后、第一次 `read(COMPONENT)` 或 `read(FEEDBACK_LIB)` 之前加 `_require_feedback()`：
>    - `test_feedback_card_note_click_disables_both_actions_while_pending`
>    - `test_feedback_card_redo_confirmation_costs`
>    - `test_feedback_card_redo_confirmed_calls_once_and_updates_view`
>    - `test_feedback_card_note_success_then_redo_click_confirms_once`
>    - `test_feedback_card_action_error_alerts_and_refetches_once`
>    - `test_feedback_card_read_states_and_retry`
>    - `test_feedback_card_note_error_then_success_clears_alert`
>    - `test_feedback_card_redo_error_alerts_and_refetches_once`
>    - `test_feedback_card_unmount_aborts_pending_post_without_refetch_or_alert`
>    - `test_feedback_card_own_model_fee_copy_self_check`
>    - `test_novel_feedback_request_paths_and_signal_passthrough`
>    - `test_novel_feedback_request_path_self_check_catches_plan_redo`
>
>    改完后，在基线 `7a17f64` 的只读导出（例如 `git archive 7a17f64 | tar -x -C <dir>`，再软链 `.venv` 与 `node_modules`、拷入新测试）上跑这个前端新文件：所有新功能类失败都必须是 `AssertionError`，不得出现 `FileNotFoundError`。无 `node_modules` 副本的 skip 数仍须为 64 + 9 = 73。
> 4. **B19 边界（扩大范围）**。四个上限各加一条「恰好等于上限时通过」的正样本，都断言 `error is None` 并核对返回值：
>    - `next_chapters` 恰 500 字（前后再加空白，去空白后 500）；
>    - `current_plan` 恰 500 字（书为 `awaiting_plan`、逐章确认、有等确认章）；
>    - 某条 `issue` 恰 200 字；
>    - `written_chapters` 恰 10 条（10 个已写好的章）。
>
>    自检：分别把 `feedback.py` 中这四处的 `>` 改成 `>=`，对应用例必须变红。
> 5. **B33（扩大范围）**。新增一条 `feedback_view` 用例：本书有 2 条 pending 留言、1 条 `delivered` 留言，另一本书有 1 条 pending 留言，断言 `book["pending_notes"] == 2`。自检：计数写死为 0，或者去掉 `status='pending'` 条件，都必须变红。
> 6. （可选，推荐）
>    - 前端加一条 SSR 用例：`awaiting_chapter=50`、`max_chapters=50`、`awaiting_is_final=False`、只有 `next_chapters`、`note=None`，说明是「第 50 章会是这本书的最后一章…」，全文不含「第 51 章」。后端成功路径加一条对应用例（第 K 章 `ending_status` 为 `continue`、`K == max_chapters`）。
>    - 交互测试加一个「同步连点两次」的场景，第二次点击在重渲染之前，断言 `sendNovelFeedbackNote` 只被调用 1 次、`confirm` 只被调用 1 次。
>    - 卸载用例里「不出现 role=alert」的断言在迷你运行时下恒真，可以删掉或改成可证伪的检查。
>    - 报告里逐处列出六份文档改过的位置。
>    - `PLAN.md` 中「卡片已发起过都拒绝」改为「同一张卡重复点击不会再次发起」。这一句在白名单文档内，只改这一处措辞。
>
> 完成后重跑 §5 第 1–9 条，在报告里贴出：后端全量 passed 数（= 8011 + 新的收集数，0 skipped）、三个新文件的收集数、无 `node_modules` 副本的 SKIPPED 行，以及上面每个自检的变红输出。

---

**复核副本还原核对**（写完本文件后执行）：

- `git diff HEAD --binary | cmp - .review/diff-r0.patch`：一致，两者 sha256 均为 `77d66fad5fa94bcbf9f13b05defe9881a7bc48f9e35f0270d6961e92f813f230`。
- `.review/untracked-r0.txt` 中 10 个未跟踪文件的 sha256 与复核开始时逐一相同。
- `git status --porcelain --untracked-files=all` 共 31 行：原来的 30 行，加上本文件 `?? docs/tasks/2026-11-12-novel-feedback/04-review.md`。
- 实验用的 `backend/tests/test_zz_review_scratch.py` 已删除。变异过的 4 个产品文件 sha1 与备份一致。
- 门禁运行生成的、被 Git 忽略的构建产物（`frontend/.next/`、`frontend/next-env.d.ts`、`frontend/tsconfig.tsbuildinfo`）已删除，`git status --ignored` 恢复为开始时的 `.review/`、`backend/.venv/`、`frontend/node_modules/` 三项。仓库外的 `/tmp/review-head`、`/tmp/review-nonode-copy` 与备份目录也已清理；变异脚本 `/tmp/review-mutate.py` 保留，供派单方复跑（复跑前需重建 `/tmp/review-backup/` 备份）。
