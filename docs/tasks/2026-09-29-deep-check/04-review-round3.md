# 独立复核 第 3 次（Fable，2026-09-29）

**结论：通过。** M1、M5 专项复核通过；四维全任务复审（本任务首次按用户规定使用 Fable）未发现必须修复项，6 条可优化项均经 Fable 对抗核实（CONFIRMED / 可优化）。

## 专项复核

### M1 专项（对应 05-fix-round4 N1）：空画面候选句经模型确认后须追问、设待补、不生图不扣费；补描述后按待补正常生图；tests/test_cha
**结论：通过**

**证据：** 全部自己验证，未采信 03-report。工作目录 scratchpad/deepfix-review-r3/m1-r3/：cur = rsync 的当前 backend 副本（intent_router.py / services/chat_service.py / tests/test_chat_image_generation.py 的 sha256 前 16 位 199221cbe2e1ee5e / 03a7fe9e14621f2e / e6270c09059636bf，与仓库逐文件一致，复核结束时再次核对不变）；base = git archive 656b7cf；rev = cur 上把 chat_service.py 候选确认分支改回第 3 轮的 `intent_result = {**intent_result, "params": params, "missing": []}` 作正控。

【N1 修复位置】backend/services/chat_service.py 约 1098–1105 行：`needs_prompt = ("prompt" in (image_candidate.get("missing") or []) or "prompt" in (intent_result.get("missing") or []))`，随后 `"missing": ["prompt"] if needs_prompt else []` 交给 stream_intent；stream_intent（约 875–884 行）对 missing 走 set_pending + ask_missing("prompt")，不进 stream_generated_image，不置 billable，finally 里 reserved 退款。intent_router.py:170–183 对「帮我生成图片/帮我生成一张图片/画一张图/给我画一幅画」均算出 missing=["prompt"]（实测）。

【基线测试逐函数比对】用 AST 脚本 compare_tests_ast.py 比对 base 与 cur 的 test_chat_image_generation.py：基线 16 个函数全部存在；16 个函数的函数体和 parametrize 装饰器（语料）逐字一致；仅 3 个测试签名多了 `confirmed_image_intent` 夹具（test_natural_request_precedes_mirror_and_old_pending、test_image_prompt_question_then_description_generates_only_description、test_pending_image_request_can_be_cancelled_or_left）。第 2 轮改成的「帮我创作」已恢复为基线原文「帮我生成图片」（当前 :107、:171）。新增夹具 confirmed_image_intent（:37–52）是模型桩：对「帮我生成图片」返回 generate_image+missing=["prompt"]，与 intent_router.py:76 INTENT_PROMPT 自带示例 `"帮我生成图片" → generate_image, missing=[prompt]` 一致；对三句基线语料返回 generate_image。M1 规格明确要求候选须经模型确认，conftest 默认桩恒返回 null，不加此夹具基线测试按新设计必然不生图，因此该夹具属于「规格改变行为而必须新增的模型桩」，合理。新增测试 test_empty_scene_candidate_asks_without_charge_then_generates_from_followup 覆盖 4 句 × 模型 missing∈{[],["prompt"]} 共 8 例。

【测试正控】cur：tests/test_chat_image_generation.py + tests/test_image_intent_precision.py 119 passed；cur 全量（排除我的探针）1487 passed。rev（回退 N1）上跑当前 test_chat_image_generation.py：17 failed / 20 passed，失败正是恢复原文的 test_image_prompt_question_then_description…（1）、test_pending_image_request_can_be_cancelled_or_left（8）和新增空画面测试（8）——证明恢复后的基线测试与新测试能抓到这个回归。

【自编探针】cur/tests/test_r3_m1_probe.py（63 例，DEV_MODE=0 用 JWT 走真实计费）：
- N1：12 句空画面候选句（点名 4 句 + 我另写「帮我画张图」「麻烦画一幅画」「请生成一张图像」「做一张图片」「帮我生成一张图片。」「画一张图！」「给我生成个图片」等）× 模型 missing∈{[], ["prompt"], 无该键}，模型桩一律给短 prompt「模型编的一只猫」+16:9：首事件恰为「想生成什么画面？可以告诉我主体、场景和风格。」，无 generating_image/generated_image，生图桩 0 调用，pending=={"intent":"generate_image","params":{},"missing":["prompt"]}，余额不变，意图模型只调 1 次；随后发「月光下的湖边小屋，水彩风格」→ generate_image(原话, "1:1") 1 次，余额 -10，pending 清空。追问后用候选句「画一只戴红围巾的企鹅站在冰川上，横版」作答且模

