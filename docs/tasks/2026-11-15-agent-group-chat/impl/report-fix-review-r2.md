# 讨论群第三期复核返修第 2 轮报告

规格：`docs/tasks/2026-11-15-agent-group-chat/02-spec.md` 的 v1.2 修订。复核：同目录 `04-review-r2.md`。基线 `eb9ec55`，分支 `feat/agent-group-chat`。本轮不 commit，不 stash/checkout/reset。命令均带 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

## 1. 改动文件

- `backend/discuss/chat.py`
  - `read_progress` 对 `_recent_messages` 的调用加 `try/except HTTPException`，接住翻页途中群被删除的 404，返回 `_failure(str(exc.detail))`；`_recent_messages` 仍用 `service.detail(after=…)` 翻页，未改做法。
- `backend/tests/test_discuss_chat_readonly.py`
  - 新增 `test_read_progress_handles_group_deleted_during_recent_pages`：205 条消息的群，`service.detail` 第 1 次照常、第 2 次起抛 `HTTPException(404, service.NOT_FOUND)`；先断言替身被调用 2 次，再断言返回值精确为 `{"text": NOT_FOUND, "model_text": NOT_FOUND, "success": False}`。
- `backend/tests/test_discuss_chat_docs.py`
  - 新增 `PRIVACY_SENTENCES`（README/ARCHITECTURE/DEPLOYMENT 各段原文逐句快照）与 `ARCH_CLEANUP_SENTENCES`。
  - 新增 `test_privacy_paragraph_matches_every_original_sentence`（参数化 3 份文档）与 `test_architecture_cleanup_matches_every_original_sentence`；先定位并断言隐私/清理段存在且非空，再逐句断言原文，缺哪句就报哪句。快照写死在测试里，不从被测文档现拆，删任意一句都会失败。
- 文档、`chat_service.py`、前端、`claude_agent.py`、`cards.py`、`intent_router.py`、`database.py`、`README.md`、`CLAUDE.md`、`.env.example`、规格与复核报告均未改。
- 本报告。

测试总数：289 → **294**（只读 64→65，文档 24→28），新增 5 条。

## 2. 新用例各钉住什么

1. **翻页途中删群**：`read_progress` 不得把 `HTTPException` 抛出去；必须走完第二页并把 `service.NOT_FOUND` 转成失败文本。
2. **隐私段逐句**：README、ARCHITECTURE、DEPLOYMENT 第三期隐私段里的每一句（按「。」「；」切分）都必须按原文存在；任删一句至少一条断言失败。
3. **清理段逐句**：ARCHITECTURE 第三期清理段每一句都必须按原文存在；任删一句至少一条断言失败。

## 3. 自检表

共 7 处，全部由 pytest 以 `failed`（非 `error`）发现；每次改坏后立即按原文写回，未用 git stash/checkout/reset。

| 改坏 | 结果 | 发现用例 |
|---|---|---|
| 去掉 `read_progress` 里 `_recent_messages` 的 `try/except` | `failed` | `test_read_progress_handles_group_deleted_during_recent_pages` |
| 删 README 隐私段「平台模型的分身读到的内容…」 | `failed` | `test_privacy_paragraph_matches_every_original_sentence[README.md]` |
| 删 README 隐私段「读到的内容只作为数据处理…」 | `failed` | 同上 |
| 删 ARCHITECTURE 隐私段「群里的发言可能包含…」 | `failed` | `test_privacy_paragraph_matches_every_original_sentence[docs/ARCHITECTURE.md]` |
| 删 ARCHITECTURE 清理段「删群把任务卡的 group_id…」 | `failed` | `test_architecture_cleanup_matches_every_original_sentence` |
| 删 DEPLOYMENT 隐私段「读到的内容作为数据处理…」 | `failed` | `test_privacy_paragraph_matches_every_original_sentence[docs/DEPLOYMENT.md]` |
| 删 DEPLOYMENT 隐私段「任务卡与意见卡的文字由作者自带的 Claude 起草…」 | `failed` | 同上 |

## 4. 验收

### 4.1 新用例（第 1 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_chat_*.py
```

结果：`294 passed, 48 warnings in 9.14s`；0 failed、0 error、0 skip。

### 4.2 全量（第 2 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8990 passed, 48 warnings in 561.46s (0:09:21)`；0 failed、0 error、0 skip。`8990 = 8696 + 294`。

### 4.3 白名单（第 3 条）

`git status --porcelain --untracked-files=all` 中本轮变动只有 `backend/discuss/chat.py`、`backend/tests/test_discuss_chat_readonly.py`、`backend/tests/test_discuss_chat_docs.py` 与本报告。其余文件与本单派出时逐字节相同；作者放置的 `06-fix-review-r1.md` 等任务文档未改。

### 4.4 既有测试 diff（第 4 条）

`git diff -- backend/tests` 仍只有 `test_empty_states_settings_privacy.py` 两处数字：

```diff
@@ -123,8 +123,8 @@ def test_eight_privacy_paragraphs_appear_once_and_stay_unadorned():
     details_start = source.index("<details")
     details_end = source.index("</details>")
     fold = source[details_start:details_end]
-    assert fold.count("<p>") == 7
-    assert fold.count("</p>") == 7
+    assert fold.count("<p>") == 8
+    assert fold.count("</p>") == 8
```

## 5. 未完成 / 需人工确认

- 真实浏览器走查仍由规格作者执行；本轮只做后端用例与全量回归。
- 文档逐句断言把当前三段原文写死在测试里；以后若有意改文案，需要同步更新这份快照，这是“按原文钉住”的预期代价。
- 未调用真实模型、未访问外网、未读真实 `.env`/数据库；临时脚本与结果文件在仓库外，已删除。
