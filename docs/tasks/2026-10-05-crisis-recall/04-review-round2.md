# 复核 第 2 次：返修后核验（2026-10-05）

- **复核方式**：Opus 5.5，2 个视角。按规则只核验第 1 次复核的「必须修复」是否消除；新发现一律降为「可优化」。
- **背景**：用户 2026-10-05 拍板「保留路由保护，改用模型判级」。第 1 轮返修撤回全部判级扩充，只保留路由保护与繁体「計畫」；勘误补了 设→設、统→統 两组映射。
- **主会话机械验证**：
  - 全量 `1588 passed`；
  - 9061a52 时三个危机测试文件共 689 个字面量，新旧判级只有「計畫下週跳樓」一句不同；
  - `traditional_chinese.py` 只多两行映射。

## 结论：通过

## 判级层面：通过

| 条目 | 已消除 | 证据 |
|---|---|---|
| 返修单 F1 / R3（safety.py 只保留三处） | 是 | git diff 9061a52 -- backend/safety.py 只有 4 处改动：第 56 行和第 60 行的「计划」都换成 (?<![设统])计(?:划/画/畫)，新增 _normalize_crisis_text（assess_crisis 改为调用它），新增 is_informational_crisis_context。第 0 轮加的日常剥离（原 :33-:36）、他人语境扩词（:44-45）、_METHOD_QUERY 新分支（:59-62）、新 high/possible 规则（:68-:101）和 contextual_death 都已从文件里消失。文件 125 行，基线 114 行，多出的 11 行正好是两个辅助函数。复核开始和结束时文件哈希都是 f2f5fde6…，审查期间没有被改。 |
| 返修单 F2 勘误 / R2（traditional_chinese.py） | 是 | diff 只有两行追加："设": "設" 和 "统": "統"，没有删除行。「画」没有映射，「畫」没有归一成「画」，所以 normalize_traditional 的结果是：設計畫→设计畫、統計畫→统计畫、計畫→计畫、計劃→计划。 |
| spec-compliance M1（大量日常话从 None 升到 high） | 是 | 引发问题的 :68/:72/:73/:74/:79/:80/:86 规则都已撤回。把基线 9061a52 的 safety.py 和 traditional_chinese.py 导出到 scratchpad/rev2_judge/base，与工作区版本分两个子进程导入，stderr 各自打印了加载路径。正控：「計畫下週跳樓」基线 possible，新版 high，说明比对真的生效。M1 原证据和反方补测共 28 句（吊死在一棵树上、各自尽力、寻死觅活、金鱼是怎么死的、吃完所有的药、my phone is gonna die、需要结束生命周期等），新旧判级 0 处不同，新版全部是 None。 |
| spec-compliance M2（possible 兜底误伤后拦工具） | 是 | :96/:97 的天台、不想醒来/撑了、买好绳子规则和 :36 的剥离都已撤回。17 句（美梦不想醒来、伞不想撑了、买好绳子去跳绳/绑纸箱、我们到天台了、真不想醒来+查天气等）新旧判级 0 处不同，新版全部是 None，is_informational 都是 False。因为不再判 possible，skip_tools 不会被触发。 |
| spec-compliance M3（新规则只覆盖语料原句） | 是 | 这条针对的是 :79-80、:94、:59-62、:86 这几条新规则泛化不够，这些规则都已撤回。按用户拍板，判级扩充整体转给下一单（模型判级）。29 句证据（整盒药、半瓶药倒装、跳几楼会死、i will hang myself、寻短见等）新旧判级 0 处不同，新版是 22 句 None、6 句 possible、1 句 high，和基线一致，没有比基线更差。 |
| classifier-overreach MF1（我…6 字内跳河/海/自尽/寻死，按子串判 high） | 是 | 原 :73 新增的 割脉/跳河/跳江/跳海/自尽/寻死 已撤回；traditional_chinese 也没有「尽:盡儘」映射了。19 句（各自尽力、各自儘量、跳海草舞、跳江南style、寻死觅活、屈原自尽等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF2（意图动词+吊死/烧炭/自尽/寻死） | 是 | 原 :74 的扩词已撤回，基线 :60 只把「计划」换了写法，方法词表和基线逐字相同。20 句（吊死在一棵树上、吊死鬼、火锅要烧炭吗、准备烧炭烤鱼、虞姬自尽、写寻死的小说等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF3（致死询问新分支：几/死/跨标点） | 是 | _METHOD_QUERY 和基线相同（diff 没有涉及），:59-62 的两条新分支已撤回，「几:幾」映射也撤回了。17 句（晒死了、烦死了、贵死了、挂上吊牌、墙上吊着辣椒、自杀式袭击等）新旧判级 0 处不同：12 句 None、5 句 possible，都是基线原值，没有一句升到 high。 |
| classifier-overreach MF4（「吃完所有药」判 high） | 是 | :79/:80 两条泛药规则已撤回。16 句按疗程吃完药的说法新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF5（药备好…今天…结束） | 是 | :81 已撤回。12 句（今天化疗结束、疗程就结束了、会议结束、输液结束+查天气等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF6（知道…怎么死、怎么死最快） | 是 | :72 已撤回。10 句（剧本杀、程序/进程怎么死的、MC 里怎么死最快等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF7（生命分支放宽，误伤「生命周期」） | 是 | 生命分支和基线逐字相同：(?<![现正实])在 和 (?<![只需重主])要 都还在，没有 需要/现在/这就。17 句（需要结束生命周期、Windows 10 现在结束生命周期、生命支持、生命值等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF8（楼上/天台…想跳 跨逗号） | 是 | :76 已撤回，第 61 行只剩基线的 (?:楼上/楼顶/窗户/桥上).{0,8}跳下去。8 句（楼上跳广场舞我也想跳、桥上蹦极我也想跳等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF9（英文 gonna、life 前缀没有词边界） | 是 | :86 的 (?:i'?m)?gonna 和 :101 的 donewith/disappear 都已撤回。18 句（my phone is gonna die、I'm gonna diet、stocks are gonna jump、done with life insurance、vanish forever from social media 等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF10（他人语境扩词，日常转述被兜底成 possible） | 是 | _CONTEXTUAL_MENTIONS 不在 diff 里，和基线相同。15 句（他们去三亚跳海了、有人在河边烧炭烤串、她寻死觅活地要买包等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF11（不想醒来/撑了、备好绳子） | 是 | :97 和 :36 都已撤回。13 句（梦太美不想醒来、伞不想撑了、买好绳子去拔河/放风筝、查五金店那句等）新旧判级 0 处不同，新版全部是 None。 |
| classifier-overreach MF13（哪种/什么安眠药…睡不醒，窗口吞掉否定） | 是 | :84 已撤回。7 句（第二天不会睡不醒、半夜不醒、整晚不醒等）新旧判级 0 处不同，新版全部是 possible，即基线原值，没有升到 high。 |
| classifier-overreach MF14（日常剥离删掉了危机句） | 是 | 新增的剥离规则（:33「这/那棵树上吊死」、:35「跳河江海.{0,4}游泳/救人…」）已撤回，_EVERYDAY_PHRASES 不在 diff 里。17 句（我想在楼下那棵树上吊死、我想跳河，我不会游泳、我想在那棵树上吊死自己等）新旧判级 0 处不同，新版 15 句 high、1 句 possible、1 句 None，都是基线原值，召回已回到基线。 |
| classifier-recall MF1（剥离导致召回比基线还差） | 是 | 原因和 overreach MF14 相同，规则已撤回。16 句（后山那棵树上吊死自己、我要跳河，别救人、我想跳海，不用救援了等）新旧判级 0 处不同，新版 15 句 high、1 句 possible（「我今晚就在楼下那棵树上吊死」基线就是 possible），回退已消除。 |
| classifier-recall MF2（结束生命只认少数前置词） | 是 | 这条针对的是原 :68 的新前置词（需要/现在就/这就），已撤回，判级扩充转下一单。24 句新旧判级 0 处不同：23 句 None，1 句 high（「我想现在就结束生命」）。规格句「我需要结束生命」「现在就结束生命」也回到基线 None，没有比基线更差。 |
| classifier-recall MF3（即时跳水域依赖「我」锚点） | 是 | :73/:74 的扩词已撤回，转下一单。30 句（省略主语、加时间词、跳海酒馆等）新旧判级 0 处不同，新版全部是 None。反方顺带指出的「我去跳海酒馆了」从 None 升到 high 的误伤也已消失。 |
| classifier-recall MF4（句尾前瞻只认 $ 和少数标点） | 是 | 三处前瞻（:76 想跳、:81 结束、:140 跟他走）所在的规则都已整条撤回，转下一单。18 句新旧判级 0 处不同：16 句 None，2 句 possible，都是基线原值。 |
| classifier-recall MF5（吊死只覆盖三种写法） | 是 | :71/:73/:74 的吊死规则已撤回，转下一单。17 句新旧判级 0 处不同，新版全部是 None，没有比基线更差。 |
| classifier-recall MF6（吞药倒装只认一个模板） | 是 | :79-80 已撤回，转下一单。21 句新旧判级 0 处不同：18 句 None，3 句 possible，都是基线原值。 |
| classifier-recall MF7（烧炭/一死了之等没有兜底） | 是 | 相关新规则已撤回，转下一单。30 句新旧判级 0 处不同，新版全部是 None，和基线相同。 |
| classifier-recall MF8（致死询问依赖固定方法词） | 是 | :59-62、:72、:84 三条新规则已撤回，_METHOD_QUERY 和基线相同，转下一单。24 句新旧判级 0 处不同，新版全部是 None。 |
| classifier-recall MF10（英文只认固定连写前缀） | 是 | :86-88、:101 的英文扩充已撤回，转下一单。36 句（含 6 句规格原句）新旧判级 0 处不同，新版全部是 None，和基线相同。 |
| 附加核对(1) 计划词改动是否让日常句从 None 升档 | 是 | 自拟了约 50 句只含「计划/计画/計畫/計劃/設計/統計/会计/伙计/估计/预计/总计/累计/计算」、不含危机词的日常句，比如「我计划明天去北京出差」「估计画完要三天」「预计画展下周开幕」「共计画了二十张」「设计画册要重印」「統計畫面要更新」「会计划分科目」「帮我计算一下房贷」「这个设计划算吗」，新旧判级 0 处不同，全部是 None。test_design_frame 的 6 条参数在新版下全部符合期望。升档只出现在「X计+画（动词）」后面跟着危机方法词的构造句里，见可优化第 1 条。 |
| 附加核对(2) / 返修单 R4：现有测试的字符串字面量 | 是 | 用 AST 从 9061a52 版的 test_beta_safety.py、test_traditional_crisis.py、test_crisis_resource_paths.py 取出 690 个去重字符串字面量，按基线判级为 None 537、high 98、possible 55，样本不是空集。新旧判级不同的只有「計畫下週跳樓」一句（possible→high）。扩大到 9061a52 的全部 62 个测试文件（3235 个去重字面量），结果也只有这一句。 |
| 附加核对(3) / 返修单 F5：新测试文件 | 是 | test_crisis_recall_2026_10.py 里已经没有 SPEC_MUST_HIGH 等四组语料和 GENERALIZED_METHOD_CONTEXT_CASES 等护栏组。用 grep 搜 SPEC_/GENERALIZED/吊死/烧炭/自尽/寻死/一死了之/gonna/end it all，命中 0 次。保留和新增的参数组共 29 条，用 AST 取出后直接调用新版逐条核对，全部符合期望（0 失败）：TRADITIONAL_PLAN_CASES 11 条和规格第 5 节原句逐字一致，9 句判 high、2 句判 None；PLAN_AND_WORD_BOUNDARY_CASES 10 条；INFORMATIONAL_CONTEXT_CASES 8 条。新测试文件 118 个字面量中，新旧判级不同的 13 句全是计划词句，说明没有用例依赖已撤回的规则。路由用句「活着没意思」「查一下安眠药吃多少会有危险」「画一张猫，活着没意思」「把这张图片换成黑白，活着没意思」都判 possible、info=False，是基线原值。另外模拟了字符覆盖测试：清单两侧相等，没有多余字也没有遗漏字，变体全部能归一回简体。 |

**可优化**

- 【新发现，降为可优化】计划词的前置排除 (?<![设统]) 只挡了「设计/统计」两个复合词。其他以「计」结尾的词（预计、会计、合计、伙计、估计、累计、总计）后面接动词「画」时，也会被当成计划词。如果 8 字内再出现方法词，就会升档。实测：「预计画好跳海那一幕要一周」「預計畫展裡有一幅跳海的畫」「总计画了三幅跳河的画」「累计画了几十张吞药的插图」从 None 升到 high；「会计画了个自杀率的图表」「伙计画的那张割腕的海报被撤了」「合计画了五张上吊的分镜」「估計畫完這幅跳樓的插畫要三天」从 possible 升到 high。前提是句子里本来就有危机方法词，而且是在讲画画，所以不含危机词的日常句没有受影响。建议在模型判级那一单里一起处理：可以扩大前置排除，或者要求「计画/计畫」后面不能紧跟 了/的/完/好/展 这类表示「画」是动词的字。
- 【新发现，仅供知悉】反方向也有变化：「设计划分/统计划分」后面接方法词时，判级比基线低。例如「这个设计划分了跳河救援区」「設計劃分了跳河救援區」从 high 降到 None，「统计划分出跳楼高发楼层」从 high 降到 possible。这几句是日常话，降级相当于修掉了误报。没有找到因此漏判的真实危机句。
- 【转下一单的跟踪项】按用户拍板撤回后，第 1 次复核里召回类各条（M3、recall MF2-MF8、MF10）的证据句，以及 02-spec 第 5 节的语料都回到了基线水平：SPEC_MUST_HIGH 54 句中只有 9 句繁体計畫判 high，另有 31 句 None、14 句 possible；SPEC_AT_LEAST_POSSIBLE 16 句全是 None；SPEC_MUST_BE_NONE 里仍有 2 句 high、1 句 possible。建议把这些句子和第 1 次复核里的日常反例一起，原样写进模型判级那一单的验收语料和日常护栏，避免遗漏。
- 第 1 次复核里已降为可优化的 overreach MF12（否定句）和 recall MF9（计划+结束生命）：前者 12 句、后者 13 句，新旧判级都是 0 处不同。MF9 里的「計畫結束生命」仍判 None，和基线一致，因为本单的计划词只接到了自杀/轻生/去死和方法词上。

## 路由与文档：通过

| 条目 | 已消除 | 证据 |
|---|---|---|
| 第1次复核·routing 视角（3.2 路由，第1次结论：通过，0 项必须修复） | 是 | git diff 9061a52 -- backend/services/chat_service.py 与第1次复核所见一致，行号对得上（skip_tools 在 :1023，候选 :1079，生图 pending :1113，镜子 :1153，skip 分支 :1164-1169，preserve_pending 在 :657）。skip_tools = possible 且 not is_informational_crisis_context，并且只对 possible 才求值（短路）。possible 非信息语境时：explicit_image_intent 不调用；image_pending 取 None，stream_pending、fallback、clear_pending 都到不了；return 发生在 get_pending、stream_pending、recognize_intent_with_fallback、stream_intent 之前。detect_mode、镜子、has_image 走 stream_image 的顺序都在 skip 分支之前，没有变；stream_normal 负责计费和热线，trace 的 crisis 字段没有改。显式 image/image_edit 和 image_edit_requires_reference 两个分支都在 skip 判断之前，一字未改。high 在 :1047-1059 就 return；skip_tools=False 时，三处改动表达式都与基线等价。判级回滚后重新探测：活着没意思 possible/False，查一下安眠药吃多少会有危险 possible/False，画一张猫，活着没意思 possible/False（explicit_image_intent 的正则对这句确实会提名候选，测试没有空跑），帮我查下割腕的急救方法 possible/True，帮我查下明天天气 None。_CONTEXTUAL_MENTIONS[3] 仍然是 :43 的信息或求助语境规则。结论：返修后仍符合原规格 3.2。 |
| spec-compliance M1/M2 及 classifier-overreach MF1–MF14（误判后果：日常话被升级，possible 拦掉工具） | 是 | 用户已拍板撤回全部判级扩充。safety.py 相对 9061a52 只剩三处改动：两处计划词换成 (?<![设统])计(?:划/画/畫)（直接写的汉字）、_normalize_crisis_text、is_informational_crisis_context。用 git show 取出基线 safety.py 和 traditional_chinese.py 在内存里执行，并做了正控（基线没有 is_informational_crisis_context；計畫下週跳樓 基线判 possible、现在判 high）。把 04-review.md 里全部「」引句和 02-spec.md 里全部引号句共 1012 句新旧逐句对比，只有 9 句判级变化，全部是 計畫+方法 的危机句升为 high；M2 点名的工具类日常句（帮我查下附近的五金店，我买好绳子了还差钉子／帮我订个闹钟，我不想醒来也得醒／我到天台了／帮我搜Windows 10是不是现在结束生命周期了 等）现在都判 None，不再拦工具。另把 test_beta_safety、test_traditional_crisis、test_crisis_resource_paths、test_o1_resource_cleanup、test_image_intent_precision 五个文件在 9061a52 时的字面量共 827 个唯一字符串新旧对比，判级变化的只有「計畫下週跳樓」一句，与返修单 R4 一致。 |
| spec-compliance M3 / classifier-recall MF1–MF10（召回与覆盖面） | 是 | 按返修单和用户拍板，这部分不在本单修，转到下一单「模型判级」。PLAN.md:277 已加待办「危机判级改为规则加模型复核（下一单）」。日常剥离已撤回，所以 recall MF1「剥离删掉危机句」的回退不复存在：上面 1012 句对比里没有任何一句比基线判得更低。 |
| 返修单 F6·CLAUDE.md / README.md / docs/ARCHITECTURE.md | 是 | 三处文档 diff 用 --word-diff 看，只改了 possible 路由那句并补了一句「繁体『計畫』与『計劃』判级一致」。diff 的增删行里搜 跳河/跳江/跳海/吊死/烧炭/自尽/割脉/寻死/了断/致死/安眠药/天台/绳子/消失/一了百了/gonna/补词 等，命中 0 次，没有残留撤回的判级词。路由描述（保留模式判定、镜子、看图、普通回复、计费；信息或求助语境以外跳过生图候选、意图、工具和待补参数并保留 pending；信息或求助语境、显式 image/image_edit、修图固定引导保持原路由）与代码一致。「計畫与計劃判级一致」已实测：计划、计画、计畫、計劃、計畫、計画 六种写法 × 18 种句尾 × 3 种句首，判级完全一致，0 处不同。ARCHITECTURE.md:73、:86 里涉及 possible 的旧句没有改，但仍然成立。 |
| 返修单 F6·PLAN.md | 是 | 2026-09-29 小节与基线逐字相同，第 0 轮插进去的那行已经移走。紧接着新建了「### 2026-10-05：危机路由保护」（PLAN.md:120），下面两条：可能相关非信息语境的路由保护；繁体『計畫』与『計劃』判级一致。「产品安全政策」清单新增待办「危机判级改为规则加模型复核（下一单）」（:277），措辞和返修单 F6 逐字一致。:83、:100 是带「当时」的历史记录，基线原样保留。 |
| 返修单 F7·03-report.md「第 1 轮返修」 | 是 | 这一节如实写了按 F2/F3 原文执行后的冲突：5 个非 HTTP 失败，R4 多出 2 句（遊戲設計畫面…、電影設計畫面…）。它没有自行放宽，而是提出了最小例外。R3 贴出的 safety.py diff 与当前 git diff 9061a52 -- backend/safety.py 逐行一致。F5 写的 42 例我用 AST 数参数化组合核过：11+10+8+6+5+1+1=42。F4 写 chat_service.py 本轮没动，行号与第 1 次复核引用的完全吻合。表里 F2「diff 为空」已经被勘误一节明确标为历史记录，并且由勘误节更新。 |
| 返修单·勘误（F2/F3 追加 设/設、统/統）及 03-report「第 1 轮返修·勘误」 | 是 | traditional_chinese.py 相对基线只追加了 "设": "設"、"统": "統" 两行；test_traditional_crisis.py 的 RULE_CHARACTER_VARIANTS 末尾只追加这两项，NO_VARIANT 只追加「画畫」和指定的两行注释。不跑 pytest，按测试逻辑模拟字符覆盖：清单与规则字面汉字完全相等，两表无交集，所有变体都能归一回简体。test_plan_word_does_not_cross_word_boundaries 的 4 条参数和 test_design_frame_mentions_keep_baseline_crisis_level 的 6 条参数直接调用都通过，勘误节说「5 个非 HTTP 失败已消除」属实。R4 我独立复现：只有「計畫下週跳樓」一句 possible→high。勘误节的定向回归数 205 用 AST 核为 42+107+56=205，相符。全量 1588（1582 通过 + 6 个端口用例）按硬规则没有重跑。worktree 无 .pytest*、__pycache__ 遗留，git status 里只有白名单文件和任务文档。 |
| 第1次复核·可优化 O2（镜子 preserve_pending） | 否（可优化，不阻断） | 现状没变（可优化项，不构成阻断）。stream_mirror 仍带只能按关键字传的 preserve_pending=False（chat_service.py:657），只有 skip_tools 时才传 True（:1153），也就是受保护轮在手动镜子模式下不清 pending。返修单没有处理它，也没有记录用户确认；03-report 第 0 轮未决问题第 3 条仍是唯一的披露。文档「保留 pending」「镜子保持现状」与这一行为一致。仍需用户确认这个取舍。 |
| 第1次复核·可优化 O3（会话删除时清 pending） | 否（可优化，不阻断） | 现状没变（可优化项，不构成阻断）。finally 分支 missing_conversation and not high_crisis 时仍会 clear_pending 和 clear_user_mode，possible 跳过轮也受影响。test_o1_resource_cleanup.py 与基线逐字节相同，这个语义仍被既有测试钉住；03-report 第 0 轮未决问题第 2 条已披露。被清的是已删除会话的 pending，对用户没有实际伤害。 |
| 第1次复核·可优化 O4（余额断言写法） | 否（可优化，不阻断） | 现状没变（可优化项，不构成阻断）。test_crisis_resource_paths.py:325 仍是 assert _balance(user) == before - 10，与「possible+pending 那一支改为扣 10」对 6 组参数结果等价。high、mirror 分支一字未改。第 0 轮和第 1 轮返修的未决问题里都没有记录这一处形式偏离。 |

**可优化**

- [新发现·降为可优化] 判级撤回、路由保护保留之后，基线就判 possible 的日常说法现在会连同句里的工具请求一起被拦。例如「帮我查下明天天气，别在一棵树上吊死」判 possible、非信息语境，本轮不再联网搜索；「统计画面显示上吊人数」同理。这是规格 §2 第 4 条点名的「上吊」子串误伤，本单没有修（与第 1 次复核 OP4 同一根源）。建议在 PLAN 下一单「模型判级」的验收里写明：要把这类基线 possible 日常句的拦截率当作指标。README 沿用基线的「日常口语不触发」一句，现在略显过满。
- [可优化] O2 镜子模式 preserve_pending 的取舍仍待用户确认；返修单和报告第 1 轮都没有给出结论。
- [可优化] O4 余额断言简化成 before - 10 的形式偏离，仍未写进 03-report 的未决问题，可以补一句。
- [可优化] 03-report 第 0 轮未决问题第 5 条（画/畫用 \u 转义来绕开覆盖测试）已经过时：第 1 轮按 F1 改成直接写汉字，并列入 NO_VARIANT 清单。第 1 轮未决问题第 4 条只笼统说「第 0 轮的自行判断不再代表当前实现」，建议在第 5 条旁加注「已由第 1 轮取代」，以免读者误解。
- [可优化] 第1次复核 routing O5 现状不变：is_informational_crisis_context 仍按下标 _CONTEXTUAL_MENTIONS[3] 引用规则，以后调整规则顺序会静默改变语义。现在只有 INFORMATIONAL_CONTEXT_CASES 从行为上间接钉住；可以给第 4 条单独命名一个常量。