**回归：** 未发现与本条直接相关的回归。M1 全部既有要求（候选需模型确认、null/异常不生图、单轮只调一次模型、镜子模式下确认仍生图、讨论兜底、完整原话、生图按钮路径不变）在 cur 上的探针与实施方测试均通过；基线 16 个测试函数体与语料逐字一致，仅 3 个签名追加了合理的模型桩夹具。

**可优化：**
- backend/intent_router.py:180 的主体清洗正则 `^(?:图片|图像|画|图)?[。！!？?，,:：\s]*$` 不剥语气词，「能帮我画一幅画吗」「帮我生成一张图片吧」「画一张图呗」「可以给我生成一张图片吗」被判为有画面（missing=[]）；基线 656b7cf 对这些句同样 missing=[] 且当时直接生图，故不是回归，现在改为依赖模型的 missing 标记，比基线更安全。建议在该正则里加入 吗|呢|吧|呗|呀 等句末语气词，使追问不再依赖模型。
- tests/test_chat_image_generation.py:41–43 的 confirmed_image_intent 夹具对「帮我生成图片」返回 missing=["prompt"]，恢复原文的两条基线测试因此经模型缺参分支通过；仅靠正则空画面判断的分支由新增参数化测试 model_missing=[] 及本复核探针（无 missing 键）覆盖。若想让基线测试本身也检验正则分支，可把夹具改为 missing=[]。
- chat_service.py 约 1098–1100 行 `"prompt" in (intent_result.get("missing") or [])`：intent_router.recognize_intent 对模型返回的 missing 不做类型校验，若模型返回非可迭代值（如数字）会抛 TypeError，被 run_chat 外层 except 转成错误事件；基线 stream_intent 同样不校验，非本轮回归，可顺手做 isinstance(list) 保护。
- 第 2 次复核已提过、仍存在：候选句被模型否决时旧的 generate_image 待补原样保留，用户被追问后若用候选句作答且模型返 null，则既不生图也不填待补。属于设计取舍，非回归。

### M5 繁简归一缺字、覆盖性测试测不出漏字（T4）——第 3 次专项复核，对应 05-fix-round4 的 N2（删除词级替换）与 N3（覆盖性测试精确相等 
**结论：通过**

**证据：** 全部实验在副本 /private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/deepfix-review-r3/M5/backend 上做（rsync 排除 .venv/uploads/*.db*/.env*，用 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python，环境变量 PYTHON_DOTENV_DISABLED=1、FIONA_DB_PATH/FIONA_UPLOADS_DIR 指向临时目录、DEV_MODE=1、JWT_SECRET 测试值、两个 API KEY=placeholder、PYTHONDONTWRITEBYTECODE=1）。基线 656b7cf（"On main: pre-fix baseline 2026-09-29"，HEAD 是其祖先，即任务起点工作区快照）的 safety.py 用 git show 提取到 …/M5/baseline/。开头与收尾比对仓库目标文件 sha256 前 16 位一致：safety.py 03ad88b8129b9cf2、utils/traditional_chinese.py e5576d76ed4177a6、tests/test_traditional_crisis.py 3b30500a6948ee5d，审查期间未被改动。仓库未被我改动（探针文件只在副本 tests/ 下，ls 仓库同名文件不存在；8073/8074 无监听；我未启动任何常驻进程，pgrep 看到的 8217/8261 两个 uvicorn 不是我起的，未动）。

1）词级替换已删除：grep 整个 backend 生产代码（排除 tests/）无 `_WORD_REPLACEMENTS`、`計畫`、`计畫`、`计画`；/Users/yangjing/Desktop/ai-workspace/Fiona/backend/utils/traditional_chinese.py:140-149 只剩 `str.maketrans` 逐字表与 `normalize_traditional` 一行 `return text.translate(_TRANSLATION)`。git diff 656b7cf -- backend/safety.py 仅 2 处：第 9 行 import，第 80 行 `normalized = normalize_traditional(re.sub(r"\s+", "", text or "").lower().replace("’", "'"))`。

