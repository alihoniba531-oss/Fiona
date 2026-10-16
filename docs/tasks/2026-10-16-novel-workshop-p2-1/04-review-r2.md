# 小说工坊 P2.1 独立复核记录（第 2 轮）

> - 复核对象：分支 `novel-p2-1`，基线 `2979e2d`，未提交改动（本轮相对第 1 轮新增 `runner.py` F1 重放段、F2/F3 小改、4 个 `test_novel_p21_fix_r1_*.py`、裁定后同步的两处测试期望）。
> - 复核范围：**只核验第 1 轮必须修复项 M1 是否真正修好、有无回归**；依据 `04-review.md`（M1）、`05-fix-r1.md`（F1 修法与授权范围）、完整 diff 与工作树源码；`03-report.md` 只作线索。其他新发现只列为「可优化」。
> - 未修改仓库任何文件（本文件除外），未执行 npm install/build/dev，未用浏览器，未联网，未读 `.env`。所有探针放在 `scratchpad/p21-review/`。
> - 复核日期：2026-10-16。解释器 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，目录 `backend/`，环境变量 `DASHSCOPE_API_KEY/DEEPSEEK_API_KEY/ARK_API_KEY/OPENAI_API_KEY=placeholder PYTHON_DOTENV_DISABLED=1`。

## 结论：通过

M1 已按返修单 F1 的修法修好：`_rearchive` 重建后按版本升序重放本章原归档之后的 `user_edit` 版本，每个版本只与其紧邻前一版比对三个白名单字段，按人物 id 叠加，重建结果里没有的人物跳过。原复现探针由 `USER EDIT LOST` 变为 `USER EDIT SURVIVED`；我另写的三个边界探针（同一章连续两次重新归档、两次 PATCH 不同字段、两章书跨归档 PATCH）在现版全部通过，把 `_rearchive` 在内存中换回旧逻辑后全部失败，证明探针和新测试都能分辨。`runner.py` 的改动只在圣经重建段，状态机、暂停原因、计费、`run_token` 写法与基线逐行相同；其他文件本轮改动只对应 F2/F3。`tests/test_novel*.py` 1382 passed；后端全量（排除 6 个已知沙箱端口用例所在的两个文件）5236 passed，总数 5251 = 基线 5223 + 新增 28。

没有「仍需修复项」。有一条由修法本身带来的窄路径副作用（可优化 1），建议下一轮顺手加一行名字守卫。

## M1 核验

### 1. 新逻辑（`backend/novel/runner.py:392–415`）

