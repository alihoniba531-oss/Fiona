# 小说工坊 P0 第 4 轮独立复核（R3-1 失效 ID 剔除 + 07 默认 DeepSeek 改 flash）

复核对象：工作树 `.worktrees/fiona-novel-p0`，以 `scratchpad/snap-r3/`（R3 改前）与 `snap-r4/`（07 改前）为基线做三向 diff。全程离线：未运行真实提供方、未读密钥、未联网、未读写 `outputs/`、未改仓库内任何文件（仅写本文件）。所有命令在 `backend/` 下用 `Fiona/backend/.venv/bin/python`，带 `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`。

## 结论：通过

两份需求均按字面落实，完结守卫未放宽，测试纪律符合授权范围，没有发现会让真跑白花钱或让结论不可信的新问题。下列「可优化项」均不阻断。

## 改动面（diff 实测）

| 阶段 | 文件 | 变化 |
| --- | --- | --- |
| R3（snap-r3 → snap-r4） | `novel/schemas.py` | `validate_decision` 回收清单段重写：按圣经状态分 open/resolved/不存在，剔除后写回规范化副本，顶层新增 `warnings` |
| R3 | `novel/report.py` | 每章推演摘要在「合并说明」后增加「裁决警告」表（字段/ID/原因），无 warnings 不出现 |
| R3 | 新增 `tests/test_novel_r3_schemas.py`、`test_novel_r3_report.py`、`test_novel_r3_integration.py` | 共 26 项 |
| 07（snap-r4 → 当前） | `novel/pilot_configs/exp{A,B,C}.json` | 仅 `writer`、`character_advocate` 两行 ×3 由 `deepseek:deepseek-v4-pro` 改为 `deepseek:deepseek-flash`，其余字节不变 |
| 07 | `novel/README.md` | 新增一段说明切换原因与「不设白名单、v4-pro 仍可选」；Ark 段「默认配置保持原样」改为「默认未采用豆包」 |
| 07 | 新增 `tests/test_novel_deepseek_flash.py` | 8 项 |
| 授权例外 | `tests/test_novel_schemas.py` | 仅 `test_decision_end_guards_and_fields[unknown_resolution]` 分支新增 7 行期望（见「测试纪律」） |
| 授权删除 | `tests/test_novel_r3_integration.py` | 删除 `test_real_final_decision_replays_without_modifying_evidence`、`EVIDENCE` 常量及其专用 `validate_decision` 导入 |

`novel/llm_router.py`、`pilot.py`、`deliberation.py` 等其余模块与 snap-r3 逐字节一致。`git status --porcelain` 无 `M` 条目。

## 逐条核验

### 1. R3-1 失效 ID 剔除与完结守卫

**实现读查**（`schemas.py:315-359`）：

- `foreshadow_statuses` 取圣经全部伏笔的 `id→status`；`open_foreshadows` 只含 `status=="open"`。
- `requested = c.strings(..., nonempty=True)` 先做类型/非空校验；`requested_ids` 过滤为字符串后，**在剔除之前**用 `len(requested_ids) != len(set(requested_ids))` 判「ID 不得重复」——不论该 ID 是 open、resolved 还是不存在，重复都报错，满足「同一 ID 写两次仍失败」。
- 剔除规则：`key in open_foreshadows` 保留，否则记 `{"field":"beat_sheet.foreshadowing_resolve","id":key,"reason":"已回收"|"不存在"}`，原因按 `foreshadow_statuses.get(key)=="resolved"` 判。格式与返修单逐字一致。
- `beat["foreshadowing_resolve"] = resolved`、`root["warnings"] = warnings` 都写在 `_normalized_copy` 的副本上，模型若自带 `warnings` 字段会被覆盖（`test_valid_open_resolutions_keep_order_and_have_no_model_warnings` 用字符串值验证）。
- 完结守卫 `schemas.py:356-359` 用剔除后的 `resolved` 计算 `unresolved_major`，任一不在 `handling_ids` 即失败；`unresolved_major_handling[i].id` 仍必须 `in open_foreshadows`（`schemas.py:348`），未放宽。

**测试运行**：`tests/test_novel_*.py` → `742 passed in 2.58s`，退出 0。

**正控**（剔除后仍有未处理 major）：`test_end_still_rejects_open_major_after_pruning` 构造 `resolve=["F002"(resolved),"F999"(不存在)]`、`ending_status=end`、无 handling，F001(open major) 剩下 → 断言 `ValidationError` 含「每条未回收的主要伏笔」。另有 `test_end_accepts_explicit_open_major_handling_after_pruning` 证明给了 `leave_open` 后通过且 warnings 两条。

