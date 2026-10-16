# 小说工坊 P2.1 实施报告

## 结果与范围

已按 `02-spec.md` T1–T4 及 §7 修订 R1 完成实现，新增 129 项离线测试。既有测试全部保持不变，没有提交 commit。Lint 为 0 错误、25 警告，TypeScript 和 webpack 生产构建通过；原样 Turbopack 构建受沙箱端口权限限制，后端全量最终结果见检查表，不将环境受限项记为通过。

分支为 `novel-p2-1`，基线及当前 HEAD 均为 `2979e2dee98ad0dda1a6e6c0e24ffff478c2bf0e`。用户提供的 `02-spec.md` 在首次开始时已处于未跟踪任务目录中，本次没有修改规格。

## 修改文件

| 范围 | 文件 | 用途 |
| --- | --- | --- |
| 后端 | `backend/novel/service.py` | 创建配置、人物修改与圣经版本化、导出、查找、范围读取与共享章节组装 |
| 后端 | `backend/routers/novel.py` | 人物 PATCH 路由，沿用门禁和限流 |
| 后端 | `backend/novel/schemas.py` | 审校与档案严格校验的可选关键字参数 |
| 后端 | `backend/novel/writing.py` | 传递短剧开关、条件 payload、P1 档案严格校验 |
| 后端 | `backend/novel/agent_pool.py` | 保留冻结审校原句并追加例外、补充档案员外形要求 |
| 后端 | `backend/novel/runner.py` | 仅按 §7.2 为重新归档 validator 传入严格标志 |
| 前端 | `frontend/lib/novels.ts` | 创建字段、人物 PATCH 类型及请求 |
| 前端 | `frontend/components/novel/NovelWizard.tsx` | 复选框、顾问联动、受控展开与提交汇总 |
| 前端 | `frontend/components/novel/BiblePanel.tsx` | 外形提示、人物编辑、计数、就近错误与刷新期间保留卡片 |
| 前端 | `frontend/components/novel/NovelWorkbench.tsx` | 页头标签、保存人物、采用完整圣经并取消过期请求 |
| 新增测试 | `backend/tests/test_novel_p21_service.py` | 60 项服务/API/导出/查询/签名用例 |
| 新增测试 | `backend/tests/test_novel_p21_schemas.py` | 26 项审校、外形及 R1 默认兼容用例 |
| 新增测试 | `backend/tests/test_novel_p21_writing.py` | 22 项重写、payload、P1/P0 与重新归档用例 |
| 新增测试 | `backend/tests/test_novel_p21_frontend.py` | 21 项源码契约和无依赖 Node 行为探针 |
| 文档 | `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md` | 小说工坊新配置、路由、导出与进程内服务说明 |
| 报告 | 本文件 | 实现、验收结果及首次停止记录 |

共修改/新增 19 个交付文件。`fake_llm.py` 默认输出 `new_characters=[]`，不需要调整；`NovelModelFields.tsx` 复用现有顾问和模型规则，不需要修改。package、lockfile、globals.css、数据库结构、`bible.apply_archive`、计费以及运行器状态机均未修改。

## 实现与自行决定的细节

### T1 建书可选短剧改编

`CreateNovel.drama_adaptation` 默认 false，存入配置，仍不允许通过 PATCH 修改。向导默认不勾选，勾选时按现有可选模型第一项加入短剧顾问；已选满五位时显示指定就近提示，不自动替换其他顾问。取消短剧勾选保留顾问，手动取消顾问也不会被自动重新勾回。改编参数用受控 `open` 展开，汇总显示是/否，工作台在状态旁显示 `.tag`。

只有开关为真，审校 payload 才增加 `adaptation_blocking` 和 `adaptation_limits`；关闭或缺省时，首次与复审、压缩与非压缩两种路径均保持旧 user payload 的 UTF-8 字节。`validate_review` 默认沿用旧行为，开启后仅保留 adaptation 的模型阻断值，style 永远不阻断，证据过滤规则不变。

按 R1 保留冻结原句及三条规则，在原句后追加指定例外，并在列表后指向例外。独自构思模式继续沿用原来的顾问过滤逻辑，不强行改变用户选择的推演方式。

### T2 人物外形与补改

`validate_archive(..., require_new_appearance=False)` 默认完全兼容；P1 写书及重新归档显式开启严格校验，P0 各 arm 和 `apply_archive` 内部调用保持默认。档案员提示词补足外形至少 20 字及角色卡用途。

`CharacterEdit(Input)` 仅接受外形、性格、动机，至少提交一项；显式 null、多余字段、空请求、提交的空性格/动机均拒绝。只有提交外形时才按 `compact()` 校验至少 20 字，部分修改不强迫补齐旧人物未提交的外形。

人物编辑在 `BEGIN IMMEDIATE` 中校验所有权、允许状态和章节编辑互斥，读取当前完整圣经，仅改目标人物的指定字段，写入 `source=user_edit` 新版本并更新 `bible_version`，返回完整圣经和罗盘。章节状态、正文、flags 等不变。paused 但立项尚未生成圣经时，返回 404「人物不存在」，避免空圣经导致 500。

