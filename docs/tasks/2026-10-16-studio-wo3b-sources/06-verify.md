# WO3b 主控验证记录（R1 返修后）

## 机械验证（沙箱外执行）
| 环境 | 结果 |
|---|---|
| 临时合并副本（WO3b + R1 合入 origin/main 37ff96b），不带 `frontend/node_modules`，等同 CI | 6587 passed，104 skipped，0 failed；skip 全部是「frontend dependencies unavailable」 |
| 同一副本，带 `frontend/node_modules` | 6691 passed，0 failed，0 skipped |
| 前端（工作室分支） | lint 0 个错误（25 条警告，与基线相同）；tsc 通过；默认 Turbopack build 通过 |

## 合并 main 的冲突
只有 `backend/services/chat_service.py` 顶部一行 import 冲突：WO3b 加了 `from intent_router import NOVEL_INTENTS, …`，main 把 `from llm import …` 扩成含 `CHAT_VISION_*` 的版本。解决方式：两行都保留。R1 前后两次试合并，解决结果逐字节一致。

## 界面实测（隔离临时库 + 自写示例书，截图见 screens/01–12）
- 新建项目 → 小说工坊书单：合格 / 写作中 / 有待复核三种状态，flags 中文说明，改编短剧标签。
- 「①拆解」作品来源面板：快照摘要；模拟改第 3 章、新增第 4 章后改动检测准确；确认同步后升为快照第 2 版，`snap-0001` 目录保留。
- 小说页页头和完结横幅都有「做成片」；已有项目时可「打开」或「再建一个」；不合格的书显示原因并禁用提交；390px 宽度无横向溢出。
- R1 后：选中整卡高亮；从作品建的项目落在「①拆解」；「打开」为主按钮。

## 留给作者定的观感问题
同一本书有多个项目时，每个「打开」都是深色主按钮（见 screens/12），同名项目只靠快照版本号区分。可选做法：只把最近一个设为主按钮，并在项目名后显示建立日期。

## 复核
- 第 1 轮（04-review.md）：通过；必须修复 1 项（阻塞 I/O）。
- 第 2 轮（04-review-r2.md）：通过；必须修复项已落实，无回归；新发现 3 条，均为低严重度可优化项。
