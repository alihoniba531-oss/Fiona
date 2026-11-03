# 03 报告：UI 复核收尾（第五批，v1.2 / R2）

- 基线：`main` @ `bccbf9f`；工作分支 `feat/ui-closeout`；工作树 `<工作树>`
- 规格：v1.2（2026-11-02）；本报告是 R2 返修后的最终结果。
- 状态：**T1–T5 全部完成，R2 测试补强完成**。全量 pytest `7863 passed`（7836 基线 + 27 个新用例），0 failed、0 skipped；前端 tsc/lint/build 在 R1 后全绿，R2 未改实现文件。

## 0. R1 记录：裁决与返修

首轮执行在 T1 停下，原因已由 v1.1 裁决解除：

1. **readout 计数冲突**：采用方案 1。`backend/tests/test_ui_polish_page_contracts.py` 加入白名单，只把 `test_page_readout_numbers_are_not_bold` 的 `== 2` 改成 `== 4`；T1 第 6 条和 T5 cost_hint 的两个余额数字按规格原文使用 `className="readout font-normal"`。
2. **`::backdrop` 计数**：按规则行计数，§5.6 改为 `grep -c "::backdrop {"` = 2；T3 文件未再改动。
3. **页脚行判据**：按 T1 第 5 条代码块。容器 `<div className={cn("mt-2 flex min-w-0 items-center justify-between gap-3 border-t border-[color:var(--carve)] pt-2 text-fs-12 text-[color:var(--ink2)] shadow-[inset_0_1px_0_var(--etch)] xl:flex-nowrap max-md:mt-1 max-md:pt-1 max-md:text-fs-11", !hasContent && "max-md:hidden")}>` 一行，`<span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>` 在下一行；cost_hint 测试按 v1.1 的两行判据。

R1 由主代理直接完成（未再派 subagent）：

- 用 Python `open(path, "rb")` / `"wb"` 按字节改写 `frontend/app/page.tsx`，保留 UTF-8 BOM；按 T1 第 1–7 条落地全部代码。
- 新建 `backend/tests/test_ui_closeout_cost_hint.py`（5 个用例：1 个真实契约 + 4 个改坏副本自检）。
- 只改 `backend/tests/test_ui_polish_page_contracts.py` 的指定数字；`git diff -U0` 为单 hunk、一行 `-`、一行 `+`。
- 重跑 §5 第 1–7 条；重跑四个新测试与两个门禁文件的 HEAD 对照；更新本报告与 `impl/A.md`。

## 1. 拆分表（派出过的全部 agent）

本批首轮用 `workflow` 工具的 `parallel()` 一次并行派出 A、B、C、D 四个执行 agent；R1 没有新派 agent，由主代理执行。

| agent | 任务 | 负责文件 | 结果 |
|---|---|---|---|
| A | T1 + `test_ui_closeout_cost_hint.py` | `frontend/app/page.tsx`、新测试 | 首轮按 §7 中止（未改代码）；R1 由主代理按裁决完成 T1，成功 |
| B | T2 + `test_ui_closeout_history_keyboard.py`（含盲区 1） | `frontend/app/history/page.tsx`、新测试 | 成功；工作树 4 passed、HEAD 4 FAIL 均为 AssertionError |
| C | T3 + T4 + `test_ui_closeout_dialog_scrim.py` | `globals.css`、8 个组件、2 个门禁测试、新测试 | 成功；工作树全绿、HEAD 对照符合预期 |
| D | T5 盲区 2、3：`test_ui_closeout_structure_guards.py` | 新测试 | 成功；工作树与 HEAD 均 7 passed |
| 主代理 | 拆分、派发、白名单核对、T1 R1、§5、报告 | `page.tsx`、cost_hint 测试、`test_ui_polish_page_contracts.py`、本报告 | 已执行 |

各 agent/主代理的执行记录：`docs/tasks/2026-11-02-ui-closeout/impl/A.md`、`B.md`、`C.md`、`D.md`。

## 2. 修改了哪些文件

`git status --porcelain` 原文：

```text
 M backend/tests/test_design_system_css.py
 M backend/tests/test_design_system_gate.py
 M backend/tests/test_ui_polish_page_contracts.py
 M frontend/app/globals.css
 M frontend/app/history/page.tsx
 M frontend/app/page.tsx
 M frontend/components/ConfirmDialog.tsx
 M frontend/components/GeneratedImage.tsx
 M frontend/components/SongProjectCard.tsx
 M frontend/components/novel/NovelSettingsDialog.tsx
 M frontend/components/studio/BrainTrial.tsx
 M frontend/components/studio/QuoteDialog.tsx
 M frontend/components/studio/ShotCard.tsx
 M frontend/components/studio/SourceChoices.tsx
?? backend/tests/test_ui_closeout_cost_hint.py
?? backend/tests/test_ui_closeout_dialog_scrim.py
?? backend/tests/test_ui_closeout_history_keyboard.py
?? backend/tests/test_ui_closeout_structure_guards.py
?? docs/tasks/2026-11-02-ui-closeout/
```

说明：