前端仅 PATCH 用户实际改动的字段，无变化则关闭表单。外形字数按 Unicode 码点计数，与后端 `compact()` 一致：移除 Python 空白和中英引号，省略号归一计一字。旧空值不会阻拦其他字段补改。表单沿用 16px 输入字号、至少 40px 按钮及既有令牌。

保存通过工作台原有账号请求与 mutation 机制，采用 PATCH 的完整圣经并取消旧读取。交叉复核补上状态竞争边界：另一标签页恢复运行后 PATCH 返回 409，表单隐藏时仍保留卡片内错误；已有圣经刷新期间保持人物卡挂载，避免丢失草稿和错误。

### T3 导出待复核标注

仍按原顺序导出全部有正文的章节。stale 章节在正文第一行标题之后加入指定待复核行，书名下汇总数量和章号；单行正文也保留。无 stale 时沿用旧逻辑的字节输出。HTTP 导出响应头、Content-Type 和文件名规则保持不变。

### T4 查找与范围读取

`find_books` 先 trim，再用 `casefold()` 做字面包含匹配，复用 `list_books` 的本人摘要和顺序；`%`、`_` 不作为通配符，空查询返回空列表。

`chapters_range` 先 `owned()`，再校验整数范围 1–300、含两端最多 50 章；浮点数和布尔值也返回 422。用单次有序查询跳过缺章，与 `chapter()` 共用 `_chapter_result`，不新增 HTTP 路由。原有五个服务函数的签名保持不变。

## 规格与测试清单逐项对应

以下名称均位于新增 `test_novel_p21_*.py`，没有修改既有输入或断言。

| 规格/测试清单 | 对应新增用例 |
| --- | --- |
| T1 建书默认 false、显式 true 写入配置、建后不可改 | service：`test_create_persists_drama_adaptation_with_default_false` |
| T1 两种开关下 adaptation/style 阻断，默认值与证据过滤兼容 | schemas：`test_review_blocking_respects_opt_in_and_keeps_style_nonblocking`、`test_review_default_still_downgrades_advice`、`test_adaptation_opt_in_keeps_evidence_requirements` |
| T1 开启重写一轮，关闭不重写 | writing：`test_adaptation_blocker_rewrites_once_only_when_enabled` |
| T1 关闭 payload 不含新键且字节一致 | writing：`test_disabled_review_user_payload_bytes_match_legacy_formula`，覆盖缺省/显式 false × 压缩/非压缩 × 首次/复审 |
| T1 前端复选框、汇总与 tag；顾问第一模型、满五、不移除与保留已选模型 | frontend：`test_adaptation_checkbox_copy_summary_and_workbench_tag`、`test_adaptation_toggle_preserves_choices_and_respects_advisor_limit` |
| T2 严格模式拒绝空/短外形，接受 compact 后恰好 20 字和更长外形 | schemas：`test_strict_archive_rejects_missing_or_short_new_appearance`、`test_strict_archive_accepts_twenty_compact_characters` |
| R1 默认值及 apply_archive 兼容、新参数为 keyword-only | schemas：`test_archive_default_and_apply_archive_keep_legacy_appearance`、`test_new_schema_switches_are_keyword_only_and_default_off` |
| R1 P1 validator 严格、P0 各 arm 兼容；持续短外形失败 | writing：`test_only_p1_writing_repairs_short_new_character_appearance`、`test_p1_writing_rejects_repeated_short_appearance` |
| R1 P1 重新归档严格校验 | writing：`test_rearchive_repairs_short_new_appearance_before_persisting`，走真实 service→runner 离线路径，先短外形修复，再落库并核对版本/source |
| T1/T2 提示词约束 | schemas：`test_prompts_explain_adaptation_exception_and_new_character_cards`；既有冻结提示词与 P0 pilot 回归同时通过 |
| T2 PATCH 五种允许状态、版本 +1、source=user_edit、完整圣经、仅三字段变化且章节不变 | service：`test_character_patch_allowed_states_versioning_and_full_bible` |
| T2 PATCH 运行/立项 409、改稿互斥 | service：`test_character_patch_rejects_disallowed_states_without_writing`、`test_character_patch_obeys_chapter_edit_exclusion` |
| T2 PATCH 422：短外形、多余字段、空请求、空字符串、null | service：`test_character_patch_rejects_invalid_fields_without_writing`、`test_character_appearance_uses_compact_twenty_character_boundary` |
| T2 PATCH 404：人物不存在、他人的书、无圣经 | service：`test_character_patch_returns_404_for_missing_or_unowned_records`、`test_character_patch_paused_before_setup_without_bible_returns_404` |
| T2 部分更新不重验未提交旧外形 | service：`test_character_patch_supports_partial_updates_without_revalidating_old_appearance`；frontend：`test_character_patch_validates_only_fields_the_user_changes` |
| T2 前端外形提示、修改入口/允许状态、字数口径、就近错误、完整圣经刷新 | frontend：`test_character_editing_is_local_and_only_available_in_permitted_states`、`test_character_appearance_count_matches_backend_compact`、`test_character_api_returns_full_bible_and_workbench_cancels_old_reads`、`test_character_save_conflict_stays_visible_when_book_resumes_running` |
| T3 stale 标注、书首汇总、不跳章、响应头和单行正文 | service：`test_export_marks_stale_chapters_without_skipping_or_changing_headers`、`test_export_stale_single_line_body_keeps_all_text` |
| T3 无 stale 时按旧逻辑构造期望，逐字节相同 | service：`test_export_without_stale_is_byte_for_byte_old_logic` |
| T4 标题匹配、大小写、空查询、字面通配符、本人隔离与顺序 | service：`test_find_books_matches_literal_trimmed_case_insensitive_titles_and_ownership` |
| T4 范围边界、缺章、逐章返回形状、超过 50、先检查所有权 | service：`test_chapters_range_matches_single_chapter_shapes_and_skips_gaps`、`test_chapters_range_rejects_invalid_boundaries`、`test_chapters_range_checks_ownership_before_range` |
| 五个原有服务签名保护 | service：`test_public_read_signatures_are_preserved`，使用 `inspect.signature` 核对 list_books/detail/bible/chapter/owned |

