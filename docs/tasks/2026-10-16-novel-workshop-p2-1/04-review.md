# 小说工坊 P2.1 独立复核记录

> - 复核对象：分支 `novel-p2-1`，基线 `2979e2d`，未提交改动（14 个跟踪文件 +213/−25，新增 4 个测试文件 129 例）。
> - 复核方式：只依据 `02-spec.md`（含 §7 R1）、完整 diff 与工作树源码；`03-report.md` 只作线索。未修改仓库任何文件（本文件除外），未执行 npm install/build/dev，未联网，未读 `.env`。
> - 复核日期：2026-10-16。

## 结论：不通过（1 项必须修复，数据风险）

实现质量整体较高：五个外部契约函数签名与返回字段未变，`chapter()` 抽出共用后逐字段一致，关闭短剧时审校请求与 HEAD 版逐字节相同（用 HEAD 版 `writing.py` 实跑对比，而非只看测试里重写的公式），T3/T4 行为与规格一致，新增测试覆盖了 §4 与 §7.2 的全部断言并真走真实路径。

但 T2「立项后补改人物」与 P1 既有「改最新章正文 → 重新归档」叠加后，会把用户刚改好的人物字段**静默回退**。已用离线真实路径复现（见 M1）。这正是题面第 3 条问的「与 runner 竞争时是否可能写入圣经导致被覆盖」——不是并发竞争，而是顺序操作必然丢失。

## 必须修复项

### M1 立项后补改的人物字段会被「最新章重新归档」静默丢弃

- **现象**：书处于 D4 允许的任一状态（复现用 `awaiting_end`），`PATCH /novels/{id}/characters/C1` 写入 `user_edit` 新版本；随后作者改最新章正文（`PUT /novels/{id}/chapters/{n}`，P1 既有功能，同样在这些状态下可用）。重新归档完成后，最新圣经里 C1 的外形、动机回到 PATCH 之前的值，前端轮询刷新后人物卡无提示地变回旧文字，短片工作室读到的也是旧外形。
- **证据**：
  - `backend/novel/runner.py:371–376`：`_rearchive` 取 `source='archive:{chapter}'` 的首个版本为 `original`，再取 `version < original` 的最近一版为 `previous`，以 `previous` 为底重建；`:392` 新版本号 `book["bible_version"]+1`。介于 `original` 与当前最新版之间的 `user_edit` 版本完全不参与。
  - `backend/novel/service.py:308–331`：`update_character` 只写一条新版本，没有留下可重放的差异记录。
  - 探针 `scratchpad/p21-review/probe_rearchive.py`（离线 FakeLLM + dry_run 路由，走真实 `service.create → approve_setup → update_character → edit_chapter → runner._rearchive`）输出：
    ```
    status after chapter 1: awaiting_end bible_version: 3
    after PATCH: version 4 appearance: '齐肩黑发束在脑后，身形清瘦，穿洗旧的深蓝长外套，左眉有一道浅疤。'
    status after rearchive: awaiting_end bible_version: 5
    versions: [(1, 'setup'), (2, 'user_edit'), (3, 'archive:1'), (4, 'user_edit'), (5, 'rearchive:1')]
    final appearance: '身形清瘦，黑色齐耳短发，左眉有浅疤，常穿深灰工装外套并佩戴银色发夹。'
    final motivation: '保护被抹去的人'
    USER EDIT LOST
    ```
  - P2.1 之前 `user_edit` 只出现在立项确认（`service.py:363`），必然位于所有归档之前，不会被重建丢弃；本单首次引入归档之后的 `user_edit`，因此是新引入的数据风险。
- **后果**：T2 的目的（给短剧角色卡补齐外形）在一个常见操作序列后失效，且用户与下游都无感知；版本表里留着 v4，但没有任何入口能找回。
- **修法**（需验收方授权把 §1 白名单扩到 `runner._rearchive` 的圣经重建段；不触碰状态机、暂停原因、计费）：
  1. `_rearchive` 得到 `next_bible` 后，查询 `novel_bible_versions` 中 `version > original.version AND source='user_edit'` 的各版本，与其各自前一版本比对 `locked.characters[]` 的 `appearance / personality / motivation`，把差异按人物 `id` 叠加回 `next_bible`（人物在重建结果中不存在则跳过）。只叠加这三个字段，与 `CharacterEdit` 的白名单一致。
  2. 补一条离线测试（可直接沿用 `test_rearchive_repairs_short_new_appearance_before_persisting` 的骨架）：PATCH 后改最新章 → 排空任务 → 断言三字段保留、版本来源序列以 `user_edit, rearchive:n` 结尾。
  3. 不推荐的替代：在 `update_character` 里当最新章可被重新归档时拒绝——D4 允许的大多数状态都满足该条件，会让功能基本不可用。

