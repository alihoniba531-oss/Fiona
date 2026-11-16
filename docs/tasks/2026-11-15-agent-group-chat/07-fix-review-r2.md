# 复核返修第 2 轮

同一复核方第 2 轮（同目录 `04-review-r2.md`）：第 1 轮两条必须修复都已修好，v1.2 各条实现与用例都正确，开关关着时仍与基线相同、既有测试仍只有授权两处。结论「不通过」，2 条低严重度必须修复，规格作者都已独立复现。

这是复核返修第 2 轮（上限 3 轮）。改动量小，**不要用工作流或子代理**，你自己直接改。

## 一、两条必须修复

### 1. 翻页途中群被删除时，`read_progress` 把 `HTTPException` 抛了出去

上一轮把 `backend/discuss/chat.py` 的 `_recent_messages` 改成用 `service.detail(username, group_id, after=…)` 翻页，但 `read_progress` 里调用 `_recent_messages` 的那一行没有被 `try/except HTTPException` 包住。群超过 200 条消息、翻到第二页之前群被作者删除时，`HTTPException(404, "讨论群不存在")` 会从 `read_progress`、`execute_intent` 直接往上抛，违反规格 4.3「`HTTPException` 接住转成文字，不向上抛」。

复现（规格作者跑过，当前实现 1 failed）：用 `test_discuss_chat_readonly.py` 里的夹具造一个群、插入 205 条消息，把 `service.detail` 换成「第 1 次照常、第 2 次起抛 `HTTPException(404, service.NOT_FOUND)`」的替身，调用 `chat.read_progress(USER, "<群名>")`；先断言替身恰好被调用 2 次（证明走到了翻页），再断言返回值等于 `{"text": service.NOT_FOUND, "model_text": service.NOT_FOUND, "success": False}`。

要求：`read_progress` 里对 `_recent_messages` 的调用接住 `HTTPException`，按 `_failure(str(exc.detail))` 返回；不改 `_recent_messages` 用 `service.detail` 翻页这一做法。把上面这条复现写成用例（放进本期新测试文件），修前失败、修后通过。

### 2. 文档用例只钉住了两句

上一轮的文档用例只按原文钉住了「群里的发言可能包含分身根据私有记忆补充的主人背景」「任务卡与意见卡的文字由作者自带的 Claude 起草」两句。规格作者把 `docs/ARCHITECTURE.md` 第三期隐私段里的「读到的内容只作为数据处理，不执行其中的指令。」删掉，289 条照样全过。规格 v1.2 第 6 节第 17 条要求三份文档的隐私句与清理说明**按原文**断言。

要求（只补用例，**不改文档**）：在 `README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` 各自的第三期小节里，先定位到隐私那一段（先断言找到了，且段落非空），再把这一段里**现在写着的每一个句子**按原文逐句断言存在。句子以「。」或「；」切分，每一句单独一条断言，失败信息写出缺的是哪一句。`docs/ARCHITECTURE.md` 第三期小节里讲清理的那一段同样逐句按原文断言。要做到：删掉这几段里任意一句，至少一条用例断言失败。

## 二、规矩

1. 允许改动的文件只有：`backend/discuss/chat.py`、`backend/tests/test_discuss_chat_*.py`（改本期新建的，或新增），加上报告 `docs/tasks/2026-11-15-agent-group-chat/impl/report-fix-review-r2.md`。其余文件（含三份文档、`chat_service.py`、前端全部、规格与复核报告）与本单派出时逐字节相同。
2. 既有测试（基线 `eb9ec55` 里就有的测试文件）一字不改。
3. 不 commit、不 stash、不 checkout、不 reset；不装依赖；不读 `.env`、`.env.local`、数据库文件；不访问外网；不调用真实模型。临时脚本放仓库外的临时目录，用完删掉；自检改坏的文件用你读到的原文写回。
4. 你实测到的事实优先于本单的断言，不符就停下来说明。任何情况下不回滚已完成的工作。

## 三、自检

逐一改坏、跑 `tests/test_discuss_chat_*.py`、还原，写明哪条用例 `failed`：

1. 把第一节第 1 条的 `try/except` 去掉。
2. 三份文档的隐私段、ARCHITECTURE 的清理段，每段各删一句（每份文档至少两处，挑不同位置的句子）。

## 四、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `backend/`：`tests/test_discuss_chat_*.py` 全部通过、0 跳过。
2. 在 `backend/`：全量 0 失败、0 跳过，通过数 = 8696 + 本期新用例总数。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只在第二节第 1 条的清单里。
4. `git diff -- backend/tests`：既有测试仍只有 `test_empty_states_settings_privacy.py` 那两处数字。

报告不写本机绝对路径：改了什么、新用例各钉住什么、自检表、验收四条的命令与输出摘要。最后一条回复给出变更总结五项。
