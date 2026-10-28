# 独立复核任务书：空态与文案（UI 复核第三批）

你是独立复核方，和实现方、规格作者没有对话上下文。只以本目录（git 工作树副本，基线 `f6adca6`，已套上候选改动）里的落盘文件为依据。

## 输入

- 规格：`docs/tasks/2026-10-28-empty-states/02-spec.md`（权威）。
- 候选改动：本副本相对 `HEAD` 的 `git diff`，加上未跟踪的 9 个新测试文件 `backend/tests/test_empty_states_*.py`。
- 门禁与实测证据：`verify/gate-record.md`、`verify/gate.sh`、`verify/measure.py`、`verify/compare.py`、`verify/extra_probe.py`、`verify/repro_p320_slow.py`、`verify/results/*`（HEAD 与候选用同一脚本在真实无头 Chromium 上量出；HEAD 是正控）。隐私一条的测法中途修正过一次（v1 只看布局盒，对收起的 `<details>` 恒为真；v2 加 `checkVisibility()` 后只重跑隐私部分），来龙去脉见 `gate-record.md` 第 3 节，请一并审这次修正是否站得住。
- 实现方报告 `03-report.md`：**只当线索，不可信**，每个结论都要自己验。

## 要做的事

1. 开始先记下面这条命令输出的前 16 位（应为 `aa9aef9f6cc4699f`），结束再比：
   `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256`
2. 规格 §6 第 1–6 条逐条实际运行：
   - 跑 npm 前 `export npm_config_cache=/tmp/fiona-npm-cache`；
   - `cd frontend && npx tsc --noEmit`、`npm run lint`、`npm run build`；
   - `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider`（全量，约 5 分钟，要求 0 failed、0 skipped）；
   - `bash docs/tasks/2026-10-28-empty-states/verify/gate.sh "$PWD"`。
   - 注意：`gate.sh` 会删并重建 `frontend/.next`，这在副本里无害。
3. 逐条核验 §3.2「必须原样保留」、§3.3「测试替身的限制」与 §5「不允许的做法」。重点：
   - `lib/useAccountIdentity.ts` 只有新增、没有改动；新 hook 只用 `useEffect` / `useSyncExternalStore`、模块级变量和已导入的 `getUsername` / `ensureAccountIdentity`；没有 `useId`、`dispatchEvent`、`location`、`document`；`lib/auth.ts` 未动。
   - 10 处接线：外层调用新 hook 并下传 `identityPending`；内层 `identityPending = false` 默认；原登录文案一字不改；「正在加载身份…」只在 `!owner` 分支内部，没有吞掉「小说工坊尚未开放」等错误态。
   - 三个开场处理函数里没有任何发送或请求；`page.tsx` 的计数与切片锁全部仍成立；`handleSend` 未动。
   - 既有测试只改了 `test_ui_polish_settings_drawers.py` 第 83 行这一处；三份文档各只改了一行。
   - `VoiceButton.tsx` 只有新增；`ChatModelSection.tsx` 8 段原文逐字未变，被锁的三段仍是一行、不带属性的 `<p>`。
4. 审 T1 新 hook 的正确性：
   - 服务端渲染与水合时不出现水合不匹配；
   - 本地有用户名时不闪「正在加载身份…」；
   - 找回成功、失败、401 三条路径最终状态是否正确；
   - 多个组件同时挂载、跨标签登出时会怎样；
   - 有没有监听泄漏。
5. 审新测试：离线、不依赖 git 历史、不读仓库外文件；断言能否区分对错实现。至少做 6 个变异，看新测试是否变红，例如：
   - 去掉内层的 `identityPending = false` 默认值；
   - 把 `serverIdentityPending` 改成返回 false；
   - 让某个开场处理函数调用 `handleSend`；
   - 去掉语音气泡的 `!showHint &&`；
   - 去掉书斋页眉的 `books.length > 0 &&`；
   - 把隐私第一段挪回 `<details>` 里；
   - 把 `dayFace` 的「不限」兜底删掉。
   变异只能临时改已跟踪或新增的源码，改前按字节备份，改完拷回并校验 sha256；**不要用 `git checkout`**（会把候选改动一起退回）。
6. 审实测证据：读 `measure.py`，判断每条判据是否真的量到、HEAD 正控是否确实失败；对照 `results/*.json` 与 `gate-record.md` 的表格是否一致。你没有浏览器，不要起服务器量，只审逻辑与数据一致性。

## 输出

写 `docs/tasks/2026-10-28-empty-states/04-review.md`（中文），结构固定：

1. 结论：通过 / 不通过（一句话）。
2. 验收标准逐条核验：§6 第 1–7 条，每条写明实际值、期望、判定、证据。
3. §3.2 / §3.3 / §5 逐条核验。
4. 变异实验记录。
5. 必须修复项（没有就写「无」）。
6. 可优化项（不阻塞合并）。
7. 给执行者的二次修改指令（只在不通过时写）。
8. 哈希核对（开始 / 结束）。

## 规矩

- 不得调用 subagent / subagent_fork / workflow，不得起浏览器或服务器。
- 除 `04-review.md` 外不得新增或保留任何修改。结束时 `git status --porcelain --untracked-files=all` 只比开始多出 `04-review.md`，第 1 步的哈希必须一致。
- 每个结论要有证据（命令输出摘要或「文件:行」）；「看起来没问题」不算。
