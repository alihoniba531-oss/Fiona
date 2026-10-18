# WO3e 导演知识库：独立复核第 2 轮（只核验 M1–M7、X1–X6 与回归）

- 复核对象：基线 `4b45346` + `.review/wo3e.diff`（全量 116 个文件）；R1 增量见 `.review/r1.diff`（23 个文件）。
- 复核方式：只看落盘产物，自己跑门禁、探针和变异。`05-report-r1.md` 只当线索用。
- 副本核对：
  - 把 `wo3e.diff` 应用到 `git archive 4b45346` 的干净树上，与副本逐个 `cmp`：`checked=116 bad=0`。
  - R1 改动的 23 个文件都在 `06-fix-r1.md` 四个白名单的并集里（含报告）。
  - `database.py`、`store.py`、`brain.py`、`brain_jobs.py`、`routers/studio.py` 本轮都没有改。其中 `database.py` 的 sha256 为 `0e13b709…`，`brain.py` 为 `029d08a4…`，都与第 1 轮记录的一致。
- 运行环境：pytest 统一用 `env -u NO_PROXY -u no_proxy PYTHONDONTWRITEBYTECODE=1 <py> -m pytest -p no:cacheprovider …`。
- 副本还原：
  - 开始前和结束后，各对 1749 个受版本控制或未被忽略的文件做 sha256，两次一致（`HASH_SAME`）；`git status` 前后也一致。
  - 临时探针 `backend/tests/test_studio_zz_r2_probe.py` 和 tsc 生成的 `frontend/tsconfig.tsbuildinfo` 都已删除。
  - 探针脚本、变异脚本和探针测试的副本留在 `/tmp/wo3e-r2-review/`。

---

## 1. 结论

**通过。**

- M1–M7 都已真正修好。凡是第 1 轮探针能复现的场景，我都按原场景重跑过，结果全部符合预期。
- 第 1 轮存活的变异 B、D、E，现在用全量 `-k studio` 都能测出。我另外加了 9 处变异，也全部测出。
- X1–X6 都已按 `06-fix-r1.md` 落实，判定都是「做了」。
- 回归检查没有发现问题。
- 没有新的必须修复项。新发现都列在第 6 节「可优化项」，留给作者裁决。

---

## 2. M1–M7 逐条核验

### M1 混合币种报价 ✅ 已修复

**落点**
- 后端 `kb_trial.py:388-409`（`_public_quote`）：
  - 每行都带 `currency`；
  - `totals` 用 Decimal 按币种累加；
  - 单一币种时 `total` 是数字、`currency` 是该币种；
  - 混合币种时 `total=None`、`currency="mixed"`。
- 前端：
  - `lib/studio-kb.ts:122-134`：`KbQuoteLine.currency`、`KbQuote.totals`、`total: number | null`。
  - `KbQuoteDialog.tsx:9-17`：合计按币种拆开显示。
  - `KbQuoteDialog.tsx:40`：逐行按该行自己的币种显示。

**按第 1 轮场景重跑**（导演 Claude、审核 qwen）
```
M1 items [('with_kb:shot_plan','USD',0.43291), ('with_kb:cross_review','CNY',0.379476),
          ('without_kb:shot_plan','USD',0.43176), ('without_kb:cross_review','CNY',0.379476)]
M1 total None currency mixed totals {'CNY': 0.758952, 'USD': 0.86467}
```
- 逐行相加与 `totals` 一致。
- 审核行的金额从第 1 轮的 0.274296 变成 0.379476，这是 M5 修复后的预期结果。

**前端**
- `test_mixed_currency_quote_shows_per_line_currency_and_split_totals` PASSED。它用 SSR 渲染，断言合计为 `¥0.5486 + $0.8647`，并且不出现 `$1.4133`。
- 我把逐行的 `unit` 和 `est` 都改回按 `quote.currency` 格式化（等于回到旧实现），这个测试变红；还原后 sha256 一致。

