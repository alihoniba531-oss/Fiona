# 独立复核（第 2 轮，窄范围）：短片工作室「边写边拆」R1 返修

- 复核对象：基线 `135253f` + R1 交回后的全部未提交改动。开始和结束时，`git diff` 都与 `scratchpad/review-serial-materials/diff-r1.patch` 逐字节一致（`git diff | cmp - diff-r1.patch`）。未跟踪的三个新测试文件和报告直接读副本里的文件。
- 依据：`02-spec.md` v1.2 §4.8，以及 `04-review.md` §3 的复现方法和期望改法。实现方报告 `impl/report-r1.md` 只当线索，下面的结论都来自我自己跑的命令、差分和变异实验。
- 复核方式：只有我一个人做，没有调用 subagent / subagent_fork / workflow。实验用的临时探针、变异和构建产物都已还原或删除，见 §8。
- 本轮只核验派单里的 5 项范围。范围外新发现的问题，一律放在 §6 可优化项。

## 1. 结论：不通过（唯一原因：R1-P7 没有把细节迁到 ARCHITECTURE）

- **MF1–MF5 全部修好。**
  - MF1–MF4：用上一轮的变异 B26、B14、B2/B4、B20/B21 重跑新测试，全部变红，每条都由派单指定的那条用例杀死（§2）。
  - 上一轮的 74 个变异整表重跑：r0 时杀死的仍全部杀死；r0 存活的 8 个里，非等价的 7 个（B2、B4、B14、B20、B21、B26、P5）和前端 F14 现在都变红。剩下 5 个存活，和 r0 判定一样，都是等价或接近等价的变异：B3、B8、B9、B34、P4（§7.4）。
  - 结论：r0 已有的断言没有被放宽。
- **R1-P1 到 P6 正确，而且只改了这些。** 实现文件从 r0 到 R1 的差分，只有 §4.8 列出的几处（§3）。
- **R1 白名单、§5 第 1–7 条、R1 验收全部通过**（§4）：
  - 后端全量 `8352 passed`，即 8264 + 88，0 skipped；
  - `tsc`、`lint`、`build` 都是 0；
  - 在没有 `node_modules` 的副本里跑三个新文件，SKIPPED 22 个，等于前端新文件里起 node 的用例数；
  - R1 白名单外的文件与 r0 交回时逐字节相同。
- **R1-P7 只完成了一部分。**
  - 做到的：
    - `CLAUDE.md` 是 67,350 字节，没有超过 67,400；
    - 六项要点齐全；
    - 基线已有的事实都还能在 `CLAUDE.md` 或 `ARCHITECTURE.md` 里找到。
  - 没做到的：r0 在 `CLAUDE.md` 续拆段里写的 4 条细节，压缩时被删掉了，却没有迁到 `docs/ARCHITECTURE.md` 的续拆段落。现在 `CLAUDE.md` 和 `ARCHITECTURE.md` 里都找不到这 4 条，只在 `README.md` / `PLAN.md` 里还有。这不符合 §4.8 R1-P7「细节移到 `docs/ARCHITECTURE.md` 的续拆段落」的要求，也过不了派单要求的「逐段对照基线与 ARCHITECTURE」核验（§3 R1-P7、§5 MF-R2-1）。
  - 实现方报告第 60 行说「细节保留在 `docs/ARCHITECTURE.md:507/509`」，第 312 行说「六项续拆要点与其它事实均保留」，与事实不符。
  - 修复只需在 `docs/ARCHITECTURE.md:507` 补一句话：不改代码、不改测试，也不改 `CLAUDE.md`，所以不影响 67,400 字节上限。
  - 如果派单方认为 README/PLAN 里还有这些事实就够了，这一项可以降为可优化项，其余各项全部通过。

## 2. MF1–MF5 逐条核验

变异做法：用 `/tmp/r2-mat/mutate2.py`，每次只改一处（锚点必须恰好出现一次），跑指定用例，记录结果，然后按原字节写回，并核对 sha256。

