# 第二轮复核：桌面安装包启动页缺脚本

日期：2026-09-23　基线：`main` @ `5e2adde`　复核方式：第二轮独立复核（未参与规格、实现与返修），只读；所有正控在 scratchpad `reviewD2/` 下的隔离副本（独立 `git init`）中执行，仓库本身未被写入。

复核范围按第二轮规则：只核验 R1 是否真正修好、返修是否引入回归（Q1–Q5、dist 三文件内容、两份 YAML）。新发现一律标为 optional，不阻断。

## 结论：通过

- R1（根相对路径 `/xxx` 漏判）已真正修好：`/main.js` 缺文件 → exit 1；`/main.js` 存在 → PASS、exit 0；`//cdn…` 仍跳过；`/../main.js` 仍判越界；`/vendor.js` 存在但被 `dist/*` 忽略 → exit 1。
- 上一轮的 7 个正控重跑结果全部不变；Q1–Q5 逐项核实；dist 三文件 sha256 与第一轮记录一致，`index.html` 与 `HEAD` 逐字节一致；两份 YAML 可解析且结构正确。
- 未发现回归。新发现只有两条 optional 文档小项。

## R1 核验（证据）

改动点：`desktop/scripts/check-dist-assets.mjs` 第 31 行 `isLocalRelative()` 排除正则改为 `^(?:\/\/|#|\?|[a-z][a-z\d+.-]*:)`（只排 `//`、`#`、`?`、带 scheme），第 81 行对单 `/` 开头的 `pathPart` 做 `slice(1)` 后再 `resolve(distDir, …)`；第 88–92 行「越出 dist」判断原样保留。

隔离副本：把 `desktop/dist/*` 三文件、`desktop/.gitignore`、`desktop/scripts/check-dist-assets.mjs` 复制到 `reviewD2/repo/desktop/`，`git init` 后只提交 `.gitignore`、`index.html`、脚本（`main.js`/`style.css` 保持未跟踪，与真实仓库当前状态一致）；每个用例前恢复原始副本；脚本从无关目录 `/private/tmp` 调用，验证与 cwd 无关。

| 用例 | 退出码 | 关键输出 |
|---|---:|---|
| R1a `<script src="/main.js">` + 删除 `main.js` | 1 | `FAIL /main.js: file does not exist (ENOENT)` |
| R1b `<script src="/main.js">` + 文件存在 | 0 | `PASS /main.js: exists, not ignored by Git` |
| R1c `<link href="/style.css">` | 0 | `PASS /style.css: exists, not ignored by Git` |
| R1d 追加 `<script src="//cdn.example.com/x.js">` | 0 | 该地址不出现在 PASS/FAIL 列表，其余两条 PASS |
| R1e `<script src="/../main.js">` | 1 | `FAIL /../main.js: resolves outside desktop/dist` |
| R1f `<script src="/">`（边缘） | 1 | `FAIL /: not a file` |
| R1g `<script src="/main.js?v=2#top">` | 0 | query/hash 先剥掉再查文件，PASS |
| R1h `<script src="/vendor.js">` 且副本里真有 `vendor.js`（未加 `!` 放行） | 1 | `FAIL /vendor.js: ignored by Git (desktop/dist/vendor.js)` |

R1h 正是第一轮描述的失败场景（根相对写法引用新文件、忘记入库/忘记放行），现在会被拦下，目标 2 恢复成立。

## 回归检查（Q1–Q5、dist 内容、YAML）

### 上一轮 7 个正控重跑（同一隔离副本）

| 用例 | 退出码 | 关键输出 |
|---|---:|---|
| C0 副本基线（两文件未跟踪） | 0 | 两条 `WARN … not tracked by Git` + 两条 `PASS` + `Desktop dist assets check passed.` |
| C1 换回 `5e2adde` 的旧 `.gitignore` | 1 | `FAIL ./style.css: ignored by Git`、`FAIL ./main.js: ignored by Git` |
| C2 删除 `main.js` | 1 | `FAIL ./main.js: file does not exist (ENOENT)` |
| C3 `retry-btn` 加 `onclick="x()"` | 1 | `FAIL inline event attribute onclick is blocked by CSP` |
| C4 追加 `<script>alert(1)</script>` | 1 | `FAIL inline script is blocked by CSP` |
| C5 `<head>` 加 `<style>body{}</style>` | 1 | `FAIL <style> block is blocked by CSP` |
| C6 `./main.js` 改 `../main.js` | 1 | `FAIL ../main.js: resolves outside desktop/dist` |
| C7 恢复原始副本 | 0 | `Desktop dist assets check passed.` |

### Q1 `quality.yml` 回到最小改动

`git diff 5e2adde -- .github/workflows/quality.yml` 输出只有一个 hunk：在 `jobs:` 下新增 `desktop-assets`（`ubuntu-latest`、`timeout-minutes: 5`、`checkout@v4` + `setup-node@v4` Node 20 + `node desktop/scripts/check-dist-assets.mjs`），共 11 行新增、0 行删除。`on.push.branches: [main]` 仍在（第 6 行），`backend`/`frontend` 两个 job 均无 `if`（Ruby 结构打印 `if=nil`）。符合返修单要求。

### Q2 大小写精确匹配

