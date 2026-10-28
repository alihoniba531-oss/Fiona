# 返修单 R1 补交：变异自检与报告

上一轮你在等后台全量 pytest 时，会话就结束了。现状：

- 返修单 `05-fix-r1.md` 第一节的 1–8 号改动都已落盘，Claude 已独立验证：
  - 门禁 v2 共 155 项，0 失败；
  - tsc 0 错误；lint 0 errors、25 warnings；build exit 0；
  - 全量 pytest 7826 passed、0 failed、0 skipped；
  - 新测试 52 条；
  - 52 条新测试在 HEAD 副本上全部失败，且都是 AssertionError。
- **没做完的有两件**：
  - 变异自检；
  - 03-report.md 的「返修 R1」一节。你写在 `/tmp/fiona-r1-section.md` 的草稿还留着 `__NEW_COUNT__`、`__FULL_PYTEST__`、`__MUTATION_TABLE__` 三个占位符，而且已经写了「全部变异均按预期变红」「ALL_RESTORED = True」这类还没发生的结论。

## 本轮只做这些

1. **所有命令都在前台跑完再继续**。不要用后台方式跑命令，不要 `sleep` 等待。
2. **不改任何源码和测试的最终内容**。只有做变异时可以临时改，改完必须还原。
   - 不要跑 `npm run build` / `npm run dev`，不要删 `frontend/.next`，不要起服务器、不用浏览器。
3. **变异自检**：按规格 §10 第 8 条，1–10 小项每项至少 1 个变异。每个变异的步骤：
   1. 按字节备份到仓库外的临时目录，记 sha256；
   2. 改；
   3. 前台跑对应的新测试文件；
   4. 记下哪条测试变红；
   5. 拷回备份，复核 sha256 一致。

   至少包括下面这些：
   - `page.tsx`：把 `if (e.repeat) return;` 挪回 `handleKeyDown` 第一行；
   - `page.tsx`：给「帮我画一张…」那个按钮加 `onKeyDown={handleKeyDown}`；
   - `NovelShelf.tsx`：去掉页眉行的 `min-h-10`；
   - `StudioShelf.tsx`：去掉页眉行的 `min-h-10`；
   - `history/page.tsx`：把 `dayFace` 改回 `(key && formatBeijingDateLong(beijingDayStart(key))) || "不限"`；
   - `history/page.tsx`：去掉「到」的 `max="9999-12-31"`；
   - `history/page.tsx`：把 `aria-label="从（开始日期）"` 改回 `aria-label="开始日期"`；
   - `match/page.tsx`：section 的 `pt-10` 改回 `mt-10`；
   - `ChatModelSection.tsx`：把隐私第一段包进 `{needsKey && …}`；
   - `ChatModelSection.tsx`：交换折叠里「Key 加密保存」与「自带模型文字聊天」两段的顺序；
   - `useAccountIdentity.ts`：交换 `identityRecoverySettled = true;` 与 `identityPendingListeners.forEach(...)` 两行；
   - `useAccountIdentity.ts`：把 `clientIdentityPending` 改成 `() => !getUsername()`；
   - `StudioWorkbench.tsx`：把「正在加载身份…」改成「正在打开项目…」；
   - `VoiceButton.tsx`：把气泡条件改成 `{(!showHint && holding) || dictating ? (…) : null}` 一类的写法，只要能让「听写且首次提示在场」时出现气泡即可。

   每个变异都必须真的让至少一条新测试变红。没有变红的，如实记为「存活」，并写明原因；不要改测试去凑结果。
4. **还原核对**：全部变异还原后，满足下面三条，任何一条不满足就停下来说明：
   - 前台跑 52 条新测试，必须全部通过；
   - `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` 的前 16 位必须是 `7c4aa5ca5c3c3510`（Claude 记录的 R1 快照）；
   - `git status --porcelain --untracked-files=all` 除 03-report.md 外与开始时相同。
5. **报告**：用实测结果替换草稿里的三个占位符，再把这一节追加到 `03-report.md` 末尾：
   - 新测试条数：52；
   - 全量 pytest：写「7826 passed、0 failed、0 skipped（Claude 门禁 v2 实测）」；你自己在前台跑过全量的，也一并写上；
   - 变异表：按第 3 步的实测逐行填写。

   删掉一切没有实测依据的结论。§8.5 的「8 处，分布在 7 行」与 Claude 实测一致，保留。

回复给出变更总结五项：修改了哪些文件、实现了哪些功能、与任务清单的逐项对应、测试结果、未完成或需人工确认的地方。
