# 03 实施报告：设计系统收口（UI 复核第四批）

- 执行者：dsh（DeepSeek Flash，max）
- 基线：`main` @ `647a486`，工作分支工作树 `<工作树>`
- 规格：`docs/tasks/2026-10-30-design-system/02-spec.md` v2
- 结论：T1–T6 全部完成；§6 第 1–6 条由执行者实跑并通过；§6 第 7 条真实浏览器实测按规格留给 Claude。
- 全程未做 git 写操作；`02-spec.md` 与 `verify/**` 一个字节未动（sha256 见 §4.6）。

---

## 0. 拆分表：派出过的全部 agent

**并行方式**：第一个工作流只跑 A；A 完成并做反向核对后，第二个工作流用 `parallel()` 同时跑 B–G，按文件不重叠拆分。每个 agent 的任务说明都写明不得调用 subagent / subagent_fork / workflow，并自行读规格与附件。

| agent | 任务 | 负责文件 |
|---|---|---|
| A 总表 | T1：写套用脚本、套用 `replacements.tsv`、§T1 第 7 条反向核对 | `verify/replacements.tsv` 第一列的 76 个前端文件 |
| B 令牌层 | T2：按 `verify/t2_edits.json` 套 28 条 | `frontend/app/globals.css`（第 300 行 2 处之外）、`frontend/lib/utils.ts`、`frontend/components/Seal.tsx` |
| C 源码门禁 | T3-1 | `backend/tests/test_design_system_gate.py` |
| D 对比度 | T3-2 | `backend/tests/test_design_tokens_contrast.py` |
| E cn 与 CSS | T3-3、T3-4 | `backend/tests/test_design_system_cn.py`、`backend/tests/test_design_system_css.py` |
| F 既有测试 | T4：只改 29 行 | `verify/test_literals.tsv` 里的 10 个既有测试文件 |
| G 文档 | T5 | `frontend/README.md` |

**过程说明**：第二个工作流的第一次调用把 `parallel()` 的参数直接写成了已创建的 Promise，工作流在执行任何 agent 之前就报 `parallel() item 0 is not a function`。主代理核对 `git status` 与 `list_agents`，确认没有任何 agent 启动、没有文件变化，然后把参数改为 thunk 重跑；B–G 六个 agent 全部完成。该失败重试不影响最终产物。

---

## 1. 修改与新增的文件清单

### 1.1 T1 总表改动的 76 个前端文件（只做表内替换）