| 用例 | 退出码 | 关键输出 |
|---|---:|---|
| Q2a `./Style.css`（实际 `style.css`） | 1 | `FAIL ./Style.css: filename case mismatch (expected "Style.css", actual "style.css")` |
| Q2b `/Main.js`（根相对 + 大小写错） | 1 | `FAIL /Main.js: filename case mismatch (expected "Main.js", actual "main.js")` |
| Q2c 目录分量大小写错 `./Assets/app.js`（实际 `assets/app.js`） | 1 | `FAIL ./Assets/app.js: filename case mismatch (expected "Assets", actual "assets")` |
| Q2d `./nope.js`（无任何大小写候选） | 1 | 走原路径：`FAIL ./nope.js: file does not exist (ENOENT)` |

逐级 `readdirSync` 比对（第 94–116 行）在 macOS 这种不区分大小写的文件系统上也能抓到，且不影响缺文件的原有报错。

### Q3 未跟踪提示不改退出码

- 真实仓库从根目录、`desktop/`、`/private/tmp` 三处运行输出完全相同：`./style.css`、`./main.js` 各一条 `WARN … not tracked by Git (commit it before pushing)` + 一条 `PASS`，最后 `Desktop dist assets check passed.`，三次均 exit 0。
- 副本中把两文件 `git add` + commit 后再跑：无 WARN、两条 PASS、exit 0（Q3a）；`git rm --cached` 回到未跟踪：WARN 重现、仍 exit 0（Q3b）。
- `git ls-files --error-unmatch` 的 stderr（`error: pathspec … did not match`）被 `spawnSync` 捕获，不会漏到 CI 日志里制造噪音（真实仓库运行输出中无此行）。
- 副本拷到仓库外（N1）与 `PATH=/nonexistent`（N2）：均打印 `NOTE: Git unavailable or outside a repository; skipping ignore checks.`，两条 `PASS … exists`，exit 0——第一轮验过的行为未变。

### Q4 Windows 工作流检查步骤位置

Ruby Psych 解析 `build-windows-desktop.yml` 成功；步骤索引：`[1] Setup Node 20` → `[2] Check desktop startup assets`（`run: node scripts/check-dist-assets.mjs`）→ `[3] Setup Rust stable` → … → `[7] Tauri build (.msi)`。job `working-directory: desktop`，与相对命令一致。`git diff` 显示该文件只有这 3 行新增。

### Q5 README

`desktop/README.md` 第 91 行现为：「质量检查从仓库根目录运行 `node desktop/scripts/check-dist-assets.mjs`；Windows 工作流在 `desktop/` 下运行 `node scripts/check-dist-assets.mjs`。」第 5 行三文件表述与第 112 行既有条目一致。全库 `*.md` grep `index.html`（排除本任务目录）只命中 `desktop/README.md` 这三处，均已是三文件表述。

### dist 三文件内容

`shasum -a 256`：
- `desktop/dist/index.html` = `90c3dacf6c22ec9a3e909af8bb21a6c7c0c4c438327970691e10a4c931ad087b`，与 `git show HEAD:desktop/dist/index.html` 的 sha256 逐字节一致；
- `desktop/dist/main.js` = `1a88b58556f044321a9233fb811b6373dad63873bdb25ea004b30324f4f1a56c`；
- `desktop/dist/style.css` = `1744f7b5c6ec5c45bda4e4d94e71066595f91145ac6320d83da1cacaca4eab61`；

三个值与 `03-report.md`、`04-review.md` 记录完全相同。`git status` 中 `desktop/dist/` 只有 `main.js`、`style.css` 两个 `??`，`index.html` 无改动。

### `.gitignore`

真实仓库 `git check-ignore -q`：`main.js`、`style.css`、`index.html` 均 exit 1（未忽略）；`desktop/dist/tmp-check.txt`、`desktop/dist/extra.js` 均 exit 0（仍被忽略；`check-ignore` 只按模式匹配，无需创建文件，因此本轮没有向仓库写任何临时文件）。`-v` 模式对两文件报出的是否定规则 `!dist/main.js`/`!dist/style.css`，与第一轮的说明一致。`desktop/.gitignore` 相对基线只多了两行 `!` 与一行注释改写。

### YAML 与白名单

- 两份 workflow 均由 Ruby Psych `YAML.load_file` 成功解析；`quality.yml` jobs = `[desktop-assets, backend, frontend]`。（本机无 PyYAML，只用了 Ruby。）
- `git diff --check` exit 0。
- `git status --porcelain --untracked-files=all`：5 个 `M`（两 workflow、`PLAN.md`、`desktop/.gitignore`、`desktop/README.md`）+ 3 个 `??`（`main.js`、`style.css`、`check-dist-assets.mjs`）+ 本任务目录下的 4 份文档，全部在白名单内。
- Node 版本：本机只有 Node 26，未能实跑 Node 20；返修新增的 API 只有 `readdirSync`（无 options）与 `git ls-files` 子进程调用，均为 Node 20 标准库既有能力，静态判断无风险。

## 新发现（仅 optional）

1. **`03-report.md` 第 10 行 T4 描述已过期**：仍写「覆盖所有分支 push 和 PR。原有 backend/frontend job 在 push 时仍仅限 main」，与 Q1 回到最小改动后的实际行为（整个 workflow push 只在 `main` 触发）不符。「返修第 1 轮」小节已注明「上文 T4 的描述已由本轮取舍取代」，所以不算隐瞒，但入库前若顺手把第 10 行改成「与既有触发器一致（push main + 所有 PR）」，读者不必往下翻才知道哪句作数。
2. **PASS/WARN 行打印的是原始地址含 query/hash**（如 `PASS /main.js?v=2#top`），实际检查的是剥掉 query/hash 后的文件；当前页面没有这种写法，纯输出美观问题，可不处理。
