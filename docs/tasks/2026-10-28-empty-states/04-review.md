# 04 独立复核：空态与文案（UI 复核第三批）

- 复核对象：基线 `f6adca6` 上的候选改动（`git diff HEAD` + 9 个未跟踪新测试文件），快照哈希 `aa9aef9f6cc4699f`（与任务书、`verify/gate-record.md` 一致）。
- 复核方式：只以本副本落盘文件为依据；§6 第 1–6 条全部亲自复跑；第 7 条无浏览器，只审 `verify/` 脚本逻辑与 `results/*` 数据一致性。实现方报告 `03-report.md` 只当线索，每条结论均独立验证。
- 复核环境备注：本沙箱注入的 `NO_PROXY=...,[::1]` 会让 httpx 在 pytest 收集阶段抛 `InvalidURL: Invalid port: ':1]'`（17 个文件收集错误，已单独复现确认为环境问题、与候选代码无关）。跑 pytest 时用 `env -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY -u http_proxy -u https_proxy -u no_proxy` 清除代理变量后执行，与 `03-report.md` §4 备注的做法一致。

---

## 1. 结论

**不通过**——代码、测试、门禁与实测证据全部合格（§6 第 1–7 条、§3.2/§3.3/§5、8 个变异实验全数通过），唯一阻断项是交付物 `03-report.md` 留有 2 处未填充的模板占位符（`:135` 的 `__PYTEST_RESULT__`、`:195` 的 `__SKIP_NOTE__`），违反规格 §7 第 4 条；属文档级修复，按第 7 节指令改完后只需复核该文件，无需重跑代码门禁。

## 2. 验收标准逐条核验（规格 §6 第 1–7 条）