### M2 Claude 月额度漏计占位任务 ✅ 已修复

**落点**
- `spend.py:98-100`：`brain_month_used` 改为统计 `kind IN ('brain','kb_shot','kb_review')`。
- `/studio/access`（`routers/studio.py:377`）也调用同一个函数，展示值会跟着修正。

**按第 1 轮场景重跑**
- 设置：导演和审核都用 Claude，开 5 张报价。
- 月上限设为单次报价 `totals.USD` 的 1.05 倍：1.49713 × 1.05 = 1.571987。
```
M2 quote USD 1.49713 limit 1.571987 codes [200, 409, 409, 409, 409] month_used 0.666645 access 0.666645
```
- 第 1 轮这组请求 5 次都返回 200，`month_used` 为 0.0。
- 现在只有第一次成功。
- 首次确认后，`/studio/access` 的 `caps.brain_month_used_usd` 为 0.666645，等于四个占位任务 `first_max` 之和。

**其他按 `kind='brain'` 统计的地方**
- 我 grep 了 studio 目录。美元月额度只有 `spend.py` 这一处 SQL（`confirmed_month` 也只在这里使用）。
- 人民币日额度 `committed()` 本来就不按 kind 过滤。
- `sources.py:476/599` 的「在途导演任务」检查不统计占位任务，但它只管快照同步，与额度无关，见第 6 节 R2-P7。

**变异**：把这条 SQL 改回 `kind='brain'`，`test_claude_monthly_budget_counts_kb_placeholders` 变红。

### M3 重启续跑与归档清理 ✅ 已修复

**落点**
- `kb_trial.py:583-632`：`_run_trial` 可以续跑。
  - 只有 `kb_shot` 且为 `queued` 时才激活；
  - 已经是 `brain` 的任务只等待，不再发；
  - 审核占位按最终尝试的分镜激活；导演没成功时取消审核占位。
- `kb_trial.py:521-535`：`_cancel_quote_placeholders`，只把本报价下仍为 `queued` 的 `kb_*` 改成 `cancelled`，并清零预留。
- `recovery.py:10-39`：新增 `_recover_kb_trials`，在 `recovery.py:101` 调用。
- 启动顺序：`main.py:131` 先执行 `recover_studio_jobs()`，再启动调度器。调度器 `dispatch_queued` 仍然只派发 `kind='brain'` 的任务（`brain_jobs.py:220`）。

**探针**（临时测试复用 `test_studio_kb_api.kb` 夹具，全部离线）

| 场景 | 输出 | 结论 |
|---|---|---|
| a. 第 1 轮原场景：确认后不跑 `_run_trial`，执行 `recover_studio_jobs()` 和 `dispatch_queued()` | `scheduled trials ['238bb6da…']`；`dispatched brain jobs []`；确认后 `committed_cny 0.799974`；续跑后调用为 `['shot_plan','cross_review','shot_plan','cross_review']`，状态 `done`，`committed_cny 0.024`（实际结算） | 能续跑完；导演只调 2 次 |
| b. with_kb 导演已是 `brain/running` 时进程退出 | 恢复后该任务为 `uncertain`，保留预留 0.229026；续跑只发 `('shot_plan', without_kb)` 和一次审核；with_kb 的审核占位为 `cancelled`、预留 0；总状态 `partial` | with_kb 导演没有被重发 |
| c. with_kb 导演已激活成 `brain/queued` 后进程退出；两个 `_run_trial` 与调度器的 `_background` 并发竞争 | 调用为 `[('shot_plan',True),('cross_review',…),('shot_plan',False),('cross_review',…)]`，状态 `done` | 单发规则成立：每个模式只调 1 次导演 |
| d. 项目已归档后重启 | 4 个占位全部 `cancelled`、`reserved_amount 0`、`error_code project_archived`；`committed_cny` 从 0.342612 降到 0.0；USD 月额度从 0.381135 降到 0.0；没有调度；直接执行 `_run_trial` 也是 0 次调用 | 占位已清理，预留已释放 |

