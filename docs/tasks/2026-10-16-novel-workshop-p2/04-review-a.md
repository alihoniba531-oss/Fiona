# 小说工坊 P2 前端 独立复核 A（接口契约与业务逻辑）

复核对象：工作树 `.worktrees/fiona-novel-p0`（分支 novel-workshop-p0，基线 8c58057），未提交改动；规格 `docs/tasks/2026-10-16-novel-workshop-p2/02-spec.md`。
复核方式：通读规格与完整 diff；逐接口对照 `backend/routers/novel.py`、`backend/novel/service.py`、`schemas.py`、`deliberation.py`、`writing.py`、`bible.py`、`context.py`、`store_db.py`、`runner.py`；在 backend 下跑新增测试与全部 `test_novel_*`；用前端会发送的**原样请求体**写了一支端到端契约探针（`scratchpad/p2-review/probe_contract.py`，FakeLLM 离线驱动真实后端）；对接口路径扫描测试做了变异探针；只读运行 `tsc --noEmit --incremental false`。未改动仓库任何文件，未运行 npm install/build/dev，未用浏览器。

## 1. 结论：**通过**（无必须修复项；可优化项见 §3，其中前两条建议在合并前顺手处理）

- 新增测试：`test_novel_p2_api.py` + `test_novel_p2_frontend.py` → 57 passed；全部 43 个 `tests/test_novel_*.py` → 1207 passed，无回归。
- 契约探针：59 项全部通过（catalog/estimate/create/detail/bible/notes/chapter/setup-approve 差量体/plan-approve 改写 beat_sheet/plan-redo/notes/PATCH 对话框体/continue/pause/resume/end-reject/end-confirm/export Content-Type/PUT 改稿/DELETE/403/404 文案）。
- `tsc --noEmit`：0 错误。lint/build 本路未跑（另一路验收复跑）。

## 2. 必须修复项

无。所有前端发出的请求体字段、HTTP 方法与路径都能被后端接受；前端读取的字段后端都真实返回；§5.4 的 16 个状态/原因均有标签、横幅与正确的接口调用；两个新增只读接口的所有权、开关、白名单、未裁剪与排序均正确且被强断言的测试覆盖。

## 3. 可优化项（按建议优先级）

1. **轮询请求量偏大（性能，非契约错误）**。
   - 工作台每 3 秒并行拉 `detail + /bible + /notes`（`NovelWorkbench.tsx:65-67`），且每次 `load` 成功后 `revision+1`（:86）会让当前章节再 GET 一次（:126 依赖 `revision`）。`/bible` 是未裁剪全量（60 章规模可达数百 KB），运行态每 3 秒重复下载。建议：仅当 `bible_version` 变化时再拉 `/bible`；`pending_notes`/`updated_at` 不变时跳过 `/notes`；章节按 `signature` 变化再刷新。
   - 书架为了取 `max_chapters` 对每本书再 GET 一次详情（`NovelShelf.tsx:31`），并在有运行中书时每 3 秒重复 N+1（:39-52）。规格禁改 P1 接口语义，实施方选择了这条路；可考虑只在首次与 `updated_at` 变化时取详情。
   - 首次打开长书时对所有已完成章节逐章 GET 以补 `edited_by_user`（`NovelWorkbench.tsx:72-76`，60 章 ≈ 60 个含正文/会议记录的请求）。报告已自述；若 P3 允许在 P1 章节摘要里加 `edited_by_user` 字段可一次解决。
