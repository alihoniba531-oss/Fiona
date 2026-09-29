# 复核报告：恢复内测前的代码加固

日期：2026-09-25　基线：`main` @ `ae026c9`　复核对象：工作树 `git diff` + 未跟踪 `backend/tests/test_beta_session_revival.py`、`backend/tests/test_event_loop_slots.py`

复核方式：三位独立复核员（T1 会话复活 / T2 危机分级与计费 / T3 事件循环与数据库）各自只读复核并在临时库跑探针；本报告由总结人对每条 must_fix 亲自复现（`git show HEAD:backend/safety.py` 与新版逐句对照、临时库 pytest 探针、WAL 恢复探针），不成立的已降级或删除。全部探针脚本与日志在 `scratchpad/reviewH/`（仓库外）。

## 结论：不通过

T1（会话复活）与 T3（事件循环）实现扎实，未发现必须修复项。T2（危机分级）虽然规格列出的三级夹具全部通过，但与基线 HEAD 逐句对照后发现三类**行为回归**：明确的第一人称危机句被降为 `possible`（其中方法类询问会被真实执行联网搜索）、无主语/正在进行的自伤句被降为 `possible` 甚至 `None`、以及「亲人/宠物快要死了」被升为 `high` 劫持进危机模式。这直接违反规格目标 2「明确的第一人称危机走危机支持……日常口语不受影响」。另有一条部署手册回滚步骤在 WAL 下会回放残留 `-wal`，属数据完整性缺陷。共 4 条必须修复（R1–R4），9 条可优化。

## 验收标准逐条核验（规格第 5 节 1–9）

| # | 标准 | 结果 | 证据 |
|---|------|------|------|
| 1 | 全量 pytest 通过；逐文件通过；前后 `uploads`/`*.db` 不变 | 通过 | 总结人重跑：`1014 passed, 13 warnings in 29.51s`，退出 0；前后 `ls uploads \| sort \| shasum` 均为 `ccf9c152…`，`fiona.db` 192512 B（Sep 10）、`local-avatar.db` 1536000 B（Sep 23）未变。逐文件 45/45 由 Claude 机械验证完成。 |
| 2 | `compileall -q -x '\.venv' .` 退出 0 | 通过 | 总结人重跑，退出 0。 |
| 3 | T1 复现：旧 token 认证失败、新用户名 `tester03` | 通过 | `tests/test_beta_session_revival.py` 3 项通过；T1 复核员探针：HEAD 副本下同场景「sv=0、再发码得 tester02、旧 token 认证为 tester02」，新代码下全部反转；并发 10 删号 × 10 发码无撞名；手机号路径与 `get_or_create_user` 重建后旧 token 均为 `None`。 |
| 4 | T2 三级夹具全过；high/possible/None 行为测试通过 | **字面通过，但分级质量回归（见 R1–R3）** | `tests/test_beta_safety.py` 全部通过（含规格全部夹具）。但 HEAD→新版逐句对照发现约 30 句「HEAD 判危机、新版非 high」与 9 句「HEAD 不触发、新版 high」的回归，均由总结人在临时库探针实跑确认路由后果。 |
| 5 | T3 循环延迟测试通过，且有「修改前失败」记录 | 通过 | 新代码 2 passed；HEAD 副本上 `1 failed`（Claude 5.69s / 报告 5.82s，`database is locked`）。 |
| 6 | 剩余 `sqlite3.connect` 调用点不在事件循环请求路径 | 通过 | 剩 `intent_router.py:213`、`mode_switcher.py:118`（槽位 helper）、`analyze.py:85`（CLI）。20 处外部调用点全部 `await asyncio.to_thread(...)`；T3 复核员用「_slot_conn 在运行中事件循环线程被调用即记录」插件跑全套件：正控先抓到 2 条，正式运行 0 条违规。 |
| 7 | `tsc` 0、`lint` 0 错 ≤28 警、`build` 成功 | 通过 | Claude 机械验证：tsc 0、lint 0 错 28 警、默认 Turbopack 构建成功。 |
| 8 | `git diff -- frontend` 只含 `page.tsx` 流式事件改动，无 className 变化 | 通过 | `git diff --name-only -- frontend` 仅 `frontend/app/page.tsx`（+7 行）；diff 中 `className` 出现 0 次。 |
| 9 | `git status` 路径都在白名单内 | 通过（基线例外） | 修改/新增路径均在白名单；唯一例外是任务开始前已存在的未跟踪 `02-spec.md`（规格本身，非实现方产物）。本报告 `04-review.md` 由复核流程写入。 |

