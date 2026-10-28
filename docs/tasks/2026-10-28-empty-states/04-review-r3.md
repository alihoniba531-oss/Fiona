# 04 独立复核 R3：只核验返修 R2（补回 BOM）

- 复核对象：基线 `f6adca6` + 返修 R2（补回 `frontend/app/page.tsx` 的 UTF-8 BOM）后的候选改动，快照哈希 `0705c76b88785496`；返修单 `05-fix-r2.md`。
- 复核方式：任务书 4 项全部亲自执行；未调用 subagent，未起浏览器或服务器。

---

## 1. 结论

**通过**——BOM 已按字节补回且与 HEAD 一致，page.tsx 相对 HEAD 恢复为恰 4 个授权 hunk；除这 3 个字节与 `03-report.md` 的两处授权修改外，整个候选（全部 tracked diff 与 9 个测试文件）与 R1 状态逐字节相同（用重建 R1 master 哈希的方法证明）；52 条新测试与 gate.sh v3（157 项，含新增的 BOM 与 4-hunk 两条判据）全绿；报告 §9 与 §8.1 第 1 行的记载与实测相符。无必须修复项。

## 2. 逐项核验

### 2.1 任务书第 1 项：开始哈希

`(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` = `0705c76b88785496de97fad2d21711d8894358e23ab7ac9d454665bccc1ccef1`，前 16 位 **`0705c76b88785496`，与任务书预期一致**；与报告 §9.2 自报的补回后快照相同。

### 2.2 任务书第 2 项：R2 改动核验

| 判据 | 期望 | 实际 | 判定 |
|---|---|---|---|
| `head -c3 frontend/app/page.tsx \| xxd -p` | `efbbbf` | `efbbbf` | 通过 |
| `git show HEAD:frontend/app/page.tsx \| head -c3 \| xxd -p` | 与上相同 | `efbbbf`（相同） | 通过 |
| `git diff HEAD -- frontend/app/page.tsx \| grep -c '^@@'` | 4 | **4**（`@@ -959,7`、`@@ -1789,6`、`@@ -2223,6`、`@@ -2593,9`，与 R1 复核记录的 T3 授权四处一致；R1 返修后曾多出的 `@@ -1,4 +1,4 @@` BOM hunk 已消失） | 通过 |
| page.tsx 去掉开头 3 字节后与 R1 状态逐字节相同 | sha256 一致 | `sha256(当前内容[3:])` 前 16 位 = **`38348cc0e7867dbd`**，与两个独立记录相符：① 报告 §8.4 变异基线 `38348cc0e7867dbd → 38348cc0e7867dbd`；② 我方 R2 变异日志（MH/MI/MJ 三次）记录的 `file=frontend/app/page.tsx sha=38348cc0e7867dbd`。另 `git hash-object` 去 BOM 内容 = `38a1f14`，与我方 R2 记录的 R1 时 diff index 行 `index eeb726c..38a1f14` 相同 | 通过 |
| 其余文件与 R1 相同：除 page.tsx、03-report.md 外 `git diff HEAD` 无新变化 | 逐字节相同 | **重建证明**：把当前 `git diff HEAD` 中 page.tsx 段的 index 行换回 `eeb726c..38a1f14` 并在其 hunk 前插回原 BOM hunk（`@@ -1,4 +1,4 @@`，内容取自 R2 复核时的原始记录），再拼接当前 9 个测试文件原文，sha256 = **`7c4aa5ca5c3c35108554019106b13af455158f2fe9759a708e3228677bb3e607`**，与 R2 轮记录/实测的 R1 master 哈希**全值相同**。该哈希覆盖全部 tracked diff 与 9 个测试文件，故除 page.tsx 的 BOM 外，其余 21 个已改文件与 9 个新测试均与 R1 逐字节一致 | 通过 |
| `git diff` 总量旁证 | 190/89 − 1/1 | `22 files changed, 189 insertions(+), 88 deletions(-)`（R1 返修后为 190/88+1，差值恰为 BOM 那一对 +1/−1）；改动文件仍为同 22 个 | 通过 |

