# WO3e 复核返修 R1 报告

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 依据：`04-review.md` 第 3 节 M1–M7、第 5 节第 1–9 条；`06-fix-r1.md` 主控追加 X1–X6。
- 结论：M1–M5、M6、M7、P5、P9、P13、X1–X6 已落地；复核第 5 节第 1–9 条完成。P6 其余、P7、P8、P10、P11、P12、P14、P15 按本单不做。

## 1. 拆分表

| agent | 负责条目 | 白名单 | 结果 |
|---|---|---|---|
| K 试拆与计费 | M1 后端、M2、M3、M4、M5、M6-B、P9、X3 后端、get_trial lint 线程化 | `kb_trial.py`、`cross_review.py`、`spend.py`、`recovery.py`、`test_studio_kb_api.py`、`test_studio_cross_review.py` | ✅ 32 passed（K 两个测试文件）；全工作室 1788 passed |
| L 取材料与 lint | M7、P5、M6-D、M6-E、X1、X2（schema/retrieval）、X5 | `director_kb/{lint,retrieval,schema,loader}.py`、`test_studio_kb_core.py` | ✅ 48 passed（core）；M7/X5 正反用例齐全 |
| N 卡片内容 | X2 卡片 tags、X4、X6 | `cards/**/*.yaml`（两张样卡除外） | ✅ 58 张卡 schema 通过；改动卡 20 字重合 0 |
| F 前端 | M1 前端、X3 前端、P13 | `lib/studio-kb.ts`、`components/studio/kb/*.tsx`、`app/studio/page.tsx`、`test_studio_kb_frontend.py` | ✅ 18 passed；tsc 0；lint 0 error |
| N 集成修正 R1 | X4 位置卡 example 去掉通用「4 秒」 | 两张位置卡 | ✅ 仅改 2 行；48 passed；重合 0 |

## 2. 逐条改动

### M1 混合币种报价
- `backend/studio/kb_trial.py:388-409`：每行 `currency`；`totals` 用 Decimal 分币种累加；同币种 `total` 数字、`currency` 该币种；混合 `total=null`、`currency="mixed"`。
- `frontend/lib/studio-kb.ts:122-134`：`KbQuoteLine.currency`、`KbQuote.totals`、`total: number | null`、`currency: CNY | USD | mixed`。
- `frontend/components/studio/kb/KbQuoteDialog.tsx:9-17,40-42`：逐行按行内币种显示；合计按分币种显示（如 `¥0.5500 + $0.8600`）。
- 测试：`test_mixed_currency_quote_has_line_currency_and_null_total`（`test_studio_kb_api.py:482`）、`test_mixed_currency_quote_shows_per_line_currency_and_split_totals`（`test_studio_kb_frontend.py:446`）。

### M2 Claude 月额度
- `backend/studio/spend.py:99`：`brain_month_used` 统计 `kind IN ('brain','kb_shot','kb_review')`。
- 测试：`test_claude_monthly_budget_counts_kb_placeholders`（`test_studio_kb_api.py:507`）：第一次确认 200，第二次 409，确认后月额度 > 0。

### M3 重启续跑
- `backend/studio/kb_trial.py:521-535`：归档项目清理占位并清零预留。
- `kb_trial.py:547-569`：`_final_attempt` 沿 `parent_job_id` 取最新尝试。
- `kb_trial.py:572-580`：`_wait_terminal` 去掉 300 秒 deadline，一直等最终尝试终态。
- `kb_trial.py:583-632`：`_run_trial` 可续跑（kb_shot 才激活；brain 在途只等；终态用最终尝试；审核占位按最终分镜激活；失败取消审核）。
- `backend/studio/recovery.py:10-34,101`：启动时找出 confirmed kb_trial 且仍有 queued 占位的报价，重新 `_schedule`；归档项目只清占位。
- 测试：`test_recovery_resumes_confirmed_trial_without_duplicate_director_calls`（`:624`）、`test_resume_after_director_success_only_sends_review`（`:642`）、`test_recovery_cancels_placeholders_for_archived_project`（`:734`）。

