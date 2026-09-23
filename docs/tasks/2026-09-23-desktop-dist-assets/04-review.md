# 复核报告：桌面安装包启动页缺脚本

日期：2026-09-23　基线：`main` @ `5e2adde`　复核方式：独立复核（未参与规格与实现），只读；所有临时副本在 scratchpad `reviewD/` 下。

## 结论：不通过（1 项 must_fix，改动量约 5 行）

主线目标（T1 放行三个文件、T3/T4 接入 CI、T5 文档）全部达成，机械验证我全部复跑一致。唯一的必须修复项是检查脚本 `isLocalRelative()` 把**单个 `/` 开头的根相对路径当成外部地址跳过**，而 Tauri 把 `dist/` 挂在 `tauri://localhost/` 根下，`/main.js` 是合法本地引用。规格 T2.1 只授权忽略 `http(s):`、`data:`、`//` 三类，这个漏判违反规格且直接削弱目标 2（「以后再引用新文件却忘了入库时 CI 报错」）。修复是一处正则 + 一行路径拼接。

`quality.yml` 触发器改动判为**可优化项**（不阻断），理由见下。

## 验收标准逐条核验（规格第 5 节 1–6）

| # | 标准 | 我的复跑结果 | 判定 |
|---|------|-------------|------|
| 1 | `main.js`/`style.css` 不再被忽略；`tmp-check.txt` 仍被忽略 | `git check-ignore -q` 对两文件均 exit 1；`tmp-check.txt` exit 0（已删除）。**注意规格原文写的 `-v` 会 exit 0**：verbose 模式会把命中的否定规则 `!dist/main.js` 也报出来并计为「匹配」，这是 Git 语义，不是实现问题；报告已如实说明，脚本用的是 `-q`。 | 通过（规格文本应改为 `-q`） |
| 2 | 脚本列出 `./style.css`、`./main.js` 均通过、exit 0；根目录与 `desktop/` 下一致 | 根目录、`desktop/`、以及无关目录 `/tmp` 三处运行输出完全相同：两条 `PASS … exists, not ignored by Git` + `Desktop dist assets check passed.`，exit 0 | 通过 |
| 3 | 正控：删 `main.js` → exit 1；加内联 `onclick` → exit 1 | 副本中：删 `main.js` → `FAIL ./main.js: file does not exist (ENOENT)` exit 1；加 `onclick` → `FAIL inline event attribute onclick` exit 1。另加测：旧 `.gitignore` → 两文件 `ignored by Git` exit 1；内联 `<script>` → exit 1；`<style>` 块 + `style=` 属性 → 两条 FAIL exit 1；`../main.js` → `resolves outside desktop/dist` exit 1；新增 `extra.js` 存在但被 `dist/*` 忽略 → exit 1 | 通过 |
| 4 | 三个 dist 文件 sha256 与改动前一致 | `index.html` = `90c3dacf…087b`（与 `HEAD:desktop/dist/index.html` 逐字节一致）；`main.js` = `1a88b585…a56c`；`style.css` = `1744f7b5…eab61`，与报告记录一致 | 通过 |
| 5 | 两个 workflow YAML 可解析，新步骤/新 job 调用脚本 | Ruby Psych 解析成功；`quality.yml` jobs = `[desktop-assets, backend, frontend]`，`desktop-assets` 最后一步 `node desktop/scripts/check-dist-assets.mjs`；Windows 工作流 `Check desktop startup assets`（索引 6）在 `Tauri build (.msi)`（索引 7）之前 | 通过 |
| 6 | `git status --porcelain --untracked-files=all` 都在白名单内 | 5 个 `M`（两 workflow、`PLAN.md`、`desktop/.gitignore`、`desktop/README.md`）+ 5 个 `??`（`main.js`、`style.css`、`check-dist-assets.mjs`、`02-spec.md`、`03-report.md`），`02-spec.md` 是派单前就存在的未跟踪文件 | 通过 |

### 规格 T1–T5 逐项