## 检查结果

后端统一在本工作树的 `backend/` 下使用 §7.3 指定解释器：

```text
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
```

前端统一在 `frontend/` 下执行。测试只使用 fake、本地临时数据库和仓库源码，不调用真实模型，不依赖 git 历史或仓库外测试输入。

| 检查 | 最终结果 |
| --- | --- |
| `npm run lint` | 退出 0；0 errors，25 warnings，满足 ≤25 门槛；小说组件没有新增警告 |
| `npx tsc --noEmit` | 退出 0，无错误输出 |
| `npm run build` | 退出 1；Turbopack CSS 处理子进程绑定本地端口被沙箱拒绝，见单列说明 |
| `NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack` | 最终代码退出 0，编译/TypeScript/静态页面成功，含 `/novels`、`/novels/new`、`/novels/[id]` |
| `python -m pytest -q tests/test_novel_p21_*.py` | 129 passed，29 warnings，5.12s；0 failed/error/skipped |
| 无 `frontend/node_modules` 源码副本中运行同一新增测试命令 | 129 passed，29 warnings，3.64s；0 failed/error/skipped |
| 全部既有 `tests/test_novel*.py`（排除新增 p21） | 1333 passed，29 warnings，22.26s；冻结提示词、P0 pilot、旧空外形和 apply_archive 兼容 |
| 前端新增及既有前端定向回归 | 83 passed，3.30s |
| 全量 `python -m pytest -q -ra` | 退出 1；5211 passed、1 failed、5 errors、6 skipped、29 warnings，138.54s；全部未通过/跳过项均为下列既有回环端口用例 |
| `git diff --check` | 通过 |
| 既有测试/依赖/锁文件/globals.css/bible.py/数据库文件 diff | 均为空；runner.py 只包含 §7.2 指定 validator 参数变更 |

29 条后端警告来自已有 slowapi 对 Python 3.14 的 `asyncio.iscoroutinefunction` 弃用提示。Node 行为探针仅用内置能力，缺少 Node 时允许 skip；本环境及无 node_modules 副本中均实际执行，没有 skip。副本位于 `/private/tmp/fiona-p21-no-node-zqm4amjw`，包含 backend/frontend 源码，已断言不存在 `frontend/node_modules`。

### 沙箱端口问题单列

默认构建输出：

```text
Error [TurbopackInternalError]: [project]/app/globals.css [app-client] (css)
Caused by:
- creating new process
- binding to a port
- Operation not permitted (os error 1)
```

按 §7.3 补跑 webpack 成功，没有更改默认构建脚本、配置、样式或依赖。webpack 是补充构建证据，原命令仍需在允许绑定本地端口的环境复跑。构建实际显示现有 node_modules 的 Next.js 为 16.3.3，package.json 声明为 16.3.8；依照约束没有调整依赖。

后端最终全量共 5223 项，等于规格基线 5094 加新增 129。原始末尾：

```text
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
1 failed, 5211 passed, 6 skipped, 29 warnings, 5 errors in 138.54s (0:02:18)
```

1 个失败停在 `asyncio.start_server(..., '127.0.0.1', 0)` 的 bind；5 个 setup 错误停在共享 `ThreadingHTTPServer` 的 `socket.bind`。全部抛 `PermissionError: [Errno 1] Operation not permitted`，未进入对应业务断言，不涉及小说功能。6 个跳过也由既有测试明确标注端口权限原因：

```text
SKIPPED [2] tests/test_byok_client.py:652: R1-6 loopback bind is denied by sandbox permissions
SKIPPED [4] tests/test_byok_client.py:882: R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun
```

未排除、改写或重标记这些测试，未提权绕过沙箱；本次后端全量不能记为全部通过。最终新增 129 项均通过，P0/P1 小说既有回归也全部通过。最终前端边界修复后重新执行了 Lint、tsc、webpack、新增测试、无 node_modules 副本测试及完整后端全量，以上表格均取最终结果。

