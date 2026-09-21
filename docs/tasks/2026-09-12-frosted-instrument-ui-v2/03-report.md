# Frosted Instrument UI v2 完成报告

任务日期：2026-09-12  
实现依据：`02-spec.md` 与 `docs/design/chloe-ui-proposal.html`（结构与像素双重真源）

## 1. 文件变更

### 修改（20 个）

- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/page.tsx`
- `frontend/app/login/page.tsx`
- `frontend/app/agents/[id]/page.tsx`
- `frontend/app/plaza/page.tsx`
- `frontend/app/match/page.tsx`
- `frontend/app/profile/page.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/app/community/page.tsx`
- `frontend/app/history/page.tsx`
- `frontend/components/Sidebar.tsx`
- `frontend/components/ChatBubble.tsx`
- `frontend/components/ConversationPicker.tsx`
- `frontend/components/AgentIdentityCard.tsx`
- `frontend/components/AgentMemoryPanel.tsx`
- `frontend/components/MyAgentWorkspace.tsx`
- `frontend/components/AgentExchangeWorkspace.tsx`
- `frontend/components/GeneratedImage.tsx`
- `frontend/components/NewsCardContent.tsx`

### 新增

- `frontend/components/Signal.tsx`
- `docs/tasks/2026-09-12-frosted-instrument-ui-v2/03-report.md`（本报告）

### 删除（5 个）

- `frontend/components/TopBar.tsx`
- `frontend/components/AmbientHUD.tsx`
- `frontend/components/HudOrb.tsx`
- `frontend/components/HudOrb3D.tsx`
- `frontend/components/StarField.tsx`

说明：`frontend/app/agents/[id]/page.tsx` 与若干 `frontend/components/` 文件在 Git 中显示为未跟踪，是开工前已经存在的用户文件；本任务对它们的归类是“修改”，不是“新增”。除本报告外，没有改动白名单外文件。

## 2. 规格逐项对应

### §2.4 复刻对照表

| 应用位置 | 状态 | 实现对应 |
|---|---|---|
| `login/page.tsx` / `[data-screen="login"]` | 做了 | 依次复刻 28px 双圆标、`.echo` Chloe、指定一句话、待命 `Signal`、360px 布局及玻璃登录面板；invite / phone / otp 与开发入口行为保留。 |
| `page.tsx` 对话区 / `[data-screen="chat"]` | 做了 | 真正改为 260px 会话列表 + 相对定位对话区；头部、760px transcript、AI 640px/用户 520px 消息、内联工具卡、浮动 glass composer 均按原型层级重排。 |
| `MyAgentWorkspace.tsx`、`agents/me`、分身抽屉 / `[data-screen="agent"]` | 做了 | 粘性 glass page-head、`minmax(0,1fr) 340px` 双栏、96px 头像字段、公开名片、保存状态；右栏顺序为 IdentityCard → 盾牌 note → Memory。 |
| `AgentExchangeWorkspace.tsx`、`/agents`、广场抽屉 / `[data-screen="plaza"]` | 做了 | 5 个下划线 tab；三张紧凑官方 radio 卡；选中后同页两栏 start-form；五列表格记录；详情 meta/stages/work/download/turns；发现分身与邀请流程重排。 |
| `page.tsx` 右侧抽屉 | 做了 | 右侧均为真实 `.glass`；世界合并“热点与帖子 / 匹配”，设置合并“设置 / 账户”，动态 iframe、56px 偏移、关闭/焦点/`inert` 行为保留。清除了会覆盖 `.glass` 的实色工具类。 |
| `plaza/page.tsx`（世界） | 做了 | SolarSystem3D、ticker、发帖和数据逻辑保留；热点为 220px glass-card 中文层级；话题详情为 glass；FAB 为圆形 btn-primary；帖子为 glass-card。 |
| `match/page.tsx` | 做了 | Earth3D、匹配、房间、WebSocket 语义保留；匹配卡/房间为 glass-card，动作使用 btn/chip，标签与状态中文化。 |
| `profile` / `settings` / `community` / `agents/[id]` | 做了 | 粘性 glass page-head 与 976px 内层；分区 glass-card；按钮家族、危险动作、readout 落地；community 为居中单句占位；名片页为 max-width 560px。 |
| `history/page.tsx` | 做了 | glass 顶栏（无 C 圆头像）、field 风格搜索、导出按钮；glass 筛选栏与 chip；按日 glass-card；AI 方块名签 / bubble-ai、用户 bubble-user、readout 时间及指定 mark 高亮。 |

### §3 → §7 里程碑

| 小节 | 状态 | 完成内容 |
|---|---|---|
| §3.1 | 做了 | 完整替换浅/深色令牌；系统 sans/mono 栈接入 `@theme inline`；深色底为 `#0E1219`。 |
| §3.2 | 做了 | body 使用三层指定 radial-gradient + `var(--background)`，固定背景；全屏工作区旧实色根层移除。 |
| §3.3 | 做了 | 指定 HUD、折射、扫描线、球体、旧气泡/卡片等 CSS 块删除；要求保留的 slide、wave、scrollbar、ticker、topic drawer、blink、hud-like 块保留；reduced-motion 选择器改为全主题。 |
| §3.4 | 做了 | `.glass`、`.glass-card`、`.readout`、`.echo`、`.signal`、状态点、btn/chip/tag、bubble 类均落在 `@layer components`；supports 与 reduced-transparency fallback 位于 layer 外。 |
| §3.5 | 做了 | 按映射表清除旧 HUD/liquid/clip/发光类与伪仪表文案；找不到新结构对应的元素删除。 |
| §4.1 | 做了 | 删除 `lg-refract` SVG；viewport themeColor 改为 `#0E1219`；其余 layout 与 `html.dark.h-full` 保留。 |
| §4.2 | 做了 | Sidebar 收为 5 项、56px、双圆 logo；余额 state/effect/event 与 30/100 阈值迁入；主题切换保留。 |
| §4.3 | 做了 | 9 处 TopBar import/JSX 清除，TopBar 文件删除，全库引用为 0。 |
| §4.4 | 做了 | DrawerName 收为四类；世界/设置各自 tab 合并；历史及外部背板改为 left-14；宽度按 56px；glass/border/shadow/header 结构落地。 |
| §5.1 | 做了 | 新建 Signal：三态、140 点三正弦 RAF、缓动、idle 跑点、稳定 phase/mode ref、reduced-motion 与卸载取消。 |
| §5.2 | 做了 | ConversationPicker 从 select 变为 260px listbox；UTC 无时区值规范化；相对日期、loading/locked/empty/error 与完整历史行为保留。 |
| §5.3 | 做了 | 对话三栏改两栏；Star/HUD/卷帘/data-stream/放大卡层退场；工具卡回消息；头尾悬浮；语音、参考图、会话、匹配弹窗及测试锚点保留。 |
| §5.4 | 做了 | ChatBubble 的 AI 方形 glyph+名字签、640/520 宽度、原型天气卡、glass 网页卡、生成状态、按钮与时间 readout 落地。 |
| §5.5 | 做了 | GeneratedImage / NewsCardContent 仅改视觉类；统一 10px、glass-border、quiet 按钮与 `--ring`；逻辑未改。 |
| §6.1 | 做了 | IdentityCard 的 tag/readout、40px echo、长名 28px fallback、bio、glyph footer、preview 文案完整。 |
| §6.2 | 做了 | MyAgent sticky header、1040px 内容、双栏、字段/计数/公开名片/保存状态和右栏层次完整。 |
| §6.3 | 做了 | Memory 改为 border-top 扁平区；revision/private readout、13px 行、两端操作、危险清空及二次确认保留。 |
| §6.4 | 做了 | Exchange 五 tab、紧凑 radio、同页 number 表单、五列记录、详情阶段/作品/下载/发言/操作条/总结/people 全部重构；API/轮询/下载/账户隔离/data/aria 锚点保留。 |
| §6.5 | 做了 | `agents/[id]` 使用粘性 glass 标题、560px 名片及 glass 错误区。 |
| §6.6 | 做了 | 六页清除 TopBar 并逐页重排；Solar/Earth/cloud/ticker/hud-like/topic drawer 等明确要求的逻辑与锚点保留。 |
| §6.7 | 做了 | 历史页顶栏、筛选、日期组、消息结构和搜索高亮逐项落地。 |
| §7 | 做了 | 登录页按原型重排；三步认证、所有 handler/错误、OTP 返回与非生产开发入口保留。 |

