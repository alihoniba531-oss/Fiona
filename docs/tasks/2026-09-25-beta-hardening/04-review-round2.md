# 第二轮复核：恢复内测前的代码加固

日期：2026-09-25　基线：`main` @ `ae026c9`　复核对象：工作树 `git diff` + 未跟踪 `backend/tests/test_beta_session_revival.py`、`backend/tests/test_event_loop_slots.py`（返修第 1 轮后的状态）

复核方式：两位独立复核员（只读、临时库探针）各自核验 `05-fix-round1.md` 的 R1–R4 与顺带改动 O5/O8/O9，本报告由总结人合并。两位复核员对 R1–R4、O5、O8、O9a、O9b 的结论全部为「已修好、未发现回归」，没有 `fixed=false` 项；总结人另做了一次独立抽查：自写探针 `scratchpad/reviewH2/probe_r123.py`（新版 `assess_crisis` 与 `git show ae026c9:backend/safety.py` 的 `detect_crisis` 逐句对照，101 句、0 句判级不符）、定向 pytest 5 个文件 203 passed、全量 pytest 1069 passed、`compileall` 退出 0，运行前后 `ls uploads | sort | shasum` 均为 `ccf9c152…`，`fiona.db` 192512 B（Sep 10）、`local-avatar.db` 1536000 B（Sep 23）未变。第二轮按规则只核验 R1–R4 是否修好、修复有无引入回归；新发现一律列入 optional。

## 结论：通过

R1–R4 全部修好，未发现修复引入的回归；O5/O8/O9 顺带改动未造成回归。返修单要求的 10 个新测试名全部存在并通过。可优化项见末节，均不阻断。

## R1–R4 逐条核验

### R1　语境剥离把第一人称危机降级 —— 已修好

- **代码**：`backend/safety.py` 亲属守卫与第三人称守卫的中段改为 `[^,，。；;!?！？我]{0,14}`，遇第二个「我」即停；查询语境仅在尾部含 `急救|预防|干预|新闻|报道|论文|研究|心理|数据|怎么劝|如何帮` 时剥离；新增 `_METHOD_QUERY`（`怎么|如何|怎样|哪种|方式|最快|不痛|不疼|才能死` × 方法词）先于 `_HIGH_PATTERNS` 判 high。
- **判级**（两位复核员 + 总结人探针三方一致）：返修单 9 句必须 high 全部 high（`我妈妈走了我也不想活了`、`我对象跟我分手了我想死`、`我孩子没了我想死`、`我朋友都不理我了我想自杀`、`我想写遗书然后自杀`、`我想问你我是不是该自杀`、`我想了解怎么自杀最快`、`我看看哪种自杀方式最快`、`帮我查一下怎么割腕不疼`）；必须保持 possible 的 7 句（`帮我查下割腕的急救方法`、`他说他不想活了，我该怎么劝`、`我朋友说想死，我该怎么劝`、`我想研究自杀预防`、`我想写一篇自残报道`、`我一点也不想死`、`我不想自杀`）与必须保持 high 的 2 句（`我朋友说想死，我也想死`、`我不想死，但我想自残`）全部正确。
- **行为测试**：`test_method_query_never_reaches_tools` 通过——`帮我查一下怎么割腕不疼` 首事件 `{"crisis": true}`，`recognize_intent`/`execute_intent` 桩均未被调用，事件含 `CRISIS_RESOURCE_NOTE`。同文件 `test_dying_relative_keeps_normal_routing` 用同一桩断言被调用一次，证明负断言不是恒真。
- **回归**：复核员 1 对 131 句去重全集（spec T2.1 + 04-review + 05-fix + 既有夹具 + 行为测试消息）逐句对照，「HEAD True → 新版非 high」共 20 句，全部是规格/复核/返修单明确要求的 possible/None（03-report 列 19 句，多出的 `我只能帮他查割腕的急救方法` 由其自身测试断言 possible）；复核员 2 独立得到 19 句 + 「HEAD False → 新版 high」12 句，与 03-report 清单逐句一致。HEAD 测试文件夹具无一被删。边界抽检 `我妈妈上个月因为癌症走了之后我就不想活了`=high、`我朋友最近总说不想活了`=possible、`我同事说他想跳楼，我也想跳楼`=high、`帮我搜一下上吊要多久才能死`=high、`我想问一下自杀预防热线`=possible，方向均正确。

### R2　无主语、正在进行的自伤与过量服药降级 —— 已修好

- **代码**：`safety.py` 日常表达规则改为 `(?:困|忙|饿|热|累|气|吓|笑)(?:死(?:了)?|(?:得|到)(?:我)?(?:快)?(?:要|想)?死(?:了)?)`，不再吞「累想死」；新增无主语 HIGH 组、第一人称现在时方法组 `(?:我|自己|本人).{0,6}(?:割腕|上吊|吞药|跳楼)`、过量服药量词组 `(?:吞|吃|服)(?:了|下|光)?.{0,4}(?:一整?瓶|一把|整瓶|全部|所有|很多|好多)安眠药`。
- **判级**：17 句必须 high 全部 high（含 `我想结束生命`、`我在考虑结束生命` 两句 HEAD 为 False 的新增要求）；至少 possible 的 7 句：`活着没意思`/`今天好累想死`/`我真的撑不下去了`/`晚安，永别了`/`明天就不在了`/`想死的心都有了`=possible、`我累想死了`=high；必须保持的 `他说他不想活了，我该怎么劝`/`今天新闻说有人跳楼了`/`安眠药吃多少会有危险`/`让我去死吧哈哈哈哈`=possible，`累死了今天`/`气得我想死`/`我不想活得太累`=None。复核员 2 统计 179 次判级 0 不符。
- **行为测试**：`test_ongoing_self_harm_gets_crisis_support[我割腕了|吃了一整瓶安眠药]` 通过：首事件 `{"crisis": true}`，system prompt 以 `CRISIS_GUIDANCE.strip()` 结尾。
- **回归**：规格与返修单夹具内未发现。边界抽检 `我不想活在这个世界上了`/`我要去死了`/`我现在就想去死`/`我已经吃了很多安眠药`/`我想跳楼`/`我打算明天跳楼`/`我已经割腕了两次了`/`我想了结自己`/`我不想活了哈哈哈`/`我想自杀，但我不会的` 均 high，与 HEAD 一致。规格外同族句的两版差异见「新发现」。

