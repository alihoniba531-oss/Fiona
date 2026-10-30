# 04 独立复核：设计系统收口（UI 复核第四批）

- 复核方：Claude Opus 5.5（全新上下文，独立复核）
- 复核日期：2026-10-30
- 复核对象：复核副本（基线 `647a486` + 候选改动，含未跟踪新文件），即 `.cache/review/cand-snapshot.diff` 所述内容。逐文件比对过：快照里 89 个已跟踪文件的 diff 与副本当前 `git diff HEAD` 一致。
- 依据：`02-spec.md` v2 及 `verify/` 附件。执行者报告 `03-report.md` 和 `impl/*.md` 只当线索，下面的结论都是我自己重跑得到的。
- 临时目录都在会话 scratchpad 的 `b4rev/` 下，包括 HEAD 副本、标准答案副本和变异脚本。副本里没有留下任何改动，见第 6 节。

---

## 1. 结论

**通过。**

- 76 个总表文件、`utils.ts`、`Seal.tsx` 和 10 个既有测试，共 88 个文件。我用自己写的脚本，从 HEAD 出发套用 `replacements.tsv`、`t2_edits.json`、`test_literals.tsv`，重建出一份「标准答案」，与候选逐字节比对：88/88 相同。
- 4 个新测试的规则、正则、扩展名和白名单逻辑，与 `verify/ref/` 的参考实现完全一致。我用程序逐条比对过 19 条正则的 pattern 和 flags，见第 2 节第 5 条。
- 在 HEAD 副本上，除自检外的 7 个函数全部因 `AssertionError` 失败，各规则命中数与规格表逐条相等。在候选上 10/10 通过。
- 我做了 47 项变异：规格 §7 列的 19 项全部复现，另外追加 28 项。每一项都让应该变红的函数变红，没有漏网。
- 没有必须修复项。可优化项见第 4 节，都不阻断。

---

## 2. 验收标准逐条核验（§6 第 1–6 条）

所有命令都在复核副本里跑，pytest 按 §3.5 清掉了代理变量。

### 第 1 条：`cd frontend && npx tsc --noEmit`

```
tsc exit=0
```
通过。

### 第 2 条：`cd frontend && npm run lint`

```
✖ 25 problems (0 errors, 25 warnings)
lint exit=0
```
0 errors，25 warnings，等于 HEAD 的 25 条，没有新增。通过。

### 第 3 条：`cd frontend && rm -rf .next && npm run build`

```
build exit=0
✓ Generating static pages using 17 workers (18/18)
```
通过。构建产物 `.next`、`next-env.d.ts`、`tsconfig.tsbuildinfo` 是我的这次运行新生成的，跑完已删掉，副本恢复到复核前的状态。

### 第 4 条：全量 pytest

```
cd backend && env -u … .venv/bin/python -m pytest -q -p no:cacheprovider -rs
7836 passed, 35 warnings in 297.72s (0:04:57)
exit=0
```
- 0 failed，0 skipped，`-rs` 的输出里也没有任何 SKIPPED 行。
- **既有 7826 条一条不少**：
  - 在 HEAD 副本上 `--collect-only`，排除 4 个新文件，得到 7826 个用例 ID；
  - 在候选上 `--collect-only`，得到 7836 个；
  - HEAD 里有、候选里没有的：0 个。候选里多出的 10 个，正好是 4 个新文件里的 10 个函数。
- 通过。

### 第 5 条：结构判据

**参考实现**（候选上）：
```
python3 -I verify/ref/gate_rules.py .              → == FAIL 0（退出码 0）；19 条规则全部 0 命中，T1–T7 全部 PASS
python3 -I verify/ref/contrast_check.py …/globals.css → 不达标 0 条（退出码 0）
                                                    昼：--ink2 最差 4.64、--seal 4.70、--ink3 3.22
                                                    夜：--seal 4.56、--ink3 3.16；夜素瓷 --seal 4.61；印章字 4.53
node verify/ref/gate_twcss.mjs frontend            → scannedFiles=131 font-size/font 违规=0 令牌编译不符=0（退出码 0）
```

