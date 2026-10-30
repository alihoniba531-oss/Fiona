# 04 复核 R1：遮罩兜底色 + 新测试收紧

- 日期：2026-10-30
- 对象：返修单 `05-fix-r1.md` 的交付。复核副本基于 `647a486`，已套上候选的全部改动（含 R1）；增量见 `.cache/review/r1-delta.diff`。
- 做法：执行者的 `impl/R1.md` 和报告「返修 R1」只当线索，结论都来自本副本里重新跑的结果。变异和改名都在 `.cache/review/work/` 下的副本里做，做完就删。工作树里 4 个改动文件的 sha256 前后一致，`git status` 除 `.cache/review/` 外仍是 125 项。没有做 git 写操作，没有用浏览器。

## 结论：通过

- 改动恰好是返修单第 1 节的三件事，没有夹带别的修改。
- 新增的兜底色和 HEAD 原来的颜色逐条相同；在旧版和新版浏览器里，算出来的遮罩色都和 HEAD 一样。生产构建的产物里兜底也保留着。
- T8 和参考实现逐行等价。自检的坏样本确实能抓住判定空转。
- cn、css 两个测试：源文件缺失时 FAILED，没有 node 或缺依赖时 skip。css 测试去掉 `typescript` 后能真跑通。
- 全量 pytest：7836 passed，0 failed，0 skipped。HEAD 副本上的结果与规格逐条一致。

**必须修复项：无。**

---

## 1. 改动范围（逐字核对 `verify/r1_edits.json`）

**`frontend/app/globals.css`**
- 当前文件的 `git hash-object` 是 `1cb1441…`，和 delta 里返修后的 blob 一致。
- 按 `r1_edits.json` 反向替换，把 `new` 换回 `old`：每条 `new` 在当前文件里恰好出现 1 次。
  - 换回后 blob 是 `73028b1…`，正是 delta 里返修前的 blob；
  - sha256 是 `3943d855…567e34f00`，和 R1.md 的「改前」一致。
- 再正向套用：先断言每条 `old` 恰好出现 `count`=1 次，套完和当前文件逐字节相等，27221 → 27538 字节。
- 所以这个文件只改了这 2 条，没碰别的字节。

**三个测试文件**
- 按 delta 把改动逐处撤回，撤回后的 sha256 与 R1.md 的「改前」逐个相等：

| 文件 | 撤回后 sha256 | 行数 |
|---|---|---|
| `test_design_system_gate.py` | `5cff72a1…809fb8896` | 738 |
| `test_design_system_cn.py` | `74ef4cf1…c803f5291` | 150 |
| `test_design_system_css.py` | `40149dbb…67f168d12` | 201 |

- 这说明三个文件的改动只有 delta 里列出的这些：
  - gate：docstring 从 T1–T7 改成 T1–T8；新增 T8 判定块；自检样本加了 `dialogs` 块；自检里加了 T8 坏样本。
  - cn：源文件检查改成断言，并挪到 node 探测之前。
  - css：同上；另外 `REQUIRED_PACKAGES` 去掉了 `typescript`。

**其余**
- delta 里剩下的都是文档：
  - `03-report.md` 只在末尾追加了「返修 R1」一节，前文没动；
  - 新增了 `impl/R1.md`；
  - `04-review.md`、`05-fix-r1.md`、`verify/claude/*`、`verify/r1_edits.json`、`verify/README.md`，以及 `ref/gate_rules.py` 里的 T8，都是 Claude 放的。
- 没有其他源码文件变化。

## 2. 遮罩兜底在新旧浏览器上的效果

**HEAD 与候选逐条对照**

| 选择器 | HEAD | 候选 |
|---|---|---|
| `.image-preview-dialog::backdrop` | `rgba(31,41,38,.18)` | `var(--scrim, rgba(31,41,38,.18))` |
| `.dark .image-preview-dialog::backdrop` | `rgba(0,0,0,.45)` | `var(--scrim, rgba(0,0,0,.45))` |
| `.confirm-dialog::backdrop` | `rgba(31,41,38,.18)` | `var(--scrim, rgba(31,41,38,.18))` |
| `.dark .confirm-dialog::backdrop` | `rgba(0,0,0,.45)` | `var(--scrim, rgba(0,0,0,.45))` |

- 兜底色与 HEAD 的字面色逐条相同，昼夜没有写反。

**`--scrim` 的来源**
- HEAD 和候选的定义一样：`:root` 里是 `rgba(31,41,38,.18)`，顶层 `.dark` 里是 `rgba(0,0,0,.45)`。
- `.dark` 由 `app/layout.tsx` 挂在 `document.documentElement` 上。
- 整个前端没有别处定义 `--scrim`，也没有 `@property --scrim`，所以不会有注册初始值抢在兜底前面。

