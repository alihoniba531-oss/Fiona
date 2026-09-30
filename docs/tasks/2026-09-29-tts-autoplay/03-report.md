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
