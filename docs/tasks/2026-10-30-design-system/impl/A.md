# A：T1 总表套用记录

- 角色：工作流 agent A（总表）。只做 `02-spec.md` §T1；未调用 subagent / subagent_fork / workflow。
- 工作目录：`<工作树>`
- 基线：`HEAD` = `647a486`。git 只做读操作（`show` / `status` / `diff`）。
- 脚本：`docs/tasks/2026-10-30-design-system/impl/apply_t1.py`（`apply` / `verify`）。
- 结果：PASS，无偏差。

## 1. 套用范围与结果

- 附件：`verify/replacements.tsv`，1158 个数据行、76 个文件。
- 实际套用：1158 个表项，分布在 **854 个不同行** 上；76 个文件全部发生变化。
- `kind` 分布：`size` 831、`color` 223、`syntax` 69、`legacy` 32、`contrast` 3。
- 四种情况计数：
  - 普通替换 `replace`：1146；
  - `old` 为空、插入 `new`：8（7 处 `<small>` 补 `text-fs-11 `，`studio/EpisodePlan.tsx:74` 补 `text-fs-15 `）；
  - `new` 为空、按 §T1 第 3 条删类名：3（(a) 1、(b) 1、(c) 1）；
  - `old` 以空格开头、原样删掉 `old`：1（`app/plaza/page.tsx:517` 的 ` opacity-60`）。
- `globals.css` 只改第 300 行的 2 处（`border-border`、`outline-ring/50`）；T1 不改变行数，改后仍是第 300 行。
- 每一行替换前都断言 `line:col` 处的原文等于 `old`：1158/1158 通过；没有跳过，也没有自行修正。
- 脚本采用两阶段：先在内存中构造并校验全部 76 个候选文件，全部通过后才写盘，避免中途失败留下半套结果。
- 读写方式：按字节读入后 `decode("utf-8")` / `encode("utf-8")`，没有使用 `utf-8-sig`；`app/page.tsx` 的 UTF-8 BOM 原样保留。列号按 Python `str` 的 Unicode 码位计，不是字节。
- 所有 76 个文件保持 LF、文件末尾换行不变；写盘前后行数不变（854 行改的是行内字符，不增删行）。

套用的 76 个文件（即 `replacements.tsv` 第一列去重排序）：

```text
app/agents/[id]/page.tsx
app/community/page.tsx
app/globals.css
app/history/page.tsx
app/login/page.tsx
app/match/page.tsx
app/page.tsx
app/plaza/page.tsx
app/profile/page.tsx
app/settings/page.tsx
components/AgentExchangeWorkspace.tsx
components/AgentIdentityCard.tsx
components/AgentMemoryPanel.tsx
components/ChatBubble.tsx
components/ChatModelSection.tsx
components/ChatScrollArea.tsx
components/ComposerImageMenu.tsx
components/ConfirmDialog.tsx
components/ConversationPicker.tsx
components/GeneratedImage.tsx
components/LocalWatchSection.tsx
components/MessageText.tsx
components/MyAgentWorkspace.tsx
components/NewsCardContent.tsx
components/Sidebar.tsx
components/SongProjectCard.tsx
components/StarChart.tsx
components/VoiceButton.tsx
components/novel/BiblePanel.tsx
components/novel/ChapterList.tsx
components/novel/ChapterReader.tsx
components/novel/DeliberationTimeline.tsx
components/novel/GateBanner.tsx
components/novel/NotesPanel.tsx
components/novel/NovelContent.tsx
components/novel/NovelFilmDialog.tsx
components/novel/NovelModelFields.tsx
components/novel/NovelSettingsDialog.tsx
components/novel/NovelShelf.tsx
components/novel/NovelStates.tsx
components/novel/NovelWizard.tsx
components/novel/NovelWorkbench.tsx
components/novel/PlanEditor.tsx
components/novel/SetupEditor.tsx
components/studio/BibleTable.tsx
components/studio/BrainTrial.tsx
components/studio/BreakdownDialog.tsx
components/studio/BreakdownPanel.tsx
components/studio/BreakdownStage.tsx
components/studio/CastingItemCard.tsx
components/studio/CastingItems.tsx
components/studio/CastingQuoteDialog.tsx
components/studio/CastingStage.tsx
components/studio/ClipComposer.tsx
components/studio/CreateProjectDialog.tsx
components/studio/EpisodePlan.tsx
components/studio/QuoteDialog.tsx
components/studio/SetupCard.tsx
components/studio/ShotCard.tsx
components/studio/ShotWall.tsx
components/studio/SourceChoices.tsx
components/studio/SourcePanel.tsx
components/studio/StudioAssetAudio.tsx
components/studio/StudioBudget.tsx
components/studio/StudioShelf.tsx
components/studio/StudioWorkbench.tsx
components/studio/StyleCard.tsx
components/studio/SynopsisPanel.tsx
components/studio/VoicePanel.tsx
components/studio/kb/KbCardBrowser.tsx
components/studio/kb/KbCardDetail.tsx
components/studio/kb/KbExemplars.tsx
components/studio/kb/KbStatsPanel.tsx
components/studio/kb/KbTrialPanel.tsx
components/studio/kb/KbWorkbench.tsx
components/studio/kb/ReviewProviderPicker.tsx
```

