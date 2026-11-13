# 独立复核：短片工作室「边写边拆」（续拆）r0

- 复核对象：基线 `135253f` + 未提交改动（`git diff` 与 `scratchpad/review-serial-materials/diff-r0.patch` 逐字节一致，已用 `cmp` 核对），以及三个新测试文件 `backend/tests/test_studio_serial_{sources,continue,frontend}.py`。
- 依据：`02-spec.md` v1.1。实现方报告 `impl/report.md` 只作线索，下面的结论都来自我自己跑的命令、差分和变异实验。
- 复核方式：只有我一个人做，没有派子代理。实验时临时改过的文件和探针都已还原或删除，见 §7。

## 1. 结论：不通过

**实现代码我没有找到违反规格的错误。** 我逐条对照了 §3、§4.2–§4.5，又做了两项差分：`batch_plan` 默认参数与基线比 300 组随机输入，输出逐字节相同；未续拆拆解的 `_insert_bible` 与基线函数比 138 次真实调用，结果完全相同。所有门禁都是绿的。

不通过的原因在测试和报告：

- 有几条新测试证明不了它要证明的事。四个关键点的变异（读原文用错快照、partial 时照样发布、退役循环不跳过冻结条目、续拆确认不走 `_confirmed_quote`）改坏以后，新测试仍然全绿。
- 报告缺少验收 §5.8 要求的「文档改动位置」。

这些必须修复项（§3）都只需要改测试或报告，不用改实现代码。

## 2. 验收 §5 逐条核验

| § | 结果 | 我跑的命令与关键输出 |
|---|---|---|
| 5.1 | 通过 | `cd frontend && npx tsc --noEmit` → `TSC_EXIT:0` |
| 5.2 | 通过 | `cd frontend && npm run lint` → `✖ 25 problems (0 errors, 25 warnings)`，`LINT_EXIT:0`；告警只在 `app/page.tsx`（24 条）和 `app/plaza/page.tsx`（1 条），本次新增和改动的文件没有告警 |
| 5.3 | 通过 | `cd frontend && npm run build` → `BUILD_EXIT:0`（日志里只有 Node 的 `DEP0205` 弃用提示） |
| 5.4 | 通过 | `cd backend && NO_PROXY=… no_proxy=… .venv/bin/python -m pytest -q -p no:cacheprovider -rs` → `8343 passed, 37 warnings in 406.56s`，`EXIT:0`，日志里 `SKIPPED` 0 行。8343 = 8264 + 79；`--collect-only` 三个新文件共 `79 tests collected`（23 + 35 + 21） |
| 5.5 | 通过 | 用 rsync 做了一份不含 `frontend/node_modules` 和 `.next` 的副本，只跑三个新文件：`58 passed, 21 skipped`，每行 skip 原因都是 `SKIPPED [21] … frontend dependencies unavailable: typescript, react, react/jsx-runtime, react-dom/server`。前端新文件 21 个用例都要起 node，数目对得上。副本已删除 |
| 5.6 | 通过 | `git status --porcelain --untracked-files=all` 里的改动都在 §4.1 白名单内。既有测试只改了 5 个文件，我逐个函数比对过，都在 §4.6 第 1 条授权范围内，见 §2.1 |
| 5.7 | 通过 | `pytest tests/test_studio_sources.py::test_studio_sources_only_call_allowlisted_novel_functions tests/test_studio_sources_readonly_integration.py::test_chat_novel_access_cannot_import_or_call_writer_functions` → `2 passed` |
| 5.8 | **不通过** | 报告里没有「文档改动位置」逐处清单（§4.7 要求「在报告里列出改过的每一处」）。报告第 280 行声称已经包含，但正文只写了「四份文档…陈述改对」。见必须修复项 MF5 |

另外两项差分（不属于 §5，用来核对「默认行为不变」）：