- `docs/tasks/2026-11-02-ui-closeout/` 在本批开始前就是未跟踪目录（含 `02-spec.md`、`dispatch.md`）；本批新增四个 `impl/*.md` 与本报告。
- `frontend/app/page.tsx` 是 R1 新增的修改；BOM 保持 `ef bb bf`。
- 新增的四个测试文件都在 §3.1 白名单内。
- 没有修改 `02-spec.md`、`docs/tasks/**` 的其他文件、`package.json`、`frontend/node_modules` 或 `backend/.venv`。

`git diff --stat`：

```text
 backend/tests/test_design_system_css.py           |  2 +-
 backend/tests/test_design_system_gate.py         | 95 ++++++++++++++++-------
 backend/tests/test_ui_polish_page_contracts.py    |  2 +-
 frontend/app/globals.css                         |  8 +-
 frontend/app/history/page.tsx                    | 35 ++++++++-
 frontend/app/page.tsx                            | 39 +++++++---
 frontend/components/ConfirmDialog.tsx             |  2 +-
 frontend/components/GeneratedImage.tsx            |  2 +-
 frontend/components/SongProjectCard.tsx           |  2 +-
 frontend/components/novel/NovelSettingsDialog.tsx |  2 +-
 frontend/components/studio/BrainTrial.tsx         |  2 +-
 frontend/components/studio/QuoteDialog.tsx        |  2 +-
 frontend/components/studio/ShotCard.tsx           |  2 +-
 frontend/components/studio/SourceChoices.tsx      |  2 +-
 14 files changed, 142 insertions(+), 55 deletions(-)
```

## 3. 实现了哪些功能，与 T1–T5 逐项对应

### T1 费用提示只在首次与低余额时显示（已完成）

- `frontend/app/page.tsx` 在 `ChatModelFooter` 前加入模块级 `costHintSeenKey` 与 `markCostHintSeen`；存储键为 `fiona_cost_hint_seen:<encodeURIComponent(username)>`，存储不可用时按首次处理。
- `ChatModelFooter` 新增 `balance: number | null` prop；在现有 state/ref 之后加入 `firstVisit`、`firstVisitDecided` ref 和 effect，用 ref 防止 React 严格模式把首次判成非首次。
- 在 `label` 前加入 `lowBalance`、`showCost`、`hasContent`；页脚容器移入组件，桌面保留 `Enter 发送，Shift + Enter 换行`，手机在无内容时用 `!hasContent && "max-md:hidden"` 隐藏。
- 两处费用文字加 `showCost &&`：平台模型文案低余额时 `text-[color:var(--seal)]` 并追加「，还剩 N 颗」；图片模式同理。`label` / `labelTitle`、思考档、「改用平台 / 改用我的模型」、错误行未动。
- 原页脚四行容器改为一行 `<ChatModelFooter key={username} username={username} settingsOpen={settingsOpen} chatMode={!imageMode && !hasReferenceImages} loading={isLoading} balance={strawberryBalance} />`；BOM 用字节脚本保留。
- `backend/tests/test_ui_closeout_cost_hint.py` 覆盖 v1.1 清单全部断言，并带 4 个改坏副本自检（缺 `showCost`、余额数字非 `readout font-normal`、Enter 提示位置变化、BOM 丢失）。
- `backend/tests/test_ui_polish_page_contracts.py` 只把 readout 计数从 2 改为 4。

### T2 日期 chip 接管键盘焦点（已完成）

- `frontend/app/history/page.tsx` 增加 `dateFromRef`、`dateToRef`、`rawChip`；`openDatePicker` 保留 `try { input.showPicker(); } catch {`，不支持时按 `data-chip` 显示原生框并聚焦，失焦收回。
- 两枚 chip 增加透明按钮（Tab 焦点、Enter/Space、带中文日期的 `aria-label`）；原生 date input `aria-hidden`、`tabIndex={-1}`、`data-chip`、`ref`，鼠标 `onClick` 和已聚焦后的 `onKeyDown` 保留。
- 既有字面量锁（透明 overlay 恰 2、`openDatePicker(e.currentTarget)` 4、两个 input `aria-label` 各 1 等）保持。
- `test_ui_closeout_history_keyboard.py` 覆盖盲区 1：input 与 value/data-chip/ref 配对、按钮与下一行 onClick 配对、两条互换自检。

### T3 遮罩统一成 `scrim-dialog`（已完成）

- `frontend/app/globals.css` 只保留 `.scrim-dialog::backdrop` 与 `.dark .scrim-dialog::backdrop` 两条规则（昼夜各带 `rgba` 兜底），`::backdrop` 规则行数为 2。
- 6 个字符串中的 `backdrop:bg-[color:var(--scrim)]` 原位替换为 `scrim-dialog`；`ConfirmDialog.tsx`、`GeneratedImage.tsx` 补上公共类。
- 13 个 `<dialog>` 全部含 `scrim-dialog`；`grep -rln "scrim-dialog" frontend/components` 为 8 个文件；`backdrop:` 变体 0 行。
- `test_ui_closeout_dialog_scrim.py` 用花括号/字符串感知扫描器校验标签、公共 CSS 规则与 `backdrop:` 反查，并带自检。

### T4 门禁补强（已完成，只改点名位置）

