# 桌面启动页资源修复报告

日期：2026-09-23

## 变更与任务对应

- **T1** `desktop/.gitignore`：继续忽略 `dist/` 下其他文件，显式放行必须入库的 `index.html`、`main.js`、`style.css`，并更新注释。
- **T2** 新增 `desktop/scripts/check-dist-assets.mjs`：从脚本自身位置读取启动页，检查本地 `src`/`href` 引用的文件存在且未被 Git 忽略，并拒绝内联脚本、事件属性、`<style>` 块和 `style` 属性。只使用 Node 标准库；无 Git 仓库或未安装 Git 时提示跳过忽略检查。
- **T3** `.github/workflows/build-windows-desktop.yml`：在 Tauri 打包前运行资源检查。
- **T4** `.github/workflows/quality.yml`：增加无需 `npm ci` 的 Node 20 `desktop-assets` job，覆盖所有分支 push 和 PR。原有 backend/frontend job 在 push 时仍仅限 main。
- **T5** `desktop/README.md`：说明三个手写启动页文件必须入库及 CI 检查；`PLAN.md`：记录此次修复及仍未完成的桌面发布项。全库 Markdown 搜索未发现其他声称启动页只有 `index.html` 的文档。

`desktop/dist/index.html`、`desktop/dist/main.js`、`desktop/dist/style.css` 的内容均未修改；没有新增依赖，也没有执行 `git add`、提交、推送、暂存、重置或检出。

## 自测（规格第 5 节的 1、2、4、5 条）

1. `git check-ignore -q desktop/dist/main.js` 和 `git check-ignore -q desktop/dist/style.css` 均退出 **1**，表示未被忽略。创建 `desktop/dist/tmp-check.txt` 后运行 `git check-ignore -q desktop/dist/tmp-check.txt` 退出 **0**；测试文件已删除。按规格原文另运行 `git check-ignore -v`：两文件分别显示 `!dist/main.js` 和 `!dist/style.css`，退出码均为 **0**。这是 Git 的详细模式会报告匹配到的否定规则所致，不能把其退出码解读为文件被忽略；脚本使用规格指定的 `-q` 判定。
2. 在仓库根目录运行 `node desktop/scripts/check-dist-assets.mjs`、在 `desktop/` 运行 `node scripts/check-dist-assets.mjs`：两次均输出 `PASS ./style.css: exists, not ignored by Git`、`PASS ./main.js: exists, not ignored by Git` 和 `Desktop dist assets check passed.`，退出码均为 **0**。
4. 修改前后 SHA-256 一致：`index.html` 为 `90c3dacf6c22ec9a3e909af8bb21a6c7c0c4c438327970691e10a4c931ad087b`，`main.js` 为 `1a88b58556f044321a9233fb811b6373dad63873bdb25ea004b30324f4f1a56c`，`style.css` 为 `1744f7b5c6ec5c45bda4e4d94e71066595f91145ac6320d83da1cacaca4eab61`。
5. Ruby Psych 成功解析两个 workflow YAML，退出码 **0**。结构检查确认 Windows 资源检查位于 `Tauri build (.msi)` 之前，Quality 的 `desktop-assets` job 使用 `ubuntu-latest`、Node 20 和 `node desktop/scripts/check-dist-assets.mjs`，且无 `npm ci`；退出码 **0**。`git diff --check` 退出码 **0**。

## 需要人工确认

- `desktop/dist/main.js`、`desktop/dist/style.css` 当前按预期显示为未跟踪文件；由后续入库操作把它们和本次代码变更一起提交，才能使干净检出的 CI 安装包携带资源。会话开始时 `02-spec.md` 也已是未跟踪文件，本次未修改它。
- 实际 Windows CI 构建与安装包启动、跳转和诊断界面仍需在提交后验证。本地未运行 Windows 打包。
- 若按验收 1 原文检查 `git check-ignore -v` 的退出码，需要考虑上述 Git 否定规则行为；以 `git check-ignore -q` 的退出码判断是否被忽略。

## 返修第 1 轮

