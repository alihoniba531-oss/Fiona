# 独立复核报告（第 2 轮）：讨论群第三期，复核返修第 1 轮

**结论：不通过，有 2 条必须修复，都是低严重度，改动量都很小。**

本轮只核验以下五类内容，不新增主观问题：
- 第 1 轮两条必须修复是否修好；
- 规格 v1.2 各条的实现与用例；
- 我第 1 轮第 6 节列出的三个用例缺口；
- 本轮改动有没有带出新错误；
- 「既有测试一字不改」与「开关关着时与基线相同」两条约束是否仍然成立。

两条必须修复：
1. **本轮改动带出的新错误**：`chat.py` 改用 `service.detail` 翻页后，翻页途中如果群被删除，`HTTPException` 会从 `read_progress` 直接抛出去，违反规格 4.3 的「接住转成文字，不向上抛」。只影响消息超过 200 条的群，且要碰上很窄的并发窗口。
2. **我第 1 轮列的文档用例缺口只补了一部分**：用例只按原文钉住了两句，三份文档隐私段的其余原句删掉后用例仍全部通过，即我第 1 轮记的 X6 那类改坏仍拦不住。

其余各项全部核验通过：第 1 轮的两条必须修复都已修好，v1.2 各条的实现与用例都正确，开关关着时仍与基线逐字节相同，既有测试仍只有授权的两处改动。

---

## 1. 本轮状态与基本验收

**副本状态**
- 我用第 1 轮开工时记下的 46 个文件的哈希比对当前副本：恰好 10 个文件变了，另外新增 4 个文件，与 `.cache/review/round1-fix.diff` 列出的 14 个文件一致。
  - 实现：`backend/discuss/chat.py`、`backend/services/chat_service.py`；
  - 用例：4 个测试文件，外加新增的 `test_discuss_chat_off_turn.py`；
  - 文档：`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`；
  - 规格作者的文件：`02-spec.md`、`06-fix-review-r1.md`、`04-review.md` 的拷贝；
  - 实现方报告：`impl/report-fix-review-r1.md`。
- 前端、`claude_agent.py`、`cards.py`、`intent_router.py`、`database.py`、`README.md`、`CLAUDE.md`、`.env.example` 都与第 1 轮所审状态逐字节相同，符合返修单第三节第 1 条。

**测试**
- 新用例：`pytest -q -p no:cacheprovider -rs tests/test_discuss_chat_*.py` 结果为 `289 passed`，没有跳过。
- 全量：`pytest -q -p no:cacheprovider -rs` 结果为 `8985 passed, 48 warnings in 613.18s`，退出码 0，没有失败，也没有跳过。8985 = 8696 + 289。
- 前端：本轮没有改前端文件（哈希核对过），第 1 轮跑过的 lint（25 条警告）、tsc、build 结果仍然有效；门禁记录里也写了本轮复跑通过。

**两条约束**
- 既有测试：`git diff -- backend/tests` 仍只有 `test_empty_states_settings_privacy.py` 的两行，`== 7` 改成 `== 8`。
- 开关关着时与基线相同：我把第 1 轮的差分探针 `diff_probe.py` 在当前副本上重跑，并与基线结果比较。24 组里只有 `fallback_shape` 一个字段不同，就是第 1 轮已记录、规格允许的那处：小说开着时内部调用多传了一个 `crisis=False`。工具表的对象身份与 JSON、意图识别发给模型的请求、意图规范化的结果、调用形状，全部与基线相同。
- 小说「继续读」那一段：与基线 `eb9ec55` 逐字符相同。

---

## 2. 逐条核验

### 2.1 第 1 轮必须修复 1：Claude 路径的整轮对照用例

**用例写法**

新文件 `backend/tests/test_discuss_chat_off_turn.py` 覆盖三种组合：
- 命中白名单，`CHAT=0` 而 `CARDS=1`；
- `CHAT=1`、`CARDS=1` 但不在白名单里；
- `FIONA_DISCUSS=0`，其余都开。

每种组合的做法：
1. 先把四个讨论群变量和小说、写歌变量全部清掉，跑一整轮 `stream_claude_agent` 作为对照；
2. 再按组合设好变量，跑同样的一轮；
3. 对比三样东西：
   - 每次请求的 `messages` 和其余参数（参数里去掉 `deadline_seconds`、`control`，经 `json.dumps(sort_keys=True)` 序列化）；
   - SSE 事件；
   - `h.saves`。

