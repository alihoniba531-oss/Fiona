# WO3e 导演知识库 + 交叉审核：独立复核（L3）

- 复核对象：基线 `4b45346` + `.review/wo3e.diff`（111 个文件；diff 的文件集合与副本工作区改动逐一核对一致）。
- 复核方式：只看落盘产物，自己跑测试、探针与变异。实现方报告只当线索用。
- 环境说明：本机 shell 的 `NO_PROXY` 里有 `[::1]`，httpx 收集期会报 `InvalidURL`，导致 16 个非 studio 模块收集失败。这是环境问题，与本单无关。下文所有 pytest 都用 `env -u NO_PROXY -u no_proxy -u HTTP_PROXY -u HTTPS_PROXY PYTHONDONTWRITEBYTECODE=1 <py> -m pytest -p no:cacheprovider …` 运行。
- 副本还原：复核前后对全部受版本控制及未忽略的文件（共 1797 个）做 sha256 比对，结果一致。用过的临时探针测试 `backend/tests/test_studio_zz_review_probe.py` 和 `frontend/tsconfig.tsbuildinfo` 都已删除。临时脚本只放在 `/tmp/wo3e-review/`。

---

## 1. 结论

**不通过。**

§12 的 1–8 条和 6a 条按字面都能举出证据，现有测试也全绿。但重点审的计费与试拆数据流里，发现 5 处会导致错账、超上限或付费结果丢失的缺陷（M1–M5），全部有可复现的探针证据。另有 3 处变异存活（M6），说明 §12 第 4 条和 §5 的渲染格式没有被测试真正证明。lint 内置规则 1、2 还有明显的漏报和误报（M7）。

---

## 2. §12 逐条核验

| # | 验收项 | 结论 | 证据 |
|---|---|---|---|
| 1 | `pytest -k studio` 全过；tsc、lint 0 error | ✅ | `cd backend && <py> -m pytest -q tests/ -k studio` → **`1765 passed, 5550 deselected, 32 warnings in 73.44s`**，0 failed、0 skipped（汇总行里没有 skipped）。`cd frontend && npx tsc --noEmit` → exit 0。`npm run lint` → `✖ 25 problems (0 errors, 25 warnings)`，exit 0；警告都在既有文件里（如 `app/plaza/page.tsx`）。 |
| 2 | 卡片 schema、id 唯一、引用存在；场景卡 19 张，恰 2 张带 position；§3.6 的 id 全在；样卡逐字节不变 | ✅ | 探针 `/tmp/wo3e-review/cards.py` 的输出：`counts {'grammar': 13, 'model': 5, 'negative': 21, 'scene': 19}`；`scene with position ['scene-cliffhanger', 'scene-opening-hook']`；`missing required []`；`scene_types covered == §4 True`。`loader.load_library()` 在加载时完成全库校验，包括重复 id、文件名、引用和 YAML 重复键（`loader.py:116-171`）。样卡 sha256 为 `d99982df…3673d`（dialogue）和 `72e48fd0…5129`（fight），与 `02-dispatch-phase2.md:57-58` 给出的派单值一致。 |
| 3 | `select_materials` 确定、≤8000、template/position/model 永远保留、opening→opening-hook、位置卡类型 422 | ✅（有附注） | 探针 `/tmp/wo3e-review/sel2.py` 穷举 17 类 × 3 个位置 × 2 个视频模型 × 3 档写实度 × 敏感标记有/无，共 612 组。每组两次调用的 JSON 逐字相同，`chars == len(text) <= 8000`（最大正好 8000），也都包含「【template id】」。position 和 model 卡只要存在，就带「【id】」头。`test_position_and_model_selection`、`test_position_scene_type_is_422` 均通过。**附注**：`realism=3d` 时万相和 Seedance 都没有 3d 卡，也没有 `any` 卡，所以 model 为 None（共 204 组，见 P3）。fight + opening + seedance 时反例被裁到 0 张（见 P4）。 |
| 4 | lint 拦下 6 类内置问题和 model/negative 数据驱动规则（各有用例） | ⚠️ 字面通过，但证明不足 | `test_studio_kb_core.py:201-271` 各有用例。但两处变异存活：**变异 D**（`when` 型 model 规则被整体关闭）和**变异 E**（反例卡渲染格式被改），见下文变异表与 M6。内置规则 1、2 在中文提示词里有明显漏报和误报，见 M7。 |
| 5 | 报价只确认一次；过期或超上限 409；两模式各 1 次导演调用；带 KB 每镜有 basis；不联网 | ⚠️ 字面通过，但高风险面不通过 | `test_quote_confirm_once_expiry_and_daily_cap`、`test_two_modes_each_one_director_call_and_with_kb_basis` 通过。另做了并发探针：5 个协程同时 `kb_trial.start` 同一报价，结果为 `[409, 409, 409, 'ok', 409]`，只建了 4 个 job，只调度 1 次。**但**：修正重试后的付费结果会丢（M4）；重启后试拆永久卡住（M3）；Claude 月额度被绕过（M2）；混合币种报价错标（M1）；审核预留不是上界（M5）。 |
| 6 | 旧库（d11b60d / 4b45346）init_db 补出两表和 `review_provider`，旧项目为 qwen；连跑两次正常 | ✅ | `test_studio_kb_migration.py` 通过。我另用 git 历史里**真实的** d11b60d、4b45346 `STUDIO_TABLES_DDL`（AST 提取，脚本 `/tmp/wo3e-review/mig.py`）建库，插入旧项目后连跑两次 `init_db`。两个形态的输出都是 `True ('qwen',) True True True ('ok',)`，依次对应：有该列、旧项目为 qwen、两表存在、新索引存在、WO3d 补列索引存在、integrity ok。之后 `get/set_review_provider` 读写正常。新索引 `idx_studio_exemplars_owner_scene` 只引用新表自己的列，和建表放在同一批 DDL 里，不需要放进 `_ADDED_COLUMN_INDEXES`；`review_provider` 没有索引。删号时两张新表在同一事务里删除（`database.py:916-919`，`commit` 在 `:929`）。变异 A 能被测出。 |
| 6a | deepseek 导演 + qwen 审核走 DashScope、model 为 qwen3.8-max；off 不发审核、报价不含审核费；审核失败结果完整；PATCH 非法值 422；不联网 | ✅ | `test_deepseek_director_qwen_review_goes_to_dashscope` 和 `test_trial_sends_two_shot_plans_to_director_and_two_reviews_to_qwen` 用 httpx `MockTransport` 断言 host 为 `dashscope.aliyuncs.com`、`model == "qwen3.8-max"`、DeepSeek 端只收到 `shot_plan`。`test_off_sends_no_review_and_quote_has_no_review_fee`、`test_review_failure_is_recorded_but_trial_result_stays_complete`、`test_trial_keeps_shot_results_when_review_raises`、`test_review_provider_patch_and_validation`（`bogus` → 422；他人项目 → 404）均通过。 |
| 7 | 七个页签四态齐全，390px 不横向滚动 | ✅（主控已验，我抽查） | `KbWorkbench.tsx:20-27` 有七个页签；`:67-76` 有未登录、加载、未开放、错误、成功各态。用 grep 检查 `font-(semibold|bold|…)|fontWeight|<b>|<strong`，新文件里 0 处。390px 下的效果沿用主控结论。 |
| 8 | 每块一份 `03-report-<块>.md` | ✅ | A、B、C、D1、D2、D3、D4 共 7 份都在。 |

