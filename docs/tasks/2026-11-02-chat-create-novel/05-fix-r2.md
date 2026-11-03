# 返修单 R2：去掉注释绕行、补透传断言（2026-11-03）

独立复核（`04-review.md`）结论：功能与 §5 七条全过，但有两项必须修复，裁决如下；规格已升 v1.2（`02-spec.md` 开头、§4.1、§5.7），以 v1.2 为准。

## 裁决

1. **注释字面量绕过既有锁不接受**（与 R1 否决 `importlib` 同一类）。v1.2 授权 `backend/tests/test_novel_p2_frontend.py` **只改 `:40` 那一处**：把 `assert 'src="/novels?embed=1"' in drawer` 换成三行（缩进相同）：
   ```python
       assert "src={novelFrameSrc}" in drawer
       assert 'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")' in source
       assert 'src="/novels?embed=1"' not in drawer
   ```
   同时 `frontend/app/page.tsx` **按字节删掉**整行 `        {/* 初始 src="/novels?embed=1"；打开草稿或已建书时由 novelFrameSrc 切换。 */}`（含行尾换行），保留 BOM。该测试文件 `git diff -U0` 必须恰一个 hunk。
2. **补 `ChatBubble → ChatCard` 的 `onOpenNovel` 透传断言**：按 `04-review.md` §6 B 的代码原样加进 `backend/tests/test_novel_chat_create_frontend.py`「ChatCard 分发」一节末尾（`CHAT_CARD_TAG`、`check_bubble_passes_open_novel`、`test_chat_bubble_passes_open_novel_to_every_chat_card`）。
3. **两条自检改成先正样本再坏副本**（`04-review.md` §6 C.1）：`test_bad_one_per_turn_copy_is_caught` 与 `test_bad_save_message_copy_is_caught` 各抽一个检查函数，真实用例与自检共用；自检先对原实现断言通过，再对坏副本 `with pytest.raises(AssertionError)`。删掉「先 `assert == 2` 再 `pytest.raises` 包 `assert == 1`」的写法。
4. 清掉 `test_novel_chat_create.py` 里 v1.0 残留的注释与多余设置（§6 C.2：`workshop` 夹具里「开关 0 初始化 / 按开关 1 补建草稿表」的注释、多余的 `init_db` 调用与开关设置），`test_init_db_creates_draft_table_without_switch` 保留。

## 白名单（本轮）

- `frontend/app/page.tsx`（只删那一行注释，按字节读写）
- `backend/tests/test_novel_p2_frontend.py`（只 `:40` 一处）
- `backend/tests/test_novel_chat_create_frontend.py`、`backend/tests/test_novel_chat_create.py`
- `docs/tasks/2026-11-02-chat-create-novel/03-report.md`（追加「R2 记录」）、`impl/主代理.md`

其他文件一个字节不动；git 只读；不得调用 subagent / subagent_fork / workflow，主代理直接做。

## 验收（原始输出贴进报告）

1. 自查：`grep -c 'src="/novels?embed=1"' frontend/app/page.tsx` = 0；`head -c 3 frontend/app/page.tsx | xxd` = `efbb bf`；`git diff -U0 HEAD -- backend/tests/test_novel_p2_frontend.py | grep -c '^@@'` = 1。
2. 变异（改完按字节还原）：把 `useState("/novels?embed=1")` 临时改成 `useState("/novels/new?embed=1")` → `test_home_keeps_novel_iframe_mounted_when_drawer_closes` 变红；把 `ChatBubble.tsx` 两处 ` onOpenNovel={onOpenNovel} songCardCompact` 都删掉 → 新用例变红。
3. 规格 §5 第 1–7 条重跑（§5.7 按 v1.2）：全量 `passed = 7863 + 新用例实数`、0 failed、0 skipped；HEAD 对照新用例全部 `AssertionError`。
4. `03-report.md` 追加「R2 记录」（裁决、改了什么、各条末行、变异实际输出、两个授权文件的 `git diff -U0` 原文），`impl/主代理.md` 追加本轮。不写本机绝对路径。

最终回复：改了哪些文件、§5 各条末行、变异输出、未完成或需人工确认的地方。
