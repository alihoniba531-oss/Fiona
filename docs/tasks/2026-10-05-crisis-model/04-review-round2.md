# 复核 第 2 次：第 1 轮返修核验（2026-10-06）

- **复核方式**：Opus 5.5，2 个视角（代码；评测与文档），只核验第 1 轮返修是否做到、是否正确、有无回归。
- **主会话实测**（默认 2 秒超时，沙箱外真实模型，每句 3 次取最差）：
  - 全量 `1727 passed`；
  - 324 次调用仅 1 次超时，中位 0.92 秒、p90 1.37 秒（返修前 125/357 次超时）；
  - 必须高危 54/54、至少可能 16/16；
  - 日常唯一句 48 句，模型新增高危 0，None→possible 2.08%；
  - 私藏盲测：明确危机 30/30、20/20，隐晦表达 9/9、10/10，日常模型新增高危 0。

## 结论：通过

## code：通过

| 条目 | 结论 | 证据 |
|---|---|---|
| 返修1 连接池参数与惰性复用 | 符合 | crisis_model.py:38-55：_client 为 None 时才建 AsyncOpenAI(max_retries=0, timeout=本次配置, http_client=httpx.AsyncClient(limits=Limits(20,10,120), timeout=本次配置))，之后复用。导入期不建客户端（原测试 runpy 仍成立）。test_crisis_model.py:747-772 用假 AsyncClient 断言了池参数、只建 1 次、http_client 透传。探针用真实 openai 2.37.0 + httpx 0.28.1 + httpcore 1.0.9，假网络后端，无 socket：3 次快速调用 connect_tcp 只发生 1 次，即保活复用生效；直连池和 macOS 系统代理池的 max_connections、max_keepalive、keepalive_expiry 都是 20/10/120。 |
| 返修1 超时调用时生效、不被首个客户端锁死 | 符合 | 每次调用都重新读 _timeout_seconds()，并同时传给 create(timeout=...) 和 wait_for(timeout=...)（:70、:88、:90）。探针用 0.75 秒建客户端后，把配置改成 3.5 再调用：httpcore 收到的读超时是 [3.5]，说明请求级超时覆盖了客户端初建时的 0.75。现有单测只校验传给 create 的参数；真实 SDK 下确实生效，由本次探针证实。 |
| 返修1 超时取消后连接重建 | 符合 | 探针 S3：连续 25 次 wait_for 超时，每次都返回 None，日志为 failed type=TimeoutError；新建连接 24 次（第 1 次用的是原有的保活连接），结束后存活连接 0、池内连接和排队请求都清空；下一次快速调用新建 1 条连接并成功。S4：30 个并发同时超时，同时存活的连接最多 20 条，未超过上限；之后存活 0，下一次调用成功，后续调用复用连接（只新建 1 次）。报告 6.1 对重建过程的描述与实测一致。没有预热请求，也没有后台任务。 |
| 返修1 多事件循环与进程退出关闭 | 符合 | 线上 run.py 是单个 asyncio.run 加 uvicorn；classify 只在 routers/chat.py:107 调用，评测脚本只调一次 asyncio.run。测试中 autouse 夹具把 AsyncOpenAI 换成桩，真实 httpx 客户端从不发请求，monkeypatch 会把 _client 还原为 None，测试之间不会串用。全局客户端始终不 aclose，进程退出时由操作系统回收 socket，不构成资源泄漏。第 1 次复核的 O3（跨事件循环复用）这一轮按设计没有处理，保活期从 5 秒延长到 120 秒后，这一风险的窗口变大（见可优化项）。 |
| 返修2 final_crisis 兜底与 CancelledError 传出 | 符合 | routers/chat.py:111-118：except Exception 时按 model=None 合并，CancelledError（BaseException）照常传出。model_task 只在 final_crisis 和 finally 的 gather(return_exceptions=True) 中被 await。8 处调用点（144/155/160/176/182/186/197/202）以及 build_context 的 crisis_resolver 都经过 final_crisis，行号相对第 1 次复核整体只偏移 +4。路由探针：消息分「活着没意思」「帮我查下明天天气」两种，覆盖 9 个分支（参数校验、预扣异常、零余额、ResourceNotFound 退款成功/失败、上下文 RuntimeError 退款成功/失败、HTTPException、正常），classify 分别抛 RuntimeError、ValueError、OSError，与 classify 返回 None 的基线逐字比对，差异 0，悬空任务 0。 |
| 返修2 补测是否真能拦住回归 | 符合 | test_crisis_model.py:806-828 覆盖规则 possible、classify 抛 RuntimeError、image_edit 参数校验错误三者同时出现，断言资源恰好 1 次、events[0] 是资源、最后一条是精确的错误文案、余额不变；:831-845 验证取消会传出。正控（复制 chat.py 后改动再驱动这两个场景）：去掉 try/except 后 runtime 场景抛 RuntimeError，第一条测试会失败；改成 except BaseException 后取消场景变成返回资源流，第二条测试会失败；原代码两项都符合预期。 |
| 返修3 首尾各 1000 字与边界 | 符合 | crisis_model.py:62-68：先 strip，长度超过 2000 才取前 1000 +「……」+ 后 1000。探针：前后包上全角空格和 \t\r\n，正文长度为 1、1999、2000 时原样送判；2001、2002、8000 时送判 2002 字，与期望拼接完全一致。测试 :276-283（2700 字加首尾空白）、:775-786（8000 字末尾危机句，断言 endswith）、:789-797（2000 和 2001 两档加首尾空白）都是精确断言：换回旧的 [:2000] 写法、把判断改成 >=2000、或先比长度再 strip，都会被这几条测出来。被改写的旧测试只同步成同样精确的新断言，没有放宽。 |
| 返修5 level 先 strip/lower 再比对 | 符合 | crisis_model.py:93-99：非字符串一律抛 ValueError；字符串先 strip().lower() 再与枚举比对。:800-803 用 HIGH 和 " high " 两种写法，断言都识别为 high，日志只有 level=high；不做规范化时这两条会失败。探针中 " Possible\n" 也被识别为 possible。合并规则只升不降，所以这样放宽解析是安全的。 |
| 返修4 提示词按返修单改写 | 符合 | crisis_model.py:15-22 逐项对照返修单：格式示例改为占位写法 {"level":"high/possible/none"}；possible 一句与规格原文逐字一致，并补上「拿不准时倾向possible」；「才判high」改成「以下任一情况判high」；想消失、不想醒来只有在句中明确给出日常目的时才豁免为 none，例子是定个闹钟、去旅行、捆箱子；普通睡眠休息须有明确的日常目的或语境才算 none；危险词与本人备有危险物品两种情况已分开写。主会话实测：必须高危 54/54、至少可能 16/16，盲测全部达标。 |
| 返修4 报告逐条列差异 | 符合 | 03-report.md 6.2 逐行列出 :15–:22 的差异和理由，另附字面重合与语义重合的披露。有一处漏列：规格写的是「不带求死语境的中性问题（例如问桥有多高、楼有几层）」，提示词收窄成「中性高度/楼层问题」，报告却写成「保留」。收窄的是 none 一侧，方向对危机用户更安全，只是披露不完整，记为可优化。 |
| 无回归：文档和既有行为 | 符合 | git diff 57d2056 显示 safety.py、chat_service.py、conftest.py 没有新增改动。README、CLAUDE.md、ARCHITECTURE.md 已同步首尾送判，ARCHITECTURE 写的「最多 32 tokens」与代码一致；DEPLOYMENT 补充了 journalctl -u fiona 的统计口径和 10% 阈值，服务名与该文件第 21 行的 fiona.service 一致。全部探针运行前后 git status 一致，没有生成 __pycache__，临时目录已删除。 |

