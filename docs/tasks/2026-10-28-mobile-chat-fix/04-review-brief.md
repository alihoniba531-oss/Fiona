# 独立复核任务书：手机对话页修缮（UI 复核第一批）

你是独立复核方，和实现方、规格作者没有任何对话上下文。只以本目录（git 工作树副本，基线 `58be576`，已套上候选改动）里的落盘文件为依据。

## 输入

- 规格：`docs/tasks/2026-10-28-mobile-chat-fix/02-spec.md`（权威）。
- 候选改动：本副本相对 `HEAD`（`58be576`）的 `git diff`，加上未跟踪的新文件 `backend/tests/test_mobile_chat_fix.py`。另有一份同内容的 diff 快照放在副本之外的会话临时目录（只读，派单时给出路径）。
- 门禁记录与实测证据：`docs/tasks/2026-10-28-mobile-chat-fix/verify/gate-record.md`、`verify/gate.sh`、`verify/measure.py`、`verify/results/*.json|*.png`（HEAD 与候选用同一脚本在真实无头 Chromium 上量出的数值与截图）。
- 实现方报告：`docs/tasks/2026-10-28-mobile-chat-fix/03-report.md`——**只能当线索，不可信**；它的每个结论都要你自己验。

## 要做的事

1. 逐条核验规格 §6 第 1–7 条：在本副本里实际运行命令（`cd frontend && npx tsc --noEmit`、`npm run lint`、`npm run build`、`cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py -p no:cacheprovider`、§6-5 的全部 grep / awk / diff 判据），把实际输出摘要写进报告。跑 npm 前先 `export npm_config_cache=/tmp/fiona-npm-cache`。
2. 逐条核验规格 §3.2「必须原样保留」与 §5「不允许的做法」：读 diff，确认没有超出 §3.1 白名单、没有动既有测试、`ChatScrollArea.tsx:21–113` 逐字节未动、桌面样式未动（输入区新增 class 是否都带 `max-md:`，globals.css 新规则是否都在 `:564` 开头的手机媒体块内）。
3. 审 §6 第 8 条的实测证据是否可信：读 `verify/measure.py` 的测量逻辑，判断每条判据是否真的被量到、有没有恒真或量错对象的地方；对照 `verify/results/head-measure.json` 与 `cand-measure.json` 的数字和 `gate-record.md` 的表格是否一致。你没有浏览器，不要试图自己起服务器量；只审逻辑与数据一致性。
4. 审新测试 `backend/tests/test_mobile_chat_fix.py`：是否离线、不依赖 git 历史、不读仓库外文件；断言能否区分对错实现。自己至少做 3 个变异实验（在副本里临时改坏源码，跑新测试看是否变红，然后 `git checkout -- <file>` 恢复；别碰未跟踪的新文件）。至少包括一个规格 §5 禁止的做法（例如把浮标塞回 `.chat-message-layer`、把 `max-md:pb-2` 留着并存、把上报回调塞进 `updateButton`）。
5. 审实现本身的风险：`overflow-clip` 对 fixed / absolute 后代、backdrop-filter 取样有没有副作用；`--composer-height` 提到 `[data-chat-panel]` 后 `globals.css:510–528` 的 `var()` 是否仍能读到；浮标 `z-[3]` 与页头 / 输入釉片 `z-[2]`、遮罩层的层叠关系是否正确、能否点到；`useEffect` 上报有没有多余的渲染或 `react-hooks/exhaustive-deps` 警告；T5 去掉 `rim` 后手机边到边面板是否有可见退化；`ChatScrollArea` 的旧分支保留是否完整。
6. 实现方报告 §6.1 列了两处「只改测试写法」的偏离，核对是否属实、是否只影响测试。

## 输出

写 `docs/tasks/2026-10-28-mobile-chat-fix/04-review.md`（中文），结构固定：

1. 结论：通过 / 不通过（一句话）。
2. 验收标准逐条核验：§6 第 1–9 条，每条写「实际值 / 期望 / 判定 / 证据（命令输出摘要或文件:行）」；第 8、9 条写你对实测证据的审读结论。
3. §3.2 / §5 逐条核验。
4. 变异实验记录（每个：改了什么、哪条测试变红、是否恢复）。
5. 必须修复项（没有就写「无」）。
6. 可优化项（不阻塞合并，留给用户裁决）。
7. 给执行者的二次修改指令（只在不通过时写）。

## 规矩

- 不得调用 subagent / subagent_fork / workflow，不得起浏览器或服务器。
- 除 `04-review.md` 外不得新增或修改任何文件；变异实验改过的源码必须恢复（`git status --porcelain` 结束时只多出 `04-review.md`，且 `git diff HEAD` 与开始时逐字节相同——开始时先 `git diff HEAD | shasum` 记一下，结束再比）。
- 每个结论要有证据；「看起来没问题」不算。