## 可优化项（不阻断）

1. **复审轮提示词未指向例外**：`agent_pool.py:122`「新发现的问题只有属于上述三类中的严重情况，才可以判为阻断」被 `test_novel_r2_prompts.py` 冻结，开启短剧时复审轮模型可能据此把场景数超限降为非阻断。可在该句之后追加一句「或符合前述唯一例外」（只追加，不改原句）。
2. **PATCH 校验顺序**：外形不足 20 字（`service.py:318–319`）先于人物存在性（`:326`）判断，对不存在的人物传短外形得到 422 而非 404；建议先查人物再校验字段。
3. **`failed` 状态文案**：`service.py:314–315` 对 `failed` 也返回「书正在运行，请先暂停再改人物」。规格字面如此，但与实际状态不符，可按状态分文案。
4. **solo 模式下的说明文字**：勾选「改编短剧」会把 `adaptation_advisor` 写进 `agents`（`NovelWizard.tsx:172`），提交体按既有规则在 solo 时剔除顾问（`:78`），行为正确；但说明文字「勾选后会请短剧改编顾问参会」在 solo 模式下不成立，可在 solo 时换一句。
5. **人物卡草稿残留**：状态切到运行态时表单隐藏但 `draft` 保留（`BiblePanel.tsx:40`），恢复到可编辑状态后旧草稿重现。可在 `editable` 变为 false 时清空草稿。
6. **无变化的保存**：`BiblePanel.tsx:26` 用未 trim 的草稿与原值比较，再发送 trim 后的值；用户只加了首尾空白时仍会写一条内容相同的新版本。可比较 trim 后的值。
7. **导出标注位置**：`service.py:551–552` 固定插在正文首行之后；若 stale 章正文首行不是「# 第n章」（只在作者手改过非最新章、之后它又被标 stale 时可能），标注会落在一行正文之后，不报错但与「标题行之后」略有出入。可用 `first.startswith('# ')` 决定是否插入在首行后，否则插在正文最前。

## 逐条核验表