2）N2 六句判级与基线一致（同一探针 probe_n2.py 分别跑基线与副本）：游戏设计画面里加一段跳海的动画 None/None；我在做设计画面，主角最后跳河 None/None；这部片的设计画面有自杀镜头 possible/possible；统计画面显示上吊人数 possible/possible；遊戲設計畫面裡加一段跳海的動畫 None（基线 None，对应简体基线 None）；電影設計畫面有自殺鏡頭 possible（基线繁体 None、对应简体基线 possible，按 N2「以简体基线为准」正确）。「計畫下週跳樓」现为 possible（简体基线 high），符合 N2 明文允许；测试 test_word_level_plan_and_second_person_variant 期望已相应改为 possible，该测试文件是基线后新增文件，不属于「基线已有测试」。「我想死妳」None（基线 high）修复保持。test_beta_safety.py 相对 656b7cf 差异 0 行。

3）N3 覆盖性测试（tests/test_traditional_crisis.py:92-109）：用 ast.walk 收集 safety.py 全部字符串常量汉字 296 个；RULE_CHARACTER_VARIANTS 114 键 + NO_VARIANT_RULE_CHARACTERS 182 字，并集 296，且两清单无交集；断言 `rule_characters == oracle_characters` 并在消息里分别点名 unlisted / absent。测试只 import normalize_traditional，不 import 生产映射表，两份清单为字面量。正控（每次先删 __pycache__ 并禁写字节码——首轮我没清缓存时 B4 报错点名成了上一轮的 薬，是陈旧 pyc 造成的假结果，清缓存后重跑全部正确）：
 A1 在 assess_crisis 内联加 `re.search(r"想离开这个世界", stripped)` → 1 failed，`unlisted rule chars: 世开界离`；同时验证注入后「我想離開這個世界」判 None 而简体 high，说明该测试确实能拦住这类漏字。
 A3 在模块级 _POSSIBLE_PATTERNS 加 `r"溺水|服毒"` → 1 failed，`unlisted rule chars: 毒水溺`。
 A4 删掉一条规则 `(?:楼上|楼顶|窗户|桥上).{0,8}跳下去` → 1 failed，`oracle chars absent from rules: 户桥窗顶`（少字也失败）。
 A2 阴性对照：加只含已列字的规则 `想死了算了` → passed（不误报）。
 B1–B12 在映射表删掉已列繁体字：讓→('让','讓')、整条删 伞→('伞','傘')、薬→('药','薬')、絶→('绝','絶')、整条删 真→('真','眞')、対→('对','対')

**回归：** 无。与本条直接相关的路径均已复核：简体「设计画面/统计画面」句子判级回到基线；生图模式含「设计画面」的请求正常出图且不再被判危机；「我想死妳」None、「讓我去死吧哈哈哈」possible 等前两轮修复保持；基线 test_beta_safety.py 相对 656b7cf 零差异；全量 1487 passed。（我自己实验中遇到的 B4 误报是副本里陈旧 __pycache__ 所致，与仓库代码无关，清缓存后重跑正确。）

**可优化：**
- 覆盖性测试把 CRISIS_GUIDANCE / CRISIS_RESOURCE_NOTE 提示语文案里的汉字也纳入「规则字」精确相等（296 字中有 127 个出现在文案里）。实测在 safety.py:23 文案里加一个「们」字，测试即失败点名 `unlisted rule chars: 们`。这比 N3 要求更严、不漏字，但今后每次改文案措辞都要同步改白名单；可考虑只收集正则元组与 assess_crisis 内联字面量，或在测试注释里写明这一约定。
- OpenCC 交叉比对仍有少数罕用字形未归一，均不在本条点名字之列，影响极小：有映射字的罕用变体 箇(个)、彆(别)、祇(只)、覆(复)、乾(干)、噹(当)；白名单字的罕用变体 衕(同)、迴(回)、傢(家)、揹(背)、緻(致)、錶(表)。其中唯一有判级影响的是 祇：文言式「祇要結束一切」因 祇 不归一为 只，safety.py:56 的 `(?<![只需重主])要结束…一切` 后顾排除失效会判 high，而简体「只要结束一切」不判 high；属误报方向，按需补 只→隻祇。
- tests/test_traditional_crisis.py:16-36 的 RULE_CHARACTER_VARIANTS 与生产表在 114 个共有键上的变体集合逐一相同（形式独立，实为同源抄写），第 2 次复核已指出。我用本机 OpenCC TSCharacters 对 141 个变体反查 0 个错挂，可把这类外部字典抽样（写死在测试里，不引入依赖）作为独立对照加进测试。
- 词汇层缺口为基线既有、与繁简归一无关（前两次复核已记录）：「活著沒甚麼意義」「活着没甚么意义」均 None；「我把整瓶药都吞了」「我吊死自己算了」简体亦 None。属 safety 规则覆盖问题，可另开单。

