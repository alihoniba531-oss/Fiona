# 小说工坊 P2 第 2 轮独立复核（核验第 1 轮返修单 F1–F9）

复核对象：工作树 `.worktrees/fiona-novel-p0`（基线 8c58057，未提交改动）。核验范围只限 `05-fix-r1.md` 的 F1–F9 是否真正修好、有无回归；新发现只列为「可优化」。
复核方式：通读返修后的全部前后端改动；用 `p2.diff` 重建返修前的每个文件并与当前逐一 `diff`（新文件取 `+` 行，修改文件以 8c58057 为底打补丁），确认改动只落在返修单范围；对照后端 `service.py`/`runner.py`/`billing.py`/`schemas.py` 复核校验口径；在 backend 下跑 `test_novel_p2_api.py` + `test_novel_p2_frontend.py` + `test_novel_p2_r1.py`；另在 scratchpad 里按 CI 后端作业的条件（有 node、无 `frontend/node_modules`）复跑新测试做正控。未改仓库任何文件，未跑 npm、未用浏览器、未联网、未读密钥。

验收方实测（引用，不重复）：lint 0 错误 25 警告、tsc 通过、build 含三个 `/novels` 路由、后端全量 5093 passed；Playwright 各宿主尺寸无横向溢出、窄时切三标签；360 宽向导价格可见；书架每轮 1 个 `/novels`；已完结书首屏无逐章请求；运行态 11 秒内 `/bible` 仅 1 次；独立页侧栏昼夜切换与余额可见；默认三顾问 + 写手 DeepSeek Flash。

## 1. 结论：**不通过**（F1–F9 本身全部核验通过；但新增测试文件会让 CI 后端作业变红，须补 1 处 skip 守卫，见 §3）

- 本地：`test_novel_p2_api.py` + `test_novel_p2_frontend.py` + `test_novel_p2_r1.py` → **74 passed**。
- 返修单范围内的 9 项均已在代码层面落实，前后端口径一致，返修前复核 A 判定通过的契约没有被破坏（§4）。
- 唯一必须修复项不属于 F1–F9 的功能，而是 R1 新增的 `backend/tests/test_novel_p2_r1.py` 对 `frontend/node_modules/typescript` 的硬依赖：CI `quality.yml` 的 backend 作业只做 `actions/checkout` + pip 安装、不跑 `npm ci`，ubuntu-latest 自带 node，于是 14 条探针全部以 `MODULE_NOT_FOUND` 失败（已在 scratchpad 复现：`14 failed in 0.47s`）。仓库里同类测试 `test_claude_agent_r1_frontend.py:147-158` 的先例是缺包即 `pytest.skip`。改法只有几行，改完即可通过。

## 2. F1–F9 逐条核验

