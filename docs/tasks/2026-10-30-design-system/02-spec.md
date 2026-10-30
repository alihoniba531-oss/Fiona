# 02 规格：设计系统收口（UI 复核第四批）

- 规格版本：v2（2026-10-30）。v1 经四个视角的对抗复核后修订，v1 没有派单。
- 基线：`main` @ `647a486`；工作分支 `feat/design-system`（本工作树）。
- 来源：`docs/tasks/2026-10-28-ui-review/01-audit.md` 的 P1-5（对比度）、P2-6（旧令牌与新令牌双轨）、P2-7（字号 30 种）。
- 用户已拍板：
  1. 10-28 审计「待拍板」按推荐：
     - 接受 8 档字阶 11 / 12 / 13 / 15 / 16.5 / 18 / 22 / 30，展示字 46 / 76 另列，从此禁止新的任意字号；
     - 对比度按审计方向修。
  2. 10-30，看过在 HEAD 上注入样式的对比图后：
     - 授权按附件 `verify/test_literals.tsv` 修改**既有测试的 29 行字面量**。只换写法，断言逻辑、文案、次数一概不动；门禁逐行核对。
     - 14px 按角色分：
       - 界面字 → 13，包括表单标签、按钮、状态、表格、读数；
       - 正文段落、标题、页头导语、导航、列表或卡片标题 → 15；
       - 文字输入控件 → 16.5。
     - 夜间朱字用 `#E56F5D`，昼间不变。
  3. 10-30 确认本规格 v2 时：
     - 8 处原来继承祖先行高的任意值字号补 `leading-[inherit]`，保持原行高；
     - 复核查出的 14px 角色误判按规则改正：12 处改 13、3 处改 15，分集卡片标题补 15；带说明文字的设置项标题按列表项标题保持 15；
     - 登录页标语桌面端 20 → 22；
     - 3 处导语加 `text-pretty`，匹配页空态图标保持原来的淡色。
- 级别：L3（整仓机械替换 + 令牌取值变化）。**本规格经用户确认后才派执行者。**
- 执行者：dsh（DeepSeek Flash，max）。门禁与真实浏览器实测由 Claude 做；独立复核用 Opus 5.5 xhigh。

---

## 1. 产品目标

把「影青釉」设计系统从「能看」收到「守得住」：

1. **字号只剩十个值**：8 档加 2 个展示字。全站 30 种字号收成 `--fs-*` 令牌和 `text-fs-*` 工具类；新写任意字号会被门禁拦下。
2. **对比度达标**：
   - 昼主题淡墨三号 `--ink3` 加深，并且只许当装饰，不再用于文字；
   - 夜主题朱色整体换成 `#E56F5D`，朱字在所有底色、悬停、录音态上都 ≥ 4.5:1；朱印另用 `--stamp`，保持原来的深朱；
   - 透明度修饰的文字、默认颜色的占位符也改到达标。
3. **写法只剩一种**：旧 shadcn 令牌类（`text-muted-foreground` 等）全部换成新令牌的 `text-[color:var(--x)]` 写法；遗留变量名（`--amber-ink`、`--rec`、`--glass-border` 等）清掉。除 18 处带透明度的文字色按 §T1 吸附到令牌外，编译后逐字等价。
4. **门禁防回退**：4 个新测试文件把上述规则写成离线断言。
   - 源码规则、对比度两个只读源码，CI 的 backend 任务直接跑；
   - tailwind-merge、生成 CSS 两个依赖 `frontend/node_modules`，CI 里会 skip，本机门禁必须跑过。

用户能看到的变化（对比图与浏览器实测见 §6 第 7 条）：
- 字号：
  - 原 14px 的字按角色分：界面字小 1px 到 13；正文、标题、导语、导航、列表或卡片标题大 1px 到 15；
  - 文字输入框统一 16.5：原 16px 的（含用户气泡）、原 14px 的两处、广场桌面发帖框原 13px（+3.5px）；
  - 20px 的区块标题和登录页标语变 22；Markdown 一、二级标题（18.5、17.5）同为 18；
  - 9–10.5px 的角标、时间变 11；
  - 登录页品牌字在手机上也用 76，原来是 64。
- 行高：
  - `text-sm` 换成 15 的，每行高 2.5px（20 → 22.5）；换成 13 的不变；
  - 原来没写行高、继承祖先行高的 8 处任意值字号，补 `leading-[inherit]` 保持原行高。包括书斋空态标题、匹配页「匹配是什么」、广场官方搭档卡片标题、分身名称输入框、新建书的估算说明；
  - 其余个别元素差 0.5–3px；
  - 正文变 15 后，个别段落会多折一行，例如 390 宽的分身抽屉导语、知识库卡片说明；分身抽屉导语和书斋两处说明补了 `text-pretty`，末行不留单字。
- 颜色：
  - 夜间朱色更亮，偏珊瑚色。这包括朱字，以及点赞心形、垃圾桶悬停、录音波形、标签边框这些图标和边线；朱印不变；
  - 默认占位符从半透明墨色改成 `--ink2`。与已填文字的对比从约 4.5 降到 2.4（夜 3.1 → 2.0）；HEAD 里已有 14 处占位符本来就是 `--ink2`；
  - 18 处带透明度的文字色按深浅吸附到 `--ink` 或 `--ink2`。例如对话记录抽屉的条数、时间和来源卡网址变深，与日期同色；广场展开卡的导语与正文同为 `--ink`；
  - 匹配页空态的人形图标保持原来的淡色，改用 `opacity-40`。

## 2. 现状事实（HEAD `647a486` 实测）

**工具链与基线**
- next 16.4.3、tailwindcss 4.3.0、tailwind-merge 3.5.0。
- 基线：`npx tsc --noEmit` 0 错误；`npm run lint` 0 errors、25 warnings；`npm run build` 通过；全量 pytest **7826 passed、0 skipped、0 failed**。

**扫描面与规模**
- 扫描面：`frontend/app`、`frontend/components`、`frontend/lib` 下的 .ts .tsx .js .jsx .mjs .css，共 138 个文件。其中 `frontend/components/ui/*` 7 个文件是 shadcn 原件，全仓 0 处 import，**豁免、不改**；实际扫描 131 个。
- 字号：
  - 应用代码（不含 `components/ui`）的 TS/TSX 里有 821 处字号类：
    - 具名类 563 处：`text-sm` 291、`text-xs` 207、`text-xl` 28、`text-base` 26、`text-lg` 11；
    - 任意值 258 处；
    - `components/ui` 另有 12 处，豁免；
  - CSS 里写死的 `font-size` 8 条，另有 1 条手机输入框护栏 `max(16px, 1em)`；
  - 行内 `fontSize` 3 处；
  - 不带字号类的 `<small>` 7 处，预检样式按父元素的 80% 算，会落在字阶外。
- 颜色：
  - 旧 shadcn 颜色类 321 处，其中应用代码 223 处，`components/ui` 98 处；
  - 不带类型的 `util-[var(--x)]` 写法 69 处（text 42、border 18、bg 9）；
  - 遗留变量 `--glass-border` 16 处、`--amber-ink` 3 处、`--rec` 4 处、`--rec-soft` 1 处；
  - TSX 里直接引用 shadcn 别名变量 8 处：`var(--ring)` 5、`var(--accent)` 2、`var(--foreground)` 1。

**主题与别名（`frontend/app/globals.css`）**
- 4 套主题块：`:root`（昼，55–108 行）、`.dark`（夜，110–163）、`:root[data-solid]`（昼素瓷，165–218）、`.dark[data-solid]`（夜素瓷，220–273）。素瓷块把 `--ink3`、`--seal` 原样重抄了一遍，改值时四块都要看。
- 别名在第二个 `:root`（275–297 行）。
- `dark` 类和 `data-solid` 属性都挂在 `<html>` 上。`:root[data-solid]` 的特异度高于 `.dark`，所以夜素瓷的层叠是：昼块 → `.dark` → `:root[data-solid]` → `.dark[data-solid]`。