### M4 修正后结果丢失
- `kb_trial.py:547-569` 的 `_final_attempt`；`kb_trial.py:708-766` 的 `get_trial` 导演/审核结果、`review_pending` 全部使用最终尝试；`_run_trial` 的等待与判断也使用最终尝试。
- 测试：`test_repaired_shot_output_is_used_by_detail_and_review`（`:520`）、`test_repaired_review_output_is_shown_in_detail`（`:577`）。

### M5 审核预留上界
- `kb_trial.py:359-385`：`_review_quote_item` 按原文 token + `shot_plan.max_tokens` + 包装开销估算首调；修正加入 `cross_review.max_tokens + REPAIR_OVERHEAD_TOKENS`；`first_max` 作为预留上界。
- `kb_trial.py:469-473`：报价改用该函数，不再传 `estimated_shot_chars` 占位。
- 测试：`test_review_quote_covers_shot_plan_output_upper_bound`（`:670`）。

### M6 存活变异补测
- M6-B：`test_quote_max_cny_cap_blocks_before_and_after_quote`（`test_studio_kb_api.py:701`）：单次上限极小时报价 409 且不新增 `studio_quotes`；正常报价后调低上限，确认 409。
- M6-D：`test_when_model_rules_for_seedance_and_wan`（`test_studio_kb_core.py:386`）：Seedance 写实近景露脸命中 `seedance-portrait-photoreal`；anime/剪影/背影不命中；万相写实特写命中 `wan-face-closeup`（info）。
- M6-E：`test_select_materials_renders_every_card_header`（`test_studio_kb_core.py:414`）：grammar/negatives 每块以「【id】title：summary」开头，`card_ids` 都在 text 中以「【id】」出现。

### M7 lint 规则 1、2
- `backend/studio/director_kb/lint.py:25-35`：英文运镜与英文看镜头正则改 ASCII 边界。
- `lint.py:30` 否定词表；`lint.py:121-130` 中文短语前 0–2 字含 `不/别/勿/避免/不要/禁止` 时跳过；`lint.py:160-168` 规则 2 使用该逻辑。
- 测试：`test_builtin_ascii_boundary_and_negated_looking_phrases`（`test_studio_kb_core.py:292`）。

### P5 lint 只加载一次卡片
- `lint.py:237-240,290-319`：`_model_rules` / `_negative_rules` 接受 cards；`lint_shots` 每次调用各加载一次并传入。
- 测试：`test_lint_loads_model_and_negative_cards_once_per_call`（`:355`）。

### P9 去掉 300 秒超时
- `kb_trial.py:572-580`：`_wait_terminal` 不再有 deadline；由 `_final_attempt` 等最终尝试终态。
- 由 M3 的续跑测试覆盖。

### P13 知识库入口保留 embed
- `frontend/app/studio/page.tsx:4,8,10-12,19`：拆 `KbEntryLink`，用 `useSearchParams` 判断 embed，链接 `studioHref("/studio/kb", embedded)`，外层独立 Suspense。
- 测试：`test_studio_page_kb_entry_keeps_embed`（`test_studio_kb_frontend.py:482`）。

### X1 grammar 优先级
- `backend/studio/director_kb/retrieval.py:130-145`：template → position → 标签命中依次去重，先截 5 张，再按 id 排序。
- 测试：`test_grammar_priority_keeps_template_related_cards`（`test_studio_kb_core.py:427`）：dialogue + body + `face_closeup` 必含 `grammar-over-shoulder`、`grammar-shot-reverse-shot`、`grammar-shot-size`。