### 2b. 高风险面核验摘要（详细问题见第 3、4 节）

**计费**
- 只能确认一次：在 `BEGIN IMMEDIATE` 里检查 `status='open'`（`kb_trial.py:547-563`）。并发探针确认只有 1 个成功。✅
- 15 分钟过期：`kb_trial.py:443`、`:559-560`。✅
- 日上限与单次上限：`spend.check_brain_budget` 在报价时（`:446`）和确认时（`:561`）各调一次。但报价时这次检查删掉后所有测试照样通过（变异 B），见 M6。
- 并发确认不重复扣费：✅。
- 审核费计入报价与预留：已计入；`off` 时不计。✅ 但**审核预留低估**，见 M5。
- 混合币种：上限检查用分币种的 `totals`，没有被单一的 `total` 污染。但**展示口径错误**（M1）；**USD 月额度对占位任务漏计**（M2）。

**单发规则**
- `_execute_brain` 先做 CAS `queued→running`（`brain_jobs.py:284-286`），再取适配器并发请求。调度器 `dispatch_queued` 与 `_run_trial` 同时调用 `_background` 时，后到的一方得到 409，被 `_background` 吞掉，不会二次付费。✅
- 唯一的第二次付费是 WO3a 允许的「不合格修正一次」。
- 错误分类只认 `exc.status_code` 是否为 int 且落在 4xx（`brain.py:258-270`）；正则只用来校验上游 code 字符串的格式。变异 C（把 429 判成 uncertain）被 `test_studio_brain_core` 测出 6 处。✅

**交叉审核数据流**
- 路由都依赖 `studio_user`；store 读写都带 `owner` 和 `archived=0` 过滤（`store.py:417-437`）。✅
- `ReviewProviderBody` 用 Literal 限定取值，非法值返回 422。✅
- 失败摘要都取固定文案（`cross_review.py:10-19`、`brain.py:268-270`）。后台任务出错时只打印异常类型（`utils/background_tasks.py:21-24`）。`kb_trial` 和 `cross_review` 都没有日志输出。✅

### 2c. 内容抽查（对照 `00-house-rules.md`）

抽查范围：
- 场景卡：confrontation、chase、scare、intimacy，加两张位置卡 opening-hook、cliffhanger。
- 模型卡：seedance-2-5-photoreal、wan-3-photoreal，加 seedream-5。
- 反例卡：unverified-model-syntax、photoreal-face-seedance、giant-offscreen-camera-move、looking-at-camera。

