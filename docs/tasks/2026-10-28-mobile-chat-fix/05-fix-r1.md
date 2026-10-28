# 返修单 R1（2026-10-28）

独立复核（`04-review.md`）结论：有条件通过，两项必须修复。第 2 项是验收证据问题（测量脚本把状态 C 量成了 B），由 Claude 自己改脚本补测，不归你。你只做下面三件事，仍只许动 §3.1 白名单里的文件。

## R1-1 浮标层级 `z-[3]` → `z-[1]`（`frontend/app/page.tsx`）

- 问题：输入釉片是 `absolute … z-[2]`，构成层叠上下文；「图片」菜单（`components/ComposerImageMenu.tsx:103`，`absolute bottom-full z-[60]`）被困在釉片这一层里。浮标作为釉片的同级 `z-[3]`，会画在打开的菜单之上，手机上刚好压住「生成图片」一项的右侧，点下去会关掉菜单并回到底部。
- 改法：把浮标 className 字面串里的 `z-[3]` 改为 `z-[1]`，其余字符不变。改后浮标仍高于 `.chat-message-layer`（z auto），低于页头与输入釉片（`z-[2]`）；它离釉片上沿 12–16px，不会被釉片遮住。
- 规格 §4-T2-2 的 className 已同步改为 `z-[1]`（见 02-spec.md v2.1 修订记录）。

## R1-2 新测试补强（`backend/tests/test_mobile_chat_fix.py`，只增不减）

在现有断言之外追加（保持离线、文本契约写法）：

1. 浮标 className（用现有的 `re.search(r'className="([^"]*\bchat-latest\b[^"]*)"', source)` 取到的 `classes`）含 `z-[1]`，且不含 `z-[2]`、`z-[3]`；含 `absolute`、`bottom-[calc(var(--composer-height)+34px)]`、`max-md:bottom-[calc(var(--composer-height)+var(--tabbar-h)+env(safe-area-inset-bottom)+12px)]`；不含 `opacity-`。
2. 含 `onClick={() => chatScrollRef.current?.scrollToLatest()}` 的那一行就是浮标所在行（`chat-latest` 与它出现在同一个 `<button` 元素的文本里：取 `source.index('{showLatestPill && <button')` 到其后第一个 `</button>}` 之间的片段，断言片段同时含 `chat-latest` 与 `scrollToLatest()`）。
3. `--composer-height` 的内联变量位置：含 `data-chat-panel` 的那一行含 `"--composer-height"`；含 `className="chat-message-layer` 的那一行不含 `--composer-height`。
4. 页脚行：含 `border-t border-[var(--carve)] pt-2` 的那一行恰好 1 行，且含 `max-md:mt-1`、`max-md:pt-1`、`max-md:text-[11px]`。
5. footer 行的 `max-md:pt-2` / `max-md:pb-1.5` 断言改用边界正则：`re.search(r"max-md:pt-2(?![\d.])", footer)` 非空、`re.search(r"max-md:pb-1\.5(?![\d.])", footer)` 非空。
6. `globals.css`：对取出的手机媒体块 `block`，用正则找出每一条选择器含 `.glaze-finish` 的规则体（`{…}` 内文本），断言每个规则体都不含 `lipdk`、不含 `linear-gradient`、含 `inset 0 1px 0 var(--lip)`（对规则体断言，不对常量断言）。

## R1-3 报告

在 `03-report.md` 末尾追加「R1 返修」一节：改了什么、新增了哪些断言、以下命令的实际输出：

- `cd frontend && npx tsc --noEmit`；`npm run lint`（0 errors，warnings ≤ 25）；
- `cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py -p no:cacheprovider`（全部通过，总数 ≥ 499）；
- `grep -c 'z-\[1\]' frontend/app/page.tsx`（≥ 1）、`grep 'chat-latest' frontend/app/page.tsx | grep -c 'z-\[3\]'`（= 0）。

不跑 `npm run build`（Claude 会在换成与 lockfile 一致的 node_modules 后自己跑）。不改其他任何文件；不提交 git；不得调用 subagent / subagent_fork / workflow（改动很小，单代理直接做）。