| MF | 复核期望改法 | 现状（`test_studio_serial_continue.py`） | 变异 → 结果 |
|---|---|---|---|
| MF1 | 快照 2 对第 3 章的改动落在旧 range 以内；保留「读回快照 1 原文」和「refresh 后旧单元不变」两条断言 | `prefixed_body()` = `'改过的开头。' + changed_body()`，`changed_body` 本身没动，其他用例语义不变。`:684–711` 两条断言都保留，另加了 `'改过的开头。' not in text`、`snapshot_no == 2`、单元数增加 | **B26**（`_source_inputs` 只用 `breakdown['snapshot_no']`）→ 只跑该用例 `1 failed`，断言差异是读到了快照 2 的文本；整文件 `1 failed, 17 passed`（`-x`） |
| MF2 | 同步到第 16 章，只让第 16 章补全批失败，第一段分集批成功、拆解为 partial：revision 和集数不变、`appended_from is None`；重跑后 revision 只加 1、新集齐全 | 新增 `test_continuation_two_segment_partial_publishes_once_after_retry`（`:1044`）：断言本轮四批状态是 succeeded / failed / succeeded / blocked；partial 时 `plan_revision == 1`、2 集、`appended_from is None`；重跑后 `plan_revision == 2`、6 集、`appended_from == 3`、单元区间逐集核对、`_assert_marking`。原来的单段用例保留 | **B14**（续拆 partial 也发布）→ `1 failed`，`assert (2 == 1)`，位置 `:1062` |
| MF3 | 两条重名行之一是第 0 轮自动条目（uuid5）并且已定妆 approved；书斋登记 C2；确认后和 drain 后各断言一次 | `test_continuity_duplicate_active_names_warn_and_insert`（`:896`）：第 0 轮输出「船夫」，断言 `uuid.UUID(id).version == 5`，把它的 `studio_items` 设为 approved；另一条是 `create_bible` 手建的；快照 2 登记 `C2`。确认后和 drain 后都断言：`merged_into is None`、`casting.is_orphaned` 为假、定妆仍是 approved、新行的 `ref_id == 'C2'`、重名 warning 照常出现 | **B2**（退役循环去掉冻结跳过）→ `1 failed`；**B4**（两种跳过都去掉）→ `1 failed`。两者都失败在 `:916`：自动条目被合并，不在活动行里 |
| MF4 | 过期 409、额度不足 409、未结束批次 409，每条都不改动计数；成功后报价 confirmed | 新增三条：`test_continue_start_rejects_expired_quote` / `_exhausted_budget` / `_unfinished_batches`（`:560/576/592`）。每条断言 409 文案，`counts_of` 前后一致（批数、job 数、预留总额），报价仍为 `open`。成功用例 `:630` 断言 `status == 'confirmed'` | **B20**（`_confirmed_quote` 换成 `payload = preview`）→ 过期用例 `DID NOT RAISE`，额度用例 `DID NOT RAISE`，成功用例 `- confirmed + open`；**B21**（确认时不查未结束批次）→ 未结束批次用例 `DID NOT RAISE` |
| MF5 | `impl/report.md` 补「文档改动位置」表，逐处写文件:行号，并注明 ARCH:505 不改的理由 | `report.md:125–149` 新增 17 行表，覆盖复核要求的全部位置：CLAUDE 186/188/192/194/196，README 359/361/363/369/394/396，ARCH 412/416/418/507/509，PLAN:525；`:149` 注明 ARCH:505 不改的理由。我逐行核对了行号（`sed -n`）以及 `git diff -U0` 的 hunk，全部正确（README 与 PLAN 的 hunk 和 r0 相同） | 不适用。表里第 194 行「压缩为六项要点」属实，但见 §3 R1-P7 |

## 3. R1-P1 到 P7 逐条核验

r0 版本的取得方法：对 7 个文件，用 `git show 135253f:<f>` 取基线，再打上 `diff-r0.patch` 里对应文件的片段，得到 r0 版本。结果和实现方留下的 `/tmp/studio-serial-r0` 逐字节一致。用它和当前文件做 `diff -u`，实现文件只有下面这些改动。

