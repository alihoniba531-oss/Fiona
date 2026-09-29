# 独立复核 第 2 次（2026-09-29）

只核验第 1 次复核的 5 条必须修复项（M1–M5，含规格作者追加的 V1–V4）。每条由一位全新上下文复核员复现原失败并核验修复。

> 说明：本次与第 1 次复核由主会话默认模型执行，未按用户规定使用 Fable；第 3 次复核改用 Fable，并补做一次全任务审阅。

| 条目 | 结论 |
|---|---|
| M1（生图改为「正则提名、意图模型确认」）+ 05-fix-round3 V1（讨论兜底恢复）+ V2（生图用完整原话） | **不通过** |
| M2（Safari/iOS 朗读只播第一句）+ 05-fix-round3 V4（Chromium 开放区间 bytes=0- 走流式 20 | **通过** |
| M3 并发重复「停止」把用户永久锁死（T3，本任务引入的回归） | **通过** |
| M4 部署手册 umask 077 影响后续更新步骤（T10，第 1 轮引入的回归），附带核对 O7 文档修正 | **通过** |
| M5 繁简归一缺字，覆盖性测试测不出漏字（T4） | **不通过** |

## M1（生图改为「正则提名、意图模型确认」）+ 05-fix-round3 V1（讨论兜底恢复）+ V2（生图用完整原话）

**结论：不通过**

**修复前复现：** 没有采信 03-report，全部自己复现。实验只在 scratchpad/deepfix-review-r2/M1-V1V2/ 下的四份后端副本里做：base 是用 git archive 取出的 656b7cf；r1 取自第 1 轮复核留下的 deepfix-review/concurrency/be，其中有 _IMAGE_QUESTION_WORD，intent_router 的 md5 为 4be12468…；r2 是第 3 轮返修前的快照 verify-deepfix/r2/be；cur 是当前仓库的 rsync 副本，sha256 与仓库逐文件一致。

1）复核第 1 轮的端到端场景，用真实 uvicorn 复现。起法是 launcher.py，端口 8062，DEV_MODE=0，意图模型打桩一律返回 null，生图打桩只记录调用。在 r1 上 POST /chat 发「生成一张图片失败了」，结果：
- SSE 依次是 generating_image、generated_image、「图片已生成。」、done；
- calls.jsonl 只有一条 generate_image(prompt=生成一张图片失败了)，意图模型一次都没调；
- 草莓 200→190。

2）我自写了 tests/test_review_m1.py::test_A，共 12 句：返修单点名的 7 句，外加我另写的 5 句。它在 r1 和 base 上都是 11 句直接生图、classified=[]。

3）V1 在 r2 上复现。模型桩对讨论句返回 generate_image，11 句全部生图（prompt='误判'）。这 11 句包括「你会画画吗」「怎么生成图片」「不要画了」，以及我另写的「如何画一只猫」「生成一张图片的提示词怎么写」「介绍一下生图功能」等。

4）V2 在 r2 上复现。模型桩返回截短的 prompt 时，送去生图的是模型给的 '黑猫'、'雪夜书店'、'柴犬'、'狐狸'、'x'，不是用户的完整原话。

**现状证据：** 当前代码副本上运行 PYTHON_DOTENV_DISABLED=1、临时 DB/uploads、DASHSCOPE/DEEPSEEK=placeholder 下 `.venv/bin/python -m pytest tests/test_review_m1.py`，结果 43 passed、4 failed。4 个失败全部是下面「回归」一栏里的 H 探针。逐项如下：

- A：12 句候选句 + DEV_MODE=0 + 模型返回 null。全部 generated=[]，classified==[原句]（只调一次），回复是普通回复「测试回复」，草莓只扣普通回复的 10 颗。
- B：两端带空格的长描述 + 模型给出截短 prompt「黑猫」和 9:16。generate 收到的是 strip 后的完整原话，比例 9:16（原文没写比例，采用模型的合法值），扣 10。
- B2：普通意图路径（非候选句）同样用完整原话。原文写了「竖版」「横版」时，原文比例优先于模型比例。
- C1/C2/C3：分别是 recognize_intent 抛异常、真实 recognize_intent 下游客户端超时、返回非 JSON。三种情况都不生图，走普通回复，模型只调 1 次，不重试。
- D：同一轮只调一次模型（复用）。覆盖 5 种情形：null、null+旧生图待补、web_search+旧生图待补（工具被执行）、null+route 待补、非候选句，classified 都恰好 1 次。
- E：用真实 detect_mode，把会话设为 mirror。
  - 模型确认生图：生成「画一只在海边看日落的狐狸」，stream_mirror 调用 0 次。
  - 模型否决：stream_mirror 调用 1 次（正控，证明镜子确实处于激活状态）。
- F：11 句讨论句，模型误判为 generate_image，全部被拦截。其中既有候选句（如「生成一张图片的提示词怎么写」），也有非候选句。正控「能帮我画一辆雨中的红色自行车吗」仍然生图。
- G：mode=image 按钮下 5 组比例组合，都不调意图模型、不走模式判定，按原文和按钮比例生图，与 base、r1、r2 结果一致。