**可优化**

- PLAN.md:127 仍写着「由 qwen3.8-flash 只看本轮前 2000 字复核」，与返修 3 后的首尾各 1000 字不符。本轮白名单没有包括 PLAN.md，所以文档之间出现了不一致；建议主会话把这一句同步改掉。
- 提示词第 21 行「只出现死亡、药…高处等危险词，但本人没有表达处境或意图的，判none」，与第 16 行「询问致死的方法、剂量、高度、时长判high」之间有张力：「吃多少安眠药会死」「跳楼多高能死」这类问句本身就不含本人处境或意图，按字面可以套进第 21 行。这句话照抄了返修单的措辞。实测没有造成损害（模型单独判，必须高危 45/45 都是 high；主会话三次取最差 54/54），但建议在第 21 行补一句「致死方法、剂量、高度、时长的询问除外」，消除歧义。
- 03-report 6.2 漏列一处收窄：规格的「不带求死语境的中性问题（例如问桥多高、楼几层）」在提示词里成了「中性高度/楼层问题」，报告写成「保留」。方向对危机侧更安全，只需要补一行披露。
- final_crisis 的 except Exception 吞掉异常时不打印任何日志，DEPLOYMENT 里用 failed/(failed+level) 算的回落比例统计不到这种路由层回落。按当前的 classify 实现走不到这条路径，以后换实现时会变成静默失效。建议在 except 里打印 `[crisis-model] failed type=<类型> ms=...`（不带原文）。
- 保活期从 5 秒延长到 120 秒后，第 1 次复核 O3 的跨事件循环风险窗口变大：将来如果有脚本或测试用真实客户端跨多个 asyncio.run 调用，会复用绑定在已关闭事件循环上的旧连接，每条旧连接导致一次静默回落。线上是单个事件循环，不受影响。可以按正在运行的事件循环缓存客户端，或者在 lifespan 关闭时 aclose，也顺带解决进程退出时没有关闭客户端的问题。
- keepalive_expiry=120：如果 DashScope 前端或中间网络设备在 120 秒内静默丢弃空闲连接（不发 FIN/RST），空闲一段时间后的第一次复核会一直等到 2 秒超时、回落到规则结果。离线无法验证，主会话的评测是连续调用，也测不出这种情况。建议在真实网络下各测一次间隔 30、60、150 秒的调用，上线后用 DEPLOYMENT 里的回落比例盯这一项。
- max_connections=20：同时超过 20 个非高危请求时，多出来的请求要排队等连接，排队时间占用 2 秒超时预算，可能回落到规则结果（探针 S4 证实上限生效）。内测流量下可以接受，但部署文档可以写明有这个上限。
- 返修 1 的单测只用假 AsyncClient 检查了构造参数。请求级超时是否真正传到 httpcore，以及取消后能否重建连接，目前只有本次复核的探针证明过。可以补一条无网络的持久单测（用 httpx.MockTransport，或给 httpcore 注入假网络后端）。
- 原文正好 2001 字时，送判文本变成 2002 字，丢掉中间 1 字、插入「……」，比原文还长。不影响结果，可以把阈值改成超过 2002 字才截断。属于纯整洁性问题。

