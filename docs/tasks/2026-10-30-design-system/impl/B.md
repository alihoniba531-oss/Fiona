# B：T2 令牌层套用记录

- 角色：工作流 agent B（令牌层）。只做 `02-spec.md` §T2 的 28 条；未调用 subagent / subagent_fork / workflow。
- 工作目录：`<工作树>`
- 基线：`HEAD` = `647a486`，且 A 的 T1 已完成（76 个文件已套用）。git 只做读操作（`status` / `diff` / `show`），未做任何 git 写操作。
- 附件：`docs/tasks/2026-10-30-design-system/verify/t2_edits.json`（28 条，以其为准）。
- 结果：**PASS**。28/28 条全部套用；每条套用前 `old` 出现次数等于 JSON 的 `count`；只写了 3 个目标文件。

## 1. 改动范围与结果

| 文件 | 改动条数 | 字节变化 | 行数变化 | 结果 sha256 |
|---|---|---|---|---|
| `frontend/app/globals.css` | 1–26（26 条） | 27410 → 27221（-189） | 598 → 604（+6） | `3943d85552c85be8caf580d9b91dce1bc27de869c8c01202b92b7dc567e34f00` |
| `frontend/lib/utils.ts` | 27（1 条） | 166 → 499（+333） | 6 → 11（+5） | `849a7b1ad509ee0aa8111d6d5cae3fff6b389c7e79717e3bd610f8cbc8fb1340` |
| `frontend/components/Seal.tsx` | 28（1 条） | 1320 → 1321（+1） | 16 → 16（+0） | `5c2fde64abb5b1af0e19e968acfc9ed1c2c5d9d7b1dd8a6f3c7f533a5d594460` |

套用前 sha256：

```text
94223fc81d8e977a5bdd8a2f0ed50523495a9a7178f23a632f4b0695b6d2a147  frontend/app/globals.css
7c8c3dfc0cdd370d44932828eb067ef771c8fe7996693221d5d4b90af6d54f2d  frontend/lib/utils.ts
5a4b9353b7608ea35a0e674cac2ce2a126031ca03cdbb4d6991177b91f63e029  frontend/components/Seal.tsx
```

## 2. 每条明细（按 JSON 顺序）

`count` 来自 `t2_edits.json`，`found` 是替换前在该文件当前内容里的实际出现次数（两者必须相等）；`bytes` 是该条替换后的字节增量。

| n | 文件 | count | found | bytes | 结果 |
|---:|---|---:|---:|---:|---|
| 1 | `frontend/app/globals.css` | 1 | 1 | -430 | OK（删 8 行 `--color-sidebar-*`） |
| 2 | `frontend/app/globals.css` | 1 | 1 | +471 | OK（`@theme inline` 登记 10 个 `--text-fs-*` + 4 个行高） |
| 3 | `frontend/app/globals.css` | 2 | 2 | +0 | OK（昼两套 `--ink3`） |
| 4 | `frontend/app/globals.css` | 2 | 2 | +40 | OK（昼两套 `--stamp`） |
| 5 | `frontend/app/globals.css` | 2 | 2 | +40 | OK（夜两套 `--seal` / `--stamp`） |
| 6 | `frontend/app/globals.css` | 1 | 1 | +158 | OK（10 个 `--fs-*`） |
| 7 | `frontend/app/globals.css` | 1 | 1 | -67 | OK（删 `--amber-ink/--dim/--rec`） |
| 8 | `frontend/app/globals.css` | 1 | 1 | +2 | OK（`--rec-soft` → `--seal-soft`） |
| 9 | `frontend/app/globals.css` | 1 | 1 | -86 | OK（删 `--glass-*` 别名） |
| 10 | `frontend/app/globals.css` | 1 | 1 | -272 | OK（删 `--sidebar-*` 别名） |
| 11 | `frontend/app/globals.css` | 1 | 1 | -33 | OK（删 `--shadow`） |
| 12 | `frontend/app/globals.css` | 1 | 1 | +40 | OK（`::placeholder`，T1 的第 300 行原样保留） |
| 13 | `frontend/app/globals.css` | 1 | 1 | +27 | OK（body 根字号） |
| 14 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.readout`） |
| 15 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.btn`） |
| 16 | `frontend/app/globals.css` | 1 | 1 | +1 | OK（`.btn-danger`） |
| 17 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.chip`） |
| 18 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.tag`） |
| 19 | `frontend/app/globals.css` | 1 | 1 | +10 | OK（`.bubble-user`） |
| 20 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.bubble-ai`） |
| 21 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.porcelain-like-pop`） |
| 22 | `frontend/app/globals.css` | 1 | 1 | -6 | OK（打字光标） |
| 23 | `frontend/app/globals.css` | 1 | 1 | -78 | OK（图片预览遮罩） |
| 24 | `frontend/app/globals.css` | 1 | 1 | -72 | OK（确认框遮罩） |
| 25 | `frontend/app/globals.css` | 1 | 1 | +10 | OK（手机输入框护栏） |
| 26 | `frontend/app/globals.css` | 1 | 1 | +8 | OK（`.image-model-segments .chip`） |
| 27 | `frontend/lib/utils.ts` | 1 | 1 | +333 | OK（`extendTailwindMerge` 登记 10 个字号组） |
| 28 | `frontend/components/Seal.tsx` | 1 | 1 | +1 | OK（印章 `var(--seal)` → `var(--stamp)`） |