真实 uvicorn 端到端：端口 8061，DEV_MODE=0，模型桩返回 null，发「生成一张图片失败了」。
- SSE 是「测试」「回复」、done；
- calls.jsonl 是 intent_model(生成一张图片失败了) 一次 + reply_model，没有 generate_image，uploads 目录为空；
- 草莓 200→190，只是普通回复计费。

其他检查：
- 实施方的 test_image_intent_precision.py 与 test_chat_image_generation.py：110 passed。
- 改图的 test_chat_image_editing、test_chat_multi_image_editing、test_image_generation（与基线相同）：186 passed。
- cur 副本全量 pytest：1461 passed。
- docs/ARCHITECTURE.md:86 已写明「候选句因此多一次模型识别的延迟和调用成本」。
- 结束时仓库目标文件的 sha256 全部一致，端口 8061/8062 已无监听，launcher 进程已全部结束。

**回归：** 有一处与 M1 直接相关的回归：画面为空的候选句不再追问，而是直接付费生成一张无意义的图。

**位置**：backend/services/chat_service.py:1097。候选句经确认的分支里写的是：

```python
intent_result = {**intent_result, "params": params, "missing": []}
```

它把模型返回的 missing 丢掉了。explicit_image_intent 自己算出的 missing 也没有被使用（intent_router.py:183 仍在计算 `"missing": [] if subject else ["prompt"]`）。

**复现**：输入「帮我生成图片」「帮我生成一张图片」「画一张图」「给我画一幅画」，模型按 INTENT_PROMPT 自带示例返回 `{"intent":"generate_image","params":{},"missing":["prompt"]}`。
- 当前代码：以原句本身作为画面描述调用生图，回复「图片已生成。」。
- base 与 r1：回复「想生成什么画面？可以告诉我主体、场景和风格。」，不生图。

**真实 uvicorn 实测**（DEV_MODE=0，同样的模型桩，消息「帮我生成一张图片」）：
- cur（8061）：调用 generate_image(prompt=帮我生成一张图片)，草莓 200→190；
- base（8062）：只追问，模型和生图都没调用，草莓 200→200。

**被测试改动掩盖**：第 2 轮把基线测试 tests/test_chat_image_generation.py:42/107/118 的输入从「帮我生成图片」改成了「帮我创作」。「帮我创作」不是候选句，走的是普通意图路径，所以测试仍然通过。我把输入还原成「帮我生成图片」、沿用实施方自己的 confirmed_image_intent 夹具重跑，9 个用例全部失败，断言是 `[('帮我生成图片','1:1')] == []`。这违反 02-spec T1 的「基线里已有的生图相关测试全部保持通过」。

**建议修法**：确认分支改用 image_candidate["missing"]。它由正则判断画面主体是否为空，不受模型短 prompt 影响。同时把两条基线测试的输入还原为「帮我生成图片」。

除此之外，mode=image/image_edit 按钮路径、镜子模式、待补参数、讨论兜底、完整原话、单轮只调一次模型，均未发现回归。

**可优化：**
- ARCHITECTURE.md 对延迟和成本只有一句定性描述。可以写得更准确：被模型否决的候选句会复用本轮识别结果，比普通消息没有多出调用；多出的是「确认生图」这一类请求——生图开始前要先等一次意图模型（max_tokens=150）。
- 候选句被模型否决时，旧的 generate_image 待补状态会原样保留，不会清除。刚被追问「想生成什么画面」的用户如果用「画一只戴帽子的猫」这类候选句作答，而模型返回 null，就既不生图也不填待补。这取决于模型，可以考虑在否决时清掉，或让候选句优先填这个待补。
- explicit_image_intent 返回的 params.prompt 和 aspect_ratio 在 run_chat 里已经不再使用，只剩「是不是候选」这一个信号。建议精简返回值，或者像上面「回归」一栏建议的那样改用它的 missing，免免调用方误以为这些字段仍然生效。
- 非候选句走普通意图路径时，recognize_intent_with_fallback 在 recognize_intent 之外抛出的异常没有被单独捕获，会进入外层 except，给用户返回错误事件。这与基线一致，不算本轮回归。

## M2（Safari/iOS 朗读只播第一句）+ 05-fix-round3 V4（Chromium 开放区间 bytes=0- 走流式 200）

**结论：通过**

**修复前复现：** 第 1 轮代码已被覆盖，所以我用对照版本复现，工作目录是 scratchpad/deepfix-review-r2/M2/。

1）M2 原问题。把后端 rsync 一份到 backend_ctrl/（排除 .venv、uploads、*.db、.env*，另外把误带过来的 *.db.bak 也删了），只改 routers/voice.py 两处，恢复第 1 轮的语义：不做 Range 校验，任何请求都走 StreamingResponse 200。前端用同一份生产构建（next start 8064，后端 8063，synthesize/synthesize_stream 打桩返回 ffmpeg 生成的本地 mp3），跑 pw_queue.py webkit ctrl1 的结果如下：
- 后端日志：range=bytes=0-1 得到 200、无 Content-Length、发回整段 20107 字节；接着无 Range 请求，同样是 200；
- 前端事件：loadedmetadata/durationchange 的 dur=inf，playing 之后在 5521ms 和 5654ms 触发 stalled；
- play_order 只有「第一句」，ended 为空。
这和第 1 轮复核描述的失败完全一致，也说明我的测量脚本能测出失败（正控成立）。同一份对照代码下 Chromium 三句都正常。