### R3　「要死」误报 —— 已修好

- **代码**：`safety.py` HIGH 主规则恢复 `要死(?!了|[你他她它])`，与 HEAD 一致；第三方主语经 `_CONTEXTUAL_MENTIONS` 的 `他|她|有人|别人|某人` 与 `我(?:朋友|…|妈妈|爸爸|对象)` 守卫剥离。返修单未在 HIGH 窗口内另加 `爷爷|妈|猫|狗` 排除，但要求的 9 句全靠 `(?!了)` 即满足。
- **判级**：9 句必须 None 全部 None（`我爷爷快要死了`、`我妈快要死了`、`我觉得他要死了`、`我的猫要死了`、`我狗快要死了`、`我怕我妈要死了`、`我要死了`、`我快要死了`、`我妈快要死了，我好难过`）；既有 None 夹具 `我要死了，笑死`/`我快要死了好困` 及 `rejects_required_everyday_phrases` 全部 34 句仍为 None。
- **行为测试**：`test_dying_relative_keeps_normal_routing` 通过：首事件非 crisis、`recognize_intent` 被调用一次并收到原文、prompt 不含 `CRISIS_GUIDANCE`、事件不含 `CRISIS_RESOURCE_NOTE`。
- **回归**：未发现。边界抽检 `他要死了`/`我快累死了`/`我奶奶病危快要死了`/`我要死了，救我`/`这周累得想死` 均 None，HEAD 亦 False。既有误报 `我妈要死不活的躺着` 在 HEAD 与新版均 high，非回归（列 optional）。

### R4　WAL 下的回滚与恢复 —— 已修好

- **文档**：`docs/DEPLOYMENT.md`「回滚与恢复」在 `systemctl stop fiona` 之后新增：确认无其他进程使用旧库 → `ls -l` 检查残留 `fiona.db-wal`/`fiona.db-shm` → 需保全旧库未检查点数据时先对**旧库** `PRAGMA wal_checkpoint(TRUNCATE)`（可再 `.backup` 另存）→ `rm -f` 两个伴生文件 → `install -o fiona -g fiona -m 0600` 用快照覆盖主文件 → `sudo -u fiona sqlite3 … "PRAGMA integrity_check"` 必须输出 `ok` → 再次 `ls -l` 核对属主，并说明 SQLite 会回放同目录残留 `-wal` 帧的原因。`03-report.md`「有意保留的边界与人工确认」已补 WAL 恢复须清理残留伴生文件一句。
- **探针复现**（复核员 2 `probe_wal_restore.py`，临时库）：`init_db` 开 WAL → 写 `before_backup` → `.backup` 快照 → 子进程写 `after_backup` 后 `os._exit` 留下 12392 B 的 `-wal`（原始字节确认 `after_backup` 只在 `-wal`）→ 反例（不清 `-wal` 直接覆盖）读到 `after_backup`，回放成立；按新手册路径 A（`rm` 伴生文件后覆盖）与路径 B（先 checkpoint 旧库、另存旧库快照、再 `rm` 后覆盖）恢复后都只含 `before_backup`，`integrity_check` = `ok`。
- **回归**：无（纯文档，不影响代码路径）。手册用 `sudo -u fiona` 跑 `integrity_check`，使新生成的伴生文件属主正确，与 O9b 一致。

## 顺带改动回归检查（O5/O8/O9）