- **T2 `batch_plan` 默认参数逐字节不变**：把基线 `breakdown_material.py`（`git show 135253f:…`）作为独立模块加载，随机生成 300 组输入。覆盖小说和次要来源两种，1–35 章，正文 50–50000 字（含超过 24000 字被切成片段的章），有的章带细纲、有的不带。两边 `json.dumps(batch_plan(manifest, entries))` 全部相同：`IDENTICAL 300`。
- **未续拆拆解的 `_insert_bible` 与基线一致**：写了一个 pytest 插件，把 `breakdown._insert_bible` 换成一个包装。拆解没有 `_continuations` 时，先在 `SAVEPOINT` 里跑一遍基线函数，记下 `studio_bible` 行和 `imported`，回滚到 savepoint 后再跑新函数，两边比较。跑 `test_studio_breakdown_*.py`、`test_studio_casting_*.py`、`test_studio_serial_continue.py`，结果 `392 passed`，`DIFF_STATS 138 41 0`：比较了 138 次未续拆调用，0 处不同；另有 41 次续拆调用跳过。

### 2.1 既有测试改动逐函数核对（§4.6 第 1 条）

| 文件::函数 | 授权内容 | 实际 |
|---|---|---|
| `test_studio_sources.py::test_eligibility_rejects_with_reason` | 六个参数 id 与签名不变；running/planning/stale 改成断言可以建项目（经 `novel_project` 断言 201）；planning 换成真实形状的第 3 章，并断言 manifest 只有 1–2 章、`range_calls == [(1, 2)]`；stale 两边都设，并断言 manifest 第 1 章 `status == 'stale'`；bible、editing 仍断言 409；empty 改输入、改期望子串 | 一致。parametrize 列表没动，只改了函数体 |
| `::test_candidate_flags_projects_and_exact_title_search` | 最后一步加 `chapters_done=0, chapters=[]`，补 `reason` 断言 | 一致 |
| `::test_consistent_snapshot_retries_once` | 扰动改成 `bible_version + 1`，保留 `details == 4` 和读两轮，末行断言 `bible_version == 4` | 一致 |
| `::test_continuous_change_rejected` | 扰动改成 `100 + details` | 一致 |
| `::test_sync_rejects_ineligible_and_busy_brain` | 前半段改成 `bible=None` 并期望「故事圣经」，然后恢复；后半段不动 | 一致 |
| `::test_drift_detect_sync_archive_and_delete_source`（原 `:243`） | 补 `'stale': [], 'chapters_done': 3` | 一致 |
| `test_studio_sources_frontend.py::test_incomplete_workbench_never_requests_studio` | 改成 `chapters_done=0` 的书不请求工作室 | 一致，另外加了 `chapters=[]` 让夹具自洽，原有三条断言都保留 |
| `test_novel_chat.py`（`:116`） | 复用分支期望 `["《春山》", "快照第 2 版", "已有项目，打开即可继续"]` | 一致 |
| `test_novel_chat_feedback.py` `WRITTEN_SENTENCE`、`test_novel_chat_feedback_frontend.py` `WRITTEN_DESCRIPTION` | 只改那半句 | 一致 |

没有放宽任何断言，也没有拆分或合并参数化用例。全量数字 8343 = 8264 + 79 也说明既有文件的收集数没变。

### 2.2 规格逐条对照（正确性）

- **T1（`sources.py`）**：
  - 资格判断只剩三条，按规格顺序：圣经 → `chapters_done ≥ 1` → `is_editing` 或 `_rearchive`；不再看书的 status。
  - `_all_chapters` 校验 `type is int` 且在 0–300，只读第 1 到 `chapters_done` 章。
  - `_signature` 按 §3 第 3 条实现，只取章号 ≤ `chapters_done` 的章。
  - 漂移新增 `stale` 和 `chapters_done`；`source_status.snapshot.stale` 来自 manifest；候选新增 `stale`，`projects` 用 LEFT JOIN 取 `snapshot_chapters`。
  - 我额外核实了 `novel/service.edit_chapter`：改较早一章、而它后面的章已经全是 stale 时，正文变了，签名里的四项却都不变。这是规格 §3 第 3 条有意去掉 `updated_at` 的结果。单章正文是原子读取，读到改前或改后都对应某一个真实时刻，不算缺陷。
