# 04 复核 R2：聊天建书（第二轮）

- 复核方：独立复核，与实现方、规格作者没有任何对话上下文。
- 依据：`02-spec.md` v1.2（唯一依据）；`04-review.md` §4 两项必须修复与 §6；`05-fix-r2.md` 裁决 1–4。`03-report.md` 的「R2 记录」只当线索看，下面每条结论都由本轮亲自重跑得到。
- 范围：按本轮规则，只核验第一轮 §4 两项必须修复是否修好、返修单 1–4 是否按字面落地，不新增主观问题；新发现一律放在「可优化项」。
- 对象：基线 `0ca95af` + 工作区改动。

## 0. 开工与收尾核对

**快照一致。**

```text
$ cmp <(git diff) .review/diff.patch && echo DIFF_SAME
DIFF_SAME
$ (git diff; while IFS= read -r f; do echo "== $f"; cat -- "$f"; done < .review/untracked.txt) | shasum -a 256
bfb6d51b6cb4c9e01f5aa9704051a5a9f83ecaa3ae987fa2c73d8f8ba8b57065  -
$ cat .review/snapshot.sha256
bfb6d51b6cb4c9e01f5aa9704051a5a9f83ecaa3ae987fa2c73d8f8ba8b57065
```

`.review/untracked.txt` 列了 18 个文件。工作区里另有 `verify/claude/` 下的派单方走查文件，不在清单内，也不属于执行方交付。

**本轮改动范围：`.review/r1/diff.patch` 对比当前 `git diff`。**

```text
$ diff .review/r1/diff.patch .review/diff.patch
392a393,407   + backend/tests/test_novel_p2_frontend.py 整段（新出现，唯一 hunk，见 §1.2）
458c473       page.tsx 的 index 行 cfeb58d → b04e58d
501c516       @@ -2958,7 +2968,8 @@ → @@ -2958,7 +2968,7 @@
506d520       删除 +        {/* 初始 src="/novels?embed=1"；打开草稿或已建书时由 novelFrameSrc 切换。 */}
```

已跟踪文件只有这两处差异：`frontend/app/page.tsx` 删了一行，`backend/tests/test_novel_p2_frontend.py` 改了 `:40` 一处。其余 18 个已跟踪文件的 diff 与 R1 逐字节相同。

为确认 `page.tsx` 是按字节删的，本方用 HEAD 版加上 R1 diff 中的 page.tsx 段，在临时目录重建出 R1 版的 `page.tsx`，再与当前文件比较：

```text
PATCH_OK
2971d2970
<         {/* 初始 src="/novels?embed=1"；打开草稿或已建书时由 novelFrameSrc 切换。 */}
BOM_BOTH            # 两版开头都是 efbb bf
```

只少了这一整行（含换行），没有别的字节变化。

**未跟踪文件。**
- 两个新测试与 `.review/r1/` 副本有差异，差异内容见 §1.3、§2、§3。
- 文档方面：`03-report.md` 追加了「R2 记录」，`impl/主代理.md` 追加了「R2」一节，两份都在返修单白名单内。`02-spec.md`（v1.2）、`04-review.md`、`05-fix-r2.md` 由派单方 / 复核方产生。
- `backend/novel/drafts.py` 与 `frontend/components/NovelDraftCard.tsx`：`.review/r1/` 没有这两份文件的副本，无法逐字节比对。旁证是两者的 mtime（01:21 / 01:22）早于 R1 副本的生成时间（01:36）；本轮改动过的文件 mtime 都是 01:46，这两份不在其中。

**收尾。** 全部变异逐项按字节还原，每项都核对了 sha256（`restored_sha_ok=True`）。收尾时 `git diff` 仍与 `.review/diff.patch` 逐字节相同（`DIFF_SAME`），快照哈希仍为 `bfb6d51b…57065`，与 `.review/snapshot.sha256` 一致。

**操作说明。** 试算快照哈希的格式时，本方在一条循环里误带了一次 `git add -N .`。执行后立刻核对：`git status --short` 与开工时相同（20 个 `M` 加 5 个 `??` 条目），`git diff --cached` 为空，索引没有被改动。其余操作都没有写 git。

## 1. 结论：**通过**

第一轮 §4 的两项必须修复都已修好；返修单 1–4 按字面落地，本轮没有超出白名单的改动；回归全绿。