`frontend/app/agents/[id]/page.tsx`、`frontend/app/community/page.tsx`、`frontend/app/globals.css`、`frontend/app/history/page.tsx`、`frontend/app/login/page.tsx`、`frontend/app/match/page.tsx`、`frontend/app/page.tsx`、`frontend/app/plaza/page.tsx`、`frontend/app/profile/page.tsx`、`frontend/app/settings/page.tsx`、`frontend/components/AgentExchangeWorkspace.tsx`、`frontend/components/AgentIdentityCard.tsx`、`frontend/components/AgentMemoryPanel.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/ChatModelSection.tsx`、`frontend/components/ChatScrollArea.tsx`、`frontend/components/ComposerImageMenu.tsx`、`frontend/components/ConfirmDialog.tsx`、`frontend/components/ConversationPicker.tsx`、`frontend/components/GeneratedImage.tsx`、`frontend/components/LocalWatchSection.tsx`、`frontend/components/MessageText.tsx`、`frontend/components/MyAgentWorkspace.tsx`、`frontend/components/NewsCardContent.tsx`、`frontend/components/Sidebar.tsx`、`frontend/components/SongProjectCard.tsx`、`frontend/components/StarChart.tsx`、`frontend/components/VoiceButton.tsx`、`frontend/components/novel/BiblePanel.tsx`、`frontend/components/novel/ChapterList.tsx`、`frontend/components/novel/ChapterReader.tsx`、`frontend/components/novel/DeliberationTimeline.tsx`、`frontend/components/novel/GateBanner.tsx`、`frontend/components/novel/NotesPanel.tsx`、`frontend/components/novel/NovelContent.tsx`、`frontend/components/novel/NovelFilmDialog.tsx`、`frontend/components/novel/NovelModelFields.tsx`、`frontend/components/novel/NovelSettingsDialog.tsx`、`frontend/components/novel/NovelShelf.tsx`、`frontend/components/novel/NovelStates.tsx`、`frontend/components/novel/NovelWizard.tsx`、`frontend/components/novel/NovelWorkbench.tsx`、`frontend/components/novel/PlanEditor.tsx`、`frontend/components/novel/SetupEditor.tsx`、`frontend/components/studio/BibleTable.tsx`、`frontend/components/studio/BrainTrial.tsx`、`frontend/components/studio/BreakdownDialog.tsx`、`frontend/components/studio/BreakdownPanel.tsx`、`frontend/components/studio/BreakdownStage.tsx`、`frontend/components/studio/CastingItemCard.tsx`、`frontend/components/studio/CastingItems.tsx`、`frontend/components/studio/CastingQuoteDialog.tsx`、`frontend/components/studio/CastingStage.tsx`、`frontend/components/studio/ClipComposer.tsx`、`frontend/components/studio/CreateProjectDialog.tsx`、`frontend/components/studio/EpisodePlan.tsx`、`frontend/components/studio/QuoteDialog.tsx`、`frontend/components/studio/SetupCard.tsx`、`frontend/components/studio/ShotCard.tsx`、`frontend/components/studio/ShotWall.tsx`、`frontend/components/studio/SourceChoices.tsx`、`frontend/components/studio/SourcePanel.tsx`、`frontend/components/studio/StudioAssetAudio.tsx`、`frontend/components/studio/StudioBudget.tsx`、`frontend/components/studio/StudioShelf.tsx`、`frontend/components/studio/StudioWorkbench.tsx`、`frontend/components/studio/StyleCard.tsx`、`frontend/components/studio/SynopsisPanel.tsx`、`frontend/components/studio/VoicePanel.tsx`、`frontend/components/studio/kb/KbCardBrowser.tsx`、`frontend/components/studio/kb/KbCardDetail.tsx`、`frontend/components/studio/kb/KbExemplars.tsx`、`frontend/components/studio/kb/KbStatsPanel.tsx`、`frontend/components/studio/kb/KbTrialPanel.tsx`、`frontend/components/studio/kb/KbWorkbench.tsx`、`frontend/components/studio/kb/ReviewProviderPicker.tsx`

### 1.2 T2 令牌层文件

- `frontend/app/globals.css`（T1 第 300 行 2 处之外，T2 第 1–26 条）
- `frontend/lib/utils.ts`（T2 第 27 条）
- `frontend/components/Seal.tsx`（T2 第 28 条）

### 1.3 T4 既有测试（10 个文件，只改授权的 29 行）

`backend/tests/test_empty_states_agents.py`、`backend/tests/test_empty_states_match_profile.py`、`backend/tests/test_empty_states_settings_privacy.py`、`backend/tests/test_mobile_chat_fix.py`、`backend/tests/test_novel_p21_frontend.py`、`backend/tests/test_novel_p2_frontend.py`、`backend/tests/test_song_frontend.py`、`backend/tests/test_ui_polish_beijing_time.py`、`backend/tests/test_ui_polish_composer_controls.py`、`backend/tests/test_ui_polish_markdown.py`

### 1.4 T3 新增的 4 个测试文件

- `backend/tests/test_design_system_gate.py`（738 行）
- `backend/tests/test_design_tokens_contrast.py`（380 行）
- `backend/tests/test_design_system_cn.py`（150 行）
- `backend/tests/test_design_system_css.py`（201 行）

### 1.5 T5 文档

- `frontend/README.md`（新增「设计令牌与门禁」一节，+8 行）

### 1.6 任务目录内的辅助脚本与记录

- `docs/tasks/2026-10-30-design-system/impl/A.md`–`G.md`（7 个 agent 记录）
- `impl/apply_t1.py`、`impl/apply_t2.py`、`impl/verify_t2.py`、`impl/mutation_check.py`
- 本报告 `docs/tasks/2026-10-30-design-system/03-report.md`

### 1.7 改动规模

- `git diff --numstat`：89 个 tracked 文件，+939 / -920。
  - 76 个总表文件：854 行改动（+854 / -854）；
  - `globals.css` 相对 HEAD 为 +42 / -36（含 T1 36 行与 T2 净 +6 行）；
  - `utils.ts` 为 +6 / -1，`Seal.tsx` 为 +1 / -1；
  - 10 个既有测试合计 +29 / -29；
  - `frontend/README.md` 为 +8 / -0。
- 4 个新测试合计 1469 行；任务目录新增 19 个文件（报告写完后为 20 个）。
- 未改 `frontend/components/ui/**`、`desktop/**`、`package.json`、lockfile；未新增依赖。