- **T1** 通过。`dist/*` + 三条 `!` 放行，注释准确。`dist/*` 不忽略目录本身，所以否定规则有效（已实测）。
- **T2** 基本通过，但有 1 处漏判（见必须修复项）。逐点核对：
  - 解析：所有标签的 `src`/`href` 都扫（不限于 `<script>`/`<link>`）；`<link rel=preload>`、`rel=icon` 指向缺失文件 → 两条 FAIL（实测）；带 `?v=2` / `#x` 的地址先切掉 query/hash 再查文件（实测 PASS）；大写 `<LINK HREF>`、`<SCRIPT SRC>` 正常识别（属性名统一小写，`<script>` 正则带 `i`）；HTML 注释先整段剥掉，注释里的 `<script>`/`onclick`/缺失引用不误报（实测）；`mailto:`、`#top`、`//cdn`、`https:`、`data:` 都正确跳过；无引号属性与自闭合 `<link … />` 正常；引号值里含 `>` 不会截断标签（`title="a > b"` 后的 `onClick` 仍被抓到，`data-onclick` 不误报）。
  - git 判定：`git rev-parse --show-toplevel` 以脚本所在目录为 cwd，与运行目录无关；不在仓库（副本拷到仓库外）→ 打印 NOTE 并跳过忽略检查、exit 0；git 不在 PATH（`env PATH=/nonexistent node …`）→ 同样 NOTE + exit 0；`check-ignore` 非 0/1 退出码（如 128）按失败上报。已跟踪文件不受 exclude 规则约束（`check-ignore` exit 1）→ 入库后即使有人误加忽略规则也不会误报，行为正确。
  - Windows：`git rev-parse` 在 Git for Windows 下输出 `D:/a/Fiona/Fiona`（正斜杠），脚本用 `path.relative` 后 `split(sep).join('/')`；我用 `path.win32` 模拟：混合分隔符 → `desktop\dist\main.js` → 转成 `desktop/dist/main.js`；小写盘符也正确；跨盘符 `relative()` 返回绝对路径，脚本已用 `isAbsolute` 兜住。`spawnSync('git')` 在 Windows 上由 libuv 自动补 `.exe`，无需 shell。CRLF 不影响正则（用的是 `\s`/`[\s\S]`）。
  - Node 20 兼容：只用了 `node:fs`/`node:child_process`/`node:path`/`node:url`、`matchAll`、`??`、`?.`，均为 Node 14+ 特性；本机只有 Node 26，未能实跑 Node 20，静态判断无风险。
- **T3** 通过。步骤位于 Rust 测试之后、Tauri 打包之前，命令 `node scripts/check-dist-assets.mjs` 与 job 的 `working-directory: desktop` 一致。
- **T4** 通过（job 本身符合：`ubuntu-latest`、Node 20、无 `npm ci`、5 分钟超时）。触发器改动见可优化项 1。
- **T5** 通过。`desktop/README.md` 第 5 行原「`dist/index.html` 是启动/跳转载体」已改为三文件；第 91 行新增段落准确描述 CI 检查；第 110 行「三文件 = prod build 的启动页」在 HEAD 就已存在。`PLAN.md` 补句位置正确（「P0：剩余发布阻断 → 桌面发布验证」小节开头），措辞与规格一致。全库 `*.md` 我重新 grep `index.html`，除本任务目录外只剩 `desktop/README.md` 三处，均已是三文件表述；报告「未发现其他文档」属实。

### 第 3 点：`main.js` 与 Tauri 侧一致性

- 调用的三条命令 `probe_backend`、`startup_diagnostics`、`open_logs_dir` 都在 `lib.rs` 的 `generate_handler!` 里，也都列在 `build.rs` 的 `AppManifest.commands`（因此自动生成 `allow-probe-backend` 等权限）；`capabilities/default.json` 恰好授予这三条，`local: true`、`windows: ["main"]`，覆盖 `tauri://localhost` 启动页。`open_url`/`open_url_in_app` 在 `remote-links` 里，启动页不用，无交叉。
- 参数：`invoke("probe_backend", { port })` ↔ `fn probe_backend(port: u16)`；另两条无参。`port` 来自 `diag.primary_port || 3000`，无配置时 `StartupReport::default()` 的 `primary_port` 为 0，JS 回退 3000，正确。
- 诊断字段：JS 读取 `config_path`、`config_loaded`、`primary_port`、`ssh_pid`、`port_ready`、`elapsed_ms`、`ssh_log_path`、`notes` 八个，与 `StartupReport` 的 serde 字段一一对应（默认 snake_case，无 rename）。`ssh_pid: Option<u32>` → `null`，JS 用 `!= null` 判断；`elapsed_ms: u128` 由 serde_json 正常序列化为数字。
- 桥：`withGlobalTauri: false`，所以 `window.__TAURI__` 不存在，但 `__TAURI_INTERNALS__.invoke` 由 Tauri 2 无条件注入，JS 优先走它，正确。
- CSP：`script-src 'self'` 放行 `./main.js`，`style-src 'self'` 放行 `./style.css`；页面无内联脚本/样式/事件属性（脚本已验证）；`connect-src` 含 `ipc:`、`http://ipc.localhost`（Tauri IPC）和 `http://localhost:*`（兜底 `fetch`）；`window.location.replace` 不受 CSP 约束；`alert` 不受限。可正常执行。