| 项 | 结论 |
|---|---|
| 4.1 注释字面量绕过既有锁 | ✅ 注释已删；`:40` 一处换成三行，与 v1.2 逐字一致；锁恢复效力（M1、M1b、M1c 都红） |
| 4.2 `ChatBubble → ChatCard` 透传无断言 | ✅ 新用例与 §6 B 逐字一致；删两处、删任一处、删解构都红；HEAD 上以 `AssertionError` 失败 |
| 返修单 3 自检先正样本 | ✅ 两条自检已改为「共享检查函数 + 先正样本 + 坏副本 `pytest.raises`」；保留标记的真实实现变异会在正样本这一步就红 |
| 返修单 4 清残留 | ✅ `workshop` 夹具的注释、`database` 导入、开关设置和 `init_db` 都已删；`test_init_db_creates_draft_table_without_switch` 仍在并通过 |
| 回归 | ✅ 新测试 41 passed；全量 `7904 passed`、0 failed、0 skipped（7904 = 7863 + 41）；HEAD 对照 41 条全部 `AssertionError`；`tsc` 退出码 0 |

### 1.1 第 4.1 项：注释绕行

```text
$ grep -c 'src="/novels?embed=1"' frontend/app/page.tsx; echo "grep_exit=$?"
0
grep_exit=1
$ head -c 3 frontend/app/page.tsx | xxd
00000000: efbb bf                                  ...
$ grep -n 'novelFrameSrc\|初始 src' frontend/app/page.tsx
522:  const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1");
2971:        {username ? <iframe ref={novelFrameRef} title="书斋工作区" src={novelFrameSrc} className="min-h-0 w-full flex-1 border-0" />
```

### 1.2 `test_novel_p2_frontend.py` 恰一个 hunk，内容与 v1.2 一致

```text
$ git diff -U0 HEAD -- backend/tests/test_novel_p2_frontend.py
@@ -40 +40,3 @@ def test_home_keeps_novel_iframe_mounted_when_drawer_closes():
-    assert 'src="/novels?embed=1"' in drawer
+    assert "src={novelFrameSrc}" in drawer
+    assert 'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")' in source
+    assert 'src="/novels?embed=1"' not in drawer
$ git diff -U0 HEAD -- backend/tests/test_novel_p2_frontend.py | grep -c '^@@'
1
$ git diff HEAD --stat -- backend/tests ':!backend/tests/test_novel_chat_create*' ':!backend/tests/test_studio_sources_readonly_integration.py' ':!backend/tests/test_novel_p2_frontend.py'
（空）
$ … -m pytest -q -p no:cacheprovider tests/test_novel_p2_frontend.py
48 passed in 0.07s
```

三行与规格 v1.2 开头、§4.1 第 82 行、§5.7 以及返修单裁决 1 逐字一致，缩进 4 格，与原行相同。

### 1.3 第 4.2 项：透传断言

`test_novel_chat_create_frontend.py` 相对 R1 副本只多了一段：`CHAT_CARD_TAG`、`check_bubble_passes_open_novel`、`test_chat_bubble_passes_open_novel_to_every_chat_card`。位置在「ChatCard 分发」一节末尾、「NovelDraftCard 三态与样式」分节线之前，代码与 `04-review.md` §6 B 逐字一致。该文件其余内容没有变化。

```text
PASSED tests/test_novel_chat_create_frontend.py::test_chat_bubble_passes_open_novel_to_every_chat_card
```

这条用例先对原文调用 `check_bubble_passes_open_novel(source)` 并通过，再用两份坏副本（删第一处透传、删解构）各跑一次 `pytest.raises(AssertionError)`。

HEAD 对照中这条用例的失败信息：

```text
AssertionError: ChatBubble 未解构 onOpenNovel
assert 'onOpenNovel' in 'function ChatBubble({ message, agentName = "Chloe", onDelete, …
```

## 2. 返修单 3：两条自检

`test_novel_chat_create.py` 相对 R1 副本的改动如下。

**新增共享检查函数：**
- `check_one_draft(rows)`：`assert len(rows) == 1, rows`；
- `check_foreign_draft_stored_null(stored)`：`assert stored is None, stored`。

**真实用例改用共享函数：**
- `test_one_draft_per_turn_then_text_reply` 用 `check_one_draft(rows)` 代替 `assert len(rows) == 1`；
- `test_save_message_checks_draft_owner_and_conversation` 用 `check_foreign_draft_stored_null(...)` 检查 `own-other` 与 `foreign` 两项。