**旧版浏览器**（Safari 17.4 之前、Chrome 122 之前、Firefox 120 之前）
- 这些版本里 `::backdrop` 不从任何元素继承，`--scrim` 取不到值，`var()` 就用兜底。
- 选择器是否匹配看所属的对话框元素，所以 `.dark` 祖先的判断和 HEAD 一样有效。
- 夜间那条的特异性是 (0,2,1)，高于昼间的 (0,1,1)，夜间用的是夜间兜底。
- 结果：昼间 `rgba(31,41,38,.18)`、夜间 `rgba(0,0,0,.45)`，和 HEAD 相同。返修前只有一条 `var(--scrim)`，遮罩是透明的；这次修好了。

**新版浏览器**
- `::backdrop` 从对话框继承自定义属性，`--scrim` 取到 html 上的值：昼间 `.18`、夜间 `.45`，和 HEAD 相同。兜底不起作用。

**生产构建实测**
- 在副本里跑 `npm run build`，退出码 0。产物 CSS 里是这四条：
  ```
  .image-preview-dialog::backdrop{background:var(--scrim,#1f29262e)}
  .dark .image-preview-dialog::backdrop{background:var(--scrim,#00000073)}
  .confirm-dialog::backdrop{background:var(--scrim,#1f29262e)}
  .dark .confirm-dialog::backdrop{background:var(--scrim,#00000073)}
  ```
- 兜底没有被 Lightning CSS 去掉，只是改写成了等值的 hex：`#1f29262e` = `rgba(31,41,38,.18)`，`#00000073` = `rgba(0,0,0,.45)`。
- 产物里 Tailwind 只给 `::backdrop` 注入了 `--tw-*` 变量，没有 `--scrim`，所以旧版里兜底确实会生效。
- 限制：没有在真实的旧版 Safari 上实测。本单不许用浏览器，本机也没有旧版；上面是按规范推导，再加上核对构建产物得出的。

## 3. T8 是否忠实于 `verify/ref/gate_rules.py`

**逐行对照**
- 期望映射一样：4 个选择器，各对应一个值。
- 判法一样：遍历全部块，凡选择器以 `::backdrop` 结尾，就收集它的 `background`；结果必须等于 `{选择器: [值]}`。
- 用到的 `_parse_blocks`、`_decls_of`、`_walk`、`_strip_css_comments` 与参考实现的 `parse_blocks`、`decls_of`、`walk`、`strip_css_comments` 逻辑等价。
- 新加的注释里也有 `::backdrop` 字样，但会先被剥成空白，不会混进选择器。
- 本副本上跑参考门禁：28 项全 PASS，`== FAIL 0`。

**真实文件上的变异**
- 在副本里改 `globals.css`，跑 `-k token_layer`：

| 变异 | 结果 |
|---|---|
| C0 不改（正控） | 2 passed |
| M1 只去掉 `.image-preview-dialog` 的昼间兜底 | `test_token_layer` 失败，只有 T8 FAIL，AssertionError |
| M2 只去掉 `.dark .confirm-dialog` 的夜间兜底 | 同上 |
| M3 昼夜兜底色对调 | 同上 |
| M4 回到返修前（只剩两条 `var(--scrim)`） | 同上 |
| M5 改回 HEAD 的字面色 | 同上 |
| M6 删掉 `.dark .image-preview-dialog` 一条 | 同上 |
| M7 多加一条 `.foo::backdrop` | 同上 |
| M8 同一选择器写两次 `background` | 同上 |
| C1 还原后 | 2 passed |

**自检坏样本能不能抓住空转**
- 在副本里改测试代码，让 T8 空转，跑 `test_selfcheck_token_layer`：
  - S1 T8 恒为真；
  - S2 只比选择器集合；
  - S3 只比去掉兜底以后的值。
- 三种都失败，失败点都在第 769 行，也就是 T8 坏样本那条断言。
- 如果哪天坏样本没替换到任何内容，`bad == css`，`assert not True` 一样会失败，不会悄悄空转。

## 4. cn、css 两个测试

**代码顺序**
- 两个测试的源文件断言都在 `shutil.which("node")` 之前。
- 之后的 skip 只剩三种：没有 node；探测命令本身失败；缺包。

**副本实测**
- 每个副本带 `frontend/{app,components,lib,package.json}`、克隆的 `node_modules`、两个测试文件，外加一个空的 `pytest.ini` 固定 rootdir：

| 情形 | 结果 |
|---|---|
| A 不改（正控） | 2 passed |
| B 把 `utils.ts` 改名 | cn **FAILED**：`AssertionError: frontend/lib/utils.ts is missing…`；css passed |
| C 把 `globals.css` 改名 | css **FAILED**：`AssertionError: frontend/app/globals.css is missing…`；cn passed |
| D 两个都改名，且 `PATH=/usr/bin:/bin`（没有 node） | 2 failed，都是源文件缺失的 AssertionError |
| E 文件都在，没有 node | 2 skipped，原因都是 Node.js is unavailable |
| F 删掉副本里的 `typescript` | 在 `frontend/` 里 `require.resolve('typescript')` 报 MODULE_NOT_FOUND；css **PASSED**，真跑完了编译和断言；cn 因 typescript 缺失 skip |
| G 删掉 `@tailwindcss/oxide` 和 `clsx` | 2 skipped |