机械检查日志保留在 `/private/tmp/fiona-p21-lint.log`、`fiona-p21-tsc.log`、`fiona-p21-build.log`、`fiona-p21-build-webpack-final.log`、`fiona-p21-pytest-new.log`、`fiona-p21-pytest-no-node.log`、`fiona-p21-pytest-full-final.log`。这些为本机临时日志，不属于提交文件。

## 并行实施与约束

三个子代理继承父代理模型和推理档位，未传 model/reasoning_effort：服务/API 独占 service/router/service 测试；写作校验独占 schemas/writing/prompts/runner 及对应测试；前端独占四个前端文件和 frontend 测试。主代理负责文档、全局门禁和范围核对；交叉复核只读，修正仍交回原文件负责人串行完成。

前端修改前已读取 `frontend/AGENTS.md`、Next 内置 `01-app/03-api-reference/01-directives/use-client.md` 和 `01-app/01-getting-started/05-server-and-client-components.md`；主代理另读 `01-app/02-guides/forms.md` 和 CLI 文档中的 webpack 构建选项。没有新增颜色、字体或依赖，没有修改既有测试。

## 首次按 §6 停止的记录

第一次实施在任何实现改动前停止，唯一新增文件为当时的本报告，T1–T4 均未落盘，没有执行 pytest：PATH 中没有 python，当时检查的 Homebrew/system python3 也没有 pytest；未安装依赖、未提交 commit。

停止证据：

1. `backend/tests/test_novel_r2_prompts.py:97` 冻结 `style 和 adaptation 一律 blocking=false`，第 100 行断言提示词含此句，与原 T1 指定替换冲突。
2. `backend/tests/test_novel_r1_schemas.py:99–115` 的 `new_appearance` 参数构造新增人物，将 appearance 设为 None，要求 `validate_archive` 成功归一化为空字符串，与原 T2 全面要求至少 20 字冲突，明确触发 §6 第二条。

用户随后确认验收方在规格中追加 §7 R1：保留冻结原句并追加例外；档案严格校验通过默认 false 的 keyword-only 参数，仅在 P1 写书/重新归档传 true，`apply_archive` 保留默认；并给出现有后端解释器路径。本轮按该修订恢复，不修改既有测试。修改前相关基线 102 passed，修改后冻结提示词/P0/完整 R1 schema/state/workflow 254 passed；两项冲突已消解，未出现新的 §6 停止条件。

## 未完成或待人工确认

T1–T4 没有已知未完成的实现项。仍需验收方：

1. 在允许回环端口绑定的环境原样复跑默认 `npm run build` 与后端全量测试，确认沙箱受限项目。
2. 按规格 §5.4 验收 1440、390、360 宽度、昼夜两主题截图：向导勾选前后、顾问满五位提示、人物外形不足提示及修改表单、工作台标签，并实拍确认无横向滚动。

本次源码与 Node 探针不替代浏览器截图验收；没有运行真实供应商模型或进行真实计费质量验收。

## 第 1 轮返修

### 范围、结果与仍待裁定的冲突

依据 `05-fix-r1.md` 与 `04-review.md` 实施。F1 必修项已修复，原复核探针从 `USER EDIT LOST` 变为 `USER EDIT SURVIVED`；F2 和 F3.1/3.3/3.4/3.6/3.7 已完成，F3.5 已按双边 trim 的新语义落盘。没有使用 git stash，没有提交 commit，没有读取密钥、联网或新增依赖。

两处测试契约冲突已向作者请求裁定，未擅自改动旧测试：

1. **F3.2 尚未实施**：`test_novel_p21_service.py:178` 为 failed 状态固定旧文案「书正在运行，请先暂停再改人物」，`:191` 严格相等断言。返修单要求改为「这本书已出错，不能修改人物」。需明确允许仅同步此期望，或延期 F3.2。
2. **F3.5 新实现与两条旧期望冲突**：原性格/动机为空、草稿仅输入空格或换行时，两边 trim 后没有实质变化，按返修单应不请求并提示「没有改动」；旧 `test_novel_p21_frontend.py::test_character_patch_validates_only_fields_the_user_changes` 的两条参数固定要求「性格和动机都不能为空」。当前保留新实现，旧用例仍失败；需明确允许同步这两条期望，或将此情况裁定为保留旧空值报错的边界例外。没有把这两项失败归因于沙箱。

本节以前的报告内容按字节保持原样，包含首次停止记录。本轮在写文件前保存了工作树文件及全部测试的只读快照 `/private/tmp/fiona-p21-fix-r1-before-wan243si`，用于核对原文件与断言未改；新增测试本身不依赖该快照、复核探针或任何仓库外输入。

### 本轮修改文件