| 核验点 | 结论 | 证据 |
|---|---|---|
| 选取范围 `version > original.version AND source='user_edit'`，按版本升序 | 符合 | `:402–403`。`original` 仍是本章首个 `archive:{chapter}`（`:371–372`），`previous` 仍是 `original` 之前最近一版（`:373–374`），重建底本未变。 |
| 每个版本与**紧邻前一版**比对 | 符合 | `:398–401` 用 `previous.version = (SELECT MAX(version) ... WHERE version < edited.version)` 关联，不依赖版本号连续；探针 V1 用同一条 SQL 实测第二次重新归档时的选取为 `[(4,3),(6,5),(7,6),(8,7)]`。 |
| 只叠加 `appearance / personality / motivation` 中有变化的字段 | 符合 | `:413–415`，与 `CharacterEdit` 白名单（`service.py:81–83`）一致；未碰 `name`、`world_rules`、`dynamic.*`。探针 V2 把重建结果与「同样流程但不 PATCH」的对照书逐字段比较：除被改的 4 个字段外整本圣经相等（`PASS rest of bible ... identical`）。 |
| 按人物 id 叠加，重建结果中不存在的人物跳过 | 符合 | `:404`、`:409–411`；`test_novel_p21_fix_r1_runner.py:178` 用例：归档新增的 C3 被 PATCH 后，重新归档不再产生 C3，结果 `set == {"C1","C2"}` 且 C1 的编辑仍在。 |
| 同一人物多次修改：后者覆盖前者、不同字段各自保留 | 符合 | 探针 V1：v4 改外形=A、v6 改动机、v7 再改外形=B、v8 改 C2 性格 → 最终外形=B、动机保留、性格=重建原值、C2 性格保留（4 条 PASS）。测试 `:159` 同类断言。 |
| 同一章连续两次重新归档 | 符合 | `original` 只认 `archive:N`，`rearchive:N` 不会改变底本（`:371`）；第二次时 v4 对 v3 得到首次编辑、v6 对 v5（v5 = 首次重归档结果，已含 v4 的重放）只得到新增编辑，不会重复叠加也不会被 v5 吞掉。探针 V1 第二次重归档后版本来源为 `[..., 'user_edit','rearchive:1','user_edit','user_edit','user_edit','rearchive:1']`，内容正确；旧代码下同一探针 4 条 FAIL。 |
| `original` 之前的 `user_edit`（立项确认 v2）不重放 | 符合 | `edited.version > ?`（`:402`）；探针 V1/V3 打印的选取集均不含 v2。立项确认后的任何版本本来就在 `previous` 底本里，不需要也不应重放。 |
| 更早章节归档之后、本章归档之前的 PATCH | 符合（在底本中） | 探针 V3（两章、`per_chapter`）：PATCH#1 在 `archive:1` 与 `archive:2` 之间（v4），PATCH#2 在 `archive:2` 之后（v6）；重归档第 2 章时底本=v4、选取仅 `[(6,5)]`，两次编辑都在，且第 1 章摘要仍在圣经中。旧代码下 PATCH#2 丢失、PATCH#1 保留，与分析一致。 |
| 前一版本缺失 / 人物在前一版本中不存在 | 可接受 | 前者不可能发生（`original` 自身就是更低版本，INNER JOIN 至多丢弃该行）；后者 `previous_characters.get(id, {})`（`:412`）会把三字段全部视为变化而复制，但 `update_character` 总是在当前最新版上整体复制再改（`service.py:320–329`），`user_edit` 版本里不会出现其前一版没有的人物，此分支实际不可达。测试 `:193` 还覆盖了中间插入非 `user_edit` 版本、版本号有间隙、人物数组倒序的情形。 |
| 重放后的圣经仍通过校验 | 符合 | 叠加的值都是已持久化的 `user_edit` 版本里的字符串，写入时已过 `compact() >= 20`（`service.py:327–328`）与 `CharacterEdit` 非空/去空白（`service.py:33–34, 81–83`）校验；`apply_archive` 的 `validate_archive` 在重放之前已完成，重放不改变结构。 |
| 版本号与 `source` 写法未变 | 符合 | `:416` `book["bible_version"] + 1`、`:428–429` `f"rearchive:{chapter}"`，与 `git show 2979e2d` 逐字相同。 |

### 2. 授权范围

- `runner.py` 相对 `2979e2d` 只有两处：`:386–387` 的 `require_new_appearance=True`（第 1 轮已有，对应规格 T2），`:392–415` 本轮新增重放段。`:416–435`（状态、`pause_reason`、`locked_conflict` 置暂停、flags、`run_token=CASE WHEN ... 'running'`、三条写库语句、返回值）与基线逐行相同。计费不在此函数内，本轮也未碰 `billing.py`、`llm_router.py`。
- 用第 1 轮留存的 `p21-tracked.diff` 与当前 `git diff 2979e2d` 做 diff-of-diffs，本轮新增改动只有：
  - `agent_pool.py:123` 追加「或符合前述唯一例外（payload 含 adaptation_blocking=true 时的硬约束）。」，原句未动 —— F2。
  - `service.py:314–315` `failed` 分支文案 —— F3.2；`:318–328` 人物存在性判断移到外形长度校验之前 —— F3.1；`:554–555` stale 标注位置按 `first.startswith('# ')` 决定 —— F3.6。
  - `BiblePanel.tsx:22–26` `previousEditable` 守卫清草稿 —— F3.4；`:33–36, 48, 55` 双边 trim、无变化返回「没有改动」并以 `role="status"` 显示 —— F3.5；`:29, 56` 只显示四个已知状态键 + 「最近出场：第 n 章」—— F3.7。
  - `NovelWizard.tsx:191` solo 模式说明文案 —— F3.3。
  - `schemas.py / writing.py / routers/novel.py / NovelWorkbench.tsx / lib/novels.ts / 三份文档` 本轮零变化。
