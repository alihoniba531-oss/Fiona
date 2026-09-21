# 独立复核报告：Fiona 前端视觉重设计 v2（磨砂玻璃仪器 + 一条信号线）

复核日期：2026-09-12。复核员为全新上下文，只使用四样输入：`02-spec.md`、`docs/design/chloe-ui-proposal.html`、`scratchpad/codex/run3.diff`（5803 行）、`scratchpad/shots3/`（19 张 1280×800 截图，`console-errors.json` 为 `{}`）。另用 `scratchpad/baseline/extract/Fiona/frontend` 做了一次全目录 `diff -rq` 以核对改动范围。

## 1. 结论

**最终结论（第 2 轮复核后）：通过。** 第 1 轮列出的两条必须修复项已按 `05-fix-round1.md` 修复并逐条核验（见文末「第 2 轮复核」）：① `ChatBubble` 文字块守卫去掉 `!message.cardData`、顺序调整为 名字标签 → 正文 → 卡片 → 帮我读 → Meta；② `MyAgentWorkspace` 恢复「查看已保存的公开名片」链接，条件 / href / 文案与基线一致。返修增量只落在这两个文件，lint 0 errors / 28 warnings，tsc 退出 0。

第 1 轮结论（保留存档）：**不通过**——结构复刻的保真度整体很高（§8 全部命令通过、§2.4 对照表逐行基本复刻、19 张截图无旧 HUD 痕迹），但有两处违反 §2.2 行为红线的功能回退必须返修：① 工具卡片回到消息里之后，卡片回复的正文提示（天气建议句 / 「搜到了…」）被 `ChatBubble` 的旧守卫吞掉不再显示；② `MyAgentWorkspace` 无授权删除了「查看已保存的公开名片」链接。两处都是机械小改，修完即可通过。

## 2. §8 验收命令逐条

全部在 `frontend/` 目录亲自执行（`npm run build` 未跑，按任务书引用派单方 `codex/gates-run3.log`）。

### A. 门禁

**`npm run lint`**

```
> frontend@0.1.0 lint
> eslint

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/page.tsx
    77:10  warning  'MiniCloudCard' is defined but never used   @typescript-eslint/no-unused-vars
   168:7   warning  'DEMO_MESSAGES' is assigned a value but never used
   248:10  warning  'allUsers' is assigned a value but never used
   286:9   warning  'nlsWsRef' is assigned a value but never used
   287:9   warning  'mediaRecorderRef' is assigned a value but never used
   288:9   warning  'audioCtxRef' is assigned a value but never used
   292:10  warning  'peerRooms' is assigned a value but never used
   293:10  warning  'activePeer' is assigned a value but never used
   294:10  warning  'pendingMatches' is assigned a value but never used
   295:10  warning  'cardPositions' is assigned a value but never used
   298:10  warning  'peerConnected' is assigned a value but never used
   304:10  warning  'myGender' is assigned a value but never used
   305:10  warning  'matchPref' is assigned a value but never used
   549:20  warning  '_' is defined but never used
   553:16  warning  '_' is defined but never used
   624:18  warning  '_' is defined but never used
   753:51  warning  '_' is defined but never used
   757:53  warning  '_' is defined but never used
   821:9   warning  'saveUserSettings' is assigned a value but never used
   841:9   warning  'handleCardExpire' is assigned a value but never used
   849:9   warning  'handleAcceptCard' is assigned a value but never used
   870:9   warning  'handleSkipCard' is assigned a value but never used
   906:9   warning  'handleClearChat' is assigned a value but never used
  1002:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1340) change on every render...  react-hooks/exhaustive-deps
  1439:9   warning  'openPeerChat' is assigned a value but never used
  1478:9   warning  'handlePeerKeyDown' is assigned a value but never used
  1685:23  warning  Using `<img>` could result in slower LCP...  @next/next/no-img-element

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/plaza/page.tsx
  593:21  warning  Using `<img>` could result in slower LCP...  @next/next/no-img-element

✖ 28 problems (0 errors, 28 warnings)
```

判定：**通过**（0 errors，28 warnings ≤ 35）。`MiniCloudCard` 未使用是基线已有（diff 里没有任何 `<MiniCloudCard` 的 `-`/`+` 行），不是本次引入。

**`npx tsc --noEmit`**

```
（无输出）
TSC_EXIT=0
```

判定：**通过**。

