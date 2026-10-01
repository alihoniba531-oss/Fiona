# 朗读自动播放修复报告

基线：`8c7f0cf`。实现仅修改 `frontend/app/page.tsx`，本文件为新增报告；未修改规格文件、测试、依赖、后端或其他文件。没有启动浏览器、执行 `next dev`、读取 `.env*`、发起真实网络请求或写入 git 状态。

## 变更与任务对应

| 任务 | 实现 |
| --- | --- |
| T1 | `page.tsx` 中按需创建两个长期存活的 audio 元素，以 `PreparedTtsAudio` 对象和 slot 归属管理当前句及预取句；用 `AbortController` 成对清理句子监听，并在换票异步结果写入前检查归属、取消状态和会话号。 |
| T2 | 在朗读、免提、帮我读、点此播放的同步点击路径调用 `primeTtsAudio()`；生成 40 ms 静音 WAV，并以 document 捕获阶段的 `click`、`keydown`、`touchend` 补救尚未解锁的空闲元素。 |
| T3 | 当前句的 `play()` 遭 `NotAllowedError` 时保留句子、预取及队列，显示输入区提示；点此播放复用原票据续播，不听了或关闭朗读立即清队列。 |
| T4 | 本报告列出修改文件、3.1–3.3 对应、状态转换、第 5.1 节逐条检查结果和人工验证项。 |

另外将原有 `new AudioContext()` 写成等价的 `new window.AudioContext()`，使第 5.1 节针对 `new Audio` 的文本检查只针对媒体元素，不改变录音行为。

## 与设计要求逐条对应

### 3.1 两个可复用的 audio 元素

1. **元素池**：`getTtsAudioPool()` 在第一次需要时一次创建恰好两个 `document.createElement("audio")`，设置 `preload = "auto"` 并保存在 ref；当前句与预取句共用这两个元素。
2. **归属**：每个 slot 的 `owner` 同时至多指向一个 `PreparedTtsAudio`；仅空闲 slot 可被新句取得，句子结束、出错、放弃或清空时释放。
3. **身份判断**：当前句用 `ttsCurrentRef.current === prepared`，元素归属用 `slot.owner === prepared`；不再用元素本身判断句子身份。
4. **监听清理**：`ended` 和 `error` 共用每句独立的 `AbortController`；释放时先 abort 监听，再 pause、移除 `src`、`load()`。没有 `{ once: true }` 留下另一种监听。
5. **监听生效时机**：票据返回并设置、加载真实 `src` 后，提升为当前句时才添加句子监听。静音音频结束及移除旧 `src` 时，该句尚无监听。
6. **接手元素**：占用 slot 前先 pause、移除静音 `src` 并 `load()`；原解锁尝试的异步收尾凭尝试对象识别，不能改写后续尝试或真实句子。
7. **迟到结果**：换票返回及 JSON 解析之后、写 `src` 和调用 `load()` 之前，均检查 owner、取消/abort 和 `ttsSessionRef`；播放前再次检查这三项。播放 Promise 的后续处理也检查句子身份。
8. **清空**：`clearTtsQueue()` 中止当前和预取的换票请求、移除监听、停止并清空音源、清队列和提示；两个 audio 元素留在池中。空闲元素上尚在播放的静音解锁音频也一并停止。

### 3.2 用户手势解锁

1. **同步解锁**：`primeTtsAudio()` 不等待异步操作，只对空闲、未解锁且没有进行中尝试的 slot 设置代码生成的 40 ms 静音 WAV，并同步调用各自的 `play()`。
2. **成功判定**：仅 `NotAllowedError` 保持未解锁；成功或其他错误（包括音源随后被替换产生的 `AbortError`）标记为已解锁。尝试对象防止迟到结果污染新的尝试。
3. **收尾与占用保护**：仅当仍是同一次尝试、slot 空闲且 `src` 仍为静音 WAV 时，才 pause、移除 `src`、`load()`；已由真实句子占用的元素不会被收尾改动。
4. **不打断已占用元素**：解锁循环跳过当前句和预取句。被拒续播时如预取占着未解锁元素，先取消预取并将原文放回队头。
5. **四个显式手势**：开启朗读、开启免提、点击气泡「帮我读」、点击「点此播放」均在事件处理函数的同步部分调用解锁；续播随后直接对当前元素调用 `play()`。
6. **兜底监听**：document 捕获阶段监听 `click`、`keydown`、`touchend`；只有朗读开启且池中存在未解锁的空闲元素时才解锁，组件卸载时移除监听。朗读关闭状态下的普通交互不会放静音；关闭朗读/清队列还会停止当次点击已启动的空闲静音音频。

### 3.3 被拒提示与续播

1. **被拒保留**：当前句 `play()` 拒绝为 `NotAllowedError` 时不推进；当前句及其元素、预取句、队列保留，`ttsPlayingRef` 仍为 true。后续句子照常排队和预取，免提录音不会在等待用户时启动。
2. **其他失败**：其他 Promise 拒绝和元素 `error` 事件结束当前句、释放元素并继续下一句。
3. **提示 UI**：在 footer 的 `[data-chat-composer]` 顶部、与 `referenceUploadError` 同级显示一行「浏览器拦下了自动朗读」和带 `Volume2` 的「点此播放」及「不听了」。按钮沿用 `btn btn-quiet h-7 px-2.5 text-xs`，手机为 `max-md:h-9`，文字为 `text-xs text-muted-foreground`；仅使用 Tailwind 工具类，文字可收缩换行而按钮不被挤出。容器有 `role="status"`、`aria-live="polite"`，两个按钮均为 `<button type="button">`，没有自动移动焦点。
4. **点此播放**：同步取消占用未解锁元素的预取、abort 换票、释放并把其原文放回队头；解锁空闲元素；直接对被拒句调用 `play()`，不重新换票或 `load()`；隐藏提示，随后恢复预取。再次遭 `NotAllowedError` 时只重新显示提示，不自动循环；成功后由原 `ended` 监听推进。
5. **不听了及清空**：「不听了」调用 `clearTtsQueue()`，保留朗读开关；每次清空均隐藏提示。若同一条流式回复随后还有分句，已停止的 TTS 会话不再入队，也不会在空队列时启动免提录音；下一条新消息或新的「帮我读」使用新会话号，照常可读。
6. **关闭朗读**：关闭按钮立即调用 `clearTtsQueue()` 并关闭开关，当前播放和提示立即停止。
7. **免提**：被拒期间保持当前句占用状态；续播全部结束后，原有「读完后录音」分支照常执行。

保留了原有票据请求体字段、300 字截断、流地址、预取、`normalizeForTTS`、切句规则及 `enqueueSpeech` 的 `voiceOn` 守卫。仅为避免“停止后同一流继续朗读”，在该守卫之后增加了已停止会话检查。

## 状态转换