2. **向导估算在预算输入时也会重发**：估算 effect 依赖整个 `input`（含 `budget_strawberries`，`NovelWizard.tsx:54-59, 92`），但后端 `estimate_cost` 与预算无关（`billing.py:89`）。预算框每次停顿 600ms 都打一次 `POST /novels/estimate`（限流 20/分钟，`routers/novel.py:30`）。建议从防抖依赖里排除预算。
3. **budget_80「调高预算并继续」只校验「高于原预算」**（`NovelSettingsDialog.tsx:22`），而后端 resume 还要求 `spent*5 < budget*4` 且 `> _budget_at_pause`（`service.py:391-393`）。结果：PATCH 已生效、resume 返回 409「请先调高预算再继续」，对话框保持打开并显示该文案，用户需再调高一次。功能可用但多一步；建议前端把最小值算出来提示（`max(原预算, ⌈已花×1.25⌉)+1`）。
4. **立项卡外形长度校验口径与后端不一致**：前端只去空白后数 ≥20（`SetupEditor.tsx:48`），后端 `compact()` 还会去掉引号并折叠省略号（`schemas.py:23-26, 181`）。含引号的 20 字外形会通过前端却被后端 422。可复用相同正则。
5. **工作台对「开关关闭 404」显示的是通用文案**：`novelErrorMessage(cause)` 未传 `access`（`NovelWorkbench.tsx:87`），后端 `detail='Not Found'` 非中文 → 「请求未完成，请稍后重试。」。书架/向导已正确映射（`NovelShelf.tsx:34`、`NovelWizard.tsx:70`）；工作台通常由书架进入，影响小。
6. **书架把单本详情 404 也映射为「小说工坊尚未开放」**（`NovelShelf.tsx:31-34` 用 `access=true` 包住 `getNovel`）：若某本书刚在别处被删，整个书架会报「尚未开放」。建议 `listNovels` 用 `access=true`，`getNovel` 失败单独忽略该本。
7. **操作错误会被 3 秒后的成功轮询清掉**：`load` 成功即 `setError("")`（`NovelWorkbench.tsx:86`），运行态下一次 409（如「章节正在改稿」）只显示约 3 秒。可把操作错误与加载错误分开保存。
8. **立项 422 双重显示**：`mutate` 已在页顶 `setError`（:150）并重抛，`SetupEditor` 再显示一条编辑器内文案（`SetupEditor.tsx:61`）。按规格任选其一即可。
9. **小细节**：留言列表 `created_at` 直接显示 UTC 原串（`NotesPanel.tsx:30`，书架已有 `formatDate` 可复用）；伏笔账本对立项时埋下的伏笔显示「埋下：第 0 章」（`BiblePanel.tsx:21`，`bible.py:45-47` planted_chapter=0），可改为「立项时」；iframe 内在 textarea 里按 Esc 也会发关抽屉消息（`NovelShell.tsx:9-12`）。

## 4. 逐条核验表