| 规则 | 结论 |
|---|---|
| 人物不看镜头 | ✅ 各卡的 camera 字段都写了「视线落在…，不看镜头」；示例用侧后、背对。 |
| 每镜 ≤3 个动作 | ✅ 抽查的示例镜都不超过 3 个，例如 chase 第 2 镜是「跨过水洼 / 绕开推车 / 跟拍」。 |
| 敏感镜头固定机位 | ✅ 结构、材质、触碰点、巨物都写了固定机位；scare 卡写明「巨物始终在画外」加锁定句。 |
| 写实正脸绕开肖像闸 | ✅ 各卡写了 Seedance 用侧后、逆光剪影、约 65° 俯拍、背影，正脸改用万相。 |
| 英文运镜术语不裸写 | ✅ 渲染后的 scene 和 model 文本里没有裸写的 Dolly/Crane 等（扫描脚本 `/tmp/wo3e-review/eng.py`）。英文术语只出现在 grammar 卡的 `avoid`/`entries` 和反例卡的 `wrong` 字段，这是有意为之。 |
| 未核实写法不写成定论 | ✅ Seedance 2.0 时间戳、万相时间戳、万相版权时点、参考价都标了「待作者实测核实」；schema 强制每条 facts 注明「实测」或「官方」（`schema.py` 的 `_validate_model`）。 |
| 位置卡只写「额外做什么」 | ⚠️ beats 和 coverage 符合要求。但两张位置卡的 camera 第 4–6 条（不看镜头、至少 4 秒、写实不脏）和 opening-hook 的 IP 拦截风险，都是通用规则的重复，不是位置专属。每张卡渲染后约 1.3–1.4k 字，会把反例挤出预算（见 P4）。 |
| tags 写法混用 | ❌ 确有混用。grammar 卡里有的同时写 `face-closeup` 和 `face_closeup`，有的只写其中一种。`grammar-axis-eyeline`、`grammar-camera-movement`、`grammar-insert-closeup`、`grammar-shot-reverse-shot` 只有连字符写法，而 `SceneTags.sensitive` 用下划线，所以 `face_closeup` **永远命中不到这 4 张**。把两种写法归一后重跑，51 组（17 类 × 3 个位置，sensitive=face_closeup）里有 **28 组**选出的语法卡会变（`/tmp/wo3e-review/tags.py`），见 P2。schema 的 `_TAG_RE` 同时接受 `-` 和 `_`，是混用的根源。 |

另有一处文字小瑕疵：confrontation 卡的 camera 写「压力升级用固定机位加轻微推轨」，固定机位与推轨在字面上自相矛盾。

### 2d. 变异（每次只改一处 → 跑测试 → `cp` 还原 → `cmp` 与 sha256 校验）

| 编号 | 位置 | 改法 | 跑的测试 | 结果 |
|---|---|---|---|---|
| A | `database.py:918` | 删号列表去掉 `"studio_exemplars"` | `tests/ -k "studio or delete or account"`（1856 项） | **测出**：`test_delete_account_removes_kb_rows` 失败 |
| B | `kb_trial.py:446` | 报价时的 `check_brain_budget` 改成 `pass` | `tests/ -k studio`（1765 项） | **存活**：1765 passed |
| C | `brain.py:260` | `400 <= status < 500` 改成 `< 429`（429 被当作 uncertain） | `tests/ -k studio` | **测出**：`test_studio_brain_core` 6 项失败 |
| D | `lint.py:229` | `matched = False and _when_matches(...)`，即关闭全部 `when` 型 model 规则 | `tests/ -k studio` | **存活**：1765 passed |
| E | `retrieval.py:229` | 反例卡头部 `【id】标题：要点` 改成 `[id] 标题: 要点` | `tests/ -k studio` | **存活**：1765 passed |

每次还原后的 sha256 与原文件一致，分别为 database `0e13b709…`、kb_trial `605dad40…`、brain `029d08a4…`、lint `318b23b2…`、retrieval `040452f4…`。

---

## 3. 必须修复项

### M1 混合币种报价被错标为单一币种（默认配置就会触发）

**位置**
- `backend/studio/kb_trial.py:353-372`（`_public_quote`：`:369` 把各行跨币种相加，`currency` 取导演模型的币种）
- `frontend/components/studio/kb/KbQuoteDialog.tsx:28-32`（逐行和合计都按 `quote.currency` 格式化）
- `frontend/lib/studio-kb.ts:122-130`（`KbQuote` 没有 `totals`，也没有逐行币种）

**失败场景**
- 项目默认导演是 `claude`（`config.py:118`），默认审核是 `qwen`。
- 探针：导演 Claude、审核 qwen 时，报价返回 `items[*].est` 为 `0.43291 / 0.274296 / 0.43176 / 0.274296`，`"total": 1.413262, "currency": "USD", "totals": {"CNY": 0.548592, "USD": 0.86467}`。
- 前端会把两行审核费（实际是人民币）显示成 `$0.27`，合计显示 `$1.41`，而真实金额是 `$0.86 + ¥0.55`。
- 作者据此确认付费，看到的金额与币种都是错的。

