# 返修单 R1（2026-10-28）

门禁 54 项与真实浏览器实测都已通过（原生弹窗 0、加载无滑入、Tab 30 步焦点全为墨线、粗体 0、消息行按钮 / 朗读 / 复制 / 删除确认均符合规格）。只有一处要改，只许动 `frontend/components/ConfirmDialog.tsx` 与 `backend/tests/test_component_language.py`（后者只增不减），并在 `03-report.md` 末尾追加「R1 返修」一节。

## R1-1 确认框去掉「无 Context 兼容分支」，改为模块级队列

问题：为了让 `backend/tests/test_novel_p2_r1.py` 里的精简 React（没有 `createContext` / `useContext`）能渲染 `NovelWorkbench`，现在的实现：

- `createContext` 存在才建 Context，否则 `ConfirmContext = null`；
- 把 `useContext` 改名为 `readContext` 引入，在普通函数 `readContextValue` 里有条件地调用——这是借改名躲开 `react-hooks/rules-of-hooks` 检查；
- `ConfirmProvider` 在没有 Context 时直接渲染 children。

功能上没错，但生产代码为测试替身开了一条分支，还靠改名绕 lint。改成不依赖 Context 的写法（既有测试不改）：

1. 模块级状态：
   - `let host: ((item: QueueItem) => void) | null = null;`——由已挂载的 `ConfirmProvider` 注册；
   - 两个**模块级**函数（不是 hook，也不调用任何 hook）：
     - `function confirmImpl(options: ConfirmOptions): Promise<boolean>`
     - `function noticeImpl(options: NoticeOptions): Promise<void>`
     
     两者在 `host` 为空时返回 `Promise.reject(new Error("ConfirmProvider missing"))`，否则 `new Promise(resolve => host!({...}))`。
2. `export function useConfirm() { return confirmImpl; }`、`export function useNotice() { return noticeImpl; }`：返回稳定引用，不调用任何 React API。导出名与签名不变。
3. `ConfirmProvider`：用 `useEffect` 在挂载时把自己的 `enqueue` 设为 `host`，卸载时若 `host` 仍是自己就置回 `null`。其余行为（FIFO 队列、`showModal()`、`role="alertdialog"`、取消 / 确定的默认焦点、Esc 与点遮罩 = 取消、关闭后焦点归还、样式类）**一律不变**。
4. 删掉：`createContext`、`useContext` / `readContext`、`ConfirmContext`、`readContextValue`、`ConfirmContextValue`、`useMemo(...)` 的 value，以及「没有 Context 就直接渲染 children」的分支和相关注释。`ConfirmProvider` 返回 `<>{children}{dialog}</>`。
5. 每个文档（主页面、每个 iframe 抽屉）都有自己的模块实例和根布局，因此各自有自己的 `host`，不需要额外处理。

## R1-2 测试补强（只增不减）

在 `test_component_language.py` 追加：

- `ConfirmDialog.tsx` 不含 `createContext`、`useContext`、`readContext`、`ConfirmContext`；
- 含 `Promise.reject(new Error("ConfirmProvider missing"))`；
- `useConfirm` 与 `useNotice` 的函数体内不含 `use` 开头的调用（正则：取 `export function useConfirm` 到下一个 `\n}` 的片段，断言不匹配 `\buse[A-Z]\w*\(`）；
- node 行为用例（缺依赖则 skip，写法同现有用例）：转译 `ConfirmDialog.tsx`，在**不挂 Provider** 的情况下调用 `useConfirm()({ body: "x" })`，断言 Promise 被拒绝且错误信息为 `ConfirmProvider missing`。

## R1-3 自检

在报告里写出以下命令的实际输出：

- `cd frontend && npx tsc --noEmit`；
- `npm run lint`：0 errors，warnings ≤ 25；
- `npm run build`；
- `cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py tests/test_component_language.py tests/test_novel_p2_r1.py -p no:cacheprovider`：全部通过，0 skipped。

不改其他文件；不提交 git；改动很小，单代理直接做，不得调用 subagent / subagent_fork / workflow。