**逐字节比对标准答案**：执行者的套用脚本我没用，自己另写了一份，即 scratchpad 的 `b4rev/build_answer.py`。做法：
- 按 Unicode 字符计列；同一行按 `col` 从大到小替换；每处替换前断言 `line:col` 处的原文就是 `old`；
- 删除和插入的三种特殊情形按 §T1 第 3–5 条处理；
- 再按 `count` 逐条断言并套用 T2 的 28 条，最后套用 29 行测试字面量。

```
rows 1158 files 76
Counter({'size': 831, 'color': 223, 'syntax': 69, 'legacy': 32, 'contrast': 3})
literals 29 files 10
compared 88 differ 0 []
```
- 3 处删类名的结果，与 §T1 第 3 条 (a)(b)(c) 写的逐字相同：
  - `login/page.tsx:145` → `… tracking-[0.01em] max-md:mt-7">Chloe</h1>`
  - `MessageText.tsx:69` → `            : "tracking-[.08em] text-[color:var(--ink2)]";`
  - `profile/page.tsx:98` → `… tracking-[0.16em] ${embedded ? " sr-only" : ""}`
- `app/page.tsx` 开头仍是 BOM `efbbbf`。
- 所以 Claude 门禁报告里「88 个文件与标准答案逐字节一致」这句话本身是可信的，我独立复现了。

**§T1 第 7 条反向核对、T2 次数核对**：我的重建脚本在每处替换前都断言了原文，1158 行、28 条全部对上；没有任何一条断言失败。

**§3.3 numstat**：
```
git diff --numstat HEAD -- backend/tests/
9 9 test_empty_states_agents.py      1 1 test_empty_states_match_profile.py
1 1 test_empty_states_settings_privacy.py  2 2 test_mobile_chat_fix.py
2 2 test_novel_p21_frontend.py       1 1 test_novel_p2_frontend.py
2 2 test_song_frontend.py            1 1 test_ui_polish_beijing_time.py
9 9 test_ui_polish_composer_controls.py    1 1 test_ui_polish_markdown.py
```
- 与 TSV 里每个文件的行数逐一相等；内容已由上面的逐字节比对确认。
- 另做了一次反证：把这 10 个文件换回 HEAD 版本，跑在「标准答案」的前端上，结果是 **17 failed, 139 passed**，失败的正是规格说的 17 个用例。换回候选版本后，这 10 个文件全绿（全量里已包含）。可见这 29 行正好把 17 个用例由红转绿，没有多改。
- 第 266 行的反向断言 `"text-[color:var(--seal)]" not in idle` 随之改了名。它和后面 dictating、holding 两态的正向断言配对，不是恒真。

**粗体与「·」**：比较范围是 76 个总表文件、`utils.ts`、`Seal.tsx`、`README.md` 和 10 个既有测试，共 89 个文件。逐文件比 HEAD 与候选：
```
bold HEAD/cand 42 42   dot HEAD/cand 79 79   increased: []
```
没有新增。通过。

### 第 6 条：改动集合

- `git status --porcelain --untracked-files=all`，不算 `.cache/`，共 113 项：
  - 89 个 M：76 个总表文件、`utils.ts`、`Seal.tsx`、`README.md`、10 个既有测试；
  - 4 个新测试；
  - 本任务目录下 20 个文件。
- 我用脚本逐项比对 §3.1 白名单：白名单外 0 项，白名单内没改到的 0 项。
- `frontend/components/ui/**`、`desktop/**`、`package.json` 和 lockfile 的 diff 为空。
- `components/ui/*` 在 app、components、lib 里没有任何 import，确实没有被用到。
- 保护文件当前的 sha256 与 `03-report.md` §4.6 表里的逐项相同：

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

派单时的 sha256 我手上没有独立来源，只能确认：当前值与执行者报告一致，Claude 的门禁对这一项也报 PASS。

> 说明：复核中途，我用 importlib 载入参考实现做正则比对，在 `verify/ref/` 下生成了一个被 git 忽略的 `__pycache__/`。发现后已立即删除，`verify/ref/` 现在只剩原来的 3 个文件。之后的运行都带了 `PYTHONDONTWRITEBYTECODE=1`。

---

### 第 2 节补充：4 个新测试是否忠实实现 §T3（复核说明重点 1）

**5. 与参考实现逐条比对（程序化）**