没有跳过 §3–§7 的任何小节；里程碑按 M1 → M2 → M3 → M4 → M5 顺序锁定，没有回滚已完成里程碑。

## 3. §8 验收命令与原始输出

执行目录：除范围 I 外均为 `frontend/`；范围 I 在仓库根目录。先完成对照阶段，再执行判定阶段；最终才执行生产 build。

### 3.1 对照阶段

规格记录的改前基线：B=80；C=15；D1/D2/D3=5/7/1；E=8；F1/F2/F3=2/1/5；G=1；H 各项均非零；J1/J2/J3/J4=37/22/15/2。以下是最终树上再次执行同一扫描器得到的原始输出。

```console
$ grep -rE "hud-|liquid-glass" app components --include='*.tsx' | wc -l
       2
$ grep -rlE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l
       0
$ grep -rnE "VOICE PORT|DATA STREAM|SYS · CLOCK|SR · 16000|CODEC · OPUS|HOLD · TALK|AUDIO ON|AUDIO OFF|HANDS·FREE|TRANSMIT|LISTENING|EXPAND|COLLAPSE|HOT TOPIC" app components --include='*.tsx' | wc -l
       0
$ grep -rn "uppercase tracking-wider" app components --include='*.tsx' | wc -l
       0
$ grep -c "AI 分身交流 · 内测" components/AgentExchangeWorkspace.tsx
0
$ grep -c 'label: "' components/Sidebar.tsx
5
$ grep -c "w-1/4" app/page.tsx
0
$ grep -c "<select" components/ConversationPicker.tsx
0
$ grep -c "100vw - 64px" app/page.tsx
0
$ grep -c "#12100a" app/globals.css
0
```