2）V4 原问题。再做一份 backend_r2sem/，只把判定改回第 2 轮的「凡带 Range 都走缓存合成 206」。Chromium 实测三条请求都是 range=bytes=0- 得到 206，Content-Length 为全长，合成日志三次都是 kind=synthesize（非流式），这就是 V4 所说首音变慢的路径。

3）测试的正控：
- tests/test_tts_private_tickets.py 在 backend_ctrl 上 12 failed / 3 passed；
- 在 backend_r2sem 上，test_tts_first_zero_open_range_streams_then_reuses_cache_as_206 失败，报「zero-open playback must stream first」。

**现状证据：** 环境：仓库外副本 backend/，与仓库的 routers/voice.py 哈希一致（194abdf2…）。环境变量为 FIONA_DB_PATH/FIONA_UPLOADS_DIR（指向临时路径）、DEV_MODE=1、JWT_SECRET（随机）、DASHSCOPE/DEEPSEEK=placeholder、PYTHON_DOTENV_DISABLED=1。启动命令是 run_stub.py（打桩 tts.synthesize/synthesize_stream，并记录每次合成和每个 /tts 请求的状态码与头）在 127.0.0.1:8063 起服务。前端用 cp -cR 克隆，删掉 .next 后执行 FIONA_BACKEND_ORIGIN=http://127.0.0.1:8063 next build，build exit=0，再 next start -p 8064。

A. 原始 HTTP 协议检查：proto_check.py 8063 … main，46 项 0 失败；expire 模式 5 项 0 失败。
- 同一票据：
  - bytes=0-1 得 206，body 2 字节，Content-Range: bytes 0-1/20107，Content-Length: 2，Accept-Ranges: bytes；
  - 再请求 bytes=0-20106 得 206，body 全长 20107；再请求 bytes=0- 也得 206 全长；
  - 以上三次合计只合成一次（synth delta=1）；
  - 第 4 次仍是 206，第 5 次带或不带 Range 都是 404「朗读票据已用完」。
- 非法 Range 返回 416：bytes=abc、bytes=0-1,2-3、items=0-1、bytes=、bytes=-、bytes=-0、「bytes= 1-x」。越界的 bytes=5-2、bytes=20107-、bytes=20207-20307 返回 416，并带 Content-Range: bytes */20107。
- 未缓存时：
  - 无 Range 得 200，Transfer-Encoding: chunked，没有 Content-Length/Content-Range，合成日志是 kind=stream；
  - bytes=0- 同样是 200 chunked，kind=stream。
- 已缓存后：bytes=0-、0-1、-100、10- 都得 206，字节和头正确，没有再次合成。
- 未缓存时的 bytes=5- 走缓存合成，得 206。
- 并发：bytes=0- 流式进行中再发 bytes=0-1，前者 200 全长，后者 206 两字节，总共合成 1 次。
- 跨用户：带或不带 Range、票据缓存前后，一律 404，且不消耗次数（本人随后仍得 206）。无 Cookie 得 401；?text= 得 422；?ticket=&text= 得 400。
- 过期：签发后等 62 秒，未缓存票据（bytes=0-1、bytes=0-、无 Range）和已缓存票据（bytes=0-1）都返回 404。