| 条目 | 核验 | 结论 |
|---|---|---|
| **P1 同步守卫** | `sources.py:469` 新增 `_continuation_in_progress`。它按 `project['breakdown_id']` 查 `studio_breakdowns WHERE id=? AND owner=?`，只有 status 是 running 或 partial、并且 `import_json._continuations` 非空时才返回真；`import_json` 解析失败时返回假。<br>调用位置：`sync_source:635` 在事务外、紧跟「导演模型任务进行中」检查之后；`_save_snapshot:503` 在 `BEGIN IMMEDIATE` 内、紧跟同一检查之后。文案都是「续拆进行中，完成后再同步」。<br>两处的 `project` 都是 `store._project(db, pid, owner)` 按 owner 读的。`import_json` 在 `store._row` 里不会被解码，是字符串，所以 `json.loads` 的用法是对的。<br>建项目时 `_create_with_snapshot` 也会调 `_save_snapshot`，这时没有 `breakdown_id`，直接返回假。<br>探针结果：<br>• 未续拆的拆解 partial、组里没有在途 job 时，同步照常（`P1_NONCONTINUED_PARTIAL_SYNC_OK 1 2`）；<br>• 续拆完成（done）后同步照常（`P1_DONE_CONTINUED_SYNC_OK 3`）；<br>• 续拆 running 时，按规格的顺序先命中原有检查，返回「导演模型任务进行中…」；<br>• 绕过事务外检查、直接调 `_save_snapshot`，写事务内的检查也拦住了（`P1_INNER 409 续拆进行中，完成后再同步`），快照号不变 | 正确 |
| **P2 降级** | `breakdown.py:961–991`：<br>• `warnings` 先由原有两类 warning 组成，然后 `try` 读 manifest，捕获 `(HTTPException, OSError, ValueError)`，在末尾 `append` 规格原文；<br>• `changed_covered` 的条件从 `snapshot is not None` 改成 `manifest is not None`，所以读失败时为 `[]`；<br>• `continuable` 新增 `manifest is not None`，`continue_from/to` 随之为 None；<br>• `stale_chapters` 仍从 `_chapter_basis` 计算，没有变。<br>`_read_manifest` 只会抛 `HTTPException(500)`，它内部已经把 OSError、ValueError、TypeError 转换掉了。<br>探针：拆解原本可续拆（`continuable True`、`changed_covered [3]`、`stale [2]`），改坏当前快照的 sha 后，`continuable False`、`None/None`、`[]`、`stale [2]`，warning 是最后一条，前面的 warning 和改坏前一样。<br>返回路径：`retry` 确认成功后返回的视图正常带 warning（`P2_RETRY running 当前快照无法读取…`）；`cancel` 由 R1-T9 覆盖；`continue_start` 的返回路径是同一个 `get_current` | 正确 |
| **P3 过滤条件** | `breakdown_plan.py:166` 和 `:683`，条件都改成「已发布拆解的 `imported._continuations` 非空」。`get_episodes` 返回的 `continuing` 仍按 `_continuing` 计算。<br>续拆发布时，`refresh:905–906` 在发布的同一事务里把 `_published_max_seq` 设成 `MAX(seq)`。探针（续拆发布后）：`_published_max_seq == max(seq) == 16`，视图单元和库里单元逐个相同（`P3_AFTER_PUBLISH 16 16 16 16`），过滤不改变结果。<br>续拆 partial 后整本重拆的情形由 R1-T10 覆盖：视图和导出的「未纳入」都不含第 11–16 个单元 | 正确 |
| **P4 读回完整行** | `breakdown.py:662`：`row_by_id[identifier] = await _one(db, 'SELECT * FROM studio_bible WHERE id=?', (identifier,))`，用的是同一个连接、同一个事务。后面用到的 `aliases_json` 等键在完整行里都有 | 正确（防御性改动，到不了的分支，变异存活属于预期，见 §7.2） |
| **P5 按钮层级** | `BreakdownPanel.tsx:65` 只改了 className：`breakdown?.continuable ? "btn btn-quiet min-h-10" : "btn btn-primary min-h-10"`。disabled、onClick、文案都不变 | 正确 |
| **P6 表格标签** | `EpisodePlan.tsx:57` 的 `addedTag` 多收一个类名参数，类型限定为 `"tag" \| "tag ml-2"`。表格视图（`:76`）传 `"tag ml-2"`，卡片视图（`:77`）传 `"tag"`，卡片视图的输出和 r0 相同 | 正确 |
| **P7 `CLAUDE.md` 体积** | 体积：`wc -c` = 67,350（基线 66,525，r0 69,419），没有超过 67,400。<br>要点：现在的 `CLAUDE.md:194` 包含适用条件、两个接口、同一份拆解追加且总表、定妆、声线保留、发布后重新批准、进行中不能取消也不能同步、次要来源不支持，六项齐全。<br>基线事实：逐段对照，186/188/192/196 被删的内容都能在 ARCH 里找到：`_rearchive` 和 0–300 范围在 ARCH:412，「按需检测」在 ARCH:416，续拆视图字段、`appended_from/continuing`、「重新拆解」入口在 ARCH:509，`auth_method` 为 None 不放行在 ARCH:418。<br>**缺口**：r0 续拆段里有 4 条细节，现在 `CLAUDE.md` 和 `ARCHITECTURE.md` 里都没有（`grep` 和逐句核对）：<br>① 续拆的每集时长沿用原拆解，而且**不能改**（只在 PLAN:529；README:394 只写了「沿用」）；<br>② 续拆进行中新人物会立即出现在定妆页，**G1 回到未通过**（只在 PLAN:529、535）；<br>③ 单批重跑**读本轮绑定的快照**，在书斋改原文对重跑无效（只在 README:396、PLAN:529、535）；<br>④ 仍失败只能整本重新拆解，会生成新总表，已定的妆要重新定（只在 README:396、PLAN:535）。<br>另外两条是隐含的：「同一报价只能确认一次」由 CLAUDE:204 的通用规则覆盖；「已发布的集和作者改过的内容保留」由 ARCH:507「把旧集加本轮新集发布」隐含。 | **部分未完成 → MF-R2-1** |