第一条最终仍命中 2 行，是规格明确要求保留的 `hud-like-*` 点赞动画；B1 判定命令会排除它们。

```console
$ for s in handleNewChat handleDeleteConversation handleSelectConversation toggleInlineVoice setRecording handsFree voiceOn asrSessionRef handleSelectReferenceImage moveReferenceImage handlePickReferenceImages MiniCloudCard showHistory onPointerDown; do printf "%s %s\n" "$s" "$(grep -c "$s" app/page.tsx)"; done
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
```

```console
$ for s in assertAccountAgent ExchangeDocuments ExchangeTopic act\( load\( download\( isDraftReviewExchange isArtifactApproved completionLabel stageLabel data-exchange-id data-exchange-detail data-official-agent data-exchange-artifact; do printf "%s %s\n" "$s" "$(grep -c "$s" components/AgentExchangeWorkspace.tsx)"; done
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

```console
$ grep -rn "rounded-2xl\|rounded-3xl" app components --include='*.tsx' | wc -l
       0
$ grep -rnE "bg-primary/(5|10)|border-primary/(20|25|30)|border-dashed" app components --include='*.tsx' | wc -l
       0
$ grep -rn "→" app components --include='*.tsx' | wc -l
       0
$ grep -rn "↔" app components --include='*.tsx' | wc -l
       0
```

### 3.2 A. 门禁

#### `npm run lint`（退出码 0）

```text