按 `05-fix-round1.md` 处理 R1 和 Q1–Q5，保留上轮已完成的工作：

- **R1** `desktop/scripts/check-dist-assets.mjs` 将单个 `/` 开头的引用按 `dist/` 根路径解析，仍跳过 `//`、`#`、`?` 和带 scheme 的地址；存在性、越界、文件类型与 Git 忽略检查照常执行。
- **Q1** `.github/workflows/quality.yml` 恢复 `push.branches: [main]`，移除上轮给 backend/frontend job 增加的 `if`。相对基线 `5e2adde`，该文件现在只新增 `desktop-assets` job。上文 T4 的“覆盖所有分支 push”描述已由本轮取舍取代。
- **Q2** 脚本用 `readdirSync` 逐级比对引用与实际路径分量的大小写；不一致时输出期望和实际文件名并失败。
- **Q3** 对未被 Git 跟踪的本地资源输出 `WARN … not tracked by Git (commit it before pushing)`，不改变成功退出码。
- **Q4** Windows 工作流的资源检查已移至 `Setup Node 20` 之后、`Setup Rust stable` 之前。
- **Q5** `desktop/README.md` 明确质量检查从仓库根目录运行脚本，而 Windows 工作流在 `desktop/` 下运行 `node scripts/check-dist-assets.mjs`。

### 本轮自测

正控在 `/private/tmp` 的隔离副本中执行：逐项复制脚本、三个 `dist/` 文件和 `.gitignore`，只改副本；用 `GIT_DIR` 指向原仓库的 Git 元数据、`GIT_WORK_TREE` 指向副本以做只读 Git 检查，再运行 `node <副本>/desktop/scripts/check-dist-assets.mjs`。每项的命令退出码与关键输出如下，临时副本已清理。

| 用例 | 退出码 | 关键输出 |
|---|---:|---|
| 旧 `.gitignore` | 1 | `FAIL ./style.css: ignored by Git`（`main.js` 也失败） |
| 删除 `main.js` | 1 | `FAIL ./main.js: file does not exist (ENOENT)` |
| 内联 `onclick` | 1 | `FAIL inline event attribute onclick is blocked by CSP` |
| 内联 `<script>` | 1 | `FAIL inline script is blocked by CSP` |
| `<style>` 块 | 1 | `FAIL <style> block is blocked by CSP` |
| `../main.js` 越出 `dist/` | 1 | `FAIL ../main.js: resolves outside desktop/dist` |
| 恢复原始副本 | 0 | `Desktop dist assets check passed.` |
| `/main.js` 且删除文件 | 1 | `FAIL /main.js: file does not exist (ENOENT)` |
| `/main.js` 且文件存在 | 0 | `PASS /main.js: exists, not ignored by Git` |
| `//cdn.example.com/x.js` | 0 | `Desktop dist assets check passed.`；该地址未出现在 PASS/FAIL 中 |
| `./Style.css` 对应实际 `style.css` | 1 | `filename case mismatch (expected "Style.css", actual "style.css")` |

正常运行 `node desktop/scripts/check-dist-assets.mjs`，以及从 `desktop/` 运行 `node scripts/check-dist-assets.mjs`，两次均退出 **0**，输出相同：`./style.css` 和 `./main.js` 各有一条未跟踪 `WARN` 和一条存在且未被忽略的 `PASS`，最后为 `Desktop dist assets check passed.`。这也验证 Q3 提示不改变退出码。

`shasum -a 256 desktop/dist/index.html desktop/dist/main.js desktop/dist/style.css` 与上文记录的三个 SHA-256 完全一致。Ruby `YAML.load_file` 成功解析两份 workflow；结构检查显示 Windows 步骤索引依次为 Node 20 = 1、资源检查 = 2、Rust stable = 3，Quality jobs 为 `desktop-assets, backend, frontend`。`git diff 5e2adde -- .github/workflows/quality.yml` 仅显示新增 job；`git diff --check` 退出 **0**。

未修改 `desktop/dist/*` 内容，也未执行 `git add` 或提交。`main.js` 与 `style.css` 仍按预期未跟踪，需要在后续入库时一并提交。
