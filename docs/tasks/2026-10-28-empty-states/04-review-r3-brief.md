# 独立复核任务书 R3：只核验返修 R2（补回 BOM）

上一轮（R2）你判「通过」。你和 Claude 都发现：返修 R1 去掉了 `frontend/app/page.tsx` 开头的 UTF-8 BOM。Claude 裁决要补回，执行者已按 `05-fix-r2.md` 做完。本副本已换成补回之后的状态。

## 要做的事

1. 开始先记下 `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` 的前 16 位，应为 `0705c76b88785496`；结束时再算一次比对。
2. 核验 R2 的改动：
   - `head -c3 frontend/app/page.tsx | xxd -p` 为 `efbbbf`，与 `git show HEAD:frontend/app/page.tsx | head -c3 | xxd -p` 相同；
   - `git diff HEAD -- frontend/app/page.tsx | grep -c '^@@'` 为 4；
   - 除了补回的这三个字节，page.tsx 与 R1 状态逐字节相同。R1 状态 = 本副本当前内容去掉开头三个字节，用 `cmp` 或 sha256 比对。上一轮的 `04-review-r2.md` 记录过 R1 时 page.tsx 的情况，可作对照。
   - 其余文件与 R1 相同：除 page.tsx 和 `03-report.md` 外，`git diff HEAD` 里没有新变化。
3. 复跑：52 条新测试，以及 `bash docs/tasks/2026-10-28-empty-states/verify/gate.sh "$PWD"`（v3，会跑全量 pytest 与 build）。全部通过才算过。
4. 核对 `03-report.md` 新增的「## 9. 返修 R2」一节，以及 §8.1 第 1 行的改动是否属实。

## 输出

写 `docs/tasks/2026-10-28-empty-states/04-review-r3.md`（中文），结构如下：

1. 结论：通过 / 不通过；
2. 逐项核验，附证据；
3. 必须修复项（没有就写「无」）；
4. 哈希核对（开始 / 结束）。

不要另提新的主观问题。

## 规矩

- 不得调用 subagent / subagent_fork / workflow，不得起浏览器或服务器。
- 除 `04-review-r3.md` 外，不得新增或保留任何修改。