做法：在 scratchpad 里载入 `gate_rules.py` 和 `test_design_system_gate.py`，逐条比较两边的 `RULES`（编号、`pattern`、`flags`、扩展名、逐行还是整文件），以及 `SCALE / FS / FSVAR / D / V / R / SHADCN / COLOR_UTILS / LEGACY / TYPE_WORDS / EXTS / SCAN / EXEMPT`：

```
F1…F10、K1…K6、R2、R3、R4：19/19 SAME
SCALE True  FS True  FSVAR True  D True  V True  R True  SHADCN True  COLOR_UTILS True  LEGACY True  TYPE_WORDS True  EXTS True
SCAN True EXEMPT True JS True
files 131 131 True（扫描到的文件列表完全一致）
token_layer 结果一致：True
```
- F7、F8、F9、F10、R3 的放行条件，与参考实现逐句等价。测试里写成 `if/elif`，参考实现写成并列的 `if`，但每次只会有一个 rid，二者等价。
- `_parse_blocks`、`_decls_of`、`_token_layer` 与参考实现逐句等价。

`test_design_tokens_contrast.py` 与 `contrast_check.py` 对照：

| 项 | 结论 |
|---|---|
| 层叠方式 | 一致：夜 = 昼 + `.dark`，昼素瓷 = 昼 + `:root[data-solid]`，夜素瓷 = 四块依次叠加 |
| 两个正则（HEX/RGBA、块切分）、注释剥离 | 一致 |
| 半透明叠底、逐通道四舍五入 | 一致 |
| WCAG 亮度公式 | 一致，阈值点 0.03928 |
| 底色集合 S | 一致，8 个底，半透明时叠在 paper / hi 上 |
| 悬停底 | 一致：基色 paper、hi、glass、glass2、tile，`--ink3` 排除 chip 系 |
| 门槛 | 一致：4.5 / 4.5 / 4.5 / 3.0，`--btnink`/`--btn`、`--glyph`/`--stamp` 均 ≥ 4.5 |
| `--seal-soft` 基色 | 一致。参考实现：基色是 `--stamp` 而主题里没有 `--stamp` 时，回落到 `--seal`；测试的写法与之等价 |
| HEAD 的 `--rec-soft` 回退 | 一致 |
| 比参考实现更严的地方 | 两个 `:root` 缺一就报 AssertionError；主题块缺被检查的颜色就报 AssertionError，参考实现在这里会崩 KeyError |

`test_design_system_cn.py`：
- 规格表 1–8 条加 10 个令牌合并，共 19 个用例，写在一个函数里；
- 断言的是完整输出字符串，比规格写的「两个都在」更严；
- `assert len(actuals) == len(CASES)` 防止结果被静默截短。

`test_design_system_css.py`：
- 反向白名单、`color: var(--fs-` 检查、正向 12 个类的期望规则体、`blockOf` 的写法，都与 `gate_twcss.mjs` 逐字一致；
- 扫描面同为 `app/`、`components/`、`lib/`，排除 `components/ui/`；
- 扫描到的文件数 ≥ 130 是硬断言。

**HEAD 正控（我自己重做）**

做法：`mktemp -d`，`git archive HEAD | tar -x`，只拷入 4 个新测试，用 `cp -cR` 克隆 `node_modules`，再用副本的 `.venv` 跑 `-rfs`。

```
7 failed, 3 passed in 1.76s（0 skipped）
7 个失败的类型全部是 AssertionError（字号规则、颜色规则、角色规则、令牌层、不达标 43 条、tailwind-merge、生成 CSS）
```

| 规则 | HEAD 实测 | 规格表 | 规则 | HEAD 实测 | 规格表 |
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
| F10 | 0 | 0 | T1–T7 | 全 FAIL | 全 FAIL |

- 对比度：恰好 43 条，分组为 `day/--ink3 6，day-solid/--ink3 3，night/--seal 21，night-solid/--seal 13`。
- cn：规格点名的第 1、2、5、6 条失败；另外第 8 条和 10 个令牌合并也失败，原因相同，即默认 twMerge 把 `text-fs-*` 当成颜色。规格只说这四条「都会失败」，没说只有这四条，所以不矛盾。
- 生成 CSS：反向 49 条违规，正向 12/12 不符。
- 参考实现 `gate_rules.py` 在同一个 HEAD 副本上输出 `== FAIL 20`，各规则计数与测试完全相同。

