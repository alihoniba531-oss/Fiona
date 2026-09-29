# 独立复核 第 1 轮（2026-09-29）

方式：4 个全新上下文复核员（危机与计费 / 并发与交流 / 前端与隐私 / 范围与文档），输入仅限 02-spec.md、05-fix-round1.md、相对基线 656b7cf 的 diff 与截图；每位复核员的问题再交独立核实员尝试推翻。

**结论：不通过**——5 条经核实的必须修复项（另有若干可优化项），返修指令见 `05-fix-round2.md`。

规格作者机械验证（复核前）：后端 1391 passed、逐文件 55/55、新测试在基线全部失败、前端 tsc/lint/build、真实数据哈希不变、生产构建界面实测 18/18、线程池饥饿与滴流的独立复现均已修复、繁体盲测 16/16。

## 危机与计费

| 条目 | 结论 | 证据摘要 |
|---|---|---|
| T4-1 匹配前繁转简归一，只用于分类，不改存库、送模型、显示的原文 | 通过 | safety.py:80 `normalized = normalize_traditional(re.sub(r"\s+", "", text or "").lower().replace("’", "'"))`；grep 确认 normalize_traditional 只在 safety.py 里被导入。自写 pytest test_db_note_once_and_original_kept（放在 scratchpad/rt 目… |
| T4-2 内置映射表不引入依赖，至少覆盖 safety.py 全部规则汉字和语料汉字的常见繁体、异体 | 部分通过 | 规格点名的 36 个繁体/异体全部能映射（test_specified_traditional_variants_are_mapped 通过，我逐字核对过）。但用 uv 缓存里的 OpenCC STCharacters/TSCharacters 与 safety.py 规则汉字交叉比对后，以下字形没有归一：讓(让)、傘(伞)、繩(绳)、遠(远)，这四个字出现在 safety.py:97-101 的内联规则里；另有异体 葯(药)、喫(吃)… |
| T4-3 覆盖性检查测试 | 部分通过 | tests/test_traditional_crisis.py:61-80 只取 6 组模块级正则元组，得到 210 个字；safety.py:97-101 两条内联规则里的 让/伞/绳/远/槽/舞/高/吧 共 8 个字没被扫到（我实算为 210 对 218）。另外测试以映射表自身作为期望（`SIMPLIFIED_TO_TRADITIONAL_VARIANTS.get(character, "")`），表里没有的字会被直接跳过，所以测… |
| T4-4 规格三组繁体语料（15 条 high、6 条 possible、7 条 None） | 通过 | test_traditional_crisis.py 全部通过。正控：用 git archive 取出基线 656b7cf 的 backend，只拷入新测试和 traditional_chinese.py，运行 test_traditional_crisis.py + test_crisis_resource_paths.py，结果 54 failed / 69 passed，说明这些测试在基线上确实会失败。… |
| T4-5 test_beta_safety.py 的基线夹具以及日常/危机语料护栏继续通过 | 通过 | 单独跑 test_crisis_resource_paths/test_traditional_crisis/test_beta_safety/test_beta_billing：410 passed。按规则 3 设好隔离环境变量后跑后端全量 pytest：1391 passed。… |
| T4 自编语料（71 句，均未照抄规格） | 部分通过 | probe_crisis.py 有 47 对繁/简对照句，其中 38 对两边判级一致，9 对不一致：計畫下週跳樓、喫…安眠藥、…安眠葯、剛吞了好多葯、活著沒甚麼意義、讓我去死吧哈哈哈、跳傘、跳繩、我想瞭解自殺的預防方法。probe2.py 另有 24 句，除两处外与预期一致：「我想死妳」得到 high（简体「我想死你」为 None）；「我根本不想死，只是好累」得到 possible，与简体一致，属于我预期写错，不算缺陷。日常句（熱死了、… |
| T5 不变量：high/possible 在每条服务端可控的结束路径上恰好收到一次 CRISIS_RESOURCE_NO | 通过 | 逐条核对了路由和服务层。路由层：校验失败 chat.py:104-128，预扣异常 133-138，余额不足 139-149，build_context 抛 ResourceNotFound 或其他异常 153-177。服务层：run_chat 的 high 分支 1021-1039；图片模式、修图提示、显式生图、待补图片、改图替换意图、镜子、看图、待补、意图、普通对话各分支；异常出口 1125-1138。stream_* 的出错、空回… |
| T5 high 首事件为 {"crisis": true}，照常计费不拦截；possible 不发 crisis | 通过 | crisis 事件只在 chat_service.py:1021-1022 和 chat.py:64-65、141 出现，三处都限定 high。探针逐条断言：possible 路径中 crisis 事件数为 0，high 路径中 events[0]=={"crisis": True}。… |
| T5 余额不足：high 保持现状；possible 先发资源文本再发余额错误，不调模型、不扣费 | 通过 | chat.py:139-149。探针 test_traditional_zero_balance 实际输出：「活著沒意思」得到 [{'text': NOTE}, {'error': '草莓不足…'}]，余额仍为 0；「我想自殺」得到 [{'crisis': True}, {'text': NOTE}, {'done': True}]。截图 02-possible-zero.png 前端把资源和「错误：草莓不足」合并显示，与 page.t… |
| T5 错误路径先资源后 error，退款语义不变；预检 HTTPException 和 reserve 异常也覆盖 | 通过 | _crisis_error_stream 的事件顺序是 text 然后 error。build_context 失败时先 _refund_before_stream；退款本身失败时，非危机仍按基线抛出，危机只打日志并照样送资源，资金损失与基线相同。探针 test_possible_bad_image_precheck 输出 NOTE 后接「只支持 PNG…」错误，余额退回。test_possible_tool_raises、test_p… |
| T5 把 assess_crisis 移到请求级校验之前 | 通过 | chat.py:102 在所有 400 校验之前判级，校验包在 try/except HTTPException 中，危机时返回 SSE。test_crisis_request_validation_still_streams_resources 覆盖 6 种非法组合，high 和 possible 都覆盖，全部通过。… |
| T5 FastAPI 进入路由前的 422 不在范围内，报告须注明 | 部分通过 | 03-report.md:58 已注明 422 和客户端主动断开。但 @limiter.limit("30/minute") 的 429 同样在处理函数之前返回：探针 test_rate_limited_crisis 第 31 次发「我想死」得到 status 429 {"error":"Rate limit exceeded: 30 per 1 minute"}，没有资源。报告和文档都没把它列为例外，CLAUDE.md 却写着「服务端… |
| T5 新增参数化测试覆盖各路径（high/possible、资源恰好一次、crisis 只在 high、计费/退款） | 通过 | test_crisis_resource_paths.py 覆盖文字、上游错、空回复、零余额、预检 4 类、校验 6 类、看图 3 类、生图/改图的成功/失败/忙、high 图片模式、工具/待补/镜子、run_chat 失败 2 类，并用 _assert_resource_once 断言次数和 crisis 事件。「活着没意思」「晚安，永别了」零余额用例都在其中。这些测试在基线上失败（54 failed）。缺口：测试不检查库内文本，这一… |
| T5 存库文本不重复附资源 | 通过 | 探针里文字回复、自然语言生图成功、卡片工具、修图提示、镜子空回复这几条路径的 assistant 行都断言 NOTE 计数为 1，全部通过。生图落库失败路径靠 chat_service.py:97 的 endswith 守卫，SSE 仍只有 1 次。另发现生图失败、工具异常等路径的资源根本不入库（见可优化项）。… |
| T4/T5 在 docs/ARCHITECTURE.md、CLAUDE.md、PLAN.md 中的描述与代码一致 | 部分通过 | ARCHITECTURE.md:73、:84，CLAUDE.md:76，PLAN.md:83/100/117，README.md:136 对 possible 行为、零余额顺序、只在分类时做繁简归一的描述都与代码一致。有两处不一致：ARCHITECTURE.md:86 仍写「失败只发错误」，而 possible 级生图失败会先发资源；关于「服务端能控制的错误路径」的表述没有排除 429 限流。… |
| 验收标准 1/5（全量 pytest、真实数据哈希不变） | 通过 | 全量：1391 passed, 12 warnings in 36.48s。复核前后执行 `ls uploads \| sort \| shasum; shasum *.db`，diff 为空（HASH_SAME）；仓库未跟踪文件仍为 26 个，没有新增。… |