**对比度**（WCAG 2.x）
- 叠在 `--paper` 上：昼 `--ink3` 2.79、`--seal` 5.66；夜 `--seal` 3.61。
- 夜间朱字落在瓷片（`--tile`）、釉片（`--glass` / `--glass2`）、悬停底上为 2.81–3.57；全部底色里最差的是 chip 叠 `--hi`，2.78。
- `--ink3` 当文字只有 1 处：`components/AgentExchangeWorkspace.tsx:132` 的表头，11px。
- 透明度修饰的文字里有 6 处不到 4.5，最低 1.60（广场「链接失效」）。
- 28 个占位符里有 12 个没写颜色，走预检默认的 `currentcolor 50%`，昼 2.96。

**Tailwind 与 tailwind-merge 的行为**（仓库自带版本实测）
- `@theme inline { --text-fs-13: var(--fs-13); --text-fs-13--line-height: calc(20 / 13); }` 会生成 `.text-fs-13{font-size:var(--fs-13);line-height:var(--tw-leading, calc(20 / 13))}`。
- 档名可以带小数点：`--text-fs-16\.5` 生成 `text-fs-16.5`，oxide 扫描器能抽到。CSS 自定义属性名不能有裸 `.`，所以变量叫 `--fs-16-5`。
- 具名字号自带行高：xs 16px、sm 20px、base 24px、lg 28px、xl 28px。任意值不带，元素继承祖先的行高；令牌带不带，取决于是否写了配套的 `--line-height`。
- **tailwind-merge 3.5.0 默认把不认识的 `text-<名>` 当成文字颜色**：
  - `cn("text-fs-13 text-[color:var(--ink2)]")` 会删掉字号；
  - `cn("text-primary-foreground text-fs-13")` 会删掉颜色；
  - 应用代码里有 8 处 `cn()` 调用同时带字号和颜色，例如 `Sidebar.tsx:125`、`:143`，`VoiceButton.tsx:160`，`ComposerImageMenu.tsx:93`；
  - 用 `extendTailwindMerge` 把 10 个令牌登记为字号组后，两种情况都正确。
- 这些写法会悄悄失效，禁止使用：
  - `text-[var(--fs-13)]`、`text-(--fs-13)`：会编译成 `color:`；
  - `text-[length:--fs-13]`：生成非法值，浏览器丢弃；
  - 类名紧贴 `${`：oxide 抽不到，例如 `app/profile/page.tsx:98` 的 `mobile:text-[26px]${…}` 从来没生效过。
- 同名时颜色优先：`--text-x` 与 `--color-x` 并存时，`text-x` 输出的是 color。所以令牌一律带 `fs-` 前缀。

**手机输入框护栏**
- `globals.css:455-460` 有一条不在任何 `@layer` 里的规则：`:root:not([data-shell="desktop"]) input, … { font-size: max(16px, 1em); }`。它压过所有工具类，保证 iPhone 聚焦时不放大。
- 没有任何测试锁着这一条。

**既有测试**
- 含 frontend 字样的测试文件 47 个、676 个用例（由 `grep -l -i frontend backend/tests/*.py` 得到），其中真正读前端源码的 45 个、604 个；基线全过。
- 整仓替换后，这 47 个文件里有 17 个用例会变红，原因全是断言里锁着旧写法的字面量。用户已授权改的那 29 行，正好覆盖这 17 个用例。Claude 已在一份模拟副本上实测：改完这 29 行，676/676 全绿。
- 另有两段 sha256 锁不受影响，它们锁的是 `page.tsx` 的「旅行规划卡」和「错误处理」切片，切片里没有任何样式写法。

**CI**
- backend 任务所在的 runner 没有 `frontend/node_modules`，依赖 TypeScript 的前端用例在 CI 里会 skip，所以 CI 绿不代表它们过。
- 本地门禁要求全量 0 skipped。

## 3. 约束

### 3.1 白名单（只许改动或新增这些）

1. `verify/replacements.tsv` 里出现的 76 个前端文件（第一列），只做表里列出的替换。
2. `frontend/app/globals.css`：总表里的 2 处，加上 T2 第 1–26 条。
3. `frontend/lib/utils.ts`、`frontend/components/Seal.tsx`：只做 T2 第 27、28 条。
4. 新测试 4 个：
   - `backend/tests/test_design_system_gate.py`
   - `backend/tests/test_design_tokens_contrast.py`
   - `backend/tests/test_design_system_cn.py`
   - `backend/tests/test_design_system_css.py`
5. `verify/test_literals.tsv` 里的 10 个既有测试文件，**只改表里那 29 行**。
6. `frontend/README.md`：新增一节「设计令牌与门禁」（T5）。
7. 本任务目录 `docs/tasks/2026-10-30-design-system/` 下：
   - 新增 `03-report.md`；
   - `impl/` 下放你写的辅助脚本（如 T1 的套用脚本）和各 agent 的记录（见 §9）；变异用的备份也放这里或系统临时目录，收尾删掉；
   - 本目录里 Claude 放的文件（`02-spec.md`、`verify/**`）只读，一个字节也不许动。

`frontend/components/ui/*`、`desktop/**`、`frontend/package.json` 和 lockfile 一律不动；不新增任何依赖。

### 3.2 必须原样保留

- 所有用户可见的文字一字不改。本批只动样式写法和令牌，不动文案。
- `components/ui/*`，以及 globals.css 里给它们用的 shadcn 别名：`--background` 到 `--ring` 这几行，和 `@theme inline` 里对应的 `--color-*` 注册。只有 `--color-sidebar-*` 8 行按 T2 删除。
- 手机输入框护栏规则的位置不变：仍然不在任何 `@layer` 里，选择器不变。只按 T2 把 `max(16px, 1em)` 改成 `max(var(--fs-16-5), 1em)`。
- `globals.css` 里手机抽屉、目录弹层的那个 `@media (width < 48rem)` 块逐字不动。既有测试靠 `css.index(".drawer-panel")` 和它前面最近的 `@media` 定位，所以：
  - 新内容不得插在这两者之间；
  - 注释里也不得提前出现 `.drawer-panel`。
- 第一个 `@layer base` 里的 `:focus-visible` 规则（`outline:1px solid var(--ink)`）不动。
- `page.tsx` 里被 sha256 锁住的两段（「旅行规划卡」「错误处理」）不重排。
- 组件里 `import { cn } from "@/lib/utils";` 这一行的写法不变：4 个测试文件里有 7 个探针脚本（4 个 SSR、3 个 fakeReact），会按原文替换这一行来加载 `VoiceButton.tsx` 与 `ComposerImageMenu.tsx`。也不给这两个组件新增 import。
- `components/Seal.tsx` 里 SVG 的 `fontSize="30"` 是 viewBox 坐标单位，不改。

### 3.3 既有测试：授权范围

- **只**允许改 `verify/test_literals.tsv` 列出的 29 行，每行只把 `old` 列那一段原文换成 `new` 列。每段原文在该行里恰好出现一次。
- 同一文件的其他行、其他文件，一概不许改。
- 改完后，`git diff --numstat HEAD -- backend/tests/` 里的既有文件只能是这 10 个，每个文件的增删行数等于表里该文件的行数。门禁会逐文件核对，再逐行比对内容。
- 这 29 行改完，对应的 17 个用例必须由红转绿，其余用例不得变化。

### 3.4 禁止的写法（实测会悄悄失效）

- 字号只能用 `text-fs-11 / 12 / 13 / 15 / 16.5 / 18 / 22 / 30 / 46 / 76` 这 10 个工具类，带不带 variants 前缀都行，例如 `max-md:text-fs-11`、`mobile:text-fs-22`、`@[640px]:text-fs-15`。也可以带 `!` 后缀，例如 `text-fs-30!`。
- CSS 与行内样式只能用 `var(--fs-*)`，而且必须是这 10 个之一。
- 不得写 `text-[var(--fs-*)]`、`text-(--fs-*)`、`text-[length:…]`、`text-fs-16-5`、`[font-size:…]`。
- 不得新写任何 `text-[Npx]` 或具名字号 `text-xs/sm/base/lg/xl…`。
- 颜色只用 `text-/bg-/border-[color:var(--令牌)]`，不得写圆括号简写 `text-(--x)`、`bg-(--x)`。
- 不得让类名紧贴 `${`：`${` 前面留一个空格。

### 3.5 执行环境