**`test_bad_one_per_turn_copy_is_caught`：**
- 抽出 `_run_two_drafts(module, h, conversation)`，每次运行都重置 `ChatState` 和流；
- 先用真实 `h.agent` 跑一轮，`check_one_draft(_draft_rows())` 通过；
- `_clear_drafts` 清空后再跑坏副本，用 `with pytest.raises(AssertionError): check_one_draft(...)` 断言变红。

**`test_bad_save_message_copy_is_caught`：**
- 先用真实 `draft_db.db.save_message` 存别人的草稿，断言行存在且 `check_foreign_draft_stored_null` 通过；
- 再用坏副本存一次，断言行存在，并用 `pytest.raises(AssertionError)` 包住同一个检查函数。

旧写法「先 `assert == 2` / `stored == foreign_id`，再用 `pytest.raises` 包 `assert == 1` / `is None`」已全部删除。

**正样本是否真起作用。** 本方加做了保留标记的真实实现变异：自检用的标记字符串不动，只破坏真实实现。两条自检都在正样本这一步红，失败信息就是检查函数自身的断言参数，不是 `DID NOT RAISE`。结果见 §5 的 M5p、M6p。

## 3. 返修单 4：清残留

```text
@@ workshop 夹具 @@
-    import database
-    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "1")
-    # client fixture 已按开关 0 初始化；这里按开关 1 幂等补建草稿表。
-    asyncio.run(database.init_db())
@@ draft_db 夹具 @@
-    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "1")
```

```text
$ grep -n '按开关\|开关 0' backend/tests/test_novel_chat_create.py
（无输出）
PASSED tests/test_novel_chat_create.py::test_init_db_creates_draft_table_without_switch
```

`test_init_db_creates_draft_table_without_switch`（`:246`）仍先 `delenv("FIONA_NOVEL_CHAT_CREATE")`，再执行 `init_db`，然后断言表和索引都存在。

`draft_db` 删掉开关设置这一项，超出了返修单裁决 4 字面上的「`workshop` 夹具」。但它对应 `04-review.md` §5.8 点名的「`draft_db` 也设置了开关」，改动在白名单文件内，相关用例全绿，不构成问题。

## 4. 回归

```text
$ … --collect-only tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py | tail -1
41 tests collected in 0.88s          # 后端 32 + 前端 9
$ … -rs tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py | tail -1
41 passed, 33 warnings in 4.06s

# HEAD 对照：git archive HEAD 解到临时目录，只拷入两个新测试，frontend/node_modules 用 cp -cR 克隆
$ … -rfEs --tb=line --junitxml=… tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py | tail -1
41 failed, 33 warnings in 2.22s
junit: tests 41 failures 41 errors 0 skipped 0
failure 首行分类: Counter({'AssertionError': 29, 'assert': 12})   # 'assert' 是 pytest 断言重写的 AssertionError

# 全量（后台任务）
$ … -m pytest -q -p no:cacheprovider -rs
7904 passed, 35 warnings in 324.42s (0:05:24)
EXIT=0
$ grep -cE 'SKIPPED|skipped' full-run-output
0
$ … --collect-only | tail -1
7904 tests collected in 7.57s

$ cd frontend && npx tsc --noEmit; echo "TSC_EXIT=$?"
TSC_EXIT=0
```

7904 = 7863 + 41；0 failed、0 skipped。HEAD 对照中没有 ImportError、ModuleNotFoundError、OperationalError、skip，也没有其他异常类型。HEAD 对照用的临时目录已删除。

## 5. 变异记录

做法：脚本按字节读出目标文件，断言替换目标的出现次数恰好符合预期，替换后写回，只跑对应用例，用 junit 记录每条用例首个 `E` 行，再把原字节写回并核对 sha256。`page.tsx` 全程按字节处理，BOM 保留。