说明：第 4、5、6 条的 `new` 包含 `old`（例如新增 `--stamp` 行时保留 `--seal` 行），因此最终文件里这些 `old` 的出现次数不一定为 0；是否套用正确由下面的逆序逐字节核对覆盖。

## 3. 自查

### 3.1 28 条与 count 断言

- `t2_edits.json` 共 28 条，`n` 严格为 1–28；覆盖文件集合恰为 3 个目标文件，无白名单外路径。
- 每条在**当前内存内容**上先断言 `count(old) == e["count"]`，不通过就退出且不写任何文件；28/28 通过，见 §2 的 `found` 列。
- 两阶段写盘：先在内存里按顺序完成全部 28 条并逐条校验，再一次性写入 3 个文件；写盘后逐字节复读，与内存结果一致。
- 按字节 `read_bytes()` / `decode("utf-8")` / `encode("utf-8")` 读写，未使用 `utf-8-sig`；三个文件均无 BOM，写后无 CR，文件末尾换行状态不变。

### 3.2 逆序逐字节核对（独立于套用路径）

`impl/verify_t2.py` 从最终文件出发，按 JSON 逆序撤销 28 条：

- 24 条 `new` 非空的：每条断言 `new` 恰好出现 `count` 次，再 `replace(new, old)`；
- 4 条删除项（n=1、7、9、10）：断言套用前快照里 `old` 恰好出现 `count` 次、最终文件里为 0 次；
- 撤销后与“套用前快照扣掉这 4 个删除段”的基准逐字节比较：
  - `frontend/app/globals.css`：`True`（expected / rebuilt 均 `12e66b623233…`）
  - `frontend/lib/utils.ts`：`True`（`7c8c3dfc0cdd…`）
  - `frontend/components/Seal.tsx`：`True`（`5a4b9353b760…`）
- 结论：三个文件相对套用前**只有**这 28 条改动，没有别的字符变化；T1 的第 300 行内容未被改动（第 12 条只在其后插入 `::placeholder`）。

### 3.3 三个文件之外的 tracked 改动

- 本 agent 的脚本只写 `frontend/app/globals.css`、`frontend/lib/utils.ts`、`frontend/components/Seal.tsx` 三个路径（`ALLOWED_FILES` 白名单 + 写盘循环）。
- 完成时 `git diff --name-only` 共 89 个 tracked 文件：
  - 76 个 A 已套用的总表文件（含 `globals.css`）；
  - 2 个 B 新增的 tracked 文件：`frontend/lib/utils.ts`、`frontend/components/Seal.tsx`；
  - 10 个 F 负责的既有测试文件（与 `verify/test_literals.tsv` 的文件集合逐一相同）；
  - 1 个 G 负责的 `frontend/README.md`。
- 也就是说，B 相关的 tracked 改动只有 3 个目标文件；另外 11 个是在 B 运行期间由并行 agent F、G 改的，B 未触碰。除这 3 个文件外，B 没有产生任何 tracked 改动。
- 未跟踪文件都在 `docs/tasks/2026-10-30-design-system/`（任务目录）或 C/D/E 的 4 个新测试文件下，没有 B 产生的白名单外文件；B 在 `impl/` 下新增了 `apply_t2.py`、`verify_t2.py`、`B.md`。

### 3.4 只读文件校验

`02-spec.md`、`verify/README.md`、`verify/t2_edits.json`、`verify/replacements.tsv`、`verify/test_literals.tsv`、`verify/ref/*` 的 sha256 与 A 记录中的派单时值逐一相同（8/8），B 未改动：

```text
1a0274b29affcce671f3e9a07ef83c1929ebc18ed7e1dbd083c0a7b01f73af0b  02-spec.md
f677e6930a7c88175d1a6539136ac5d139166f65e391a47528bf7dd0d41c52c1  verify/README.md
7beed58a195bd0a8afead6621bca94da09f93bc9f4eea2c59a4b74c81bc454e7  verify/t2_edits.json
223580db0326928b4bb495619525647674d43b3b5f93890fc9ab4eb8d394f425  verify/replacements.tsv
e2a191cf795c18307d883dfb2da941ddca10c65ef6c4acfcb3adc369fb4cc3c6  verify/test_literals.tsv
f73eb2115d009a8701a565d8faaf21428adc1dc561d19585c4ade54953f052a6  verify/ref/contrast_check.py
d01ade965797badce2ea939aeca737f38b0be94792c27ad58b48d464e64c2511  verify/ref/gate_rules.py
1ac83e07948b6558c14c61a6c65bee60154ee8463db236b86c28a7ab83508bdb  verify/ref/gate_twcss.mjs
```