## 必须修复项

### R1　`_CONTEXTUAL_MENTIONS` 把明确的第一人称危机句整体剥掉，降为 `possible`；方法类询问因此被放行到联网搜索

- **位置**：`backend/safety.py:34`（亲属模式中段 `[^,，。；;!?！？]{0,14}` 可以跨过第二个「我」）、`backend/safety.py:35`（查询模式动词表含 `写|问|看看|了解`，不要求信息/救助语境）。
- **证据**（总结人 `summ_compare.py`，HEAD → 新版）：`我妈妈走了我也不想活了` True→possible；`我对象跟我分手了我想死` True→possible；`我孩子没了我想死` True→possible；`我朋友都不理我了我想自杀` True→possible；`我想写遗书然后自杀` True→possible；`我想问你我是不是该自杀` True→possible；`我想了解怎么自杀最快` True→possible；`我看看哪种自杀方式最快` True→possible；`帮我查一下怎么割腕不疼` True→possible。
- **失败场景**（临时库 pytest 探针实跑）：输入 `帮我查一下怎么割腕不疼` → `assess_crisis`='possible' → `recognize_intent` 返回 None 后被 `services/chat_service.py:813-828` 的正则兜底判成 `web_search` → `execute_intent` 收到 `('web_search', {'query': '怎么割腕不疼'})` → 返回搜索卡片，热线只作为卡片后的附注。输入 `我妈妈走了我也不想活了` → 'possible' → 普通路径，system prompt 不含 `CRISIS_GUIDANCE`，只在末尾附热线。基线 HEAD 上以上句子全部判 True 并跳过工具直接危机支持。
- **修复要求**：以上 9 句必须为 `high`，且 `帮我查一下怎么割腕不疼` 的行为测试要断言 `execute_intent` 未被调用、首事件为 `{"crisis": true}`。同时规格夹具 `帮我查下割腕的急救方法`、`他说他不想活了，我该怎么劝` 与现有 `我朋友说想死，我该怎么劝`、`我想研究自杀预防`、`我想写一篇自残报道`、`我一点也不想死`、`我不想自杀` 必须保持 `possible`，`我朋友说想死，我也想死`、`我不想死，但我想自残` 保持 `high`。规则写法自定（建议：中段改为 `[^,，。；;!?！？我]{0,14}` 遇第二个「我」即停；查询模式只在尾部出现 `急救|预防|干预|新闻|报道|论文|研究|心理|数据|怎么劝|如何帮` 之一时才视为语境提及，其余含 `怎么|如何|怎样|哪种|方式|最快|不痛|不疼|才能死` 的方法类询问一律 `high`；把 `写.{0,18}自杀` 这类计划性描述移出 contextual 表）。

### R2　无主语的第一人称危机句、正在进行的自伤/过量服药句相对基线降级为 `possible` 甚至 `None`