**建议改法**
- 报价每行带 `currency`。
- `total` 只在单一币种时给出；混合币种时给 `null`，或者干脆去掉。
- 前端改为逐行按各自币种格式化，合计显示 `totals` 的分币种金额，例如「¥0.55 + $0.86」。
- `KbQuote` 增加 `totals` 和 `KbQuoteLine.currency`。
- 补后端测试和前端测试，覆盖混合币种的报价结构与展示文本。

### M2 Claude 月额度被试拆占位任务绕过

**位置**
- `backend/studio/spend.py:93-108`（`brain_month_used` 只统计 `kind='brain'`，见 `:99`）
- `backend/studio/kb_trial.py:570-582`（确认时把任务落成 `kind='kb_shot'` 和 `kind='kb_review'`）

**失败场景**
- 导演和审核都用 Claude，`FIONA_STUDIO_BRAIN_MONTHLY_USD` 设成刚够 1 次试拆（报价 `totals.USD=1.32183`，上限 `1.3879`）。
- 连续确认 5 次试拆，全部返回 200。
- `brain_month_used` 一直是 `0.0`，实际 USD 预留已达 `2.894975`，超过上限的 2 倍。
- 正常流程里也有同样的问题：without_kb 的导演任务和两条审核在前一模式跑完之前一直是占位任务，都不计入月额度。这段时间可能长达数分钟，其间别的导演确认会被放行。
- `/studio/access` 显示的 `brain_month_used_usd` 同样偏低。

**建议改法**
- `brain_month_used` 改为统计 `kind IN ('brain','kb_shot','kb_review')`，或者让占位任务从一开始就是 `kind='brain'`，另用独立字段标记「暂不调度」。
- 只要还有其他地方按 `kind='brain'` 统计在途或额度，也一并检查。
- 补测试：Claude 导演连续确认两次试拆，第二次应返回 409。

### M3 进程重启或任务被取消后，试拆永久卡在 running，预留不释放

**位置**
- `backend/studio/kb_trial.py:504-536`（`_run_trial` 只在 `start` 后由 `_schedule` 起一次，`:592-593`）
- `backend/studio/recovery.py:21-26`（只恢复 `kind='brain'` 和非 brain 的在途任务）
- `backend/studio/brain_jobs.py:217-222`（`dispatch_queued` 只派发 `kind='brain'`）
- `frontend/components/studio/kb/KbTrialPanel.tsx:230`（在途时每 3 秒轮询一次）

**失败场景**
- 确认后、`_run_trial` 跑完之前，进程重启或关停取消了任务。
- 探针在确认后执行 `recover_studio_jobs()` 和 `dispatch_queued()`，结果是：派发列表为空；4 个 `kb_shot`/`kb_review` 仍为 `queued`；`get_trial` 一直返回 `running`；当日 `committed_cny` 仍占着 `0.694794`。
- 如果重启发生在 with_kb 已成功之后，审核占位任务也永远不会被激活。
- 前端在页面可见时会一直每 3 秒轮询，每次还会对已有分镜重跑 lint，见 P5。
- 试拆详情里没有 job id，作者也无法从界面取消或释放这些任务。

**建议改法**
- 启动恢复时，找出所有 `items.kind='kb_trial'`、已确认、且仍有 `kb_shot`/`kb_review` 为 `queued` 的报价，重新调度 `_run_trial`。
- 把 `_run_trial` 改成**可续跑**：
  - 某模式的导演任务已是 `brain` 且为终态时，直接取它的结果（含 M4 的修正子任务），继续审核那一步，不能像现在这样 `continue` 跳过；
  - 导演任务是 `brain` 且为 `queued` 或 `running` 时，等它跑到终态；
  - 只有 `kb_shot` 仍为 `queued` 时才激活。
- 项目归档或删号时，取消残留的占位任务。
- 补测试：
  - 确认后不跑 `_run_trial`，模拟重启恢复，试拆应能完成；
  - with_kb 导演已成功、审核仍是占位时续跑，只发审核，不重发导演。

### M4 「不合格修正」成功后，付费结果在试拆里丢失

**位置**
- `backend/studio/kb_trial.py:511-528`（`_run_trial` 只等原 job id）
- `backend/studio/kb_trial.py:613-626`（`get_trial` 只读 `payload["shot_jobs"]` 和 `review_jobs` 里的原 id）
- `backend/studio/cross_review.py:37-52`（`review_record` 同样只看原任务）
- `backend/studio/brain_jobs.py:385`（修正会新建一个 `parent_job_id=原任务` 的 job）

**失败场景**
- with_kb 有硬约束：每镜 basis 不能为空（`brain_tasks.py:173-177`）。模型第一次漏写某一镜的 basis，并不少见。
- 探针中第一次输出不合格、修正后合格，任务表为：
  ```
  ('shot_plan','failed','invalid_output',1,'0.0066'), ('cross_review','cancelled','review_not_needed',…),
  … ('shot_plan','succeeded',None,2,'0.0066')
  ```