| # | 核验点 | 结论 | 证据与说明 |
|---|---|---|---|
| 1 | 外部契约不破 | 通过 | `list_books/detail/bible/chapter/owned` 定义在 `service.py:210/222/237/262/132`，签名与 HEAD 相同（`test_novel_p21_service.py:1209–1215` 用 `inspect.signature` 校验，复跑通过）；`detail().config` 只新增 `drama_adaptation` 字段。`chapter()` 原函数体（`git show HEAD:backend/novel/service.py` 第 240–250 行）与新 `_chapter_result`（`service.py:271–277`）逐行相同，仅把 `fail('章节不存在',404)` 之后的组装移出；`test_novel_p21_service.py:1186` 还逐章比对 `chapters_range` 与 `chapter()` 相等。`store_db.py`、`bible.py` 零 diff，表与列未变；`update_character` 只在既有 `locked.characters[]` 元素上 `dict.update` 三个字段（`service.py:327`），不触碰 `dynamic.*`、`completed/done/stale`。|
| 2 | T1 | 通过 | `drama_adaptation: bool = False`（`service.py:62`），`create()` 用 `model_dump()` 整体写入 `config_json`，`PATCH /novels/{id}` 的 `PatchNovel` 未放行该字段（测试 `:1003` 断言 422）。`validate_review(data, body, *, adaptation_blocking=False)`（`schemas.py:429`）：style 永远 False、adaptation 仅在参数为 True 时保留模型值（`:465–467`）。`writing.py:189–192` 仅在开启时向 payload 加两个键，`:198` 把同一标志传给校验。**探针 A**（`scratchpad/p21-review/probe_payload.py`）把 HEAD 版 `writing.py` 以 `novel.writing_old` 载入，与现版在同一 FakeLLM 脚本下跑 `write_chapter`：实验 A/B/P1 × 压缩开关 × 缺省/显式 False × panel/solo 共 12 组，全部请求（messages 逐条）与返回产物序列化后逐字节相同；开启时仅审校 payload 多出 `adaptation_blocking: true` 与 `adaptation_limits`，无缺键/改键，第 0 轮 adaptation 问题由 False 变 True，第 1 轮写手 payload 的 `blocking_issues` 含 `adaptation`，`revision_rounds=1`。提示词：原句 `agent_pool.py:111` 原样保留，`:112` 紧接追加例外，`:118` 在三类之后指向例外；未开启时 payload 不含 `adaptation_blocking`，例外条款的触发条件不成立，且代码层仍强制 False，双重保险。向导：复选框与说明（`NovelWizard.tsx:191`），默认 false（`:61`），勾选联动（`:162–173`：展开参数、顾问未选且 <5 位时按现有规则取首个可选模型、满 5 位时就近 `ErrorNotice`），`<details open onToggle>` 受控（`:192`），汇总「改编短剧：是/否」（`:202`），提交体 `drama_adaptation`（`:82`）；工作台 `.tag`（`NovelWorkbench.tsx:257`）；`lib/novels.ts:13` 类型可选。`tsc --noEmit` 退出 0，`eslint` 四个改动文件退出 0。|
| 3 | T2 | **不通过（M1）** | 校验：`validate_archive(..., *, require_new_appearance=False)`（`schemas.py:473`），`_character` 仅在 `new and require_new_appearance` 时要求 20 字（`:183`），计数走 `_Check.text → compact()`（`:120–124`）；默认行为与 HEAD 一致（`test_novel_r1_schemas.py` 的 `new_appearance` 用例与 `test_novel_state.py` 直接调用 `apply_archive` 的用例都复跑通过）。调用点：`writing.py:220` 按 `experiment == "P1"` 传 True，`runner.py:386` 重新归档传 True，`bible.apply_archive` 内部保持默认（`bible.py` 零 diff）。PATCH 路由 `routers/novel.py:114–117`，复用 `workshop_user` 与 `20/minute` 限流。`update_character`（`service.py:308–335`）：`BEGIN IMMEDIATE` → `owned()` → `awaiting_setup` 专门文案 409（`:313`）→ 五状态白名单外 409（`:315`）→ `_check_not_editing`（`:316`）→ 外形 `compact()<20` 422（`:319`）→ 无圣经/人物不存在 404（`:322/:326`）→ 只 `update` 三字段 → 新版本 `source='user_edit'`、`version+1`（`:328–330`）→ 返回带 `compass` 的完整圣经，形状与 `bible()`（`:237–247`）一致。`CharacterEdit`（`:81–93`）`extra='forbid'` + `str_strip_whitespace`，空体/显式 null/多余字段/空白性格动机均 422。并发：真正能写圣经的只有 `running` 态下的 `commit_chapter` 与 `_rearchive`，而 PATCH 在 `running` 态被 409 挡住；`continue/resume/approve_plan/reject_end` 都在 `BEGIN IMMEDIATE` 内先置 `running` 再 `start_novel`，`_advance` 每轮从库里按 `bible_version` 重读（`runner.py:268–271`），PATCH 先提交的版本会被接上；`edit_chapter` 在 `editing_novel` 内先置 `_editing` 再开事务（`runner.py:50–57`，`service.py:497–525`，`:503` 进入 `editing_novel`），PATCH 的 `_check_not_editing` 在事务内检查。**但顺序场景下** `_rearchive` 以本章原归档之前的版本为底重建，归档之后的 `user_edit` 被丢弃——见 M1，已实跑复现。前端：`editableStatuses` 五状态（`BiblePanel.tsx:9`），「修改」只在可编辑且未展开时渲染（`:38`），运行态不渲染入口与表单（`:38/:40`），「外形未写全，改编时需要补」（`:39`），外形字数口径与 `compact()` 一致（`:11`，`test_novel_p21_frontend.py:668–681` 用 Node 执行源码中的表达式与 Python `compact` 比对 6 组含控制字符/BOM/全角空格/成对引号/省略号的样例），错误经 `mutate` 以 `errorTarget:"local"` 重新抛出后在卡片内 `ErrorNotice` 就近显示（`:46`，`NovelWorkbench.tsx:231–237`）。|
| 4 | T3 | 通过 | `export()`（`service.py:539–554`）仍 `WHERE body IS NOT NULL ORDER BY chapter`，不跳章、顺序不变；`pending` 只统计有正文的 stale 章（`:543`），书首汇总行（`:546`）与章内标注行（`:552`）文案与规格逐字一致；无 stale 时 `heading+'\n\n'+'\n\n'.join(bodies)` 与 HEAD 的 `'# '+title+'\n\n'+'\n\n'.join(c['body'])` 等价（`test_novel_p21_service.py:1140–1149` 含 `None` 标题、零章、空正文三组逐字节比对）。单行正文 `partition('\n')` 后 `separator==''`，不会多出换行（`:1152–1156`）。首行非标题时不报错，只是标注位置略偏（可优化项 7）。路由与响应头零 diff（`routers/novel.py:138–140`）。|
| 5 | T4 | 通过 | `find_books`（`service.py:215–220`）：`strip().casefold()`，空查询返回 `[]`，复用 `list_books` 的形状与顺序，`title` 为 `None` 时按空串处理，只查本人；`%`/`_` 按字面匹配（测试 `:1172`）。`chapters_range`（`:279–287`）：先 `owned()` 再范围校验，越权/不存在 404 先于 422（测试 `:1201–1206`）；`type(...) is not int` 拒绝 bool/float；`1≤start≤end≤300` 且 `end-start+1≤50`；单条 `BETWEEN … ORDER BY chapter` 查询自然跳过缺章；复用 `_chapter_result`，形状与 `chapter()` 相同。|
| 6 | 测试质量 | 通过 | 4 个新文件 129 例（`--collect-only` 核对），复跑全绿；全部 `tests/test_novel*.py` 1354 passed；指定集合 337 passed。真实路径：service 测试走 FastAPI 客户端 + 临时库；writing 测试走真实 `write_chapter` + FakeLLM，`offline_only` 夹具把 `_single_real_call` 打桩成 AssertionError；`test_rearchive_repairs_short_new_appearance_before_persisting` 走 `service.create → runner` 真实后台任务。前端测试用正则截取源码中的事件处理函数在 Node 中实跑，`shutil.which("node")` 缺失时 `pytest.skip`，不 import `node_modules`；源码读取都在仓库内，无 git 历史依赖。空集恒真排查：`test_chapters_range_matches_single_chapter_shapes_and_skips_gaps` 的 `expected=[]` 一组循环体为空，但同一参数化内其余四组非空；`test_only_p1_writing_repairs_short_new_character_appearance` 断言 `len(attempts)` 具体值而非 `>0`。既有测试：`git diff HEAD --stat -- backend/tests frontend/package.json frontend/package-lock.json frontend/app/globals.css backend/novel/fake_llm.py backend/novel/bible.py backend/novel/store_db.py` 为空；新增四个测试文件的 blob 哈希（`7622ea3/78b9da1/d9215d6/c16c7a6`）与 diff 的 `index 0000000..` 行一致。缺口：没有覆盖「PATCH 后改最新章」的组合场景，所以 M1 没被测试捕获。|