- **位置**：`backend/safety.py:39` HIGH 主规则强制要求 `我|自己|本人` 在 10 字内；`:40` 只收字面「不如死了算了」；`:43` 方法规则要求意图动词；`:45-46` 安眠药规则丢掉基线的 `吞|吃|服` 分支；`:27` 日常表达把 `得/到` 设为可选，吞掉「累想死」。
- **证据**（HEAD → 新版）：`不想活了` True→possible；`不想再活了` True→possible；`活不下去了` True→possible；`想自杀`/`打算自杀`/`准备自杀`/`真的想自杀`/`想轻生` True→possible；`活着没意思` True→**None**；`活着没意思，不如死了` True→**None**；`我割腕了`/`我在割腕`/`我刚割腕了` True→possible；`吃了一整瓶安眠药`/`吞了一把安眠药` True→possible；`累死了不想活了` True→possible；`我累想死了` True→None。另 `我想结束生命`、`我在考虑结束生命` 两版都为 None（规格 high 夹具 `想结束自己的生命`、`我想结束这一切` 的近邻写法）。
- **失败场景**（临时库探针实跑）：`吃了一整瓶安眠药`、`我割腕了`、`不想活了` → 'possible' → 首事件是普通 `text`，prompt 不含 `CRISIS_GUIDANCE`，可能进入镜子/意图分支，仅末尾附热线；`活着没意思，不如死了` → None → 不附热线、不做任何危机处理，且若含硬词还会拼接反问附录。基线 HEAD 对这些句子全部判 True 并走危机支持。中文口语省略主语极常见，「不想活了」「我割腕了」是最典型的第一人称危机表达，属规格目标 2 的「明确的第一人称危机」。
- **修复要求**：以下句子必须为 `high`：`不想活了`、`不想再活了`、`活不下去了`、`想自杀`、`打算自杀`、`准备自杀`、`真的想自杀`、`想轻生`、`活着没意思，不如死了`、`我割腕了`、`我在割腕`、`我刚割腕了`、`吃了一整瓶安眠药`、`吞了一把安眠药`、`累死了不想活了`、`我想结束生命`、`我在考虑结束生命`。以下句子至少为 `possible`（不得为 None）：`活着没意思`、`我累想死了`、`今天好累想死`。同时保住 `他说他不想活了，我该怎么劝`、`今天新闻说有人跳楼了`、`安眠药吃多少会有危险`、`让我去死吧哈哈哈哈` = `possible`，`累死了今天`、`气得我想死`、`我不想活得太累` = None。规则写法自定（建议：新增无主语 HIGH 组 `(?:不想(?:再)?活(?!得)|活不下去|活着没(?:有)?(?:意思|劲).{0,8}(?:不如死|想死|自杀)|不如死了|(?:想|要|打算|准备|计划|考虑).{0,4}(?:自杀|轻生|去死|死了算了)|(?:想|在)?(?:考虑)?结束(?:自己|我|这)?(?:的)?(?:生命|一切))`；第一人称现在时方法 `(?:我|自己|本人).{0,6}(?:割腕|上吊|吞药|跳楼(?![价机]))`；过量服药 `(?:吞|吃|服)(?:了|下|光)?.{0,4}(?:一整?瓶|一把|整瓶|全部|所有|很多|好多)安眠药`；为保住第三人称夹具，在 contextual 表加入 `(?:他|她|有人|别人|某人)[^,，。；;!?！？我]{0,14}(?:想死|不想(?:再)?活|自杀|轻生|自残|自伤|跳楼)` 先行剥离；`:27` 改为 `(?:困|忙|饿|热|累|气|吓|笑)(?:死(?:了)?|(?:得|到)(?:我)?(?:快)?(?:要|想)?死(?:了)?)` 不再吞「累想死」）。

### R3　「要死」丢掉基线的 `(?!了)` 前瞻，谈论亲人/宠物病危的普通句被劫持进危机模式