**`npm run build`**：未亲自运行。派单方 `codex/gates-run3.log` 记录 Turbopack 构建成功、14 条路由（/、/_not-found、/agents、/agents/[id]、/agents/me、/community、/history、/login、/manifest.webmanifest、/match、/plaza、/profile、/settings、Proxy）。判定：按派单方结果记为通过。

### B. 旧类彻底清除

```
== B1 == grep -rnE "hud-[a-z0-9-]+|liquid-glass|lg-refract|hud-card-float|shutter-handle|plaza-card" app components --include='*.tsx' | grep -v "hud-like" | wc -l
       0
== B2 == grep -nE "hud-(panel|corners|card-float|pill|label|pulse|btn|avatar-ring|orb|ekg|cyan)|liquid-glass|shutter-handle|hud-scan|body::after" app/globals.css | wc -l
       0
```

判定：**通过**（期望 0 / 0）。

### C. 组件退场

```
== C1 == grep -rnE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l
       0
== C2 == ls components/TopBar.tsx components/AmbientHUD.tsx components/HudOrb.tsx components/HudOrb3D.tsx components/StarField.tsx 2>&1 | grep -c "No such file"
5
== C3 == test -f components/Signal.tsx && echo ok
ok
```

判定：**通过**（0 / 5 / ok）。

### D. 英文伪仪表标签与眉标清除

```
== D1 == ... | wc -l
       0
== D2 == grep -rn "uppercase tracking-wider" app components --include='*.tsx' | wc -l
       0
== D3 == grep -c "AI 分身交流 · 内测" components/AgentExchangeWorkspace.tsx
0
```

判定：**通过**。

### E. 侧栏 5 项

```
== E1 == grep -c 'label: "' components/Sidebar.tsx
5
== E2 == grep -nE '"对话"|"分身"|"广场"|"世界"|"设置"' components/Sidebar.tsx | wc -l
       5
13:  { href: "/", icon: MessageCircle, label: "对话" },
14:  { href: "/agents/me", icon: Bot, label: "分身" },
15:  { href: "/agents", icon: Orbit, label: "广场" },
16:  { href: "/plaza", icon: Globe, label: "世界" },
17:  { href: "/settings", icon: Settings, label: "设置" },
```

判定：**通过**。

### F. 三栏退场、下拉退场、信号线

```
w-1/4 page.tsx: 0
<select ConversationPicker: 0
<select AgentExchangeWorkspace: 0
role=listbox: 1
<Signal page.tsx: 1
<Signal login: 1
100vw - 64px: 0
replace T: 1
```

判定：**通过**（全部符合期望）。

### G. 令牌换血

```
#12100a: 0
--background 0E1219: 1
.glass-card {: 1
.echo::after {: 1
lg-refract layout: 0
@layer components: 1
```

判定：**通过**。

### H. 交互逻辑保留

```
== H1 (app/page.tsx) ==
handleNewChat 2
handleDeleteConversation 3
handleSelectConversation 2
toggleInlineVoice 2
setRecording 6
handsFree 14
voiceOn 8
asrSessionRef 11
handleSelectReferenceImage 2
moveReferenceImage 5
handlePickReferenceImages 2
MiniCloudCard 1
showHistory 3
onPointerDown 1
== H2 (components/AgentExchangeWorkspace.tsx) ==
assertAccountAgent 4
ExchangeDocuments 3
ExchangeTopic 2
act( 4
load( 5
download( 3
isDraftReviewExchange 4
isArtifactApproved 4
completionLabel 2
stageLabel 2
data-exchange-id 1
data-exchange-detail 1
data-official-agent 1
data-exchange-artifact 1
```

判定：**通过**（每行 ≥ 1）。

### J. 结构复刻

```
J1 rounded-2xl/3xl:        0
J2 bg-primary/5|10 etc:    0
J3 →:                      0
J4 ↔:                      0
tablist: 1
radio: 1
glass-card AEW: 7
主创初稿: 3
<progress: 0
glass-card plaza: 2
bg-primary text-primary-foreground history: 0
bubble-user history: 1
sticky top-0 MyAgent: 1
sticky top-0 AEW: 2
```

判定：**通过**。注：J3 为 0 的原因之一是 `page.tsx` 把 `normalizeForTTS` 里的字符类 `[→←↑↓…]` 改写成 `[→←↑↓…]`、并把注释里的箭头改成中文——功能完全等价，只是绕开了 grep，可接受。

### I. 范围

```
git status --porcelain -- backend desktop docs README.md PLAN.md CLAUDE.md frontend/lib frontend/components/ui frontend/next.config.ts frontend/package.json frontend/package-lock.json | grep -vE "^\?\? docs/(design|tasks)/" | wc -l
      72
```