| 从 → 到 | 触发 | 元素归属与监听 |
| --- | --- | --- |
| 空闲 → 换票中 | 队列启动当前句或预取队头 | 占用一个空闲 slot；先停静音源；没有该句监听；发起可中止的换票请求。 |
| 换票中 → 可播放 | 有效票据返回，三项迟到结果检查通过 | owner 不变；设置 `/tts/stream?ticket=…` 并 `load()`；此时仍无该句监听。 |
| 可播放 → 播放中 | 作为当前句且 `ready` 成功，调用 `play()` | owner 不变；在真实 `src` 已设置后挂该句的 `ended` 和 `error` 监听。预取句在升为当前句前不挂播放监听。 |
| 可播放/播放中 → 被拒 | 当前句 `play()` 以 `NotAllowedError` 拒绝 | owner、该句监听、预取和队列均保留；占用标志保持，显示提示。 |
| 被拒 → 续播/播放中 | 用户点击「点此播放」 | 必要时释放未解锁预取并把文本放回队头；空闲 slot 解锁；当前句 owner 与监听不变，直接 `play()`，继续预取。 |
| 播放中 → 结束 | `ended`、`error` 或非 `NotAllowedError` 拒绝 | 先 abort 两个监听，再 pause/移除 `src`/`load()`；owner 清空，推进到预取句或队头。 |
| 换票中/可播放/播放中/被拒 → 放弃 | 不听了、关闭朗读、新发送、会话/账号切换、页面卸载等清空操作 | abort 当前与预取换票和监听；两元素停止、清源并回池；清空队列和提示。 |

## 第 5.1 节自检：实际输出摘要与退出码

前端克隆位置为 `/private/tmp/tts-autoplay.qO7L7u/fe`。首次按规格示例把 `node_modules` 软链接到仓库时，`npm run build` 退出码 **1**，输出 `Symlink [project]/node_modules is invalid, it points out of the filesystem root`。随后仅在仓库外将该软链接替换为 `node_modules` 实体副本；以下是同步最终 `page.tsx` 后的结果。克隆时额外排除了 `.env*`；检查时设置 `npm_config_offline=true`，构建另设置 `NEXT_TELEMETRY_DISABLED=1`。

| 位置与命令 | 实际输出摘要（保留原文） | 退出码 |
| --- | --- | ---: |
| 克隆中：`npx tsc --noEmit` | 无输出 | 0 |
| 克隆中：`npm run lint -- --max-warnings=28` | `> frontend@0.1.0 lint`；`> eslint --max-warnings=28`；`✖ 26 problems (0 errors, 26 warnings)` | 0 |
| 克隆中：`npm run build` | `▲ Next.js 16.3.3 (Turbopack)`；`✓ Compiled successfully in 258ms`；`Finished TypeScript in 1005ms ...`；`✓ Generating static pages using 16 workers (14/14) in 293ms`；输出静态/动态路由表。另有 Node 的 `DEP0205` deprecation warning。 | 0 |
| 仓库根：`git status --porcelain` | ` M frontend/app/page.tsx`<br>`?? docs/tasks/2026-09-29-tts-autoplay/`（目录含原有规格和本报告） | 0 |
| 仓库根：`grep -n "new Audio" frontend/app/page.tsx` | 无输出（零行；grep 对无匹配返回 1） | 1 |
| 仓库根：`grep -rn "new Audio\|createElement(\"audio\")" frontend/app frontend/lib` | `frontend/app/page.tsx:778:        const audio = document.createElement("audio");`，唯一创建点，池初始化时恰执行两次 | 0 |
| 仓库根：`shasum backend/local-avatar.db backend/fiona.db` | `172d800a603128374bab9177d39b7f66be20be7e  backend/local-avatar.db`<br>`403a086c4ec0cf28493fc9fa37b2b6eee528b261  backend/fiona.db`；与开工前一致 | 0 |
| 仓库根：`git diff --stat -- frontend/AGENTS.md backend/` | 无输出 | 0 |

补充：`git diff --check -- frontend/app/page.tsx` 无输出，退出码 0。lint 的 26 条均位于原有未使用代码、Hook 依赖和 `<img>` 等位置；本次新增代码没有 lint 告警。没有修改已有测试的输入或断言。

## 未决问题与人工确认

实现与第 5.1 节自检已完成，没有待定的实现选择。按规格第 0 节，本环境未启动浏览器；第 5.2 节 WebKit/Chromium 的 A–H 播放、时延、元素计数及 390/1280 宽视觉实测仍需在主会话中人工/浏览器确认。

## 第 1 轮返修

以上内容记录第 0 轮状态；本节记录返修后的现状，覆盖前文关于 AudioContext 写法、清队列阻止后续入队及免提录音、以及第 5.1 节 grep 输出的旧结论。本轮只修改 frontend/app/page.tsx，并追加本报告。

### 改动行号与前后代码