- **[必须修复｜核实 CONFIRMED]** 繁简表缺少 safety.py 规则汉字的标准繁体和常见异体（讓傘繩遠葯喫瞭），危机句被降级甚至判成 None（`backend/utils/traditional_chinese.py:11`）
  - 核实意见：已亲自复现。backend/utils/traditional_chinese.py:11-102 的映射表里确实没有 让/伞/绳/远 的条目；药 只收了「藥」，没有「葯」；也没有 吃→喫、了→瞭。safety.py:97「让我去死吧?哈哈哈+」和 :101「我.{0,2}想跳(?![槽伞绳远高舞])」这两条内联正则在基线里就有，属于 assess_crisis 的规则，规格 T4 要求「表至少覆盖 safety.py 所有规则……汉字的常见繁体与异体写法」。本机 OpenCC 词典可以印证这些都是常见写法：STCharacters 有 让→讓、伞→傘、绳→繩、远→遠、药→藥 葯、吃→喫、了→瞭；OpenCC 自己的 TSCharacters 也把 讓傘繩遠葯喫 转回简体，说明它们不是生僻写法。复现输出：『吃了一整瓶安眠葯』判 None，简体判 high；『剛吞了好多葯』判 None，简体…
- **[可优化｜核实 CONFIRMED]** 「覆盖性检查」测试漏扫 assess_crisis 的内联规则，而且以映射表本身为准，测不出漏字（`backend/tests/test_traditional_crisis.py:63`）
  - 核实意见：事实属实。tests/test_traditional_crisis.py:63-80 只收集了模块级正则里的汉字。我实测得到 210 个，safety.py 规则区总共 218 个，漏掉的正好是内联正则里的 伞吧槽绳舞让远高。但这个遗漏本身没有实际后果：规格 T4 对覆盖性检查的原话是「只要映射表的反查里有对应繁体，就必须能归一回该汉字」，也就是规格自己规定以映射表为准。按这个定义，就算把内联规则纳入扫描，让 在表里没有条目，照样会被跳过，讓傘繩遠 的缺失还是发现不了。所以漏字真正的原因是规格设计的判定依据本身较弱，不是扫描面漏了 8 个字。测试以表为准，现在只能抓出「同一个异体挂在两个简体下」这类冲突，确实很弱。不过它符合规格的字面要求，改成独立期望清单属于规格之外的加强。建议并入 #0 的返修一起做：#0 已经要求补繁简对照句的参数化用例，足以防止同类回归。不列为必须修复。…
- **[可优化｜核实 PLAUSIBLE]** 词级写法「甚麼」「計畫」没有归一，港台常见写法的危机句降级或判成 None（`backend/safety.py:80`）
  - 核实意见：复现属实：『活著沒甚麼意義』判 None；『計畫下週跳樓』判 possible，简体『计划下周跳楼』判 high；『我計畫下週跳樓』仍判 high。但要拆成两部分看。(1)「甚麼」不是繁体字形问题，是词汇变体：OpenCC 的 STPhrases 把「甚么」当作正常简体词（甚么→甚麼），TSPhrases 也不会把 甚麼 转成 什么。简体用户写『活着没甚么意义』，实测同样判 None，『活着没啥意义』也是 None。这是 safety 规则本身的词汇覆盖缺口，和 T4 的繁体支持无关，不能算繁体归一的缺陷。(2)「計畫」确实是繁体特有的词级写法，OpenCC TSPhrases 有 計畫→计划，但规格 T4 要求的是按字的「常见繁体与异体写法」映射表，畫 按字只能归到「画」，不在规格明确的验收范围内。而且影响只是无主语句由 high 降为 possible，按 T5 这类句子仍然恰好收到一…
- **[可优化｜核实 CONFIRMED]** 台湾写法「妳」「牠」没有归一，「我想死妳了」被误判为 high 危机（`backend/utils/traditional_chinese.py:11`）
  - 核实意见：已复现：『我想死妳』『我想死牠了』判 high，『我想死你』『我想死它了』判 None。映射表确实没有 妳、牠。这个问题在产品上确实常见：persona.py 里 Fiona 用「她」自称，台湾用户对女性角色写「妳」很普遍。但它不构成违反规格：(1) 不是回归，基线同样没有繁简归一，『我想死妳』在基线也命中 `想死(?![你他她它])`，判 high；(2) OpenCC 里没有 妳 这个字的任何条目，它被当作独立用字；牠 只出现在 STCharacters 的次选（它→它 牠），OpenCC 自己的 TSCharacters 也不会把 牠 转回 它，拿「标准繁转简会不会转」来衡量，它们不算规格要求的「常见繁体」。(3) 后果只是误报：进入危机支持并附热线，照常计费，和普通轮次一样，不是漏报，也不是计费错误。建议与 #0 一并低成本补上（你→妳、它→牠），并在测试中补上『我想死妳了』应为 …