**变异验证**（在 scratchpad 隔离副本 `mut/` 上逐个变异、每次跑全部 742 项、自动还原；已用 `novel.schemas.__file__` 证明导入的是副本；还原后基线 742 passed）：

| 变异 | 结果 |
| --- | --- |
| M1 重复检查挪到剔除之后（只查 open ID 的重复） | 3 红：`test_duplicate_resolution_ids_remain_errors_for_every_status[F002]`、`[F999]`、R3 集成测试 |
| M2 去掉完结守卫（`if False and any(...)`） | 3 红：`test_end_still_rejects_open_major_after_pruning`、既有 `[missing_major]`、`test_novel_pilot.py::test_major_foreshadowing_requires_resolution_or_explicit_reason` |
| M3 守卫改用剔除前清单 `requested_ids` | **0 红（742 passed）**——这是行为等价变异：剔除只移走非 open 的 ID，而守卫只看 open major，所以「剔除前/后」对守卫没有差别。说明复核单举的这条示例变异本身不构成削弱；真正削弱守卫的 M1/M2 都被抓住 |
| M4 warnings 原因「已回收/不存在」互换 | 4 红（R3 两项 + 集成 + 既有 `[unknown_resolution]`） |
| M5 不剔除（写回 `requested_ids`） | 4 红（同上组合） |
| M6 report.md 不展示 warnings | 2 红：`test_report_lists_each_normalization_warning_in_its_chapter`、R3 集成测试 |

**report.md 展示**：`report.py:155-156` 在 `decision.get("warnings")` 非空时输出「裁决警告：」+ 三列表；`test_novel_r3_report.py` 验证表头、两行内容、位置在「摘要」之前，且旧记录（无 `warnings` 键或空列表）不出现该段。R3 集成测试进一步验证 warnings 从 `03-decision-editor.json.result` → `chapter_record.meeting.decision` → `report.md` 全链路落盘，且 writer/reviewer/archivist 收到的 `beat_sheet.foreshadowing_resolve` 已是剔除后的 `["F001"]`，档案 `foreshadowing_resolved` 只含 F001。

### 2. 07 默认 DeepSeek 改为 flash

- `grep -rn deepseek-v4-pro backend/novel/pilot_configs` 无输出；改前快照 snap-r4 下 `novel/` 内 `deepseek-v4-pro` 仅三份配置 6 处命中，README/提示文本/其他源码本来就没有，故 README 只需新增说明（已加）。`02-spec.md` 未动。
- 三份配置 `writer` 与 `character_advocate` 均为 `deepseek:deepseek-flash`（diff 与 `test_default_configs_use_deepseek_flash[A/B/C]` 双重确认）。
- 白名单：`llm_router.py:23` `MODEL_ALLOWLISTS = {"ark": ...}` 仅含 ark；`parse_model` 只对 ark 查白名单。`test_deepseek_models_remain_selectable_without_allowlist` 参数化 `deepseek-flash / deepseek-v4-pro / custom-deepseek-model` 全部可解析可校验。
- **独立 MockTransport 截获**（我自己写的 `scratchpad/review4-capture.py`，清空 `os.environ` 只放占位 key、禁 socket，经 `LLMRouter._single_real_call` 走真实 OpenAI SDK 序列化）：
  - json：`https://api.deepseek.com/chat/completions` `{"model":"deepseek-flash","thinking":{"type":"disabled"},"response_format":{"type":"json_object"}}`，无 `enable_thinking`
  - markdown：同 URL，`thinking` disabled，**无** `response_format`
- 新测试 `test_deepseek_flash_sdk_disables_thinking_and_sets_json_format_only_for_json[json/markdown]` 断言同样内容，并核对 base_url、Bearer 头、max_tokens、messages、usage 归一化（含 `prompt_cache_hit_tokens→cached_tokens`）。
- 变异 M7（去掉 `thinking disabled`）→ 14 红（2 项 flash + 12 项既有 ark）；M8（markdown 也传 response_format）→ 7 红；M9（expB 写手改回 v4-pro）→ 1 红 `[B]`。测试确实在咬。
- 三份默认配置 dry-run（输出 `scratchpad/review4-{A,B,C}`，C 以 A 为 `--source-run`）均退出 0，manifest `status=completed, dry_run=true`，`agents` 中 deepseek 两角色均为 flash。

### 3. 测试纪律

