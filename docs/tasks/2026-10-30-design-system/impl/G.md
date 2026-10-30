# G：T5 文档记录

- 角色：工作流 agent G（文档）。只做 `02-spec.md` §T5；未调用 subagent / subagent_fork / workflow。
- 工作目录：`<工作树>`
- 任务：只在 `frontend/README.md` 新增一节「设计令牌与门禁」，10 行以内，写清 T5 的五点。
- 结果：PASS，无偏差。

## 1. 改了哪些文件

| 文件 | 操作 | 增删 |
|---|---|---|
| `frontend/README.md` | 新增一节 | +8 / -0 |
| `docs/tasks/2026-10-30-design-system/impl/G.md` | 新增本记录 | 新文件 |

没有改其他任何文件：`02-spec.md`、`verify/**`、A 已套用的 76 个文件均未触碰；未做任何 git 写操作。

## 2. 新增位置

- 插在「开发约束」之后、「页面」之前：原第 9 行（开发约束段）与第 11 行（`## 页面`）之间。
- 现在位于 `frontend/README.md` 第 11–17 行（第 18 行是原有的 `## 页面`）。
- README 总行数：111 → 119（新增 8 行）。

## 3. 节内容（逐字）

```markdown
## 设计令牌与门禁

- 字号只用 10 个 `text-fs-11 / 12 / 13 / 15 / 16.5 / 18 / 22 / 30 / 46 / 76`；CSS 与行内样式只用对应的 `var(--fs-*)`。
- 颜色只用 `text-/bg-/border-[color:var(--令牌)]`；令牌名见 `app/globals.css` 的四套主题块：`:root`、`.dark`、`:root[data-solid]`、`.dark[data-solid]`。
- `--ink3` 只当装饰，`--stamp` 只给朱印，朱字用 `--seal`。
- 新写法会被 `backend/tests/test_design_system_*.py` 与 `test_design_tokens_contrast.py` 拦下。
- `components/ui/*` 是未使用的 shadcn 原件，豁免。
```

## 4. 行数与五点对应

- 行数：节标题 1 行、空行 1 行、正文 5 条 5 行，共 **7 行**，满足「10 行以内」；diff 新增 8 行（另含节后原有的分隔空行由插入带出），删除 0 行。
- 五点逐条对应：
  1. 字号只用 10 个 `text-fs-*`，CSS 与行内样式用 `var(--fs-*)`：第 1 条。
  2. 颜色只用 `text-/bg-/border-[color:var(--令牌)]`，令牌名见 `app/globals.css` 四套主题块：第 2 条，并列出四套主题块选择器。
  3. `--ink3` 只当装饰、`--stamp` 只给朱印、朱字用 `--seal`：第 3 条。
  4. 新写法会被 `backend/tests/test_design_system_*.py` 与 `test_design_tokens_contrast.py` 拦下：第 4 条。
  5. `components/ui/*` 是未使用的 shadcn 原件、豁免：第 5 条。

## 5. git diff

```diff
diff --git a/frontend/README.md b/frontend/README.md
index 29ca5ea..75836df 100644
--- a/frontend/README.md
+++ b/frontend/README.md
@@ -8,6 +8,14 @@ Fiona 的 Web/PWA 客户端，使用 Next.js 16.4.3、React 19、Tailwind CSS 4
 
 本项目使用的 Next.js 16 与旧版本存在 API、约定和文件结构差异。修改前端代码前，先阅读 [AGENTS.md](./AGENTS.md)，再查阅本地安装版本对应的 `node_modules/next/dist/docs/`，不要直接套用旧版 Next.js 示例。
 
+## 设计令牌与门禁
+
+- 字号只用 10 个 `text-fs-11 / 12 / 13 / 15 / 16.5 / 18 / 22 / 30 / 46 / 76`；CSS 与行内样式只用对应的 `var(--fs-*)`。
+- 颜色只用 `text-/bg-/border-[color:var(--令牌)]`；令牌名见 `app/globals.css` 的四套主题块：`:root`、`.dark`、`:root[data-solid]`、`.dark[data-solid]`。
+- `--ink3` 只当装饰，`--stamp` 只给朱印，朱字用 `--seal`。
+- 新写法会被 `backend/tests/test_design_system_*.py` 与 `test_design_tokens_contrast.py` 拦下。
+- `components/ui/*` 是未使用的 shadcn 原件，豁免。
+
 ## 页面
 
 | 路由 | 功能 |
```

`git diff --numstat -- frontend/README.md`：`8  0  frontend/README.md`；diff 中没有任何删除行。

## 6. 跑过的命令与结果

| 命令 | 结果 |
|---|---|
| `git status --porcelain -- frontend/README.md docs/tasks/2026-10-30-design-system/impl/` | 改前 README 干净；`impl/` 整体未跟踪（已有 `A.md`、`apply_t1.py`）。写入后：`M frontend/README.md`，`?? impl/A.md`、`?? impl/G.md`、`?? impl/apply_t1.py` |
| `git show HEAD:frontend/README.md \| sha256sum` | `df2fb77f01c6117e36255d269395559b88d62dc866fab7ec6ba15e1f53899f75`，作为改前基线 |
| `wc -l frontend/README.md` | `119`（改前 111） |
| `git diff -- frontend/README.md` | 仅新增上述 8 行，无删除、无其他段改动 |
| `git diff --numstat -- frontend/README.md` | `8  0  frontend/README.md` |
| `git diff -U0 -- frontend/README.md \| grep -c '^+[^+]'` | `6`，即新增的非空行（标题 + 5 条）；另有 2 个空行，合计 8 |
| 对 diff 的删除行过滤 | 无删除行 |
| `git diff --check -- frontend/README.md` | 退出码 0，无空白错误 |
| `sed -n '10,18p' frontend/README.md` | 节标题、5 条正文、`## 页面` 前后衔接正常 |
| 节内 grep 中间点（U+00B7）/ `font-semibold` / `font-bold` / `fontWeight` / `<strong` / `<b ` | 均无命中；未新增中间点文案与粗体 |
| `grep -n -- "--text-fs\|--fs-" frontend/app/globals.css` | 写入时 B 尚未套用 T2，暂无该定义；本节按 spec 的目标状态描述，不依赖当前中间态 |
| `sha256sum docs/tasks/2026-10-30-design-system/02-spec.md` | `1a0274b29affcce671f3e9a07ef83c1929ebc18ed7e1dbd083c0a7b01f73af0b`，与 A 记录中的基线一致，未改动 |

说明：C、D、E 并行创建 4 个新测试文件，写入本节时它们尚未落盘，所以没有 pytest 可跑；本节只引用 spec T5 指定的测试文件名，不涉及代码命令。未跑 `npx tsc --noEmit`、`npm run lint`、`npm run build`、pytest（本节为纯文档，权限与任务范围也不包含这些门禁）。

## 7. 偏差与说明

- 无规格偏差；未改 README 其他内容，未改其他文件。
- 四套主题块在文中用选择器 `:root`、`.dark`、`:root[data-solid]`、`.dark[data-solid]` 指代（对应昼、夜、昼素瓷、夜素瓷），避免新增命名歧义；令牌名本身仍以 `app/globals.css` 为准。
- 测试文件路径按 spec T5 原文写为仓库根相对的 `backend/tests/test_design_system_*.py`，未改成 `../backend/...`。
- 未做任何 git 写操作；未触碰 `02-spec.md`、`verify/**` 与 A 的 76 个文件。
