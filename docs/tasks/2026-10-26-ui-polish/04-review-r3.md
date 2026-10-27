# R3 独立复核（2026-10-27，订阅 Opus 5.5 兜底；百炼欠费，千问复核不可用）

## 结论：通过，必须修复项：无

O1、O2 都按 `05-fix-r3.md` 落实。四份相关测试 37 个用例全部通过、0 跳过；新测试经 6 个变异实验全部会变红；白名单内只改了该改的地方。复核方只读工作树，变异实验在自己的临时副本里做，复核开始与结束时 6 个被审文件 sha256 一致。

## 对照基线

- `git diff 5985f43 -- . ':(exclude)README.md'` 的 sha256 与 04-review-r2 记录的 R2 复核结束值相同；`fix_r2_controls.py`、`composer_controls.py` 与 R3 前快照逐字节一致。
- 代码改动只有 `messageMarkdown.ts`、`VoiceButton.tsx`、`test_ui_polish_fix_r2.py`，另新增 `test_ui_polish_fix_r3.py`。

## O1 `stripMessageMarkdown`：落实

- 删掉了 `LITERAL_DOUBLE_STAR`、那条 `replace`、注释和末尾的 `split/join`，直接对 `parseMessageMarkdown(text)` 拼纯文本；各块拼法、列表编号、`\n\n` 连接不变；前端没有调用方。
- 实测：`"2**10**3"` → `"2103"`（与解析结果 text「2」、em「10」、text「3」一致）；`"x " + U+E000 + " y"` 逐码点原样返回；`` "2**10 和 `x`" `` → `"2**10 和 x"`；`"**重点**"` → `"重点"`；`"a ** b"` 原样。R3 前版本对照：前两项分别返回 `2**10**3` 与 `x ** y`，正是 O1 的两个问题。
- 旧 combined 输入 `"2**10 和 **重点**"` 现返回 `"210 和 重点**"`，按 T1 从左到右配对，旧期望本来不可能成立，换输入是对的。
- 字节扫描：4 个改动文件无 U+E000、无 Cf/Co/Zs/Cc 类不可见字符、无反斜杠 u 转义、无 BOM；全前端与 backend/tests 零命中。正控能抓到旧版的转义与合成文件里的 E000 / U+2060 / U+00A0。

## O2 VoiceButton：落实

- 新增 `CLICK_AFTER_POINTERUP_MS = 500`、`pointerUpAtRef`（初值 `Number.NEGATIVE_INFINITY`）；`handlePointerUp` 置标记后记 `performance.now()`；`handleClick` 无参数、保留 `if (pointerUpHandledRef.current) {`，两个标记都复位，只在时限内吞 click；未用 `event.detail`。
- 假事件实测（tap / start / end，R3 → R3 前）：

| 序列 | R3 | R3 前 |
|---|---|---|
| 短按 → up → lost → 立即 click | 1/0/0 | 相同 |
| 长按 → up → lost → 立即 click | 0/1/1 | 相同 |
| 长按 → up → lost → 600ms 后 click(0) | 1/1/1 | 0/1/1 |
| 长按 → up → lost → 600ms 后 click(1) | 1/1/1 | 0/1/1 |
| 短按 → up → lost → 600ms 后 click | 2/0/0 | 1/0/0 |
| 直接键盘 click / 键盘后紧跟读屏 click | 1/0/0、2/0/0 | 相同 |
| 录音中短按 + click / 录音中按住超 350ms | 1/0/0、1/0/0 | 相同 |
| pointercancel 路径（短 / 长） | 1/0/0、1/1/1 | 相同 |
| Firefox 顺序 up → click → lost，再 600ms 键盘 click | 2/0/0 | 相同 |
| 快速连按两次短按 | 2/0/0 | 相同 |

  只有该变的三行变了，无重复或漏触发。冻结时钟边界：0、1、499、500ms 被吞，501ms、10000ms 放行，与 `<=` 一致。
- `performance.now()` 只在事件处理函数里调用，不影响服务端渲染；`tsc --noEmit` 退出码 0，两个文件 eslint 0 问题。

## 新测试证明力（每次只改一处，跑 `test_ui_polish_fix_r3.py`，还原后 cmp 一致）

| 变异 | 结果 |
|---|---|
| M1 去掉时限判断 | 2 失败（运行时 + 源码断言） |
| M2 换回 U+E000 占位版 | 2 失败 |
| M3 占位换 U+E001 并改常量名，绕开源码断言 | 1 失败（运行时 `2**10**3` 抓到） |
| M4 `handlePointerUp` 不记时间 | 1 失败 |
| M5 先复位标记后读标记 | 1 失败 |
| M6 时限改 5000 | 2 失败 |

无 node 或无 node_modules 时：2 通过、2 跳过，源码断言照常执行。

## 白名单

`test_ui_polish_fix_r2.py` 只改了 `combined` 的输入、对应期望和紧挨着的一行注释；两份控件测试逐字节未变；`git diff -- backend` 为 0 行。

## 可优化项（不必修）

1. 时限按处理函数执行时刻计，不是事件时刻；`onTap` 的同步重渲染若超过 500ms，同一次指针操作带出的 click 会被当成新点击。更稳的做法是比较两个事件的 `event.timeStamp`，但需要 `handleClick` 带参数，与 R2 的源码断言冲突，留待规格层面再定。
2. `test_ui_polish_fix_r3.py` 的依赖探测没列 `lucide-react`；只装了部分依赖时会失败而不是跳过。
3. 03-report 的断言改动清单漏写了那行注释。
4. 长按松手后 500ms 内的键盘 / 读屏点击仍会被吞，这是返修单有意的设计。
5. 复核期间发现任务文档与 README 被改：由主会话所为（去掉本机路径与一句时区描述、README 同步新界面入口），不影响 R3 代码结论。