---

## 2. 实现了什么：与 T1–T6 逐项对应

### T1 逐处替换

- A 写套用脚本 `impl/apply_t1.py`，按 `verify/replacements.tsv` 将 1158 个表项套到 76 个文件，落在 854 个不同行上。
- 处理了表内四种特殊情形：普通替换 1146；`old` 为空插入 8（7 处 `<small>` 补 `text-fs-11 `，`EpisodePlan.tsx:74` 补 `text-fs-15 `）；`new` 为空删类名 3（(a)(b)(c) 各 1）；`old` 以空格开头删除 1（`plaza/page.tsx:517` 的 ` opacity-60`）。
- 1158/1158 表项在替换前断言 `line:col` 处原文等于 `old`；按 Unicode 字符计列；`app/page.tsx` 的 UTF-8 BOM 保留；76 个文件保持 LF 与末尾换行。
- §T1 第 7 条反向核对：76/76 文件、14488 个内容行、854 个含替换行、1158 个表项重放、1154 处非空 `new` 定位核对，0 不匹配。主代理另写独立脚本按表重建每个文件，76 个文件全部逐字节相符。

### T2 令牌层

- `verify/t2_edits.json` 的 28 条全部按顺序套用，每条替换前断言 `old` 恰好出现 `count` 次；28/28 通过。
- 字号：别名 `:root` 新增 10 个 `--fs-*`；`@theme inline` 登记 10 个 `--text-fs-*` 及 12/13/15/22 四档行高；`body` 设 `font-size: var(--fs-16-5)`。
- 对比度：昼两套主题 `--ink3` 改 `#6F7C76`；夜两套主题 `--seal` 改 `#E56F5D`；四套主题新增 `--stamp`（昼 `#A8322A`、夜 `#BF4537`）；`--rec-soft` 改为 `--seal-soft` 且基色为 `--stamp`；`Seal.tsx` 印章底色改用 `--stamp`。
- 清理：删除 `--amber-ink`、`--dim`、`--rec`、`--rec-soft`、`--glass-border`、`--glass-strong`、`--glass-hi`、`--shadow`、`--sidebar-*` 以及 `@theme inline` 的 8 行 `--color-sidebar-*`；保留 `--fill`、`--scrim`。
- 组件与基础层：8 个组件类字号改用 `var(--fs-*)`；默认占位符 `var(--ink2)`；两个对话框 `::backdrop` 用 `var(--scrim)` 并删 `.dark` 覆盖；打字光标用 `--ink`；手机输入框护栏 `max(var(--fs-16-5), 1em)`，仍在 `@layer` 外、选择器不变。
- `utils.ts` 用 `extendTailwindMerge` 登记 10 个字号组；`Seal.tsx` 的 `fontSize="30"` 未改。
- 主代理独立重建校验：HEAD 套 T1 的 globals 两处、再套 T2 全部 28 条后，与工作树三个文件逐字节相等。

### T3 新测试门禁

- T3-1：`test_design_system_gate.py` 实现 F1–F10、K1–K6、R2–R4、T1–T7，扫描面 131 个文件，豁免 `components/ui/`，CSS 先去注释；四个分组函数按规格命名，组内汇总断言；两个 `test_selfcheck_*` 覆盖每条规则的坏样本/好样本及规格点名的合法写法。
- T3-2：`test_design_tokens_contrast.py` 解析四套主题（按浏览器层叠）、校验四个主题块键集合与别名块、只接受 `#RRGGBB` / `rgba()`、解析 `--seal-soft`（HEAD 回退 `--rec-soft`），按 WCAG 2.x 与 sRGB alpha 叠加计算断言表；`test_selfcheck_head_tokens_fail` 复现 HEAD 的 43 条不达标并核对四组分布与 `seal-soft@` 底。
- T3-3：`test_design_system_cn.py` 用 node + TypeScript 转译 `utils.ts`，加载 `clsx`/`tailwind-merge`，单个函数覆盖规格表全部用例与 10 个令牌合并。
- T3-4：`test_design_system_css.py` 用 `@tailwindcss/node` 的 `compile` 与 `@tailwindcss/oxide` 的 `Scanner` 编译真实 `globals.css`；反向白名单、`color: var(--fs-` 检查、正向 12 个类规则体逐条比对；扫描 131 个文件。
- 4 个文件都只读仓库内前端源码，不 import/执行/读取 `docs/`，依赖缺失时按规格 skip（本机全量 0 skipped）。