**变异**：去掉 `recovery.py:101` 的 `await _recover_kb_trials()` 后，`test_recovery_resumes_confirmed_trial_without_duplicate_director_calls` 和 `test_recovery_cancels_placeholders_for_archived_project` 都变红。

### M4 修正后的结果被详情和审核使用 ✅ 已修复

**落点**
- `kb_trial.py:547-569`：`_final_attempt` 沿 `parent_job_id` 找到最新一次尝试。
- `kb_trial.py:572-580`：`_wait_terminal` 等待最终尝试到终态。
- `kb_trial.py:613-632`：`_run_trial` 判断导演状态、组装审核输入时都用最终尝试。
- `kb_trial.py:716-719`：`get_trial` 的导演结果和审核结果都取最终尝试。
- `kb_trial.py:749-752`：`review_pending` 把 `kb_review` 和 `brain` 两种在途状态都算进去。
- `cross_review.review_record` 拿到的是最终尝试，修正子任务同样是 `kind='brain'`、`task='cross_review'`，可以正常渲染。

**探针（自己构造）**
- with_kb 第一次输出里，镜 2 的 basis 为空，action 写成 `FIRST-ATTEMPT`。
- with_kb 的审核第一次故意把 must 排在 should 之后，并在审核修正**进行中**调用 `get_trial`。
```
M4 status done with_kb succeeded n shots 2 actions ['叶岚把钥匙放在操作台上，周默看向钥匙', '周默说出决定，手指按在台边']
M4 review with_kb succeeded ['must', 'should']
M4 review inputs actions [[…修正后…], […修正后…]]        # 两次审核输入都是修正后的分镜
M4 detail while review repair in flight ('running', 'running')
jobs: shot_plan invalid_output a=1 / cross_review invalid_output a=1 / … / shot_plan succeeded a=2 child / cross_review succeeded a=2 child
```
- 第 1 轮的结果是：with_kb 显示 `invalid_output`、0 镜，审核被取消，总状态 `partial`。
- 现在详情显示修正后的分镜，审核也用修正后的分镜发出。
- 审核修正在途时，总状态是 `running`，不会提前停止轮询。

**变异**：让 `_final_attempt` 永远返回原任务，两个修正用例都变红。

### M5 审核预留是上界 ✅ 已按约定口径修复（附残余风险，见 R2-P1）

**落点**
- `kb_trial.py:356-385`：`_review_quote_item`。
  - 首调输入 token = `ceil(原文×1.5) + shot_plan.max_tokens(8192) + ceil((审核系统提示 + 512)×1.5)`；
  - 修正按 `+cross_review.max_tokens + REPAIR_OVERHEAD_TOKENS` 计；
  - 预留取 `first_max`。
- `kb_trial.py:470-473`：报价改用这个函数，不再传 `{"estimated_shot_chars": …}`。

**按第 1 轮场景重跑**（原文 3000 字）

| 审核方 | first_max（新） | 第 1 轮 |
|---|---|---|
| qwen3.8-max | ¥0.198018 | ¥0.145428 |
| claude-sonnet-5-5 | $0.165015 | — |
| deepseek-v4-pro | ¥0.045526 | — |

- 手算核对 qwen 一行：
  - 输入 token：4500 + 8192 + ceil((2106 + 512) × 1.5) = 16619；
  - 金额：(16619 × 6 + 4096 × 24) / 1e6 = 0.198018，与报价一致。

**判定口径**
- 我自己构造了一份 12 镜分镜，JSON 有 7083 字，审核实际输入为 12289 字。两种算法得到的上界不同：
  - 按「字符 × 1.5」统一估算（第 1 轮探针用的口径），首调上界是 ¥0.208908，比 `first_max` 高；
  - 按「分镜部分取导演输出 token 上限」估算，是 ¥0.19431，不超过 `first_max`。
