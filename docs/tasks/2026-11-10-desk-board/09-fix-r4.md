# 返修单 R4：案头第一期

R3 之后，机械门禁、变异、三个宽度的界面走查（101 项）都通过了。第二轮独立复核（报告在同目录 `08-review-r2.md`，请完整读第 5、6、8 节和附录）确认上一轮 2 条已修好、验收 10 条全部符合，但新发现 3 条必须修复，前两条是 R2 的改动带出来的。

规格已改成 v1.4：**请读 `docs/tasks/2026-11-10-desk-board/02-spec.md` 第 13 节**，它就是这一轮的完整要求。

硬规矩不变：只改白名单内的文件；`backend/` 下只许动 `tests/test_desk_*.py`；`frontend/app/page.tsx`、`lib/useRovingTabs.ts`、`lib/useAccountIdentity.ts` 和任何既有组件（含 `components/studio/BreakdownDialog.tsx`、`EpisodePlan.tsx`）都不许改；不装依赖；不提交、不 stash、不切分支；任务目录下 `01`–`09` 开头的文件和 `design/` 不要改。由你自己直接改，不要调用 subagent / subagent_fork / workflow。

## 要做的事

| 规格小节 | 内容 | 主要文件 |
|---|---|---|
| 13.1 | 分集三个对话框的 `busy` 不再含锁定状态；合并 / 批准用 `disabled`，修改在锁定时拒绝保存；加 `initialDialog` | `DeskEpisodesView.tsx` |
| 13.2 | 面板里的收起按钮收起后把焦点还给头部开关 | `DeskDock.tsx` |
| 13.3 | 四处断言绑到元素上，各配自检 | `test_desk_views_frontend.py` |
| 13.4 | 分集三个对话框开着时也忽略定位（`onDialogOpenChange`） | `DeskEpisodesView.tsx`、`DeskDock.tsx` |
| 13.5 | 细纲对话框「关闭」在 busy 时禁用；收起时清空呈现方式 | `DeskDialogs.tsx`、`DeskDock.tsx` |
| 13.6 | 测试补充（视图、容器、逻辑） | `backend/tests/test_desk_*.py` |

## 这一轮特别要注意的

1. **13.1 先复现。** 用复核报告附录 A 的 `lock409edit` / `lock409approve` 场景（或附录 B 的服务端渲染）在修复前确认：锁定方案下对话框的「取消」带 `disabled`。修完再确认不带。报告里贴前后输出。
2. **13.2 先复现。** 用附录 A 的 `xclose-auto` / `xclose-restore` 场景，修复前 `focusAfterClose` 是 body，修复后是头部开关。
3. **每条新用例都把对应实现改坏一次确认变红，再按原字节还原。** 13.3 必须把复核报告的 R5A、R5B、R5C、R4C 四个变异各做一次。
4. 不要顺手重构，`DeskDock.tsx` 只按 13.2、13.4、13.5 改。

## 验收

逐条执行规格第 7 节的 10 条命令并给出实际输出（全量仍用 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local` 前缀）。另外：

- `grep -c 'busy={busy || ' frontend/components/desk/DeskEpisodesView.tsx` 输出 0。
- `git diff main -- frontend/app/page.tsx` 与 R3 结束时逐字节相同。
- `git diff main -- frontend/components/studio frontend/components/novel frontend/lib/useRovingTabs.ts frontend/lib/useAccountIdentity.ts` 为空。

## 报告

在 `impl/主代理.md` 末尾追加「## R4」，然后回复五项：改了哪些文件；规格 13.1–13.6 各自怎么改的；逐项对应；每条命令的实际输出；没做完或需要人工确认的地方。四份文档里如有与本轮变化相关的描述，同步改对。