## 2. §T1 第 3、4、5 条的特殊结果

脚本在整行处理完后，对规格点名的 3 行按 §T1 第 3 条做逐字断言，对 `plaza` 的 1 行按第 4 条再断言一次：

```text
app/login/page.tsx:145  (a: 左邻空格、右邻不是 ${)
          <h1 className="mt-11 text-fs-76 font-light leading-none tracking-[0.01em] max-md:mt-7">Chloe</h1>

components/MessageText.tsx:69  (b: 类名紧跟在引号后)
            : "tracking-[.08em] text-[color:var(--ink2)]";

app/profile/page.tsx:98  (c: 右邻是 ${)
              <h1 className={`mt-[18px] text-fs-30 font-medium tracking-[0.16em] ${embedded ? " sr-only" : ""}`}>社交画像（旧版）</h1>

app/plaza/page.tsx:517  (第 4 条，删除 " opacity-60")
                              <span className="ml-1 text-fs-11">（链接失效）</span>
```

8 处插入也已核对：7 处 `<small>` 的 `className="` 后插入 `text-fs-11 `，`studio/EpisodePlan.tsx:74` 的标题 `className="` 后插入 `text-fs-15 `。

## 3. 反向核对（§T1 第 7 条）

以 `git show HEAD:frontend/<file>` 的原文为基准，对 76 个文件的每一行重放该行的全部表项，构造期望行，再与盘上套用后的行逐字比较。验证器是脚本里独立的、从左到右的重建路径，不复用 `apply_line` 的倒序原地替换。

结果：

- 核对文件：**76 / 76**；
- 核对内容行：**14488**（另有 76 个末尾换行哨兵，合计 14564 个 split 元素）；
- 含替换的行：**854**；
- 重放表项：**1158**；
- 非空 `new` 的位置逐一核对：**1154 / 1154**（4 处 `new` 为空的删除由整行逐字相等覆盖）；
- 全部 76 个文件的候选字节与“HEAD + 该行表项重放”逐字节相等；
- 未在表中的行全部与 HEAD 逐字相等；
- 不匹配：**0**；
- 76 个文件的字节都与 HEAD 不同（符合预期）；
- 结论：**PASS**。

输出摘录：

```text
reverse check files: 76
reverse check content lines: 14488
reverse check final-newline sentinels: 76
reverse check lines with replacements: 854
reverse check table rows replayed: 1158
reverse check non-empty new placements verified: 1154
files whose bytes differ from HEAD: 76
PASS: every candidate line equals HEAD with that line's table rows replayed
PASS: every non-empty new sits at its expected position; all other characters match HEAD
```

## 4. 跑过的命令与每步结果

### 4.1 套用

```bash
python3 docs/tasks/2026-10-30-design-system/impl/apply_t1.py apply --dry-run
python3 docs/tasks/2026-10-30-design-system/impl/apply_t1.py apply
python3 docs/tasks/2026-10-30-design-system/impl/apply_t1.py verify
```

- `--dry-run`：1158 个表项、76 个文件、854 个改动行、`{'insert': 8, 'replace': 1146, 'rule3a': 1, 'rule3b': 1, 'rule3c': 1, 'rule4': 1}`；特殊行断言全部 OK；退出码 0，未写盘。
- `apply`：同一组断言通过；76 个文件写盘；`APPLIED: 76 files written`；退出码 0。
- `verify`：上述反向核对全部通过；退出码 0。