| 文件 | 本轮用途 |
| --- | --- |
| `backend/novel/runner.py` | F1，仅在 `_rearchive` 圣经重建后叠加用户人物差异 |
| `backend/novel/agent_pool.py` | F2，复审冻结原句之后追加例外指向 |
| `backend/novel/service.py` | F3.1 人物存在性前移；F3.6 非标题正文的标注位置 |
| `frontend/components/novel/NovelWizard.tsx` | F3.3 solo 说明 |
| `frontend/components/novel/BiblePanel.tsx` | F3.4 草稿清理、F3.5 无变化提示、F3.7 状态中文显示 |
| 新增 `backend/tests/test_novel_p21_fix_r1_runner.py` | 5 项 F1 反证与回归 |
| 新增 `backend/tests/test_novel_p21_fix_r1_service.py` | 11 项人物存在性及导出位置回归 |
| 新增 `backend/tests/test_novel_p21_fix_r1_prompts.py` | 1 项冻结原句与追加例外回归 |
| 新增 `backend/tests/test_novel_p21_fix_r1_frontend.py` | 11 项前端返修行为与源码契约 |
| 本报告 | 仅在末尾追加本节 |

共 10 个本轮交付文件。旧测试文件（包括上一轮的四个 P2.1 测试文件）与本轮开始时快照逐字节相同；没有放宽旧断言。表结构、五个对外服务函数签名、圣经 JSON 结构、状态机、暂停原因、计费和 `apply_archive` 均保持不变。

### F1 改法与证据

`backend/novel/runner.py:392` 在 `apply_archived_chapter` 得到重建结果之后、版本和数据库写入之前重放作者差异：

- `runner.py:396` 查询同书 `version > original.version AND source='user_edit'` 的版本，按版本升序。
- `runner.py:399` 用 `MAX(version) < edited.version` 关联每个 user_edit 的紧邻前版，支持版本号存在间隙，不把中间归档产生的差异误当用户修改。
- `runner.py:404` 以人物 id 关联重建结果，缺失人物跳过。
- `runner.py:413` 仅比较并叠加 appearance、personality、motivation 的变化值，复制后写入重建对象，不重放人物名称、世界规则或动态区。
- `runner.py:416` 之后原有版本加一、`source=rearchive:n`、章节/状态/暂停原因/计费提交代码未动。

新增 `test_novel_p21_fix_r1_runner.py`：

| 用例/行号 | 证据 |
| --- | --- |
| `:126`，参数 all-three-fields | 真实 FastAPI PATCH 三字段后，改最新章正文并排空 runner；三字段保留，来源以 user_edit/rearchive:1 结尾 |
| `:126`，参数 two-partial-patches | 连续两次 PATCH 不同字段均保留 |
| `:147` 起对照组断言 | 与未 PATCH 的同样重建比较其他人物、整个 dynamic 及其余圣经；同时断言 dynamic 确实不同于原归档，防止简单复用旧动态区蒙混通过 |
| `:159` | 多次重新归档及同字段再次修改，后写值胜出 |
| `:178` | 重建中消失的人物跳过，不凭旧编辑复活人物 |
| `:193` | 紧邻前版含非 user_edit 归档差异、版本间隙、人物数组倒序时仍只重放作者三字段 |

全部通过真实离线 service/runner 路径，FakeLLM 及 `_single_real_call` 拒绝真实调用；重建后的版本、source、其他人物与动态结果均有精确断言。

### 修复前反证输出与原探针

严格按先测试后实现执行：先新增上述 5 项测试，在未修改 `_rearchive` 的代码上运行，保存 `/private/tmp/fiona-p21-fix-r1-counterexample.log`；随后才修改 runner。命令在 backend 下使用规定的虚拟环境解释器：

```text
python -m pytest -q tests/test_novel_p21_fix_r1_runner.py
E           AssertionError: user edit lost for C1.appearance
FAILED ...::test_rearchive_preserves_real_patches_and_matches_unpatched_rebuild[all-three-fields]
FAILED ...::test_rearchive_preserves_real_patches_and_matches_unpatched_rebuild[two-partial-patches]
FAILED ...::test_rearchive_replays_patches_in_version_order_across_multiple_rebuilds
FAILED ...::test_rearchive_skips_edited_characters_absent_from_the_rebuilt_chapter
FAILED ...::test_rearchive_diffs_each_user_edit_against_its_immediate_prior_version
5 failed, 29 warnings in 1.75s
```

修复后，上述 5 项联合已有 P2.1 writing、P1 runner、P0、state 回归为 `76 passed, 29 warnings in 4.16s`。

作者指定的外部探针保持原样，在 backend 下使用四个占位 API Key 和 `PYTHON_DOTENV_DISABLED=1` 实际运行。修复前 `/private/tmp/fiona-p21-fix-r1-probe-before.log` 的末尾：

```text
final appearance: '身形清瘦，黑色齐耳短发，左眉有浅疤，常穿深灰工装外套并佩戴银色发夹。'
final motivation: '保护被抹去的人'
USER EDIT LOST
```

修复后 `/private/tmp/fiona-p21-fix-r1-probe-after.log` 的末尾：

```text
status after rearchive: awaiting_end bible_version: 5
versions: [(1, 'setup'), (2, 'user_edit'), (3, 'archive:1'), (4, 'user_edit'), (5, 'rearchive:1')]
final appearance: '齐肩黑发束在脑后，身形清瘦，穿洗旧的深蓝长外套，左眉有一道浅疤。'
final motivation: '把原件交给证人'
USER EDIT SURVIVED
```

### F2、F3 逐条改法与证据