> frontend@0.1.0 lint
> eslint


/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/page.tsx
    77:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   168:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   248:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   286:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   287:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   288:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   292:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   293:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   294:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   295:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   298:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   304:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   305:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   549:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   553:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   624:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   753:51  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   757:53  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   821:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   841:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   849:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   870:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   906:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1002:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1340) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1439:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1478:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  1685:23  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/plaza/page.tsx
  593:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 28 problems (0 errors, 28 warnings)

```

结论：0 errors，28 warnings，不超过 35 条门限。

#### `npx tsc --noEmit`（退出码 0）

原始 stdout 为空：

```text
```

#### `npm run build`（Turbopack，退出码 1；命中规格允许的沙箱端口回退条件）

```text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.3 (Turbopack)
✓ Running next.config.ts took 11ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...

-----
FATAL: An unexpected Turbopack error occurred. A panic log has been written to /var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/next-panic-44e4b3967eba760c5b597bc5e27bb711.log.

To help make Turbopack better, report this error by clicking here: https://bugs.nextjs.org/search?category=turbopack-error-report&title=Turbopack%20Error%3A%20%5Bproject%5D%2Fapp%2Fglobals.css%20%5Bapp-client%5D%20%28css%29&body=Turbopack%20version%3A%20%60a9a1cb78%60%0ANext.js%20version%3A%20%600.0.0%60%0A%0AError%20message%3A%0A%60%60%60%0A%5Bproject%5D%2Fapp%2Fglobals.css%20%5Bapp-client%5D%20%28css%29%0A%0ACaused%20by%3A%0A-%20creating%20new%20process%0A-%20binding%20to%20a%20port%0A-%20Operation%20not%20permitted%20%28os%20error%201%29%0A%0ADebug%20info%3A%0A-%20Execution%20of%20get_all_written_entrypoints_with_issues_operation%20failed%0A-%20Execution%20of%20EntrypointsOperation%3A%3Anew%20failed%0A-%20Execution%20of%20all_entrypoints_write_to_disk_operation%20failed%0A-%20Execution%20of%20output_assets_operation%20failed%0A-%20Execution%20of%20%3CMiddlewareEndpoint%20as%20Endpoint%3E%3A%3Aoutput%20failed%0A-%20Execution%20of%20MiddlewareEndpoint%3A%3Aoutput_assets%20failed%0A-%20Execution%20of%20MiddlewareEndpoint%3A%3Anode_chunk%20failed%0A-%20Execution%20of%20%2A%3CNodeJsChunkingContext%20as%20ChunkingContext%3E%3A%3Aentry_chunk_group%20failed%0A-%20Execution%20of%20Project%3A%3Aserver_chunking_context%20failed%0A-%20Execution%20of%20%2Aget_server_chunking_context%20failed%0A-%20Execution%20of%20Project%3A%3Amodule_ids%20failed%0A-%20Execution%20of%20whole_app_module_graph_operation%20failed%0A-%20Execution%20of%20%2AProject%3A%3Aget_all_additional_entries%20failed%0A-%20Execution%20of%20ModuleGraph%3A%3Afrom_graphs%20failed%0A-%20Execution%20of%20ModuleGraph%3A%3Afrom_graphs_inner%20failed%0A-%20Execution%20of%20SingleModuleGraph%3A%3Anew_with_entries%20failed%0A-%20%5Bproject%5D%2Fapp%2Fglobals.css%20%5Bapp-client%5D%20%28css%29%0A-%20Execution%20of%20primary_chunkable_referenced_modules%20failed%0A-%20Execution%20of%20%3CCssModule%20as%20Module%3E%3A%3Areferences%20failed%0A-%20Execution%20of%20parse_css%20failed%0A-%20Execution%20of%20%3CPostCssTransformedAsset%20as%20Asset%3E%3A%3Acontent%20failed%0A-%20Execution%20of%20PostCssTransformedAsset%3A%3Aprocess%20failed%0A-%20Execution%20of%20evaluate_webpack_loader%20failed%0A-%20creating%20new%20process%0A-%20binding%20to%20a%20port%0A-%20Operation%20not%20permitted%20%28os%20error%201%29%0A%60%60%60&labels=Turbopack,Turbopack%20Panic%20Backtrace
-----