## 复核过程记录

- 工作树一致性：`git diff HEAD` 与 `p21.diff` 前 564 行（跟踪文件部分）`diff` 为空；四个新文件 `git hash-object` 与 diff 的 index 行匹配。
- 命令与结果（解释器 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，目录 `backend/`）：
  - `-m pytest -q -p no:cacheprovider tests/test_novel_p21_*.py tests/test_novel_r2_prompts.py tests/test_novel_r1_schemas.py tests/test_novel_state.py` → 337 passed。
  - `-m pytest -q -p no:cacheprovider tests/test_novel*.py` → 1354 passed（29 条既有 slowapi 弃用警告）。
  - `frontend/node_modules/.bin/tsc --noEmit -p .` → 退出 0；`frontend/node_modules/.bin/eslint` 四个改动文件 → 退出 0。未运行 `npm run build`。
- 探针（均在 `/private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/8c7c9461-074c-48c4-aa9b-bbaaef19ee71/scratchpad/p21-review/`）：
  - `probe_payload.py`：HEAD 版 vs 现版 `write_chapter` 12 组逐字节对比全部相同，开启时差异仅两键；`PROBE A OK`。
  - `probe_rearchive.py`：以 conftest 同款占位 Key 运行，复现 M1，输出 `USER EDIT LOST`。
- 未做：浏览器截图走查（规格 §5.4 由验收方完成）、真实厂商模型验证、默认 Turbopack 构建。