- **T2**：差分全部相同；偏移只在返回前统一加；次要来源传非默认参数时抛 `ValueError`。
- **T3 / T4**：
  - 报价拒绝的顺序和文案与规格一致。确认的五步校验顺序与规格逐字一致，全部在 `BEGIN IMMEDIATE` 里，之后才调 `_confirmed_quote`。
  - `_continued_import` 写入了全部 `_` 键：`_chapter_basis` 不覆盖已有章；`_published_max_seq` 和 `_frozen_bible_ids` 按「不存在 / 存在」分别处理；`_published_chunk_ids` 有兼容分支。
  - 旧批补记 `snapshot_no`；最后的 UPDATE 不碰 `settings_json`、`synopsis_json` 和项目行。
- **T4 第 6 步：总表沿用已有条目。** 规格点名的四种情形，在 `continue_start` 后和本轮新补全批成功触发 refresh 后，我都看过：
  - 书斋后来登记同名人物：并入原条目、补上 `ref_id`，不产生孤儿。
  - 作者改名：既有测试同时叠加了书斋登记。我另写探针单测「只改名、新批输出禾生」：只有一条活动行，id 不变。
  - 作者手建条目：并入手建行。
  - 多行重名：新建一行并写 warning。

  我又构造了一种更危险的情形：两条重名活动行里有一条是自动（uuid5）条目，并且已经定妆。实现靠 `_frozen_bible_ids` 跳过退役循环，没有写 `merged_into`，也不是孤儿（探针 `AUTO_AFTER_DRAIN None False`）。但新测试没有覆盖这种情形，见 MF3。

  未续拆拆解的行为由上面的 SAVEPOINT 差分证明与基线一致。
- **T5**：
  - `_source_inputs` 先用批自己记的快照号。
  - `_dependency_input` 在 round ≥ 1 时不写 `suggested_episodes`；本轮第一个分集批用已发布方案的末集；后续段取本轮上一批的输出。`prepare_job` 和 `retry_quote` 都走同一套逻辑。
  - 发布路径：`existing + new`，`_appended_from_unit` 取较小值，`_published_max_seq` 取 `MAX(seq)`，partial 不发布，退役不发布。
  - 取消守卫只放在 `cancel()` 里。整本 `start()` 在续拆 partial 时能取消未执行批并释放预留，已由新测试覆盖：qwen 与 claude 两组参数，都核对了日额度和月额度。
- **T6**：拆解视图新增的 8 个键、分集视图的 `continuing` 和 `appended_from`、续拆进行中的单元过滤、导出过滤、批准时清空标记，都按规格实现。
  - 作者在发布后、批准前删除、补建、合并、拆分旧集，「新增」都标对了。
  - 把边界挪过新旧交界（第 2 集变成 6–11）时，`appended_from` 变成 2，符合规格「第一个 `unit_to ≥` 标记」的定义。探针输出：`MOVE 2 [(1,1,5),(2,6,11),(3,12,13),(4,14,16)]`。
- **前端（§4.4）**：12 条逐项对过。
  - 续拆块替换 outdated 块，主按钮不受时长输入框影响，次按钮沿用原写法。
  - 改过的旧章那一句：续拆块里放在第 2 句之后，块外放在状态行下方。
  - stale、已续拆、正在续拆三行各自的条件都对。续拆进行中隐藏取消按钮并显示说明句；partial 说明句的位置也对。
  - 报价对话框的 continue 模式压掉了三条整本提示；不传 `continueRange` 时 JSX 条件与原来等价。
  - `BreakdownStage` 加了第三个确认分支。`EpisodePlan` 的 `continuing` 文案正确；卡片视图里「新增」标签在 h3 外面，表格视图里在标题之后。
  - `SourcePanel` 的三处条件、`SerialSourceHints`、`chaptersDone`、`NovelFilmDialog`、`filmReady` 和依赖数组 `[beginStudio, filmReady]`（lint 无告警）、`GateBanner` 的 `onMakeFilm` 仍然要求 `completed`、`CreateProjectDialog` 的整句、修改意见卡那半句，都对。
  - 新元素都带 `data-serial`，字重检查也通过。