- **位置**：`backend/safety.py:39` `要死(?![你他她它])`，HEAD 为 `要死(?!了|[你他她它])`。
- **证据**（HEAD → 新版）：`我爷爷快要死了` False→high；`我妈快要死了` False→high；`我觉得他要死了` False→high；`我的猫要死了` False→high；`我狗快要死了` False→high；`我怕我妈要死了` False→high；`我要死了` False→high；`我快要死了` False→high；`我妈快要死了，我好难过` False→high。
- **失败场景**（临时库探针实跑 `我爷爷快要死了，我好难过`）：首事件 `{"crisis": true}`，system prompt 注入 `CRISIS_GUIDANCE`，`recognize_intent` 未被调用（镜子/意图全部跳过），模型被指令「询问对方现在是否安全、鼓励拨打紧急服务」，回复末尾强塞 120/110/12356 热线；前端按危机轮渲染。基线 HEAD 上该句走正常陪伴回复。违反规格目标 2「日常口语不受影响」。
- **修复要求**：以上 9 句必须为 None（`我要死了，笑死`、`我快要死了好困` 等既有 None 夹具保持）。建议恢复 `要死(?!了|[你他她它])`；可选地在 HIGH 主规则窗口内排除第三方主语（他|她|它|爷爷|奶奶|爸|妈|猫|狗）。补一条行为测试：`我妈快要死了，我好难过` 首事件不是 `{"crisis": true}` 且 `recognize_intent` 被调用。

### R4　WAL 开启后，部署手册「回滚与恢复」会把残留的旧 `fiona.db-wal` 回放到恢复后的数据库

- **位置**：`docs/DEPLOYMENT.md:388-398`「回滚与恢复」仍是「`systemctl stop fiona` → 把备份恢复到 `/var/lib/fiona/fiona.db` → 启动旧代码」；全文只在 `:312` 说不要把 `-wal/-shm` 当备份，没有任何一步要求恢复前清掉 `fiona.db-wal`/`fiona.db-shm` 或先 checkpoint。`CLAUDE.md:66` 声明「所有生产命令、备份和回滚步骤以 docs/DEPLOYMENT.md 为准」。
- **证据**（总结人重跑 `probe_wal.py`，临时库）：`init_db`(WAL) → 写入 `before_backup` → backup API 生成快照 → 另一连接写 `after_backup` 且不干净关闭（`-wal`/`-shm` 残留）→ `copyfile` 用快照覆盖主文件 → 重新打开读 `users` 得 `['after_backup', 'before_backup']`，即旧 WAL 帧被应用到了恢复后的库。
- **失败场景**：生产回滚时后端曾被 SIGKILL/崩溃（`-wal` 未 checkpoint 也未删除），运维按手册 `cp` 备份覆盖 `fiona.db` 并启动 → SQLite 把与备份不匹配的旧 WAL 页回放进去 → 恢复出的库含本应回滚掉的数据，或（备份与旧 WAL 页布局不一致时）页面不一致/损坏，而手册声称已「恢复到备份时间点」。此风险由本次启用 WAL 引入，属规格 T4「凡改变事实……逐处更新」的遗漏。
- **修复要求**：在「回滚与恢复」增加明确步骤：停服后先确认 `/var/lib/fiona/` 下不存在 `fiona.db-wal` 与 `fiona.db-shm`（存在则先对旧库执行 `sqlite3 fiona.db "PRAGMA wal_checkpoint(TRUNCATE)"` 后删除，或直接删除这两个文件），再复制备份覆盖主文件，启动前跑 `sqlite3 fiona.db "PRAGMA integrity_check"`；并在 `03-report.md`「需要人工确认」补一句该事实。

## 可优化项