B. 浏览器实测：pw_queue.py。只用 route 伪造 /api/chat 的三句 SSE，/api/tts/* 全部经 next start 代理打到真实后端；生产构建，未登录态之外没有其他伪造。
- WebKit（webkit-2359/pw_run.sh）跑 3 次（cur1、cur2、cur3）：
  - play_order 均为 第一句→第二句→第三句；
  - 每次都有 3 个 ended，例如 cur1 在 4286ms、6306ms、8721ms，dur 分别为 1.2539、1.6718、2.0637（有限值）；
  - errors=[]，stalled=0，seq_ok=True（下一句的 play() 都在上一句 ended 之后）；
  - 后端日志：每票两次请求，bytes=0-1 得 206（2 字节），再 bytes=0-N 得 206 全长；每票只有一次 kind=synthesize。
- Chromium（chromium_headless_shell-1243）跑 3 次：顺序相同，每次 3 个 ended，errors=[]，seq_ok=True；后端日志是每票一次 range=bytes=0- 得 200 流式（无 Content-Length/Content-Range），合成全是 kind=stream。
- WebKit 另加一轮 55 秒的长中句（xl 集）：3 个 ended

**回归：** 无。
- Chromium/WebView2 的 bytes=0- 首次请求恢复为流式 200（synthesize_stream），不再先整句合成。
- WebKit 每句 2 次请求、合成 1 次，55 秒长句也不超过每票 4 次。
- 跨用户、过期、超次数在带或不带 Range 时都是 404。
- 无 Range 仍是流式 200，/tts/synthesize 与缓存共用同一次合成。
- 预取和按序播放正常。

**可优化：**
- 缓存总量超过 64MB 时，_complete_tts_audio 会把最旧的整条票据从表中删掉（_tts_tickets.pop），而不只是丢弃它的 cached_audio。若 WebKit 某张票据恰好在 0-1 探测和 0-N 全长请求之间被挤掉，第二次请求会得到 404，这一句会被跳过。小规模内测概率很低，建议改为只清 cached_audio/audio_build，保留票据本身。
- Range 语法校验放在票据校验之前：跨用户、过期或不存在的票据如果带畸形 Range，会返回 416 而不是 404。不泄露信息，也不消耗次数，只是错误码口径不一致。
- 边缘情况：bytes=0- 的流式请求中途断开时，build 以 None 收尾；此时正在等待同一 build 的闭区间请求会得到 502，这一句被跳过。WebKit 不走流式分支，实际很难同时出现。
- 按 M2 的设计，Safari/iOS 的首音要等整句非流式合成完成才返回首字节，首句延迟等于整句合成耗时，比 Chromium 的流式分支慢。这是规格选定的取舍，建议在产品侧知晓。
- 免提模式在队列播完后重新开麦，本轮未实测（需要麦克风设备）。只从代码推断：最后一句的 ended 已稳定触发，会走到 playNextInQueue，在队列为空且 streamDoneRef/handsFreeRef 成立时调用 startHandsFreeRecording。
- 03-report.md 第 3 轮称本机无法启动 Playwright。本次已用本机现有的 WebKit 2359 与 chromium_headless_shell-1243，通过 uv --offline 的 playwright 1.63.0 完成实测，没有下载任何东西，可以把结果补进报告。脚本在 /private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/deepfix-review-r2/M2/（run_stub.py、proto_check.py、pw_queue.py、pw_out/*.json）。

## M3 并发重复「停止」把用户永久锁死（T3，本任务引入的回归）

**结论：通过**

**修复前复现：** 做法：把当前 backend 用 rsync 复制两份到 scratchpad/deepfix-review-r2/M3/ 下（排除 .venv、uploads、*.db*、.env*，误带过来的 local-avatar.db.bak-* 已立即删除）。cur 是当前代码，与仓库 diff -rq 一致，只多出我自己的测试文件。r1 只把 services/exchange_service.py 换成第 1 轮复核员留存的快照（deepfix-review/concurrency/be），diff 确认两者只差取消处理器和 cancel_exchange 两处，exchange_store 等其他文件都用当前版本，这样对照只隔离 M3 这一处修复。

1）进程内 TestClient，用我自写的 tests/test_zz_m3_review.py，每轮换新用户，每场景 40 轮：
- 同一交流两线程 Barrier 同时 /stop：泄漏 28/40（这 28 轮 task.cancelling()=2）；每次 DB 往返加 5ms 放大窗口后为 30/40、32/40。
- 4 路同时 /stop：泄漏 30/40（放大窗口后）。
- peer 双方 Barrier 同时 /stop：泄漏 12/40；放大窗口后 25/40、22/40。
- reserve_model_call 已提交但未返回时停止，四个变体各 40/40 泄漏。四个变体是：注入点在「返回后」或「提交后、仍在连接 async with 内」，各配 1 次或 2 次停止。
- 在收尾期间直接对任务连发 7 次 task.cancel()：40/40 泄漏。
- 泄漏形态与返修单描述一致：交流 stopped，inflight_call_id 非空，reserved_tokens=12730（peer 为 2912），调用停在 reserved。停止后再发起返回 409「你已有进行中的交流，请结束后再开始。」，peer 时双方都 409。

2）真实 uvicorn（uvloop，端口 8065）+ 假上游（8066），同一用户连续轮次：同交流双停在第 1 轮泄漏，peer 双停在第 0 轮泄漏且双方 409，预留未返回在第 0 轮泄漏。

3）正控：仓库自带的三条 M3 用例在 r1 上 3 failed，说明这些用例能测出原问题，不是空转。

**现状证据：** 代码核对（当前工作区，sha256：exchange_service.py 5c98d01d…，exchange_store.py 8e234c62…，结束时复核未变）：
- exchange_service.py:238-252：取消分支把 stop_and_discard_reserved_calls 建成独立任务，用 while not done + asyncio.shield 循环等待，吞掉收尾期间的再次取消，结算完成后再 raise。分支内不引用 call_id。
- cancel_exchange:283-290：只有 task.cancelling()==0 时才调用 cancel()，之后只等待。
- exchange_store.stop_and_discard_reserved_calls：在一个 BEGIN IMMEDIATE 事务里按 exchange_id 结清全部 reserved 调用，run_token 必须是 NULL 或本 run 的令牌（交流不会重启，所以成立）。调用记为 discarded，estimated=1，按 input/output_limit 计量，扣回 reserved_tokens，清空 inflight_call_id。

1）TestClient，当前代码，同一用户连续 40 轮（任何一轮泄漏都会让后续轮次 409，比每轮换新用户更严）：
- 同交流双停（jitter 0 或 4ms）、四路停止、peer 双方同时停止、预留未返回的四个变体、收尾期间直接连发 7 次 cancel：failures=0，每轮立即再发起都是 201，调用为 discarded，inflight_call_id=NULL，reserved_tokens=0，全库泄漏计数 (0,0)，task.cancelling() 始终为 1（没有重复 cancel）。
- 通过监视 cancel_exchange 入口，确认第二次 /stop 确实落在收尾期间：自然时序下每 40–60 轮重叠 0–11 次，60 轮重复跑 3 次仍 0 泄漏；每次 DB 往返加 5ms 后重叠 21–31/40，0 泄漏。
- 每轮换新用户再跑一遍，泄漏同样为 0。其中两个变体本次重叠 0 次，被我自设的「必须发生重叠」断言判失败，属于场景覆盖提示，不是泄漏。

2）真实 uvicorn + 假上游，当前代码，FIONA_DEFAULT_POOL_WORKERS=4：
- 同交流双停、peer 双停、预留未返回（1 次或 2 次停止）各 60 轮：0 fails，立即再发起全 201，全库泄漏 (0,0)；被停交流的上游连接在发出 /stop 后 ≤0.005s 断开。
- 每次 DB 往返加 5ms 后跑 40 轮：重叠 28/30/24 次，recancel=0，0 泄漏，断开 ≤0.084s。
- 库一致性：296 个交流全部 stopped，296 条调用全部 discarded 且 estimated=1，budget_used 等于用量之和，reserved_tokens 全为 0，inflight 全为 NULL。

3）T3 相关回归：
- 8 个交流同时挂在假上游，上游并发连接数为 8，而默认池 max_workers=4。默认池只起了 1 个线程（给探针用），队列 0，往返 0.1–0.3ms；exchange_service/exchange_models 里 grep 不到 to_thread 或 run_in_executor。
- 8 个交流各双击停止：上游连接在 0.03s 内全部断开（DB 放大时 0.86s），8/8 结清，8/8 立即再发起为 201。
- SIGTERM 关机时有 3 个在途交流：进程 0.42s 退出，上游连接断开，交流记为 stopped（重启原因），调用 discarded，inflight 为 NULL。

4）在副本里跑仓库测试：交流相关 180 passed，后端全量 1461 passed。

复现文件与日志在 /private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/deepfix-review-r2/M3/：test_zz_m3_review.py、fake_upstream.py、launch_backend.py、drive_live.py、live_r1.log、live_cur2.log、live_cur_slow.log、r1_fresh.log、full.log。本轮启动的进

**回归：** 无。交流相关 180 条与后端全量 1461 条均通过。上游取消后 ≤0.1s 断开，交流不占默认线程池（8 个在途，默认池 4），关机时正常结算，预算与用量账目一致。

**可优化：**
- 结算失败没有兜底：stop_and_discard_reserved_calls 如果抛出非取消异常（例如 SQLite 忙等超过 SQLITE_BUSY_TIMEOUT=5s 后报 database is locked），settlement.result() 会把异常抛出去，预留仍然留着，用户仍会被锁到重启；/stop 也会因为 cancel_exchange 只忽略 CancelledError 而返回 500。这一条是读代码得出的，没有实测复现。建议对结算做有限次重试，或者失败时记日志并交给恢复流程处理。
- /stop 现在会一直等到 runner 结束，第 1 轮的写法有 2 秒上限。实际耗时受 SQLite 忙等时限约束，实测为毫秒级。另外 cancel_exchange 里的 suppress(asyncio.CancelledError) 也会吞掉 /stop 请求处理器自身被取消的信号，可以考虑区分开。
- 仓库里的 _stop_twice 用 ThreadPoolExecutor 发请求，没有 Barrier，也没有断言「第二次停止确实落在收尾期间」。我实测自然时序下重叠率很低（每 40 轮 0–11 次）。好在这三条用例在第 1 轮代码上确实会失败，并非空转。建议加 Barrier，并在测试里监视 cancel_exchange 断言发生过重叠，或放慢 DB 来放大窗口。
- _exchange_tasks 是按进程保存的。当前部署是单 worker，没有影响；将来如果改成多 worker，/stop 可能落到不持有任务的进程，只能等 runner 每 0.25s 轮询发现撤销，停止后立即再发起可能短暂 409。

## M4 部署手册 umask 077 影响后续更新步骤（T10，第 1 轮引入的回归），附带核对 O7 文档修正

**结论：通过**

**修复前复现：** 先从 scratchpad/codex-deepfix-r2/codex.log 第 742–752 行确认第 1 轮手册原文：`git rev-parse HEAD` 后面单独一行 `umask 077`，没有放进子 shell。然后用基线 656b7cf 的 DEPLOYMENT.md，在同一位置插入这一行，还原出第 1 轮文本。

模拟脚本 scratchpad/deepfix-review-r2/M4/sim.py 从文档的「日常发布」一节按原文抽出两个 bash 代码块，只做路径替换，不手抄命令，在同一个 shell 里顺序执行。git pull 是真实执行：临时源仓库 v1→v2，改写 app.py、page.tsx，新增文件、目录和可执行文件。pip/pytest/npm ci/npm run build 用桩脚本模拟，都作为子进程运行，会继承 shell 的 umask；其中 build 用 mkdir 生成 .next。

结果：bash 和 dash 下，备份块结束后外层 umask 都变成 0077，一直延续到更新块结束。检查项里 17 项异常：
- git pull 改写的 backend/app.py、frontend/app/page.tsx 是 0600；
- 新增的 newpkg、newroute 目录是 0700；
- 模拟的 pip、npm ci 产物，以及 .next/static、.next/server、BUILD_ID 都是 0600/0700。

也就是说原问题确实存在：服务账号 fiona 读不了新代码。这一步同时是检查脚本的正控，证明它在原文本上会失败（BAD 数=17）。

**现状证据：** 一、当前 docs/DEPLOYMENT.md（shasum d27251eb…）的实测

做法：用同一个 sim.py 按原文抽出「日常发布」的 2 个块和「回滚与恢复」的 4 个块（停服、检查点、回滚前快照、恢复）。恢复块里的快照名换成实际备份文件。systemctl、chown、sudo、install 打桩，其中 install 只去掉 -o/-g，保留 -m 0600。

在 /bin/bash 3.2、/bin/dash（Debian 的 /bin/sh）、/bin/zsh 下各跑一遍，结果相同：
- 外层 umask 在起始、备份块后、更新块后、回滚前快照子 shell 后、恢复块后都是 0022（zsh 下显示为 022）。
- 备份产物权限：fiona-*.db 0600，uploads-*.tar.gz 0600，pre-rollback-*.db 0600。
- git pull 改写或新增的文件是 0644，新增目录是 0755，新增可执行文件是 0755。
- 模拟的 pip、pytest 缓存、npm ci、.next（mkdir）产物是 0644/0755。
- 用 install -m 0600 恢复的库是 0600，PRAGMA integrity_check 输出 ok。
- 三种 shell 都是 BAD 数=0，exit 0。

备份内容有效：两个 .db 的 integrity_check 都是 ok，能读出测试数据；tar -tzvf 能看到 uploads/ 和其中的文件，而且保留了源文件原来的 0700/0600 权限，不受 umask 影响。

另外模拟了逐行粘贴到交互式 shell 的情况。把文档里的备份子 shell 原文喂给 bash --norc -i、zsh -f -i、dash -i：子 shell 前后 umask 都是 0022，备份是 0600，之后 touch 的文件是 0644、mkdir 的目录是 0755。

grep 确认手册命令块里的 umask 只有两处，都在子 shell 内：
- 第 317 行，位于第 316–320 行的子 shell 里；
- 第 435 行，单行写法 `( umask 077; sqlite3 … ".backup …pre-rollback-…" )`。

第 326 行已注明后续更新使用外层默认 umask。第 158、195 行的 UMask=0077 是基线原有的 systemd 配置。

二、其他涉及权限、属主的步骤，逐条核对
- 第 321–323 行的 chown 循环在子 shell 之外，与 umask 无关，可以照做。
- 第 442 行 `install -o fiona -g fiona -m 0600` 显式指定了权限，实测结果是 0600。
- 第 81 行 /var/backups/fiona 是 root 0755，里面放 0600 的备份，二者一致。
- 第 218 行「代码 root 只写、fiona 只读」：修复后新代码是 root 0644/0755，fiona 作为 other 可以读，一致。
- 第 443 行 `sudo -u fiona sqlite3` 读 fiona 0600 的库，可行。

三、O7 核对（只影响「可优化」，不影响本条结论）
1. 自检命令：从第 69 行原文抽出三条命令执行，全部 exit=0：ffmpeg 8.1.2，sqlite3 3.54.0，`python3 -c "import sqlite3; print(sqlite3.sqlite_version)"` 输出 3.53.3（≥3.35）。作为对照，本机 `command -v python` 返回 exit=1，原来写的 python 确实跑不通。
2. ARCHITECTURE 生图失败的描述：chat_service.py:638–641 的 ImageGenerationError 分支，以及 :580–584 的忙碌分支，都先发资源再发 error。在临时副本里（rsync，隔离数据库，占位 key）跑 tests/test_crisis_resource_paths.py，再加一个 429 探针，共 57 passed。探针连续发 31 次「我想死」，前 30 次返回 200，第 31 次返回 429 `{"error":"Rate limit exceeded: 30 per 1 minute"}`，不带资源。这与 ARCHITECTURE:84、CLAUDE.md:76、PLAN.md:117 写的「422/429 例外」一致，ARCHITECTURE:86 的「先资源

**回归：** 无。回滚一节原来的单个代码块被拆成了三块：检查点、回滚前快照、恢复。顺序仍然正确：先做检查点，再用 .backup 留快照，再 rm 掉 -wal/-shm，最后 install 恢复。恢复块照旧无条件删除 -wal/-shm，也仍用 install -m 0600 写入。在三种 shell 下按文档顺序实跑，integrity_check 都是 ok，外层 umask 也没有变化。

**可优化：**
- README.md:108 写着 FIONA_ALLOWED_DEV_ORIGINS「可带端口」，这不对。Next 16.3.3 的 blockCrossSiteDEV 只拿 Origin 里的 hostname 去和列表逐项比，要么完全相等，要么按点分段做通配匹配。实测填 `192.168.3.45:3000` 会被拦成 403，只有填纯主机名 `192.168.3.45` 才放行。建议删掉「可带端口」，改成「只填主机名或 IP，也可用 *.example.local 这类通配，不带协议和端口」。03-report.md 的 O7 一行里也有同样的说法。
- README.md:136 写的是「文字、工具、图片及失败路径都会附求助资源」，没提进入路由前的 422 校验和 429 限流这两个例外。ARCHITECTURE:84、CLAUDE.md:76、PLAN.md:117 都已写明，README 是唯一还说得过满的一处。
- DEPLOYMENT.md:326 默认运维 shell 的 umask 是 022。如果服务器按 CIS 等规范加固过，root 默认 umask 是 027 或 077，那么更新步骤产出的文件照样是 root 0640/0600，fiona 读不了。这个风险基线就有，不是本次引入的。可以在更新块开头加一句检查 `umask` 输出 0022，或者把更新命令包在 `( umask 022; … )` 里。
- DEPLOYMENT.md:131 只在首次安装时把 .next/cache 设成 fiona 0700。Next 16 的 build 在清理 distDir 时会保留 cache/dev/lock/trace（build/index.js:623-624），所以 cache 目录本身还是 fiona 的；但日常发布里 root 执行 npm run build 时在其中新建的子目录归 root，是 0755，fiona 能读不能写。这是基线就有的问题。建议在日常发布和代码回滚的 build 之后补一行 `chown -R fiona:fiona /opt/fiona/frontend/.next/cache`。
- DEPLOYMENT.md:425-430 拆块以后，检查残留 -wal/-shm 的 `ls -l` 被放进了「若要保全旧库未检查点的数据」这个有条件执行的块里。只打算恢复到快照、跳过检查点的运维可能连这一步检查也一起跳过。安全性不受影响，因为恢复块照旧会 rm -f；但可以把 ls 挪回不带条件的位置。
- DEPLOYMENT.md:310 写的是「由有权读取备份目录的运维账号执行」，但这组命令里有 systemctl stop、chown，还要往 root 0755 的 /var/backups/fiona 写文件，实际上需要 root 或 sudo。这是基线原有的措辞，可以改得更准确。

## M5 繁简归一缺字，覆盖性测试测不出漏字（T4）

**结论：不通过**

**修复前复现：** 用第 1 轮复核时留下的第 1 轮代码快照（scratchpad/deepfix-review/concurrency/be，其中 safety.py 与当前逐字节相同，traditional_chinese.py 是第 1 轮版本，sha 83cb47c4）复现了原问题。
- 11 个字 讓傘繩遠葯喫瞭纔弔妳牠 全部原样不变；計畫/计画/计畫/計画 都不会变成「计划」。
- 本条列出的 8 句全部判错（8/8 BAD）：
  - 吃了一整瓶安眠葯 → None（应为 high）
  - 剛吞了好多葯 → None（应为 possible）
  - 喫了一整瓶安眠藥 → possible（应为 high）
  - 讓我去死吧哈哈哈、他說想跳樓，我想跳傘散心、我想瞭解自殺的預防方法 → 都是 high（应为 possible）
  - 計畫下週跳樓 → possible（应为 high）
  - 我想死妳 → high（应为 None）
- 覆盖性测试的漏洞也复现了：第 1 轮快照的映射表里根本没有「让」，但它自带的 test_traditional_crisis.py 结果是 67 passed。原因是旧测试只扫模块级正则元组，而且以映射表本身作为期望，缺的字直接被跳过。
- 反证：把新测试文件放到第 1 轮快照上跑，结果 26 failed / 66 passed。

**现状证据：** 所有实验都在副本 scratchpad/deepfix-review-r2/M5/backend 里做，用 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python 运行。副本已排除 .env*、*.db、uploads，拷进来的 db.bak 已删。环境变量：PYTHON_DOTENV_DISABLED=1，FIONA_DB_PATH 与 FIONA_UPLOADS_DIR 指向临时路径，DEV_MODE=1，JWT_SECRET 为测试值，两个 API KEY 都是 placeholder。收尾时比对过哈希：副本里的 safety.py、traditional_chinese.py、test_traditional_crisis.py、chat_service.py、routers/chat.py 与仓库一致，审查期间目标文件没有被改动。

1）逐字与词级归一：`probe_listed.py` 输出显示 讓→让、傘→伞、繩→绳、遠→远、葯→药、喫→吃、瞭→了、纔→才、弔→吊、妳→你、牠→它；計畫、计画、计畫、計画 四种写法都变成「计划」。

2）本条列出的 8 句全部符合预期（8/8 OK，bad 0）：
- 吃了一整瓶安眠葯 high
- 剛吞了好多葯 possible
- 喫了一整瓶安眠藥 high
- 讓我去死吧哈哈哈 possible
- 他說想跳樓，我想跳傘散心 possible
- 我想瞭解自殺的預防方法 possible
- 計畫下週跳樓 high
- 我想死妳 None

3）覆盖性测试：test_crisis_rule_character_variants_normalize_back_to_rule_characters 用 `ast.walk` 收集 safety.py 全部字符串常量里的汉字（296 个，其中规则区 218 个），并断言内联正则里才有的 {让,伞,绳,远} 已被收集到。期望清单 EXPECTED_VARIANTS 是写死在测试里的字面量，不从映射表导入。

正控：在临时副本里分别从映射表删掉「讓」、删掉「葯」（药 的变体由 藥葯 改为 藥）、删掉「妳」。三次该测试都失败，报错分别是 AssertionError ('让','讓')、('药','葯')、('你','妳')。整个测试文件的结果依次是 3 failed、4 failed、3 failed；未改动的副本是 92 passed。

4）只用于分类、不改原文：grep 结果显示 normalize_traditional 只在 safety.py:80 被调用，assess_crisis 只返回判级。chat.py:102、chat_service.py:505/1019 传给模型和存库的都是原始 req.message / ctx.message。test_traditional_crisis_chat_persists_and_sends_original 通过，送给模型的和存进库的都是繁体原文。

5）自编 47 对繁/简对照句（均为新写，含 high 18 对、possible 10 对、None 19 对），繁简判级不一致 0 对，与预期不符 0 对。覆盖的字：葯、喫、讓、繩、傘、遠、瞭、纔、弔、妳、牠、計畫、計劃、戶、裡、幹、與。

6）用 OpenCC 的 STCharacters/TSCharacters/TWVariantsRev/HKVariantsRev 交叉比对 218 个规则汉字：常见繁体写法全部能归一。剩下没归一的只有日文新字体（薬、譲、縄、気等）和罕用字（彆、衕、傢、乾、緻）。

7）后端全量 pytest 在副本上 1461 passed。

不通过的唯一理由是第 8 点：本条新增的词级替换引入了回归，详见 regressions 字段。本条要求的其他核验点全部通过。

**回归：** 有一处回归，由本条新增的词级替换直接引入（backend/utils/traditional_chinese.py:122）。代码 `_WORD_REPLACEMENTS = {"计畫": "计划", "计画": "计划"}` 对全文做子串替换，会把「设计画面」「统计画面」「設計畫面」里跨词的「计画/計畫」改写成「计划」（如 设计画面 → 设计划面），从而命中 safety.py 的 `(?:想|要|打算|准备|计划|考虑).{0,4}(?:自杀|…)` 和 `(?:…|计划|考虑).{0,8}(?:跳楼|上吊|跳河|跳江|跳海|跳下去|…)` 两条 high 规则。这一步对简体输入同样生效，而简体用户本来完全不受繁体归一影响。

判级对比（同一段 probe_word.py 分别在基线 656b7cf、第 1 轮快照、当前代码上运行）：

| 句子 | 基线 | 第 1 轮 | 当前 |
|---|---|---|---|
| 游戏设计画面里加一段跳海的动画 | None | None | high |
| 我在做设计画面，主角最后跳河 | None | None | high |
| 这部片的设计画面有自杀镜头 | possible | possible | high |
| 统计画面显示上吊人数 | possible | possible | high |
| 遊戲設計畫面裡加一段跳海的動畫 | None | None | high |
| 電影設計畫面有自殺鏡頭 | None | possible | high |

端到端复现：在副本里用 TestClient 发送 POST /chat，mode="image"，消息「帮我画一张游戏设计画面，主角正在跳海」，generate_image 打桩。
- 当前代码：判为 high，发出 crisis:true，generate_image 调用 0 次，没有图，改走危机支持话术。
- 同一副本只把 _WORD_REPLACEMENTS 清空：判为 None，generate_image 调用 1 次，出图正常。

后果只是误报，不会漏报，但同属第 1 轮已列为必须修复的那一类错误（我想死妳、讓我去死吧哈哈哈 被误判为 high）。而且它影响的是简体主流用户，会让生图模式的正常请求直接失效。

修起来很小，建议二选一：
- 替换时加后顾排除，例如 `re.sub(r"(?<![设設统統会會估伙])计[画畫]", "计划", s)`；
- 或者只在确属「计划」义时替换。

同时补参数化用例：上表句子的判级应与去掉词级表时一致，且生图模式下「帮我画一张游戏设计画面，主角正在跳海」应正常出图。

**可优化：**
- 覆盖性测试收集了 safety.py 的全部汉字，却只用来做两条弱断言：{让,伞,绳,远} ⊆ 收集结果，以及交集 ≥75。它没有强制「每个有常见繁体写法的规则字都要出现在 EXPECTED_VARIANTS 里」。实测：在副本里给 assess_crisis 新加一条内联规则 r"想离开这个世界"，覆盖性测试仍然 passed，而「我想離開這個世界」判为 None，简体判为 high。建议在测试里放一份写死的「规则字 → 繁体」表（或者一份显式的「无繁体写法」白名单），要求两者合起来等于收集到的规则字集，这样今后新增规则字漏配时测试会失败。
- EXPECTED_VARIANTS 与生产映射表逐项、逐序相同，形式上是独立字面量，实际是复制粘贴。今后如果两边一起改错，测试发现不了。可以考虑另附少量来自 OpenCC 的抽样作为外部对照（只在测试里写死，不引入依赖）。
- OpenCC 里还有少数规则字的变体没有归一：日文新字体 薬、譲、縄、気、軽、対、実，港式或旧字形 絶、眞。例如「我絶對不想死」里的 絶 没有归一，否定语境剥不掉，会被判为 high，而简体「我绝对不想死」是 possible。影响面小，可按需补。
- 词汇层面的缺口与繁体归一无关，基线本来就有：「活著沒甚麼意義」「活着没甚么意义」判 None；「我把整瓶药都吞了」「我吊死自己算了」简体同样判 None。属于 safety 规则的覆盖问题，可另开单处理。