- **聊天文案（§4.5）**：`claude_agent.py:125/845`、`intent_router.py:148`、`.env.example:231` 与规格逐字一致；`start_film` 复用分支的四行卡片也对。
- **越权**：用 `other` 账号调两个续拆接口都返回 404，未登录也是 404（探针 `OTHER_QUOTE 404 / OTHER_START 404 / ANON 404`）。`get_current` 新增的快照查询带 `owner`；`continuations` 不外露 `quote_id`。
- **文档（§4.7）**：`CLAUDE.md` 186/188/192/194(新)/196、`README.md` 359/361/363/369/394/396、`ARCHITECTURE.md` 412/416/418/507(新)/509、`PLAN.md` 新的一节，相关陈述都改对了，也没有残留「已完结才可建项目」「待复核不能做成片」「同步后只能整本重拆」这几类说法（我用 grep 核对过）。
  - `ARCHITECTURE.md:505` 没改。我看了原文，没有错误陈述；取消的例外写在紧随其后的新段落 507。
  - 白名单外 `docs/tasks/2026-11-12-novel-feedback/` 里还有旧说法，按规则不改。

## 3. 必须修复项

### MF1：「执行 / 原文」用例证明不了读的是哪一版快照（变异 B26 存活）

- **位置**：`backend/tests/test_studio_serial_continue.py:620` `test_continuation_execution_reads_bound_snapshot_and_keeps_old_units`。
- **问题**：快照 2 的第 3 章用的是 `changed_body(3) = default_body(3) + 追加的一行`。`_source_inputs` 按批记下的 `ranges[start:end]` 切片，所以就算从快照 2 读，切出来的仍然正好是 `default_body(3)`。
- **复现**：把 `breakdown.py:753` 改成 `snapshot_no = breakdown['snapshot_no']`（忽略批自己的快照号）。新测试 35 个全过（`35 passed`）。用例后半段「旧单元 start/end/label 不变」同样因为这个原因无效。
- **期望改法**：快照 2 对第 3 章的修改必须落在旧 range 以内，比如在开头插入 `'改过的开头。'`，或者替换掉第一场的锚点句。两条断言都要保留：读回快照 1 原文，以及 refresh 后旧单元不变。我的探针用开头插入的写法，在 B26 下失败（`1 failed`），在现实现下通过。

### MF2：「partial 不发布」用例没有触及守卫（变异 B14 存活）

- **位置**：`test_continuation_partial_does_not_publish_until_retry`（`:908`）。
- **问题**：用例让本轮唯一的补全批失败，下游分集批一直 blocked，本轮根本没有成功的分集批可发布。所以把 `breakdown.py:891` 改成 `if status in {'done', 'partial'}` 也照样全绿。
- **期望改法**：新章要跨两段，例如同步到第 16 章；只让第二段的补全批（第 16 章）失败，这样第一段的分集批会成功，而拆解停在 partial。然后断言：`plan_revision`、集数不变，`appended_from is None`。单批重跑成功后，断言只发布一次（revision 加 1）、新集都在。我的探针确认：现实现下是 `PLAN 1 2 None`，B14 下失败。

### MF3：退役循环的「冻结条目跳过」（T4 第 6 步第 4 点）没有任何测试覆盖（变异 B2、B4 存活）

- **位置**：`test_continuity_duplicate_active_names_warn_and_insert`（`:825`）。
- **问题**：两条重名行都用 `create_bible` 手建，是 uuid4 条目，本来就不参加退役循环。用例里「本拆解没有新的 `merged_into`」这条断言因此恒真。把 `breakdown.py:702` 的冻结跳过整个删掉，35 个用例照样全过。可这一条正是「已定的妆不会变孤儿」的核心保护。
- **复现**：两条重名行之一是第 0 轮模型输出的自动条目（uuid5）并且已经定妆，书斋随后把这个名字登记成 C2。现实现下，自动条目 `merged_into` 为空、不是孤儿。删掉冻结跳过（B2/B4）后，它会被标 `merged_into` 指向新插入的 C2 行，定妆变成孤儿：探针 `1 failed`。
- **期望改法**：把多行重名用例里的一条改成自动条目（第 0 轮新批输出「船夫」或「阿禾」），并把它的定妆项设为 approved。在续拆确认后和 drain 后各断言一次：它没有 `merged_into`、`casting.is_orphaned` 为假、定妆状态仍是 approved，同时新行和 warning 照常出现。