- 我认为后一种才是真实账单的上界。理由有三：
  - 分镜是导演在 `max_tokens=8192` 以内生成的，回灌时实际 token 数受这个上限约束；
  - 本仓库 `pricing.estimate_brain_repair` 本来就按这个口径算（注释写明「上轮输出以其 token 上限计入，不将生成 token 再当字符放大」）；
  - 第 1 轮第 5 节第 5 条的指令也规定了这个公式。
- 第 1 轮那份 10.5k 字的例子按「字符 × 1.5」算出 ¥0.2398，这个口径本身就把模型输出放大了一遍，所以不再用它作为未修复的证据。
- 残余风险：导演与审核用的是不同厂商、分词器不同时，可能超出上界，见 R2-P1。实际费用按真实用量结算并如实记账（`pricing.brain_actual_cost`），不构成错账。

**变异**：把 `+ shot_max` 改回约 45 token 的旧口径，`test_review_quote_covers_shot_plan_output_upper_bound` 变红。

### M6 存活变异现在都能测出 ✅

每处变异只改一处，跑**全量** `tests/ -k "studio and not zz_r2"`（排除我的临时探针），然后还原并比对 sha256。

| 编号 | 位置 | 改法 | 结果 | 还原后 sha256 |
|---|---|---|---|---|
| B | `kb_trial.py:481`（报价时的额度检查） | 改成 `pass` | **测出**：`test_quote_max_cny_cap_blocks_before_and_after_quote`（1 failed / 1787 passed） | `ee6c78ef…` ✓ |
| D | `lint.py:263` | `matched = False and _when_matches(…)` | **测出**：`test_when_model_rules_for_seedance_and_wan` | `b076beb9…` ✓ |
| E1 | `retrieval.py:238`（反例卡头部） | 改成 `[id] 标题: 要点` | **测出**：`test_select_materials_renders_every_card_header` | `755e9675…` ✓ |
| E2 | `retrieval.py:211`（grammar 卡头部） | 同上 | **测出**：同上 | `755e9675…` ✓ |
| B′（附加） | `kb_trial.py:657`（确认时的额度检查） | 改成 `pass` | **测出**：3 个用例变红 | `ee6c78ef…` ✓ |

另外，在 4 个 kb 测试文件上又补跑了 8 处变异，全部测出：X1、X2、M1、M2、M3、M4、M5、M7（否定词、ASCII 边界各 1 处）。最后一处是前端 M1 的逐行币种变异，已在 M1 一节说明。还原后的 sha256 与 `05-report-r1.md` 第 3 节报告的数值一致。

### M7 lint 内置规则 1、2 ✅ 已修复

**落点**
- `lint.py:23-28`：英文运镜术语改用 `(?<![A-Za-z])term(?![A-Za-z])`，并加 `re.IGNORECASE`。
- `lint.py:31-36`：英文看镜头正则改用 ASCII 边界。
- `lint.py:29-30,121-133`：中文看镜头短语前 0–2 字内出现否定词时不报警。
- `lint.py:157-166`：规则 2 使用上面的判定。

**探针**（真实 `lint_shots`，内容写在 `video_prompt` 里）

| 输入 | 第 1 轮 | 现在 |
|---|---|---|
| `镜头做Dolly缓慢靠近` | `[]` | `['bare-camera-term']` |
| `Crane上升` | `[]` | `['bare-camera-term']` |
| `她looks at camera` | `[]` | `['looking-at-camera']` |
| `视线落在周默身上，不直视镜头` | `['looking-at-camera']` | `[]` |
| `避免看向镜头，视线落在钥匙上` | `['looking-at-camera']` | `[]` |
| `她直视镜头` / `她猛地看向镜头` | — | `['looking-at-camera']`（正例仍能报出） |
| `别看向镜头` / `禁止直视镜头` / `不要直视镜头` | — | `[]` |
| `ORBIT around her`、`She stares into the camera`、`walk toward camera` | — | 都能报出 |
| `Dollyzoom` | — | `[]`（后面紧跟字母，按 ASCII 边界不算命中） |

