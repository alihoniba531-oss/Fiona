# 返修单 第 1 轮（桌面启动页资源）

来源：`04-review.md`（独立复核，结论：不通过）。原规格 `02-spec.md` 的白名单与禁止事项不变；`desktop/dist/*` 三个文件内容仍不许改。

## 必须修复

- **R1 根相对路径漏判**：按 `04-review.md`「给 Codex 的二次修改指令」修改 `desktop/scripts/check-dist-assets.mjs`：只有 `//` 开头视为外部地址；单个 `/` 开头（后面不是 `/`）视为 `dist/` 内的本地路径，去掉首个 `/` 后按 `dist/` 解析，照常做「越出 dist / 非文件 / 被 Git 忽略」三项检查；`#`、`?` 开头与带 scheme 的地址仍跳过。

## 同轮处理（Claude 替产品负责人做的取舍与小改进）

- **Q1 回到最小 CI 改动**：`.github/workflows/quality.yml` 恢复 `push` 触发的 `branches: [main]`，删除给 `backend`、`frontend` 两个 job 加的 `if` 条件；只保留新增的 `desktop-assets` job。改完后该文件相对基线（`git show 5e2adde:.github/workflows/quality.yml`）的差异应只剩新增的 job。
- **Q2 大小写精确匹配**：对每个本地引用，除存在性外，用目录列表逐级核对文件名大小写与引用完全一致（macOS/Windows 文件系统不区分大小写，但打包后的资源查找可能区分）；不一致时失败并打印期望与实际文件名。
- **Q3 未跟踪提示**：在 Git 仓库内且文件未被 `git ls-files --error-unmatch` 收录时，打印 `WARN … not tracked by Git (commit it before pushing)`，不改变退出码。
- **Q4 提前失败**：`.github/workflows/build-windows-desktop.yml` 里的检查步骤移到 `Setup Node 20` 之后、`Setup Rust stable` 之前。
- **Q5 文档**：`desktop/README.md` 注明 Windows 工作流在 `desktop/` 下运行 `node scripts/check-dist-assets.mjs`。

## 自测（写进报告）

- 原有 7 个正控（旧 `.gitignore`、缺 `main.js`、内联 `onclick`、内联 `<script>`、`<style>` 块、路径越出 dist、恢复后通过）重跑结果不变；
- 新增正控：`<script src="/main.js">` + 删文件 → exit 1；`/main.js` + 文件存在 → PASS；`//cdn.example.com/x.js` 仍跳过；引用 `./Style.css` 而文件是 `style.css` → exit 1；
- `desktop/dist/*` 三文件 sha256 与改动前一致；两份 workflow YAML 可解析。

把本轮说明追加到 `03-report.md` 末尾「返修第 1 轮」小节。不要 `git add/commit`。