### MF4：续拆确认的报价与额度复核、未结束批次校验没有测试（变异 B20、B21 存活）

- **问题**：
  - 把 `breakdown.py:433` 的 `_confirmed_quote(...)` 换成 `payload = preview`，等于跳过过期检查、只确认一次和确认时的额度复核。新测试全过：「同一报价第二次确认」在第 2 步就因为拆解已是 running 被拦下，碰不到 `_confirmed_quote`。
  - 把确认时的「未结束批次」查询改成永远查不到（B21），新测试也全过。

  这是 L3 计费流程里的守卫。
- **期望改法**：在 `test_studio_serial_continue.py` 里补以下用例：
  - 报价过期后确认 → 409「报价已过期，请重新报价」，批数、job 数、预留总额都不变；
  - 成功确认后，`studio_quotes.status == 'confirmed'`；
  - 报价后把日额度或月额度压到不够，再确认 → 409，且没有任何改动；
  - 报价后插入一条 queued 的 probe job，再确认 → 409「拆解还有未结束的批次」，且没有任何改动。

  前两条我已用探针验证现实现正确（`EXPIRED 409 报价已过期，请重新报价`、`QUOTE_STATUS confirmed`），B20 下这个探针失败。

### MF5：报告缺「文档改动位置」逐处清单（§4.7、§5.8）

- **位置**：`impl/report.md`。§4.7 要求「在报告里列出改过的每一处」，§5.8 要求写明「文档改动位置」。报告第 280 行声称已经包含，正文却只有笼统的一句。
- **期望改法**：补一张表，每行写「文件:行号 → 原陈述类别 → 改后要点」。至少要包括：
  - `CLAUDE.md` 186、188、192、194（新段落）、196；
  - `README.md` 359、361、363、369、394、396；
  - `docs/ARCHITECTURE.md` 412、416、418、507（新段落）、509；
  - `PLAN.md` 新的「2026-11-12：工作室续拆」一节。
  - 再注明 `ARCHITECTURE.md:505` 核对后保留不改，以及理由。

## 4. 可优化项（不阻断）

1. **续拆 partial 时有时仍能同步新章（需规格作者裁决）。** 失败的是本轮最后一个分集批，或者 partial 是 `uncertain` 造成的，这时组里没有 queued 或 running 的 job，`sync_source` 照样成功（探针：`STATUS partial … True` 后 `SYNC_OK 3`）。可界面文案（`BreakdownPanel` 的 partial 说明）、README:396、PLAN 的已知局限和规格 §7 都写着「完成前不能同步新章」。我核对了后果：同步后单批重跑仍读本轮绑定的快照，完成后发布正常，之后可以再续拆，所以行为本身无害，只是文案不准。实现方报告第 5 节第 2 条也提到了。两种处理任选其一：在 `sync_source` 里加一条「当前拆解 `_continuing` 时拒绝同步」，或者把文案改成「可能」。由规格作者决定。
2. **`get_current` 每次都读当前快照的 manifest，manifest 损坏时整个拆解视图 500。** 我把当前快照的 `manifest_sha256` 改坏：`get_current` 返回 500「作品快照校验失败」，`get_episodes` 仍然正常（探针 `VIEW_ERR 500 / EPISODES_OK 2`）。基线的拆解视图不读 manifest。这会让未续拆的拆解也跟着坏，而且 `retry`、`cancel`、`continue_start` 提交成功后返回值也会是 500。前提是存储损坏，概率很低，来源面板在同样情况下本来也是 500。建议读取失败时降级：`changed_covered=[]`、`continuable=False`，再加一条 warning。另外可以按 `(rel_dir, manifest_sha256)` 缓存解析结果，免得每 5 秒轮询都完整读一遍、算一遍哈希。
3. **续拆 partial 后发起整本重拆，旧方案视图会把本轮新单元算进「未纳入」。** 这时已发布的旧拆解已退役，`_continuing` 为假，单元不再过滤，第 11–13 场显示为未纳入（探针 `REBREAKDOWN True False True [(11, 13)] 13`），导出也一样。由于 `rebreakdown_pending`，编辑本来就被锁住，只影响观感。建议：已发布拆解有 `_continuations` 时，一律只取 `seq ≤ _published_max_seq` 的单元。
4. **`_insert_bible` 插入新行后，放进 `row_by_id` 的是只有 7 个键的精简 dict（`breakdown.py:662`）。** 同一次调用里如果再有条目解析到同一个 id，就会在 `existing['appearance_source']` 处 KeyError。`merge_bible` 的合并规则保证 `kind:(ref_id or name)` 不会重复，所以目前到不了这一步。建议存完整行或改用 `.get`，以防以后改动 `merge_bible`。
5. **单章批标签。** 续拆的单章批仍写成「第 11–11 章 · 补全」。规格 T2 的「单章写第 x 章」和「按现有写法」互相矛盾，实现方按默认输出必须逐字节不变的原则保留了现状，我认为合理，请规格作者确认。
6. **其余存活的变异与测试小缺口**：
   - P5：分集跨新旧交界时的 `appended_from`，没有用例；
   - F14：可续拆时「改过的旧章」一句在块外重复出现，新测试测不出；
   - 改名用例把「改名」和「书斋登记」叠在一起测。只改名的情形我已用探针验证通过。