- `get_trial` 返回 `with_kb.status == "invalid_output"`，镜头 **0 条**，`review.with_kb is None`，总状态为 `partial`。
- 也就是说：修正调用已付费且成功，但结果不显示；该模式的审核被当成「分镜没有成功产出」取消掉了。
- 审核任务被修正时也一样，原任务显示 `invalid_output`。而且原任务已是终态，`review_pending` 判为否，前端停止轮询，修正后的审核永远看不到。

**建议改法**
- 新增 `_final_attempt(owner, job_id)`，沿 `parent_job_id` 链找到最新一次尝试（按 `attempt` 降序取第一条）。
- `_run_trial` 在等待和判断导演任务状态时用这个最终尝试的状态与输出。
- `get_trial` 的导演结果和审核结果都改用最终尝试。
- `review_pending` 要把「父任务已失败、子任务仍在途」也算作在途。
- 补测试：第一次 basis 为空、修正后合格，断言 with_kb 为 `succeeded` 且有镜头、该模式的审核已发出、详情里显示的是修正后的结果。审核修正也补一个同样的用例。

### M5 审核调用的报价与预留不是上界，实际费用可超出预留

**位置**
- `backend/studio/kb_trial.py:433-438`。代码注释写的是「用目标时长估一个上界」，但实际把 `{"estimated_shot_chars": N}` 当作 shots 数据传入。序列化后只有约 30 个字符，分镜的字数根本没有计入。
- `kb_trial.py:465-473`：激活审核时只更新输入，不调整预留。

**失败场景**
- 输入 3000 字原文、`target_seconds=10`。
- 报价时审核的 `input_chars=5236`，`first_max=¥0.145428`。
- 一份 12 镜分镜（JSON 约 10.5k 字，在 `shot_plan` 8192 token 的输出范围内）组成的真实审核输入为 15721 字，首调上界是 **¥0.239796**，比预留高 65%。
- 结算时 `actual_amount` 按实际用量记，可能超过预留；确认时的日上限检查和展示给作者的报价都偏低。Claude 审核的情况相同。

**建议改法**
- 审核项报价按「原文 + 导演输出上限」估算：在 `estimate_brain` 的输入 token 上加上 `get_task("shot_plan").max_tokens`（再加少量包装开销），或者构造等价长度的占位文本。
- 修正一次的估算同步调整。
- 补测试：用一份接近 `shot_plan` 输出上限的分镜构造审核输入，断言报价的 `first_max` 不低于按真实输入算出的 `estimate_brain`。

### M6 三处变异存活：§12 第 4 条与 §5 的渲染格式没有被测试真正证明

**位置**
- 变异 D：`backend/studio/director_kb/lint.py:229`（`when` 型 model 规则）
- 变异 E：`backend/studio/director_kb/retrieval.py:202`、`:229`（grammar 和反例卡头部格式）
- 变异 B：`backend/studio/kb_trial.py:446`（报价时的额度检查）
- 对应测试：`backend/tests/test_studio_kb_core.py:257-262`、`:91-153`，`backend/tests/test_studio_kb_api.py:179-213`

**失败场景**
- §3.4 规格自己举的 model 规则就是 `when` 型（`seedance-portrait`），但 `_when_matches` 里 6 种条件一种都没有测试。把它整体关掉，测试照样全过。
- §5 要求「卡片文本统一渲染成【卡片 id】标题：要点」，提示词也依赖这个格式来约束 basis 只能引用 kb_text 里的 id。但 grammar 和反例卡的头部格式改掉后测试照样全过。
- 报价时超过单次或当日上限本应返回 409，删掉这次检查后测试照样全过。另外，单次上限 `FIONA_STUDIO_MAX_QUOTE_CNY` 在试拆的报价和确认上都没有测试。

**建议改法（只补测试）**
- **D**：
  - Seedance、写实、`近景`、露脸 → 命中 `seedance-portrait-photoreal`；
  - 改为 anime，或改为「逆光剪影/背影」 → 不命中；
  - 万相、写实、`特写`、露脸 → 命中 `wan-face-closeup`，level 为 `info`。
- **E**：对 `select_materials` 的结果，断言 `grammar` 和 `negatives` 里每张卡的头部都是 `【{id}】{title}：{summary}`，并且 `card_ids` 中每个 id 都在 `text` 里以 `【id】` 出现。
- **B**：
  - 设 `FIONA_STUDIO_MAX_QUOTE_CNY` 为极小值，报价应返回 409，且 `studio_quotes` 不新增行；
  - 先报价、再调低单次上限，确认应返回 409。

### M7 lint 内置规则 1、2 在中文提示词里有明显漏报和误报

**位置**
- `backend/studio/director_kb/lint.py:23-31`（`\b{term}\b` 和英文看镜头正则）
- `lint.py:132-141`（规则 2 的中文短语没有排除否定写法）