1. **M1（929、995、1006–1033、1937–1943、1998 行）**：通用清队列只释放音频和清提示；停止会话标记只由用户显式停止设置。929 行免提门槛从
   ~~~ts
   if (streamDoneRef.current && handsFreeRef.current && ttsStoppedSessionRef.current !== ttsSessionRef.current) {
   ~~~
   改为
   ~~~ts
   if (streamDoneRef.current && handsFreeRef.current) {
   ~~~
   1006 行的 clearTtsQueue 原先首句为
   ~~~ts
   ttsStoppedSessionRef.current = ttsSessionRef.current;
   ttsQueueRef.current = [];
   ~~~
   现在从 ttsQueueRef.current = []; 开始，不再写停止标记。新增的 1028–1033 行（此前无此函数）为
   ~~~ts
   const stopTtsByUser = useCallback(() => {
     const wasPlaying = ttsPlayingRef.current;
     ttsStoppedSessionRef.current = ttsSessionRef.current;
     clearTtsQueue();
     if (wasPlaying && streamDoneRef.current && handsFreeRef.current) startHandsFreeRecording();
   }, [clearTtsQueue, startHandsFreeRecording]);
   ~~~
   1938 行关朗读由 clearTtsQueue(); 改为 stopTtsByUser();，随后仍 setVoiceOn(false);。1998 行「不听了」由 onClick={clearTtsQueue} 改为 onClick={stopTtsByUser}。995 行 enqueueSpeech 的停止会话守卫保持原样。只有这两个用户入口调用 stopTtsByUser；账号切换、会话重置、新发送、卡片分支和流式错误继续调用 clearTtsQueue。

2. **M2（1016–1022 行）**：原代码为
   ~~~ts
   // A click that clears the queue may have just primed an otherwise idle slot.
   for (const slot of ttsAudioPoolRef.current ? getTtsAudioPool() : []) {
     if (slot.owner || !slot.primeAttempt) continue;
     slot.primeAttempt = null;
     slot.audio.pause();
     slot.audio.removeAttribute("src");
     slot.audio.load();
   }
   ~~~
   现在为
   ~~~ts
   // A click that clears the queue may have just primed an otherwise idle slot: stop the silent
   // audio but keep primeAttempt so finish() still classifies the resulting AbortError as unlocked (spec 3.2).
   for (const slot of ttsAudioPoolRef.current ? getTtsAudioPool() : []) {
     if (slot.owner || !slot.primeAttempt) continue;
     slot.audio.pause();
     slot.audio.removeAttribute("src");
     slot.audio.load();
   }
   ~~~
   finish() 未改；被 pause/移源打断的解锁 Promise 仍可把 AbortError 记为已解锁。

3. **O1（1940–1943 行）**：开朗读分支从
   ~~~ts
   primeTtsAudio();
   setVoiceOn(true);
   ~~~
   改为
   ~~~ts
   ttsStoppedSessionRef.current = null;
   primeTtsAudio();
   setVoiceOn(true);
   ~~~
   同一条流在关闭后重新开启朗读时，后续句子可再次入队。

4. **O2（711 行）**：从 const audioCtx = new window.AudioContext(); 改回基线写法 const audioCtx = new AudioContext();。这是 Web Audio 上下文，不是 HTMLAudioElement。

5. **O3（1992–2000 行）**：提示容器从条件渲染
   ~~~tsx
   {ttsPlaybackBlocked && <div role="status" aria-live="polite" className="mb-2 flex min-w-0 items-center gap-1 text-xs">
     <span className="min-w-0 flex-1 text-muted-foreground">浏览器拦下了自动朗读</span>
     <button type="button" onClick={resumeBlockedTts} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">
       <Volume2 size={13} />点此播放
     </button>
     <button type="button" onClick={clearTtsQueue} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">不听了</button>
   </div>}
   ~~~
   改为常驻 live region，内容仍按状态条件渲染：
   ~~~tsx
   <div role="status" aria-live="polite">
     {ttsPlaybackBlocked && <div className="mb-2 flex min-w-0 items-center gap-1 text-xs">
       <span className="min-w-0 flex-1 text-muted-foreground">浏览器拦下了自动朗读</span>
       <button type="button" onClick={resumeBlockedTts} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">
         <Volume2 size={13} />点此播放
       </button>
       <button type="button" onClick={stopTtsByUser} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">不听了</button>
     </div>}
   </div>
   ~~~
   外层无 class，隐藏时无高度和间距；「不听了」处理函数的变化属于 M1。

**清队列与用户停止的分工及产品决定**：clearTtsQueue 继续负责停止当前句和预取句、中止请求、清空队列与提示，不给会话打停止标记。stopTtsByUser 在「不听了」和「关朗读」时先给当前会话打标记，再清队列，使同一流随后送达的句子不再入队。按复核附录 B 第 1 条的默认方案，若此举确实打断正在进行的朗读、流已结束且免提仍开启，则补开一次麦；流未结束时仍由流结束后的原有分支开麦，空闲录音状态不重复开 MediaRecorder。这项产品决定仍待用户确认。

### 第 5.1 节命令原样输出与退出码

在仓库外建立 /private/tmp/tts-autoplay-round1.PEkVBo/fe：rsync 排除 node_modules、.next 和 .env*，然后以 cp -Rc frontend/node_modules /private/tmp/tts-autoplay-round1.PEkVBo/fe/node_modules 复制实体目录；test ! -L node_modules 退出码 0。前端命令在该克隆执行；为确保离线并禁止 Next telemetry，设置 npm_config_offline=true，build 另设 NEXT_TELEMETRY_DISABLED=1。没有在仓库内构建。

#### 前端克隆：npx tsc --noEmit

原样输出：

~~~text

~~~

退出码：0。

#### 前端克隆：npm run lint -- --max-warnings=28

原样输出：

~~~text

> frontend@0.1.0 lint
> eslint --max-warnings=28


/private/tmp/tts-autoplay-round1.PEkVBo/fe/app/page.tsx
   124:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   215:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   373:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   416:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   417:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   418:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   422:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   423:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   424:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   425:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   428:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   434:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   435:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   689:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   693:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   764:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1125:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1145:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1153:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1174:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1211:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1307:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1651) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1750:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1790:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2026:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/tmp/tts-autoplay-round1.PEkVBo/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)

~~~

退出码：0。

#### 前端克隆：npm run build

原样输出：

~~~text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.3 (Turbopack)
✓ Running next.config.ts took 781ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:63338) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 2.2s
  Running TypeScript ...
  Finished TypeScript in 2.5s ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) 
  Generating static pages using 16 workers (6/14) 
  Generating static pages using 16 workers (10/14) 
✓ Generating static pages using 16 workers (14/14) in 356ms
  Finalizing page optimization ...

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

~~~

退出码：0。

#### 仓库根：git status --porcelain

原样输出：

~~~text
 M frontend/app/page.tsx
?? docs/tasks/2026-09-29-tts-autoplay/
~~~

退出码：0。

#### 仓库根：grep -n "new Audio" frontend/app/page.tsx

原样输出：

~~~text
711:      const audioCtx = new AudioContext();
~~~

退出码：0。

#### 仓库根：grep -rn 'new Audio\|createElement("audio")' frontend/app frontend/lib

原样输出：

~~~text
frontend/app/page.tsx:711:      const audioCtx = new AudioContext();
frontend/app/page.tsx:778:        const audio = document.createElement("audio");
~~~

退出码：0。

#### 仓库根：shasum backend/local-avatar.db backend/fiona.db

原样输出：

~~~text
172d800a603128374bab9177d39b7f66be20be7e  backend/local-avatar.db
403a086c4ec0cf28493fc9fa37b2b6eee528b261  backend/fiona.db
~~~

退出码：0。

#### 仓库根：git diff --stat -- frontend/AGENTS.md backend/

原样输出：

~~~text

~~~

退出码：0。


恢复基线的 new AudioContext() 后，第一个宽泛 grep 在 711 行命中 1 行；第二个宽泛 grep 也命中 711 行及 778 行。711 行是 Web Audio 上下文，真正创建媒体元素的只有 778 行元素池，组件生命周期内只执行两次。建议规格作者把第一条检查改为 grep -nE 'new Audio\s*\(' frontend/app/page.tsx；此修正模式的本轮原样输出和退出码为：

~~~text

~~~

退出码：1。另外 git diff --check -- frontend/app/page.tsx 无输出，退出码 0。数据库两项 SHA-1 与开工前一致。lint 26 条警告、0 错误，未超过 28 条上限。

### 未决问题