### 第 4 点：文档陈述

报告 `03-report.md` 中每条数字（退出码、sha256、YAML 解析、步骤顺序）我都复跑一致；对 `-v` 退出码的说明正确；T4 的描述「覆盖所有分支 push 和 PR，原有 backend/frontend 在 push 时仍仅限 main」与 YAML 实际行为一致。`desktop/README.md` 与 `PLAN.md` 陈述准确。仅有一处措辞不精确：README 说 CI 运行 `node desktop/scripts/check-dist-assets.mjs`，Windows 工作流实际在 `desktop/` 下跑 `node scripts/check-dist-assets.mjs`，含义相同，不影响理解。

## 必须修复项（问题、证据、失败场景、修复要求）

### M1 根相对路径 `/xxx` 被当成外部地址跳过（漏判，违反 T2.1）

- **问题**：`desktop/scripts/check-dist-assets.mjs` 第 31 行 `isLocalRelative()` 的排除正则含 `\/`，任何以单个 `/` 开头的地址都不检查。规格 T2.1 只允许忽略 `http(s):`、`data:`、`//` 三类；`/main.js` 在 Tauri 里指向 `tauri://localhost/main.js`，即 `dist/main.js`，是本地引用。
- **证据**：副本 `O_rootrel`：把 `index.html` 改为 `<script src="/main.js">` 并删除 `main.js` → 脚本只打印 `PASS ./style.css` 与 `Desktop dist assets check passed.`，exit 0。
- **失败场景**：以后有人用根相对写法新增 `<link rel="icon" href="/icon.png">` 或 `<script src="/vendor.js">` 却忘了入库（或忘了在 `.gitignore` 加 `!dist/vendor.js`）→ 本地与两个 CI job 全绿 → Windows 打出的安装包再次缺文件，正是本次要杜绝的故障模式；且脚本打印「passed」制造了虚假安全感。
- **修复要求**：
  1. `isLocalRelative()`：只把 `//` 开头视为外部（protocol-relative），单个 `/` 开头视为本地；`#`、`?` 开头仍跳过。
  2. 解析路径时对单 `/` 开头的地址去掉首个 `/` 后再 `resolve(distDir, …)`，现有「越出 dist」判断保持。
  3. 在 `03-report.md` 自测里补一条正控：`<script src="/main.js">` + 删除文件 → exit 1；以及 `/main.js` + 文件存在 → PASS。
  4. 不得改动 `dist/*`、`src-tauri/**` 或其他白名单外文件。

## 可优化项