## eval-docs：通过

| 条目 | 结论 | 证据 |
|---|---|---|
| 返修6-1 规则 high 跳过模型并单独计数（eval_crisis_model.py:248-254、279-280、180-182） | 符合 | 用打桩 classify、真实 safety 规则跑全语料：sentences=119 calls=108 rule_high_skipped=11；repeats=3 时 calls=324，与主会话实测的 324 次一致。规则 high 的句子记为 Result(models=(), combined=('high',))，模型单评时被排除，合并评分时计入。转换表每句记一次 rule=high model=skipped。线上 chat.py:106-109 同样只在 crisis!='high' 且非空时建任务，两边口径一致。 |
| 返修6-2 期望 none/not_high 的句子在模型单评中 high 比 unavailable 更差（worst_level :91-107） | 符合 | 打桩让「这栋楼有几层」三次返回 none、None、high。模型单评输出 high=1，fail 行为 worst=high repeats=none,unavailable,high（第 1 次复核时这里显示 unavailable）。危机侧 ('high',None) 仍返回 None。另用随机桩跑 324 次，独立重算各组合并档位的达标数，5 组全部与脚本输出一致。 |
| 返修6-3 泄漏检查：≥6 字片段 / 短句整句 / stdout+stderr / JSON 转义（:121-136、:257-270） | 符合 | 全语料正控（108 次调用）：stdout 打印 6 字片段、stderr 打印 6 字片段、json.dumps 后 ASCII 转义的整句和 6 字片段、ensure_ascii=False 的 JSON、logging lastResort 输出到 stderr，均检出 108/108。只打印长句的 5 字片段时为 0，符合设计。短句（不足 6 字）整句打印检出 6，正好等于非规则高危的短句数。干净日志的反控为 0。1017 个片段与各类异常名、level 行、dotenv 提示做了比对，误报为 0。 |
| 返修6-3 level/failed 行数之和等于调用数的断言（:282-286） | 符合 | 用真实 crisis_model.classify 加假客户端驱动（不出网），覆盖 high、HIGH、' possible '、none、非 JSON、未知档位、level=1、超时 0.5 秒和 ConnectionError：calls=18，level_lines=8，failed_lines=10，failure_type 依次为 ConnectionError、JSONDecodeError、TimeoutError、ValueError，断言成立。日志行尾附带原文时 level_lines=0，断言按预期抛出，且没有打印原文。 |
| 返修6-4 C4 按唯一句去重（unique_daily_results :139-153） | 符合 | 真实语料中日常条目 49 条，去重后 48 条。跨组同句的全部尝试会合并保留：「这栋楼有几层」两组共 6 次尝试中有 1 次 high，合并后 added_high=1，较差的档位没有丢。 |
| 返修6-5 纯函数单测是否测到计分边界（test_eval_crisis_model.py:13-122） | 符合 | 共 56 个用例，数量与报告一致。照抄这些测试的参数表做内存变异：去掉日常 high 优先、min/max 对调、忽略 None、not_high 接受 None、p90 改用 floor 或 ceil 不减一或 quantiles、窗口改成 5 或 7 字、去掉转义形式、去掉短句整句、不去重、只保留首组尝试，以上变异全部被杀死。只有 p90 改成 round(n*0.9)-1 这一个变异存活（见可优化）。 |
| 返修7 DEPLOYMENT.md:116-123 网络延迟、journalctl 命令、10% 阈值与调到 3 秒 | 符合 | 文档写明了到 DashScope 的网络延迟决定回落比例，并给出 failed/(failed+level)、10% 阈值、调到 3 秒后再观察。两条命令与 crisis_model.py:102-109 的 print 格式逐字对应。用 journald 格式的样例行测试：BSD grep 和 ugrep 都匹配，计数为 failed=1、level=2。unit 名 fiona 与 DEPLOYMENT:151 的 fiona.service 一致。 |
| 返修7 ARCHITECTURE.md:132 模型清单 | 符合 | 清单写明「也用于独立的危机复核，危机复核不回退、不重试」；llm.QWEN_MODEL 确实是 qwen3.8-flash，max_retries=0。 |
| 返修7 报告自述更正（03-report.md:3、18、27、52、636、6.1） | 符合 | 开头、文件表中 CLAUDE/README 一行（已改为「仅在 README 登记，CLAUDE 未登记，也未量化首字延迟」）、§2.1 首尾送判、473 字统计已标为历史结果。复算提示词 612 字与语料的最长公共子串分布为 {0:3,1:75,2:32,3:7,4:2}，4 字的两处都是「不想醒来」，与报告一致。6.1 引用的行号逐一核对无误。 |
| 回归检查 | 符合 | main() 先拒绝 FIONA_CRISIS_MODEL_ENABLED=0，避免分类器不打日志导致断言误报。断言失败的消息里不含原文。conftest 已全局设置 PYTHON_DOTENV_DISABLED=1，评测函数再设一次不污染其他测试。本次检查全部打桩，未调用真实模型，没有读 .env。 |

