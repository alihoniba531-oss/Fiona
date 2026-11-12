# 返修单 R3：案头第一期

R2 之后：机械门禁 50 项全过，全量 7997 通过、0 跳过，变异全部能被抓到。三个宽度的真实界面走查 100 项里有 2 项没过，都是确实的问题。规格已改成 v1.3：**请读 `docs/tasks/2026-11-10-desk-board/02-spec.md` 第 12 节**，它就是这一轮的完整要求。

硬规矩不变：只改白名单内的文件；`backend/` 下只许动 `tests/test_desk_*.py`；`frontend/app/page.tsx`、`lib/useRovingTabs.ts`、`lib/useAccountIdentity.ts` 和任何既有组件这一轮都不许改；不装依赖；不提交、不 stash、不切分支；任务目录下 `01`–`07` 开头的文件和 `design/` 不要改。由你自己直接改，不要调用 subagent / subagent_fork / workflow。

## 要修的两处

### 1. 竖排阶段标签的上下方向键（规格 12.1）

真实界面：焦点在「分集」标签上按 ↓，焦点不动；按 ↑ 也不动；Home / End 正常。原因是 `useRovingTabs` 只认左右键。

按规格 12.1：`lib/desk.ts` 新增 `deskStageByKey`；`DeskFrame` 两组标签改用它处理按键，按 `data-stage` 找目标按钮并移焦点；不再用 `useRovingTabs`。

### 2. 一张卡片只定位一次（规格 12.2）

真实界面：工作室卡片把案头定位到一本书的分集页 → 在「作品」下拉里手动换到另一本书 → 收起案头 → 再打开，又被拉回卡片指向的那本书。原因是 R2 在关闭时让定位的读作用域失效，而定位靠「上次请求是否仍有效」判断处理过没有。

按规格 12.2：用 `handledFocusNonceRef` 记录已经走完的 nonce，定位 effect 开头先判它。

## 测试（规格 12.3）

四个测试文件各补几条，清单见规格 12.3。两条要求：

- 竞态文件里新加的「定位一次」场景，**先在修复前跑一次确认是红的**，再修，再确认变绿。报告里贴修复前后的输出。
- 每条新用例都把对应实现改坏一次确认变红，再按原字节还原。

## 验收

逐条执行规格第 7 节的 10 条命令并给出实际输出（全量仍用 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local` 前缀）。另外：

- `grep -c 'useRovingTabs' frontend/components/desk/DeskFrame.tsx` 输出 0。
- `grep -c 'deskStageByKey(' frontend/components/desk/DeskFrame.tsx` 不小于 1。
- `git diff main -- frontend/app/page.tsx` 与 R2 结束时逐字节相同（这一轮没碰它）。
- `git diff main -- frontend/lib/useRovingTabs.ts` 为空。

## 报告

在 `impl/主代理.md` 末尾追加「## R3」，然后回复五项：改了哪些文件；两处各自怎么改的；与规格 12.1–12.3 的逐项对应；每条命令的实际输出；没做完或需要人工确认的地方。四份文档里如果写了方向键或定位的行为，同步改对。