原始数字 72 全部是仓库开工前就存在的未提交改动（`backend/*`、`docs/ARCHITECTURE.md`、`frontend/lib/*.ts` 等），规格也注明「以开工前快照为准」。为了排除误判，另做 `diff -rq baseline/extract/Fiona/frontend ↔ frontend`（排除 node_modules/.next）：**差异文件恰好是白名单 20 个修改 + 1 个新增（Signal.tsx）+ 5 个删除**，外加 `next-env.d.ts`（Next 自动生成、已在 `frontend/.gitignore:41` 忽略，不算改动）。`frontend/lib/**`、`components/ui/**`、`next.config.ts`、`package*.json`、`proxy.ts`、`ChatScrollArea.tsx`、`SolarSystem3D.tsx`、`Earth3D.tsx` 全部与基线字节一致。判定：**通过**。

## 3. 行为红线核对（§2.2）

| 红线 | 结果 | diff 证据 |
|---|---|---|
| `page.tsx` 只允许删除星空、语音球栏、卷帘门、DATA STREAM 栏、activeCards/enlargedCard/hoveredCard/handleDismissCard/cardDialogRef、放大层及专用样式常量、历史抽屉「查看完整历史记录」按钮 | **符合**。删除的 state/handler 清单：`activeCards`、`hoveredCard`、`enlargedCard` + 其焦点 `useEffect`、`cardDialogRef`、`chatCollapsed`、`recordingBars`(useMemo)、`handleDismissCard`、`getWeatherTheme`、`matchOpen/communityOpen/profileOpen`；全部在授权范围内。`recording`/`voiceText`/`asrSessionRef`、所有语音 effect、`handleNewChat`/`handleDeleteConversation`/`handleSelectConversation`、参考图逻辑、账号切换清理、`MiniCloudCard`、匹配弹窗逻辑均在。 | run3.diff L1905–1960、L2036–2044、L2107 |
| `AgentExchangeWorkspace.tsx` 只允许删 `<progress>`、眉标、`bg-primary/5` 提示区、大图标/示例话题/选择按钮的搭档卡壳、`<select>`；handler/请求/校验/下载/轮询/`data-*` 必须还在 | **符合**。`act(`/`load(`/`download(`/`assertAccountAgent`/`submit`/`validTopic`/`validMaxTurns`/轮询（未出现在 diff 中，即未动）/`data-exchange-id`/`data-exchange-detail`/`data-official-agent`/`data-exchange-artifact`/`data-exchange-message` 全部保留；`<select>` 换成 `input type=number min=2 max={turnLimit}`，`turnLimit = official ? 99 : 6`（当前文件 L124），与 §2.5 一致。 | run3.diff L3798–3838、L4020–4028 |
| 不改交互语义 | **两处违反，见 §6 必须修复项 1、2**。① `page.tsx` L1285：`cardData: undefined` → `cardData: card`，本身是「工具卡回到消息里」的必要接线，但 `ChatBubble.tsx` L269 的旧守卫 `!message.cardData && …` 未同步调整，导致有卡片的回复**不再渲染正文**（基线里 `content: tip` 是可见文字）。② `MyAgentWorkspace.tsx` 删掉了 `{savedAgent?.is_public && <Link href={/agents/${id}}>查看已保存的公开名片</Link>}` 及 `ExternalLink` import，规格 §6.2 未授权删除这条到 `/agents/[id]` 的导航。 | run3.diff L2086–2094；L5061–5066（基线 MyAgentWorkspace.tsx L153） |
| `aria-*` / `inert` / `tabIndex` / 键盘处理 / `embed=1` | **符合**。抽屉的 `id`、`inert`、`aria-controls`、`onKeyDown` 均为 diff 上下文行（未改）；`embedded` 判断在 9 个页面/组件均保留；`ConversationPicker` 新增 `role="listbox"/option`、`aria-selected`、`aria-label`；AEW 标签由 `aria-current` 换成 `role="tab" aria-selected`（规格要求）。 | run3.diff L2649–2697、L4580–4606、L3724–3728 |
| 不引入依赖 / 不用 `next/font/google` / 不新增 `!important` | **符合**。`package.json`/`package-lock.json` 与基线一致；`layout.tsx` 无任何 `font` 引用；`grep -nE "^\+.*!important" run3.diff` 为空。 | — |
| `.dark` 机制、`@custom-variant dark`、CSP | **符合**。`<html className="dark h-full">` 与 `classList.toggle("dark")` 未动；`next.config.ts` 与基线一致。 | run3.diff L1200、L5247–5250 |
| 白名单外文件 | **符合**（见 §2 I）。 | — |
| 附带观察（不违规） | `page.tsx` 把两句提示文案「右边卡片有详情」「搜到了，看右边卡片」改成「下面的卡片有详情」「搜到了，详情在下面的卡片里」，随布局调整，合理。`ExchangeDocuments` 的「作品 Markdown」按钮从「无稿件时不渲染」改为「无稿件时 disabled」，下载逻辑不变。`AgentMemoryPanel` 新增读取 `data.revision`（规格 §6.3 要求）。 | run3.diff L2077–2082、L3974、L4097–4100 |