## 全任务复审

### safety

| 条目 | 结论 |
|---|---|
| T4-1 繁转简只用于分类，不改动存库、送模型、显示的原文 | 通过 |
| T4-2 内置映射表覆盖 safety.py 规则字与语料字的常见繁体/异体（含 M5 补字与 N3 日文新字体） | 通过 |
| T4-3 覆盖性检查改为精确集合断言，缺字/多字都失败（N3） | 通过 |
| T4-4 规格三组繁体语料（15 high / 6 possible / 7 None）、返修补测语料、基线 test_beta_safety 夹具与护栏 | 通过 |
| T4-5 自编繁/简对照语料判级一致（未照抄规格） | 通过 |
| T4-6 N2 回归：跨词「计画/計畫」不再被误改，设计画面类句子与基线一致 | 通过 |
| T5-A 路由层（routers/chat.py）结束路径：请求级校验失败、预扣异常、零余额、build_context ResourceNotFound、其他预检异常/HTTPE | 通过 |
| T5-B 服务层（services/chat_service.py）结束路径：正常文字、上游异常、空回复、生图/改图成功与失败与忙碌、工具卡片、待补追问、镜子、run_chat 兜 | 部分通过 |
| T5-C high 首事件恰为 {"crisis": true}，possible 不发 crisis 标记 | 通过 |
| T5-D 计费与退款：交付才结算，失败/追问/错误卡/落库失败退款，零余额不扣费不调模型 | 通过 |
| T5-E 存库文本不重复附资源 | 通过 |
| T5-F 路由前 422/429 属例外并已在文档与报告注明 | 通过 |
| 文档一致性：ARCHITECTURE/CLAUDE/PLAN/README 对 T4/T5 行为的描述与代码一致 | 通过 |
| 基线已有测试未被改输入/断言（T4/T5 相关，round4 硬规则） | 通过 |

- **[可优化｜核实 CONFIRMED]** ResourceNotFound 处理器先做可失败的 DB 清理再发资源，possible 级在清理抛错时资源丢失（`backend/services/chat_service.py:1184`）
  - 代码原文（1182-1189）：
    except ResourceNotFound:
        if not high_crisis:
            await asyncio.to_thread(clear_pending, ctx.state_key)
            from mode_switcher import clear_user_mode
            await asyncio.to_thread(clear_user_mode, ctx.state_key)
        if _needs_crisis_resource(state):
            yield _crisis_resource_event(state)
        yield _sse({"error": "会话已删除或不可用"})

clear_pending / clear_user_mode 都是 SQLite 写操作，会因 database is locked 等原因抛异常。possible 级走到 if not high_cris
- **[可优化｜核实 CONFIRMED]** 03-report.md 主表 T4 行的覆盖性数字已过期，与第 4 轮实际实现矛盾（`docs/tasks/2026-09-29-deep-check/03-report.md:23`）
  - 第 23 行仍写「检查 210 个规则汉字中可反查的 74 字/77 变体」，这是第 1 轮弱断言时期的数字；第 4 轮 N3 之后测试改为对 safety.py 全部字符串常量的 296 个汉字做精确集合断言（114 字有映射 + 182 字无异体白名单），同文件第 183 行自己写的也是 296/114/182。实测（ast 收集）：296 个汉字、映射表 126 键、测试清单 114 + 182。主表与返修段落自相矛盾，读者按主表理解会低估覆盖面。

### concurrency