| 项 | 结论 | 证据（文件:行号） |
|---|---|---|
| F1 工作台按容器宽度切换 | **通过** | `NovelWorkbench.tsx:265` 外层 `@container min-w-0 [overflow-wrap:anywhere]`；`:266` 标签栏 `@[1040px]:hidden`；`:267` `@[1040px]:grid @[1040px]:grid-cols-[minmax(180px,.65fr)_minmax(480px,2fr)_minmax(300px,1fr)]`（180+480+300+2×20=1000 ≤ 1040，不会溢出）；`:268/:269/:278` 三栏 `min-w-0 break-words`，非当前标签时 `hidden @[1040px]:block`；阅读列 `ChapterReader.tsx:33` 仍 `max-w-[38em]`。Tailwind 4.3.0 原生支持：`node_modules/tailwindcss/dist/lib.js` 中 `functional("@",…)` 对任意值生成 `@container (width >= 1040px)`，无需插件/配置。JS 侧 `:153-161` 用 `ResizeObserver contentRect.width >= 1040` 决定 `notesVisible`，与 CSS 容器查询同测 content-box，口径一致。源码契约测试 `test_novel_p2_frontend.py:127-138`（含旧写法 `minmax(150px` 必须不存在）。 |
| F2 手机价格行 | **通过** | `NovelModelFields.tsx:23-24` 取当前所选模型价格；`:32` 新增 `hidden … mobile:block whitespace-normal break-words` 说明行，平台模型数字用 `.readout`，`byok:self` 显示完整「我的模型（厂商·型号）· 不扣草莓」；`<option>` 文案 `lib/novels.ts:165` 未变。`test_novel_p2_r1.py:295-306` 对 10 个角色逐一断言。 |
| F3 后端两字段只增不改 + 前端按需请求 | **通过** | 后端：`service.py:159-162` `summary()` 追加整数 `max_chapters`（原 13 个键原样）；`:204` 多查 `edited_by_user` 列，`:207` 从原字典中排除该原始列后追加 `edited_by_user: bool(...)`，原 `chapter/title/status/words/flags` 不变；与返修前 `service.py` 相比只多 8 行、无删除；`routers/novel.py`、`runner.py`、`billing.py` 未动。测试 `test_novel_p2_api.py:177-251` 整体相等断言（`set(summary) == 原13键 ∪ {max_chapters}`、`detail['chapters'] == expected`、改稿后 `edited_by_user` 变 `True`、单章接口整数型保持）。前端：书架 `NovelShelf.tsx:30` 只 `listNovels`，`:39-52` 首载与 3 秒轮询分离；工作台 `NovelWorkbench.tsx:74-95` `load()` 只取 detail；当前章 `:26` 签名 `[status, words, flags, edited_by_user]` + `:117-131` 按签名/切章/显式刷新令牌读取；圣经 `:133-150` 只在 `bible_version` 变化或首次打开圣经标签；留言 `:162-179` 只在可见、`status`/`chapters_done` 变化或提交后；改稿 `:273` 以 `{chapter}` 令牌与摘要同一次 `setBookState` 发布（`:84-90`），只请求一次；留言提交 `:282` `{notes:true}`。漏刷新排查：`plan/redo` 会把章节置为 `planning`（`service.py:338`）再回到 `awaiting_plan_approval`，签名两次变化都会重取细纲；`setup_running→awaiting_setup` 时 `bible_version 0→1` 触发首次圣经读取供立项卡使用；状态切换必触发留言重取。探针 `test_novel_p2_r1.py:189-233`。 |
| F4 独立页侧栏 | **通过** | `NovelWorkbench.tsx:235` 非嵌入根 `h-dvh overflow-hidden`，`:237` 内层 `flex min-h-0 flex-1`，`:238` `main overflow-y-auto`；嵌入模式保留 `min-h-screen mobile:min-h-dvh`。与书架 `NovelShelf.tsx:54-56`、向导 `NovelWizard.tsx:160-162` 同骨架。 |
| F5 错误只显示一次 / 不被轮询清掉 / 404·403 映射 | **通过** | `lib/novels.ts:149-157`：404 且 detail 恰为 `Not Found` → 「小说工坊尚未开放」；404 中文 detail 原样；403 → 「你的账号暂未开通小说工坊」；`access` 参数保留但忽略，书架 `NovelShelf.tsx:33`、向导 `NovelWizard.tsx:91/109/155`、工作台 `NovelWorkbench.tsx:93/128/141/170/202` 走同一函数。读错误与操作错误分开：`:49-53`；轮询成功只 `setReadError("")`（`:92`），`operationError` 只在下次操作开始（`:194`）或「关闭提示」（`:243`）清除。`errorTarget:"local"` 时页顶不写错误（`:204`），用于立项卡/细纲（`:270`）、改稿（`:273`）、留言（`:282`）、调整对话框（`:229`），各子组件就近显示：`ChapterReader.tsx:30,36`、`NotesPanel.tsx:19,28`、`SetupEditor.tsx:103-109,115`、`PlanEditor.tsx:14,24`、`NovelSettingsDialog.tsx:40,44`；横幅/页头操作仍走页顶（`:208` 默认 `page`）。探针 `test_novel_p2_r1.py:141-154`、`:236-249`（409 跨一次成功轮询仍只显示 1 条）、`:287-292`（三页关闭态 404 文案）。 |
| F6 估算依赖 / budget_80 / 立项卡口径 | **通过** | 估算：`NovelWizard.tsx:74-79` `estimateInput` 不含预算，`:80` 另组 `input`；`:98-113` 效果依赖 `[step, catalog, estimateInput, beginCost]`，请求体 `budget_strawberries: 1`，后端 `service.py:153-157` `estimate()` 只做 `validate_selection` + `estimate_cost`，确不使用预算；探针 `:252-265`（改预算不重发、改批次重发）。budget_80：`NovelSettingsDialog.tsx:10-13` `min = max(原预算+1, ceil(spent×1.25)+1, _budget_at_pause+1)`；后端 `service.py:393-394` 要求 `spent×5 < budget×4` 且（budget_80 时）`budget > _budget_at_pause`，`runner.py:189-190` 在 budget_80 暂停时必写 `_budget_at_pause`（`billing.py:37` `NovelBudgetExceeded.status="budget_80"`、`llm_router.py:48 BudgetExhausted` 两条路径都经 `_pause`）；前端下限 ≥ 后端下限（`ceil+1 > 1.25×spent` 恒成立），不会出现 PATCH 成功后 resume 409；不满足时 `:32` 就近提示「预算至少要 N 草莓才能继续」，`:45` 输入框 `min`。探针 `:171-186`（四组边界 + 暂停预算 1000 时要求 1001）、`:322-331`。立项卡：`SetupEditor.tsx:19-21` `compactSetupText` 的字符类逐一对应 Python `\s` 的 Unicode 空白（U+0009–000D、001C–0020、0085、00A0、1680、2000–200A、2028、2029、202F、205F、3000）加同一组引号、省略号折叠，`:25` 用 `Array.from` 按码点计数与 `len()` 一致，`:33` 外形 ≥20 对应 `schemas.py:181` `minimum=20 if initial`；422 时 `:54-63` 先按后端字段路径定位，无路径则 `:41-52` 标出本次改动字段，再退到整体提示。探针 `:171-186` 以后端 `compact()` 为基准比对 6 组样例（引号、省略号、特殊空白、补充平面字符），`:332-341` 验证 422 落到字段。 |
| F7 默认配置 | **通过** | `NovelWizard.tsx:20-38` `defaultNovelAgents`：critique 默认（`:62`）；默认角色 = 必选 + reviewer + `plot_architect/character_advocate/twist_designer`；默认模型表与返修单逐项一致；首选不在可选列表时退回首项。可选列表顺序 `lib/novels.ts:160-167` 以 `allowed_models[role]` 顺序 `flatMap`，无限制时按 `catalog.models` 顺序。探针 `:157-168` 精确核对七角色、顺序与回退。 |
| F8 章名去重（建议） | **通过** | `lib/novels.ts:169-171` 只剥开头「第[0-9一二…两]+章」及紧随空白/标点；用于目录 `ChapterList.tsx:27` 与正文标题 `ChapterReader.tsx:34`；正文草稿（`ChapterReader.tsx:35` 用原 `chapter.body`）、存储、导出未动。探针 `:147-149`、`:309-311`。 |
| F9 小项（建议） | **通过** | ① 留言时间 `NotesPanel.tsx:30` `formatNovelDate` + `<time dateTime=…Z>`；② 伏笔 `BiblePanel.tsx:21` `planted_chapter===0 → 立项时`；③ Esc `NovelShell.tsx:5-8` 判 `key/defaultPrevented/isComposing/dialog[open]/closest(input,textarea,select,[contenteditable])`，`:15` 接入；④ 关闭按钮 `page.tsx:2745` class 与设置抽屉 `:2707` 逐字相同，`:2733` 面板 `outline-none`；⑤ `NovelWorkbench.tsx:238` 嵌入模式 `mobile:pb-6`，不再加 tabbar 留白；⑥ 三个栏目 `:268/:269/:278` 常驻、`role="tabpanel"`、`aria-labelledby` 指向 `:266` 的 `id`，右栏三面板 `:280-282` 常驻并以 `hidden` 切换，`aria-controls` 全部有目标，`ChapterList.tsx:25` `aria-current="true"`；⑦ `ChapterList.tsx:3,7-14` 改用 lucide 图标，保留文字与 `title`。测试 `test_novel_p2_frontend.py:141-153`、`test_novel_p2_r1.py:226-229`、`:268-279`。 |