ARCH:507 新增的同步说明（事务外和写事务内各查一处、两条文案）与代码一致。

## 4. §5 与 R1 验收逐条结果

| 项 | 结果 | 命令与关键输出 |
|---|---|---|
| §5.1 | 通过 | `cd frontend && npx tsc --noEmit` → `TSC_EXIT:0` |
| §5.2 | 通过 | `npm run lint` → `✖ 25 problems (0 errors, 25 warnings)`、`LINT_EXIT:0`。告警只在 `app/page.tsx`（24 条）和 `app/plaza/page.tsx`（1 条），本次改动的文件没有告警 |
| §5.3 | 通过 | `npm run build` → `BUILD_EXIT:0`，日志里只有 Node 的 `DEP0205` 弃用提示 |
| §5.4 | 通过 | `cd backend && NO_PROXY=… no_proxy=… .venv/bin/python -m pytest -q -p no:cacheprovider -rs` → `8352 passed, 37 warnings in 442.84s (0:07:22)`、`EXIT:0`，日志里 `SKIPPED` 0 行。<br>`--collect-only`：三个新文件分别是 `23` / `43` / `22`，共 88；8352 = 8264 + 88，所以既有文件的收集数没变 |
| §5.5 | 通过 | 用 `rsync` 做了一份不含 `frontend/node_modules`、`.next`、`tsbuildinfo` 的副本，只跑三个新文件 → `66 passed, 22 skipped`，`SKIPPED [22] tests/test_studio_sources_frontend.py:21: frontend dependencies unavailable: typescript, react, react/jsx-runtime, react-dom/server`，`EXIT:0`。<br>`test_studio_serial_frontend.py` 有 22 个 `def test_`，每个都调用 node 驱动，数目对得上。副本已删除 |
| §5.6 | 通过 | `git status --porcelain --untracked-files=all` 开始和结束时一致（40 行）。和 r0 复核开始时相比，只多了派单方的 `04-review.md`、`05-fix-r1.md` 以及实现方的 `impl/report-r1.md`。既有测试没有 R1 改动，见下一行 |
| §5.7 | 通过 | 两条 AST 只读锁用例 → `2 passed`、`EXIT:0` |
| R1 白名单 | 通过 | 把 `diff-r0.patch` 和 `diff-r1.patch` 按文件切开后逐个比较：30 个已跟踪文件里，**有差异的只有 7 个**，`CLAUDE.md`、`docs/ARCHITECTURE.md`、`backend/studio/{sources,breakdown,breakdown_plan}.py`、`frontend/components/studio/{BreakdownPanel,EpisodePlan}.tsx`，全部在 R1 白名单内；其余 23 个逐字节相同，包括 5 个既有测试、README、PLAN 和其他前端文件。<br>未跟踪文件：`test_studio_serial_sources.py` 的 sha1 仍是 r0 的 `068496cc…`；continue 和 frontend 两个测试文件有改动，在白名单内；`impl/report.md` 只在 `:125–150` 新增 §2.1；`impl/report-r1.md` 是新文件。`01-brief.md`、`03-dispatch.md`、`04-review.md` 与 r0 快照逐字节一致 |
| R1 收集数与 skipped | 通过 | 同 §5.4 和 §5.5 |
| r0 新测试断言是否被放宽 | 没有放宽 | 逐行看了 r0→R1 的测试差分（`continue` 412 行 diff，`frontend` 新增和改写）。删除的断言都对应规格指定的换输入：<br>• R1-T1 把 `!= changed_body(3)` 改成更强的 `'改过的开头。' not in`；<br>• R1-T3 把两条手建行换成自动加手建；<br>• R1-T6 把「改名 + 登记 C2」换成「只改名」，所以删掉 `ref_id == 'C2'`，并改成断言 `ref_id is None`。<br>前端的「新增」标签断言从「出现 3 个」收紧为「表格精确为 `tag ml-2`、卡片精确为 `tag`」。r0 的 74 个变异整表重跑，r0 时杀死的仍全部杀死（§7.4） |