**可优化**

- PLAN.md:127 还写着「只看本轮前 2000 字复核」，与返修 3 的首尾各 1000 字不一致。PLAN.md 不在第 1 轮白名单内，实施方没改，也没在 6.5 未决问题里列出，需要主会话同步。
- DEPLOYMENT 的两条 journalctl 命令没带 --since。按文档建议把超时调到 3 秒后再「观察回落比例」，统计会混入调整前的累计日志，结论会被稀释。建议两条命令统一加 --since "<调整时间>" 或 --since today。另可补一条 grep -c 'failed type=TimeoutError'，把网络超时和其他错误分开统计。非 root 读不到日志时计数为 0，会落进「分母为 0」，可提示加 sudo。
- grep 模式 '\[crisis-model\]' 已在 BSD grep 和 ugrep 上实测能匹配；GNU grep 本机没有，未实测（3.8 以后对 POSIX 未定义的转义可能给出警告）。改成固定串 grep -cF '[crisis-model] failed' 更稳。
- C4 的 none_to_possible 统计的是「任一尝试含 possible」，没按取最差：同一句的尝试里既有 possible 又有 high 时，会同时计入 added_high 和 none_to_possible。随机桩实测重复计了 12 句（29 对 17）。测试 test_daily_statistics_* 把这种重复计数固化成了期望值。方向偏保守，本次真实评测 added_high=0，不受影响。
- 模型单评只让 high 压过 unavailable。期望 none 的句子出现 ('possible', None) 时显示为 unavailable，possible 误升在模型单评的计数里被藏住；合并报告和 fail 行的 repeats 仍能看到。
- 日志检查的盲区（打桩实测）：事先绑定到原始 stderr 的 logging handler 会绕过捕获，有 3 行漏到外部且不计数，比如 OPENAI_LOG=debug 时 SDK 打印的请求体；repr(utf-8 字节) 只检出 11/108；大写 \uXXXX 只检出 10/108。行数断言只核对总数，不逐次调用核对：一次调用打 2 行、另一次打 0 行仍能通过。另外 assert 在 python -O 下会被去掉。
- p90 单测只用了 n=1、2、10、11，分不出「最近秩 ceil」和 round(n*0.9)-1，这个变异存活。可加 n=16 一类的用例（此时 ceil 取第 15 位，round 取第 14 位）。

## 主会话处理

收尾小返修（第 2 轮）只处理三项：`PLAN.md` 首尾送判的描述同步；路由兜底时打印 `[crisis-model] failed type=... ms=...`；报告补上「中性问题」口径的披露。提示词不改，评测结果仍然有效。其余可优化项留待以后。