### T4 既有测试字面量

- 严格按 `verify/test_literals.tsv` 改 29 行、10 个文件；每行替换前断言 `old` 在该行恰好出现 1 次；其他行逐字节未动。
- `git diff --numstat HEAD -- backend/tests/` 的既有文件恰为这 10 个，合计 +29 / -29，与表内行数逐一相符。
- 这 10 个测试文件复跑：156 passed、0 failed、0 skipped。

### T5 文档

- `frontend/README.md` 在「开发约束」与「页面」之间新增「设计令牌与门禁」一节，共 7 行（标题、空行、5 条正文），覆盖规格要求的五点。

### T6 报告

- 本文件即 T6；内容按规格 §7 组织。

---

## 3. 拆分表（见文首 §0）

派出过的全部 agent、各自负责的文件与两个工作流的说明见文首 §0。

---

## 4. §6 第 1–6 条的实际结果

以下命令均在仓库根或注明的子目录执行；pytest 全部按 §3.5 清掉 `HTTP_PROXY`、`HTTPS_PROXY`、`http_proxy`、`https_proxy`、`ALL_PROXY`、`all_proxy`、`NO_PROXY`、`no_proxy`。

### 4.1 `cd frontend && npx tsc --noEmit`

- 退出码 **0**，无错误。

### 4.2 `cd frontend && npm run lint`

- 退出码 **0**，**0 errors、25 warnings**（与 HEAD 的 25 条相同，未新增）。
- 警告均为 `app/page.tsx` 既有的未使用变量、Hook 依赖与 `<img>` 提示，以及 `app/plaza/page.tsx` 的 `<img>` 提示。

### 4.3 `cd frontend && rm -rf .next && npm run build`

- 退出码 **0**；Next.js 16.4.3 生产构建通过，18 个静态页面生成完成。
- 构建前删除 `.next`；构建只产生被 git 忽略的 `.next`，未进入改动集合。

### 4.4 全量 pytest

- 命令：在 `backend/` 下 `env -u … .venv/bin/python -m pytest -q -p no:cacheprovider`。
- 结果：**7836 passed、0 failed、0 skipped、35 warnings，312.54 秒（0:05:12）**，退出码 0。
- 基线 7826 条一条不少，另有 4 个新测试文件共 **10 个用例**，合计 7836。
- 该次全量运行发生在 19 项变异自检全部还原之后；随后又用 sha256 逐文件确认还原一致。

### 4.5 结构判据

#### 4.5.1 参考实现门禁

- `python3 -I docs/tasks/2026-10-30-design-system/verify/ref/gate_rules.py .`
  - 扫描 131 个文件；19 条源码规则全部 0 命中；T1–T7 令牌层全部 PASS；**`== FAIL 0`**，退出码 0。
- `python3 -I docs/tasks/2026-10-30-design-system/verify/ref/contrast_check.py frontend/app/globals.css`
  - **不达标 0 条**，退出码 0。
  - 最差值：昼 `--ink2` 4.64、`--seal` 4.70、`--ink3` 3.22；夜 `--seal` 4.56、`--ink3` 3.16；夜素瓷 `--seal` 4.61；印章字 `--glyph`/`--stamp` 4.53。
- `node docs/tasks/2026-10-30-design-system/verify/ref/gate_twcss.mjs frontend`
  - `scannedFiles=131 font-size/font 违规=0 令牌编译不符=0`，退出码 0。

#### 4.5.2 每条规则的命中数（终态与 HEAD 对照）

终态（工作树，参考实现实测）：

| 规则 | 终态命中 | 规则 | 终态命中 | 规则 | 终态命中 |
|---|---:|---|---:|---|---:|
| F1 | 0 | K1 | 0 | R2 | 0 |
| F2 | 0 | K2 | 0 | R3 | 0 |
| F3 | 0 | K3 | 0 | R4 | 0 |
| F4 | 0 | K4 | 0 | T1–T7 | 全部 PASS |
| F5 | 0 | K5 | 0 | | |
| F6 | 0 | K6 | 0 | | |
| F7 | 0 | | | | |
| F8 | 0 | | | | |
| F9 | 0 | | | | |
| F10 | 0 | | | | |

HEAD 副本（`git archive HEAD` + 4 个新测试）上的命中数，与规格 T3 表逐条一致：