### 4.2 改动集合与保护文件

```bash
git status --porcelain --untracked-files=all
git diff --stat
git diff --numstat
git diff --check
git diff --name-only
sha256sum -c /tmp/fiona-t1-protected-before.sha256
```

- `git status --porcelain --untracked-files=all`：76 个 `M`，全部是 `frontend/` 下总表第一列的 76 个文件；9 个 `??` 是任务目录原有文件（本工作树里该目录未提交）加 `impl/apply_t1.py`。写本记录后为 10 个 `??`。
- `git diff --stat`：`76 files changed, 854 insertions(+), 854 deletions(-)`（854 是改动行数；1158 个表项中有 304 个表项与别的表项同行）。
- `git diff --numstat` 汇总：76 个文件，新增 854 行、删除 854 行。
- `git diff --check`：退出码 0，无空白错误。
- `git diff --name-only`：76 个文件，全部属于总表第一列；`frontend/` 之外的 tracked 改动为 0。
- `backend/**`、`frontend/README.md` 的 `git diff` 为空；`02-spec.md` 与 `verify/**` 在 HEAD 中未跟踪，另用 sha256 做前后比对，8 个文件全部 `OK`。
- 独立用 `git diff -U0` 解析每个文件的改动旧行号，与表中的行号集合逐文件比较：76/76 文件一致，合计 854 行，无多改、无漏改、无行号偏移。

### 4.3 BOM、行尾与附件只读

```bash
xxd -l 8 frontend/app/page.tsx
sed -n '300p' frontend/app/globals.css
```

另用内联 `python3` heredoc 逐文件检查 76 个文件的 CR、末尾换行与 BOM（不是占位符；结果见下）。

- `xxd -l 8 frontend/app/page.tsx`：`efbb bf22 7573 6520`，即 `EF BB BF` + `"use `；BOM 保留，且只出现 1 次。
- 76 个文件：无 `CR`，全部以 LF 结尾；除 `app/page.tsx` 外无 BOM，`app/page.tsx` 的 BOM 与 HEAD 一致。
- `frontend/app/globals.css` 第 300 行：
  - HEAD：`  * { @apply border-border outline-ring/50; }`
  - 现在：`  * { @apply border-[color:var(--rule)] outline-[color:var(--ink)]/50; }`

### 4.4 保护文件 sha256（前后一致）

```text
1a0274b29affcce671f3e9a07ef83c1929ebc18ed7e1dbd083c0a7b01f73af0b  02-spec.md
f677e6930a7c88175d1a6539136ac5d139166f65e391a47528bf7dd0d41c52c1  verify/README.md
223580db0326928b4bb495619525647674d43b3b5f93890fc9ab4eb8d394f425  verify/replacements.tsv
7beed58a195bd0a8afead6621bca94da09f93bc9f4eea2c59a4b74c81bc454e7  verify/t2_edits.json
e2a191cf795c18307d883dfb2da941ddca10c65ef6c4acfcb3adc369fb4cc3c6  verify/test_literals.tsv
f73eb2115d009a8701a565d8faaf21428adc1dc561d19585c4ade54953f052a6  verify/ref/contrast_check.py
d01ade965797badce2ea939aeca737f38b0be94792c27ad58b48d464e64c2511  verify/ref/gate_rules.py
1ac83e07948b6558c14c61a6c65bee60154ee8463db236b86c28a7ab83508bdb  verify/ref/gate_twcss.mjs
```

## 5. 偏差与说明

- 无规格偏差；没有跳过或自行修正任何表项。
- 本 agent 只做 T1。按派单要求，没有跑 `npx tsc --noEmit`、`npm run lint`、`npm run build`、pytest；这些属于 B–G 完成后的 §6 门禁，由主代理统一执行。
- 为确认脚本可解析，跑过一次 `python3 -m py_compile`；生成的 `impl/__pycache__/` 已删除，`impl/` 现在只保留脚本与本记录。
- 写盘前在 `/tmp/fiona-t1-backup/` 留过 76 个文件的临时备份，收尾已删除；没有进入仓库。
- 未做任何 git 写操作。