### X2 tags 统一 kebab-case
- `schema.py:111,243-245`：`_TAG_RE = ^[a-z0-9]+(?:-[a-z0-9]+)*$`，错误文案改为 kebab-case。
- `retrieval.py:85-97,138-141`：`_normalize_tag` 把 `_` 换成 `-`；`_tag_tokens` 对所有字符串 token 归一；grammar 命中比较也对卡片 tags 归一。
- 卡片（N）：`grammar-camera-angle.yaml:5`、`grammar-over-shoulder.yaml:5`、`grammar-backlight-silhouette.yaml:5`、`grammar-camera-movement.yaml:5`、`grammar-lens-focal.yaml:5`、`grammar-shot-size.yaml:5` 去重并只留连字符写法；全库 58 张 tags 均为 kebab-case。
- 测试：`test_tag_schema_rejects_underscores`（`:457`）、`test_grammar_tag_matching_normalizes_sensitive_underscores`（`:465`）、`test_tag_tokens_normalize_all_underscores`（`:485`）。

### X3 model_card_missing
- `kb_trial.py:692-705`：按模型卡库判断 `video_model + realism` 是否有卡；`get_trial:720,743` 每个模式返回 `model_card_missing`。
- `frontend/lib/studio-kb.ts:173`、`frontend/components/studio/kb/KbTrialPanel.tsx:103`：true 时栏顶显示「该写实度没有对应的模型卡，未注入模型能力与其检查规则」。
- 测试：`test_trial_detail_reports_missing_model_card_for_3d`（`test_studio_kb_api.py:715`）、`test_trial_mode_column_warns_when_model_card_missing`（`test_studio_kb_frontend.py:465`）。

### X4 位置卡去通用条目
- `backend/studio/director_kb/cards/scene/scene-opening-hook.yaml:34-37`：camera 6→3 条（删不看镜头、至少 4 秒、写实不脏）；`ai_risks` 5→4（删 IP 拦截项）；`example:53` 去掉「单条生成不短于 4 秒」。
- `scene-cliffhanger.yaml:34-37`：camera 6→3；`example:55` 去掉同一通用句。
- 自查：全库 58 张 schema 通过；两张位置卡 camera 各 3 条、opening ai_risks 4 条；改动卡 20 字重合 0。

### X5 lint 规则 4 与提示词长度
- `lint.py:179-183`：`fixed_camera = "固定" in camera and "非固定" not in camera`，含「非固定」按非固定处理。
- `lint.py:41-45,257-261`：长度规则只量 `video_prompt`（Seedance）或 `first_frame_prompt`（Seedream），不再用 5 字段拼接。
- 测试：`test_builtin_nonfixed_camera_is_not_fixed`（`:323`）、`test_prompt_length_rules_only_measure_their_own_field`（`:334`），两条规则各正反用例。

### X6 confrontation camera
- `backend/studio/director_kb/cards/scene/scene-confrontation.yaml:41`：改为「压力升级：人脸镜头用固定机位；非人脸的双人中景可以轻推轨（镜头沿地面缓慢靠近），不做环绕」。

## 3. 变异自测

| 变异 | 打入位置 | 目标测试 | 结果 | 还原后 sha256 |
|---|---|---|---|---|
| M6-D：关闭 when 型 model 规则 | `lint.py` 的 `matched = _when_matches(...)` 前加 `False and` | `test_when_model_rules_for_seedance_and_wan` | **红**：`1 failed`，`seedance-portrait-photoreal` 为 0 | `b076beb98fd4f70b320bd133f6b727a8001ec46ddd1f424eaa58d27c8d5ba56d` |
| M6-E：反例卡头部格式 | `retrieval.py` `_render_negative` 改为 `[id] 标题: 要点` | `test_select_materials_renders_every_card_header` | **红**：`1 failed` | `755e9675b07aaa11ccdc1a009e86abd2b3b28c19e62eb10837af933c4673d27f` |
| M6-B：报价额度检查 | `kb_trial.py` quote 内 `check_brain_budget` 改为 `pass` | `test_quote_max_cny_cap_blocks_before_and_after_quote` | **红**：`1 failed`，返回 200 而非 409 | `ee6c78efeabf88c56214eed9d092e68dcebaec4f8c376518db51c3186d25e1be` |
| X1：grammar 先排序再截 5 | `retrieval.py` `_select_grammar` 改回 `sorted(set(ordered))[:5]` | `test_grammar_priority_keeps_template_related_cards` | **红**：`1 failed`，三张模板语法卡被挤出 | `755e9675b07aaa11ccdc1a009e86abd2b3b28c19e62eb10837af933c4673d27f` |
| X2：schema 接受下划线 tag | `schema.py` `_TAG_RE` 加回 `[-_.]` | `test_tag_schema_rejects_underscores` | **红**：`1 failed`，未抛 `CardValidationError` | `46da226aedfe3af1ba0e8830b55290ff3a06d8c36265135758e70e29826fc175` |

