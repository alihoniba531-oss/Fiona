# 独立复核任务书 R2：空态与文案（返修 R1 之后）

你在上一轮（R1 复核）审过这个改动。之后：
- 规格更新为 v1.2，修订点见 `docs/tasks/2026-10-28-empty-states/02-spec.md` 文末 §10；
- 执行者按返修单 `05-fix-r1.md` 做了返修；
- Claude 重新跑了门禁和真实浏览器实测。

本副本已换成返修后的状态：基线 `f6adca6` + 新的候选改动，加上未跟踪的新测试与任务目录。

## 输入

- 规格 v1.2（权威，重点读 §10）与返修单 `05-fix-r1.md`。
- 候选改动：本副本相对 `HEAD` 的 `git diff`，加上未跟踪的 9 个 `backend/tests/test_empty_states_*.py`。
- 证据：`verify/gate-record.md`（已更新到 R1）、`verify/gate.sh`（v2）、`verify/compare.py`、`verify/probe_r1.py`、`verify/results/*`。
- 实现方报告 `03-report.md` 的「返修 R1」一节：只当线索，不可信。
- 你上一轮的结论 `04-review.md`（R1）。

## 要做的事

1. 开始先记下 `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` 的前 16 位，应为 `7c4aa5ca5c3c3510`；结束时再算一次比对。
2. 复跑规格 §6 第 1–6 条：
   - 先 `export npm_config_cache=/tmp/fiona-npm-cache`，跑 pytest 前清代理变量；
   - 跑 `tsc`、`lint`、`build`、全量 `pytest`（0 failed、0 skipped）；
   - 跑 `bash docs/tasks/2026-10-28-empty-states/verify/gate.sh "$PWD"`。
3. **只核验本轮的必须修复项**：返修单第一节 1–9 号、规格 §10 第 8 条的 1–10 小项。逐项给出判定和证据。不要另提新的主观问题；新发现降为可优化项。
   - 例外：修复本身引入了相对 HEAD 的新回归，列为必须修复项。
   - **规格本身也在审查范围内**：如果「照 v1.2 做」本身会出问题，照样要报，不能用规格条款开脱。上一轮你看到了按住 Enter 后的实测值「聊聊今天\n\n\n\n」，却判为无害，理由是规格禁止改动——这就是这条要防的情况。
4. 变异：对 §10 第 8 条的加固项，至少各做 1 个变异，看新测试是否变红。至少要包括：
   - 把 `if (e.repeat) return;` 挪回 `handleKeyDown` 第一行；
   - 去掉书斋页眉行的 `min-h-10`；
   - 把 `dayFace` 改回 v1.1 写法；
   - 把 `useAccountIdentityPending` 里「置位」与「通知」两行对调；
   - 把快照函数改成只看 `!getUsername()`；
   - 在某个开场按钮上加 `onKeyDown={handleKeyDown}`；
   - 把隐私第一段包进 `{needsKey && …}`。

   变异只临时改源码：改前按字节备份到仓库外，改完拷回并校验 sha256。**不要用 `git checkout`**。
5. 审实测证据：读 `probe_r1.py` 与 `compare.py`，判断判据是否真的量到了、HEAD 正控是否成立；对照 `results/*` 与 `gate-record.md` 的表格是否一致。你没有浏览器，不要起服务器。

## 输出

写 `docs/tasks/2026-10-28-empty-states/04-review-r2.md`（中文），结构如下：

1. 结论：通过 / 不通过，一句话。
2. 本轮必须修复项逐项核验：判定加证据。
3. §6 第 1–6 条复跑结果。
4. 变异实验记录。
5. 必须修复项（没有就写「无」）。
6. 可优化项。
7. 二次修改指令（只在不通过时写）。
8. 哈希核对。

## 规矩

- 不得调用 subagent / subagent_fork / workflow，不得起浏览器或服务器。
- 除 `04-review-r2.md` 外，不得新增或保留任何修改。结束时 `git status --porcelain --untracked-files=all` 只比开始多这一个文件，第 1 步的哈希必须一致。
- 每个结论都要有证据：命令输出摘要，或「文件:行」。