## 5. 必须修复项

### MF-R2-1：R1-P7 没有把续拆段的 4 条细节迁到 `docs/ARCHITECTURE.md`

- **位置**：`docs/ARCHITECTURE.md:507`（续拆实现段）。
- **问题**：§4.8 R1-P7 要求把 `CLAUDE.md` 续拆段压缩到要点，并把「细节移到 `docs/ARCHITECTURE.md` 的续拆段落」。压缩后，§3 R1-P7 列出的 ①–④ 在 `CLAUDE.md` 和 `ARCHITECTURE.md` 里都没有了，只散落在 README 和 PLAN。实现方报告说这些细节保留在 ARCH:507/509，与事实不符。
- **给实现方的修改指令**（可直接转发）：

> 只改 `docs/ARCHITECTURE.md`，并在 `impl/report-r1.md` 里补一行说明。不改代码、测试和 `CLAUDE.md`。
>
> 1. 在 `docs/ARCHITECTURE.md:507` 段末（「整本重新拆解仍走原路，取消本轮未执行批并释放预留。」之后）补上下面这句，或与它等价的表述，并与已有文字合并，不要重复：
>    「续拆的每集时长沿用原拆解且不能改，续拆报价不带时长与「大约几集」；续拆进行中新章人物就会进入总表并出现在定妆页，G1 回到未通过；本轮批次无论首次执行还是单批重跑，都按批 `source_json.snapshot_no` 读本轮绑定的快照，书斋里再改原文对重跑无效，仍失败只能整本重新拆解（会生成新的总表，已定的妆要重新定）。」
> 2. 顺手（可选）把 ARCH:509 里的「（`continuing` 时只取 `seq ≤ _published_max_seq` 的单元）」改成「（已发布拆解的 `_continuations` 非空时只取 `seq ≤ _published_max_seq` 的单元）」，与 R1-P3 一致。
> 3. 自检：
>    - `wc -c CLAUDE.md` 仍是 67,350；
>    - `git diff` 相对现状只有 `docs/ARCHITECTURE.md` 和报告有变化；
>    - `grep` 能在 ARCHITECTURE 里找到「不能改」「G1 回到未通过」「绑定的快照」「已定的妆要重新定」。
>
>    这一处只改文档，不需要重跑后端全量。