## 3. 仍需修复项

**R2-1【必须，回归】`backend/tests/test_novel_p2_r1.py` 在 CI 后端作业里会整文件变红。**
- 现象：`DRIVER` 第 20 行 `require(path.join(frontend,'node_modules/typescript'))`，`probe()`（`:130-138`）只在 `shutil.which("node")` 为空时 skip。`.github/workflows/quality.yml:28-46` 的 backend 作业只 `checkout` + `pip install` 后 `python -m pytest -q`，不安装前端依赖；ubuntu-latest 自带 node。按同样条件在 scratchpad 复现（复制 `frontend/lib`、`frontend/components/novel` 与该测试，不带 `node_modules`）：`14 failed in 0.47s`，首个错误 `Cannot find module '…/frontend/node_modules/typescript'  code: 'MODULE_NOT_FOUND'`。
- 改法（任选其一，几行即可）：在 `probe()` 开头增加 `if not (ROOT / "frontend/node_modules/typescript").exists(): pytest.skip("frontend/node_modules/typescript is unavailable")`；或照 `test_claude_agent_r1_frontend.py:147-158` 的先例，先用 `node -e "require.resolve(...)"` 探测缺包再 skip。两种都不改既有断言。
- 为什么算回归：返修前后端全量在 CI 是绿的；本轮新增文件引入了对仓库中被 gitignore 的目录的硬依赖。与 2026-10-10「本地绿、CI 红」同一类问题。

