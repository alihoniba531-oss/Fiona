# 小说工坊 P2.1：面向短剧改编的四项改进

> - **任务等级**：L2，常规功能，不改变产品方向。规格经作者确认后再派给实施方。
> - **工作目录**：Fiona 仓库工作树 `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-novel-p0`，分支 `novel-p2-1`，基于 main `2979e2d`。下文路径都相对于仓库根目录。
> - **建议来源**：同一作者的「短片工作室」会话。工作室会在进程内只读调用 `backend/novel/service.py`，读取已完成的书并改编成 AI 短剧。作者在 2026-10-16 拍板做以下四项：
>   - 第 1 条（可选「要改编短剧」）
>   - 第 2 条（配角必须写外形）
>   - 第 3 条，作者改为「导出时标注待复核，不跳过」
>   - 第 5 条（查找与按范围读取）
>
>   地点表 / 道具表、定稿锁 / 改稿留版本这两项放到 P3，本单不做。

## 0. 背景与已定决策

小说工坊的用法：用户只给一个故事思路，多个智能体按章推演并写作，写完可以改编成 AI 短剧。本单的四项改进都是为了让书更适合改编。

已定决策（作者可以在派单前改）：

- **D1**：「要改编短剧」默认**不勾选**。这是作者原话「建书时可选」的字面含义。勾选后每章会多一次顾问调用，审校阻断可能导致更多重写，费用会上升。
- **D2**：勾选后，自动勾上「短剧改编顾问」，模型按向导现有规则默认为可选列表的第一项。用户仍然可以手动取消这位顾问。取消勾选「要改编短剧」时，不自动移除这位顾问。
- **D3**：「要改编短剧」建书后不能修改。本单不改 PATCH，以后需要再加。
- **D4**：人物外形「立项后可补改」只在书没有运行时允许，包括：等你审阅、等你确认细纲、等你确认完结、已暂停、已完结。可以修改的字段只有外形、性格、动机。

## 1. 修改范围

**可以修改**：

- `backend/novel/service.py`：
  - `CreateNovel` 新增字段；
  - export；
  - 新增人物修改函数；
  - 新增两个只读服务函数。
- `backend/routers/novel.py`：新增一个 PATCH 路由。
- `backend/novel/schemas.py`：`_character` 对新人物的外形要求；`validate_review` 新增关键字参数。
- `backend/novel/writing.py`：把短剧标志传给审校的校验和 payload。
- `backend/novel/agent_pool.py`：审校和档案员的提示词。
- `backend/novel/fake_llm.py`：只在离线假模型的输出需要满足新校验时修改。
- 前端：
  - `frontend/lib/novels.ts`
  - `frontend/components/novel/NovelWizard.tsx`
  - `frontend/components/novel/NovelModelFields.tsx`，确有需要时才改
  - `frontend/components/novel/BiblePanel.tsx`
  - `frontend/components/novel/NovelWorkbench.tsx`
- 测试：新增 `backend/tests/test_novel_p21_*.py`。
- 文档：
  - `CLAUDE.md` 的小说工坊一节
  - `README.md`、`docs/ARCHITECTURE.md`：新路由和导出说明
  - `PLAN.md`
  - `docs/tasks/2026-10-16-novel-workshop-p2-1/03-report.md`

**必须保持不变**（短片工作室依赖这些接口，改了会出错）：

- `service.py` 中 `list_books`、`detail`、`bible`、`chapter`、`owned` 的函数签名，以及它们已有返回字段的含义。可以新增字段，不能删除或改名。
- `novel_chapters` 表的列：`body`、`status`、`flags_json`、`meeting_json`、`updated_at`。不新增表，也不新增列。
- 故事圣经 JSON 的结构：`locked.characters[]`（包括 `appearance`）、`dynamic.chapter_summaries`、`arc_summaries`、`character_states`。
- 状态 `completed`、`done`、`stale` 的含义不变。
- P1 的计费、运行器状态机和暂停原因语义不变。
- P0 离线 pilot 的步骤键和流程不变。
- 已有的全部测试：输入和断言一律不改。
- `package.json` 和 lockfile 不改，不加依赖；`globals.css` 已有的令牌不改，不新增颜色和字体。

## 2. 技术约束

- 沿用现有写法：
  - 后端使用 pydantic `Input`（`extra='forbid'`）、`fail(msg, code)`、`owned()`、`BEGIN IMMEDIATE` 事务、`encoded()`；
  - 圣经每次变更都新写一条 `novel_bible_versions`（`source='user_edit'`），并更新 `novels.bible_version`。