## 6. 可优化项（不阻断）

1. **ARCH:509 的过滤条件描述没跟上 R1-P3**：仍写「`continuing` 时只取…」。这句话本身没错，但不完整：续拆 partial 后整本重拆时也会过滤。建议和 MF-R2-1 一起改，见指令第 2 条。
2. **CLAUDE:196「缺失拒绝」有歧义**：基线原文是「`auth_method` 缺失拒绝」，压缩后主语没了。ARCH:418 写着「None 不放行」，事实没有丢。补回 `auth_method` 只多 12 字节（67,362），仍在上限以内。
3. **R1 测试没覆盖到的三处（都用临时探针确认实现是对的，见 §7.2）**：
   - **P1 写事务内的复查**：只删 `_save_snapshot` 里的那一处（R-P1b），R1-T8 仍然全绿，因为事务外的检查先拦住了。建议加一条用例：绕过事务外检查，直接调 `_save_snapshot`，断言 409。
   - **P1 不误伤**：把守卫改成「任何 running/partial 都拦」（R-P1e），三个新文件和两个既有来源测试文件共 186 条用例全绿。建议加「未续拆拆解 partial、没有在途 job 时同步照常」的用例。
   - **R1-T9 的 `continuable` 断言恒真**：用例没有同步新章，所以就算不改坏 manifest，`continuable` 也本来就是假。去掉 `manifest is not None`（R-P2c）也能通过。建议先同步出新章，断言改坏前 `continuable` 为真、改坏后为假。另外 warning 的位置（「末尾」）没有断言（R-P2e）；代码里确实是 `append`。
4. **R1-T6 把 r0「改名 + 书斋登记 C2」的组合场景改没了**：这次是改写原用例，而不是新增一条。补 `ref_id` 的行为仍由 `test_continuity_recognizes_workshop_registered_character` 覆盖，B6 变异仍会变红，所以没有实际的覆盖损失。如果想保留组合场景，可以另加一条用例。
5. **快照损坏时日志偏多**（实现方报告第 6 节第 3 条已提到）：`_read_manifest` 每次都会 `logger.exception`，前端每 5 秒轮询一次，同一条错误会反复写进日志。可以降级成一次 warning，或者按快照去重。

## 7. 变异实验清单与结果

工具在仓库外：`/tmp/r2-mat/mutate2.py` 和日志 `mut-all.log`、`mut-r0.log`。每次只改一处，用 `pytest -x` 跑目标，按原字节写回，并核对 sha256。全部做完后，`git diff` 与 `diff-r1.patch` 用 `cmp` 比对一致。

### 7.1 MF1–MF4（7 个整文件变异，加 8 个单用例定位）

| 变异 | 整个 continue 文件 | 指定用例 |
|---|---|---|
| B26 `_source_inputs` 忽略批自己的快照号 | 变红 | R1-T1 用例变红 |
| B14 续拆 partial 也发布 | 变红 | R1-T2 用例变红 |
| B2 退役循环去掉冻结跳过 | 变红 | R1-T3 用例变红 |
| B4 两种跳过都去掉 | 变红 | R1-T3 用例变红 |
| B3 只去掉 alias 跳过 | 存活（与 r0 一致，接近等价） | — |
| B20 `_confirmed_quote` 换成 `payload = preview` | 变红 | 过期、额度、成功后 confirmed 三条用例分别变红 |
| B21 确认时不查未结束批次 | 变红 | R1-T4 未结束批次用例变红 |

### 7.2 R1 产品改动（26 个，存活 5 个）