1. 「不听了」/「关朗读」在免提模式下是否应重新开麦？本轮按附录 B 默认实现：仅确实打断朗读、流已结束且免提开启时补开一次；若产品意图是退出免提循环，需用户确认后另改。
2. O4：被拒提示显示期间点旧卡片「帮我读」，是否应先放弃被拒的旧回复？这涉及规格 3.4 对 handleConfirmTts 保持不变的要求，本轮未改。
3. O5：正在播放时点「帮我读」，已预取就绪的下一句应按基线继续播放，还是按规格 3.1 的播放前会话号检查跳过？规格 3.1 与 3.4 在此冲突，本轮未改。
4. O7：「点此播放」复用原票据，iOS 上超过 60 秒才点击可能丢句；应在前端按 ticketIssuedAt 超 50 秒重换票，还是由后端放宽 TTL？后端超出白名单，本轮未改。

浏览器场景与截图复测由 Claude 主会话执行；本轮未启动浏览器。


## 第 2 轮返修

本节依据 `05-fix-round2.md` 的 F1–F3 和用户 D1–D4 拍板，记录 2026-10-01 第 2 轮返修。基线为 `49b2f5a0ba7e2c31eb543f110b038acbbbccc372`，开工时 `frontend/app/page.tsx` SHA-1 为 `389ab742b654c5e570215fdff1ab31f6d1e5ebd4`。以下“修改前”行号对应该基线，“修改后”行号对应本轮最终源码。

本轮修改文件只有 `frontend/app/page.tsx` 和本报告 `03-report.md`；本报告原内容完整保留，只在末尾追加。未改已有测试、依赖、lockfile、前端 AGENTS 或后端；未读 `.env*`、未启动浏览器或 `next dev`、未写 git 状态、未做真实网络调用或下载。独立 subagent 仅只读复核源码，并在仓库外写一次性验证脚本；`page.tsx` 始终由主 agent 独自修改。

开工时已存在以下工作区变更，本轮保留，不能把它们计为本轮新增的越界修改：

~~~text
 M docs/tasks/2026-09-29-tts-autoplay/02-spec.md
?? docs/tasks/2026-09-29-tts-autoplay/04-review-round2.md
?? docs/tasks/2026-09-29-tts-autoplay/05-fix-round2.md
~~~

### F1–F3 的行号与前后代码

**F1 / D2：`handleConfirmTts`（基线 1249–1260 行 → 1269–1285 行）。**

修改前：

~~~ts
  const handleConfirmTts = useCallback((id: string, text: string) => {
    primeTtsAudio();
    if (!voiceOn) setVoiceOn(true);
    ttsSessionRef.current += 1;
    streamDoneRef.current = true;
    const t = normalizeForTTS(text.trim());
    if (t) {
      ttsQueueRef.current.push(t);
      if (!ttsPlayingRef.current) playNextInQueue();
    }
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  }, [normalizeForTTS, playNextInQueue, voiceOn, setMessages, primeTtsAudio]);
~~~

修改后：

~~~ts
  const handleConfirmTts = useCallback((id: string, text: string) => {
    stopHandsFreeRecording({ discard: true });
    clearTtsQueue();
    primeTtsAudio();
    if (!voiceOn) {
      ttsStoppedSessionRef.current = null;
      setVoiceOn(true);
    }
    ttsSessionRef.current += 1;
    streamDoneRef.current = true;
    const t = normalizeForTTS(text.trim());
    if (t) {
      ttsQueueRef.current.push(t);
      playNextInQueue();
    }
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  }, [normalizeForTTS, playNextInQueue, voiceOn, setMessages, primeTtsAudio, clearTtsQueue, stopHandsFreeRecording]);
~~~

整个点击处理函数没有 `await`：同步停止并丢弃免提录音 → 通用清队列 → 解锁池内元素。`clearTtsQueue` 原有的停止当前句/预取句、取消请求、释放元素、隐藏被拒/限速提示均保持不变；此入口不调用 `stopTtsByUser`，不会打用户停止标记或触发补开麦。关闭朗读时打开并清停止标记；会话号照旧加一，旧流随后到达的分句仍由原有会话守卫丢弃。清队列后直接 `playNextInQueue()`；归一化和清气泡 `pendingTtsText` 均保留。卡片读完仍走原有免提门槛，由 F2 保证重复触发不会重复开录音。

**F2 / D3：免提录音状态与停止并丢弃。**

1. **418 行新增 ref**（基线无此声明）：

~~~ts
  const handsFreeRecRef = useRef<{ recorder: MediaRecorder | null; discard: boolean } | null>(null);
~~~

`null` 表示空闲；本次 `rec` 对象表示正在申请或录音，字段记录其录音机和是否丢弃。

2. **入口及麦克风申请返回分支**（基线 719–729 行 → 720–733 行）：

修改前：