- **O1（T2）报告「已知误判」披露不完整**：`03-report.md` 只列 3 句，未做 HEAD 对照；规格 T2.1 要求诚实披露。修完 R1–R3 后应补「与基线对照」一节（HEAD 判 True 而新版非 high 的句子应只剩规格明确要求的 possible/None 夹具；新版判 high 而 HEAD 判 False 的句子逐条说明）。已并入下方 Codex 指令。
- **O2（T2）引号/转述语境仍判 high**（基线同样如此，非回归）：`这句歌词是‘我想死’，你怎么看`、`他在小说里说我想死`、`我们班有人自杀了`、`我读了一篇关于自杀的文章`、`我不会轻生的` → high。可在归一化后把 「」『』“”‘’ 内片段替换为占位再匹配，并把 `(?:歌词|小说|电影|新闻|文章|报道|论文).{0,10}(?:自杀|想死|轻生)` 加入 contextual 表。
- **O3（T2）Claude 抽查的边缘句建议纳入 possible**：`我真的撑不下去了`、`晚安，永别了`、`明天就不在了` 目前 None（不附热线）；`想死的心都有了` = possible 合理。建议把 `撑不下去|永别|(?:不想|不会)再醒来|明天(?:就)?不在了` 加入 `_POSSIBLE_PATTERNS`。
- **O4（T2）possible 轮搜索卡片后的热线文本会被自动朗读**：`frontend/app/page.tsx` 卡片分支 `clearTtsQueue()` 并把 tip 挂到 `pendingTtsText`（不自动播），随后 `{"text": "\n\n"+NOTE}` 走 `data.text` 分支 `flushSentences()` → 开启语音时立即朗读热线。可有意保留但应在报告写明；若要一致，前端在 `cardData` 存在时不对后续 text 走朗读。
- **O5（T1）随机 sv 上界 `2**63-1` 撞顶后 `session_version+1` 溢出为 REAL**：`backend/database.py:354`、`:1569` 用 `secrets.randbelow(2**63 - 1) + 1`；`:687/:721/:759` 三处 `+1`。总结人验证 `9223372036854775807+1` → `9.223372036854776e+18`(real)，此后 `+1` 不再变化，该账号 logout/revoke/rotate 永远撤销不掉旧 JWT。概率约 k/2^63，实际不会发生，但零成本可消除：改为规格示例的 `2**31 - 1`。
- **O6（T1）本次部署前已删除的 `testerNN` 未回填 `retired_usernames`**：存量库若最大编号恰是删号，发布后会再发一次该名（旧 token 不会复活，只违反「永不回收」字面）。线上库已下线、影响很小；可在 `init_db` 加幂等回填，或在报告披露。
- **O7（T1）删号与邀请码兑换交错留下无邀请码绑定的孤儿账号**：`routers/auth.py:91-94` `redeem_invite` 与 `get_or_create_user` 是两个事务；毫秒级窗口内兑换方拿到指向空账号的 Cookie，过期后无法再登录。非复活、属既有竞态；可合并进同一 `BEGIN IMMEDIATE`，或在报告披露。
- **O8（T3）过期槽位清理「非事务 SELECT → 无条件 DELETE」，to_thread 后可删掉并发请求刚写入的新鲜 pending**：`backend/intent_router.py:242-257`、`backend/mode_switcher.py:188-200`。T3 复核员钩住 `_is_expired` 复现：A 读到过期行 → B `set_pending` 写新鲜行 → A 的 DELETE 删掉 B 的行 → `get_pending` 返回 None。建议条件删除 `... AND expires_at IS ?`（用读到的原值做 CAS）或 `BEGIN IMMEDIATE` 包住。
- **O9（T3）回归网薄弱 + 运维属主**：(a) `tests/test_event_loop_slots.py:61-72` 只有 `detect_and_save` 一处是生产协程，`/chat` 主路径 16 处 `to_thread` 包裹没有任何测试守护，改回同步调用全套件仍绿；建议在两处 `_slot_conn` 开头加「运行中事件循环线程禁止访问」守卫（或 conftest autouse 桩），并补用例触达 `chat_service.py:796`、`:1046`。(b) `docs/DEPLOYMENT.md` 管理脚本/备份未写明执行账号，root 在停服时跑脚本被中断会残留 root 属主的 `-wal/-shm`，服务账号随后无法写库；建议注明 `sudo -u fiona` 或事后 `chown`。

## 给 Codex 的二次修改指令（仅不通过时，逐条可执行、自包含）