- 沙箱是 workspace-write：可写的是本工作树和系统临时目录。
- `frontend/node_modules`、`backend/.venv` 已就位，不要重装，不要 `npm ci`。跑 npm / npx 前先 `export npm_config_cache=/tmp/fiona-npm-cache`。
- pytest 一律在 `backend/` 下这样跑：
  ```bash
  env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider …
  ```
  沙箱的 `NO_PROXY` 里有 `[::1]`，不清掉的话 httpx 在收集阶段就报 InvalidURL。
- 全量 pytest 约 5 分钟：用后台任务跑，等它结束再写结果。跑不完就照实写明，由 Claude 在沙箱外补跑。报告里不许留占位符。
- `app/page.tsx` 开头有 UTF-8 BOM。前两批的编辑工具两次把它去掉了，所以不要用编辑工具改这个文件；T1 一律用脚本按字节读写。
- git 只许做读操作：status、diff、show、archive、log。

## 4. 任务

**顺序**：T1 → T2、T3、T4、T5 并行 → T6。

原因有两个：
- 总表的行列号对应的是 HEAD 原文，必须在任何其他改动之前套用；
- T2 第 12 条要改的 `globals.css` 第 300 行，是总表已经改过的结果。

### T1 逐处替换（附件 `verify/replacements.tsv`）

**文件格式**：UTF-8，制表符分隔，**不做引号解析**（有的格子本身带英文引号），第一行是表头。

| 列 | 含义 |
|---|---|
| `file` | 相对 `frontend/` 的路径 |
| `line` / `col` | HEAD `647a486` 上的行号、列号，**都从 1 开始**；`col` 是 `old` 首字符所在列 |
| `old` | 原写法，必须恰好出现在 `line:col` 处 |
| `new` | 替换成什么 |
| `kind` | `size` 字号、`color` 旧 shadcn 类、`syntax` B 式改 A 式、`legacy` 遗留变量、`contrast` 对比度 |
| `note` | 依据：规则名，后面可能跟着调查期自动标注的角色。角色标注只供审阅、可能不准，一律以 `new` 列为准 |

共 1158 行、76 个文件：size 831、color 223、syntax 69、legacy 32、contrast 3。

**套用规则**
0. 读写方式：
   - 列号按 Unicode 字符计，不是字节。有 137 行在 `col` 之前就有中文，按字节算会错位；
   - `app/page.tsx` 开头有 UTF-8 BOM，必须原样保留：不要用 `utf-8-sig` 读写，也不要去掉；
   - 76 个文件都是 LF 行尾，文件末尾的换行保持原样。
1. 按文件分组；同一行按 `col` **从大到小**依次替换，前面的列号才不会失效。
2. 每一行替换前先断言：`line:col` 处的原文就是 `old`。任何一行对不上就**停下来说明**，不得跳过或自行修正。
3. `new` 为空、`old` 不以空格开头：删除这个类名，并按下面三种情况处理相邻空格。这类行只有 3 行，套完后断言它们与下面的结果逐字相等：
   - (a) 左邻是空格、右邻不是 `${`：删类名和左侧一个空格。`login/page.tsx:145` → `… tracking-[0.01em] max-md:mt-7">Chloe</h1>`
   - (b) 左邻不是空格（类名紧跟在引号后）：删类名和右侧一个空格。`MessageText.tsx:69` → `            : "tracking-[.08em] text-[color:var(--ink2)]";`
   - (c) 右邻是 `${`：只删类名，两侧空格都不动。`profile/page.tsx:98` → `… font-medium tracking-[0.16em] ${embedded ? " sr-only" : ""}`
4. `old` 以空格开头：原样删掉 `old` 那一段，只有 1 行，即广场的 ` opacity-60`。
5. `old` 为空：在 `col` 处插入 `new`，共 8 处：
   - 7 处 `<small>` 补 `text-fs-11 `；
   - 1 处分集卡片标题补 `text-fs-15 `（`studio/EpisodePlan.tsx:74`）；
   - `col` 指向 `className="` 后面的第一个字符。
6. 其余行：把 `old` 原样换成 `new`。
7. A 套完、B 开始之前，用同一张表反向核对一遍：每一处 `new` 都出现在预期位置上，这一行的其余字符与 HEAD 相同。只做这一次；B 改过 `globals.css` 之后，第 300 行会挪到第 307 行，不要再按行号核对。

**表里的取舍**（已由 Claude 定好，执行时照表即可，这里只作说明）
- 字号：
  - 9 / 10 / 10.5 → 11；11.5 → 12；13.5 → 13；14.5 → 15；
  - 14 按用户定的角色分：
    - 界面字 → 13：表单标签、单选标签、展开开关、按钮、状态、读数、表格；
    - 正文、标题、导语、导航和标签页、列表或卡片标题 → 15；设置页里带说明文字的设置项标题（如「素瓷（减少透明度）」）按列表项标题算，也是 15；
  - 文字输入控件统一 16.5：原 16、原 14 的两处（`BreakdownDialog.tsx:8`、`StyleCard.tsx:56`）、原 13 的一处（`plaza/page.tsx:613`）；
  - 16 → 16.5；17 / 17.5 / 18.5 → 18；20 → 22，包括登录页标语；23 → 22；26、28、32 → 30。
  - 特殊几处：
    - `MessageText.tsx:34` 行内代码的 `.92em`（实算 15.18）→ `text-fs-15`；
    - `MessageText.tsx:69` 的 `text-[1em]` 删掉：预检样式本来就让 h1–h6 继承字号；
    - 天气卡温度的行内 `fontSize: 32` → `fontSize: "var(--fs-30)"`；
    - 星图标签的 `"fontSize": "13px"` → `"fontSize": "var(--fs-13)"`。
- 行高与折行：
  - 8 处原来没写行高、继承祖先行高的任意值字号，换成带配套行高的令牌后行盒会矮 3–8px，所以 `new` 里在令牌后面补了 ` leading-[inherit]`，保持原来的继承行为；
  - 3 处导语和说明在 `new` 里补了 ` text-pretty`，避免手机上末行只剩一个字。
- 颜色：
  - 旧 shadcn 类换成等价的 A 式。例如 `text-muted-foreground` → `text-[color:var(--ink2)]`，`bg-secondary/50` → `bg-[color:var(--slip)]/50`。variants 前缀和非文字类的透明度后缀都原样保留。
  - **文字色**带透明度后缀的，按深浅吸附到令牌：`ink` 的 /60–/80 → `--ink2`，/85–/95 → `--ink`；`ink2` 的 /40、/50 → `--ink2`。
  - 唯一的例外是匹配页空态的装饰图标 `text-muted-foreground/40`：它不是文字，改成 `text-[color:var(--ink2)] opacity-40`，保持原来的淡色。
  - `text-destructive` → `text-[color:var(--seal)]`。夜间 `--seal` 本身已经是达标的文字色，见 T2。
- 写法：B 式 `text-/bg-/border-[var(--x)]` → A 式 `…-[color:var(--x)]`，只限这三类颜色工具。`shadow-[…]` 等不动。
- 遗留变量：
  - `var(--glass-border)` → `var(--rule)`；
  - `var(--ring)`、`var(--foreground)`、`var(--amber-ink)` → `var(--ink)`；
  - `var(--accent)` → `var(--slip)`；
  - `var(--rec)` → `var(--seal)`；
  - `var(--rec-soft)` → `var(--seal-soft)`。
- 对比度：
  - `AgentExchangeWorkspace.tsx:132` 表头的 `var(--ink3)` → `var(--ink2)`；
  - 广场「失效链接」那一行的 `text-[color:var(--ink)] opacity-40` → `text-[color:var(--ink2)]`，里面「（链接失效）」的 ` opacity-60` 删掉。

### T2 令牌层（逐字改动，共 28 条）

**以 `verify/t2_edits.json` 为准**：28 条按顺序排列，字段为 `n`（序号，与下文一致）、`file`、`count`（原文恰好出现几次）、`old`、`new`。删除项的 `new` 是空串，`old` 含行尾换行。B 的脚本直接读这个文件套用：
- 每条替换前先断言 `old` 在文件里恰好出现 `count` 次，对不上就停下来说明；
- 按字节读写，不碰别的字符。

下文的「改前 / 改后」代码块只供审阅。它们在 Markdown 里多缩进了 3 个空格：每行去掉开头恰好 3 个空格才是原文，行首剩下的 2 或 4 个空格要保留；块内只有空格的行视为空行；不要按最小缩进整体去空格。「改后：整段删除，不留空行」指连同这几行的行尾换行一起删掉。两者有出入时以 JSON 为准。