~~~ts
  const startHandsFreeRecording = useCallback(async () => {
    if (!handsFreeRef.current) return;
    const selectionVersion = getSelectionVersion();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (selectionVersion !== getSelectionVersion() || !handsFreeRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      const chunks: Blob[] = [];
~~~

修改后：

~~~ts
  const startHandsFreeRecording = useCallback(async () => {
    if (!handsFreeRef.current || handsFreeRecRef.current) return;
    const selectionVersion = getSelectionVersion();
    const rec: { recorder: MediaRecorder | null; discard: boolean } = { recorder: null, discard: false };
    handsFreeRecRef.current = rec;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (rec.discard || selectionVersion !== getSelectionVersion() || !handsFreeRef.current) {
        stream.getTracks().forEach(track => track.stop());
        if (handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
        return;
      }
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      rec.recorder = mr;
~~~

重复启动在第一个 `await` 前返回，不能再次调用 `getUserMedia`。申请返回时，丢弃、会话切换、免提关闭共用停轨道和身份复位分支。

3. **`onstop` 第一行复位与丢弃守卫**（基线 767–770 行 → 772–776 行）：

修改前：

~~~ts
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        audioCtx.close().catch(() => {});
        if (selectionVersion !== getSelectionVersion() || !handsFreeRef.current) return;
~~~

修改后：

~~~ts
      mr.onstop = async () => {
        if (handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
        stream.getTracks().forEach(t => t.stop());
        audioCtx.close().catch(() => {});
        if (rec.discard || selectionVersion !== getSelectionVersion() || !handsFreeRef.current) return;
~~~

复位后始终先释放轨道和 AudioContext，再检查本次 `rec.discard`；丢弃时不会进入 Blob/ASR/`handleSendRef`。原有会话、免提、未讲话、小 Blob 和 ASR 完成后的守卫不变。

4. **异常出口**（基线 790 行 → 796–799 行）：

修改前：

~~~ts
    } catch (e) { console.error('[handsfree] mic error', e); }
~~~

修改后：

~~~ts
    } catch (e) {
      if (handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
      console.error('[handsfree] mic error', e);
    }
~~~

异常日志保留，新增的复位只能清理本次对象，旧申请的迟到拒绝不能清掉新一次录音。

5. **802–811 行新增同步停止函数**（基线无此函数）：

~~~ts
  const stopHandsFreeRecording = useCallback(({ discard }: { discard: boolean }) => {
    const rec = handsFreeRecRef.current;
    if (!rec) return;
    if (discard) rec.discard = true;
    if (!rec.recorder) {
      if (discard && handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
      return;
    }
    if (rec.recorder.state === 'recording') rec.recorder.stop();
  }, []);
~~~
空闲时无操作。申请中丢弃时，先把旧对象标记 `discard=true`，再按身份同步复位；卡片读完后可立即申请新的麦克风。旧请求迟到返回时，仍读取旧 `rec.discard`，停轨道并早退，绝不创建旧录音机；其返回/异常分支的身份比较不会误清新对象。正在录音时先标丢弃再 `stop()`；`onstop` 负责复位和释放资源。重复停止不会对 inactive 录音机再次 `stop()`，也不会把 `discard` 改回 false。

静音阈值与 1.5 秒静音停止、30 秒上限、关闭免提时 `tick` 停止并由 `onstop` 丢弃、会话切换丢弃均保持原样。`stopTtsByUser`（现 1088–1093 行）和 `streamDoneRef.current && handsFreeRef.current` 的免提门槛（现 986–988 行）逐字未变；本轮只在录音入口防止重复启动。换票限流、429 退避、票据 TTL 及「点此播放」重换票逻辑未改。

**F3 / D4：免提按钮打开分支**（基线 2008–2014 行 → 2033–2040 行）：

修改前：

~~~ts
                    const next = !handsFree;
                    setHandsFree(next);
                    if (next) {
                      primeTtsAudio();
                      setVoiceOn(true);
                    }
                  }}
~~~

修改后：

~~~ts
                    const next = !handsFree;
                    setHandsFree(next);
                    if (next) {
                      ttsStoppedSessionRef.current = null;
                      primeTtsAudio();
                      setVoiceOn(true);
                    }
                  }}
~~~

第 2036 行在 `primeTtsAudio()` 前清除停止标记，与打开朗读一致；仅放行此后到达的分句，未增加补读已到达内容。

### `handsFreeRecRef` 全部置位、复位和字段变更

| 最终行号 | 操作 | 路径与覆盖说明 |
|---|---|---|
| 418 | `useRef(...)(null)` 初始化空闲 | 组件首次初始化；此处不是运行期复位 |
| 723–724 | 创建 `{ recorder: null, discard: false }`，`current = rec` | 唯一非 null 置位点，在 `await getUserMedia` 前；721 行重复启动守卫不修改已有对象 |
| 733 | `rec.recorder = mr` | 唯一录音机字段置位；从申请中进入录音准备阶段，引用仍是同一个对象 |
| 805 | `rec.discard = true` | 唯一丢弃字段置位；正在申请和正在录音都覆盖，且只单向置 true |
| 807 | `discard && current === rec` 时复位 `null` | 申请中被卡片点击取消的同步出口；旧对象保留 discard 标记，立即允许下一次合法开麦 |
| 729 | `current === rec` 时复位 `null` | 申请返回后丢弃、会话切换、免提关闭的全部早退；先停全部轨道。已被同步取消的旧请求无法清掉新对象 |
| 773 | `current === rec` 时复位 `null`，`onstop` 第一行 | 覆盖用户丢弃、静音自动停、30 秒上限、免提关闭等所有 stop；随后会话切换、免提关闭、未讲话、小 Blob、ASR 成功/失败/迟到等退出都发生在复位之后 |
| 797 | `current === rec` 时复位 `null` | `getUserMedia` 拒绝和启动过程抛错；包含取消的旧申请迟到拒绝，不能误清后来的新申请/录音 |

运行期复位共 **4 处：729、773、797、807**，全部按对象身份比较；非 null 置位只有 **724**。空闲 stop、免提关闭的入口、已有申请/录音的入口均未创建本次对象，不需要复位，也不能清掉他人对象。

### 仓库外离线克隆与第 5.1 节自检

克隆目录：`/private/tmp/tts-autoplay-round2.a6p5eu4f/fe`。按本轮要求覆盖规格旧的链接 node_modules 方案，建空目录后执行：

~~~bash
rsync -a --exclude node_modules --exclude .next --exclude '.env*' frontend/ /private/tmp/tts-autoplay-round2.a6p5eu4f/fe/
~~~

输出为空，退出码 0。没有复制或链接仓库的 node_modules。为将 npm 的写入也限制在仓库外，先把本机已有 `/Users/yangjing/.npm/_cacache` 用 `cp -Rc` 复制到 `/private/tmp/tts-autoplay-round2.a6p5eu4f/npm-cache/_cacache`（本地缓存复制，输出为空，退出码 0），设置 `npm_config_cache` 指向该临时目录。所有 npm/npx 命令同时设置 `npm_config_offline=true`、`npm_config_audit=false`、`npm_config_fund=false`、`NEXT_TELEMETRY_DISABLED=1`；然后在克隆中实际执行 `npm ci --offline`。克隆内 Next 版本为 **16.3.8**，node_modules 是实体目录；被检查的 page.tsx 与仓库最终源码逐字节一致。构建和安装均未在仓库的 frontend 中执行。

下面各代码块保存命令 stdout/stderr 的原样合并输出，退出码单独列出；空块表示命令没有输出。原始日志保存在临时目录 `logs/`。

#### 前端克隆安装：npm ci --offline

原样输出：

~~~text

added 426 packages in 3s
npm warn allow-scripts 1 package has install scripts not yet covered by allowScripts:
npm warn allow-scripts   unrs-resolver@1.11.1 (postinstall: napi-postinstall unrs-resolver 1.11.1 check)
npm warn allow-scripts
npm warn allow-scripts Run `npm approve-scripts --allow-scripts-pending` to review, or `npm approve-scripts <pkg>` to allow.
npm notice
npm notice New major version of npm available! 11.17.0 -> 12.2.0
npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.0
npm notice To update run: npm install -g npm@12.2.0
npm notice
~~~

退出码：0。

#### 前端克隆：npx tsc --noEmit

原样输出：

~~~text

~~~

退出码：0。

#### 前端克隆：npm run lint -- --max-warnings=28

原样输出：

~~~text

> frontend@0.1.0 lint
> eslint --max-warnings=28


/private/tmp/tts-autoplay-round2.a6p5eu4f/fe/app/page.tsx
   136:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   227:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   385:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   432:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   433:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   434:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   444:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   445:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   446:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   447:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   450:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   456:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   457:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   711:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   715:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   791:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1201:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1221:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1229:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1250:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1292:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1388:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1732) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1831:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1871:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2115:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/tmp/tts-autoplay-round2.a6p5eu4f/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)

~~~

退出码：0。

#### 前端克隆：npm run build

原样输出：

~~~text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.8 (Turbopack)
✓ Running next.config.ts took 555ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:58075) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 1807ms
  Running TypeScript ...
  Finished TypeScript in 1806ms ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) 
  Generating static pages using 16 workers (6/14) 
  Generating static pages using 16 workers (10/14) 