- 前端沿用 P2 的组件和令牌：
  - 请求统一用 `lib/novels.ts`；
  - 错误用 `ErrorNotice` 就近显示；
  - 窄屏可点区域 ≥40px，输入框字号 ≥16px；
  - 不出现横向滚动。
- 测试必须离线：不读仓库外文件，不依赖 git 历史，不依赖 `frontend/node_modules`。如果要用 Node，缺包时 `pytest.skip`。

## 3. 任务清单

### T1 建书时可选「要改编短剧」（建议第 1 条）

1. **后端字段**：`CreateNovel` 新增 `drama_adaptation: bool = False`，存进 `config_json`。`detail().config` 会自然带出这个字段。
2. **审校规则**：`schemas.validate_review(data, body, *, adaptation_blocking=False)` 新增关键字参数，默认值保持现有行为。
   - `style` 类问题一律 `blocking=False`，规则不变。
   - `adaptation` 类问题：`adaptation_blocking=False` 时强制 `False`，规则不变；为 `True` 时保留模型给出的 `blocking` 值。
3. **把标志传给审校**（`writing.py`）：审校步骤从 `config.get('drama_adaptation')` 读取标志，并传给 `validate_review`。只有在标志为真时，审校 payload 才加入以下两个字段：
   - `"adaptation_blocking": true`
   - `"adaptation_limits": config["adaptation"]`

   标志为假时，payload 与现在逐字节相同，保证 P0 和已有书不受影响。
4. **审校提示词**（`agent_pool.py` 的 `REVIEW_SCHEMA`）：把「style 和 adaptation 一律 blocking=false」改成：
   > style 一律 blocking=false；adaptation 默认 blocking=false，只有 payload 含 adaptation_blocking=true 时，以下可客观核对的硬约束才判 blocking=true：本章场景数超过 adaptation_limits.max_scenes_per_chapter，或本章出场的主要人物超过 adaptation_limits.max_main_characters。

   并在「只有以下三类问题可以判为阻断」之后补上这一条件类别。

   如果 P0 有冻结的提示词期望（例如 `tests/test_novel_r2_prompts.py`、`test_novel_p1_p0.py`）因此失败：**停下来报告**，不要修改既有测试。
5. **向导**（`NovelWizard.tsx`）：
   - 在第 1 步「改编参数」区域上方，新增复选框「这本书要改编成短剧」，默认不勾选。下方说明文字：
     > 勾选后会请短剧改编顾问参会；审校发现「场景太多、主要人物太多」这类不好拍的硬伤时，会要求重写。每章可能多花一些草莓。
   - 勾选时：
     - 如果「短剧改编顾问」未被选中，且已选顾问少于 5 位，自动选中它；
     - 如果已选满 5 位，就近提示「顾问已满 5 位，先取消一位才能加入短剧改编顾问」，不自动选中；
     - 「改编参数」区域自动展开。
   - 第 3 步的汇总里显示「改编短剧：是 / 否」。
   - 提交请求体带上 `drama_adaptation`。
6. **工作台**（`NovelWorkbench.tsx`）：`config.drama_adaptation` 为真时，页头的状态标签旁边显示一个 `.tag`「改编短剧」。
7. **类型**（`lib/novels.ts`）：在 `NovelCreateInput` 中加 `drama_adaptation?: boolean`。`NovelDetail.config` 的类型就是 `NovelCreateInput & Record<string, unknown>`，旧书没有这个字段，按 false 处理。另外，「改编参数」的 `<details>` 目前是非受控组件；要实现「勾选时自动展开」，需要把它改成受控的 `open`。

### T2 配角也必须写外形（建议第 2 条）

1. **档案员新增人物的校验**（`schemas.py` 的 `_character`）：`new=True` 时，`appearance` 与立项相同，都要求不少于 20 字，计数口径用同一个 `compact()`。
   - 只在 `validate_archive` 校验时生效；`bible.apply_archive` 不加校验。
   - 已有测试 `test_novel_state.py` 直接调用 `apply_archive`，传入外形为「短发」的人物。这条测试必须继续通过。