| 规则 | HEAD | 规格 T3 表 | 规则 | HEAD | 规格 T3 表 |
|---|---:|---:|---|---:|---:|
| F1 | 300 | 300 | K1 | 144 | 144 |
| F2 | 0 | 0 | K2 | 223 | 223 |
| F3 | 563 | 563 | K3 | 50 | 50 |
| F4 | 0 | 0 | K4 | 8 | 8 |
| F5 | 0 | 0 | K5 | 69 | 69 |
| F6 | 1 | 1 | K6 | 0 | 0 |
| F7 | 2 | 2 | R2 | 1 | 1 |
| F8 | 7 | 7 | R3 | 0 | 0 |
| F9 | 9 | 9 | R4 | 18 | 18 |
| F10 | 0 | 0 | T1–T7 | 全部 FAIL | 全部 FAIL |

#### 4.5.3 §T1 第 7 条反向核对

- A 的结果：76/76 文件、14488 个内容行、854 个含替换行、1158 个表项重放、1154 处非空 `new` 定位，0 不匹配。
- 主代理在 B 开始前用独立脚本重做：按 HEAD 原文逐行重放表项，76 个文件全部逐字节相符，0 问题。
- B 完成后 `globals.css` 第 300 行已移动到第 307 行，按规格不再按行号核对。

#### 4.5.4 §3.3 numstat 核对

- `git diff --numstat HEAD -- backend/tests/` 的既有文件恰为 10 个：
  - `test_empty_states_agents.py` 9/9、`test_empty_states_match_profile.py` 1/1、`test_empty_states_settings_privacy.py` 1/1、`test_mobile_chat_fix.py` 2/2、`test_novel_p21_frontend.py` 2/2、`test_novel_p2_frontend.py` 1/1、`test_song_frontend.py` 2/2、`test_ui_polish_beijing_time.py` 1/1、`test_ui_polish_composer_controls.py` 9/9、`test_ui_polish_markdown.py` 1/1。
- 合计 29 行新增、29 行删除，与 TSV 逐文件行数一致；其余行主代理独立按 HEAD + TSV 重建，10 个文件全部逐字节相符。

#### 4.5.5 T2 逐条次数核对

- `verify/t2_edits.json` 的 28 条全部套用；每条 `old` 在文件中的出现次数等于 `count`（28/28）。
- 主代理独立以 HEAD 套 T1 两处后再套全部 28 条，`globals.css`、`utils.ts`、`Seal.tsx` 与工作树逐字节相等。

#### 4.5.6 新测试在 HEAD 副本上的结果（4 个文件一起跑一次）

做法：`mktemp -d` 新建目录；`git archive HEAD | tar -x`；只拷 4 个新测试到副本 `backend/tests/`；`cp -cR` 克隆本工作树 `frontend/node_modules` 到副本 `frontend/`；在副本 `backend/` 下用本工作树 `backend/.venv/bin/python` 跑。

汇总：**7 failed、3 passed、0 skipped**；7 个失败全部是 `AssertionError`，没有 KeyError 一类崩溃。

| 测试函数 | HEAD 结果 | 失败类型 | 关键命中/失败 |
|---|---|---|---|
| `test_font_size_rules` | FAILED | AssertionError | F1 300、F3 563、F6 1、F7 2、F8 7、F9 9；F2/F4/F5/F10 为 0 |
| `test_color_rules` | FAILED | AssertionError | K1 144、K2 223、K3 50、K4 8、K5 69；K6 为 0 |
| `test_role_rules` | FAILED | AssertionError | R2 1、R4 18；R3 为 0 |
| `test_token_layer` | FAILED | AssertionError | T1–T7 全部 FAIL |
| `test_selfcheck_source_rules` | PASSED | — | 每条源码规则坏样本命中、好样本不误伤 |
| `test_selfcheck_token_layer` | PASSED | — | 合法令牌层基线通过、7 种坏变体被识别 |
| `test_token_contrast` | FAILED | AssertionError | 恰好 43 条：昼 `--ink3` 6、昼素瓷 `--ink3` 3、夜 `--seal` 21、夜素瓷 `--seal` 13；夜含 `seal-soft@` 底 |
| `test_selfcheck_head_tokens_fail` | PASSED | — | 集合恰为四组、43 条、分布正确 |
| `test_cn_keeps_size_and_color` | FAILED | AssertionError | 第 1、2、5、6 条失败，另有第 8 条与 10 个令牌合并因同一 tailwind-merge 误分类而失败 |
| `test_generated_css_font_sizes` | FAILED | AssertionError | 扫描 131 文件；反向 49 条违规、`color: var(--fs-` 0 条；正向 12/12 不符 |

