# 独立复核报告（第 3 轮）：讨论群第三期，复核返修第 2 轮

## 1. 结论：通过，没有必须修复项

本轮核验了三件事：
- 第 2 轮的两条必须修复是否已经修好；
- 本轮改动有没有带出新错误；
- 两条约束是否仍然成立：既有测试一字不改，开关关着时与基线一致。

两条必须修复都已修好，新用例都能在对应改坏时以断言失败拦住，没有发现新错误，两条约束仍然成立。

本轮改动的范围核对：
- 第 2 轮收尾时我记下了 50 个文件的哈希。和当前副本逐个比对，只有 3 个文件变了：
  - `backend/discuss/chat.py`
  - `backend/tests/test_discuss_chat_readonly.py`
  - `backend/tests/test_discuss_chat_docs.py`
- 新增了 3 个文件，都是返修单、报告之类的文字材料：
  - `07-fix-review-r2.md`
  - `04-review-r2.md`
  - `impl/report-fix-review-r2.md`
- 这与 `.cache/review/round2-fix.diff` 列出的文件一致。文档、前端、`chat_service.py` 等其余文件都与第 2 轮逐字节相同。

---

## 2. 逐条核验

### 2.1 第 2 轮必须修复 1：翻页途中群被删除

**实现**

`chat.py` 的 `read_progress` 里，调用 `_recent_messages` 的那一处包上了 `try/except HTTPException`，接住后返回 `_failure(str(exc.detail))`。写法与第一次调用 `detail` 那一处一致，没有改动别的地方。

**我的复现草稿**

`.cache/review/proposed_test_paging_http_exception.py` 的内容和第 2 轮相同。在当前实现上跑，结果是 `1 passed`。上一轮同一份草稿是 `1 failed`。

**新加的用例**

`test_read_progress_handles_group_deleted_during_recent_pages`：
- 先造 205 条消息，再把 `service.detail` 换成第二次调用时抛 404 的版本；
- 断言 `detail` 确实被调用了两次，证明真的走到了翻页；
- 再断言返回值严格等于 `{"text": "讨论群不存在", "model_text": "讨论群不存在", "success": False}`。

**改坏实验**

每处改坏后跑一遍 `tests/test_discuss_chat_*.py`，跑完立即写回原文：

| 编号 | 怎么改坏 | 结果 |
|---|---|---|
| T1 | 去掉这层 `try/except`，回到第 2 轮的代码 | 新用例以断言失败拦住 |
| T2 | 接住异常后不返回失败，而是当作没有发言、照样返回成功 | 新用例以断言失败拦住 |
| T3 | 接住异常后换成别的文案 | 新用例以断言失败拦住 |

**独立脚本**

第 2 轮写的 `r2_check.py` 重跑后 4 项全部通过：
- 翻页后最近 8 条的发言人与群聊页逐条一致；
- 没有出现内部代号；
- 翻页途中群被删除时，`read_progress` 返回文字；
- 同样情况下，`execute_intent` 也返回文字。

**判定：通过。**

### 2.2 第 2 轮必须修复 2：文档隐私段与清理段逐句钉住

**新用例**
- `test_privacy_paragraph_matches_every_original_sentence`：对 README、ARCHITECTURE、DEPLOYMENT 三份文档各跑一次。
- `test_architecture_cleanup_matches_every_original_sentence`：只针对 ARCHITECTURE 的清理段。

两条都先用 `third_phase_paragraph` 定位段落，它依次检查：
1. 找到第三期小节的标题；
2. 小节里「隐私：」或「清理：」恰好出现一次；
3. 截取到空行为止的那一段，并确认这一段不为空。

之后才对照写死的原文快照逐句检查是否在段内。快照不是从被测文档现拆出来的，用例的注释里也说明了这样做的理由：避免删掉一句后快照跟着变少、用例变成恒真。

**改坏实验**

逐句删除用的句子由我自己的脚本从文档现文拆出来（按「。」「；」切），没有照抄用例里的快照，每处改坏都在文档上直接删除原文。

| 改坏 | 处数 | 结果 |
|---|---|---|
| 第 2 轮存活的 X6b–X6e（ARCHITECTURE、DEPLOYMENT 隐私段删「发给厂商、落库」半句，删「作为数据处理」句，删「点按钮前不建群」句） | 4 | 全部以断言失败拦住 |
| 三份文档隐私段逐句删除（README 5 句，ARCHITECTURE 4 句，DEPLOYMENT 4 句） | 13 | 全部以断言失败拦住 |
| 三份文档隐私段逐个删除逗号分句（例如「，卡片只存在本地数据库」「，不执行其中的指令」） | 12 | 全部以断言失败拦住 |
| ARCHITECTURE 清理段逐句删除 | 4 | 全部以断言失败拦住 |
| ARCHITECTURE 清理段逐个删除逗号分句 | 2 | 全部以断言失败拦住 |
| 句子挪位：把句子挪出原段落但留在同一小节里（ARCHITECTURE 隐私句挪到已知局限段；清理句挪进隐私段；DEPLOYMENT 私有记忆句挪到变量列表） | 3 | 全部以断言失败拦住 |

合计 38 处，全部拦住，没有一处只靠报错。挪位那 3 处说明断言落在了正确的段落上，句子只要不在本段内就会失败，所以不是恒真。

**判定：通过。**

### 2.3 本轮改动有没有带出新错误，两条约束是否仍然成立

- **chat.py 的改动**：只是给 `_recent_messages` 的调用包了一层 `try/except HTTPException`，其他异常照旧往上抛，正常读取的路径没有变化。用第 2 轮写的 230 条消息独立核验重跑，发言人名仍与 `detail` 逐条一致。
- **新用例**：`tests/test_discuss_chat_*.py` 共 `294 passed`，没有跳过。
- **全量**：`8990 passed`，没有失败，也没有跳过，退出码 0。8990 = 8696 + 294。
- **既有测试**：`git diff -- backend/tests` 仍只有 `test_empty_states_settings_privacy.py` 里授权的两行，`== 7` 改成 `== 8`。
- **开关关着时与基线一致**：第 1 轮的差分探针重跑了一遍。24 组组合里，唯一不同的字段仍是 `fallback_shape`，就是第 1 轮已记录、规格允许的那一处：小说开着时，内部调用多传了一个默认值 `crisis=False`。
- **前端**：本轮没有改前端，第 1 轮的 lint、tsc、build 结果仍然有效。

---

## 3. 必须修复项

无。

## 4. 可优化项

本轮没有新增。第 2 轮第 4 节的两条仍然只是可选：一是「最多列 8 个群」没有用例测到；二是翻页时每一页都会把成员、成果摘要等重新查一遍。

## 5. 还原声明

- 本轮的改坏都是先读出原始字节，改坏、跑测后立即写回，再核对 sha256。
- 没有使用 stash、checkout 或 reset。
- 收尾时 53 个改动或新增文件的哈希与本轮开工时的记录完全一致，`git diff` 整体的哈希也一致。
- 副本里只新增了本报告。
- 临时脚本和结果都放在副本之外的 `review-wo3-tmp/` 目录：
  - `muts_r3_code.py`、`muts_r3_docs.py`、`muts_r3_reloc.py`
  - `mut-r3.log`、`mut-r3-reloc.json`、`full-r3.log`