| 变异 | 目标 | 结果 |
|---|---|---|
| R-P1a 只删事务外的同步检查 | R1-T8 | 存活（等价：写事务内会再拦一次，文案相同） |
| R-P1b 只删 `_save_snapshot` 内的检查 | R1-T8 + 探针 | R1-T8 通过，**探针变红** → §6 第 3 条 |
| R-P1c 两处都失效 | continue + serial_sources | 变红（R1-T8） |
| R-P1d 只拦 running、不拦 partial | continue | 变红（R1-T8） |
| R-P1e 忽略 `_continuations`，任何 running/partial 都拦 | 3 个新文件中的 2 个 + 两个既有来源测试文件，共 186 条 | **存活**；探针变红 → §6 第 3 条 |
| R-P1f 不看状态，done 也拦 | continue | 变红 |
| R-P2a 不降级（`except ()`） | continue | 变红（R1-T9） |
| R-P2b 不加 warning | continue | 变红 |
| R-P2c `continuable` 不看 manifest | continue | **存活**；探针（先同步出新章）变红 → §6 第 3 条 |
| R-P2d `changed_covered` 不看 manifest | continue | 变红 |
| R-P2e warning 插在开头而不是末尾 | continue + 探针 | 存活（没有其他 warning 时位置看不出来；代码核对是 `append`） |
| R-P3a 视图过滤退回 `continuing` | continue | 变红（R1-T10） |
| R-P3b 导出过滤退回 `_continuing` | continue | 变红（R1-T10） |
| R-P4 退回 7 键精简 dict | continue + 既有拆解测试 + 定妆测试，共 400 条 | 存活（防御性改动，到不了这个分支，属于预期） |
| R-T5 转向条目别名只取新条目 | continue | 变红（`'老船夫' in []`） |
| R-T6 名字/别名匹配失效 | continue | 变红（`2 == 1`） |
| R-T7 `unit_to >= marker` 改成 `>` | continue | 变红（`3 == 2`） |
| R-T7b 改用 `unit_from`（即 r0 的 P5） | continue | 变红 |
| F-P5a / b / c 按钮固定 primary / 固定 quiet / 条件反转 | frontend | 全部变红 |
| F-P6a 表格标签不带 `ml-2` | frontend | 变红 |
| F-P6b 卡片标签带上 `ml-2` | frontend | 变红 |
| F14 可续拆时块外重复「改过的旧章」一句 | frontend | 变红（r0 时存活） |

上表 26 项里，R-P1e@probe、R-P2c@probe 两项只跑探针，用来确认探针本身能区分对错，两项都变红。

### 7.3 临时探针（`/tmp/r2-mat/test_zz_r2_probe.py`，跑完已从仓库删除）

在现实现下 6 条全部通过：
- `P1_NONCONTINUED_PARTIAL_SYNC_OK`
- `P1_DONE_CONTINUED_SYNC_OK`
- `P1_RUNNING 409 导演模型任务进行中…`，以及 `P1_INNER 409 续拆进行中，完成后再同步`
- `P2_VIEW False None None [] [2] [warning]`
- `P2_RETRY running …`
- `P3_AFTER_PUBLISH 16 16 16 16`

### 7.4 r0 的 74 个变异整表重跑

做法：r0 的变异表原样复用，锚点有变化的只改锚点，改坏的语义不变：B31 的条件已改成 `manifest`，P1/P2 的过滤条件已改，F1/F17 的 `addedTag` 多了参数。

- 后端 56 个：B1–B35、M1–M5、P1–P5、S1–S10、N1。存活 5 个：B3、B8、B9、B34、P4，r0 时都已判定为等价或接近等价。r0 存活的 B2、B4、B14、B20、B21、B26、P5 现在全部变红。
- 前端 18 个：F1–F18 全部变红，包括 r0 唯一存活的 F14。

## 8. 现场还原

- 源码：每个变异写回后都核对了 sha256。最终 `git diff | cmp - diff-r1.patch` 一致，三个新测试文件和 `docs/tasks/…` 下各文件的 sha1 与开始时相同。
- 临时文件：
  - 已删除：探针 `backend/tests/test_zz_r2_probe.py`；没有生成对应的 `.pyc`（`find` 核对过）。
  - 已删除：`tsc` 和 `build` 生成的 `frontend/tsconfig.tsbuildinfo`、`frontend/.next/`，以及 `frontend/next-env.d.ts`。这三个都在 gitignore 里，开始时并不存在（`next-env.d.ts` 的创建时间就是本次 build 的时间）。
  - 无 `node_modules` 副本建在 `/tmp/r2-mat/nonm`，已删除。