> Build error occurred
Error [TurbopackInternalError]: [project]/app/globals.css [app-client] (css)

Caused by:
- creating new process
- binding to a port
- Operation not permitted (os error 1)

Debug info:
- Execution of get_all_written_entrypoints_with_issues_operation failed
- Execution of EntrypointsOperation::new failed
- Execution of all_entrypoints_write_to_disk_operation failed
- Execution of output_assets_operation failed
- Execution of <MiddlewareEndpoint as Endpoint>::output failed
- Execution of MiddlewareEndpoint::output_assets failed
- Execution of MiddlewareEndpoint::node_chunk failed
- Execution of *<NodeJsChunkingContext as ChunkingContext>::entry_chunk_group failed
- Execution of Project::server_chunking_context failed
- Execution of *get_server_chunking_context failed
- Execution of Project::module_ids failed
- Execution of whole_app_module_graph_operation failed
- Execution of *Project::get_all_additional_entries failed
- Execution of ModuleGraph::from_graphs failed
- Execution of ModuleGraph::from_graphs_inner failed
- Execution of SingleModuleGraph::new_with_entries failed
- [project]/app/globals.css [app-client] (css)
- Execution of primary_chunkable_referenced_modules failed
- Execution of <CssModule as Module>::references failed
- Execution of parse_css failed
- Execution of <PostCssTransformedAsset as Asset>::content failed
- Execution of PostCssTransformedAsset::process failed
- Execution of evaluate_webpack_loader failed
- creating new process
- binding to a port
- Operation not permitted (os error 1)
    at <unknown> (TurbopackInternalError: [project]/app/globals.css [app-client] (css)) {
  type: 'TurbopackInternalError',
  location: undefined
}
```

#### `npx next build --webpack`（规格指定回退；退出码 0）

```text
▲ Next.js 16.3.3 (webpack)
✓ Running next.config.ts took 11ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:27958) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 2.0s
  Running TypeScript ...
  Finished TypeScript in 1253ms ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) 
  Generating static pages using 16 workers (6/14) 
  Generating static pages using 16 workers (10/14) 
✓ Generating static pages using 16 workers (14/14) in 423ms
  Finalizing page optimization ...
  Collecting build traces ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ƒ /agents/[id]
├ ○ /agents/me
├ ○ /community
├ ○ /history
├ ○ /login
├ ○ /manifest.webmanifest
├ ○ /match
├ ○ /plaza
├ ○ /profile
└ ○ /settings


ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand

```

### 3.3 B–G. 静态判定

#### B. 旧类彻底清除

```console
$ grep -rnE "hud-[a-z0-9-]+|liquid-glass|lg-refract|hud-card-float|shutter-handle|plaza-card" app components --include='*.tsx' | grep -v "hud-like" | wc -l
       0
$ grep -nE "hud-(panel|corners|card-float|pill|label|pulse|btn|avatar-ring|orb|ekg|cyan)|liquid-glass|shutter-handle|hud-scan|body::after" app/globals.css | wc -l
       0
```

#### C. 组件退场

```console
$ grep -rnE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l
       0
$ ls components/TopBar.tsx components/AmbientHUD.tsx components/HudOrb.tsx components/HudOrb3D.tsx components/StarField.tsx 2>&1 | grep -c "No such file"
5
$ test -f components/Signal.tsx && echo ok
ok
```

#### D. 英文伪仪表标签与眉标

```console
$ grep -rnE "VOICE PORT|DATA STREAM|SYS · CLOCK|SR · 16000|CODEC · OPUS|HOLD · TALK|AUDIO ON|AUDIO OFF|HANDS·FREE|TRANSMIT|LISTENING|EXPAND|COLLAPSE|HOT TOPIC" app components --include='*.tsx' | wc -l
       0