**恒真断言、空集伪装、吞异常**

- 4 个分组函数都先断言扫描到的文件 ≥ 130。`_token_layer` 固定返回 7 项，`all()` 不会落到空集上。
- 令牌层自检里的 7 个坏变体都用 `str.replace` 构造。如果替换目标不存在，变体就等于好样本，而好样本已断言全部通过，这时 `assert not …` 会直接失败。所以自检不可能空转。
- 源码规则的 `test_` 函数和对比度测试里都没有 try/except。cn 和 css 测试只在依赖探测上 catch，命中就 skip；真正运行时出错，由 `returncode == 0` 断言抓住。
- 坏样本里没有 `<button`、`<br`。规格要求的 7 种好样本写法都在 `required_good` 里，并断言它们不被任何一条规则误伤。

**是否读 docs/、仓库外文件或 git 历史**
- 没有。4 个文件都只经由 `Path(__file__).parents[2]` 读 `frontend/` 下的文件，没有 `git`、`subprocess git`，也没有 `docs` 路径。
- cn 和 css 测试经 `createRequire(frontend/package.json)` 解析依赖，与既有测试 `test_ui_polish_markdown.py` 的探测写法一致。

**skip 只在依赖缺失时触发（模拟 CI）**

做法：在一份没有 `node_modules` 的候选等价副本（标准答案副本加 4 个新测试）里跑：
```
........ss
SKIPPED tests/test_design_system_cn.py:118: Frontend dependencies unavailable: typescript, clsx, tailwind-merge
SKIPPED tests/test_design_system_css.py:159: Frontend dependencies unavailable: typescript, @tailwindcss/node, @tailwindcss/oxide
8 passed, 2 skipped
```
- 源码规则和对比度测试不依赖 node，CI 里照常运行；
- cn 和 css 测试只因为依赖缺失才 skip；本机有依赖时 0 skipped。

---

## 3. 必须修复项

**无。**

---

## 4. 可优化项（不阻断）

1. **F7 的类型词放行是前缀匹配，不按整词。** 这一点参考实现和测试相同，属于规格层面的问题。
   - `val.startswith(("number", "string", "any", "null", …))` 会把 `fontSize: anySize`、`fontSize: numberPx`、`fontSize: nullableSize ?? 14` 这类变量名放过去。
   - `el.style.fontSize = "14px"` 不会被抓，因为左边界排除了 `.`；`style.setProperty("font-size", …)` 也没有覆盖。
   - 我 grep 过，仓库当前 0 处这种写法，所以现在不构成漏洞。
   - 建议下一版规格把放行条件改成整词匹配，例如 `re.match(r"(?:number|string|…)\b", val)`；再给 F7 加一条 `\.style\.fontSize\s*=` 和 `setProperty\(\s*["']font(-size)?["']`。

2. **cn、css 两个测试在源码文件缺失时也会 skip**，即 `utils.ts`、`globals.css` 不存在的情况。这比「只在依赖缺失时 skip」宽了一点。
   - 目前影响很小：`globals.css` 缺失时，源码规则和对比度测试会直接失败；`utils.ts` 缺失时，tsc 和大量 import 也会挂。
   - 建议把这两处改成 `assert …is_file()`。

3. **`test_design_system_css.py` 的 `REQUIRED_PACKAGES` 多了一个 `typescript`**，这个测试并不需要它。如果哪天 typescript 不在而 Tailwind 在，测试会白白 skip。可以删掉。

4. **`frontend/README.md` 新增一节，措辞可以更准。** 内容已覆盖 §T5 的五点，行数 7 行，不超过 10 行；所列事实我核对过，没有写错的。可以改进的地方：
   - 「新写法会被 … 拦下」容易读成「新令牌写法会被拦下」。建议改成「不合规的写法（任意字号、具名字号、旧 shadcn 类、遗留变量等）会被 … 拦下」。
   - 「令牌名见四套主题块」不完整：`--seal-soft`、`--fill`、`--scrim`、`--fs-*` 定义在别名 `:root` 和其后的 `.dark {…}` 里，不在四套主题块里。可以补半句「以及其后的别名 `:root`」。
   - 可以补一句：其中 cn 和生成 CSS 两个测试依赖 `frontend/node_modules`，CI 里会 skip，须本机跑。
   - 这几处措辞大多照抄自规格 §T5 原文，不算执行者的错。