- F7 的 `TYPE_WORDS` 换成整词 `TYPE_WORD_RX`，放行改 `TYPE_WORD_RX.match(val)`；正则补 `.style.fontSize =` 与 `setProperty("font-size"/"font")`。
- F7 自检增加两条好样本、6 条坏样本、两条误伤反例；T8 改为校验 `.scrim-dialog::backdrop` 公共类，名称同步，样本和 5 个坏样本按要求更新。
- `test_design_system_css.py` 的 `REQUIRED_PACKAGES` 增加 `tailwindcss`。

### T5 三处反例测试（已完成）

- 盲区 1：`test_ui_closeout_history_keyboard.py`（4 例）。
- 盲区 2、3：`test_ui_closeout_structure_guards.py`（7 例）。
- T1 的 cost_hint：`test_ui_closeout_cost_hint.py`（5 例）。
- 三条 v1 的阻塞点均已按 v1.1 落地，没有留下未覆盖的清单项。

## 4. §5 第 1–7 条的实际输出（R1 历史；R2 最新结果见 §7）

### §5.1 `npx tsc --noEmit`

```text
$ cd frontend
$ export npm_config_cache=/tmp/fiona-npm-cache
$ npx tsc --noEmit
EXIT=0
```

无输出，退出码 0。

### §5.2 `npm run lint`

```text
$ cd frontend
$ export npm_config_cache=/tmp/fiona-npm-cache
$ npm run lint

> frontend@0.1.0 lint
> eslint


<工作树>/frontend/app/page.tsx
   170:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   261:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   642:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   701:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   702:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   703:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   713:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   714:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   715:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   716:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   719:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   725:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   726:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
  1030:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1124:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1550:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1570:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1578:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1599:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1657:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1890:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 2257) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  2357:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  2397:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2713:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

<工作树>/frontend/app/plaza/page.tsx
  603:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
EXIT=0
```

0 错误，警告 25 条（≤ 25）。

### §5.3 `npm run build`

```text
$ cd frontend
$ export npm_config_cache=/tmp/fiona-npm-cache
$ npm run build

> frontend@0.1.0 build
> next build

▲ Next.js 16.4.3 (Turbopack)
✓ Running next.config.ts took 41ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:90174) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 514ms
  Running TypeScript ...
  Finished TypeScript in 1378ms ...
  Collecting page data using 17 workers ...
  Generating static pages using 17 workers (0/18) ...
  Generating static pages using 17 workers (4/18) 
  Generating static pages using 17 workers (8/18) 
  Generating static pages using 17 workers (13/18) 
✓ Generating static pages using 17 workers (18/18) in 239ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ƒ /agents/[id]
├ ○ /agents/me
├ ○ /community
├ ○ /history
├ ○ /login
├ ○ /manifest.webmanifest
├ ○ /match
├ ○ /novels
├ ƒ /novels/[id]
├ ○ /novels/new
├ ○ /plaza
├ ○ /profile
├ ○ /settings
├ ○ /studio
├ ƒ /studio/[id]
└ ○ /studio/kb


ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
EXIT=0
```

构建通过，退出码 0。

### §5.4 全量 pytest

命令：

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  .venv/bin/python -m pytest -q -p no:cacheprovider
```

结果原文：

```text
7855 passed, 35 warnings in 313.74s (0:05:13)
```

0 failed、0 skipped。7855 = 7836 + 19（cost_hint 5 + history_keyboard 4 + dialog_scrim 3 + structure_guards 7）。

### §5.5 HEAD 对照（必做）

实际执行：

```bash
H=$(mktemp -d)          # 实际目录在报告中记为 <HEAD 副本>
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_ui_closeout_*.py "$H/backend/tests/"
cp backend/tests/test_design_system_gate.py backend/tests/test_design_system_css.py "$H/backend/tests/"
cp -cR frontend/node_modules "$H/frontend/node_modules"
cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  <工作树>/backend/.venv/bin/python \
  -m pytest -q -p no:cacheprovider -rf --tb=line \
  tests/test_ui_closeout_*.py tests/test_design_system_gate.py tests/test_design_system_css.py
```

`-rf` 原文：

```text
FFFFFFFFFFFF..........F...                                               [100%]
=================================== FAILURES ===================================
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x76bb6b8000>('balance: number | null;')
     +    where <built-in method count of str object at 0x76bb6b8000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:43: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x76bb7b8000>('balance: number | null;')
     +    where <built-in method count of str object at 0x76bb7b8000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:43: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x76bb700000>('balance: number | null;')
     +    where <built-in method count of str object at 0x76bb700000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:43: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x76bbc00000>('balance: number | null;')
     +    where <built-in method count of str object at 0x76bbc00000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:43: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x76bbc48000>('balance: number | null;')
     +    where <built-in method count of str object at 0x76bbc48000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:43: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: dialog in frontend/components/ConfirmDialog.tsx must include scrim-dialog: '<dialog\n      ref={dialogRef}\n      className="confirm-dialog"\n      role={active?.kind === "confirm" ? "alertdialog" : undefined}\n      aria-labelledby={active?.title ? titleId : undefined}\n      aria-describedby={active ? bodyId : undefined}\n      onCancel={(event) => {\n        event.preventDefault();\n        settle(false);\n      }}\n      onClick={(event) => {\n        if (event.target === event.currentTarget) settle(false);\n      }}\n    >'
    assert 'scrim-dialog' in ['confirm-dialog']
     +  where ['confirm-dialog'] = <built-in method split of str object at 0x10afc00f0>()
     +    where <built-in method split of str object at 0x10afc00f0> = 'confirm-dialog'.split