## 4. §2.4 对照表逐行核对 + §2.5 逐条扫描

| 应用位置 | 判定 | 依据 |
|---|---|---|
| `login/page.tsx` ↔ `[data-screen="login"]` | **复刻了** | 双圆 SVG 28px → `.echo` Chloe 44px → 「每个人自己的分身。」→ `<Signal mode="idle">` → `glass rounded-[10px] border p-[22px]` 面板 → 表单 + 「新用户赠送 <b class=readout>200</b> 颗草莓」。截图 01 与原型 L412–426 一致。 |
| `page.tsx` 对话区 ↔ `[data-screen="chat"]` | **复刻了（一处轻微偏差）** | `.convs`：`aside.glass w-[260px]`，头部 h-16「对话」+ Clock + Plus，条目 title/`readout` 时间/悬停 Trash2，页脚「对话仅你可见」+「完整历史」（diff L4555–4619）。`.talk-head`：`grid-cols-[auto_minmax(120px,1fr)_auto] h-16`，glyph + 名字 + 「AI 分身 / 仅你可见」｜`<Signal>`｜state-dot + 状态词 + 「朗读」「免提」chip（L2182–2292）。`.transcript`：分身 = 琥珀方块 + 名字 + `bubble-ai` 无底 640；我方 = `bubble-user` 520；时间 `readout`（ChatBubble L4305–4333、L4451–4456）。`.composer`：`footer.glass absolute bottom-0` → `--fill` 内框 → chips → 麦克风/按住说话/发送 → 提示行（L2397–2500）。头部与输入区 `absolute` 浮在 `absolute inset-0 pt-16 pb-[172px]` 的滚动区之上。**偏差**：原型的 chips 在 `.composer-box` 内部 textarea 下方一行（原型 L491–497），实现把 chips 放在内框上方一行（截图 02）；§5.3 只说「那行小按钮 → chip」，未要求挪位，不计违规，列入可优化。 |
| `MyAgentWorkspace.tsx` / `agents/me` / 分身抽屉 ↔ `[data-screen="agent"]` | **复刻了** | 粘性 `glass` `.page-head` h1「分身」+ 一句话（L4990–4998）；`grid gap-10 lg:grid-cols-[minmax(0,1fr)_340px]`；`.field-row` 96px 头像 + 名称；简介；性格（`em` 仅自己可见）；`.switch-row` → `glass-card` label + checkbox；`btn btn-primary` + 「有未保存的修改」；右栏 `AgentIdentityCard`（tag「AI 分身」+ readout「名片预览」+ `.echo` 40px + 简介 + glyph 页脚）→ `.note` 盾牌 → `.memory`（`border-t pt-[18px]`，h3 + readout「修订 N / 仅自己可见」，`li` 13px 灰 `border-b`，页脚「刷新」quiet + 红「清空记忆与个人画像」）。截图 05/11/12 与原型 L506–543 对得上。 |
| `AgentExchangeWorkspace.tsx` / `/agents` / 广场抽屉 ↔ `[data-screen="plaza"]` | **复刻了** | 粘性 `.page-head` 「广场」+ 原型原句 + 「管理我的分身」+ 右侧「刷新」quiet（L3699–3709）；`role="tablist"` 下划线 5 标签，待处理数 `readout` 琥珀（L3724–3728）；单人体验 = 一句 12px 说明 + `.partners` 三张紧凑 `glass-card role=radio`（h3 + tag「官方 AI」｜bio line-clamp-3｜模型 readout；无大图标/示例话题/按钮；选中 `border-[color:var(--amber-ink)]`）+ 选中后同页下方 `ExchangeStartForm`（`lg:grid-cols-[minmax(0,1fr)_220px]`：textarea min-h-150 + 计数 readout｜回复次数 `.field` 数字 + 「开始讨论」`btn-primary w-full h-10` + 说明段）（L3743–3755、L3807–3838）；记录 = `.records-head` 五列 + 表格式行（话题｜搭档｜tag｜readout 次数｜readout MM/DD 或 HH:mm）（L3777–3793）；详情 = 返回 quiet → `.detail-head`（h2 前 40 字 + `.meta` 双方名 + 模型 readout + 「第 <b>N</b> 次 / M」+ 右 tag）→ `.stages` 三段（`messages.some(stage===key)` → 勾）→ `.work` glass-card（头行「当前作品」+ 字数 readout + tag；正文；底部三个下载 `btn`）→ `.turns`（28px 序号 readout｜名字 + 阶段 tag｜13px 正文）→ 结束态「停止交流」禁用 + 「已结束，记录仅你可见」（L3868–3926、L3933–3977）；发现分身 = `.people` 三列 `.person`（glyph + h3｜12px 简介｜「邀请交流」btn）（L3763–3770）。截图 06/13 与原型 L546–625 一致。 |
| `page.tsx` 右侧抽屉 | **复刻了** | 四个抽屉 `glass`，头部 `border-b px-4 py-2` + `text-xs font-medium text-muted-foreground` 标题；世界抽屉 chips「热点与帖子 / 匹配」+ iframe src 切换；设置抽屉 chips「设置 / 账户」；宽度 `calc(100vw - 56px)`；阴影/边线按 §4.4。截图 07/08/09。 |
| `plaza/page.tsx`（世界） | **复刻了** | SolarSystem3D、ticker、发帖流程、`hud-like-*`、`topic-drawer-in` 保留；热点卡 `glass-card w-[220px] px-3 py-2 pointer-events-auto`，中文 13px 500 标题 + 琥珀图标 + quiet 刷新，序号 `readout`，条目 12px，「获取于」readout；`accent` prop 连同彩色描边/`textShadow`/`HOT TOPIC`/`TRANSMIT` 全部删除；话题抽屉 `glass`；FAB `btn btn-primary rounded-full`；帖子卡 `glass-card`（L2950–3375）。截图 07/14。 |
| `match/page.tsx` | **复刻了** | Earth3D 保留；最近聊天栏与聊天区 `glass-card`；匹配卡 `cloud-card glass-card`；按钮 btn/btn-primary/btn-quiet；消息块 `bubble-user`/`bubble-ai` + 方块名字标签；输入区 `--fill` 内框（L1497–1717）。截图 09/15。 |
| `profile` / `settings` / `community` / `agents/[id]` | **复刻了** | 四页都是粘性 `glass page-head`（h1 20px 500 + 13px 灰）；分区 `glass-card p-5`，14px 500 标题 + 琥珀图标；身份切换 `chip/chip-on`；危险动作 `btn btn-danger`；删除账号输入框 `.field` 样式；数字 `readout`；`rounded-2xl` 全清；community 占位 `glass-card p-8`；`agents/[id]` `max-w-[560px]` + `glass-card p-6` 错误区 + 「重新加载」quiet。截图 16/17/19。 |
| `history/page.tsx` | **复刻了** | 顶栏 `glass`，去「C」头像，「历史记录」+ `用户名 · <b>N</b> 条` readout，中间搜索 `.field` 风格，右「导出」btn；左栏 `glass`，快捷筛选 `chip/chip-on`，区间输入 `.field` + readout，日期跳转 `chip-on`；按日卡 `glass-card`（日期 + 条数 readout）；分身 `bubble-ai` + 方块名字标签，我方 `bubble-user`，无圆头像，时间 `readout`；三处 `uppercase tracking-wider` → 12px 灰中文；`mark` → `bg-[color:var(--accent)] rounded-[3px]`（L946–1176）。截图 18。 |