5. **`::backdrop` 改成 `var(--scrim)`，依赖一个较新的浏览器行为**，这是规格 T2 第 23、24 条的内容，执行者照做无误。
   - 只有 Chrome 122+、Firefox 120+、Safari 17.4+ 里，`::backdrop` 才从所属元素继承自定义属性。
   - 更老的 Safari 和 iOS（17.4 之前）解析不到 `--scrim`，遮罩会变成透明。只是外观问题，不影响功能。
   - Claude 的浏览器对比（`browser-compare.txt` 第 9 条）没有注明引擎，大概率只测了 Chromium。
   - 如果要照顾旧 iOS，可以在前面加一行写死的 `background:rgba(31,41,38,.18);` 作兜底，或者写成 `var(--scrim, rgba(31,41,38,.18))`。这需要规格作者定，不在本批白名单内。

6. **依赖探测会向上级目录找 node_modules**，这是既有测试的惯例。`createRequire(frontend/package.json)` 按 Node 的规则逐级往上找：如果 `frontend/node_modules` 缺了，可能会解析到仓库外上级目录里的同名包。真实工作区位于 `ai-workspace/.worktrees/…`，而 `ai-workspace/` 根下就有 `node_modules/`。本机依赖齐全时没有影响，只作提示。

---

## 5. 给执行者的二次修改指令

无，本批不需要返修。第 4 节各项留给规格作者决定是否放进下一批。

---

## 6. 变异实验记录

做法：
- 脚本在 scratchpad 的 `b4rev/mutate.py`；
- 每项先按字节备份目标文件，记下 sha256；改动后只跑 4 个新测试（`-q -p no:cacheprovider --tb=no -rfs`）；
- 跑完写回原字节，校验 sha256；新建的临时文件 `frontend/components/ReviewMutation.tsx` 每项结束即删除；
- 47 项全部还原成功。收尾时对 113 个改动文件做 `shasum -c`，全部 OK；`git status` 仍是 113 项，`ReviewMutation.tsx` 已不存在。
- 每项的结果都是 skip 0。

### 6.1 规格 §7 的 19 项（复现）

| 编号 | 变异 | 必须变红 | 实测变红 | 结果 |
|---|---|---|---|---|
| S01 | Sidebar 一处 `text-fs-13` 改回 `text-sm` | font | font、css | PASS |
| S02 | 写一个 `text-fs-16-5` | font | font | PASS |
| S03 | 写一个 `text-[14px]` | font、css | font、css | PASS |
| S04 | `style={{ fontSize: 14 }}` | font | font | PASS |
| S05 | `` `mobile:text-fs-13${x}` `` | font | font | PASS |
| S06 | `<small>` 删掉 `text-fs-11` | font | font | PASS |
| S07 | globals.css 写 `.zz { font-size: 14px; }` | font、css | font、css | PASS |
| S08 | 一处颜色改回 `text-muted-foreground` | color | color | PASS |
| S09 | 写一个 `text-[var(--ink2)]` | color | color、font（F1 同报） | PASS |
| S10 | 写一个 `var(--rec)` | color | color | PASS |
| S11 | 写一个 `bg-(--slip)` | color | color | PASS |
| S12 | 写一个 `text-[color:var(--ink3)]` | role | role | PASS |
| S13 | 非 Seal 组件写 `var(--stamp)` | role | role | PASS |
| S14 | 一处文字色加 `/60` | role | role | PASS |
| S15 | 两个夜块的 `--seal` 改回 `#BF4537` | contrast、layer | contrast、layer | PASS |
| S16 | 夜 `--chip` 改成 `rgba(74,63,52,0.60)` | contrast | contrast | PASS |
| S17 | `--text-fs-13--line-height` 改成 `1.4` | layer、css | layer、css | PASS |
| S18 | 手机输入框护栏挪进 `@layer base` | layer | layer | PASS |
| S19 | `utils.ts` 改回默认 `twMerge` | cn | cn | PASS |

### 6.2 复核方追加的 28 项