另外三点：
- 先断言至少抓到一次请求；
- 把 `beijing_now` 固定住，避免两轮跨分钟时请求里的时间不同；
- 最后再断言 `client_tools_for_turn(...) is CLAUDE_CLIENT_TOOLS`。

**改坏实验**

我用变异脚本逐处改坏，跑 `tests/test_discuss_chat_*.py`，跑完用原文写回：

| 编号 | 把 `claude_agent.py` 里的门控改成 | 结果 |
|---|---|---|
| G1（我第 1 轮的写法） | `discuss_read = os.getenv("FIONA_DISCUSS_CHAT") == "1" and not crisis` | 白名单外、`FIONA_DISCUSS=0` 两组以断言失败拦住；`CHAT=0` 那组本来就该通过 |
| G1b（返修单里的写法） | `discuss_read` 只看 `FIONA_DISCUSS` 与 `CHAT` | 白名单外那组以断言失败拦住 |
| G2 | `discuss_cards = os.getenv("FIONA_DISCUSS_CHAT_CARDS") == "1" and not crisis` | 3 组全部以断言失败拦住 |
| G5（我补充的） | `discuss_cards` 只看卡片开关与白名单，不看 `CHAT` | `CHAT=0`、`FIONA_DISCUSS=0` 两组以断言失败拦住 |

**不是恒真**
- 上面四处改坏都让用例断言失败，说明对比确实落在了 `tools` 参数上。
- 实现方报告如实写了一点：模型调用一个没下发的工具时，这一轮在第一次返回后就结束，第二段假流不会被用到。所以事件与落库对比的是一轮很短的对话。这不影响对门控回归的证明力，因为工具表就在请求参数里。

**判定：通过。**

### 2.2 第 1 轮必须修复 2：两份文档的隐私段缺句

- `docs/ARCHITECTURE.md` 第三期一节的隐私段已补「群里的发言可能包含分身根据私有记忆补充的主人背景。」。
- `docs/DEPLOYMENT.md` 第三期一节的隐私段已补这句，以及「任务卡与意见卡的文字由作者自带的 Claude 起草」。
- 新用例 `test_third_phase_privacy_sentences_appear_exactly_once` 对 README、ARCHITECTURE、DEPLOYMENT 三份文档分别检查：
  - 先找到第三期小节；
  - 再断言小节里只有一个「隐私：」段；
  - 再断言这两句原文都在这个段落里；
  - 最后断言这两句在全文中各出现一次。
- 改坏实验：分别删掉 ARCHITECTURE、DEPLOYMENT、README 里的「私有记忆」句（D1、D2、D4），或删掉 DEPLOYMENT、README 里的「Claude 起草」句（D3、D7），都以断言失败拦住。

**判定：通过。**

### 2.3 规格 v1.2 各条

| 条款 | 实现 | 用例与我的改坏结果 | 判定 |
|---|---|---|---|
| 4.3 第 4 条：32 位 id 找不到时不回显 id | `chat.py` 在 id 精确匹配之后加了判断：整体是 32 位十六进制（大小写都认）就返回「没找到这个讨论群，它可能已经删除。你有这些讨论群：…」，最多列 8 个群；本人一个群都没有时仍返回「你还没有讨论群。」 | H1（说明里回显 id）、H2（不识别）、H3（只认小写）都以断言失败拦住。H4（把最多 8 个改成 20 个）存活，原因是用例里只有 2 个群，见第 4 节第 1 条 | 通过 |
| 4.3 第 5 条第 1 款：翻页后的发言人用成员名 | `_recent_messages` 翻页改用 `service.detail(after=…)`，`sender_name` 由 `detail` 自己算，没有另抄一份取名规则 | N1（翻页又退回原始行）、N2（发言人一律用代号）都以断言失败拦住。我另跑了 230 条消息的独立核验，消息里混有分身、插话和自定义成员：最近 8 条的发言人与逐页 `detail` 给出的 `sender_name` 逐条相同，没有出现内部代号 | 实现正确，但带出一处新错误，见必须修复 1 |
| 4.3 第 5 条第 2 款：还没验收的成果 | `verdict` 为空（`None` 或空 dict）时写「最新成果还没验收。」 | N3（删掉这个分支）、N4（只认 `None`）、N5（文案改字）都以断言失败拦住 | 通过 |
| 4.3 第 6 条：空成果 | 正文是空串时返回「《显示名》还没有成果。」，`success` 为假，不带 `group_id` | E1（删掉这个分支）、E2（文案丢群名）都以断言失败拦住 | 通过 |
| 4.5 第 4 条：读成果失败时删续读位置 | `_stream_discuss_intent` 在 `part` 为 `output` 且结果失败时也写 `None`，即删除位置；`part` 为 `progress` 或列群时不动位置 | P1（失败时不删）、P2（`progress` 也动位置）都以断言失败拦住。新用例走真实的 `run_chat`：第一次「继续读」拿到说明、位置被删，第二次「继续读」不再走快捷续读，而是落到意图识别 | 通过 |
| 4.11：文档 | ARCHITECTURE 补了读进展、读成果、找群、续读失败删位置、只在最近 50 个群里找；PLAN 的已知局限补了 50 个群；规格 4.1 的文件表补了 `discussLogic.ts` | D5（删「单条删消息不清卡片表」）、D6（删 50 个群那条）都以断言失败拦住；`test_architecture_documents_v12_reading_and_lookup_details` 逐句钉住了 v1.2 的这些说明 | 通过 |