新发现的边界情况：`她不时看向镜头` 返回 `[]`，是漏报，见 R2-P4。

---

## 3. X1–X6 核验

| 编号 | 判定 | 证据 |
|---|---|---|
| X1 grammar 先按优先级截 5 张，再按 id 排序 | **做了** | `retrieval.py:130-145`：template → position → 标签命中依次去重，`[:5]` 之后再 `sorted`。探针：dialogue + body + `face_closeup` 得到 `['grammar-axis-eyeline','grammar-camera-movement','grammar-over-shoulder','grammar-shot-reverse-shot','grammar-shot-size']`，正好是 dialogue 卡 `related_grammar` 的 5 张，包含指定的 3 张；establishing + `face_closeup` 保留了 `grammar-establishing-shot`。`library.of_type` 按 id 排序（`loader.py:57,158`），结果确定。改回「先排序再截取」的变异被 `test_grammar_priority_keeps_template_related_cards` 测出。 |
| X2 tags 统一 kebab-case | **做了** | `schema.py:110-111,243-245`：正则为 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。探针：`face_closeup` 和 `a.b` 被拒（CardValidationError），`face-closeup` 通过。`retrieval.py:85-97` 在匹配前把输入里的 `_` 换成 `-`，`:140` 卡片一侧也做同样处理。全库 58 张卡（grammar 13 / scene 19 / model 5 / negative 21）：解析后不符合 kebab 的 tag 为 0，原始 YAML 里带下划线的 tag 为 0，重复 tag 为 0。R1 只改了 6 张 grammar 卡的 `tags` 行。两张样卡的 sha256 仍为 `d99982df…3673d`（dialogue）和 `72e48fd0…5129`（fight）。schema 接受 `_` 的变异会被测出。 |
| X3 3d 时 `model_card_missing` | **做了** | 后端 `kb_trial.py:692-705,720,743`；前端 `studio-kb.ts:173`，`KbTrialPanel.tsx:103` 在该栏 header 里显示指定文案。后端和前端各 1 条测试，均 PASSED。全量组合中有 204/612 组 `model=None`，全部是 3d。without_kb 也返回 true，符合「每个模式加」的写法；实现方已把语义问题提给作者（05 报告 §5.2）。 |
| X4 两张位置卡删去通用条目 | **做了** | 两张位置卡的 camera 都从 6 条减到 3 条，删掉的正是第 4–6 条（不看镜头、至少 4 秒、写实不脏）。opening-hook 的 `ai_risks` 从 5 条减到 4 条，删掉的是 IP 拦截项。两张卡 example 里的「单条生成不短于 4 秒」也一并删掉，与「只留位置额外动作」一致。效果：fight + opening + seedance 时注入的反例从第 1 轮的 0 张变为 1 张。附带一处报告笔误：05 报告 §5.5 说 opening-hook 的 `related_negative` 保留了 `negative-ip-lookalike`，实际上 opening-hook 从来没有这一项（它在 cliffhanger 里），见 R2-P8。 |
| X5 规则 4 与提示词长度 | **做了**（按字面） | 规则 4 在 `lint.py:179-183`：`非固定机位，手持跟拍` 报出 `sensitive-nonfixed-camera`，`固定机位` 不报。长度规则在 `lint.py:40-45,257-261`，只量对应字段：Seedance 写实下 `video_prompt` 2100 字时报出；`video_prompt` 1000 字加 `first_frame_prompt` 1500 字时不报。正反用例各有。同类遗漏见 R2-P2、R2-P3。 |
| X6 confrontation 的 camera 改写 | **做了** | `scene-confrontation.yaml:41` 改为「压力升级：人脸镜头用固定机位；非人脸的双人中景可以轻推轨（镜头沿地面缓慢靠近），不做环绕」。自相矛盾已消除。 |