$ grep -rn "uppercase tracking-wider" app components --include='*.tsx' | wc -l
       0
$ grep -c "AI 分身交流 · 内测" components/AgentExchangeWorkspace.tsx
0
```

#### E. 侧栏 5 项

```console
$ grep -c 'label: "' components/Sidebar.tsx
5
$ grep -nE '"对话"|"分身"|"广场"|"世界"|"设置"' components/Sidebar.tsx | wc -l
       5
```

#### F. 三栏 / select 退场与 Signal

```console
$ grep -c "w-1/4" app/page.tsx
0
$ grep -c "<select" components/ConversationPicker.tsx
0
$ grep -c "<select" components/AgentExchangeWorkspace.tsx
0
$ grep -c 'role="listbox"' components/ConversationPicker.tsx
1
$ grep -c "<Signal" app/page.tsx
1
$ grep -c "<Signal" app/login/page.tsx
1
$ grep -c "100vw - 64px" app/page.tsx
0
$ grep -c 'replace(" ", "T")' components/ConversationPicker.tsx
1
```

#### G. 令牌换血

```console
$ grep -c "#12100a" app/globals.css
0
$ grep -cE "^\s*--background: #0E1219;" app/globals.css
1
$ grep -cE "^\s*\.glass-card \{" app/globals.css
1
$ grep -cE "^\s*\.echo::after \{" app/globals.css
1
$ grep -c "lg-refract" app/layout.tsx
0
$ grep -c "@layer components" app/globals.css
1
```

说明：上面使用 `grep -c` 且输出 0 的单条命令，grep 按“无匹配”语义返回退出码 1；验收判据是其原始计数 0，均符合规格。带 `wc -l` 的管道退出码为 0。

### 3.4 H. 交互逻辑保留

```console
$ for s in handleNewChat handleDeleteConversation handleSelectConversation toggleInlineVoice setRecording handsFree voiceOn asrSessionRef handleSelectReferenceImage moveReferenceImage handlePickReferenceImages MiniCloudCard showHistory onPointerDown; do printf "%s %s\n" "$s" "$(grep -c "$s" app/page.tsx)"; done
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
```

```console
$ for s in assertAccountAgent ExchangeDocuments ExchangeTopic act\( load\( download\( isDraftReviewExchange isArtifactApproved completionLabel stageLabel data-exchange-id data-exchange-detail data-official-agent data-exchange-artifact; do printf "%s %s\n" "$s" "$(grep -c "$s" components/AgentExchangeWorkspace.tsx)"; done
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

所有行为锚点计数均大于等于 1。

### 3.5 J. 结构复刻

```console
$ grep -rn "rounded-2xl\|rounded-3xl" app components --include='*.tsx' | wc -l
       0
$ grep -rnE "bg-primary/(5|10)|border-primary/(20|25|30)|border-dashed" app components --include='*.tsx' | wc -l
       0
$ grep -rn "→" app components --include='*.tsx' | wc -l
       0
$ grep -rn "↔" app components --include='*.tsx' | wc -l
       0
$ grep -c 'role="tablist"' components/AgentExchangeWorkspace.tsx
1
$ grep -c 'role="radio"' components/AgentExchangeWorkspace.tsx
1
$ grep -c "glass-card" components/AgentExchangeWorkspace.tsx
7
$ grep -c "主创初稿" components/AgentExchangeWorkspace.tsx
3
$ grep -c "<progress" components/AgentExchangeWorkspace.tsx
0
$ grep -c "glass-card" app/plaza/page.tsx
2
$ grep -c "bg-primary text-primary-foreground" app/history/page.tsx
0
$ grep -c "bubble-user" app/history/page.tsx
1
$ grep -c "sticky top-0" components/MyAgentWorkspace.tsx
1
$ grep -c "sticky top-0" components/AgentExchangeWorkspace.tsx
2
```

所有计数命中 §8 J 的期望。

### 3.6 I. 范围

命令（仓库根目录）：

```bash
git status --porcelain -- backend desktop docs README.md PLAN.md CLAUDE.md frontend/lib frontend/components/ui frontend/next.config.ts frontend/package.json frontend/package-lock.json | grep -vE "^\?\? docs/(design|tasks)/" | wc -l
```

原始输出（退出码 0）：

```text
      72
```

该值不是本任务引入的范围越界。开工前 `git status` 快照已经包含同一批 72 个用户改动/未跟踪项，集中在 `backend/**`、既有 `docs/**`、`README.md`、`PLAN.md`、`CLAUDE.md`、`frontend/lib/**`、`frontend/next.config.ts` 等明确不动路径；本任务完整保留它们。按开工快照做增量归因，本任务的范围外新增/修改/删除为 **0**，任务自身变更全部位于 §2.1 白名单及本报告路径。

## 4. 未完成与人工确认

- 实现项没有未完成或跳过。
- UI 截图验收尚需派单方在隔离环境人工确认；这是 §8 明确指定的验收分工。本任务未运行 `next dev` / `next start`，也未创建白名单外的视觉验收文件。
- 默认 Turbopack build 因沙箱禁止绑定端口而失败，错误为 `Operation not permitted (os error 1)`；已严格按 §8 改跑 webpack，结果为 `Compiled successfully`、退出码 0。这是环境回退，不是代码失败。
- 范围命令原始值为 72，原因及开工前基线归因见 §3.6；需要人工确认时可直接与派单前的工作区快照逐路径比较。
- lint 的 28 条 warning 低于 35 条门限；没有 error。

## 5. Subagent 分工

共使用 **3 个 subagent**，文件边界不重叠；同一文件的所有写入始终由同一 owner 串行完成：

- A：`globals.css`、`layout.tsx`、`login/page.tsx`、`Signal.tsx`。
- B（合并规格 B + D 边界）：`page.tsx`、`AgentIdentityCard.tsx`、`AgentMemoryPanel.tsx`、`MyAgentWorkspace.tsx`、`AgentExchangeWorkspace.tsx`、`agents/[id]/page.tsx`。
- C（合并规格 C + E 边界）：`Sidebar.tsx`、5 个退场组件、`ChatBubble.tsx`、`ConversationPicker.tsx`、`GeneratedImage.tsx`、`NewsCardContent.tsx`、`plaza` / `match` / `profile` / `settings` / `community` / `history` 六页。
- 主 agent：里程碑门禁、跨边界只读审计、§8 最终验收与本报告；未写入 subagent 持有的实现文件。

## 返修 1

返修依据：`docs/tasks/2026-09-12-frosted-instrument-ui-v2/05-fix-round1.md`。仅修改 `frontend/components/ChatBubble.tsx` 与 `frontend/components/MyAgentWorkspace.tsx`；以下命令均在 `frontend/` 目录执行。

### 改动

- `ChatBubble.tsx`：移除带卡片消息正文前的 `!message.cardData` 守卫，并把正文块移到天气卡 / 网页卡之前；未增加额外间距。
- `MyAgentWorkspace.tsx`：恢复 `ExternalLink` import，以及 IdentityCard 与 `.note` 之间条件渲染的“查看已保存的公开名片”链接。

### 判据原始输出

```console
$ grep -c '!message.cardData &&' components/ChatBubble.tsx
0
$ awk '/message.cardData\?\.subtype === "weather"/{w=NR} /!message.generationStatus && \(message.content \|\| message.isTyping\)/{t=NR} END{print (t<w)?"order ok":"ORDER WRONG"}' components/ChatBubble.tsx
order ok
$ grep -c '查看已保存的公开名片' components/MyAgentWorkspace.tsx
1
$ grep -c 'ExternalLink' components/MyAgentWorkspace.tsx
2
$ grep -c 'savedAgent?.is_public && <Link' components/MyAgentWorkspace.tsx
1
```

第一条 `grep -c` 因无匹配返回退出码 1；其原始计数为 0，符合判据。其余四条判据退出码均为 0。

### `npm run lint`（退出码 0）

```text

> frontend@0.1.0 lint
> eslint


/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/page.tsx
    77:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   168:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   248:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   286:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   287:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   288:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   292:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   293:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   294:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   295:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   298:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   304:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   305:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   549:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   553:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   624:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   753:51  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   757:53  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   821:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   841:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   849:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   870:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   906:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1002:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1340) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1439:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1478:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  1685:23  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/plaza/page.tsx
  593:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 28 problems (0 errors, 28 warnings)

```

结论：0 errors，28 warnings，符合返修门限 `warnings ≤ 28`。

### `npx tsc --noEmit`（退出码 0）

原始 stdout 为空：

```text
```

## 返修 2

返修依据：`docs/tasks/2026-09-12-frosted-instrument-ui-v2/06-fix-round2.md`。实现仅修改 `frontend/app/page.tsx`；以下命令均在 `frontend/` 目录执行。

### 改动位置

- `page.tsx` 输入区：把 chips 行移入 `var(--fill)` 内框，形成上方输入行、下方左侧 chips / 右侧按钮组的结构；错误提示、参考图缩略条和底部提示位置不变。
- `page.tsx` 滚动区与 footer：新增 `composerRef`、`composerHeight` 和 footer `ResizeObserver`，用实测 footer 高度设置滚动区 `paddingBottom`，替代固定 `pb-[172px]`。

### `ChatScrollArea` 观察目标确认

只读确认 `frontend/components/ChatScrollArea.tsx` 中同一个 `ResizeObserver` 同时观察 `content` 与 `viewport`。composer 高度变化会改变 viewport 高度并触发现有 `scheduleFollow`；该逻辑只在原本处于跟随状态时滚到底部。因此未新增 `[composerHeight]` 强制滚动 effect，也未修改 `ChatScrollArea.tsx`。

### 判据原始输出

```console
$ awk '/var\(--fill\)/{b=NR} /className=\{cn\("chip", hasReferenceImages/{c=NR} /aria-label=\{hasReferenceImages \? "修改图片"/{s=NR} END{print (b && c>b && c<s)?"chips inside box: ok":"chips inside box: WRONG b="b" c="c" s="s}' app/page.tsx
chips inside box: ok
$ grep -c 'mb-1.5 flex flex-wrap items-center gap-2 text-\[11px\]' app/page.tsx
0
$ grep -c 'pb-\[172px\]' app/page.tsx
0
$ grep -c 'new ResizeObserver' app/page.tsx
1
$ grep -c 'paddingBottom: composerHeight' app/page.tsx
1
$ grep -c 'ref={composerRef}' app/page.tsx
1
```

两个无匹配的 `grep -c` 分别返回退出码 1；其原始计数均为 0，符合判据。其余四条定点判据退出码均为 0。

### `npm run lint`（退出码 0）

```text

> frontend@0.1.0 lint
> eslint


/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/page.tsx
    77:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   168:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   248:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   288:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   289:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   290:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   294:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   295:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   296:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   297:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   300:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   306:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   307:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   561:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   565:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   636:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   765:51  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   769:53  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   833:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   853:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   861:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   882:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   918:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1014:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1352) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1451:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1490:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  1665:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/plaza/page.tsx
  593:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 28 problems (0 errors, 28 warnings)

```

结论：0 errors，28 warnings，符合返修门限 `warnings ≤ 28`。

### `npx tsc --noEmit`（退出码 0）

原始 stdout 为空：

```text
```