✓ Generating static pages using 16 workers (14/14) in 270ms
  Finalizing page optimization ...

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

~~~

退出码：0。

#### 仓库根：git status --porcelain

原样输出：

~~~text
 M docs/tasks/2026-09-29-tts-autoplay/02-spec.md
 M docs/tasks/2026-09-29-tts-autoplay/03-report.md
 M frontend/app/page.tsx
?? docs/tasks/2026-09-29-tts-autoplay/04-review-round2.md
?? docs/tasks/2026-09-29-tts-autoplay/05-fix-round2.md
~~~

退出码：0。

#### 仓库根：grep -n "new Audio" frontend/app/page.tsx

原样输出：

~~~text
737:      const audioCtx = new AudioContext();
~~~

退出码：0。

#### 仓库根：grep -rn 'new Audio\|createElement("audio")' frontend/app frontend/lib

原样输出：

~~~text
frontend/app/page.tsx:737:      const audioCtx = new AudioContext();
frontend/app/page.tsx:819:        const audio = document.createElement("audio");
~~~

退出码：0。

#### 仓库根：shasum backend/local-avatar.db backend/fiona.db

原样输出：

~~~text
172d800a603128374bab9177d39b7f66be20be7e  backend/local-avatar.db
403a086c4ec0cf28493fc9fa37b2b6eee528b261  backend/fiona.db
~~~

退出码：0。

#### 仓库根：git diff --stat -- frontend/AGENTS.md backend/

原样输出：

~~~text

~~~

退出码：0。

`git status --porcelain` 的全量输出包含开工前已有的三个任务文档变更；本轮新增变更恰好只有白名单中的 page.tsx 和本报告。三个已有文档、package.json、lockfile、frontend/AGENTS.md 与数据库的 SHA-256 已逐字节核对；不清理或回滚用户的已有变更。

两条规格原始宽泛 grep 如实命中第 737 行 `new AudioContext()`，这是保持原样的 Web Audio 上下文，不是 `new Audio()` 媒体元素。真正创建 HTMLAudioElement 的唯一位置仍为第 819 行，受 `if (!ttsAudioPoolRef.current)` 保护，`Array.from({ length: 2 }, ...)` 在组件生命周期内仅创建两个元素。此旧规格检查模式的歧义与第 1 轮相同；本轮不改规格或 AudioContext 写法。补充精确构造检查如下：

#### 仓库根：grep -nE 'new Audio\s*\(' frontend/app/page.tsx

原样输出：

~~~text

~~~

退出码：1。

#### 仓库根：git diff --check -- frontend/app/page.tsx

原样输出：

~~~text

~~~

退出码：0。

精确构造 grep 的退出码 1 表示无匹配；`git diff --check` 退出码 0。数据库 SHA-1 与开工前及规格前缀一致；受保护的 AGENTS/backend diff 为空。TypeScript、lint 和 build 均退出码 0；lint 26 条既有警告、0 错误，没有本轮新增警告。安装时的 npm allow-scripts 提醒针对 `unrs-resolver` 的已有 postinstall；安装及全部自检已通过，没有执行额外审批或联网动作。

### 补充：一次性免提状态与同步顺序验证

在仓库外执行 `node /private/tmp/tts-autoplay-round2.a6p5eu4f/round2-mock-check.cjs`。脚本通过 TypeScript AST 从最终 page.tsx 提取实际三个 hook 函数体，用本地 VM/mocks 验证申请/停止时序；没有启动浏览器、没有真实媒体权限调用或网络请求，没有修改任何已有测试的输入/断言，也没有在仓库新增测试文件。

原样输出：

~~~text
One-off round 2 VM mock checks; actual page.tsx hook bodies; no browser/network.
PASS F2 duplicate pending and active starts issue one getUserMedia request
PASS F2 canceled pending resolve releases tracks and preserves newer active recording
PASS F2 canceled pending rejection preserves newer active recording
PASS F2 current getUserMedia rejection resets its ref
PASS F2 pending session changed early return resets ref and releases tracks
PASS F2 pending hands-free disabled early return resets ref and releases tracks
PASS F2 active discard is idempotent, releases resources and skips ASR/send
PASS F2 normal spoken onstop resets immediately and sends once
PASS F2 onstop no-speech and small-blob early returns also reset
PASS F2 active session switch or hands-free shutdown discards onstop
PASS F2 original silence threshold and 30-second stop paths still reset
PASS F1 confirm hook synchronously stops/discards, clears, primes, then plays new session
PASS F3 exact insertion and unrelated TTS functions match pre-edit source
PASS 13/13 checks
SOURCE startHandsFreeRecording: page.tsx:720
SOURCE stopHandsFreeRecording: page.tsx:802
SOURCE handleConfirmTts: page.tsx:1269
~~~

退出码：0。

13/13 检查通过：重复 pending/active 启动只申请一次；取消的旧申请迟到 resolve/reject 不创建旧 recorder、不清新 rec；丢弃已讲话且有数据的录音只释放资源，不发 ASR/handleSend；正常发送、静音/上限停止和各早退全部复位；卡片点击同步顺序和新会话播放正确。静态检查还核对 `stopTtsByUser`、整个 `playNextInQueue`（含免提门槛）、`primeTtsAudio`、`clearTtsQueue`、准备/预取/续播/归一化/入队函数均与开工前源码完全一致，F3 按钮只有指定插入的一行。此验证不代替真实浏览器自动播放或 MediaRecorder 的验收。

最终范围检查通过：三个开工前已有任务文档、frontend/AGENTS.md、package.json、lockfile 和两份数据库共 8 个文件的 SHA-256 均未变化；报告开工前的完整字节前缀未变化；相对于开工前 `git status --porcelain` 的新增项恰好只有两个白名单文件；被检查的克隆 page.tsx 与仓库最终源码相同。

### 未决问题

没有影响本轮实现的未决问题。D1 的补开麦原行为保留，D2 的卡片打断与丢弃已实现，D3 的幂等录音已实现，D4 的停止标记清除已实现；先前报告中的相关待拍板事项由本轮用户决定覆盖。票据限流、429 退避与 TTL 150 秒及按剩余有效期重换票行为全部保持不变。

本轮按硬规则未运行浏览器。`05-fix-round2.md` 第 4 节的 CONFIRM-PLAY、CONFIRM-BLOCKED、CONFIRMHF/CONFIRMNAT、DRAIN*、DOFF/DSTOP/DNAT/RECOFF/MIDSTOP、HFON-AFTER-OFF 以及 V1–V11/A–H 仍由 Claude 主会话实测，尤其确认真实环境中同时录音的 MediaRecorder ≤1、卡片读完后开麦一次、旧回复不再出声和被拒提示消失。静音解锁改 muted 和关朗读再开补读已到达内容按用户决定不在本轮范围内。


