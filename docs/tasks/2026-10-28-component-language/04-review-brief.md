# 独立复核任务书：组件语言统一（UI 复核第二批）

你是独立复核方，和实现方、规格作者没有对话上下文。只以本目录（git 工作树副本，基线 `6410890`，已套上候选改动）里的落盘文件为依据。

## 输入

- 规格：`docs/tasks/2026-10-28-component-language/02-spec.md`（权威）与返修单 `05-fix-r1.md`。
- 候选改动：本副本相对 `HEAD` 的 `git diff`，加上未跟踪的新文件 `frontend/components/ConfirmDialog.tsx`、`frontend/lib/ttsChunks.ts`、`backend/tests/test_component_language.py`。
- 门禁与实测证据：`verify/gate-record.md`、`verify/gate.sh`、`verify/measure.py`、`verify/results/*.json|*.png`（HEAD 与候选用同一脚本在真实无头 Chromium 上量出；HEAD 是正控）。
- 实现方报告 `03-report.md`：**只当线索，不可信**，每个结论都要自己验。

## 要做的事

1. 开始先记 `(git diff HEAD; cat frontend/components/ConfirmDialog.tsx frontend/lib/ttsChunks.ts backend/tests/test_component_language.py) | shasum -a 256` 的前 16 位（应为 `3eeeee7c2c58d000`），结束再比。
2. 规格 §6 第 1–7 条逐条实际运行（`cd frontend && npx tsc --noEmit`、`npm run lint`、`npm run build`；`cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py tests/test_component_language.py tests/test_novel_p2_r1.py -p no:cacheprovider`；`bash docs/tasks/2026-10-28-component-language/verify/gate.sh "$PWD"`）。跑 npm 前 `export npm_config_cache=/tmp/fiona-npm-cache`。**注意**：`gate.sh` 会删并重建 `frontend/.next`，这在副本里无害。
3. 逐条核验 §3.2「必须原样保留」与 §5「不允许的做法」：重点
   - `primeTtsAudio()` 是否在 `handleSpeakMessage` 里同步、先于任何异步调用；单条朗读是否没有 `setVoiceOn`；
   - 12 段确认 / 提示正文是否逐字未改；
   - `await confirm(...)` 之后的复查是否读的是**新鲜值**（例如 `getUsername()`、`isCurrentOwner()`、`beginRequest()` 的结果），还是只是闭包里的旧 state（旧 state 复查等于没查）；逐个文件写结论；
   - `ChatCard` 与三个天气函数、`{/* 文字气泡` 之后的条件表达式、「帮我读 / 不用」是否未动；
   - 中点：§2.6 表的 8 处是否按表改了，「不改」清单里的是否一个没动；
   - 被 iframe 内嵌的页面（`/plaza`、`/settings`、`/profile`）有没有新出现 `max-md:`。
4. 审 `ConfirmDialog.tsx` 的实现：模块级 `host` 在 Provider 重挂载、React 严格模式双挂载、多个调用排队时是否正确；对话框关闭后焦点归还；Esc / 点遮罩 / 按钮三条路径是否都恰好 resolve 一次；`showModal()` 在已 open 时会不会抛错。
5. 审 `splitTtsChunks`：是否会丢字、是否保证每段 ≤ max、数字间句点、连续标点、空白输入。自己写几个输入在 node 里跑（转译方法参照新测试）。
6. 审新测试：离线、不依赖 git 历史、不读仓库外文件；断言能否区分对错实现。至少做 4 个变异（例：把 `primeTtsAudio()` 挪到 `setTimeout` 里；在单条朗读里加 `setVoiceOn(true)`；把某处 `await confirm(...)` 换回原生 `confirm(`；让 `splitTtsChunks` 丢最后一段；去掉 `!message.id.startsWith("db-")` 条件），看新测试是否变红。变异只能临时改已跟踪或新增的源码，改前按字节备份、改完拷回并校验 sha256；**不要用 `git checkout`**（会把候选改动一起退回）。
7. 审实测证据：读 `measure.py`，判断每条判据是否真的量到、HEAD 正控是否确实失败；对照 `results/*.json` 与 `gate-record.md` 的表格是否一致。你没有浏览器，不要起服务器量；只审逻辑与数据一致性。

## 输出

写 `docs/tasks/2026-10-28-component-language/04-review.md`（中文），结构固定：

1. 结论：通过 / 不通过（一句话）。
2. 验收标准逐条核验：§6 第 1–8 条，每条「实际值 / 期望 / 判定 / 证据」。
3. §3.2 / §5 逐条核验（含第 3 点里「新鲜值复查」的逐文件结论）。
4. 变异实验记录。
5. 必须修复项（没有就写「无」）。
6. 可优化项（不阻塞合并）。
7. 给执行者的二次修改指令（只在不通过时写）。
8. 哈希核对（开始 / 结束）。

## 规矩

- 不得调用 subagent / subagent_fork / workflow，不得起浏览器或服务器。
- 除 `04-review.md` 外不得新增或保留任何修改；结束时 `git status --porcelain` 只比开始多出 `04-review.md`，第 1 步的哈希必须一致。
- 每个结论要有证据（命令输出摘要或 文件:行）；「看起来没问题」不算。