| # | 判据 | 期望 | 实际值（本副本实测） | 判定 | 证据 |
|---|---|---|---|---|---|
| 1 | `cd frontend && npx tsc --noEmit` | 退出码 0 | 退出码 0 | 通过 | 本次运行输出 `tsc exit=0`；`gate.sh` 行 `PASS tsc exit 0` |
| 2 | `npm run lint` | 0 errors，warnings ≤ 25 | 0 errors、25 warnings | 通过 | 本次运行输出 `✖ 25 problems (0 errors, 25 warnings)`；gate `PASS lint errors 0`、`PASS lint warnings 25<=25` |
| 3 | `npm run build` | 退出码 0 | 退出码 0（next 16.4.3，19 行路由输出） | 通过 | 本次后台运行 `build exit=0`；gate `PASS build exit 0`、`PASS next version 16.4.3` |
| 4 | 后端全量 pytest | 0 failed、0 skipped、passed ≥ 7774+39 | **7813 passed、0 failed、0 skipped**（两次独立全量：直接跑 292.92s，gate 内 286.06s）；新测试收集 39 条 | 通过 | 输出 `7813 passed, 35 warnings in 292.92s (0:04:52)`；gate `PASS pytest failed 0`、`PASS pytest skipped 0`、`PASS new tests collected 39>=16`、`PASS pytest passed >= 7774 + new 7813>=7813`。§3.4 的 7 条 git 历史跳过项一条都未出现 |
| 5 | 结构判据（`verify/gate.sh`） | 143 项 0 失败 | **143 项，FAIL=0**，退出码 0 | 通过 | 本次运行 `== 汇总: 143 项，FAIL=0`；`grep -c '^PASS'` = 143。关键项本副本另行直查：「旧社交画像」grep = 0（HEAD 正控 6）；「社交画像（旧版）」出现 7 处 ≥ 6（HEAD 0）；含 `useAccountIdentityPending()` 的文件恰 10 个（`git grep` HEAD = 0）；`aria-label=` = 119 ≥ 118；`onClick={() => setImageMode(true)}` = 0；`type="file"` = 2；diff 新增行 `font-semibold/font-bold/fontWeight/<strong` = 0、「·」= 0 |
| 6 | 改动集合 | 只出现 §3.1 白名单路径与规格目录 | `git status --porcelain -uall` 共 53 条（22 修改 + 31 未跟踪），白名单外 **0** 条 | 通过 | 用 gate.sh 同款 ALLOW 正则过滤后为空；修改文件集合与 §3.1 白名单一一对应（22 个），未跟踪为 9 新测试 + 规格目录（02/03/04-brief、verify/*、results/*） |
| 7 | 真实浏览器实测 | 66 项 0 失败 + 补测；【改】HEAD 败/候选过，【回归】两边过 | 本复核无浏览器，改为审脚本逻辑与落盘数据：**`compare.py` 在本地重放 `results/*.json` 得到 66 项、FAIL 0，且 66 行表格与 `gate-record.md` §3 逐行逐字一致（mismatch=0）** | 通过（基于证据审计） | 见下方「第 7 条证据审计」 |

**第 7 条证据审计（ measure.py / compare.py / extra_probe.py / results/*）**

- 脚本哈希与记录一致：`gate.sh` = `bee7d1f54557eef0`、`measure.py` = `03bdf7cc273932cf`（即记录所称 v2）、`compare.py` = `24a2000e7204148f`、`extra_probe.py` = `0703793fb414d9b2`，四条都与 `gate-record.md` 写的相同。
- `measure.py` 的每条判据确实量到了对应事实：SSR 用带 Cookie 的 `page.request.get` 取原始 HTML 找「正在加载身份…/请登录后」；脚本晚到用路由延迟 3 秒 + 1s/2.5s/6s 三点取 `body.innerText`；profile 慢/500 用路由拦截并在文档开始时清 `fiona_user`（`profileRequests` 计数证明请求确实被拦到 1 次）；开场判据同时量布局（页头之下、釉片之上、视口内、minHeight≥40、无粗体、无中点、无横滚）与网络（非 GET 计数），并先在 HEAD 与候选两边做「打字回车数到 1 次 /api/chat」的计数器正控（`counterControl` 两边均为 1，证明计数器有效）；按住 Enter 用 `keyboard.down` 重复 5 次模拟 auto-repeat，候选 `nonGetDuring=0`，textarea 值为「聊聊今天\n\n\n\n」——说明重复 Enter 被 `e.repeat` 守卫拦住、只走了浏览器默认换行，没有发送。
- 关键数据抽查（`results/cand-measure.json` vs `head-measure.json`）：SSR `/novels/new` HEAD `{pending:False, login:True}` → 候选 `{pending:True, login:False}`；late-js `/novels` HEAD 1s/2.5s 显示 login、候选显示 pending；profile 慢 4s 候选 1s/2.5s pending、8s wizard=True；profile 500 两边 8s 都回到 login 文案（【回归】，即规格 §1 的已知局限）；工作室抽屉 h1 候选 1×1px、HEAD 174×42px；书斋 0 本书候选可见「新建一本」1 个且 0 个在页眉、HEAD 为 2/1；匹配页右侧文字候选 258 字、h2「匹配是什么」、link `/agents/me` + `_top`、禁用词 false、leftSize 12px，HEAD 右侧 0 字；历史页候选可见文字「自定义区间|从|不限|到|不限」、chip 高 40、showPicker 点击 1 次/回车累计 2 次、填 `2026-10-27` 后显示「2026年10月27日」、只设「到」时「全部」allOn=False、en-US 与 zh-CN 可见文字全等，HEAD 为「自定义区间|至」（原生框）；语音 m390 按住时 `data-voice-status` 气泡可见、文字「松开发送」、`pointer-events:none`、`aria-hidden`、在按钮上方视口内，d1440 按住时气泡不显示而桌面短字可见。以上与 `gate-record.md` 表格逐条吻合。
- **隐私测法 v1→v2 修正的审查：修正站得住。** v1 的 `rendered` 只看 `getClientRects()` + 高度，而 Chromium 对收起的 `<details>` 用 `content-visibility` 隐藏内容、段落仍有布局盒，所以 v1 在候选收起态量出 `[真×8]`（`cand-measure.json` privacy `rendered` 全真、无 `boxed` 字段），与 HEAD 无折叠块的全真不可区分——这正是记录里「4 项两边都判失败」的原因，且失败方向是「量不出收起」，不会把坏实现判成好实现。v2 只加 `checkVisibility()` 并同时输出 `boxed` 列：候选收起态 `rendered=[真,假×7]`、`boxed=[真×8]`（自证 v1 恒为真的机理），HEAD `details=None`、8 段全真（正控成立）；展开后 `rendered` 全真、8 段文字与 HEAD 收起态逐字相同（`texts` 全等）。v2 用同一脚本量 HEAD 与候选、只重跑隐私部分，`compare.py` 明确支持用 v2 覆盖 privacy 段（argv[3]/argv[4]），回归行「展开后与 HEAD 逐字相同」比对的也是 v2 的 HEAD 数据。程序正当、数据自洽。
- `extra_probe.py` / `extra-probe.json`：小说功能关闭时三个 novel 路径两种宽度下「小说工坊尚未开放」`{all:1, visible:1}`，「正在加载身份…」「请登录后」全为 0，HEAD 与候选相同——证明新 pending 分支没有吞掉 ErrorNotice；工作室嵌入 h1 候选 1×1px 且 `getByRole('heading',{name:'短片工作室',level:1})` 仍数到 1（读屏可读），HEAD 174×42。`inAriaSnapshot` 两边皆 false，记录如实声明该子项不作为证据（定位到了别的 header），未夸大。
- HEAD 正控（新测试）：`results/head-newtests.txt` 恰 39 条 FAILED、0 passed、无收集/导入错误，按文件分布 4+4+4+5+4+8+4+3+3 = 39，与候选上每个文件的测试数一一对应，即**每个新测试函数都含至少一条在 HEAD 上失败的断言**（规格 T9 总则满足）。
- 审计中未发现数据与表格不一致之处；`gate-record.md` §1 的 143 项 / 7813 / 25 warnings 等数字均被本次复跑独立重现。

## 3. §3.2 / §3.3 / §5 逐条核验

### §3.2 必须原样保留

| 项 | 判定 | 证据 |
|---|---|---|
| page.tsx 计数锁：`type="file"`=2、`<ComposerImageMenu`=1、`<VoiceButton`=1、`drawer-panel`=6 | 通过 | 本副本 grep 实测 2/1/1/6；gate 对应行 PASS |
| page.tsx 结构锁：`<ChatScrollArea`、`</ChatScrollArea`、`chat-message-layer`、`<Glaze as="footer"`、`chat-latest` 各 1；`data-chat-panel` 恰 1 行；「回到最新」1 | 通过 | grep 实测全部 =1；`data-chat-panel` 行数 =1 |
| page.tsx 字重锁：`className="readout font-normal"`=2、无 `<b>`、无 `font-semibold` | 通过 | grep 实测 2/0/0 |
| page.tsx 禁项：`title="语音转文字"`、`aria-label="按住说话"`、`>上传参考图<`、`<ImagePlus`、`<Mic`、`onClick={() => setImageMode(true)}` 均 0；开场 chip 无图标 | 通过 | grep 实测全 0；开场 JSX 三个 button 内只有文字（diff `:2611-2622`） |
| 图片菜单 `items` 原文不动、未抽共享变量 | 通过 | HEAD 与候选的 items 数组按括号配平提取后逐字节相同（长度均 1827） |
| `handleSend` 一字不动（两段 sha256 锁） | 通过 | 直接比对：HEAD 与候选 `const handleSend = async` 至 `handleSendRef.current = handleSend;` 全段逐字节相同（sha256 前 16 位 `78e9df25c2271992`）；`test_claude_agent_frontend.py:117-123`、`test_claude_agent_r1_frontend.py:137-144` 两段 sha256 锁在全量 7813 条中通过；page.tsx diff 恰 4 个 hunk（:959 注释、:1789 开场函数、:2233 e.repeat、:2608 空态），均在 T3 授权范围 |
| 工作室提醒 useEffect 锚点：`createStudioNoticePoller` 往前最近 `useEffect(() => {` 之间无新插入 | 通过 | HEAD 与候选分别做锚点检查，两者区间内 `useEffect(() => {` 计数均为 1 |
| 费用/快捷键文案不复制：「每条消息消耗…10…颗草莓」1、`"平台模型 · 每条 10 颗草莓"` 2、「平台模型每条消息消耗 10 颗；自带模型聊天不扣」1、「Enter 发送，Shift + Enter 换行」1、「有新的工作室提醒 · 」1 | 通过 | grep 实测 1/2/1/1/1 |
| 设备时区扫描（page.tsx、ConversationPicker、AgentExchangeWorkspace、history/page.tsx，含注释） | 通过 | 四文件 diff 新增行匹配 `toLocale*|toDateString(|getHours(|getMinutes(|getDate(|getDay(|getMonth(|getFullYear(` = 0；四个整文件全文匹配也为 0 |
| VoiceButton.tsx 全部现有行原样（HINT_KEY、localStorage、try/catch 各 1、stateLabel、指针状态机等）；导入行不变；不新增 hook/try；根元素 children 为数组且 button 是直接子元素 | 通过 | `git diff` 该文件删除行 = 0、新增仅 T8 那 5 行（`data-voice-status` 气泡）；导入仍只有 react / lucide-react / `@/lib/utils` 三行；`try {` 全文件 =1（gate PASS）；结构未动 |
| ChatModelSection.tsx：被锁三段仍各为一行、不带属性的 `<p>`，生图在选 Claude 之前；第一段 `<p className={noteClass}>` 文字一字不改；其余四段原样无属性；`noteClass` 不动；删除确认文案 1 处；`useConfirm()` 保留 | 通过 | 8 段与 HEAD 逐字节比对全部相同（第一段仅按 T6 加 `className={noteClass}`，文字不变；其余 7 段属性串为空即无属性）；三段锁定行均为单行且以 `<p>` 开头；顺序检查 `生图 < 选 Claude` 成立；删除确认文案计数 =1、`useConfirm()` 在（`test_empty_states_settings_privacy.py` 断言，全量通过） |
| history/page.tsx：`@/lib/beijingTime` 导入与 `formatBeijingTime(` 保留；`<MessageText text={msg.content} highlight={query} />` 原样 | 通过 | diff 显示导入行只增 `formatBeijingDateLong`；新测试断言三者均在且通过 |
| profile/page.tsx：h1 保留 `${embedded ? " sr-only" : ""}`；`.join("、")` 保留、无 `.join(" · ")` | 通过 | diff 中 h1 模板串原样；grep 实测 1 / 0 |
| AgentExchangeWorkspace.tsx：广场标题 h1 恰一行；无 `<b className="readout">`；「平台官方 AI · 无真人用户」恰 1 | 通过 | grep 实测 `<h1` =1 行、`<b className="readout">` =0、该文案 =1 |
| AgentMemoryPanel.tsx：清空确认文案恰 1；`useConfirm()` 与 `isCurrentOwner()` 复查保留 | 通过 | `test_empty_states_agents.py:76-80` 断言计数 =1、`useConfirm()` 在、`isCurrentOwner()` ≥2，全量通过 |
| match/page.tsx `:74` `{/* 匿名头像 */}` 原样 | 通过 | diff 未触及；文件内计数 =1（gate 与新测试均 PASS） |
| `app/novels/page.tsx` 不动；StudioShelf 嵌入态「新建项目」仍是原生 `button`；404 时恰 1 个 ErrorNotice | 通过 | `git diff --name-only` 无该文件（gate PASS）；M8 变异实验证明 `test_novel_p2_r1.py::test_r1_all_pages_map_closed_workshop_404` 确实锁住 ErrorNotice 恰 1 个；`test_empty_states_studio.py` probe 断言 button 标签与 `ml-auto` |
| `components/novel/**`、`app/novels/**` 无 `max-md:`、十六进制色、`rgba(`/`hsla(`、`font-family`、`font-mono` | 通过 | diff 新增行匹配上述模式 = 0 |
| 通用：不新增加粗；新文案不用「·」；被嵌入页面只 `mobile:`；`aria-label=` ≥118；不新增原生 `confirm(`/`alert(` | 通过 | 新增行粗体 0、「·」0、`max-md:` 0（novel/studio/match/profile 范围）、aria-label 119、`confirm(|alert(` 0；新增 `<b` 0 |

### §3.3 测试替身的限制

| 项 | 判定 | 证据 |
|---|---|---|
| 新 hook 只用 `useEffect` / `useSyncExternalStore` / 模块级变量 / 已导入的 `getUsername`、`ensureAccountIdentity`；无 `useId`、`dispatchEvent`、`location`、`document`；不新增 `@/lib/auth` 导入 | 通过 | `useAccountIdentity.ts:60-86` 通读：只有 `let identityRecoverySettled`、`identityPendingListeners`（模块级）、`subscribeAccount`（本文件既有）、两个快照函数与 `useEffect`+`useSyncExternalStore`；导入行未动（`:3-4`）；gate `lib new code avoids useId/dispatchEvent/location/document` = 0；`test_empty_states_identity.py:228-244` 源码契约同锁 |
| `lib/useAccountIdentity.ts` 只有新增、没有改动 | 通过 | `git diff` 删除行 = 0（gate PASS）；追加块与规格 T1-1 代码逐字比对 `verbatim match: True`（追加在文件末尾即 `useAccountRequest` 之后，仍满足「在 `useAccountIdentity` 之后」，报告 §7 已如实声明该偏差） |
| `lib/auth.ts` 未动 | 通过 | `git diff --name-only HEAD -- frontend/lib/auth.ts` = 0 行；不在 git status 中 |
| T1 的 1–6 号文件不新增 `cn` / `@/lib/utils` 导入 | 通过 | novel/studio 六文件 diff 新增 import 行仅 6 条，全部是 `useAccountIdentityPending` 那一行 |
| 内层新增 prop 可选且默认 false，`test_studio_kb_frontend.py:196-197` 直接挂 `AccountKbWorkbench` 传 `{owner:'', embedded:false}` 仍渲染「请登录后打开导演知识库。」 | 通过 | 10 处内层签名均为 `identityPending = false` + `identityPending?: boolean`（gate 10×2 PASS）；全量 7813 条含该既有用例通过 |
| 新 hook 模块级状态单向；新测试场景隔离（单独 probe / cache.clear） | 通过 | `test_empty_states_identity.py` 每场景独立 node 进程（`probe()` 每次 `subprocess.run`）；`test_empty_states_novel.py:38-41` 空用户名场景单独一次 `probe()` 并注释原因；`test_empty_states_studio.py:41` SSR 场景 `cache.clear()` 后切 `env.mode='ssr'` |
| 新测试离线、不依赖 git 历史、不读仓库外文件 | 通过 | 9 个文件路径全部 `Path(__file__).resolve().parents[2]` 定位仓库根；无任何 `git` 子进程调用；node 子进程 cwd 均为 `frontend/`（仓库内依赖）；用 node 的 4 个文件（identity、novel/studio 经由既有驱动、voice_hint）都带 socket/DNS 阻断 fixture 或复用既有驱动的离线约定 |

### §5 不允许的做法

| 项 | 判定 | 证据 |
|---|---|---|
| 不改既有测试（除授权一行） | 通过 | `git diff --numstat HEAD -- backend/tests/` 只有 `1 1 test_ui_polish_settings_drawers.py`；hunk 头 `@@ -80,7 +80,7 @@`，改动行即第 83 行，仅把 `"旧社交画像"` 换成 `"社交画像（旧版）"` |
| 不新增依赖；不改 `lib/auth.ts`；共享 hook 不用禁用 API | 通过 | `package.json`/lockfile/`next.config.ts` 不在改动集合；上节 §3.3 各行 |
| 开场按钮不调用 `handleSend`、不发任何请求、不自动发送；不复制费用文案；chip 无图标 | 通过 | 三个函数体（`page.tsx:1792-1804`）只含守卫 + `composeSongSection("聊聊今天")` / `setImageMode(true)`+聚焦 / `fileInputRef.current?.click()`；awk 切片 grep `handleSend|handleSendRef|apiFetch|fetch(` = 0；M3 变异证明测试能捕获；费用文案计数与 HEAD 相同；button 内无组件标签 |
| 不改 `handleSend`、`ChatScrollArea`、`ComposerImageMenu`、图片菜单 items；`handleKeyDown` 只加第一行 | 通过 | 上节 sha256/逐字节比对；`ChatScrollArea.tsx`、`ComposerImageMenu.tsx` 不在改动集合；`handleKeyDown` diff 仅 +1 行 `if (e.repeat) return;`（hunk `@@ -2219,6 +2233,7 @@`），其余由 `test_empty_states_chat_openers.py:64-73` 锁定并通过 |
| 不去掉工作室嵌入态「新建项目」；不改 `app/novels/page.tsx`；不改 match `:74` 注释 | 通过 | 按钮仍是原生 `<button type="button">`、仅 className 加条件 `ml-auto`（diff `StudioShelf.tsx:70-71`）；另两项见 §3.2 表 |
| 不删改被锁隐私段落；不给被锁三段加属性或拆行 | 通过 | §3.2 表 ChatModelSection 行（8 段逐字节相同、三段单行无属性） |
| 不改 VoiceButton 任何现有行 | 通过 | diff 删除行 = 0 |
| 不新增粗体/「·」文案/嵌入页 `max-md:` | 通过 | §3.2 通用行 |
| 白名单外无改动 | 通过 | §6-6 行：白名单外 0 条 |
| 三份文档各只改一行 | 通过 | `git diff --numstat` = README 1/1、PLAN 1/1、ARCHITECTURE 1/1，且都只替换「旧社交画像」→「社交画像（旧版）」 |

### T1 新 hook 正确性审查（任务书第 4 条）

- **SSR 与水合**：服务端渲染走 `serverIdentityPending`（恒 true），10 个内层在 `!owner`（服务端 `serverIdentity` 恒空串）时渲染「正在加载身份…」；水合首帧 React 对 `useSyncExternalStore` 仍用 server 快照，与 SSR HTML 一致，**不产生水合不匹配**；水合完成后切到客户端快照。`test_empty_states_studio.py` 的真实 React SSR 探针（`renderToStaticMarkup`）证实输出含「正在加载身份…」且不含登录文案。
- **本地有用户名不闪**：`clientIdentityPending = !getUsername() && !identityRecoverySettled`，本地有名时首次客户端渲染即 false，不会出现「正在加载身份…」；`test_empty_states_identity.py::test_known_username_is_not_pending` 锁定。实测数据佐证：正常网络 1s 起显示内容（gate-record §3 late-js 6000ms 两点均无 pending/login）。
- **找回三条路径**：`ensureAccountIdentity`（`lib/auth.ts:34-66`，未动）永不 reject——成功写入 `fiona_user` 并 dispatch 事件后 resolve 用户名；401 走 `redirectExpiredSession()`（`window.top` 优先，规避 iframe 自套）返回空串；其他错误/断网 `.catch(() => "")` 返回空串。三条路径 `.finally` 都把 `identityRecoverySettled` 置 true 并通知订阅者：成功→`getUsername()` 有名，pending=false 且 owner 有名，显示正常内容；失败/断网→pending=false、owner 空，回到原「请登录后…」（规格 §1 已知局限，实测 profile-500 行佐证）；401→整页跳 `/login?reason=expired`。`void …finally` 不会产生未处理 rejection（promise 恒 resolve）。
- **多组件同时挂载**：每个外层组件的 effect 都会调 `ensureAccountIdentity()`，但 auth.ts 内部有 `identityRecovery` 在途去重与 `identityRecoveryAttempted` 守卫，**只会发一次 `GET /api/profile`**（实测 `profileRequests=1` 佐证）；落定后 `identityPendingListeners.forEach` 通知所有实例统一重渲染。`settled` 守卫避免后续挂载重复触发。
- **跨标签登出**：`subscribeIdentityPending` 同时订阅 `subscribeAccount`（storage / fiona-user-changed 事件），登出清 `fiona_user` 会触发重渲染；此时 `settled` 已为 true，pending=false、owner 空 → 显示原登录文案，语义正确（确实已登出）。auth.ts 的 `identityVersion` 机制会在下次 `getUsername()` 时重新武装找回，若 Cookie 仍有效身份会被恢复——期间短暂显示登录文案与 HEAD 行为一致，不是回归；单向 `settled` 是规格 §3.3 的明文设计。
- **监听泄漏**：`subscribeIdentityPending` 返回的清理函数把回调移出 `identityPendingListeners` 并调用 `subscribeAccount` 的退订，`useSyncExternalStore` 在卸载时执行清理；模块级 Set 中只会有在挂载的订阅者，**无泄漏**。`forEach` 通知期间即便有订阅者被移除，JS Set 迭代语义也安全。

## 4. 变异实验记录

方法：变异前把目标文件按字节备份到 `/tmp/b3-mut/backups/`（仓库外）并记录 sha256；改后跑目标测试；跑完拷回备份并校验 sha256 一致；全程未用 `git checkout`。共做 **8 个变异（任务书列举的 7 个 + 自加 1 个），全部被新测试或既有测试捕获（8/8 变红）**。pytest 均清代理变量后运行。

| # | 变异 | 目标文件（sha256 前 16 位，改前=改后已验证） | 变红的测试 | 结果 |
|---|---|---|---|---|
| M1 | 去掉内层 `identityPending = false` 默认值 | `NovelShelf.tsx`（`e4042ffaa9ab9ce7`） | `test_empty_states_novel.py::test_novel_pages_wire_identity_pending_before_login[NovelShelf.tsx]`（assert `'identityPending = false' in source` 失败） | 捕获 |
| M2 | `serverIdentityPending` 改为返回 false | `useAccountIdentity.ts`（`01887c487a94a734`） | `test_empty_states_identity.py::test_server_snapshot_is_pending`（`assert False is True`）；另单独验证 `test_empty_states_studio.py::test_studio_page_ssr_shows_identity_loading_instead_of_login` 也红（SSR HTML 变回「请登录后打开工作室。」） | 捕获 |
| M3 | `startChatOpener` 里加 `void handleSend();` | `page.tsx`（`1a646cb3b09a4573`） | `test_empty_states_chat_openers.py::test_chat_openers_offer_three_draft_only_actions`（函数体禁词 `handleSend`） | 捕获 |
| M4 | 去掉语音气泡的 `!showHint &&` | `VoiceButton.tsx`（`427de6565d25ebda`） | `test_empty_states_voice_hint.py::test_voice_status_bubble_respects_first_use_hint`（showHint=true 时仍能取到 `data-voice-status` span） | 捕获 |
| M5 | 去掉书斋页眉「新建一本」的空态隐藏条件（`{!(owner && !error && !loading && books.length === 0) && …}` 整体去包裹） | `NovelShelf.tsx`（`e4042ffaa9ab9ce7`） | `test_empty_states_novel.py::test_shelf_empty_state_has_exactly_one_new_book_link`（驱动 probe 断言 `2 !== 1`，行为级捕获） | 捕获 |
| M6 | 把隐私第一段挪回 `<details>` 里 | `ChatModelSection.tsx`（`783eb46cb4f03db8`） | `test_empty_states_settings_privacy.py::test_first_privacy_paragraph_is_visible_before_switch_and_save`（位置断言 `19205 < 18655` 失败） | 捕获 |
| M7 | 删掉 `dayFace` 的「不限」兜底 | `history/page.tsx`（`9804879e0aa9dfde`） | `test_empty_states_history_dates.py::test_date_chips_render_chinese_day_faces_and_drop_native_placeholder`（`'"不限"' in source` 失败） | 捕获 |
| M8（自加） | 把 NovelWizard 的 `!catalog` ErrorNotice（「小说工坊尚未开放」）换成「正在加载身份…」，模拟 pending 分支吞掉错误态 | `NovelWizard.tsx`（`6ad6605af3ae44a7`） | 既有 `test_novel_p2_r1.py::test_r1_all_pages_map_closed_workshop_404[NovelWizard-/api/novels/catalog]`（ErrorNotice 计数 `0 !== 1`） | 捕获 |

全部变异结束后：每个文件 sha256 与备份前一致（脚本内 `assert` 逐个校验并打印 `restored sha256 verified`）；总哈希 `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` 前 16 位仍为 `aa9aef9f6cc4699f`；`git status` 仍为 53 条、白名单外 0 条；变异备份均存于 `/tmp/b3-mut/backups/`（仓库外），仓库内无残留。完整日志：`/tmp/b3-mut/log.txt`。

结论：新测试既能源码级也能行为级（node 驱动 probe、真实 React SSR）区分对错实现，且规格声称的既有测试锁（ErrorNotice 恰 1 个）确实存在并有效。

## 5. 必须修复项

1. **`03-report.md` 两处模板占位符未填充**（违反规格 §7 第 4 条「第 4 条写 passed / skipped 数」与 T10 交付要求）：
   - `:135`：`→ __PYTEST_RESULT__`；
   - `:195`：句尾 `__SKIP_NOTE__`。
   报告开头自称「只记录本工作树中的实际结果」，占位符使全量 pytest 结果与跳过说明这两个必填项在交付物里缺失。仅此一项，不涉及任何代码/测试改动。

## 6. 可优化项（不阻塞合并）

1. `03-report.md` §4-3 写「18 个路由生成成功」，本次 build 输出为 19 行路由（含 `/_not-found` 与 `/manifest.webmanifest`）；§4-5 写「7 行」，实为「社交画像（旧版）」出现 7 次、分布在 6 行（profile `:136` 一行含 2 处）。均属表述精度问题，判定不受影响。
2. 按住 Enter 实测中 textarea 值为「聊聊今天\n\n\n\n」：`if (e.repeat) return;` 早退发生在 `preventDefault()` 之前，重复 Enter 走浏览器默认行为向草稿插入换行。无发送、无扣费、无害（且规格 §5 禁止改 `handleKeyDown` 其余部分，本批无法也无需处理），仅作记录：如日后想让草稿保持干净，需另行立项评估。
3. hook 的 `identityRecoverySettled` 单向设计意味着跨标签登出→Cookie 仍有效→身份被重新找回的窗口期内，页面短暂显示「请登录」而非「正在加载身份…」。与 HEAD 行为一致、符合规格 §3.3 明文设计，建议在报告的已知局限里补一句，方便下批复核。
4. `test_empty_states_identity.py` 的 React 替身每次渲染都新订阅且不退还（`identityPendingListeners` 在单进程内累积）。不影响现有断言（`notified >= 1` 方向安全），如日后加「恰好通知 N 次」类断言需先改替身。

## 7. 给执行者的二次修改指令

只改 `docs/tasks/2026-10-28-empty-states/03-report.md`，两处，不得触碰其他任何文件：

1. 第 135 行：把 `__PYTEST_RESULT__` 替换为你在修复环境实际复跑 `cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider` 得到的结果，格式与 §4 其他条目一致，须含 passed / failed / skipped 三个数（本复核两次实测均为 **7813 passed、0 failed、0 skipped**，耗时约 290 秒；如你复跑数字不同，以你的实测为准并停下来说明）。
2. 第 195 行：把 `__SKIP_NOTE__` 替换为如实说明，例如「实际运行 0 skipped，§3.4 列出的 7 条 git 历史相关测试均未发生跳过。」（若你的环境确有跳过，逐条写明是哪几条、原因是否为读不到 `.git`。）
3. 改完自验并回报：`(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` 前 16 位仍须为 `aa9aef9f6cc4699f`（03-report.md 是未跟踪文件，不影响该哈希）；`grep -n '__[A-Z_]*__' docs/tasks/2026-10-28-empty-states/03-report.md` 为空；`git status --porcelain -uall` 条目数不变。无需重跑任何代码门禁。

## 8. 哈希核对

- 开始：`(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` = `aa9aef9f6cc4699f3816489c23e47f1b2b175c79820774911cc81631001a31b7`（前 16 位 `aa9aef9f6cc4699f`，与任务书预期一致）。
- 结束（本文件写入前后各算一次，均相同；本文件为未跟踪文件、不在 `backend/tests/test_empty_states_*.py` 内，不影响该哈希）：`aa9aef9f6cc4699f3816489c23e47f1b2b175c79820774911cc81631001a31b7`。
- 结束 `git status --porcelain --untracked-files=all`：54 条 = 开始 53 条 + 本文件（`docs/tasks/2026-10-28-empty-states/04-review.md`），别无增减；白名单外 0 条。变异备份与日志均在 `/tmp/b3-mut/`（仓库外），仓库内无残留。
