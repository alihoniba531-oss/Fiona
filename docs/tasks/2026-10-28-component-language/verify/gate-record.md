# 门禁记录（Claude，2026-10-28）

- 候选：工作树 `feat/component-language`，基线 `6410890`。执行者 dsh 作业 `cx-20261028-121353-76fcbd`（DeepSeek Flash，max，17 分钟）；R1 返修 `cx-20261028-123524-336d5c`（续原会话）。
- 依赖：next 16.4.3（与锁文件一致，`gate.sh` 首项核对）。
- 命令类判据：`gate.sh` 54 项全过（原生弹窗 0、12 段正文各 1 次、`useConfirm()`/`useNotice()` 各文件到位、`<ConfirmProvider>`、`font-semibold` 0、ChatBubble 死状态与图标 0、`setVoiceOn` 仍 5、`aria-label=` ≥118、中点 8 处、ChatCard 块逐字未动、白名单、tsc / lint 0 错 25 警告 / build / pytest 定向全绿 0 skipped、`test_novel_p2_frontend` 的 `confirm(` 用例仍绿）。
- 首轮门禁唯一 FAIL 是门禁脚本自身的计数写错（两个标签分两行，应为 2），已更正。
- R1：首轮实现为了让 `test_novel_p2_r1.py` 的精简 React（无 `createContext`）能渲染 `NovelWorkbench`，在确认框里加了「无 Context 兼容分支」并把 `useContext` 改名引入以避开 hooks 规则检查。返修改为模块级 `host` + Provider 注册，`useConfirm()`/`useNotice()` 返回稳定的模块函数，Provider 未挂载时调用会 reject `ConfirmProvider missing`；既有测试未改。

## 真实浏览器实测（`measure.py`，Playwright 1.63.0 无头 Chromium；HEAD 3097 / 候选 3098，共用隔离后端 8097）

HEAD 是正控：以下四项在 HEAD 上必须失败，候选必须通过。

| 项 | HEAD | 候选（R1 后） |
|---|---|---|
| 原生弹窗次数（删除对话→取消、上传非图片、设置页清空→取消） | 3 | 0（三处都弹出瓷片确认框 / 提示框） |
| 加载样例对话后带滑入动画的消息数 | 9 | 0；发一条后只有末尾 2 条（新用户消息与回复占位）带动画 |
| 1440 下 Tab 30 步，非文本框焦点不是 1px 实线的数量 | 20 / 28（浏览器默认 `auto`） | 0 / 30 |
| 7 个页面 + 打开历史抽屉的粗体（≥600）元素数 | 4（历史抽屉「当前对话记录」与日期） | 0 |

候选另外通过（昼夜 × 1440 / 390 四轮一致）：

- 消息行：4 条分身消息各有可见「朗读」，10 条消息各有可见「复制」「删除」（未悬停）；元信息行无 `svg`；手机按钮高 40px。
- 朗读：点击后出现 1 个「停止」、发出 1 次换票请求；点「停止」后 0 个；全局「朗读」开关 `aria-pressed` 前后都是 `false`。
- 复制：Markdown 那条复制后出现「已复制」，剪贴板内容无 `**`、无 `## `、无 `- ` 开头的行。
- 删除：弹出 `.confirm-dialog[open]`（`role=alertdialog`），正文「删除这条消息？此操作不可恢复。」，焦点在「取消」；Esc 关闭、消息仍在、0 次 DELETE；再点确认后消息少 1 条、1 次 DELETE。
- 确认框昼 / 夜截图见 `results/`：瓷片底、朱字危险操作、无粗体。

## 结论

门禁通过，进入独立复核（千问 3.8 Max，xhigh）。

## 补测：确认框打开时的粗体扫描（复核 O4 指出的证据缺口）

千问复核发现 `results/cand-measure.json` 缺 `boldWithDialog` 键：落盘 JSON 是在 `measure.py` 加入这段之前产出的。用 `bold_dialog.py` 单独补测（候选 3098，只按 Esc 取消，不删除）：

| 运行 | 确认框 | 粗体（框打开时整页） | 正控：给框内正文临时加 700 | Esc 后 | 原生弹窗 |
|---|---|---|---|---|---|
| 昼 1440 | 打开，alertdialog | 0 | 抓到 1 处（P，700） | 已关 | 0 |
| 夜 390 | 打开，alertdialog | 0 | 抓到 1 处（P，700） | 已关 | 0 |

数据：`results/cand-bold-dialog.json`。

## 复核可优化项的裁定（Claude）

- O2「`mkTtsAudio` 返回空时不复位朗读按钮」不成立：它只在两个音频槽都被占用时返回空（`page.tsx:1192-1193`），是等空槽、不是失败；票据或播放失败走 `ready=false → finishCurrentTts`，队列播空时复位。此处复位反而会与实际播放状态不符。
- O4 已由上面的补测补齐。
- O1、O3、O5、O6、O7 不阻塞合并，留给后续批次。
