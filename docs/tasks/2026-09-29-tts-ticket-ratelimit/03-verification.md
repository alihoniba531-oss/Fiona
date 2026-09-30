# 第 0 轮机械验证（Claude 主会话独立复跑）

被测：worktree `claude/tts-ticket-ratelimit`（基线 `8c7f0cf`）上 Codex 第 0 轮的未提交改动。
Codex 自报结果未采信，以下全部由主会话重跑。

## 门禁

| 项 | 结果 |
|---|---|
| `git status --porcelain --untracked-files=all` | 只有白名单文件：`backend/rate_limit.py`、`backend/routers/voice.py`、`docs/ARCHITECTURE.md`、`frontend/app/page.tsx`，新建 `backend/tests/test_tts_ticket_rate_limit.py`、`frontend/lib/ttsTicket.ts`，以及本任务目录 |
| 新测试 | `14 passed` |
| 后端全量 | `1524 passed`（基线 1510 + 14） |
| 后端正控 | 把新测试放到基线代码上跑：「默认限额下真实使用序列全部放行」在第 21 张票处 `assert 429 == 200` 失败，即旧的 20 次/分钟/IP 确实会误伤；另外 3 条按设计失败（基线没有这些常量） |
| `npx tsc --noEmit` | 退出码 0 |
| `npx eslint` | `28 problems (0 errors, 28 warnings)`，与基线相同 |
| `next build`（仓库外副本，`FIONA_BACKEND_ORIGIN=http://127.0.0.1:8031`） | 退出码 0 |
| 真实库 | `backend/local-avatar.db` `172d800a…`、`backend/fiona.db` `403a086c…`（主仓库，前后未变） |

## 浏览器实测

环境：

- 生产构建 + `next start`：新版在 3031，基线 `8c7f0cf` 在 3032；
- 后端在 8031：`DEV_MODE=0`、临时库、假模型（8897，每条回复 5 句）、假 TTS（每句约 1 秒）；
- 无头 Chromium（headless shell）与 WebKit 2359；
- 场景 S1–S5 用 Playwright 拦截 `/api/tts/ticket`，按需返回 429。

| 场景 | Chromium | WebKit |
|---|---|---|
| S1 第 2 张票 429 + `Retry-After: 3` | 6 次请求 `[200,429,200,200,200,200]`；5 句按序读完；退避期内 0 次请求；提示倒计时 2→1，结束后消失 | 同左 |
| S2 首张票 429，仅 body `retry_after: 2` | 首音延后到约 2.4–3.0 秒；5 句按序读完；退避期内 0 次请求 | 同左 |
| S3 首张票 429，无头无 body | 等待 5.0–5.1 秒后重试；倒计时 5→1；5 句按序读完 | 同左 |
| S4 提示出现时点「不听了」（12 句的长回复仍在流式到达） | 点击后 0 次换票、0 次出声；提示消失；朗读开关仍开；下一条消息 5 句按序读完 | 同左 |
| S5 等待中发新消息 | 旧回复 0 次再出声；新回复首张票在退避结束后 0–180ms 发出（没有提前撞限流）；新回复 5 句按序读完；同一时刻最多 1 个元素在出声 | 同左 |
| S6 真实限流（后端用户次数限额临时调到 4/分钟，不拦截） | 第 5 张票收到真实 429，`Retry-After` 头与 body 均为 55，经 Next 代理后前端能读到；倒计时 54→1 逐秒递减；窗口重置后第 5 句读出，5 句全部读完 | 同左（56 秒） |
| S7 正控：S1 的注入在基线上跑 | 第 2 句被直接跳过（5 句只响 4 句）；无提示；退避期内还发了 2 次请求 | 同左 |
| S8 无 429 | 5/5 按序；首音 768ms（基线 681ms） | 5/5 按序；首音 374ms（基线 372ms） |
| 输入区截图（无提示） | 1280 与 390 宽，与基线逐字节相同 | 同左 |
| 提示截图 | `shots/` 下 4 张；390 宽下「不听了」按钮右边缘在 378px、高 36px，没有溢出 | 同左 |

## 发现的小问题

- `voice.py` 的 `[TTS限流]` 日志用 `print` 但没加 `flush=True`。
  - S6 两次真实 429 之后，后端日志文件里一直没有出现这一行；同一进程里带 `flush=True` 的 `[harness]` 行和 `[硬词检测]` 行则正常写出。
  - 生产环境 stdout 是管道时同样会被缓冲。
  - 仓库里热路径日志多数带 `flush=True`，例如 `chat_service`。

## 第 1 轮返修（复核可优化项 1）

- Codex 只把 `log_rejection` 的 `print(...)` 改为 `print(..., flush=True)`，返修前后 diff 对比只差这一行。
- 新测试 `14 passed`；全量 `1524 passed`。
- 真实进程验证：后端用户次数限额临时调为 1/分钟，stdout 重定向到文件。用 curl 登录后连换两张票：第 2 张返回 `429`、`retry-after: 60`，body 为 `{"detail":"朗读请求太频繁，请稍后再试","retry_after":60}`。日志文件 1 秒内出现 `[TTS限流] scope=user kind=count retry_after=60`，不含用户名和文本。
- 复核指出的验收脚本辅助判据假阳性（`sentence_order_ok`、S5 的 `old_text_requests_after_send`）：本文档的结论已按 `ended_texts` 与「发送后请求总数恰为 5」判定，不受影响。

---

