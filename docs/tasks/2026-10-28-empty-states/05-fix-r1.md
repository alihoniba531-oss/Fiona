# 返修单 R1：空态与文案（第三批）

你上一轮按规格 v1.1 交付的实现，经独立复核与 Claude 的真实浏览器实测，需要返修。规格已更新为 v1.2：`docs/tasks/2026-10-28-empty-states/02-spec.md`，修订点集中在文末 §10，T2、T3-3、T4-3、T6-2、T7、T9、§5、§6 第 7 条里也有原位修改。**先通读 §10，再按本单动手**；本单与规格冲突时，以规格 v1.2 为准，并停下来说明。

## 一、要改的地方

| # | 文件 | 改法（逐字见规格 v1.2 对应条目） |
|---|---|---|
| 1 | `frontend/app/page.tsx` | `handleKeyDown`：去掉函数体第一行的 `if (e.repeat) return;`，改为插在 `e.preventDefault();` 与 `handleSend();` 之间。改完的 8 行见 T3-3。page.tsx 其余一字不动。 |
| 2 | `frontend/components/novel/NovelShelf.tsx` | 页眉行 `<div className="flex flex-wrap items-center justify-between gap-3">` 改为 `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">`（T2-2）。 |
| 3 | `frontend/components/studio/StudioShelf.tsx` | 同上，页眉行加 `min-h-10`（T2-1）。 |
| 4 | `frontend/app/history/page.tsx` | 三处：<br>① `dayFace` 改为 `const dayFace = (key: string) => (key ? formatBeijingDateLong(beijingDayStart(key)) || key : "不限");`；<br>② 「从」`aria-label="从（开始日期）"`、`max={dateTo \|\| "9999-12-31"}`；<br>③ 「到」`aria-label="到（结束日期）"`、`min={dateFrom \|\| undefined} max="9999-12-31"`（T7-2、T7-3）。 |
| 5 | `frontend/app/match/page.tsx` | `<section data-match-empty …>` 的 className 换成 T4-3（v1.2）给出的整串：`mt-10` 去掉、加 `pt-10`；`mobile:mt-2` 换成 `mobile:pt-2`。 |
| 6 | `frontend/components/ChatModelSection.tsx` | Claude 提示句改为 `已选 Claude：你在聊天里发的图片和工具结果也会发送给 Anthropic，详见下方「更多隐私与计费说明」。`（T6-2），该行其余不动。 |
| 7 | `frontend/lib/useAccountIdentity.ts` | 只把新代码第一行注释换成 T1-1 代码块里的两行注释；代码一字不动。 |
| 8 | `backend/tests/test_empty_states_*.py`（9 个） | 按规格 §10 第 8 条加固；与上面第 1–7 条对应的断言同步更新。 |
| 9 | `docs/tasks/2026-10-28-empty-states/03-report.md` | 见第三节。 |

## 二、规矩（延续 v1.1，另加几条）

- 白名单：只改上表 9 类文件。其余任何文件不得改动，尤其是：
  - `docs/tasks/2026-10-28-empty-states/` 下除 `03-report.md` 以外的文件；`verify/` 里是 Claude 的验收脚本。
  - 03-report.md 里 Claude 已补的两处（§4 第 4 条、git 历史测试那一条），以及所有既有测试。
- 既有测试一字不改；`test_ui_polish_settings_drawers.py:83` 那一处已授权的改动保持现状。
- 不做任何 git 写操作（commit、checkout、stash、reset、restore）。做变异时，先按字节备份到仓库外的临时目录，改完拷回并校验 sha256。
- **用工作流并行（workflow 工具）**：在脚本里用 `parallel()` 同时运行下面 9 个 agent，按文件不重叠拆分。
  - 每个 agent 的任务说明自包含：写明它负责的文件、要改什么、规格 v1.2 的哪几条，并写明「不得调用 subagent / subagent_fork / workflow」。
  - 拆分如下：

    | agent | 负责的文件 |
    |---|---|
    | A | `useAccountIdentity.ts`（只改注释）+ `test_empty_states_identity.py` |
    | B | `NovelShelf.tsx` + `test_empty_states_novel.py` |
    | C | `StudioShelf.tsx` + `test_empty_states_studio.py` |
    | D | `test_empty_states_agents.py` |
    | E | `page.tsx` + `test_empty_states_chat_openers.py` |
    | F | `match/page.tsx` + `test_empty_states_match_profile.py` |
    | G | `ChatModelSection.tsx` + `test_empty_states_settings_privacy.py` |
    | H | `history/page.tsx` + `test_empty_states_history_dates.py` |
    | I | `test_empty_states_voice_hint.py` |

  - 主代理只做拆分、派发、汇总、白名单检查、跑门禁、写报告。agent 失败时先读它的结果再决定，不许盲目重派。
- 何时停下来问：只有影响「实现什么」的问题才停，例如规格 v1.2 自相矛盾、按规格做会让既有测试变红、某条做不到。只影响「怎么实现、怎么验证」的问题，自己定并在报告里写明理由。任何情况下不回滚已完成的工作。**你实测到的事实优先于规格和本单的断言**，不符就停下来说明。
- 测试仍须离线、不依赖 git 历史、不读仓库外文件；跑 pytest 前照旧清掉代理变量。

## 三、交付

在 `03-report.md` 末尾追加一节「返修 R1」，写这几项：

1. 逐项对应：本单第一节 1–9 号、规格 §10 第 8 条的 1–10 小项，各改了什么。
2. 拆分表：派出过的全部 agent，以及各自负责的文件。
3. 结果：
   - `npx tsc --noEmit`、`npm run lint`（errors / warnings 数）、`npm run build`；
   - 全量 `pytest`（passed / failed / skipped 三个数）；
   - 新测试条数。
4. 变异自检：每个加固项至少一个变异、哪条测试变红、还原后的 sha256 校验结果。
5. 报告原文的两处精度修正：
   - §4-3 的「18 个路由」改为实际路由数；
   - §4-5 的「7 行」改为「7 处，分布在 6 行」，或按你实测的写。
6. 已知局限：补上规格 §10 末尾的三条，原有的几条保留。
7. 未完成或需人工确认的地方。

回复里给变更总结五项：修改了哪些文件、实现了哪些功能、与任务清单的逐项对应、测试结果、未完成或需人工确认的地方。