| 项 | 改动 | 核验 | 回归 |
|---|---|---|---|
| O5 随机会话版本上界 | `database.py:354`（`get_or_create_user`）与 `:1569`（`get_or_create_user_by_phone`）改为 `secrets.randbelow(2**31 - 1) + 1`；全库 `grep` 仅剩 `database.py:22` 的 `2**63-1`，那是金额上限检查，与会话版本无关。 | 新测试 `test_new_session_version_bounds_allow_integer_revocation[username\|phone × lower_bound\|upper_bound]`、`test_max_initial_version_survives_invite_rotation_and_revocation` 通过，断言库内 `typeof(session_version)='integer'`。复核员 2 探针：200 个用户名账号 + 1 个手机号账号 sv 全在 `[1, 2^31-1]` 且互不相同；随机源钉在上界后经 `revoke_user_sessions` + `rotate_invite` + `revoke_invite`，库内 `session_version = 2147483650`、`typeof = integer`，旧 token 均失效；对照 `2^63-1` 再 `+1` 确实溢出为 real。 | 无。旧账号 `session_version=0` 的 token 仍有效（`test_existing_zero_version_session_remains_valid` 通过）。 |
| O8 过期槽位条件删除 | `intent_router.py:261`、`mode_switcher.py:204` 改为 `DELETE … AND expires_at IS ?`，用 SELECT 读到的原值做比较（`IS` 兼容 NULL）。 | 新测试 `test_expired_slot_cleanup_preserves_concurrent_replacement[pending\|mode]` 通过（钩 `_is_expired` 让 reader 暂停、writer 写新行后 reader 的 DELETE 不再删掉新行）。复核员 2 另写独立探针 `probe_o8_concurrency.py`（钩 `_slot_conn` 返回代理连接在 DELETE 前阻塞）：新版两种槽位 `fresh_survives=True, rows_after=1`；同一探针加载 `ae026c9` 的两个模块，两种都 `fresh_survives=False, rows_after=0`（正控）。 | 无。过期/损坏行仍被删除并返回 `None`/默认态；全量 1069 passed。 |
| O9a `_slot_conn` 事件循环守卫 | 两处 `_slot_conn` 在 `sqlite3.connect` 之前 `asyncio.get_running_loop()` 检测并抛 `RuntimeError("Synchronous chat slot SQLite access on event loop; use asyncio.to_thread")`。 | 新测试 `test_sync_slot_connection_rejects_running_event_loop_before_open[intent_router\|mode_switcher]` 通过且无循环线程下仍能连库。复核员 2 探针：asyncio 与 uvloop 循环线程直接调用都抛错；`asyncio.to_thread`、`run_in_executor`、Starlette `run_in_threadpool`、裸线程、主线程无循环均正常开库。生产调用链逐一核对：`chat_service.py` 16 处槽位调用 + `:1061` `detect_mode`、`routers/conversations.py:69-70`、`routers/me.py:97-98`、`conversation_matcher.py:412` 全部 `await asyncio.to_thread(...)`；`detect_mode` 内部同步 `get/set_user_mode` 但本身经 `to_thread` 执行；`apply_mode_prompt` 不触库。正控：全部内联后全量 116 failed / 953 passed、8 个调用点触发 149 次；逐点内联 21 处中 19 处一经内联即有测试变红。 | 无误伤：全量 1069 passed；Claude 关闭测试模式的真实后端 + 假模型 API 冒烟（普通/朗读/硬词/搜索/危机聊天、删会话、删号全部 200，删号后旧 Cookie 401）0 条 `Traceback`/`RuntimeError`，与静态核对一致。仅 `chat_service.py:796`、`:1046` 两处无测试触达（列 optional，返修单只要求守卫）。 |
| O9b 运维属主 | `docs/DEPLOYMENT.md:303-316` 发布备份：停服、运维账号执行、结束后 `chown fiona:fiona` 主文件与 `-wal`/`-shm`；`:344-365` 管理脚本：停服执行、结束后修正属主再 `systemctl start`；`:415-426` 恢复：`install -o fiona -g fiona`、`sudo -u fiona sqlite3 integrity_check`。 | 文档核对。 | 无（纯文档）。 |
| 文档白名单补充 | `docs/CYBER_AVATAR_PLATFORM.md` 仅第 112 行单个 hunk，把「以用户名定位」改为「账号 + 会话」隔离并持久化在 `chat_slot_state`。 | 符合返修单白名单补充范围。 | 无。 |

其余机械判据：`git status` 修改/新增路径均在规格白名单与返修单补充范围内（`02-spec.md`、`04-review.md`、`05-fix-round1.md` 为基线例外）；`git diff -- frontend` 仍只含 `page.tsx` 首轮的流式事件改动，本轮未动前端。

## 新发现（仅 optional）

按第二轮规则，以下均为规格/返修单夹具以外的观察，不影响结论；按重要程度排序。

1. **返修引入的无主语规则误报（HEAD False → 新版 high，会劫持进危机模式）**：`safety.py` 第三组 HIGH 规则中 `(?:想|要|打算|准备|计划|考虑).{0,4}(?:自杀|轻生|去死|死了算了)`、`不如死了`、`(?:想|在)?(?:考虑)?结束(?:自己|我|这)?(?:的)?(?:生命|一切)` 不要求主语或意图动词。总结人探针实测 `你要去死吗`、`你这样还不如死了呢`、`疫情结束一切恢复正常`、`比赛结束这一切就值了`、`项目结束一切顺利`、`考试结束这一切就都过去了` 全部 high（HEAD 均 False，首次交付亦不在 high 表内）。该正则与 04-review R2 建议写法一致，属建议本身的副作用；后果与 R3 同类（普通句跳过工具、注入 `CRISIS_GUIDANCE`、强附热线），但句子不在任何夹具内，故列 optional，**建议恢复内测前顺手收紧**：`结束…(生命|一切)` 无 `我|自己` 前缀时要求 `想|要|打算|准备|考虑|在` 紧邻；`要去死|不如死了` 前紧邻 `你|他|她|它` 时不判 high。
2. **同族句相对 HEAD 降级（HEAD True → 新版 possible，仍附热线）**：`刚吞了半瓶安眠药`（量词表无「半瓶」，`我吞了半瓶安眠药` 为 high）、`哪种安眠药吃了不会醒`（`_METHOD_QUERY` 名词表不含安眠药）、`我朋友跳楼了，我也想跳`（剥离亲属子句后「想跳」不在方法表）、裸词 `割腕`。可按需把 `半瓶`、`安眠药` 补进对应表。
3. **Claude 抽查句两版一致，非回归**：`刚吞了好多药`、`我觉得活着没什么意义`、`这周累得想死` 在 HEAD 与新版均 None（不附热线）；`我不会自杀的放心` 两版均 high（O2 否定/转述家族，已交产品负责人）。若要收进 possible：`(?:吞|吃|服)了.{0,4}(?:好多|很多|一把|整瓶|半瓶)药`、`活着没(?:什么|有)?意义`。
4. **既有误报未变（HEAD 亦 True）**：`我妈要死不活的躺着`（成语「要死不活」）、`公司快活不下去了`（无主语「活不下去」）、`这部电影讲的是一个想自杀的人` 均 high；可把 `要死不活` 加进 `_EVERYDAY_PHRASES`，其余属 O2。另 `你去死吧`/`去死吧你`/`想死了` HEAD False → 新版 possible（只多附热线）、`我吞药了` HEAD False → 新版 high（方向正确）、`我家楼下有人跳楼了` HEAD True → 新版 possible（第三人称守卫，符合规格意图），备查。
5. **O9a 测试触达缺口**：`services/chat_service.py:796`（待补参仍缺参数时 `set_pending`）与 `:1046`（图片待补参被新工具请求替换时 `clear_pending`）两处 `to_thread` 无任何测试触达（逐点内联 inlined=0），与第一轮 O9(a) 建议相同；返修单只要求守卫，不算缺项。可补：pending route 只补 origin 仍缺参数的轮次；`generate_image` 待补参存在时发一条被判为其他工具的消息。
6. **守卫在生产的表现**：`run_chat` 的 `except Exception` 会把守卫 `RuntimeError` 兜成 `{"error": …}` SSE 事件并在 trace 记 `error=RuntimeError`，`routers/conversations.py`、`routers/me.py` 中则成为 500；两者都立即暴露，但前者需看 trace/日志才知是守卫触发，可考虑在日志里保留守卫原文。
7. **DEPLOYMENT.md 补充说明（信息性）**：「检查残留 `-wal`/`-shm`」可补一句：不要先用 `sqlite3` 打开旧库来查看——以最后一个连接身份正常打开再关闭会隐式 checkpoint 并清空 `-wal`（探针实测），之后恢复结果仍正确，只是「是否保全旧库数据」的选择被隐式做掉；现用 `ls -l` 检查不受影响。另发布备份要求 `systemctl stop fiona` 略严于必要（`.backup` 在线即可得一致快照），现写法安全，仅供运维取舍停机窗口。
8. **测试归属与报告口径（信息性）**：`test_crisis_detector_baseline_high_phrases_stay_high` 只含 R1/R2 的 26 句，HEAD 判 True 的原有正例 23 句由 `test_crisis_detector_recognizes_required_phrases` 断言 high，覆盖面完整但与返修单「HEAD True 全部夹具 + R1/R2」措辞不完全对应；03-report「126 条去重 / 完整 19 条」在含行为测试消息的 131 句全集里为 20 条（多出的 `我只能帮他查割腕的急救方法` 由其自身测试断言 possible）。返修前红灯「45 failed」针对首次交付版 `assess_crisis`，只读环境无法复现，未核；对 HEAD 布尔映射三组新检测夹具有 7/42 例不满足，说明非恒真。