| 编号 | 变异 | 必须变红 | 实测变红 | 结果 |
|---|---|---|---|---|
| X01 | `text-[length:var(--fs-13)]` | font | font | PASS |
| X02 | `text-(--fs-13)` | font | font、color、css | PASS |
| X03 | `[font-size:14px]` | font | font、css | PASS |
| X04 | `"text-" + s` 拼接 | font | font | PASS |
| X05 | `text-fs-xl md:text-fs-14` | font | font | PASS |
| X06 | `--fs-13: 13px` 改成 `14px` | layer | layer | PASS |
| X07 | 行内 `color: "var(--ink3)"` | role | role | PASS |
| X08 | 别名 `:root` 里重定义 `--seal` | contrast、layer | contrast、layer、selfcheck_head | PASS |
| X09 | 昼 `--ink2` 调浅到 `#6A7772` | contrast | contrast、selfcheck_head | PASS |
| X10 | 删掉 `::placeholder` 规则 | layer | layer | PASS |
| X11 | `utils.ts` 漏登记 `fs-16.5` | cn | cn | PASS |
| X12 | `body` 去掉 `font-size` | layer | layer | PASS |
| X13 | `outline-(--ink)` | color | color | PASS |
| X14 | `border-[var(--rule)]` | color | color | PASS |
| X15 | `hover:bg-primary/80` | color | color | PASS |
| X16 | TSX 写 `var(--foreground)` | color | color | PASS |
| X17 | `text-[color:var(--ink2)]/[0.6]` | role | role | PASS |
| X18 | `--text-fs-15--line-height` 改成 `1.6` | layer、css | layer、css | PASS |
| X19 | `.btn` 字号改成 `var(--fs-14)`，即字阶外的变量 | font、css | font、css | PASS |
| X20 | 跨行的 `<sup>` 不带 `text-fs` | font | font | PASS |
| X21 | `--seal-soft` 比例改成 30% | layer | layer、role（R3 白名单按整行放行）、contrast、selfcheck_head | PASS |
| X22 | 行内 `font: "14px serif"` | font | font | PASS |
| X23 | 重新定义 `--glass-border` | color | color | PASS |
| X24 | `fill-[var(--seal)]` | color | color | PASS |
| X25 | 删掉昼两块的 `--stamp`，键集合因此不齐 | layer | layer、contrast、selfcheck_head | PASS |
| X26 | 夜 `--stamp` 改成 `#E56F5D` | layer | layer、contrast | PASS |
| X27 | 删掉 5 个 `--fs-*` 令牌（18–76） | layer | layer | PASS |
| X28 | `md:!text-sm`，`!` 写在前面 | font | font、css | PASS |

函数名缩写：font = `test_font_size_rules`，color = `test_color_rules`，role = `test_role_rules`，layer = `test_token_layer`，contrast = `test_token_contrast`，selfcheck_head = `test_selfcheck_head_tokens_fail`，cn = `test_cn_keeps_size_and_color`，css = `test_generated_css_font_sizes`。

**MISS 数 0 / 47。**

---

## 7. 其他核对

- **§3.2 保留项**。88 个文件与标准答案逐字节相同，以下各项因此都由标准答案保证：
  - `.drawer-panel` 与它前面那个 `@media` 之间没有插入内容；
  - `:focus-visible` 规则没动；
  - `page.tsx` 两段 sha256 锁住的切片没有重排，全量里对应用例通过；
  - `import { cn } from "@/lib/utils";` 写法不变，`VoiceButton.tsx` 和 `ComposerImageMenu.tsx` 没有新增 import；
  - `Seal.tsx` 的 `fontSize="30"` 保留。
- **§5「不允许的做法」**：逐条对照，没有违反。
  - 白名单外改动 0；既有测试只改了 29 行；阈值、白名单和 HEAD 命中数与参考实现一致，没有调低；
  - 没有新增粗体或「·」；没有改文案；没有动 `components/ui/*`、依赖和 lockfile；
  - 副本里没有 git 写操作的痕迹，我自己也没有做任何 git 写操作。
- **执行者报告**：抽查的数字全部与我的实测一致，包括 7836 passed、HEAD 命中表、43 条的分组、最差对比度和 19 项变异结果。E.md 说「10 个令牌合并在 HEAD 上全部失败」，我核对过，16.5 档也在失败之列，属实。