E 的说明：规格 T3-3 写「第 1、2、5、6 条都会失败」，实测第 8 条与 10 个令牌合并也必然失败，原因是同一个 tailwind-merge 误分类；测试按表逐项严格断言，没有为凑「只失败 4 条」放宽。

### 4.6 改动集合与保护文件

- `git status --porcelain --untracked-files=all` 共 113 项：
  - 89 个 `M`：76 个总表文件 + `utils.ts` + `Seal.tsx` + `README.md` + 10 个既有测试；
  - 24 个 `??`：4 个新测试 + 任务目录中规格/附件（7 个 verify 文件、`02-spec.md`）与 impl 记录/脚本 + 本报告。
  - 全部路径都在 §3.1 白名单内；`frontend/` 的 79 个改动全部属于 76 个总表文件、`utils.ts`、`Seal.tsx`、`README.md`。
- 任务目录保护文件 sha256（与派单时一致，未被改动）：

| 文件 | sha256 |
|---|---|
| `02-spec.md` | `1a0274b29affcce671f3e9a07ef83c1929ebc18ed7e1dbd083c0a7b01f73af0b` |
| `verify/README.md` | `f677e6930a7c88175d1a6539136ac5d139166f65e391a47528bf7dd0d41c52c1` |
| `verify/replacements.tsv` | `223580db0326928b4bb495619525647674d43b3b5f93890fc9ab4eb8d394f425` |
| `verify/t2_edits.json` | `7beed58a195bd0a8afead6621bca94da09f93bc9f4eea2c59a4b74c81bc454e7` |
| `verify/test_literals.tsv` | `e2a191cf795c18307d883dfb2da941ddca10c65ef6c4acfcb3adc369fb4cc3c6` |
| `verify/ref/contrast_check.py` | `f73eb2115d009a8701a565d8faaf21428adc1dc561d19585c4ade54953f052a6` |
| `verify/ref/gate_rules.py` | `d01ade965797badce2ea939aeca737f38b0be94792c27ad58b48d464e64c2511` |
| `verify/ref/gate_twcss.mjs` | `1ac83e07948b6558c14c61a6c65bee60154ee8463db236b86c28a7ab83508bdb` |

- `app/page.tsx` 的 BOM 仍为 `EF BB BF`；76 个总表文件与 T2 三个文件均为 LF、末尾换行保留；`git diff --check` 退出码 0。
- 未改 `frontend/components/ui/**`、`desktop/**`、`frontend/package.json`、lockfile。

### 4.7 补充：主代理对 A/B/F 的独立复核

- A 的 76 个文件：独立重建 76/76 逐字节相符。
- B 的三个文件：独立按 T1→T2 重建，逐字节相符；28/28 次数断言通过。
- F 的 10 个测试文件：独立按 HEAD + TSV 重建，逐字节相符；29/29 行命中一次。

---

## 5. 变异自检

做法：每个变异先把目标文件按字节备份到 `/tmp/fiona-design-system-mutation-backups/<编号>/` 并记 sha256；改动后单独跑 4 个新测试文件（`pytest -q -p no:cacheprovider --tb=no -rf`）；跑完把原字节写回并重新算 sha256，必须与备份一致。19 项全部还原成功，临时备份与 HEAD 副本已删除。记录脚本为 `impl/mutation_check.py`。