## 4. 回归核对（对比返修前 `p2.diff`）

- **请求路径/请求体**：`lib/novels.ts` 与返修前相比只改了类型（`max_chapters`、`edited_by_user: boolean`、`NovelChapter` 用 `Omit`）、`novelErrorMessage` 映射、`novelModelOptions` 改为按 `allowed` 顺序 `flatMap`（选项集合不变）、新增 `displayNovelChapterTitle`/`formatNovelDate`；`listNovels/getNovel/.../exportNovel` 的 URL、方法、请求体一行未改。
- **§5.4 状态文案与操作**：`GateBanner.tsx`、`DeliberationTimeline.tsx`、`PlanEditor.tsx`、`NovelContent.tsx`、`NovelStates.tsx`、三个 `app/novels/**/page.tsx`、`Sidebar.tsx`、`routers/novel.py` 与返修前逐字节相同；`NovelWorkbench.tsx` 中页头四按钮、暂停可见状态（`:255`）、关卡横幅接线（`:264`）、`act` 调用的动作名与请求体（`:270`：`setup/approve` 差量体、`plan/approve` `{beat_sheet}`/`{}`、`plan/redo` `{text}`）未变。
- **P1 语义/计费/运行器**：`git status` 中后端只有 `novel/service.py`（本单授权的两字段）与 `routers/novel.py`（与 R0 相同，仅两只读路由）；`runner.py`、`billing.py`、`schemas.py` 未修改。
- **既有测试**：`git diff -- backend/tests frontend/app/globals.css frontend/package.json frontend/proxy.ts` 为空；`test_novel_p2_api.py` 原 174 行、`test_novel_p2_frontend.py` 原 124 行均为当前文件的逐字前缀（`diff` 仅 `174a175,251`、`124a125,153`），原断言未放宽。
- **白名单**：`git status --porcelain` 改动均在 §1 白名单与本单授权范围内；`package.json`/lockfile 无改动。
- **本地门禁**：三份 P2 测试 74 passed；lint/tsc/build/全量由验收方复跑（见页首）。

## 5. 可优化项（非阻断，供下一轮或 P3 参考）

1. **切章时一帧空态闪烁**：`NovelWorkbench.tsx:270` 把 `ChapterReader` 的 `loading` 从返修前的 `chapterLoading || (selectedChapter != null && !currentChapter)` 改为只看 `chapterLoading`，而 `setChapterLoading(true)` 要等 effect 的微任务（`:124,:131`）才执行，切章后首帧 `currentChapter` 为 null、`loading` 为 false，会先画一帧「章节正文写好后…」空态再变为加载态。恢复原来的 `|| (selectedChapter != null && !currentChapter)` 即可。
2. **章名去重边界**：`displayNovelChapterTitle` 对恰好只有「第二章」的章名会返回空串（目录有「待定章名」兜底，正文 `ChapterReader.tsx:34` 的 h2 会只剩「第 2 章　」）；对「第三章节的秘密」这类以「章」为词首的标题会误剥。可在正则后追加「剥完为空则回退原文」。
3. **宽布局下的 tabpanel 语义**：三栏在 ≥1040px 时标签栏 `display:none`，三个栏目仍带 `role="tabpanel"`/`aria-labelledby` 指向不可见按钮；屏幕阅读器会读到没有 tablist 的 tabpanel。可按 `wideLayout` 条件去掉这两个属性。
4. **首次打开圣经标签的一次冗余请求**：`:147-149` 在版本已加载的情况下首次切到「圣经」标签仍会再请求一次 `/bible`；返修单允许，但可在 `bibleVersion.current === version` 时跳过。
5. **留言标签可见时每轮都重取 `/notes`**：`:178` 在运行态且留言标签可见时每 3 秒请求一次；符合返修单措辞，若想再省可改为只在 `pending_notes` 或 `chapters_done` 变化时请求。
6. **预算下限比后端多 1**：当 `spent×1.25` 非整数时，前端 `ceil(spent×1.25)+1` 比后端实际需要的 `floor(spent×1.25)+1` 多 1 草莓（如 spent=81：后端 ≥102，前端提示 ≥103）。方向安全，与返修单「大于 ceil(spent×1.25)」措辞一致，仅记录。
7. **budget_80 下页头「继续」按钮**：仍会直接 `resume` 并收到 409「请先调高预算再继续」显示在页顶（返修前已如此，复核 A 已通过）；可在 `pause_reason==="budget_80"` 时让页头「继续」也打开调整对话框。