| 项目 | 改法/文件:行号 | 验证 |
| --- | --- | --- |
| F2 | `agent_pool.py:123`，在原复审整句后追加指定例外指向，原句和默认规则不变 | 新增 prompts 用例精确检查原整句紧接例外；与既有冻结提示词和 P0 测试联跑通过，没有触发停止条件 |
| F3.1 | `service.py:318` 读取圣经并确认人物存在，`:325` 再做业务外形长度校验；HTTP 输入结构仍由原 Pydantic 模型校验 | unknown id + 短外形返回 404，存在人物 + 短外形返回 422，所有失败无写入 |
| F3.2 | 等待作者对旧 failed 文案期望的裁定，当前尚未修改 | 冲突证据见本节开头 |
| F3.3 | `NovelWizard.tsx:191`，solo/critique 分别使用返修单指定说明 | Node 执行实际条件表达式检查两种文案 |
| F3.4 | `BiblePanel.tsx:22`，以 previousEditable 守卫响应权限变化，变 false 时清空 draft | 执行实际状态调整片段，true→false→true 后草稿仍为空；晚到 409 错误保持可见 |
| F3.5 | `BiblePanel.tsx:33` 双边 trim 后比较，`:36` 无变化不请求并返回消息，`:48/:55` 以就近 role=status 显示「没有改动」 | 新增探针覆盖三个字段的首尾空白、真正变化仅 PATCH 改动字段；原空字段纯空白的两条旧期望仍待裁定 |
| F3.6 | `service.py:551` 仅 `first.startswith('# ')` 时插在第一行后，否则加在正文最前 | 覆盖 # 标题、纯正文、空白首行、## 首行、单行与空正文；无 stale 输出保持旧字节 |
| F3.7 | `BiblePanel.tsx:28` 过滤状态键，`:56` 单独显示「最近出场：第 n 章」 | 选择**隐藏未知顶层人物状态键**，已知 location/condition/knows/relationships 复用中文标签，关系内人物 ID 保留；测试断言不修改原 state 对象 |

F2/F3 后端新用例与旧服务、冻结提示词、P0 共 `145 passed, 29 warnings in 3.09s`。前端新返修用例 `11 passed`；另一次旧前端定向回归为 `2 failed, 81 passed in 3.19s`，失败仅是上述 F3.5 两个待裁定期望，日志为 `/private/tmp/fiona-p21-fix-r1-frontend-legacy-conflict.log`。

### 本轮机械检查

后端解释器为 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，cwd 为本工作树 backend。前端 cwd 为本工作树 frontend。原探针以外的新测试只读取仓库内源码/输入，不依赖 git 历史、外部探针或 node_modules。

| 检查 | 结果 |
| --- | --- |
| `npm run lint` | 退出 0，0 errors、25 warnings，无新增警告 |
| `npx tsc --noEmit` | 退出 0，无错误输出 |
| `npm run build` | 退出 1，Turbopack CSS 子进程绑定端口被沙箱拒绝：Operation not permitted |
| `NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack` | 退出 0，包含三个小说路由，编译/TypeScript/页面产出成功 |
| 本轮新增 `test_novel_p21_fix_r1_*.py` | 28 passed、29 warnings，2.42s，无失败/错误/跳过 |
| 无 node_modules 的源码副本中运行本轮新增测试 | 28 passed、29 warnings，3.11s，无失败/错误/跳过 |
| 后端全量 `-m pytest -q -ra` | 退出 1；5237 passed、3 failed、5 errors、6 skipped、29 warnings，133.26s；原因分列于下方 |
| 探针 | 修前 USER EDIT LOST，修后 USER EDIT SURVIVED，前后均为原探针实际输出 |
| 旧测试文件 | 与返修开始时快照逐字节相同，既有测试 git diff 为空 |
| `git diff --check` | 通过 |

29 条 warning 为已有 slowapi 对 Python 3.14 `asyncio.iscoroutinefunction` 的弃用提示。无 node_modules 副本为 `/private/tmp/fiona-p21-fix-r1-no-node-b19cx8xu`，已断言该目录下不存在 frontend/node_modules。

本轮日志统一为 `/private/tmp/fiona-p21-fix-r1-*.log`；没有把临时探针输出或环境快照作为仓库交付文件。

全量共 5251 项，等于 5223 基线加本轮新增 28。原始末尾：

```text
3 failed, 5237 passed, 6 skipped, 29 warnings, 5 errors in 133.26s (0:02:13)
```

其中 **2 个非环境失败**为 F3.5 待裁定的旧期望：

```text
FAILED tests/test_novel_p21_frontend.py::test_character_patch_validates_only_fields_the_user_changes[changes5-None-性格和动机都不能为空]
FAILED tests/test_novel_p21_frontend.py::test_character_patch_validates_only_fields_the_user_changes[changes6-None-性格和动机都不能为空]
E       AssertionError: assert '' == '性格和动机都不能为空'
```