<HEAD 副本>/backend/tests/test_ui_closeout_dialog_scrim.py:109: AssertionError: dialog in frontend/components/ConfirmDialog.tsx must include scrim-dialog: '<dialog\n      ref={dialogRef}\n      className="confirm-dialog"\n      role={active?.kind === "confirm" ? "alertdialog" : undefined}\n      aria-labelledby={active?.title ? titleId : undefined}\n      aria-describedby={active ? bodyId : undefined}\n      onCancel={(event) => {\n        event.preventDefault();\n        settle(false);\n      }}\n      onClick={(event) => {\n        if (event.target === event.currentTarget) settle(false);\n      }}\n    >'
E   AssertionError: globals.css must have exactly two ::backdrop rules, found 4
    assert 4 == 2
     +  where 4 = <built-in method count of str object at 0x76bb580000>('::backdrop')
     +    where <built-in method count of str object at 0x76bb580000> = '@import "tailwindcss";\n@import "tw-animate-css";\n@import "./shadcn-tailwind.css";\n@import "./fonts/noto-serif-sc.c...l-behavior:auto !important;\n    transition-duration:0.01ms !important;\n    transition-delay:0s !important;\n  }\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_dialog_scrim.py:120: AssertionError: globals.css must have exactly two ::backdrop rules, found 4
E   AssertionError: frontend/components/SongProjectCard.tsx:340: Tailwind backdrop: utility is forbidden: 'backdrop:bg-[color:var(--scrim)]"\n      '
<HEAD 副本>/backend/tests/test_ui_closeout_dialog_scrim.py:143: AssertionError: frontend/components/SongProjectCard.tsx:340: Tailwind backdrop: utility is forbidden: 'backdrop:bg-[color:var(--scrim)]"\n      '
E   AssertionError: both native date inputs must leave the Tab order
    assert 0 == 2
     +  where 0 = <built-in method count of str object at 0x76bbe60000>('tabIndex={-1}')
     +    where <built-in method count of str object at 0x76bbe60000> = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:55: AssertionError: both native date inputs must leave the Tab order
E   AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
    assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:84: AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E   AssertionError: the from chip button label must appear exactly once
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x76bbe78000>('aria-label={`从（开始日期）：${dayFace(dateFrom)}`}')
     +    where <built-in method count of str object at 0x76bbe78000> = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:105: AssertionError: the from chip button label must appear exactly once
E   assert ('aria-label={`从（开始日期）：${dayFace(dateFrom)}`}' in '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n')
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:113: assert ('aria-label={`从（开始日期）：${dayFace(dateFrom)}`}' in '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n')
E   AssertionError: 令牌层未通过：
      PASS T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确
      PASS T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有
      PASS T3 四套主题逐块取值正确、键集合相同
      PASS T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%
      PASS T5 手机输入框护栏：选择器三项、在顶层 @media (width < 48rem) 里、不进 @layer
      PASS T6 ::placeholder { color: var(--ink2) } 在第一个 @layer base 里
      PASS T7 body 规则块里 font-size: var(--fs-16-5)
      FAIL T8 所有对话框共用 .scrim-dialog::backdrop，用 var(--scrim) 并带兜底色，昼夜各一条
    assert False
     +  where False = all(dict_values([True, True, True, True, True, True, True, False]))
     +    where dict_values([True, True, True, True, True, True, True, False]) = <built-in method values of dict object at 0x10b46ec40>()
     +      where <built-in method values of dict object at 0x10b46ec40> = {'T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确': True, 'T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有': True, 'T3 四套主题逐块取值正确、键集合相同': True, 'T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%': True, ...}.values
<HEAD 副本>/backend/tests/test_design_system_gate.py:556: AssertionError: 令牌层未通过：
=========================== short test summary info ============================
FAILED tests/test_ui_closeout_cost_hint.py::test_cost_hint_contract - Asserti...
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_show_cost_guard_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_balance_digits_are_rejected_when_not_readout
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_moved_enter_hint_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_bom_is_rejected
FAILED tests/test_ui_closeout_dialog_scrim.py::test_all_dialogs_use_scrim_dialog
FAILED tests/test_ui_closeout_dialog_scrim.py::test_scrim_backdrop_rules_are_the_only_two
FAILED tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_chip_keyboard_contract
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_inputs_pair_with_their_own_chips
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_buttons_pair_with_their_own_inputs
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_swapped_labels_are_rejected
FAILED tests/test_design_system_gate.py::test_token_layer - AssertionError: ...
13 failed, 13 passed in 1.59s
```

对照结论：

- `test_ui_closeout_cost_hint.py`：5 个用例全部 FAIL，原因均为 `AssertionError`（HEAD 缺 `balance: number | null;` 等 T1 契约）。
- `test_ui_closeout_history_keyboard.py`：4 个用例全部 FAIL，均为 `AssertionError`。
- `test_ui_closeout_dialog_scrim.py`：3 个用例全部 FAIL，均为 `AssertionError`。
- `test_ui_closeout_structure_guards.py`：7 passed。
- `test_design_system_gate.py`：`test_token_layer` FAIL（T8 对不上 HEAD 的四条规则），`test_selfcheck_source_rules`、`test_selfcheck_token_layer` PASS。
- `test_design_system_css.py`：PASS，未 skip。
- 总计：13 failed、13 passed；没有 ImportError / FileNotFoundError / SyntaxError。

### §5.6 计数

```text
$ grep -rn "backdrop:" frontend/app frontend/components frontend/lib | wc -l
0
$ grep -rln "scrim-dialog" frontend/components | wc -l
8
$ grep -c "::backdrop {" frontend/app/globals.css
2
$ grep -c 'className="absolute inset-0 h-full w-full cursor-pointer opacity-0"' frontend/app/history/page.tsx
2
$ grep -c 'tabIndex={-1}' frontend/app/history/page.tsx
2
$ grep -c '"平台模型 · 每条 10 颗草莓"' frontend/app/page.tsx
2
$ head -c 3 frontend/app/page.tsx | xxd | head -1
00000000: efbb bf                                  ...
$ git status --porcelain
（见 §2；只包含 §3.1 的文件）
$ git diff --stat -- backend/tests
 backend/tests/test_design_system_css.py        |  2 +-
 backend/tests/test_design_system_gate.py       | 95 ++++++++++++++++++--------
 backend/tests/test_ui_polish_page_contracts.py |  2 +-
 3 files changed, 69 insertions(+), 30 deletions(-)