2. **档案员提示词**（`agent_pool.py` 的档案员卡片或 `ARCHIVE_SCHEMA`）：明确写出「new_characters 每人必须写外形，不少于 20 字，写清发型、体型、衣着或显著特征，便于改编时出角色卡」。
3. **离线假模型**：如果 `fake_llm.py` 产出的 `new_characters` 不满足新规则，补足它的外形文字。
4. **立项后补改人物**：新增服务函数 `update_character(username, novel_id, character_id, data)` 和路由 `PATCH /novels/{id}/characters/{character_id}`。
   - **请求体**：`CharacterEdit(Input)`，可选字段 `appearance`、`personality`、`motivation`，至少要有一个；多余字段返回 422。
   - **允许修改的状态**：`awaiting_review`、`awaiting_plan`、`awaiting_end`、`paused`、`completed`。其他状态返回 409「书正在运行，请先暂停再改人物」。`awaiting_setup` 返回 409「立项阶段请在立项卡里修改」。另外复用 `_check_not_editing`。
   - **校验**：`appearance` 去空白后不少于 20 字（`compact`），否则返回 422「外形至少写 20 个字」。`personality` 和 `motivation` 为非空字符串。人物不存在返回 404。所有权用 `owned()` 校验。
   - **写入**：读取最新圣经，只修改该人物的这三个字段，然后新写一个版本（`source='user_edit'`），并更新 `bible_version`。不修改章节状态，也不标记 stale。
   - **返回**：最新的完整圣经，形状与 `GET /novels/{id}/bible` 相同。
5. **前端**（`BiblePanel.tsx`）：
   - 在「人物卡」块中，每个人物的外形如果为空或不足 20 字，显示提示「外形未写全，改编时需要补」。
   - 在允许修改的状态下，每个人物有一个「修改」按钮。点开后是就近的编辑表单，包含外形、性格、动机三个字段，外形下方显示字数。保存后刷新圣经，错误就近显示。
   - 在运行状态下不显示「修改」按钮。
   - `lib/novels.ts` 新增 `updateNovelCharacter()`。

### T3 导出时标注待复核（建议第 3 条，按作者的改法）

1. **`export()` 的改动**：
   - 仍然导出所有有正文的章节，顺序不变，不跳过。
   - 对 `status='stale'` 的章节，在该章第一行标题（`# 第n章 …`）之后插入一行：
     > 【待复核】前面章节改过稿，本章尚未按新内容复核。
   - 如果全书有待复核的章节，在书名行下方加一行：
     > 本书有 N 章待复核：第 a、b、c 章。
   - 没有待复核章节时，导出内容与现在逐字节相同。
2. 不改变导出的 HTTP 响应头和文件名规则。

### T4 查找与按章节范围读取（建议第 5 条）

只新增 `service.py` 中的两个只读函数，不新增 HTTP 路由。

1. **`find_books(username, query)`**：
   - 返回该用户书名包含 `query` 的书，`query` 先去掉首尾空白，英文字母不区分大小写；
   - 结果形状和顺序与 `list_books` 相同；
   - `query` 为空时返回空列表；
   - 只查当前用户自己的书。
2. **`chapters_range(username, novel_id, start, end)`**：
   - 先用 `owned()` 校验所有权，不属于该用户的书返回 404；
   - 返回第 `start` 到 `end` 章（含两端）中已存在的章节，每章的形状与 `chapter()` 的返回值完全一致，缺失的章跳过；
   - 范围校验：`1 ≤ start ≤ end ≤ 300`，且 `end − start + 1 ≤ 50`，否则返回 422。
3. **实现方式**：`chapter()` 中的单章组装逻辑抽成内部函数供两者共用。`chapter()` 的签名和返回值不能变。

## 4. 测试（新增 `backend/tests/test_novel_p21_*.py`）

- **T1**：
  - 建书时 `drama_adaptation` 默认为 false，为 true 时写入 config；
  - `validate_review` 在两种取值下 adaptation 和 style 的阻断结果（style 永远不阻断）；
  - 用 `fake_llm` 或直接调用 `write_chapter` 的离线路径：开启短剧时，一条 adaptation 阻断问题会触发一轮重写；关闭时不会；
  - 关闭时，审校 payload 中不出现那两个新键；
  - 前端源码断言：复选框文案、汇总「改编短剧」、工作台标签。
- **T2**：
  - `validate_archive` 拒绝外形不足 20 字的新人物，接受 20 字以上的；
  - PATCH 接口覆盖：允许的状态、409（运行中、立项阶段）、422（外形太短、多余字段、空请求体）、404（人物不存在、他人的书）；修改后新版本的 `source=user_edit`、`bible_version` 加 1，且只有这三个字段变化；
  - 前端源码断言：「外形未写全」提示与「修改」入口。
- **T3**：
  - 有 stale 章节时出现标注行和书首汇总行，没有被跳过的章；
  - 没有 stale 章节时，导出与改动前的输出逐字节相同（在测试里用旧逻辑构造期望值）。
- **T4**：
  - `find_books` 的匹配规则、大小写、空查询、只返回本人的书；
  - `chapters_range` 的边界、缺章跳过、越权 404、超过 50 章返回 422，返回形状与 `chapter()` 逐章相等。