**沙箱端口问题单列**：另外 1 个失败和 5 个 setup 错误分别停在 `asyncio.start_server(..., '127.0.0.1', 0)` 和 `ThreadingHTTPServer` 的 bind，抛出 `PermissionError: [Errno 1] Operation not permitted`，未到业务断言：

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
```

6 个跳过均来自既有 `test_byok_client.py` 的回环用例，分别在 :652（2 个）和 :882（4 个），原测试明确标注 sandbox loopback bind denied。没有改测试、排除节点或将失败重标记为 skip。默认 Turbopack 的端口绑定错误同属环境限制，webpack 补充构建成功不替代默认构建结果。

### 待人工确认

- F3.2 与 F3.5 的三条旧期望如何处理，等待作者裁定；未获明确授权前不改旧测试。
- 在允许回环绑定的环境复跑默认 Turbopack 构建及全量端口用例。
- 按返修单截图复验 solo 说明、运行后草稿清空、无变化状态提示和最近出场中文显示，昼夜主题及 1440/390/360 宽度。

### 裁定后同步

依据作者本轮明确裁定，仅同步本任务尚未提交的以下三条期望；此前「待裁定」和失败输出保留为历史记录。本次已完成 F3.2，保留 F3.5 双边 trim 语义，两处测试契约冲突已消解。

| 获授权的期望 | 改前 → 改后 | 文件证据 |
| --- | --- | --- |
| F3.2，failed 状态 | HTTP 409、detail 严格等于「书正在运行，请先暂停再改人物」 → HTTP 409、detail 严格等于「这本书已出错，不能修改人物」；无写入断言不变 | `backend/novel/service.py:314` 增加 failed 分支；`backend/tests/test_novel_p21_service.py:178` 仅更新 failed 参数文案，`:189` 严格相等断言原样保留 |
| F3.5，changes5，空性格输入纯空格 | 错误「性格和动机都不能为空」 → 无错误、不发 PATCH、就近显示「没有改动」 | `backend/tests/test_novel_p21_frontend.py:120` 更新错误期望；`:152` 起添加严格断言 |
| F3.5，changes6，空动机输入换行 | 错误「性格和动机都不能为空」 → 无错误、不发 PATCH、就近显示「没有改动」 | `backend/tests/test_novel_p21_frontend.py:121` 更新错误期望；`:152` 起添加严格断言 |

前端探针扩展为执行源码中的实际 `onSubmit` 回调、等待 Promise 完成，并从实际 `role=status` JSX 投影提示。对 changes5/6 分别精确断言 `error == ''`、`saved is None`、`calls == 0`、`prevented is True`、`notice == '没有改动'`，以及完整就近提示段落严格相等；没有删除报错断言或改用宽松匹配。原参数化测试中全部既有 assert 文字原样保留，其他参数与其他测试函数不变。

本次仅修改 `backend/novel/service.py`、两个获授权的 P2.1 测试文件及本报告。与裁定同步前快照 `/private/tmp/fiona-p21-ruling-before-qjddo05g` 比对确认：服务实现只新增两行 failed 分支；服务测试只有一个参数字符串变化；前端测试只有两个参数期望变化、必要的实际提交探针扩展及新增严格断言；其他所有测试文件逐字节相同，原有断言源码逐条原样保留。报告仅追加本小节，没有改写前节。未使用 stash，未提交 commit，HEAD 仍为 `2979e2dee98ad0dda1a6e6c0e24ffff478c2bf0e`。

| 按裁定复跑的检查 | 结果 |
| --- | --- |
| `npm run lint` | 退出 0，0 errors、25 warnings |
| `npx tsc --noEmit` | 退出 0，无错误输出 |
| `NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack` | 退出 0，编译、TypeScript、静态页面成功，含三个小说路由 |
| `python -m pytest -q tests/test_novel_p21_*.py` | 全部 P2.1 原新增及返修测试共 157 passed、29 warnings，5.58s，无失败/错误/跳过 |
| 无 node_modules 副本执行同一 P2.1 命令 | 157 passed、29 warnings，4.80s，无失败/错误/跳过 |
| 后端全量 `python -m pytest -q -ra` | 退出 1；5239 passed、1 failed、5 errors、6 skipped、29 warnings，133.75s；未通过/跳过项均为下列既有端口用例 |
| 作者指定复核探针，四个 Key 均为 placeholder，禁用 dotenv | 原探针实际运行，输出 `USER EDIT SURVIVED`，版本来源仍以 user_edit、rearchive:1 结尾 |
| 断言/范围检查 | 通过，仅三条获授权的期望变化；其他原有断言文字不变，基线既有测试 diff 为空；`git diff --check` 通过 |

**端口类结果单列**：全量共 5251 项，原始末尾为 `1 failed, 5239 passed, 6 skipped, 29 warnings, 5 errors in 133.75s (0:02:13)`。1 个失败停在 asyncio 回环监听 bind，5 个 setup 错误停在 ThreadingHTTPServer 的 socket.bind，均为 `PermissionError: [Errno 1] Operation not permitted`：

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
```

6 个跳过仍为 `test_byok_client.py:652` 的 2 项和 `:882` 的 4 项，原测试明确标注 sandbox loopback bind denied。此前两条 F3.5 非环境失败已消失，没有其他功能测试失败。未排除测试、改为宽松匹配或重标记跳过，全量不能记为全部通过。