背景：仓库 `/Users/yangjing/Desktop/ai-workspace/Fiona`，基线 `ae026c9`，当前工作树含 2026-09-25 加固改动（未提交）。你只需在现有工作树上继续修改，**不得回滚任何已完成工作**，不得 `git add/commit/stash/reset/checkout`。白名单同规格第 2 节：`backend/**`（不含 `.env*`、`*.db`、`uploads/**`）、`docs/DEPLOYMENT.md`、`docs/tasks/2026-09-25-beta-hardening/03-report.md`；本轮不需要改前端与其他文档。所有测试在 `backend/` 下用 `.venv/bin/python -m pytest -q -p no:cacheprovider` 运行；运行前后 `ls uploads | sort | shasum` 与 `ls -l *.db` 必须一致。

### 指令 1（R1+R2+R3）：修正 `backend/safety.py` 的分级规则，并补「基线对照」参数化测试

1. 在 `backend/tests/test_beta_safety.py` 新增三个参数化测试（名字固定，便于验收）：
   - `test_crisis_detector_baseline_high_phrases_stay_high`：断言 `assess_crisis(m) == "high"`，参数为：
     `我妈妈走了我也不想活了`、`我对象跟我分手了我想死`、`我孩子没了我想死`、`我朋友都不理我了我想自杀`、`我想写遗书然后自杀`、`我想问你我是不是该自杀`、`我想了解怎么自杀最快`、`我看看哪种自杀方式最快`、`帮我查一下怎么割腕不疼`、`不想活了`、`不想再活了`、`活不下去了`、`想自杀`、`打算自杀`、`准备自杀`、`真的想自杀`、`想轻生`、`活着没意思，不如死了`、`我割腕了`、`我在割腕`、`我刚割腕了`、`吃了一整瓶安眠药`、`吞了一把安眠药`、`累死了不想活了`、`我想结束生命`、`我在考虑结束生命`。
   - `test_crisis_detector_ambiguous_phrases_are_at_least_possible`：断言 `assess_crisis(m) in ("possible", "high")`，参数为：`活着没意思`、`我累想死了`、`今天好累想死`、`我真的撑不下去了`、`晚安，永别了`、`明天就不在了`、`想死的心都有了`。
   - `test_crisis_detector_dying_relatives_and_hyperbole_stay_none`：断言 `assess_crisis(m) is None`，参数为：`我爷爷快要死了`、`我妈快要死了`、`我觉得他要死了`、`我的猫要死了`、`我狗快要死了`、`我怕我妈要死了`、`我要死了`、`我快要死了`、`我妈快要死了，我好难过`。
2. 先运行 `tests/test_beta_safety.py` 确认这三个新测试**当前失败**（把失败计数写进报告），再修改 `backend/safety.py` 让它们通过，同时文件内**所有既有夹具**（`test_crisis_detector_recognizes_required_phrases`、`test_crisis_detector_marks_related_talk_possible`、`test_crisis_detector_separates_contextual_mentions_from_personal_risk`、`test_crisis_detector_rejects_required_everyday_phrases`、`test_crisis_detector_normalizes_case_and_whitespace`）必须继续通过。规则写法自定；R1/R2/R3 各自的「修复要求」段给了可用的正则建议，关键约束是：
   - 第三人称守卫（`他|她|有人|别人|某人` + 危机词）与亲属守卫（`我(?:朋友|…)` + 危机词）要在 HIGH 判定前剥离，但剥离范围遇到第二个「我」必须停止；
   - 查询/研究类语境只在尾部出现 `急救|预防|干预|新闻|报道|论文|研究|心理|数据|怎么劝|如何帮` 之一时才降为 possible，含 `怎么|如何|怎样|哪种|方式|最快|不痛|不疼|才能死` 的方法类询问判 high；
   - 恢复 `要死(?!了|[你他她它])`；
   - 日常表达规则不得吞掉「累想死」「累死了不想活了」中的危机词。