§2.5 逐条：

| 不允许的做法 | 扫描结果 |
|---|---|
| 只换类名不换结构 | 未发现。搭档卡、记录列表、详情页、对话列表、登录页、名片、记忆面板都是新 DOM 结构（见上表引用行）。 |
| `rounded-2xl` / `rounded-3xl` / `bg-primary/5` / `bg-primary/10` / `border-primary/25` / `border-dashed` | J1 = 0、J2 = 0。（`rounded-xl` 仅剩 `page.tsx` 历史抽屉一处与待发送图缩略图一处，规格未列入判据。） |
| 眉标 / `uppercase tracking-wider` / 按钮文字里的 `→` `↔` | D3 = 0、D2 = 0、J3 = 0、J4 = 0；截图无眉标。 |
| `<progress>` 表示回合 | 0；改为 `readout`「第 <b>N</b> 次 / M」（L3876）。 |
| `<select>` 做对话切换或回合数 | 两文件都为 0；真人邀请改 `input type=number min=2 max=6`。 |

## 5. 截图核对（逐张一句话）

| 文件 | 结论 |
|---|---|
| 01-login-dark | 双圆标、`.echo` 字标、一句话、待命信号线（亮点在左端）、玻璃面板、`readout` 200——与原型登录页一致，无旧痕迹。 |
| 02-chat-empty-dark | 两栏（260px 列表 + 对话区），侧栏 5 项 + 🍓 200 读数，talk-head 三段式，信号线平线，我方浅层块右对齐，composer 玻璃条 + `--fill` 内框 + 按住说话——无三栏/3D 球/尖括号/英文标签。 |
| 03-chat-new-dark | 新对话空态文案，信号线亮点跑到中段，「+」按钮 hover 态正常。 |
| 04-chat-after-send-dark | 分身消息 = 琥珀方块 + 「Chloe」标签 + 无气泡正文 + `readout` 时间 + 静音图标；我方块 520 以内；层次靠 1px 线。 |
| 05-drawer-agent-dark | 抽屉 `glass` + 12px 灰标题，`.page-head` 粘性，两栏 340px，名片 `.echo`、盾牌 `.note`、`.memory` 页脚「刷新 / 清空」——与原型分身页一致。 |
| 06-drawer-plaza-dark | 广场页头 + 「管理我的分身」+ 刷新 quiet，下划线标签，三张紧凑搭档卡（标题 + tag｜简介｜模型读数），无大图标/示例话题/按钮。 |
| 07-drawer-world-dark | 「世界」抽屉 chips「热点与帖子(on) / 匹配」，热点卡 `glass-card` 中文 13px 标题 + 琥珀图标 + 序号读数 + 「获取于」，太阳系保留，FAB 圆形琥珀。 |
| 08-drawer-settings-dark | chips「设置(on) / 账户」，三张 `glass-card` 分区，身份 chip，`btn` 退出，`btn-danger` 清空/删除，`.field` 输入框。 |
| 09-drawer-world-match-dark | 「匹配」chip 选中，最近聊天 `glass-card`，Earth3D 保留。 |
| 10-chat-light | 浅色主题文字全部可读，琥珀改 #9E6209，玻璃透出底场光斑，信号线可见。 |
| 11-drawer-agent-light | 浅色名片 `.echo` 描边副本可见，tag/readout/按钮对比度正常。 |
| 12-page-agents-me | 整页版：「回到对话」12px 灰在 h1 上方，其余同 05。 |
| 13-page-agents | 整页版广场，同 06。 |
| 14-page-plaza | 整页世界：7 张热点卡 `glass-card`，底部兴趣栏 `glass`，无 `HOT TOPIC`/彩色描边。 |
| 15-page-match | 整页匹配：`glass-card` 最近聊天 + Earth3D。 |
| 16-page-settings | 整页设置：粘性 `page-head` + 三张 `glass-card`。 |
| 17-page-profile | 整页旧社交画像：`page-head` + `glass-card` 分区 + `btn` 链接，无 `uppercase`。 |
| 18-page-history | 顶栏 `glass`（无「C」头像，条数读数，搜索 `.field`，「导出」btn），左栏 chip 筛选，日期卡 `glass-card`，我方 `bubble-user`，时间 `readout`。 |
| 19-page-community | 占位页 `glass-card p-8` 居中一句话。 |
| console-errors.json | `{}`，无控制台错误。 |