本次日志为 `/private/tmp/fiona-p21-ruling-{lint,tsc,webpack,pytest-p21,pytest-no-node,pytest-full,probe}.log`。无 node_modules 验证继续使用 `/private/tmp/fiona-p21-fix-r1-no-node-b19cx8xu` 源码副本，同步了本次三个源码/测试文件并确认没有 frontend/node_modules。29 条后端 warning 仍来自既有 slowapi 弃用提示。F1–F3 已无待裁定实现项；全量端口类环境限制和既定截图复验仍需在适合的环境完成。

## 第 2 轮返修

按 `05-fix-r2.md` 完成人名守卫，先写真实路径反证测试、确认修复前失败，再修改实现。未使用 git stash，未提交 commit。

| 本轮文件与行号 | 改动 |
| --- | --- |
| `backend/novel/runner.py:410` | 仅将 `_rearchive` 重放段的一行条件改为 `if target is None or target["name"] != character["name"]:`；同 ID 不同名跳过，同名继续原有三字段差异重放，不按名字回退查找 |
| 新增 `backend/tests/test_novel_p21_fix_r2_runner.py:12` | 一条离线真实路径用例：FastAPI PATCH 临时证人 C3，改最新章并以 dry_run runner 重归档出同 ID 的老张，`:48` 断言老张完整人物卡仍为重建原值；`:46–47` 同时断言同名 C1 的三字段补改仍保留 |
| 本报告 | 仅末尾追加本节，原有记录逐字节保留 |

写测试前保存 `/private/tmp/fiona-p21-r2-before-ftiqcfrn` 快照；比对确认本轮实现只改上述一行，所有开始时已存在的测试文件（包括 P2.1 和第 1 轮返修测试）逐字节不变，没有改任何既有断言、状态机、暂停原因、计费、数据结构或其他代码。

**反证先于修复**：使用指定解释器在 backend 下运行 `-m pytest -q tests/test_novel_p21_fix_r2_runner.py`，未修改 runner 时输出：

```text
E       AssertionError: GRAFTED ONTO UNRELATED CHARACTER: 临时证人的补改覆盖了老张的重建人物卡
FAILED tests/test_novel_p21_fix_r2_runner.py::test_rearchive_skips_user_edits_when_new_character_reuses_id_with_another_name
1 failed, 29 warnings in 1.17s
```

失败前同名 C1 的保留断言已通过；失败 diff 显示老张的外形、性格、动机被临时证人的补改替换。原始反证日志为 `/private/tmp/fiona-p21-r2-counterexample.log`。随后添加守卫，同一测试 `1 passed, 29 warnings in 1.40s`，测试文件没有再改写。

**两个原始复核探针**均以四个占位 Key（DASHSCOPE/DEEPSEEK/ARK/OPENAI 均为 placeholder）、`PYTHON_DOTENV_DISABLED=1`、指定虚拟环境解释器在 backend 下实跑，未修改探针：

```text
probe_v4_new_character_id_reuse.py，修复前：
V4 RESULT: GRAFTED ONTO UNRELATED CHARACTER (corner case)

probe_v4_new_character_id_reuse.py，修复后：
PASS edit made for 临时证人(C3) NOT grafted onto unrelated new character 老张(C3)
V4 RESULT: no graft

probe_rearchive.py，修复后：
USER EDIT SURVIVED
```

V4 修复后的老张保留重建出的花白寸头外形、性格「健谈」、动机「看守仓库」；普通探针仍保留作者修改，版本来源仍以 `user_edit, rearchive:1` 结尾。

| 验证 | 结果 |
| --- | --- |
| P2.1 全部 `-m pytest -q tests/test_novel_p21_*.py` | 158 passed、29 warnings，5.68s，无失败/错误/跳过 |
| 后端全量 `-m pytest -q -ra` | 退出 1；5240 passed、1 failed、5 errors、6 skipped、29 warnings，128.56s；未通过/跳过项均为下列既有端口用例 |
| 范围与断言 | 实现仅一行变化，所有既有测试字节及断言不变，`git diff --check` 通过 |

后端解释器为 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。29 条 warnings 仍为既有 slowapi 的 Python 3.14 弃用提示。本轮日志为 `/private/tmp/fiona-p21-r2-{counterexample,targeted,pytest-p21,pytest-full,probe-v4-before,probe-v4-after,probe-rearchive-before,probe-rearchive-after}.log`，不作为仓库交付文件。

**端口类失败单列**：全量共 5252 项，等于上一轮 5251 加本轮新增 1 项。1 个失败停在 asyncio 回环监听 bind，5 个 setup 错误停在 ThreadingHTTPServer 的 socket.bind，均为 `PermissionError: [Errno 1] Operation not permitted`，未进入相关业务断言：

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 5240 passed, 6 skipped, 29 warnings, 5 errors in 128.56s (0:02:08)
```

6 个跳过仍为 `test_byok_client.py:652` 的 2 项和 `:882` 的 4 项，原测试明确标注 sandbox loopback bind denied。未排除或改写这些测试，不把全量记为全部通过；本轮新用例及 P2.1 全部 158 项均通过。实现无未完成项，端口用例需在允许回环绑定的环境复跑。