---

## 4. 回归检查

| 项 | 结果 | 证据 |
|---|---|---|
| 门禁 | ✅ | `pytest tests/ -k studio`：**1788 passed, 5550 deselected, 32 warnings in 75.18s**，没有 failed，也没有 skipped。`npx tsc --noEmit` exit 0。`npm run lint`：`✖ 25 problems (0 errors, 25 warnings)`，exit 0。 |
| 单发规则 | ✅ | R1 没有改 `brain_jobs.py` 和 `brain.py`：CAS `queued→running` 与错误分类和第 1 轮相同。M3 场景 c 的三方并发竞争中，每个模式只调 1 次导演。`_wait_terminal` 现在也会等 `queued`；这样即使 `_background` 在 CAS 之前抛异常，调度器之后接手，试拆也不会被当成失败。 |
| 并发确认 | ✅ | 5 个协程同时对同一报价调用 `kb_trial.start`：`[409, 409, 'ok', 409, 409]`，只建了 4 个任务，只调度 1 次。 |
| 删号 | ✅ | R1 没有改 `database.py`（sha256 `0e13b709…`，与第 1 轮一致）。`test_delete_account_removes_kb_rows` PASSED。 |
| 迁移 | ✅ | R1 没有改 `store.py` 和 `database.py`。`test_d11b60d_database_upgrades_and_keeps_project`、`test_4b45346_database_upgrades_and_keeps_project`、`test_review_provider_roundtrip_and_validation` 均 PASSED。 |
| 两张样卡 | ✅ | sha256 与派单值逐字一致，见 X2。 |
| `select_materials` 不变量 | ✅ | 612 组（17 类 × 3 个位置 × 2 个视频模型 × 3 档写实度 × 敏感标记有/无）全部满足：两次调用结果完全相同；`chars == len(text) ≤ 8000`（最大 7997）；grammar 不超过 5 张；template 和 position 的「【id】」都在；只要有 model 卡，它的头部也在；`card_ids` 中的每个 id 都在 text 里出现。坏例 0。 |
| 既有测试 | ✅ | 5 个改动过的测试文件都是 WO3e 新增的，`4b45346` 里已有的测试一字未改。另外，R1 改了 `test_studio_kb_frontend.py` 里本期自己的 2 处旧断言（`quote` 常量补上币种字段；`href="/studio/kb"` 改为 embed 感知）。这是 M1 和 P13 改了契约后不得不改的，只作记录。 |
| 其他已通过项 | ✅ | `test_review_placeholders_are_not_dispatched_before_shots`、`test_one_mode_shot_failure_cancels_only_its_review_hold`、`test_off_sends_no_review_and_quote_has_no_review_fee`、6a 的 DashScope 路由等用例都在全量里通过。 |

---

## 5. 必须修复项

**无。**

第 6 节的新发现都不会直接导致错账、重复扣费或付费结果丢失：
- R2-P1 只影响预留上界，实际费用仍按真实用量结算并记账；
- R2-P5 不会发出付费请求。

---

## 6. 可优化项（新发现，留给作者裁决）

**R2-P1 审核预留上界在跨厂商时仍可能偏低（M5 的残余风险）**
- 现在的公式把分镜部分按导演的 `max_tokens` 计。审核方与导演用同一种分词器时，这是上界。
- 但导演是千问或 DeepSeek、审核是 Claude 时，同样多的中文可能被 Claude 切成更多 token，实际输入可能超过 8192 token 这个假设。
- 粗估最多比预留高约一成。实际费用照实结算，只是日额度或月额度可能被少量突破。
- 建议：按审核方与导演的分词比例加一个系数（例如审核方为 Claude、导演不是 Claude 时 × 1.5）；或者在激活审核时，按真实输入重新估算，再补足预留差额。