- **[可优化｜核实 CONFIRMED]** /chat 限流返回的 429 在处理函数之前，危机消息拿不到资源；报告和文档都没列为例外（`backend/routers/chat.py:98`）
  - 核实意见：已亲自复现：打开 limiter 后连续 31 次 POST「我想死」，最后一次返回 429 {"error":"Rate limit exceeded: 30 per 1 minute"}，没有资源。routers/chat.py:98 的 `@limiter.limit("30/minute")` 由 slowapi 装饰器在进入处理函数之前拦截，chat.py:102 的 assess_crisis 不会执行。另外 rate_limit.py 按客户端 IP 计数，同一 NAT 下的多个用户会共享额度，所以不一定是用户自己刷屏才触发。不过规格 T5 列举的路径里没有限流；规格已经明确把「进入路由之前就返回的 422」排除在外，装饰器层的 429 性质相同，所以不构成违反验收标准。真正的问题是文档说过头了：CLAUDE.md:76 和 ARCHITECTURE.md:84 写「服务端能…
- **[可优化｜核实 CONFIRMED]** ARCHITECTURE.md 的生图段仍写「失败只发错误」，与 possible 级先发资源的行为不一致（`docs/ARCHITECTURE.md:86`）
  - 核实意见：docs/ARCHITECTURE.md:86 仍是基线原文，写的是「失败只发错误，不保存成功消息、不扣草莓」，本次没有改。代码 chat_service.py:578-582（忙碌）和 :629-633（ImageGenerationError）在 possible 级会先 yield 资源文本再发 error。我的探针在 mode=image 下发「活着没意思」，得到的事件序列是 [status, {text: "\n\n"+NOTE}, {error: ...}]，与第 86 行的字面描述不符，也和同文件第 84 行的新描述互相矛盾。规格 T5 只要求同步「关于 possible 级行为的描述」，第 84 行已经更新，第 86 行是图片 SSE 的通用描述，所以属于文档一致性问题，不是验收失败。修改建议合理，列为可优化。…
- **[可优化｜核实 CONFIRMED]** 生图失败/忙碌和 run_chat 兜底异常路径的资源只在 SSE 里，不入库，刷新后历史里没有这条回复（`backend/services/chat_service.py:631`）
  - 核实意见：已亲自复现：possible 级（「活着没意思」）在 mode=image 下生图失败，SSE 里有一次资源文本，但入库历史只有 [('user','活着没意思')]。代码 chat_service.py:629-633 发出资源事件后直接发 error，没有调用 _save_response；run_chat 的 :1134-1137 同样没有保存。而 stream_normal 的 :946-951、stream_mirror 的 :674-679、stream_image 的 :747-752 出错时都会 _save_response，两类路径行为不一致属实。但规格 T5 的不变量是「恰好收到一次」，没有要求持久化，当轮确实送达了一次。基线的生图失败路径既不发资源也不入库，所以这不是回归。run_chat 的兜底异常有可能正是入库失败引起的，那里只能包 try/except 尽力保存…

## 并发与交流

| 条目 | 结论 | 证据摘要 |
|---|---|---|
| T2 request_public_url 墙钟总时限（含 DNS、连接、响应头、正文、重定向） | 通过 | 读 backend/utils/safe_http.py 全文：deadline=monotonic()+timeout；DNS 放进 _resolver_pool 并 result(timeout=remaining)；每跳 Timer 看门狗到期 shutdown socket（urllib3 2.7.0 connection.py:759 在 TLS 握手前已赋 self.sock，握手滴流也能被关）；正文 read1 分块并把 … |
| T3-1 交流上游不再占默认线程池（AsyncOpenAI）+ 验收场景（默认池 4、8 个交流各挂 5s、8 个滴流  | 通过 | exchange_models.py 新增 get_async_main_client/get_async_deepseek_client（base_url、key、超时与同步版一致）；exchange_service.generate_exchange_reply 直接 await AsyncOpenAI。我写了比仓库测试更贴近生产的端到端复核（scratchpad/.../review_t3_e2e.py）：在 SDK 客户端边界打… |
| T3-2 停止/撤销时取消在途上游，2 秒内断开，按 discarded 记 | 部分通过 | 单次停止的正常路径通过：test_stop_disconnects_async_upstream_and_releases_user_slot（真实 AsyncOpenAI→本地服务器）通过；我用真实 uvicorn(8052)+假上游(8053) 复现时 upstream_open_now=0，连接确实断开；撤销走 _generate_while_authorized 每 0.25s 轮询 is_exchange_running，te… |
| T3-3 同一用户在途上游调用 ≤ MAX_RUNNING_PER_USER，「开始→停止」循环不能突破 | 部分通过 | 上限本身成立：exchange_store._count_participation(running_only) 改为 (status='running' OR inflight_call_id IS NOT NULL)；test_rapid_start_stop_never_exceeds_one_inflight_call_per_owner 通过；我另跑 150 轮「开始→立即停止→再开始」（不等上游进入），0 次越限、0 行泄漏… |
| T3-4 execute_intent、hot.py、cards.py 慢调用改到专用有界池；run_slow 信号量取 | 通过 | grep 确认 chat_service.py:800/884 的 execute_intent、hot.py 全部 hot_topics/topic_expand/_classify_with_llm、cards.py card_detail 都改成 run_slow。utils/slow_pool.py：线程池 FIONA_SLOW_POOL_WORKERS 默认 16，每个事件循环一个 Semaphore(workers*2)。用… |
| T3-5 启动时显式设置默认线程池（环境变量可配，默认≥32） | 通过 | main.py lifespan 第一行 set_default_executor(ThreadPoolExecutor(max_workers=_default_pool_workers()))，FIONA_DEFAULT_POOL_WORKERS 默认 32、合法范围 1..256；backend/.env.example 写了 FIONA_DEFAULT_POOL_WORKERS=32 和 FIONA_SLOW_POOL_WORK… |
| T3-6 验收测试在基线上应当失败 | 通过 | 独立确认：同一端到端场景在 git archive 导出的基线副本上 first_event=19.507s，失败；当前代码为 0.015s。不过仓库里的验收测试保真度不足（见可优化条目）：把 chat_service 的 execute_intent 改回 asyncio.to_thread 后，全量 1391 个测试照样全部通过。… |
| 返修单 R3：生产路径无条件用异步客户端，删掉识别测试替身的分支 | 通过 | 在 services/exchange_service.py、exchange_models.py 里 grep 'run_slow\|to_thread\| is _\|is not _' 无匹配；get_deepseek_client 已删，仓库里也没有其他引用；测试改为打桩 get_async_main_client/get_async_deepseek_client。交流相关 7 个测试文件共 160 passed。… |
| finish_model_call 状态语义变化（not valid 时一律记 discarded）对预算/恢复的影响 | 通过 | exchange_store.py:692 只改了 agent_exchange_calls.status 的标签；预算列（input/output_tokens、budget_used、reserved_tokens、inflight_call_id）的 UPDATE 与状态无关，照旧执行。全仓 grep：'discarded'/'failed' 调用状态除这里外没有消费方（exchange_exports 用的是交流状态），reco… |
| recover_interrupted_exchanges 与新语义兼容 | 通过 | 关机时 shutdown_background_tasks 取消 runner，处理器先 stop_running_exchange(RESTART_REASON)，再 finish_model_call(result={})，按 input_limit+output_limit 估算后记 discarded，和重启时把 reserved 记为 interrupted 的计费口径一致；泄漏的 reserved/inflight 在重启时… |
| _generate_while_authorized 异常/取消时是否泄漏上游任务 | 通过 | create_task 与 try 之间没有 await，不会在中间被取消；finally 里对未完成的 upstream 先 cancel 再 await（suppress CancelledError），覆盖外层取消、wait_for 超时、is_exchange_running 抛异常三种情况。我的双停止复现里假上游 upstream_open_now=0，也证实上游连接都已断开。… |
| T9.1 dotenv 提前加载 + FIONA_ENV_FILE | 通过 | main.py:16-19 在 import database/auth/llm/media 之前执行 load_dotenv(FIONA_ENV_FILE 或 backend/.env, override=False)。test_selected_dotenv_is_loaded_before_database_and_uploads_import 用子进程+临时 dotenv 通过。我在副本里用绝对路径 FIONA_ENV_FILE… |
| T9.1 admin_env 与服务使用同一套解析规则 | 部分通过 | 默认路径（backend/.env）和绝对路径 FIONA_ENV_FILE 两边一致。但 admin_env 会 expanduser，并且文件缺失时报错；main.py 两样都不做。实测 HOME=临时目录、FIONA_ENV_FILE='~/iso.env'：服务 database.DB_PATH=.../be/fiona.db，管理脚本数据库=.../home/tilde.db（见必须修复第 2 条）。另外 test_early… |
| main.py 设置 PYTHON_DOTENV_DISABLED 的副作用 | 通过 | 全仓 load_dotenv 只出现在 auth.py、llm.py（两者本来就要被禁用）、main.py、admin_env.py（管理脚本是独立进程，不 import main）。服务进程唯一的子进程是 routers/voice.py 的 ffmpeg，与此无关。conftest 也全局设了 PYTHON_DOTENV_DISABLED=1，防止测试读到真实 .env；test_beta_admin_scripts 和 test_… |