- 测试文件：4 个 `test_novel_p21_fix_r1_*.py` 与第 1 轮复核留存的裁定前快照逐字节相同；`test_novel_p21_schemas.py`、`test_novel_p21_writing.py` 哈希不变（`78b9da1`、`c16c7a6`）。`test_novel_p21_service.py:178`（failed 文案）与 `test_novel_p21_frontend.py:120–121, 129–131, 137–146, 152–158`（纯空白输入改为「没有改动」并新增严格断言）有改动，内容与返修单 F3.2/F3.5 的新语义一致、范围最小；报告称已获作者裁定，裁定本身无法从工作树核实，由验收方确认即可。基线既有测试 `git diff 2979e2d --stat -- tests/ novel/bible.py novel/store_db.py novel/fake_llm.py frontend/package.json` 为空。

### 3. 测试质量（`backend/tests/test_novel_p21_fix_r1_runner.py`）

- 真实路径：PATCH 走 FastAPI 客户端 `self.client.patch("/novels/{id}/characters/{cid}")`（`:79`），改稿走 `service.edit_chapter`（`:86`）→ `start_novel` → `_advance` → `_rearchive`；`router_factory` 换成离线 dry_run 路由（`:114`），`LLMRouter._single_real_call` 打桩为 `AssertionError`（`:112`）。
- 能在旧代码上失败：用 pytest 插件在收集结束后把 `novel.runner._rearchive` 在内存中替换（不改任何仓库文件），两种旧变体都跑：
  - `baseline`（`2979e2d` 原文）：`5 failed`，首条 `AssertionError: user edit lost for C1.appearance`；
  - `strip`（现版去掉 `:392–415` 重放段，隔离 T2 的 `require_new_appearance` 改动）：`5 failed`，同样 5 条。
  现版 `5 passed`。
- 无空集恒真：`FIELDS` 是常量三元组；两组 `parametrize` 都非空（`:122–125`）；`:154` `assert rebuilt == expected` 为整本圣经严格相等，`:150` `rebuilt["dynamic"] != original["dynamic"]` 防止用旧动态区蒙混；`:178` 用例先断言 `"C3" in ...` 再断言重建后不在。

### 4. 探针

均在 `/private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/8c7c9461-074c-48c4-aa9b-bbaaef19ee71/scratchpad/p21-review/`：

| 文件 | 场景 | 现版 | 旧代码（`OLD_REARCHIVE_MODE=strip/baseline`） |
|---|---|---|---|
| `probe_rearchive.py`（第 1 轮原探针，未改） | PATCH 外形+动机 → 改最新章 | `versions: [(1,'setup'),(2,'user_edit'),(3,'archive:1'),(4,'user_edit'),(5,'rearchive:1')]`，`USER EDIT SURVIVED` | `USER EDIT LOST` |
| `probe_v1_double_rearchive.py` | 同一章连续两次重归档；同字段改两次；中间改另一字段与另一人物；核对选取集 | 8/8 PASS，`V1 RESULT: USER EDITS SURVIVED` | 4 FAIL（外形、后写值、动机、C2） |
| `probe_v2_two_patches.py` | 两次 PATCH 不同字段 + 第三次改 C2，一次重归档；与未 PATCH 对照书整本比对 | 6/6 PASS，`USER EDITS SURVIVED` | 5 FAIL |
| `probe_v3_multichapter.py` | `per_chapter` 两章书，PATCH 分别落在 `archive:2` 前后，再改第 2 章 | 4/4 PASS，`USER EDITS SURVIVED`；选取集 `[(6,5)]` | PATCH#2 FAIL、PATCH#1 PASS |
| `probe_v4_new_character_id_reuse.py` | 第 1 章归档新增「临时证人」(C3)，PATCH C3，改稿后重归档新增的是另一人「老张」(也被编为 C3) | 老张的外形与动机被替换成给临时证人写的值（见可优化 1） | 不适用（旧代码下 C3 与编辑一起丢失） |