| 变异 | 必须变红 | 实测变红的函数 | 结果 |
|---|---|---|---|
| 把任意一处 `text-fs-13` 改回 `text-sm` | `test_font_size_rules` | `test_font_size_rules`、`test_generated_css_font_sizes` | PASS |
| 写一个 `text-fs-16-5` | `test_font_size_rules` | `test_font_size_rules` | PASS |
| 写一个 `text-[14px]` | `test_font_size_rules`、`test_generated_css_font_sizes` | 两个都红 | PASS |
| 写 `style={{ fontSize: 14 }}` | `test_font_size_rules` | `test_font_size_rules` | PASS |
| 写 `mobile:text-fs-13${x}` | `test_font_size_rules` | `test_font_size_rules` | PASS |
| 给某个 `<small>` 删掉 `text-fs-11` | `test_font_size_rules` | `test_font_size_rules` | PASS |
| 在 globals.css 写 `.zz { font-size: 14px; }` | `test_font_size_rules`、`test_generated_css_font_sizes` | 两个都红 | PASS |
| 把一处颜色改回 `text-muted-foreground` | `test_color_rules` | `test_color_rules` | PASS |
| 写一个 `text-[var(--ink2)]` | `test_color_rules` | `test_color_rules`、`test_font_size_rules`（F1 同报） | PASS |
| 写一个 `var(--rec)` | `test_color_rules` | `test_color_rules` | PASS |
| 写一个 `bg-(--slip)` | `test_color_rules` | `test_color_rules` | PASS |
| 写一个 `text-[color:var(--ink3)]` | `test_role_rules` | `test_role_rules` | PASS |
| 在某个非 Seal 组件里写 `var(--stamp)` | `test_role_rules` | `test_role_rules` | PASS |
| 给一处文字色加 `/60` | `test_role_rules` | `test_role_rules` | PASS |
| 把夜 `--seal` 改回 `#BF4537` | `test_token_contrast`、`test_token_layer` | 两个都红 | PASS |
| 把夜 `--chip` 改成 `rgba(74,63,52,0.60)` | `test_token_contrast` | `test_token_contrast` | PASS |
| 把 `--text-fs-13--line-height` 改成 `1.4` | `test_token_layer`、`test_generated_css_font_sizes` | 两个都红 | PASS |
| 把手机输入框护栏挪进 `@layer base` | `test_token_layer` | `test_token_layer` | PASS |
| 把 `utils.ts` 改回默认的 `twMerge` | `test_cn_keeps_size_and_color` | `test_cn_keeps_size_and_color` | PASS |

- 19/19 项的「必须变红」集合全部覆盖；额外变红的函数是规则重叠导致的合理连带（F1 与 K5、F3 与 `text-sm` 生成 CSS 等），已逐条记录。
- 每项还原后 sha256 与备份一致；19 项结束后再跑 4 个新测试：**10 passed、0 skipped**；参考门禁仍为 `FAIL 0` / 对比度 0 / 生成 CSS 0。

---

## 6. 未完成、需人工确认与主动偏离

### 6.1 未完成/留给 Claude 的部分

- **§6 第 7 条真实浏览器实测未由执行者做**：13 个画面、4 套主题、2 种视口、字号普查、朱字截图取样、版式与文本回归，按规格由 Claude 在隔离实例执行。
- **§6.5 的逐字节标准答案比对、粗体与「·」出现次数比对由 Claude 做最终独立比对**：执行者已跑参考实现并做了自有独立重建，但不替代 Claude 的最终比对。
- 除上述两项外，T1–T6 与 §6 第 1–6 条均已完成，无阻塞项。

### 6.2 需人工确认的地方

- 无实现层面的待确认项。规格与实测没有出现冲突；总表 1158 行在 HEAD 上全部对得上。
- E 在 HEAD 副本上观察到 `test_cn_keeps_size_and_color` 除规格点名的第 1、2、5、6 条外，第 8 条与 10 个令牌合并也失败；这是同一 tailwind-merge 误分类的必然结果，测试按规格表严格断言，未放宽。
- D 的 HEAD 正控在把夜 `.dark --chip` 改为 `rgba(74,63,52,0.60)` 后确认 `test_token_contrast` 变红，符合规格要求。

### 6.3 主动偏离

- 无实现偏离。唯一的流程事件是第二个工作流首次调用因 `parallel()` 参数写法错误在启动任何 agent 前失败，主代理核对后改为 thunk 重跑；没有产生文件改动，也没有重做已完成工作。
- 全量 pytest 在全量还原后执行；tsc/lint/build 在变异前执行，变异全部按 sha256 还原后又在终态复跑了 tsc、lint、build（结果同上：0、0 errors/25 warnings、0）。

---

## 7. 已知局限（照规格）

- 普通（非素瓷）主题下，直接落在远山画上的 `--ink2` 文字，实际像素对比度可能低于令牌计算值。这一类只能截图取样，本批不处理；
- `frontend/components/ui/*` 仍保留旧写法和 shadcn 别名，它们没有被引用；
- 80 处 HTML 静态行内 style 颜色（如 `style={{ borderColor: "var(--rule)" }}`）保持原样，没有改成类名；
- `frontend/app/settings/page.tsx:166` 的 `tracking-[0.24em]${…}` 同样紧贴 `${`、从来没生效过，但它不是字号类，不在本批范围内。