## 6. 必须修复项

1. **有卡片的分身回复不再显示正文（`ChatBubble.tsx` + `page.tsx` 联动回退）**
   - 现状：`frontend/app/page.tsx` L1285 把流式卡片回复写成 `{ ...m, content: tip, cardData: card, pendingTtsText: tip || undefined }`（基线是 `cardData: undefined`，卡片走右栏）。而 `frontend/components/ChatBubble.tsx` L269 的文字块守卫仍是 `{!message.cardData && !message.generationStatus && (message.content || message.isTyping) && message.content !== "[发了一张图片]" && (…)}`，于是 `content`（天气建议句「…微凉，带件薄外套。下面的卡片有详情……」或「搜到了，详情在下面的卡片里」）在界面上消失，只剩卡片和「帮我读 / 不用」按钮；基线里这句话是可见的。原型 `[data-screen="chat"]` L459–471 的分身消息是「`.msg-who` → `.msg-body` 正文 → `.tool` 卡片」三者并存。
   - 改法（只动 `ChatBubble.tsx`）：
     a. L269 的条件去掉 `!message.cardData &&`，改为 `{!message.generationStatus && (message.content || message.isTyping) && message.content !== "[发了一张图片]" && (…)}`；
     b. 把这整个文字块（L268–279，含注释）整体上移到「天气卡片」块之前（即插在 L208 `generationStatus` 块之后、L210 `{/* 天气卡片 */}` 之前），使顺序变成 名字标签 → 正文 → 天气/网页卡片 → 重新生成 → 帮我读 → meta，与原型一致；
     c. 注释「文字气泡（如果有内容或正在打字，且不是卡片）」改为「文字正文（有内容或正在打字）」。
   - 验证：`grep -c '!message.cardData && !message.generationStatus' components/ChatBubble.tsx` 期望 0；`npx tsc --noEmit` 退出 0。