## v2：在朗读自动播放修复（`61fc01f`）之上重接后的验证（2026-09-30）

被测：`61fc01f` + v1 的非页面文件原样恢复 + Codex v2 重接的 `page.tsx`（相对 `61fc01f` +40/−9）。

### 门禁

| 项 | 结果 |
|---|---|
| 工作区 | 相对暂存区只改了 `frontend/app/page.tsx` 与 `03-report.md`；`git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend frontend/lib docs/ARCHITECTURE.md` 为空 |
| 后端全量 | `1524 passed` |
| `npx tsc --noEmit` | 0 |
| `npx eslint` | 0 errors / 26 warnings（与 `61fc01f` 相同） |
| `next build`（仓库外副本） | 0 |
| grep | `tts/ticket` 只在 `ttsTicket.ts:76`；`stopTtsForReply` 0 处；`role="status"` 7 处（与 `61fc01f` 相同，限速提示放进已有的常驻状态容器） |

### 浏览器实测

环境：

- v2 前端在 3031；新基线 `61fc01f` 前端在 3032；
- 后端 8031：临时库、假模型、假 TTS；
- 两个引擎都跑。

| 场景 | Chromium | WebKit |
|---|---|---|
| 正控（`61fc01f` 上跑 S1/S9） | 第 2 句被跳过，4/5，无限速提示，退避期内 2 次请求 | —— |
| S1 / S2 / S3 | 5/5 按序；退避期 0 请求；倒计时 `[2,1]` / `[2,1]` / `[5,4,3,2,1]` | 同左（S1 倒计时 `[1]`，因首句结束时退避只剩不到 1 秒） |
| S4「不听了」 | 0 次换票、0 次出声、提示消失、朗读开关仍开；下一条 5/5 | 同左 |
| S5 等待中发新消息 | 旧回复 0 次出声；新回复首请求在退避结束后 143ms；5/5 | 同左（1ms） |
| S6 真实限流（用户次数限额临时 4/分钟） | 第 5 张票真实 429，`Retry-After` 头与 body 均为 56；倒计时 55→1；5/5 | 同左（57） |
| S8 无 429 | 5/5，无提示 | 同左 |
| **S9 限速 + 被拦** | 限速提示出现 → 等到后第 2 句首次 play 被模拟拦下 → 限速提示消失、「浏览器拦下了自动朗读」出现 → 点「点此播放」后 4 句续读，5/5 按序；最多 1 个元素出声 | 同左 |
| 朗读自动播放 A0/A/B/C/D/F | 全部与其原验收一致：A0 句间空档 51–53ms；B 提示 1ms 内出现、被拒期间 0 句结束、点击后 5 句；C 点击后 0 次出声；D 旧回复 0 次再出声；F 关朗读后 0 次出声（停止延迟 560ms，其原记录 562ms）；audio 元素始终 2 个 | A0 空档 1–2ms、首音 351ms；B/C/D 同左；F 停止延迟 41ms |
| 输入区截图（无提示） | 1280 与 390 宽，与 `61fc01f` 逐字节相同 | 同左 |
| 提示截图 | `shots/` 已换成 v2 截图；390 宽「不听了」按钮右边缘 378px、高 36px | 同左 |
| 限流日志 | `[TTS限流] scope=user kind=count retry_after=56` 即时写出 | —— |

---

## v3：复核可选项返修后的验证（2026-09-30）

本轮返修 F1（预取票超龄重换）、F2（补两条后端测试）、F3（§1.3 勘误）。Codex 用 `gpt-6.1-sol` 执行。

### 门禁

| 项 | 结果 |
|---|---|
| 改动范围 | 相对 v2 暂存区只改了 `page.tsx`（+16/−2）、测试文件（追加 94 行）、`02-spec.md`（§1.3 追加勘误段）、`03-report.md`；`rate_limit.py`、`voice.py`、`ttsTicket.ts`、`ARCHITECTURE.md` 与 v1 逐字节相同 |
| 新测试文件 | `19 passed`（14 + 5） |
| 变异正控 | 用临时 pytest 插件把 `voice.check_and_hit` 换成「逐项 test、通过就立刻 hit」的错误写法，没有改仓库：新增的两条 F2a 测试失败，其余 17 条通过 |
| 后端全量 | `1529 passed` |
| tsc / ESLint / 构建 | 0 / 0 errors 26 warnings / 0 |

### 浏览器实测

v3 前端在 3031，产物里有 45 秒阈值常量，不是旧构建。

| 场景 | v2（修前） | v3（修后） |
|---|---|---|
| S10 当前句限流等约 60 秒、预取句已先拿到票 | Chromium：第 2 句票龄约 69 秒，播放时触发 `error` 被跳过，结束顺序 [1,3,4,5]；WebKit 未复现 | Chromium 与 WebKit 都是 5/5 按序、0 次 `error`；旧票被放弃，第 2 句在轮到时（第 68–70 秒）重新换票；等待期间限速提示倒计时正常 |
| S1–S5、S8、S9 | —— | 两个引擎全部与 v2 一致（5/5 按序，退避期 0 请求，S9 限速提示与被拦提示依次互斥出现） |
| 朗读自动播放 A0/A/B/C/D/F | —— | 两个引擎全部与其原验收一致（Chromium A0 空档 54–55ms，F 停止延迟 594ms；WebKit 空档 1–2ms，F 43ms；audio 元素始终 2 个） |
| 输入区截图（无提示） | —— | 1280 与 390 宽，与 `61fc01f` 逐字节相同 |