辅助文件：`old_rearchive_plugin.py`（内存替换 `_rearchive`，`-p old_rearchive_plugin` 或 `install()`）、`probe_common.py`（离线 FakeLLM + 临时库 + 辅助函数）。

## 仍需修复项

无。M1 已修好，未发现回归。

## 可优化项（不阻断）

1. **按位置分配的人物 id 复用时，重放会把编辑嫁接到另一个新人物上**（修法本身的窄路径副作用）。新增人物 id 由 `_next_number` 顺延分配（`bible.py:80–83`），本章归档新增的 C3 被作者 PATCH 后，若改稿后的重新归档产生的是另一位新人物，它也会得到 C3，`:409` 按 id 命中，`:413–415` 把原给旧 C3 写的外形/动机覆盖上去（探针 V4 实测：「老张」拿到了「临时证人」的外形与动机）。基线代码下此路径是「C3 与编辑一起消失」，现版变成「值落在错的人身上」，可见、可再 PATCH，但属静默写错。而 T2 的典型用途恰是给归档新增人物补外形，此路径并非极罕见。建议在 `:409–411` 之后加一行名字守卫：`if target.get("name") != character.get("name"): continue`（作者不能改名，`user_edit` 版本里的名字必然等于原归档的名字），一行即可、不影响其他分支；或改为以 `original` 版本之前的底本是否含该 id 判定是否为「本章新增人物」再比名字。
2. 同一机制的反向情形：被编辑的新人物在重新归档后换了 id（例如原归档新增 C3、C4，作者改 C4，重归档只剩同名的 C3），按「重建结果里不存在则跳过」会丢弃该编辑。符合返修单字面，若做第 1 条的名字守卫，可顺带用名字做回退匹配。
3. `:395–403` 每次重新归档都把本章归档之后的全部 `user_edit` 版本及其前版整份 JSON 读出并解析，复杂度随 PATCH 次数线性增长；书级规模下可忽略，只记录。
4. 两处旧测试期望的变更（`test_novel_p21_service.py:178`、`test_novel_p21_frontend.py:120–121`）依据报告中的「作者裁定」，与返修单红线「已有的断言只能收紧」字面有出入；内容与 F3.2/F3.5 新语义一致，建议验收方在合并说明里记一笔裁定来源。

## 复核过程记录

- 工作树：`git status` 显示 14 个跟踪文件修改 + 8 个新测试文件 + 本任务目录；HEAD `2979e2d`。
- 命令与结果（均在 `backend/`，解释器与环境变量见文首）：
  - `-m pytest -q -p no:cacheprovider tests/test_novel_p21_fix_r1_runner.py` → `5 passed`。
  - `PYTHONPATH=scratchpad/p21-review OLD_REARCHIVE_MODE=baseline ... -p old_rearchive_plugin tests/test_novel_p21_fix_r1_runner.py` → `5 failed`；`OLD_REARCHIVE_MODE=strip` → `5 failed`。插件在 `pytest_collection_finish` 中以 `exec(..., runner.__dict__)` 替换函数并断言 `co_filename`，输出 `[old_rearchive_plugin] installed mode=...`。
  - `-m pytest -q -p no:cacheprovider tests/test_novel*.py` → `1382 passed`（第 1 轮 1354 + 本轮 28）。
  - `-m pytest -q -p no:cacheprovider --deselect tests/test_exchange_isolation.py --deselect tests/test_safe_http_deadline.py` → `5236 passed, 15 deselected`（被排除的两个文件只含沙箱禁止回环 bind 的用例，与本单无关）。
  - 原探针与 V1–V4 的运行输出见上表；V1–V3 另以 `OLD_REARCHIVE_MODE=strip` 复跑确认会失败。
- 范围核对：`diff p21-tracked.diff r2-tracked.diff` 隔离本轮改动；`snap-before-ruling/` 与当前 8 个 P2.1 测试文件逐个 `diff`；`git hash-object` 核对哈希。
- 未做：浏览器截图走查、`npm run build`、真实厂商模型验证（均不在本轮范围）。