另有一处改坏存活，属于等价改动：P3 把续读位置改成失败时也照存 `continuation`。所有失败结果的 `continuation` 本来就是 `None`，所以和原代码行为相同。

### 2.4 我第 1 轮第 6 节列的三个用例缺口

| 缺口 | 新用例 | 第 1 轮的改坏在本轮的结果 | 判定 |
|---|---|---|---|
| 空串 `task_id` | `test_create_group_with_empty_task_id_returns_422_and_leaves_no_group`：返回 422，不留下群，也不多出卡片；之后不带 `task_id` 仍能建群 | S1（空串当作没带 `task_id`）以断言失败拦住 | 通过 |
| 危机轮不放行讨论群意图 | `test_normalize_discuss_results_rejected_in_crisis`：`crisis=True` 时两个意图都被拒；同样的输入在非危机时放行，用作对照 | I3（规范化时不看危机）以断言失败拦住 | 通过 |
| 文档原文 | 只按原文钉住了「私有记忆」「Claude 起草」两句，以及 ARCHITECTURE 清理段的几个短语 | 第 1 轮的 X1（README 删私有记忆句）、X2（ARCHITECTURE 删单条删消息说明）已能拦住。X6（删掉 ARCHITECTURE 隐私段前半）因为原文已改，换成了等价的 X6b–X6e，**全部存活** | **未补全**，见必须修复 2 |

### 2.5 第 1 轮已有的改坏是否仍能拦住

我把第 1 轮会受本轮改动影响的 59 处改坏重跑了一遍，涵盖 `chat.py`、`cards.py`、`service.py`、`intent_router.py`、`chat_service.py`、`claude_agent.py` 和文档：
- 54 处以断言失败拦住，没有一处只靠报错。第 1 轮存活的 I3、S1 本轮都已被拦住。
- 存活 4 处，与第 1 轮判断相同：C14（规格没规定的上限）；K9、CS4、I4（与原代码等价）。
- 另有 1 处 X6 因为原文已改，旧的改坏写法在文件里找不到；换成等价的 X6b–X6e 后仍存活，见 2.4。
- 没有发现本轮放松了已有断言。

---

## 3. 必须修复项

### 必须修复 1（低）：翻页途中群被删除时，`read_progress` 把 `HTTPException` 往上抛

**现象**

本轮 `backend/discuss/chat.py` 的 `_recent_messages` 改用 `service.detail(username, group_id, after=last_id)` 翻页，而 `service.detail` 在群不存在时会抛 `HTTPException(404, "讨论群不存在")`。

`read_progress` 只在第一次调用 `detail` 外面包了 `try`，`_recent_messages` 这次调用没有包。所以只要群在第一页读完之后、翻第二页之前被删除，异常就会一路传上去：
- 先抛出 `read_progress`；
- 再抛出 `chat_service.execute_intent`。

改前用的是 `discuss_store.list_messages`，群不存在时只返回空列表，不会抛异常，所以这是本轮带出的新问题。