- **[必须修复｜核实 CONFIRMED]** 并发/重复「停止」打断取消收尾，预留与 inflight_call_id 永不结清，用户（peer 时双方）被永久 409 锁定直到重启（`backend/services/exchange_service.py:238`）
  - 核实意见：引用核对属实：exchange_service.py:238-246 的取消处理器依次 await stop_running_exchange 和 finish_model_call，没有任何保护；cancel_exchange（277-283）只检查 task.done()，不看 task.cancelling()，所以会再次调用 task.cancel()。Python 3.14 下，第二次 cancel 会在处理器当前的 await 处抛出新的 CancelledError。_transition 对任意参与者的 stop 都会走到 cancel_exchange（routers/agent_exchanges.py:124），而 _stop 对已停止的交流不报错。exchange_store.py:368 新的计数口径会把 inflight_call_id 非空的已停止交流继续算作…
- **[可优化｜核实 CONFIRMED]** 服务进程解析 FIONA_ENV_FILE 的规则与 admin_env 不一致（不展开 ~、文件缺失时静默），服务与管理脚本会用到不同的数据库（`backend/main.py:16`）
  - 核实意见：引用属实：main.py:16-19 对 FIONA_ENV_FILE 既不 expanduser，文件缺失时也不报错，随后设置 PYTHON_DOTENV_DISABLED=1；admin_env.py:34-51 则会 expanduser().resolve()，文件缺失时抛 AdminConfigError。
我在副本里复现：HOME 指向 scratch，FIONA_ENV_FILE='~/iso.env'，密钥放在进程环境里。服务得到 DB=.../be/fiona.db，admin_env 得到 .../home/tilde.db，两边确实不一致；文件路径拼错时服务同样静默回退到默认库。
不过影响面比描述窄。我把密钥也放进该 dotenv 文件（这是常规配置）再试，服务在导入阶段直接报 OpenAIError Missing credentials，启动失败是显性的，不会静默…
- **[可优化｜核实 PLAUSIBLE]** reserve_model_call 已提交、尚未返回时被取消，call_id 仍为 None，处理器跳过结算，同样造成永久锁定（`backend/services/exchange_service.py:211`）
  - 核实意见：机制存在：aiosqlite 0.22.1 里，commit 在连接线程中执行，即使等待它的协程被取消，提交也照样完成。之后 __aexit__→close() 还要两次 await（先执行 _conn.close，再等 stop future）。如果 cancel 恰好落在这段时间，预留已经落库，而 runner 的 call_id 还是 None，处理器 242 行会跳过结算。
但在自然时序下几乎到不了这个窗口。cancel 只能在 stop 事务提交之后发出，而 stop 的 BEGIN IMMEDIATE 必须等 reserve 提交、释放写锁后才能拿到锁（SQLite 忙等要睡眠后才重试）。拿到锁后，stop 还要依次完成 _participant_row、_stop、_participant_row、_messages、commit、close，约 8-9 次线程往返，最后才调…
- **[可优化｜核实 CONFIRMED]** DNS 解析改用全局仅 4 线程的共享池，4 个挂起的解析会让所有用户的网页卡片/链接检测一起超时失败（`backend/utils/safe_http.py:33`）
  - 核实意见：引用属实：safe_http.py:33 的解析池是全局共享的，只有 4 个线程；:299 把每次解析都提交到这里。getaddrinfo 不能取消，调用方超时后 resolution.cancel() 只能取消还在排队的任务，取消不了正在跑的。
我独立复现（在副本里把 resolve_public_url 桩掉，让 slow-dns 睡 6s，本地 127.0.0.1:8062 起一个正常服务器）：同时挂起 4 个解析后，正常 URL 以 timeout=3 请求，结果是 PublicUrlTimeoutError「公网抓取超过总时限」，耗时 3.01s，此时 fiona-dns_0..3 四个线程都被占着；只挂起 3 个时，正常请求 0.01s 返回 200。
不过这不是回归。基线在调用线程里直接解析，挂起的 DNS 会占住默认池线程，连聊天主链路都会被拖住；现在的设计保护了聊天和慢调…
- **[可优化｜核实 CONFIRMED]** T3 验收测试绕过了真实接线：把 execute_intent 改回默认线程池，全量 1391 个测试仍全部通过（`backend/tests/test_exchange_isolation.py:93`）
  - 核实意见：引用属实：test_exchange_isolation.py:76 把整个 generate_exchange_reply 换成了桩；:93 在测试里直接调用 run_slow(fetch_card)，完全不经过 /chat 和 execute_intent。