**小结**
- css 测试确实不再依赖 typescript。
- cn 测试保留 typescript 是对的：它的 RUNNER 直接 `require('typescript')`。
- CI 的 backend 任务是完整 checkout，源文件在，而且没有 `node_modules`，所以照旧 skip，不会因为这次改动变红。

## 5. 全量 pytest 与 HEAD 副本

**本副本**
- 全量 pytest，在 `backend/` 下按 §3.5 清掉代理变量后台跑：**7836 passed、0 failed、0 skipped**，35 warnings，319.89 秒，退出码 0。`-rs` 输出里一条 SKIPPED 都没有。
- 4 个新测试单独跑：10 passed，0 skipped。
- 三个参考门禁：
  - `gate_rules.py`：28 项全 PASS，`== FAIL 0`；
  - `contrast_check.py`：退出码 0，不达标 0 条；
  - `gate_twcss.mjs`：退出码 0，`scannedFiles=131`，违规 0，令牌编译不符 0。
- 生产构建：在副本里跑 `npm run build`，退出码 0（见第 2 节）。

**HEAD 副本**
- 跑法同规格 §T3：`git archive HEAD`，加当前的 4 个新测试，加克隆的 `node_modules`，带 `-rf -rs`。
- 结果：**7 failed、3 passed、0 skipped**。7 个失败全是 AssertionError，分别在 gate:308（×3）、gate:566、cn:149、css:200、contrast:320。
- 命中数与规格表逐条相等：

| 组 | 命中数 |
|---|---|
| 字号规则 | F1 300、F3 563、F6 1、F7 2、F8 7、F9 9；F2、F4、F5、F10 为 0 |
| 颜色规则 | K1 144、K2 223、K3 50、K4 8、K5 69；K6 为 0 |
| 角色规则 | R2 1、R4 18；R3 为 0 |

- 令牌层 T1–T8 全部 FAIL，T8 也在其中。
- 对比度不达标 43 条：昼 `--ink3` 6、昼素瓷 `--ink3` 3、夜 `--seal` 21、夜素瓷 `--seal` 13。
- 生成 CSS：反向违规 49 条，正向 12 个类全部不符。
- cn：第 1、2、5、6 条失败。第 8 条和令牌用例也失败，和上一轮复核看到的一样。
- 参考门禁在 HEAD 上是 `== FAIL 21`，和 `verify/README.md` 一致。

## 必须修复项

无。

## 可优化项（不阻断）

1. **另外 6 个对话框的遮罩没有兜底。**
   - 涉及 `SongProjectCard.tsx`、`novel/NovelSettingsDialog.tsx`、`studio/BrainTrial.tsx`、`studio/QuoteDialog.tsx`、`studio/ShotCard.tsx`、`studio/SourceChoices.tsx`。
   - 它们用的是 Tailwind 写法 `backdrop:bg-[color:var(--scrim)]`，构建产物是 `background-color:var(--scrim)`，旧版 Safari 上同样透明。
   - HEAD 上本来就这样，不是本批引入的，也不在本单范围。
   - 以后要统一的话，可以改成带兜底的公共类。昼夜兜底色不同，需要像本单一样各写一条。
2. **css 测试没有探测 `tailwindcss` 和 `tw-animate-css`。**
   - 这两个包是 `globals.css` 用 `@import` 引进来的。
   - 实测删掉 `tw-animate-css` 后，测试是 FAILED（`Can't resolve 'tw-animate-css'`），不是 skip。这是偏严的方向，不会假通过，可以不动。
   - 如果要补：`tailwindcss` 可以直接加进 `REQUIRED_PACKAGES`。`tw-animate-css` 不能照搬 `require.resolve`：实测它装着也会报 `ERR_PACKAGE_PATH_NOT_EXPORTED`，加进去会让测试永远 skip。
3. **T8 的自检只有一种坏样本**：四条兜底一起去掉。
   - 第 3 节的 M1–M8 已经证明真实判定是严的。
   - 想把它写进自检的话，可以再加三个坏样本：只去掉一条、昼夜对调、少一条夜间规则。
4. **文档小瑕疵。**
   - `impl/R1.md` 里 css 测试的「改前」sha256 缩写写成了 `40149dbb…668d12`，实际是 `…67f168d12`。
   - `impl/R1.md` 说 `git status` 「仍为 124 项，无新增文件」；报告说「124 → 125，新增 `impl/R1.md`」。以报告为准：本副本扣掉 `.cache/review/` 之后正好 125 项。

## 附：复核用的脚本与记录

都放在 `.cache/review/work/`：
- `mut_gate.py`：T8 的变异；
- `mut_cn_css.sh`：cn、css 的改名和缺依赖；
- `head_run.sh`：HEAD 副本；
- `globals.pre-r1.css`：反推出来的返修前文件；
- 日志：`full-pytest.log`、`head-pytest.log`、`head-gate-ref.txt`、`gate-ref.txt`、`contrast.txt`、`build.log`。

副本和构建目录都已删除。