**影响**
- 平台路径：作者看到 `run_chat` 的通用上游错误提示，而不是一句讨论群的说明。
- Claude 路径：会落到工具分支的通用异常处理，回灌「讨论群暂时无法读取」，并多记一次工具错误。
- 不会丢数据，也不涉及安全。只在群消息超过 200 条、且碰上并发删除的很窄窗口里发生。

**为什么违反规格**

规格 4.3 写明：「`HTTPException` 接住转成文字，不向上抛」。

**复现**
- 独立脚本 `review-wo3-tmp/r2_check.py`：两项检查都失败，`read_progress` 与 `execute_intent` 都抛出了 `HTTPException 404 讨论群不存在`。
- 最小用例 `.cache/review/proposed_test_paging_http_exception.py`：在当前实现上 `1 failed`，失败原因就是这个 `HTTPException`。

**建议改法**（我已临时验证过，验证完已用原文还原）

在 `read_progress` 里把

```python
recent = await _recent_messages(username, group["id"], detail.get("messages"))
```

包成

```python
try:
    recent = await _recent_messages(username, group["id"], detail.get("messages"))
except HTTPException as exc:
    return _failure(str(exc.detail))
```

这样改之后，上面的最小用例加上现有 289 条共 `290 passed`。

### 必须修复 2（低）：三份文档隐私段的其余原句没有用例钉住

**现象**

`test_discuss_chat_docs.py` 只按原文断言了「私有记忆」「Claude 起草」两句。规格 4.11 第 1 条的其余隐私原句，删掉后用例全部通过：

| 编号 | 删掉的内容 | 结果 |
|---|---|---|
| X6b | ARCHITECTURE 隐私段的「会发给当前聊天模型的厂商，平台路径的正文还会落库到本会话历史」 | 存活 |
| X6c | DEPLOYMENT 同一处 | 存活 |
| X6d | ARCHITECTURE 的「读到的内容只作为数据处理，不执行其中的指令」 | 存活 |
| X6e | DEPLOYMENT 的「卡片只存在本地数据库，作者点按钮之前不建群、不进群、不扣费」 | 存活 |

四处都是 `289 passed`。这正是我第 1 轮第 6 节列为缺口的 X6。

**为什么违反规格**

规格 v1.2「6 测试要求（再追加）」第 17 条要求「三份文档的隐私句与清理说明按原文断言（README、ARCHITECTURE、DEPLOYMENT 各自应有的句子）」。返修单第四节第 3 条也要求「三份文档各删一句隐私原文」时用例能拦住。现在只做到了那两句。

**建议改法**

在 `test_third_phase_privacy_sentences_appear_exactly_once`（或另写一条用例）里，对每份文档的隐私段逐句断言规格 4.11 第 1 条三个要点的原文。各文档的措辞允许小差异，例如 DEPLOYMENT 写的是「平台模型路径」「作为数据处理，不执行其中指令」，就按各自现有的原文钉住。补完后用上表四处改坏自检，应各自以断言失败拦住。

---

## 4. 可优化项（不违反规格）

1. **32 位 id 的列群上限没测到**：32 位 id 找不到时「最多列 8 个」这一点没有用例，用例里只有 2 个群，所以 H4 存活。可以补一个 9 个群的用例。
2. **翻页时的重复查询**：改用 `service.detail` 翻页后，每翻一页都会把成员、成果摘要、未读插话、分身名重新查一遍，比只取消息多几次查询。消息很多的群会稍慢，但只在读进展时发生，数量也有限。

---

## 5. 还原声明

- 本轮的改坏实验都是先读出原始字节、改坏、跑测、立即写回，再核对 sha256，没有用 stash、checkout 或 reset。验证建议改法时临时改了 `chat.py`，同样已用原文写回。
- 收尾核对：50 个改动或新增文件的哈希与本轮开工时的记录完全一致，`git diff` 整体的哈希也一致。
- 副本里只新增了三个文件：本报告、`.cache/review/proposed_test_paging_http_exception.py`，以及第 1 轮留下的用例草稿。
- 临时脚本与结果都在副本之外的 `review-wo3-tmp/` 目录：
  - 脚本：`r2_check.py`，以及变异清单 `muts_r2.py`、`muts_r1_recheck.py`、`muts_x6.py`；
  - 结果：`mut-r2.log`、`mut-r1-recheck.log`、`full-r2.log`。