1. **`quality.yml` 触发器改动（不阻断，但需用户拍板）**。实现方删掉 `push.branches: [main]`、给 `backend`/`frontend` 加 `if: github.event_name != 'push' || github.ref == 'refs/heads/main'`。核验结论：
   - **未改变既有关键行为**：push 到 `main` 与所有 PR 仍跑全部三个 job；`workflow_dispatch` 行为不变。
   - **新增行为**：任何分支（及 tag）push 都会触发 workflow，`desktop-assets` 跑约 20 秒，`backend`/`frontend` 显示为 skipped；有 PR 的分支每次 push 产生 push + pull_request 两个 run，`desktop-assets` 重复跑一次。
   - **concurrency**：组键 `quality-${{ github.ref }}` 按 ref 区分（push 为 `refs/heads/x`，PR 为 `refs/pull/N/merge`），互不取消；同分支连续 push 只取消自己的旧 run。
   - **分支保护**：`gh api …/branches/main/protection` 返回 404（未启用），skipped 不会顶替 required check；若将来启用 required checks 需注意 push 事件上的 skipped 结论。
   - **副作用**：现存远端分支 `origin/security-hardening-deep-check` 若再 push，会因不含 `main.js` 而红（这是正确告警，但会显得突兀）。
   - **授权判断**：白名单允许改 `quality.yml`，但规格只写「新增一个轻量 job」，给两个既有 job 加 `if` 超出字面范围；「每次 push/PR 都会检查」按既有触发器（push main + PR）解释已足够达成目标。报告已如实披露，不算隐瞒。**建议**：二选一——保留现状（换取 feature 分支的早期提醒），或回到最小改动（恢复 `branches: [main]`、删除两个 `if`）。由用户拍板；不拍板则默认建议回到最小改动，减少 Actions 噪音与与规格的偏差。
2. **大小写不匹配只靠 Linux job 兜底**：`./Style.css` 在 macOS/Windows（含 `windows-latest`）上 `statSync` 通过（副本 `N_case` exit 0），只有 `ubuntu-latest` 的 `desktop-assets` 会红。可用 `readdirSync` 精确比对文件名，让本机和 Windows 打包步骤也能抓到。
3. **本机未跟踪文件不告警**：脚本只判「存在且未被忽略」，文件 untracked 时本机 PASS、CI 才红。可加 `git ls-files --error-unmatch` 打印 WARN（不改退出码），把发现时机提前到 push 之前。
4. **Windows 工作流步骤可再前移**：现在排在 `npm ci` + `cargo test` 之后（数分钟），放到 `Setup Node 20` 之后即可让 45 分钟的 job 也在几秒内失败。规格只要求「打包前」，现状合规。
5. **`<script type="application/json">` 会被判为内联脚本**：CSP 不执行 JSON 数据块，属于保守误报；当前页面没有此写法，可不处理。
6. **规格文本**：第 5 节第 1 条 `git check-ignore -v … → 退出码 1` 与 Git 语义不符（verbose 报否定规则匹配也 exit 0），应改为 `-q`，避免下次验收误判。
7. **文档小措辞**：`desktop/README.md` 第 91 行可注明 Windows 工作流在 `desktop/` 目录下运行 `node scripts/check-dist-assets.mjs`；`PLAN.md`「依赖和工程门禁」小节可顺带加一句桌面资源检查 job，非必需。

## 给 Codex 的二次修改指令（仅不通过时）

仅改 `desktop/scripts/check-dist-assets.mjs` 与 `docs/tasks/2026-09-23-desktop-dist-assets/03-report.md`，其他文件一律不动，不运行任何 git 写操作。

1. 把 `isLocalRelative(value)` 改为：空串、`#`/`?` 开头、`//` 开头、`data:`、`http(s):` 及任何 `scheme:` 开头 → 非本地；**单个 `/` 开头（后面不是 `/`）→ 本地**。
2. 在引用解析处，取 `pathPart` 后若以 `/` 开头则去掉首个 `/`（只去一个），再 `resolve(distDir, decodeURIComponent(...))`；保留现有「越出 dist」「不是文件」「被 git 忽略」三段判断。
3. 自测并写进 `03-report.md`：
   - 副本中 `<script src="/main.js">` 且删除 `main.js` → exit 1，输出含 `file does not exist`；
   - 副本中 `<script src="/main.js">` 且文件存在 → `PASS /main.js`，exit 0；
   - `<a href="//cdn.example/x.js">` 仍被跳过（不出现在 PASS/FAIL 列表）；
   - 原有正控（缺文件、`onclick`、内联 `<script>`、`<style>`、`../` 越界、旧 `.gitignore`）重跑仍 exit 1；根目录与 `desktop/` 下正常运行 exit 0。
4. 可选（若顺手）：按可优化项 2 用 `readdirSync(dirname(assetPath))` 精确比对 `basename`，不匹配则 FAIL 并给出实际文件名；若做了，补一条 `./Style.css` 正控。

以上改完后 `desktop/dist/*` 三个文件 sha256 必须仍为报告中的值。