各条改动的用意：
- **字号令牌**：
  - 10 个 `--fs-*` 写在第二个 `:root` 里，字号不随昼夜、素瓷变化；
  - `@theme inline` 里登记 10 个 `--text-fs-*`。其中 12、13、15、22 四档带配套行高：12 / 13 / 22 档和原来的 `text-xs`、`text-sm`、`text-xl` 行盒一样高，15 档用 1.5 倍；
  - `body` 设根字号 `var(--fs-16-5)`。设在 `body` 上而不是 `html` 上，rem 间距因此不变。
- **对比度**：
  - 昼两套主题 `--ink3` → `#6F7C76`；
  - 夜两套主题 `--seal` → `#E56F5D`；
  - 四套主题都新增 `--stamp`，取原来的朱色：昼 `#A8322A`，夜 `#BF4537`；
  - `--rec-soft` 改名为 `--seal-soft`，基色改用 `--stamp`，悬停底、录音底与原来完全一样；
  - 朱印（`Seal.tsx`）的底色改用 `--stamp`。印章字对底色仍是昼 5.92:1、夜 4.53:1，与原来相同。
- **清理别名**：删 `--amber-ink`、`--dim`、`--rec`、`--rec-soft`、`--glass-border`、`--glass-strong`、`--glass-hi`、`--shadow`、`--sidebar-*`，以及 `@theme inline` 里的 8 行 `--color-sidebar-*`。`--fill`、`--scrim` 是真令牌，保留。
- **组件类与基础层**：
  - 8 个组件类写死的字号改用 `var(--fs-*)`；
  - 默认占位符颜色设为 `var(--ink2)`；
  - 两个对话框的 `::backdrop` 改用 `var(--scrim)`，并删掉各自的 `.dark` 覆盖；
  - 打字光标改用 `--ink`；
  - 手机输入框护栏改为 `max(var(--fs-16-5), 1em)`。
- **`lib/utils.ts`**：用 `extendTailwindMerge` 把 10 个令牌登记为字号组。

**`frontend/app/globals.css`**

1. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --color-sidebar-ring: var(--sidebar-ring);
     --color-sidebar-border: var(--sidebar-border);
     --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
     --color-sidebar-accent: var(--sidebar-accent);
     --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
     --color-sidebar-primary: var(--sidebar-primary);
     --color-sidebar-foreground: var(--sidebar-foreground);
     --color-sidebar: var(--sidebar);
   ```
   改后：整段删除，不留空行。

2. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --radius-4xl: calc(var(--radius) * 2.6);
   }
   ```
   改后：
   ```text
     --radius-4xl: calc(var(--radius) * 2.6);
     --text-fs-11: var(--fs-11);
     --text-fs-12: var(--fs-12);
     --text-fs-12--line-height: calc(16 / 12);
     --text-fs-13: var(--fs-13);
     --text-fs-13--line-height: calc(20 / 13);
     --text-fs-15: var(--fs-15);
     --text-fs-15--line-height: 1.5;
     --text-fs-16\.5: var(--fs-16-5);
     --text-fs-18: var(--fs-18);
     --text-fs-22: var(--fs-22);
     --text-fs-22--line-height: calc(28 / 22);
     --text-fs-30: var(--fs-30);
     --text-fs-46: var(--fs-46);
     --text-fs-76: var(--fs-76);
   }
   ```

3. 原文恰好出现 2 次，全部替换。

   改前：
   ```text
     --ink3: #84918B;
   ```
   改后：
   ```text
     --ink3: #6F7C76;
   ```

4. 原文恰好出现 2 次，全部替换。

   改前：
   ```text
     --seal: #A8322A;
   ```
   改后：
   ```text
     --seal: #A8322A;
     --stamp: #A8322A;
   ```

5. 原文恰好出现 2 次，全部替换。

   改前：
   ```text
     --seal: #BF4537;
   ```
   改后：
   ```text
     --seal: #E56F5D;
     --stamp: #BF4537;
   ```

6. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --radius: 0.625rem;
   ```
   改后：
   ```text
     --radius: 0.625rem;
     --fs-11: 11px; --fs-12: 12px; --fs-13: 13px; --fs-15: 15px; --fs-16-5: 16.5px;
     --fs-18: 18px; --fs-22: 22px; --fs-30: 30px; --fs-46: 46px; --fs-76: 76px;
   ```

7. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --amber-ink: var(--ink); --dim: var(--ink3); --rec: var(--seal);
   ```
   改后：整段删除，不留空行。

8. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --rec-soft: color-mix(in srgb, var(--seal) 12%, transparent);
   ```
   改后：
   ```text
     --seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);
   ```

9. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --glass-border: var(--rule); --glass-strong: var(--glass2); --glass-hi: var(--rim);
   ```
   改后：整段删除，不留空行。

10. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --sidebar: var(--glass); --sidebar-foreground: var(--ink); --sidebar-primary: var(--btn);
     --sidebar-primary-foreground: var(--btnink); --sidebar-accent: var(--slip);
     --sidebar-accent-foreground: var(--ink); --sidebar-border: var(--rule); --sidebar-ring: var(--ink);
   ```
   改后：整段删除，不留空行。

11. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     --fill: rgba(31,41,38,.03); --shadow: 0 1px 2px var(--drop);
   ```
   改后：
   ```text
     --fill: rgba(31,41,38,.03);
   ```

12. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     * { @apply border-[color:var(--rule)] outline-[color:var(--ink)]/50; }
   ```
   改后：
   ```text
     * { @apply border-[color:var(--rule)] outline-[color:var(--ink)]/50; }
     ::placeholder { color: var(--ink2); }
   ```

13. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
       font-family: var(--font-sans-stack); -webkit-font-smoothing: antialiased;
   ```
   改后：
   ```text
       font-family: var(--font-sans-stack); font-size: var(--fs-16-5); -webkit-font-smoothing: antialiased;
   ```

14. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   font-variant-numeric:tabular-nums; font-size:12px; color:var(--ink2); }
   ```
   改后：
   ```text
   font-variant-numeric:tabular-nums; font-size:var(--fs-12); color:var(--ink2); }
   ```

15. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   color:var(--ink); font-size:13px; letter-spacing:.08em;
   ```
   改后：
   ```text
   color:var(--ink); font-size:var(--fs-13); letter-spacing:.08em;
   ```

16. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   .btn-danger:hover { background:var(--rec-soft); border-color:transparent; }
   ```
   改后：
   ```text
   .btn-danger:hover { background:var(--seal-soft); border-color:transparent; }
   ```

17. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   border:1px solid var(--rule2); color:var(--ink2); font-size:12px; white-space:nowrap; }
   ```
   改后：
   ```text
   border:1px solid var(--rule2); color:var(--ink2); font-size:var(--fs-12); white-space:nowrap; }
   ```

18. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   border-radius:4px; font-size:11px; border:1px solid var(--rule2);
   ```
   改后：
   ```text
   border-radius:4px; font-size:var(--fs-11); border:1px solid var(--rule2);
   ```

19. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   padding:10px 15px; font-size:16px; line-height:1.8;
   ```
   改后：
   ```text
   padding:10px 15px; font-size:var(--fs-16-5); line-height:1.8;
   ```

20. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   padding:0; font-size:16.5px; line-height:1.95; }
   ```
   改后：
   ```text
   padding:0; font-size:var(--fs-16-5); line-height:1.95; }
   ```

21. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   color:var(--seal); font-size:12px; animation:porcelain-like-pop
   ```
   改后：
   ```text
   color:var(--seal); font-size:var(--fs-12); animation:porcelain-like-pop
   ```

22. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     color: var(--amber-ink);
   ```
   改后：
   ```text
     color: var(--ink);
   ```

23. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     .image-preview-dialog::backdrop { background:rgba(31,41,38,.18); }
     .dark .image-preview-dialog::backdrop { background:rgba(0,0,0,.45); }
   ```
   改后：
   ```text
     .image-preview-dialog::backdrop { background:var(--scrim); }
   ```

24. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
     .confirm-dialog::backdrop { background:rgba(31,41,38,.18); }
     .dark .confirm-dialog::backdrop { background:rgba(0,0,0,.45); }
   ```
   改后：
   ```text
     .confirm-dialog::backdrop { background:var(--scrim); }
   ```

25. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
       font-size: max(16px, 1em);
   ```
   改后：
   ```text
       font-size: max(var(--fs-16-5), 1em);
   ```

26. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   .image-model-segments .chip { flex-shrink:0; padding-inline:8px; font-size:12px; }
   ```
   改后：
   ```text
   .image-model-segments .chip { flex-shrink:0; padding-inline:8px; font-size:var(--fs-12); }
   ```


**`frontend/lib/utils.ts`**

27. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   import { twMerge } from "tailwind-merge"
   
   export function cn
   ```
   改后：
   ```text
   import { extendTailwindMerge } from "tailwind-merge"
   
   // 字阶令牌 text-fs-*（见 app/globals.css）登记为字号组，否则 tailwind-merge 会把它们当成文字颜色，与颜色类互相吞掉。
   const twMerge = extendTailwindMerge({
     extend: { theme: { text: ["fs-11", "fs-12", "fs-13", "fs-15", "fs-16.5", "fs-18", "fs-22", "fs-30", "fs-46", "fs-76"] } },
   })
   
   export function cn
   ```


**`frontend/components/Seal.tsx`**

28. 原文恰好出现 1 次，全部替换。

   改前：
   ```text
   <rect x="2" y="2" width="52" height="52" rx="1" fill="var(--seal)"/>
   ```
   改后：
   ```text
   <rect x="2" y="2" width="52" height="52" rx="1" fill="var(--stamp)"/>
   ```

### T3 新测试（门禁，4 个文件）

**总则**
- 全部离线，不依赖 git 历史，不读仓库外文件，只读仓库内的前端源码。
- 需要 node 和 `frontend/node_modules` 的用例，照既有测试的写法探测依赖，缺失时 `pytest.skip`。可参考 `backend/tests/test_ui_polish_markdown.py` 的 `require_node_typescript` 与转译写法。CI 的 backend 任务会因此跳过它们；本机门禁要求 0 skipped。
- **参考实现**：`verify/ref/` 下有三个脚本，用法见 `verify/README.md`。
  - `gate_rules.py` 对应 T3-1，`contrast_check.py` 对应 T3-2，`gate_twcss.mjs` 对应 T3-4；
  - Claude 的门禁用的就是它们。规则、正则、阈值和算法以脚本为准，本节表格只是摘要；
  - 测试要把逻辑写进测试文件本身，不得 import、执行或读取 `docs/` 下的任何文件。
- **在 HEAD 上必须失败，而且失败的原因要对**：
  - 除自检函数外，每个 `test_` 函数在 HEAD 上都必须失败，失败必须是 `AssertionError`，不能是 KeyError 一类的崩溃；
  - 不要按单条规则参数化，HEAD 上本来就 0 命中的规则会照样通过。按下面各节写明的分组，每组写一个 `test_` 函数，组内逐条规则汇总后一次性断言；
  - 失败信息逐条列出每条规则的命中数和前 3 处；
  - HEAD 上的命中数必须逐条等于下面各表的「HEAD」列。主代理把对照表写进 `03-report.md`，Claude 的门禁也逐条比对。
- **自检**：每条规则都配一段会命中的合成坏样本、一段不该命中的合成好样本，证明正则没有空转、也不误伤合法写法。
  - 自检集中写在名字以 `test_selfcheck_` 开头的函数里，它们在 HEAD 上也通过；
  - 好样本至少包括 `text-fs-30!`、`mobile:text-fs-22`、`@[640px]:text-fs-15`、`text-fs-16.5`、`text-fs-22 leading-[inherit]`、`text-fs-15 text-pretty`、注释里的 `text-fs-12.`；
  - 坏样本不要用 `<button`、`<br` 这类标签，以免干扰 §6 第 5 条的粗体计数。
- **HEAD 正控的跑法**（只读，不碰工作树）：
  1. 每次都用 `mktemp -d` 新建目录，例如 `$H`；
  2. `git archive HEAD | tar -x -C $H`；
  3. 只把自己负责的新测试拷进 `$H/backend/tests/`；
  4. 用 `cp -cR` 把 `frontend/node_modules` 克隆到 `$H/frontend/`；
  5. 在 `$H/backend` 下，用本工作树的 `backend/.venv/bin/python` 按 §3.5 的写法跑，加 `-rf`。
  - 预期：除 `test_selfcheck_*` 外全部失败，0 skipped，命中数与表一致。
  - 主代理收口时另建一个目录，4 个新测试一起跑一次，结果写进报告。

**T3-1 `backend/tests/test_design_system_gate.py`：源码规则**

- 扫描面：`frontend/app`、`frontend/components`、`frontend/lib` 下的 .ts .tsx .js .jsx .mjs .css，跳过 `node_modules`、`.next`，豁免 `frontend/components/ui/`。
- .css 文件先去掉 `/* … */` 注释再扫。
- 每个分组函数都先断言扫描到的文件 ≥ 130 个（HEAD 实测 131）。
- 改后每条规则都必须是 0 处命中。