**失败场景**（探针 `/tmp/wo3e-review/lintprobe.py`）
- 漏报：Python 的 `\b` 把汉字也当作单词字符，所以英文术语前后紧挨汉字时匹配不到边界。
  - `"镜头做Dolly缓慢靠近"` → `[]`，而 `"镜头做 Dolly 缓慢靠近"` → `['bare-camera-term']`；
  - `"Crane上升"` → `[]`；
  - `"她looks at camera"` → `[]`。
  - 中文提示词通常不加空格，规则 1 基本失效。
- 误报：
  - `"视线落在周默身上，不直视镜头"` → `['looking-at-camera']`；
  - `"避免看向镜头，视线落在钥匙上"` → `['looking-at-camera']`。
  - `shot_plan.md` 提示词本身就要求「人物不直视镜头」，模型照着写就会被报警，两种模式的对比因此被噪声干扰。
  - 反例卡的 `lint_pattern` 已经用 `(?<![不要别])` 处理否定写法，内置规则没有跟上。

**建议改法**
- 英文术语改用 ASCII 边界：`(?<![A-Za-z])Dolly(?![A-Za-z])`，英文看镜头正则同样处理。
- 中文看镜头短语前面 0–2 字内出现 `不/别/勿/避免/不要/禁止` 时不报警。
- 补正反用例：`"做Dolly缓慢靠近"` 应报警；`"不直视镜头"`、`"避免看向镜头"` 不应报警。

---

## 4. 可优化项

**P1 语法卡「先排序再截 5 张」会丢掉模板自己的核心语法卡（需作者裁定）**
- 位置：`retrieval.py:124-136`。
- §5 原文是「依次取 template、position 的 related_grammar，再取命中卡；去重后按 id 排序，最多 5 张」。实现先把所有候选按 id 排序，再截前 5 张，「依次」体现的优先级就没了。
- 实例：
  - dialogue + body + `face_closeup` 时，`over-shoulder`、`shot-reverse-shot`、`shot-size` 被挤掉，换成字母序靠前的 `backlight-silhouette`、`camera-angle`、`lens-focal`；
  - dialogue + opening 同样会丢掉这三张；
  - establishing 加 `face_closeup` 并把标签归一后，会连 `grammar-establishing-shot` 都丢掉。
- 建议：按优先级去重并截到 5 张，再按 id 排序输出。这样仍然确定，也更符合「依次」的本意。改之前请作者确认。

**P2 tags 写法混用导致标签命中不到**
- 4 张 grammar 卡只写了 `face-closeup`，`sensitive=face_closeup` 永远命中不到它们，影响 28/51 组选材。
- 建议：
  - 全库 tags 统一成下划线，或者在 `_tag_tokens` 和卡片两侧都做 `-`/`_` 归一；
  - schema 只允许一种写法；
  - 补测试：`face_closeup` 能命中 `grammar-insert-closeup`。

**P3 写实度为 3d 时没有模型卡**
- 万相和 Seedance 都没有 3d 卡或 `any` 卡，`model=None`，模型卡里的数据驱动 lint 也全部跳过，但界面允许选 3d。
- 建议二选一：增加回落规则（例如回落到 anime 卡并注明「3d 按动漫通道近似」），或者在试拆结果里明确提示「无对应模型卡」。

**P4 位置卡重复通用规则，挤占注入预算**
- 两张位置卡的 camera 第 4–6 条和 IP 风险项是通用规则。
- 后果：fight + opening + seedance 时注入里一张反例都没有；fight + ending 只剩 1 张。
- 建议：删掉这些重复条目，让位置卡只写「位置额外动作」。

**P5 lint 在事件循环里同步读 YAML，GET 试拆会阻塞约 1 秒/模式**
- 位置：`lint.py:212`、`:259`，每个镜头都会调用 `load_cards_of_type`。
- 实测 60 镜 lint 用时 1.035 秒。`get_trial` 每次请求都会对两种模式重算，前端每 3 秒轮询一次，单 worker 进程会被反复阻塞。
- 建议：一次 `lint_shots` 调用只加载一次卡片（或按 mtime 缓存），并用 `asyncio.to_thread` 执行；也可以在任务终态时算一次 lint 并缓存起来。

**P6 lint 的近似规则误报、漏报偏多**
- 规则 4：camera 写「非固定机位」时，因为字符串里含「固定」而被放过。
- 规则 3：只用逗号分隔的 5 个动作数不出来（规格字面允许，可以把「，」后接动词也算作分隔）。
- 规则 2：没有覆盖「正对 / 望向 / 盯着 / 看着镜头」。
- 内置规则 5 与 `seedance-portrait-photoreal` 对同一镜各报一次 warn。
- `seedance-prompt-too-long` 和 `seedream-prompt-too-long` 拿 5 个字段拼接后的长度去比对 2000/1500 字符上限，应该只看 `video_prompt` 或 `first_frame_prompt`。

**P7 节奏统计的「累计集数」不准**
- 位置：`stats.py` 用各场景类型行里 `episodes` 的最大值当总集数。
- 场景类型分散时会低估。例如 5 集各只有一种不同类型，最大值仍是 1，永远不会就绪。
- 建议：增加一条每个 owner 的总计行（如 `scene_type='*'`），或者另建计数表。