我做了变异验证：在副本里用 sed 把 chat_service.py:800/884 的 await run_slow(execute_intent 改回 await asyncio.to_thread(execute_intent)，跑全量 pytest，1391 passed，没有任何测试发现。
我另写了一个端到端用例：默认池设为 4，把 recognize_intent 打桩成 fetch_card（query 指向滴流地址），8 个用户并发 POST /chat，然后另一位用户发普通聊天。当前代码上，8 个滴流全部进入，…

## 前端与隐私

| 条目 | 结论 | 证据摘要 |
|---|---|---|
| T1 生图抢先判定（宁可漏判不可误判） | 不通过 | 跑了 tests/test_image_intent_precision.py，规格和返修单列出的语料全部通过。另外自编了一套语料（脚本 scratchpad/deepfix-review/fe-privacy/t1_corpus.py），把当前实现和基线 656b7cf 的 explicit_image_intent 对比：49 句非命令里当前误判 34 句（69%），基线误判 42 句；其中以「动词+量词」开头的评论、抱怨、反问 3… |
| T6 私聊文本不出现在任何 URL（含验收标准 7） | 通过 | 在 frontend/ 和 backend/ 源码执行验收标准 7 的 rg，没有命中。前端所有 tts 相关请求只有 page.tsx:736 的 POST /tts/ticket（文本在请求体里）和 page.tsx:744 的 /tts/stream?ticket=。生产构建加无头 Chromium 实测一段 4 句的回复：收集页面发出的全部请求 URL 并做 URL 解码，含句子原文的 0 条；stream 请求形如 /api/… |
| T6 票据有效期、次数、跨用户、旧 text 参数 | 通过 | 对运行中的后端（8054，经 Next 3054 代理）实测：B 用 A 的票据得 404（朗读票据不存在或已失效），而且不消耗次数；不带 Cookie 得 401；?text= 得 422；?ticket=…&text=x 和 ?ticket=…&dev_user=… 都得 400；签发 61 秒后 A 本人使用得 404（朗读票据已过期）。voice.py:64 的计数逻辑是第 4 次使用后删除票据，test_tts_ticket_… |
| T6/R2 Range 探测与 Safari 正常播放 | 部分通过 | 后端层面成立：Playwright WebKit 26.6（macOS，AVFoundation 媒体栈）确实先发 Range: bytes=0-1，再发一次不带 Range 的请求，两次都在 4 次上限内，能出声。但回复有多句时队列只播第一句，原因是 200 分块、无 Content-Length 的响应在 WebKit 中始终 duration=Infinity、只触发 stalled、不触发 ended（15 秒内 ended=f… |
| T6 限流不比现在更严 | 通过 | POST /tts/ticket 限额 20/minute，每句一张票，与基线 /tts/stream 的 20/min 持平；/tts/stream 和 /tts/synthesize 去掉了 limiter。没有变严，但上游合成次数的上限反而变松了，见可优化问题 4。… |
| T6 前端队列：票据失败不中断、预取仍有效 | 通过 | 无头 Chromium 加生产构建，用 route 让第二句的换票返回 500，第一、三、四句正常。播放事件为：play 第一句 4617 → ended 6470 → play 第三句 6624 → play 第四句 8404 / ended 第三句 8404 → ended 第四句 9939。第二句被跳过，队列没有卡住。第一句播放期间就已发出第二句的换票，第三句播放期间已完成第四句的换票和 stream GET，预取生效。… |
| T6 停止朗读中止在途换票 | 不通过 | 用 route 把换票延迟 2.5 秒。第一条消息的两句还在换票时，在 5.1s 发第二条消息，handleSend 会调用 clearTtsQueue。在 7.05s 仍发出两条 GET /api/tts/stream?ticket=…，对应旧回复的两句，没有播放。clearTtsQueue（page.tsx:858）不会中止换票 fetch，mkTtsAudio 在换票返回后无条件设置 src 并 load（page.tsx:744… |
| T7 退出失败保留状态 | 通过 | 生产构建实测：/auth/logout 被 route 成 500 时，仍停在 /settings，localStorage 保持 carol_t7，显示「退出失败，会话仍可能有效。请重试。」；route.abort 时显示「网络错误，退出未完成。请重试。」，状态同样保留；恢复后点重试，跳到 /login?reason=logout，localStorage 清空，Cookie 清空。唯一例外：会话已在别处撤销时（401）会一直卡在「退… |
| T7 Cookie 有效而 localStorage 丢失时回填 | 通过 | 用 test-login 取得 Cookie，不写 localStorage，逐个直达页面：/、/settings、/match、/profile、/history、/history?user=someone_else、/plaza，最终 localStorage 都回填为 alice_t7，页面里都没有出现「默认用户」。主页截图显示会话已加载，余额 200。把 /api/profile 改成返回 500 后，/settings 只发 … |
| T7 /history /match /profile 直达页 reload 是否死循环或错误重载 | 通过 | 用 framenavigated 计数：/ 和 /settings 各 2 次，即一次加载，没有重载；/match 和 /profile 各 4 次，恰好重载 1 次；/history 不重载；/history?user=someone_else 做一次 replace，去掉 user 参数。6 秒内计数不再增长。嵌入页（embed=1）被 isDirectIdentityRoute 排除；sessionStorage 标记防止同一用户… |
| T7 生产构建不把「默认用户」当身份做账号操作 | 通过 | rg 显示白名单内的 page.tsx、settings、plaza 已不再使用「默认用户」。删号比对用 useAccountIdentity 取得的真实用户名，拿不到时输入框和按钮都禁用；清空记录按钮同样禁用；广场发布在没有用户名时禁用。白名单外的 profile、match、history 页仍以「默认用户」作初始显示，只用于显示、判断 isSelf 和导出文件名，不是账号操作，而且回填后会重载或重渲染成真实用户名。… |
| T8 dev 默认绑定回环与 allowedDevOrigins | 通过 | package.json 中 dev 为 next dev -H 127.0.0.1，dev:lan 为 next dev -H 0.0.0.0；next.config.ts 中 allowedDevOrigins 为 [127.0.0.1, localhost, 以及 FIONA_ALLOWED_DEV_ORIGINS 的值]，不再是 "*"。README 已写明 dev:lan 的风险。读了 Next 16 的 block-cros… |
| T8 后端回环校验是否只信 socket 对端 | 部分通过 | 代码按规格用 request.client.host 判断，test_dev_loopback.py 3 条测试通过。实测发现两点。第一，uvicorn 默认开启 proxy_headers，并信任来自 127.0.0.1 的 X-Forwarded-For：直连 8054 带 XFF=203.0.113.9 时，后端日志记为 203.0.113.9:0，结果 401，说明 client.host 由 XFF 改写。第二，前端全部请求经… |
| T8 WebSocket 与 /uploads 的 DEV 通道 | 通过 | rg 确认所有 WS 端点（/ws/peer、/tts/ws、tts_ws 复检）都经过 ws_authenticate，其中 dev_user 分支已加 is_loopback_client；main.py:173-175 的 /uploads DEV 旁路也加了回环判断。测试断言：远端对端访问 /uploads/nonexistent.jpg 得 401，WS dev_user 得 4401，回环对端得 4403（身份通过、房间拒绝… |
| T9.2 HEIC/AVIF 与视频 brand | 通过 | 用 sips 和 ffmpeg 生成真实文件，直接调用 _sniff_video_ext：real.heic（brand 为 heic,mif1,MiPr,miaf）得 None；real.avif（avif,mif1,miaf）得 None；real.mp4（isom,iso2,avc1,mp41）得 mp4；real.mov（qt  ）得 mov。未知 brand 被拒绝。广场 UI 上传伪 HEIC 返回 400，提示「暂不支持 … |
| T9.3 广场发布错误显示 | 通过 | 生产构建实测：上传 HEIC 后弹窗仍打开，role=alert 显示「暂不支持 HEIC/AVIF…」，文案「保留的文案photo.heic」还在；上传 6MB 的 PNG 显示后端 detail「文件太大」（413），弹窗和文案都保留；major brand 为 isom、兼容 brand 含 avif 的文件被拒，提示同上。handleSubmit 失败时不调用 handleClose，所以已选标签不会被清掉。截图在 scratc… |

- **[必须修复｜核实 CONFIRMED]** T1 生图抢先判定仍把「动词+量词」开头的陈述、抱怨、口语反问当成付费命令（`backend/intent_router.py:190`）
  - 核实意见：引用属实。backend/intent_router.py:152 定义了 _IMAGE_QUESTION_WORD，第 190-194 行的判定是：动词为画/绘制时有量词即成立；做/生成/制作时要求有图片名词，并且有量词或请求前缀。除此之外，只按疑问词和评价、感叹标记这张黑名单排除。我用独立脚本直接调用 explicit_image_intent（环境变量全部指向临时路径，未做模型调用），测了本条列出的 27 句陈述、抱怨、口语反问和关系从句，27 句全部返回 generate_image。例如「生成一张图片失败了」「画一只猫扣了我十颗草莓」「画一只猫不难」「做一张海报咋弄」「给我画个头像的朋友去年走了」。规格正例和 R1 追加正例共 19 句仍全部识别。接线已核实：services/chat_service.py:1041 在模式判定和 recognize_intent 之前调用 ex…
- **[必须修复｜核实 CONFIRMED]** R2 的「Safari 正常播放」未达成：WebKit 下分块流不触发 ended，朗读队列停在第一句（`backend/routers/voice.py:216`）
  - 核实意见：引用属实：backend/routers/voice.py:204-220 对任何请求（含 Range 请求）都返回 StreamingResponse 200，分块传输，不带 Content-Length；frontend/app/page.tsx:794 只靠 ended 或 error 推进队列，没有其他兜底。我在 3064/3065 端口独立复现：用 ffmpeg 生成 1.2 秒 mp3，由模拟服务按同样语义返回（忽略 Range，200 分块），让 Playwright WebKit（webkit-2359）按前端的 ended/error 逻辑顺序播放 3 句。服务端依次收到 range=bytes=0-1 和 range=None 两次请求；事件为 loadedmetadata dur=Infinity、playing、play-resolved，3.5 秒时 stalle…
- **[可优化｜核实 CONFIRMED]** 停止朗读不中止在途换票，停止后仍对旧句子发出 stream 请求并触发上游合成（`frontend/app/page.tsx:744`）
  - 核实意见：代码属实：frontend/app/page.tsx 的 mkTtsAudio 在 await response.json() 之后无条件设置 audio.src 并调用 load()，没有检查是否已被丢弃。clearTtsQueue 只对当前项和预取项调用 pause() 并把引用置空，没有 AbortController，也没有 removeAttribute('src')。所以停止后换票才返回的句子仍会发出 GET /tts/stream，后端开始流式合成；ready.then 里的 ttsAudioRef 守卫只阻止播放。但复核员说「基线停止后不会新发请求」是在比时机，不是比费用：基线 mkTtsAudio 用 new Audio(url) 且 preload=auto，创建当时（入队或预取时）就已发出 /tts/stream 请求，而且 clearTtsQueue 只 pause…
- **[可优化｜核实 CONFIRMED]** 播放接口去掉限流后每票可用 4 次，单 IP 的上游 TTS 合成上限从 40 次/分钟变为 80 次/分钟（`backend/routers/voice.py:204`）
  - 核实意见：对照基线 diff 属实：基线的 /tts/synthesize 和 /tts/stream 各有 @limiter.limit("20/minute")，现已删除；只有 /tts/ticket 保留 20/minute。TTS_MAX_TICKET_USES=4，_use_tts_ticket 每次使用都会重新调用 synthesize 或 synthesize_stream。limiter 的 key 是 _client_ip（X-Real-IP 或 XFF 最后一跳）。因此单 IP 每分钟的上游合成上限从 20+20=40 变为 20×4=80。tests/test_tts_private_tickets.py:99 test_tts_synthesize_shares_ticket_use_limit_with_stream 也证明同一张票据 3 次 synthesize 加 1 …
- **[可优化｜核实 REFUTED]** 经 Next rewrite 代理后后端看到的对端恒为 127.0.0.1，dev:lan 时回环校验不起作用；client.host 还会被 uvicorn 按 XFF 改写（`backend/auth_dep.py:22`）
  - 核实意见：事实部分属实，但不构成缺陷。(1) 经 Next rewrite 代理后，后端看到的 socket 对端必然是 127.0.0.1，这是 T8 方案本身的结构。T8 的后端纵深防御针对的是直接从局域网访问后端；对 dev:lan，规格只要求设显式脚本并在 README 写明风险。实现已照做：package.json 中 dev 为 next dev -H 127.0.0.1，dev:lan 单列；README.md:108 已写明该模式「可能让能访问它的人触及调试接口和内测数据，只在可信网络临时使用」，README.md:137 也提示不要经不可信代理转发开发站点。生产部署文档是 next start -H 127.0.0.1 配 DEV_MODE=0。(2) uvicorn 0.47 的 ProxyHeadersMiddleware 只在 socket 对端属于 trusted_host…
- **[可优化｜核实 CONFIRMED]** 会话已失效时（/auth/logout 返回 401）退出流程卡死，提示「会话仍可能有效」（`frontend/app/settings/page.tsx:79`）
  - 核实意见：代码属实。backend/routers/auth.py:99 的 /auth/logout 依赖 get_current_user。会话被撤销或过期时，backend/main.py 中间件的 authenticate_token 返回 None，于是返回 401 并 delete_cookie('fiona_token')。frontend/app/settings/page.tsx:79-82 对任何非 ok 响应都提示「退出失败，会话仍可能有效。请重试。」，不清 localStorage，重试仍是 401。基线在这一分支会清除身份并跳转，所以 401 分支的体验比基线差，提示也与事实相反。不过这完全符合 T7 字面「非 2xx 留在原页、不清本地状态」，而且后果有限：服务端会话已失效，Cookie 已被 401 响应删除；生产构建的 apiFetch 不发 X-Dev-User，残…

## 范围与文档

| 条目 | 结论 | 证据摘要 |
|---|---|---|
| §2 约束：不引入新依赖（requirements*、package.json 依赖、lock 不变；package.j | 通过 | `git diff 656b7cf -- 'backend/requirements*.txt' frontend/package-lock.json desktop \| wc -l` → 0；先用 `git ls-files` 证明 requirements.txt、requirements-dev.txt、frontend/package-lock.json、desktop/（26 个文件）都在跟踪中，所以空 diff 不是没扫到… |
| §2 约束：不做 schema 变更 | 通过 | `git diff 656b7cf -- backend \| grep -cE '^[+-].*(CREATE TABLE\|ALTER TABLE\|ADD COLUMN\|CREATE INDEX\|DROP )'` → 0。正控：同一正则在基线 database.py 上命中 42 次。exchange_store 新用到的 inflight_call_id 在基线建表语句里就有（基线 exchange_store.py 第 6… |
| §2.1 受限范围文件（database 仅 DB 路径、persona 仅时区、auth_dep/routers/au | 通过 | 逐个读了 diff：database.py 只改 DB_PATH 一行（加 resolve）；persona.py 只把 datetime.now()/date.today() 换成 beijing_now()；auth_dep 新增 is_loopback_client，三处 DEV 分支加回环判断；routers/auth.py 的 send-otp/test-login/verify-otp 加 request 参数和回环判断；m… |
| §2 约束：测试只用端口 0、不碰 3000/3001/8000/8001/8010 | 通过 | test_safe_http_deadline.py:50 `ThreadingHTTPServer(("127.0.0.1", 0), _Handler)`；其他新测试没有写死端口。新测试里直连 sqlite 的地方用的是 database.DB_PATH，它由 client fixture 指到 tmp_path。… |
| 返修第 1 轮白名单 | 通过 | 按 mtime 排序：05-fix-round1.md 写于 02:56:17，之后改动的只有 docs/ARCHITECTURE.md、docs/DEPLOYMENT.md、exchange_models.py、exchange_service.py、routers/voice.py、tests/test_exchange_models.py、tests/test_exchange_workflow.py、tests/test_tts… |
| 验收标准 1（全量 pytest > 1169，0 failed/0 error） | 通过 | `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider`（额外设了临时 FIONA_DB_PATH/UPLOADS、占位 KEY 和 PYTHON_DOTENV_DISABLED=1）→ `1391 passed, 12 warnings in 34.13s`，EXIT=0。… |
| 验收标准 2（逐文件 pytest 无 FAIL） | 通过 | 对 tests/test_*.py 逐个跑，55/55 个文件的末行都是 'N passed'，没有 failed/error/no tests ran，各文件相加共 1391 passed。10 个新测试文件的结果：beijing_time 1、crisis_resource_paths 56、dev_loopback 3、early_env_loading 1、exchange_isolation 4、image_intent_pr… |
| 验收标准 3（compileall） | 通过 | `PYTHONPYCACHEPREFIX=<scratch> .venv/bin/python -m compileall -q -x '\.venv' .` → compileall_exit=0（pycache 重定向到临时目录，没往仓库写字节码）。… |
| 验收标准 4（tsc / lint --max-warnings=38 / build） | 通过 | 在 `cp -cR` 出来的前端克隆里（已删 .next）执行：`npx tsc --noEmit` 退出 0，并用 `--listFiles` 确认 app/page.tsx、lib/auth.ts、settings、plaza、useAccountIdentity 这些改动文件都被扫到了；`npm run lint -- --max-warnings=38` 退出 0，结果 '28 problems (0 errors, 28 wa… |
| 验收标准 5（真实数据哈希前后一致） | 通过 | 测试前：uploads 的列表哈希 ccf9c152…，fiona.db 403a086c…，local-avatar.db e6c4397d…；全量和逐文件测试、前端构建之后三项哈希不变（diff 为空）。uploads 下有 476 个条目，列表不是空的。`find backend/uploads -mmin -60` 和 `find backend -maxdepth 1 -name '*.db*' -mmin -60` 都没有结… |
| 验收标准 6（diff --stat 与新增未跟踪文件全在白名单内） | 通过 | diff --stat 共 44 个文件，逐个对照 §2.1 都在白名单内（报告开头写 42 个，漏计了返修轮改的 test_exchange_models.py、test_exchange_workflow.py，返修一节已补上）。新增未跟踪文件：10 个 backend/tests/test_*.py、3 个 backend/utils/ 新模块、本目录 03-report.md，另有规格作者自己的 02-spec.md、05-fi… |
| 验收标准 7（私聊文本不进 URL） | 通过 | `rg -n "tts/stream\?\$\{\|text=\$\{\|params\.set\(\"text\"\|text: text" frontend backend -g '!node_modules' -g '!.next' -g '!.venv'` → rg_exit=1，无命中。正控：同一正则在基线 page.tsx 上命中第 727 行 `text: text.slice(0, 300),`。另外全面搜了前端拼查询串… |
| 验收标准 8（T1–T9 新增测试与语料存在并通过） | 通过 | 写了脚本从 02-spec.md 和 05-fix-round1.md 里解析语料行，用 AST 与测试文件的参数列表逐条比对：T1 识别 13/13、T1 不识别 18/18、T4 high 15/15、possible 6/6、None 7/7、R1 识别 5/5、R1 不识别 8/8，缺失 0。T2/T3/T5/T6(R2)/T8/T9.1/T9.2/T9.4 的测试函数都在，逐文件运行全部通过。报告按任务列出了函数名；T6 那一… |
| 验收标准 9（frontend/AGENTS.md 与基线一致） | 通过 | frontend/AGENTS.md 在跟踪中；基线版本和当前文件的 shasum 都是 b402af8a…；mtime 仍是 Sep 25 04:34，没被 next dev 改写过。… |
| T9.4 北京时间只替换面向用户的时间，内部计时未改 | 通过 | diff 里删掉的 7 处 datetime.now()/date.today() 都是面向用户的：card_detail、system_tools、topic_expand×2、travel_plan、web_search、persona×2。mode_switcher.py、database.py 的过期计时、intent_router 的 UTC 过期判断、model_router、peer.py 都没改（diff --stat … |
| T10 部署前置条件（ffmpeg / sqlite3 / SQLite≥3.35 与自检命令） | 部分通过 | DEPLOYMENT.md:60-62 补了三项，第 69 行给了 `apt-get install -y ffmpeg sqlite3` 和自检命令。代码里确实有依赖：voice.py:118 用到 ffmpeg，database.py:666/682/1621/1636 用到 RETURNING。本机实跑：`ffmpeg -version` 正常，`sqlite3 --version` 得 3.54.0；但 `python -c "… |
| T10 备份产物权限 600/640 | 部分通过 | 备份产物本身达标：照文档设 umask 077 后，sqlite3 .backup 生成的文件和 tar.gz 实测都是 -rw-------。但 umask 077 会一直留在运维的 shell 里，紧接着的「更新、验证和重启」一段里 git pull、pip、npm ci、build 新写的文件也都会变成 0600 且属 root，而服务以 User=fiona 运行，读不了这些文件。已复现，见必须修复项。… |
| T10 README 局域网调试说明 | 通过 | README.md:108 写了默认只监听本机、用 dev:lan 显式开放、FIONA_ALLOWED_DEV_ORIGINS，以及相应风险。在前端克隆里实测：`npm run dev -- -p 8055` 的 lsof 结果是 `TCP 127.0.0.1:8055 (LISTEN)`，127.0.0.1 和 localhost 访问都返回 200，用局域网 IP 192.168.3.45 访问连接被拒（curl exit 7）；… |
| T10 backend/.env.example 新变量 | 通过 | 在新增代码里 grep getenv/environ：本任务新增的后端变量是 FIONA_DEFAULT_POOL_WORKERS（默认 32）、FIONA_SLOW_POOL_WORKERS（默认 16）、FIONA_ENV_FILE。前两个在 .env.example:51-55 写了默认值和说明，与 main.py:_default_pool_workers、slow_pool.DEFAULT_SLOW_POOL_WORKERS … |
| T10 其他文档只改相关句子 | 通过 | 逐段读了 CLAUDE.md、PLAN.md、ARCHITECTURE.md、DEPLOYMENT.md、README.md 的 diff，都对应 T5/T4/T6/T3/T8/T9.1 的行为变化。CLAUDE.md 里「可能相关的轮次……文字回复末尾附资源」一句已按 T5 改写。DEPLOYMENT.md:352 管理脚本默认配置文件的说明，已与 admin_env.py 去掉 /etc/fiona/fiona.env 候选的改动同… |

- **[必须修复｜核实 CONFIRMED]** 发布手册的 umask 077 会延续到后面的更新步骤，照做后服务读不了新代码（`docs/DEPLOYMENT.md:316`）
  - 核实意见：引用属实。docs/DEPLOYMENT.md:316 这行光秃秃的 `umask 077` 是本任务新加的（相对基线 656b7cf 的 diff 里就是 `+umask 077`），没有放进子 shell，也没有事后恢复。第 326 行「然后更新、验证和重启」之后的第二个代码块在同一个 /opt/fiona 下接着执行 git pull、pip install、npm ci、npm run build，最后 restart。/opt/fiona 由 root 创建，模式 0755（第 79 行）；两个 systemd 单元都是 User=fiona（第 150、187 行）。我用同一个复现脚本在自己的临时目录重跑了一遍，结果：发布前 umask 0022，app.py 是 -rw-r--r--；按手册顺序执行后 umask 变成 0077，git pull 改写的 app.py 和新增…
- **[可优化｜核实 CONFIRMED]** SQLite 版本自检命令用 python，在文档针对的 Debian/Ubuntu 和本机都找不到这个命令（`docs/DEPLOYMENT.md:69`）
  - 核实意见：docs/DEPLOYMENT.md:69 的原文确实是 `python -c "import sqlite3; print(sqlite3.sqlite_version)"`。同一手册安装时用的是 `python3 -m venv`（第 85 行）。本机 `command -v python` 没有输出（exit=1），`python3` 输出 3.53.3。Debian 12、Ubuntu 22.04/24.04 默认也不装 python-is-python3，照抄会得到 command not found。不过这条命令是规格 T10 原文给的，实施方照规格写，而且运维换成 python3 很容易，所以只算可优化：改成 python3，或者改用 venv 里的 `.venv/bin/python`。补充一点：venv 里的解释器和基础 python3 链接的是同一个 libsqlite…
- **[可优化｜核实 CONFIRMED]** FIONA_ALLOWED_DEV_ORIGINS 要填主机名，README 写的是「来源」，填完整 origin 会被 Next 拦截（`README.md:108`）
  - 核实意见：失败机制我核对过代码，也实测过。frontend/next.config.ts 把 FIONA_ALLOWED_DEV_ORIGINS 按逗号拆开后原样放进 allowedDevOrigins。Next 16.3.3 的 block-cross-site-dev.js 从请求的 Origin 里只取 hostname（小写），再交给 csrf-protection.js 的 isCsrfOriginAllowed，只做精确相等或按点分段的通配匹配。我直接用 node 调 blockCrossSiteDEV，模拟 Origin 为 http://192.168.3.45:3000 的 /_next/webpack-hmr 请求：环境变量设成 "http://192.168.3.45:3000" 时 blocked=true、返回 403，日志 Blocked cross-origin ...…
- **[可优化｜核实 CONFIRMED]** 北京时间测试只比日期，在纽约时间上午那半天，基线代码也能通过（`backend/tests/test_beijing_time.py:23`）
  - 核实意见：backend/tests/test_beijing_time.py:23 用的是实时时间 datetime.now(ZoneInfo("Asia/Shanghai"))，后面的断言只检查日期字符串，没有检查 get_datetime() 里的 HH:MM，也没有检查 get_time_context() 按小时给的问候语。我用 git archive 导出基线 backend 到临时目录，只放进新测试和 utils/beijing_time.py，工具代码仍是基线的 datetime.now() 和 _date.today()。在 03:43 EDT（北京 15:43，两地同一天）运行这条测试，结果 1 passed，说明纽约 00:00–11:59 这半天它区分不出回归。当前实现本身是对的；规格 T9.4 要求的测试存在并能通过，只是区分力不够，所以定为可优化：把时间固定到两地日期不同…