五个变异均逐一打入、确认变红后还原；还原后 sha256 与变异前完全一致。实现文件未残留改动。

## 4. 门禁数字

- 后端：`cd backend && env -u NO_PROXY -u no_proxy <Python> -m pytest -q tests/ -k studio`
  → **1788 passed, 5550 deselected, 32 warnings in 79.96s**（0 failed / 0 skipped）。
- 后端相关四个测试文件：`tests/test_studio_kb_api.py tests/test_studio_cross_review.py tests/test_studio_kb_core.py tests/test_studio_kb_frontend.py`
  → **98 passed, 32 warnings in 9.70s**。
- 前端：`cd frontend && npx tsc --noEmit && npm run lint`
  → tsc **exit 0，无输出**；lint **✖ 25 problems (0 errors, 25 warnings)，exit 0**（warning 全在既有 `app/page.tsx`、`app/plaza/page.tsx`）。
- 新前端源码粗体扫描：`font-bold|font-semibold|font-weight≥600|<b>|<strong>` **0 处**（`test_studio_kb_frontend.py` 里只有反向断言字符串，不是 UI 样式）。
- 原文重合（主控复跑）：§11 来源 56 个文件，新写卡片连续 20 字 **0 命中**。
- 白名单：本轮 22 个文件变更，全部落在 K/L/N/F 白名单并集；没有白名单外文件。两张样卡 sha256 仍为
  - `d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d`（dialogue）
  - `72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129`（fight）

## 5. 未完成或需要人工确认

1. **P9 的无超时边界**：若项目在 `_run_trial` 已通过归档检查之后才被归档，本轮按 P9 不设墙钟超时，`_wait_terminal` 会持续轮询，进程内这次运行不会自行中断；重启恢复能清理 queued 占位。K 已按本单要求保留该行为。
2. **X3 `model_card_missing` 的模式语义**：3D 时 with_kb 与 without_kb 都返回 true（without_kb 本就不注入模型卡）。若作者希望 without_kb 恒为 false，需要再调整字段语义。
3. **M5 预留上界公式的边界**：按「原文 + `shot_plan.max_tokens` + 包装」估算；若实际 shots JSON 字符数明显超过约 `max_tokens/1.5`，仍可能超出该估算口径，这是公式本身的边界，不是漏算已报价的审核项。
4. **X6 文案前缀**：最终保留「压力升级：」前缀，语义为「人脸镜头固定、非人脸双人中景可轻推轨、不做环绕」；若要求逐字等于复核建议句，需要作者裁定。
5. **X4 关联列表**：只删了 opening-hook 的 `ai_risks` IP 项；`related_negative` 中的 `negative-ip-lookalike` 引用保留（本单未点名删除）。
6. **P13**：只做了 embed 感知链接；入口仍在页面级 header、gate 判定前可见（复核 P13 的建议只要求 embed 感知 href，未要求移到 gate 后）。
7. **本轮明确不做**：复核 P6 其余部分、P7、P8、P10、P11、P12、P14、P15。
8. 前端只跑了 tsc/lint 与离线 pytest，没有跑 `npm run build`（本单门禁未要求）。
9. 本机 `NO_PROXY` 含 `[::1]`，后端门禁按派单要求用 `env -u NO_PROXY -u no_proxy` 运行；没有修改仓库配置。