3. 在 `backend/tests/test_beta_safety.py` 补三条行为测试（可参考同文件 `test_possible_crisis_keeps_tool_routing_billing_resources_and_trace` 与 `test_crisis_chat_bypasses_existing_mirror_mode` 的写法）：
   - `test_method_query_never_reaches_tools`：消息 `帮我查一下怎么割腕不疼`，monkeypatch `services.chat_service.execute_intent` 与 `recognize_intent` 为记录桩，断言首事件 `{"crisis": True}`、两者都未被调用、事件中含 `CRISIS_RESOURCE_NOTE`。
   - `test_ongoing_self_harm_gets_crisis_support`：对 `我割腕了`、`吃了一整瓶安眠药` 参数化，断言首事件 `{"crisis": True}`，且模型 system prompt 以 `CRISIS_GUIDANCE.strip()` 结尾。
   - `test_dying_relative_keeps_normal_routing`：消息 `我妈快要死了，我好难过`，monkeypatch `recognize_intent` 返回 `{"intent": None, "params": {}, "missing": []}` 并记录调用，断言首事件不是 `{"crisis": True}`、`recognize_intent` 被调用一次、prompt 不含 `CRISIS_GUIDANCE.strip()`、事件中不含 `CRISIS_RESOURCE_NOTE`。
4. 跑全量 `pytest`、`compileall -q -x '\.venv' .`，确认 1014+新增 全部通过。

### 指令 2（R4）：补 `docs/DEPLOYMENT.md`「回滚与恢复」的 WAL 步骤

在「恢复前先停后端：`systemctl stop fiona`」之后、「确认备份文件和目标路径后再执行恢复」之前，插入一段并附命令块：停服后必须先检查 `/var/lib/fiona/` 下是否残留 `fiona.db-wal`、`fiona.db-shm`；若存在，先对**旧库**执行 `sqlite3 /var/lib/fiona/fiona.db "PRAGMA wal_checkpoint(TRUNCATE)"` 再删除这两个文件（或在确认不需要旧库未落盘数据时直接删除），然后才能把 `.backup` 快照复制到 `/var/lib/fiona/fiona.db`；启动前执行 `sqlite3 /var/lib/fiona/fiona.db "PRAGMA integrity_check"` 必须输出 `ok`；恢复后的文件属主须为 `fiona:fiona`。说明原因：SQLite 打开数据库时会无条件回放同目录下匹配的 `-wal` 帧，残留的旧 WAL 会把备份时间点之后的页写回恢复后的库。

### 指令 3（O1，随 R1–R3 一起完成）：更新 `docs/tasks/2026-09-25-beta-hardening/03-report.md`

1. 在「已知边界与人工确认」前新增「与基线对照」一节：用 `git show ae026c9:backend/safety.py` 的 `detect_crisis` 与新版 `assess_crisis` 对规格全部夹具 + 指令 1 的三组句子逐句对照，列出（a）HEAD 判 True 而新版非 high 的句子（修复后应只剩规格明确要求为 possible/None 的夹具，逐条注明「规格要求」），（b）HEAD 判 False 而新版判 high 的句子（逐条说明理由）。
2. 把 O2/O3/O4 列入「已知边界」（引号/转述语境判 high；`撑不下去`/`永别` 类目前 None 或 possible 的取舍；possible 轮卡片后热线会被朗读）。
3. 在「需要人工确认」补：WAL 恢复前须清理残留 `-wal/-shm`（指向 `docs/DEPLOYMENT.md` 新增步骤）。
4. 记录指令 1 第 2 步「修改前失败 N 项 / 修改后全部通过」的两次输出。

### 交付判据

- `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` 全绿，且 `tests/test_beta_safety.py` 中指令 1 的六个新测试名全部存在并通过；
- `.venv/bin/python -m compileall -q -x '\.venv' .` 退出 0；
- `git status --porcelain --untracked-files=all` 中本轮新增/修改的路径只有 `backend/safety.py`、`backend/tests/test_beta_safety.py`、`docs/DEPLOYMENT.md`、`docs/tasks/2026-09-25-beta-hardening/03-report.md`；`git diff -- frontend` 与本轮开始时相同。