| # | 项目 | 结论 | 证据 |
|---|---|---|---|
| 1a | catalog 类型 | 通过 | 后端 `service.py:169` 返回 `agents/models/byok/allowed_models/notice`；`byok` 为 `{provider,model,model_spec}` 或 None（`byok_bridge.py:23-33, 39-42`）；价目为每千 token 草莓（`billing.py:19-24, 81-88` 除以 1000）；前端 `lib/novels.ts:84-89, 156-162` 一致，文案「每千 token 输入/输出约 x/y 草莓」正确；探针 catalog 4 项通过 |
| 1b | estimate | 通过 | 请求体用 `CreateNovel`（`routers/novel.py:31`，`service.py:54-62` extra=forbid）；前端 `NovelCreateInput`（`novels.ts:9-14`）字段完全对应，solo 时过滤顾问（`NovelWizard.tsx:55`）；返回 `per_chapter/total/method`（`billing.py:136-139`）与 `NovelEstimate`（`novels.ts:90`）一致；探针通过 |
| 1c | create / detail | 通过 | POST `/novels` 201 返回 detail（`service.py:172-190`）；`NovelDetail`（`novels.ts:79-82`）对应 `detail()`（`service.py:198-210`）的 `config/compass/bible/chapters[{chapter,title,status,words,flags}]/pending_gate/pending_notes/last_error`；探针通过 |
| 1d | chapter / meeting 结构 | 通过 | 章节返回 `SELECT *` 去 username + `flags/meeting/review/archive/review_summary`（`service.py:238-248`）；critique meeting = `{mode,brief,plan,critiques,objections,decision}`（`deliberation.py:151-152`），objections 含 O 与 A 两类、A 带 `alternative`（:130-140）；前端 `DeliberationTimeline.tsx:27-38, 51-61` 同时兼容 `alternative_responses`（新）与 `objection_responses` 里的 A 回应（旧），solo（`deliberation.py:211-212` 无 mode/plan、proposals 为空）走「主编裁决+理由」分支（:38, 42）；探针实测 `['O1','O2','A1']`、`alternative_responses=[{A1,reject,...}]`、`user_note_responses=[{N1,...}]`、`brief.user_notes` N 前缀全部一致 |
| 1e | setup/approve | 通过 | 前端只放有改动字段，但数组整体发送（`SetupEditor.tsx:54-59`）；后端白名单 `compass_fields/locked_fields`（`service.py:276-279`）、人物 id/主线 id 不变校验（:289-296）均满足；探针用「改书名+改一人外形」差量体得 200 |
| 1f | plan/approve、plan/redo | 通过 | `{beat_sheet}` 或 `{}`（`novels.ts:115`，`NovelWorkbench.tsx:211`）对应 `PlanApproval`（`service.py:80-87`）；PlanEditor 保留原 beat_sheet 其它字段（`PlanEditor.tsx:9, 19`），场景上限取 `config.adaptation.max_scenes_per_chapter`（`NovelWorkbench.tsx:211`）与后端 `bible.locked.adaptation`（`schemas.py:372`）同源；节拍 3–8（`PlanEditor.tsx:18` vs `schemas.py:376`）；redo `{text}` 1–500（`novels.ts:116`，`service.py:72-73`）；探针通过 |
| 1g | continue/pause/resume/end/confirm/end/reject | 通过 | 路径与方法见 `novels.ts:92, 113, 117-121` 与 `routers/novel.py:84-99, 120-129`；`end/reject` 体 `{extend_chapters, text?}` 对应 `RejectEnd`（`service.py:101-103`），可选 text 为空时不发送（`GateBanner.tsx:27`）；暂停按钮只在后端允许的四个状态显示（`NovelWorkbench.tsx:197` vs `service.py:375`）；探针通过 |
| 1h | PATCH | 通过 | 只放有改动键（`NovelSettingsDialog.tsx:24-28`），`agents` 仅 paused/awaiting_* 下发送（:16, 28）与后端 `service.py:347-349` 一致；预算下限 `max(1, spent)`（:20）对应 `service.py:352-353`；探针通过 |
| 1i | PUT 改稿 / notes / bible / export / delete / strawberry | 通过 | PUT `{body}` ≤30000（`novels.ts:123`，`service.py:76-77`），返回 `{rearchiving,message}` 并显示 message（`ChapterReader.tsx:29`）；POST notes `{text}`→`{status:'pending'}`（`service.py:361-368`）；GET bible 允许 JSON null（`novels.ts:100-106`，`service.py:218-219`）；export 校验 `text/markdown`（`novels.ts:131`，`routers/novel.py:134`）；DELETE→`{deleted:true}`；`/strawberry`→`{username,balance}`（`me.py:127-130`）；探针全部通过 |
| 2 | §5.4 状态/原因 | 通过 | 标签表 `novels.ts:145-148`；横幅与操作 `GateBanner.tsx:16-44`：setup_running 无横幅+进度行（`NovelWorkbench.tsx:205`）、awaiting_setup→立项卡编辑器（:211）、awaiting_review→插一句话/继续写下 N 章→`continue`、awaiting_plan→细纲编辑器三操作、awaiting_end→`end/confirm`/`end/reject`(1–10+可选一句话)、completed→导出、paused 九种原因各自文案与 `resume`/调整对话框/设置、failed 只显示原因；按钮统一 `disabled={busy}`+「正在处理…」（:17）；`mutating` ref 防重入（`NovelWorkbench.tsx:136, 140`）；错误经 `ErrorNotice`（:188, 150） |
| 3 | 轮询 | 通过（见可优化 1） | setTimeout 链 3000ms，仅 `setup_running/running`（`NovelWorkbench.tsx:25, 92-109`）；`visibilitychange` 隐藏暂停、可见立即补一轮（:103-107）；状态变化 effect 重建并清理（:108-109）；操作后 `load(true)`（:144, 149）；按 `${owner}:${id}` 重挂载（:30），`useAccountRequest` 卸载即 abort（`useAccountIdentity.ts:36-41`），写入前 `isCurrent()`+`nextBook.id===id`（:68-69, 75-77） |
| 4 | 向导校验 | 通过（见可优化 2） | 思路 1–2000+计数（`NovelWizard.tsx:96, 152`）；章数 1–200 且最少≤最多（:97-99）；每章字数 1000–4000 默认 2000（:38, 100）；改编参数折叠默认 6/3（:39-40, 154）；顾问≤5 且第 6 位勾选禁用（:107-108，`NovelModelFields.tsx:25`）；solo 顾问 fieldset disabled+置灰+说明（`NovelModelFields.tsx:35-37`）；`byok:self` 仅 `catalog.byok && allowed` 时出现（`novels.ts:160`）；估算 600ms 防抖（:80-92）；成功 `router.push` 保留 embed（:133） |
| 5 | 新增后端接口与测试 | 通过 | 所有权 `owned()`（`service.py:216, 228` → 404「小说不存在」）；开关/白名单经同一 `workshop_user`（`routers/novel.py:51-58, 12-18`）；未裁剪：`bible()` 直接 `json.loads(bible_json)` 不调用 `trim_bible`（:220），存库 bible 由 runner 以全量 `bible_json` 经 `apply_archive(deepcopy(full))` 追加后整份写入（`runner.py:271, 314`，`writing.py:214-215`，`bible.py:56-92`，`store_db.py:287, 309-312`），`trim_bible` 只用于一次性视图（`context.py:12-19, 125, 145, 187`）；探针：全量 `chapter_summaries==chapters_done`，detail 裁剪为 10；notes `ORDER BY created_at,id` 字段齐全、未下发为 null（:225-235）。测试 `test_novel_p2_api.py` 以 60 章/60 人物/60 伏笔/60 留言夹具做**整体相等**断言（:102, 119）并逐项验长度（:104-108, 120），越权 404、开关关 404、白名单 403、缺书 404、无圣经 null 各有用例，不存在空集恒真 |
| 6 | 前端源码断言测试 | 通过 | §7.3 五条：侧栏六项顺序（`test_novel_p2_frontend.py:27`）、`novel` 抽屉+`/novels?embed=1`（:37-40）、三页存在（:47-51）、§5.4 全部标签与横幅文案（:54-70）、接口路径（:83-100）。路径扫描有正控 `paths >= {5 条}`（:99）防空集；变异探针：加入 `${API_BASE}/novels/nope` 或把 `pause` 改成 `halt` 均被捕获（实扫 17 条路径 ⊆ 24 条后端路由）。`read()` 断言路径在仓库内（:13-16），不依赖 git |
| 7 | 嵌入模式 | 通过 | 内链 `novelHref` 带 `embed=1`（`novels.ts:155`；`NovelShelf.tsx:53, 65`、`NovelWizard.tsx:133, 143`、`NovelWorkbench.tsx:172, 186`）；「在新页面打开」`target=_blank` 去 embed（`NovelShelf.tsx:61`、`NovelWizard.tsx:143`、`NovelWorkbench.tsx:202`）；子页 `postMessage(..., window.location.origin)`（`NovelShell.tsx:11`、`NovelWorkbench.tsx:206`），父页校验 `origin` 与 `source===iframe.contentWindow`（`page.tsx:148`） |
| 8 | 不得改动项 | 通过 | `git diff -- backend/tests globals.css package.json lockfile proxy.ts` 为空；`service.py`/`routers/novel.py` diff 删除行数 0，仅新增两函数/两路由；`page.tsx`/`Sidebar.tsx` 为新增项与 `/novels` 专属高亮分支（`Sidebar.tsx:252`），不影响既有五项；1207 条既有+新增小说测试全绿 |

## 5. 备注

- 规格 §5.3 要求 solo 模式「只显示主编裁决和理由」，实现据此在 solo 下也隐藏了「用户留言回应」（`DeliberationTimeline.tsx:70`）；是否要在 solo 下保留留言回应，属规格口味，作者可拍板。
- 本路未验证：`npm run lint`、`npm run build`、各尺寸/主题截图、360px 底栏六项实机。