**P8 试拆里的 uncertain 任务无法在界面上释放**
- 详情接口不返回 job id。目前只能绕道 `/projects/{pid}/brain/groups/{trial_id}` 查到 id，再调 `/jobs/{jid}/release`。
- 建议：在试拆详情里给出各任务的 id 和状态，并提供「核对后释放」入口。

**P9 `_wait_terminal` 有 300 秒超时，与调度器抢任务时可能误取消审核**
- 位置：`kb_trial.py:486-501`。
- 调度器先抢到导演任务、且该任务跑超过 300 秒时，`_run_trial` 会把仍在 running 的导演任务当成失败，取消该模式的审核。
- 建议：不设超时，一直等到终态。

**P10 `shot_plan` 的 `max_tokens=8192` 对快节奏长戏可能不够**
- 位置：`brain_tasks.py:130`。
- 例如 120 秒的 fight 约 40 镜以上，输出会被截断，按规则记 `invalid_output`：已经付费，却没有结果，也不做修正。
- 建议：按 `target_seconds` 和节奏限制目标时长或镜头数，或者调高 `max_tokens` 并相应调整报价。

**P11 带知识库时，basis 只检查非空，不检查 id 是否真的在 kb_text 里**
- 位置：`brain_tasks.py:173-177`。
- 建议：校验 basis ∩ card_ids 非空（作为硬约束），或者至少报一条 lint warn。

**P12 迁移测试里「d11b60d」形态只是 4 张表的子集**
- 位置：`test_studio_kb_migration.py:24-77`。真实的 d11b60d 有 15 张以上的 studio 表。
- 我用真实 DDL 验证过可以升级，但测试本身没有覆盖。
- 建议：把真实 DDL 嵌进测试。仍不依赖 git 历史。

**P13 工作室首页的「导演知识库」链接不支持 embed**
- 位置：`frontend/app/studio/page.tsx`。
- 链接写死为 `/studio/kb`，主页抽屉 `?embed=1` 打开时会丢掉 embed 参数；而且在 gate 判定之前就显示了。
- 建议：按 `StudioWorkbench` 的做法改用 `studioHref(..., embedded)`。

**P14 反例选取不使用 sensitive，也不看写实度**
- 例子：
  - chase 场景加 `giant_offscreen` 时，拿不到 `negative-giant-offscreen-camera-move`；
  - `negative-photoreal-face-seedance` 在动漫写实度下也会被选中。
- 建议：反例选取也参考 sensitive 与写实度。

**P15 `cross_review.review()` 目前只被测试调用**
- 它走的是不绑定任务的 `run_brain`，每次调用都会新建一个「导演模型」占位项目（`brain_jobs.py:275`）。
- WO4 接入前应改成绑定任务的调用方式。

---

## 5. 给执行者的二次修改指令（可直接派单）