## 第 3 轮返修

依据 `04-review-round3.md` 第 3 节，严格执行 3.0 硬规则与白名单、3.1 唯一必改项。本轮相对于开工时的未提交工作区，源码只新增一行；本报告仅在末尾追加。F1/F2/F3 全部保留，未修改已有测试的输入或断言、依赖、package.json、lockfile、其他任务文档或任何后端文件。未读 `.env*`，未发起真实网络调用或下载，未运行 `next dev` 或浏览器，未写入 git 状态。辅助代理只读核查，没有并行修改文件。

### 改动行号与前后代码

文件：`frontend/app/page.tsx`。在 `handleSend` 的第 **1441 行**新增 `stopHandsFreeRecording({ discard: true });`，紧挨原 `clearTtsQueue()` 之前；后者现为 **1442 行**。所有入口早退仍位于 **1390、1391、1392、1395–1398 行**，均已通过才执行新增调用，因此被拒的发送不会停止正在进行的免提录音。`handleSend` 为普通 async 函数，无依赖数组需要修改。

改动前（开工快照第 1440–1444 行）：

```ts
    // ── 流式 TTS：新一轮先清队列并创建 session，再按句切（首句激进、碰逗号也切）──
    clearTtsQueue();
    ttsSessionRef.current += 1;
    const mySession = ttsSessionRef.current;
    streamDoneRef.current = false;
```

改动后（第 1440–1445 行）：

```ts
    // ── 流式 TTS：新一轮先清队列并创建 session，再按句切（首句激进、碰逗号也切）──
    stopHandsFreeRecording({ discard: true });
    clearTtsQueue();
    ttsSessionRef.current += 1;
    const mySession = ttsSessionRef.current;
    streamDoneRef.current = false;
```

逐字节验证：删除新增的第 1441 行后，整个 page.tsx 与开工快照完全相同。保留位置包括 F1 `handleConfirmTts` **1269–1285**、F2 ref **418** / `startHandsFreeRecording` **720–800** / `stopHandsFreeRecording` **802–811**、F3 停止标记复位 **2037**、免提门槛 **986–988**、`stopTtsByUser` **1088–1093**；19e5804 和 063a999 的换票、退避、TTL 逻辑全部保留。F3 及其他后续源码只因插入而整体顺延一行。

### 各调用来源的效果

以下行号均为改后源码；行为说明来自实际代码核查，浏览器时序仍由主会话验收。

| 调用来源 | 新增调用的效果 |
| --- | --- |
| 输入框发送按钮，2187 | 接受发送后，将旧免提录音 R1 标为 discard 并停止；现有 onstop 在释放资源后因 discard 早退，不向 `/asr/recognize` 发送这段录音。新回复读完后由保留的门槛开新录音，30 秒上限从新录音开始重新计时，入口幂等保护继续限制最多一路。 |
| 回车，1740 | 与发送按钮经过同一个 handleSend，效果相同；原有 Shift+Enter、输入法合成过滤及全部发送早退保持不变。 |
| 图片重试，2066 | 通过用户、会话、图片及参考图校验后，同样停止并丢弃旧免提录音。不合法或被加载/活动流拒绝的重试仍在新增调用之前早退，不停止录音。 |
| 免提 ASR 回调，790 | 该路录音的 onstop 第一行 **773** 已按对象身份把 handsFreeRecRef 复位，随后才做 ASR 并调用 handleSendRef。正常免提主路径中，此处新增调用为**空操作**，不影响已经完成的 ASR、识别文字发送或读完后再次开麦。 |
| 按住说话 / 语音面板 ASR 回调，641 | 该路录音已停止并释放自己的轨道；新增函数只读取免提录音 ref，不改变该路 ASR 或识别结果。若仍有旧免提录音则丢弃，没有则空操作。 |
| 内联录音 ASR 回调，710（返修单列出的另一语音入口） | 同样经过 handleSendRef，效果与 641 相同；不改自身录音、ASR 或识别文字发送。 |

### 仓库外离线克隆与规格 5.1 全部命令

克隆目录：`/private/tmp/tts-autoplay-round3.toahwb6c/fe`。没有复制或链接仓库的 node_modules。克隆只复制前端源码，额外排除 `.env*` 和旧 tsconfig.tsbuildinfo；依赖通过 **npm ci --offline** 安装为克隆内实体目录。规格旧的 node_modules 链接示例由本轮 3.2 明确要求覆盖。

克隆命令：

```bash
rsync -a --exclude node_modules --exclude .next --exclude '.env*' --exclude tsconfig.tsbuildinfo frontend/ /private/tmp/tts-autoplay-round3.toahwb6c/fe/
```

原样输出：

~~~text
~~~

退出码：0。

将本机已有 npm 包缓存复制到仓库外临时目录（仅本地复制，不是复制仓库的 node_modules）：

```bash
cp -Rc /Users/yangjing/.npm/_cacache /private/tmp/tts-autoplay-round3.toahwb6c/npm-cache/_cacache
```

原样输出：

~~~text
~~~

退出码：0。

所有 npm/npx 命令设置 `npm_config_cache=/private/tmp/tts-autoplay-round3.toahwb6c/npm-cache`、`npm_config_offline=true`、`npm_config_audit=false`、`npm_config_fund=false`、`NEXT_TELEMETRY_DISABLED=1`。安装及 TypeScript、lint、build 均在克隆目录执行；未在仓库 frontend 内安装或构建。下列输出以 stdout/stderr 合并原始字节记录，没有删掉警告或 notice；构建进度输出的回车字符也保留。

#### 前端克隆安装：npm ci --offline

原样输出：

~~~text

added 426 packages in 3s
npm warn allow-scripts 1 package has install scripts not yet covered by allowScripts:
npm warn allow-scripts   unrs-resolver@1.11.1 (postinstall: napi-postinstall unrs-resolver 1.11.1 check)
npm warn allow-scripts
npm warn allow-scripts Run `npm approve-scripts --allow-scripts-pending` to review, or `npm approve-scripts <pkg>` to allow.
npm notice
npm notice New major version of npm available! 11.17.0 -> 12.2.0
npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.0
npm notice To update run: npm install -g npm@12.2.0
npm notice
~~~

退出码：0。

#### 前端克隆：npx tsc --noEmit

原样输出：

~~~text
~~~

退出码：0。

#### 前端克隆：npm run lint -- --max-warnings=28

原样输出：

~~~text

> frontend@0.1.0 lint
> eslint --max-warnings=28


/private/tmp/tts-autoplay-round3.toahwb6c/fe/app/page.tsx
   136:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   227:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   385:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   432:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   433:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   434:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   444:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   445:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   446:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   447:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   450:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   456:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   457:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   711:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   715:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   791:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1201:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1221:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1229:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1250:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1292:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1388:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1733) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1832:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1872:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2116:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/tmp/tts-autoplay-round3.toahwb6c/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)