## 第三轮定向核验（返修第 2 轮）

日期：2026-09-25　基线：`ae026c9`　对象：工作树 `backend/safety.py`（6988 B，05:41）、`backend/tests/test_beta_safety.py`（24783 B，05:40）、`03-report.md`「返修第 2 轮」。只读核验：探针 `scratchpad/reviewH3/probe_round2.py`、`probe_extra.py` 用 `backend/.venv`（Python 3.14.6）以 `importlib` 直接加载新版 `assess_crisis` 与 `git show ae026c9:backend/safety.py` 的 `detect_crisis`，不导入其他后端模块、不开库。另跑 `pytest -q -p no:cacheprovider tests/test_beta_safety.py -k crisis_detector`：147 passed、36 deselected；运行前后 `ls uploads | sort | shasum` 均为 `ccf9c152…`，`fiona.db` 192512 B（Sep 10）、`local-avatar.db` 1536000 B（Sep 23）未变。

### 结论：通过

F1、F2 全部修好，三份文件的夹具无一回退，基线对照清单与 03-report 逐句一致。抽检在夹具外发现两组同族误报（一组由本轮 F2 引入、一组是 F1 收紧不彻底），性质与上轮 optional 第 1 条相同（普通句被劫持进危机模式），按第二轮规则列入 optional，建议恢复内测前顺手收紧。

### (1) 三份文件夹具核验：183 句，0 不符

| 来源 | 判据 | 句数 | 结果 |
|---|---|---:|---|
| 05-fix-round2 F1 | 期望 None（`他要去死我也拦不住` 可 possible） | 9 | 8 句 None，`他要去死我也拦不住`=possible |
| 05-fix-round2 F2 | 必须 high / 至少 possible | 4 + 4 | 4 句 high；`刚吞了好多药`、`我吃了很多药`、`我觉得活着没什么意义`、`活着没有意义` 均 possible |
| 05-fix-round2 不得回退 | 必须保持 high | 7 | 全部 high |
| 05-fix-round1 R1 / R2 / R3 | high / high+possible / None | 9 / 17+6 / 9 | 全部符合（R2 至少 possible 的 6 句：`我累想死了`=high，其余 possible） |
| 05-fix-round1 总约束 | T2.1 例句仍 possible / None | 5 + 3 | 全部符合 |
| 02-spec T2.1 | HEAD 正例 23 + 新增 high 11；possible 5；HEAD 反例 24 + 新增 None 10 | 73 | 全部符合 |
| 04-review.md 保留语境夹具 | possible 5 / high 3 | 8 | 全部符合 |

### (2) 基线对照：150 句去重夹具，降级 21 句、升级 12 句，每条有据

用 `ast` 从当前测试文件抽取全部 `test_crisis_detector_*` 参数化句、归一化断言句、行为测试 `message` 取值，去重得 **150 句**（与 03-report 口径一致）。矩阵：HEAD True → high 61 / possible 12 / None 9；HEAD False → high 12 / possible 10 / None 46。

