# 规格：桌面安装包启动页缺脚本

日期：2026-09-23　级别：L1　基线：`main` @ `5e2adde`

## 0. 背景（你看不到之前的对话，这里是全部上下文）

Fiona 的 Windows 桌面壳是 Tauri 2（`desktop/`）。`desktop/src-tauri/tauri.conf.json` 的 `frontendDist` 是 `../dist`，打包时把 `desktop/dist/` 整个目录嵌进安装包。启动页 `desktop/dist/index.html` 在 2026-08-26 的安全整改（提交 `106a894`）中把内联脚本与样式拆到了同目录的 `./main.js` 与 `./style.css`，以满足 CSP（`script-src 'self'`、`style-src 'self'`）。

问题：`desktop/.gitignore` 第 8–9 行是

```
dist/*
!dist/index.html
```

所以 `main.js`、`style.css` 从未进入版本库。作者本机构建能用（磁盘上有这两个文件），但 GitHub Actions 的 `Build Windows Desktop`（`.github/workflows/build-windows-desktop.yml`）从干净检出构建，安装包里只有 `index.html`：窗口永远停在「加载菲欧娜中…」，既不跳转公网，也不显示诊断面板。CI 的构建本身会成功，所以一直没人发现。

这两个文件是手写的静态文件（无构建步骤生成），内容已由 Claude 审阅：只含公开域名 `https://madchloechat.online`，没有密钥或 SSH 信息，可以入库。它们的内容**不需要也不允许修改**。

## 1. 目标

1. 干净检出后 `desktop/dist/` 里有启动页需要的全部文件，CI 打出的安装包能正常跳转/显示诊断。
2. 以后启动页再引用新文件却忘了入库时，CI 在几秒内报错，而不是打出一个坏安装包。

## 2. 约束

- **允许修改（白名单）**：`desktop/.gitignore`、新增 `desktop/scripts/check-dist-assets.mjs`、`.github/workflows/build-windows-desktop.yml`、`.github/workflows/quality.yml`、`desktop/README.md`、`PLAN.md`，以及本目录下的 `03-report.md`。
- **禁止修改**：`desktop/dist/*` 三个文件的内容、`desktop/src-tauri/**`、任何 `package*.json` 与锁文件、`backend/**`、`frontend/**`。不新增依赖（检查脚本只用 Node 20 自带模块）。
- 不要运行 `git add`/`commit`/`push`/`stash`/`reset`/`checkout`；入库由 Claude 负责。

## 3. 任务清单

- **T1** `desktop/.gitignore`：保留「忽略 `dist/` 下其他临时文件」的意图，放行 `dist/index.html`、`dist/main.js`、`dist/style.css` 三个文件；把注释改成准确描述（这三个是启动页必需文件，必须入库）。
- **T2** 新增 `desktop/scripts/check-dist-assets.mjs`（Node 20 标准库，ESM）：
  1. 读取 `desktop/dist/index.html`，找出所有 `<script src>`、`<link href>`（以及其他指向本地相对路径的 `src`/`href`），忽略 `http(s):`、`data:`、`//` 开头的外部地址；
  2. 对每个本地引用断言：文件存在；且未被 git 忽略（在仓库里时调用 `git check-ignore -q <path>`，返回 0 即视为被忽略→失败；不在 git 仓库里或没有 git 时跳过这一项并打印提示）；
  3. 断言 `index.html` 不含内联脚本（`<script>` 有内容且无 `src`）、内联事件属性（`on[a-z]+=`）、`<style>` 块或 `style=` 属性——它们会被 CSP 拦截；
  4. 通过时打印每个引用及结果、退出码 0；任一失败打印原因、退出码 1。脚本路径解析要与运行时工作目录无关（基于脚本自身位置定位 `dist/`）。
- **T3** `.github/workflows/build-windows-desktop.yml`：在 `Tauri build (.msi)` 之前加一步运行 T2 脚本。
- **T4** `.github/workflows/quality.yml`：新增一个轻量 job（如 `desktop-assets`，`ubuntu-latest`、Node 20、无需 `npm ci`），检出后运行 T2 脚本。这样每次 push/PR 都会检查，不必等 45 分钟的 Windows 构建。
- **T5** 文档：`desktop/README.md` 说明 `dist/` 三个启动页文件必须入库、CI 会用 T2 脚本检查；`PLAN.md`「P0：剩余发布阻断 → 桌面发布验证」处补一句：2026-09-23 已修复启动页脚本/样式未入库导致 CI 安装包卡在加载页的问题（签名、`Cargo.lock`、版本发布等其余项仍未完成）。全库搜索是否还有其他文档声称启动页只有 `index.html`，一并更正。

## 4. 何时停下来问

- 必须停：只能通过修改 `dist/*` 内容或 `src-tauri/**` 才能达成目标时。
- 不要停、自己定：脚本的具体解析方式、输出格式、job 名称、注释措辞。
- 任何情况下不回滚已完成的工作。

## 5. 验收标准（Claude 会逐条执行）

在仓库根目录：

1. `git check-ignore -v desktop/dist/main.js; echo $?` 与 `desktop/dist/style.css` 同样 → 均输出退出码 1（不再被忽略）；`touch desktop/dist/tmp-check.txt && git check-ignore -q desktop/dist/tmp-check.txt; echo $?` → 0（其他临时文件仍被忽略），随后删除该临时文件。
2. `node desktop/scripts/check-dist-assets.mjs; echo $?` → 列出 `./style.css`、`./main.js` 两个引用均通过，退出码 0；在 `desktop/` 与仓库根目录下运行结果相同。
3. 正控（Claude 在副本中做）：删除副本里的 `main.js` → 脚本退出码 1；在副本 `index.html` 加一个内联 `onclick` → 退出码 1。
4. `desktop/dist/` 三个文件的 sha256 与改动前一致。
5. 两个 workflow YAML 可被解析，新步骤/新 job 调用了该脚本。
6. `git status --porcelain --untracked-files=all` 中的路径都在第 2 节白名单内（`desktop/dist/main.js`、`desktop/dist/style.css` 会因不再被忽略而以 `??` 出现，这是预期）。

## 6. 交付

把变更总结写入 `docs/tasks/2026-09-23-desktop-dist-assets/03-report.md`：修改了哪些文件、T1–T5 逐项对应、自测命令与输出、需要人工确认的地方。