```

`grep -c "::backdrop {"` 为 2，与 v1.1 的规则行口径一致（T3 注释里的 `::backdrop` 不算）。

### §5.7 既有测试原样与 diff 范围

`git diff -U0 HEAD -- backend/tests/test_ui_polish_page_contracts.py` 原文：

```text
diff --git a/backend/tests/test_ui_polish_page_contracts.py b/backend/tests/test_ui_polish_page_contracts.py
index a1de6cc..08d7625 100644
--- a/backend/tests/test_ui_polish_page_contracts.py
+++ b/backend/tests/test_ui_polish_page_contracts.py
@@ -178 +178 @@ def test_page_readout_numbers_are_not_bold():
-    assert source.count('className="readout font-normal"') == 2
+    assert source.count('className="readout font-normal"') == 4
```

只有单 hunk、一行 `-`、一行 `+`，且只改 `== 2` → `== 4`。

其余既有测试：

```text
$ git diff HEAD --stat -- backend/tests/ ':!backend/tests/test_design_system_gate.py' ':!backend/tests/test_design_system_css.py' ':!backend/tests/test_ui_polish_page_contracts.py' ':!backend/tests/test_ui_closeout_*'
（无输出）
```

`backend/tests/test_design_system_gate.py` 的改动 hunk 全部落在 T4 点名区域（`TYPE_WORDS`、F7 正则与放行、F7 自检、T8 断言/样本/自检）；`test_design_system_css.py` 只改 `REQUIRED_PACKAGES` 一行。v1.1 新增白名单的 `test_ui_polish_page_contracts.py` 已在上面单独核对。

## 5. 未完成或需人工确认的地方

1. **真实浏览器行为未由执行者实测**：T1 的 390×844 首次/非首次/低余额高度、朱色、自带模型 157px、图片模式，以及 T2 的 Tab 顺序、`showPicker` 打桩、失焦收回等，按 §5 末尾属于 Claude 在沙箱外的复核项。
2. **`git diff --stat -- backend/tests` 现在有三个既有文件**（gate、css、polish），与 v1 规格注释的「两个」不同；v1.1 已把 `test_ui_polish_page_contracts.py` 加入白名单并限定只改一个数字，本报告已用 `-U0` 单 hunk 核对。
3. 没有 commit；工作树保持改动状态，等待作者按流程提交。

## 6. 新增用例数与每个新文件的用例数（R2 后）

| 新测试文件 | 用例数 | 工作树 | HEAD 对照 |
|---|---:|---|---|
| `backend/tests/test_ui_closeout_cost_hint.py` | 8 | 8 passed | 8 failed（均为 AssertionError） |
| `backend/tests/test_ui_closeout_history_keyboard.py` | 8 | 8 passed | 8 failed（均为 AssertionError） |
| `backend/tests/test_ui_closeout_dialog_scrim.py` | 4 | 4 passed | 3 个真实用例 failed（均为 AssertionError）；空集自检 passed |
| `backend/tests/test_ui_closeout_structure_guards.py` | 7 | 7 passed | 7 passed |
| **合计** | **27** | **27 passed** | **20 failed / 14 passed** |

工作树聚焦运行 `tests/test_ui_closeout_*.py tests/test_design_system_gate.py tests/test_design_system_css.py` 为 `34 passed`（27 个新用例 + 门禁 6 个 + CSS 依赖探测 1 个）；全量 pytest 为 `7863 passed`，与 7836 + 27 一致。

## 7. R2 记录：T5 新测试补强（2026-11-02）

### 7.1 独立复核发现

`docs/tasks/2026-11-02-ui-closeout/04-review.md` 指出实现 T1–T4 与规格逐条一致、白名单与字面量锁成立、§5 七条全过；不通过只在两个新测试文件，另有 cost_hint 可优化项：

1. `history_keyboard` 的 `tabIndex={-1}`、`aria-hidden="true"`（HEAD 上已有 7 处，`>= 6` 恒真）、`onBlur` 是全文件计数，不绑定到两个原生日期框；把两处 `tabIndex={-1}` 挪到按钮、或删掉两个原生框的 `aria-hidden`，旧测试仍全绿。
2. `dialog_scrim` 的 `test_no_backdrop_tailwind_variants_remain` 有空集问题：`SCAN_BASES` 三个目录都不存在时 `_source_map` 返回空字典，反查 `{}` 什么也不查。
3. `cost_hint` 没锁首次判定逻辑：`setFirstVisit(firstVisitDecided.current)` 改成 `setFirstVisit(false)`、去掉 ref 守卫、去掉第一处 `lowBalance &&`，旧测试仍全绿。

### 7.2 改了什么

本轮只改三个新测试文件，实现文件、门禁文件、`structure_guards`、其他既有测试一个字节未动。

- `backend/tests/test_ui_closeout_history_keyboard.py`
  - `check_date_input_pairing` 对两个原生 `<input>` 标签追加 `aria-hidden="true"`、`tabIndex={-1}`、`onBlur={() => setRawChip(null)}`、各自的 `rawChip === "from"` / `rawChip === "to"`，与原有的 value / data-chip / ref 一起逐框核对。
  - 新增 `check_date_buttons_stay_in_tab_order`：按 label 行向上找最近的 `<button`、向下找最近的 `/>`，断言按钮标签内没有 `tabIndex`、没有 `aria-hidden`；新增真实用例 `test_date_buttons_stay_in_tab_order`。
  - `test_selfcheck_swapped_labels_are_rejected` 开头先要求原文通过 input 配对与 button 配对。
  - 新增三条自检：去掉原生框 `aria-hidden`、把 `tabIndex={-1}` 挪到按钮、对调 `rawChip` 的两处键。
- `backend/tests/test_ui_closeout_dialog_scrim.py`
  - 新增 `assert_scan_is_not_empty(sources, *, require_css=True)`：逐个断言 `SCAN_BASES` 目录存在、`sources` 非空、包含 `SongProjectCard.tsx`，需要 CSS 时还要求包含 `globals.css`。
  - `test_all_dialogs_use_scrim_dialog` 在真实断言前调用空集检查（`require_css=False`）；`test_no_backdrop_tailwind_variants_remain` 在反查前调用空集检查。
  - 新增 `test_selfcheck_empty_scan_is_rejected`：空字典与缺组件文件两种输入都必须抛 `AssertionError`。
- `backend/tests/test_ui_closeout_cost_hint.py`
  - `check_cost_hint_contract` 追加三条断言：ref 守卫行、`setFirstVisit(firstVisitDecided.current);`、两处 `{lowBalance && <>，还剩 …` 各自的数量。
  - 新增三条自检：`setFirstVisit(false)`、去掉 ref 守卫前缀、去掉第一处 `lowBalance &&`。

用例数：cost_hint 5 → 8（+3），history_keyboard 4 → 8（+4），dialog_scrim 3 → 4（+1），structure_guards 保持 7；合计 **27**（新增 8）。`--collect-only -q` 末行：`27 tests collected in 0.06s`。四个文件全绿：`27 passed in 0.21s`；再带两个门禁文件为 `34 passed in 1.60s`。

### 7.3 真实变异复现（改完按字节还原并核对 sha256）

所有变异都直接改真实源码，跑完立即从临时备份恢复，并用 `shasum -a 256` 核对恢复前后一致。实现文件最终未变化；`page.tsx` sha256 为 `6f735f49ae0a32bd46250926aee455340e046042580aeb251f60ab4c383b65e8`，`history/page.tsx` 为 `9dd4f3b8b591c35450b5fb223ffe3d65fe358a68c9cad5d0f0cb44d92bc5b345`。

**A.4.1 删掉原生框的 `aria-hidden="true"`**（`aria-hidden="true"\n                  tabIndex={-1}` 恰 2 处 → 替换为 `tabIndex={-1}`）：

```text
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_inputs_pair_with_their_own_chips
E   AssertionError: the input labeled 「从（开始日期）」 must carry aria-hidden="true", not the other chip's binding
1 failed, 3 passed, 4 deselected in 0.03s
```

**A.4.2 把 `tabIndex={-1}` 从原生框挪到按钮**（删两条 `                  tabIndex={-1}`，再在两条 `                  type="button"` 后各加一条；替换后仍恰 2 处）：

```text
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_inputs_pair_with_their_own_chips
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_buttons_stay_in_tab_order
E   AssertionError: the 从（开始日期） chip button must stay in the Tab order
2 failed, 2 passed, 4 deselected in 0.03s
```

**B 把 `SCAN_BASES` 临时改成三个不存在的目录**：

```text
FAILED tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain
E   AssertionError: scan base is missing: <工作树>/frontend/__r2_missing_app__
1 failed in 0.03s
```

**C 把 `setFirstVisit(firstVisitDecided.current);` 改成 `setFirstVisit(false);`**（保留 BOM）：

```text
FAILED tests/test_ui_closeout_cost_hint.py::test_cost_hint_contract - Asserti...
E   AssertionError: the effect must set firstVisit from the decided ref
E   assert 0 == 1
1 failed, 7 deselected in 0.03s
```

### 7.4 HEAD 对照

命令（临时目录在报告中记为 `<HEAD 副本>`；`git archive HEAD` 后只拷四个新测试和两个门禁文件，不拷 `test_ui_polish_page_contracts.py`）：

```bash
H=$(mktemp -d)
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_ui_closeout_*.py "$H/backend/tests/"
cp backend/tests/test_design_system_gate.py backend/tests/test_design_system_css.py "$H/backend/tests/"
cp -cR frontend/node_modules "$H/frontend/node_modules"
cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  <工作树>/backend/.venv/bin/python -m pytest -q -p no:cacheprovider -rf --tb=line -rA \
  tests/test_ui_closeout_*.py tests/test_design_system_gate.py tests/test_design_system_css.py
```

`--tb=line -rA` 原始输出（路径统一记为 `<HEAD 副本>`）：

```text
FFFFFFFFFFF.FFFFFFFF..........F...                                       [100%]
=================================== FAILURES ===================================
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c16b8000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c16b8000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c17b8000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c17b8000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1700000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c1700000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1c00000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c1c00000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1c48000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c1c48000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1c90000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c1c90000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1cd8000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c1cd8000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: the footer must accept a nullable balance prop
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1d20000>('balance: number | null;')
     +    where <built-in method count of str object at 0x77c1d20000> = '\ufeff"use client";\n\nimport { useState, useRef, useEffect, useCallback } from "react";\nimport Glaze from "@/compon...nset-bottom))]"\n          onClick={closeDrawer}\n          aria-hidden\n        />\n      )}\n\n    </div>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_cost_hint.py:51: AssertionError: the footer must accept a nullable balance prop
E   AssertionError: dialog in frontend/components/ConfirmDialog.tsx must include scrim-dialog: '<dialog\n      ref={dialogRef}\n      className="confirm-dialog"\n      role={active?.kind === "confirm" ? "alertdialog" : undefined}\n      aria-labelledby={active?.title ? titleId : undefined}\n      aria-describedby={active ? bodyId : undefined}\n      onCancel={(event) => {\n        event.preventDefault();\n        settle(false);\n      }}\n      onClick={(event) => {\n        if (event.target === event.currentTarget) settle(false);\n      }}\n    >'
    assert 'scrim-dialog' in ['confirm-dialog']
     +  where ['confirm-dialog'] = <built-in method split of str object at 0x1098e9830>()
     +    where <built-in method split of str object at 0x1098e9830> = 'confirm-dialog'.split
<HEAD 副本>/backend/tests/test_ui_closeout_dialog_scrim.py:123: AssertionError: dialog in frontend/components/ConfirmDialog.tsx must include scrim-dialog: '<dialog\n      ref={dialogRef}\n      className="confirm-dialog"\n      role={active?.kind === "confirm" ? "alertdialog" : undefined}\n      aria-labelledby={active?.title ? titleId : undefined}\n      aria-describedby={active ? bodyId : undefined}\n      onCancel={(event) => {\n        event.preventDefault();\n        settle(false);\n      }}\n      onClick={(event) => {\n        if (event.target === event.currentTarget) settle(false);\n      }}\n    >'
E   AssertionError: globals.css must have exactly two ::backdrop rules, found 4
    assert 4 == 2
     +  where 4 = <built-in method count of str object at 0x77c1580000>('::backdrop')
     +    where <built-in method count of str object at 0x77c1580000> = '@import "tailwindcss";\n@import "tw-animate-css";\n@import "./shadcn-tailwind.css";\n@import "./fonts/noto-serif-sc.c...l-behavior:auto !important;\n    transition-duration:0.01ms !important;\n    transition-delay:0s !important;\n  }\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_dialog_scrim.py:134: AssertionError: globals.css must have exactly two ::backdrop rules, found 4
E   AssertionError: frontend/components/SongProjectCard.tsx:340: Tailwind backdrop: utility is forbidden: 'backdrop:bg-[color:var(--scrim)]"\n      '
<HEAD 副本>/backend/tests/test_ui_closeout_dialog_scrim.py:157: AssertionError: frontend/components/SongProjectCard.tsx:340: Tailwind backdrop: utility is forbidden: 'backdrop:bg-[color:var(--scrim)]"\n      '
E   AssertionError: both native date inputs must leave the Tab order
    assert 0 == 2
     +  where 0 = <built-in method count of str object at 0x77c1f40000>('tabIndex={-1}')
     +    where <built-in method count of str object at 0x77c1f40000> = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:55: AssertionError: both native date inputs must leave the Tab order
E   AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
    assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:92: AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E   AssertionError: the from chip button label must appear exactly once
    assert 0 == 1
     +  where 0 = <built-in method count of str object at 0x77c1f58000>('aria-label={`从（开始日期）：${dayFace(dateFrom)}`}')
     +    where <built-in method count of str object at 0x77c1f58000> = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'.count
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:121: AssertionError: the from chip button label must appear exactly once
E   AssertionError: the 从（开始日期） chip button label must appear on exactly one line
    assert 0 == 1
     +  where 0 = len([])
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:133: AssertionError: the 从（开始日期） chip button label must appear on exactly one line
E   AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
    assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:92: AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E   AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
    assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:92: AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E   AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
    assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:92: AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E   AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
    assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'
<HEAD 副本>/backend/tests/test_ui_closeout_history_keyboard.py:92: AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E   AssertionError: 令牌层未通过：
      PASS T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确
      PASS T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有
      PASS T3 四套主题逐块取值正确、键集合相同
      PASS T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%
      PASS T5 手机输入框护栏：选择器三项、在顶层 @media (width < 48rem) 里、不进 @layer
      PASS T6 ::placeholder { color: var(--ink2) } 在第一个 @layer base 里
      PASS T7 body 规则块里 font-size: var(--fs-16-5)
      FAIL T8 所有对话框共用 .scrim-dialog::backdrop，用 var(--scrim) 并带兜底色，昼夜各一条
    assert False
     +  where False = all(dict_values([True, True, True, True, True, True, True, False]))
     +    where dict_values([True, True, True, True, True, True, True, False]) = <built-in method values of dict object at 0x108fbb940>()
     +      where <built-in method values of dict object at 0x108fbb940> = {'T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确': True, 'T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有': True, 'T3 四套主题逐块取值正确、键集合相同': True, 'T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%': True, ...}.values
<HEAD 副本>/backend/tests/test_design_system_gate.py:556: AssertionError: 令牌层未通过：
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED tests/test_ui_closeout_dialog_scrim.py::test_selfcheck_empty_scan_is_rejected
PASSED tests/test_ui_closeout_structure_guards.py::test_first_privacy_paragraph_is_not_wrapped_in_needs_key_conditional
PASSED tests/test_ui_closeout_structure_guards.py::test_chat_openers_are_not_wrapped_by_extra_keyboard_handlers
PASSED tests/test_ui_closeout_structure_guards.py::test_selfcheck_privacy_guard_rejects_split_needs_key_wrapper
PASSED tests/test_ui_closeout_structure_guards.py::test_selfcheck_privacy_guard_rejects_single_line_needs_key_wrapper
PASSED tests/test_ui_closeout_structure_guards.py::test_selfcheck_opener_guard_rejects_on_key_down_on_group
PASSED tests/test_ui_closeout_structure_guards.py::test_selfcheck_opener_guard_rejects_wrapped_first_button
PASSED tests/test_ui_closeout_structure_guards.py::test_selfcheck_opener_guard_rejects_on_key_down_on_container
PASSED tests/test_design_system_gate.py::test_font_size_rules
PASSED tests/test_design_system_gate.py::test_color_rules
PASSED tests/test_design_system_gate.py::test_role_rules
PASSED tests/test_design_system_gate.py::test_selfcheck_source_rules
PASSED tests/test_design_system_gate.py::test_selfcheck_token_layer
PASSED tests/test_design_system_css.py::test_generated_css_font_sizes
FAILED tests/test_ui_closeout_cost_hint.py::test_cost_hint_contract - Asserti...
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_show_cost_guard_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_balance_digits_are_rejected_when_not_readout
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_moved_enter_hint_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_bom_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_first_visit_always_false_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_first_visit_ref_guard_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_first_low_balance_guard_is_rejected
FAILED tests/test_ui_closeout_dialog_scrim.py::test_all_dialogs_use_scrim_dialog
FAILED tests/test_ui_closeout_dialog_scrim.py::test_scrim_backdrop_rules_are_the_only_two
FAILED tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_chip_keyboard_contract
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_inputs_pair_with_their_own_chips
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_buttons_pair_with_their_own_inputs
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_buttons_stay_in_tab_order
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_swapped_labels_are_rejected
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_inputs_without_aria_hidden_are_rejected
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_tabindex_moved_to_buttons_is_rejected
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_swapped_raw_chip_keys_are_rejected
FAILED tests/test_design_system_gate.py::test_token_layer - AssertionError: ...
20 failed, 14 passed in 1.83s
```

末行 **20 failed, 14 passed in 1.83s**。逐项：cost_hint 8 个全部 FAIL；history_keyboard 8 个全部 FAIL；dialog_scrim 的 3 个真实用例 FAIL、空集自检 PASS；structure_guards 7 个全 PASS；`test_design_system_gate.py::test_token_layer` FAIL，另外 5 个门禁测试 PASS；`test_design_system_css.py` PASS。所有失败原因均为 `AssertionError`，没有 ImportError / FileNotFoundError / SyntaxError。

### 7.5 全量 pytest 与不可变性核对

全量 pytest（后台任务跑完）：

```text
7863 passed, 35 warnings in 311.42s (0:05:11)
```

0 failed、0 skipped；7863 = 7855 + 本轮新增 8 个用例，也等于 7836 + 27。

`git diff | shasum -a 256` 开工前、收尾均为：

```text
419727acfd3b3c6dabbf6ed6a3ed2f9c67bfa848b9970b47632f3faffea03fdd  -
```

`git status --porcelain` 的未跟踪集合与开工前一致，没有多出新文件；三个新测试文件本来就是未跟踪文件，所以 `git diff` 不因本轮测试改动而变化。R2 临时变异过的 `frontend/app/history/page.tsx`、`frontend/app/page.tsx` 与 `test_ui_closeout_dialog_scrim.py` 都已按字节恢复，sha256 与备份一致。