7. **新增的包裹元素和样式。** `EpisodePlan` 卡片视图的包裹 div、`BreakdownPanel` 状态行的包裹 div，在没有续拆时也会渲染（带 `data-serial`），不影响功能。表格视图里「新增」标签紧贴标题文字，没有间距，可以加 `ml-2`。
8. **`CLAUDE.md` 变大。** 从 66,525 字节增长到 69,419 字节；它在基线时已经超过 65,536 字节的代理指令预算，现在末尾会有更多内容被截掉。建议压缩新段落，或者改成链接到 ARCHITECTURE。
9. **`_eligibility` 的比较顺序。** 它先做 `(chapters_done or 0) < 1` 比较，之后才在 `_all_chapters` 里校验类型。`chapters_done` 万一是字符串，会抛 TypeError 变成 500，而不是 409。数据库列是整数，这只是理论问题。

## 5. 给实现方的二次修改指令（只针对必须修复项，可直接转发）

> 只改 `backend/tests/test_studio_serial_continue.py` 和 `docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md`。不改实现代码，不改其他文件，不放宽现有断言。
>
> 1. **MF1**：`test_continuation_execution_reads_bound_snapshot_and_keeps_old_units` 里，同步到快照 2 时第 3 章的改动必须落在旧 range 以内，例如 `bodies={3: '改过的开头。' + changed_body(3)}`。保留「`_source_inputs` 读回快照 1 原文」和「refresh 后旧单元 start/end/label 不变」两条断言。自检：把 `breakdown.py` 的 `_source_inputs` 临时改成 `snapshot_no = breakdown['snapshot_no']`，这条用例必须变红；之后还原。
> 2. **MF2**：改写 `test_continuation_partial_does_not_publish_until_retry`，或者新增一条用例。同步到第 16 章，只让第 16 章的 `novel_complete` 失败，使第一段的 `episode_plan` 成功而拆解为 partial。断言 `plan_revision`、集数不变，`appended_from is None`。单批重跑成功后断言 revision 只加 1、新集齐全、`appended_from` 正确。自检：把 `refresh` 里续拆分支的 `if status == 'done':` 临时改成 `if status in {'done', 'partial'}:`，用例必须变红。
> 3. **MF3**：多行重名用例里的两条重名行，改成其中一条是第 0 轮新批输出的自动条目（uuid5），并把它的 `studio_items` 设成 approved。快照 2 的书斋圣经登记同名 `ref_id='C2'`。在 `continue_start` 后和 `drain` 后各断言一次：该自动条目 `merged_into is None`、`casting.is_orphaned` 为假、定妆仍是 approved；新行与「与总表里多个同类条目重名」warning 照常出现。自检：把 `_insert_bible` 退役循环里的 `old['id'] in frozen` 临时去掉，用例必须变红。
> 4. **MF4**：新增续拆确认用例，每条都断言 409 文案，并断言批数、job 数、预留总额不变：
>    - 报价过期 → 「报价已过期，请重新报价」；
>    - 报价后把额度压到不够（照 `test_studio_breakdown_pipeline.py` 改额度环境变量），再确认 → 额度不足的 409；
>    - 报价后插入一条 queued probe job（可复用 `insert_queued_probe`），再确认 → 「拆解还有未结束的批次」。
>
>    另外在成功用例里断言 `studio_quotes.status == 'confirmed'`。自检：把 `continue_start` 里的 `_confirmed_quote(...)` 临时换成 `payload = preview`，用例必须变红。
> 5. **MF5**：在 `impl/report.md` 里补「文档改动位置」表，逐处写文件:行号、原陈述类别、改后要点（清单见复核 §3 MF5），并注明 `ARCHITECTURE.md:505` 核对后保留不改及理由。
> 6. 改完后重跑：三个新文件、后端全量（期望 passed = 8264 + 新文件收集数，0 skipped），以及 §5.5 的无 `node_modules` 副本。报告里更新收集数和结果。