~~~

退出码：0。

#### 前端克隆：npm run build

原样输出：

~~~text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.8 (Turbopack)
✓ Running next.config.ts took 533ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:87919) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 1960ms
  Running TypeScript ...
  Finished TypeScript in 2.0s ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) 
  Generating static pages using 16 workers (6/14) 
  Generating static pages using 16 workers (10/14) 
✓ Generating static pages using 16 workers (14/14) in 297ms
  Finalizing page optimization ...

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

~~~

退出码：0。

#### 仓库根：git status --porcelain

原样输出：

~~~text
 M docs/tasks/2026-09-29-tts-autoplay/02-spec.md
 M docs/tasks/2026-09-29-tts-autoplay/03-report.md
 M frontend/app/page.tsx
?? docs/tasks/2026-09-29-tts-autoplay/04-review-round2.md
?? docs/tasks/2026-09-29-tts-autoplay/04-review-round3.md
?? docs/tasks/2026-09-29-tts-autoplay/05-fix-round2.md
~~~

退出码：0。

#### 仓库根：grep -n "new Audio" frontend/app/page.tsx

原样输出：

~~~text
737:      const audioCtx = new AudioContext();
~~~

退出码：0。

#### 仓库根：grep -rn "new Audio\|createElement(\"audio\")" frontend/app frontend/lib

原样输出：

~~~text
frontend/app/page.tsx:737:      const audioCtx = new AudioContext();
frontend/app/page.tsx:819:        const audio = document.createElement("audio");
~~~

退出码：0。

#### 仓库根：shasum backend/local-avatar.db backend/fiona.db

原样输出：

~~~text
172d800a603128374bab9177d39b7f66be20be7e  backend/local-avatar.db
403a086c4ec0cf28493fc9fa37b2b6eee528b261  backend/fiona.db
~~~

退出码：0。

#### 仓库根：git diff --stat -- frontend/AGENTS.md backend/

原样输出：

~~~text
~~~

退出码：0。

`git status --porcelain` 只出现白名单源码/报告和本任务目录。02-spec.md 的修改及 04-review-round2.md、04-review-round3.md、05-fix-round2.md 未跟踪项都在开工时已存在，本轮没有改动它们，也未清理或回滚已有工作区变更。

TypeScript、lint、build 均退出码 0；lint 为 **26 条警告、0 错误**。为确认警告没有增加，还在同一克隆、同一离线依赖下临时替换为开工前 page.tsx 跑了一次 `npm run lint -- --max-warnings=28`，随后恢复最终源码：改前同样退出码 0、26 条警告、0 错误。将诊断位置及消息里的引用行号归一化后，全部警告消息和规则逐条一致。handleSend 仍有原有 exhaustive-deps 警告，没有增加警告或改为 useCallback。

安装输出中的 allow-scripts 提醒对应既有 unrs-resolver postinstall；安装和所有自检已通过，没有执行 npm approve-scripts 或新增依赖。npm 的版本 notice 已原样记录，没有执行更新命令。构建中的 DEP0205 也保留在原始输出中。

数据库开工前和自检后的 SHA-1 完全相同，分别为 `172d800a603128374bab9177d39b7f66be20be7e` 和 `403a086c4ec0cf28493fc9fa37b2b6eee528b261`。AGENTS/backend diff 为空。

两条规格原始宽泛 grep 如实命中保留的第 737 行 `new AudioContext()`；因此第一条没有达到旧规格字面的「0 行」，这是既有 Web Audio 上下文，并非 HTMLAudioElement 构造。本轮唯一允许的源码变更不包括改写它，故保留原样并如实报告。真正的 HTMLAudioElement 创建只在第 819 行，受 `if (!ttsAudioPoolRef.current)` 保护、`Array.from({ length: 2 }, ...)` 在组件生命周期内创建两个元素。补充精确检查如下；退出码 1 表示无匹配：

#### 仓库根：grep -nE 'new Audio\s*\(' frontend/app/page.tsx

原样输出：

~~~text
~~~

退出码：1。

#### 仓库根：git diff --check -- frontend/app/page.tsx

原样输出：

~~~text
~~~

退出码：0。

### 最终范围与自检核对

仓库外 Python 范围检查对照开工快照的 351 个文件，核对报告原始字节前缀、严格的一行源码差异、克隆源码、包文件、诊断消息、数据库哈希及 git status。没有修改或新增仓库测试。原样输出：

~~~text
PASS opening snapshot: 351 files checked; only frontend/app/page.tsx and task 03-report.md changed
PASS report keeps all original bytes and only appends 第 3 轮返修
PASS source adds exactly one line at 1441; all other bytes and all early returns are preserved
PASS F1/F2/F3, hands-free gate, stopTtsByUser and ticket/backoff/TTL code are unchanged
PASS git status matches opening status and contains only whitelist files and this task directory
PASS clone page.tsx matches final source; node_modules is a real directory; package.json and lockfile match
PASS baseline/final lint: 26 warnings, 0 errors; warning messages and rules match after line-number normalization
PASS database hashes match before/after; AGENTS/backend diff is empty
PASS npm ci --offline and all specification 5.1 command outputs/exit codes are recorded verbatim
~~~

退出码：0。

最终相对于开工快照，只有两个白名单文件的内容变化；其余 349 个快照文件未变化，没有新增仓库文件。报告此前全部字节保留，源码严格只新增指定调用。所有规格 5.1 命令已实际重跑；宽泛 grep 的既有 AudioContext 命中和精确 grep 的无匹配退出码均如实列出，没有为让文本检查通过而扩大源码改动。

### 未决问题

没有影响本轮一行实现的未决问题。以下是保留的既有偏离或验证待办，不扩大本轮实现范围：

- **F2.4 已接受的现有时机偏离**：申请中丢弃时同步复位 ref，旧 getUserMedia 返回后只停轨道、不创建录音机；这是 04-review-round3.md 第 2.2 节已接受的方案，本轮逐字保留。05-fix-round2.md 和 02-spec.md 的措辞同步由返修单作者负责，本轮不修改。相关 iOS Safari 两次申请在途的 O8 真机风险仍待确认。
- **浏览器验收仍由 Claude 主会话执行**：按 3.0 硬规则没有启动浏览器。第 3.3 节 TYPED-SILENT、TYPED-SPEAK（含在 9abbf677 上先失败的正控）及不退化矩阵尚未在本轮实测；本报告的调用效果为代码推导，不能替代 stop 事件 300ms、30 秒计时、ASR 完整文本和并发上限的真实浏览器证据。
- **O1–O10 全部未做**：没有改入口幂等保护、stopHandsFreeRecording、stopTtsByUser、门槛、F1/F3 或票据相关代码，也没有借本轮修正其他已知问题。