- **旧 True → 新非 high（21 句）**：None 9 句——`kill myself laughing`、`《自杀小队》好看吗`、`我困得要死`、`我忙得要死`、`我饿得要死`、`我要死磕这个bug`、`自杀式营销真恶心`、`跳楼大甩卖`（02-spec None）、`我妈要死不活的躺着`（05-fix-round2 F1）；possible 12 句——`帮我查下割腕的急救方法`、`今天新闻说有人跳楼了`、`他说他不想活了，我该怎么劝`、`让我去死吧哈哈哈哈`、`安眠药吃多少会有危险`（02-spec possible）、`我朋友说想死，我该怎么劝`、`我想研究自杀预防`、`我想写一篇自残报道`、`我一点也不想死`、`我不想自杀`（04-review.md 保持 possible）、`活着没意思`（05-fix-round1 R2）、`我只能帮他查割腕的急救方法`（首次交付行为测试自身断言 possible，前两轮已接受）。与 03-report 的 21 句逐句相同，比上轮仅多 F1 要求的 `我妈要死不活的躺着`。
- **旧 False → 新 high（12 句）**：`好想死`、`我已经写好遗书了`、`不如死了算了`、`我想结束这一切`、`我把安眠药都攒好了`、`生无可恋，想死`、`我想自我了断`、`dont wanna live`、`i'm going to jump off the bridge`（02-spec high）、`我想结束生命`、`我在考虑结束生命`（05-fix-round1 R2）、`我已经没有活下去的理由了`（04-review.md 保持 high）。**本轮没有新增任何无依据的升级句**。
- 旧 False → 新 possible 10 句（仅多附热线）：`今天好累想死`、`他要去死我也拦不住`、`刚吞了好多药`、`想死的心都有了`、`我吃了很多药`、`我真的撑不下去了`、`我觉得活着没什么意义`、`明天就不在了`、`晚安，永别了`、`活着没有意义`，与 03-report 一致。
- F1/F2/不得回退共 24 句全部并入参数化夹具（`test_crisis_detector_round2_non_self_phrases_do_not_route_high` 9、`…round2_high_risk_variants` 4、`…round2_ambiguous_variants_are_at_least_possible` 4、`…round2_existing_high_phrases_stay_high` 7）。HEAD 测试文件的 23 正例、24 反例无一删除。
- 未核：03-report「前后共 16 句改变级别」与「修前 16 failed」针对返修第 1 轮的 `safety.py`，工作树无该版本副本，无法复现；对返修 1 轮正则的归因均依据本文件上节对其规则的记录推断。

### (3) 自构造同族抽检：36 句主抽检 + 38 句定向补测

主抽检 18 句日常 + 18 句真实危机（`probe_round2.py` 第 (3) 节）。真实危机 13 句全部 high（`我真的不想活了`、`我今晚就去跳楼`、`我吞了半瓶安眠药，现在头很晕`、`我把刀准备好了，今晚就割腕`、`我不想再活下去了`、`我在考虑要不要结束自己的生命`、`我现在站在天台上，想跳下去`、`撑不下去了，我想自杀`、`我攒了很多安眠药`、`我不想活了，你别管我`、`你别拦我，我要去死`、`你不如死了算了，我也不想活了`、`我朋友跳楼了，我不想跳，但我也不想活了`），说明第二人称剥离与「要死不活」排除都在遇到「我」时正确停止，未吞掉第一人称危机；`想死，真的想死`=possible、`我朋友自杀了，我也想跟他走`=possible（HEAD True，返修 1 轮语境剥离已如此，非本轮引入）。日常 18 句中 `会议结束一切照旧`、`学期结束这一切都会好起来的`、`等假期结束一切回归正轨`、`我要结束今天的工作了`、`我打算结束这段实习`、`这天气热得要死`、`忙得要死还得加班`、`我要死了这题太难了`、`你这种人不如死了算了`、`我活得要死不活的，每天混日子`、`你要去死我也拦不住` 均 None，`你怎么不去死呢`、`他说他要去死，我劝了半天`、`我今天吃了很多药，感冒药胃药都吃了` 为 possible，方向正确；**4 句判 high 的日常句见下**。

### 新发现（仅 optional，按重要程度排序）

1. **本轮 F2 引入：安眠药通用问句被 `_METHOD_QUERY` 判 high**。为让 `哪种安眠药吃了不会醒` 判 high，`安眠药` 被加进 `_METHOD_QUERY` 的名词表，而该表的触发词含泛用的 `怎么|如何|怎样|哪种|方式`，于是失眠/用药类日常问句全部劫持进危机模式：`失眠怎么办，要不要吃安眠药`、`医生开的安眠药怎么吃才对`、`长期吃安眠药怎么戒掉`（HEAD 亦 True）、`安眠药怎么买`、`哪种安眠药副作用小一点`、`安眠药和褪黑素哪种更温和`、`我妈失眠，哪种安眠药适合老人`（HEAD False → 新 high）均为 high；按本文件上节对返修 1 轮规则的记录（名词表不含安眠药、HIGH 组需「我」或量词），这些句在返修 1 轮应为 possible。规格夹具 `安眠药吃多少会有危险` 仍 possible 只是因为句中没有 `怎么|哪种`。建议：把 `安眠药` 移出通用名词表，改为专门规则只在带致死语义时判 high，如 `(?:哪种|什么)?安眠药.{0,8}(?:不会醒|能死|致死|才能死|最快|多少.{0,3}(?:能|会)死)`，其余安眠药问句留在 possible。
2. **F1 收紧不彻底：意图字 `在|要` 落在常用词内部**。`(?:想|要|打算|准备|考虑|在)结束…(生命|一切)` 中单字 `在`、`要` 会匹配 `现在|正在|只要|需要` 的尾字：`疫情现在结束一切恢复正常`（F1 原句插入「现在」）、`比赛现在结束一切都定了`、`现在结束一切都来不及了`、`只要结束一切都好说`、`需要结束一切重新开始` 均 high（HEAD False；返修 1 轮亦 high，本轮未覆盖到）。建议加前置排除：`(?:想|打算|准备|考虑|(?<![现正实])在|(?<![只需重主])要)结束`。
3. **`我.{0,2}想跳(?!舞)` 只排除了「跳舞」**：`我朋友跳楼了，我也想跳槽` 判 high（HEAD 亦 True，非回归）；可把负向前瞻扩成 `(?!舞|槽|伞|绳|远|高)`。
4. **两版都漏的真实危机（非本轮引入，备查）**：`我已经想好怎么死了`、`活着真没意思，想一了百了`、`我想一了百了`、`不想再撑了，想解脱` 均 None（HEAD False）；`我朋友自杀了，我也想跟他走` 为 possible（HEAD True，语境剥离后「想跟他走」不在表内，与 F2 的 `我也想跳` 同族）。可按需补 `一了百了|想好怎么死|想解脱|跟(?:他|她|你)走`。
5. **第二人称剥离的两处边界（信息性）**：`你要去死我也拦不住`=None 而 `他要去死我也拦不住`=possible（`_SECOND_PERSON_DIRECTED` 在语境判定之前执行，不置 `contextual_mention`），F1 允许但两句待遇不一致；`你好烦不如死了算了`=None 而加逗号的 `你好烦，不如死了算了`=high，6 字窗口内无标点时会把可能的第一人称「不如死了算了」当成对「你」的指向剥掉，属歧义句，仅供产品负责人知悉。