## 6. 变异实验清单与结果

做法：用脚本一次只改一处（锚点文本必须恰好出现一次），用 `pytest -x` 跑对应的新测试，记录结果后立刻还原。全部做完后，`git diff` 与 `diff-r0.patch` 用 `cmp` 比对一致，三个新测试文件的 sha1 也没变。

### 6.1 后端（56 个变异，存活 12 个）

| 编号 | 改坏的内容 | 跑的测试 | 结果 |
|---|---|---|---|
| B1 | 总表第 3 步：名字 / ref 匹配不生效 | continue | 变红 |
| B2 | 退役循环只跳过 alias 目标（去掉冻结跳过） | continue | **存活**（我的探针能抓到 → MF3） |
| B3 | 退役循环只跳过冻结条目（去掉 alias 跳过） | continue | 存活（接近等价：alias 目标通常本来就在 desired 里） |
| B4 | 两种跳过都去掉 | continue | **存活**（我的探针能抓到 → MF3） |
| B5 | 「沿用」逻辑对未续拆拆解也生效 | 既有 `test_studio_breakdown_*` 与 `test_studio_casting_*` | 变红 |
| B6 | 转向时不补 `ref_id` | continue | 变红 |
| B7 | 删掉多行重名 warning | continue | 变红 |
| B8 | 去掉「derived 已存在就用它」 | continue | 存活（接近等价） |
| B9 | 去掉「alias 复用」 | continue | 存活（接近等价，第 3 步会重新找到同一行） |
| B10 | round ≥ 1 仍写 `suggested_episodes` | continue | 变红 |
| B11 | 永远不用 `published_last` | continue | 变红 |
| B12 | `earlier` 不按轮次过滤 | continue | 变红 |
| B13 | `published_last` 取最早一集 | continue | 变红 |
| B14 | 续拆的 partial 也发布 | continue | **存活**（探针能抓到 → MF2） |
| B15 | `_appended_from_unit` 不取较小值 | continue | 变红 |
| B16 | 发布后不更新 `_published_max_seq` | continue | 变红 |
| B17 | 已有集丢掉 `notes` | continue | 变红 |
| B18 | 删掉取消守卫 | continue | 变红 |
| B19 | 取消守卫挪进 `_cancel_unexecuted` | continue | 变红 |
| B20 | `continue_start` 跳过 `_confirmed_quote` | continue | **存活**（探针能抓到 → MF4） |
| B21 | `continue_start` 不查未结束批次 | continue | **存活**（→ MF4） |
| B22 | `continue_quote` 不查未结束批次 | continue | 变红 |
| B23 | `continue_start` 不查快照号 | continue | 变红 |
| B24 | `continue_start` 不查 `covered_through` | continue | 变红 |
| B25 | 旧批不补记 `snapshot_no` | continue | 变红 |
| B26 | `_source_inputs` 不用批自己的快照号 | continue | **存活**（探针能抓到 → MF1） |
| B27 | `_chapter_basis` 覆盖旧章 | continue | 变红 |
| B28 | 兼容分支不初始化 `_published_chunk_ids` | continue | 变红 |
| B29 | 不清 `outdated` | continue | 变红 |
| B30 | `continuable` 不看未结束批次 | continue | 变红 |
| B31 | `changed_covered` 只在快照号不同时计算 | continue | 变红 |
| B32 | `_continuing` 不看拆解状态 | continue | 变红 |
| B33 | 「新增」起点误用第一轮的 `pre_max_seq` | continue | 变红 |
| B34 | 续拆的 `segment_base` 少加 1 | continue | 存活（对外不可观察，等价） |
| B35 | `stale_chapters` 改读当前快照 | continue | 变红 |
| M1–M5 | `batch_plan`：终点用 `len(entries)`、`map_nos` 不偏移、`depends` 不偏移、段号忽略 `start_chapter`、次要来源不抛错 | continue | 全部变红 |
| P1 | `get_episodes` 续拆中不过滤新单元 | continue | 变红 |
| P2 | 导出不过滤 | continue | 变红 |
| P3 | 批准时不清「新增」标记 | continue | 变红 |
| P4 | 已批准时仍返回 `appended_from` | continue | 存活（等价：批准时标记已被清空） |
| P5 | `appended_from` 改用 `unit_from` 判断 | continue | 存活（没有跨新旧交界的用例，见 §4 第 6 条） |
| S1–S10 | `sources`：重新要求完结、签名带 `updated_at`、签名忽略 `_rearchive`、签名包含 `chapters_done` 之后的行、接受 bool、资格忽略 `_rearchive`、快照 stale 置空、漂移 stale 置空、候选 `snapshot_chapters` 置 NULL、读取范围回到 detail 的最大章号 | serial_sources | 全部变红 |
| N1 | 做成片卡片在快照章数等于 `chapters_done` 时也提示同步 | serial_sources | 变红 |