- **契约保护**：断言 `list_books`、`detail`、`bible`、`chapter`、`owned` 的签名（`inspect.signature`）与改动前相同。

## 5. 验收（验收方复跑）

1. `cd frontend && npm run lint`：0 个错误，警告不超过 25 条；`npx tsc --noEmit` 无错误；`npm run build` 成功。
2. `cd backend && python -m pytest -q`：全量通过，基线为 5094 passed。在不含 `frontend/node_modules` 的仓库副本中，新增测试 0 failed。
3. `git status --porcelain` 的改动只在 §1 范围内；已有测试文件的 diff 为空；`package.json` 和 lockfile 没有改动。
4. 截图验收由验收方完成：
   - 向导第 1 步勾选「改编短剧」前后；
   - 顾问满 5 位时的提示；
   - 圣经人物卡的「外形未写全」提示和修改表单；
   - 工作台的「改编短剧」标签；
   - 宽度 1440、390、360，昼夜两种主题。

## 6. 何时停下来问

- P0 冻结的提示词或 payload 期望因 T1、T2 的提示词修改而失败。
- 某个既有测试依赖「新人物外形可以为空」并会因此失败。
- 需要修改 §1「必须保持不变」中的任何一项。
- 其他「怎么实现」类问题，由实施方自行决定并在报告中说明。

## 7. 修订 R1（验收方裁定，2026-10-16）

实施方按 §6 停下来，报告了两处与既有测试的冲突。裁定如下：两处都改用不触碰既有测试的写法，既有测试仍然一律不改。

### 7.1 冲突一：T1 审校提示词

`tests/test_novel_r2_prompts.py:97` 冻结了子串「style 和 adaptation 一律 blocking=false」。

- **原句保留不动**，紧接其后追加一条例外条款：
  > 唯一例外：payload 含 adaptation_blocking=true 时，adaptation 类中以下可客观核对的硬约束判 blocking=true——本章场景数超过 adaptation_limits.max_scenes_per_chapter，或本章出场的主要人物超过 adaptation_limits.max_main_characters；其余 adaptation 问题仍为 false。
- 在「只有以下三类问题可以判为阻断」的列表后面，用一句话指向这条例外，不改动原有三条的文字。
- 原句表达的是默认规则，追加的是由 payload 触发的例外，两者不矛盾。P0 离线 pilot 不会发送 `adaptation_blocking`，行为不变。
- 如果追加文字导致其他冻结期望（例如提示词哈希、`test_novel_p1_p0.py`）失败，仍然**停下来报告**。

### 7.2 冲突二：T2 新人物外形

`tests/test_novel_r1_schemas.py` 中的 `new_appearance` 用例要求 `validate_archive` 接受空外形。

- 给 `schemas.validate_archive(data, bible, *, require_new_appearance=False)` 加一个关键字参数，默认保持现有行为：
  - 为 `True` 时，`new_characters[].appearance` 去空白后不少于 20 字，计数用 `compact()`；
  - 为 `False` 时与现在完全一致。
- `_character` 相应地增加参数，由 `validate_archive` 传入。
- **P1 的正式写书路径一律传 `True`**，包括：
  - `novel/writing.py` 中档案员步骤的 validator：当 `config.get("experiment") == "P1"` 时传 `True`，P0 的各 arm 传 `False`；
  - `novel/runner.py:386` 重新归档步骤的 validator：传 `True`。
- `bible.apply_archive` 内部的 `validate_archive(archive, bible)` 调用**保持默认值不变**。它的输入在 P1 路径上已经由上面的 validator 严格校验过；`tests/test_novel_state.py` 直接调用 `apply_archive` 的用例也要继续通过。
- 测试（`test_novel_p21_*.py`）补充以下断言：
  - `require_new_appearance=True` 时拒绝空外形和不足 20 字的外形，接受 20 字以上的外形；
  - 默认值行为不变；
  - P1 写书路径的 validator 确实传了 `True`。可以用离线 fake 路由跑一章，让档案员先返回短外形，断言会被重试或判为失败；P0 arm 则不受影响。

### 7.3 运行环境

- 后端测试解释器用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，在 `backend/` 目录下执行 `-m pytest`。PATH 里没有 `python`，系统自带的 `python3` 也没有装 pytest。
- 前端在 `frontend/` 下执行 `npm run lint`、`npx tsc --noEmit` 和 `npm run build`。`node_modules` 已经就绪。如果 Turbopack 构建因沙箱端口权限失败，补跑 webpack 构建，并在报告中说明。

T3、T4 不受这两处冲突影响，一并实施。