| 条目 | 结论 |
|---|---|
| T2 request_public_url 的 timeout 是整个调用的墙钟总时限，覆盖 DNS、连接/TLS 握手、响应头、响应体与每一跳重定向 | 通过 |
| T2 响应体分块读取，每块检查剩余时间并把 socket 读超时设为 min(剩余, 原单次读超时) | 通过 |
| T2 测试：临时端口滴流服务器 Content-Length 很大、每 0.5s 1 字节，timeout=2 在 3 秒内失败；快速响应含重定向不受影响；只桩 resolve_p | 通过 |
| T2 调用方（fetch_card、topic_expand）把超时当普通抓取失败处理，不崩溃 | 通过 |
| T3 官方/分身交流上游调用不占默认线程池，生产路径无条件使用 AsyncOpenAI（R3） | 通过 |
| T3 停止或撤销时取消在途上游调用，上游 2 秒内观察到断开，被取消调用记为 discarded | 通过 |
| T3 同一用户任何时刻最多 MAX_RUNNING_PER_USER 个在途上游调用，「开始→停止」快速循环不能突破 | 通过 |
| T3/M3 取消收尾不可被再次取消打断；不依赖局部 call_id；cancel_exchange 在 cancelling()>0 时不再 cancel | 通过 |
| T3/P2 结算抛非取消异常时有限次重试并记日志，/stop 不返回 500，重试仍失败时 recover_interrupted_exchanges 在下次启动结清 | 通过 |
| T3 execute_intent、hot.py、cards.py 慢外部调用改到专用有界线程池，池大小环境变量可配、默认值写进 .env.example | 通过 |
| T3 应用启动时显式设置默认线程池大小（环境变量可配，默认不低于 32） | 通过 |
| T3 验收测试（默认池 4、8 个交流挂 5s、8 个滴流 fetch_card，另一用户聊天 1.5s 内完成）以及 O5 要求测试真正覆盖 execute_intent 接线并 | 通过 |
| T9.1 在导入任何读取环境变量的模块之前加载 dotenv（override=False），FIONA_ENV_FILE 可指定文件，默认 backend/.env | 通过 |
| T9.1/O1 admin_env 与服务进程共用 dotenv 选择规则：展开 ~、显式文件缺失或不可读时启动失败并给中文说明、默认 backend/.env 缺失静默跳过 | 通过 |
| T9.1 main.py 设置 PYTHON_DOTENV_DISABLED=1 的副作用 | 通过 |
| 后端全量与相关文件测试门禁（副本复跑） | 通过 |

- **[可优化｜核实 CONFIRMED]** 交流在途轮询每 0.25 秒新开一个 aiosqlite 连接（即新起一个 OS 线程）（`backend/services/exchange_service.py:162`）
  - _generate_while_authorized 用 `if not await exchange_store.is_exchange_running(exchange_id, run_token):` 每 0.25s 轮询撤销，而 exchange_store.is_exchange_running（exchange_store.py:562-565）每次 `async with aiosqlite.connect(...)` 新建连接；aiosqlite 0.22.1 的 Connection 是 Thread 子类，每次连接都是一次线程创建+SQLite 打开+关闭。实测一个挂起的上游调用在 3 秒窗口内触发 aiosqlite.connect 11 次、Thread.start 11 次；一次 45s 普通调用约 180 次，120s 工作流调用约 480 次，按运行中的交流数线性叠加。不占默认线程池、不影响 T3 判据，但在 2 vCPU 主机上是持续的无谓开销。

### frontend

| 条目 | 结论 |
|---|---|
| T1 候选层与接线：explicit_image_intent 只提名、模型确认后才生图；同轮复用一次识别；空画面追问不扣费（N1）；讨论兜底（V1）与完整原话（V2） | 通过 |
| T6 私聊文本不进任何 URL（验收 6.7） | 通过 |
| T6 票据鉴权、有效期 ≤60s、次数上限、跨用户、旧 text 参数拒绝 | 通过 |
| T6 Range 语义：闭区间 206 + Content-Range/Content-Length/Accept-Ranges；非法或越界 416；bytes=0- 首次与无 R | 通过 |
| T6 前端队列：按序播放触发 ended、票据失败跳过不中断、停止朗读中止在途换票且不再对旧句发 stream 请求（O3） | 通过 |
| T6 限流不比现在更严 | 通过 |
| T7 退出登录：只有 2xx 才清本地并跳转；失败留在原页并可重试；401 视为已退出（O2） | 通过 |
| T7 身份回填：Cookie 有效但 localStorage 为空时从 /profile 取回并写回；401 去登录页；只做一次不死循环；/history /match /pro | 通过 |
| T7 生产构建不把「默认用户」当身份；删号需真实用户名，拿不到时禁用并提示加载中 | 通过 |
| T8 前端：dev 默认只绑 127.0.0.1，dev:lan 显式开放并在 README 写明风险；allowedDevOrigins 不再是 * | 通过 |
| T8 后端：DEV 通道（X-Dev-User/dev_user 中间件与依赖、WebSocket dev_user、/auth/test-login、send-otp、verif | 通过 |
| T9.2 HEIC/AVIF 与视频 brand：图像 brand 400 并给中文提示；只有已知视频 brand 算视频；未知 brand 拒绝 | 通过 |
| T9.3 广场发布非 2xx 时把 detail 显示在弹窗，保留文案与已选标签，不关闭弹窗 | 通过 |
| 前端门禁与范围：tsc、lint --max-warnings=38、build 通过；package.json 仅 scripts；frontend/AGENTS.md 与基线一 | 通过 |