记号：`D` = 左边界 `(?<![^\s"'`{}(!])`；`V` = variants 链 `(?:[^\s"'`{}(]*?:)?`；`R` = 右边界 `(?=$|[\s"'`{}),;!/$])`。

| 规则 | 禁止什么（要点；精确正则见 `verify/ref/gate_rules.py`） | HEAD |
|---|---|---|
| F1 | `text-[…]` 方括号里不以 `color:` 开头。任意值字号、`length:`、`var(--fs-*)` 当颜色、B 式文字色都算 | 300 |
| F2 | 任何 `text-(…)` 圆括号写法 | 0 |
| F3 | 具名字号 `text-(xs\|sm\|base\|lg\|xl\|[2-9]xl)`，可带 variants、`!`、`/行高` | 563 |
| F4 | 任意属性 `[font-size:…]`、`[font:…]`，一律禁止 | 0 |
| F5 | 拼接字号类：`text-${`、`text-[${`、`"text-" +` | 0 |
| F6 | 字号类紧贴 `${` | 1 |
| F7 | 行内 `fontSize` / `font`（style 对象的键、JSX 属性）的值不是 `"var(--fs-…)"` 十个之一。类型声明里的 `fontSize: number` 不算；白名单只有 `components/Seal.tsx` 的 `fontSize="30"` | 2 |
| F8 | `<small>`、`<sub>`、`<sup>` 开标签里没有 `text-fs-`。整文件匹配，开标签可以跨行 | 7 |
| F9 | .css 里 `font-size` / `font` 的值不是 `var(--fs-…)` 十个之一（可带 `!important`）。整文件、忽略大小写，可跨行；白名单 `inherit`、`max(var(--fs-16-5), 1em)` | 9 |
| F10 | `text-fs-<值>` 的值不在 {11, 12, 13, 15, 16.5, 18, 22, 30, 46, 76} 里，例如 `text-fs-14`、`text-fs-16-5`、`text-fs-xl`。句末的英文句点不算进值 | 0 |
| K1 | `text-muted-foreground` | 144 |
| K2 | 全部 shadcn 语义颜色类（含 K1 那一种），可带 `/NN` | 223 |
| K3 | 遗留变量名的使用或定义：`--amber-ink`、`--rec`、`--rec-soft`、`--dim`、`--glass-border`、`--glass-strong`、`--glass-hi`、`--shadow`、`--sidebar*`；`var(--x, 回退值)` 也算 | 50 |
| K4 | .ts/.tsx/.js 里直接写 shadcn 别名变量，如 `var(--accent)`、`var(--ring)`、`var(--foreground)` | 8 |
| K5 | B 式颜色写法：`颜色工具-[var(--x)]`（`x` 不以 `fs-` 开头），必须写成 `[color:var(--x)]` | 69 |
| K6 | 颜色工具的圆括号简写：`text-(`、`bg-(`、`border-(`、`ring-(`、`fill-(`、`stroke-(` 等，一律禁止 | 0 |
| R2 | `--ink3` 或 `--dim` 当文字色：`text-[(color:)var(--ink3)]`、`text-((color:)--ink3)`、`color: "var(--ink3)"`（引号含反引号） | 1 |
| R3 | `var(--stamp)` 出现在两处原文以外。只放行 globals.css 的 `--seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);` 和 Seal.tsx 的 `fill="var(--stamp)"` | 0 |
| R4 | 文字色带透明度后缀：`text-[color:var(--x)]`、`text-(--x)`、`text-(muted-)?foreground` 后面跟 `/N`、`/[…]` 或 `/(…)` | 18 |

令牌层：按花括号深度把 `app/globals.css` 切成块（参考实现里的 `parse_blocks`），逐块断言。

| 项 | 断言 |
|---|---|
| T1 | 10 个 `--fs-*` 只定义在别名 `:root`（第二个 `:root`）里，各一次，值依次为 11px / 12px / 13px / 15px / 16.5px / 18px / 22px / 30px / 46px / 76px；没有别的 `--fs-*` |
| T2 | `@theme inline` 块内登记 10 个 `--text-fs-N: var(--fs-N)`，16.5 档写作 `--text-fs-16\.5: var(--fs-16-5)`；行高恰为 12 档 `calc(16 / 12)`、13 档 `calc(20 / 13)`、15 档 `1.5`、22 档 `calc(28 / 22)`，没有别的 `--text-fs-*`；块外不出现 `--text-fs-` |
| T3 | `:root` 与 `:root[data-solid]` 的 `--ink3` 为 `#6F7C76`、`--seal` 与 `--stamp` 为 `#A8322A`；`.dark` 与 `.dark[data-solid]` 的 `--seal` 为 `#E56F5D`、`--stamp` 为 `#BF4537`；四个主题块的键集合相同；别名 `:root` 和它后面的顶层 `.dark {…}` 不定义被检查的颜色（`--ink`、`--ink2`、`--ink3`、`--seal`、`--stamp`、各底色、`--btn`、`--btnink`、`--glyph`） |
| T4 | `--seal-soft` 只在别名 `:root` 定义一次，值为 `color-mix(in srgb, var(--stamp) 12%, transparent)` |
| T5 | 手机输入框护栏：值为 `max(var(--fs-16-5), 1em)` 的规则恰好一条；选择器恰为 `:root:not([data-shell="desktop"]) input`、`… textarea`、`… select` 三项；外层只有一个顶层 `@media (width < 48rem)`，没有任何 `@layer` |
| T6 | `::placeholder { color: var(--ink2); }` 是第一个 `@layer base` 的直接子规则 |
| T7 | 第一个 `@layer base` 里的 `body` 规则块有 `font-size: var(--fs-16-5)` |

HEAD 上 T1–T7 每项都失败。

分组（函数名照写）：

| 函数 | 规则 | HEAD 上因哪些规则失败 |
|---|---|---|
| `test_font_size_rules` | F1–F10 | F1、F3、F6、F7、F8、F9 |
| `test_color_rules` | K1–K6 | K1–K5 |
| `test_role_rules` | R2–R4 | R2、R4 |
| `test_token_layer` | T1–T7 | 全部 |

**T3-2 `backend/tests/test_design_tokens_contrast.py`：令牌对比度**

**解析**
- 解析 `app/globals.css` 的 4 套主题，层叠方式同浏览器：
  - 夜 = 昼块 + `.dark`；
  - 昼素瓷 = 昼块 + `:root[data-solid]`；
  - 夜素瓷 = 昼块 + `.dark` + `:root[data-solid]` + `.dark[data-solid]`。
- 同时断言：四个主题块的键集合相同；别名 `:root` 与其后的顶层 `.dark {…}` 不定义被检查的颜色键。
- 参与计算的令牌值只许 `#RRGGBB` 或 `rgba(r,g,b,a)`，其它写法直接失败。
- 悬停 / 录音底按别名 `:root` 里 `--seal-soft` 的定义解析：`color-mix(in srgb, var(--X) N%, transparent)`，取各主题 X 的值，透明度 N/100。解析不到就直接失败。

**算法**
- 按 WCAG 2.x 相对亮度公式计算对比度。
- 半透明底先在 sRGB 里按 alpha 叠到不透明底上，逐通道四舍五入到整数，再计算。

**底色集合 S**
- `--paper`、`--hi`、`--slip`；
- `--glass`、`--glass2`、`--chip`、`--tile`、`--mount`：不透明时直接用；半透明时分别叠在 `--paper` 和 `--hi` 上，各算一次。

**断言**（四套主题都要过）

| 前景 | 背景 | 门槛 |
|---|---|---|
| `--ink`、`--ink2` | S 中每一个 | ≥ 4.5 |
| `--seal`（朱字） | S 中每一个 | ≥ 4.5 |
| `--seal`（朱字） | 悬停 / 录音底：`--seal-soft` 叠在 S 中以 `--paper`、`--hi`、`--glass`、`--glass2`、`--tile` 为基的那些底上 | ≥ 4.5 |
| `--ink3` | S 中除 `--chip` 系以外的每一个 | ≥ 3 |
| `--btnink` | `--btn` | ≥ 4.5 |
| `--glyph`（印章字） | `--stamp` | ≥ 4.5 |

- `--ink3` 只当装饰（Markdown 列表圆点），不会落在 chip 上，所以它的判据排除 chip 系。
- 分组：
  - `test_token_contrast` 断言上表。HEAD 上（没有 `--stamp`，按 `--seal` 代算）不达标恰好 43 条：昼 `--ink3` 6、昼素瓷 `--ink3` 3、夜 `--seal` 21、夜素瓷 `--seal` 13；
  - `test_selfcheck_head_tokens_fail` 是正控：用当前 globals.css 解析出的四套主题，只把昼两块的 `--ink3` 换回 `#84918B`、夜两块的 `--seal` 换回 `#BF4537`，去掉 `--stamp`，悬停底基色按 `--seal`。断言不达标的（主题，前景）集合恰为 {(昼, `--ink3`), (昼素瓷, `--ink3`), (夜, `--seal`), (夜素瓷, `--seal`)}，共 43 条，并且夜 `--seal` 的失败项里有 `seal-soft@` 底。这条不依赖 git 历史。
- Claude 已在模拟替换后的副本上算过，全部达标：
  - 昼：`--ink2` 最差 4.64、朱字最差 4.70、`--ink3` 最差 3.22；
  - 夜：朱字最差 4.56、`--ink3` 最差 3.16；
  - 印章字 4.53。

**T3-3 `backend/tests/test_design_system_cn.py`：tailwind-merge 配置**

做法：用 node 加载 `frontend/node_modules` 里的 `clsx`、`tailwind-merge`，并用 TypeScript 转译 `frontend/lib/utils.ts`，依赖缺失就 skip。然后断言下面各项：

| 输入 | 期望输出 |
|---|---|
| `cn("text-fs-13", "text-[color:var(--ink2)]")` | 两个类都保留 |
| `cn("text-[color:var(--ink)]", "text-fs-16.5")` | 两个类都保留 |
| `cn("text-fs-12", "text-fs-13")` | 只剩 `text-fs-13` |
| `cn("max-md:text-fs-11", "max-md:text-fs-12")` | 只剩 `max-md:text-fs-12` |
| `cn("text-[13px]", "text-fs-13")` | 只剩 `text-fs-13` |
| `cn("leading-6", "text-fs-13")` | 只剩 `text-fs-13` |
| `cn("text-fs-22 leading-[inherit]")`、`cn("text-fs-15 text-pretty")` | 原样保留 |
| `cn("btn btn-quiet h-8 px-2.5 text-fs-12", "text-[color:var(--seal)] bg-[color:var(--seal-soft)]")` | 原样保留全部类 |
| 10 个令牌逐个与 `text-[color:var(--ink)]` 合并 | 两个都在 |

全部写在一个 `test_cn_keeps_size_and_color` 里。在 HEAD 的 `utils.ts` 上，第 1、2、5、6 条都会失败。

**T3-4 `backend/tests/test_design_system_css.py`：生成后的 CSS**

做法：
- 用 `frontend/node_modules` 里的 `@tailwindcss/node` 的 `compile`，加上 `@tailwindcss/oxide` 的 `Scanner`，按真实的 `app/globals.css` 编译；
- sources 为 `app/`、`components/`、`lib/`，排除 `components/ui/`；
- 不写盘、不跑 next build。

断言：
- 扫描到 ≥ 130 个文件。
- **反向**：对生成的 CSS 全文扫描（不按块切），每一条 `font-size` / `font` 的值只能是：
  - 10 个 `var(--fs-*)` 之一，可带 `!important`；
  - 预检白名单 `inherit`、`1em`、`75%`、`80%`；
  - `max(var(--fs-16-5), 1em)`。
- 不出现 `color: var(--fs-`。
- **正向**：用 `compiler.build([...])` 单独编译这 12 个类：10 个令牌，加 `max-md:text-fs-11`、`text-fs-30!`。逐条断言规则体（空白归一后）与下表完全相同：

| 选择器 | 规则体 |
|---|---|
| `.text-fs-11` / `.text-fs-18` / `.text-fs-30` / `.text-fs-46` / `.text-fs-76` | `font-size: var(--fs-N);` |
| `.text-fs-16\.5` | `font-size: var(--fs-16-5);` |
| `.text-fs-12` | `font-size: var(--fs-12); line-height: var(--tw-leading, calc(16 / 12));` |
| `.text-fs-13` | `font-size: var(--fs-13); line-height: var(--tw-leading, calc(20 / 13));` |
| `.text-fs-15` | `font-size: var(--fs-15); line-height: var(--tw-leading, 1.5);` |
| `.text-fs-22` | `font-size: var(--fs-22); line-height: var(--tw-leading, calc(28 / 22));` |
| `.text-fs-30\!` | `font-size: var(--fs-30) !important;` |
| `.max-md\:text-fs-11` | `@media (width < 48rem) { font-size: var(--fs-11); }` |

写成一个 `test_generated_css_font_sizes`。依赖缺失就 skip。HEAD 上反向有 49 条违规（例如 `14px`、`var(--text-base)`），正向 12 条全部不符。

### T4 既有测试字面量（附件 `verify/test_literals.tsv`）

格式：制表符分隔、不做引号解析。四列为 `file`（相对 `backend/tests/`）、`line`、`old`、`new`。

逐行把 `old` 原样换成 `new`：
- 替换前断言该行里 `old` 恰好出现 1 次；
- 共 29 行、10 个文件；
- 其他行一个字节也不许动。

| 文件 | 行 | 改什么 |
|---|---|---|
| test_empty_states_agents.py | 24、25、36、37、41、42、92、126、143 | `text-sm/xs text-muted-foreground` → `text-fs-13/12 text-[color:var(--ink2)]` |
| test_empty_states_match_profile.py | 86 | `text-xs` → `text-fs-12` |
| test_empty_states_settings_privacy.py | 105 | 隐私说明折叠开关 `text-sm` → `text-fs-13` |
| test_mobile_chat_fix.py | 222、226 | 选行用的 `border-[var(--carve)]` → `border-[color:var(--carve)]`；`max-md:text-[11px]` → `max-md:text-fs-11` |
| test_novel_p21_frontend.py | 95、158 | `text-[16px]` → `text-fs-16.5`；`text-[13px] text-[var(--ink2)]` → `text-fs-13 text-[color:var(--ink2)]` |
| test_novel_p2_frontend.py | 32 | 手机底栏 `text-sm` → `text-fs-15` |
| test_song_frontend.py | 39、42 | `tag shrink-0 text-xs` → `text-fs-12` |
| test_ui_polish_beijing_time.py | 247 | `text-[30px]` → `text-fs-30` |
| test_ui_polish_composer_controls.py | 49、63、64、100、101、243、266、271、276 | `text-xs/sm` → `text-fs-12/15`；`--rec` / `--rec-soft` → `--seal` / `--seal-soft`。266 行是反向断言，一并改名，否则它会变成恒真 |
| test_ui_polish_markdown.py | 337 | `--amber-ink` → `--ink` |

### T5 文档：`frontend/README.md`

新增一节「设计令牌与门禁」，10 行以内，写清：
- 字号只用 10 个 `text-fs-*`，CSS 与行内样式用 `var(--fs-*)`；
- 颜色只用 `text-/bg-/border-[color:var(--令牌)]`，令牌名见 `app/globals.css` 的四套主题块；
- `--ink3` 只当装饰，`--stamp` 只给朱印，朱字用 `--seal`；
- 新写法会被 `backend/tests/test_design_system_*.py` 与 `test_design_tokens_contrast.py` 拦下；
- `components/ui/*` 是未使用的 shadcn 原件，豁免。

### T6 报告 `03-report.md`

见 §7。

## 5. 不允许的做法

- 改附件 29 行以外的任何既有测试、夹具或测试辅助模块；为了让测试通过去改 §3.2 的保留项。
- 不按总表、自行取整或改判字号档。对某一行的取舍有异议，停下来说明，不要改表。
- 调低本规格或参考实现里写死的阈值、白名单、HEAD 命中数，或者为了过测试删掉规则。
- 改任何用户可见文案；改 `components/ui/*`、`desktop/**`、依赖与 lockfile。
- 使用 §3.4 禁止的写法；为字号新建 TS 模块再 import；给 `ComposerImageMenu`、`VoiceButton` 新增 import。
- 把令牌块或注释插进 `.drawer-panel` 与它前面那个 `@media (width < 48rem)` 之间；改动手机输入框护栏的选择器或把它挪进 `@layer`。
- 新增粗体（`font-semibold`、`font-bold`、`fontWeight` ≥ 600、`<strong>`、`<b>` 不带 `font-normal`）；新写带「·」的文案。
- 白名单外的任何文件改动；任何 git 写操作（commit、checkout、stash、reset、restore）。

## 6. 验收标准（Claude 逐条复跑，以 Claude 的结果为准）

在仓库根执行。第 1–6 条执行者也要自己跑，并写进报告；第 5 条里的逐字节比对只由 Claude 做。

1. `cd frontend && npx tsc --noEmit` → 退出码 0。
2. `cd frontend && npm run lint` → 0 errors，warnings ≤ 25（HEAD 为 25）。
3. `cd frontend && rm -rf .next && npm run build` → 退出码 0。
4. `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` → **全量**，0 failed，0 skipped，passed ≥ 7826 + 新增用例数。既有 7826 条一条不少。按 §3.5 清掉代理变量。
5. 结构判据：
   - 执行者跑：
     - `python3 -I docs/tasks/2026-10-30-design-system/verify/ref/gate_rules.py .` → `== FAIL 0`；
     - `python3 -I …/verify/ref/contrast_check.py frontend/app/globals.css` → 退出码 0；
     - `node …/verify/ref/gate_twcss.mjs frontend` → 退出码 0；
     - §T1 第 7 条的反向核对、§3.3 的 numstat 核对、T2 的逐条次数核对；
   - Claude 另外做逐字节比对。「标准答案」= HEAD 套总表，再套 T2 全部 28 条（`verify/t2_edits.json`），再套 29 行测试字面量；与候选的 76 个总表文件、`utils.ts`、`Seal.tsx` 和 10 个既有测试逐字节比对；
   - 粗体与「·」：比较范围是 76 个总表文件、`utils.ts`、`Seal.tsx`、`frontend/README.md` 和 10 个既有测试。逐文件比较 HEAD 与候选，下面两项的出现次数都不得增加：
     - `font-semibold`、`font-bold`、`fontWeight`、`<strong`、`<b` 后跟空白或 `>`；
     - 「·」。
     - 总表改到的行里，原本就有 `<b className="font-normal …">` 和「·」，所以不能按「diff 新增行里 0 处」来判。新测试、`03-report.md`、`impl/` 不在比较范围内。
6. 改动集合：
   - `git status --porcelain --untracked-files=all` 只出现 §3.1 白名单里的路径，加上本任务目录；
   - 本任务目录里 Claude 放的文件（`02-spec.md`、`verify/**`）的 sha256 与派单时一致。
7. 真实浏览器实测，由 Claude 在隔离实例里做：
   - 范围：
     - HEAD 与候选用同一脚本，共 13 个画面：对话页、六个抽屉、设置页滚到「永久删除账号」处、交流记录、匹配、名片、新建书、导演知识库；
     - 4 套主题：昼、夜、昼素瓷、夜素瓷；2 种视口：1440×900、390×844；
     - 手机上没有工作室入口，那 4 个组合不量；
     - 世界抽屉的热榜接口两边回放同一份录制数据，排除外部内容变化的干扰。
   - 【改】表示 HEAD 上应失败、候选应通过；【回归】表示两边都要过。
   - 判据：
     - 【改】所有可见文字的计算字号都 ∈ {11, 12, 13, 15, 16.5, 18, 22, 30, 46, 76}，只豁免 SVG 内文字。HEAD 上应能抓到字阶外的值，例如 14、16、20。
     - 【改】设置页「永久删除账号」的朱字对截图取样的背景 ≥ 4.5，四套主题都量。交流记录表头的 `--ink3` 由源码规则 R2 把关：隔离实例里没有交流记录，表头不渲染。
     - 【回归】版式：
       - 页头、输入区、主导航、竖排书签、打开的抽屉、确认框这些地标，位置和尺寸与 HEAD 相差 ≤ 2px；
       - 手机输入区空闲高度 ≤ 140px；
       - 不新增横向溢出、不新增被裁切的文字；
       - 不超过 12 个字的短标签不新增换行，按文字节点的行盒数判断；
       - 手机上原本 ≥ 40px 的可点区域不跌破 40；
       - 每段文字的行高不比 HEAD 低 2px 以上；字号变小的，按字号比例折算后再比；
       - 每个画面、每个框架里的可见文字与 HEAD 逐段相同，不计位置。
     - 【回归】两个对话框的遮罩颜色与 HEAD 相同。
     - 只报告、不判失败：行数比 HEAD 多的文字块逐条列出，由 Claude 看截图确认。
     - 截图：对话页、设置抽屉、分身抽屉、广场抽屉、书斋、新建书、历史页、匹配页，昼夜与两种视口各一组，Claude 逐张看过。
   - Claude 已用这套量具在 HEAD 与「标准答案」之间跑过一遍，全部通过：
     - 字号普查在 HEAD 上抓到 14、16、13.5 等 11 种字阶外的值；
     - 朱字对比度昼 5.31 / 5.78、夜 6.07 / 5.64，HEAD 夜间只有 3.70 / 3.43；
     - 行高判据在没补 `leading-[inherit]` 的上一版表上报了 12 处，补上后为 0；
     - 每条【回归】判据都做过反向验证：人为注入回归，判据确实报了失败。

## 7. 交付：变更总结（写进 `03-report.md`）

1. 修改与新增的文件清单。
2. 实现了什么，与 T1–T6 逐项对应。
3. 拆分表：派出过的全部 agent，以及各自负责的文件。
4. §6 第 1–6 条的实际结果：
   - 第 4 条写 passed / skipped 数；
   - 第 5 条写每条规则的命中数；
   - 新测试在 HEAD 副本上的结果：每个函数失败与否、失败类型，以及各规则命中数与 T3 表的对照。
5. 变异自检。每个变异都按字节备份、改完还原并校验 sha256；单独跑 4 个新测试文件，记下哪些函数变红。下表每一行，「必须变红」列里的函数都要变红：

| 变异 | 必须变红 |
|---|---|
| 把任意一处 `text-fs-13` 改回 `text-sm` | `test_font_size_rules` |
| 写一个 `text-fs-16-5` | `test_font_size_rules` |
| 写一个 `text-[14px]` | `test_font_size_rules`、`test_generated_css_font_sizes` |
| 写 `style={{ fontSize: 14 }}` | `test_font_size_rules` |
| 写 `mobile:text-fs-13${x}` | `test_font_size_rules` |
| 给某个 `<small>` 删掉 `text-fs-11` | `test_font_size_rules` |
| 在 globals.css 写 `.zz { font-size: 14px; }` | `test_font_size_rules`、`test_generated_css_font_sizes` |
| 把一处颜色改回 `text-muted-foreground` | `test_color_rules` |
| 写一个 `text-[var(--ink2)]` | `test_color_rules` |
| 写一个 `var(--rec)` | `test_color_rules` |
| 写一个 `bg-(--slip)` | `test_color_rules` |
| 写一个 `text-[color:var(--ink3)]` | `test_role_rules` |
| 在某个非 Seal 组件里写 `var(--stamp)` | `test_role_rules` |
| 给一处文字色加 `/60` | `test_role_rules` |
| 把夜 `--seal` 改回 `#BF4537` | `test_token_contrast`、`test_token_layer` |
| 把夜 `--chip` 改成 `rgba(74,63,52,0.60)` | `test_token_contrast` |
| 把 `--text-fs-13--line-height` 改成 `1.4` | `test_token_layer`、`test_generated_css_font_sizes` |
| 把手机输入框护栏挪进 `@layer base` | `test_token_layer` |
| 把 `utils.ts` 改回默认的 `twMerge` | `test_cn_keeps_size_and_color` |

6. 未完成或需人工确认的地方；主动偏离及理由。
7. 已知局限，照实写：
   - 普通（非素瓷）主题下，直接落在远山画上的 `--ink2` 文字，实际像素对比度可能低于令牌计算值。这一类只能截图取样，本批不处理；
   - `components/ui/*` 仍保留旧写法和 shadcn 别名，它们没有被引用；
   - 80 处 HTML 静态行内 style 颜色（如 `style={{ borderColor: "var(--rule)" }}`）保持原样，没有改成类名；
   - `app/settings/page.tsx:166` 的 `tracking-[0.24em]${…}` 同样紧贴 `${`、从来没生效过，但它不是字号类，不在本批范围内。

## 8. 何时停下来问

只有影响「实现什么」的问题才停下来，例如：
- 规格自相矛盾；
- 总表某一行在 HEAD 上对不上；
- 按规格做会让 29 行以外的既有测试变红；
- 某条做不到。

只影响「怎么实现、怎么验证」的问题，自己决定，并在报告里写明理由。任何情况下都不回滚已完成的工作。**你实测到的事实优先于规格里的断言**，两者不符就停下来说明。

## 9. 执行方式

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分。主代理只做拆分、派发、汇总、白名单检查、跑门禁和写报告。

**两个工作流**
- 第一个工作流只跑 A。A 完成并做完 §T1 第 7 条的反向核对后，再起第二个工作流跑 B–G。这样 B–G 里有一个失败，也不会连累 A 的结果。
- 工作流整体报错时不会返回部分结果。这时主代理先读 `impl/` 下的记录、`git status` 和 `git diff --stat`，只重派没有完成记录的 agent，已完成的不重做。

| agent | 负责 | 文件 |
|---|---|---|
| A 总表 | T1：写一个套用脚本放在 `impl/`，把 `replacements.tsv` 套到 76 个文件上，再按 §T1 第 7 条反向核对 | 表里第一列的 76 个文件，含 `globals.css` 第 300 行的 2 处 |
| B 令牌层 | T2：按 `verify/t2_edits.json` 逐条套用 28 条改动 | `app/globals.css`（除第 300 行那 2 处）、`lib/utils.ts`、`components/Seal.tsx` |
| C 源码门禁 | T3-1 | `test_design_system_gate.py` |
| D 对比度 | T3-2 | `test_design_tokens_contrast.py` |
| E cn 与 CSS | T3-3、T3-4 | `test_design_system_cn.py`、`test_design_system_css.py` |
| F 既有测试 | T4：只改 29 行 | 附件里的 10 个测试文件 |
| G 文档 | T5 | `frontend/README.md` |

**每个 agent 的任务说明**
- 自包含，并写明「不得调用 subagent / subagent_fork / workflow」。
- 不要把 T1、T2 或规则表的原文转抄进工作流脚本。JS 字符串会吃掉反斜杠，`--text-fs-16\.5` 会变成 `--text-fs-16.5`；模板字符串里的 `${` 还会被当成插值。任务说明里只写「先读 `docs/tasks/2026-10-30-design-system/02-spec.md` 的 §T1 / §T2 / §T3 和 `verify/` 下的附件，逐字照做」。非内联不可时用 `String.raw`，派发前核对反斜杠还在。
- 结束前把「改了哪些文件、跑了哪些命令、结果如何」写到 `impl/<agent 字母>.md`，同时作为结果返回。

**新测试的验证分两段**
- C、D、E 在 B 完成之前，只验证「HEAD 上失败、命中数与表一致」和自检。
- B 完成后，主代理统一跑 4 个新测试，确认「改后全部通过」。
- 红了就把失败输出交回原来那个 agent 返修。先读过它的结果再派，不算盲目重派。不得调低规格里写死的阈值。

**收口**：全部 agent 结束后，主代理跑 §6 第 1–6 条，写报告。