| # | 改了什么 | 跑的用例 | 结果（首个 `E` 行摘要） | 还原 |
|---|---|---|---|---|
| M1 | `useState("/novels?embed=1")` → `useState("/novels/new?embed=1")` | p2 `test_home_keeps_novel_iframe_mounted_when_drawer_closes` | **1 failed**：`assert 'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")' in '\ufeff"use client";…` | ✅ |
| M1b | 把删掉的注释行原样加回 iframe 前（R1 的绕行写法） | 同上 | **1 failed**：`assert 'src="/novels?embed=1"' not in '…'` | ✅ |
| M1c | M1b + M1（第一轮 C2 的组合，当时 48 passed） | 同上 | **1 failed**：`useState("/novels?embed=1")` 断言红 | ✅ |
| M2 | `ChatBubble.tsx` 两处 ` onOpenNovel={onOpenNovel} songCardCompact` 都删（第一轮 F5） | `test_chat_bubble_passes_open_novel_to_every_chat_card` | **1 failed**：`AssertionError: <ChatCard card={message.cardData} onCompose={onCompose} songCardCompact={songCardCompact} />` | ✅ |
| M3a | 只删第 1 处（`message.cardData`） | 同上 | **1 failed**：同上，指向 `cardData` 那个标签 | ✅ |
| M3b | 只删第 2 处（`message.cards?.map`） | 同上 | **1 failed**：`AssertionError: <ChatCard key={index} card={card} onCompose={onCompose} songCardCompact={songCardCompact} />` | ✅ |
| M4 | 删解构：`onCompose, onOpenNovel, songCardCompact }: ChatBubbleProps` → `onCompose, songCardCompact }: ChatBubbleProps` | 同上 | **1 failed**：`AssertionError: ChatBubble 未解构 onOpenNovel` | ✅ |
| M5 | 真实实现 `if draft_written:` → `if False:` | `test_one_draft_per_turn_then_text_reply`、`test_bad_one_per_turn_copy_is_caught` | 2 failed：真实用例 `AssertionError: [{…两行…}]`；自检因标记消失红（符合设计） | ✅ |
| M5p | 保留标记，真实实现 `draft_written = True` → `False` | 同上 | 2 failed：真实用例红；**自检在正样本这一步红**：`AssertionError: [{…}]`（来自 `check_one_draft`） | ✅ |
| M6 | 真实 `save_message` 删掉整段草稿归属校验 | `test_save_message_checks_draft_owner_and_conversation`、`test_bad_save_message_copy_is_caught` | 2 failed：真实用例 `AssertionError: <foreign id>`；自检因标记消失红（符合设计） | ✅ |
| M6p | 保留标记，归属 SQL 改为只按 `id` | 同上 | 2 failed：真实用例红；**自检在正样本这一步红**：`AssertionError: <foreign id>`（来自 `check_foreign_draft_stored_null`） | ✅ |

全部 11 项都是 `restored_sha_ok=True`。做完后 `git diff` 与 `.review/diff.patch` 逐字节相同（`DIFF_SAME`）。

## 6. 必须修复项

无。第一轮 §4.1、§4.2 都没有残留。

## 7. 可优化项（不阻断，本轮新发现或观察）

1. `CHAT_CARD_TAG = re.compile(r"<ChatCard\b[^>]*/>")` 用的是 `[^>]*`。以后如果给 `<ChatCard>` 加上带 `=>` 的内联箭头函数属性，正则会匹配不到完整标签，`len(tags) == 2` 失败。这种情况会误报红，不会误报绿，所以不影响本轮结论；需要时可改为按 JSX 花括号配平来取标签。`body.split(")", 1)[0]` 截取签名也一样：若参数默认值里出现 `)`，只会误报红。
2. `_run_two_drafts` 每次都会把 `h.ctx.conversation_id` 和 `h.state` 改掉，自检里也没有恢复。它目前只在这一条自检里用；以后如果别的用例复用 `harness` 并依赖这两个字段的初值，需要注意。
3. 第一轮 §5 的其余可优化项（F7、F8、F12、F13 的覆盖缺口，`config` 快照，卡片不自动刷新，重复点击不导航，孤儿草稿与竞态，文档顺带同步，`count == 2` 的绑定，延迟导入，走查补步骤）本轮不在核验范围，没有重新评估，状态沿用第一轮。§5.8 的真实走查执行方仍未做，留给派单方。
4. 可复核性：`.review/r1/` 只保存了两个新测试的副本，`drafts.py`、`NovelDraftCard.tsx` 和文档没有 R1 副本，本轮只能用 mtime 作旁证（见 §0）。下一轮如果还需要做范围核对，建议把全部未跟踪文件的副本或逐文件 sha256 一起存档；本轮快照哈希的格式（`git diff` 后接每个文件的 `== 路径` 与内容）也可以写进 `.review/` 的说明里。

## 8. 给执行者的三次修改指令

无需三次修改。