- **[可优化｜核实 CONFIRMED]** WebKit/iOS 朗读首音需等整句非流式合成完成（`backend/routers/voice.py:317`）
  - `if range_header is not None and (has_cached_audio or not _is_zero_open_range(range_header)):` 之后走 `_get_tts_audio`，对 WebKit 的 `bytes=0-1` 试探要先完成整句 `synthesize` 才返回首字节，随后 `bytes=0-N` 读缓存。这是 M2 选定的取舍（WebKit 需要有限长度才会触发 ended），Chromium/WebView2 不受影响；但 Safari/iOS 上每句首音延迟等于整句合成耗时，长句会明显慢于原来的流式播放。实测打桩合成 0.3s 时 WebKit 第一句 play() 比 Chromium 略早只是因为打桩快，真实 TTS 对 200 字句子会是数秒级。
- **[可优化｜核实 CONFIRMED]** /history 直达页在身份回填前后仍以「默认用户」渲染一次（`frontend/app/history/page.tsx:43`）
  - `const username = params.get("user") || localStorage.getItem("fiona_user") || "默认用户";` 在每次渲染时计算，不使用 useAccountIdentity，也不监听 fiona-user-changed。Cookie 有效但 localStorage 为空时，首屏头部显示「默认用户 · 0 条」，直到 /api/history 完成触发 setLoading 重渲染才换成真实用户名（实测最终头部为真实用户名，功能正常）。导出按钮若在这个窗口内点击，文件名会是 Chloe_默认用户_日期.txt（history/page.tsx:126、:132）。该文件在 §2.1 白名单之外，属于显示层残留，不是账号操作。

### scope

| 条目 | 结论 |
|---|---|
| 验收 1：后端全量 pytest 全部通过且数量 > 1169、0 failed / 0 error | 通过 |
| 验收 2：逐文件 pytest 无 FAIL | 通过 |
| 验收 3：compileall 退出码 0 | 通过 |
| 验收 4：前端 tsc / lint --max-warnings=38 / build | 通过 |
| 验收 5：真实数据哈希前后一致 | 通过 |
| 验收 6：改动文件全部在 §2.1 白名单内；requirements*/package-lock/desktop 无差异；package.json 只改 scripts | 通过 |
| 验收 7：源码中找不到把回复文本放进 URL 的写法 | 通过 |
| 验收 8：T1–T9 及各返修单要求的测试名称和语料存在并通过；报告逐条给出测试函数名 | 部分通过 |
| 验收 9：frontend/AGENTS.md 与基线一致 | 通过 |
| §2 约束：测试隔离与端口（不读写真实 .env/.db/uploads，只用 127.0.0.1 临时端口，不占 3000/3001/8000/8001/8010） | 通过 |
| 各返修单中「修改基线已有测试」均有规格依据；第 4 轮硬规则（逐条列出）满足 | 通过 |
| T9.4：北京时间只替换面向用户的时间，内部计时不改；测试在基线上会失败 | 通过 |
| T10：部署文档照做可行（前置条件、自检命令、备份权限子 shell、README 局域网调试、.env.example 新变量） | 通过 |

- **[可优化｜核实 CONFIRMED]** 03-report.md 顶部 T1–T10 对应表与文件清单已过期：引用 5 个不存在的测试函数名，文件数写 42 实为 45（`docs/tasks/2026-09-29-deep-check/03-report.md:20`）
  - 第 20 行 T1 行列出 `test_explicit_image_requests`、`test_image_comments_and_questions_are_not_early_commands`、`test_direct_image_request_bypasses_model_intent_classifier`；第 25 行 T6 行列出 `test_tts_ticket_single_use_and_bound_to_user`、`test_tts_synthesize_consumes_same_ticket_once`。用脚本收集 backend/tests/test_*.py 全部 `def test_` 名称核对，这 5 个名字均不存在（当前对应的是 test_image_intent_precision.py 的 test_image_request_is_only_a_candidate / test_image_discussion_with_null_model_never_generates 等，以及 test_tts_private_tickets