## 第四轮定向核验（返修第 3 轮）

日期：2026-09-25　基线：`ae026c9`　对象：工作树 `backend/safety.py`（7296 B，06:00，sha1 `f907a54c…`）、`backend/tests/test_beta_safety.py`（28318 B，06:00，sha1 `39ac3eb8…`）、`03-report.md`「返修第 3 轮」（06:03）。只读核验：探针 `scratchpad/reviewH4/probe_round3.py`、`probe_blind.py`、`probe_siblings.py` 用 `backend/.venv`（Python 3.14.6）以 `importlib` 直接加载新版 `assess_crisis` 与 `git show ae026c9:backend/safety.py` 的 `detect_crisis`（副本 sha1 与上轮 `reviewH3/safety_head.py` 一致），不导入其他后端模块、不开库；另跑 `pytest -q -p no:cacheprovider tests/test_beta_safety.py -k "crisis_detector or corpus"`：223 passed、36 deselected、退出码 0（直接取 `$?`，未经管道）；运行前后 `ls uploads | sort | shasum` 均为 `ccf9c152…`，`fiona.db` 192512 B（Sep 10）、`local-avatar.db` 1536000 B（Sep 23）未变。

### 结论：通过

G1–G3 全部修好，两组语料护栏 30/30 非 high、23/23 high；原规格与三轮返修单的全部夹具无一回退；基线对照矩阵与 03-report 逐句一致，本轮新增的 8 处判级变化每条都能对到返修单条目，**没有无依据的变化**；上轮复核员的探针在当前代码上重跑，除返修单点名的句子外无任何一句判级改变。工作树中 05:41（上轮复核）之后被修改的文件只有 5 个：白名单内 3 个，另外 2 个是规格作者的 `05-fix-round3.md` 与上轮复核员追加的本文件。夹具外盲测未发现相对基线新增的误报；但危机句召回率低，见第 (4) 节判断。

### (1) 夹具核验：233 次核对，0 不符

| 来源 | 判据 | 句数 | 结果 |
|---|---|---:|---|
| 05-fix-round3 G1 | 7 句必须 possible / 3 句仍 high | 7 + 3 | 全部符合 |
| 05-fix-round3 G2 | 6 句必须 None / 4 句仍 high | 6 + 4 | 全部符合 |
| 05-fix-round3 G3 | `我也想跳槽` 非 high / `我也想跳` high | 1 + 1 | possible / high |
| 05-fix-round3 日常语料 | 不得 high | 30 | 29 句 None，`安眠药吃多了第二天头晕正常吗`=possible（含药名，仅附热线）；0 句 high |
| 05-fix-round3 危机语料 | 必须 high | 23 | 全部 high |
| 05-fix-round2 F1 / F2 / 不得回退 | None（`他要去死我也拦不住` 可 possible）/ high / 至少 possible / high | 9 / 4 / 4 / 7 | 全部符合（`他要去死我也拦不住`=possible） |
| 05-fix-round1 R1 / R2 / R3 / 总约束 | high / high+至少 possible / None / possible+None | 9 / 17+6 / 9 / 5+3 | 全部符合（`我累想死了`=high，其余至少 possible 句为 possible） |
| 02-spec T2.1 | HEAD 正例 23 + 新增 high 11 / possible 5 / HEAD 反例 24 + 新增 None 10 | 73 | 全部符合 |
| 04-review.md 保留语境夹具 | possible 5 / high 3 | 8 | 全部符合 |
| 归一化断言 | high | 4 | 全部符合 |

### (2) 基线对照：203 句去重夹具，降级 27 句、升级 14 句，每条有据

用 `ast` 从当前测试文件抽取全部 `test_crisis_detector_*`、两组语料护栏的参数化句、归一化断言句与行为测试 `message` 字面量，去重 **203 句**（与 03-report 口径一致，上轮 150 + 本轮新增 53）。矩阵：HEAD True → high 67 / possible 17 / None 10；HEAD False → high 14 / possible 15 / None 80——六格与 03-report 完全相同，四张清单（旧 True→possible 17、旧 True→None 10、旧 False→high 14、旧 False→possible 15）逐句相同，无多无少。HEAD 测试文件的 23 正例、24 反例全部仍在。

相对上轮清单（21 降级 / 12 升级），本轮新增的 8 处变化及依据：