`03-report.md`（未跟踪文件，不在上述哈希内）的改动核验见 2.4。

### 2.3 任务书第 3 项：复跑

| 项 | 期望 | 实际 | 判定 |
|---|---|---|---|
| 52 条新测试（清代理变量后前台跑） | 全部通过 | **`52 passed in 3.39s`**，0 failed、0 skipped | 通过 |
| `bash verify/gate.sh "$PWD"`（v3） | 全部通过 | **`== 汇总: 157 项，FAIL=0`**，退出码 0；`grep -c '^PASS'` = 157。脚本自述「v3 加 page.tsx 文件头 BOM 与 hunk 数」，两条新判据实测：`PASS page.tsx keeps HEAD UTF-8 BOM (v3) efbbbf`、`PASS page.tsx diff is exactly 4 hunks (v3) 4` | 通过 |
| gate 内工具链 | 全绿 | next 16.4.3；tsc 退出 0；lint 0 errors、25 warnings ≤ 25；build 退出 0；全量 pytest 退出 0、failed 0、skipped 0、`7826 passed, 35 warnings in 286.09s`（gate 内输出文件 `/tmp/b3-pytest.txt`）；new tests collected 52；`7826 ≥ 7774+52` | 通过 |

gate.sh v3 的本副本 sha256 前 16 位为 `fef475b220bffffd`（v2 为 `dc50f4fce0535a05`）。事实性备注：`verify/gate-record.md`（186 行）尚停留在 R1/v2 的记录（登记的仍是 v2 sha 与 R1 快照 `7c4aa5ca5c3c3510`），未含 v3 与 `0705c76b88785496`；该文件由 Claude 维护、按其流程在验收后登记，不作为本轮判定对象，仅提请登记时同步。

### 2.4 任务书第 4 项：`03-report.md` 的改动

| 项 | 判定 | 证据 |
|---|---|---|
| §8.1 表格第 1 行按返修单改写 | **通过** | `:205` 现为「…函数体恰为 v1.2 的 8 行；page.tsx 其余未动（R1 时曾误删文件开头的 UTF-8 BOM，R2 已补回）」，与返修单第 2 条要求的措辞一致，行内其余文字未动 |
| 新增「## 9. 返修 R2」一节 | **通过** | `:302` 起。内容逐项核对属实：① 对问题的描述（HEAD `efbbbf`、R1 后 `227573`、多出第 1 行 hunk 共 5 个）与我方 R2 复核的原始记录一致；② 引用的补回命令与返修单第 1 条命令逐字相同（带 `assert not b.startswith(b'\xef\xbb\xbf')` 防重复前置）；③ 三项自检数字（`efbbbf`、`4`、`52 passed`）与我本轮独立实测一致；④ 补回后快照 `0705c76b88785496` 与我方开始哈希一致；⑤ 范围声明（只改 page.tsx 字节 0–2 与本报告）已被 2.2 的重建哈希证明 |
| 报告其余部分未被波及 | **通过** | 行数 300 → 321（+21 = §9 一节）；`grep '__[A-Z_]*__'` 为空（无占位符回潮）；R2 轮核过的锚点原样在位（`:134` 「19 条 Route」、`:138` 「8 处，分布在 7 行」、§8.5、§8.6、§8.7、`ALL_RESTORED = True` 等） |

## 3. 必须修复项

无。

## 4. 哈希核对

- 开始：`(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` = `0705c76b88785496de97fad2d21711d8894358e23ab7ac9d454665bccc1ccef1`（前 16 位 `0705c76b88785496`，与任务书预期一致）。
- 结束（本文件写入后复算）：同值 `0705c76b88785496…ccef1`（本文件为未跟踪文件，不进入 `git diff HEAD`，也不属于 `test_empty_states_*.py`，不影响该哈希）。
- 结束 `git status --porcelain --untracked-files=all`：68 条 = 开始 67 条 + 仅本文件（`docs/tasks/2026-10-28-empty-states/04-review-r3.md`）。本轮无任何仓库内临时文件残留（比对与重建脚本的输出均在会话内，未写盘到仓库）。