> **WO3e 复核返修 R1**
>
> 工作目录 `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`。Python 用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
>
> 禁止联网、读 `.env`、读或打印 Key、提交。既有测试一字不改，新测试只加在 `backend/tests/test_studio_kb_api.py`、`test_studio_kb_core.py`、`test_studio_cross_review.py`、`test_studio_kb_frontend.py`。只许改下面列出的实现文件。
>
> 如果本机 `NO_PROXY` 含 `[::1]`，pytest 前加 `env -u NO_PROXY -u no_proxy`。
>
> **1. 混合币种报价（M1）**
> - 改 `backend/studio/kb_trial.py` 的 `_public_quote`：每行加 `currency`（取对应 item 的币种）；`totals` 保留；只有全部行同币种时才给 `total` 和 `currency`，否则 `total=null`、`currency="mixed"`。
> - 改 `frontend/lib/studio-kb.ts`：`KbQuoteLine` 加 `currency`，`KbQuote` 加 `totals: {CNY:number; USD:number}`，`currency` 允许 `"mixed"`。
> - 改 `frontend/components/studio/kb/KbQuoteDialog.tsx`：逐行按行内币种显示；合计显示非零的分币种金额，例如「¥0.55 + $0.86」。
> - 测试：导演 claude、审核 qwen 时报价 `total is None`、各行币种正确；前端测试断言混合币种下的展示文本。
>
> **2. Claude 月额度漏计（M2）**
> - 改 `backend/studio/spend.py` 的 `brain_month_used`，统计 `kind IN ('brain','kb_shot','kb_review')`。
> - 测试：Claude 导演、`FIONA_STUDIO_BRAIN_MONTHLY_USD` 设成报价 `totals.USD` 的 1.05 倍，第一次确认 200、第二次确认 409；确认后 `brain_month_used` 大于 0。
>
> **3. 修正后结果丢失（M4）**
> - 在 `kb_trial.py` 新增 `_final_attempt(owner, job_id)`：沿 `studio_jobs.parent_job_id` 找到最新一次尝试。
> - `_run_trial` 里导演任务的等待和判断、审核占位任务的激活与取消，都用最终尝试。
> - `get_trial` 的导演结果、`review_record` 的输入、`review_pending` 判断都用最终尝试。
> - 测试：带知识库第一次有一镜 basis 为空、修正后合格，断言 with_kb 为 `succeeded` 且镜头数正确、该模式的审核已发出、总状态为 `done`。审核第一次 must 排在 should 之后、修正后合格，断言详情里的审核是修正后的结果。
>
> **4. 重启续跑（M3）**
> - `_run_trial` 改成可续跑：
>   - 导演任务仍是 `kb_shot`、`queued` → 激活并执行；
>   - 已是 `brain` 且为 `queued`/`running`/`submitting` → 等到终态，不设 300 秒超时；
>   - 已是终态 → 直接用最终尝试的结果；
>   - 导演成功且审核仍是 `kb_review`、`queued` → 激活审核；导演未成功 → 取消审核占位。
> - 在 `backend/studio/recovery.py` 的 `recover_studio_jobs` 末尾：找出所有 `studio_quotes.status='confirmed'`、`items.kind='kb_trial'`、且还有 `kind IN ('kb_shot','kb_review') AND status='queued'` 的报价，调用 `kb_trial._schedule(trial_id)`。项目已归档的，把占位任务转为 `cancelled` 并清零预留。
> - 测试：
>   - 确认后不执行 `_run_trial`，调用 `recover_studio_jobs()`，再执行被调度的 `_run_trial`，试拆完成且每种模式只有 1 次导演调用；
>   - with_kb 导演已成功、审核仍为占位时续跑，只多 1 次审核调用。
>
> **5. 审核预留上界（M5）**
> - `kb_trial.quote` 估算审核项时，输入 token 按 `ceil(len(原文部分)×1.5) + get_task("shot_plan").max_tokens + 包装开销` 计。可以直接调用 `pricing.estimate_brain_tokens` 和 `estimate_brain_repair` 的同口径函数，不要再传 `{"estimated_shot_chars": …}`。
> - 测试：构造一份 JSON 长度约等于 `shot_plan.max_tokens/1.5` 字的分镜，断言报价里审核项的 `first_max` 不低于按真实审核输入算出的 `pricing.estimate_brain(...)["amount"]`。
>
> **6. lint 内置规则 1、2（M7）**
> - 改 `backend/studio/director_kb/lint.py`：
>   - 英文术语正则改为 `(?<![A-Za-z])term(?![A-Za-z])`，加 `re.IGNORECASE`；英文看镜头正则同样使用 ASCII 边界；
>   - 中文看镜头短语前面 0–2 字内有 `不|别|勿|避免|不要|禁止` 时不报警。
> - 同时让每次 `lint_shots` 调用只加载一次 model 卡和 negative 卡（P5），可以给 `_model_rules` 和 `_negative_rules` 传入卡片元组。
> - `kb_trial.get_trial` 里的 lint 用 `asyncio.to_thread` 执行。
> - 测试：`"镜头做Dolly缓慢靠近"` 报 `bare-camera-term`；`"她looks at camera"` 报 `looking-at-camera`；`"不直视镜头"` 和 `"避免看向镜头"` 不报。
>
> **7. 补测试杀死存活变异（M6）**
> - `when` 型 model 规则：
>   - Seedance、写实、近景、露脸 → 命中 `seedance-portrait-photoreal`；改为 anime 或背影 → 不命中；
>   - 万相、写实、特写 → `wan-face-closeup`，level 为 `info`。
> - 渲染格式：grammar 和反例卡的每个块都以 `【{id}】{title}：{summary}` 开头；`card_ids` 中每个 id 都在 `text` 里以 `【id】` 出现。
> - 额度：
>   - 设 `FIONA_STUDIO_MAX_QUOTE_CNY=0.00000001`，报价返回 409，且 `studio_quotes` 行数不变；
>   - 正常报价后调低该值，确认返回 409。
> - 自测：逐一打入以下 3 个变异，确认对应测试变红，然后还原并核对 sha256：
>   - `lint.py` 里 `matched = False and _when_matches(`；
>   - `retrieval.py` 里反例卡头部改为 `[id] 标题: 要点`；
>   - `kb_trial.py` 里报价时的 `check_brain_budget` 改成 `pass`。
>
> **8. 可选（建议同轮做，改动小）**
> - P2：全库 tags 统一为下划线，或在 `retrieval._tag_tokens` 里把 `-`/`_` 归一；补测试：`face_closeup` 能命中 `grammar-insert-closeup`。
> - P13：`frontend/app/studio/page.tsx` 的知识库链接改用 embed 感知的 href。
>
> **9. 门禁**
> - `cd backend && <py> -m pytest -q tests/ -k studio` 0 failed、0 skipped。
> - `cd frontend && npx tsc --noEmit && npm run lint` 0 error。
> - 新文件不得出现粗体写法。
> - 报告写到 `docs/tasks/2026-10-18-studio-wo3e-director-kb/05-report-r1.md`：逐条列出改动文件与行号、新增测试名、三处变异的自测结果和门禁数字。
> - P1（语法卡截取的优先级）需要作者先裁定，本轮不要改。