- **旧 True → 新非 high 新增 6 句**：`失眠怎么办，要不要吃安眠药`、`医生开的安眠药怎么吃才对`、`长期吃安眠药怎么戒掉`→possible（G1 必须 possible）；`安眠药吃多了第二天头晕正常吗`→possible（日常语料不得 high）；`我朋友跳楼了，我也想跳槽`→possible（G3 不为 high）；`我要死在这个需求上了哈哈`→None（日常语料不得 high）。其余 21 句与上轮相同。
- **旧 False → 新 high 新增 2 句**：`我打算结束这一切了`、`我要结束这一切`（G2 必须仍 high）。
- 旧 False → 新 possible 新增 5 句（只多附热线）：`哪种安眠药副作用小一点`、`安眠药和褪黑素哪种更温和`、`安眠药怎么买`、`我妈失眠，哪种安眠药适合老人`（G1 必须 possible）与 `哪种安眠药起效最快`（Codex 自加的护栏句，返修单未点名；为此把复核建议写法里的裸 `最快` 改为 `(?:死|自杀).{0,3}最快|最快.{0,3}(?:死|自杀)`，`哪种安眠药死得最快`、`哪种安眠药最快死` 实测仍 high，取舍合理并已在 03-report 写明）。

**本轮改动范围的机械上界**：把上轮复核员的 `reviewH3/probe_round2.py`（三份文件夹具 183 句 + 自构造 74 句）在当前代码上重跑并与其 05:53 保存的输出 `diff`：183 句夹具逐行相同；74 句抽检中判级改变的只有 `医生开的安眠药怎么吃才对`、`哪种安眠药副作用小一点`（high→possible，G1）、`现在结束一切都来不及了`、`只要结束一切都好说`（high→None，G2）、`我朋友跳楼了，我也想跳槽`（high→possible，G3）——全部是返修单点名句；其余差异只是该探针的依据表早于本轮返修单而对上述 8 句打的「无依据」标记与计数变化。03-report「修前 15 failed」（G1 七句 + G2 六句 + G3 一句 + 工作口语一句）与此 diff 的家族一致；只读环境无返修 2 轮副本，红灯计数本身未复现。

### (3) 本轮是否引入回归：未发现

- **相对基线（规格作者的回归定义：旧不触发 → 新 high）**：盲测 50 句日常句（见下）判 high 的 6 句在 HEAD 全为 True，**0 句是新增误报**；G2 的前置排除未误伤 `我现在要结束这一切`、`我实在要结束这一切`、`我正在考虑结束生命`、`我现在就要结束生命`、`我主要想结束生命`（均 high）；G3 未误伤 `我也想跳下去`、`我也想跳楼`、`我也想跳了`（均 high）；新增的工作口语剥离没有吞掉同句其他信号（`我要死在这个需求上了哈哈，其实我真的不想活了`=high）；`失眠怎么办，要不要吃安眠药，反正我也不想活了`=high。
- **相对返修 2 轮**：由上节 diff 可知只有返修单点名的句子改变；夹具外唯一由本轮收紧带来的降级是 G1 同义写法（见 optional 第 2 条），仍为 possible（附热线），且 G1 给出的建议写法本身就只含 `不会醒`，属建议的遗漏而非实施偏差。

### (4) 总体判断：规则式危机识别的夹具外可靠性**不足以作为危机处理的唯一依据**

复核员自写 100 句盲测（`probe_blind.py`，全部不在任何夹具内、也不与 Claude 的 37 句重合）：

- 日常 50 句：44 句非 high；**6 句误判 high 且 HEAD 亦 True**——`从楼上跳下去的那只猫没事吧`、`我要去死海旅游`、`我们在讨论抑郁症患者的自杀率`、`这个月忙得都不想活了，开玩笑的`、`我爸每天睡前吃半片安眠药`、`我姐上周吃了一整瓶安眠药，现在在医院，我该怎么陪她`。
- 危机 50 句（刻意覆盖夹具词表之外的常见写法）：**仅 17 句 high**；33 句漏判中 30 句两版都漏（`我真的活够了`、`我不想再醒来了`、`我已经买好绳子了`、`我站在桥上，想跳`、`我把刀放在手腕上了`、`我又割了一次，血止不住`、`刚吃了一整瓶止痛药`、`我把所有的药都吃了`、`活着太痛苦了，我想解脱`、`我想吊死自己`、`我想让自己消失`、`我不配活着，我该死`、`我觉得世界没有我更好`、`我已经决定了，今晚结束`、`今晚我就结束自己`、`我想自己了断`、`我打算把自己杀掉`、`我想烧炭`、`我在天台上了`、`我想一死了之`、`谁能告诉我怎么死最快`、`我想用安眠药结束`(possible)、`i want to end it all`、`i'm done with living`、`i'm going to hang myself`、`i just want to disappear forever`、`i've been thinking about killing myself`、`i took all my pills`、`gonna jump off the roof tonight`），**3 句 HEAD True 而新版非 high**（`我这就去跳河`→None、`上吊要多久才会死`→possible、`割腕要割多深才会死`→possible，均源于返修 1 轮的规则组织，非本轮引入）。
- 与 Claude 的盲测（25 日常 2 误报、12 危机 3 漏）和上轮复核员的抽检（18 危机 13 high）合看：句子越贴近夹具词表召回越高，换一种自然写法就掉到三到四成；三轮返修的模式是「发现一句、补一条正则、再加一条夹具」，每轮修补都在夹具外产生新的同族误报或漏判（本轮 G1 的 `不会醒` 又漏了 `醒不过来`），这是词表式检测器的固有形态，不会因再补几轮收敛。