## 4. 跑过的命令与结果

### 4.1 套用与逆向核对

```bash
python3 docs/tasks/2026-10-30-design-system/impl/apply_t2.py --dry-run
python3 docs/tasks/2026-10-30-design-system/impl/apply_t2.py
python3 docs/tasks/2026-10-30-design-system/impl/verify_t2.py
```

- `--dry-run`：28 条断言全部通过，输出 `DRY-RUN: all 28 assertions passed; nothing written.`，退出码 0，未写盘。
- `apply`：28 条全部 `OK`；写盘后复读校验通过；输出 `APPLIED: 28 edits in 3 files; post-write byte check OK.`，退出码 0。
- `verify`：逆序撤销 28 条后三个文件与套用前基准逐字节相同；输出 `PASS: reverse replay of all 28 edits byte-exactly restores the pre-T2 files.`，退出码 0。

### 4.2 结构门禁与类型检查（只读）

```bash
python3 -I docs/tasks/2026-10-30-design-system/verify/ref/contrast_check.py frontend/app/globals.css
python3 -I docs/tasks/2026-10-30-design-system/verify/ref/gate_rules.py .
node docs/tasks/2026-10-30-design-system/verify/ref/gate_twcss.mjs frontend
export npm_config_cache=/tmp/fiona-npm-cache
cd frontend && npx tsc --noEmit
```

- `contrast_check.py`：退出码 0；`不达标 0 条：无`。昼/夜/昼素瓷/夜素瓷四套均达标，朱印对 `--stamp` 为昼 5.92、夜 4.53。
- `gate_rules.py`：退出码 0，`== FAIL 0`；扫描 131 个文件，20 条源码规则全 0，T1–T7 令牌层规则全部 PASS（含“10 个 `--fs-*` 只定义一次”“`@theme inline` 10 个 `--text-fs-*`、四档行高精确”“`--seal-soft` 为 `--stamp` 的 12%”“`::placeholder` 在第一个 `@layer base`”“body 有 `--fs-16-5`”）。
- `gate_twcss.mjs`：退出码 0；`scannedFiles=131 font-size/font 违规=0 令牌编译不符=0`。
- `npx tsc --noEmit`：退出码 0，无输出（全前端类型检查通过）。

### 4.3 git 只读查看

```bash
git status --porcelain --untracked-files=all
git diff --stat
git diff --numstat -- frontend/app/globals.css frontend/lib/utils.ts frontend/components/Seal.tsx
git diff -- frontend/app/globals.css frontend/lib/utils.ts frontend/components/Seal.tsx
```

- `git diff --stat`（完成时，含并行 F/G 的在途改动）：
  ```text
  89 files changed, 939 insertions(+), 920 deletions(-)
  ```
- 三文件 diffstat：
  ```text
   frontend/app/globals.css     | 78 ++++++++++++++++++++++++--------------------
   frontend/components/Seal.tsx |  2 +-
   frontend/lib/utils.ts        |  7 +++-
   3 files changed, 49 insertions(+), 38 deletions(-)
  ```
- 三文件 numstat：`42  36  frontend/app/globals.css`、`1  1  frontend/components/Seal.tsx`、`6  1  frontend/lib/utils.ts`。
- `git diff` 人工复核：`globals.css` 的每一处删除/新增都对应 §2 的 1–26 条（第 300 行的 T1 改动保持原样，只在其后新增 `::placeholder`）；`utils.ts` 只有第 27 条一处 hunk；`Seal.tsx` 只有第 28 条一行。

## 5. 偏差与说明

- **内容无偏差**：28 条全部逐字套用，无跳过、无自行修正、无额外格式化。
- **未跑项（按派单要求）**：没有运行 4 个新测试文件；没有重跑 T1；没有跑 `npm run lint`、`npm run build`、pytest（这些由主代理在 B–G 完成后统一执行）。额外跑了 `npx tsc --noEmit`，仅作为令牌层改动的类型自检。
- **核对脚本迭代**：`verify_t2.py` 第一版只对 `new` 非空的条目做逆序替换，对 4 个删除项无法恢复原文，因而误报不一致；随后改为“删除项核对套用前 `count` 次、最终 0 次；其余 24 条逆序撤销后与套用前扣掉删除段的基准逐字节比较”。修正的是核对逻辑，文件内容没有因此改动，修正后 PASS。
- **并行改动**：完成时全仓 89 个 tracked 改动里有 11 个属于并行的 F（10 个测试文件）与 G（`frontend/README.md`），不是 B 改的；B 的写盘路径被脚本白名单限制为 3 个目标文件，见 §3.3。
- 未做任何 git 写操作；未改 `02-spec.md`、`verify/**`、`frontend/components/ui/*`、`desktop/**`、依赖和 lockfile。