- snap-r3 → snap-r4：17 份既有测试零 diff，仅新增 3 份 R3 测试。
- snap-r4 → 当前：既有测试仅 `test_novel_schemas.py` 一处，新增 7 行：在 `unknown_resolution` 分支调用校验器、断言 `foreshadowing_resolve==[]` 与 `warnings==[{...F999,不存在}]` 后 `return`。**原输入（chapter=8、normal、`["F999"]`）与其余 11 个参数分支及 `pytest.raises` 断言未动**，与验收方授权完全一致。
- 删除的 `test_real_final_decision_replays_without_modifying_evidence` 在 snap-r3 中不存在、snap-r4 中存在，确属本轮新增；它读的是 `/Users/yangjing/Desktop/ai-workspace/outputs/.../03-decision-editor.json`，正是「读仓库外文件」的那条。随之删除的 `EVIDENCE` 常量与 `validate_decision` 导入均只服务于它。
- `grep -nE "/Users/|outputs/|ai-workspace|Desktop" tests/test_novel_*.py` 无命中。残余 `/tmp` 字面量 3 处（`test_novel_store.py:17`、`test_novel_r1_pilot_report.py:150,166`）均是「路径逃逸必须被拒绝」的参数化输入，不读文件。
- 03-report 中「742 passed」「三配置除 6 处替换外字节不变」「README 原无旧型号」三项声明均与我的实测一致。

### 4. 是否引入让真跑白花钱 / 结论不可信的新问题

未发现。逐项排查：

- warnings 只进 `step.result`、`chapter_record` 与 `report.md`；`history.append(decision)` 的 history 在 `context.chapter_mode` 只读 `ending_status`，`build_writer_context` 只取 `beat_sheet`，所以 warnings 不进任何提示词，不增加 token。
- 失效 ID 不再触发「一次修正重试」，正是本单要修的卡死点（主编重试仍写 F011 → 全书停在末章）；现在一次通过，少一次裁决调用。
- 配置哈希（`run_store.configuration_hash` 含 `agents`）：用新默认配置指向旧 expB 目录会被 `配置已变化，请换一个 --out` 拒绝，不会静默混用两个 DeepSeek 型号续跑。
- 价格文件缺 `deepseek-flash` 条目时，成本表显式标「部分模型未提供价格」，不会算错或静默为 0。
- DeepSeek `json_object` 要求提示里出现「json」字样：`agent_pool.DECISION_SCHEMA` 等 JSON 角色提示本来就写「只返回 JSON」，与 v4-pro 时相同。

## 阻断问题

无。

## 可优化项（不阻断）

1. **续跑旧 expB 需用原配置**：真跑实验 B 的 manifest 里 `config` 仍是 v4-pro；作者续跑时必须用与 manifest 一致的配置文件（可从 `manifest.json.config` 抽出），直接用新默认 `expB.json` 会被哈希拒绝。建议在 README 或 03-report 的「待人工确认」里把这一步写成可操作的命令，避免作者真跑时才发现。
2. **价格文件补 flash 条目**：07 单给出的官方价（高峰 0.30/1.20、非高峰 0.15/0.60 USD/百万）需要作者写进自己的 `--prices` 文件的 `deepseek-flash` 键，否则 cost.md 对写手/代言人这两大头只显示「未提供价格」。
3. **reason 的兜底**：当前 `status` 只有 open/resolved（`bible.py:46,75,79`），`"resolved" 以外一律记「不存在"` 是对的；若日后新增第三种状态（如「放弃」），该分支会误报「不存在」，届时应改成按状态映射。
4. **非末章的幻觉 ID 不再被纠正**：按规格，普通章里回收一个不存在的 ID 现在只记 warning、不回炉；warning 只出现在 report.md 每章摘要里。若作者希望一眼看到全书出现过多少次此类情况，可在 manifest `completion` 里加一个 warnings 计数——属于规格外的加分项。
5. **真实 F011 证据回放已无自动化覆盖**：删除外部证据测试后，「真 raw_response 下 F011 被剔除」只由 03-report 的回放日志背书；可移植的 FakeLLM 集成测试用「resolved + 不存在」同形状输入在 final 模式下覆盖了同一路径，我认为足够，但作者若要留档，可把那份 raw_response 脱敏后放进 `tests/fixtures/`（它不含密钥，只是裁决 JSON）。
6. 复核单示例变异「守卫在剔除前计算」是行为等价变异（见 M3），后续复核若再用它做正控会得到假阴性；应改用 M1/M2 这类真正削弱守卫的变异。

## 复核产物位置

- 变异脚本与隔离副本：`scratchpad/mut/run_mutations.py`、`scratchpad/mut/{novel,tests}`
- 独立请求截获脚本：`scratchpad/review4-capture.py`
- dry-run 输出与日志：`scratchpad/review4-{A,B,C}/`、`scratchpad/review4-{A,B,C}.log`