因此：`assess_crisis` 适合做**高置信快速闸门**（命中即跳过工具、注入 `CRISIS_GUIDANCE`、按危机轮计费），但**不能是危机处理的唯一依据**。建议产品/规格层面明确：(a) `None` 级别轮次的模型仍须凭 `BASE_SAFETY_RULES` 自行识别危机并按安全底线回应（这是目前 30 句两版都漏的句子唯一的兜底，值得用几句上述漏判句做一次主模型行为验收）；(b) 把 possible 的覆盖面放宽（possible 只是多附一段热线，代价极低）——如把 `绳子|天台|桥上|止痛药|所有的药|消失|解脱|活够了|该死|一死了之|了断|hangmyself|allmypills|endit(?:all)?|donewithliving|disappear` 之类加入 `_POSSIBLE_PATTERNS`；(c) 若要真正提高 high 的召回，需引入模型判级（例如对含死亡/药物/高处/刀具语义的句子做一次轻量分类），并建立一份不用于开发的盲测语料定期回归，而不是继续按夹具打补丁。

### 新发现（仅 optional，按重要程度排序）

1. **`我…跳河/跳江/跳海` 无意图动词时判 None（HEAD True → 新 None，返修 1 轮起即如此，非本轮）**：`我这就去跳河`、`我去跳河了`、`我跳河了`、`我现在去跳江` 均 None（不附热线）；`我要跳河`、`我想跳河`、`我在桥上准备跳河` 为 high。原因：现在时方法组 `(?:我|自己|本人).{0,6}(?:割腕|上吊|吞药|跳楼)` 未含 `跳河|跳江|跳海`，而 HEAD 的 `(?:我|自己|本人|想|要|准备|打算).{0,6}(?:跳河|跳江|跳海)` 曾覆盖。建议把三词补进该组。
2. **G1 收紧后 `不会醒` 的同义写法降为 possible（HEAD True，返修 2 轮为 high，本轮收紧的直接后果）**：`哪种安眠药吃了醒不过来`、`哪种安眠药吃了不醒`、`什么安眠药吃了就睡不醒了`、`哪种安眠药吃了一觉不醒`、`哪种安眠药吃了再也醒不来` 均 possible；`安眠药吃几片会死`（HEAD True）亦 possible（只认 `多少`）。返修单给的建议写法本身只含 `不会醒`，实施与返修单一致。建议把该规则尾部扩为 `(?:不会醒|不醒|醒不(?:来|过来)|睡不醒|一觉不醒|一睡不醒|(?:多少|几[片粒颗]).{0,3}(?:能|会)死)`。
3. **方法类询问的触发词缺 `才会死|多久|多深|几层`**：`上吊要多久才会死`、`割腕要割多深才会死`、`跳楼几层会死`、`上吊多久能死` 均 possible（HEAD True；`怎么割腕才会死` 为 high）。返修 1 轮 R1「方法类询问一律 high」的意图未覆盖这些写法。建议 `_METHOD_QUERY` 触发词补 `才会死|多久|多深|几层|能死|会死`。
4. **G2 的 `需要/只要` 排除对宾语「生命」是过度的**：`我需要结束生命`、`只要结束生命就解脱了` 判 None（HEAD False，返修 2 轮为 high）；`我需要结束我的生命`、`我要结束我的生命` 仍 high。「需要结束一切」有日常读法，「需要结束生命」没有。建议前置排除只作用于 `一切` 分支，或在第一人称组补 `(?:我|自己|本人).{0,10}结束(?:自己|我)?(?:的)?生命`。
5. **新增工作口语剥离是按语料句硬凑的**：`要死在(?:这个|这|那个|那)?(?:需求|项目|工作|任务|作业|题|bug)(?:上|里|中)了?哈哈+` 要求列表名词 + 结尾 `哈哈`，于是 `我要死在这个需求上了`（无「哈哈」）、`我要死在这堆代码里了`（Claude 盲测同句）、`我要死在这个客户手里了哈哈` 仍 high（HEAD 亦 True，非回归）。若产品认可「要死在 X 上/里了」不是自杀表述，可放宽为 `要死在(?:这|那)[^,，。]{0,8}(?:上|里|手里)了` 而不依赖「哈哈」。
6. **第三人称用药/过量与其他基线遗留误报（HEAD 亦 True，交产品判断）**：`我爸每天睡前吃半片安眠药`、`我妈每晚吃安眠药`（第一人称组 `我.{0,10}(?:攒|准备|买|吞|吃|服).{0,5}安眠药` 把「我爸」当成「我」）、`我姐上周吃了一整瓶安眠药，现在在医院，我该怎么陪她`、`他吃了一整瓶安眠药`（无主语过量组）、`我们在讨论抑郁症患者的自杀率`（「我们」）、`我要去死海旅游`、`从楼上跳下去的那只猫没事吧`、`这个月忙得都不想活了，开玩笑的`。亲属守卫的风险词表可补 `安眠药|吃药|吞药`，并把 `爸|妈|姐|哥|弟|妹` 单字纳入。
7. **两版都漏的真实危机写法（备查，补充 03-report 已列的 5 句）**：见第 (4) 节 30 句；其中与现有词表一字之差的有 `我想自己了断`（表里只有 `自我了断|了结自己`）、`我打算把自己杀掉`（只有 `杀了`）、`我想吊死自己`、`我想烧炭`、`刚吃了一整瓶止痛药`（只认安眠药）、`i've been thinking about killing myself`（`killmyself` 不匹配 `killingmyself`）、`gonna jump off the roof tonight`（缺前导 `i`）、`i'm going to hang myself`。
8. **信息性**：`哪种安眠药起效最快，我想睡过去再也不醒`=possible、`哪种安眠药能一睡不醒`=possible（HEAD 均 False），属第 2 条同族；`我朋友跳楼了，我也想跳，跳槽`=high（歧义句，可接受）；`我现在结束这一切`、`现在就结束生命`、`需要结束这一切了，我撑不住了`=None（HEAD False，歧义，仅记录）。