2. **`MyAgentWorkspace.tsx` 无授权删除「查看已保存的公开名片」链接**
   - 现状：基线右栏在盾牌 `.note` 之后有 `{savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} …><ExternalLink size={13} />查看已保存的公开名片</Link>}`（基线 L153）；run3.diff L5065 删除了它，并把 `ExternalLink` 从 lucide import 里去掉（L4961–4962）。§6.2 只规定右栏顺序为 名片 → `.note` → 记忆面板，没有授权删除这条到 `/agents/[id]` 的导航；`/agents/[id]` 页面仍在白名单里并已重排，删掉入口等于让该页不可达。
   - 改法：在 `frontend/components/MyAgentWorkspace.tsx` 右栏 `<aside className="flex flex-col gap-5">` 内、盾牌 `.note` `<div>` 之后、`<AgentMemoryPanel />` 之前，恢复：
     ```tsx
     {savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} className="inline-flex items-center gap-1.5 text-xs text-[color:var(--amber-ink)] hover:underline"><ExternalLink size={13} />查看已保存的公开名片</Link>}
     ```
     并把 `ExternalLink` 加回 `import { ArrowLeft, ExternalLink, Loader2, Save, ShieldCheck } from "lucide-react";`。条件、href、文案与基线完全一致，只换颜色类。
   - 验证：`grep -c "查看已保存的公开名片" components/MyAgentWorkspace.tsx` 期望 1；`npm run lint` 0 errors；`npx tsc --noEmit` 退出 0。

## 7. 可优化项（不阻塞，留给用户裁决）

1. **composer chips 位置**：原型把「图片 / 生成图片」chips 放在 `.composer-box` 内 textarea 下方一行（`.composer-row`），实现放在内框上方一行（截图 02）。如要像素级贴合原型，可把 `data-chat-composer` 内第一个 `<div className="mb-1.5 flex flex-wrap …">` 移到 `--fill` 内框里、textarea 之后，与右侧麦克风/发送同一行。
2. **`pb-[172px]` 固定底距**：出现参考图缩略条（`max-h-[144px]`）、`referenceUploadError` 或 `voiceText` 时，footer 会高于 172px 并盖住最后一条消息。可用 `ResizeObserver` 量 footer 高度写进 CSS 变量，或把 footer 改成常规流布局（不 absolute）。
3. **世界 / 设置抽屉切 tab 会重载 iframe**：`src` 随 `worldTab`/`settingsTab` 切换，每次切换都会重新初始化 SolarSystem3D/Earth3D。可改成两个 iframe 常驻、用 `hidden` 切换（与原注释「不卸载 iframe，重开秒回原状态」一致）。
4. **交流详情丢了一行状态提示**：基线 `<progress>` 旁的「正在写稿、审稿或修订… / 正在整理总结… / 自动更新中… / 本次创作已结束」随进度条一起删了；现在只靠 `StatusBadge` 与粘性条的「交流正在自动更新」表达。若想保留，可在 `.meta` 行末尾加一个 12px 灰 span。
5. **广场抽屉标题**：抽屉头部仍写「分身广场」，侧栏与 `.page-head` 已改成「广场」，可统一。
6. **历史页分身名硬编码「Chloe」**：`history/page.tsx` 的方块名字标签写死 `Chloe`（该页没有 agent 数据）。可从 `/agents/me` 拉一次 `display_name`，或接受现状。
7. **`NewsCardContent.tsx` 已无引用**：放大层删除后没有任何文件 import 它；规格要求保留文件，故未动。后续若确认不再需要可单独删除。
8. **`ExchangeDocuments` 的「作品 Markdown」按钮**：从「无稿件不渲染」改为「无稿件 disabled」，展示更稳定但多一个灰按钮；两种都可。