**R2-P2 `seedance-anime-prompt-too-long` 仍按 5 个字段拼接后的长度判定**
- 位置：`model-seedance-2-5-anime.yaml:62`。X5 只点名了两条规则，这条同类规则没有覆盖。
- 探针：Seedance、动漫、`video_prompt` 1000 字加 `first_frame_prompt` 1500 字，仍然报出这条，属于误报。
- 建议：把它加进 `_PROMPT_LENGTH_RULE_FIELDS`，对应 `video_prompt`。

**R2-P3 `seedream-prompt-too-long` 在试拆 lint 中永远不会触发**
- 原因：`model-seedream-5.yaml` 的 `model` 是 `seedream-5.0`，而 `_model_rules` 只按 `video_model ∈ {wan, seedance}` 筛选同一系列的卡片。
- 后果：X5 改好的这条规则在试拆里不可达。
- 建议：首帧提示词另外套用 Seedream 卡的规则；或者在卡片说明里注明这条只在出首帧时生效。

**R2-P4 中文否定窗口有漏报**
- 现象：`她不时看向镜头` 不报警。「不时」「不禁」「不由得」这类词都含「不」，落在 0–2 字窗口里就会被当成否定。
- 建议：否定词表改成精确的前缀短语，例如 `不|不要|别|勿|避免|禁止` 必须紧贴短语，或者中间只隔「去/再」，并排除「不时/不禁/不由得/不住」。

**R2-P5 `_wait_terminal` 没有墙钟上限**
- 现象：如果项目在 `_run_trial` 已经过了归档检查之后才被归档，`brain` 任务会因为 `transition` 拒绝而一直停在 `queued`。协程会每 0.25 秒查一次库，直到进程重启。
- 目前没有归档项目的接口，只有直接改库才会触发。实现方已在报告里自述（05 §5.1）。
- 建议：等待循环里每 N 次检查一下项目是否已归档或任务是否已被删除，命中就退出并清理占位。

**R2-P6 前端 M1 测试对「仅 est 改回」的变异不敏感**
- 现象：只把 `est` 改成按 `quote.currency` 格式化时，测试照样通过。原因是同一行前半段的 `unit` 仍按该行币种显示 `¥0.2743`，断言被它满足了。
- 建议：断言完整片段，例如 `= ¥0.2743`。

**R2-P7 快照同步的「在途导演任务」检查不统计 `kb_*` 占位任务**
- 位置：`sources.py:476,599`。
- 试拆不依赖快照，影响很小。可以考虑与 M2 的口径保持一致。

**R2-P8 05 报告的笔误**
- §5.5 说 opening-hook 的 `related_negative` 里保留了 `negative-ip-lookalike`。实际上 opening-hook 从未有这一项，它在 cliffhanger 里。不影响代码。

**沿用的第 1 轮遗留项**
- 按 `06-fix-r1.md` 本轮不做：P6 其余部分、P7、P8、P10、P11、P12、P14、P15。
- 状态与第 1 轮一致，仍然待做。

---

## 7. 给执行者的修改指令

**本轮没有必须修改项。**

如果作者决定处理第 6 节的可优化项，建议合成一单：
1. **R2-P2**：在 `lint.py` 的 `_PROMPT_LENGTH_RULE_FIELDS` 里加 `"seedance-anime-prompt-too-long": "video_prompt"`。补正反用例各 1 条。
2. **R2-P4**：收紧 `_zh_looking_at_camera` 的否定判定，排除「不时/不禁/不由得/不住」。补用例：`她不时看向镜头` 应报警，`不直视镜头` 仍不报。
3. **R2-P6**：在 `test_mixed_currency_quote_shows_per_line_currency_and_split_totals` 里加断言 `= ¥0.2743`。
4. **R2-P1、R2-P3、R2-P5**：涉及计费口径或卡片作用域，需要作者先定方案再派单。