---

## 返修 R1（2026-10-30）

- 依据：`05-fix-r1.md`，来自 `04-review.md` 可优化项 2、3、5。只做三件事，白名单见返修单第 2 节。
- 执行方式：工作流拆两个 agent 并行，文件不重叠：
  - agent 1：R1-1 + R1-2（`frontend/app/globals.css`、`backend/tests/test_design_system_gate.py`）；
  - agent 2：R1-3（`backend/tests/test_design_system_cn.py`、`backend/tests/test_design_system_css.py`）。
  - 两个 agent 均写明并遵守不得调用 subagent / subagent_fork / workflow；均未做 git 写操作。
- 记录：`impl/R1.md`。

### R1-1 对话框遮罩兜底色

- 按 `verify/r1_edits.json` 的 2 条逐字套用，每条 `old` 的出现次数断言为 1/1，按字节读写。
- 现在两个对话框各有昼、夜两条 `::backdrop`：昼 `var(--scrim, rgba(31,41,38,.18))`、夜 `var(--scrim, rgba(0,0,0,.45))`；上方加 1 行 Safari 17.4 之前变量不可用的说明注释。
- 反向撤销这 2 条后，`globals.css` 的 sha256 精确回到返修前 `3943d85552c85be8caf580d9b91dce1bc27de869c8c01202b92b7dc567e34f00`，证明没有碰其他字符。

### R1-2 源码门禁补 T8

- `_token_layer` 新增 T8，逻辑与 `verify/ref/gate_rules.py` 一致：遍历全部块，选择器以 `::backdrop` 结尾的收集 `background`，结果必须恰好是 4 条选择器到单值列表的映射。
- `_selfcheck_token_css()` 补 4 条合法 backdrop 规则；`test_selfcheck_token_layer` 补坏样本：去掉兜底值写回 `var(--scrim)` 时 T8 必须判失败。
- HEAD 上 T8 失败，`test_token_layer` 照旧失败；工作树去掉任一条兜底值后 `test_token_layer` 变红（`1 failed, 5 passed`），已按字节还原。

### R1-3 源文件缺失必须失败

- `test_design_system_cn.py` 的 `frontend/lib/utils.ts` 检查改为 `assert UTILS.is_file()`，位于 node 探测之前，不再 skip。
- `test_design_system_css.py` 的 `frontend/app/globals.css` 检查改为 `assert ...is_file()`，同样位于 node 探测之前；`REQUIRED_PACKAGES` 去掉未使用的 `typescript`，只保留 `@tailwindcss/node`、`@tailwindcss/oxide`。
- 临时副本验证（未在工作树改名）：`utils.ts` 改名后 `test_cn_keeps_size_and_color` FAILED（AssertionError，不是 skip）；`globals.css` 改名后 `test_generated_css_font_sizes` FAILED（AssertionError，不是 skip）。无 node、文件存在时两测试仍按设计 skip。

### 返修验收结果

| 项目 | 结果 |
|---|---|
| `gate_rules.py` | 28 项全 PASS（扫描面 1 + 19 条源码规则 + T1–T8），`== FAIL 0` |
| `contrast_check.py` | 不达标 0 条 |
| `gate_twcss.mjs` | `scannedFiles=131 违规=0 令牌编译不符=0` |
| 4 个新测试 | 10 passed、0 failed、0 skipped |
| HEAD 副本 | 7 failed、3 passed、0 skipped，全部 AssertionError；各规则命中数与 T3 表一致；T8 FAIL |
| 全量 pytest | **7836 passed、0 failed、0 skipped、35 warnings，302.49 秒** |
| `npm run build` | 退出码 0 |

### 返修改动集合

- 修改：`frontend/app/globals.css`（R1 净 +3 行，607 行）、`backend/tests/test_design_system_gate.py`（770 行）、`backend/tests/test_design_system_cn.py`（152 行）、`backend/tests/test_design_system_css.py`（202 行）、本报告。
- 新增：`impl/R1.md`。
- 工作树 `git status --porcelain --untracked-files=all` 由返修前的 124 项变为 125 项，新增的是 `impl/R1.md`。
- 任务目录保护文件（`02-spec.md`、`04-review.md`、`05-fix-r1.md`、`verify/**`）sha256 前后一致，未改动。
- 无实现偏差，无未完成项；第 3 节 7 条验收全部由执行者实跑通过。