- 状态：最终 `git status --porcelain --untracked-files=all` 与开始时相比，只多了本文件 `?? docs/tasks/2026-11-12-studio-serial-breakdown/07-review-r2.md`。
- 实验材料都在仓库外的 `/tmp/r2-mat/`：变异脚本、探针、全量和变异日志、r0 版本重建文件。

## 9. R2 核验

结论：**通过**。MF-R2-1、修改指令第 2 条、可优化项第 2 条都已完成；代码和测试相对 R1 没有任何变化。本节只核验这三项，不新增问题，也没有重跑后端全量。

**依据**：
- 把 `baselines/2026-11-12-studio-serial/` 与 `review-serial-materials/` 里的 `diff-r1.patch`、`diff-r2.patch` 分别对比，两处的文件逐字节相同（`cmp`）。
- 副本当前的 `git diff | cmp - diff-r2.patch` 也一致。
- R1 版本的两份文档，是用基线 `135253f` 加上 `diff-r1.patch` 的对应片段重建出来的。重建出的 `CLAUDE.md` 为 67,350 字节，与第 1–8 节核验时一致。

| 项 | 结果 | 证据 |
|---|---|---|
| 1. ARCHITECTURE 续拆段补齐 ①–④ | 通过 | 和 R1 版本比，ARCH 只改了 `507`、`509` 两行（`diff` 输出 `507c507`、`509c509`）。507 段末、「整本重新拆解仍走原路…释放预留。」之后新增四句：<br>①「续拆的每集时长沿用原拆解且不能改，续拆报价不带时长与「大约几集」」；<br>②「续拆进行中新章人物就会进入总表并出现在定妆页，G1 回到未通过」；<br>③「本轮批次无论首次执行还是单批重跑，都按批 `source_json.snapshot_no` 读本轮绑定的快照，书斋里再改原文对重跑无效」；<br>④「仍失败只能整本重新拆解，会生成新的总表，已定的妆要重新定」。<br>用 `grep -o` 计数，「不能改」「G1 回到未通过」「读本轮绑定的快照」「已定的妆要重新定」在全文各出现 1 次，没有重复。<br>与已有文字对照：<br>• 同段前文写的是报价层「不写 `target_episodes`」和分集批「不带 `suggested_episodes`」，新句写的是作者可见的报价参数，层次不同，不矛盾；<br>• 509「旧方案与 G0 继续有效」说的是分集方案，新句说的是总表与 G1，不冲突。<br>与代码一致：<br>• 续拆报价路由没有请求体参数（`routers/studio.py:408`）；<br>• `_source_inputs` 用的是 `source.get('snapshot_no') or breakdown['snapshot_no']`（`breakdown.py:751`）。 |
| 2. 过滤条件措辞与 R1-P3 一致 | 通过 | ARCH:509 由「（`continuing` 时只取…）」改为「（已发布拆解的 `_continuations` 非空时只取 `seq ≤ _published_max_seq` 的单元）」，与 `breakdown_plan.py:166`、`:683` 的条件一致 |
| 3. CLAUDE.md 补回 `auth_method` | 通过 | `wc -c CLAUDE.md` = **67,364**，不超过 67,400。和 R1 版本 `diff` 只有 1 处改动（`grep -c '^[<>]'` = 2，即一行删、一行加），出现在第 196 行：「缺失拒绝」改为「`auth_method` 缺失拒绝」。字数差 14 字节，就是加上的这段文字 |
| 4. 代码与测试没有变化 | 通过 | 把 `diff-r1.patch` 和 `diff-r2.patch` 按文件切开比较，两边都是 30 个文件，有差异的只有 `CLAUDE.md` 和 `docs/ARCHITECTURE.md`。<br>未跟踪文件的 sha1 与第 1–8 节核验结束时一致：三个新测试文件、`impl/report.md`、`impl/report-r1.md`。<br>新出现或变化的只有派单方的 `06-fix-r2.md`、`02-spec.md`（新增 §4.9），以及实现方的 `impl/report-r2.md` |

**现场**：
- 本次核验只在副本外的 `/tmp/r2-mat/r1tree` 重建过 R1 文档，没有改动副本里的任何文件。
- 和本次核验开始时相比，副本里只有本文件多了这一节。