## 第 2 轮复核（只核验第 1 轮的两条必须修复项）

输入：`05-fix-round1.md`（返修指令）、`scratchpad/codex/run4.diff`（返修后累计 diff，5820 行）。方法：`diff run3.diff run4.diff` 看增量；判据命令在 `frontend/` 亲自执行；对照当前文件核对顺序与链接内容。

### 增量范围确认

`diff run3.diff run4.diff` 的全部差异只落在两个文件：`components/ChatBubble.tsx`（文字块从原第 268–279 行整段上移到「天气卡片」块之前，守卫去掉 `!message.cardData &&`）与 `components/MyAgentWorkspace.tsx`（lucide import 恢复 `ExternalLink`；右栏插入一行链接）。`run4.diff` 仍为 26 个文件（20 改 + 1 增 + 5 删），与白名单一致；`diff -rq baseline ↔ frontend` 结果与第 1 轮相同（差异文件 = 白名单 + 被忽略的 `next-env.d.ts`）。判定：**除这两处外无其他改动**。

### 通用判据

```
npm run lint   → ✖ 28 problems (0 errors, 28 warnings)
npx tsc --noEmit → （无输出）TSC_EXIT=0
```

判定：**通过**（0 errors，warnings 28 ≤ 28）。

### 修复项 1：`ChatBubble.tsx` 带卡片回复的正文不再被守卫隐藏

判据原始输出：

```
grep -c '!message.cardData &&' components/ChatBubble.tsx
0
awk '/message.cardData\?\.subtype === "weather"/{w=NR} /!message.generationStatus && \(message.content \|\| message.isTyping\)/{t=NR} END{print (t<w)?"order ok":"ORDER WRONG"}' components/ChatBubble.tsx
order ok
```

渲染顺序（当前文件行号）：名字标签 L183–186 → 图片/参考图 L189–204 → `generationStatus` L206–208 → **文字正文 L211–222**（守卫为 `!message.generationStatus && (message.content || message.isTyping) && message.content !== "[发了一张图片]"`）→ 天气卡 L224 → 网页卡 L251 → 重新生成 L281 → 「帮我读 / 不用」L290 → Meta 行 L308。与 `05-fix-round1.md` 要求的「名字标签 → 文字正文 → 天气卡 / 网页卡 → 帮我读 / 不用 → Meta」一致；卡片与正文之间未加额外 margin（沿用外层 `gap-1.5`）。run4.diff L4353–4366 为新增的文字块、L4460–4477 为原位置的删除，内容逐字相同，只有守卫少了 `!message.cardData &&`。

判定：**通过**。

### 修复项 2：`MyAgentWorkspace.tsx` 恢复「查看已保存的公开名片」链接

判据原始输出：

```
grep -c '查看已保存的公开名片' components/MyAgentWorkspace.tsx
1
grep -c 'ExternalLink' components/MyAgentWorkspace.tsx
2
grep -c 'savedAgent?.is_public && <Link' components/MyAgentWorkspace.tsx
1
```

逐字对照（基线 L153 ↔ 当前 L154）：

```
基线：{savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline"><ExternalLink size={13} />查看已保存的公开名片</Link>}
当前：{savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} className="inline-flex items-center gap-1.5 text-xs text-[color:var(--amber-ink)] hover:underline"><ExternalLink size={13} />查看已保存的公开名片</Link>}
```

条件、`href`、图标、文案与基线完全一致，仅 `text-primary` → `text-[color:var(--amber-ink)]`（返修指令指定的样式）。位置：右栏 L153 `<AgentIdentityCard agent={agent} preview />` 之后、L155 盾牌 `.note` 之前（按 `05-fix-round1.md`「AgentIdentityCard 与 .note 之间」），L156 `<AgentMemoryPanel />` 不变；import 行 L5 `import { ArrowLeft, ExternalLink, Loader2, Save, ShieldCheck } from "lucide-react";` 恢复。

判定：**通过**。

### 第 2 轮新发现（按要求降级为可优化项，不阻塞）

9. `ChatBubble.tsx` L210 文字块的注释仍写「文字气泡（如果有内容或正在打字，且不是卡片）」，「且不是卡片」已与代码不符，可顺手改成「文字正文（有内容或正在打字）」。