### 6.2 前端（18 个变异，存活 1 个）

F1–F13 全部变红：
- F1：「新增」标签放进加粗的 h3；
- F2：续拆确认误调整本 start；
- F3：续拆中仍显示取消；
- F4：续拆按钮受时长输入框影响；
- F5：快照 stale 那一行只在 changed 时显示；
- F6：连载提示去掉 `typeof` 判断；
- F7：`filmReady` 改回要求完结；
- F8：续拆对话框显示 `replacesPartial`；
- F9：`SerialSourceHints` 不看 eligible；
- F10：快照章数相等时也提示落后；
- F11：partial 说明句加粗；
- F12：新增提示句的祖先加粗；
- F13：`formatChapterRanges` 单章写成范围。

F15–F18 也全部变红：
- F15：已续拆那一行在 running 时也显示；
- F16：Stage 不传 `continuing`；
- F17：表格视图漏掉「新增」；
- F18：续拆块和 outdated 块同时显示。

只有 **F14**（可续拆时「改过的旧章」一句在块外再出现一次）存活。

### 6.3 用临时探针补测的存活变异

| 变异 | 探针 | 现实现 | 变异后 |
|---|---|---|---|
| B2、B4 | 自动条目与手建条目重名、已定妆、书斋后登记 C2 | 通过（`merged_into` 为空，不是孤儿） | 失败 |
| B3 | 同上 | 通过 | 通过（等价） |
| B14 | 两段新章，第二段补全批失败 | 通过（revision 1、2 集） | 失败 |
| B26 | 第 3 章在开头插入文字后读旧批原文 | 通过 | 失败 |
| B20 | 过期报价确认 → 409；成功确认后报价状态为 confirmed | 通过 | 失败 |

## 7. 现场还原

- 临时文件：探针 `backend/tests/test_zz_review_probe.py` 已删除；`tsc` 和 `build` 生成的 `frontend/tsconfig.tsbuildinfo`、`frontend/.next/`（都在 gitignore 里，开始时并不存在）已删除；探针对应的 `.pyc` 已删除；无 `node_modules` 副本建在仓库外，也已删除。
- 源码：变异脚本每次改完立即还原；全部结束后 `git diff | cmp - diff-r0.patch` 一致，三个新测试文件 sha1 不变。
- 状态：最终 `git status --porcelain --untracked-files=all` 与开始时相比，只多了本文件 `?? docs/tasks/2026-11-12-studio-serial-breakdown/04-review.md`。
- 实验材料（变异脚本、差分插件、日志）放在仓库外的 `scratchpad/review-serial-materials/`。
